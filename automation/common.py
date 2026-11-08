"""Shared helpers: secrets, Supabase storage, Telegram, Sheet settings, queue state. Never prints secret values."""
import json, os, time
from datetime import datetime, timedelta, timezone
import requests

IST = timezone(timedelta(hours=5, minutes=30))
GRAPH = "https://graph.facebook.com/v25.0"
PAGE_ID = os.environ.get("FB_PAGE_ID", "1513958021798147")
def env(k):
    v = os.environ.get(k, "").strip()
    if not v: raise RuntimeError(f"secret {k} is empty")
    return v
def now(): return datetime.now(IST)

# ---------- Supabase storage (public bucket 'reels') ----------
def sb_headers(ct="application/octet-stream"):
    k = env("SUPABASE_KEY"); return {"apikey": k, "Authorization": f"Bearer {k}", "x-upsert": "true", "Content-Type": ct}
def sb_upload(path, data, ct):
    for attempt in range(5):                     # Supabase/Cloudflare sometimes answers 5xx for a moment: wait and retry
        try: r = requests.post(f"{env('SUPABASE_URL').rstrip('/')}/storage/v1/object/reels/{path}", headers=sb_headers(ct), data=data, timeout=300)
        except requests.RequestException as e: r = None; err = str(e)[:150]
        if r is not None and r.ok: break
        if r is not None: err = f"HTTP {r.status_code} {r.text[:80]}"
        if r is not None and r.status_code < 500: break
        time.sleep(15 * (attempt + 1))
    if r is None or not r.ok: raise RuntimeError(f"Supabase upload {path}: {err}")
    return sb_public(path)
def sb_public(path): return f"{env('SUPABASE_URL').rstrip('/')}/storage/v1/object/public/reels/{path}"
def sb_delete(paths):
    requests.delete(f"{env('SUPABASE_URL').rstrip('/')}/storage/v1/object/reels", headers=sb_headers("application/json"), json={"prefixes": paths}, timeout=60)

STATE = "state/queue.json"
def load_state():
    r = requests.get(f"{env('SUPABASE_URL').rstrip('/')}/storage/v1/object/reels/{STATE}", headers=sb_headers(), timeout=60)
    if r.status_code in (400, 404) or not r.ok: return {"items": {}, "tg_offset": 0}
    return r.json()
def save_state(st, only=None):
    """Merge with the newest copy first, so two jobs saving at once never undo each other's changes.
    only=[ids]: this job only ADDED those items (deliver, daily posts) -> everything else is kept as it is now."""
    cur = load_state()
    if only is not None:
        cur["items"].update({k: st["items"][k] for k in only}); st = cur
    else:
        for k, v in cur["items"].items(): st["items"].setdefault(k, v)
        st["tg_offset"] = max(st.get("tg_offset", 0), cur.get("tg_offset", 0))
    sb_upload(STATE, json.dumps(st, ensure_ascii=False, indent=1).encode(), "application/json")

# ---------- Telegram ----------
def tg(method, **kw):
    files = kw.pop("files", None)
    r = requests.post(f"https://api.telegram.org/bot{env('TELEGRAM_TOKEN')}/{method}", data=kw if files else None, json=None if files else kw, files=files, timeout=120)
    j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"ok": False}
    if not j.get("ok"): print(f"telegram {method} failed: {str(j.get('description'))[:150]}")
    return j.get("result")
def tg_msg(text, **kw): return tg("sendMessage", chat_id=env("TELEGRAM_CHAT_ID"), text=text, **kw)

# ---------- Sheet settings (optional; defaults if the Sheet can't be read) ----------
DEFAULTS = {"live_mode": "false", "reels_per_day": "2", "reel_times": "12:30,18:30,20:30", "voice_rate": "+30%"}
def settings():
    s = dict(DEFAULTS)
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        cr = Credentials.from_service_account_info(json.loads(env("GOOGLE_SA_JSON")), scopes=["https://www.googleapis.com/auth/spreadsheets"])
        sh = gspread.authorize(cr).open_by_key(env("SHEET_ID"))
        for row in sh.worksheet("settings").get_all_records():
            if str(row.get("key", "")).strip(): s[str(row["key"]).strip()] = str(row.get("value", "")).strip()
    except Exception as e:
        print("settings: using defaults,", type(e).__name__, str(e)[:120])
    return s
def is_live(s): return str(s.get("live_mode", "")).strip().lower() in ("true", "yes", "1", "on")
def log_posted(row):
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        cr = Credentials.from_service_account_info(json.loads(env("GOOGLE_SA_JSON")), scopes=["https://www.googleapis.com/auth/spreadsheets"])
        gspread.authorize(cr).open_by_key(env("SHEET_ID")).worksheet("posted").append_row(row, value_input_option="USER_ENTERED")
    except Exception as e:
        print("posted log skipped:", type(e).__name__, str(e)[:120])
