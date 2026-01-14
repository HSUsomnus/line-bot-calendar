import datetime
from datetime import timedelta # 👈 記得引入這個用來減一天
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
        
        # 設定查詢範圍：該月1號 ~ 下個月1號
        # (Google API 會自動抓取「時間重疊」的活動，所以跨月活動也會被抓出來)
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
            singleEvents=True, 
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])
        
        roc_year = year - 1911
        if not events:
            return f"📅 {roc_year}-{target_month}月 目前沒有安排活動喔！"
            
        reply = f"📣{roc_year}-{target_month}月活動🎉\n\n"
        
        for event in events:
            summary = event.get('summary', '無標題')
            
            # =================================================
            # 👇 邏輯判斷：整日活動 (含跨日/跨月)
            # =================================================
            if 'date' in event['start']:
                start_str = event['start']['date'] # YYYY-MM-DD
                end_str = event['end']['date']     # YYYY-MM-DD
                
                s_dt = datetime.datetime.strptime(start_str, '%Y-%m-%d')
                e_dt = datetime.datetime.strptime(end_str, '%Y-%m-%d')
                
                # Google 的結束日是「隔天」，所以顯示時要減 1 天
                display_end_dt = e_dt - timedelta(days=1)
                
                # 判斷是否為「多日」活動
                if s_dt == display_end_dt:
                    # 單日：顯示 1/17
                    date_str = f"{s_dt.month}/{s_dt.day}"
                else:
                    # 多日(跨日或跨月)：顯示 1/28-2/1
                    # 格式：開始月/日-結束月/日
                    date_str = f"{s_dt.month}/{s_dt.day}-{display_end_dt.month}/{display_end_dt.day}"
                
                reply += f"{date_str} {summary}(整日)\n"
            
            # =================================================
            # 👇 邏輯判斷：計時活動 (例如 13:00-15:00)
            # =================================================
            else:
                start_str = event['start'].get('dateTime', '')
                # 解析時間字串 (ISO 格式)
                s_dt = datetime.datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                
                # 簡單顯示：月/日
                date_str = f"{s_dt.month}/{s_dt.day}"
                reply += f"{date_str} {summary}\n"
                
        return reply.strip()
        
    except Exception as e:
        return f"查詢月份失敗：{str(e)}"