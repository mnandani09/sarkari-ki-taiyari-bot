"""Script writer: keeps a buffer of ready scripts so tomorrow's render never runs dry.
For each missing script: next topic from content/topic_bank.txt -> Claude Code writes it in Madam Ji's storytelling
style (Gemini if Claude is unavailable) -> code checks the format -> Gemini fact-checks every claim -> one fix round.
A script that still fails is skipped (never rendered). Usage: python write_scripts.py [how_many_ready_to_keep]"""
import glob, json, os, re, subprocess, sys, time
import requests
from common import settings, now, tg_msg

END = {"id": "pEND", "seg": "end", "roman": "Follow karo Sarkari Ki Taiyari!", "dev": "फॉलो करो, सरकारी की तैयारी!",
       "banner": ["🔔 Follow karo", "@sarkari.ki.taiyari"], "sticker": "🔔"}
COUNTDOWN = {"seg": "body", "roman": "3 second, socho!", "dev": "तीन सेकंड, सोचो।", "cards": [{"type": "countdown"}]}
TWIST_DEV = "लेकिन स्टोरी यहीं खत्म नहीं होती।"
CARD_TYPES = {"countdown": [], "answer": ["value"], "headline": ["lines"], "emoji": ["emoji", "lines"], "panel": ["lines"],
              "timeline": ["nodes"], "chips": ["chips"], "grid": ["n"], "options": ["question", "options"]}
EXAMPLE = open("content/scripts/2026-11-06-r1-fundamental-duties.json", encoding="utf-8").read()

def prompt_for(subject, topic, angle, rid):
    return f"""You write 30-40 second Instagram Reel scripts for "Sarkari Ki Taiyari", where Madam Ji (an Indian woman teacher) teaches
SSC / Railway / state exam GK in friendly Roman Hinglish. Write ONE script as JSON, in exactly the same structure as this example:

{EXAMPLE}

Today's topic: subject "{subject}", topic "{topic}". Angle to use: {angle}
Use id "{rid}".

Rules (follow all):
1. Story flow: p01 hook (seg "hook": why this is asked again and again + the question) -> p02 exactly
   {{"seg":"body","roman":"3 second, socho!","dev":"तीन सेकंड, सोचो।","cards":[{{"type":"countdown"}}]}} -> p03 the answer with an "answer" card
   -> 3 to 6 short story lines (seg "body"), including exactly one line {{"roman":"Lekin story yahin khatam nahi hoti.","dev":"{TWIST_DEV}"}}
   with an emoji card -> one memory-trick line with a headline card tagged "🧠 YAAD KARNE KI TRICK" -> a closing question (seg "close") with a
   banner ["💬 Comment karo: A ya B?", "A) ...   B) ..."] and sticker "💬" -> the ending exactly:
   {json.dumps(END, ensure_ascii=False)}
2. Only Madam Ji lines (hook, close, end) have "banner" and "sticker"; every body line has 1-2 "cards". Card types allowed: {", ".join(CARD_TYPES)}.
   In card text, *word* = yellow highlight, _word_ = green. Keep card text short (it is shown big on a phone).
3. "roman" = what appears as captions (Roman Hinglish, numbers as digits). "dev" = the SAME words in Devanagari for the Hindi voice:
   spell numbers and years as Hindi words (1976 = उन्नीस सौ छिहत्तर, 42nd = बयालीसवें), write English words as they sound (Amendment = अमेंडमेंट).
   Never use "..." anywhere. Each line max 14 words. Whole script max 95 Roman words.
4. Facts: only standard, well-established facts as printed in NCERT / Lucent GK. No opinions, no politics, no living politicians, no guesses.
   If you are not sure of a detail, leave it out.
5. "caption": hook question + 3-5 emoji bullet facts + the comment question + "Save karo 📌 Follow karo @sarkari.ki.taiyari" + 10-12 hashtags.
   "first_comment": "Answer: ..." with the correct option. "topic": short title. "subject": "{subject}".
Reply with the JSON only. Do not use any tools, do not write files."""

def extract_json(text):
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b < a: raise ValueError("no JSON in reply")
    return json.loads(text[a:b + 1])

def ask_claude(prompt):
    if not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"): raise RuntimeError("no Claude token")
    p = subprocess.run(["claude", "-p", prompt, "--output-format", "text"], capture_output=True, text=True, timeout=420)
    if p.returncode: raise RuntimeError(f"claude exit {p.returncode}: {p.stderr[-200:]}")
    return p.stdout

_gem_model = None
def gemini(prompt, as_json=True):
    global _gem_model
    key = os.environ["GEMINI_API_KEY"]
    if not _gem_model:
        ms = requests.get("https://generativelanguage.googleapis.com/v1beta/models", params={"key": key, "pageSize": 200}, timeout=60).json().get("models", [])
        ok = [m["name"] for m in ms if "generateContent" in m.get("supportedGenerationMethods", []) and "flash" in m["name"]
              and not any(x in m["name"] for x in ("lite", "image", "tts", "audio", "live", "exp", "preview", "thinking"))]
        def ver(n):
            v = re.findall(r"(\d+(?:\.\d+)?)", n); return float(v[0]) if v else 0
        _gem_model = sorted(ok, key=ver)[-1] if ok else "models/gemini-2.5-flash"
        print("gemini model:", _gem_model)
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.2}}
    if as_json: body["generationConfig"]["responseMimeType"] = "application/json"
    for attempt in range(3):
        r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/{_gem_model}:generateContent", params={"key": key}, json=body, timeout=180)
        if r.ok:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        print("gemini retry", r.status_code, r.text[:150]); time.sleep(10 * (attempt + 1))
    raise RuntimeError("gemini failed")

def write(prompt):
    try: return extract_json(ask_claude(prompt)), "claude"
    except Exception as e:
        print("Claude unavailable, using Gemini:", str(e)[:150])
        return extract_json(gemini(prompt)), "gemini"

def validate(j, rid):
    errs = []
    P = j.get("phrases", [])
    if j.get("id") != rid: j["id"] = rid
    for k in ("topic", "caption", "first_comment"):
        if not str(j.get(k, "")).strip(): errs.append(f"missing {k}")
    if len(P) < 8: errs.append("too few lines")
    if P and P[0].get("seg") != "hook": errs.append("first line must be the hook")
    segs = [p.get("seg") for p in P]
    if "close" not in segs: errs.append("no closing question")
    if sum(1 for p in P if p.get("dev", "").strip() == TWIST_DEV) != 1: errs.append("needs exactly one 'Lekin story yahin khatam nahi hoti' line")
    words = 0
    for i, p in enumerate(P):
        p.setdefault("id", f"p{i + 1:02d}")
        for k in ("roman", "dev"):
            if not str(p.get(k, "")).strip(): errs.append(f"{p['id']} missing {k}")
        if "..." in p.get("dev", "") + p.get("roman", ""): p["dev"] = p["dev"].replace("...", ","); p["roman"] = p["roman"].replace("...", ",")
        if p.get("dev") and not re.search(r"[ऀ-ॿ]", p["dev"]): errs.append(f"{p['id']} dev is not Devanagari")
        words += len(p.get("roman", "").split())
        if p.get("seg") == "body":
            if not p.get("cards"): errs.append(f"{p['id']} has no card")
            for c in p.get("cards", []):
                t = c.get("type")
                if t not in CARD_TYPES: errs.append(f"{p['id']} unknown card type {t}")
                else:
                    for need in CARD_TYPES[t]:
                        if not c.get(need): errs.append(f"{p['id']} {t} card missing {need}")
        elif p.get("seg") in ("hook", "close"):
            if not (isinstance(p.get("banner"), list) and len(p["banner"]) == 2): errs.append(f"{p['id']} needs a 2-line banner")
    if words > 105: errs.append(f"too long ({words} words, max 95)")
    # force the fixed lines so the cached ending and timing stay identical
    P = [p for p in P if p.get("seg") != "end"] + [dict(END)]
    if len(P) > 1 and P[1].get("seg") == "body": P[1].update(COUNTDOWN)
    seen = set()
    for i, p in enumerate(P):
        if p["id"] in seen or not p["id"]: p["id"] = f"p{i + 1:02d}"
        seen.add(p["id"])
    j["phrases"] = P
    return errs

def fact_check(j):
    text = "\n".join(p["roman"] for p in j["phrases"]) + "\n\nCAPTION:\n" + j["caption"] + "\n\nANSWER COMMENT:\n" + j["first_comment"]
    reply = gemini(f"""You are a strict fact-checker for Indian competitive exams (SSC, Railway). Check EVERY factual claim (dates, numbers,
names, articles, amendments, places) in this Reel script against standard sources (NCERT, Lucent GK, official government facts).
Also check that the quiz answer in ANSWER COMMENT is correct.
Script:
{text}

Reply as JSON: {{"ok": true or false, "issues": ["each wrong or doubtful claim, with the correct fact"]}}.
"ok" must be false if anything is wrong, doubtful, or outdated.""")
    r = extract_json(reply)
    return bool(r.get("ok")), r.get("issues", [])

def main():
    keep = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] else int(settings().get("reels_per_day", "3") or 3) + 1
    done = set(json.load(open("content/rendered.json"))) if os.path.exists("content/rendered.json") else set()
    scripts = [json.load(open(f, encoding="utf-8")) for f in sorted(glob.glob("content/scripts/*.json"))]
    ready = [s for s in scripts if s["id"] not in done]
    need = keep - len(ready)
    print(f"{len(ready)} script(s) ready, keeping {keep}: writing {max(0, need)}")
    if need <= 0: return
    used = {s.get("topic", "").lower() for s in scripts} | {s.get("bank_topic", "").lower() for s in scripts}
    bank = [l.split("|") for l in open("content/topic_bank.txt", encoding="utf-8") if l.strip() and not l.startswith("#")]
    bank = [[x.strip() for x in b] for b in bank if len(b) >= 3 and b[1].strip().lower() not in used]
    today = now().strftime("%Y-%m-%d"); n = len(glob.glob(f"content/scripts/{today}-w*.json")); written = []
    for subject, topic, angle in bank:
        if len(written) >= need: break
        n += 1; rid = f"{today}-w{n}"
        try:
            j, by = write(prompt_for(subject, topic, angle, rid))
            errs = validate(j, rid)
            ok, issues = (False, []) if errs else fact_check(j)
            if errs or not ok:
                print(f"{rid} ({topic}) round 1: format {errs} facts {issues}")
                fix = prompt_for(subject, topic, angle, rid) + "\n\nYour previous draft had these problems, fix all of them:\n- " + "\n- ".join(errs + issues) + \
                      "\n\nPrevious draft:\n" + json.dumps(j, ensure_ascii=False)
                j, by = write(fix); errs = validate(j, rid)
                ok, issues = (False, []) if errs else fact_check(j)
            if errs or not ok:
                print(f"SKIP {topic}: format {errs} facts {issues}"); continue
            j["bank_topic"], j["written_by"], j["fact_check"] = topic, by, "passed (Gemini)"
            slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")[:40]
            json.dump(j, open(f"content/scripts/{rid}-{slug}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            written.append(j["topic"]); print(f"WROTE {rid}: {j['topic']} (by {by}, fact-check passed)")
        except Exception as e:
            print(f"error on {topic}: {str(e)[:200]}")
    if written: tg_msg("✍️ New scripts written and fact-checked: " + "; ".join(written))
    if len(written) < need: tg_msg(f"⚠️ Script writer made {len(written)} of {need} scripts. Check the Nightly render run in GitHub Actions.")

if __name__ == "__main__":
    main()
