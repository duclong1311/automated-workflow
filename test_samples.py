"""
Test samples cho Teams Jira AI Bot v2.0
Chạy test: python test_samples.py
"""

# Test case 1: Basic task
test_basic = """
@JiraBot tạo task: Update documentation for API v2
"""

# Test case 2: Task with priority
test_priority = """
@JiraBot Bug: Login page không hoạt động
Priority: Khẩn cấp
Mô tả: Users không thể đăng nhập sau update
"""

# Test case 3: Task with dates
test_dates = """
@JiraBot tạo task: Implement payment gateway
Bắt đầu từ: 15/01/2024
Hạn chót: 31/01/2024
Priority: High
"""

# Test case 4: Task with relative dates
test_relative_dates = """
@JiraBot Bug: Critical security issue
Priority: Highest
Bắt đầu: hôm nay
Deadline: ngày mai
"""

# Test case 5: Task with assignee
test_assignee = """
@JiraBot tạo task: Design new homepage
Gán cho: Nguyễn Văn A
Priority: Medium
"""

# Test case 6: Task with epic link
test_epic = """
@JiraBot tạo task: Add search functionality
Epic link: DXAI
Gán cho: Trần Thị B
Priority: High
"""

# Test case 7: Complete task with all fields
test_complete = """
@JiraBot tạo task: Refactor authentication module
Priority: High
Bắt đầu từ: 20/01/2024
Hạn chót: 28/01/2024
Gán cho: Lê Văn C
Epic link: PROJ-100
Mô tả: 
- Cải thiện security
- Thêm 2FA
- Update documentation
"""

# Test case 8: Task with media URLs
test_media = """
@JiraBot tạo task: Review UI mockups
Mockup: https://imgur.com/abc123.png
Reference: https://example.com/design.jpg
Demo video: https://youtu.be/xyz789
Priority: Medium
Gán cho: Designer Team
"""

# Test case 9: Bug with image attachment
test_bug_image = """
@JiraBot Bug: Button không hiển thị đúng
Screenshot: https://i.imgur.com/bug123.png
Priority: High
Bắt đầu: hôm nay
"""

# Test case 10: Epic creation
test_create_epic = """
@JiraBot tạo Epic: Q1 2024 Infrastructure Upgrade
Mô tả: Nâng cấp toàn bộ hệ thống infrastructure trong Q1
Priority: Highest
"""

# Test case 11: Task link to epic (not create epic)
test_link_epic = """
@JiraBot tạo task: Migrate database to PostgreSQL 15
Epic link đến: Infrastructure Upgrade
Priority: High
Start date: 05/02/2024
Due date: 20/02/2024
"""

# Test case 12: Mixed Vietnamese and English
test_mixed = """
@JiraBot Create task: API Performance Optimization
Priority: cao
Start date: tuần sau
Gán cho: Backend Team
Epic link: PERF-2024
Description: Optimize slow endpoints, reduce response time
"""

# Test case 13: Task with multiple assignees in text (AI should pick first)
test_multi_mentions = """
@JiraBot tạo task: Code review session
Gán cho: Nguyễn Văn A và Trần Thị B
Note: Cả 2 người cùng review
Priority: Medium
"""

# Test case 14: Long description with formatting
test_long_desc = """
@JiraBot tạo task: Implement user authentication flow

Mô tả chi tiết:
1. Login page with email/password
2. OAuth integration (Google, Facebook)
3. Password reset functionality
4. Email verification
5. Session management

Technical requirements:
- Use JWT tokens
- Implement refresh token rotation
- Add rate limiting
- Security headers

Timeline:
- Start: 10/02/2024
- End: 25/02/2024

Priority: Highest
Assignee: Security Team
Epic link: AUTH-2024
"""

if __name__ == "__main__":
    print("=" * 60)
    print("TEAMS JIRA AI BOT - TEST SAMPLES")
    print("=" * 60)
    
    tests = [
        ("Basic task", test_basic),
        ("Task with priority", test_priority),
        ("Task with dates", test_dates),
        ("Task with relative dates", test_relative_dates),
        ("Task with assignee", test_assignee),
        ("Task with epic link", test_epic),
        ("Complete task", test_complete),
        ("Task with media", test_media),
        ("Bug with image", test_bug_image),
        ("Create epic", test_create_epic),
        ("Link to epic", test_link_epic),
        ("Mixed language", test_mixed),
        ("Multiple mentions", test_multi_mentions),
        ("Long description", test_long_desc),
    ]
    
    print("\n📋 Available test cases:\n")
    for i, (name, _) in enumerate(tests, 1):
        print(f"{i:2d}. {name}")
    
    print("\n" + "=" * 60)
    print("\n💡 Để test, gửi các message này qua Teams webhook")
    print("   hoặc sử dụng curl:\n")
    print('curl -X POST http://localhost:8000/webhook/teams \\')
    print('  -H "Content-Type: application/json" \\')
    print('  -d \'{"text": "' + test_basic.strip() + '"}\'')
    print("\n" + "=" * 60)
    
    # Test import
    print("\n🧪 Testing imports...\n")
    try:
        from config.settings import settings
        print("✅ config.settings")
        
        from models.task_info import TaskInfo
        print("✅ models.task_info")
        
        from services.gemini_service import GeminiService
        print("✅ services.gemini_service")
        
        from services.jira_service import JiraService
        print("✅ services.jira_service")
        
        from utils.text_parser import clean_teams_message
        print("✅ utils.text_parser")
        
        from utils.date_parser import parse_vietnamese_date
        print("✅ utils.date_parser")
        
        from handlers.webhook_handler import process_teams_message
        print("✅ handlers.webhook_handler")
        
        print("\n🎉 All imports successful!")
        
        # Test date parser
        print("\n🧪 Testing date parser...\n")
        test_dates_list = [
            "15/01/2024",
            "2024-01-15",
            "hôm nay",
            "ngày mai",
            "tuần sau"
        ]
        
        for date_str in test_dates_list:
            result = parse_vietnamese_date(date_str)
            print(f"  '{date_str}' → {result}")
        
        print("\n✅ Date parser working!")
        
    except Exception as e:
        print(f"\n❌ Import error: {e}")
        import traceback
        traceback.print_exc()
