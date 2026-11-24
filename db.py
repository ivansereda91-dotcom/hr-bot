"""SQLite-хранилище бота. Каждое обращение открывает и закрывает соединение (без утечек)."""
import json
import sqlite3
from contextlib import contextmanager

DB_PATH = "hr-bot.db"


def set_path(path):
    global DB_PATH
    DB_PATH = path


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS allowed (id INTEGER PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                mode TEXT DEFAULT 'menu',
                digest_time TEXT DEFAULT '08:00',
                last_digest TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS offers (
                id TEXT PRIMARY KEY,
                user_id INTEGER,
                title TEXT, company TEXT, place TEXT, url TEXT,
                score INTEGER, summary TEXT,
                status TEXT DEFAULT 'new',
                created TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, chan TEXT, role TEXT, content TEXT
            );
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, at TEXT, text TEXT, sent INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, text TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
            """
        )


# --- доступ ---
def allow(ids):
    with conn() as c:
        c.executemany("INSERT OR IGNORE INTO allowed(id) VALUES (?)", [(int(i),) for i in ids])


def is_allowed(uid):
    with conn() as c:
        return c.execute("SELECT 1 FROM allowed WHERE id=?", (uid,)).fetchone() is not None


def allowed_ids():
    with conn() as c:
        return [r[0] for r in c.execute("SELECT id FROM allowed")]


# --- пользователи ---
def user(uid):
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO users(id) VALUES (?)", (uid,))
        return dict(c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())


def set_user(uid, **kw):
    user(uid)
    with conn() as c:
        for k, v in kw.items():
            c.execute(f"UPDATE users SET {k}=? WHERE id=?", (v, uid))


# --- вакансии ---
def offer_known(uid, oid):
    with conn() as c:
        return c.execute("SELECT 1 FROM offers WHERE id=? AND user_id=?", (oid, uid)).fetchone() is not None


def add_offer(uid, o):
    with conn() as c:
        c.execute(
            "INSERT OR IGNORE INTO offers(id,user_id,title,company,place,url,score,summary) VALUES (?,?,?,?,?,?,?,?)",
            (o["id"], uid, o["title"], o["company"], o["place"], o["url"], o.get("score", 0), o.get("summary", "")),
        )


def set_offer_status(uid, oid, status):
    with conn() as c:
        c.execute("UPDATE offers SET status=? WHERE id=? AND user_id=?", (status, oid, uid))


def saved_offers(uid):
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM offers WHERE user_id=? AND status='saved' ORDER BY created DESC LIMIT 30", (uid,))]


# --- история диалогов (чат-режимы) ---
def add_msg(uid, chan, role, content):
    with conn() as c:
        c.execute("INSERT INTO history(user_id,chan,role,content) VALUES (?,?,?,?)", (uid, chan, role, content))


def get_msgs(uid, chan, limit=20):
    with conn() as c:
        rows = c.execute(
            "SELECT role,content FROM history WHERE user_id=? AND chan=? ORDER BY id DESC LIMIT ?",
            (uid, chan, limit)).fetchall()
    msgs = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
    while msgs and msgs[0]["role"] != "user":  # API требует начинать с user
        msgs.pop(0)
    return msgs


def clear_msgs(uid, chan):
    with conn() as c:
        c.execute("DELETE FROM history WHERE user_id=? AND chan=?", (uid, chan))


# --- напоминания и заметки ---
def add_reminder(uid, at, text):
    with conn() as c:
        c.execute("INSERT INTO reminders(user_id,at,text) VALUES (?,?,?)", (uid, at, text))


def due_reminders(now_iso):
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM reminders WHERE sent=0 AND at<=?", (now_iso,))]


def mark_sent(rid):
    with conn() as c:
        c.execute("UPDATE reminders SET sent=1 WHERE id=?", (rid,))


def pending_reminders(uid):
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM reminders WHERE user_id=? AND sent=0 ORDER BY at", (uid,))]


def del_reminder(uid, rid):
    with conn() as c:
        c.execute("DELETE FROM reminders WHERE id=? AND user_id=?", (rid, uid))


def add_note(uid, text):
    with conn() as c:
        c.execute("INSERT INTO notes(user_id,text) VALUES (?,?)", (uid, text))


def notes(uid):
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM notes WHERE user_id=? ORDER BY id DESC LIMIT 30", (uid,))]


def del_note(uid, nid):
    with conn() as c:
        c.execute("DELETE FROM notes WHERE id=? AND user_id=?", (nid, uid))


# --- kv ---
def kv_get(k, default=None):
    with conn() as c:
        r = c.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
    return json.loads(r[0]) if r else default


def kv_set(k, v):
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO kv(k,v) VALUES (?,?)", (k, json.dumps(v)))
