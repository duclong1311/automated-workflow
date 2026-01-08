# Migration Guide: v1.0 → v2.0

## 📋 Checklist di chuyển

### 1. Backup files cũ
```bash
# File main.py và common.py đã được giữ lại làm backup
# Không cần xóa - để tham khảo nếu cần
```

### 2. Cài đặt dependencies
```bash
pip install -r requirements.txt
```

### 3. Kiểm tra .env file
File `.env` không thay đổi, sử dụng như cũ:
```env
JIRA_SERVER=https://your-domain.atlassian.net
JIRA_API_TOKEN=your_jira_api_token
JIRA_PROJECT_KEY=PROJ
GEMINI_API_KEY=your_gemini_api_key
```

### 4. Test code mới
```bash
# Test import modules
python -c "from handlers.webhook_handler import process_teams_message; print('OK')"

# Test services
python -c "from services.gemini_service import GeminiService; print('OK')"
python -c "from services.jira_service import JiraService; print('OK')"

# Chạy server
python main_new.py
```

### 5. Cập nhật webhook URL (nếu cần)
- Endpoint không đổi: `/webhook/teams`
- Có thể chạy cả 2 version song song (port khác nhau)

## 🔄 So sánh thay đổi

### Cấu trúc cũ:
```
main.py (800+ lines)
common.py (50 lines)
```

### Cấu trúc mới:
```
config/
  - settings.py (environment vars)
  - prompts.py (AI prompts)
models/
  - task_info.py (data class)
  - messages.py (responses)
services/
  - gemini_service.py (AI logic)
  - jira_service.py (Jira logic)
utils/
  - text_parser.py (clean text)
  - date_parser.py (parse dates)
  - fallback_parser.py (quick parse)
handlers/
  - webhook_handler.py (main logic)
main_new.py (clean entry point)
```

## ✨ Tính năng mới

### 1. Priority Detection
**Cũ:** Chỉ có 3 levels cố định
**Mới:** AI tự nhận diện từ text
```python
# Keywords được nhận diện:
- "urgent", "khẩn cấp" → Highest
- "high", "cao", "ưu tiên" → High
- "medium", "trung bình" → Medium
- "low", "thấp" → Low
```

### 2. Date Parsing
**Cũ:** Không hỗ trợ
**Mới:** Nhận diện start_date, due_date
```python
# Formats được hỗ trợ:
- "15/01/2024", "15-01-2024"
- "2024-01-15"
- "hôm nay", "ngày mai", "tuần sau"
- "start date: ...", "deadline: ..."
```

### 3. Media Handling
**Cũ:** Không hỗ trợ
**Mới:** Tự động extract và attach
```python
# Supported:
- Image: .jpg, .png, .gif, .webp
- Video: .mp4, .mov, youtube.com, vimeo.com
- Auto download images
- Add URLs to comments
```

### 4. Background Updates
**Cũ:** Sync (chậm)
**Mới:** Create fast → Update in background
```python
# Workflow:
1. Create issue với minimal fields (< 1s)
2. Response ngay cho user
3. Update epic/assignee/dates/media trong background
```

## 🐛 Breaking Changes

### Import paths
**Cũ:**
```python
from common import GEMINI_PARSE_PROMPT, Messages, Config
```

**Mới:**
```python
from config.prompts import GEMINI_PARSE_PROMPT
from config.settings import settings
from models.messages import Messages
```

### Config access
**Cũ:**
```python
Config.AI_TIMEOUT
Config.BOT_MENTION_NAME
```

**Mới:**
```python
settings.AI_TIMEOUT
settings.BOT_MENTION_NAME
```

### Functions
**Cũ:**
```python
ask_gemini_to_parse_task(text)  # In main.py
update_issue_async(...)  # In main.py
```

**Mới:**
```python
gemini_service.parse_task(text)  # In services/
jira_service.update_issue(...)  # In services/
```

## 🧪 Testing

### Test từng module:

```bash
# Test config
python -c "from config.settings import settings; print(settings.JIRA_SERVER)"

# Test models
python -c "from models.task_info import TaskInfo; t = TaskInfo('test', 'Task', 'desc'); print(t)"

# Test utils
python -c "from utils.date_parser import parse_vietnamese_date; print(parse_vietnamese_date('15/01/2024'))"

# Test full flow
curl -X POST http://localhost:8000/webhook/teams \
  -H "Content-Type: application/json" \
  -d '{"text": "@JiraBot tạo task test"}'
```

## 📊 Performance comparison

### v1.0:
- Response time: 3-5s
- All operations sync
- Timeout risk

### v2.0:
- Response time: 1-3s (create only)
- Background updates
- Better timeout handling
- Fallback parser

## 🔧 Rollback plan

Nếu cần rollback về v1.0:

```bash
# Stop new version
pkill -f main_new

# Run old version
python main.py
```

## 📝 TODO sau migration

- [ ] Test với real Teams messages
- [ ] Verify Jira field IDs (customfield_*)
- [ ] Check performance với load cao
- [ ] Update Teams bot webhook URL (nếu đổi port)
- [ ] Delete old files khi stable:
  - `main.py` (old)
  - `common.py` (old)
  - Rename `main_new.py` → `main.py`

## 💡 Tips

1. **Chạy song song**: Có thể chạy cả 2 version trên ports khác nhau để test
2. **Check logs**: Log format giống nhau, dễ so sánh
3. **Gradual migration**: Có thể chuyển từng tính năng một
4. **Keep backups**: Giữ lại old files ít nhất 1 tuần

## ❓ FAQ

**Q: Code cũ có hoạt động không?**
A: Có, `main.py` vẫn hoạt động bình thường

**Q: Có thể dùng một số modules mới trong code cũ?**
A: Có, ví dụ: `from utils.date_parser import parse_vietnamese_date`

**Q: Priority/Dates có hoạt động với fallback parser?**
A: Có, fallback parser cũng hỗ trợ các tính năng mới

**Q: Performance có tốt hơn?**
A: Có, nhờ background updates và better caching

---

Last updated: 2026-01-08
