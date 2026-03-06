from flask import Flask, jsonify, request, Response
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)

TRADE_BASE = "https://polytoria.trade"

@app.route("/trade/<path:path>", methods=["GET","POST"])
def proxy_trade(path):
    url = f"{TRADE_BASE}/{path}"
    headers = {
        "content-type": "application/json",
        "referer": "https://polytoria.trade/",
        "origin": "https://polytoria.trade",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        if request.method == "POST":
            r = requests.post(url, params=request.args, headers=headers, data=request.get_data(), timeout=15)
        else:
            r = requests.get(url, params=request.args, headers=headers, timeout=15)
        return Response(r.content, status=r.status_code, mimetype="application/json")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run()
