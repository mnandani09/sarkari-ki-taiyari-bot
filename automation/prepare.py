"""Pick TOMORROW's scripts and put them in jobs/pending/ for the Kaggle render.
Day-ahead rhythm: today's run makes tomorrow's Reels; you approve them by midnight; tomorrow they post on schedule."""
import glob, json, os, shutil, sys
from datetime import timedelta
from common import settings, now
s = settings()
arg_n = sys.argv[1] if len(sys.argv) > 1 else ""
event = sys.argv[2] if len(sys.argv) > 2 else ""
force = event == "workflow_dispatch" and arg_n != ""          # a manual test run with a count always renders
n = int(arg_n) if arg_n else int(s.get("reels_per_day", "3") or 3)
target = (now() + timedelta(days=1)).date().isoformat()
first = str(s.get("first_post_date", "")).strip()
dates = json.load(open("content/rendered_dates.json")) if os.path.exists("content/rendered_dates.json") else []
done = set(json.load(open("content/rendered.json"))) if os.path.exists("content/rendered.json") else set()
reason = ""
if not force and first and target < first: reason = f"waiting for first_post_date {first}"
elif not force and target in dates: reason = f"Reels for {target} were already made"
todo = [] if reason else [f for f in sorted(glob.glob("content/scripts/*.json")) if json.load(open(f, encoding="utf-8"))["id"] not in done][:n]
if not reason and not todo: reason = "no scripts left"
shutil.rmtree("jobs/pending", ignore_errors=True); os.makedirs("jobs/pending")
for i, f in enumerate(todo):
    job = json.load(open(f, encoding="utf-8")); job["post_date"], job["order"] = target, i
    json.dump(job, open(f"jobs/pending/{os.path.basename(f)}", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"target post date {target}: {len(todo)} script(s)", [os.path.basename(f) for f in todo], reason)
with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as o:
    o.write(f"count={len(todo)}\ntarget={target}\nreason={reason}\n")
