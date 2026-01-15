# 使用輕量級的 Python 3.9
FROM python:3.9-slim

# 設定工作目錄
WORKDIR /app

# 複製所有檔案到容器內
COPY . .

# 安裝 Python 套件
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn

# 設定環境變數 (讓 Python 知道即時顯示 log)
ENV PYTHONUNBUFFERED=True
ENV PORT=8080

# 啟動指令 (使用 gunicorn 取代原本的 app.run)
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app