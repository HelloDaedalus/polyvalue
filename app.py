import os, json, time, hashlib
from flask import Flask, jsonify, request, Response, redirect, session
from flask_cors import CORS
import requests

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "polyvalue-dev-secret-change-in-prod")
CORS(app, supports_credentials=True, origins=[
    "https://polyvaluehtml.onrender.com",
    "http://localhost:5500", "http://127.0.0.1:5500", "null"
])

TRADE_BASE            = "https://polytoria.trade"
DISCORD_CLIENT_ID     = os.environ.get("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET", "")
DISCORD_REDIRECT_URI  = os.environ.get("DISCORD_REDIRECT_URI", "https://polyvalue.onrender.com/auth/discord/callback")

DATA_DIR = "/tmp/pvdata"
os.makedirs(DATA_DIR, exist_ok=True)

def read_json(name, default):
    try:
        with open(f"{DATA_DIR}/{name}.json") as f:
            return json.load(f)
    except:
        return default

def write_json(name, data):
    with open(f"{DATA_DIR}/{name}.json", "w") as f:
        json.dump(data, f)

# ── Proxy ──
@app.route("/trade/<path:path>", methods=["GET","POST"])
def proxy_trade(path):
    item_id = request.args.get("itemid","")
    referer = f"https://polytoria.trade/store/{item_id}" if item_id else "https://polytoria.trade/"
    url = f"{TRADE_BASE}/{path}"
    hdrs = {
        "content-type":"application/json",
        "referer": referer,
        "origin":"https://polytoria.trade",
        "user-agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
    }
    params = {k:v for k,v in request.args.items() if k != "itemid"}
    try:
        if request.method == "POST":
            r = requests.post(url, params=params, headers=hdrs, data=request.get_data(), timeout=15)
        else:
            r = requests.get(url, params=params, headers=hdrs, timeout=15)
        return Response(r.content, status=r.status_code, mimetype="application/json")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Discord OAuth ──
@app.route("/auth/discord")
def discord_login():
    url = (f"https://discord.com/api/oauth2/authorize"
           f"?client_id={DISCORD_CLIENT_ID}"
           f"&redirect_uri={requests.utils.quote(DISCORD_REDIRECT_URI)}"
           f"&response_type=code&scope=identify")
    return redirect(url)

@app.route("/auth/discord/callback")
def discord_callback():
    code = request.args.get("code")
    if not code:
        return redirect("https://polyvaluehtml.onrender.com/?auth=error")
    try:
        tr = requests.post("https://discord.com/api/oauth2/token", data={
            "client_id": DISCORD_CLIENT_ID, "client_secret": DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": DISCORD_REDIRECT_URI,
        }, headers={"Content-Type": "application/x-www-form-urlencoded"})
        token = tr.json()
        ur = requests.get("https://discord.com/api/users/@me",
                          headers={"Authorization": f"Bearer {token['access_token']}"})
        u = ur.json()
        session.permanent = True
        session["discord_id"]       = u["id"]
        session["discord_username"] = u.get("global_name") or u["username"]
        session["discord_avatar"]   = u.get("avatar","")
        return redirect("https://polyvaluehtml.onrender.com/?auth=success")
    except Exception as e:
        return redirect(f"https://polyvaluehtml.onrender.com/?auth=error")

@app.route("/auth/me")
def auth_me():
    if "discord_id" not in session:
        return jsonify({"loggedIn": False})
    av = session.get("discord_avatar","")
    did = session["discord_id"]
    return jsonify({
        "loggedIn": True, "id": did,
        "username": session["discord_username"],
        "avatarUrl": f"https://cdn.discordapp.com/avatars/{did}/{av}.png?size=64" if av else None
    })

@app.route("/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})

# ── Trades ──
def load_trades():
    cutoff = time.time() - 86400
    return [t for t in read_json("trades", []) if t.get("time", 0) > cutoff]

def save_trades(t):
    write_json("trades", t)

@app.route("/trades", methods=["GET"])
def get_trades():
    q = request.args.get("q","").lower().strip()
    trades = load_trades()
    if q:
        def match(ad):
            names = [i.get("name","").lower() for i in ad.get("offer",[])+ad.get("want",[])]
            return any(q in n for n in names) or q in ad.get("username","").lower()
        trades = [t for t in trades if match(t)]
    return jsonify(trades)

@app.route("/trades", methods=["POST"])
def post_trade():
    if "discord_id" not in session:
        return jsonify({"error": "Login with Discord first"}), 401
    data = request.json or {}
    offer = (data.get("offer") or [])[:4]
    want  = (data.get("want")  or [])[:4]
    if not offer or not want:
        return jsonify({"error": "Add items to both sides"}), 400
    trades = load_trades()
    mine = [t for t in trades if t.get("discordId") == session["discord_id"]]
    if len(mine) >= 5:
        return jsonify({"error": "You have 5 active ads already — remove one first"}), 400
    ad = {
        "id": hashlib.md5(f"{session['discord_id']}{time.time()}".encode()).hexdigest()[:12],
        "discordId": session["discord_id"],
        "username":  session["discord_username"],
        "avatar":    session.get("discord_avatar",""),
        "offer": offer, "want": want,
        "time": time.time()
    }
    trades.insert(0, ad)
    save_trades(trades)
    return jsonify(ad)

@app.route("/trades/<aid>", methods=["DELETE"])
def delete_trade(aid):
    if "discord_id" not in session:
        return jsonify({"error": "Not logged in"}), 401
    trades = load_trades()
    ad = next((t for t in trades if t["id"] == aid), None)
    if not ad:
        return jsonify({"error": "Not found"}), 404
    if ad["discordId"] != session["discord_id"]:
        return jsonify({"error": "That's not your ad"}), 403
    save_trades([t for t in trades if t["id"] != aid])
    return jsonify({"ok": True})

# ── Player RAP snapshots ──
@app.route("/player-history/<pid>", methods=["GET"])
def get_ph(pid):
    return jsonify(read_json(f"ph_{pid.replace('/','').replace('..','')}", []))

@app.route("/player-history/<pid>", methods=["POST"])
def save_ph(pid):
    safe = pid.replace("/","").replace("..","")
    data = request.json or {}
    rap = data.get("rap")
    if rap is None:
        return jsonify({"error":"no rap"}), 400
    history = read_json(f"ph_{safe}", [])
    today = time.strftime("%Y-%m-%d")
    if not history or history[-1].get("date") != today:
        history.append({"date": today, "rap": int(rap), "ts": time.time()})
        write_json(f"ph_{safe}", history[-90:])
    return jsonify(history)

@app.route("/")
def health():
    return jsonify({"status":"ok"})

if __name__ == "__main__":
    app.run(debug=True)
