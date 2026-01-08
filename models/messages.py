"""
Message templates cho responses
"""

class Messages:
    AI_PARSE_ERROR = "🤖 AI không thể phân tích nội dung."
    PROCESSING = "⏳ Đang xử lý yêu cầu của bạn..."
    
    @staticmethod
    def success(issue_type, issue_key, issue_url, summary, has_background_updates=False):
        msg = (
            f"✅ Đã tạo {issue_type} thành công!\n\n"
            f"• **Key**: [{issue_key}]({issue_url})\n\n"
            f"• **Tiêu đề**: {summary}"
        )
        if has_background_updates:
            msg += "\n\n⏳ Đang cập nhật thêm thông tin (epic link, assignee, dates, attachments)..."
        return msg
    
    @staticmethod
    def error(error_msg):
        return f"❌ Có lỗi xảy ra: {error_msg}"
