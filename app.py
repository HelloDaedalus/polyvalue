import os, json, time, hashlib
from flask import Flask, jsonify, request, Response, redirect, session
from flask_cors import CORS
import requests

app = Flask(__name__)
app.secret_key=os.environ.get("SECRET_KEY","polyvalue-dev-secret-change-in-prod")

app.config.update(
SESSION_COOKIE_SAMESITE="None",
SESSION_COOKIE_SECURE=True,
SESSION_COOKIE_HTTPONLY=True,
SESSION_COOKIE_NAME="pv_session",
PERMANENT_SESSION_LIFETIME=604800
)

CORS(app,supports_credentials=True,origins=[
"https://polyvaluehtml.onrender.com",
"https://polyvalue.xyz",
"https://www.polyvalue.xyz",
"http://localhost:5500",
"http://127.0.0.1:5500",
"null"
])

TRADE_BASE="https://polytoria.trade"
DISCORD_CLIENT_ID=os.environ.get("DISCORD_CLIENT_ID","")
DISCORD_CLIENT_SECRET=os.environ.get("DISCORD_CLIENT_SECRET","")
DISCORD_REDIRECT_URI=os.environ.get("DISCORD_REDIRECT_URI","https://polyvalue.onrender.com/auth/discord/callback")

DATA_DIR="/tmp/pvdata"
os.makedirs(DATA_DIR,exist_ok=True)

_cache={}
_cache_time={}

def read_json(name,default):
    now=time.time()
    if name in _cache and now-_cache_time.get(name,0)<2:
        return _cache[name]
    try:
        with open(f"{DATA_DIR}/{name}.json") as f:
            data=json.load(f)
            _cache[name]=data
            _cache_time[name]=now
            return data
    except:
        return default

def write_json(name,data):
    _cache[name]=data
    _cache_time[name]=time.time()
    with open(f"{DATA_DIR}/{name}.json","w") as f:
        json.dump(data,f)

def add_to_dm_index(a,b):
    ia=read_json(f"dm_index_{a}",[])
    if b not in ia:
        ia.append(b)
        write_json(f"dm_index_{a}",ia)
    ib=read_json(f"dm_index_{b}",[])
    if a not in ib:
        ib.append(a)
        write_json(f"dm_index_{b}",ib)

@app.route("/trade/<path:path>",methods=["GET","POST","OPTIONS"])
def proxy_trade(path):
    if request.method=="OPTIONS":
        return Response(status=200)
    item_id=request.args.get("itemid","")
    referer=f"https://polytoria.trade/store/{item_id}" if item_id else "https://polytoria.trade/"
    url=f"{TRADE_BASE}/{path}"
    hdrs={"content-type":"application/json","referer":referer,"origin":"https://polytoria.trade","user-agent":"Mozilla/5.0"}
    params={k:v for k,v in request.args.items() if k!="itemid"}
    try:
        if request.method=="POST":
            r=requests.post(url,params=params,headers=hdrs,data=request.get_data(),timeout=15)
        else:
            r=requests.get(url,params=params,headers=hdrs,timeout=15)
        return Response(r.content,status=r.status_code,mimetype="application/json")
    except Exception as e:
        return jsonify({"error":str(e)}),500

@app.route("/auth/discord")
def discord_login():
    url=(f"https://discord.com/api/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={requests.utils.quote(DISCORD_REDIRECT_URI)}&response_type=code&scope=identify")
    return redirect(url)

@app.route("/auth/discord/callback")
def discord_callback():
    code=request.args.get("code")
    if not code:
        return redirect("https://polyvalue.xyz/?auth=error")
    try:
        tr=requests.post("https://discord.com/api/oauth2/token",data={"client_id":DISCORD_CLIENT_ID,"client_secret":DISCORD_CLIENT_SECRET,"grant_type":"authorization_code","code":code,"redirect_uri":DISCORD_REDIRECT_URI},headers={"Content-Type":"application/x-www-form-urlencoded"})
        token=tr.json()
        access=token.get("access_token")
        if not access:
            return redirect("https://polyvalue.xyz/?auth=error")
        ur=requests.get("https://discord.com/api/users/@me",headers={"Authorization":f"Bearer {access}"})
        u=ur.json()
        session.permanent=True
        session["discord_id"]=u["id"]
        session["discord_username"]=u.get("global_name") or u["username"]
        session["discord_avatar"]=u.get("avatar","")
        return redirect("https://polyvalue.xyz/?auth=success")
    except:
        return redirect("https://polyvalue.xyz/?auth=error")

@app.route("/auth/me")
def auth_me():
    if "discord_id" not in session:
        return jsonify({"loggedIn":False})
    did=session["discord_id"]
    av=session.get("discord_avatar","")
    return jsonify({"loggedIn":True,"id":did,"username":session["discord_username"],"avatarUrl":f"https://cdn.discordapp.com/avatars/{did}/{av}.png?size=64" if av else None})

@app.route("/auth/logout",methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok":True})

def load_trades():
    cutoff=time.time()-86400
    return [t for t in read_json("trades",[]) if t.get("time",0)>cutoff]

def save_trades(t):
    write_json("trades",t)

@app.route("/trades",methods=["GET"])
def get_trades():
    q=request.args.get("q","").lower().strip()
    trades=load_trades()
    if q:
        def match(ad):
            names=[i.get("name","").lower() for i in ad.get("offer",[])+ad.get("want",[])]
            return any(q in n for n in names) or q in ad.get("username","").lower()
        trades=[t for t in trades if match(t)]
    return jsonify(trades)

@app.route("/trades",methods=["POST"])
def post_trade():
    if "discord_id" not in session:
        return jsonify({"error":"Login with Discord first"}),401
    data=request.json or {}
    offer=(data.get("offer") or [])[:4]
    want=(data.get("want") or [])[:4]
    if not offer or not want:
        return jsonify({"error":"Add items to both sides"}),400
    trades=load_trades()
    mine=[t for t in trades if t.get("discordId")==session["discord_id"]]
    if len(mine)>=5:
        return jsonify({"error":"You have 5 active ads already — remove one first"}),400
    ad={"id":hashlib.md5(f"{session['discord_id']}{time.time()}".encode()).hexdigest()[:12],"discordId":session["discord_id"],"username":session["discord_username"],"avatar":session.get("discord_avatar",""),"polyUsername":(data.get("polyUsername") or "").strip()[:32] or None,"polyUserId":(data.get("polyUserId") or "").strip()[:32] or None,"offer":offer,"want":want,"time":time.time()}
    trades.insert(0,ad)
    save_trades(trades)
    return jsonify(ad)

@app.route("/trades/<aid>",methods=["DELETE"])
def delete_trade(aid):
    if "discord_id" not in session:
        return jsonify({"error":"Not logged in"}),401
    trades=load_trades()
    ad=next((t for t in trades if t["id"]==aid),None)
    if not ad:
        return jsonify({"error":"Not found"}),404
    if ad["discordId"]!=session["discord_id"]:
        return jsonify({"error":"That's not your ad"}),403
    save_trades([t for t in trades if t["id"]!=aid])
    return jsonify({"ok":True})

CHAT_CUTOFF=86400

def load_chat():
    cutoff=time.time()-CHAT_CUTOFF
    return [m for m in read_json("global_chat",[]) if m.get("ts",0)>cutoff]

@app.route("/chat/messages",methods=["GET","OPTIONS"])
def chat_messages():
    if request.method=="OPTIONS":
        return Response(status=200)
    since=float(request.args.get("since",0))
    msgs=load_chat()
    if since:
        msgs=[m for m in msgs if m.get("ts",0)>since]
    return jsonify(msgs)

@app.route("/chat/send",methods=["POST","OPTIONS"])
def chat_send():
    if request.method=="OPTIONS":
        return Response(status=200)
    if "discord_id" not in session:
        return jsonify({"error":"Not logged in"}),401
    data=request.json or {}
    text=(data.get("text") or "").strip()[:300]
    if not text:
        return jsonify({"error":"Empty message"}),400
    msgs=load_chat()
    my_id=session["discord_id"]
    recent=[m for m in msgs if m.get("userId")==my_id and time.time()-m.get("ts",0)<3]
    if recent:
        return jsonify({"error":"Slow down"}),429
    msg={"id":hashlib.md5(f"{my_id}{time.time()}".encode()).hexdigest()[:10],"userId":my_id,"username":session["discord_username"],"avatar":session.get("discord_avatar",""),"text":text,"ts":time.time()}
    msgs.append(msg)
    write_json("global_chat",msgs[-500:])
    return jsonify(msg)

@app.route("/chat/report",methods=["POST","OPTIONS"])
def chat_report():
    if request.method=="OPTIONS":
        return Response(status=200)
    if "discord_id" not in session:
        return jsonify({"error":"Not logged in"}),401
    data=request.json or {}
    msg_id=data.get("msgId","")
    reported_username=data.get("username","")
    reports=read_json("chat_reports",[])
    reports.append({"msgId":msg_id,"reportedUsername":reported_username,"reportedBy":session["discord_id"],"reportedByUsername":session["discord_username"],"ts":time.time()})
    write_json("chat_reports",reports[-500:])
    return jsonify({"ok":True})

DM_CUTOFF=86400

def dm_key(a,b):
    return "dm_"+"_".join(sorted([str(a),str(b)]))

def load_thread(a,b):
    cutoff=time.time()-DM_CUTOFF
    msgs=read_json(dm_key(a,b),[])
    return [m for m in msgs if m.get("ts",0)>cutoff]

def save_thread(a,b,msgs):
    write_json(dm_key(a,b),msgs)

@app.route("/dm/send",methods=["POST","OPTIONS"])
def dm_send():
    if request.method=="OPTIONS":
        return Response(status=200)
    if "discord_id" not in session:
        return jsonify({"error":"Not logged in"}),401
    data=request.json or {}
    to_id=str(data.get("toId",""))
    to_name=data.get("toUsername","")
    to_av=data.get("toAvatar","")
    text=(data.get("text") or "").strip()[:500]
    if not to_id or not text:
        return jsonify({"error":"Missing fields"}),400
    from_id=session["discord_id"]
    if from_id==to_id:
        return jsonify({"error":"Can't DM yourself"}),400
    msgs=load_thread(from_id,to_id)
    recent=[m for m in msgs if m.get("fromId")==from_id and time.time()-m.get("ts",0)<2]
    if recent:
        return jsonify({"error":"Slow down"}),429
    msg={"id":hashlib.md5(f"{from_id}{to_id}{time.time()}".encode()).hexdigest()[:10],"fromId":from_id,"fromUsername":session["discord_username"],"fromAvatar":session.get("discord_avatar",""),"toId":to_id,"toUsername":to_name,"toAvatar":to_av,"text":text,"ts":time.time(),"read":False}
    msgs.append(msg)
    save_thread(from_id,to_id,msgs[-200:])
    add_to_dm_index(from_id,to_id)
    return jsonify(msg)

@app.route("/dm/thread/<peer_id>")
def dm_thread(peer_id):
    if "discord_id" not in session:
        return jsonify({"error":"Not logged in"}),401
    my_id=session["discord_id"]
    msgs=load_thread(my_id,peer_id)
    for m in msgs:
        if m.get("fromId")==peer_id:
            m["read"]=True
    save_thread(my_id,peer_id,msgs)
    return jsonify(msgs)

@app.route("/dm/inbox")
def dm_inbox():
    if "discord_id" not in session:
        return jsonify({"error":"Not logged in"}),401
    my_id=session["discord_id"]
    peers=read_json(f"dm_index_{my_id}",[])
    threads=[]
    for peer_id in peers:
        raw=load_thread(my_id,peer_id)
        if not raw:
            continue
        last=raw[-1]
        unread=sum(1 for m in raw if m.get("fromId")==peer_id and not m.get("read"))
        peer_name=last.get("fromUsername") if last.get("fromId")==peer_id else last.get("toUsername")
        peer_av=last.get("fromAvatar") if last.get("fromId")==peer_id else last.get("toAvatar")
        threads.append({"peerId":peer_id,"peerName":peer_name,"peerAvatar":peer_av,"lastMsg":last.get("text",""),"unread":unread,"ts":last.get("ts",0)})
    threads.sort(key=lambda x:x["ts"],reverse=True)
    return jsonify(threads)

@app.route("/dm/unread")
def dm_unread():
    if "discord_id" not in session:
        return jsonify({"total":0,"latest":[]})
    my_id=session["discord_id"]
    peers=read_json(f"dm_index_{my_id}",[])
    total=0
    latest=[]
    for peer_id in peers:
        raw=load_thread(my_id,peer_id)
        new=[m for m in raw if m.get("fromId")==peer_id and not m.get("read")]
        total+=len(new)
        latest.extend(new)
    latest.sort(key=lambda x:x.get("ts",0),reverse=True)
    return jsonify({"total":total,"latest":latest[:5]})

@app.route("/")
def health():
    return jsonify({"status":"ok"})

if __name__=="__main__":
    port=int(os.environ.get("PORT",10000))
    app.run(host="0.0.0.0",port=port)
