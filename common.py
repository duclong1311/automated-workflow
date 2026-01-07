"""
Common module chứa messages, prompts và constants
"""

# =============== PROMPTS ===============
GEMINI_PARSE_PROMPT = """Parse JSON:
{{
  "summary": "copy exact title",
  "issuetype": "Bug|Task|Epic|Improvement",
  "description": "copy content",
  "priority": "High|Medium|Low",
  "epic_link": "epic key (e.g. PROJ-123) or epic name if mentioned in text, null if not",
  "assignee": "username or email if mentioned in text, null if not"
}}

IMPORTANT RULES:
1. issuetype: 
   - "Epic" ONLY if text explicitly says "tạo Epic" or "create Epic" or "Epic:" at the start
   - "Bug" if text has "Bug"|"lỗi"|"bug"
   - "Task" for everything else (including when text says "epic link" or "link to epic" - that's just linking, not creating Epic)
   
2. epic_link: 
   - Extract epic key (format: PROJ-123, DXAI-456) or epic name (e.g. "DXAI", "DX-AI") 
   - Look for phrases like "epic link", "link to epic", "epic:", "epic=", "gán epic", "epic link đến"
   - Examples: "epic link DXAI" -> epic_link: "DXAI", "epic link đến PROJ-123" -> epic_link: "PROJ-123"
   - If epic_link exists, issuetype should be "Task" (not "Epic")
   
3. assignee:
   - Extract when text says "assign to", "gán cho", "assignee:", "assign:", "gán task này cho"
   - Extract name or email after these phrases
   - Examples: "gán cho Lê Đức Anh" -> assignee: "Lê Đức Anh", "assign to john@example.com" -> assignee: "john@example.com"

Text: "{text}"
"""

# =============== MESSAGES ===============
class Messages:
    AI_PARSE_ERROR = "🤖 AI không thể phân tích nội dung."
    PROCESSING = "⏳ Đang xử lý yêu cầu của bạn..."
    
    @staticmethod
    def success(issue_type, issue_key, issue_url, summary):
        return (
            f"✅ Đã tạo {issue_type} thành công!\n\n"
            f"• **Key**: [{issue_key}]({issue_url})\n\n"
            f"• **Tiêu đề**: {summary}"
        )
    
    @staticmethod
    def error(error_msg):
        return f"❌ Có lỗi xảy ra: {error_msg}"

# =============== CONSTANTS ===============
class Config:
    AI_TIMEOUT = 2.8  # 2.8s cho AI (để dư thời gian cho Jira)
    WEBHOOK_RESPONSE_TIMEOUT = 4.9  # Tổng <5s
    BOT_MENTION_NAME = "JiraBot"
