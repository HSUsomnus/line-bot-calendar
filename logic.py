import datetime
import difflib
from datetime import timedelta
from linebot.models import (
    TextSendMessage, QuickReply, QuickReplyButton, MessageAction, 
    PostbackAction, DatetimePickerAction, TemplateSendMessage, ConfirmTemplate
)
import services
import config
import utils

# 使用者狀態與暫存資料
user_sessions = {}
# 對話狀態機：儲存使用者目前進行到哪一步
user_states = {} 

# 定義狀態常數
STATE_WAITING_NAME = 'WAITING_NAME'
STATE_WAITING_TYPE = 'WAITING_TYPE'
STATE_WAITING_METHOD = 'WAITING_METHOD'
STATE_WAITING_DATETIME = 'WAITING_DATETIME'
STATE_WAITING_CONFIRM = 'WAITING_CONFIRM'

# 定義選項
TYPES = ['保單諮詢', '保單簽約', '專屬諮詢', '天耀週轉']

# --- 互動式新增流程 (Start) ---
def start_add_flow(user_id):
    user_states[user_id] = {
        'step': STATE_WAITING_NAME,
        'data': {}
    }
    return TextSendMessage(text="請輸入名字？")

def handle_user_input(user_id, text, postback_data=None, postback_params=None):
    # 檢查該使用者是否在對話流程中
    if user_id not in user_states:
        return None
    
    current_step = user_states[user_id]['step']
    data = user_states[user_id]['data']
    
    # 1. 輸入名字階段
    if current_step == STATE_WAITING_NAME:
        data['name'] = text
        user_states[user_id]['step'] = STATE_WAITING_TYPE
        
        # 產生類型按鈕
        actions = [QuickReplyButton(action=MessageAction(label=t, text=t)) for t in TYPES]
        return TextSendMessage(text=f"嗨 {text}，請選擇類型？", quick_reply=QuickReply(items=actions))

    # 2. 選擇類型階段
    elif current_step == STATE_WAITING_TYPE:
        if text not in TYPES:
            return TextSendMessage(text="請點選下方的按鈕選擇類型喔！")
        
        data['type'] = text
        
        # 判斷是否需要問 實體/線上
        if text in ['保單諮詢', '專屬諮詢']:
            user_states[user_id]['step'] = STATE_WAITING_METHOD
            actions = [
                QuickReplyButton(action=MessageAction(label="實體", text="實體")),
                QuickReplyButton(action=MessageAction(label="線上", text="線上"))
            ]
            return TextSendMessage(text="請問是實體還是線上？", quick_reply=QuickReply(items=actions))
        else:
            # 其他類型預設實體，直接跳去問時間
            data['method'] = '實體'
            user_states[user_id]['step'] = STATE_WAITING_DATETIME
            return TextSendMessage(
                text="請選擇日期與時間",
                quick_reply=QuickReply(items=[
                    QuickReplyButton(action=DatetimePickerAction(
                        label="選擇時間", data="action=sel_time", mode="datetime"
                    ))
                ])
            )

    # 3. 選擇 實體/線上 階段
    elif current_step == STATE_WAITING_METHOD:
        if text not in ['實體', '線上']:
            return TextSendMessage(text="請選擇實體或線上。")
        
        data['method'] = text
        user_states[user_id]['step'] = STATE_WAITING_DATETIME
        return TextSendMessage(
            text="請選擇日期與時間",
            quick_reply=QuickReply(items=[
                QuickReplyButton(action=DatetimePickerAction(
                    label="選擇時間", data="action=sel_time", mode="datetime"
                ))
            ])
        )

    # 4. 選擇 日期時間 階段 (接收 Postback)
    elif current_step == STATE_WAITING_DATETIME:
        if not postback_params:
            return TextSendMessage(text="請點擊按鈕選擇時間喔！")
        
        # LINE datetime picker 回傳格式: "2024-02-01T14:00"
        dt_str = postback_params['datetime'] 
        dt_obj = datetime.datetime.fromisoformat(dt_str)
        
        data['datetime'] = dt_obj
        
        # 產生預覽格式：2/1 毓紘保單諮詢(21線上)
        # 取得小時
        hour = dt_obj.hour
        month = dt_obj.month
        day = dt_obj.day
        name = data['name']
        ctype = data['type']
        method = data['method']
        
        preview_text = f"{month}/{day} {name}{ctype}({hour}{method})"
        data['preview'] = preview_text
        
        user_states[user_id]['step'] = STATE_WAITING_CONFIRM
        
        actions = [
            QuickReplyButton(action=MessageAction(label="正確", text="確認:正確")),
            QuickReplyButton(action=MessageAction(label="錯誤", text="確認:錯誤"))
        ]
        return TextSendMessage(text=f"新增內容：\n{preview_text}\n\n請問是否正確？", quick_reply=QuickReply(items=actions))

    # 5. 確認階段
    elif current_step == STATE_WAITING_CONFIRM:
        if text == "確認:正確":
            # 寫入邏輯
            # 計算結束時間
            start_dt = data['datetime']
            duration = utils.DURATION_MAP.get(data['type'], 1) # 預設1小時
            end_dt = start_dt + timedelta(hours=duration)
            
            # 標題只包含文字部分：毓紘保單諮詢(21線上)
            # 但Google日曆只要標題即可，時間由 start_dt 控制
            summary = data['preview'].split(' ', 1)[1] # 去掉前面的日期
            
            # 構建寫入物件
            item = {
                'summary': summary,
                'start': start_dt,
                'end': end_dt,
                'operation': 'insert',
                'all_day': False
            }
            
            # 寫入 Session 讓 finish_and_write 處理 (重用舊邏輯)
            if user_id not in user_sessions:
                user_sessions[user_id] = {'to_write': []}
            user_sessions[user_id]['to_write'].append(item)
            
            # 清除狀態
            del user_states[user_id]
            
            # 執行寫入
            result_msg = finish_and_write(user_id)
            # 修改回傳文字符合需求
            return TextSendMessage(text=f"已新增{data['preview']}")
            
        elif text == "確認:錯誤":
            del user_states[user_id]
            return TextSendMessage(text="已結束新增流程。")
            
    return None

# --- 以下是原本的邏輯 (process_next_event, finish_and_write 等) 請保留 ---
# 為了節省篇幅，請確保您保留了 process_next_event 和 finish_and_write 函數
# ... (這裡應該要有 process_next_event 和 finish_and_write) ...

def process_next_event(user_id):
    # (請貼上之前給您的 process_next_event 完整代碼)
    # ...
    pass 

def finish_and_write(user_id):
    # (請貼上之前給您的 finish_and_write 完整代碼)
    # 這裡我寫個簡化版示意，您用舊的即可
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