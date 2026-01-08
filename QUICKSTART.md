# 🚀 Quick Start Guide - Teams Jira AI Bot v2.0

## ⚡ Chạy nhanh (5 phút)

### Bước 1: Cài đặt dependencies
```bash
pip install -r requirements.txt
```

### Bước 2: Cấu hình .env
File `.env` đã có, kiểm tra và cập nhật nếu cần:
```env
JIRA_SERVER=https://your-domain.atlassian.net
JIRA_API_TOKEN=your_token
JIRA_PROJECT_KEY=PROJ
GEMINI_API_KEY=your_key
```

### Bước 3: Test import
```bash
python test_samples.py
```

Kết quả mong đợi:
```
✅ config.settings
✅ models.task_info
✅ services.gemini_service
✅ services.jira_service
✅ utils.text_parser
✅ utils.date_parser
✅ handlers.webhook_handler

🎉 All imports successful!
```

### Bước 4: Chạy server
```bash
python main_new.py
```

Hoặc với uvicorn (recommended):
```bash
uvicorn main_new:app --host 0.0.0.0 --port 8000 --reload
```

### Bước 5: Test API
```bash
# Health check
curl http://localhost:8000/health

# Test webhook
curl -X POST http://localhost:8000/webhook/teams \
  -H "Content-Type: application/json" \
  -d '{"text": "@JiraBot tạo task test priority cao"}'
```

## 📁 Cấu trúc Project (Tổng quan)

```
teams-jira-ai/
├── 📂 config/              # Configuration
│   ├── settings.py        # Env settings (JIRA_SERVER, API keys...)
│   └── prompts.py         # AI prompts (GEMINI_PARSE_PROMPT)
│
├── 📂 models/              # Data models
│   ├── task_info.py       # TaskInfo dataclass
│   └── messages.py        # Response templates
│
├── 📂 services/            # Business logic
│   ├── gemini_service.py  # AI parsing service
│   └── jira_service.py    # Jira CRUD operations
│
├── 📂 utils/               # Utilities
│   ├── text_parser.py     # Clean Teams HTML, extract URLs
│   ├── date_parser.py     # Parse dates (Vietnamese/English)
│   └── fallback_parser.py # Quick regex parsing (fallback)
│
├── 📂 handlers/            # Request handlers
│   └── webhook_handler.py # Main webhook logic
│
├── 📄 main_new.py         # FastAPI app (v2.0) ⭐ USE THIS
├── 📄 main.py             # Old version (backup)
├── 📄 common.py           # Old common (backup)
│
├── 📄 test_samples.py     # Test cases
├── 📄 requirements.txt    # Dependencies
├── 📄 .env                # Environment vars
│
└── 📚 Docs/
    ├── README_NEW.md      # Full documentation
    ├── ARCHITECTURE.md    # Architecture overview
    └── MIGRATION.md       # Migration guide v1→v2
```

## ✨ Tính năng mới v2.0

### 1️⃣ AI nhận diện Priority
```
Input: "@JiraBot Bug khẩn cấp: Login lỗi"
AI detect: priority = "Highest"
```

Keywords:
- `khẩn cấp`, `urgent` → Highest
- `cao`, `high` → High
- `thấp`, `low` → Low

### 2️⃣ Nhận diện Dates
```
Input: "Bắt đầu: 15/01/2024, Deadline: tuần sau"
AI detect:
  - start_date = "2024-01-15"
  - due_date = "2024-01-15" (+ 7 days)
```

Formats hỗ trợ:
- Absolute: `15/01/2024`, `2024-01-15`
- Relative: `hôm nay`, `ngày mai`, `tuần sau`

### 3️⃣ Xử lý Media (Ảnh/Video)
```
Input: "Screenshot: https://imgur.com/abc.png"
Bot:
  ✅ Download và attach ảnh
  ✅ Thêm video URLs vào comment
```

### 4️⃣ Background Updates
```
Flow:
1. Create issue (1-2s) → Response ngay ✅
2. Update epic, assignee, dates, media (background)
```

## 🎯 Ví dụ sử dụng

### Basic Task
```
@JiraBot tạo task: Update API documentation
```

### Task với Priority + Dates
```
@JiraBot Bug: Payment gateway timeout
Priority: High
Bắt đầu: hôm nay
Hạn: tuần sau
```

### Task đầy đủ
```
@JiraBot tạo task: Implement new feature X
Priority: Cao
Bắt đầu từ: 20/01/2024
Deadline: 31/01/2024
Gán cho: Nguyễn Văn A
Epic link: PROJ-100
Screenshot: https://imgur.com/design.png
```

## 🔧 Cấu hình Jira Fields

Một số customfield IDs cần verify trong Jira instance của bạn:

```python
# services/jira_service.py

# Epic link field (thường là một trong những cái này)
'customfield_10014'  # Phổ biến nhất
'customfield_10011'
'customfield_10016'

# Start date field
'startDate'
'customfield_10015'

# Due date field
'duedate'  # Standard field
```

Kiểm tra field IDs:
```python
# Get all fields
fields = jira.fields()
for f in fields:
    print(f"{f['id']}: {f['name']}")
```

## 🐛 Troubleshooting

### Import Error
```bash
# Check Python path
export PYTHONPATH=/home/anhld/teams-jira-ai:$PYTHONPATH

# Or run from project root
cd /home/anhld/teams-jira-ai
python main_new.py
```

### Jira Connection Error
```bash
# Test connection
python -c "from services.jira_service import JiraService; j = JiraService()"
# Should see: ✅ Kết nối Jira thành công
```

### AI Timeout
- AI timeout = 2.8s → Dùng fallback parser
- Fallback vẫn hỗ trợ priority, dates, epic, assignee

### Field Update Error
- Check Jira field IDs (`customfield_*`)
- Check screen configuration (field có hiển thị không?)
- Check permissions (user có quyền set field không?)

## 📊 Performance Tips

1. **Tăng AI timeout** (nếu mạng chậm):
   ```python
   # config/settings.py
   AI_TIMEOUT = 4.0  # Từ 2.8s → 4s
   ```

2. **Bỏ qua media download** (nếu không cần):
   ```python
   # services/jira_service.py
   # Comment out download logic, chỉ add URLs
   ```

3. **Cache epic/user lookups**:
   ```python
   # TODO: Add Redis cache
   ```

## 🔄 Rollback về v1.0

Nếu có vấn đề:
```bash
# Stop new version
pkill -f main_new

# Run old version
python main.py
```

## 📚 Đọc thêm

- [README_NEW.md](README_NEW.md) - Full documentation
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
- [MIGRATION.md](MIGRATION.md) - Migration guide
- [test_samples.py](test_samples.py) - Test cases

## 💡 Tips

1. **Test locally trước**: Dùng curl test webhook
2. **Check logs**: Xem log để debug
3. **Verify field IDs**: Mỗi Jira instance khác nhau
4. **Gradual rollout**: Test với 1 team trước khi deploy toàn bộ

## ✅ Checklist Deploy

- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] .env configured
- [ ] Test imports OK (`python test_samples.py`)
- [ ] Jira connection OK
- [ ] AI connection OK
- [ ] Test webhook locally
- [ ] Verify field IDs
- [ ] Update Teams webhook URL
- [ ] Monitor logs
- [ ] Test with real messages

---

🎉 **Ready to go!** Run `python main_new.py` and start creating tasks!

Last updated: 2026-01-08
