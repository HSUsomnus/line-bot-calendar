import os

# --- 從環境變數讀取設定 (安全做法) ---

# 如果找不到環境變數 (例如在本地測試)，會回傳 None 或後面的預設值
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')

# 日曆 ID 也建議藏起來
CALENDAR_ID = os.environ.get('CALENDAR_ID')

SCOPES = ['https://www.googleapis.com/auth/calendar']

# 這裡路徑維持不變，因為我們已經用 Render 的 Secret Files 處理過了
SERVICE_ACCOUNT_FILE = '/etc/secrets/service_account.json'