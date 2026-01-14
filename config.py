# config.py
import os

# LINE Bot 設定
LINE_CHANNEL_ACCESS_TOKEN = 'LihvenpN9POEQcic0RinwKtyGTNmIROQ3pQOlMlLn370Tx4BObz9paF2FRwFmJtWWUguw2Q50DEXkZeLb7N5pP+kUzmx8rMbWFYWEq728KVwhlOZWkG2yNlrHIypuwMhh3xgbMCN8KTwafCRo1P9FQdB04t89/1O/w1cDnyilFU='
LINE_CHANNEL_SECRET = '99109aa509e2403e9e082d28a5a7394d'

# Google Calendar 設定
CALENDAR_ID = '044af9594df67ecf346aac448b1163ad573883d187c335ffa7e97b6da102f0a8@group.calendar.google.com'
SCOPES = ['https://www.googleapis.com/auth/calendar']
SERVICE_ACCOUNT_FILE = '/etc/secrets/service_account.json' 
# 注意：在 Render 上我們會用 Secret Files 產生成這個路徑，
# 如果在本地測試報錯，請暫時改回 'service_account.json'