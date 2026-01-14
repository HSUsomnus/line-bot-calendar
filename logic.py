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

# 使用者狀態
user_sessions = {}
user_states = {} 

# 定義狀態
STATE_WAITING_NAME = 'WAITING_NAME'
STATE_WAITING_TYPE = 'WAITING_TYPE'
STATE_WAITING_METHOD = 'WAITING_METHOD'
STATE_WAITING_DATETIME = 'WAITING_DATETIME'
STATE_WAITING_CONFIRM = 'WAITING_CONFIRM'

# 定義流程類型 (區分是 諮詢 還是 上課)
FLOW_CONSULT = 'FLOW_CONSULT'
FLOW_CLASS = 'FLOW_CLASS'

# 選項定義
TYPES_CONSULT = ['保單諮詢', '保單簽約', '專屬諮詢', '天耀週轉']
TYPES_CLASS = ['金流正式課', '財富藍圖課']

# --- 啟動流程 ---
def start_add_flow(user_id, flow_type=FLOW_CONSULT):
    user_states[user_id] = {
        'step': STATE_WAITING_NAME,
        'flow': flow_type, # 記住現在是哪種流程
        'data': {}
    }
    return TextSendMessage(text="請輸入名字？")

def handle_user_input(user_id, text, postback_data=None, postback_params=None):
    if user_id not in user_states:
        return None
    
    current_state = user_states[user_id]
    current_step = current_state['step']
    current_flow = current_state['flow']
    data = current_state['data']
    
    # 1. 輸入名字
    if current_step == STATE_WAITING_NAME:
        data['name'] = text
        user_states[user_id]['step'] = STATE_WAITING_TYPE
        
        # 根據流程顯示不同按鈕
        if current_flow == FLOW_CONSULT:
            items = [QuickReplyButton(action=MessageAction(label=t, text=t)) for t in TYPES_CONSULT]
        else: # FLOW_CLASS
            items = [QuickReplyButton(action=MessageAction(label=t, text=t)) for t in TYPES_CLASS]
            
        return TextSendMessage(text=f"嗨 {text}，請選擇類型？", quick_reply=QuickReply(items=items))

    # 2. 選擇類型
    elif current_step == STATE_WAITING_TYPE:
        # 檢查輸入是否合法
        valid_types = TYPES_CONSULT if current_flow == FLOW_CONSULT else TYPES_CLASS
        if text not in valid_types:
            return TextSendMessage(text="請點選下方的按鈕選擇類型喔！")
        
        data['type'] = text
        
        # 分歧點：諮詢流程可能要問線上/實體，上課流程直接問時間
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
            # 學員上課流程：直接跳問時間
            user_states[user_id]['step'] = STATE_WAITING_DATETIME
            return request_datetime_picker()

    # 3. 選擇 實體/線上 (只有諮詢流程會進來)
    elif current_step == STATE_WAITING_METHOD:
        if text not in ['實體', '線上']:
            return TextSendMessage(text="請選擇實體或線上。")
        data['method'] = text
        user_states[user_id]['step'] = STATE_WAITING_DATETIME
        return request_datetime_picker()

    # 4. 選擇 日期時間
    elif current_step == STATE_WAITING_DATETIME:
        if not postback_params:
            return TextSendMessage(text="請點擊按鈕選擇時間喔！")
        
        dt_str = postback_params['datetime'] 
        dt_obj = datetime.datetime.fromisoformat(dt_str)
        data['datetime'] = dt_obj
        
        # 預覽文字生成
        month = dt_obj.month
        day = dt_obj.day
        name = data['name']
        ctype = data['type']
        
        if current_flow == FLOW_CONSULT:
            # 諮詢格式：2/1 毓紘保單諮詢(21線上)
            hour = dt_obj.hour
            method = data.get('method', '實體')
            preview_text = f"{month}/{day} {name}{ctype}({hour}{method})"
        else:
            # 上課格式：2/18 毓紘財富藍圖課
            preview_text = f"{month}/{day} {name}{ctype}"
        
        data['preview'] = preview_text
        user_states[user_id]['step'] = STATE_WAITING_CONFIRM
        
        actions = [
            QuickReplyButton(action=MessageAction(label="正確", text="確認:正確")),
            QuickReplyButton(action=MessageAction(label="錯誤", text="確認:錯誤"))
        ]
        return TextSendMessage(text=f"新增內容：\n{preview_text}\n\n請問是否正確？", quick_reply=QuickReply(items=actions))

    # 5. 確認
    elif current_step == STATE_WAITING_CONFIRM:
        if text == "確認:正確":
            start_dt = data['datetime']
            
            # 設定結束時間邏輯
            if current_flow == FLOW_CONSULT:
                duration = utils.DURATION_MAP.get(data['type'], 1)
                end_dt = start_dt + timedelta(hours=duration)
                # 標題格式：去掉日期
                summary = data['preview'].split(' ', 1)[1]
            else:
                # 學員上課時間邏輯
                # 金流/財富藍圖 預設 18:30 結束 (參考 utils 邏輯)
                end_dt = start_dt.replace(hour=18, minute=30)
                summary = f"{data['name']}{data['type']}" # 標題：名字+課程名
            
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

def request_datetime_picker():
    return TextSendMessage(
        text="請選擇日期與時間",
        quick_reply=QuickReply(items=[
            QuickReplyButton(action=DatetimePickerAction(
                label="選擇時間", data="action=sel_time", mode="datetime"
            ))
        ])
    )

# --- 保留原本的 process_next_event 和 finish_and_write ---
def process_next_event(user_id):
    # (請貼上之前完整的程式碼，這裡省略)
    pass

def finish_and_write(user_id):
    # 這裡放簡化版示意，請用您 logic.py 裡原本完整的版本
    service = services.get_calendar_service()
    to_write = user_sessions[user_id].get('to_write', [])
    for item in to_write:
        body = {
            'summary': item['summary'],
            'start': {'dateTime': item['start'].isoformat(), 'timeZone': 'Asia/Taipei'},
            'end': {'dateTime': item['end'].isoformat(), 'timeZone': 'Asia/Taipei'},
        }
        service.events().insert(calendarId=config.CALENDAR_ID, body=body).execute()
    del user_sessions[user_id]
    return TextSendMessage(text="完成")