import os
import json
import logging
import re
import html
from fastapi import FastAPI, Request
from jira import JIRA
from google import genai
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
app = FastAPI()

# Lấy biến môi trường an toàn
JIRA_SERVER = os.getenv("JIRA_SERVER", "").strip()
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "").strip()
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# Khởi tạo clients
jira = None
client_ai = None

try:
    if not JIRA_SERVER or not JIRA_API_TOKEN:
        raise ValueError("JIRA_SERVER và JIRA_API_TOKEN không được để trống")
    jira = JIRA(server=JIRA_SERVER, token_auth=JIRA_API_TOKEN)
    logger.info("✅ Kết nối Jira thành công.")
except Exception as e:
    logger.error(f"❌ Lỗi kết nối Jira: {e}")

try:
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY không được để trống")
    client_ai = genai.Client(api_key=GEMINI_API_KEY)
    logger.info("✅ Kết nối Gemini AI thành công.")
except Exception as e:
    logger.error(f"❌ Lỗi kết nối Gemini AI: {e}")

def clean_teams_message(raw_text):
    """Loại bỏ HTML tags và mentions từ Teams message"""
    # Chuyển các thẻ đóng paragraph/div thành newline để giữ cấu trúc
    clean = re.sub(r'</p>|</div>|<br\s*/?>|</li>', '\n', raw_text)
    # Xóa tất cả HTML tags còn lại
    clean = re.sub(r'<[^>]+>', '', clean)
    # Decode HTML entities
    clean = html.unescape(clean)
    # Xóa khoảng trắng thừa ở đầu/cuối mỗi dòng
    clean = '\n'.join(line.strip() for line in clean.split('\n'))
    # Xóa các dòng trống liên tiếp (giữ tối đa 1 dòng trống)
    clean = re.sub(r'\n\n+', '\n\n', clean).strip()
    return clean

def ask_gemini_to_parse_task(text):
    # Prompt nâng cao để xử lý nội dung phức tạp như hình ảnh bạn gửi
    prompt = f"""
    Bạn là một chuyên gia quản lý dự án Jira. Hãy phân tích nội dung tin nhắn dưới đây và chuyển đổi thành một đối tượng JSON chính xác.
    
    Yêu cầu logic:
    1. summary: Lấy CHÍNH XÁC dòng đầu tiên hoặc câu đầu tiên của tin nhắn làm tiêu đề. 
       QUAN TRỌNG: Giữ NGUYÊN tất cả các tag như [Bug DXAI][DXAI-821][iPhone] - KHÔNG được cắt bỏ hoặc làm sạch các tag này.
    2. issuetype: 
       - Nếu có chứ improvement hoặc bug trong summary hoặc description hoặc ưu tiên thì phải tự biết mà sửa lại
       - Nếu tiêu đề hoặc nội dung có chữ "Bug", "[Bug]" hoặc mô tả lỗi hệ thống -> 'Bug', [Improvement] -> 'Improvement', [Test] -> 'Test'.
       - Nếu là yêu cầu làm tính năng mới -> 'Task'.
       - Nếu là một hạng mục lớn bao trùm -> 'Epic'.
    3. description: Copy y nguyên toàn bộ nội dung chi tiết (Hiện tượng, Thiết bị test, các bước tái hiện...).
    4. priority: Dựa vào từ ngữ (gấp, khẩn cấp, cực kỳ lỗi) để chọn (Highest, High, Medium, Low). Mặc định là 'Medium'.
    5. epic_link: Nếu trong tiêu đề có mã dự án như "DXAI-821", hãy trích xuất mã đó (ví dụ: DXAI-821).

    Nội dung tin nhắn:
    "{text}"
    """
    try:
        if not client_ai:
            logger.error("❌ Client AI chưa được khởi tạo")
            return None
            
        response = client_ai.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config={'response_mime_type': 'application/json'}
        )
        
        # Validate response
        if not hasattr(response, 'text') or not response.text:
            logger.error(f"❌ AI response không hợp lệ: {response}")
            return None
            
        # Parse JSON an toàn
        result = json.loads(response.text)
        logger.info(f"✅ AI parsed: {result}")
        return result
    except json.JSONDecodeError as e:
        logger.error(f"❌ JSON Parse Error: {e}, Response: {response.text if hasattr(response, 'text') else 'N/A'}")
        return None
    except Exception as e:
        logger.error(f"❌ Gemini Error: {e}")
        return None

@app.post("/webhook/teams")
async def teams_webhook(request: Request):
    data = await request.json()
    channel_id = data.get("channelData", {}).get("channel", {}).get("id")
    
    # 1. Lấy text từ tin nhắn và làm sạch HTML
    raw_text = data.get("text", "")
    logger.info(f"📨 Raw message: {raw_text[:200]}...")  # Log để debug
    message_text = clean_teams_message(raw_text)
    logger.info(f"🧹 Cleaned message: {message_text[:200]}...")
    
    # Kiểm tra clients
    if not jira:
        return {"type": "message", "text": "❌ Jira chưa được kết nối. Vui lòng kiểm tra cấu hình."}
    if not client_ai:
        return {"type": "message", "text": "❌ AI chưa được kết nối. Vui lòng kiểm tra cấu hình."}
    
    # 2. AI Phân tích
    task_info = ask_gemini_to_parse_task(message_text)
    if not task_info:
        return {"type": "message", "text": "🤖 AI không thể phân tích nội dung này. Vui lòng thử lại hoặc format lại message."}

    try:
        # 3. Xây dựng Issue
        if not JIRA_PROJECT_KEY:
            return {"type": "message", "text": "❌ JIRA_PROJECT_KEY chưa được cấu hình."}
            
        issue_dict = {
            'project': {'key': JIRA_PROJECT_KEY},
            'summary': task_info.get('summary', 'No summary'),
            'description': task_info.get('description', 'No description'),
            'issuetype': {'name': task_info.get('issuetype', 'Task')},
            'priority': {'name': task_info.get('priority', 'Medium')}
        }

        # 4. Tạo issue
        new_issue = jira.create_issue(fields=issue_dict)
        
        # Build safe Jira URL
        issue_url = f"{JIRA_SERVER}/browse/{new_issue.key}"
        logger.info(f"✅ Created issue: {new_issue.key}")
        
        return {
            "type": "message",
            "text": f"✅ **Đã tạo {task_info.get('issuetype', 'Task')} thành công!**\n\n- **Key:** [{new_issue.key}]({issue_url})\n- **Tiêu đề:** {new_issue.fields.summary}"
        }
    except Exception as e:
        logger.error(f"❌ Jira Error: {e}", exc_info=True)
        return {"type": "message", "text": f"❌ Lỗi khi tạo issue: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)