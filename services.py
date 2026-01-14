import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
import config

def get_calendar_service():
    creds = service_account.Credentials.from_service_account_file(
        config.SERVICE_ACCOUNT_FILE, scopes=config.SCOPES)
    service = build('calendar', 'v3', credentials=creds)
    return service

def query_consultation_events(month_str):
    try:
        target_month = int(month_str)
        now = datetime.datetime.now()
        year = now.year
        
        # 設定查詢範圍
        start_date = datetime.datetime(year, target_month, 1)
        if target_month == 12:
            end_date = datetime.datetime(year + 1, 1, 1)
        else:
            end_date = datetime.datetime(year, target_month + 1, 1)
        
        service = get_calendar_service()
        events_result = service.events().list(
            calendarId=config.CALENDAR_ID,
            timeMin=start_date.isoformat() + '+08:00',
            timeMax=end_date.isoformat() + '+08:00',
            singleEvents=True, orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])
        
        roc_year = year - 1911
        # 關鍵字過濾
        keywords = ['諮詢', '簽約', '週轉']
        filtered_events = []
        
        for event in events:
            summary = event.get('summary', '')
            if any(k in summary for k in keywords):
                filtered_events.append(event)

        if not filtered_events:
            return f"📣{roc_year}-{target_month}月諮詢簽約💵\n\n目前沒有安排喔！", False
            
        reply = f"📣{roc_year}-{target_month}月諮詢簽約💵\n\n"
        for event in filtered_events:
            summary = event.get('summary', '無標題')
            if 'date' in event['start']:
                start = event['start']['date']
                m_str = str(int(start[5:7]))
                d_str = str(int(start[8:10]))
                reply += f"{m_str}/{d_str} {summary}\n"
            else:
                start = event['start'].get('dateTime', '')
                m_str = str(int(start[5:7]))
                d_str = str(int(start[8:10]))
                reply += f"{m_str}/{d_str} {summary}\n"
                
        return reply.strip(), True
        
    except Exception as e:
        return f"查詢失敗：{str(e)}", False
        
# (保留原本的 query_month_events 函數，這裡不重複貼上)
# 您原本的 query_month_events 請保留在下面