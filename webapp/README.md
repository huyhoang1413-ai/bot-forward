# Bot Forward Panel

Web panel (1 admin) để quản lý **nhiều bot Telegram forward**. Dán token bot → hệ thống
tự xác thực, mã hoá lưu, bật **webhook**, và bot có ngay chức năng forward hai chiều
giữa các nhóm. Tái dùng logic `copy_message` từ bot đơn lẻ.

- FastAPI + SQLModel + **SQLite** (đổi Postgres sau qua `DATABASE_URL`).
- Bot chạy bằng **webhook** (1 endpoint `/webhook/{bot_id}` cho tất cả bot).
- Token bot **mã hoá Fernet** khi lưu.
- Deploy: Docker Compose + **Caddy** (tự động HTTPS).

## Yêu cầu
- Python 3.11+ (dev) hoặc Docker (prod).
- **Domain + HTTPS công khai** (bắt buộc cho webhook). Dev local: dùng ngrok/Cloudflare Tunnel.

## Cấu hình
```bash
cp .env.example .env
# Tạo KEK để mã hoá token:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Điền vào `.env`: `ADMIN_PASSWORD`, `SESSION_SECRET`, `BOT_TOKEN_KEK` (KEK vừa tạo — **backup lại**),
`PUBLIC_URL` (URL HTTPS công khai).

## Chạy local (dev)
```bash
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Mở http://localhost:8000 → đăng nhập bằng `ADMIN_PASSWORD`.

Webhook cần HTTPS công khai. Mở tunnel rồi đặt `PUBLIC_URL`:
```bash
ngrok http 8000        # copy URL https://xxxx.ngrok-free.app vào PUBLIC_URL, restart
```

## Deploy (VPS + Docker)
1. Trỏ A-record domain về server; mở port 80/443.
2. Sửa `Caddyfile` → thay `bots.example.com` bằng domain thật.
3. Điền `.env` (đặt `PUBLIC_URL=https://your-domain`).
4. `docker compose up -d --build`
5. Mở `https://your-domain` → đăng nhập.

## Dùng
1. Đăng nhập → **dán token bot** (từ @BotFather) → Thêm bot.
   - Nhớ `/setprivacy` → Disable (hoặc để bot làm admin) để bot đọc được tin nhóm.
2. Thêm bot làm **admin** vào các nhóm.
3. Gõ `/chatid` trong mỗi nhóm → bot trả `chat_id`.
4. Vào trang bot → thêm **tuyến** (nguồn → đích), tick *Hai chiều* cho bridge.
5. Forward chạy ngay, không cần restart.

## Test
```bash
pytest
```
Kiểm thử thật (mã hoá, logic forward, auth, webhook secret), không mock/không gọi mạng.

## Người gửi được forward + nhãn
**Khai báo chung, gán theo nhóm — có tìm kiếm + phân trang (chịu được 500–1000 người).**
- **Trang "Quản lý người gửi"** (`/bots/{id}/senders`, mở từ chi tiết bot): khai báo mỗi người + nhãn **một lần**, có ô **tìm kiếm** theo username và **phân trang** (50/trang), sửa nhãn / xoá tại chỗ.
- **Trang quản lý theo nhóm** (`/bots/{id}/groups/{source}/senders`, mở từ mỗi nhóm trong "Tuyến forward"): 2 cột — bên trái **tìm & thêm** người từ danh sách chung; bên phải danh sách **đang được phép** với nút xoá. Thêm/xoá **từng người** (không tải cả nghìn checkbox).
- **Danh sách chung trống = forward mọi người** (mọi nhóm — mặc định cũ).
- Nhóm **chưa gán ai** = **forward mọi người** ở nhóm đó (mở). Nhóm **có gán ≥1 người** = **chỉ forward những người đó**.
- Thêm người mới vào danh sách chung → nhớ **gán họ vào các nhóm** cần forward (người chưa gán sẽ bị chặn ở nhóm đã giới hạn).
- Đặt **nhãn** cho username → tin hiển thị **`[Tên] nội dung`** (áp dụng cho mọi tin của người có nhãn, kể cả nhóm mở):
  - Giữ nguyên định dạng gốc (in đậm/link/emoji).
  - Ảnh/video/file: nhãn ghép vào caption. Tin không chữ (sticker, poll…): gửi 1 tin `[Tên]` ngay trước.
  - Để trống nhãn = không gắn. Nhãn ≤32 ký tự, không chứa `[` `]` / xuống dòng.
- Khớp theo username (không phân biệt hoa/thường). Người **không username**, admin ẩn danh, tin channel → bị chặn khi danh sách có người.
- **Nhãn gắn liền allowlist**: chỉ đặt nhãn cho người trong danh sách được forward.

## Mật khẩu truy cập bot (tuỳ chọn)
Khoá riêng từng bot bằng 1 mật khẩu (khác mật khẩu đăng nhập panel):
- Khi **thêm bot**: điền "Mật khẩu truy cập bot (tuỳ chọn)" — để trống nếu không khoá.
- Hoặc vào trang bot → mục **"Mật khẩu truy cập bot"** → đặt/đổi/xoá (để trống = xoá khoá).
- Bot có khoá hiện icon 🔒 ở danh sách. Mỗi phiên, mở khoá 1 lần (nhập đúng mật khẩu) là dùng tới khi đăng xuất.
- Bảo vệ **trang cấu hình** của bot (route, người gửi, nhãn, xoá bot). **Không** ảnh hưởng việc bot forward (Telegram vẫn gửi webhook bình thường).
- Mật khẩu lưu dạng **hash PBKDF2** (không lưu thô).

## Giới hạn đã biết
- Không đồng bộ xoá/sửa tin đã forward (giới hạn Bot API).
- Album ảnh copy thành từng tin riêng.
- ~50–100 bot trên 1 VPS nhỏ (webhook).
- Khớp người gửi theo username (không theo user-id) → ai đổi/xoá username sẽ không còn khớp.

## Bảo mật
- Secrets chỉ trong `.env` (git-ignored). **Backup `BOT_TOKEN_KEK`** — mất là không giải mã được token.
- Token không bao giờ hiện lại trên UI/log. Webhook xác thực qua secret header.
- Nếu lộ token bot: `/revoke` ở @BotFather, xoá + thêm lại bot trong panel.
