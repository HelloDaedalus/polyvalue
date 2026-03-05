from flask import Flask, jsonify, request, Response
from flask_cors import CORS
from curl_cffi import requests as cf
import time

app = Flask(__name__)
CORS(app)

BASE = "https://api.polytoria.com"

# Reuse a session so cookies/TLS state persist between requests
session = cf.Session(impersonate="chrome124")

def warm_session():
    """Visit the main site first so Cloudflare sets a clearance cookie."""
    try:
        session.get("https://polytoria.com", timeout=15)
        time.sleep(1)
    except:
        pass

warm_session()

@app.route("/v1/<path:path>")
def proxy(path):
    url = f"{BASE}/v1/{path}"
    if request.query_string:
        url += "?" + request.query_string.decode()

    try:
        r = session.get(
            url,
            headers={
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://polytoria.com/",
                "Origin": "https://polytoria.com",
            },
            timeout=20
        )

        # If we hit a Cloudflare challenge, re-warm and retry once
        if r.status_code == 403 and b"cf-chl" in r.content:
            warm_session()
            r = session.get(url, timeout=20)

        return Response(r.content, status=r.status_code, mimetype="application/json")

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run()
