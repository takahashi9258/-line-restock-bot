import monitor
import os

from flask import Flask, jsonify


app = Flask(__name__)


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
