#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# HostBot BD v10.0 - No user inline KB + All buttons fixed

import telebot, sqlite3, os, sys, time, logging, threading, csv, io, requests
from datetime import datetime, timedelta
from telebot import types

# ════════════════════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════════════════════
BOT_TOKEN      = os.environ.get("BOT_TOKEN", "8570269160:AAEl4H7JWF2yTQ2Gh_H9uqrJm-6eNatDTVc")
SUPER_ADMIN_ID = int(os.environ.get("SUPER_ADMIN_ID", "7294781579"))
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "mkmuzahid")
TURSO_URL      = os.environ.get("TURSO_URL", "libsql://mkfullcompletebot-muzahidkagushi-lab.aws-ap-south-1.turso.io")
TURSO_TOKEN    = os.environ.get("TURSO_TOKEN", "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3ODMwNDM4MTAsImlkIjoiMDE5ZjI1YWYtMDgwMS03NzU3LWJjNDctZjE0MThhZTc3YjRkIiwia2lkIjoick9SNGw2SlVNaGhYZlZsWU1XeC1IQWFaREt1OVlrbzFUT0x2MFFrcERDSSIsInJpZCI6ImM5MzliMzhkLWM1ZTMtNDczOS1hZDcxLTZmOTFhZDFhNTNmMCJ9.KSxvg627BnS54nh3syIv9eofZ48XFGIXAmfHYMT52WWORRsjkzHQXBkcmewO6KAWqnV1muct7cDnQJ3_D8KUAQ")
LOG_FILE       = "error.log"

if not BOT_TOKEN or not TURSO_URL or not TURSO_TOKEN:
    print("❌ ERROR: BOT_TOKEN, TURSO_URL, TURSO_TOKEN environment variables প্রয়োজন!")
    sys.exit(1)
BOT_START_TIME = time.time()
REFERRAL_BONUS   = 5
DAILY_CHECKIN    = 2
MIN_WITHDRAW     = 100
MIN_DEPOSIT      = 20
WITHDRAW_CHARGE  = 5
MAX_WITHDRAW_DAY = 3

# ════════════════════════════════════════════════════════════
# LOGGING
# ════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE,encoding="utf-8"), logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

bot        = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
user_state = {}

# ════════════════════════════════════════════════════════════
# DATABASE - TURSO CLOUD (with SQLite3 fallback for compatibility)
# ════════════════════════════════════════════════════════════
class TursoConnection:
    """Wrapper for Turso API that mimics sqlite3 connection"""
    def __init__(self, url, token):
        self.url = url
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    def execute(self, sql, params=None):
        try:
            payload = {"statements": [{"sql": sql, "args": params if params else []}]}
            resp = requests.post(f"{self.url}/v2/turso/execute", json=payload, headers=self.headers, timeout=10)
            resp.raise_for_status()
            result = resp.json().get("results", [{}])[0] if resp.json().get("results") else {}
            return TursoCursor(result)
        except Exception as e:
            logger.error(f"Turso execute error: {e}")
            return TursoCursor({})
    
    def executescript(self, sql):
        try:
            statements = [{"sql": stmt.strip()} for stmt in sql.split(';') if stmt.strip()]
            payload = {"statements": statements}
            resp = requests.post(f"{self.url}/v2/turso/execute", json=payload, headers=self.headers, timeout=30)
            resp.raise_for_status()
            return resp.json().get("success", False)
        except Exception as e:
            logger.error(f"Turso executescript error: {e}")
            return False
    
    def cursor(self):
        return self
    
    def commit(self):
        pass
    
    def close(self):
        pass

class TursoCursor:
    """Cursor wrapper that behaves like sqlite3 cursor"""
    def __init__(self, result):
        self.result = result
        self.rows = []
        self.columns = result.get("columns", [])
        
        if "rows" in result and result["rows"]:
            self.rows = [dict(zip(self.columns, row)) for row in result["rows"]]
    
    def fetchall(self):
        return self.rows
    
    def fetchone(self):
        return self.rows[0] if self.rows else None

def get_conn():
    """Get Turso database connection"""
    return TursoConnection(TURSO_URL, TURSO_TOKEN)

def init_db():
    conn = get_conn()
    sql = """
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, name TEXT DEFAULT '', username TEXT DEFAULT '',
        language TEXT DEFAULT 'bn', balance REAL DEFAULT 0, is_banned INTEGER DEFAULT 0,
        role TEXT DEFAULT 'user', joined_at TEXT DEFAULT '', last_active TEXT DEFAULT '',
        referred_by INTEGER DEFAULT NULL, referral_count INTEGER DEFAULT 0,
        total_earned REAL DEFAULT 0, last_checkin TEXT DEFAULT '',
        is_premium INTEGER DEFAULT 0, withdraw_today INTEGER DEFAULT 0, last_wd_date TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS hosting_plans (
        plan_key TEXT PRIMARY KEY, name TEXT, price REAL, days INTEGER, is_active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, bot_name TEXT DEFAULT 'My Bot',
        plan TEXT DEFAULT '', status TEXT DEFAULT 'active', expiry_date TEXT DEFAULT '',
        auto_renew INTEGER DEFAULT 0, created_at TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS payment_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, method TEXT,
        amount TEXT, txid TEXT DEFAULT '', status TEXT DEFAULT 'pending', created_at TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS withdraw_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL,
        method TEXT, number TEXT, status TEXT DEFAULT 'pending', created_at TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS hosting_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, file_msg_id INTEGER,
        plan TEXT DEFAULT '', status TEXT DEFAULT 'pending_review', created_at TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS custom_bot_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        description TEXT DEFAULT '', status TEXT DEFAULT 'pending', created_at TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS support_tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, message TEXT DEFAULT '',
        photo_id TEXT DEFAULT '', status TEXT DEFAULT 'open', created_at TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER, action TEXT,
        target_id INTEGER DEFAULT NULL, details TEXT DEFAULT '', created_at TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS bot_settings (key TEXT PRIMARY KEY, value TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS transaction_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, tx_type TEXT,
        amount REAL, note TEXT DEFAULT '', created_at TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS coupons (
        id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, amount REAL DEFAULT 0,
        max_uses INTEGER DEFAULT 1, used_count INTEGER DEFAULT 0,
        expiry TEXT DEFAULT '', is_active INTEGER DEFAULT 1, created_at TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS coupon_uses (
        id INTEGER PRIMARY KEY AUTOINCREMENT, coupon_id INTEGER, user_id INTEGER, date TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS subscription_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, plan TEXT, price REAL,
        expiry TEXT, action TEXT DEFAULT 'purchase', created_at TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS scheduled_broadcasts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, message TEXT, send_at TEXT, sent INTEGER DEFAULT 0
    );
    """
    conn.executescript(sql)
    
    defs = {
        "maintenance_mode":"0","welcome_message":"HostBot BD-তে স্বাগতম! 🎉",
        "feature_hosting":"1","feature_custom_bot":"1","feature_referral":"1","feature_withdraw":"1",
        "referral_bonus":str(REFERRAL_BONUS),"daily_checkin_bonus":str(DAILY_CHECKIN),
        "min_withdraw":str(MIN_WITHDRAW),"min_deposit":str(MIN_DEPOSIT),
        "withdraw_charge":str(WITHDRAW_CHARGE),"max_withdraw_day":str(MAX_WITHDRAW_DAY),
        "bkash_number":"01952944577","nagad_number":"01952944577",
        "usdt_wallet":"0xYourWalletHere","notice_text":"",
        "usdt_rate":"120","min_usdt":"0.50",
        "bkash_rule":"📱 *বিকাশে টাকা পাঠানোর নিয়ম:*\n1️⃣ আপনার বিকাশ অ্যাপ খুলুন\n2️⃣ *Send Money* অপশনে যান (Payment নয়)\n3️⃣ উপরের নম্বরটি পেস্ট করে কাঙ্ক্ষিত টাকা পাঠান\n4️⃣ পাঠানো শেষে যে *Transaction ID (TrxID)* পাবেন সেটি কপি করে রাখুন",
        "nagad_rule":"📱 *নগদে টাকা পাঠানোর নিয়ম:*\n1️⃣ আপনার নগদ অ্যাপ খুলুন\n2️⃣ *Send Money* অপশনে যান (Cash Out নয়)\n3️⃣ উপরের নম্বরটি পেস্ট করে কাঙ্ক্ষিত টাকা পাঠান\n4️⃣ পাঠানো শেষে যে *Transaction ID (TrxID)* পাবেন সেটি কপি করে রাখুন",
        "usdt_rule":"💱 *USDT (BEP-20) পাঠানোর নিয়ম:*\n1️⃣ আপনার Binance / Trust Wallet / অন্য যেকোনো ওয়ালেট অ্যাপ খুলুন\n2️⃣ Send / Withdraw অপশনে গিয়ে উপরের এড্রেসটি পেস্ট করুন — নেটওয়ার্ক অবশ্যই *BEP-20* সিলেক্ট করবেন, ভুল নেটওয়ার্কে পাঠালে USDT হারিয়ে যেতে পারে\n3️⃣ কাঙ্ক্ষিত USDT পাঠান\n4️⃣ কনফার্ম হওয়ার পর *Transaction ID / Hash* কপি করে রাখুন",
        "admin_password":ADMIN_PASSWORD,"admin_pass_token":"1",
    }
    for k,v in defs.items():
        conn.execute("INSERT OR IGNORE INTO bot_settings VALUES (?,?)",(k,v))
    for pk,pn,pr,pd in [("basic","Basic Plan",20,1),("pro","Pro Plan",100,30),("ultra","Ultra Plan",1080,365)]:
        conn.execute("INSERT OR IGNORE INTO hosting_plans VALUES (?,?,?,?,1)",(pk,pn,pr,pd))
    conn.commit()

def migrate_db():
    conn = get_conn(); c = conn.cursor()
    for sql in [
        "ALTER TABLE users ADD COLUMN is_premium INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN withdraw_today INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN last_wd_date TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN referred_by INTEGER DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN referral_count INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN total_earned REAL DEFAULT 0",
        "ALTER TABLE users ADD COLUMN last_checkin TEXT DEFAULT ''",
        "ALTER TABLE subscriptions ADD COLUMN plan TEXT DEFAULT ''",
        "ALTER TABLE subscriptions ADD COLUMN auto_renew INTEGER DEFAULT 0",
        "ALTER TABLE subscriptions ADD COLUMN created_at TEXT DEFAULT ''",
        "ALTER TABLE hosting_requests ADD COLUMN plan TEXT DEFAULT ''",
        "ALTER TABLE support_tickets ADD COLUMN photo_id TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN pass_verify TEXT DEFAULT ''",
    ]:
        try: c.execute(sql)
        except: pass
    conn.commit(); conn.close()

# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════
def gs(k,fb=""): # get setting
    conn=get_conn()
    try:
        r=conn.execute("SELECT value FROM bot_settings WHERE key=?",(k,)).fetchone()
        return r[0] if r else fb
    finally: conn.close()

def ss(k,v): # set setting
    conn=get_conn()
    try: conn.execute("INSERT OR REPLACE INTO bot_settings VALUES (?,?)",(k,str(v))); conn.commit()
    finally: conn.close()

def get_all_plans():
    conn=get_conn()
    try:
        rows=conn.execute("SELECT plan_key,name,price,days FROM hosting_plans WHERE is_active=1").fetchall()
        return {r["plan_key"]:{"name":r["name"],"price":float(r["price"]),"days":int(r["days"])} for r in rows}
    finally: conn.close()

def get_plan(key):
    conn=get_conn()
    try:
        r=conn.execute("SELECT name,price,days FROM hosting_plans WHERE plan_key=? AND is_active=1",(key,)).fetchone()
        return {"name":r["name"],"price":float(r["price"]),"days":int(r["days"])} if r else None
    finally: conn.close()

def reg(user):
    now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"); conn=get_conn()
    try:
        conn.execute("INSERT OR IGNORE INTO users (user_id,name,username,joined_at,last_active) VALUES (?,?,?,?,?)",
                     (user.id,user.first_name or "",user.username or "",now,now))
        conn.execute("UPDATE users SET last_active=?,name=?,username=? WHERE user_id=?",
                     (now,user.first_name or "",user.username or "",user.id))
        conn.commit()
    finally: conn.close()

def get_user(uid):
    conn=get_conn()
    try: return conn.execute("SELECT * FROM users WHERE user_id=?",(uid,)).fetchone()
    finally: conn.close()

def get_balance(uid):
    conn=get_conn()
    try:
        r=conn.execute("SELECT balance FROM users WHERE user_id=?",(uid,)).fetchone()
        return float(r["balance"]) if r else 0.0
    finally: conn.close()

def get_lang(uid):
    conn=get_conn()
    try:
        r=conn.execute("SELECT language FROM users WHERE user_id=?",(uid,)).fetchone()
        return r["language"] if r else "bn"
    finally: conn.close()

def add_bal(uid,amt,note=""):
    now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"); conn=get_conn()
    try:
        conn.execute("UPDATE users SET balance=balance+? WHERE user_id=?",(amt,uid))
        conn.execute("INSERT INTO transaction_logs (user_id,tx_type,amount,note,created_at) VALUES (?,?,?,?,?)",
                     (uid,"credit",amt,note,now))
        conn.commit()
    finally: conn.close()

def deduct_bal(uid,amt,note=""):
    now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"); conn=get_conn()
    try:
        r=conn.execute("SELECT balance FROM users WHERE user_id=?",(uid,)).fetchone()
        if not r or float(r["balance"])<amt: return False
        conn.execute("UPDATE users SET balance=balance-? WHERE user_id=?",(amt,uid))
        conn.execute("INSERT INTO transaction_logs (user_id,tx_type,amount,note,created_at) VALUES (?,?,?,?,?)",
                     (uid,"debit",amt,note,now))
        conn.commit(); return True
    finally: conn.close()

def audit(aid,action,tid=None,details=""):
    conn=get_conn()
    try:
        conn.execute("INSERT INTO audit_logs (admin_id,action,target_id,details,created_at) VALUES (?,?,?,?,?)",
                     (aid,action,tid,details,datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    finally: conn.close()

def uptime():
    s=int(time.time()-BOT_START_TIME); h,r=divmod(s,3600); m,s=divmod(r,60); d,h=divmod(h,24)
    return f"{d}d {h}h {m}m"

def sdel(cid,mid):
    try: bot.delete_message(cid,mid)
    except: pass

def ssend(uid,txt,**kw):
    try: return bot.send_message(uid,txt,**kw)
    except: return None

def sans(call,txt="",alert=False):
    try: bot.answer_callback_query(call.id,text=txt,show_alert=alert)
    except: pass

def md_escape(text):
    """Escape Telegram legacy-Markdown special chars in user-supplied text
    (TxID, descriptions, ticket messages, names) so a stray _ * ` [ never
    breaks message parsing and silently kills a notification."""
    s=str(text)
    for ch in ("\\","_","*","`","["):
        s=s.replace(ch,"\\"+ch)
    return s

def get_staff_ids(perm=None):
    """Return the set of user_ids who should be notified for a given
    permission area (always includes SUPER_ADMIN_ID)."""
    ids={int(SUPER_ADMIN_ID)}
    conn=get_conn()
    try:
        rows=conn.execute("SELECT user_id,role FROM users WHERE role IN ('admin','moderator')").fetchall()
    finally: conn.close()
    for r in rows:
        role=r["role"]
        if role=="admin": ids.add(int(r["user_id"]))
        elif role=="moderator" and perm in ("support","hosting","custom"): ids.add(int(r["user_id"]))
    return ids

def notify_staff(perm,text,markup_builder=None,**kw):
    """Send an admin notification to every staff member allowed to act on
    `perm`, instead of only the hard-coded SUPER_ADMIN_ID. Each send is
    isolated in its own try/except and logged on failure so one bad send
    (blocked bot, markdown parse error, etc) never silently drops the rest."""
    sent=0
    for sid in get_staff_ids(perm):
        try:
            mk=markup_builder() if markup_builder else None
            bot.send_message(sid,text,reply_markup=mk,**kw)
            sent+=1
        except Exception as e:
            logger.error(f"notify_staff→{sid} failed: {e}")
    if not sent:
        logger.error(f"notify_staff: NO staff received notification for perm={perm}! text={text[:80]}")
    return sent

def is_super(uid): return int(uid)==int(SUPER_ADMIN_ID)
def get_role(uid):
    r=get_user(uid); return r["role"] if r else "user"
def get_admin_pass(): return gs("admin_password",ADMIN_PASSWORD)
def pass_token(): return gs("admin_pass_token","1")
def mark_pass_verified(uid):
    conn=get_conn()
    try: conn.execute("UPDATE users SET pass_verify=? WHERE user_id=?",(pass_token(),uid)); conn.commit()
    finally: conn.close()
def is_pass_verified(uid):
    r=get_user(uid)
    return bool(r) and (r["pass_verify"] or "")==pass_token()
def is_admin(uid):
    if is_super(uid): return True
    if get_role(uid) not in ("admin","moderator"): return False
    return is_pass_verified(uid)
def has_perm(uid,perm):
    if is_super(uid): return True
    perms={"admin":["payments","withdrawals","hosting","custom","support","broadcast","users","analytics"],
           "moderator":["support","hosting","custom"]}
    return perm in perms.get(get_role(uid),[])
def is_banned(uid):
    r=get_user(uid); return bool(r and r["is_banned"])
def is_maint(): return gs("maintenance_mode")=="1"
def is_prem(uid):
    r=get_user(uid); return bool(r and r["is_premium"])

# ════════════════════════════════════════════════════════════
# KEYBOARDS — USER (Reply only, no inline)
# ════════════════════════════════════════════════════════════
def main_kb(lang="bn"):
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    if lang=="en":
        kb.row("🤖 Bot Services","💰 Payments")
        kb.row("👥 Referral & Earn","💬 Support")
    else:
        kb.row("🤖 বট সেবা","💰 পেমেন্ট")
        kb.row("👥 রেফারেল ও আয়","💬 সাপোর্ট")
    return kb

def back_cancel_kb(lang="bn", back_label=None):
    """Every sub-section gets Back + Cancel"""
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    back = back_label or ("↩️ মূল মেনু" if lang=="bn" else "↩️ Main Menu")
    cancel = "❌ বাতিল" if lang=="bn" else "❌ Cancel"
    kb.row(back, cancel)
    return kb

def bot_services_kb(lang="bn"):
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    if lang=="en":
        kb.row("🤖 Host New Bot","🛠️ Build a Bot")
        kb.row("📦 My Active Bots","📋 Price List")
    else:
        kb.row("🤖 নতুন বট হোস্ট","🛠️ বট বানান")
        kb.row("📦 আমার বটগুলো","📋 মূল্য তালিকা")
    kb.row("↩️ মূল মেনু" if lang=="bn" else "↩️ Main Menu")
    return kb

def payment_kb(lang="bn"):
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    if lang=="en":
        kb.row("💳 Add Balance","💸 Withdraw")
        kb.row("👛 My Wallet","📊 Transaction History")
        kb.row("🎁 Use Coupon","📅 Subscription History")
    else:
        kb.row("💳 ব্যালেন্স যোগ","💸 উইথড্র")
        kb.row("👛 আমার ওয়ালেট","📊 লেনদেন ইতিহাস")
        kb.row("🎁 কুপন ব্যবহার","📅 সাব. ইতিহাস")
    kb.row("↩️ মূল মেনু" if lang=="bn" else "↩️ Main Menu")
    return kb

def referral_kb(lang="bn"):
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    if lang=="en": kb.row("🔗 Referral Panel","📅 Daily Check-in")
    else:          kb.row("🔗 রেফারেল প্যানেল","📅 দৈনিক চেক-ইন")
    kb.row("↩️ মূল মেনু" if lang=="bn" else "↩️ Main Menu")
    return kb

def support_kb(lang="bn"):
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    if lang=="en":
        kb.row("💬 Send Support","👤 My Profile")
        kb.row("🌐 Change Language")
    else:
        kb.row("💬 সাপোর্ট পাঠান","👤 আমার প্রোফাইল")
        kb.row("🌐 ভাষা পরিবর্তন")
    kb.row("↩️ মূল মেনু" if lang=="bn" else "↩️ Main Menu")
    return kb

# Payment method picker — REPLY keyboard (not inline)
def pay_method_kb(lang="bn"):
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📱 Bkash","📱 Nagad")
    kb.row("💱 USDT (BEP-20)")
    kb.row("↩️ মূল মেনু" if lang=="bn" else "↩️ Main Menu", "❌ বাতিল" if lang=="bn" else "❌ Cancel")
    return kb

def withdraw_method_kb(lang="bn"):
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📱 Bkash WD","📱 Nagad WD")
    kb.row("↩️ মূল মেনু" if lang=="bn" else "↩️ Main Menu", "❌ বাতিল" if lang=="bn" else "❌ Cancel")
    return kb

def price_cat_kb(lang="bn"):
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    if lang=="bn": kb.row("💻 হোস্টিং প্যাকেজ","🤖 কাস্টম বট মূল্য")
    else:          kb.row("💻 Hosting Packages","🤖 Custom Bot Pricing")
    kb.row("↩️ মূল মেনু" if lang=="bn" else "↩️ Main Menu")
    return kb

def hosting_plan_kb(lang="bn"):
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    for key,p in get_all_plans().items():
        kb.add(f"📦 {p['name']} — {int(p['price'])} BDT")
    kb.row("↩️ মূল মেনু" if lang=="bn" else "↩️ Main Menu", "❌ বাতিল" if lang=="bn" else "❌ Cancel")
    return kb

def lang_kb():
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🇧🇩 বাংলা","🇬🇧 English")
    kb.row("↩️ মূল মেনু")
    return kb

def submit_txid_kb(lang="bn"):
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🔑 ট্রানজেকশন আইডি দিন" if lang=="bn" else "🔑 Submit Transaction ID")
    kb.row("❌ বাতিল" if lang=="bn" else "❌ Cancel")
    return kb

def renew_kb(lang="bn"):
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🔄 নবায়ন করুন" if lang=="bn" else "🔄 Renew",
           "🚀 অটো-নবায়ন" if lang=="bn" else "🚀 Auto-Renew")
    kb.row("↩️ মূল মেনু" if lang=="bn" else "↩️ Main Menu")
    return kb

# ════════════════════════════════════════════════════════════
# KEYBOARDS — ADMIN (Reply for navigation, Inline only for actions)
# ════════════════════════════════════════════════════════════
def admin_main_kb():
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📊 ড্যাশবোর্ড","👥 ইউজার ম্যানেজ")
    kb.row("💳 পেমেন্ট ম্যানেজ","🤖 বট ম্যানেজ")
    kb.row("⚙️ সেটিংস")
    kb.row("↩️ ইউজার প্যানেল")
    return kb

def admin_sub_kb(*rows, back="↩️ অ্যাডমিন মেনু"):
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    for r in rows: kb.row(*r)
    kb.row(back, "❌ বাতিল")
    return kb

def admin_dashboard_kb():
    return admin_sub_kb(["📊 স্ট্যাটস","📈 অ্যানালিটিক্স"],["📋 অডিট লগ","💾 ব্যাকআপ"],["📤 ইউজার এক্সপোর্ট"])

def admin_user_kb():
    return admin_sub_kb(
        ["👥 ইউজার লিস্ট","🔍 ইউজার খুঁজুন"],
        ["⭐ প্রিমিয়াম দিন","🚫 ব্যান/আনব্যান"],
        ["💰 ব্যালেন্স দিন","🏆 রেফারেল লিডার"],
        ["👑 স্টাফ ম্যানেজ"]
    )

def admin_payment_kb():
    return admin_sub_kb(["💳 পেমেন্ট রিকু.","💸 উইথড্র রিকু."],["🎁 কুপন ম্যানেজ","📱 পেমেন্ট নম্বর"])

def admin_bot_kb():
    return admin_sub_kb(
        ["📁 হোস্টিং রিকু.","🤖 কাস্টম অর্ডার"],
        ["🎫 সাপোর্ট টিকেট","📢 ব্রডকাস্ট"],
        ["🎯 টার্গেটেড BC"]
    )

def admin_settings_kb():
    return admin_sub_kb(
        ["🔧 ফিচার টগল","📋 প্ল্যান ম্যানেজ"],
        ["✏️ স্বাগত মেসেজ","📢 নোটিশ সেট"],
        ["💬 ডিরেক্ট মেসেজ","💸 লিমিট সেটিংস"],
        ["🔐 পাসওয়ার্ড চেঞ্জ"]
    )

def moderator_kb():
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📁 হোস্টিং রিকু.","🤖 কাস্টম অর্ডার")
    kb.row("🎫 সাপোর্ট টিকেট")
    kb.row("↩️ ইউজার প্যানেল")
    return kb

def get_admin_kb(uid):
    if is_super(uid): return admin_main_kb()
    role=get_role(uid)
    if role=="admin": return admin_main_kb()
    if role=="moderator": return moderator_kb()
    return main_kb(get_lang(uid))

def cancel_only_kb(lang="bn"):
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("❌ বাতিল" if lang=="bn" else "❌ Cancel")
    return kb

# ════════════════════════════════════════════════════════════
# INLINE — ONLY for admin action-confirmation (auto-delete after use)
# ════════════════════════════════════════════════════════════
def feature_toggle_inline():
    def s(k): return "✅ ON" if gs(k)=="1" else "❌ OFF"
    kb=types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(f"🔧 Maintenance: {s('maintenance_mode')}",callback_data="tog_maint"))
    kb.add(types.InlineKeyboardButton(f"💻 Hosting: {s('feature_hosting')}",callback_data="tog_host"))
    kb.add(types.InlineKeyboardButton(f"🤖 Custom Bot: {s('feature_custom_bot')}",callback_data="tog_cbot"))
    kb.add(types.InlineKeyboardButton(f"👥 Referral: {s('feature_referral')}",callback_data="tog_ref"))
    kb.add(types.InlineKeyboardButton(f"💸 Withdraw: {s('feature_withdraw')}",callback_data="tog_wd"))
    kb.add(types.InlineKeyboardButton("❌ Close",callback_data="close_panel"))
    return kb

def plan_manage_inline():
    kb=types.InlineKeyboardMarkup()
    for key,p in get_all_plans().items():
        kb.add(types.InlineKeyboardButton(f"✏️ {p['name']} ({int(p['price'])}/{p['days']}d)",callback_data=f"editplan_{key}"))
    kb.add(types.InlineKeyboardButton("➕ নতুন প্ল্যান",callback_data="addplan"))
    kb.add(types.InlineKeyboardButton("🗑️ প্ল্যান মুছুন",callback_data="delplan"))
    kb.add(types.InlineKeyboardButton("❌ Close",callback_data="close_panel"))
    return kb

def targeted_bc_inline():
    kb=types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("👥 All",callback_data="tbc_all"),
           types.InlineKeyboardButton("⭐ Premium",callback_data="tbc_premium"))
    kb.row(types.InlineKeyboardButton("💰 Has Balance",callback_data="tbc_balance"),
           types.InlineKeyboardButton("🆕 New(7d)",callback_data="tbc_new"))
    kb.add(types.InlineKeyboardButton("🎯 Specific User",callback_data="tbc_userid"))
    kb.add(types.InlineKeyboardButton("❌ Cancel",callback_data="close_panel"))
    return kb

def limit_settings_inline():
    kb=types.InlineKeyboardMarkup()
    items=[("💳 Min Deposit","editlimit_mindep"),("💸 Min Withdraw","editlimit_minwd"),
           ("💳 Withdraw Charge","editlimit_wdcharge"),("📅 Max WD/Day","editlimit_maxwd"),
           ("🎁 Referral Bonus","editlimit_refbonus"),("📅 Checkin Bonus","editlimit_checkin"),
           ("📱 Bkash Number","editlimit_bkash"),("📱 Nagad Number","editlimit_nagad"),
           ("💱 USDT Wallet","editlimit_usdt")]
    for label,cb in items: kb.add(types.InlineKeyboardButton(label,callback_data=cb))
    kb.add(types.InlineKeyboardButton("❌ Close",callback_data="close_panel"))
    return kb

def bc_type_inline():
    kb=types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("📝 Text",callback_data="bc_text"),
           types.InlineKeyboardButton("📸 Photo",callback_data="bc_photo"))
    kb.row(types.InlineKeyboardButton("🎬 Video",callback_data="bc_video"),
           types.InlineKeyboardButton("📄 Document",callback_data="bc_doc"))
    kb.add(types.InlineKeyboardButton("❌ Cancel",callback_data="close_panel"))
    return kb

# ════════════════════════════════════════════════════════════
# ACTION INLINE — Approve/Reject (auto-delete on tap)
# ════════════════════════════════════════════════════════════
def pay_action_inline(uid,pid,amount):
    kb=types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("✅ Approve",callback_data=f"apay_{uid}_{pid}_{amount}"),
           types.InlineKeyboardButton("❌ Reject",callback_data=f"rpay_{uid}_{pid}"))
    return kb

def wd_action_inline(uid,wid,amount):
    kb=types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("✅ Sent",callback_data=f"wd_done_{uid}_{wid}_{amount}"),
           types.InlineKeyboardButton("❌ Cancel",callback_data=f"wd_cancel_{uid}_{wid}_{amount}"))
    return kb

def file_review_inline(uid,rid):
    kb=types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("✅ Accept",callback_data=f"haccept_{uid}_{rid}"),
           types.InlineKeyboardButton("❌ Cancel",callback_data=f"hcancel_{uid}_{rid}"))
    return kb

def custom_order_inline(uid,oid):
    kb=types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("✅ Accept",callback_data=f"caccept_{uid}_{oid}"),
           types.InlineKeyboardButton("❌ Reject",callback_data=f"creject_{uid}_{oid}"))
    kb.add(types.InlineKeyboardButton("💬 Reply",callback_data=f"creply_{uid}_{oid}"))
    return kb

def plan_confirm_inline(uid,pkey,rid):
    kb=types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("✅ Approve",callback_data=f"pok_{uid}_{pkey}_{rid}"),
           types.InlineKeyboardButton("❌ Reject",callback_data=f"prej_{uid}_{pkey}_{rid}"))
    return kb

def support_reply_inline(uid,tid):
    kb=types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💬 Reply",callback_data=f"rticket_{uid}_{tid}"))
    return kb

def user_reply_inline(admin_id):
    kb=types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💬 Reply",callback_data=f"user_reply_{admin_id}"))
    return kb

def profile_action_inline(uid,banned,premium):
    kb=types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("✅ Unban" if banned else "🚫 Ban", callback_data=f"ai_unban_{uid}" if banned else f"ai_ban_{uid}"),
        types.InlineKeyboardButton("👤 Remove Premium" if premium else "⭐ Give Premium", callback_data=f"pm_toggle_{uid}")
    )
    kb.add(types.InlineKeyboardButton("💰 Add Balance",callback_data=f"addbal_{uid}"))
    kb.add(types.InlineKeyboardButton("💬 Send Message",callback_data=f"dm_{uid}"))
    kb.add(types.InlineKeyboardButton("❌ Close",callback_data="close_panel"))
    return kb

# ════════════════════════════════════════════════════════════
# /start
# ════════════════════════════════════════════════════════════
@bot.message_handler(commands=["start"])
def cmd_start(msg):
    reg(msg.from_user)
    uid=msg.from_user.id; lang=get_lang(uid)
    if is_banned(uid): bot.send_message(uid,"🚫 আপনাকে ব্যান করা হয়েছে।"); return
    if is_maint() and not is_admin(uid): bot.send_message(uid,"🔧 বট রক্ষণাবেক্ষণে আছে।"); return

    args=msg.text.split()
    if len(args)>1 and args[1].startswith("ref_"):
        try:
            ref_uid=int(args[1][4:])
            if ref_uid!=uid:
                conn=get_conn()
                try:
                    row=conn.execute("SELECT referred_by FROM users WHERE user_id=?",(uid,)).fetchone()
                    if row and row["referred_by"] is None:
                        bonus=float(gs("referral_bonus",str(REFERRAL_BONUS)))
                        conn.execute("UPDATE users SET referred_by=? WHERE user_id=?",(ref_uid,uid))
                        conn.execute("UPDATE users SET balance=balance+?,referral_count=referral_count+1,total_earned=total_earned+? WHERE user_id=?",
                                     (bonus,bonus,ref_uid))
                        conn.execute("INSERT INTO transaction_logs (user_id,tx_type,amount,note,created_at) VALUES (?,?,?,?,?)",
                                     (ref_uid,"credit",bonus,"referral bonus",datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                        conn.commit()
                        ssend(ref_uid,f"🎉 রেফারেল বোনাস!\n*{msg.from_user.first_name}* আপনার লিংক দিয়ে যোগ দিয়েছেন।\n"
                              f"+{int(bonus)} BDT যোগ হয়েছে!\n💰 ব্যালেন্স: {round(get_balance(ref_uid),2)} BDT")
                finally: conn.close()
        except: pass

    welcome=gs("welcome_message","HostBot BD-তে স্বাগতম! 🎉")
    notice=gs("notice_text","")
    prefix="⭐ প্রিমিয়াম — " if is_prem(uid) else ""
    suffix="\n\n📋 নিচের মেনু থেকে সেবা বেছে নিন:" if lang=="bn" else "\n\n📋 Select a service:"
    kb=get_admin_kb(uid) if is_admin(uid) else main_kb(lang)
    bot.send_message(uid,prefix+welcome+suffix,reply_markup=kb)
    if notice: bot.send_message(uid,"📢 নোটিশ:\n\n"+notice)

@bot.message_handler(commands=["admin","muzahid"])
def cmd_admin(msg):
    uid=msg.from_user.id; reg(msg.from_user)
    if is_super(uid):
        bot.send_message(uid,"✅ অ্যাডমিন প্যানেলে স্বাগতম!",reply_markup=get_admin_kb(uid)); return
    role=get_role(uid)
    if role not in ("admin","moderator"):
        sa=get_user(SUPER_ADMIN_ID)
        sa_tag=f"@{sa['username']}" if sa and sa["username"] else "সুপার এডমিন"
        bot.send_message(uid,f"🚫 আপনি এডমিন নন।\nএডমিনের জন্য এপ্লাই করতে {sa_tag} এর কাছে আবেদন জানান।")
        return
    user_state[uid]="await_admin_pass"
    bot.send_message(uid,"🔑 এডমিন পাসওয়ার্ড দিন:",reply_markup=cancel_only_kb(get_lang(uid)))

@bot.message_handler(commands=["ping"])
def cmd_ping(msg):
    s=time.time(); m=bot.send_message(msg.from_user.id,"🏓 Pinging...")
    bot.edit_message_text(f"🏓 Pong! {round((time.time()-s)*1000)}ms",msg.from_user.id,m.message_id)

@bot.message_handler(commands=["restart"])
def cmd_restart(msg):
    if not is_super(msg.from_user.id): return
    audit(msg.from_user.id,"BOT_RESTART")
    bot.send_message(msg.from_user.id,"🔄 Restarting..."); time.sleep(1)
    os.execv(sys.executable,[sys.executable]+sys.argv)

@bot.message_handler(commands=["find"])
def cmd_find(msg):
    if not is_super(msg.from_user.id): return
    parts=msg.text.split()
    if len(parts)<2: bot.send_message(msg.from_user.id,"ℹ️ Usage: /find @username or user_id"); return
    q=parts[1].replace("@","")
    conn=get_conn()
    try:
        try: row=conn.execute("SELECT * FROM users WHERE user_id=?",(int(q),)).fetchone()
        except: row=conn.execute("SELECT * FROM users WHERE username LIKE ?",(f"%{q}%",)).fetchone()
    finally: conn.close()
    if row: send_admin_profile(msg.from_user.id,row)
    else: bot.send_message(msg.from_user.id,"❌ User not found.")

@bot.message_handler(commands=["setrole"])
def cmd_setrole(msg):
    if not is_super(msg.from_user.id): return
    parts=msg.text.split()
    if len(parts)!=3: bot.send_message(msg.from_user.id,"ℹ️ Usage: /setrole user_id role"); return
    try:
        target=int(parts[1]); role=parts[2]
        if role not in ("admin","moderator","user"): bot.send_message(msg.from_user.id,"❌ Invalid role."); return
        conn=get_conn()
        try: conn.execute("UPDATE users SET role=? WHERE user_id=?",(role,target)); conn.commit()
        finally: conn.close()
        audit(msg.from_user.id,"SET_ROLE",target,role)
        bot.send_message(msg.from_user.id,f"✅ User {target} role → {role}")
        ssend(target,f"👑 আপনার রোল পরিবর্তন হয়েছে: *{role}*")
    except Exception as e: bot.send_message(msg.from_user.id,f"❌ Error: {e}")

@bot.message_handler(commands=["cleancache"])
def cmd_cleancache(msg):
    if not is_super(msg.from_user.id): return
    user_state.clear(); audit(msg.from_user.id,"CLEAR_CACHE")
    bot.send_message(msg.from_user.id,"✅ Cache cleared.")

@bot.message_handler(commands=["errorlog"])
def cmd_errorlog(msg):
    if not is_super(msg.from_user.id): return
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE,"rb") as f: bot.send_document(msg.from_user.id,f,caption="📋 error.log")
    else: bot.send_message(msg.from_user.id,"⚠️ No log file.")

# ════════════════════════════════════════════════════════════
# MAIN TEXT HANDLER
# ════════════════════════════════════════════════════════════
BACK_MAIN  = {"↩️ মূল মেনু","↩️ Main Menu"}
BACK_ADMIN = {"↩️ অ্যাডমিন মেনু"}
BACK_USERP = {"↩️ ইউজার প্যানেল"}
CANCEL_SET = {"❌ বাতিল","❌ Cancel"}

def clear_state_keys(uid):
    """Remove uid state and any uid-prefixed temp keys"""
    user_state.pop(uid,None)
    for k in list(user_state.keys()):
        if str(k).startswith(f"{uid}_"):
            user_state.pop(k,None)

@bot.message_handler(content_types=["text"])
def handle_text(msg):
    try:
        reg(msg.from_user)
        uid=msg.from_user.id; text=msg.text.strip(); lang=get_lang(uid)
        state=user_state.get(uid,"")
        if text.startswith("/"): return
        if is_banned(uid): bot.send_message(uid,"🚫 আপনাকে ব্যান করা হয়েছে।"); return
        if is_maint() and not is_admin(uid): bot.send_message(uid,"🔧 বট রক্ষণাবেক্ষণে আছে।"); return

        # ── universal cancel ──
        if text in CANCEL_SET:
            clear_state_keys(uid)
            kb=get_admin_kb(uid) if is_admin(uid) else main_kb(lang)
            bot.send_message(uid,"❌ বাতিল করা হয়েছে।",reply_markup=kb); return

        if text in BACK_USERP:
            clear_state_keys(uid)
            bot.send_message(uid,"↩️ ইউজার মেনুতে ফিরে গেছেন।",reply_markup=main_kb(lang)); return
        if text in BACK_ADMIN:
            clear_state_keys(uid)
            bot.send_message(uid,"↩️ অ্যাডমিন মেনু",reply_markup=get_admin_kb(uid)); return
        if text in BACK_MAIN:
            clear_state_keys(uid)
            bot.send_message(uid,"↩️",reply_markup=main_kb(lang)); return

        # ── admin password ──
        if state=="await_admin_pass":
            clear_state_keys(uid)
            if text==get_admin_pass():
                mark_pass_verified(uid)
                audit(uid,"ADMIN_LOGIN")
                bot.send_message(uid,"✅ অ্যাডমিন প্যানেলে স্বাগতম!",reply_markup=get_admin_kb(uid))
            else:
                bot.send_message(uid,"❌ ভুল পাসওয়ার্ড!",reply_markup=main_kb(lang))
            return

        # ════════ STATE MACHINE ════════

        if state.startswith("user_replying_"):
            admin_id=int(state[len("user_replying_"):]); clear_state_keys(uid)
            ssend(admin_id,f"💬 ইউজার *{msg.from_user.first_name}* ({uid}) এর উত্তর:\n\n{text}")
            bot.send_message(uid,"✅ উত্তর পাঠানো হয়েছে।",reply_markup=main_kb(lang)); return

        if state=="await_custom_idea":
            clear_state_keys(uid)
            now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"); conn=get_conn()
            try:
                conn.execute("INSERT INTO custom_bot_orders (user_id,description,status,created_at) VALUES (?,?,?,?)",
                             (uid,text,"pending",now))
                order_id=conn.execute("SELECT last_insert_rowid()").fetchone()[0]; conn.commit()
            finally: conn.close()
            uname=f"@{msg.from_user.username}" if msg.from_user.username else str(uid)
            fname=md_escape(msg.from_user.first_name or str(uid)); safe_desc=md_escape(text)
            notify_staff("custom",f"🤖 নতুন কাস্টম বট অর্ডার!\n👤 {fname} ({uid}) {uname}\n\n📝 {safe_desc}",
                  markup_builder=lambda: custom_order_inline(uid,order_id))
            bot.send_message(uid,"✅ অর্ডার জমা হয়েছে! শীঘ্রই টিম যোগাযোগ করবে।",reply_markup=bot_services_kb(lang)); return

        if state=="await_pay_amount":
            method=user_state.get(f"{uid}_method","bkash")
            if method=="usdt":
                min_usdt=float(gs("min_usdt","0.50")); rate=float(gs("usdt_rate","120"))
                try:
                    usdt_amt=float(text)
                    if usdt_amt<min_usdt:
                        bot.send_message(uid,f"⚠️ সর্বনিম্ন {min_usdt:g} USDT পাঠাতে হবে।\nআপনি লিখেছেন: {usdt_amt:g} USDT",
                                         reply_markup=cancel_only_kb(lang)); return
                except ValueError:
                    bot.send_message(uid,"❌ সঠিক USDT পরিমাণ লিখুন (যেমন: 1.5):",reply_markup=cancel_only_kb(lang)); return
                bdt_equiv=round(usdt_amt*rate,2)
                user_state[uid]="await_txid"; user_state[f"{uid}_amount"]=f"{usdt_amt:g}"; user_state[f"{uid}_bdt_equiv"]=str(bdt_equiv)
                bot.send_message(uid,
                    f"✅ আপনি *{usdt_amt:g} USDT* এড করবেন, যা *{bdt_equiv:g} টাকার* সমান।\n\n"
                    f"🔑 এখন পাঠানো USDT-এর Transaction ID / Hash দিন:",
                    reply_markup=cancel_only_kb(lang)); return
            else:
                min_dep=float(gs("min_deposit",str(MIN_DEPOSIT)))
                try:
                    amount=float(text)
                    if amount<min_dep:
                        bot.send_message(uid,f"⚠️ সর্বনিম্ন ডিপোজিট: {int(min_dep)} BDT\nআপনি লিখেছেন: {int(amount)} BDT",
                                         reply_markup=cancel_only_kb(lang)); return
                except ValueError:
                    bot.send_message(uid,"❌ সঠিক পরিমাণ লিখুন (যেমন: 100):",reply_markup=cancel_only_kb(lang)); return
                user_state[uid]="await_txid"; user_state[f"{uid}_amount"]=text
                mname="Bkash" if method=="bkash" else "Nagad"
                bot.send_message(uid,f"✅ আপনি *{int(amount)} টাকা* {mname}-এ পাঠাচ্ছেন।\n\n🔑 এখন সেই লেনদেনের Transaction ID (TrxID) দিন:",
                                 reply_markup=cancel_only_kb(lang)); return

        if state=="await_txid":
            method=user_state.get(f"{uid}_method","bkash")
            txid=text.strip()
            if method=="usdt":
                usdt_amt=user_state.get(f"{uid}_amount","0")
                bdt_credit=user_state.get(f"{uid}_bdt_equiv","0")
                try: bdt_credit_f=float(bdt_credit)
                except ValueError: bdt_credit_f=0.0
                amount_display=f"{bdt_credit} BDT (≈{usdt_amt} USDT)"
                display_line=f"💵 {usdt_amt} USDT ≈ {bdt_credit} BDT"
                credit_amount=bdt_credit_f
            else:
                amount=user_state.get(f"{uid}_amount","0")
                try: credit_amount=float(amount)
                except ValueError: credit_amount=0.0
                amount_display=f"{amount} BDT"
                display_line=f"💵 {amount} BDT"
            clear_state_keys(uid)
            now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"); conn=get_conn()
            try:
                conn.execute("INSERT INTO payment_requests (user_id,method,amount,txid,status,created_at) VALUES (?,?,?,?,?,?)",
                             (uid,method,amount_display,txid,"pending",now))
                pay_id=conn.execute("SELECT last_insert_rowid()").fetchone()[0]; conn.commit()
            finally: conn.close()
            uname=f"@{msg.from_user.username}" if msg.from_user.username else str(uid)
            fname=md_escape(msg.from_user.first_name or str(uid)); safe_txid=md_escape(txid)
            notify_staff("payments",
                f"💳 নতুন পেমেন্ট রিকুয়েস্ট!\n👤 {fname} ({uid}) {uname}\n"
                f"{display_line} | {method.upper()}\n🔑 TxID: `{safe_txid}`",
                markup_builder=lambda: pay_action_inline(uid,pay_id,credit_amount))
            bot.send_message(uid,"⏳ পেমেন্ট অনুরোধ জমা হয়েছে! অ্যাডমিন শীঘ্রই যাচাই করবেন।",reply_markup=payment_kb(lang)); return

        if state=="await_support":
            clear_state_keys(uid)
            now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"); conn=get_conn()
            try:
                conn.execute("INSERT INTO support_tickets (user_id,message,status,created_at) VALUES (?,?,?,?)",
                             (uid,text,"open",now))
                tid=conn.execute("SELECT last_insert_rowid()").fetchone()[0]; conn.commit()
            finally: conn.close()
            uname=f"@{msg.from_user.username}" if msg.from_user.username else str(uid)
            fname=md_escape(msg.from_user.first_name or str(uid)); safe_msg=md_escape(text)
            notify_staff("support",f"🎫 Support Ticket #{tid}\n👤 {fname} ({uid}) {uname}\n\n{safe_msg}",
                  markup_builder=lambda: support_reply_inline(uid,tid))
            bot.send_message(uid,"✅ সাপোর্ট টিমের কাছে বার্তা পাঠানো হয়েছে!",reply_markup=support_kb(lang)); return

        if state.startswith("await_wd_amount_"):
            method=state[len("await_wd_amount_"):]
            min_w=float(gs("min_withdraw",str(MIN_WITHDRAW))); charge=float(gs("withdraw_charge",str(WITHDRAW_CHARGE)))
            bal=get_balance(uid)
            try: amount=float(text)
            except ValueError:
                bot.send_message(uid,"❌ সঠিক পরিমাণ লিখুন:",reply_markup=cancel_only_kb(lang)); return
            if amount<min_w:
                bot.send_message(uid,f"⚠️ সর্বনিম্ন উইথড্র: {int(min_w)} BDT",reply_markup=cancel_only_kb(lang)); return
            if amount+charge>bal:
                bot.send_message(uid,f"❌ অপর্যাপ্ত ব্যালেন্স!\n📉 প্রয়োজন: {int(amount+charge)} BDT | 💰 আছে: {round(bal,2)} BDT",
                                 reply_markup=cancel_only_kb(lang)); return
            row=get_user(uid); today=datetime.now().strftime("%Y-%m-%d"); max_wd=int(gs("max_withdraw_day",str(MAX_WITHDRAW_DAY)))
            wd_today=row["withdraw_today"] or 0 if row else 0
            last_wd=row["last_wd_date"] or "" if row else ""
            if last_wd.startswith(today) and wd_today>=max_wd:
                bot.send_message(uid,f"⚠️ দৈনিক উইথড্র সীমা পূর্ণ! সর্বোচ্চ: {max_wd} বার/দিন",reply_markup=payment_kb(lang)); return
            mname="Bkash" if method=="bkash" else "Nagad"
            user_state[uid]=f"await_wd_number_{method}"; user_state[f"{uid}_wd_amount"]=str(amount)
            bot.send_message(uid,f"📱 {mname} নম্বর লিখুন যেখানে {int(amount)} BDT পাবেন:",reply_markup=cancel_only_kb(lang)); return

        if state.startswith("await_wd_number_"):
            method=state[len("await_wd_number_"):]; mname="Bkash" if method=="bkash" else "Nagad"
            amount=float(user_state.get(f"{uid}_wd_amount",0)); charge=float(gs("withdraw_charge",str(WITHDRAW_CHARGE)))
            net=amount-charge
            ok=deduct_bal(uid,amount,f"withdraw {method}")
            if not ok:
                clear_state_keys(uid)
                bot.send_message(uid,"❌ অপর্যাপ্ত ব্যালেন্স!",reply_markup=payment_kb(lang)); return
            clear_state_keys(uid)
            now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"); today=datetime.now().strftime("%Y-%m-%d"); conn=get_conn()
            try:
                row2=conn.execute("SELECT last_wd_date,withdraw_today FROM users WHERE user_id=?",(uid,)).fetchone()
                if row2 and row2["last_wd_date"] and str(row2["last_wd_date"]).startswith(today):
                    conn.execute("UPDATE users SET withdraw_today=withdraw_today+1 WHERE user_id=?",(uid,))
                else:
                    conn.execute("UPDATE users SET withdraw_today=1,last_wd_date=? WHERE user_id=?",(today,uid))
                conn.execute("INSERT INTO withdraw_requests (user_id,amount,method,number,status,created_at) VALUES (?,?,?,?,?,?)",
                             (uid,amount,method,text,"pending",now))
                wd_id=conn.execute("SELECT last_insert_rowid()").fetchone()[0]; conn.commit()
            finally: conn.close()
            u2=get_user(uid); uname=f"@{u2['username']}" if u2 and u2["username"] else str(uid)
            fname=md_escape(u2["name"] if u2 else uid); safe_num=md_escape(text)
            notify_staff("withdrawals",f"💸 উইথড্র রিকুয়েস্ট!\n👤 {fname} ({uid}) {uname}\n"
                  f"📱 {mname} | নম্বর: `{safe_num}`\n💵 {int(amount)} BDT | চার্জ: {int(charge)} | পাবেন: {int(net)} BDT\n"
                  f"💰 ব্যালেন্স: {round(get_balance(uid),2)} BDT",
                  markup_builder=lambda: wd_action_inline(uid,wd_id,int(amount)))
            bot.send_message(uid,f"✅ উইথড্র অনুরোধ জমা!\n📱 {mname} | নম্বর: {text}\n💵 {int(amount)} BDT | পাবেন: {int(net)} BDT\n⏳ অ্যাডমিন শীঘ্রই প্রসেস করবেন।",
                             reply_markup=payment_kb(lang)); return

        if state=="await_coupon_code":
            clear_state_keys(uid); _apply_coupon(uid,lang,text); return

        if state=="adm_broadcast":
            clear_state_keys(uid)
            threading.Thread(target=do_broadcast,args=(uid,text,"all",None,None),daemon=True).start()
            bot.send_message(uid,"📢 ব্রডকাস্ট শুরু হয়েছে...",reply_markup=admin_bot_kb()); return
        if state.startswith("tbc_msg_") and not state.startswith("tbc_msg_uid_"):
            target=state[len("tbc_msg_"):]; clear_state_keys(uid)
            threading.Thread(target=do_broadcast,args=(uid,text,target,None,None),daemon=True).start()
            bot.send_message(uid,"📢 ব্রডকাস্ট শুরু হয়েছে...",reply_markup=admin_bot_kb()); return
        if state=="tbc_userid_input":
            user_state[uid]=f"tbc_msg_uid_{text.strip()}"
            bot.send_message(uid,f"✍️ ইউজার {text.strip()} কে পাঠানোর মেসেজ লিখুন:",reply_markup=cancel_only_kb(lang)); return
        if state.startswith("tbc_msg_uid_"):
            target_uid_str=state[len("tbc_msg_uid_"):]; clear_state_keys(uid)
            try:
                tid=int(target_uid_str); ssend(tid,text)
                audit(uid,"TARGETED_MSG",tid,text[:80])
                bot.send_message(uid,f"✅ {tid} কে পাঠানো হয়েছে।",reply_markup=admin_bot_kb())
            except Exception as e:
                bot.send_message(uid,f"❌ Failed: {e}",reply_markup=admin_bot_kb())
            return

        if state.startswith("adm_reply_"):
            target_id=int(state.split("_")[2]); clear_state_keys(uid)
            ssend(target_id,"📩 অ্যাডমিন উত্তর:\n\n"+text)
            bot.send_message(uid,"✅ উত্তর পাঠানো হয়েছে।",reply_markup=admin_bot_kb())
            audit(uid,"SUPPORT_REPLY",target_id,text[:80]); return

        if state.startswith("adm_custom_reply_"):
            parts2=state[len("adm_custom_reply_"):].split("_",1); target_id=int(parts2[0]); clear_state_keys(uid)
            ssend(target_id,"📩 অ্যাডমিন উত্তর:\n\n"+text)
            bot.send_message(uid,"✅ উত্তর পাঠানো হয়েছে।",reply_markup=admin_bot_kb())
            audit(uid,"CUSTOM_ORDER_REPLY",target_id,text[:80]); return

        if state=="adm_ban": clear_state_keys(uid); _do_ban(uid,text,True); return
        if state=="adm_unban": clear_state_keys(uid); _do_ban(uid,text,False); return

        if state=="adm_addbal_id":
            user_state[uid]=f"adm_addbal_amt_{text}"; bot.send_message(uid,"💵 কত BDT দেবেন?",reply_markup=cancel_only_kb(lang)); return
        if state.startswith("adm_addbal_amt_"):
            target_id=int(state[len("adm_addbal_amt_"):]); clear_state_keys(uid)
            try:
                amt=float(text); add_bal(target_id,amt,"admin credit")
                audit(uid,"ADD_BALANCE",target_id,f"+{amt}")
                bot.send_message(uid,f"✅ {target_id} কে +{amt} BDT দেওয়া হয়েছে। ব্যালেন্স: {round(get_balance(target_id),2)} BDT",reply_markup=admin_user_kb())
                ssend(target_id,f"💰 +{amt} BDT আপনার ওয়ালেটে যোগ হয়েছে!\n💰 ব্যালেন্স: {round(get_balance(target_id),2)} BDT")
            except ValueError:
                bot.send_message(uid,"❌ সঠিক পরিমাণ দিন।",reply_markup=admin_user_kb())
            return

        if state=="adm_welcome":
            clear_state_keys(uid); ss("welcome_message",text)
            bot.send_message(uid,"✅ স্বাগত বার্তা আপডেট হয়েছে।",reply_markup=admin_settings_kb()); return
        if state=="adm_notice":
            clear_state_keys(uid); ss("notice_text","" if text.lower()=="clear" else text)
            bot.send_message(uid,"✅ নোটিশ আপডেট হয়েছে।",reply_markup=admin_settings_kb()); return

        if state=="adm_change_pass":
            new_pass=text.strip()
            if len(new_pass)<6:
                bot.send_message(uid,"❌ পাসওয়ার্ড কমপক্ষে ৬ ক্যারেক্টার হতে হবে।",reply_markup=cancel_only_kb(lang)); return
            clear_state_keys(uid)
            if not is_super(uid): return
            ss("admin_password",new_pass)
            ss("admin_pass_token",str(int(time.time())))
            audit(uid,"CHANGE_ADMIN_PASSWORD")
            bot.send_message(uid,
                "✅ নতুন এডমিন পাসওয়ার্ড সেট হয়েছে!\n\n"
                "🔒 নিরাপত্তার জন্য সকল মডারেটর ও এডমিনদের এখন থেকে /admin কমান্ড দিয়ে নতুন পাসওয়ার্ড দিয়ে পুনরায় লগইন করতে হবে।",
                reply_markup=admin_settings_kb()); return

        if state=="adm_setrole_id":
            user_state[uid]=f"adm_setrole_role_{text.strip()}"
            bot.send_message(uid,"👑 রোল লিখুন: admin / moderator / user",reply_markup=cancel_only_kb(lang)); return
        if state.startswith("adm_setrole_role_"):
            target_id=int(state[len("adm_setrole_role_"):]); clear_state_keys(uid)
            role=text.strip().lower()
            if role not in ("admin","moderator","user"):
                bot.send_message(uid,"❌ ভ্যালিড রোল: admin, moderator, user",reply_markup=admin_user_kb()); return
            conn=get_conn()
            try: conn.execute("UPDATE users SET role=? WHERE user_id=?",(role,target_id)); conn.commit()
            finally: conn.close()
            audit(uid,"SET_ROLE",target_id,role)
            bot.send_message(uid,f"✅ {target_id} এর রোল → {role}",reply_markup=admin_user_kb())
            ssend(target_id,f"👑 আপনার রোল পরিবর্তন হয়েছে: *{role}*"); return

        if state=="adm_dm_uid":
            user_state[uid]=f"adm_dm_msg_{text.strip()}"
            bot.send_message(uid,f"✍️ ইউজার {text.strip()} কে পাঠানোর মেসেজ লিখুন:",reply_markup=cancel_only_kb(lang)); return
        if state.startswith("adm_dm_msg_"):
            target_id=int(state[len("adm_dm_msg_"):]); clear_state_keys(uid)
            ssend(target_id,"📩 অ্যাডমিনের বার্তা:\n\n"+text,reply_markup=user_reply_inline(uid))
            audit(uid,"DIRECT_MSG",target_id,text[:80])
            bot.send_message(uid,f"✅ {target_id} কে বার্তা পাঠানো হয়েছে।",reply_markup=admin_settings_kb()); return

        if state=="adm_profile":
            clear_state_keys(uid)
            try:
                row=get_user(int(text)); send_admin_profile(uid,row)
            except ValueError:
                try:
                    conn=get_conn()
                    row=conn.execute("SELECT * FROM users WHERE username LIKE ?",(f"%{text.replace('@','')}%",)).fetchone()
                    conn.close()
                    send_admin_profile(uid,row)
                except Exception:
                    bot.send_message(uid,"❌ সঠিক ইউজার আইডি দিন।",reply_markup=admin_user_kb())
            return

        if state=="adm_addplan_key":
            user_state[uid]=f"adm_addplan_name_{text.strip()}"
            bot.send_message(uid,f"📦 প্ল্যানের নাম লিখুন (key: {text.strip()}):",reply_markup=cancel_only_kb(lang)); return
        if state.startswith("adm_addplan_name_"):
            key=state[len("adm_addplan_name_"):]; user_state[uid]=f"adm_addplan_price_{key}|{text.strip()}"
            bot.send_message(uid,"💵 মূল্য লিখুন (BDT):",reply_markup=cancel_only_kb(lang)); return
        if state.startswith("adm_addplan_price_"):
            rest=state[len("adm_addplan_price_"):]; key,name=rest.split("|",1)
            try:
                price=float(text); user_state[uid]=f"adm_addplan_days_{key}|{name}|{price}"
                bot.send_message(uid,"📅 মেয়াদ লিখুন (দিনে):",reply_markup=cancel_only_kb(lang))
            except ValueError:
                bot.send_message(uid,"❌ সঠিক মূল্য দিন।",reply_markup=admin_settings_kb()); clear_state_keys(uid)
            return
        if state.startswith("adm_addplan_days_"):
            rest=state[len("adm_addplan_days_"):]; parts3=rest.split("|",2)
            key=parts3[0]; name=parts3[1]; price=float(parts3[2]); clear_state_keys(uid)
            try:
                days=int(text); conn=get_conn()
                try:
                    conn.execute("INSERT OR REPLACE INTO hosting_plans (plan_key,name,price,days,is_active) VALUES (?,?,?,?,1)",
                                 (key,name,price,days)); conn.commit()
                finally: conn.close()
                audit(uid,"ADD_PLAN",details=f"{key} {name} {price}BDT {days}d")
                bot.send_message(uid,f"✅ প্ল্যান যোগ হয়েছে!\n🔑 `{key}`\n📦 {name}\n💵 {int(price)} BDT\n📅 {days} দিন",reply_markup=admin_settings_kb())
            except ValueError:
                bot.send_message(uid,"❌ সঠিক দিন সংখ্যা দিন।",reply_markup=admin_settings_kb())
            return

        if state.startswith("adm_editplan_"):
            key=state[len("adm_editplan_"):]; clear_state_keys(uid)
            try:
                parts4=text.split("|")
                if len(parts4)>=3:
                    name=parts4[0].strip(); price=float(parts4[1]); days=int(parts4[2])
                    conn=get_conn()
                    try: conn.execute("UPDATE hosting_plans SET name=?,price=?,days=? WHERE plan_key=?",(name,price,days,key)); conn.commit()
                    finally: conn.close()
                    audit(uid,"EDIT_PLAN",details=f"{key} → {name} {price}BDT {days}d")
                    bot.send_message(uid,f"✅ প্ল্যান আপডেট হয়েছে!\n📦 {name} | {int(price)} BDT | {days} দিন",reply_markup=admin_settings_kb())
                else:
                    bot.send_message(uid,"❌ Format: নাম|মূল্য|দিন",reply_markup=admin_settings_kb())
            except Exception as e:
                bot.send_message(uid,f"❌ ত্রুটি: {e}",reply_markup=admin_settings_kb())
            return

        if state=="adm_delplan":
            clear_state_keys(uid); key=text.strip(); conn=get_conn()
            try: conn.execute("UPDATE hosting_plans SET is_active=0 WHERE plan_key=?",(key,)); conn.commit()
            finally: conn.close()
            audit(uid,"DELETE_PLAN",details=key)
            bot.send_message(uid,f"✅ প্ল্যান `{key}` মুছে দেওয়া হয়েছে।",reply_markup=admin_settings_kb()); return

        if state.startswith("adm_editlimit_"):
            key=state[len("adm_editlimit_"):]; clear_state_keys(uid)
            smap={"mindep":"min_deposit","minwd":"min_withdraw","wdcharge":"withdraw_charge","maxwd":"max_withdraw_day",
                  "refbonus":"referral_bonus","checkin":"daily_checkin_bonus","bkash":"bkash_number","nagad":"nagad_number","usdt":"usdt_wallet"}
            setting_key=smap.get(key)
            if setting_key:
                ss(setting_key,text.strip())
                bot.send_message(uid,f"✅ `{setting_key}` → `{text.strip()}` আপডেট হয়েছে।",reply_markup=admin_settings_kb())
            return

        if state.startswith("adm_editrule_"):
            m=state[len("adm_editrule_"):]; clear_state_keys(uid)
            if m in ("bkash","nagad","usdt"):
                ss(f"{m}_rule",text.strip())
                audit(uid,"EDIT_PAYMENT_RULE",details=m)
                bot.send_message(uid,f"✅ {m.upper()} নিয়ম আপডেট হয়েছে।",reply_markup=admin_payment_kb())
            return

        if state=="adm_premium_id":
            clear_state_keys(uid)
            try:
                target=int(text.strip()); r=get_user(target)
                if not r: bot.send_message(uid,"❌ ইউজার পাওয়া যায়নি।",reply_markup=admin_user_kb()); return
                new_val=0 if r["is_premium"] else 1
                conn=get_conn()
                try: conn.execute("UPDATE users SET is_premium=? WHERE user_id=?",(new_val,target)); conn.commit()
                finally: conn.close()
                audit(uid,"SET_PREMIUM",target,str(new_val))
                label="⭐ প্রিমিয়াম দেওয়া হয়েছে!" if new_val else "👤 প্রিমিয়াম সরানো হয়েছে।"
                bot.send_message(uid,f"{label} ইউজার: {target}",reply_markup=admin_user_kb())
                ssend(target,"⭐ আপনাকে প্রিমিয়াম করা হয়েছে!" if new_val else "👤 আপনার প্রিমিয়াম বাতিল হয়েছে।")
            except ValueError:
                bot.send_message(uid,"❌ সঠিক আইডি দিন।",reply_markup=admin_user_kb())
            return

        # ════════ SECTION NAVIGATION ════════
        if text in ("🤖 বট সেবা","🤖 Bot Services"):
            bot.send_message(uid,"🤖 বট সেবা:",reply_markup=bot_services_kb(lang)); return
        if text in ("💰 পেমেন্ট","💰 Payments"):
            bot.send_message(uid,"💰 পেমেন্ট:",reply_markup=payment_kb(lang)); return
        if text in ("👥 রেফারেল ও আয়","👥 Referral & Earn"):
            bot.send_message(uid,"👥 রেফারেল ও আয়:",reply_markup=referral_kb(lang)); return
        if text in ("💬 সাপোর্ট","💬 Support"):
            bot.send_message(uid,"💬 সাপোর্ট:",reply_markup=support_kb(lang)); return

        # ── Bot Services ──
        if text in ("🤖 নতুন বট হোস্ট","🤖 Host New Bot"):
            if gs("feature_hosting")!="1":
                bot.send_message(uid,"⚠️ এই ফিচার সাময়িকভাবে বন্ধ আছে।",reply_markup=bot_services_kb(lang)); return
            user_state[uid]="await_hosting_file"
            bot.send_message(uid,"📁 আপনার .py ফাইল এবং requirements.txt ডকুমেন্ট হিসেবে আপলোড করুন।",reply_markup=cancel_only_kb(lang)); return
        if text in ("🛠️ বট বানান","🛠️ Build a Bot"):
            if gs("feature_custom_bot")!="1":
                bot.send_message(uid,"⚠️ এই ফিচার সাময়িকভাবে বন্ধ আছে।",reply_markup=bot_services_kb(lang)); return
            user_state[uid]="await_custom_idea"
            bot.send_message(uid,"💡 আপনি কী ধরনের বট বানাতে চান তা বিস্তারিত লিখুন:",reply_markup=cancel_only_kb(lang)); return
        if text in ("📦 আমার বটগুলো","📦 My Active Bots"):
            _send_my_bots(uid,lang); return
        if text in ("📋 মূল্য তালিকা","📋 Price List"):
            bot.send_message(uid,"📋 বিভাগ বেছে নিন:",reply_markup=price_cat_kb(lang)); return
        if text in ("💻 হোস্টিং প্যাকেজ","💻 Hosting Packages"):
            plans=get_all_plans(); txt="💻 হোস্টিং প্যাকেজ:\n\n"
            for i,(k,p) in enumerate(plans.items(),1):
                txt+=f"{i}. 📦 {p['name']}: {int(p['price'])} BDT / {p['days']} দিন\n"
            bot.send_message(uid,txt,reply_markup=price_cat_kb(lang)); return
        if text in ("🤖 কাস্টম বট মূল্য","🤖 Custom Bot Pricing"):
            bot.send_message(uid,"🤖 কাস্টম বট তৈরির মূল্য:\n\n🔹 সিম্পল বাটন বট: ১০০-২৫০ BDT\n🔹 গ্রুপ/চ্যানেল কন্ট্রোলার: ২০০-৪০০ BDT\n🔹 অ্যাডমিন প্যানেল + পেমেন্ট: ৫০০-১০০০+ BDT",
                            reply_markup=price_cat_kb(lang)); return

        # ── Payment ──
        if text in ("💳 ব্যালেন্স যোগ","💳 Add Balance"):
            min_dep=float(gs("min_deposit",str(MIN_DEPOSIT)))
            bot.send_message(uid,f"💳 পেমেন্ট পদ্ধতি বেছে নিন:\n💰 সর্বনিম্ন ডিপোজিট: {int(min_dep)} BDT",reply_markup=pay_method_kb(lang)); return
        if text=="📱 Bkash":
            user_state[uid]="await_pay_amount"; user_state[f"{uid}_method"]="bkash"
            min_dep=float(gs("min_deposit",str(MIN_DEPOSIT)))
            bot.send_message(uid,
                f"📱 *Bkash নম্বর (ট্যাপ করে কপি করুন):*\n`{gs('bkash_number')}`\n\n"
                f"{gs('bkash_rule')}\n\n"
                f"💵 এখন আপনি কত টাকা পাঠাবেন তা লিখুন (সর্বনিম্ন {int(min_dep)} BDT):",
                reply_markup=cancel_only_kb(lang)); return
        if text=="📱 Nagad":
            user_state[uid]="await_pay_amount"; user_state[f"{uid}_method"]="nagad"
            min_dep=float(gs("min_deposit",str(MIN_DEPOSIT)))
            bot.send_message(uid,
                f"📱 *Nagad নম্বর (ট্যাপ করে কপি করুন):*\n`{gs('nagad_number')}`\n\n"
                f"{gs('nagad_rule')}\n\n"
                f"💵 এখন আপনি কত টাকা পাঠাবেন তা লিখুন (সর্বনিম্ন {int(min_dep)} BDT):",
                reply_markup=cancel_only_kb(lang)); return
        if text=="💱 USDT (BEP-20)":
            user_state[uid]="await_pay_amount"; user_state[f"{uid}_method"]="usdt"
            min_usdt=float(gs("min_usdt","0.50")); rate=float(gs("usdt_rate","120"))
            bot.send_message(uid,
                f"💱 *USDT ওয়ালেট এড্রেস (ট্যাপ করে কপি করুন, নেটওয়ার্ক: BEP-20/BSC):*\n`{gs('usdt_wallet')}`\n\n"
                f"{gs('usdt_rule')}\n\n"
                f"💵 এখন আপনি কত USDT পাঠাবেন তা লিখুন (সর্বনিম্ন {min_usdt:g} USDT, বর্তমান রেট: 1 USDT = {int(rate)} BDT):",
                reply_markup=cancel_only_kb(lang)); return

        if text in ("💸 উইথড্র","💸 Withdraw"):
            if gs("feature_withdraw")!="1":
                bot.send_message(uid,"⚠️ উইথড্র সাময়িকভাবে বন্ধ আছে।",reply_markup=payment_kb(lang)); return
            bal=get_balance(uid); min_w=float(gs("min_withdraw",str(MIN_WITHDRAW)))
            if bal<min_w:
                bot.send_message(uid,f"❌ অপর্যাপ্ত ব্যালেন্স!\n💰 আপনার: {round(bal,2)} BDT | সর্বনিম্ন: {int(min_w)} BDT",reply_markup=payment_kb(lang)); return
            charge=float(gs("withdraw_charge",str(WITHDRAW_CHARGE))); max_wd=int(gs("max_withdraw_day",str(MAX_WITHDRAW_DAY)))
            bot.send_message(uid,f"💸 উইথড্র প্যানেল\n\n💰 ব্যালেন্স: {round(bal,2)} BDT\n📉 সর্বনিম্ন: {int(min_w)} BDT\n"
                             f"💳 চার্জ: {int(charge)} BDT\n📊 দৈনিক সীমা: {max_wd} বার\n\n📱 পদ্ধতি বেছে নিন:",
                             reply_markup=withdraw_method_kb(lang)); return
        if text=="📱 Bkash WD":
            bal=get_balance(uid); min_w=float(gs("min_withdraw",str(MIN_WITHDRAW)))
            if bal<min_w: bot.send_message(uid,f"❌ অপর্যাপ্ত ব্যালেন্স!",reply_markup=payment_kb(lang)); return
            user_state[uid]="await_wd_amount_bkash"
            bot.send_message(uid,"💵 পরিমাণ লিখুন:",reply_markup=cancel_only_kb(lang)); return
        if text=="📱 Nagad WD":
            bal=get_balance(uid); min_w=float(gs("min_withdraw",str(MIN_WITHDRAW)))
            if bal<min_w: bot.send_message(uid,f"❌ অপর্যাপ্ত ব্যালেন্স!",reply_markup=payment_kb(lang)); return
            user_state[uid]="await_wd_amount_nagad"
            bot.send_message(uid,"💵 পরিমাণ লিখুন:",reply_markup=cancel_only_kb(lang)); return

        if text in ("👛 আমার ওয়ালেট","👛 My Wallet"): _send_profile(uid,lang); return
        if text in ("📊 লেনদেন ইতিহাস","📊 Transaction History"): _send_tx_history(uid,lang); return
        if text in ("🎁 কুপন ব্যবহার","🎁 Use Coupon"):
            user_state[uid]="await_coupon_code"
            bot.send_message(uid,"🎁 কুপন কোড লিখুন:",reply_markup=cancel_only_kb(lang)); return
        if text in ("📅 সাব. ইতিহাস","📅 Subscription History"): _send_sub_history(uid,lang); return

        # ── Referral ──
        if text in ("🔗 রেফারেল প্যানেল","🔗 Referral Panel"):
            if gs("feature_referral")!="1":
                bot.send_message(uid,"⚠️ রেফারেল ফিচার সাময়িকভাবে বন্ধ।",reply_markup=referral_kb(lang)); return
            _send_referral(uid,lang); return
        if text in ("📅 দৈনিক চেক-ইন","📅 Daily Check-in"): _do_checkin(uid,lang); return

        # ── Support ──
        if text in ("💬 সাপোর্ট পাঠান","💬 Send Support"):
            user_state[uid]="await_support"
            bot.send_message(uid,"💬 আপনার সমস্যা বা মতামত লিখুন (ছবি/স্ক্রিনশটও পাঠাতে পারেন):",reply_markup=cancel_only_kb(lang)); return
        if text in ("👤 আমার প্রোফাইল","👤 My Profile"): _send_profile(uid,lang); return
        if text in ("🌐 ভাষা পরিবর্তন","🌐 Change Language"):
            bot.send_message(uid,"🌐 ভাষা বেছে নিন:",reply_markup=lang_kb()); return
        if text=="🇧🇩 বাংলা":
            conn=get_conn()
            try: conn.execute("UPDATE users SET language='bn' WHERE user_id=?",(uid,)); conn.commit()
            finally: conn.close()
            bot.send_message(uid,"✅ ভাষা সেট হয়েছে।",reply_markup=main_kb("bn")); return
        if text=="🇬🇧 English":
            conn=get_conn()
            try: conn.execute("UPDATE users SET language='en' WHERE user_id=?",(uid,)); conn.commit()
            finally: conn.close()
            bot.send_message(uid,"✅ Language set.",reply_markup=main_kb("en")); return

        # ── Renew / Auto-renew via reply kb ──
        if text in ("🔄 নবায়ন করুন","🔄 Renew"):
            sub_id=user_state.get(f"{uid}_renew_target")
            if not sub_id: bot.send_message(uid,"❌ বট নির্বাচন করুন।",reply_markup=main_kb(lang)); return
            _do_renew(uid,lang,int(sub_id)); return
        if text in ("🚀 অটো-নবায়ন","🚀 Auto-Renew"):
            sub_id=user_state.get(f"{uid}_renew_target")
            if not sub_id: bot.send_message(uid,"❌ বট নির্বাচন করুন।",reply_markup=main_kb(lang)); return
            _toggle_autorenew(uid,lang,int(sub_id)); return

        # buy plan via reply kb
        if text.startswith("📦 ") and " — " in text:
            plan_name_part=text[2:].split(" — ")[0].strip()
            plans=get_all_plans()
            match=None
            for k,p in plans.items():
                if p["name"]==plan_name_part: match=k; break
            if match: _buy_plan(uid,lang,match); return

        # ════════ ADMIN SECTIONS ════════
        if not is_admin(uid): return

        if text=="📊 ড্যাশবোর্ড": bot.send_message(uid,"📊 ড্যাশবোর্ড:",reply_markup=admin_dashboard_kb()); return
        if text=="👥 ইউজার ম্যানেজ":
            if not has_perm(uid,"users"): bot.send_message(uid,"🚫 অ্যাক্সেস নেই।",reply_markup=get_admin_kb(uid)); return
            bot.send_message(uid,"👥 ইউজার ম্যানেজ:",reply_markup=admin_user_kb()); return
        if text=="💳 পেমেন্ট ম্যানেজ":
            if not has_perm(uid,"payments"): bot.send_message(uid,"🚫 অ্যাক্সেস নেই।",reply_markup=get_admin_kb(uid)); return
            bot.send_message(uid,"💳 পেমেন্ট ম্যানেজ:",reply_markup=admin_payment_kb()); return
        if text=="🤖 বট ম্যানেজ": bot.send_message(uid,"🤖 বট ম্যানেজ:",reply_markup=admin_bot_kb()); return
        if text=="⚙️ সেটিংস":
            if not is_super(uid): bot.send_message(uid,"🚫 শুধু সুপার অ্যাডমিন।",reply_markup=get_admin_kb(uid)); return
            bot.send_message(uid,"⚙️ সেটিংস:",reply_markup=admin_settings_kb()); return

        if text=="📊 স্ট্যাটস": _send_stats(uid); return
        if text=="📈 অ্যানালিটিক্স": _send_analytics(uid); return
        if text=="📋 অডিট লগ": _send_audit(uid); return
        if text=="💾 ব্যাকআপ":
            if os.path.exists(DB_FILE):
                with open(DB_FILE,"rb") as f: bot.send_document(uid,f,caption=f"💾 DB Backup {datetime.now().strftime('%Y-%m-%d %H:%M')}")
                audit(uid,"BACKUP_DOWNLOAD")
            return
        if text=="📤 ইউজার এক্সপোর্ট": _export_users(uid); return

        if text=="👥 ইউজার লিস্ট": _send_user_list(uid); return
        if text=="🔍 ইউজার খুঁজুন":
            user_state[uid]="adm_profile"; bot.send_message(uid,"🔍 ইউজার আইডি বা ইউজারনেম দিন:",reply_markup=cancel_only_kb(lang)); return
        if text=="⭐ প্রিমিয়াম দিন":
            user_state[uid]="adm_premium_id"; bot.send_message(uid,"⭐ ইউজার আইডি দিন:",reply_markup=cancel_only_kb(lang)); return
        if text=="🚫 ব্যান/আনব্যান":
            kb_ban=types.InlineKeyboardMarkup()
            kb_ban.row(types.InlineKeyboardButton("🚫 Ban",callback_data="ai_ban"),types.InlineKeyboardButton("✅ Unban",callback_data="ai_unban"))
            kb_ban.add(types.InlineKeyboardButton("❌ Cancel",callback_data="close_panel"))
            bot.send_message(uid,"🚫 Ban/Unban:",reply_markup=kb_ban); return
        if text=="💰 ব্যালেন্স দিন":
            user_state[uid]="adm_addbal_id"; bot.send_message(uid,"👤 ইউজার আইডি দিন:",reply_markup=cancel_only_kb(lang)); return
        if text=="🏆 রেফারেল লিডার": _send_referral_leaderboard(uid); return
        if text=="👑 স্টাফ ম্যানেজ":
            if not is_super(uid): bot.send_message(uid,"🚫 শুধু সুপার অ্যাডমিন।",reply_markup=admin_user_kb()); return
            user_state[uid]="adm_setrole_id"; bot.send_message(uid,"👤 ইউজার আইডি দিন:",reply_markup=cancel_only_kb(lang)); return

        if text=="💳 পেমেন্ট রিকু.": _send_pending_payments(uid); return
        if text=="💸 উইথড্র রিকু.": _send_pending_withdrawals(uid); return
        if text=="🎁 কুপন ম্যানেজ": _send_coupon_panel(uid); return
        if text=="📱 পেমেন্ট নম্বর":
            kb_num=types.InlineKeyboardMarkup()
            kb_num.add(types.InlineKeyboardButton(f"📱 Bkash: {gs('bkash_number')}",callback_data="editlimit_bkash"))
            kb_num.add(types.InlineKeyboardButton("✏️ Bkash নিয়ম এডিট",callback_data="editrule_bkash"))
            kb_num.add(types.InlineKeyboardButton(f"📱 Nagad: {gs('nagad_number')}",callback_data="editlimit_nagad"))
            kb_num.add(types.InlineKeyboardButton("✏️ Nagad নিয়ম এডিট",callback_data="editrule_nagad"))
            kb_num.add(types.InlineKeyboardButton("💱 USDT Wallet",callback_data="editlimit_usdt"))
            kb_num.add(types.InlineKeyboardButton("✏️ USDT নিয়ম এডিট",callback_data="editrule_usdt"))
            kb_num.add(types.InlineKeyboardButton("❌ Close",callback_data="close_panel"))
            bot.send_message(uid,"📱 পেমেন্ট নম্বর ও নিয়ম এডিট করুন:",reply_markup=kb_num); return

        if text=="📁 হোস্টিং রিকু.": _send_pending_hosting(uid); return
        if text=="🤖 কাস্টম অর্ডার": _send_pending_custom(uid); return
        if text=="🎫 সাপোর্ট টিকেট": _send_support_tickets(uid); return
        if text=="📢 ব্রডকাস্ট":
            bot.send_message(uid,"📢 ব্রডকাস্ট টাইপ বেছে নিন:",reply_markup=bc_type_inline()); return
        if text=="🎯 টার্গেটেড BC":
            bot.send_message(uid,"🎯 টার্গেট গ্রুপ বেছে নিন:",reply_markup=targeted_bc_inline()); return

        if text=="🔧 ফিচার টগল":
            bot.send_message(uid,"🔧 ফিচার অন/অফ করুন:",reply_markup=feature_toggle_inline()); return
        if text=="📋 প্ল্যান ম্যানেজ":
            bot.send_message(uid,"📋 হোস্টিং প্ল্যান ম্যানেজ:",reply_markup=plan_manage_inline()); return
        if text=="✏️ স্বাগত মেসেজ":
            user_state[uid]="adm_welcome"; bot.send_message(uid,"✏️ নতুন স্বাগত বার্তা লিখুন:",reply_markup=cancel_only_kb(lang)); return
        if text=="📢 নোটিশ সেট":
            user_state[uid]="adm_notice"; bot.send_message(uid,"📢 নোটিশ লিখুন (মুছতে 'clear' লিখুন):",reply_markup=cancel_only_kb(lang)); return
        if text=="💬 ডিরেক্ট মেসেজ":
            user_state[uid]="adm_dm_uid"; bot.send_message(uid,"👤 ইউজার আইডি দিন:",reply_markup=cancel_only_kb(lang)); return
        if text=="💸 লিমিট সেটিংস":
            bot.send_message(uid,"💸 লিমিট ও সেটিংস এডিট করুন:",reply_markup=limit_settings_inline()); return
        if text=="🔐 পাসওয়ার্ড চেঞ্জ":
            user_state[uid]="adm_change_pass"; bot.send_message(uid,"🔐 নতুন পাসওয়ার্ড দিন (৬+ ক্যারেক্টার):",reply_markup=cancel_only_kb(lang)); return
    except Exception as e:
        logger.error(f"handle_text error: {e}", exc_info=True)
        try:
            uid2=msg.from_user.id
            clear_state_keys(uid2)
            bot.send_message(uid2,"❌ একটি সমস্যা হয়েছে। আবার চেষ্টা করুন বা /start দিন।")
        except Exception:
            pass

# ════════════════════════════════════════════════════════════
# PHOTO / DOCUMENT / VIDEO HANDLERS
# ════════════════════════════════════════════════════════════
@bot.message_handler(content_types=["photo"])
def handle_photo(msg):
    reg(msg.from_user); uid=msg.from_user.id; state=user_state.get(uid,""); lang=get_lang(uid)
    if is_banned(uid) or (is_maint() and not is_admin(uid)): return
    if state=="await_support":
        clear_state_keys(uid)
        photo_id=msg.photo[-1].file_id; caption=msg.caption or ""
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"); conn=get_conn()
        try:
            conn.execute("INSERT INTO support_tickets (user_id,message,photo_id,status,created_at) VALUES (?,?,?,?,?)",
                         (uid,caption,photo_id,"open",now))
            tid=conn.execute("SELECT last_insert_rowid()").fetchone()[0]; conn.commit()
        finally: conn.close()
        uname=f"@{msg.from_user.username}" if msg.from_user.username else str(uid)
        try:
            bot.send_photo(SUPER_ADMIN_ID,photo_id,
                           caption=f"📸 Support Photo #{tid}\n👤 {msg.from_user.first_name} ({uid}) {uname}\n\n{caption}",
                           reply_markup=support_reply_inline(uid,tid))
        except: pass
        bot.send_message(uid,"✅ ছবি/স্ক্রিনশট সাপোর্ট টিমে পাঠানো হয়েছে!",reply_markup=support_kb(lang))
    elif state=="adm_broadcast_photo" and is_admin(uid):
        clear_state_keys(uid)
        threading.Thread(target=do_broadcast,args=(uid,msg.caption or "","all","photo",msg.photo[-1].file_id),daemon=True).start()
        bot.send_message(uid,"📢 Photo broadcast শুরু হয়েছে...",reply_markup=admin_bot_kb())

@bot.message_handler(content_types=["document"])
def handle_document(msg):
    reg(msg.from_user); uid=msg.from_user.id; state=user_state.get(uid,""); lang=get_lang(uid)
    if is_banned(uid) or (is_maint() and not is_admin(uid)): return
    if state=="await_hosting_file":
        clear_state_keys(uid)
        fname=msg.document.file_name or "unknown"; now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"); conn=get_conn()
        try:
            conn.execute("INSERT INTO hosting_requests (user_id,file_msg_id,status,created_at) VALUES (?,?,?,?)",
                         (uid,msg.message_id,"pending_review",now))
            req_id=conn.execute("SELECT last_insert_rowid()").fetchone()[0]; conn.commit()
        finally: conn.close()
        for sid in get_staff_ids("hosting"):
            try: bot.forward_message(sid,uid,msg.message_id)
            except: pass
        uname=f"@{msg.from_user.username}" if msg.from_user.username else str(uid)
        fname_esc=md_escape(msg.from_user.first_name or str(uid)); fname_doc=md_escape(fname)
        notify_staff("hosting",f"📁 নতুন হোস্টিং ফাইল!\n👤 {fname_esc} ({uid}) {uname}\n📄 {fname_doc} | req#{req_id}",
              markup_builder=lambda: file_review_inline(uid,req_id))
        bot.send_message(uid,"✅ ফাইল অ্যাডমিনকে পাঠানো হয়েছে! শীঘ্রই রিভিউ করা হবে।",reply_markup=bot_services_kb(lang))
    elif state=="adm_broadcast_doc" and is_admin(uid):
        clear_state_keys(uid)
        threading.Thread(target=do_broadcast,args=(uid,msg.caption or "","all","document",msg.document.file_id),daemon=True).start()
        bot.send_message(uid,"📢 Document broadcast শুরু হয়েছে...",reply_markup=admin_bot_kb())

@bot.message_handler(content_types=["video"])
def handle_video(msg):
    uid=msg.from_user.id; state=user_state.get(uid,"")
    if state=="adm_broadcast_video" and is_admin(uid):
        clear_state_keys(uid)
        threading.Thread(target=do_broadcast,args=(uid,msg.caption or "","all","video",msg.video.file_id),daemon=True).start()
        bot.send_message(uid,"📢 Video broadcast শুরু হয়েছে...",reply_markup=admin_bot_kb())

# ════════════════════════════════════════════════════════════
# CALLBACK HANDLER (admin actions — auto-delete after use)
# ════════════════════════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: True)
def handle_callback(call):
    try:
        uid=call.from_user.id; data=call.data; lang=get_lang(uid)
        sans(call)

        if data=="close_panel":
            sdel(call.message.chat.id,call.message.message_id); return

        # Payment approve/reject
        if data.startswith("apay_") and is_admin(uid) and has_perm(uid,"payments"):
            parts=data.split("_",4); tuid=int(parts[1]); pay_id=int(parts[2])
            try: amount=float(parts[3])
            except: amount=0.0
            conn=get_conn()
            try:
                ex=conn.execute("SELECT status FROM payment_requests WHERE id=?",(pay_id,)).fetchone()
                if not ex or ex["status"]!="pending":
                    sans(call,"⚠️ ইতিমধ্যে প্রসেস হয়েছে।",alert=True); sdel(call.message.chat.id,call.message.message_id); conn.close(); return
                conn.execute("UPDATE payment_requests SET status='approved' WHERE id=?",(pay_id,)); conn.commit()
            finally: conn.close()
            add_bal(tuid,amount,"payment approved"); audit(uid,"APPROVE_PAYMENT",tuid,f"+{amount}")
            sdel(call.message.chat.id,call.message.message_id)
            ssend(tuid,f"✅ পেমেন্ট অনুমোদিত!\n+{amount} BDT যোগ হয়েছে।\n💰 ব্যালেন্স: {round(get_balance(tuid),2)} BDT")
            bot.send_message(uid,f"✅ Payment approved: +{amount} BDT → {tuid}"); return

        if data.startswith("rpay_") and is_admin(uid) and has_perm(uid,"payments"):
            parts=data.split("_"); tuid=int(parts[1]); pay_id=int(parts[2]); conn=get_conn()
            try:
                ex=conn.execute("SELECT status FROM payment_requests WHERE id=?",(pay_id,)).fetchone()
                if not ex or ex["status"]!="pending":
                    sans(call,"⚠️ ইতিমধ্যে প্রসেস হয়েছে।",alert=True); sdel(call.message.chat.id,call.message.message_id); conn.close(); return
                conn.execute("UPDATE payment_requests SET status='rejected' WHERE id=?",(pay_id,)); conn.commit()
            finally: conn.close()
            audit(uid,"REJECT_PAYMENT",tuid); sdel(call.message.chat.id,call.message.message_id)
            ssend(tuid,"❌ পেমেন্ট বাতিল হয়েছে। সাপোর্টে যোগাযোগ করুন।")
            bot.send_message(uid,f"❌ Payment rejected for {tuid}"); return

        # Withdraw done/cancel
        if data.startswith("wd_done_") and is_admin(uid) and has_perm(uid,"withdrawals"):
            parts=data.split("_"); tuid=int(parts[2]); wd_id=int(parts[3]); amount=float(parts[4]); conn=get_conn()
            try:
                ex=conn.execute("SELECT status FROM withdraw_requests WHERE id=?",(wd_id,)).fetchone()
                if not ex or ex["status"]!="pending":
                    sans(call,"⚠️ ইতিমধ্যে প্রসেস হয়েছে।",alert=True); sdel(call.message.chat.id,call.message.message_id); conn.close(); return
                conn.execute("UPDATE withdraw_requests SET status='approved' WHERE id=?",(wd_id,)); conn.commit()
            finally: conn.close()
            audit(uid,"WITHDRAW_APPROVED",tuid,str(amount)); sdel(call.message.chat.id,call.message.message_id)
            ssend(tuid,f"✅ উইথড্র অনুমোদিত!\n💸 {int(amount)} BDT পাঠানো হয়েছে।\n💰 ব্যালেন্স: {round(get_balance(tuid),2)} BDT")
            bot.send_message(uid,f"✅ Withdraw sent to {tuid}: {int(amount)} BDT"); return

        if data.startswith("wd_cancel_") and is_admin(uid) and has_perm(uid,"withdrawals"):
            parts=data.split("_"); tuid=int(parts[2]); wd_id=int(parts[3]); amount=float(parts[4]); conn=get_conn()
            try:
                ex=conn.execute("SELECT status FROM withdraw_requests WHERE id=?",(wd_id,)).fetchone()
                if not ex or ex["status"]!="pending":
                    sans(call,"⚠️ ইতিমধ্যে প্রসেস হয়েছে।",alert=True); sdel(call.message.chat.id,call.message.message_id); conn.close(); return
                conn.execute("UPDATE withdraw_requests SET status='cancelled' WHERE id=?",(wd_id,))
                conn.execute("UPDATE users SET withdraw_today=MAX(0,withdraw_today-1) WHERE user_id=?",(tuid,)); conn.commit()
            finally: conn.close()
            add_bal(tuid,amount,"withdraw refund"); audit(uid,"WITHDRAW_CANCELLED",tuid,f"{int(amount)} refunded")
            sdel(call.message.chat.id,call.message.message_id)
            ssend(tuid,f"❌ উইথড্র বাতিল।\n💰 {int(amount)} BDT ফেরত দেওয়া হয়েছে।\n💰 ব্যালেন্স: {round(get_balance(tuid),2)} BDT")
            bot.send_message(uid,f"✅ Withdraw cancelled, {int(amount)} BDT refunded to {tuid}"); return

        # Hosting accept/cancel
        if data.startswith("haccept_") and is_admin(uid) and has_perm(uid,"hosting"):
            parts=data.split("_"); tuid=int(parts[1]); req_id=int(parts[2]); conn=get_conn()
            try:
                ex=conn.execute("SELECT status FROM hosting_requests WHERE id=?",(req_id,)).fetchone()
                if not ex or ex["status"]!="pending_review":
                    sans(call,"⚠️ ইতিমধ্যে প্রসেস হয়েছে।",alert=True); sdel(call.message.chat.id,call.message.message_id); conn.close(); return
                conn.execute("UPDATE hosting_requests SET status='accepted' WHERE id=?",(req_id,)); conn.commit()
            finally: conn.close()
            sdel(call.message.chat.id,call.message.message_id); audit(uid,"HOST_ACCEPT",tuid,f"req#{req_id}")
            ulang=get_lang(tuid)
            ssend(tuid,"✅ আপনার ফাইল গৃহীত হয়েছে!\n\n📦 একটি হোস্টিং প্ল্যান বেছে নিন:",reply_markup=hosting_plan_kb(ulang))
            return

        if data.startswith("hcancel_") and is_admin(uid) and has_perm(uid,"hosting"):
            parts=data.split("_"); tuid=int(parts[1]); req_id=int(parts[2]); conn=get_conn()
            try: conn.execute("UPDATE hosting_requests SET status='cancelled' WHERE id=?",(req_id,)); conn.commit()
            finally: conn.close()
            sdel(call.message.chat.id,call.message.message_id); audit(uid,"HOST_CANCEL",tuid)
            ssend(tuid,"❌ আপনার ফাইল গৃহীত হয়নি। সাপোর্টে যোগাযোগ করুন।"); return

        # Custom order
        if data.startswith("caccept_") and is_admin(uid) and has_perm(uid,"custom"):
            parts=data.split("_"); tuid=int(parts[1]); order_id=parts[2]; conn=get_conn()
            try:
                ex=conn.execute("SELECT status FROM custom_bot_orders WHERE id=?",(order_id,)).fetchone()
                if not ex or ex["status"]!="pending":
                    sans(call,"⚠️ ইতিমধ্যে প্রসেস হয়েছে।",alert=True); sdel(call.message.chat.id,call.message.message_id); conn.close(); return
                conn.execute("UPDATE custom_bot_orders SET status='accepted' WHERE id=?",(order_id,)); conn.commit()
            finally: conn.close()
            sdel(call.message.chat.id,call.message.message_id); audit(uid,"CUSTOM_ACCEPT",tuid,f"order#{order_id}")
            ssend(tuid,"✅ আপনার কাস্টম বট অর্ডার গৃহীত হয়েছে!\n\n📩 অ্যাডমিন শীঘ্রই যোগাযোগ করবেন।"); return

        if data.startswith("creject_") and is_admin(uid) and has_perm(uid,"custom"):
            parts=data.split("_"); tuid=int(parts[1]); order_id=parts[2]; conn=get_conn()
            try: conn.execute("UPDATE custom_bot_orders SET status='rejected' WHERE id=?",(order_id,)); conn.commit()
            finally: conn.close()
            sdel(call.message.chat.id,call.message.message_id); audit(uid,"CUSTOM_REJECT",tuid)
            ssend(tuid,"❌ আপনার কাস্টম বট অর্ডার বাতিল হয়েছে।\nবিস্তারিত জানতে সাপোর্টে যোগাযোগ করুন।"); return

        if data.startswith("creply_") and is_admin(uid) and has_perm(uid,"custom"):
            parts=data.split("_"); tuid=int(parts[1]); order_id=parts[2]
            user_state[uid]=f"adm_custom_reply_{tuid}_{order_id}"
            sdel(call.message.chat.id,call.message.message_id)
            bot.send_message(uid,f"✍️ কাস্টম বট অর্ডার #{order_id} (ইউজার: {tuid}) এর উত্তর লিখুন:",reply_markup=cancel_only_kb("bn")); return

        # Support reply
        if data.startswith("rticket_") and is_admin(uid):
            parts=data.split("_"); tuid=int(parts[1]); tid=parts[2]
            user_state[uid]=f"adm_reply_{tuid}"; conn=get_conn()
            try: conn.execute("UPDATE support_tickets SET status='answered' WHERE id=?",(tid,)); conn.commit()
            finally: conn.close()
            sdel(call.message.chat.id,call.message.message_id)
            bot.send_message(uid,f"✍️ Ticket #{tid} (ইউজার: {tuid}) এর উত্তর লিখুন:",reply_markup=cancel_only_kb("bn")); return

        # User reply
        if data.startswith("user_reply_"):
            admin_id=int(data[len("user_reply_"):])
            user_state[uid]=f"user_replying_{admin_id}"
            bot.send_message(uid,"✍️ আপনার উত্তর লিখুন:",reply_markup=cancel_only_kb(lang)); return

        # Plan order approve/reject
        if data.startswith("pok_") and is_admin(uid) and has_perm(uid,"payments"):
            parts=data[4:].split("_",2); tuid=int(parts[0]); plan_key=parts[1]; req_id=int(parts[2]) if len(parts)>2 else 0
            plan=get_plan(plan_key)
            if not plan: bot.send_message(uid,"❌ Plan not found."); return
            ok=deduct_bal(tuid,plan["price"],f"hosting {plan_key}")
            if ok:
                now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"); expiry=(datetime.now()+timedelta(days=plan["days"])).strftime("%Y-%m-%d")
                conn=get_conn()
                try:
                    conn.execute("INSERT INTO subscriptions (user_id,bot_name,plan,status,expiry_date,created_at) VALUES (?,?,?,?,?,?)",
                                 (tuid,f"Bot#{tuid}",plan_key,"active",expiry,now))
                    conn.execute("INSERT INTO subscription_history (user_id,plan,price,expiry,action,created_at) VALUES (?,?,?,?,?,?)",
                                 (tuid,plan_key,plan["price"],expiry,"purchase",now))
                    if req_id: conn.execute("UPDATE hosting_requests SET status='approved',plan=? WHERE id=?",(plan_key,req_id))
                    conn.commit()
                finally: conn.close()
                audit(uid,"PLAN_APPROVE",tuid,f"{plan_key} -{int(plan['price'])}")
                sdel(call.message.chat.id,call.message.message_id)
                ssend(tuid,f"🚀 হোস্টিং সক্রিয় হয়েছে!\n\n📦 {plan['name']}\n📅 মেয়াদ: {expiry} ({plan['days']} দিন)\n"
                      f"💳 কাটা হয়েছে: {int(plan['price'])} BDT | 💰 ব্যালেন্স: {round(get_balance(tuid),2)} BDT")
                bot.send_message(uid,f"✅ Plan approved for {tuid} | {plan['name']} | Expiry: {expiry}")
            else:
                sdel(call.message.chat.id,call.message.message_id)
                ssend(tuid,"❌ প্ল্যান সক্রিয় ব্যর্থ। অপর্যাপ্ত ব্যালেন্স।")
                bot.send_message(uid,f"❌ Insufficient balance for {tuid}")
            return

        if data.startswith("prej_") and is_admin(uid) and has_perm(uid,"payments"):
            tuid=int(data[5:].split("_")[0]); sdel(call.message.chat.id,call.message.message_id)
            ssend(tuid,"❌ হোস্টিং অর্ডার বাতিল হয়েছে। সাপোর্টে যোগাযোগ করুন।"); audit(uid,"PLAN_REJECT",tuid); return

        # Feature toggles (stays open, just refreshes)
        toggles={"tog_maint":("maintenance_mode","🔧 Maintenance"),"tog_host":("feature_hosting","💻 Hosting"),
                 "tog_cbot":("feature_custom_bot","🤖 Custom Bot"),"tog_ref":("feature_referral","👥 Referral"),
                 "tog_wd":("feature_withdraw","💸 Withdraw")}
        if data in toggles and is_admin(uid):
            key,name=toggles[data]; nv="0" if gs(key)=="1" else "1"; ss(key,nv)
            audit(uid,f"TOGGLE_{key}",details=nv)
            try: bot.edit_message_reply_markup(call.message.chat.id,call.message.message_id,reply_markup=feature_toggle_inline())
            except: pass
            return

        # User actions
        if data=="ai_ban" and is_admin(uid):
            user_state[uid]="adm_ban"; sdel(call.message.chat.id,call.message.message_id)
            bot.send_message(uid,"🚫 Ban করার ইউজার আইডি দিন:",reply_markup=cancel_only_kb("bn")); return
        if data=="ai_unban" and is_admin(uid):
            user_state[uid]="adm_unban"; sdel(call.message.chat.id,call.message.message_id)
            bot.send_message(uid,"✅ Unban করার ইউজার আইডি দিন:",reply_markup=cancel_only_kb("bn")); return

        if data.startswith("ai_ban_") and is_admin(uid):
            tuid=int(data[len("ai_ban_"):]); conn=get_conn()
            try: conn.execute("UPDATE users SET is_banned=1 WHERE user_id=?",(tuid,)); conn.commit()
            finally: conn.close()
            audit(uid,"BAN",tuid); sdel(call.message.chat.id,call.message.message_id)
            bot.send_message(uid,f"🚫 ব্যান হয়েছে: {tuid}"); ssend(tuid,"🚫 আপনাকে ব্যান করা হয়েছে।"); return
        if data.startswith("ai_unban_") and is_admin(uid):
            tuid=int(data[len("ai_unban_"):]); conn=get_conn()
            try: conn.execute("UPDATE users SET is_banned=0 WHERE user_id=?",(tuid,)); conn.commit()
            finally: conn.close()
            audit(uid,"UNBAN",tuid); sdel(call.message.chat.id,call.message.message_id)
            bot.send_message(uid,f"✅ আনব্যান হয়েছে: {tuid}"); ssend(tuid,"✅ আপনার ব্যান তুলে নেওয়া হয়েছে।"); return

        if data.startswith("pm_toggle_") and is_admin(uid):
            tuid=int(data[len("pm_toggle_"):]); r=get_user(tuid)
            if not r: return
            nv=0 if r["is_premium"] else 1; conn=get_conn()
            try: conn.execute("UPDATE users SET is_premium=? WHERE user_id=?",(nv,tuid)); conn.commit()
            finally: conn.close()
            audit(uid,"SET_PREMIUM",tuid,str(nv)); sdel(call.message.chat.id,call.message.message_id)
            label="⭐ প্রিমিয়াম দেওয়া হয়েছে!" if nv else "👤 প্রিমিয়াম সরানো হয়েছে।"
            bot.send_message(uid,f"{label} {tuid}")
            ssend(tuid,"⭐ আপনাকে প্রিমিয়াম করা হয়েছে!" if nv else "👤 আপনার প্রিমিয়াম বাতিল হয়েছে।"); return

        if data.startswith("addbal_") and is_admin(uid):
            tuid=int(data[len("addbal_"):]); user_state[uid]=f"adm_addbal_amt_{tuid}"
            sdel(call.message.chat.id,call.message.message_id)
            bot.send_message(uid,f"💵 {tuid} কে কত BDT দেবেন?",reply_markup=cancel_only_kb("bn")); return

        if data.startswith("dm_") and is_admin(uid) and not data.startswith("dm_msg_"):
            tuid=int(data[len("dm_"):]); user_state[uid]=f"adm_dm_msg_{tuid}"
            sdel(call.message.chat.id,call.message.message_id)
            bot.send_message(uid,f"✍️ {tuid} কে বার্তা লিখুন:",reply_markup=cancel_only_kb("bn")); return

        # Plan management
        if data.startswith("editplan_") and is_admin(uid):
            key=data[len("editplan_"):]; plan=get_plan(key)
            if plan:
                user_state[uid]=f"adm_editplan_{key}"
                sdel(call.message.chat.id,call.message.message_id)
                bot.send_message(uid,f"✏️ `{key}` এর নতুন তথ্য লিখুন:\nFormat: `নাম|মূল্য|দিন`\nবর্তমান: {plan['name']}|{int(plan['price'])}|{plan['days']}",
                                 reply_markup=cancel_only_kb("bn"))
            return
        if data=="addplan" and is_admin(uid):
            user_state[uid]="adm_addplan_key"; sdel(call.message.chat.id,call.message.message_id)
            bot.send_message(uid,"🔑 নতুন প্ল্যানের key লিখুন (e.g. weekly):",reply_markup=cancel_only_kb("bn")); return
        if data=="delplan" and is_admin(uid):
            plans=get_all_plans()
            if not plans: bot.send_message(uid,"ℹ️ কোনো প্ল্যান নেই।"); return
            txt="🗑️ মুছতে plan_key লিখুন:\n\n"
            for k,p in plans.items(): txt+=f"🔑 `{k}` — {p['name']}\n"
            user_state[uid]="adm_delplan"; sdel(call.message.chat.id,call.message.message_id)
            bot.send_message(uid,txt,reply_markup=cancel_only_kb("bn")); return

        # Limit settings
        limit_map={"editlimit_mindep":"💳 নতুন সর্বনিম্ন ডিপোজিট (BDT):","editlimit_minwd":"💸 নতুন সর্বনিম্ন উইথড্র (BDT):",
                   "editlimit_wdcharge":"💳 নতুন উইথড্র চার্জ (BDT):","editlimit_maxwd":"📅 দৈনিক সর্বোচ্চ উইথড্র সংখ্যা:",
                   "editlimit_refbonus":"🎁 নতুন রেফারেল বোনাস (BDT):","editlimit_checkin":"📅 নতুন চেক-ইন বোনাস (BDT):",
                   "editlimit_bkash":"📱 নতুন Bkash নম্বর:","editlimit_nagad":"📱 নতুন Nagad নম্বর:","editlimit_usdt":"💱 নতুন USDT ওয়ালেট:"}
        if data in limit_map and is_admin(uid):
            user_state[uid]=f"adm_editlimit_{data[len('editlimit_'):]}"
            sdel(call.message.chat.id,call.message.message_id)
            bot.send_message(uid,limit_map[data],reply_markup=cancel_only_kb("bn")); return

        # Payment rule (instructions) editing
        rule_map={"editrule_bkash":"✏️ নতুন Bkash নিয়ম লিখুন (একাধিক লাইন লেখা যাবে):",
                  "editrule_nagad":"✏️ নতুন Nagad নিয়ম লিখুন (একাধিক লাইন লেখা যাবে):",
                  "editrule_usdt":"✏️ নতুন USDT নিয়ম লিখুন (একাধিক লাইন লেখা যাবে):"}
        if data in rule_map and is_admin(uid):
            user_state[uid]=f"adm_editrule_{data[len('editrule_'):]}"
            sdel(call.message.chat.id,call.message.message_id)
            bot.send_message(uid,rule_map[data],reply_markup=cancel_only_kb("bn")); return

        # Targeted broadcast
        if data.startswith("tbc_") and is_admin(uid):
            target=data[4:]; sdel(call.message.chat.id,call.message.message_id)
            if target=="userid":
                user_state[uid]="tbc_userid_input"
                bot.send_message(uid,"🎯 ইউজার আইডি দিন:",reply_markup=cancel_only_kb("bn")); return
            labels={"all":"All Users 👥","premium":"Premium ⭐","balance":"Has Balance 💰","new":"New (7d) 🆕"}
            user_state[uid]=f"tbc_msg_{target}"
            bot.send_message(uid,f"✍️ {labels.get(target,target)} কে ব্রডকাস্ট মেসেজ লিখুন:",reply_markup=cancel_only_kb("bn")); return

        # Broadcast type
        if data=="bc_text" and is_admin(uid):
            user_state[uid]="adm_broadcast"; sdel(call.message.chat.id,call.message.message_id)
            bot.send_message(uid,"📝 ব্রডকাস্ট মেসেজ লিখুন:",reply_markup=cancel_only_kb("bn")); return
        if data=="bc_photo" and is_admin(uid):
            user_state[uid]="adm_broadcast_photo"; sdel(call.message.chat.id,call.message.message_id)
            bot.send_message(uid,"📸 ফটো পাঠান (ক্যাপশনসহ বা ছাড়া):",reply_markup=cancel_only_kb("bn")); return
        if data=="bc_video" and is_admin(uid):
            user_state[uid]="adm_broadcast_video"; sdel(call.message.chat.id,call.message.message_id)
            bot.send_message(uid,"🎬 ভিডিও পাঠান:",reply_markup=cancel_only_kb("bn")); return
        if data=="bc_doc" and is_admin(uid):
            user_state[uid]="adm_broadcast_doc"; sdel(call.message.chat.id,call.message.message_id)
            bot.send_message(uid,"📄 ডকুমেন্ট পাঠান:",reply_markup=cancel_only_kb("bn")); return
    except Exception as e:
        logger.error(f"handle_callback error: {e}", exc_info=True)
        try:
            bot.send_message(call.from_user.id,"❌ একটি সমস্যা হয়েছে। আবার চেষ্টা করুন।")
        except Exception:
            pass

# ════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ════════════════════════════════════════════════════════════
def _do_ban(admin_uid,text,ban):
    try:
        target=int(text.strip()); conn=get_conn()
        try: conn.execute("UPDATE users SET is_banned=? WHERE user_id=?",(1 if ban else 0,target)); conn.commit()
        finally: conn.close()
        audit(admin_uid,"BAN" if ban else "UNBAN",target)
        label="🚫 ব্যান হয়েছে" if ban else "✅ আনব্যান হয়েছে"
        bot.send_message(admin_uid,f"{label}: {target}",reply_markup=admin_user_kb())
        ssend(target,"🚫 আপনাকে ব্যান করা হয়েছে।" if ban else "✅ আপনার ব্যান তুলে নেওয়া হয়েছে।")
    except ValueError:
        bot.send_message(admin_uid,"❌ সঠিক ইউজার আইডি দিন।",reply_markup=admin_user_kb())

def _do_checkin(uid,lang):
    today=datetime.now().strftime("%Y-%m-%d"); row=get_user(uid)
    last=row["last_checkin"] or "" if row else ""
    if last.startswith(today):
        bot.send_message(uid,"✅ আজকে চেক-ইন হয়ে গেছে! আগামীকাল আবার আসুন।",reply_markup=referral_kb(lang)); return
    bonus=float(gs("daily_checkin_bonus",str(DAILY_CHECKIN))); conn=get_conn()
    try:
        conn.execute("UPDATE users SET last_checkin=?,balance=balance+? WHERE user_id=?",
                     (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),bonus,uid))
        conn.execute("INSERT INTO transaction_logs (user_id,tx_type,amount,note,created_at) VALUES (?,?,?,?,?)",
                     (uid,"credit",bonus,"daily checkin",datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    finally: conn.close()
    bal=get_balance(uid)
    bot.send_message(uid,f"🎉 দৈনিক চেক-ইন সম্পন্ন!\n+{int(bonus)} BDT যোগ হয়েছে!\n💰 ব্যালেন্স: {round(bal,2)} BDT\n\n⏰ আগামীকাল আবার আসুন!",
                     reply_markup=referral_kb(lang))

def _send_profile(uid,lang):
    row=get_user(uid)
    if not row: return
    conn=get_conn()
    try:
        bots=conn.execute("SELECT COUNT(*) as c FROM subscriptions WHERE user_id=? AND status='active' AND expiry_date>=?",
                          (uid,datetime.now().strftime("%Y-%m-%d"))).fetchone()["c"]
        total_dep=conn.execute("SELECT COALESCE(SUM(amount),0) as s FROM transaction_logs WHERE user_id=? AND tx_type='credit'",(uid,)).fetchone()["s"]
        total_wd=conn.execute("SELECT COALESCE(SUM(amount),0) as s FROM transaction_logs WHERE user_id=? AND tx_type='debit'",(uid,)).fetchone()["s"]
    finally: conn.close()
    status="⭐ প্রিমিয়াম" if row["is_premium"] else "👤 সাধারণ"
    role_tag=f" | 👑 {row['role']}" if row["role"]!="user" else ""
    txt=(f"👤 *আপনার প্রোফাইল*\n\n🆔 আইডি: `{uid}`\n📛 নাম: {row['name']}\n🏅 স্ট্যাটাস: {status}{role_tag}\n"
         f"💰 ব্যালেন্স: {round(float(row['balance']),2)} BDT\n🤖 সক্রিয় বট: {bots}\n"
         f"👥 রেফারেল: {row['referral_count']} | আয়: {round(float(row['total_earned']),2)} BDT\n"
         f"💳 মোট ডিপোজিট: {round(float(total_dep),2)} BDT\n💸 মোট উইথড্র: {round(float(total_wd),2)} BDT\n"
         f"🌐 ভাষা: {'বাংলা' if row['language']=='bn' else 'English'}\n"
         f"📅 যোগদান: {str(row['joined_at'])[:10] if row['joined_at'] else '-'}")
    bot.send_message(uid,txt,reply_markup=support_kb(lang) if lang else None)

def _send_tx_history(uid,lang):
    conn=get_conn()
    try:
        rows=conn.execute("SELECT tx_type,amount,note,created_at FROM transaction_logs WHERE user_id=? ORDER BY id DESC LIMIT 10",(uid,)).fetchall()
    finally: conn.close()
    if not rows:
        bot.send_message(uid,"📋 কোনো লেনদেন নেই।",reply_markup=payment_kb(lang)); return
    txt="📊 *শেষ ১০টি লেনদেন:*\n\n"
    for r in rows:
        icon="🟢 +" if r["tx_type"]=="credit" else "🔴 -"
        txt+=f"{icon}{int(r['amount'])} BDT — {r['note']} | {str(r['created_at'])[:10]}\n"
    bot.send_message(uid,txt,reply_markup=payment_kb(lang))

def _send_referral(uid,lang):
    row=get_user(uid); me=bot.get_me(); link=f"https://t.me/{me.username}?start=ref_{uid}"
    bonus=float(gs("referral_bonus",str(REFERRAL_BONUS))); ci=float(gs("daily_checkin_bonus",str(DAILY_CHECKIN)))
    txt=(f"👥 *রেফারেল ও আয় প্যানেল*\n\n🔗 আপনার রেফারেল লিংক:\n`{link}`\n\n_(লিংকে ট্যাপ করলে কপি হয়ে যাবে)_\n\n"
         f"👥 মোট রেফারেল: {row['referral_count'] if row else 0}\n"
         f"💰 মোট আয়: {round(float(row['total_earned']) if row else 0,2)} BDT\n\n"
         f"🎁 প্রতি রেফারেল: {int(bonus)} BDT\n📅 দৈনিক চেক-ইন: {int(ci)} BDT\n\n"
         f"✨ লিংক শেয়ার করুন — প্রতি সাইনআপে {int(bonus)} BDT আয় করুন!")
    bot.send_message(uid,txt,reply_markup=referral_kb(lang))

def _send_my_bots(uid,lang):
    conn=get_conn()
    try: rows=conn.execute("SELECT * FROM subscriptions WHERE user_id=? ORDER BY id DESC",(uid,)).fetchall()
    finally: conn.close()
    if not rows:
        bot.send_message(uid,"🤖 আপনার কোনো সক্রিয় বট নেই।\n'নতুন বট হোস্ট' থেকে শুরু করুন।",reply_markup=bot_services_kb(lang)); return
    now=datetime.now().date()
    for b in rows:
        try:
            exp=datetime.strptime(b["expiry_date"],"%Y-%m-%d").date(); days=(exp-now).days; active=days>=0
        except: exp=None; days=-1; active=False
        plan=get_plan(b["plan"]) or {}; pname=plan.get("name",b["plan"]) if plan else b["plan"]
        ar_txt="✅ চালু" if b["auto_renew"] else "⏹️ বন্ধ"
        status="✅ সক্রিয়" if active else "❌ মেয়াদোত্তীর্ণ"
        exp_str=exp.strftime("%d/%m/%Y") if exp else "-"
        txt=(f"🤖 *{b['bot_name']}*\n📦 প্ল্যান: {pname}\n📊 স্ট্যাটাস: {status}\n"
             f"⏰ মেয়াদ: {exp_str} ({days} দিন বাকি)\n🚀 অটো-নবায়ন: {ar_txt}")
        user_state[f"{uid}_renew_target"]=str(b["id"])
        bot.send_message(uid,txt,reply_markup=renew_kb(lang))

def _do_renew(uid,lang,sub_id):
    conn=get_conn()
    try: row=conn.execute("SELECT * FROM subscriptions WHERE id=? AND user_id=?",(sub_id,uid)).fetchone()
    finally: conn.close()
    if not row: bot.send_message(uid,"❌ বট পাওয়া যায়নি।",reply_markup=main_kb(lang)); return
    plan=get_plan(row["plan"])
    if not plan: bot.send_message(uid,"❌ প্ল্যান পাওয়া যায়নি।",reply_markup=main_kb(lang)); return
    ok=deduct_bal(uid,plan["price"],f"renew {row['plan']}")
    if ok:
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"); conn=get_conn()
        try:
            base=datetime.strptime(row["expiry_date"],"%Y-%m-%d") if row["expiry_date"] else datetime.now()
            base=max(base,datetime.now()); expiry=(base+timedelta(days=plan["days"])).strftime("%Y-%m-%d")
            conn.execute("UPDATE subscriptions SET status='active',expiry_date=? WHERE id=?",(expiry,sub_id))
            conn.execute("INSERT INTO subscription_history (user_id,plan,price,expiry,action,created_at) VALUES (?,?,?,?,?,?)",
                         (uid,row["plan"],plan["price"],expiry,"renew",now)); conn.commit()
        finally: conn.close()
        audit(uid,"RENEW",uid,f"{row['plan']} {expiry}")
        bot.send_message(uid,f"🎉 নবায়ন সফল!\n📦 {plan['name']}\n📅 নতুন মেয়াদ: {expiry}\n💳 খরচ: {int(plan['price'])} BDT | 💰 ব্যালেন্স: {round(get_balance(uid),2)} BDT",
                         reply_markup=main_kb(lang))
    else:
        bot.send_message(uid,f"❌ অপর্যাপ্ত ব্যালেন্স!\n📉 প্রয়োজন: {int(plan['price'])} BDT | 💰 আছে: {round(get_balance(uid),2)} BDT",reply_markup=main_kb(lang))

def _toggle_autorenew(uid,lang,sub_id):
    conn=get_conn()
    try:
        r=conn.execute("SELECT auto_renew FROM subscriptions WHERE id=? AND user_id=?",(sub_id,uid)).fetchone()
        if not r: bot.send_message(uid,"❌ বট পাওয়া যায়নি।",reply_markup=main_kb(lang)); conn.close(); return
        nv=0 if r["auto_renew"] else 1
        conn.execute("UPDATE subscriptions SET auto_renew=? WHERE id=?",(nv,sub_id)); conn.commit()
    finally: conn.close()
    bot.send_message(uid,"🚀 অটো-নবায়ন চালু হয়েছে!" if nv else "⏹️ অটো-নবায়ন বন্ধ করা হয়েছে।",reply_markup=main_kb(lang))

def _buy_plan(uid,lang,plan_key):
    plan=get_plan(plan_key)
    if not plan: bot.send_message(uid,"❌ প্ল্যান পাওয়া যায়নি।",reply_markup=bot_services_kb(lang)); return
    bal=get_balance(uid); bal_status="✅ পর্যাপ্ত" if bal>=plan["price"] else "❌ অপর্যাপ্ত"
    conn=get_conn()
    try:
        row=conn.execute("SELECT id FROM hosting_requests WHERE user_id=? AND status='accepted' ORDER BY id DESC LIMIT 1",(uid,)).fetchone()
        req_id=row[0] if row else 0
    finally: conn.close()
    notify_staff("payments",f"📦 প্ল্যান অর্ডার!\n👤 ইউজার: {uid}\n📋 {plan['name']}\n💵 {int(plan['price'])} BDT\n"
          f"💰 ব্যালেন্স: {round(bal,2)} BDT | {bal_status}",
          markup_builder=lambda: plan_confirm_inline(uid,plan_key,req_id))
    bot.send_message(uid,f"📤 {plan['name']} অর্ডার রিভিউয়ের জন্য পাঠানো হয়েছে।\n✅ অনুমোদিত হলে {int(plan['price'])} BDT কাটা হবে।",
                     reply_markup=bot_services_kb(lang))

def _send_sub_history(uid,lang):
    conn=get_conn()
    try: rows=conn.execute("SELECT plan,price,expiry,action,created_at FROM subscription_history WHERE user_id=? ORDER BY id DESC LIMIT 15",(uid,)).fetchall()
    finally: conn.close()
    if not rows: bot.send_message(uid,"📭 কোনো সাবস্ক্রিপশন ইতিহাস নেই।",reply_markup=payment_kb(lang)); return
    txt="📅 *সাবস্ক্রিপশন ইতিহাস:*\n\n"
    for r in rows:
        plan=get_plan(r["plan"]) or {}; pname=plan.get("name",r["plan"])
        txt+=f"📦 {pname} | {r['action']} | {int(r['price'])} BDT | 📅 {r['expiry'][:10]} | {str(r['created_at'])[:10]}\n"
    bot.send_message(uid,txt,reply_markup=payment_kb(lang))

def _apply_coupon(uid,lang,code):
    code=code.strip().upper(); now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"); conn=get_conn()
    try:
        cpn=conn.execute("SELECT * FROM coupons WHERE code=? AND is_active=1",(code,)).fetchone()
        if not cpn: bot.send_message(uid,"❌ অবৈধ বা মেয়াদোত্তীর্ণ কুপন কোড।",reply_markup=payment_kb(lang)); return
        if cpn["expiry"] and cpn["expiry"]<now[:10]:
            bot.send_message(uid,"❌ কুপনের মেয়াদ শেষ।",reply_markup=payment_kb(lang)); return
        if cpn["used_count"]>=cpn["max_uses"]:
            bot.send_message(uid,"❌ কুপনের ব্যবহার সীমা শেষ।",reply_markup=payment_kb(lang)); return
        used=conn.execute("SELECT id FROM coupon_uses WHERE coupon_id=? AND user_id=?",(cpn["id"],uid)).fetchone()
        if used: bot.send_message(uid,"⚠️ আপনি এই কুপন আগেই ব্যবহার করেছেন।",reply_markup=payment_kb(lang)); return
        conn.execute("UPDATE coupons SET used_count=used_count+1 WHERE id=?",(cpn["id"],))
        conn.execute("INSERT INTO coupon_uses (coupon_id,user_id,date) VALUES (?,?,?)",(cpn["id"],uid,now)); conn.commit()
    finally: conn.close()
    add_bal(uid,cpn["amount"],f"coupon:{code}")
    bot.send_message(uid,f"🎉 কুপন সফল!\n+{int(cpn['amount'])} BDT যোগ হয়েছে!\n💰 ব্যালেন্স: {round(get_balance(uid),2)} BDT",reply_markup=payment_kb(lang))

# ── ADMIN HELPERS ──
def send_admin_profile(admin_uid,row):
    if not row: bot.send_message(admin_uid,"❌ ইউজার পাওয়া যায়নি।"); return
    uid=row["user_id"]; conn=get_conn()
    try:
        bots=conn.execute("SELECT COUNT(*) as c FROM subscriptions WHERE user_id=? AND status='active'",(uid,)).fetchone()["c"]
        payments=conn.execute("SELECT COUNT(*) as c FROM payment_requests WHERE user_id=?",(uid,)).fetchone()["c"]
        wds=conn.execute("SELECT COUNT(*) as c FROM withdraw_requests WHERE user_id=?",(uid,)).fetchone()["c"]
    finally: conn.close()
    banned="🚫 ব্যান" if row["is_banned"] else "✅ সক্রিয়"
    premium="⭐ প্রিমিয়াম" if row["is_premium"] else "👤 সাধারণ"
    txt=(f"👤 *{row['name']}* (`{uid}`)\n📱 @{row['username'] or 'N/A'}\n💰 ব্যালেন্স: {round(float(row['balance']),2)} BDT\n"
         f"🏅 {banned} | {premium} | 👑 {row['role']}\n🤖 বট: {bots} | 💳 পেমেন্ট: {payments} | 💸 উইথড্র: {wds}\n"
         f"👥 রেফারেল: {row['referral_count']} | আয়: {round(float(row['total_earned']),2)} BDT\n"
         f"📅 যোগদান: {str(row['joined_at'])[:10] if row['joined_at'] else '-'}\n"
         f"🕐 শেষ সক্রিয়: {str(row['last_active'])[:10] if row['last_active'] else '-'}")
    bot.send_message(admin_uid,txt,reply_markup=profile_action_inline(uid,row["is_banned"],row["is_premium"]))

def _send_stats(uid):
    conn=get_conn()
    try:
        total=conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
        banned=conn.execute("SELECT COUNT(*) as c FROM users WHERE is_banned=1").fetchone()["c"]
        premium=conn.execute("SELECT COUNT(*) as c FROM users WHERE is_premium=1").fetchone()["c"]
        active_bots=conn.execute("SELECT COUNT(*) as c FROM subscriptions WHERE status='active' AND expiry_date>=?",
                                 (datetime.now().strftime("%Y-%m-%d"),)).fetchone()["c"]
        pend_pay=conn.execute("SELECT COUNT(*) as c FROM payment_requests WHERE status='pending'").fetchone()["c"]
        pend_wd=conn.execute("SELECT COUNT(*) as c FROM withdraw_requests WHERE status='pending'").fetchone()["c"]
        open_tix=conn.execute("SELECT COUNT(*) as c FROM support_tickets WHERE status='open'").fetchone()["c"]
    finally: conn.close()
    bot.send_message(uid,f"📊 *বট স্ট্যাটস*\n\n👥 মোট ইউজার: {total}\n🚫 ব্যান: {banned} | ⭐ প্রিমিয়াম: {premium}\n"
                     f"🤖 সক্রিয় বট: {active_bots}\n\n⏳ পেন্ডিং পেমেন্ট: {pend_pay}\n⏳ পেন্ডিং উইথড্র: {pend_wd}\n"
                     f"🎫 খোলা টিকেট: {open_tix}\n\n⏰ আপটাইম: {uptime()}")

def _send_analytics(uid):
    conn=get_conn()
    try:
        total_dep=conn.execute("SELECT COALESCE(SUM(amount),0) as s FROM transaction_logs WHERE tx_type='credit'").fetchone()["s"]
        total_wd=conn.execute("SELECT COALESCE(SUM(amount),0) as s FROM transaction_logs WHERE tx_type='debit'").fetchone()["s"]
        today=datetime.now().strftime("%Y-%m-%d")
        new_today=conn.execute("SELECT COUNT(*) as c FROM users WHERE joined_at LIKE ?",(today+"%",)).fetchone()["c"]
        new_week=conn.execute("SELECT COUNT(*) as c FROM users WHERE joined_at>=?",((datetime.now()-timedelta(days=7)).strftime("%Y-%m-%d"),)).fetchone()["c"]
        top_users=conn.execute("SELECT name,user_id,balance FROM users WHERE is_banned=0 ORDER BY balance DESC LIMIT 5").fetchall()
        active_plans=conn.execute("SELECT COUNT(*) as c FROM subscriptions WHERE status='active' AND expiry_date>=?",(today,)).fetchone()["c"]
    finally: conn.close()
    txt=(f"📈 *অ্যাডভান্সড অ্যানালিটিক্স*\n\n💰 মোট ডিপোজিট: {round(float(total_dep),2)} BDT\n"
         f"💸 মোট উইথড্র: {round(float(total_wd),2)} BDT\n💹 নেট ব্যালেন্স: {round(float(total_dep)-float(total_wd),2)} BDT\n\n"
         f"🆕 আজকের নতুন: {new_today}\n📅 সাপ্তাহিক নতুন: {new_week}\n🤖 সক্রিয় প্ল্যান: {active_plans}\n\n🏆 *টপ ৫ ব্যালেন্স:*\n")
    for i,r in enumerate(top_users,1):
        txt+=f"{i}. {r['name']} (`{r['user_id']}`) — {round(float(r['balance']),2)} BDT\n"
    bot.send_message(uid,txt)

def _send_audit(uid):
    conn=get_conn()
    try: rows=conn.execute("SELECT admin_id,action,target_id,details,created_at FROM audit_logs ORDER BY id DESC LIMIT 20").fetchall()
    finally: conn.close()
    if not rows: bot.send_message(uid,"📋 কোনো অডিট লগ নেই।"); return
    txt="📋 *অডিট লগ (শেষ ২০টি):*\n\n"
    for r in rows: txt+=f"👑{r['admin_id']} → {r['action']} | 👤{r['target_id']} | {r['details'][:30]} | {str(r['created_at'])[:16]}\n"
    bot.send_message(uid,txt)

def _export_users(uid):
    conn=get_conn()
    try: rows=conn.execute("SELECT user_id,name,username,balance,is_banned,is_premium,role,joined_at FROM users").fetchall()
    finally: conn.close()
    output=io.StringIO(); writer=csv.writer(output)
    writer.writerow(["user_id","name","username","balance","is_banned","is_premium","role","joined_at"])
    for r in rows: writer.writerow([r["user_id"],r["name"],r["username"],r["balance"],r["is_banned"],r["is_premium"],r["role"],r["joined_at"]])
    data=output.getvalue().encode("utf-8"); buf=io.BytesIO(data); buf.name=f"users_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    bot.send_document(uid,buf,caption=f"📤 ইউজার এক্সপোর্ট — {len(rows)} জন"); audit(uid,"EXPORT_USERS")

def _send_user_list(uid):
    conn=get_conn()
    try: rows=conn.execute("SELECT user_id,name,balance,is_banned,is_premium,role FROM users ORDER BY user_id DESC").fetchall()
    finally: conn.close()
    if not rows: bot.send_message(uid,"👥 কোনো ইউজার নেই।"); return
    role_label={"admin":"👑 Admin","moderator":"🛡️ Moderator","user":"👤 User"}
    chunk=f"👥 *সকল ইউজার* (মোট {len(rows)} জন)\n_আইডিতে ট্যাপ করলে কপি হবে_\n\n"
    for r in rows:
        icon="🚫" if r["is_banned"] else ("⭐" if r["is_premium"] else "👤")
        line=(f"{icon} *{r['name'] or 'N/A'}*\n"
              f"🆔 `{r['user_id']}` | {role_label.get(r['role'],'👤 User')} | {round(float(r['balance']),2)} BDT\n\n")
        if len(chunk)+len(line)>3800:
            bot.send_message(uid,chunk); chunk=""
        chunk+=line
    if chunk: bot.send_message(uid,chunk)

def _send_referral_leaderboard(uid):
    conn=get_conn()
    try: rows=conn.execute("SELECT name,user_id,referral_count,total_earned FROM users WHERE referral_count>0 ORDER BY referral_count DESC LIMIT 10").fetchall()
    finally: conn.close()
    if not rows: bot.send_message(uid,"🏆 কোনো রেফারেল নেই।"); return
    txt="🏆 *রেফারেল লিডারবোর্ড:*\n\n"; medals=["🥇","🥈","🥉"]+["🏅"]*7
    for i,r in enumerate(rows): txt+=f"{medals[i]} {r['name']} — {r['referral_count']} রেফারেল | {round(float(r['total_earned']),2)} BDT\n"
    bot.send_message(uid,txt)

def _send_pending_payments(uid):
    conn=get_conn()
    try: rows=conn.execute("SELECT p.*,u.name,u.username FROM payment_requests p LEFT JOIN users u ON p.user_id=u.user_id WHERE p.status='pending' ORDER BY p.id DESC").fetchall()
    finally: conn.close()
    if not rows: bot.send_message(uid,"✅ কোনো পেন্ডিং পেমেন্ট নেই।"); return
    for r in rows:
        uname=f"@{r['username']}" if r['username'] else str(r['user_id'])
        amt_num=r['amount'].split()[0]
        bot.send_message(uid,f"💳 *পেমেন্ট #{r['id']}*\n👤 {r['name']} ({r['user_id']}) {uname}\n"
                         f"💵 {r['amount']} | {r['method'].upper()}\n🔑 TxID: `{r['txid']}`\n📅 {str(r['created_at'])[:16]}",
                         reply_markup=pay_action_inline(r['user_id'],r['id'],amt_num))

def _send_pending_withdrawals(uid):
    conn=get_conn()
    try: rows=conn.execute("SELECT w.*,u.name,u.username FROM withdraw_requests w LEFT JOIN users u ON w.user_id=u.user_id WHERE w.status='pending' ORDER BY w.id DESC").fetchall()
    finally: conn.close()
    if not rows: bot.send_message(uid,"✅ কোনো পেন্ডিং উইথড্র নেই।"); return
    for r in rows:
        uname=f"@{r['username']}" if r['username'] else str(r['user_id'])
        charge=float(gs("withdraw_charge",str(WITHDRAW_CHARGE))); net=float(r['amount'])-charge
        bot.send_message(uid,f"💸 *উইথড্র #{r['id']}*\n👤 {r['name']} ({r['user_id']}) {uname}\n"
                         f"📱 {r['method'].upper()} | `{r['number']}`\n💵 {int(r['amount'])} BDT | চার্জ: {int(charge)} | পাবেন: {int(net)} BDT\n"
                         f"📅 {str(r['created_at'])[:16]}",
                         reply_markup=wd_action_inline(r['user_id'],r['id'],int(r['amount'])))

def _send_pending_hosting(uid):
    conn=get_conn()
    try: rows=conn.execute("SELECT h.*,u.name,u.username FROM hosting_requests h LEFT JOIN users u ON h.user_id=u.user_id WHERE h.status='pending_review' ORDER BY h.id DESC").fetchall()
    finally: conn.close()
    if not rows: bot.send_message(uid,"✅ কোনো পেন্ডিং হোস্টিং নেই।"); return
    for r in rows:
        uname=f"@{r['username']}" if r['username'] else str(r['user_id'])
        bot.send_message(uid,f"📁 *হোস্টিং ফাইল #{r['id']}*\n👤 {r['name']} ({r['user_id']}) {uname}\n📅 {str(r['created_at'])[:16]}",
                         reply_markup=file_review_inline(r['user_id'],r['id']))

def _send_pending_custom(uid):
    conn=get_conn()
    try: rows=conn.execute("SELECT c.*,u.name,u.username FROM custom_bot_orders c LEFT JOIN users u ON c.user_id=u.user_id WHERE c.status='pending' ORDER BY c.id DESC").fetchall()
    finally: conn.close()
    if not rows: bot.send_message(uid,"✅ কোনো পেন্ডিং কাস্টম অর্ডার নেই।"); return
    for r in rows:
        uname=f"@{r['username']}" if r['username'] else str(r['user_id'])
        bot.send_message(uid,f"🤖 *কাস্টম অর্ডার #{r['id']}*\n👤 {r['name']} ({r['user_id']}) {uname}\n\n📝 {r['description']}\n📅 {str(r['created_at'])[:16]}",
                         reply_markup=custom_order_inline(r['user_id'],r['id']))

def _send_support_tickets(uid):
    conn=get_conn()
    try: rows=conn.execute("SELECT t.*,u.name,u.username FROM support_tickets t LEFT JOIN users u ON t.user_id=u.user_id WHERE t.status='open' ORDER BY t.id DESC LIMIT 10").fetchall()
    finally: conn.close()
    if not rows: bot.send_message(uid,"✅ কোনো খোলা টিকেট নেই।"); return
    for r in rows:
        uname=f"@{r['username']}" if r['username'] else str(r['user_id'])
        msg_txt=f"🎫 *Ticket #{r['id']}*\n👤 {r['name']} ({r['user_id']}) {uname}\n\n{r['message']}\n📅 {str(r['created_at'])[:16]}"
        if r['photo_id']:
            try: bot.send_photo(uid,r['photo_id'],caption=msg_txt,reply_markup=support_reply_inline(r['user_id'],r['id'])); continue
            except: pass
        bot.send_message(uid,msg_txt,reply_markup=support_reply_inline(r['user_id'],r['id']))

def _send_coupon_panel(uid):
    conn=get_conn()
    try: rows=conn.execute("SELECT * FROM coupons ORDER BY id DESC LIMIT 10").fetchall()
    finally: conn.close()
    kb=types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("➕ নতুন কুপন তৈরি",callback_data="coupon_create"))
    kb.add(types.InlineKeyboardButton("❌ Close",callback_data="close_panel"))
    if not rows: bot.send_message(uid,"🎁 কোনো কুপন নেই।",reply_markup=kb); return
    txt="🎁 *কুপন লিস্ট:*\n\n"
    for r in rows:
        status="✅" if r["is_active"] else "❌"
        txt+=f"{status} `{r['code']}` — {int(r['amount'])} BDT | {r['used_count']}/{r['max_uses']} ব্যবহার\n"
    bot.send_message(uid,txt,reply_markup=kb)

def do_broadcast(admin_uid,text,target,media_type,media_id):
    conn=get_conn()
    try:
        now=datetime.now()
        if target=="premium": users=conn.execute("SELECT user_id FROM users WHERE is_banned=0 AND is_premium=1").fetchall()
        elif target=="balance": users=conn.execute("SELECT user_id FROM users WHERE is_banned=0 AND balance>0").fetchall()
        elif target=="new":
            since=(now-timedelta(days=7)).strftime("%Y-%m-%d")
            users=conn.execute("SELECT user_id FROM users WHERE is_banned=0 AND joined_at>=?",(since,)).fetchall()
        else: users=conn.execute("SELECT user_id FROM users WHERE is_banned=0").fetchall()
    finally: conn.close()
    ok=fail=0
    for u in users:
        try:
            if media_type=="photo": bot.send_photo(u["user_id"],media_id,caption=text)
            elif media_type=="video": bot.send_video(u["user_id"],media_id,caption=text)
            elif media_type=="document": bot.send_document(u["user_id"],media_id,caption=text)
            else: bot.send_message(u["user_id"],text)
            ok+=1
        except: fail+=1
        time.sleep(0.05)
    audit(admin_uid,"BROADCAST",details=f"ok:{ok} fail:{fail} target:{target}")
    ssend(admin_uid,f"📢 ব্রডকাস্ট সম্পন্ন!\n✅ পাঠানো: {ok}\n❌ ব্যর্থ: {fail}\n👥 মোট: {ok+fail}")

# ════════════════════════════════════════════════════════════
# BACKGROUND RUNNER
# ════════════════════════════════════════════════════════════
def background_runner():
    while True:
        try:
            now=datetime.now(); today=now.strftime("%Y-%m-%d"); conn=get_conn()
            try:
                bots=conn.execute("SELECT * FROM subscriptions WHERE auto_renew=1 AND status='active'").fetchall()
                for b in bots:
                    try:
                        exp=datetime.strptime(b["expiry_date"],"%Y-%m-%d"); days=(exp.date()-now.date()).days
                    except: continue
                    if days<=1:
                        plan=get_plan(b["plan"])
                        if not plan: continue
                        ok=deduct_bal(b["user_id"],plan["price"],f"auto-renew {b['plan']}")
                        if ok:
                            new_exp=(exp+timedelta(days=plan["days"])).strftime("%Y-%m-%d")
                            conn.execute("UPDATE subscriptions SET expiry_date=? WHERE id=?",(new_exp,b["id"]))
                            conn.execute("INSERT INTO subscription_history (user_id,plan,price,expiry,action,created_at) VALUES (?,?,?,?,?,?)",
                                        (b["user_id"],b["plan"],plan["price"],new_exp,"auto-renew",now.strftime("%Y-%m-%d %H:%M:%S")))
                            conn.commit()
                            ssend(b["user_id"],f"🔄 অটো-নবায়ন সম্পন্ন!\n🤖 {b['bot_name']}\n📅 নতুন মেয়াদ: {new_exp}\n💳 কাটা: {int(plan['price'])} BDT")
                        else:
                            ssend(b["user_id"],f"⚠️ অটো-নবায়ন ব্যর্থ!\n🤖 {b['bot_name']}\nঅপর্যাপ্ত ব্যালেন্স। ম্যানুয়ালি নবায়ন করুন।")
                subs=conn.execute("SELECT * FROM subscriptions WHERE status='active'").fetchall()
                for b in subs:
                    try: exp=datetime.strptime(b["expiry_date"],"%Y-%m-%d"); days=(exp.date()-now.date()).days
                    except: continue
                    if days==3:
                        ssend(b["user_id"],f"⚠️ মেয়াদ শেষের সতর্কতা!\n🤖 {b['bot_name']}\n📅 মেয়াদ শেষ: {b['expiry_date']} ({days} দিন বাকি)\n\n🔄 'আমার বটগুলো' থেকে নবায়ন করুন!")
                conn.execute("UPDATE subscriptions SET status='expired' WHERE expiry_date<? AND status='active'",(today,))
                pending_bc=conn.execute("SELECT * FROM scheduled_broadcasts WHERE sent=0 AND send_at<=?",(now.strftime("%Y-%m-%d %H:%M:%S"),)).fetchall()
                for bc in pending_bc:
                    conn.execute("UPDATE scheduled_broadcasts SET sent=1 WHERE id=?",(bc["id"],)); conn.commit()
                    threading.Thread(target=do_broadcast,args=(SUPER_ADMIN_ID,bc["message"],"all",None,None),daemon=True).start()
                conn.commit()
            finally: conn.close()
        except Exception as e:
            logger.error(f"background_runner: {e}")
        time.sleep(3600)

# ════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════
if __name__=="__main__":
    print("="*55)
    print("  🚀 HostBot BD v10.0 - Starting...")
    print(f"  📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*55)
    init_db(); migrate_db()
    threading.Thread(target=background_runner,daemon=True).start()
    logger.info("✅ Bot started.")
    print("\n✅ Bot is running! Press Ctrl+C to stop.\n")
    while True:
        try:
            bot.infinity_polling(timeout=30,long_polling_timeout=20)
        except KeyboardInterrupt:
            print("\n🛑 বট বন্ধ করা হয়েছে।"); sys.exit(0)
        except Exception as e:
            logger.error(f"Polling error: {e}"); time.sleep(5)
