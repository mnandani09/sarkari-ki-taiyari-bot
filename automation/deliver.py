"""After the Kaggle render: upload Reels to Supabase, add them to the approval queue, send Telegram previews
with Approve / Skip buttons, keep the reusable Madam Ji clips, mark scripts as rendered."""
import glob, json, os, shutil, sys
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
    url = sb_upload(f"{day}/{rid}.mp4", open(mp4, "rb").read(), "video/mp4")
    cover = mp4[:-4] + "_cover.jpg"
    cover_url = sb_upload(f"{day}/{rid}_cover.jpg", open(cover, "rb").read(), "image/jpeg") if os.path.exists(cover) else None
    note = f"⚠️ still photo used for: {', '.join(qc.get('fallbacks', []))}" if qc.get("fallbacks") else "✅ quality checks passed"
    msg = tg("sendVideo", chat_id=env("TELEGRAM_CHAT_ID"), video=url, supports_streaming=True,
             caption=f"🎬 Reel ready: {job['topic']}\n{qc.get('seconds','?')} s · {note}\n\nApprove to post on Instagram + Facebook at the next slot.",
             reply_markup={"inline_keyboard": [[{"text": "✅ Approve", "callback_data": f"ok:{rid}"}, {"text": "⏭ Skip", "callback_data": f"skip:{rid}"}]]})
    st["items"][rid] = {"id": rid, "kind": "reel", "topic": job["topic"], "video_url": url, "cover_url": cover_url,
                        "caption": job["caption"], "first_comment": job.get("first_comment", ""), "status": "waiting",
                        "tg_msg": (msg or {}).get("message_id"), "made": now().isoformat(), "qc": qc}
    rendered.append(rid); sent += 1
for f in glob.glob(f"{OUT}/**/face_cache/*.mp4", recursive=True):
    os.makedirs("render/face_cache", exist_ok=True); shutil.copy(f, "render/face_cache/")
save_state(st)
json.dump(sorted(set(rendered)), open("content/rendered.json", "w"), indent=1)
shutil.rmtree("jobs/pending", ignore_errors=True); os.makedirs("jobs/pending"); open("jobs/pending/.keep", "w").close()
if not sent: tg_msg("⚠️ Tonight's render finished but no Reel came out. Check the Nightly render run in GitHub Actions.")
print(f"{sent} Reel(s) sent to Telegram")
