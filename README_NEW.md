# Teams Jira AI Bot v2.0

Bot tự động tạo Jira issues từ Teams messages sử dụng Gemini AI.

## 🎯 Tính năng mới (v2.0)

### ✨ Cải tiến chính:
1. **Cấu trúc code rõ ràng** - Tổ chức theo modules
2. **AI nhận diện Priority** - Tự động detect độ ưu tiên từ text
3. **Nhận diện Dates** - Start Date và Due Date
4. **Xử lý Media** - Tự động thêm ảnh/video vào attachments
5. **Background updates** - Tạo task nhanh, cập nhật sau

### 📊 AI có thể nhận diện:
- **Priority**: High/Medium/Low từ keywords ("khẩn cấp", "urgent", "cao", "thấp"...)
- **Start Date**: "bắt đầu từ 15/01/2024", "start date: 2024-01-15"
- **Due Date**: "hạn chót 20/01/2024", "deadline 20-01-2024"
- **Epic Link**: "epic link DXAI", "link đến PROJ-123"
- **Assignee**: "gán cho Nguyễn Văn A", "assign to john@example.com"
- **Media URLs**: Tự động detect và attach ảnh/video

### 📁 Cấu trúc Project

```
teams-jira-ai/
├── config/                 # Configuration
│   ├── settings.py        # Environment settings
│   └── prompts.py         # AI prompts
├── models/                # Data models
│   ├── task_info.py       # TaskInfo dataclass
│   └── messages.py        # Message templates
├── services/              # Business logic
│   ├── gemini_service.py  # AI parsing
│   └── jira_service.py    # Jira operations
├── utils/                 # Utilities
│   ├── text_parser.py     # Text cleaning
│   ├── date_parser.py     # Date parsing
│   └── fallback_parser.py # Quick fallback
├── handlers/              # Request handlers
│   └── webhook_handler.py # Teams webhook
├── main_new.py           # FastAPI app (new)
├── main.py               # Old version (backup)
├── common.py             # Old common (backup)
└── .env                  # Environment variables
```

## 🚀 Cài đặt

### 1. Clone và cài dependencies:
```bash
git clone <repo-url>
cd teams-jira-ai
pip install -r requirements.txt
```

### 2. Tạo file `.env`:
```env
JIRA_SERVER=https://your-domain.atlassian.net
JIRA_API_TOKEN=your_jira_api_token
JIRA_PROJECT_KEY=PROJ
GEMINI_API_KEY=your_gemini_api_key
```

### 3. Chạy ứng dụng:

**Sử dụng version mới (recommended):**
```bash
python main_new.py
```

**Hoặc với uvicorn:**
```bash
uvicorn main_new:app --host 0.0.0.0 --port 8000 --reload
```

**Version cũ (backup):**
```bash
python main.py
```

## 📝 Ví dụ sử dụng

### 1. Tạo task với priority và dates:
```
@JiraBot tạo task: Fix bug login page
Priority: High
Bắt đầu từ: 15/01/2024
Hạn chót: 20/01/2024
Gán cho: Nguyễn Văn A
Epic link: DXAI
```

AI sẽ tự động:
- ✅ Tạo Task với priority High
- ✅ Set start date = 2024-01-15
- ✅ Set due date = 2024-01-20
- ✅ Assign cho Nguyễn Văn A
- ✅ Link với Epic DXAI

### 2. Tạo task với ảnh/video:
```
@JiraBot tạo task: Design new homepage
Mockup: https://imgur.com/abc123.png
Demo video: https://youtu.be/xyz789
```

AI sẽ:
- ✅ Tạo Task
- ✅ Download và attach ảnh
- ✅ Thêm video link vào comment

### 3. Sử dụng relative dates:
```
@JiraBot Bug: Login không hoạt động
Priority: khẩn cấp
Bắt đầu: hôm nay
Deadline: ngày mai
```

AI nhận diện:
- Priority: Highest (từ "khẩn cấp")
- Start: hôm nay
- Due: ngày mai

## 🔧 API Endpoints

### GET `/`
Health check
```json
{
  "message": "Teams Jira AI Bot is running",
  "version": "2.0",
  "status": "healthy"
}
```

### POST `/webhook/teams`
Nhận message từ Teams và tạo Jira issue

**Request:**
```json
{
  "text": "<at>JiraBot</at> Tạo task..."
}
```

**Response:**
```json
{
  "type": "message",
  "text": "✅ Đã tạo Task thành công!\n• Key: [PROJ-123](...)\n• Tiêu đề: ..."
}
```

## 🛠️ Development

### Chạy tests:
```bash
pytest tests/
```

### Cấu trúc code:
- **config/** - Tất cả settings và prompts
- **models/** - Data classes và message templates
- **services/** - Business logic (AI, Jira)
- **utils/** - Helper functions
- **handlers/** - Request handlers

### Thêm tính năng mới:
1. Cập nhật `config/prompts.py` cho AI
2. Thêm field vào `models/task_info.py`
3. Update logic trong `services/`
4. Test với fallback parser trong `utils/fallback_parser.py`

## 📊 Performance

- ⚡ Response time: < 5s (thường 2-3s)
- 🤖 AI timeout: 2.8s (fallback nếu vượt)
- 📋 Background updates: Epic link, assignee, dates, attachments

## 🔐 Security

- API tokens trong `.env` (không commit)
- Validate inputs
- Error handling toàn diện

## 📄 License

MIT

## 👥 Contributors

- Your Name

## 📞 Support

Issues: [GitHub Issues](link)
Docs: [Wiki](link)
