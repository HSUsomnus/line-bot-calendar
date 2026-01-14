from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, QuickReply, QuickReplyButton, MessageAction
import os
import datetime
import re 
import difflib 
from datetime import timedelta 
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = Flask(__name__)

# ==========================================
# 👇 請務必填回你的 LINE Bot 與日曆資料
# ==========================================
LINE_CHANNEL_ACCESS_TOKEN = 'LihvenpN9POEQcic0RinwKtyGTNmIROQ3pQOlMlLn370Tx4BObz9paF2FRwFmJtWWUguw2Q50DEXkZeLb7N5pP+kUzmx8rMbWFYWEq728KVwhlOZWkG2yNlrHIypuwMhh3xgbMCN8KTwafCRo1P9FQdB04t89/1O/w1cDnyilFU='
LINE_CHANNEL_SECRET = '99109aa509e2403e9e082d28a5a7394d'
CALENDAR_ID = '044af9594df67ecf346aac448b1163ad573883d187c335ffa7e97b6da102f0a8@group.calendar.google.com'

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

SCOPES = ['https://www.googleapis.com/auth/calendar']
SERVICE_ACCOUNT_FILE = 'service_account.json'

# --- 使用者狀態管理 (Session) ---
user_sessions = {}

def get_calendar_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    service = build('calendar', 'v3', credentials=creds)
    return service

# --- 查詢整月活動 ---
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
            calendarId=CALENDAR_ID,
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
            start = event['start'].get('dateTime', event['start'].get('date'))
            m_str = str(int(start[5:7]))
            d_str = str(int(start[8:10]))
            summary = event.get('summary', '無標題')
            reply += f"{m_str}/{d_str} {summary}\n"
        return reply.strip()
    except Exception as e:
        return f"查詢月份失敗：{str(e)}"

# --- 解析邏輯 (維持不變) ---
def parse_schedule_text(text):
    lines = text.split('\n')
    events_to_check = []
    default_year = datetime.datetime.now().year
    
    header_match = re.search(r'(\d{2,3})[-\u4e00-\u9fa5]', lines[0])
    if header_match:
        roc_year = int(header_match.group(1))
        default_year = 1911 + roc_year

    for line in lines:
        date_match = re.match(r'(\d{1,2})/(\d{1,2})\s+(.*)', line)
        if date_match:
            month = int(date_match.group(1))
            day = int(date_match.group(2))
            content = date_match.group(3)
            
            time_range_match = re.search(r'\((\d{1,2})-(\d{1,2})', content)
            time_single_match = re.search(r'\((\d{1,2})', content)
            
            start_dt = None
            end_dt = None

            if time_range_match:
                h_start = int(time_range_match.group(1))
                h_end = int(time_range_match.group(2))
                start_dt = datetime.datetime(default_year, month, day, h_start, 0, 0)
                end_dt = datetime.datetime(default_year, month, day, h_end, 0, 0)
            elif time_single_match:
                h_start = int(time_single_match.group(1))
                start_dt = datetime.datetime(default_year, month, day, h_start, 0, 0)
                if '金流正式課' in content or '財富藍圖' in content:
                    end_dt = start_dt.replace(hour=18, minute=30)
                elif h_start == 13:
                    end_dt = start_dt.replace(hour=17, minute=0)
                else:
                    end_dt = start_dt + timedelta(hours=2)
            else:
                start_dt = datetime.datetime(default_year, month, day, 9, 0, 0)
                end_dt = start_dt + timedelta(hours=2)

            events_to_check.append({
                'summary': content,
                'start': start_dt,
                'end': end_dt,
                'raw_line': line
            })
    return events_to_check

# ==========================================
# 👇 新增重點：客製化相似度判斷函式
# ==========================================
def calculate_similarity(title1, title2):
    # 1. 地點快篩：如果前兩個字不同 (例如 桃園 vs 台南)，直接判定為不相似
    # (前提是標題長度都要大於2)
    if len(title1) >= 2 and len(title2) >= 2:
        if title1[:2] != title2[:2]:
            return 0.0 # 完全不相似

    # 2. 去除數字干擾：把括號內的時間數字拿掉，只比對文字
    # 例如 "桃園組聚會(13-17財商)" -> "桃園組聚會(財商)"
    # 例如 "桃園組聚(12財商)" -> "桃園組聚(財商)"
    clean_t1 = re.sub(r'\d+[-:]?\d*', '', title1)
    clean_t2 = re.sub(r'\d+[-:]?\d*', '', title2)

    # 3. 計算相似度
    ratio = difflib.SequenceMatcher(None, clean_t1, clean_t2).ratio()
    return ratio

# --- 核心邏輯：處理佇列 ---
def process_next_event(user_id):
    if user_id not in user_sessions or not user_sessions[user_id]['queue']:
        return finish_and_write(user_id)

    current_new_event = user_sessions[user_id]['queue'][0]
    service = get_calendar_service()

    # 鎖定同月份
    target_date = current_new_event['start']
    year = target_date.year
    month = target_date.month
    
    month_start = datetime.datetime(year, month, 1)
    if month == 12:
        next_month_start = datetime.datetime(year + 1, 1, 1)
    else:
        next_month_start = datetime.datetime(year, month + 1, 1)

    search_min = month_start.isoformat() + '+08:00'
    search_max = next_month_start.isoformat() + '+08:00'

    events_result = service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=search_min,
        timeMax=search_max,
        singleEvents=True
    ).execute()
    existing_events = events_result.get('items', [])

    best_match = None
    # 🔥 門檻調高到 0.8，確保 "財商" vs "加盟" (文字差異大) 會被視為不同
    similarity_threshold = 0.8 

    for old_event in existing_events:
        old_title = old_event.get('summary', '')
        new_title = current_new_event['summary']
        
        # 使用新的比對邏輯
        ratio = calculate_similarity(new_title, old_title)

        if ratio > similarity_threshold:
            old_start_str = old_event['start'].get('dateTime', old_event['start'].get('date'))
            old_start_dt = datetime.datetime.fromisoformat(old_start_str.replace('Z', '+00:00'))
            old_start_dt = old_start_dt.replace(tzinfo=None)
            
            # 判斷時間是否衝突 (有重疊)
            # 邏輯：新開始 < 舊結束 AND 新結束 > 舊開始
            new_start = current_new_event['start']
            new_end = current_new_event['end']
            old_end_dt = datetime.datetime.fromisoformat(
                old_event['end'].get('dateTime', old_event['end'].get('date')).replace('Z', '+00:00')
            ).replace(tzinfo=None)

            is_time_conflict = (new_start < old_end_dt) and (new_end > old_start_dt)
            
            best_match = {
                'event_id': old_event['id'],
                'summary': old_title,
                'start_str': old_start_str[:16].replace('T', ' '),
                'ratio': ratio,
                'conflict': is_time_conflict
            }
            break # 找到最像的就停
    
    if best_match:
        user_sessions[user_id]['current_conflict'] = {
            'new': current_new_event,
            'old': best_match
        }
        
        new_time_str = current_new_event['start'].strftime('%m/%d %H:%M')
        
        if best_match['conflict']:
            # 同月份 + 相似 + 時間衝突 (如 2/1 vs 2/1 撞期)
            msg = f"⚠️ 發現同月份時間衝突！\n\n新行程：{new_time_str} {current_new_event['summary']}\n舊行程：{best_match['start_str']} {best_match['summary']}\n\n請問要怎麼做？"
            actions = [
                QuickReplyButton(action=MessageAction(label="覆蓋舊行程", text="決策:覆蓋")),
                QuickReplyButton(action=MessageAction(label="新增(保留兩者)", text="決策:新增")),
                QuickReplyButton(action=MessageAction(label="取消此項", text="決策:取消"))
            ]
        else:
            # 同月份 + 相似 + 時間不衝突 (如 2/1 vs 2/7 改期)
            msg = f"🤔 發現同月份相似行程 (疑似改期)\n\n新行程：{new_time_str} {current_new_event['summary']}\n舊行程：{best_match['start_str']} {best_match['summary']}\n\n請問要怎麼做？"
            actions = [
                QuickReplyButton(action=MessageAction(label="取代(改期)", text="決策:取代")),
                QuickReplyButton(action=MessageAction(label="新增(變兩場)", text="決策:新增")),
                QuickReplyButton(action=MessageAction(label="取消此項", text="決策:取消"))
            ]
            
        return TextSendMessage(text=msg, quick_reply=QuickReply(items=actions))
    
    else:
        # 完全無相似 (不同地點 or 不同主題) -> 直接新增
        item = user_sessions[user_id]['queue'].pop(0) 
        item['operation'] = 'insert'
        user_sessions[user_id]['to_write'].append(item)
        return process_next_event(user_id)

# --- 最終寫入 ---
def finish_and_write(user_id):
    to_write = user_sessions[user_id].get('to_write', [])
    if not to_write:
        del user_sessions[user_id]
        return TextSendMessage(text="沒有任何行程被新增。")
    
    service = get_calendar_service()
    count_insert = 0
    count_update = 0
    
    try:
        for item in to_write:
            event_body = {
                'summary': item['summary'],
                'start': {'dateTime': item['start'].isoformat(), 'timeZone': 'Asia/Taipei'},
                'end': {'dateTime': item['end'].isoformat(), 'timeZone': 'Asia/Taipei'},
            }
            
            if item['operation'] == 'insert':
                service.events().insert(calendarId=CALENDAR_ID, body=event_body).execute()
                count_insert += 1
            elif item['operation'] == 'update':
                service.events().update(calendarId=CALENDAR_ID, eventId=item['event_id'], body=event_body).execute()
                count_update += 1
                
        del user_sessions[user_id]
        return TextSendMessage(text=f"🎉 完成！\n新增 {count_insert} 筆\n修改 {count_update} 筆")
        
    except Exception as e:
        return TextSendMessage(text=f"寫入過程發生錯誤：{str(e)}")

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text
    user_id = event.source.user_id
    
    if msg.startswith("決策:") and user_id in user_sessions and 'current_conflict' in user_sessions[user_id]:
        decision = msg.split(":")[1]
        conflict_data = user_sessions[user_id]['current_conflict']
        new_item = conflict_data['new']
        old_item = conflict_data['old']
        
        user_sessions[user_id]['queue'].pop(0)
        del user_sessions[user_id]['current_conflict']
        
        if decision == "新增":
            new_item['operation'] = 'insert'
            user_sessions[user_id]['to_write'].append(new_item)
            
        elif decision in ["覆蓋", "取代"]:
            new_item['operation'] = 'update'
            new_item['event_id'] = old_item['event_id']
            user_sessions[user_id]['to_write'].append(new_item)
            
        elif decision == "取消":
            pass
            
        line_bot_api.reply_message(event.reply_token, process_next_event(user_id))
        return

    month_match = re.match(r'^(\d+)月活動$', msg)
    if month_match:
        reply = query_month_events(month_match.group(1))
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    if '月活動' in msg or re.search(r'\d+/\d+', msg):
        new_events = parse_schedule_text(msg)
        if not new_events:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 格式無法解析"))
            return
            
        user_sessions[user_id] = {
            'queue': new_events,
            'to_write': [],
        }
        
        line_bot_api.reply_message(event.reply_token, process_next_event(user_id))
        return

    if msg == '查行程':
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入「2月活動」查詢，或直接貼上列表新增。"))

if __name__ == "__main__":
    app.run(port=5000)