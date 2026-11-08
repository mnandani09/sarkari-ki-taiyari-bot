"""Supabase storage report + cleanup (runs at the end of every Nightly render, or by hand).
Reports total size, Reel/image sizes and the oldest files. Deletes nothing unless the Sheet's settings tab has
cleanup_days (e.g. 7): then files older than that are deleted, except any still waiting or approved to post.
Posted Reels stay on Instagram and Facebook; Supabase only needs each file until it is posted."""
import sys
from datetime import datetime, timedelta, timezone
from common import *

def ls(prefix):
    r = requests.post(f"{env('SUPABASE_URL').rstrip('/')}/storage/v1/object/list/reels", headers=sb_headers("application/json"),
                      json={"prefix": prefix, "limit": 1000, "offset": 0}, timeout=60)
    r.raise_for_status(); out = []
    for o in r.json():
        if o.get("id") is None: out += ls(f"{prefix}{o['name']}/")          # a folder
        else: out.append({"path": prefix + o["name"], "size": int((o.get("metadata") or {}).get("size", 0)), "at": o.get("created_at", "")})
    return out

files = [f for f in ls("") if not f["path"].startswith("state/")]
mb = lambda b: f"{b / 1e6:.1f} MB"
vids = [f for f in files if f["path"].endswith(".mp4")]; imgs = [f for f in files if f["path"].endswith(".jpg")]
st = load_state()
keep = set()
for it in st["items"].values():
    if it["status"] in ("waiting", "approved"):
        keep |= {u.split("/object/public/reels/")[-1] for u in [it.get("video_url"), it.get("cover_url"), it.get("image_url")] + it.get("image_urls", []) if u}
days = str(settings().get("cleanup_days", "")).strip()
report_only = (len(sys.argv) > 1 and sys.argv[1] == "report") or not days.isdigit()
cut = (datetime.now(timezone.utc) - timedelta(days=int(days) if days.isdigit() else 7)).isoformat()
old = [f for f in files if f["at"] and f["at"] < cut and f["path"] not in keep]
lines = [f"🗄 Supabase storage: {mb(sum(f['size'] for f in files))} of 1 GB free plan, {len(files)} files",
         f"Reels: {len(vids)} videos, {mb(sum(f['size'] for f in vids))} (average {mb(sum(f['size'] for f in vids) / max(1, len(vids)))} each)",
         f"Images: {len(imgs)} (covers, carousels, posts, Stories), {mb(sum(f['size'] for f in imgs))}",
         f"Older than {days or 7} days and not waiting to post: {len(old)} files, {mb(sum(f['size'] for f in old))}"]
if report_only:
    lines.append("Nothing deleted (to turn on automatic cleanup, add cleanup_days = 7 to the Sheet's settings tab).")
elif old:
    for i in range(0, len(old), 100): sb_delete([f["path"] for f in old[i:i + 100]])
    lines.append(f"Deleted those {len(old)} files. Posted Reels stay on Instagram and Facebook.")
msg = "\n".join(lines); print(msg); tg_msg(msg)
