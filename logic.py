import datetime
import difflib
from datetime import timedelta
from linebot.models import TextSendMessage, QuickReply, QuickReplyButton, MessageAction
import services
import config

# 使用者狀態存放區
user_sessions = {}

def process_next_event(user_id):
    if user_id not in user_sessions or not user_sessions[user_id]['queue']:
        return finish_and_write(user_id)

    current_new_event = user_sessions[user_id]['queue'][0]
    service = services.get_calendar_service()

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
        calendarId=config.CALENDAR_ID,
        timeMin=search_min,
        timeMax=search_max,
        singleEvents=True
    ).execute()
    existing_events = events_result.get('items', [])

    best_match = None
    similarity_threshold = 0.5 

    for old_event in existing_events:
        old_title = old_event.get('summary', '')
        new_title = current_new_event['summary']
        
        ratio = difflib.SequenceMatcher(None, new_title, old_title).ratio()
        if new_title in old_title or old_title in new_title:
            ratio = 1.0

        if ratio > similarity_threshold:
            # 判斷舊活動是整日(date) 還是 計時(dateTime)
            if 'date' in old_event['start']:
                old_start_str = old_event['start']['date'] # YYYY-MM-DD
                old_start_dt = datetime.datetime.strptime(old_start_str, '%Y-%m-%d')
            else:
                old_start_str = old_event['start'].get('dateTime', '')
                old_start_dt = datetime.datetime.fromisoformat(old_start_str.replace('Z', '+00:00'))
                old_start_dt = old_start_dt.replace(tzinfo=None)
            
            is_time_conflict = False
            # 只要開始日期是同一天，就視為衝突/相關
            if old_start_dt.date() == current_new_event['start'].date():
                is_time_conflict = True
            
            best_match = {
                'event_id': old_event['id'],
                'summary': old_title,
                'start_str': old_start_str[:16].replace('T', ' '),
                'ratio': ratio,
                'conflict': is_time_conflict
            }
            break
    
    if best_match:
        user_sessions[user_id]['current_conflict'] = {
            'new': current_new_event,
            'old': best_match
        }
        
        # 顯示時間格式微調
        if current_new_event.get('all_day'):
            new_time_str = current_new_event['start'].strftime('%m/%d (整日)')
        else:
            new_time_str = current_new_event['start'].strftime('%m/%d %H:%M')
        
        if best_match['conflict']:
            msg = f"⚠️ 發現同月份撞期衝突！\n\n新行程：{new_time_str} {current_new_event['summary']}\n舊行程：{best_match['start_str']} {best_match['summary']}\n\n請問要怎麼做？"
            actions = [
                QuickReplyButton(action=MessageAction(label="覆蓋舊行程", text="決策:覆蓋")),
                QuickReplyButton(action=MessageAction(label="新增(保留兩者)", text="決策:新增")),
                QuickReplyButton(action=MessageAction(label="取消此項", text="決策:取消"))
            ]
        else:
            msg = f"🤔 發現同月份相似行程 (疑似改期)\n\n新行程：{new_time_str} {current_new_event['summary']}\n舊行程：{best_match['start_str']} {best_match['summary']}\n\n請問要怎麼做？"
            actions = [
                QuickReplyButton(action=MessageAction(label="取代(改期)", text="決策:取代")),
                QuickReplyButton(action=MessageAction(label="新增(變兩場)", text="決策:新增")),
                QuickReplyButton(action=MessageAction(label="取消此項", text="決策:取消"))
            ]
        return TextSendMessage(text=msg, quick_reply=QuickReply(items=actions))
    
    else:
        item = user_sessions[user_id]['queue'].pop(0) 
        item['operation'] = 'insert'
        user_sessions[user_id]['to_write'].append(item)
        return process_next_event(user_id)

def finish_and_write(user_id):
    to_write = user_sessions[user_id].get('to_write', [])
    if not to_write:
        if user_id in user_sessions: del user_sessions[user_id]
        return TextSendMessage(text="沒有任何行程被新增。")
    
    service = services.get_calendar_service()
    count_insert = 0
    count_update = 0
    
    try:
        for item in to_write:
            # ==========================================
            # 👇 關鍵修改：區分 整日 vs 計時
            # ==========================================
            if item.get('all_day'):
                # 整日活動格式：使用 'date' (YYYY-MM-DD)
                event_body = {
                    'summary': item['summary'],
                    'start': {'date': item['start'].strftime('%Y-%m-%d')},
                    'end': {'date': item['end'].strftime('%Y-%m-%d')}, # 結束日已在 utils 加了一天
                }
            else:
                # 計時活動格式：使用 'dateTime' (ISO Format)
                event_body = {
                    'summary': item['summary'],
                    'start': {'dateTime': item['start'].isoformat(), 'timeZone': 'Asia/Taipei'},
                    'end': {'dateTime': item['end'].isoformat(), 'timeZone': 'Asia/Taipei'},
                }
            
            if item['operation'] == 'insert':
                service.events().insert(calendarId=config.CALENDAR_ID, body=event_body).execute()
                count_insert += 1
            elif item['operation'] == 'update':
                service.events().update(calendarId=config.CALENDAR_ID, eventId=item['event_id'], body=event_body).execute()
                count_update += 1
                
        if user_id in user_sessions: del user_sessions[user_id]
        return TextSendMessage(text=f"🎉 完成！\n新增 {count_insert} 筆\n修改 {count_update} 筆")
        
    except Exception as e:
        return TextSendMessage(text=f"寫入過程發生錯誤：{str(e)}")

def handle_decision(user_id, decision):
    if user_id not in user_sessions or 'current_conflict' not in user_sessions[user_id]:
        return TextSendMessage(text="⚠️ 操作已逾時，請重新傳送活動列表。")

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
        
    return process_next_event(user_id)