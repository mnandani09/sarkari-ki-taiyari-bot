"""Sends one Telegram line with the Claude tokens tonight's run used (summed from every call's own usage report)."""
import json, os
from common import tg_msg
f = os.environ.get("CLAUDE_USAGE_LOG", "/tmp/claude_usage.jsonl")
rows = [json.loads(l) for l in open(f)] if os.path.exists(f) else []
if not rows:
    print("no Claude calls this run")
else:
    t = {k: sum(r.get(k, 0) for r in rows) for k in ("in", "out", "cache_w", "cache_r", "usd")}
    total = t["in"] + t["out"] + t["cache_w"] + t["cache_r"]
    msg = (f"🧮 Claude this run: {len(rows)} call(s), {total:,} tokens "
           f"({t['in'] + t['cache_w']:,} new input, {t['cache_r']:,} cached input, {t['out']:,} output). "
           f"Same work on the paid API would cost about ${t['usd']:.2f}. Weekly % is shown at claude.ai → Settings → Usage.")
    print(msg); tg_msg(msg)
