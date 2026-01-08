# Teams Jira AI Bot - Architecture Overview

## 📐 Kiến trúc tổng quan

```
┌─────────────────────────────────────────────────────────────┐
│                       Teams Webhook                          │
│                    POST /webhook/teams                       │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    main_new.py (FastAPI)                     │
│  - Nhận request từ Teams                                     │
│  - Clean message text                                        │
│  - Gọi webhook_handler                                       │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              handlers/webhook_handler.py                     │
│  - Orchestrate toàn bộ flow                                  │
│  - Timeout management (< 5s)                                 │
│  - Background task scheduling                                │
└────────┬───────────────────────────────┬────────────────────┘
         │                               │
         ▼                               ▼
┌────────────────────┐         ┌────────────────────┐
│ services/          │         │ services/          │
│ gemini_service.py  │         │ jira_service.py    │
│                    │         │                    │
│ - Parse text       │         │ - Create issue     │
│ - AI extraction    │         │ - Update issue     │
│ - Validate data    │         │ - Find epic        │
│ - Fallback logic   │         │ - Find user        │
└────────┬───────────┘         └──────────┬─────────┘
         │                                 │
         │ Uses                           │ Uses
         │                                 │
         ▼                                 ▼
┌─────────────────────────────────────────────────────────────┐
│                         models/                              │
│  - task_info.py: TaskInfo dataclass                          │
│  - messages.py: Response templates                           │
└─────────────────────────────────────────────────────────────┘
         │
         │ Uses
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                          utils/                              │
│  - text_parser.py: Clean Teams messages, extract URLs        │
│  - date_parser.py: Parse dates (Vietnamese + English)        │
│  - fallback_parser.py: Quick regex-based parsing             │
└─────────────────────────────────────────────────────────────┘
         │
         │ Uses
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                         config/                              │
│  - settings.py: Environment variables                        │
│  - prompts.py: AI prompts                                    │
└─────────────────────────────────────────────────────────────┘
```

## 🔄 Request Flow

### Phase 1: Parse Request (< 3s)
```
1. Teams sends message → FastAPI endpoint
2. Clean HTML and mentions → utils/text_parser
3. Parse with AI (timeout 2.8s) → services/gemini_service
4. If timeout → Fallback parser → utils/fallback_parser
5. Extract media URLs → utils/text_parser
6. Parse dates → utils/date_parser
```

### Phase 2: Create Issue (< 1s)
```
1. Create minimal Jira issue → services/jira_service
2. Return response immediately → User sees result
3. Schedule background tasks → FastAPI BackgroundTasks
```

### Phase 3: Background Update (async, after response)
```
1. Find and link Epic → jira_service.find_epic()
2. Find and assign User → jira_service._find_user()
3. Update priority if detected
4. Set start_date if detected
5. Set due_date if detected
6. Download and attach images → jira_service._add_media_attachments()
7. Add video URLs to comments
```

## 📦 Module Dependencies

```
main_new.py
  └── handlers/webhook_handler.py
      ├── services/gemini_service.py
      │   ├── config/prompts.py
      │   ├── config/settings.py
      │   └── models/task_info.py
      ├── services/jira_service.py
      │   ├── config/settings.py
      │   └── models/task_info.py
      ├── utils/text_parser.py
      ├── utils/date_parser.py
      └── utils/fallback_parser.py
          ├── models/task_info.py
          └── utils/date_parser.py
```

## 🎯 Design Decisions

### 1. Modular Architecture
**Why?** Dễ maintain, test và mở rộng
- Mỗi module có 1 responsibility rõ ràng
- Easy to mock khi test
- Có thể thay thế service (ví dụ: đổi AI provider)

### 2. Background Updates
**Why?** Fast response time (< 5s requirement)
- Tạo issue ngay với minimal fields
- User nhận response nhanh
- Update chi tiết sau trong background

### 3. Fallback Parser
**Why?** Reliability khi AI slow/down
- Regex-based parsing luôn hoạt động
- Slower nhưng reliable
- Hỗ trợ tất cả features chính

### 4. Dataclass for TaskInfo
**Why?** Type safety và validation
- Clear data structure
- Easy to serialize/deserialize
- Type hints giúp IDE autocomplete

### 5. Separate Config
**Why?** Environment-agnostic code
- Easy to change settings
- No hardcoded values
- Support multiple environments (dev/prod)

## 🧩 Component Responsibilities

### config/
- **settings.py**: Load env vars, define constants
- **prompts.py**: AI prompts, templates

### models/
- **task_info.py**: Data structure cho task information
- **messages.py**: Response message templates

### services/
- **gemini_service.py**: AI parsing, validation
- **jira_service.py**: All Jira operations (CRUD, search)

### utils/
- **text_parser.py**: Text cleaning, URL extraction
- **date_parser.py**: Date parsing (Vietnamese/English, relative/absolute)
- **fallback_parser.py**: Quick regex parsing

### handlers/
- **webhook_handler.py**: Orchestrate request flow, timeout management

## 🔐 Security Considerations

1. **Environment Variables**: All secrets in .env
2. **Input Validation**: Clean and validate all inputs
3. **API Token Security**: Never log tokens
4. **Error Handling**: Don't expose internal errors to user
5. **Rate Limiting**: Consider adding for production

## 📊 Performance Optimizations

1. **Parallel Execution**: AI và data extraction có thể song song
2. **Background Tasks**: Non-critical updates sau response
3. **Caching**: Có thể cache epic/user lookups (future)
4. **Timeout Management**: Fail fast với fallback
5. **Minimal Initial Create**: Chỉ tạo required fields trước

## 🧪 Testing Strategy

### Unit Tests
- Test từng function trong utils/
- Mock services trong handlers
- Test TaskInfo validation

### Integration Tests
- Test full flow với mock Jira/AI
- Test timeout scenarios
- Test fallback logic

### E2E Tests
- Test với real Teams messages
- Verify Jira creation
- Check background updates

## 🚀 Future Enhancements

1. **Caching Layer**: Cache epic/user lookups với Redis
2. **Queue System**: Use Celery cho background tasks
3. **Webhooks**: Notify Teams khi background update done
4. **Bulk Operations**: Tạo nhiều tasks cùng lúc
5. **Analytics**: Track success rate, response time
6. **Admin Dashboard**: Monitor bot status, stats

## 📖 Reading Guide

### Để hiểu flow chính:
1. Đọc `main_new.py` - Entry point
2. Đọc `handlers/webhook_handler.py` - Main logic
3. Đọc `services/` - Business logic

### Để hiểu AI parsing:
1. Đọc `config/prompts.py` - AI prompt
2. Đọc `services/gemini_service.py` - Parsing logic
3. Đọc `utils/fallback_parser.py` - Fallback

### Để hiểu Jira operations:
1. Đọc `services/jira_service.py` - All Jira logic
2. Đọc `models/task_info.py` - Data structure

### Để customize:
1. Update `config/prompts.py` cho AI behavior
2. Update `config/settings.py` cho constants
3. Add new fields vào `models/task_info.py`

---

Last updated: 2026-01-08
Version: 2.0
