import os
import json
import logging
from fastapi import FastAPI, Request
from jira import JIRA
from google import genai # Thư viện mới của Google
from dotenv import load_dotenv

# Cấu hình Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI()

# 1. Khởi tạo Jira với PAT
try:
    # Đảm bảo loại bỏ khoảng trắng thừa nếu có
    server_url = os.getenv("JIRA_SERVER").strip()
    jira = JIRA(
        server=server_url,
        token_auth=os.getenv("JIRA_API_TOKEN").strip()
    )
    server_info = jira.server_info()
    logger.info(f"✅ Kết nối Jira thành công. Phiên bản: {server_info.get('version')}")
except Exception as e:
    logger.error(f"❌ Lỗi kết nối Jira: {e}")

# 2. Khởi tạo Gemini (SDK mới)
client_ai = genai.Client(api_key=os.getenv("GEMINI_API_KEY").strip())

def ask_gemini_to_parse_task(text):
    prompt = f"Phân tích tin nhắn sau và trả về JSON (summary, description, priority, issuetype): {text}"
    try:
        # Cấu hình theo SDK google-genai mới
        response = client_ai.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config={
                'response_mime_type': 'application/json',
            }
        )
        return json.loads(response.text)
    except Exception as e:
        logger.error(f"❌ Gemini Error: {e}")
        return None

@app.post("/webhook/teams")
async def teams_webhook(request: Request):
    data = await request.json()
    channel_id = data.get("channelData", {}).get("channel", {}).get("id")
    allowed_channels = os.getenv("ALLOWED_CHANNELS", "").split(",")
    
    logger.info(f"Yêu cầu từ Channel ID: {channel_id}")

    if channel_id not in allowed_channels:
        return {"type": "message", "text": f"⚠️ Channel chưa cấp quyền. ID: `{channel_id}`"}

    message_text = data.get("text", "").replace("<at>JiraBot</at>", "").strip()
    if not message_text:
        return {"type": "message", "text": "Nội dung trống."}

    task_info = ask_gemini_to_parse_task(message_text)
    if not task_info:
        return {"type": "message", "text": "🤖 AI không xử lý được nội dung."}

    try:
        issue_dict = {
            'project': {'key': os.getenv("JIRA_PROJECT_KEY").strip()},
            'summary': task_info.get('summary'),
            'description': task_info.get('description'),
            'issuetype': {'name': task_info.get('issuetype', 'Task')},
            'priority': {'name': task_info.get('priority', 'Medium')}
        }
        new_issue = jira.create_issue(fields=issue_dict)
        return {
            "type": "message",
            "text": f"✅ **Đã tạo Jira!**\n\n- **Key:** [{new_issue.key}]({new_issue.permalink()})\n- **Tiêu đề:** {task_info['summary']}"
        }
    except Exception as e:
        logger.error(f"Jira Error: {e}")
        return {"type": "message", "text": f"❌ Lỗi tạo Jira: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)