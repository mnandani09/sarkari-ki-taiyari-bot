"""Runs every 10 minutes: reads your Telegram taps, schedules approved Reels into their day's slots (day-ahead),
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
def planned_slot(it):
    """Day-ahead: Reel 1, 2, 3 of a day go to slot_reel_1, 2, 3 on its post date (or the next free slot if that time has passed)."""
    if it.get("fixed_slot"): return it["fixed_slot"]          # carousel / post / Stories have their own time
    if not it.get("post_date"): return next_slot()
    taken = {x.get("slot") for x in st["items"].values() if x["status"] in ("approved", "posted") and x is not it}
    d = datetime.fromisoformat(it["post_date"]).date()
    for t in times[int(it.get("order", 0)) % len(times):] + times[:int(it.get("order", 0)) % len(times)]:
        h, m = map(int, t.split(":")); slot = datetime(d.year, d.month, d.day, h, m, tzinfo=IST)
        if slot > now() + timedelta(minutes=5) and slot.isoformat() not in taken: return slot.isoformat()
    return next_slot()

# 1) Telegram taps (every tap is logged, so a missing tap can never be invisible again)
wh = tg("getWebhookInfo") or {}
print(f"telegram: webhook {'SET' if wh.get('url') else 'none'}, waiting updates {wh.get('pending_update_count', '?')}, last error: {wh.get('last_error_message', '-')}")
if wh.get("url"):
    tg("deleteWebhook", drop_pending_updates=False)
    print("telegram: removed the webhook that was taking this bot's taps; GitHub reads them from now on")
    tg_msg("🔧 Your Telegram bot was connected to another service that was catching your Approve/Skip taps. It is now released, so taps work again.")
ups = tg("getUpdates", offset=st.get("tg_offset", 0), timeout=0, allowed_updates=[])   # [] = every update type (resets an old filter)
if ups is None: print("telegram: getUpdates FAILED (see the line above; 'Conflict' means another program is reading this bot)"); ups = []
print(f"telegram: {len(ups)} new update(s), offset {st.get('tg_offset', 0)}")
for u in ups:
    cq = u.get("callback_query"); m = u.get("message") or {}
    kind = [k for k in u if k != "update_id"]
    print(f"  update {u['update_id']} {kind}: " + (f"button {cq.get('data')}" if cq else f"message {str(m.get('text', ''))[:30]!r}"))
for u in ups:
    st["tg_offset"] = u["update_id"] + 1; changed = True
    cq = u.get("callback_query")
    me = env("TELEGRAM_CHAT_ID")
    if cq:
        ids = {str(cq.get("from", {}).get("id")), str(cq.get("message", {}).get("chat", {}).get("id"))}
        if me not in ids:
            print(f"  ignored: tap came from chat …{str(cq.get('message', {}).get('chat', {}).get('id'))[-4:]} / user …{str(cq.get('from', {}).get('id'))[-4:]}, expected …{me[-4:]}")
            tg("answerCallbackQuery", callback_query_id=cq["id"], text="Not allowed from this account."); continue
        if cq.get("data", "").startswith("test:"):
            tg("answerCallbackQuery", callback_query_id=cq["id"], text="✅ Taps work!"); tg_msg("✅ Tap received. Approve and Skip buttons will work."); continue
    if cq:
        parts = cq["data"].split(":"); act, rid = parts[0], parts[1] if len(parts) > 1 else ""
        grp = sorted([x for x in st["items"].values() if x.get("group", x["id"]) == rid], key=lambda x: x.get("fixed_slot") or x["id"])   # Stories: one tap = both
        it = grp[0] if grp else None
        if act == "noop": tg("answerCallbackQuery", callback_query_id=cq["id"]); continue
        if not it or len(parts) < 3 or parts[2] != it.get("stamp"):
            tg("answerCallbackQuery", callback_query_id=cq["id"], text="This is an old preview. Use the newest one."); continue
        if act == "ok" and it["status"] in ("waiting", "skipped"):
            for x in grp: x["status"], x["slot"] = "approved", planned_slot(x)
            txt = "✅ Approved: posts " + " and ".join(nice(x["slot"]) for x in grp) + ("" if live else " (live_mode is OFF in the Sheet, so it will NOT post yet)")
        elif act == "skip" and it["status"] in ("waiting", "approved"):
            for x in grp: x["status"] = "skipped"; x.pop("slot", None)
            txt = "⏭ Skipped. It won't be posted."
        else:
            txt = f"Already {it['status']}"
        tg("answerCallbackQuery", callback_query_id=cq["id"], text=txt[:190])
        tg("editMessageReplyMarkup", chat_id=env("TELEGRAM_CHAT_ID"), message_id=cq["message"]["message_id"],
           reply_markup={"inline_keyboard": [[{"text": txt[:60], "callback_data": "noop:x"}]] if act != "noop" else []})
        if act != "noop": tg_msg(f"{txt}\n{it['topic']}")
    m = u.get("message")
    if m and str(m["chat"]["id"]) == env("TELEGRAM_CHAT_ID") and m.get("text", "").strip().lower() in ("/test", "test"):
        tg_msg("Tap the button to test:", reply_markup={"inline_keyboard": [[{"text": "👆 Tap me", "callback_data": "test:1"}]]})
    if m and str(m["chat"]["id"]) == env("TELEGRAM_CHAT_ID") and m.get("text", "").strip().lower() in ("/status", "status"):
        lines = [f"{it['status']:>9} · {it['topic'][:40]}" + (f" · {nice(it['slot'])}" if it.get("slot") and it["status"] == "approved" else "") for it in sorted(st["items"].values(), key=lambda x: x["made"])[-10:]]
        tg_msg("Queue (live_mode " + ("ON" if live else "OFF") + "):\n" + "\n".join(lines or ["empty"]))

# 2) midnight deadline + 9 PM reminder (day-ahead approvals)
KIND = {"reel": "Reel", "carousel": "carousel", "post": "quiz post", "story": "Stories"}
told = set()
for it in st["items"].values():
    if it["status"] == "waiting" and it.get("post_date") and now() >= datetime.fromisoformat(it["post_date"]).replace(tzinfo=IST):
        it["status"] = "missed"; changed = True
        if it.get("group", it["id"]) not in told:
            told.add(it.get("group", it["id"])); tg_msg(f"⌛ Not approved by midnight, so this {KIND.get(it.get('kind'), 'Reel')} will not post: {it['topic']}")
tomorrow = (now() + timedelta(days=1)).date().isoformat()
pending = list({it.get("group", it["id"]): it for it in st["items"].values() if it["status"] == "waiting" and it.get("post_date") == tomorrow}.values())
if pending and now().hour >= 21 and st.get("reminded") != tomorrow:
    st["reminded"] = tomorrow; changed = True
    tg_msg(f"⏰ {len(pending)} item(s) for tomorrow still need Approve or Skip (deadline midnight): " + ", ".join(it["topic"] for it in pending))

# 3) publish due items
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
_pt = None
def page_token():
    global _pt
    if not _pt:
        pages = requests.get(f"{GRAPH}/me/accounts", params={"fields": "id,access_token", "access_token": env("IG_TOKEN")}, timeout=60).json()
        _pt = next((p["access_token"] for p in pages.get("data", []) if p["id"] == PAGE_ID), None)
        if not _pt: raise RuntimeError("Facebook Page token not found (check permissions)")
    return _pt
def ig_container(**fields):
    ig, tok = env("IG_USER_ID"), env("IG_TOKEN")
    r = requests.post(f"{GRAPH}/{ig}/media", data={**fields, "access_token": tok}, timeout=120).json()
    if "id" not in r: raise RuntimeError(f"Instagram container: {str(r.get('error', r))[:200]}")
    for _ in range(20):
        sc = requests.get(f"{GRAPH}/{r['id']}", params={"fields": "status_code,status", "access_token": tok}, timeout=60).json()
        if sc.get("status_code") == "FINISHED": return r["id"]
        if sc.get("status_code") == "ERROR": raise RuntimeError(f"Instagram processing: {str(sc.get('status'))[:200]}")
        time.sleep(5)
    return r["id"]
def ig_publish(cid, story=False):
    ig, tok = env("IG_USER_ID"), env("IG_TOKEN")
    p = requests.post(f"{GRAPH}/{ig}/media_publish", data={"creation_id": cid, "access_token": tok}, timeout=60).json()
    if "id" not in p: raise RuntimeError(f"Instagram publish: {str(p.get('error', p))[:200]}")
    link = "" if story else requests.get(f"{GRAPH}/{p['id']}", params={"fields": "permalink", "access_token": tok}, timeout=60).json().get("permalink", "")
    return p["id"], link or f"instagram story {p['id']}"
def ig_carousel(it):
    kids = [ig_container(image_url=u, is_carousel_item="true") for u in it["image_urls"]]
    return ig_publish(ig_container(media_type="CAROUSEL", children=",".join(kids), caption=it["caption"]))
def ig_photo(it): return ig_publish(ig_container(image_url=it["image_url"], caption=it["caption"]))
def ig_story(it): return ig_publish(ig_container(media_type="STORIES", image_url=it["image_url"]), story=True)
def fb_photo_id(url, published, caption=""):
    r = requests.post(f"{GRAPH}/{PAGE_ID}/photos", data={"url": url, "published": "true" if published else "false", "caption": caption,
                      "access_token": page_token()}, timeout=180).json()
    if "id" not in r: raise RuntimeError(f"Facebook photo: {str(r.get('error', r))[:200]}")
    return r
def fb_album(it):
    ids = [fb_photo_id(u, False)["id"] for u in it["image_urls"]]
    r = requests.post(f"{GRAPH}/{PAGE_ID}/feed", data={"message": it["caption"], "access_token": page_token(),
                      **{f"attached_media[{n}]": json.dumps({"media_fbid": i}) for n, i in enumerate(ids)}}, timeout=180).json()
    if "id" not in r: raise RuntimeError(f"Facebook post: {str(r.get('error', r))[:200]}")
    return r["id"], f"https://www.facebook.com/{r['id']}"
def fb_photo(it):
    r = fb_photo_id(it["image_url"], True, it["caption"]); pid = r.get("post_id", r["id"])
    return pid, f"https://www.facebook.com/{pid}"
def fb_story(it):
    pid = fb_photo_id(it["image_url"], False)["id"]
    r = requests.post(f"{GRAPH}/{PAGE_ID}/photo_stories", data={"photo_id": pid, "access_token": page_token()}, timeout=120).json()
    if not (r.get("success") or r.get("post_id") or r.get("id")): raise RuntimeError(f"Facebook story: {str(r.get('error', r))[:200]}")
    return r.get("post_id", pid), "facebook story"
def fb_video(it):
    pt = page_token()
    r = requests.post(f"{GRAPH}/{PAGE_ID}/videos", data={"file_url": it["video_url"], "description": it["caption"], "access_token": pt}, timeout=300).json()
    if "id" not in r: raise RuntimeError(f"Facebook: {str(r.get('error', r))[:200]}")
    return r["id"], f"https://www.facebook.com/{PAGE_ID}/videos/{r['id']}"

PUB = {"reel": (ig_reel, fb_video), "carousel": (ig_carousel, fb_album), "post": (ig_photo, fb_photo), "story": (ig_story, fb_story)}
for it in sorted(st["items"].values(), key=lambda x: x.get("slot", "")):
    if it["status"] != "approved" or datetime.fromisoformat(it["slot"]) > now(): continue
    if not live:
        if not it.get("dry_note"): tg_msg(f"🧪 Dry run: '{it['topic']}' would post now. Set live_mode to true in the Sheet's settings tab to post for real."); it["dry_note"] = True; changed = True
        continue
    before_ig = bool(it.get("instagram"))
    for name, fn in zip(("instagram", "facebook"), PUB.get(it.get("kind", "reel"), PUB["reel"])):
        if it.get(name): continue
        try: r = fn(it); it[name] = r[1] or r[0]; it[name + "_id"] = r[0]
        except Exception as e:
            it.setdefault("errors", []).append(f"{name}: {str(e)[:200]}"); print(name, "failed:", str(e)[:200])
            if name == "facebook" and it.get("kind") == "story": it["facebook"] = "skipped (Page Stories not available)"   # Instagram is what matters
    changed = True
    late = now() > datetime.fromisoformat(it["slot"]) + timedelta(hours=12)      # keep retrying for 12 h (e.g. while a Meta block is fixed)
    if it.get("instagram") and it.get("facebook"): it["status"] = "posted"
    elif late: it["status"] = "failed"
    ok = [f"{k}: {it[k]}" for k in ("instagram", "facebook") if it.get(k)]
    if it["status"] == "posted":
        tg_msg("🚀 Posted: " + it["topic"] + "\n" + "\n".join(ok))
    elif it["status"] == "failed":
        tg_msg("❌ Gave up posting after 12 hours: " + it["topic"] + "\n" + "\n".join(ok + it.get("errors", [])[-2:]))
    elif not it.get("alerted"):
        it["alerted"] = True
        tg_msg("⚠️ Couldn't post yet (retrying every 10 minutes for 12 hours): " + it["topic"] + "\n" + "\n".join(ok + it.get("errors", [])[-2:]))
    if it.get("instagram") and not before_ig:
        log_posted([it["id"], now().strftime("%Y-%m-%d %H:%M"), it.get("kind", "reel"), it["topic"], "teaching", it.get("slot", ""), it["topic"], "", "", it.get("instagram", "")])
# 4) quiz post: reveal the answer as a comment 3 hours after it went up
for it in st["items"].values():
    if it.get("answer_comment") and not it.get("answer_done") and it.get("slot") and it["status"] in ("posted", "failed") \
       and now() >= datetime.fromisoformat(it["slot"]) + timedelta(hours=3):
        it["answer_done"] = True; changed = True
        if it.get("instagram_id"):
            r = requests.post(f"{GRAPH}/{it['instagram_id']}/comments", data={"message": it["answer_comment"], "access_token": env("IG_TOKEN")}, timeout=60).json()
            print("answer comment instagram:", "ok" if "id" in r else str(r)[:150])
        if it.get("facebook_id"):
            try:
                r = requests.post(f"{GRAPH}/{it['facebook_id']}/comments", data={"message": it["answer_comment"], "access_token": page_token()}, timeout=60).json()
                print("answer comment facebook:", "ok" if "id" in r else str(r)[:150])
            except Exception as e: print("answer comment facebook failed:", str(e)[:150])
if changed: save_state(st)
print("done; live_mode", live, "| queue:", {k: v["status"] for k, v in st["items"].items()})
