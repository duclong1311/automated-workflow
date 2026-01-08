"""
Quick fallback parser khi AI timeout
"""
import re
import logging
from typing import Optional

from models.task_info import TaskInfo
from utils.date_parser import extract_dates_from_text

logger = logging.getLogger(__name__)

def quick_parse_fallback(text: str) -> TaskInfo:
    """Parse nhanh bằng regex khi AI timeout"""
    summary = text.split('\n')[0][:200] if text else 'No summary'
    
    # Detect issue type
    text_lower = text.lower()
    if 'bug' in text_lower or 'lỗi' in text_lower:
        issue_type = 'Bug'
    elif 'tạo epic' in text_lower or 'create epic' in text_lower or text_lower.strip().startswith('epic:'):
        issue_type = 'Epic'
    elif 'improvement' in text_lower:
        issue_type = 'Improvement'
    else:
        issue_type = 'Task'
    
    # Parse priority
    priority = None
    if any(word in text_lower for word in ['urgent', 'khẩn cấp', 'highest', 'cao nhất']):
        priority = 'Highest'
    elif any(word in text_lower for word in ['high', 'cao', 'ưu tiên']):
        priority = 'High'
    elif any(word in text_lower for word in ['low', 'thấp', 'không gấp']):
        priority = 'Low'
    
    # Parse dates
    start_date, due_date = extract_dates_from_text(text)
    
    # Parse epic link
    epic_link = None
    epic_patterns = [
        r'epic\s+link\s+(?:đến|to)\s+([^\n,]+?)(?:\s+và|\s+and|$)',
        r'epic\s+link\s+([^\n,]+?)(?:\s+và|\s+and|$)',
        r'epic\s*[:\-=]\s*([^\n,]+?)(?:\s+và|\s+and|$)',
    ]
    for pattern in epic_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            epic_link = match.group(1).strip()
            epic_link = re.sub(r'\s+(?:và|and|cho|to|for).*$', '', epic_link, flags=re.IGNORECASE).strip('.,;:!?')
            if epic_link:
                break
    
    # Parse assignee
    assignee = None
    assignee_patterns = [
        r'gán\s+(?:task\s+này\s+)?cho\s+([^\n,]+?)(?:\s+và|\s+and|$)',
        r'gắn\s+cho\s+([^\n,]+?)(?:\s+và|\s+and|$)',
        r'assign\s+(?:to|for)?\s+([^\n,]+?)(?:\s+và|\s+and|$)',
    ]
    for pattern in assignee_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            assignee = match.group(1).strip()
            assignee = re.sub(r'\s*\([^)]+\)', '', assignee)
            assignee = re.sub(r'\s+(?:và|and|cho|to|for).*$', '', assignee, flags=re.IGNORECASE).strip('.,;:!?')
            if assignee and len(assignee) > 0:
                break
    
    # Nếu có epic_link thì phải là Task
    if epic_link and issue_type == 'Epic':
        issue_type = 'Task'
    
    # Clean description
    description = text
    if description:
        lines = description.split('\n')
        cleaned_lines = [line for line in lines if not re.search(r'(gán|assign|epic\s+link|hãy\s+gán)', line, re.IGNORECASE)]
        description = '\n'.join(cleaned_lines).strip()
    
    return TaskInfo(
        summary=summary,
        issuetype=issue_type,
        description=description,
        priority=priority,
        start_date=start_date,
        due_date=due_date,
        epic_link=epic_link,
        assignee=assignee,
        media_urls=[]
    )
