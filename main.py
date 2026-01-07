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
    """Làm sạch HTML message từ Teams"""
    clean = re.sub(r'</p>|</div>|<br\s*/?>|</li>', '\n', raw_text)
    clean = re.sub(r'<[^>]+>', '', clean)
    clean = html.unescape(clean)
    clean = '\n'.join(line.strip() for line in clean.split('\n'))
    return re.sub(r'\n\n+', '\n\n', clean).strip()

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
        logger.info(f"🔍 Gemini raw response: {response_text[:300]}")
        
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
            
        logger.info(f"✅ Parsed task: {result.get('issuetype')} - {result.get('summary')[:50]}")
        return result
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ JSON Parse Error: {e}")
        logger.error(f"   Response text: {response.text[:500]}")
        # Fallback: tạo task cơ bản
        return {
            'summary': text.split('\n')[0][:100] if text else 'No summary',
            'issuetype': 'Task',
            'description': text,
            'priority': 'Medium'
        }
    except AttributeError as e:
        logger.error(f"❌ Response Error: {e}")
        logger.error(f"   Check if response object valid")
        return None
    except Exception as e:
        logger.error(f"❌ Gemini Error: {type(e).__name__}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None

def quick_parse_fallback(text):
    """Parse nhanh bằng regex khi AI timeout"""
    summary = text.split('\n')[0][:200] if text else 'No summary'
    
    # Detect issue type
    text_lower = text.lower()
    if 'bug' in text_lower or 'lỗi' in text_lower:
        issue_type = 'Bug'
    elif 'epic' in text_lower:
        issue_type = 'Epic'
    elif 'improvement' in text_lower:
        issue_type = 'Improvement'
    else:
        issue_type = 'Task'
    
    return {
        'summary': summary,
        'issuetype': issue_type,
        'description': text,
        'priority': 'Medium'
    }

async def process_with_timeout(message_text):
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

        # 2. Tạo Jira issue nhanh
        summary = task_info.get('summary', 'No summary')
        issue_type = task_info.get('issuetype', 'Task')
        
        issue_dict = {
            'project': {'key': JIRA_PROJECT_KEY},
            'summary': summary,
            'description': task_info.get('description', 'No description'),
            'issuetype': {'name': issue_type},
            'priority': {'name': task_info.get('priority', 'Medium')}
        }

        # Nếu là Epic, bắt buộc phải có Epic Name
        if issue_type == 'Epic':
            issue_dict['customfield_10104'] = summary

        # Tạo issue
        jira_start = time.time()
        new_issue = await loop.run_in_executor(
            None, 
            lambda: jira.create_issue(fields=issue_dict)
        )
        jira_time = time.time() - jira_start
        logger.info(f"⏱️ Jira create time: {jira_time:.2f}s")
        
        issue_url = f"{JIRA_SERVER}/browse/{new_issue.key}"
        
        total_time = time.time() - start_time
        logger.info(f"⏱️ Total processing time: {total_time:.2f}s")
        
        return {
            "success": True,
            "message": Messages.success(issue_type, new_issue.key, issue_url, summary)
        }
        
    except asyncio.TimeoutError:
        elapsed = time.time() - start_time
        logger.error(f"❌ Timeout khi xử lý request sau {elapsed:.2f}s")
        return {"success": False, "message": Messages.error("Quá thời gian xử lý (>5s)")}
    except Exception as e:
        logger.error(f"❌ Lỗi: {e}")
        return {"success": False, "message": Messages.error(str(e))}

@app.post("/webhook/teams")
async def teams_webhook(request: Request):
    try:
        data = await request.json()
        raw_text = data.get("text", "")
        message_text = clean_teams_message(raw_text)
        
        # Bỏ tag mention của bot
        message_text = message_text.replace(Config.BOT_MENTION_NAME, "").strip()

        # Xử lý với timeout tổng 4s (để đảm bảo response <5s)
        result = await asyncio.wait_for(
            process_with_timeout(message_text),
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