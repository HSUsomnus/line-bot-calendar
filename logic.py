import datetime
import difflib
from datetime import timedelta
from linebot.models import (
    TextSendMessage, QuickReply, QuickReplyButton, MessageAction, 
    PostbackAction, DatetimePickerAction
)
import services
import config
import utils

# 狀態管理
user_sessions = {}
user_states = {} 

# 互動流程狀態常數
STATE_WAITING_NAME = 'WAITING_NAME'
STATE_WAITING_TYPE = 'WAITING_TYPE'
STATE_WAITING_METHOD = 'WAITING_METHOD'
STATE_WAITING_DATETIME = 'WAITING_DATETIME'
STATE_WAITING_CONFIRM = 'WAITING_CONFIRM'

FLOW_CONSULT = 'FLOW_CONSULT'
FLOW_CLASS = 'FLOW_CLASS'

TYPES_CONSULT = ['保單諮詢', '保單簽約', '專屬諮詢', '天耀週轉']
TYPES_CLASS = ['金流正式課', '財富藍圖課']

# --- 1. 互動式流程控制 ---

def start_add_flow(user_id, flow_type=FLOW_CONSULT):
    user_states[user_id] = {
        'step': STATE_WAITING_NAME,
        'flow': flow_type,
        'data': {}
    }
    return TextSendMessage(text="請輸入名字？")

def request_datetime_picker():
    return TextSendMessage(
        text="請選擇日期與時間",
        quick_reply=QuickReply(items=[
            QuickReplyButton(action=DatetimePickerAction(
                label="選擇時間", data="action=sel_time", mode="datetime"
            ))
        ])
    )

def handle_user_input(user_id, text, postback_data=None, postback_params=None):
    if user_id not in user_states:
        return None
    
    current_state = user_states[user_id]
    current_step = current_state['step']
    current_flow = current_state['flow']
    data = current_state['data']
    
    # 輸入名字
    if current_step == STATE_WAITING_NAME:
        data['name'] = text
        user_states[user_id]['step'] = STATE_WAITING_TYPE
        
        if current_flow == FLOW_CONSULT:
            items = [QuickReplyButton(action=MessageAction(label=t, text=t)) for t in TYPES_CONSULT]
        else: 
            items = [QuickReplyButton(action=MessageAction(label=t, text=t)) for t in TYPES_CLASS]
            
        return TextSendMessage(text=f"嗨 {text}，請選擇類型？", quick_reply=QuickReply(items=items))

    # 選擇類型
    elif current_step == STATE_WAITING_TYPE:
        valid_types = TYPES_CONSULT if current_flow == FLOW_CONSULT else TYPES_CLASS
        if text not in valid_types:
            return TextSendMessage(text="請點選下方的按鈕選擇類型喔！")
        
        data['type'] = text
        
        if current_flow == FLOW_CONSULT:
            if text in ['保單諮詢', '專屬諮詢']:
                user_states[user_id]['step'] = STATE_WAITING_METHOD
                actions = [
                    QuickReplyButton(action=MessageAction(label="實體", text="實體")),
                    QuickReplyButton(action=MessageAction(label="線上", text="線上"))
                ]
                return TextSendMessage(text="請問是實體還是線上？", quick_reply=QuickReply(items=actions))
            else:
                data['method'] = '實體'
                user_states[user_id]['step'] = STATE_WAITING_DATETIME
                return request_datetime_picker()
        else:
            user_states[user_id]['step'] = STATE_WAITING_DATETIME
            return request_datetime_picker()

    # 選擇方式 (僅諮詢)
    elif current_step == STATE_WAITING_METHOD:
        if text not in ['實體', '線上']:
            return TextSendMessage(text="請選擇實體或線上。")
        data['method'] = text
        user_states[user_id]['step'] = STATE_WAITING_DATETIME
        return request_datetime_picker()

    # 選擇時間
    elif current_step == STATE_WAITING_DATETIME:
        if not postback_params:
            return TextSendMessage(text="請點擊按鈕選擇時間喔！")
        
        dt_str = postback_params['datetime'] 
        dt_obj = datetime.datetime.fromisoformat(dt_str)
        data['datetime'] = dt_obj
        
        month = dt_obj.month
        day = dt_obj.day
        name = data['name']
        ctype = data['type']
        
        if current_flow == FLOW_CONSULT:
            hour = dt_obj.hour
            method = data.get('method', '實體')
            preview_text = f"{month}/{day} {name}{ctype}({hour}{method})"
        else:
            preview_text = f"{month}/{day} {name}{ctype}"
        
        data['preview'] = preview_text
        user_states[user_id]['step'] = STATE_WAITING_CONFIRM
        
        actions = [
            QuickReplyButton(action=MessageAction(label="正確", text="確認:正確")),
            QuickReplyButton(action=MessageAction(label="錯誤", text="確認:錯誤"))
        ]
        return TextSendMessage(text=f"新增內容：\n{preview_text}\n\n請問是否正確？", quick_reply=QuickReply(items=actions))

    # 確認新增
    elif current_step == STATE_WAITING_CONFIRM:
        if text == "確認:正確":
            start_dt = data['datetime']
            
            if current_flow == FLOW_CONSULT:
                duration = utils.DURATION_MAP.get(data['type'], 1)
                end_dt = start_dt + timedelta(hours=duration)
                summary = data['preview'].split(' ', 1)[1]
            else:
                end_dt = start_dt.replace(hour=18, minute=30)
                summary = f"{data['name']}{data['type']}"
            
            item = {
                'summary': summary,
                'start': start_dt,
                'end': end_dt,
                'operation': 'insert',
                'all_day': False
            }
            
            if user_id not in user_sessions:
                user_sessions[user_id] = {'to_write': []}
            user_sessions[user_id]['to_write'].append(item)
            del user_states[user_id]
            
            finish_and_write(user_id)
            return TextSendMessage(text=f"已新增{data['preview']}")
            
        elif text == "確認:錯誤":
            del user_states[user_id]
            return TextSendMessage(text="已結束新增流程。")

    return None

# --- 2. 批次處理邏輯 (process_next_event) ---

def process_next_event(user_id):
    if user_id not in user_sessions or not user_sessions[user_id].get('queue'):
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
            if 'date' in old_event['start']:
                old_start_str = old_event['start']['date']
                old_start_dt = datetime.datetime.strptime(old_start_str, '%Y-%m-%d')
            else:
                old_start_str = old_event['start'].get('dateTime', '')
                old_start_dt = datetime.datetime.fromisoformat(old_start_str.replace('Z', '+00:00'))
                old_start_dt = old_start_dt.replace(tzinfo=None)
            
            is_time_conflict = False
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

# --- 3. 寫入與決策 ---

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
            if item.get('all_day'):
                event_body = {
                    'summary': item['summary'],
                    'start': {'date': item['start'].strftime('%Y-%m-%d')},
                    'end': {'date': item['end'].strftime('%Y-%m-%d')},
                }
            else:
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