import os

from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent


app = Flask(__name__)

channel_access_token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
channel_secret = os.environ.get("LINE_CHANNEL_SECRET")

if not channel_access_token or not channel_secret:
    raise RuntimeError(
        "LINE_CHANNEL_ACCESS_TOKEN または LINE_CHANNEL_SECRET が設定されていません"
    )

configuration = Configuration(access_token=channel_access_token)
handler = WebhookHandler(channel_secret)


@app.route("/", methods=["GET"])
def health_check():
    return "LINE bot is running", 200


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")

    if not signature:
        abort(400)

    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK", 200


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    received_text = event.message.text

    reply_text = (
        "BOTは正常に動いています！\n"
        f"受信したメッセージ：{received_text}"
    )

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text)],
            )
        )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)