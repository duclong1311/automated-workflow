import os
import json
import logging
import re
import html
import asyncio
import requests
from io import BytesIO
from datetime import datetime
from fastapi import FastAPI, Request, BackgroundTasks
from jira import JIRA
from google import genai
from dotenv import load_dotenv
from common import GEMINI_PARSE_PROMPT, Messages, Config
from fastapi import Response
import sys
# Ensure project root is on sys.path so local packages import correctly when running main.py
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from handlers.bitbucket_handler import process_bitbucket_event
from services.jira_service import JiraService
from models.task_info import TaskInfo
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
app = FastAPI()

# Lấy biến môi trường
JIRA_SERVER = os.getenv("JIRA_SERVER", "").strip()
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "").strip()
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# Khởi tạo Jira Service (thay vì global jira)
jira_service = JiraService()

# Giữ biến jira global để backward compatibility (sẽ deprecated)
jira = jira_service.jira if jira_service.jira else None

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

# Đã xóa các hàm duplicate: find_epic, find_epic_link_field_id, update_issue_async
# Sử dụng JiraService.find_epic(), JiraService._find_epic_link_field_id(), JiraService.update_issue() thay thế

async def process_with_timeout(message_text, background_tasks: BackgroundTasks, media_urls=None, subject=None):
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

        # Kiểm tra Jira connection và JIRA_PROJECT_KEY
        if not jira_service.jira:
            logger.error("❌ Jira chưa được kết nối")
            return {"success": False, "message": Messages.error("Jira chưa được kết nối. Vui lòng kiểm tra cấu hình.")}
        
        if not JIRA_PROJECT_KEY:
            logger.error("❌ JIRA_PROJECT_KEY chưa được cấu hình")
            return {"success": False, "message": Messages.error("JIRA_PROJECT_KEY chưa được cấu hình.")}

        # 2. Chuyển đổi dictionary thành TaskInfo model
        summary = task_info.get('summary', 'No summary')
        issue_type = task_info.get('issuetype', 'Task')
        
        # Detect priority từ message
        priority = task_info.get('priority', 'Medium')
        if re.search(r'ưu\s*tiên\s*cao|high\s*priority|priority\s*high|urgent', message_text or '', re.IGNORECASE):
            priority = 'High'
        elif re.search(r'ưu\s*tiên\s*thấp|low\s*priority|priority\s*low', message_text or '', re.IGNORECASE):
            priority = 'Low'

        # Try to detect due date in ISO format YYYY-MM-DD or DD/MM/YYYY
        duedate = None
        iso_match = re.search(r'(\d{4}-\d{2}-\d{2})', message_text or '')
        if iso_match:
            duedate = iso_match.group(1)
        else:
            # Look for DD/MM/YYYY or D/M/YYYY
            dm_match = re.search(r'(\b\d{1,2}/\d{1,2}/\d{4}\b)', message_text or '')
            if dm_match:
                try:
                    dt = datetime.strptime(dm_match.group(1), '%d/%m/%Y')
                    # Convert to Jira-friendly ISO date YYYY-MM-DD
                    duedate = dt.strftime('%Y-%m-%d')
                except Exception:
                    duedate = None

        # Tạo TaskInfo object
        task_info_obj = TaskInfo(
            summary=summary,
            description=task_info.get('description', 'No description'),
            issuetype=issue_type,
            priority=priority,
            epic_link=task_info.get('epic_link'),
            assignee=task_info.get('assignee'),
            due_date=duedate,
            media_urls=list(media_urls) if media_urls else []
        )

        # Tạo issue ngay lập tức sử dụng JiraService
        jira_start = time.time()
        try:
            new_issue = await loop.run_in_executor(
                None, 
                lambda: jira_service.create_issue(task_info_obj)
            )
        except Exception as e:
            logger.error(f"❌ Lỗi khi tạo issue: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"success": False, "message": Messages.error(f"Không thể tạo issue: {str(e)}")}
        
        jira_time = time.time() - jira_start
        logger.info(f"⏱️ Jira create time: {jira_time:.2f}s")
        
        issue_url = f"{JIRA_SERVER}/browse/{new_issue.key}"
        
        # 3. Cập nhật epic link và assignee trong background (nếu có)
        # JiraService.create_issue đã xử lý basic fields, nhưng epic_link và assignee
        # cần được update sau vì có thể cần tìm kiếm trên Jira
        if task_info_obj.epic_link or task_info_obj.assignee:
            logger.info(f"📋 Sẽ cập nhật {new_issue.key} trong background: epic={task_info_obj.epic_link}, assignee={task_info_obj.assignee}")
            # Sử dụng JiraService.update_issue thay vì update_issue_async
            background_tasks.add_task(jira_service.update_issue, new_issue.key, task_info_obj)
        else:
            logger.info(f"ℹ️ Không có epic_link hoặc assignee để cập nhật cho {new_issue.key}")

        # Attach media files (images/videos) if any media URLs found
        # Media URLs đã được xử lý trong JiraService.create_issue() thông qua task_info_obj.media_urls

        # Nếu issue là Epic thì tạo đúng 4 task con với tên cố định và KHÔNG có description
        if issue_type and issue_type.lower() == 'epic':
            # Đợi một chút để Jira có thời gian commit/index epic mới trước khi tạo child
            try:
                await asyncio.sleep(2)
            except Exception:
                pass
            child_names = ['FE', 'BE', 'SQA', '[Estimate] những công việc ban đầu của estimate']

            # Kiểm tra parent trên Jira: chỉ tạo child nếu parent thực sự có issuetype = Epic
            try:
                parent_is_epic = False
                if jira_service.jira:
                    parent_issue = jira_service.jira.issue(new_issue.key)
                    if hasattr(parent_issue.fields, 'issuetype') and parent_issue.fields.issuetype.name.lower() == 'epic':
                        parent_is_epic = True
                    else:
                        logger.warning(f"⚠️ Issue {new_issue.key} không phải Epic trên Jira (issuetype={getattr(parent_issue.fields, 'issuetype', None)})")
                else:
                    logger.warning("⚠️ Jira client chưa khởi tạo, bỏ qua kiểm tra issuetype cho parent epic")
            except Exception as e:
                logger.warning(f"⚠️ Không thể kiểm tra issuetype của {new_issue.key}: {e}")

            if not parent_is_epic:
                logger.info(f"ℹ️ Bỏ qua tạo child vì {new_issue.key} không phải Epic trên Jira")
            else:
                created_children = []
                for name in child_names:
                    child_task_info = TaskInfo(
                        summary=name,
                        description='',
                        issuetype='Task',
                        epic_link=new_issue.key  # Link đến epic cha
                    )
                    try:
                        child = await loop.run_in_executor(
                            None,
                            lambda: jira_service.create_issue(child_task_info)
                        )
                        logger.info(f"✅ Tạo child issue {child.key} cho epic {new_issue.key}")
                        created_children.append(child)
                        # Đảm bảo child có epic link: nếu create_issue không set được, update trong background
                        try:
                            parent_summary = getattr(new_issue.fields, 'summary', None) or new_issue.key
                            bg_task_info = TaskInfo(epic_link=parent_summary)
                            background_tasks.add_task(jira_service.update_issue, child.key, bg_task_info)
                            logger.info(f"ℹ️ Đã schedule update để gắn epic cho {child.key} (search by name: {parent_summary})")
                        except Exception as e:
                            logger.warning(f"⚠️ Không thể schedule update epic cho {child.key}: {e}")
                    except Exception as e:
                        logger.warning(f"⚠️ Không thể tạo child {name}: {e}")
        
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
@app.middleware("http")
async def add_ngrok_skip_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["ngrok-skip-browser-warning"] = "true"
    return response
@app.post("/webhook/teams")
async def teams_webhook(request: Request, background_tasks: BackgroundTasks):
    headers = {"ngrok-skip-browser-warning": "true"}
    body_bytes = await request.body()
    logger.info(f"🔍 Dữ liệu thô nhận được: {body_bytes.decode()}")
    try:
        data = await request.json()
        logger.info(f"🚀 Payload nhận từ Power Automate: {data}")
        
        # Sửa cách lấy dữ liệu để tránh lỗi 'NoneType' object has no attribute 'strip'
        raw_text = data.get("text")
        raw_text = raw_text.strip() if raw_text else ""

        if not raw_text:
            logger.warning("⚠️ 'text' bị None hoặc rỗng.")
            return {
                "status": "warning",
                "jira_message": "⚠️ Power Automate chưa gửi được nội dung tin nhắn. Hãy kiểm tra tab Expression."
            }

        # Nếu Power Automate gửi một chuỗi JSON (như logs), parse để lấy Subject / PlainText / Content / Link
        subject = None
        plain_text = None
        html_content = None
        link = None

        nested = None
        try:
            nested = json.loads(raw_text)
        except Exception:
            nested = None

        if isinstance(nested, dict):
            # Hỗ trợ nhiều biến thể: teamsFlowRunContext.MessagePayload hoặc MessagePayload trực tiếp
            mp = nested.get('teamsFlowRunContext', {}).get('MessagePayload') or nested.get('MessagePayload') or {}
            # Body có thể nằm trong mp['Body']
            body = mp.get('Body') or {}
            subject = mp.get('Subject') or body.get('Subject')
            plain_text = body.get('PlainText') or mp.get('PlainText')
            html_content = body.get('Content') or mp.get('Content')
            link = mp.get('LinkToMessage') or body.get('LinkToMessage')

        # Nếu không parse được nested JSON, vẫn dùng raw_text as-is
        # Xây dựng message_text sao cho dòng đầu là subject (nếu có) để đảm bảo summary chính xác
        text_for_clean = html_content or plain_text or raw_text

        # Extract media URLs from HTML or raw text (img/src, video/src, or direct links to media files)
        media_urls = set()
        try:
            # img tags
            for m in re.finditer(r'<img[^>]+src=[\'\"]([^\'\"]+)[\'\"]', raw_text or '', re.IGNORECASE):
                media_urls.add(m.group(1))
            # video tags
            for m in re.finditer(r'<video[^>]+src=[\'\"]([^\'\"]+)[\'\"]', raw_text or '', re.IGNORECASE):
                media_urls.add(m.group(1))
            # source tags inside video/audio
            for m in re.finditer(r'<source[^>]+src=[\'\"]([^\'\"]+)[\'\"]', raw_text or '', re.IGNORECASE):
                media_urls.add(m.group(1))
            # direct links to media files (jpg/png/gif/mp4/mov/webm)
            for m in re.finditer(r'(https?://\S+?\.(?:png|jpe?g|gif|mp4|mov|webm))(?:\?|\s|\"|\'|$)', raw_text or '', re.IGNORECASE):
                media_urls.add(m.group(1))
        except Exception:
            media_urls = set()

        if subject:
            message_text = f"{subject}\n\n{text_for_clean}"
        else:
            message_text = text_for_clean

        if link:
            message_text = f"{message_text}\n\nLink: {link}"

        # Làm sạch message (loại bỏ tag, ghép assignee nếu cần)
        message_text = clean_teams_message(message_text)
        result = await process_with_timeout(message_text, background_tasks, media_urls=list(media_urls), subject=subject)
        
        return {
            "status": "success",
            "jira_message": result["message"]
        }
        
    except Exception as e:
        logger.error(f"❌ Lỗi xử lý Webhook: {e}")
        return {"status": "error", "jira_message": f"❌ Lỗi: {str(e)}"}


@app.post("/webhook/bitbucket")
async def bitbucket_webhook(request: Request):
    body_bytes = await request.body()
    logger.info(f"🔍 Bitbucket raw: {body_bytes.decode()}")
    try:
        data = await request.json()
    except Exception as e:
        logger.error(f"❌ JSON parse error from Bitbucket: {e}")
        return {"status": "error", "message": "Invalid JSON"}

    try:
        result = process_bitbucket_event(data)
        status = "success" if result.get("success") else "error"
        return {"status": status, "result": result}
    except Exception as e:
        logger.error(f"❌ Lỗi xử lý Bitbucket webhook: {e}")
        return {"status": "error", "message": str(e)}
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
    