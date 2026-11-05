"""Assemble a Sarkari Ki Taiyari Reel (v5): Madam Ji full-screen in the hook / question / follow lines,
animated cards with word-highlight captions everywhere else, sound effects, progress bar."""
import math, subprocess, random
import numpy as np, cv2, soundfile as sf
from PIL import Image, ImageDraw

FPS, W, H = 25, 1080, 1920
YEL = (242, 178, 51)

def sfx_bank(sr=44100):
    t = lambda d: np.arange(int(d * sr)) / sr
    a = t(0.09); pop = np.sin(2*np.pi*(900 - 5000*a)*a) * np.exp(-a*45) * 0.18
    a = t(0.35); noise = np.random.RandomState(1).randn(len(a))
    wh = np.convolve(noise, np.ones(30)/30, "same") * np.sin(np.pi*a/0.35)**2 * 0.25
    a = t(0.06); tick = np.sin(2*np.pi*1800*a) * np.exp(-a*80) * 0.25
    a = t(0.6); ding = (np.sin(2*np.pi*880*a) + 0.6*np.sin(2*np.pi*1320*a)) * np.exp(-a*6) * 0.15
    return {k: v.astype(np.float32) for k, v in dict(pop=pop, whoosh=wh, tick=tick, ding=ding).items()}

def cover(img, w, h, zoom=1.0):
    iw, ih = img.size; s = max(w/iw, h/ih) * zoom
    im = img.resize((max(w, int(iw*s)), max(h, int(ih*s))), Image.LANCZOS)
    x, y = (im.width - w)//2, (im.height - h)//2
    return im.crop((x, y, x + w, y + h))

def ease(x): x = max(0, min(1, x)); return 1 - (1 - x)**3

def paste_card(fr, card, cx, cy, age):
    k = 0.9 + 0.1*ease(age/0.25); dy = int(70*(1 - ease(age/0.25)))
    c = card if k == 1.0 else card.resize((int(card.width*k), int(card.height*k)))
    if age < 0.25:
        arr = np.array(c); arr[..., 3] = (arr[..., 3]*min(1, 0.2 + age/0.2)).astype(np.uint8); c = Image.fromarray(arr)
    fr.paste(c, (cx - c.width//2, cy - c.height//2 + dy), c)

def load_face(kind, path):
    """kind 'clip' = list of RGB frames; kind 'still' = one photo (fallback, slow zoom)."""
    if kind == "still": return [Image.open(path).convert("RGB")]
    cap = cv2.VideoCapture(path); out = []
    while True:
        ok, f = cap.read()
        if not ok: break
        out.append(Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)))
    return out

def build(M, A, voice_wav, faces, out_path, total, tmp="/tmp/v5"):
    import os; os.makedirs(tmp, exist_ok=True)
    bg = Image.open(f"{A}/bg_clean.png").convert("RGB")
    cache = {}
    def img(p):
        if p not in cache: cache[p] = Image.open(p).convert("RGBA")
        return cache[p]
    shade = Image.new("RGBA", (W, 700)); sd = ImageDraw.Draw(shade)
    for y in range(700): sd.line([(0, y), (W, y)], fill=(10, 20, 14, int(200*(y/700)**1.5)))
    face_frames = {pid: (kind, load_face(kind, p)) for pid, (kind, p) in faces.items()}
    cards_ev, caps_ev, sfx = [], [], []
    for ph in M["phrases"]:
        s, e = ph["start"], ph["end"]; n = len(ph["cards"])
        for k, c in enumerate(ph["cards"]):
            cs = s + (e - s)*k/n
            cards_ev.append((cs, s + (e - s)*(k + 1)/n if k < n - 1 else ph["next"], c, ph))
            sfx.append((cs, "tick" if c[-3:] in ("_c3", "_c2", "_c1") or c in ("c3", "c2", "c1") else "ding" if c.endswith("_ans") or c == "answer" else "pop"))
        if not n: cards_ev.append((s, ph["next"], None, ph)); sfx.append((s + 0.25, "pop"))
        lens = [sum(len(w) + 2 for w in ch["words"]) for ch in ph["chunks"]]; tot = sum(lens); cs = s
        for ch, L in zip(ph["chunks"], lens):
            ce = cs + (e - s)*L/tot; wl = [len(w) + 2 for w in ch["words"]]; ws = cs
            for f, x in zip(ch["files"], wl):
                we = ws + (ce - cs)*x/sum(wl); caps_ev.append((ws, we, f, ph)); ws = we
            cs = ce
    prev = None
    for ph in M["phrases"]:
        if prev and ph["mode"] != prev: sfx.append((ph["start"] - 0.12, "whoosh"))
        prev = ph["mode"]
    def at(evs, t):
        for ev in evs:
            if ev[0] <= t < ev[1]: return ev
        return None
    enc = subprocess.Popen(f"ffmpeg -y -loglevel error -f rawvideo -pix_fmt rgb24 -s {W}x{H} -r {FPS} -i - -c:v libx264 -preset medium -crf 19 -pix_fmt yuv420p {tmp}/video.mp4", shell=True, stdin=subprocess.PIPE)
    for fi in range(int(total*FPS) + 1):
        t = fi/FPS
        cs, ce, cname, ph = at(cards_ev, t) or cards_ev[-1]; age = t - cs
        bob = int(7*math.sin(2*math.pi*t/2.4))
        if ph["mode"] == "face" and ph["id"] in face_frames:
            kind, frs = face_frames[ph["id"]]; lt = t - ph["start"]
            if kind == "clip":
                fr = cover(frs[max(0, min(len(frs) - 1, int(lt*FPS)))], W, H).convert("RGBA")
            else:
                fr = cover(frs[0], W, H, 1.0 + 0.06*min(1, lt/4)).convert("RGBA")
            fr.alpha_composite(shade, (0, H - 700))
            if ph.get("banner"):
                bn = img(f"{A}/cards/{ph['banner']}.png"); ba = t - ph["start"]
                paste_card(fr, bn, W//2, 250 + bob//2, ba)
            st = ph.get("sticker"); sa = t - ph["start"] - 0.35
            if st and sa > 0:
                sk = img(f"{A}/cards/{st}.png"); k = 0.5 + 0.3*ease(sa/0.2)
                sk2 = sk.resize((int(sk.width*k), int(sk.height*k)))
                fr.paste(sk2, (W - 150 - sk2.width//2, 1250 - sk2.height//2 - bob), sk2)
            tag = img(f"{A}/cards/ai_tag.png"); fr.alpha_composite(tag, (W - tag.width - 20, 60))
            cap_y = 1590
        else:
            fr = cover(bg, W, H, 1.0 + 0.04*(t/total)).convert("RGBA")
            jx = jy = 0
            if cname and (cname == "answer" or cname.endswith("_ans")) and age < 0.35: jx, jy = random.randint(-14, 14), random.randint(-14, 14)
            if cname: paste_card(fr, img(f"{A}/cards/{cname}.png"), W//2 + jx, 820 + jy + bob, age)
            cap_y = 1560
        cv_ = at(caps_ev, t)
        if cv_: fr.alpha_composite(img(f"{A}/{cv_[2]}"), (0, cap_y))
        d = ImageDraw.Draw(fr)
        d.rounded_rectangle([40, 24, 1040, 36], 6, fill=(255, 255, 255, 70))
        d.rounded_rectangle([40, 24, 40 + int(1000*min(1, t/total)), 36], 6, fill=YEL + (255,))
        enc.stdin.write(fr.convert("RGB").tobytes())
    enc.stdin.close(); enc.wait()
    sr = 44100; bank = sfx_bank(sr); snd = np.zeros(int((total + 1)*sr), np.float32)
    for ts, k in sfx:
        i = max(0, int(ts*sr)); s_ = bank[k]; snd[i:i + len(s_)] += s_[:len(snd[i:i + len(s_)])]
    sf.write(f"{tmp}/sfx.wav", snd, sr)
    subprocess.run(f"ffmpeg -y -loglevel error -i {tmp}/video.mp4 -i {voice_wav} -i {tmp}/sfx.wav -filter_complex \"[1:a][2:a]amix=inputs=2:normalize=0,loudnorm=I=-14:TP=-1.5[a]\" -map 0:v -map \"[a]\" -c:v copy -c:a aac -b:a 160k -shortest {out_path}", shell=True, check=True)
