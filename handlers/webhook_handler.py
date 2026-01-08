"""
Webhook handler cho Teams
"""
import asyncio
import logging
import time
from fastapi import BackgroundTasks

from config.settings import settings
from models.messages import Messages
from services.gemini_service import GeminiService
from services.jira_service import JiraService
from utils.text_parser import clean_teams_message, extract_media_urls
from utils.fallback_parser import quick_parse_fallback

logger = logging.getLogger(__name__)

# Initialize services
gemini_service = GeminiService()
jira_service = JiraService()

async def process_teams_message(message_text: str, background_tasks: BackgroundTasks) -> dict:
    """
    Xử lý message từ Teams với timeout để đảm bảo response <5s
    """
    start_time = time.time()
    
    try:
        loop = asyncio.get_event_loop()
        
        # 1. Parse text với AI (có timeout)
        ai_start = time.time()
        try:
            task_info = await asyncio.wait_for(
                loop.run_in_executor(None, gemini_service.parse_task, message_text),
                timeout=settings.AI_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.warning("⚠️ AI timeout, dùng fallback parsing")
            task_info = quick_parse_fallback(message_text)
        
        ai_time = time.time() - ai_start
        logger.info(f"⏱️ AI processing time: {ai_time:.2f}s")
        
        if not task_info:
            task_info = quick_parse_fallback(message_text)
        
        # 2. Extract media URLs nếu AI chưa extract
        if not task_info.media_urls:
            _, media_urls = extract_media_urls(message_text)
            task_info.media_urls = media_urls
        
        # 3. Tạo Jira issue nhanh
        jira_start = time.time()
        new_issue = await loop.run_in_executor(
            None,
            jira_service.create_issue,
            task_info
        )
        jira_time = time.time() - jira_start
        logger.info(f"⏱️ Jira create time: {jira_time:.2f}s")
        
        issue_url = f"{settings.JIRA_SERVER}/browse/{new_issue.key}"
        
        # 4. Thêm background task để cập nhật thông tin bổ sung
        has_background_updates = (
            task_info.epic_link or 
            task_info.assignee or 
            task_info.start_date or 
            task_info.due_date or 
            task_info.media_urls
        )
        
        if has_background_updates:
            logger.info(f"📋 Sẽ cập nhật {new_issue.key} trong background")
            background_tasks.add_task(jira_service.update_issue, new_issue.key, task_info)
        
        total_time = time.time() - start_time
        logger.info(f"⏱️ Total processing time: {total_time:.2f}s")
        
        return {
            "success": True,
            "message": Messages.success(
                task_info.issuetype, 
                new_issue.key, 
                issue_url, 
                task_info.summary,
                has_background_updates
            ),
            "issue_key": new_issue.key
        }
        
    except asyncio.TimeoutError:
        elapsed = time.time() - start_time
        logger.error(f"❌ Timeout khi xử lý request sau {elapsed:.2f}s")
        return {"success": False, "message": Messages.error("Quá thời gian xử lý (>5s)")}
    except Exception as e:
        logger.error(f"❌ Lỗi: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {"success": False, "message": Messages.error(str(e))}
