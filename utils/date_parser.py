"""
Date utilities cho việc parse và format dates
"""
from datetime import datetime, timedelta
import re
from typing import Optional

def parse_vietnamese_date(text: str, today: datetime = None) -> Optional[str]:
    """
    Parse ngày tháng tiếng Việt và trả về format YYYY-MM-DD
    
    Hỗ trợ:
    - "hôm nay" -> today
    - "ngày mai" -> tomorrow
    - "tuần sau" -> 7 days from today
    - "15/01/2024", "15-01-2024" -> 2024-01-15
    - "2024-01-15" -> 2024-01-15
    """
    if today is None:
        today = datetime.now()
    
    text_lower = text.lower().strip()
    
    # Relative dates
    if 'hôm nay' in text_lower or 'today' in text_lower:
        return today.strftime('%Y-%m-%d')
    
    if 'ngày mai' in text_lower or 'tomorrow' in text_lower:
        return (today + timedelta(days=1)).strftime('%Y-%m-%d')
    
    if 'tuần sau' in text_lower or 'next week' in text_lower:
        return (today + timedelta(days=7)).strftime('%Y-%m-%d')
    
    if 'tháng sau' in text_lower or 'next month' in text_lower:
        return (today + timedelta(days=30)).strftime('%Y-%m-%d')
    
    # Absolute dates - DD/MM/YYYY hoặc DD-MM-YYYY
    date_patterns = [
        r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})',  # DD/MM/YYYY hoặc DD-MM-YYYY
        r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})',  # YYYY-MM-DD hoặc YYYY/MM/DD
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            try:
                # Check if it's YYYY-MM-DD format
                if len(match.group(1)) == 4:
                    year, month, day = match.groups()
                    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                else:
                    # DD/MM/YYYY format
                    day, month, year = match.groups()
                    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            except:
                pass
    
    return None


def extract_dates_from_text(text: str) -> tuple[Optional[str], Optional[str]]:
    """
    Trích xuất start_date và due_date từ text
    Returns: (start_date, due_date) in YYYY-MM-DD format or None
    """
    start_date = None
    due_date = None
    
    # Patterns cho start date
    start_patterns = [
        r'(?:start\s+date|ngày\s+bắt\s+đầu|bắt\s+đầu\s+từ)[:\s]+([^\n,]+)',
        r'(?:from|từ)\s+(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
    ]
    
    for pattern in start_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            date_text = match.group(1).strip()
            start_date = parse_vietnamese_date(date_text)
            if start_date:
                break
    
    # Patterns cho due date
    due_patterns = [
        r'(?:due\s+date|deadline|hạn\s+chót|đến\s+hạn|hoàn\s+thành\s+trước)[:\s]+([^\n,]+)',
        r'(?:to|đến|until)\s+(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
    ]
    
    for pattern in due_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            date_text = match.group(1).strip()
            due_date = parse_vietnamese_date(date_text)
            if due_date:
                break
    
    return start_date, due_date
