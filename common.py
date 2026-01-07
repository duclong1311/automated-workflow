"""
Common module chứa messages, prompts và constants
"""

# =============== PROMPTS ===============
GEMINI_PARSE_PROMPT = """Parse JSON:
{{
  "summary": "copy exact title",
  "issuetype": "Bug|Task|Epic|Improvement",
  "description": "copy content",
  "priority": "High|Medium|Low"
}}

Rules: Bug if has "Bug"|"lỗi", Epic if has "Epic", else Task.

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
            f"• **Key**: [{issue_key}]({issue_url})\n"
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
