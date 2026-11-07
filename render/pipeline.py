"""Nightly batch on Kaggle: every script in a jobs folder -> finished Reel MP4 + QC report.
All Madam Ji clips for all Reels are rendered in ONE InfiniteTalk session (model loads once).
Automatic: cache reuse (e.g. the 'Follow karo' ending), quality checks, one retry with a new seed,
still-photo fallback. Nothing waits for a human.
Usage: python pipeline.py <jobs_dir> <out_dir>"""
import asyncio, glob, hashlib, json, os, shutil, subprocess, sys, time
import edge_tts
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import cards, qc, compose5

JOBS, OUT = sys.argv[1], sys.argv[2]; os.makedirs(OUT, exist_ok=True)
VOICE, RATE = "hi-IN-SwaraNeural", os.environ.get("VOICE_RATE", "+30%")
MAX_S, GAP = 43.0, 0.06          # GAP = breath between Madam Ji and the visuals; long pauses are squeezed out
PY = os.environ.get("WGP_PY", "/tmp/wgpenv/bin/python")
PHOTO = os.environ.get("MADAMJI_PHOTO", f"{HERE}/madamji.jpg")
RECIPE = "it-480-lightx2v4-v2-tight"   # v2: audio trimmed, no padded silence
NEWCACHE = f"{OUT}/face_cache"; os.makedirs(NEWCACHE, exist_ok=True)
CACHES = [NEWCACHE, f"{HERE}/face_cache"]
def sh(c): return subprocess.run(c, shell=True, check=True, capture_output=True, text=True).stdout
def dur(p): return float(sh(f"ffprobe -v error -show_entries format=duration -of csv=p=0 {p}").strip())
def key(text): return hashlib.sha1(f"{text}|{VOICE}|{RATE}|{RECIPE}".encode()).hexdigest()[:12]
async def tts(text, mp3, words=None):
    for attempt in range(4):
        try:
            c = edge_tts.Communicate(text, VOICE, rate=RATE, boundary="WordBoundary"); ws = []
            with open(mp3, "wb") as f:
                async for ch in c.stream():
                    if ch["type"] == "audio": f.write(ch["data"])
                    elif ch["type"] == "WordBoundary": ws.append((ch["offset"]/1e7, ch["duration"]/1e7, ch["text"]))
            if words is not None: words.extend(ws)
            return
        except Exception as e:
            print("tts retry", attempt, e, flush=True); time.sleep(5 * (attempt + 1))
    raise RuntimeError("edge-tts failed 4 times")

# ---------- no awkward pauses: squeeze every silence longer than MAX_PAUSE ----------
import numpy as np, soundfile as sf
MAX_PAUSE, EDGE = 0.15, 0.03
def norm_dev(s): return s.replace("...", ",").replace("…", ",")
def tighten(src, dst):
    """Trim silence at both ends and shorten every pause to MAX_PAUSE. Returns a time map for word timings."""
    a, sr = sf.read(src, dtype="float32")
    if a.ndim > 1: a = a.mean(1)
    hop = int(sr * 0.01); n = len(a) // hop
    rms = np.array([np.sqrt(np.mean(a[i*hop:(i+1)*hop] ** 2)) for i in range(n)])
    loud = rms > max(0.006, rms.max() * 0.02)
    if not loud.any(): sf.write(dst, a, sr); return [(0.0, len(a) / sr, 0.0)]
    keep, i = [], 0
    first, last = int(np.argmax(loud)), n - 1 - int(np.argmax(loud[::-1]))
    s0 = max(0, first - int(EDGE / 0.01)); i = s0; seg_start = s0
    while i <= last:
        if not loud[i]:
            j = i
            while j <= last and not loud[j]: j += 1
            if (j - i) * 0.01 > MAX_PAUSE:
                half = int(MAX_PAUSE / 0.02)
                keep.append((seg_start, i + half)); seg_start = j - half
            i = j
        else:
            i += 1
    keep.append((seg_start, min(n, last + 1 + int(EDGE / 0.01))))
    out, tmap, t_new = [], [], 0.0
    for b, e in keep:
        out.append(a[b*hop:e*hop]); tmap.append((b*0.01, e*0.01, t_new)); t_new += (e - b) * 0.01
    sf.write(dst, np.concatenate(out), sr)
    return tmap
def remap(t, tmap):
    for b, e, nb in tmap:
        if t < b: return nb
        if t <= e: return nb + (t - b)
    b, e, nb = tmap[-1]; return nb + (e - b)

reels = []
for jf in sorted(glob.glob(f"{JOBS}/*.json")):
    job = json.load(open(jf, encoding="utf-8")); T = f"/tmp/job_{job['id']}"; os.makedirs(T, exist_ok=True)
    for ph in job["phrases"]: ph["dev"] = norm_dev(ph["dev"])
    M = cards.render(job, f"{T}/assets"); P = M["phrases"]
    faces = [p for p in P if p["mode"] == "face"]; body = [p for p in P if p["seg"] == "body"]
    for p in faces:
        mp3 = f"{T}/{p['id']}.mp3"; asyncio.run(tts(p["dev"], mp3))
        sh(f"ffmpeg -y -loglevel error -i {mp3} -ar 44100 -ac 1 {T}/{p['id']}_raw.wav")
        tighten(f"{T}/{p['id']}_raw.wav", f"{T}/{p['id']}_44.wav")            # same tight audio for her lips and the mix
        sh(f"ffmpeg -y -loglevel error -i {T}/{p['id']}_44.wav -ar 16000 -ac 1 {T}/{p['id']}_16.wav")
        p["voice_s"] = p["seg_s"] = dur(f"{T}/{p['id']}_44.wav")
    words = []; full = " ".join(p["dev"] for p in body)
    asyncio.run(tts(full, f"{T}/body.mp3", words)); sh(f"ffmpeg -y -loglevel error -i {T}/body.mp3 -ar 44100 -ac 1 {T}/body_untrimmed.wav")
    tmap = tighten(f"{T}/body_untrimmed.wav", f"{T}/body_raw.wav")
    words = [(remap(s0, tmap), remap(s0 + d0, tmap) - remap(s0, tmap), w) for s0, d0, w in words]
    raw = dur(f"{T}/body_raw.wav"); speed = min(1.15, max(1.0, (raw + sum(p["seg_s"] for p in faces) + 2*GAP) / MAX_S))
    sh(f"ffmpeg -y -loglevel error -i {T}/body_raw.wav -af atempo={speed:.3f} {T}/body.wav")
    reels.append(dict(job=job, T=T, M=M, faces=faces, body=body, full=full, speed=speed,
                      words=[(s/speed, d/speed, w) for s, d, w in words], body_s=dur(f"{T}/body.wav"), media={}, log={"faces": {}}))
    print(f"{job['id']}: voice ready (body x{speed:.2f}), Madam Ji lines {[round(p['seg_s'],1) for p in faces]}", flush=True)

def cached(p):
    for c in CACHES:
        f = f"{c}/{key(p['dev'])}.mp4"
        if os.path.exists(f): return f
for attempt, seed in ((1, 42), (2, 1234)):
    tasks, owners, same = [], [], {}
    for r in reels:
        for p in r["faces"]:
            if p["id"] in r["media"]: continue
            wav = f"{r['T']}/{p['id']}_16.wav"; f = cached(p)
            if f and attempt == 1:
                ok, why, m = qc.check(f, wav, PHOTO, p["seg_s"])
                if ok: r["media"][p["id"]] = ("clip", f); r["log"]["faces"][p["id"]] = {"source": "cache", **m}; continue
            k = key(p["dev"])
            if k in same: owners[same[k]].append((r, p)); continue      # same line in several Reels (e.g. the ending): render once
            same[k] = len(tasks)
            tasks.append({"audio": wav, "seconds": p["seg_s"], "seed": seed, "out": f"{r['T']}/{p['id']}_try{attempt}.mp4"}); owners.append([(r, p)])
    if not tasks: break
    json.dump(tasks, open("/tmp/tasks.json", "w"))
    print(f"InfiniteTalk attempt {attempt}: {len(tasks)} clip(s), {sum(t['seconds'] for t in tasks):.1f}s of Madam Ji", flush=True)
    pr = subprocess.Popen(f"cd /tmp/Wan2GP && MPLBACKEND=Agg MADAMJI_PHOTO={PHOTO} {PY} -u {HERE}/render_face.py /tmp/tasks.json", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in pr.stdout:
        if line.startswith(("TASK_", "Traceback")) or "Error" in line or "inference 1/" in line: print(line.rstrip()[:200], flush=True)
    pr.wait()
    for group, tk in zip(owners, tasks):
        r0, p0 = group[0]
        if not os.path.exists(tk["out"]):
            for r, p in group: r["log"]["faces"][p["id"]] = {"attempt": attempt, "fail": ["render failed"]}
            continue
        ok, why, m = qc.check(tk["out"], tk["audio"], PHOTO, p0["seg_s"])
        print(f"QC {r0['job']['id']} {p0['id']} try {attempt}: {'PASS' if ok else 'FAIL'} {why}" + (f" (shared by {len(group)} Reels)" if len(group) > 1 else ""), flush=True)
        for r, p in group:
            r["log"]["faces"][p["id"]] = {"attempt": attempt, "pass": ok, "fail": why, **m}
            if ok: r["media"][p["id"]] = ("clip", tk["out"])
        if ok and p0["seg"] == "end": shutil.copy(tk["out"], f"{NEWCACHE}/{key(p0['dev'])}.mp4")   # reusable ending
for r in reels:
    for p in r["faces"]:
        if p["id"] not in r["media"]:
            r["media"][p["id"]] = ("still", PHOTO); r["log"]["faces"].setdefault(p["id"], {})["fallback"] = "still photo"

for r in reels:
    T, P, body, full, words = r["T"], r["M"]["phrases"], r["body"], r["full"], r["words"]
    t, segs = 0.0, []
    for p in P:
        if p["mode"] == "face":
            p["start"], p["end"], p["next"] = t, t + p["voice_s"], t + p["seg_s"]; segs.append(f"{T}/{p['id']}_44.wav"); t = p["next"]
        elif p is body[0]:
            t += GAP; b0 = t; segs += [("gap", GAP), f"{T}/body.wav"]
            pos, ranges, hits = 0, [], {q["id"]: [] for q in body}
            for q in body:
                a = full.index(q["dev"], pos); ranges.append((q, a, a + len(q["dev"]))); pos = a + len(q["dev"])
            cur = 0
            for st, du, w in words:
                j = full.find(w, cur)
                if j < 0: continue
                cur = j + len(w)
                for q, a, b in ranges:
                    if a <= j < b: hits[q["id"]].append((st, st + du)); break
            pe = b0
            for q in body:
                h = hits[q["id"]]; q["start"], q["end"] = (b0 + h[0][0], b0 + h[-1][1]) if h else (pe, pe + 1.0); pe = q["end"]
            body[0]["start"] = b0
            for i, q in enumerate(body): q["next"] = body[i + 1]["start"] if i + 1 < len(body) else b0 + r["body_s"] + GAP
            t = b0 + r["body_s"] + GAP; segs.append(("gap", GAP))
    ins = [f"-f lavfi -t {s[1]} -i anullsrc=r=44100:cl=mono" if isinstance(s, tuple) else f"-i {s}" for s in segs]
    sh(f"ffmpeg -y -loglevel error {' '.join(ins)} -filter_complex \"concat=n={len(segs)}:v=0:a=1[a]\" -map \"[a]\" {T}/voice.wav")
    out = f"{OUT}/{r['job']['id']}.mp4"
    compose5.build(r["M"], f"{T}/assets", f"{T}/voice.wav", r["media"], out, t, tmp=f"{T}/c")
    sh(f"ffmpeg -y -loglevel error -ss 1.0 -i {out} -frames:v 1 -q:v 3 {OUT}/{r['job']['id']}_cover.jpg")
    r["log"].update(seconds=round(dur(out), 1), speed=round(r["speed"], 3), fallbacks=[k for k, v in r["log"]["faces"].items() if v.get("fallback")])
    json.dump(r["log"], open(f"{OUT}/{r['job']['id']}_qc.json", "w"), indent=1)
    print(f"DONE {out} {r['log']['seconds']}s fallbacks={r['log']['fallbacks']}", flush=True)
