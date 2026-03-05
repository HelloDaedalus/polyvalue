from flask import Flask, jsonify, request, Response
from flask_cors import CORS
from curl_cffi import requests as cf_requests

app = Flask(__name__)
CORS(app)

BASE = "https://api.polytoria.com"

@app.route("/v1/<path:path>")
def proxy(path):
    url = f"{BASE}/v1/{path}"
    try:
        r = cf_requests.get(
            url,
            params=request.args,
            impersonate="chrome",
            timeout=15
        )
        return Response(r.content, status=r.status_code, mimetype="application/json")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/")
def health():
    return jsonify({"status": "ok", "message": "PolyValue proxy running"})

if __name__ == "__main__":
    app.run()
