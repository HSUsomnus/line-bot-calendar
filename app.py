from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, 
    PostbackEvent, QuickReply, QuickReplyButton, MessageAction
)
import re
import config
import services
import utils
import logic

app = Flask(__name__)

line_bot_api = LineBotApi(config.LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(config.LINE_CHANNEL_SECRET)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# 處理 Postback (時間選擇器回傳)
@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    data = event.postback.data
    params = event.postback.params # 這裡會有 datetime
    
    # 將資料丟給邏輯層處理
    reply = logic.handle_user_input(user_id, "", postback_data=data, postback_params=params)
    if reply:
        line_bot_api.reply_message(event.reply_token, reply)

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text
    user_id = event.source.user_id
    
    # 1. 優先檢查：使用者是否正在「新增流程」的對話中？
    state_reply = logic.handle_user_input(user_id, msg)
    if state_reply:
        line_bot_api.reply_message(event.reply_token, state_reply)
        return

    # 2. 觸發「諮詢簽約」查詢
    consult_match = re.match(r'^(\d+)月諮詢簽約$', msg)
    if consult_match:
        reply_text, has_data = services.query_consultation_events(consult_match.group(1))
        
        # 加上「是否新增」的按鈕
        actions = [QuickReplyButton(action=MessageAction(label="新增資料", text="指令:開始新增"))]
        
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text=reply_text, quick_reply=QuickReply(items=actions))
        )
        return

    # 3. 觸發開始新增流程
    if msg == "指令:開始新增":
        reply = logic.start_add_flow(user_id)
        line_bot_api.reply_message(event.reply_token, reply)
        return

    # 4. 決策回覆 (衝突處理)
    if msg.startswith("決策:"):
        decision = msg.split(":")[1]
        reply_message = logic.handle_decision(user_id, decision)
        line_bot_api.reply_message(event.reply_token, reply_message)
        return

    # 5. 一般月份查詢
    month_match = re.match(r'^(\d+)月活動$', msg)
    if month_match:
        # 使用 services 裡的 query_month_events (記得要在 services.py 裡有這功能)
        # 這裡假設您沒把 query_month_events 刪掉
        # 若 services.py 裡只有 query_consultation_events，請把舊的加回去
        pass 

    # 6. 批次文字解析
    if '諮詢' in msg or '簽約' in msg or re.search(r'\d+/\d+', msg):
        new_events = utils.parse_schedule_text(msg)
        if not new_events:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 格式無法解析"))
            return
            
        logic.user_sessions[user_id] = {
            'queue': new_events,
            'to_write': [],
        }
        
        reply_message = logic.process_next_event(user_id)
        line_bot_api.reply_message(event.reply_token, reply_message)
        return

if __name__ == "__main__":
    app.run(port=5000)