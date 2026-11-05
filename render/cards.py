"""Turn a script's card specs into Playwright-rendered PNGs (cards, banners, stickers, word captions).
Card spec types (what the script writer may use):
  countdown                      -> 3, 2, 1 cards (one spec makes three cards)
  answer   value, label          -> big green answer with sunburst
  headline tag, tag_color(red|yellow), lines[]
  emoji    emoji, lines[], small
  panel    small, lines[], emoji
  timeline nodes[{year, label, on}]
  chips    chips[], small
  grid     n, title, caption
  options  tag, question, options[]
In any text, *word* is highlighted yellow and _word_ green."""
import html, json, os, re
from playwright.sync_api import sync_playwright

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
html,body{background:transparent;font-family:Poppins,'Noto Color Emoji',sans-serif;color:#fff}
.wrap{width:1080px;height:880px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;gap:26px;padding:0 70px}
.tag{font-weight:700;font-size:40px;padding:10px 28px;border-radius:14px;background:#f2b233;color:#1d2a1f;letter-spacing:1px}
.tag.red{background:#e5484d;color:#fff}
.big{font-weight:700;font-size:110px;line-height:1.05}
.mid{font-weight:700;font-size:80px;line-height:1.1}
.small{font-weight:500;font-size:46px;line-height:1.3;color:#e3ece4}
.y{color:#f2b233}.g{color:#7ee081}
.giant{font-weight:700;font-size:400px;line-height:.95;color:#7ee081;text-shadow:0 12px 0 rgba(0,0,0,.25)}
.chips{display:flex;gap:28px;flex-wrap:wrap;justify-content:center}
.chip{border:5px solid #fff;border-radius:28px;padding:26px 36px;font-weight:700;font-size:66px;background:rgba(0,0,0,.18)}
.chip:first-child{border-color:#f2b233}
.panel{background:rgba(0,0,0,.22);border:4px solid rgba(255,255,255,.35);border-radius:36px;padding:44px 50px;width:100%}
.tl{display:flex;align-items:flex-start;justify-content:center;width:100%}
.node{display:flex;flex-direction:column;align-items:center;gap:14px;width:400px}
.dot{width:70px;height:70px;border-radius:50%;background:#55705b;border:6px solid #fff}
.node.on .dot{background:#f2b233;box-shadow:0 0 0 14px rgba(242,178,51,.25)}
.year{font-weight:700;font-size:92px}
.node:not(.on) .year,.node:not(.on) .lab{opacity:.45}
.lab{font-weight:600;font-size:42px;line-height:1.25}
.line{height:10px;width:120px;background:#fff;opacity:.6;border-radius:5px;margin-top:30px}
.opt{display:flex;gap:26px;justify-content:center;flex-wrap:wrap}
.opt div{border:5px solid #fff;border-radius:22px;padding:16px 34px;font-weight:700;font-size:58px}
.cell{height:110px;border-radius:24px;background:#f2b233;color:#1d2a1f;font-weight:700;font-size:60px;display:flex;align-items:center;justify-content:center}
"""
def fmt(s):
    s = html.escape(str(s)).replace("  ", "&nbsp;&nbsp;")
    s = re.sub(r"\*(.+?)\*", r"<span class='y'>\1</span>", s)
    return re.sub(r"_(.+?)_", r"<span class='g'>\1</span>", s)

def page(body, w=1080, h=880, extra=""):
    return f"<html><head><style>{CSS}{extra}</style></head><body style='width:{w}px;height:{h}px'>{body}</body></html>"

def card_html(c):
    t = c["type"]; L = lambda k: "<br>".join(fmt(x) for x in c.get(k, []))
    if t == "answer":
        b = (f"<div style='position:absolute;inset:0;background:repeating-conic-gradient(from 0deg at 50% 45%,rgba(242,178,51,.16) 0deg 10deg,transparent 10deg 20deg)'></div>"
             f"<div class='tag' style='position:relative'>✅ JAWAAB</div><div class='giant' style='position:relative'>{fmt(c['value'])}</div>"
             f"<div class='mid' style='position:relative'>{fmt(c.get('label',''))}</div>")
    elif t == "headline":
        b = (f"<div class='tag{' red' if c.get('tag_color')=='red' else ''}'>{fmt(c['tag'])}</div>" if c.get("tag") else "") + f"<div class='big'>{L('lines')}</div>" + (f"<div class='small'>{fmt(c['small'])}</div>" if c.get("small") else "")
    elif t == "emoji":
        b = f"<div style='font-size:190px'>{c['emoji']}</div><div class='big'>{L('lines')}</div>" + (f"<div class='small'>{fmt(c['small'])}</div>" if c.get("small") else "")
    elif t == "panel":
        b = f"<div class='panel'><div class='small'>{fmt(c.get('small',''))}</div><div class='mid' style='margin-top:20px'>{L('lines')}</div>" + (f"<div style='font-size:180px;line-height:1.15'>{c['emoji']}</div>" if c.get("emoji") else "") + "</div>"
    elif t == "timeline":
        parts = []
        for i, n in enumerate(c["nodes"]):
            if i: parts.append("<div class='line'></div>")
            parts.append(f"<div class='node{' on' if n.get('on') else ''}'><div class='dot'></div><div class='year'>{fmt(n['year'])}</div><div class='lab'>{fmt(n.get('label',''))}</div></div>")
        b = f"<div class='tl'>{''.join(parts)}</div>"
    elif t == "chips":
        b = "<div class='chips'>" + "".join(f"<div class='chip'>{fmt(x)}</div>" for x in c["chips"]) + "</div>" + (f"<div class='small'>{fmt(c['small'])}</div>" if c.get("small") else "")
    elif t == "grid":
        n = int(c["n"]); cols = 5 if n > 6 else n
        b = (f"<div class='mid'>{fmt(c.get('title',''))}</div><div style='display:grid;grid-template-columns:repeat({cols},110px);gap:18px'>"
             + "".join(f"<div class='cell'>{i}</div>" for i in range(1, n + 1)) + f"</div><div class='mid'>{fmt(c.get('caption',''))}</div>")
    elif t == "options":
        b = (f"<div class='tag'>{fmt(c.get('tag','💬 COMMENT KARO'))}</div><div class='mid'>{fmt(c['question'])}</div>"
             "<div class='opt'>" + "".join(f"<div>{fmt(o)}</div>" for o in c["options"]) + "</div>")
    else:
        raise ValueError(f"unknown card type {t}")
    return page(f"<div class='wrap'>{b}</div>")

def countdown(n):
    col = "#f2b233" if n == 1 else "#fff"
    return page(f"<div class='wrap'><div class='small'>⏱️ Socho...</div><div class='giant' style='color:{col}'>{n}</div></div>")

BANNER_CSS = ".bn{width:1080px;height:300px;display:flex;align-items:center;justify-content:center}.box{background:rgba(20,40,28,.88);border:5px solid #f2b233;border-radius:34px;padding:22px 40px;text-align:center;box-shadow:0 12px 0 rgba(0,0,0,.25)}.t1{font-weight:700;font-size:58px;line-height:1.15}.t2{font-weight:600;font-size:40px;color:#f2b233;margin-top:6px}"
def banner(a, b): return page(f"<div class='bn'><div class='box'><div class='t1'>{fmt(a)}</div><div class='t2'>{fmt(b)}</div></div></div>", 1080, 300, BANNER_CSS)
def sticker(e): return page(f"<div style='width:240px;height:240px;margin:10px;border-radius:50%;background:#fff;box-shadow:0 10px 0 rgba(0,0,0,.25);display:flex;align-items:center;justify-content:center;font-size:140px'>{e}</div>", 260, 260)

CAP_CSS = ".cap{width:1080px;height:170px;display:flex;align-items:center;justify-content:center;gap:8px;flex-wrap:nowrap}.w{font-weight:700;color:#fff;-webkit-text-stroke:3px #000;paint-order:stroke fill;text-shadow:0 6px 0 rgba(0,0,0,.55);display:inline-block;padding:0 12px;border-radius:16px}.w.on{color:#f2b233;background:rgba(0,0,0,.45);-webkit-text-stroke:0;text-shadow:none}"
def caption(words, on):
    n = len(" ".join(words)); fs = 72 if n <= 20 else 62 if n <= 25 else 54
    spans = "".join(f"<span class='w{' on' if i == on else ''}' style='font-size:{fs}px'>{html.escape(w)}</span>" for i, w in enumerate(words))
    return page(f"<div class='cap'>{spans}</div>", 1080, 170, CAP_CSS)

BG = """<html><head><style>*{margin:0;padding:0}body{width:1080px;height:1920px;font-family:Poppins,sans-serif;background:radial-gradient(ellipse at 30% 25%,#2f5a3d 0%,#1f3d2b 55%,#173022 100%)}
.brand{position:absolute;top:58px;left:0;right:0;text-align:center;font-weight:700;font-size:38px;letter-spacing:2px;color:#f2b233}
.ch{position:absolute;color:rgba(255,255,255,.07);font-weight:700}</style></head><body>
<div class='brand'>SARKARI KI TAIYARI</div><div class='ch' style='left:60px;top:180px;font-size:90px'>A+B²</div>
<div class='ch' style='right:60px;top:240px;font-size:80px'>1857</div><div class='ch' style='left:70px;top:930px;font-size:72px'>Art. 51A</div>
<div class='ch' style='right:80px;top:960px;font-size:76px'>H₂O</div></body></html>"""
AI_TAG = page("<div style='width:300px;height:60px;display:flex;align-items:center;justify-content:center'><div style='font-weight:600;font-size:26px;background:rgba(0,0,0,.5);padding:6px 16px;border-radius:12px'>AI teacher avatar</div></div>", 300, 60)

def chunks(roman, max_words=4):
    w = roman.replace("—", "").split()
    n = max(1, -(-len(w) // max_words)); size = -(-len(w) // n)
    return [w[i:i + size] for i in range(0, len(w), size)]

def render(job, out):
    """job = script JSON; writes out/{bg_clean.png, cards/*, captions/*, manifest.json}"""
    os.makedirs(f"{out}/cards", exist_ok=True); os.makedirs(f"{out}/captions", exist_ok=True)
    M = {"id": job["id"], "phrases": []}
    with sync_playwright() as p:
        b = p.chromium.launch()
        def shot(h, w, ht, path):
            pg = b.new_page(viewport={"width": w, "height": ht}); pg.set_content(h); pg.wait_for_timeout(120)
            pg.screenshot(path=path, omit_background=True); pg.close()
        shot(BG, 1080, 1920, f"{out}/bg_clean.png"); shot(AI_TAG, 300, 60, f"{out}/cards/ai_tag.png")
        for ph in job["phrases"]:
            names = []
            for k, c in enumerate(ph.get("cards", [])):
                if c["type"] == "countdown":
                    for n in (3, 2, 1):
                        nm = f"{ph['id']}_c{n}"; shot(countdown(n), 1080, 880, f"{out}/cards/{nm}.png"); names.append(nm)
                else:
                    nm = f"{ph['id']}_{k}" + ("_ans" if c["type"] == "answer" else ""); shot(card_html(c), 1080, 880, f"{out}/cards/{nm}.png"); names.append(nm)
            e = {"id": ph["id"], "seg": ph["seg"], "mode": "face" if ph["seg"] != "body" else "broll",
                 "dev": ph["dev"], "roman": ph["roman"], "cards": names, "chunks": []}
            if ph.get("banner"):
                e["banner"] = f"{ph['id']}_banner"; shot(banner(*ph["banner"]), 1080, 300, f"{out}/cards/{e['banner']}.png")
            if ph.get("sticker"):
                e["sticker"] = f"{ph['id']}_stk"; shot(sticker(ph["sticker"]), 260, 260, f"{out}/cards/{e['sticker']}.png")
            for ci, words in enumerate(chunks(ph["roman"])):
                files = []
                for wi in range(len(words)):
                    fn = f"captions/{ph['id']}_{ci}_{wi}.png"; shot(caption(words, wi), 1080, 170, f"{out}/{fn}"); files.append(fn)
                e["chunks"].append({"words": words, "files": files})
            M["phrases"].append(e)
        b.close()
    json.dump(M, open(f"{out}/manifest.json", "w"), ensure_ascii=False, indent=1)
    return M

if __name__ == "__main__":
    import sys; render(json.load(open(sys.argv[1], encoding="utf-8")), sys.argv[2])
