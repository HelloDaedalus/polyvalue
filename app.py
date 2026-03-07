import os, json, time, hashlib
from flask import Flask, jsonify, request, Response, redirect, session
from flask_cors import CORS
import requests

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "polyvalue-dev-secret-change-in-prod")
app.config.update(
    SESSION_COOKIE_SAMESITE="None",
    SESSION_COOKIE_SECURE=True,
    PERMANENT_SESSION_LIFETIME=604800  # 7 days
)
CORS(app, supports_credentials=True, origins=[
    "https://polyvaluehtml.onrender.com",
    "https://polyvalue.xyz",
    "https://www.polyvalue.xyz",
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
        "polyUsername": (data.get("polyUsername") or "").strip()[:32] or None,
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

# ── DM System ──
DM_CUTOFF = 86400  # 24 hours

def dm_key(a, b):
    """Consistent key for a conversation between two users"""
    return "dm_" + "_".join(sorted([str(a), str(b)]))

def load_thread(a, b):
    cutoff = time.time() - DM_CUTOFF
    msgs = read_json(dm_key(a, b), [])
    return [m for m in msgs if m.get("ts", 0) > cutoff]

def save_thread(a, b, msgs):
    write_json(dm_key(a, b), msgs)

@app.route("/dm/send", methods=["POST"])
def dm_send():
    if "discord_id" not in session:
        return jsonify({"error": "Not logged in"}), 401
    data = request.json or {}
    to_id = str(data.get("toId", ""))
    to_name = data.get("toUsername", "")
    to_av = data.get("toAvatar", "")
    text = (data.get("text") or "").strip()[:500]
    if not to_id or not text:
        return jsonify({"error": "Missing fields"}), 400
    from_id = session["discord_id"]
    if from_id == to_id:
        return jsonify({"error": "Can't DM yourself"}), 400

    msgs = load_thread(from_id, to_id)
    # Rate limit: max 1 msg per 2 seconds
    my_recent = [m for m in msgs if m.get("fromId") == from_id and time.time() - m.get("ts",0) < 2]
    if my_recent:
        return jsonify({"error": "Slow down"}), 429

    msg = {
        "id": hashlib.md5(f"{from_id}{to_id}{time.time()}".encode()).hexdigest()[:10],
        "fromId": from_id,
        "fromUsername": session["discord_username"],
        "fromAvatar": session.get("discord_avatar", ""),
        "toId": to_id,
        "toUsername": to_name,
        "text": text,
        "ts": time.time(),
        "read": False
    }
    msgs.append(msg)
    save_thread(from_id, to_id, msgs[-200:])

    # Also save to recipient's perspective
    recv_msgs = load_thread(to_id, from_id)
    recv_msgs.append(msg)
    save_thread(to_id, from_id, recv_msgs[-200:])

    return jsonify(msg)

@app.route("/dm/thread/<peer_id>")
def dm_thread(peer_id):
    if "discord_id" not in session:
        return jsonify({"error": "Not logged in"}), 401
    my_id = session["discord_id"]
    msgs = load_thread(my_id, peer_id)
    # Mark messages from peer as read
    for m in msgs:
        if m.get("fromId") == peer_id:
            m["read"] = True
    save_thread(my_id, peer_id, msgs)
    return jsonify(msgs)

@app.route("/dm/inbox")
def dm_inbox():
    if "discord_id" not in session:
        return jsonify({"error": "Not logged in"}), 401
    my_id = session["discord_id"]
    # Scan all dm files for this user
    threads = []
    try:
        import os, json as _json
        data_dir = os.path.join(os.path.dirname(__file__), "data")
        if os.path.exists(data_dir):
            for fname in os.listdir(data_dir):
                if fname.startswith(f"dm_") and fname.endswith(".json") and my_id in fname:
                    raw = read_json(fname[:-5], [])
                    cutoff = time.time() - DM_CUTOFF
                    raw = [m for m in raw if m.get("ts",0) > cutoff]
                    if not raw: continue
                    peer_id = None
                    for m in raw:
                        fid = m.get("fromId",""); tid = m.get("toId","")
                        if fid == my_id: peer_id = tid
                        elif tid == my_id: peer_id = fid
                        if peer_id: break
                    if not peer_id or peer_id == my_id: continue
                    peer_name = next((m.get("toUsername") if m.get("fromId")==my_id else m.get("fromUsername") for m in raw if (m.get("fromId")==my_id or m.get("toId")==my_id)), "")
                    peer_av = next((m.get("toAvatar","") if m.get("fromId")==my_id else m.get("fromAvatar","") for m in raw), "")
                    unread = sum(1 for m in raw if m.get("fromId")==peer_id and not m.get("read"))
                    last = raw[-1].get("text","") if raw else ""
                    threads.append({"peerId":peer_id,"peerName":peer_name,"peerAvatar":peer_av,"lastMsg":last,"unread":unread,"ts":raw[-1].get("ts",0) if raw else 0})
        threads.sort(key=lambda x: x["ts"], reverse=True)
    except Exception as e:
        pass
    return jsonify(threads)

@app.route("/dm/unread")
def dm_unread():
    if "discord_id" not in session:
        return jsonify({"total": 0, "latest": []})
    my_id = session["discord_id"]
    total = 0
    latest = []
    try:
        import os
        data_dir = os.path.join(os.path.dirname(__file__), "data")
        if os.path.exists(data_dir):
            for fname in os.listdir(data_dir):
                if fname.startswith("dm_") and fname.endswith(".json") and my_id in fname:
                    raw = read_json(fname[:-5], [])
                    cutoff = time.time() - DM_CUTOFF
                    raw = [m for m in raw if m.get("ts",0) > cutoff]
                    new_msgs = [m for m in raw if m.get("fromId") != my_id and not m.get("read")]
                    total += len(new_msgs)
                    for m in new_msgs:
                        latest.append(m)
    except: pass
    latest.sort(key=lambda x: x.get("ts",0), reverse=True)
    return jsonify({"total": total, "latest": latest[:5]})

@app.route("/")
def health():
    return jsonify({"status":"ok"})

if __name__ == "__main__":
    app.run(debug=True)
