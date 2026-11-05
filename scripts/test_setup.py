"""Setup test for the sarkari.ki.taiyari automation.

Checks every service with the GitHub secrets and sends one report to Telegram.
It never prints secret values, and it posts nothing to Instagram.
"""
import json
import os
import time
from datetime import datetime, timezone, timedelta

import requests

IST = timezone(timedelta(hours=5, minutes=30))
TIMEOUT = 30
GRAPH = "https://graph.facebook.com/v25.0"


def env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"secret {name} is empty")
    return value


def short_error(resp):
    """Return a short error text from an HTTP response without any secrets."""
    try:
        data = resp.json()
        if isinstance(data, dict):
            err = data.get("error", data)
            if isinstance(err, dict):
                msg = err.get("message") or err.get("error") or json.dumps(err)[:150]
            else:
                msg = str(err)
            return f"HTTP {resp.status_code}: {str(msg)[:150]}"
    except ValueError:
        pass
    return f"HTTP {resp.status_code}: {resp.text[:150]}"


def check_gemini():
    r = requests.get(
        "https://generativelanguage.googleapis.com/v1beta/models",
        params={"key": env("GEMINI_API_KEY"), "pageSize": 5},
        timeout=TIMEOUT,
    )
    if r.ok:
        return True, f"{len(r.json().get('models', []))}+ models available"
    return False, short_error(r)


def check_groq():
    r = requests.get(
        "https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {env('GROQ_API_KEY')}"},
        timeout=TIMEOUT,
    )
    if r.ok:
        ids = [m["id"] for m in r.json().get("data", [])]
        whisper = any("whisper" in i for i in ids)
        return True, f"{len(ids)} models, Whisper {'available' if whisper else 'NOT found'}"
    return False, short_error(r)


def check_youtube():
    r = requests.get(
        "https://www.googleapis.com/youtube/v3/search",
        params={
            "part": "snippet",
            "q": "SSC CGL",
            "type": "video",
            "videoDuration": "short",
            "regionCode": "IN",
            "maxResults": 1,
            "key": env("YOUTUBE_API_KEY"),
        },
        timeout=TIMEOUT,
    )
    if r.ok:
        items = r.json().get("items", [])
        title = items[0]["snippet"]["title"][:50] if items else "no results"
        return True, f"search works ({title})"
    return False, short_error(r)


def check_kaggle():
    user, key = env("KAGGLE_USERNAME"), env("KAGGLE_KEY")
    url = "https://www.kaggle.com/api/v1/kernels/list"
    params = {"user": user, "pageSize": 5}
    # Old-style key from kaggle.json: username + 32-character key.
    r = requests.get(url, params=params, auth=(user, key), timeout=TIMEOUT)
    if r.ok:
        return True, "login works (kaggle.json key)"
    # Newer Kaggle API token: sent as a Bearer token.
    r2 = requests.get(url, params=params, headers={"Authorization": f"Bearer {key}"}, timeout=TIMEOUT)
    if r2.ok:
        return True, "login works (new-style API token)"
    # Describe the shape of the value without revealing it.
    if key.startswith("{"):
        hint = "KAGGLE_KEY holds the whole kaggle.json; paste only the value after \"key\""
    elif key.startswith('"') or key.endswith('"'):
        hint = "KAGGLE_KEY has quote marks around it; remove them"
    elif len(key) == 32 and all(ch in "0123456789abcdef" for ch in key):
        hint = "key looks like a kaggle.json key; check KAGGLE_USERNAME matches your Kaggle username exactly, or create a new token"
    else:
        hint = f"key is {len(key)} characters and was rejected both ways; create a new token in Kaggle Settings"
    return False, f"{short_error(r)}; {hint}"


def check_sheet():
    import gspread
    from google.oauth2.service_account import Credentials

    info = json.loads(env("GOOGLE_SA_JSON"))
    creds = Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    sheet = gspread.authorize(creds).open_by_key(env("SHEET_ID"))
    tabs = [ws.title for ws in sheet.worksheets()]
    needed = ["topics", "queue", "posted", "stats", "settings", "weights"]
    missing = [t for t in needed if t not in tabs]
    settings = {row["key"]: row["value"] for row in sheet.worksheet("settings").get_all_records()}
    live = settings.get("live_mode", "?")
    if missing:
        return False, f"opened '{sheet.title}' but tabs missing: {', '.join(missing)}"
    return True, f"'{sheet.title}' read OK, live_mode = {live}"


def check_supabase():
    base = env("SUPABASE_URL").rstrip("/")
    key = env("SUPABASE_KEY")
    stamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")
    body = f"hello from GitHub, {stamp}".encode()
    path = "test/hello.txt"
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "x-upsert": "true",
               "Content-Type": "text/plain"}
    r = requests.post(f"{base}/storage/v1/object/reels/{path}", headers=headers, data=body, timeout=TIMEOUT)
    if not r.ok:
        headers.pop("Authorization")
        r = requests.post(f"{base}/storage/v1/object/reels/{path}", headers=headers, data=body, timeout=TIMEOUT)
    if not r.ok:
        return False, "upload failed, " + short_error(r)
    public = f"{base}/storage/v1/object/public/reels/{path}"
    g = requests.get(public, timeout=TIMEOUT)
    if g.ok and g.content == body:
        return True, "upload works and the reels bucket is public"
    return False, f"uploaded, but the public link gives HTTP {g.status_code} (is the reels bucket Public?)"


def check_instagram():
    ig = env("IG_USER_ID")
    token = env("IG_TOKEN")
    r = requests.get(f"{GRAPH}/{ig}", params={"fields": "id,username,followers_count",
                                               "access_token": token}, timeout=TIMEOUT)
    if not r.ok:
        return False, short_error(r)
    who = r.json()
    lim = requests.get(f"{GRAPH}/{ig}/content_publishing_limit",
                       params={"fields": "quota_usage,config", "access_token": token}, timeout=TIMEOUT)
    publish = "publishing allowed" if lim.ok else "publish check failed: " + short_error(lim)
    return lim.ok, f"@{who.get('username')} ({who.get('followers_count', '?')} followers), {publish}"


def check_claude():
    try:
        with open("claude_check.txt", encoding="utf-8") as fh:
            out = fh.read().strip()
    except FileNotFoundError:
        return False, "Claude step did not run"
    if "CLAUDE_FAILED" in out or "OK" not in out.upper():
        text = out.replace("CLAUDE_FAILED", "").strip().splitlines()
        return False, (text[-1][:150] if text else "no reply")
    return True, "headless Claude Code replied"


CHECKS = [
    ("Claude Code", check_claude),
    ("Gemini", check_gemini),
    ("Groq", check_groq),
    ("YouTube", check_youtube),
    ("Kaggle", check_kaggle),
    ("Google Sheet", check_sheet),
    ("Supabase", check_supabase),
    ("Instagram", check_instagram),
]


def send_telegram(text):
    r = requests.post(
        f"https://api.telegram.org/bot{env('TELEGRAM_TOKEN')}/sendMessage",
        json={"chat_id": env("TELEGRAM_CHAT_ID"), "text": text},
        timeout=TIMEOUT,
    )
    return r.ok, (short_error(r) if not r.ok else "sent")


def main():
    lines, all_ok = [], True
    for name, fn in CHECKS:
        try:
            ok, detail = fn()
        except Exception as exc:  # report and keep going
            ok, detail = False, f"{type(exc).__name__}: {str(exc)[:150]}"
        all_ok &= ok
        line = f"{'✅' if ok else '❌'} {name}: {detail}"
        lines.append(line)
        print(line)
        time.sleep(0.5)

    stamp = datetime.now(IST).strftime("%d %b %Y, %H:%M IST")
    header = "Hello from GitHub 👋 Setup test for sarkari.ki.taiyari"
    footer = "All checks passed. Ready for Day 3." if all_ok else "Some checks failed. Share only the ❌ lines with Claude."
    ok, detail = send_telegram("\n".join([header, stamp, ""] + lines + ["", footer]))
    print(f"{'✅' if ok else '❌'} Telegram: {detail}")
    if not (ok and all_ok):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
