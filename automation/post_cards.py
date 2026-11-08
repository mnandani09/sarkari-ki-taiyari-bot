"""Image templates for the non-Reel formats (Playwright -> JPEG):
carousel slides 1080x1350, single quiz post 1080x1350, Stories 1080x1920. Same colours as the Reels."""
import base64, html, os, re
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
PHOTO = os.path.join(HERE, "..", "render", "madamji.jpg")
def photo_uri():
    return "data:image/jpeg;base64," + base64.b64encode(open(PHOTO, "rb").read()).decode()

def fmt(s):
    s = html.escape(str(s))
    s = re.sub(r"\*(.+?)\*", r"<span class='y'>\1</span>", s)
    return re.sub(r"_(.+?)_", r"<span class='g'>\1</span>", s)

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:Poppins,'Noto Color Emoji',sans-serif;color:#fff;overflow:hidden;
 background:radial-gradient(ellipse at 30% 20%,#2f5a3d 0%,#1f3d2b 55%,#163021 100%)}
.y{color:#f2b233}.g{color:#7ee081}
.page{position:absolute;inset:0;display:flex;flex-direction:column;padding:70px 72px}
.brand{font-weight:700;font-size:30px;letter-spacing:3px;color:#f2b233}
.row{display:flex;align-items:center;justify-content:space-between}
.pill{font-weight:700;font-size:30px;padding:8px 22px;border-radius:40px;background:#f2b233;color:#1d2a1f}
.pill.o{background:transparent;border:3px solid rgba(255,255,255,.45);color:#fff}
.q{font-weight:700;line-height:1.22}
.opts{display:flex;flex-direction:column;gap:20px}
.op{display:flex;align-items:center;gap:24px;border:4px solid rgba(255,255,255,.5);border-radius:26px;padding:18px 26px;font-weight:600;background:rgba(0,0,0,.16)}
.op b{flex:none;width:62px;height:62px;border-radius:50%;background:#fff;color:#1d2a1f;display:flex;align-items:center;justify-content:center;font-size:34px}
.op.ok{border-color:#7ee081;background:rgba(126,224,129,.2)}
.op.ok b{background:#7ee081}
.op.dim{opacity:.45}
.why{border-left:10px solid #f2b233;background:rgba(0,0,0,.22);border-radius:18px;padding:22px 28px;font-weight:500;line-height:1.35;color:#e9f1ea}
.foot{font-weight:600;font-size:30px;color:#cfe0d2;text-align:center}
.av{border-radius:50%;object-fit:cover;object-position:50% 18%;border:8px solid #f2b233;box-shadow:0 14px 0 rgba(0,0,0,.25)}
.big{font-weight:700;line-height:1.08}
.sp{flex:1}
"""
L = "ABCD"
def size_q(q, base):
    n = len(q); return base if n <= 70 else int(base * .88) if n <= 110 else int(base * .76)
def options(opts, answer=None, fs=40):
    out = []
    for i, o in enumerate(opts):
        cls = "" if answer is None else (" ok" if i == answer else " dim")
        mark = "✅" if answer is not None and i == answer else L[i]
        out.append(f"<div class='op{cls}' style='font-size:{fs}px'><b>{mark}</b><span>{fmt(o)}</span></div>")
    return "<div class='opts'>" + "".join(out) + "</div>"
def doc(body, w, h): return f"<html><head><style>{CSS}</style></head><body style='width:{w}px;height:{h}px'>{body}</body></html>"

def cover(c, n):
    return doc(f"""<div class='page' style='align-items:center;text-align:center'>
      <div class='brand'>SARKARI KI TAIYARI</div><div class='sp'></div>
      <img class='av' src='{photo_uri()}' style='width:300px;height:300px'>
      <div class='pill' style='margin-top:46px'>{fmt(c.get('tag', '📚 SSC · RAILWAY LEVEL'))}</div>
      <div class='big' style='font-size:92px;margin-top:34px'>{'<br>'.join(fmt(x) for x in c['title_lines'])}</div>
      <div style='font-weight:500;font-size:40px;color:#e3ece4;margin-top:26px'>{n} sawal · jawaab + explanation ke saath</div>
      <div class='sp'></div><div class='pill o' style='font-size:36px'>Swipe karo ➡️</div></div>""", 1080, 1350)

def q_slide(c, q, k, n):
    return doc(f"""<div class='page'>
      <div class='row'><div class='brand'>SARKARI KI TAIYARI</div><div class='pill'>Q{k}/{n}</div></div>
      <div class='q' style='font-size:{size_q(q['q'], 58)}px;margin-top:56px'>{fmt(q['q'])}</div>
      <div style='margin-top:44px'>{options(q['options'], q['answer'], 40)}</div>
      <div class='why' style='font-size:34px;margin-top:40px'>💡 {fmt(q['why'])}</div>
      <div class='sp'></div><div class='foot'>📌 Save karo revision ke liye · Swipe ➡️</div></div>""", 1080, 1350)

def cta(c, n):
    return doc(f"""<div class='page' style='align-items:center;text-align:center'>
      <div class='brand'>SARKARI KI TAIYARI</div><div class='sp'></div>
      <div style='font-size:150px'>🤔</div>
      <div class='big' style='font-size:84px;margin-top:20px'>Kitne sahi hue?</div>
      <div style='font-weight:600;font-size:46px;margin-top:22px'>Comment mein score likho: <span class='y'>_/{n}</span></div>
      <div class='why' style='font-size:40px;margin-top:60px;text-align:left'>📌 Save karo, exam se pehle revise karna<br>📤 Apne study group ko bhejo<br>🔔 Follow karo <span class='y'>@sarkari.ki.taiyari</span></div>
      <div class='sp'></div><img class='av' src='{photo_uri()}' style='width:170px;height:170px'></div>""", 1080, 1350)

def quiz_post(p):
    return doc(f"""<div class='page'>
      <div class='row'><div class='brand'>SARKARI KI TAIYARI</div><div class='pill'>🎯 AAJ KA SAWAL</div></div>
      <div class='q' style='font-size:{size_q(p['q'], 66)}px;margin-top:70px'>{fmt(p['q'])}</div>
      <div style='margin-top:56px'>{options(p['options'], None, 44)}</div>
      <div class='sp'></div>
      <div class='row'><div style='font-weight:700;font-size:44px'>Comment mein <span class='y'>A, B, C ya D</span> 👇<br><span style='font-weight:500;font-size:32px;color:#cfe0d2'>Jawaab raat 10 baje comment mein ✅</span></div>
      <img class='av' src='{photo_uri()}' style='width:170px;height:170px;border-width:6px'></div></div>""", 1080, 1350)

def story_q(s):
    return doc(f"""<div class='page' style='padding:250px 72px 280px'>
      <div class='row'><div class='brand'>SARKARI KI TAIYARI</div><div class='pill'>🧠 AAJ KA QUIZ</div></div>
      <div class='q' style='font-size:{size_q(s['q'], 70)}px;margin-top:70px'>{fmt(s['q'])}</div>
      <div style='margin-top:60px'>{options(s['options'], None, 46)}</div>
      <div class='sp'></div>
      <div style='font-weight:700;font-size:44px;text-align:center'>Reply mein apna answer bhejo 💬</div>
      <div style='font-weight:500;font-size:36px;text-align:center;color:#f2b233;margin-top:14px'>Jawaab aaj raat 9:30 baje 🕘</div></div>""", 1080, 1920)

def story_a(s):
    return doc(f"""<div class='page' style='padding:250px 72px 280px'>
      <div class='row'><div class='brand'>SARKARI KI TAIYARI</div><div class='pill' style='background:#7ee081'>✅ JAWAAB</div></div>
      <div class='q' style='font-size:{int(size_q(s['q'], 70) * .8)}px;margin-top:60px;color:#e3ece4'>{fmt(s['q'])}</div>
      <div style='margin-top:50px'>{options(s['options'], s['answer'], 44)}</div>
      <div class='why' style='font-size:40px;margin-top:50px'>💡 {fmt(s['why'])}</div>
      <div class='sp'></div>
      <div style='display:flex;align-items:center;gap:30px;justify-content:center'><img class='av' src='{photo_uri()}' style='width:150px;height:150px;border-width:6px'>
      <div style='font-weight:700;font-size:42px'>Roz ke quiz ke liye<br>Follow karo 🔔</div></div></div>""", 1080, 1920)

def render_all(content, out):
    """Writes out/carousel_01.jpg..., out/post.jpg, out/story_q.jpg, out/story_a.jpg; returns the file lists."""
    os.makedirs(out, exist_ok=True)
    c, p, s = content["carousel"], content["post"], content["story"]
    n = len(c["questions"])
    jobs = [("carousel_01", cover(c, n), 1350)] + [(f"carousel_{k + 2:02d}", q_slide(c, q, k + 1, n), 1350) for k, q in enumerate(c["questions"])] \
           + [(f"carousel_{n + 2:02d}", cta(c, n), 1350), ("post", quiz_post(p), 1350), ("story_q", story_q(s), 1920), ("story_a", story_a(s), 1920)]
    files = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for name, h, ht in jobs:
            pg = b.new_page(viewport={"width": 1080, "height": ht}); pg.set_content(h); pg.wait_for_timeout(200)
            over = pg.evaluate("document.querySelector('.page').scrollHeight > document.querySelector('.page').clientHeight + 2")
            if over: raise ValueError(f"{name}: text too long for the image")
            path = f"{out}/{name}.jpg"; pg.screenshot(path=path, type="jpeg", quality=92); pg.close(); files[name] = path
        b.close()
    return {"carousel": [files[k] for k in sorted(files) if k.startswith("carousel_")], "post": files["post"],
            "story_q": files["story_q"], "story_a": files["story_a"]}
