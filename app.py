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

@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    data = event.postback.data
    params = event.postback.params
    reply = logic.handle_user_input(user_id, "", postback_data=data, postback_params=params)
    if reply:
        line_bot_api.reply_message(event.reply_token, reply)

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text
    user_id = event.source.user_id
    
    # 1. 優先檢查是否在對話流程中
    state_reply = logic.handle_user_input(user_id, msg)
    if state_reply:
        line_bot_api.reply_message(event.reply_token, state_reply)
        return

    # 2. 觸發「諮詢簽約」查詢
    consult_match = re.match(r'^(\d+)月諮詢簽約$', msg)
    if consult_match:
        reply_text, has_data = services.query_consultation_events(consult_match.group(1))
        
        # 👇 修改這裡：加入「取消」按鈕
        actions = [
            QuickReplyButton(action=MessageAction(label="新增資料", text="指令:新增諮詢")),
            QuickReplyButton(action=MessageAction(label="取消", text="指令:取消新增"))
        ]
        
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text=reply_text, quick_reply=QuickReply(items=actions))
        )
        return
    
    # 3. 觸發「學員上課」查詢
    class_match = re.match(r'^(\d+)月學員上課$', msg)
    if class_match:
        reply_text, has_data = services.query_student_class_events(class_match.group(1))
        
        # 👇 修改這裡：加入「取消」按鈕
        actions = [
            QuickReplyButton(action=MessageAction(label="新增資料", text="指令:新增上課")),
            QuickReplyButton(action=MessageAction(label="取消", text="指令:取消新增"))
        ]
        
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text=reply_text, quick_reply=QuickReply(items=actions))
        )
        return

    # 4. 處理「取消新增」指令
    if msg == "指令:取消新增":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="已取消操作。"))
        return

    # 5. 啟動新增流程 (區分指令)
    if msg == "指令:新增諮詢":
        reply = logic.start_add_flow(user_id, logic.FLOW_CONSULT)
        line_bot_api.reply_message(event.reply_token, reply)
        return
    
    if msg == "指令:新增上課":
        reply = logic.start_add_flow(user_id, logic.FLOW_CLASS)
        line_bot_api.reply_message(event.reply_token, reply)
        return

    # 6. 決策回覆 (衝突處理)
    if msg.startswith("決策:"):
        decision = msg.split(":")[1]
        reply_message = logic.handle_decision(user_id, decision)
        line_bot_api.reply_message(event.reply_token, reply_message)
        return

    # 7. 一般月份查詢
    month_match = re.match(r'^(\d+)月活動$', msg)
    if month_match:
        reply_text = services.query_month_events(month_match.group(1))
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        return

    # 8. 批次文字解析 (萬用功能)
    if any(k in msg for k in ['諮詢', '簽約', '上課', '課', '活動']) or re.search(r'\d+/\d+', msg):
        new_events = utils.parse_schedule_text(msg)
        if new_events:
            logic.user_sessions[user_id] = {'queue': new_events, 'to_write': []}
            reply_message = logic.process_next_event(user_id)
            line_bot_api.reply_message(event.reply_token, reply_message)
            return

if __name__ == "__main__":
    app.run(port=5000)