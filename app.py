# app.py
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import re

# 匯入我們寫好的模組
import config
import services
import utils
import logic

app = Flask(__name__)

# 從 config 讀取設定
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

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text
    user_id = event.source.user_id
    
    # 1. 處理決策回覆 (呼叫 logic)
    if msg.startswith("決策:"):
        decision = msg.split(":")[1]
        reply_message = logic.handle_decision(user_id, decision)
        line_bot_api.reply_message(event.reply_token, reply_message)
        return

    # 2. 月份查詢 (呼叫 services)
    month_match = re.match(r'^(\d+)月活動$', msg)
    if month_match:
        reply_text = services.query_month_events(month_match.group(1))
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        return

    # 3. 處理新行程列表 (呼叫 utils 解析 -> 丟給 logic 處理)
    if '月活動' in msg or re.search(r'\d+/\d+', msg):
        new_events = utils.parse_schedule_text(msg)
        if not new_events:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 格式無法解析"))
            return
            
        # 初始化 Session
        logic.user_sessions[user_id] = {
            'queue': new_events,
            'to_write': [],
        }
        
        reply_message = logic.process_next_event(user_id)
        line_bot_api.reply_message(event.reply_token, reply_message)
        return

    # 4. 查行程引導
    if msg == '查行程':
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入「2月活動」查詢，或直接貼上列表新增。"))

if __name__ == "__main__":
    app.run(port=5000)