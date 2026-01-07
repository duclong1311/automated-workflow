import os
import json
import logging
import re
import html
import asyncio
from fastapi import FastAPI, Request, BackgroundTasks
from jira import JIRA
from google import genai
from dotenv import load_dotenv
from common import GEMINI_PARSE_PROMPT, Messages, Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
app = FastAPI()

# Lấy biến môi trường
JIRA_SERVER = os.getenv("JIRA_SERVER", "").strip()
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "").strip()
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# Khởi tạo Jira
jira = None
try:
    jira = JIRA(server=JIRA_SERVER, token_auth=JIRA_API_TOKEN)
    logger.info("✅ Kết nối Jira thành công.")
except Exception as e:
    logger.error(f"❌ Lỗi kết nối Jira: {e}")

client_ai = None
try:
    client_ai = genai.Client(api_key=GEMINI_API_KEY)
    logger.info("✅ Kết nối Gemini AI thành công.")
except Exception as e:
    logger.error(f"❌ Lỗi kết nối Gemini AI: {e}")

def clean_teams_message(raw_text):
    """Làm sạch HTML message từ Teams và parse mention tags"""
    # Bước 1: Tìm và ghép các mention tags liên tiếp thành tên đầy đủ
    at_pattern = r'<at[^>]*>([^<]+)</at>'
    mentions = []
    for match in re.finditer(at_pattern, raw_text):
        mention_text = match.group(1).strip()
        mention_text = html.unescape(mention_text)
        if len(mention_text) <= 50 and not re.search(r'[\[\]※]', mention_text):
            mentions.append(mention_text)
    
    # Tìm các mention tags liên tiếp có vẻ là tên (trước "và" hoặc "epic link")
    # Tìm vị trí của "gắn cho" hoặc "gán cho"
    assignee_from_mentions = None
    gắn_cho_pattern = r'(?:gắn|gán)\s+(?:cho|task\s+này\s+cho)'
    gắn_match = re.search(gắn_cho_pattern, raw_text, re.IGNORECASE)
    
    if gắn_match:
        # Tìm các mention tags sau "gắn cho" và trước "và" hoặc "epic link"
        start_pos = gắn_match.end()
        end_pattern = r'(?:\s+và|\s+and|epic\s+link|$)'
        end_match = re.search(end_pattern, raw_text[start_pos:], re.IGNORECASE)
        end_pos = start_pos + (end_match.start() if end_match else len(raw_text))
        
        # Lấy phần text giữa "gắn cho" và "và/epic link"
        text_between = raw_text[start_pos:end_pos]
        
        # Tìm tất cả mention tags trong phần này
        name_parts = []
        for match in re.finditer(at_pattern, text_between):
            mention_text = match.group(1).strip()
            mention_text = html.unescape(mention_text)
            # Loại bỏ phần trong ngoặc đơn
            if not mention_text.startswith('(') and not mention_text.endswith(')'):
                if len(mention_text) <= 20 and not re.search(r'[\(\)\[\]※]', mention_text):
                    name_parts.append(mention_text)
        
        if name_parts:
            # Ghép các phần thành tên đầy đủ
            assignee_from_mentions = ' '.join(name_parts).strip()
    
    # Bước 2: Tìm pattern "gán cho X" trong text (sau khi thay thế mention tags)
    # Thay thế tất cả mention tags bằng text để dễ tìm pattern
    text_with_mentions_replaced = raw_text
    for match in re.finditer(at_pattern, raw_text):
        mention_text = match.group(1).strip()
        mention_text = html.unescape(mention_text)
        # Thay thế bằng text, giữ nguyên khoảng trắng
        text_with_mentions_replaced = text_with_mentions_replaced.replace(match.group(0), mention_text)
    
    # Thay thế &nbsp; bằng space
    text_with_mentions_replaced = text_with_mentions_replaced.replace('&nbsp;', ' ')
    text_with_mentions_replaced = html.unescape(text_with_mentions_replaced)
    
    assignee_from_text = None
    assignee_patterns = [
        r'tạo\s+task\s+gắn\s+cho\s+([^\n,<]+?)(?:\s+và|\s+and|epic|$)',  # "tạo task gắn cho X"
        r'gắn\s+cho\s+([^\n,<]+?)(?:\s+và|\s+and|epic|$)',  # "gắn cho X"
        r'gán\s+(?:task\s+này\s+)?cho\s+([^\n,<]+?)(?:\s+và|\s+and|epic|$)',  # "gán cho X"
    ]
    
    for pattern in assignee_patterns:
        match = re.search(pattern, text_with_mentions_replaced, re.IGNORECASE)
        if match:
            assignee_from_text = match.group(1).strip()
            # Loại bỏ HTML tags nếu có
            assignee_from_text = re.sub(r'<[^>]+>', '', assignee_from_text)
            assignee_from_text = html.unescape(assignee_from_text)
            # Loại bỏ phần trong ngoặc đơn
            assignee_from_text = re.sub(r'\s*\([^)]+\)', '', assignee_from_text).strip()
            if assignee_from_text and len(assignee_from_text) > 2:
                break
    
    # Ưu tiên dùng assignee từ mention tags nếu có (thường chính xác hơn)
    assignee_from_text = assignee_from_mentions if assignee_from_mentions else assignee_from_text
    
    # Parse mention tags (chỉ lấy mention thực sự - tên người)
    # Teams mention format: <at>Name</at> hoặc <at id="...">Name</at>
    mentions = []
    
    # Tìm tất cả mention tags: <at>Name</at> hoặc <at id="...">Name</at>
    # Chỉ lấy những mention có vẻ là tên người (không quá dài, không có ký tự đặc biệt nhiều)
    at_pattern = r'<at[^>]*>([^<]+)</at>'
    for match in re.finditer(at_pattern, raw_text):
        mention_text = match.group(1).strip()
        # Clean HTML entities
        mention_text = html.unescape(mention_text)
        # Chỉ lấy mention nếu có vẻ là tên người (không quá 50 ký tự, không chứa nhiều ký tự đặc biệt)
        if len(mention_text) <= 50 and not re.search(r'[\[\]※]', mention_text):
            mentions.append(mention_text)
            # Thay thế bằng text đơn giản để dễ parse
            raw_text = raw_text.replace(match.group(0), mention_text)
    
    # Clean HTML
    clean = re.sub(r'</p>|</div>|<br\s*/?>|</li>', '\n', raw_text)
    clean = re.sub(r'<[^>]+>', '', clean)
    clean = html.unescape(clean)
    clean = '\n'.join(line.strip() for line in clean.split('\n'))
    clean = re.sub(r'\n\n+', '\n\n', clean).strip()
    
    # Nếu có mentions hợp lệ VÀ chưa tìm thấy assignee từ text gốc
    if mentions and not assignee_from_text:
        # Lọc mentions - chỉ lấy những cái có vẻ là tên người (không phải bot, không phải text dài)
        valid_mentions = [m.strip() for m in mentions if m.lower() != 'jirabot' and len(m.strip()) <= 30 and not m.strip().startswith('[') and not re.search(r'[\[\]※&nbsp;]', m)]
        
        # Ghép các từ liên tiếp thành tên đầy đủ (ví dụ: "Trần", "Đức", "Long" -> "Trần Đức Long")
        if valid_mentions:
            # Tìm các từ liên tiếp có vẻ là tên (không có ký tự đặc biệt, không quá ngắn)
            full_names = []
            current_name_parts = []
            
            for mention in valid_mentions:
                # Clean mention
                mention_clean = re.sub(r'[&nbsp;\xa0]', ' ', mention).strip()
                # Nếu là từ đơn (không có space, không có ký tự đặc biệt, độ dài hợp lý)
                if len(mention_clean) > 0 and len(mention_clean) <= 20 and not re.search(r'[\(\)\[\]※]', mention_clean):
                    if not mention_clean.startswith('(') and not mention_clean.endswith(')'):
                        current_name_parts.append(mention_clean)
                    else:
                        # Nếu có phần trong ngoặc, kết thúc tên hiện tại
                        if current_name_parts:
                            full_names.append(' '.join(current_name_parts))
                            current_name_parts = []
                else:
                    # Nếu không phải từ đơn, kết thúc tên hiện tại
                    if current_name_parts:
                        full_names.append(' '.join(current_name_parts))
                        current_name_parts = []
                    # Nếu là tên đầy đủ (có space hoặc dài), thêm trực tiếp
                    if len(mention_clean) > 3 and (' ' in mention_clean or len(mention_clean) > 10):
                        full_names.append(mention_clean)
            
            # Thêm tên cuối cùng nếu còn
            if current_name_parts:
                full_names.append(' '.join(current_name_parts))
            
            # Lọc lại - chỉ lấy tên có vẻ hợp lệ (không quá ngắn, không có ký tự đặc biệt)
            final_mentions = [name for name in full_names if len(name) >= 3 and len(name) <= 50 and not re.search(r'[\[\]※]', name)]
            
            if final_mentions:
                # Ưu tiên dùng assignee từ text gốc nếu có (đã ghép từ mention tags)
                if assignee_from_text:
                    # Tìm pattern "gán cho X" hoặc "gắn cho X" trong text để thay thế
                    assignee_match = re.search(r'(?:gán|gắn)\s+(?:task\s+này\s+)?cho\s+([^\n,]+?)(?:\s+và|\s+and|$)', clean, re.IGNORECASE)
                    if assignee_match:
                        # Thay thế bằng tên đầy đủ từ text gốc
                        old_text = assignee_match.group(0)
                        new_text = f"gán cho {assignee_from_text}"
                        clean = clean.replace(old_text, new_text)
                    else:
                        # Nếu không tìm thấy, thêm vào
                        clean = f"{clean}\ngán cho {assignee_from_text}"
                else:
                    # Tìm pattern "gán cho X" trong text để lấy tên đầy đủ
                    assignee_match = re.search(r'gán\s+(?:task\s+này\s+)?cho\s+([^\n,]+?)(?:\s+và|\s+and|$)', clean, re.IGNORECASE)
                    if not assignee_match:
                        # Nếu text không có "gán cho" hoặc "assign to", thêm mention vào
                        # Chỉ thêm nếu tên đủ dài (ít nhất 2 từ)
                        best_mention = None
                        for mention in final_mentions:
                            if len(mention.split()) >= 2:  # Ít nhất 2 từ
                                best_mention = mention
                                break
                        if not best_mention and final_mentions:
                            best_mention = final_mentions[0]
                        
                        if best_mention:
                            clean = f"{clean}\ngán cho {best_mention}"
    
    return clean

def ask_gemini_to_parse_task(text):
    """Phân tích task với timeout 1s"""
    try:
        prompt = GEMINI_PARSE_PROMPT.format(text=text)
        
        response = client_ai.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config={
                'response_mime_type': 'application/json',
                'temperature': 0.1,  # Giảm creativity để nhanh hơn
            }
        )
        
        # Parse JSON an toàn
        response_text = response.text.strip()
        
        # Xóa markdown code block nếu có
        if response_text.startswith('```'):
            response_text = re.sub(r'^```(?:json)?\s*', '', response_text)
            response_text = re.sub(r'\s*```$', '', response_text)
        
        # Parse JSON
        result = json.loads(response_text)
        
        # Validate required fields
        if not result.get('summary'):
            result['summary'] = text.split('\n')[0][:100]  
        if not result.get('issuetype'):
            result['issuetype'] = 'Task'
        if not result.get('description'):
            result['description'] = text
        if not result.get('priority'):
            result['priority'] = 'Medium'
        if 'epic_link' not in result:
            result['epic_link'] = None
        if 'assignee' not in result:
            result['assignee'] = None
        
        # Clean epic_link và assignee
        if result.get('epic_link'):
            epic_link_value = result['epic_link']
            if isinstance(epic_link_value, str):
                # Loại bỏ các từ thừa ở cuối
                epic_link_value = re.sub(r'\s+(?:và|and|cho|to|for).*$', '', epic_link_value, flags=re.IGNORECASE).strip()
                result['epic_link'] = epic_link_value if epic_link_value else None
            elif not epic_link_value:
                result['epic_link'] = None
        else:
            result['epic_link'] = None
        
        if result.get('assignee'):
            assignee_value = result['assignee']
            if isinstance(assignee_value, str):
                # Loại bỏ phần trong ngoặc đơn (như "(KHN.SBU3.DEV)")
                assignee_value_after_paren = re.sub(r'\s*\([^)]+\)', '', assignee_value).strip()
                # Loại bỏ các từ thừa ở cuối
                assignee_value = re.sub(r'\s+(?:và|and|cho|to|for).*$', '', assignee_value_after_paren, flags=re.IGNORECASE).strip()
                result['assignee'] = assignee_value if assignee_value else None
            elif not assignee_value:
                result['assignee'] = None
        else:
            result['assignee'] = None
        
        # Clean description: loại bỏ phần instruction về assignee và epic link
        if result.get('description'):
            description = result['description']
            # Loại bỏ các dòng chứa instruction
            lines = description.split('\n')
            cleaned_lines = []
            for line in lines:
                # Loại bỏ dòng chứa "gán", "assign", "epic link", "hãy gán"
                if not re.search(r'(gán|assign|epic\s+link|hãy\s+gán)', line, re.IGNORECASE):
                    cleaned_lines.append(line)
            result['description'] = '\n'.join(cleaned_lines).strip()
        
        # IMPORTANT: Nếu có epic_link thì phải là Task, không phải Epic
        # (epic_link = liên kết với epic có sẵn, không phải tạo Epic mới)
        if result.get('epic_link') and result.get('issuetype') == 'Epic':
            logger.warning(f"⚠️ Có epic_link nhưng issuetype là Epic, đổi thành Task")
            result['issuetype'] = 'Task'
            
        logger.info(f"✅ Parsed task: {result.get('issuetype')} - {result.get('summary')[:50]}")
        if result.get('epic_link'):
            logger.info(f"   Epic link: {result.get('epic_link')}")
        if result.get('assignee'):
            logger.info(f"   Assignee: {result.get('assignee')}")
        return result
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ JSON Parse Error: {e}")
        logger.error(f"   Response text: {response.text[:500]}")
        # Fallback: dùng quick_parse để giữ lại epic link và assignee
        logger.warning("⚠️ Dùng fallback parsing do JSON error")
        return quick_parse_fallback(text)
    except AttributeError as e:
        logger.error(f"❌ Response Error: {e}")
        logger.error(f"   Check if response object valid")
        # Fallback: dùng quick_parse để giữ lại epic link và assignee
        logger.warning("⚠️ Dùng fallback parsing do AttributeError")
        return quick_parse_fallback(text)
    except Exception as e:
        logger.error(f"❌ Gemini Error: {type(e).__name__}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # Fallback: dùng quick_parse để giữ lại epic link và assignee
        logger.warning("⚠️ Dùng fallback parsing do exception")
        return quick_parse_fallback(text)

def quick_parse_fallback(text):
    """Parse nhanh bằng regex khi AI timeout"""
    summary = text.split('\n')[0][:200] if text else 'No summary'
    
    # Detect issue type - cẩn thận với "epic link" vs "tạo Epic"
    text_lower = text.lower()
    if 'bug' in text_lower or 'lỗi' in text_lower:
        issue_type = 'Bug'
    elif 'tạo epic' in text_lower or 'create epic' in text_lower or text_lower.strip().startswith('epic:'):
        issue_type = 'Epic'
    elif 'improvement' in text_lower:
        issue_type = 'Improvement'
    else:
        issue_type = 'Task'  
    
    # Tìm epic link và assignee bằng regex
    epic_link = None
    assignee = None
    
    # Tìm epic link - lấy toàn bộ text sau "epic link đến" hoặc "epic link"
    # Thử nhiều pattern để tìm epic link
    epic_patterns = [
        r'epic\s+link\s+(?:đến|to)\s+([^\n,]+?)(?:\s+và|\s+and|$)',  # "epic link đến X"
        r'epic\s+link\s+([^\n,]+?)(?:\s+và|\s+and|$)',  # "epic link X"
        r'epic\s*[:\-=]\s*([^\n,]+?)(?:\s+và|\s+and|$)',  # "epic: X"
        r'link\s+(?:đến|to)\s+epic\s+([^\n,]+?)(?:\s+và|\s+and|$)',  # "link đến epic X"
        r'epic\s+link\s+(?:đến|to)\s+([^\n]+?)(?:\n|$)',  # Lấy đến hết dòng
        r'epic\s+link\s+([^\n]+?)(?:\n|$)',  # Lấy đến hết dòng
    ]
    for pattern in epic_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            epic_link = match.group(1).strip()
            # Loại bỏ các từ thừa ở cuối
            epic_link = re.sub(r'\s+(?:và|and|cho|to|for).*$', '', epic_link, flags=re.IGNORECASE)
            # Loại bỏ các ký tự đặc biệt ở đầu/cuối
            epic_link = epic_link.strip('.,;:!?')
            if epic_link:
                break
    
    # Tìm assignee - thử nhiều pattern, ưu tiên lấy tên đầy đủ
    assignee_patterns = [
        r'gán\s+(?:task\s+này\s+)?cho\s+([^\n,]+?)(?:\s+và|\s+and|$)',  # "gán cho X"
        r'gắn\s+cho\s+([^\n,]+?)(?:\s+và|\s+and|$)',  # "gắn cho X"
        r'tạo\s+task\s+gắn\s+cho\s+([^\n,]+?)(?:\s+và|\s+and|$)',  # "tạo task gắn cho X"
        r'gán\s+(?:task\s+này\s+)?cho\s+([^\n]+?)(?:\s+và|\s+and|\n|$)',  # "gán cho X" (lấy đến hết dòng)
        r'assign\s+(?:to|for)?\s+([^\n,]+?)(?:\s+và|\s+and|$)',  # "assign to X"
        r'assignee\s*[:\-=]\s*([^\n,]+?)(?:\s+và|\s+and|$)',  # "assignee: X"
    ]
    for pattern in assignee_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            assignee = match.group(1).strip()
            # Loại bỏ phần trong ngoặc đơn (như "(KHN.SBU3.DEV)")
            assignee = re.sub(r'\s*\([^)]+\)', '', assignee)
            # Loại bỏ các từ thừa ở cuối
            assignee = re.sub(r'\s+(?:và|and|cho|to|for).*$', '', assignee, flags=re.IGNORECASE)
            # Loại bỏ các ký tự đặc biệt ở đầu/cuối
            assignee = assignee.strip('.,;:!?')
            if assignee and len(assignee) > 0:
                break
    
    # Nếu có epic_link thì phải là Task
    if epic_link and issue_type == 'Epic':
        issue_type = 'Task'
    
    # Clean description: loại bỏ phần instruction về assignee và epic link
    description = text
    if description:
        # Loại bỏ các dòng chứa instruction
        lines = description.split('\n')
        cleaned_lines = []
        for line in lines:
            # Loại bỏ dòng chứa "gán", "assign", "epic link", "hãy gán"
            if not re.search(r'(gán|assign|epic\s+link|hãy\s+gán)', line, re.IGNORECASE):
                cleaned_lines.append(line)
        description = '\n'.join(cleaned_lines).strip()
    
    return {
        'summary': summary,
        'issuetype': issue_type,
        'description': description,
        'priority': 'Medium',
        'epic_link': epic_link,
        'assignee': assignee
    }

def find_epic(epic_identifier):
    """Tìm epic trong Jira theo key hoặc name"""
    if not epic_identifier or not jira:
        logger.warning("⚠️ Epic identifier rỗng hoặc Jira chưa kết nối")
        return None
    
    epic_identifier = epic_identifier.strip()
    
    try:
        # Nếu là epic key (format: PROJ-123)
        if re.match(r'^[A-Z]+-\d+$', epic_identifier):
            try:
                epic = jira.issue(epic_identifier)
                if epic.fields.issuetype.name == 'Epic':
                    logger.info(f"✅ Tìm thấy epic theo key: {epic.key} - {epic.fields.summary}")
                    return epic
                else:
                    logger.warning(f"⚠️ {epic_identifier} không phải là Epic (type: {epic.fields.issuetype.name})")
            except Exception as e:
                logger.warning(f"⚠️ Không tìm thấy epic key {epic_identifier}: {e}")
        
        # Chuẩn hóa epic identifier 
        epic_normalized = epic_identifier.upper().replace('-', '').replace('_', '')
        
        # Tìm theo epic name trong project
        # Thử nhiều cách tìm (không dùng ~ với key vì không hỗ trợ)
        search_queries = [
            f'project = {JIRA_PROJECT_KEY} AND issuetype = Epic AND summary ~ "{epic_identifier}"',
            f'project = {JIRA_PROJECT_KEY} AND issuetype = Epic AND summary ~ "{epic_normalized}"',
        ]
        
        # Nếu epic_identifier có thể là key, thử tìm theo key trực tiếp
        if re.match(r'^[A-Z]+-\d+$', epic_identifier):
            search_queries.insert(0, f'project = {JIRA_PROJECT_KEY} AND issuetype = Epic AND key = "{epic_identifier}"')
        
        for jql in search_queries:
            try:
                epics = jira.search_issues(jql, maxResults=10)
                
                if epics:
                    # Tìm exact match trước (theo summary hoặc key)
                    for epic in epics:
                        epic_summary_upper = epic.fields.summary.upper().replace('-', '').replace('_', '')
                        epic_key_upper = epic.key.upper().replace('-', '')
                        
                        # So sánh normalized
                        if (epic_normalized in epic_summary_upper or 
                            epic_normalized in epic_key_upper or
                            epic_identifier.upper() in epic.fields.summary.upper() or
                            epic_identifier.upper() == epic.key.upper()):
                            logger.info(f"✅ Tìm thấy epic theo name: {epic.key} - {epic.fields.summary}")
                            return epic
                    
                    # Nếu không có exact match, lấy cái đầu tiên
                    logger.info(f"✅ Tìm thấy epic (lấy đầu tiên): {epics[0].key} - {epics[0].fields.summary}")
                    return epics[0]
            except Exception as e:
                logger.warning(f"⚠️ Lỗi khi tìm với JQL {jql}: {e}")
                continue
        
        logger.warning(f"⚠️ Không tìm thấy epic: {epic_identifier}")
        return None
    except Exception as e:
        logger.error(f"❌ Lỗi khi tìm epic: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None

def find_epic_link_field_id(issue):
    """Tìm field ID của epic link field"""
    try:
        # Thử các field ID phổ biến trước (nhanh hơn)
        common_epic_fields = ['customfield_10014', 'customfield_10011', 'customfield_10016', 'customfield_10020', 'customfield_10104']
        issue_fields = issue.raw['fields']
        
        for field_id in common_epic_fields:
            if field_id in issue_fields:
                logger.info(f"✅ Tìm thấy epic link field: {field_id}")
                return field_id
        
        # Nếu không tìm thấy, thử tìm trong danh sách fields của Jira
        try:
            fields = jira.fields()
            for field in fields:
                if field['name'].lower() in ['epic link', 'parent link', 'epic']:
                    logger.info(f"✅ Tìm thấy epic link field: {field['name']} ({field['id']})")
                    return field['id']
        except:
            pass
        
        logger.warning(f"⚠️ Không tìm thấy epic link field, sẽ thử với field phổ biến nhất")
        # Trả về field phổ biến nhất để thử
        return 'customfield_10014'
    except Exception as e:
        logger.warning(f"⚠️ Không thể tìm epic link field: {e}")
        return 'customfield_10014'  # Fallback

def update_issue_async(issue_key, epic_link=None, assignee=None):
    """Cập nhật issue với epic link và assignee trong background"""
    logger.info(f"🔄 Bắt đầu cập nhật {issue_key}: epic={epic_link}, assignee={assignee}")
    
    try:
        issue = jira.issue(issue_key)
        update_fields = {}
        
        # Gắn epic link - PHẢI tìm trên Jira trước
        if epic_link:
            epic = find_epic(epic_link)
            if epic:
                logger.info(f"✅ Đã tìm thấy epic: {epic.key} - {epic.fields.summary}")
                # Tìm epic link field ID
                epic_field_id = find_epic_link_field_id(issue)
                
                if epic_field_id:
                    # Thử nhiều format khác nhau
                    formats_to_try = [
                        epic.key,  # Format 1: string key
                        {'key': epic.key},  # Format 2: dict với key
                        {'id': epic.id},  # Format 3: dict với id
                    ]
                    
                    epic_set = False
                    for fmt in formats_to_try:
                        try:
                            update_fields[epic_field_id] = fmt
                            epic_set = True
                            break
                        except Exception as e:
                            continue
                    
                    if not epic_set:
                        logger.error(f"❌ Không thể set epic link cho epic {epic.key}")
            else:
                logger.error(f"❌ KHÔNG tìm thấy epic '{epic_link}' trên Jira")
        
        # Gắn assignee - PHẢI tìm trên Jira trước
        if assignee:
            # Clean assignee: loại bỏ phần trong ngoặc đơn và thay thế \xa0 bằng space
            assignee_clean = assignee.replace('\xa0', ' ').replace('\u00a0', ' ')  # Thay non-breaking space
            assignee_clean = re.sub(r'\s*\([^)]+\)', '', assignee_clean).strip()
            assignee_clean = re.sub(r'\s+', ' ', assignee_clean)  # Normalize spaces
            try:
                # Tìm user trên Jira theo nhiều cách
                users = []
                
                # Tạo nhiều search queries khác nhau
                search_queries = []
                
                # 1. Tên đầy đủ đã clean
                search_queries.append(assignee_clean)
                
                # 2. Tên gốc
                search_queries.append(assignee)
                
                # 3. Từng phần của tên (nếu có nhiều từ)
                name_parts = assignee_clean.split()
                if len(name_parts) > 1:
                    # Thử với họ và tên (2 từ đầu)
                    if len(name_parts) >= 2:
                        search_queries.append(f"{name_parts[0]} {name_parts[1]}")
                    # Thử với tên cuối (có thể là username)
                    search_queries.append(name_parts[-1])
                
                # 4. Loại bỏ dấu tiếng Việt và lowercase
                import unicodedata
                def remove_accents(text):
                    nfd = unicodedata.normalize('NFD', text)
                    return ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')
                
                assignee_no_accent = remove_accents(assignee_clean).lower()
                if assignee_no_accent != assignee_clean.lower():
                    search_queries.append(assignee_no_accent)
                
                # 5. Chỉ tên cuối (có thể là username)
                if len(name_parts) > 1:
                    last_name_no_accent = remove_accents(name_parts[-1]).lower()
                    search_queries.append(last_name_no_accent)
                
                # Loại bỏ duplicates
                search_queries = list(dict.fromkeys(search_queries))
                
                # Thử từng query
                for query in search_queries:
                    try:
                        users = jira.search_users(query, maxResults=10)
                        if users:
                            break
                    except Exception as e:
                        continue
                
                if users:
                    # Tìm user phù hợp nhất (exact match hoặc partial match)
                    matched_user = None
                    assignee_lower = assignee_clean.lower().strip()
                    
                    # Import để loại bỏ dấu
                    import unicodedata
                    def remove_accents(text):
                        nfd = unicodedata.normalize('NFD', text)
                        return ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')
                    
                    assignee_no_accent = remove_accents(assignee_lower)
                    
                    for user in users:
                        # Kiểm tra displayName - ưu tiên exact match
                        if hasattr(user, 'displayName') and user.displayName:
                            user_display = user.displayName
                            # Loại bỏ phần trong ngoặc đơn khi so sánh
                            user_display_clean = re.sub(r'\s*\([^)]+\)', '', user_display).strip()
                            user_display_clean = user_display_clean.replace('\xa0', ' ').replace('\u00a0', ' ')
                            user_display_clean = re.sub(r'\s+', ' ', user_display_clean)
                            user_display_lower = user_display_clean.lower()
                            user_display_no_accent = remove_accents(user_display_lower)
                            
                            # So sánh với nhiều cách
                            match_reasons = []
                            if assignee_lower == user_display_lower:
                                match_reasons.append("exact match")
                            elif assignee_no_accent == user_display_no_accent:
                                match_reasons.append("exact match (no accent)")
                            elif assignee_lower in user_display_lower:
                                match_reasons.append("assignee in displayName")
                            elif assignee_no_accent in user_display_no_accent:
                                match_reasons.append("assignee in displayName (no accent)")
                            else:
                                # So sánh từng từ: nếu tất cả từ trong assignee đều có trong displayName
                                assignee_words = set(assignee_lower.split())
                                display_words = set(user_display_lower.split())
                                if assignee_words and assignee_words.issubset(display_words):
                                    match_reasons.append("all words match")
                            
                            if match_reasons:
                                matched_user = user
                                logger.info(f"✅ Tìm thấy user: {user.displayName}")
                                break
                        
                        # Kiểm tra emailAddress
                        if not matched_user and hasattr(user, 'emailAddress') and user.emailAddress:
                            if assignee_lower in user.emailAddress.lower():
                                matched_user = user
                                logger.info(f"✅ Tìm thấy user theo email: {user.emailAddress}")
                                break
                        
                        # Kiểm tra name
                        if not matched_user and hasattr(user, 'name') and user.name:
                            user_name_lower = user.name.lower()
                            user_name_no_accent = remove_accents(user_name_lower)
                            
                            if (assignee_lower == user_name_lower or
                                assignee_no_accent == user_name_no_accent or
                                assignee_lower in user_name_lower):
                                matched_user = user
                                logger.info(f"✅ Tìm thấy user theo name: {user.name}")
                                break
                    
                    # Nếu không có exact match, lấy user đầu tiên
                    if not matched_user and users:
                        matched_user = users[0]
                        logger.info(f"✅ Lấy user đầu tiên: {matched_user.displayName if hasattr(matched_user, 'displayName') else matched_user.name}")
                    
                    if matched_user:
                        # Thử nhiều format để gắn assignee
                        assignee_formats = []
                        
                        # Format 1: accountId (Jira Cloud)
                        if hasattr(matched_user, 'accountId') and matched_user.accountId:
                            assignee_formats.append({'accountId': matched_user.accountId})
                        
                        # Format 2: name (Jira Server)
                        if hasattr(matched_user, 'name') and matched_user.name:
                            assignee_formats.append({'name': matched_user.name})
                        
                        # Format 3: key
                        if hasattr(matched_user, 'key') and matched_user.key:
                            assignee_formats.append({'name': matched_user.key})
                        
                        # Format 4: emailAddress
                        if hasattr(matched_user, 'emailAddress') and matched_user.emailAddress:
                            assignee_formats.append({'name': matched_user.emailAddress})
                        
                        # Thử từng format
                        assignee_set = False
                        for fmt in assignee_formats:
                            try:
                                update_fields['assignee'] = fmt
                                assignee_set = True
                                logger.info(f"✅ Đã set assignee: {matched_user.displayName if hasattr(matched_user, 'displayName') else matched_user.name}")
                                break
                            except Exception as e:
                                continue
                        
                        if not assignee_set:
                            logger.error(f"❌ Không thể set assignee cho user {matched_user}")
                    else:
                        logger.error(f"❌ KHÔNG tìm thấy user '{assignee_clean}' trên Jira")
                else:
                    logger.error(f"❌ KHÔNG tìm thấy user '{assignee}' trên Jira")
                        
            except Exception as e:
                logger.error(f"❌ Lỗi khi tìm/gắn assignee: {e}")
                import traceback
                logger.error(traceback.format_exc())
        
        # Cập nhật issue nếu có thay đổi
        if update_fields:
            logger.info(f"📝 Cập nhật {issue_key} với fields: {update_fields}")
            try:
                issue.update(fields=update_fields)
                logger.info(f"✅ Đã cập nhật thành công {issue_key}")
            except Exception as e:
                logger.error(f"❌ Lỗi khi update issue: {e}")
                import traceback
                logger.error(traceback.format_exc())
        else:
            logger.info(f"ℹ️ Không có gì để cập nhật cho {issue_key}")
            
    except Exception as e:
        logger.error(f"❌ Lỗi khi cập nhật issue {issue_key}: {e}")
        import traceback
        logger.error(traceback.format_exc())

async def process_with_timeout(message_text, background_tasks: BackgroundTasks):
    """Xử lý với timeout để đảm bảo response trong <5s"""
    import time
    start_time = time.time()
    
    try:
        # Wrap blocking call trong thread executor
        loop = asyncio.get_event_loop()
        
        # 1. AI phân tích (KHÔNG timeout riêng, để tổng timeout quản lý)
        ai_start = time.time()
        try:
            task_info = await asyncio.wait_for(
                loop.run_in_executor(None, ask_gemini_to_parse_task, message_text),
                timeout=Config.AI_TIMEOUT  # 2.8s cho AI
            )
        except asyncio.TimeoutError:
            logger.warning("⚠️ AI timeout, dùng fallback parsing")
            task_info = quick_parse_fallback(message_text)
        
        ai_time = time.time() - ai_start
        logger.info(f"⏱️ AI processing time: {ai_time:.2f}s")
        
        if not task_info:
            task_info = quick_parse_fallback(message_text)

        # 2. Tạo Jira issue nhanh (chỉ với thông tin cơ bản để tránh timeout)
        summary = task_info.get('summary', 'No summary')
        issue_type = task_info.get('issuetype', 'Task')
        
        # Tạo issue dict với minimal fields trước
        issue_dict = {
            'project': {'key': JIRA_PROJECT_KEY},
            'issuetype': {'name': issue_type}
        }
        
        # Thêm các field khác (có thể bị lỗi nếu screen không cho phép)
        try:
            issue_dict['summary'] = summary
            issue_dict['description'] = task_info.get('description', 'No description')
            issue_dict['priority'] = {'name': task_info.get('priority', 'Medium')}
        except Exception as e:
            logger.warning(f"⚠️ Không thể thêm một số fields: {e}")

        # Nếu là Epic, bắt buộc phải có Epic Name
        if issue_type == 'Epic':
            try:
                issue_dict['customfield_10104'] = summary
            except:
                pass

        # Tạo issue ngay lập tức
        jira_start = time.time()
        try:
            new_issue = await loop.run_in_executor(
                None, 
                lambda: jira.create_issue(fields=issue_dict)
            )
        except Exception as e:
            # Nếu lỗi do fields không được phép, thử với minimal fields
            error_str = str(e)
            if 'cannot be set' in error_str or 'not on the appropriate screen' in error_str:
                logger.warning(f"⚠️ Một số fields không được phép, thử với minimal fields...")
                minimal_dict = {
                    'project': {'key': JIRA_PROJECT_KEY},
                    'issuetype': {'name': issue_type}
                }
                try:
                    new_issue = await loop.run_in_executor(
                        None,
                        lambda: jira.create_issue(fields=minimal_dict)
                    )
                    # Sau đó update với các field khác trong background
                    update_fields = {}
                    if summary:
                        update_fields['summary'] = summary
                    if task_info.get('description'):
                        update_fields['description'] = task_info.get('description')
                    if update_fields:
                        try:
                            new_issue.update(fields=update_fields)
                        except Exception as e2:
                            logger.warning(f"⚠️ Không thể update fields sau khi tạo: {e2}")
                except Exception as e2:
                    logger.error(f"❌ Lỗi khi tạo issue với minimal fields: {e2}")
                    raise
            else:
                raise
        
        jira_time = time.time() - jira_start
        logger.info(f"⏱️ Jira create time: {jira_time:.2f}s")
        
        issue_url = f"{JIRA_SERVER}/browse/{new_issue.key}"
        
        # 3. Thêm background task để cập nhật epic link và assignee
        epic_link = task_info.get('epic_link')
        assignee = task_info.get('assignee')
        
        # Normalize: nếu epic_link là empty string hoặc None, set thành None
        if epic_link and isinstance(epic_link, str) and epic_link.strip():
            epic_link = epic_link.strip()
        else:
            epic_link = None
            
        if assignee and isinstance(assignee, str) and assignee.strip():
            # Clean non-breaking space và normalize
            assignee = assignee.replace('\xa0', ' ').replace('\u00a0', ' ')
            assignee = re.sub(r'\s+', ' ', assignee).strip()
        else:
            assignee = None
        
        if epic_link or assignee:
            logger.info(f"📋 Sẽ cập nhật {new_issue.key} trong background: epic={epic_link}, assignee={assignee}")
            # FastAPI BackgroundTasks có thể chạy sync function trực tiếp
            background_tasks.add_task(update_issue_async, new_issue.key, epic_link, assignee)
        else:
            logger.info(f"ℹ️ Không có epic_link hoặc assignee để cập nhật cho {new_issue.key}")
        
        total_time = time.time() - start_time
        logger.info(f"⏱️ Total processing time: {total_time:.2f}s")
        
        return {
            "success": True,
            "message": Messages.success(issue_type, new_issue.key, issue_url, summary),
            "issue_key": new_issue.key
        }
        
    except asyncio.TimeoutError:
        elapsed = time.time() - start_time
        logger.error(f"❌ Timeout khi xử lý request sau {elapsed:.2f}s")
        return {"success": False, "message": Messages.error("Quá thời gian xử lý (>5s)")}
    except Exception as e:
        logger.error(f"❌ Lỗi: {e}")
        return {"success": False, "message": Messages.error(str(e))}

@app.post("/webhook/teams")
async def teams_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        data = await request.json()
        raw_text = data.get("text", "")
        message_text = clean_teams_message(raw_text)
        
        # Bỏ tag mention của bot
        message_text = message_text.replace(Config.BOT_MENTION_NAME, "").strip()

        # Xử lý với timeout tổng 4s (để đảm bảo response <5s)
        result = await asyncio.wait_for(
            process_with_timeout(message_text, background_tasks),
            timeout=Config.WEBHOOK_RESPONSE_TIMEOUT
        )
        
        return {
            "type": "message",
            "text": result["message"]
        }
        
    except asyncio.TimeoutError:
        logger.error("❌ Webhook timeout")
        return {
            "type": "message",
            "text": Messages.error("Webhook timeout (>5s)")
        }
    except Exception as e:
        logger.error(f"❌ Lỗi webhook: {e}")
        return {
            "type": "message",
            "text": Messages.error(str(e))
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)