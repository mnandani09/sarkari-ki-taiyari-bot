"""After the Kaggle render: upload Reels to Supabase, add them to the approval queue, send Telegram previews
with Approve / Skip buttons, keep the reusable Madam Ji clips, mark scripts as rendered."""
import glob, json, os, shutil, sys
from datetime import datetime
from common import *
OUT = sys.argv[1]
st = load_state(); s = settings(); rendered = json.load(open("content/rendered.json")) if os.path.exists("content/rendered.json") else []
jobs = {json.load(open(f, encoding="utf-8"))["id"]: json.load(open(f, encoding="utf-8")) for f in glob.glob("jobs/pending/*.json")}
sent = 0
for mp4 in sorted(glob.glob(f"{OUT}/**/*.mp4", recursive=True)):
    rid = os.path.basename(mp4)[:-4]
    if rid not in jobs: continue
    job = jobs[rid]; qc = {}
    qf = mp4[:-4] + "_qc.json"
    if os.path.exists(qf): qc = json.load(open(qf))
    day = rid[:10]
    stamp = now().strftime("%H%M%S")              # new name every render, so no app can show an old cached copy
    url = sb_upload(f"{day}/{rid}-{stamp}.mp4", open(mp4, "rb").read(), "video/mp4")
    cover = mp4[:-4] + "_cover.jpg"
    try: cover_url = sb_upload(f"{day}/{rid}-{stamp}_cover.jpg", open(cover, "rb").read(), "image/jpeg") if os.path.exists(cover) else None
    except Exception as e: print("cover skipped:", str(e)[:150]); cover_url = None
    note = f"⚠️ still photo used for: {', '.join(qc.get('fallbacks', []))}" if qc.get("fallbacks") else "✅ quality checks passed"
    pdate = job.get("post_date"); order = int(job.get("order", 0))
    when = datetime.fromisoformat(pdate).strftime("%a %d %b") if pdate else "the next free slot"
    msg = tg("sendVideo", chat_id=env("TELEGRAM_CHAT_ID"), video=url, supports_streaming=True,
             caption=f"🎬 Reel {order + 1} for {when}: {job['topic']}\n{qc.get('seconds','?')} s · {note}\n\nApprove or Skip by midnight tonight. Approved Reels post on {when} at their scheduled time.",
             reply_markup={"inline_keyboard": [[{"text": "✅ Approve", "callback_data": f"ok:{rid}:{stamp}"}, {"text": "⏭ Skip", "callback_data": f"skip:{rid}:{stamp}"}]]})
    st["items"][rid] = {"id": rid, "kind": "reel", "topic": job["topic"], "video_url": url, "cover_url": cover_url,
                        "caption": job["caption"], "first_comment": job.get("first_comment", ""), "status": "waiting",
                        "tg_msg": (msg or {}).get("message_id"), "stamp": stamp, "made": now().isoformat(), "qc": qc, "post_date": pdate, "order": order}
    rendered.append(rid); sent += 1
for f in glob.glob(f"{OUT}/**/face_cache/*.mp4", recursive=True):
    os.makedirs("render/face_cache", exist_ok=True); shutil.copy(f, "render/face_cache/")
save_state(st)
json.dump(sorted(set(rendered)), open("content/rendered.json", "w"), indent=1)
pdates = sorted({j.get("post_date") for j in jobs.values() if j.get("post_date")})
if sent and pdates:
    old = json.load(open("content/rendered_dates.json")) if os.path.exists("content/rendered_dates.json") else []
    json.dump(sorted(set(old) | set(pdates)), open("content/rendered_dates.json", "w"), indent=1)
    tg_msg(f"📋 {sent} Reel(s) for {datetime.fromisoformat(pdates[0]).strftime('%A %d %b')} are above. Please Approve or Skip each one by midnight tonight.")
shutil.rmtree("jobs/pending", ignore_errors=True); os.makedirs("jobs/pending"); open("jobs/pending/.keep", "w").close()
if not sent: tg_msg("⚠️ Tonight's render finished but no Reel came out. Check the Nightly render run in GitHub Actions.")
print(f"{sent} Reel(s) sent to Telegram")
