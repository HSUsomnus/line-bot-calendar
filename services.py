import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
import config

def get_calendar_service():
    creds = service_account.Credentials.from_service_account_file(
        config.SERVICE_ACCOUNT_FILE, scopes=config.SCOPES)
    service = build('calendar', 'v3', credentials=creds)
    return service

def query_month_events(month_str):
    try:
        target_month = int(month_str)
        now = datetime.datetime.now()
        year = now.year
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
        if not events:
            return f"📅 {roc_year}-{target_month}月 目前沒有安排活動喔！"
            
        reply = f"📣{roc_year}-{target_month}月活動🎉\n\n"
        for event in events:
            # 判斷是整日 (date) 還是 計時 (dateTime)
            if 'date' in event['start']:
                start = event['start']['date'] # YYYY-MM-DD
                # 簡單抓月日
                m_str = str(int(start[5:7]))
                d_str = str(int(start[8:10]))
                summary = event.get('summary', '無標題')
                reply += f"{m_str}/{d_str} {summary} (整日)\n"
            else:
                start = event['start'].get('dateTime', '')
                m_str = str(int(start[5:7]))
                d_str = str(int(start[8:10]))
                summary = event.get('summary', '無標題')
                reply += f"{m_str}/{d_str} {summary}\n"
                
        return reply.strip()
    except Exception as e:
        return f"查詢月份失敗：{str(e)}"