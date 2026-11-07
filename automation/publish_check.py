"""Safe end-to-end posting check. Posts NOTHING.
Instagram: creates a Reel container from an approved video (Instagram downloads and processes it) and waits for FINISHED,
then leaves it unpublished. Facebook: confirms the Page key and posting permissions. Reports to Telegram."""
import time
from common import *
st = load_state(); lines = []
it = next((x for x in sorted(st["items"].values(), key=lambda x: x.get("slot", "")) if x["status"] in ("approved", "waiting")), None)
ig, tok = env("IG_USER_ID"), env("IG_TOKEN")
try:
    who = requests.get(f"{GRAPH}/{ig}", params={"fields": "username", "access_token": tok}, timeout=60).json()
    lim = requests.get(f"{GRAPH}/{ig}/content_publishing_limit", params={"fields": "quota_usage,config", "access_token": tok}, timeout=60).json()
    lines.append(f"Instagram @{who.get('username')}: login OK, posts used in last 24 h: {(lim.get('data') or [{}])[0].get('quota_usage', '?')}")
    if it:
        r = requests.post(f"{GRAPH}/{ig}/media", data={"media_type": "REELS", "video_url": it["video_url"], "caption": it["caption"], "access_token": tok}, timeout=60).json()
        if "id" not in r: raise RuntimeError(str(r.get("error", r))[:200])
        status = "?"
        for _ in range(30):
            time.sleep(10)
            status = requests.get(f"{GRAPH}/{r['id']}", params={"fields": "status_code,status", "access_token": tok}, timeout=60).json()
            if status.get("status_code") in ("FINISHED", "ERROR"): break
        lines.append(f"Instagram test upload of '{it['topic']}': {status.get('status_code')} {status.get('status', '')[:80]} (not published)")
    else:
        lines.append("Instagram: no Reel in the queue to test with")
except Exception as e:
    lines.append(f"Instagram FAILED: {str(e)[:200]}")
try:
    pages = requests.get(f"{GRAPH}/me/accounts", params={"fields": "id,name,access_token,tasks", "access_token": tok}, timeout=60).json()
    pg = next((p for p in pages.get("data", []) if p["id"] == PAGE_ID), None)
    if not pg: raise RuntimeError("Page not found for this key")
    perms = requests.get(f"{GRAPH}/me/permissions", params={"access_token": tok}, timeout=60).json()
    granted = {p["permission"] for p in perms.get("data", []) if p.get("status") == "granted"}
    need = {"pages_manage_posts", "pages_read_engagement", "pages_show_list"}
    lines.append(f"Facebook Page '{pg['name']}': key OK, can post: {'CREATE_CONTENT' in pg.get('tasks', [])}, missing permissions: {sorted(need - granted) or 'none'}")
except Exception as e:
    lines.append(f"Facebook FAILED: {str(e)[:200]}")
msg = "🔎 Posting check (nothing was posted):\n" + "\n".join(lines)
print(msg); tg_msg(msg)
