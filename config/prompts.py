"""
AI prompts cho Gemini
"""

GEMINI_PARSE_PROMPT = """Parse JSON with ALL fields (even if null):
{{
  "summary": "copy exact title",
  "issuetype": "Bug|Task|Epic|Improvement",
  "description": "copy content, include media URLs if present",
  "priority": "Highest|High|Medium|Low|Lowest or null",
  "start_date": "YYYY-MM-DD or null",
  "due_date": "YYYY-MM-DD or null",
  "epic_link": "epic key (e.g. PROJ-123) or epic name if mentioned in text, null if not",
  "assignee": "username or email if mentioned in text, null if not",
  "media_urls": ["list of image/video URLs found in text, empty array if none"]
}}

IMPORTANT RULES:

1. issuetype: 
   - "Epic" ONLY if text explicitly says "tạo Epic" or "create Epic" or "Epic:" at the start
   - "Bug" if text has "Bug"|"lỗi"|"bug"
   - "Task" for everything else (including when text says "epic link" or "link to epic")
   
2. priority:
   - Extract priority from keywords: "urgent"|"khẩn cấp"|"cao"|"high"|"highest" -> "High" or "Highest"
   - "medium"|"trung bình"|"bình thường" -> "Medium"
   - "low"|"thấp"|"không gấp" -> "Low"
   - Default: null (will use Medium in Jira)

3. start_date & due_date:
   - Extract dates from phrases like:
     * "start date: 2024-01-15", "bắt đầu từ 15/01/2024", "ngày bắt đầu 15-01-2024"
     * "due date: 2024-01-20", "hạn chót 20/01/2024", "deadline 20-01-2024"
   - Convert to YYYY-MM-DD format
   - Today is {today_date}
   - Relative dates: "hôm nay" -> today, "ngày mai" -> tomorrow, "tuần sau" -> 7 days from today
   
4. epic_link: 
   - Extract epic key (format: PROJ-123, DXAI-456) or epic name (e.g. "DXAI", "DX-AI") 
   - Look for phrases like "epic link", "link to epic", "epic:", "epic=", "gán epic", "epic link đến"
   - If epic_link exists, issuetype should be "Task" (not "Epic")
   
5. assignee:
   - Extract when text says "assign to", "gán cho", "assignee:", "assign:", "gán task này cho"
   - Extract full name or email after these phrases

6. media_urls:
   - Extract ALL URLs that look like images or videos
   - Image extensions: .jpg, .jpeg, .png, .gif, .webp, .svg
   - Video extensions: .mp4, .mov, .avi, .webm
   - Video platforms: youtube.com, youtu.be, vimeo.com, drive.google.com (videos)
   - Return as array of strings

Text: "{text}"
"""
