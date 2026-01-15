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
    
    # 1. 優先檢查是否在互動流程中
    state_reply = logic.handle_user_input(user_id, msg)
    if state_reply:
        line_bot_api.reply_message(event.reply_token, state_reply)
        return

    # 2. 查詢「諮詢簽約」
    consult_match = re.match(r'^(\d+)月諮詢簽約$', msg)
    if consult_match:
        reply_text, has_data = services.query_consultation_events(consult_match.group(1))
        actions = [QuickReplyButton(action=MessageAction(label="新增資料", text="指令:新增諮詢"))]
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text=reply_text, quick_reply=QuickReply(items=actions))
        )
        return
    
    # 3. 查詢「學員上課」
    class_match = re.match(r'^(\d+)月學員上課$', msg)
    if class_match:
        reply_text, has_data = services.query_student_class_events(class_match.group(1))
        actions = [QuickReplyButton(action=MessageAction(label="新增資料", text="指令:新增上課"))]
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text=reply_text, quick_reply=QuickReply(items=actions))
        )
        return

    # 4. 查詢「一般活動」 (這個之前可能被漏掉了，現在加回來)
    month_match = re.match(r'^(\d+)月活動$', msg)
    if month_match:
        reply_text = services.query_month_events(month_match.group(1))
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        return

    # 5. 啟動新增流程指令
    if msg == "指令:新增諮詢":
        reply = logic.start_add_flow(user_id, logic.FLOW_CONSULT)
        line_bot_api.reply_message(event.reply_token, reply)
        return
    
    if msg == "指令:新增上課":
        reply = logic.start_add_flow(user_id, logic.FLOW_CLASS)
        line_bot_api.reply_message(event.reply_token, reply)
        return

    # 6. 衝突決策
    if msg.startswith("決策:"):
        decision = msg.split(":")[1]
        reply_message = logic.handle_decision(user_id, decision)
        line_bot_api.reply_message(event.reply_token, reply_message)
        return

    # 7. 批次文字貼上解析 (最後的防線)
    # 只要包含這些關鍵字，或者有 日期/日期 格式，就嘗試解析
    if any(k in msg for k in ['諮詢', '簽約', '上課', '課', '活動', '聚會']) or re.search(r'\d+/\d+', msg):
        new_events = utils.parse_schedule_text(msg)
        if new_events:
            logic.user_sessions[user_id] = {
                'queue': new_events,
                'to_write': [],
            }
            reply_message = logic.process_next_event(user_id)
            line_bot_api.reply_message(event.reply_token, reply_message)
            return
    
    # 8. 查行程引導
    if msg == '查行程':
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入「2月活動」、「2月諮詢簽約」或「2月學員上課」。"))

if __name__ == "__main__":
    app.run(port=5000)