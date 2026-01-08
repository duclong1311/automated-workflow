"""
Gemini AI Service cho việc parse task information
"""
import json
import re
import logging
from datetime import datetime
from google import genai
from typing import Optional

from config.prompts import GEMINI_PARSE_PROMPT
from config.settings import settings
from models.task_info import TaskInfo

logger = logging.getLogger(__name__)

class GeminiService:
    def __init__(self):
        self.client = None
        try:
            self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
            logger.info("✅ Kết nối Gemini AI thành công.")
        except Exception as e:
            logger.error(f"❌ Lỗi kết nối Gemini AI: {e}")
    
    def parse_task(self, text: str) -> Optional[TaskInfo]:
        """
        Phân tích task với AI
        Returns TaskInfo hoặc None nếu lỗi
        """
        if not self.client:
            logger.error("❌ Gemini client chưa được khởi tạo")
            return None
        
        try:
            today_date = datetime.now().strftime('%Y-%m-%d')
            prompt = GEMINI_PARSE_PROMPT.format(text=text, today_date=today_date)
            
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config={
                    'response_mime_type': 'application/json',
                    'temperature': 0.1,
                }
            )
            
            response_text = response.text.strip()
            
            # Xóa markdown code block nếu có
            if response_text.startswith('```'):
                response_text = re.sub(r'^```(?:json)?\s*', '', response_text)
                response_text = re.sub(r'\s*```$', '', response_text)
            
            result = json.loads(response_text)
            
            # Validate và clean data
            result = self._validate_and_clean(result, text)
            
            task_info = TaskInfo.from_dict(result)
            
            logger.info(f"✅ Parsed task: {task_info.issuetype} - {task_info.summary[:50]}")
            if task_info.epic_link:
                logger.info(f"   Epic link: {task_info.epic_link}")
            if task_info.assignee:
                logger.info(f"   Assignee: {task_info.assignee}")
            if task_info.priority:
                logger.info(f"   Priority: {task_info.priority}")
            if task_info.start_date:
                logger.info(f"   Start date: {task_info.start_date}")
            if task_info.due_date:
                logger.info(f"   Due date: {task_info.due_date}")
            if task_info.media_urls:
                logger.info(f"   Media URLs: {len(task_info.media_urls)} found")
            
            return task_info
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON Parse Error: {e}")
            logger.error(f"   Response text: {response.text[:500]}")
            return None
        except Exception as e:
            logger.error(f"❌ Gemini Error: {type(e).__name__}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def _validate_and_clean(self, result: dict, original_text: str) -> dict:
        """Validate và clean dữ liệu từ AI"""
        # Validate required fields
        if not result.get('summary'):
            result['summary'] = original_text.split('\n')[0][:100]
        if not result.get('issuetype'):
            result['issuetype'] = 'Task'
        if not result.get('description'):
            result['description'] = original_text
        
        # Ensure optional fields exist
        for field in ['priority', 'epic_link', 'assignee', 'start_date', 'due_date']:
            if field not in result:
                result[field] = None
        
        if 'media_urls' not in result:
            result['media_urls'] = []
        
        # Clean epic_link
        if result.get('epic_link'):
            epic_link = result['epic_link']
            if isinstance(epic_link, str):
                epic_link = re.sub(r'\s+(?:và|and|cho|to|for).*$', '', epic_link, flags=re.IGNORECASE).strip()
                result['epic_link'] = epic_link if epic_link else None
            elif not epic_link:
                result['epic_link'] = None
        
        # Clean assignee
        if result.get('assignee'):
            assignee = result['assignee']
            if isinstance(assignee, str):
                assignee = re.sub(r'\s*\([^)]+\)', '', assignee).strip()
                assignee = re.sub(r'\s+(?:và|and|cho|to|for).*$', '', assignee, flags=re.IGNORECASE).strip()
                result['assignee'] = assignee if assignee else None
            elif not assignee:
                result['assignee'] = None
        
        # Clean description (remove instructions)
        if result.get('description'):
            description = result['description']
            lines = description.split('\n')
            cleaned_lines = []
            for line in lines:
                if not re.search(r'(gán|assign|epic\s+link|hãy\s+gán)', line, re.IGNORECASE):
                    cleaned_lines.append(line)
            result['description'] = '\n'.join(cleaned_lines).strip()
        
        # Validate dates format
        for date_field in ['start_date', 'due_date']:
            if result.get(date_field):
                # Check if format is YYYY-MM-DD
                if not re.match(r'^\d{4}-\d{2}-\d{2}$', result[date_field]):
                    logger.warning(f"⚠️ Invalid date format for {date_field}: {result[date_field]}")
                    result[date_field] = None
        
        # IMPORTANT: Nếu có epic_link thì phải là Task
        if result.get('epic_link') and result.get('issuetype') == 'Epic':
            logger.warning(f"⚠️ Có epic_link nhưng issuetype là Epic, đổi thành Task")
            result['issuetype'] = 'Task'
        
        return result
