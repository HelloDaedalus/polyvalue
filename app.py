from flask import Flask, jsonify, request, Response
from flask_cors import CORS
from curl_cffi import requests as cf
import time

app = Flask(__name__)
CORS(app)

BASE = "https://api.polytoria.com"

# Realistic browser fingerprint
session = cf.Session(
    impersonate="chrome124",
    timeout=20
)

def warm_session():
    """Warm Cloudflare session by visiting main site."""
    try:
        session.get(
            "https://polytoria.com/",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9"
            }
        )
        time.sleep(1.5)
    except:
        pass

warm_session()

@app.route("/v1/<path:path>")
def proxy(path):

    url = f"{BASE}/v1/{path}"

    if request.query_string:
        url += "?" + request.query_string.decode()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://polytoria.com/",
        "Origin": "https://polytoria.com",
        "Connection": "keep-alive"
    }

    try:
        r = session.get(
            url,
            headers=headers,
            cookies=request.cookies
        )

        # Detect Cloudflare challenge
        if r.status_code in [403, 503] and b"challenge-platform" in r.content:
            warm_session()

            r = session.get(
                url,
                headers=headers,
                cookies=request.cookies
            )

        return Response(
            r.content,
            status=r.status_code,
            mimetype=r.headers.get("content-type", "application/json")
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
