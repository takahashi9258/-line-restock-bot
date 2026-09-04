import monitor
import os


from flask import Flask, jsonify




app = Flask(__name__)

if os.environ.get("TEST_NOTIFY_ON_START", "false").lower() == "true":
    test_stores = (
        ("イオンスタイルオンライン", "https://aeonretail.com/"),
        ("あみあみ", "https://www.amiami.jp/"),
        ("Joshin web", "https://joshinweb.jp/"),
        ("トイザらスオンライン", "https://www.toysrus.co.jp/"),
    )
    for store_name, store_url in test_stores:
        monitor.discord_notify(
            f"✅ テスト通知｜{store_name}",
            "4店舗監視BotからのDiscord疎通テストです。",
            store_url,
            0x57F287,
        )




@app.route("/", methods=["GET"])
def health_check():
    return "AEON Discord monitor is running", 200




@app.route("/status", methods=["GET"])
def status():
    with monitor.state_lock:
        public_state = {
            "started_at": monitor.state["started_at"],
            "last_check_at": monitor.state["last_check_at"],
            "last_success_at": monitor.state["last_success_at"],
            "waiting": monitor.state["waiting"],
            "initialized": monitor.state["initialized"],
            "known_products": len(monitor.state["known_products"]),
            "last_error": monitor.state["last_error"],
        }
    return jsonify(public_state)




if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)

