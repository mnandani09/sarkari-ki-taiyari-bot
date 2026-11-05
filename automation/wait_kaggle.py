"""Wait for the Kaggle render to finish (checks every 60 s)."""
import subprocess, sys, time
kid, limit = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 5 * 3600
t = time.time(); last = ""
while time.time() - t < limit:
    out = subprocess.run(f"kaggle kernels status {kid}", shell=True, capture_output=True, text=True).stdout.strip()
    s = out.lower()
    if out != last: print(f"[{(time.time()-t)/60:5.1f} min] {out}", flush=True); last = out
    if "complete" in s: sys.exit(0)
    if "error" in s or "cancel" in s: sys.exit(1)
    time.sleep(60)
print("timed out"); sys.exit(1)
