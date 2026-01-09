# AI Jira Task Automation (Teams & Gemini)

Công cụ tự động hóa quy trình quản lý dự án, giúp tạo Jira Task ngay lập tức từ tin nhắn trên Microsoft Teams thông qua sức mạnh của Gemini AI.

**Tính năng chính**
- **AI Parsing**: Tự động trích xuất Tiêu đề, Mô tả, Mức độ ưu tiên và Loại công việc (Task/Bug) từ ngôn ngữ tự nhiên.
- **Whitelist Security**: Chỉ cho phép tạo task từ các Channel ID được cấu hình sẵn.
- **Jira Integration**: Kết nối trực tiếp với Jira Server/Data Center thông qua Personal Access Token (PAT).
- **Real-time Response**: Phản hồi link task trực tiếp trong luồng hội thoại trên Teams.

## Yêu cầu hệ thống
- Python 3.12+
- Ngrok (để tạo đường hầm webhook cục bộ)
- Tài khoản Jira (ví dụ: Kaopiz) & Gemini API Key

## Cài đặt
1. Clone repo và vào thư mục dự án

```bash
cd teams-jira-ai
```

2. Tạo và kích hoạt môi trường ảo

```bash
python3 -m venv venv
source venv/bin/activate
```

3. Cài đặt thư viện

```bash
pip install google-genai fastapi uvicorn jira python-dotenv
```

## Cấu hình biến môi trường
Tạo file `.env` từ file mẫu và điền thông tin của bạn:

```bash
cp .env.example .env
nano .env
```

Các tham số cần điền:
- `JIRA_SERVER`: URL Jira của bạn (Ví dụ: https://jira.kaopiz.com)
- `JIRA_API_TOKEN`: Personal Access Token từ Jira
- `JIRA_PROJECT_KEY`: Mã dự án (Ví dụ: BUILDEE)
- `GEMINI_API_KEY`: API key từ Google AI Studio
- `ALLOWED_CHANNELS`: Danh sách Channel ID (phân tách bằng dấu phẩy)
- `BITBUCKET_AUTO_COMMENT`: Bật/tắt comment tự động từ Bitbucket (mặc định: `true`). Đặt `false` để tắt comment tự động.

Ví dụ `.env` (không lưu trữ công khai):

```
JIRA_SERVER=https://jira.kaopiz.com
JIRA_API_TOKEN=xxxxxxxxxxxxxxxx
JIRA_PROJECT_KEY=BUILDEE
GEMINI_API_KEY=xxxxxxxxxxxxxxxx
ALLOWED_CHANNELS=19:abcd1234@thread.tacv2,19:efgh5678@thread.tacv2
BITBUCKET_AUTO_COMMENT=true
```

## Vận hành

1. Khởi động Server

```bash
python main.py
```

Server mặc định chạy tại http://0.0.0.0:8000.

2. Mở Webhook ra Internet (ngrok)

```bash
ngrok http 8000
```

Copy link ngrok (ví dụ: https://xxxx.ngrok-free.app).

3. Cấu hình Microsoft Teams

- Vào Channel -> Manage team -> Apps -> Create an outgoing webhook.
- Name: `JiraBot` (hoặc tên bạn muốn).
- Callback URL: `https://<NGROK_DOMAIN>/webhook/teams` (ví dụ: https://xxxx.ngrok-free.app/webhook/teams).
- Sau khi tạo, thử gõ `@JiraBot test` trong channel — server Python sẽ in ra Channel ID. Thêm Channel ID này vào `ALLOWED_CHANNELS` trong `.env`.

## Cách sử dụng
Trong channel đã cấu hình, gõ `@JiraBot` kèm yêu cầu bằng tiếng Việt hoặc tiếng Anh. Ví dụ:

```
@JiraBot tạo bug lỗi không đăng nhập được trên Android, mức độ nghiêm trọng cao
```

Bot sẽ phân tích yêu cầu và trả về link tới issue Jira nếu tạo thành công cùng thông tin tóm tắt.

## Lưu ý bảo mật
- KHÔNG push file `.env` lên GitHub.
- Chỉ thêm Channel ID vào `ALLOWED_CHANNELS` nếu bạn tin tưởng các thành viên trong channel.
- Mỗi lần chạy lại `ngrok` có thể tạo ra URL mới — đảm bảo cập nhật Callback URL trong Teams nếu cần.

## Troubleshooting nhanh
- Nếu bot không phản hồi: kiểm tra logs server (`main.py`) để xem có nhận webhook từ Teams hay không.
- Nếu không thể kết nối Jira: kiểm tra `JIRA_SERVER` và `JIRA_API_TOKEN`.

## Developer
Developed by AnhLD

---

Nếu bạn muốn, tôi có thể tiếp tục: thêm `README` tiếng Anh, cập nhật `.env.example`, hoặc tạo script để tự động commit và push (loại bỏ `.env`).
