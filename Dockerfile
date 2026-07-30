FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/ ./bot/

# Token comes from env (.env via compose); routes mounted at runtime.
CMD ["python", "-m", "bot"]
