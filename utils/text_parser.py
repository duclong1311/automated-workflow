"""
Utility functions cho việc làm sạch và parse Teams messages
"""
import re
import html
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

def clean_teams_message(raw_text: str) -> str:
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
    assignee_from_mentions = None
    gắn_cho_pattern = r'(?:gắn|gán)\s+(?:cho|task\s+này\s+cho)'
    gắn_match = re.search(gắn_cho_pattern, raw_text, re.IGNORECASE)
    
    if gắn_match:
        start_pos = gắn_match.end()
        end_pattern = r'(?:\s+và|\s+and|epic\s+link|$)'
        end_match = re.search(end_pattern, raw_text[start_pos:], re.IGNORECASE)
        end_pos = start_pos + (end_match.start() if end_match else len(raw_text))
        
        text_between = raw_text[start_pos:end_pos]
        
        name_parts = []
        for match in re.finditer(at_pattern, text_between):
            mention_text = match.group(1).strip()
            mention_text = html.unescape(mention_text)
            if not mention_text.startswith('(') and not mention_text.endswith(')'):
                if len(mention_text) <= 20 and not re.search(r'[\(\)\[\]※]', mention_text):
                    name_parts.append(mention_text)
        
        if name_parts:
            assignee_from_mentions = ' '.join(name_parts).strip()
    
    # Bước 2: Thay thế mention tags bằng text
    text_with_mentions_replaced = raw_text
    for match in re.finditer(at_pattern, raw_text):
        mention_text = match.group(1).strip()
        mention_text = html.unescape(mention_text)
        text_with_mentions_replaced = text_with_mentions_replaced.replace(match.group(0), mention_text)
    
    text_with_mentions_replaced = text_with_mentions_replaced.replace('&nbsp;', ' ')
    text_with_mentions_replaced = html.unescape(text_with_mentions_replaced)
    
    assignee_from_text = None
    assignee_patterns = [
        r'tạo\s+task\s+gắn\s+cho\s+([^\n,<]+?)(?:\s+và|\s+and|epic|$)',
        r'gắn\s+cho\s+([^\n,<]+?)(?:\s+và|\s+and|epic|$)',
        r'gán\s+(?:task\s+này\s+)?cho\s+([^\n,<]+?)(?:\s+và|\s+and|epic|$)',
    ]
    
    for pattern in assignee_patterns:
        match = re.search(pattern, text_with_mentions_replaced, re.IGNORECASE)
        if match:
            assignee_from_text = match.group(1).strip()
            assignee_from_text = re.sub(r'<[^>]+>', '', assignee_from_text)
            assignee_from_text = html.unescape(assignee_from_text)
            assignee_from_text = re.sub(r'\s*\([^)]+\)', '', assignee_from_text).strip()
            if assignee_from_text and len(assignee_from_text) > 2:
                break
    
    assignee_from_text = assignee_from_mentions if assignee_from_mentions else assignee_from_text
    
    mentions = []
    for match in re.finditer(at_pattern, raw_text):
        mention_text = match.group(1).strip()
        mention_text = html.unescape(mention_text)
        if len(mention_text) <= 50 and not re.search(r'[\[\]※]', mention_text):
            mentions.append(mention_text)
            raw_text = raw_text.replace(match.group(0), mention_text)
    
    # Clean HTML
    clean = re.sub(r'</p>|</div>|<br\s*/?>|</li>', '\n', raw_text)
    clean = re.sub(r'<[^>]+>', '', clean)
    clean = html.unescape(clean)
    clean = '\n'.join(line.strip() for line in clean.split('\n'))
    clean = re.sub(r'\n\n+', '\n\n', clean).strip()
    
    if mentions and not assignee_from_text:
        valid_mentions = [m.strip() for m in mentions if m.lower() != 'jirabot' and len(m.strip()) <= 30 and not m.strip().startswith('[') and not re.search(r'[\[\]※&nbsp;]', m)]
        
        if valid_mentions:
            full_names = []
            current_name_parts = []
            
            for mention in valid_mentions:
                mention_clean = re.sub(r'[&nbsp;\xa0]', ' ', mention).strip()
                if len(mention_clean) > 0 and len(mention_clean) <= 20 and not re.search(r'[\(\)\[\]※]', mention_clean):
                    if not mention_clean.startswith('(') and not mention_clean.endswith(')'):
                        current_name_parts.append(mention_clean)
                    else:
                        if current_name_parts:
                            full_names.append(' '.join(current_name_parts))
                            current_name_parts = []
                else:
                    if current_name_parts:
                        full_names.append(' '.join(current_name_parts))
                        current_name_parts = []
                    if len(mention_clean) > 3 and (' ' in mention_clean or len(mention_clean) > 10):
                        full_names.append(mention_clean)
            
            if current_name_parts:
                full_names.append(' '.join(current_name_parts))
            
            final_mentions = [name for name in full_names if len(name) >= 3 and len(name) <= 50 and not re.search(r'[\[\]※]', name)]
            
            if final_mentions:
                if assignee_from_text:
                    assignee_match = re.search(r'(?:gán|gắn)\s+(?:task\s+này\s+)?cho\s+([^\n,]+?)(?:\s+và|\s+and|$)', clean, re.IGNORECASE)
                    if assignee_match:
                        old_text = assignee_match.group(0)
                        new_text = f"gán cho {assignee_from_text}"
                        clean = clean.replace(old_text, new_text)
                    else:
                        clean = f"{clean}\ngán cho {assignee_from_text}"
                else:
                    assignee_match = re.search(r'gán\s+(?:task\s+này\s+)?cho\s+([^\n,]+?)(?:\s+và|\s+and|$)', clean, re.IGNORECASE)
                    if not assignee_match:
                        best_mention = None
                        for mention in final_mentions:
                            if len(mention.split()) >= 2:
                                best_mention = mention
                                break
                        if not best_mention and final_mentions:
                            best_mention = final_mentions[0]
                        
                        if best_mention:
                            clean = f"{clean}\ngán cho {best_mention}"
    
    return clean


def extract_media_urls(text: str) -> Tuple[str, List[str]]:
    """
    Trích xuất URLs của ảnh/video từ text
    Returns: (cleaned_text, media_urls)
    """
    media_urls = []
    
    # Patterns cho media URLs
    url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
    
    urls = re.findall(url_pattern, text)
    
    for url in urls:
        url_lower = url.lower()
        
        # Check image extensions
        if any(ext in url_lower for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp']):
            media_urls.append(url)
            continue
        
        # Check video extensions
        if any(ext in url_lower for ext in ['.mp4', '.mov', '.avi', '.webm', '.mkv', '.flv']):
            media_urls.append(url)
            continue
        
        # Check video platforms
        if any(platform in url_lower for platform in ['youtube.com', 'youtu.be', 'vimeo.com', 'drive.google.com']):
            media_urls.append(url)
            continue
        
        # Check image hosting platforms
        if any(platform in url_lower for platform in ['imgur.com', 'flickr.com', 'instagram.com', 'i.redd.it']):
            media_urls.append(url)
    
    return text, media_urls
