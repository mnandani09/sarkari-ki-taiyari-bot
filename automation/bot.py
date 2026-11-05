"""Runs every 10 minutes: reads your Telegram taps, schedules approved Reels into the next free slot,
and publishes due Reels to Instagram + the Facebook Page (only when live_mode is true in the Sheet)."""
import time
from datetime import datetime, timedelta
from common import *

st = load_state(); s = settings(); live = is_live(s); changed = False
times = sorted(v.strip() for k, v in s.items() if k.startswith("slot_reel_") and ":" in str(v)) or [t.strip() for t in s.get("reel_times", DEFAULTS["reel_times"]).split(",") if t.strip()]

def next_slot():
    taken = {it.get("slot") for it in st["items"].values() if it["status"] in ("approved", "posted")}
    d = now()
    for day in range(0, 14):
        base = (d + timedelta(days=day)).date()
        for t in times:
            h, m = map(int, t.split(":"))
            slot = datetime(base.year, base.month, base.day, h, m, tzinfo=IST)
            if slot > d + timedelta(minutes=5) and slot.isoformat() not in taken: return slot.isoformat()
    return (d + timedelta(hours=1)).isoformat()
def nice(iso): return datetime.fromisoformat(iso).strftime("%a %d %b, %I:%M %p")

# 1) Telegram taps
ups = tg("getUpdates", offset=st.get("tg_offset", 0), timeout=0, allowed_updates=["callback_query", "message"]) or []
for u in ups:
    st["tg_offset"] = u["update_id"] + 1; changed = True
    cq = u.get("callback_query")
    if cq and str(cq["message"]["chat"]["id"]) == env("TELEGRAM_CHAT_ID"):
        act, rid = cq["data"].split(":", 1); it = st["items"].get(rid)
        if not it: tg("answerCallbackQuery", callback_query_id=cq["id"], text="Not found"); continue
        if act == "ok" and it["status"] in ("waiting", "skipped"):
            it["status"], it["slot"] = "approved", next_slot()
            txt = f"✅ Approved: posts {nice(it['slot'])}" + ("" if live else " (live_mode is OFF in the Sheet, so it will NOT post yet)")
        elif act == "skip" and it["status"] in ("waiting", "approved"):
            it["status"] = "skipped"; it.pop("slot", None); txt = "⏭ Skipped. It won't be posted."
        else:
            txt = f"Already {it['status']}"
        tg("answerCallbackQuery", callback_query_id=cq["id"], text=txt[:190])
        tg("editMessageReplyMarkup", chat_id=env("TELEGRAM_CHAT_ID"), message_id=cq["message"]["message_id"],
           reply_markup={"inline_keyboard": [[{"text": txt[:60], "callback_data": "noop:x"}]] if act != "noop" else []})
        if act != "noop": tg_msg(f"{txt}\n{it['topic']}")
    m = u.get("message")
    if m and str(m["chat"]["id"]) == env("TELEGRAM_CHAT_ID") and m.get("text", "").strip().lower() in ("/status", "status"):
        lines = [f"{it['status']:>9} · {it['topic'][:40]}" + (f" · {nice(it['slot'])}" if it.get("slot") and it["status"] == "approved" else "") for it in sorted(st["items"].values(), key=lambda x: x["made"])[-10:]]
        tg_msg("Queue (live_mode " + ("ON" if live else "OFF") + "):\n" + "\n".join(lines or ["empty"]))

# 2) publish due items
def ig_reel(it):
    ig, tok = env("IG_USER_ID"), env("IG_TOKEN")
    r = requests.post(f"{GRAPH}/{ig}/media", data={"media_type": "REELS", "video_url": it["video_url"], "caption": it["caption"],
                      "share_to_feed": "true", "access_token": tok}, timeout=60).json()
    if "id" not in r: raise RuntimeError(f"Instagram container: {str(r.get('error', r))[:200]}")
    cid = r["id"]
    for _ in range(40):
        time.sleep(15)
        sc = requests.get(f"{GRAPH}/{cid}", params={"fields": "status_code,status", "access_token": tok}, timeout=60).json()
        if sc.get("status_code") == "FINISHED": break
        if sc.get("status_code") == "ERROR": raise RuntimeError(f"Instagram processing: {str(sc.get('status'))[:200]}")
    p = requests.post(f"{GRAPH}/{ig}/media_publish", data={"creation_id": cid, "access_token": tok}, timeout=60).json()
    if "id" not in p: raise RuntimeError(f"Instagram publish: {str(p.get('error', p))[:200]}")
    mid = p["id"]
    if it.get("first_comment"):
        requests.post(f"{GRAPH}/{mid}/comments", data={"message": it["first_comment"], "access_token": tok}, timeout=60)
    link = requests.get(f"{GRAPH}/{mid}", params={"fields": "permalink", "access_token": tok}, timeout=60).json().get("permalink", "")
    return mid, link
def fb_video(it):
    pages = requests.get(f"{GRAPH}/me/accounts", params={"fields": "id,access_token", "access_token": env("IG_TOKEN")}, timeout=60).json()
    pt = next((p["access_token"] for p in pages.get("data", []) if p["id"] == PAGE_ID), None)
    if not pt: raise RuntimeError("Facebook Page token not found (check permissions)")
    r = requests.post(f"{GRAPH}/{PAGE_ID}/videos", data={"file_url": it["video_url"], "description": it["caption"], "access_token": pt}, timeout=300).json()
    if "id" not in r: raise RuntimeError(f"Facebook: {str(r.get('error', r))[:200]}")
    return r["id"], f"https://www.facebook.com/{PAGE_ID}/videos/{r['id']}"

for it in sorted(st["items"].values(), key=lambda x: x.get("slot", "")):
    if it["status"] != "approved" or datetime.fromisoformat(it["slot"]) > now(): continue
    if not live:
        if not it.get("dry_note"): tg_msg(f"🧪 Dry run: '{it['topic']}' would post now. Set live_mode to true in the Sheet's settings tab to post for real."); it["dry_note"] = True; changed = True
        continue
    res = {}
    for name, fn in (("instagram", ig_reel), ("facebook", fb_video)):
        if it.get(name): continue
        try: res[name] = fn(it); it[name] = res[name][1] or res[name][0]
        except Exception as e: res[name] = None; it.setdefault("errors", []).append(f"{name}: {str(e)[:200]}"); print(name, "failed:", str(e)[:200])
    changed = True
    if it.get("instagram") and it.get("facebook"): it["status"] = "posted"
    elif len(it.get("errors", [])) >= 6: it["status"] = "failed"
    ok = [f"{k}: {it[k]}" for k in ("instagram", "facebook") if it.get(k)]
    bad = [e for e in it.get("errors", [])[-2:]] if not (it.get("instagram") and it.get("facebook")) else []
    tg_msg(("🚀 Posted: " if it["status"] == "posted" else "⚠️ Partly posted: ") + it["topic"] + "\n" + "\n".join(ok + bad))
    if it.get("instagram"): log_posted([it["id"], now().strftime("%Y-%m-%d %H:%M"), "reel", it["topic"], "teaching", it.get("slot", ""), it["topic"], "", "", it.get("instagram", "")])
if changed: save_state(st)
print("done; live_mode", live)
