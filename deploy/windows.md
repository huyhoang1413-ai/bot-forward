# Chạy bot 24/7 trên Windows

Có 2 cách giữ bot chạy nền và tự khởi động lại. Chọn 1.

## Cách A — Task Scheduler (không cần cài thêm gì)

1. Tạo file `run-bot.bat` trong thư mục dự án:
   ```bat
   @echo off
   cd /d "%~dp0"
   call .venv\Scripts\activate
   python -m bot
   ```
2. Mở **Task Scheduler** → **Create Task** (không phải Basic Task).
   - **General**: đặt tên `BotForward`; chọn *Run whether user is logged on or not*.
   - **Triggers** → New → *At startup*.
   - **Actions** → New → *Start a program* → chọn `run-bot.bat`.
   - **Settings**: bật *If the task fails, restart every 1 minute* (số lần restart = 3).
3. OK → nhập mật khẩu Windows nếu được hỏi.

Hạn chế: Task Scheduler khởi động lại chậm hơn và ít "mượt" hơn service thật.

## Cách B — NSSM (chạy như Windows Service, khuyến nghị)

1. Tải NSSM: https://nssm.cc/download → giải nén, lấy `win64\nssm.exe`.
2. Mở **CMD (Run as Administrator)**:
   ```bat
   nssm install BotForward
   ```
3. Trong cửa sổ NSSM:
   - **Path**: `D:\Hoc Code\BOT-Forward\.venv\Scripts\python.exe`
   - **Startup directory**: `D:\Hoc Code\BOT-Forward`
   - **Arguments**: `-m bot`
   - Tab **Exit actions**: *Restart* (mặc định) — bot tự chạy lại khi crash.
   - Tab **I/O** (tùy chọn): Output/Error trỏ tới `D:\Hoc Code\BOT-Forward\service.log`.
4. **Install service** → khởi động:
   ```bat
   nssm start BotForward
   ```
5. Quản lý: `nssm stop BotForward`, `nssm restart BotForward`,
   `nssm remove BotForward confirm` để gỡ.

Xem log: mở file `bot.log` trong thư mục dự án (bot tự ghi, xoay vòng 3 file).
