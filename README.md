# BOT-Forward — Bot Telegram forward hai chiều giữa các nhóm

Bot dùng **Telegram Bot API** để cầu nối (bridge) tin nhắn **hai chiều** giữa các nhóm.
Tin nhắn gửi ở nhóm A được sao chép sang nhóm B và ngược lại — hỗ trợ mọi loại:
text, ảnh, video, file, sticker...

- Không cần database (stateless, KISS).
- Cấu hình bằng file: `.env` (token) + `config/routes.yaml` (các cặp nhóm).
- Dùng `copy_message` → tin sạch, không hiện nhãn "Forwarded from".

## Yêu cầu
- Python 3.11+
- Một bot token từ [@BotFather](https://t.me/BotFather)

## Cài đặt

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

## Tạo bot & lấy token
1. Chat với **@BotFather** → `/newbot` → đặt tên → nhận **token**.
2. **Quan trọng**: tắt privacy mode để bot đọc được tin trong nhóm:
   `/setprivacy` → chọn bot → **Disable**.
   (Hoặc cấp bot làm **admin** trong nhóm — admin luôn nhận được mọi tin.)
3. Copy file cấu hình:
   ```bash
   cp .env.example .env
   cp config/routes.example.yaml config/routes.yaml
   ```
4. Mở `.env`, dán token vào `BOT_TOKEN=...`

## Thêm bot vào nhóm & lấy chat_id
1. Thêm bot vào **cả hai** nhóm, và đặt bot làm **admin** (cần quyền gửi tin).
2. Chạy bot (xem dưới), gõ `/chatid` trong mỗi nhóm → bot trả về `chat_id`.
3. Điền cặp id vào `config/routes.yaml`:
   ```yaml
   bridges:
     - [-1001111111111, -1002222222222]
   log_level: INFO
   ```
4. Khởi động lại bot để nạp cấu hình mới.

## Chạy bot
```bash
python -m bot
```
Gửi thử một tin ở nhóm A → nó xuất hiện ở nhóm B, và ngược lại.

Lệnh có sẵn: `/start`, `/chatid`, `/status`.

## Chạy 24/7
- **Windows**: xem [deploy/windows.md](deploy/windows.md) (Task Scheduler hoặc NSSM).
- **Linux VPS**: xem [deploy/systemd-bot-forward.service](deploy/systemd-bot-forward.service).
- **Docker**:
  ```bash
  docker compose up -d --build
  ```

## Test
```bash
pytest
```

## Giới hạn đã biết
- **Không đồng bộ xóa tin**: Bot API không báo khi ai đó xóa tin → không xóa bản sao được.
- **Không sửa/sync tin đã forward**: bản sao là tin độc lập.
- **Album ảnh**: mỗi ảnh trong album được sao chép thành tin riêng (chưa gộp lại thành album).

## Bảo mật
- Token chỉ để trong `.env` — **không commit**. Nếu lỡ lộ, thu hồi token qua @BotFather (`/revoke`).
- Chỉ cấp bot quyền admin tối thiểu (gửi tin); không cần quyền xóa/ban.
