"""Pick the next scripts to render tonight and put them in jobs/pending/ for the Kaggle notebook."""
import glob, json, os, shutil, sys
from common import settings
n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] else int(settings().get("reels_per_day", "2") or 2)
done = set(json.load(open("content/rendered.json"))) if os.path.exists("content/rendered.json") else set()
todo = [f for f in sorted(glob.glob("content/scripts/*.json")) if json.load(open(f, encoding="utf-8"))["id"] not in done][:n]
shutil.rmtree("jobs/pending", ignore_errors=True); os.makedirs("jobs/pending")
for f in todo: shutil.copy(f, "jobs/pending/")
print(f"{len(todo)} script(s) queued for tonight:", [os.path.basename(f) for f in todo])
open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a").write(f"count={len(todo)}\n")
