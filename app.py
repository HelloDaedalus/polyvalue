from flask import Flask, jsonify, request, Response
from flask_cors import CORS
from playwright.sync_api import sync_playwright
import threading

app = Flask(__name__)
CORS(app)

BASE = "https://api.polytoria.com"

_playwright = None
_browser = None
_lock = threading.Lock()

def get_browser():
    global _playwright, _browser
    if _browser is None or not _browser.is_connected():
        _playwright = sync_playwright().start()
        _browser = _playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
    return _browser

@app.route("/v1/<path:path>")
def proxy(path):
    url = f"{BASE}/v1/{path}"
    if request.query_string:
        url += "?" + request.query_string.decode()

    with _lock:
        try:
            browser = get_browser()
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            result = {"status": None, "body": None}

            def handle_response(response):
                if BASE in response.url:
                    result["status"] = response.status
                    try:
                        result["body"] = response.text()
                    except:
                        pass

            page.on("response", handle_response)
            page.goto(url, wait_until="networkidle", timeout=20000)

            body = result["body"] or page.inner_text("body")
            status = result["status"] or 200
            context.close()

            return Response(body, status=status, mimetype="application/json")

        except Exception as e:
            return jsonify({"error": str(e)}), 500

@app.route("/")
def health():
    return jsonify({"status": "ok", "message": "PolyValue proxy running"})

if __name__ == "__main__":
    app.run()
