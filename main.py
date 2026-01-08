"""
Main FastAPI application (refactored entry point)
"""
import logging
import asyncio
from fastapi import FastAPI, Request, BackgroundTasks

from config.settings import settings
from handlers.webhook_handler import process_teams_message
from handlers.bitbucket_handler import process_bitbucket_event
from models.messages import Messages
from utils.text_parser import clean_teams_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Teams Jira AI Bot", version="2.0")


@app.get("/")
async def root():
    return {
        "message": "Teams Jira AI Bot is running",
        "version": "2.0",
        "status": "healthy"
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhook/teams")
async def teams_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Webhook endpoint cho Teams messages
    """
    try:
        data = await request.json()
        raw_text = data.get("text", "")
        
        # Clean message từ Teams
        message_text = clean_teams_message(raw_text)
        
        # Bỏ tag mention của bot
        message_text = message_text.replace(settings.BOT_MENTION_NAME, "").strip()
        
        # Xử lý với timeout
        result = await asyncio.wait_for(
            process_teams_message(message_text, background_tasks),
            timeout=settings.WEBHOOK_RESPONSE_TIMEOUT
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
        import traceback
        logger.error(traceback.format_exc())
        return {
            "type": "message",
            "text": Messages.error(str(e))
        }


@app.post("/webhook/bitbucket")
async def bitbucket_webhook(request: Request):
    """
    Webhook endpoint cho Bitbucket events
    Tự động chuyển trạng thái Jira và log work dựa trên sự kiện Bitbucket
    """
    try:
        data = await request.json()
        
        # Log event để debug
        event_type = data.get('eventKey', 'unknown')
        logger.info(f"📥 Nhận Bitbucket event: {event_type}")
        
        # Xử lý event
        result = process_bitbucket_event(data)
        
        if result.get("success"):
            logger.info(f"✅ {result.get('message', 'Đã xử lý thành công')}")
            return {
                "status": "success",
                "message": result.get("message", "Đã xử lý thành công"),
                "results": result.get("results", [])
            }
        else:
            logger.error(f"❌ {result.get('message', 'Lỗi khi xử lý')}")
            return {
                "status": "error",
                "message": result.get("message", "Lỗi khi xử lý")
            }, 400
        
    except Exception as e:
        logger.error(f"❌ Lỗi webhook Bitbucket: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "status": "error",
            "message": f"Lỗi: {str(e)}"
        }, 500


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host=settings.HOST, 
        port=settings.PORT,
        log_level="info"
    )