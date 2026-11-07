"""Automatic quality checks for a Madam Ji clip. No human needed.
Checks: length matches voice, her face in (almost) every frame and still matching the reference photo,
mouth moves with the voice, no black / frozen / glitchy frames."""
import subprocess, numpy as np, cv2

def frames(path, step=1):
    cap = cv2.VideoCapture(path); out = []; i = 0
    while True:
        ok, f = cap.read()
        if not ok: break
        if i % step == 0: out.append(f)
        i += 1
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    return out, fps

def audio_env(wav, fps, n):
    raw = subprocess.run(f"ffmpeg -loglevel error -i {wav} -ac 1 -ar 16000 -f s16le -", shell=True, capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    hop = int(16000 / fps); a = np.pad(a, (0, max(0, n*hop - len(a))))
    env = np.array([np.sqrt(np.mean(a[i*hop:(i+1)*hop]**2) + 1e-9) for i in range(n)])
    return env

import os
_xml = os.path.join(os.path.dirname(os.path.abspath(__file__)), "haarcascade_frontalface_default.xml")
_cas = cv2.CascadeClassifier(_xml)
def face_box(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    f = _cas.detectMultiScale(g, 1.1, 5, minSize=(60, 60))
    return max(f, key=lambda b: b[2]*b[3]) if len(f) else None

def hist(img, b):
    x, y, w, h = b; c = cv2.cvtColor(img[y:y+h, x:x+w], cv2.COLOR_BGR2HSV)
    hh = cv2.calcHist([c], [0, 1], None, [30, 32], [0, 180, 0, 256]); return cv2.normalize(hh, hh)

def check(clip, voice_wav, ref_img_path, expect_s):
    fr, fps = frames(clip); n = len(fr); reasons = []; m = {}
    if n == 0: return False, ["no frames"], m
    m["seconds"] = round(n / fps, 2)
    if abs(n / fps - expect_s) > 0.35: reasons.append(f"length {n/fps:.2f}s vs voice {expect_s:.2f}s")
    ref = cv2.imread(ref_img_path); rb = face_box(ref); rh = hist(ref, rb) if rb is not None else None
    boxes = []; sims = []
    for i in range(0, n, 5):
        b = face_box(fr[i]); boxes.append(b)
        if b is not None and rh is not None: sims.append(cv2.compareHist(rh, hist(fr[i], b), cv2.HISTCMP_CORREL))
    m["face_found"] = round(sum(b is not None for b in boxes) / len(boxes), 2)
    m["face_match"] = round(float(np.mean(sims)), 2) if sims else 0
    if m["face_found"] < 0.85: reasons.append(f"face found in only {m['face_found']:.0%} of frames")
    if m["face_match"] < 0.5: reasons.append(f"face looks different from the photo ({m['face_match']})")
    good = [b for b in boxes if b is not None]
    if good:
        x, y, w, h = np.median(np.array(good), 0).astype(int)
        mx0, mx1, my0, my1 = x + w//5, x + 4*w//5, y + int(h*.62), min(y + int(h*1.0), fr[0].shape[0])
        g = [cv2.cvtColor(f[my0:my1, mx0:mx1], cv2.COLOR_BGR2GRAY).astype(np.float32) for f in fr]
        mot = np.array([0] + [np.abs(g[i] - g[i-1]).mean() for i in range(1, n)])
        env = audio_env(voice_wav, fps, n)
        k = np.ones(5) / 5; a, b2 = np.convolve(mot, k, "same"), np.convolve(env, k, "same")
        m["lip_sync"] = round(float(np.corrcoef(a, b2)[0, 1]), 2) if a.std() > 0 and b2.std() > 0 else 0
        if m["lip_sync"] < 0.15: reasons.append(f"mouth doesn't follow the voice ({m['lip_sync']})")
    full = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32) for f in fr]
    br = np.array([f.mean() for f in full]); dif = np.array([np.abs(full[i] - full[i-1]).mean() for i in range(1, n)])
    m["darkest"], m["max_jump"] = round(float(br.min()), 1), round(float(dif.max()), 1)
    frozen = run = 0
    for v in dif:
        run = run + 1 if v < 0.25 else 0; frozen = max(frozen, run)
    m["frozen_frames"] = frozen
    if br.min() < 15 or br.max() > 245: reasons.append("black or blown-out frames")
    if dif.max() > 40: reasons.append(f"glitchy jump between frames ({dif.max():.0f})")
    if frozen > 15: reasons.append(f"video freezes for {frozen} frames")
    return not reasons, reasons, m
