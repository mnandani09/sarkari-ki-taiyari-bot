"""Day-ahead extras for tomorrow: 1 quiz carousel (5 exam-level MCQs), 1 single quiz post, 2 Stories (7 AM quiz, 9:30 PM answer).
Claude writes them (Gemini if Claude is unavailable) -> code checks the format -> Gemini fact-checks every answer -> one fix round
-> Playwright renders JPEGs -> Supabase -> Telegram previews with Approve / Skip (same midnight deadline as the Reels).
Usage: python daily_posts.py [YYYY-MM-DD to force a date] [event_name]"""
import json, os, sys
from datetime import date, datetime, timedelta
from common import *
from write_scripts import ask_claude, gemini, extract_json
import post_cards

SUBJECTS = ["Indian Polity", "Indian History", "Indian Geography", "General Science", "Indian Economy", "Static GK (firsts, largest, capitals, days)",
            "Computer & General Awareness", "World Geography", "Art & Culture of India", "Biology"]
LOG = "content/posts_log.json"; DATES = "content/posts_dates.json"
DEFAULT_SLOTS = {"slot_story_q": "07:00", "slot_carousel": "13:00", "slot_post": "19:00", "slot_story_a": "21:30"}

def prompt(subjects, avoid):
    return f"""You make quiz content for "Sarkari Ki Taiyari", an Instagram page for SSC (CGL/CHSL/MTS/GD) and Railway (NTPC/Group D) aspirants,
written in friendly Roman Hinglish (Hindi in English letters; keep proper nouns, terms and numbers in English).
Make tomorrow's content as ONE JSON object:
{{
 "carousel": {{"topic": "short topic title", "subject": "{subjects[0]}", "tag": "📚 <SUBJECT IN CAPS> · SSC LEVEL",
   "title_lines": ["2-3 short lines for the cover, max 22 characters each; *word* = yellow, _word_ = green"],
   "questions": [5 x {{"q": "question, max 95 characters", "options": ["4 options, max 30 characters each"], "answer": 0-3, "why": "one-line explanation, max 95 characters"}}],
   "caption": "hook line + '5 sawal, kitne sahi hue? Score comment karo 👇' + 'Save karo 📌 Follow karo @sarkari.ki.taiyari' + 10-12 hashtags"}},
 "post": {{"topic": "...", "subject": "{subjects[1]}", "q": "max 95 characters", "options": [4], "answer": 0-3, "why": "max 95 characters",
   "caption": "the question + 'Comment mein A, B, C ya D likho 👇 Jawaab raat 10 baje comment mein' + 'Follow karo @sarkari.ki.taiyari' + 8-10 hashtags (do NOT reveal the answer)",
   "answer_comment": "✅ Sahi jawaab: <letter>) <option> — <one-line reason>. Kitne logon ne sahi bataya? 🙌"}},
 "story": {{"topic": "...", "subject": "{subjects[2]}", "q": "max 90 characters", "options": [4], "answer": 0-3, "why": "max 90 characters"}}
}}
Rules:
- Exactly the kind of one-liner static GK questions asked in SSC and Railway exams. Do NOT claim a question is from a specific exam or year.
- Only standard, well-established facts as printed in NCERT / Lucent GK. No current affairs, no politics, no living politicians, nothing that changes yearly.
- Exactly one option is correct; the other three must be clearly wrong but believable. Vary the position of the correct answer.
- The 5 carousel questions share the carousel topic. All 7 questions must be different from each other and from these recent ones:
{chr(10).join('  - ' + a for a in avoid[-60:]) or '  (none yet)'}
Reply with the JSON only. Do not use any tools, do not write files."""

def mcq_errs(q, where, qmax=95, omax=30):
    e = []
    if not str(q.get("q", "")).strip(): e.append(f"{where}: no question")
    elif len(q["q"]) > qmax + 15: e.append(f"{where}: question too long")
    o = q.get("options", [])
    if not (isinstance(o, list) and len(o) == 4 and all(str(x).strip() for x in o)): e.append(f"{where}: needs 4 options")
    elif len({str(x).strip().lower() for x in o}) < 4: e.append(f"{where}: duplicate options")
    elif max(len(str(x)) for x in o) > omax + 10: e.append(f"{where}: an option is too long")
    if q.get("answer") not in (0, 1, 2, 3): e.append(f"{where}: answer must be 0-3")
    if not str(q.get("why", "")).strip() or len(str(q.get("why", ""))) > 125: e.append(f"{where}: why missing or too long")
    return e

def validate(j):
    e = []
    c, p, s = j.get("carousel", {}), j.get("post", {}), j.get("story", {})
    if len(c.get("questions", [])) != 5: e.append("carousel needs exactly 5 questions")
    for i, q in enumerate(c.get("questions", [])): e += mcq_errs(q, f"carousel Q{i + 1}")
    if not c.get("title_lines") or not c.get("caption"): e.append("carousel needs title_lines and caption")
    e += mcq_errs(p, "post"); e += mcq_errs(s, "story", 90)
    if not p.get("caption") or not p.get("answer_comment"): e.append("post needs caption and answer_comment")
    for k, x in (("carousel", c), ("post", p), ("story", s)):
        if not x.get("topic"): e.append(f"{k} needs a topic")
    return e

def shuffle(j, seed):
    """Models put the right answer at A too often; spread it over A-D and rebuild the answer comment to match."""
    import random
    rnd = random.Random(seed)
    for q in all_qs(j):
        right = q["options"][q["answer"]]; rnd.shuffle(q["options"]); q["answer"] = q["options"].index(right)
    p = j["post"]
    p["answer_comment"] = f"✅ Sahi jawaab: {'ABCD'[p['answer']]}) {p['options'][p['answer']]}. {p['why']} Kitne logon ne sahi bataya? 🙌"

def all_qs(j): return j["carousel"]["questions"] + [j["post"], j["story"]]
def fact_check(j):
    L = "ABCD"; lines = []
    for i, q in enumerate(all_qs(j)):
        lines.append(f"Q{i + 1}. {q['q']}\n   " + "  ".join(f"{L[k]}) {o}" for k, o in enumerate(q["options"])) + f"\n   MARKED ANSWER: {L[q['answer']]}\n   EXPLANATION: {q['why']}")
    r = extract_json(gemini("""You are a strict fact-checker for Indian competitive exams (SSC, Railway). For each multiple-choice question below, check:
the MARKED ANSWER is correct, it is the ONLY correct option, the question is not ambiguous or outdated, and the EXPLANATION is true.
Use standard sources (NCERT, Lucent GK, official government facts).

""" + "\n".join(lines) + """

Reply as JSON: {"ok": true or false, "issues": ["Qn: what is wrong and the correct fact"]}. "ok" must be false if anything is wrong or doubtful."""))
    return bool(r.get("ok")), r.get("issues", [])

def write(subjects, avoid, seed=0):
    base = prompt(subjects, avoid); last = ([], [])
    for rnd in range(2):
        try: j, by = extract_json(ask_claude(base)), "claude"
        except Exception as ex:
            print("Claude unavailable, using Gemini:", str(ex)[:150]); j, by = extract_json(gemini(base)), "gemini"
        errs = validate(j)
        if not errs:
            shuffle(j, seed)
            try: post_cards.render_all(j, "out_posts")
            except ValueError as ex: errs = [str(ex) + " (make that text shorter)"]
        ok, issues = (False, []) if errs else fact_check(j)
        print(f"round {rnd + 1} ({by}): format {errs} facts {issues}")
        if not errs and ok: return j, by
        last = (errs, issues)
        base = prompt(subjects, avoid) + "\n\nYour previous draft had these problems, fix all of them (replace any doubtful question with a safer one):\n- " + \
               "\n- ".join(errs + issues) + "\n\nPrevious draft:\n" + json.dumps(j, ensure_ascii=False)
    raise RuntimeError("could not get fact-checked content: " + "; ".join((last[0] + last[1])[:4]))

def main():
    s = settings()
    force = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1].strip() else ""
    target = force or (now() + timedelta(days=1)).date().isoformat()
    first = str(s.get("first_post_date", "")).strip()
    dates = json.load(open(DATES)) if os.path.exists(DATES) else []
    if str(s.get("daily_posts", "true")).strip().lower() in ("false", "no", "0", "off"): print("daily_posts is off in the Sheet"); return
    if not force and first and target < first: print(f"waiting for first_post_date {first}"); return
    if not force and target in dates: print(f"posts for {target} already made"); return
    log = json.load(open(LOG)) if os.path.exists(LOG) else []
    avoid = [q for e in log for q in e.get("questions", [])]
    import glob    # Reel topics too, so a quiz doesn't repeat a Reel from the same week
    avoid += ["(Reel topic) " + json.load(open(f, encoding="utf-8")).get("topic", "") for f in sorted(glob.glob("content/scripts/*.json"))[-15:]]
    k = date.fromisoformat(target).toordinal()
    subjects = [SUBJECTS[k % len(SUBJECTS)], SUBJECTS[(k + 3) % len(SUBJECTS)], SUBJECTS[(k + 6) % len(SUBJECTS)]]
    try:
        j, by = write(subjects, avoid, date.fromisoformat(target).toordinal())
        files = post_cards.render_all(j, "out_posts")
    except Exception as ex:
        tg_msg(f"⚠️ Couldn't make the carousel / post / Stories for {target}: {str(ex)[:300]}\nThe Reels are not affected."); raise
    st = load_state(); stamp = now().strftime("%H%M%S"); me = env("TELEGRAM_CHAT_ID")
    when = datetime.fromisoformat(target).strftime("%a %d %b")
    slot = lambda key: f"{target}T{(s.get(key) or DEFAULT_SLOTS[key]).strip()}:00+05:30"
    up = lambda f: sb_upload(f"{target}/posts/{os.path.basename(f)[:-4]}-{stamp}.jpg", open(f, "rb").read(), "image/jpeg")
    btn = lambda rid: {"inline_keyboard": [[{"text": "✅ Approve", "callback_data": f"ok:{rid}:{stamp}"}, {"text": "⏭ Skip", "callback_data": f"skip:{rid}:{stamp}"}]]}
    base = {"status": "waiting", "stamp": stamp, "made": now().isoformat(), "post_date": target, "written_by": by}
    t = lambda key: (s.get(key) or DEFAULT_SLOTS[key]).strip()

    # carousel
    c = j["carousel"]; rid = f"{target}-carousel"; urls = [up(f) for f in files["carousel"]]
    tg("sendMediaGroup", chat_id=me, media=[{"type": "photo", "media": u} for u in urls])
    tg_msg(f"🗂 Carousel for {when} {t('slot_carousel')}: {c['topic']} ({len(urls)} slides above)\n\nCaption:\n{c['caption'][:700]}", reply_markup=btn(rid))
    st["items"][rid] = {**base, "id": rid, "kind": "carousel", "topic": "Carousel: " + c["topic"], "image_urls": urls, "caption": c["caption"],
                        "first_comment": "", "fixed_slot": slot("slot_carousel")}
    # single post
    p = j["post"]; rid = f"{target}-post"; u = up(files["post"])
    tg("sendPhoto", chat_id=me, photo=u, caption=f"🖼 Quiz post for {when} {t('slot_post')}: {p['topic']}\nAnswer comment 3 h later: {p['answer_comment'][:200]}\n\nCaption:\n{p['caption'][:600]}"[:1020], reply_markup=btn(rid))
    st["items"][rid] = {**base, "id": rid, "kind": "post", "topic": "Quiz post: " + p["topic"], "image_url": u, "caption": p["caption"],
                        "answer_comment": p["answer_comment"], "fixed_slot": slot("slot_post")}
    # stories (one approval for both)
    sq, sa = up(files["story_q"]), up(files["story_a"]); grp = f"{target}-stories"
    tg("sendMediaGroup", chat_id=me, media=[{"type": "photo", "media": sq}, {"type": "photo", "media": sa}])
    tg_msg(f"📱 2 Stories for {when}: quiz at {t('slot_story_q')}, answer at {t('slot_story_a')} ({j['story']['topic']})", reply_markup=btn(grp))
    for part, u2, key in (("q", sq, "slot_story_q"), ("a", sa, "slot_story_a")):
        st["items"][f"{grp}-{part}"] = {**base, "id": f"{grp}-{part}", "group": grp, "kind": "story", "topic": f"Story ({'quiz' if part == 'q' else 'answer'}): " + j["story"]["topic"],
                                        "image_url": u2, "caption": "", "fixed_slot": slot(key)}
    save_state(st, only=[k for k, v in st["items"].items() if v.get("post_date") == target and v.get("stamp") == stamp and v.get("kind") != "reel"])
    tg_msg(f"📋 Carousel, quiz post and 2 Stories for {when} are above (fact-checked). Approve or Skip each by midnight tonight.")
    log.append({"date": target, "topics": [c["topic"], p["topic"], j["story"]["topic"]], "questions": [q["q"] for q in all_qs(j)]})
    json.dump(log[-40:], open(LOG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(sorted(set(dates) | {target}), open(DATES, "w"), indent=1)
    os.makedirs("content/posts", exist_ok=True)
    json.dump(j, open(f"content/posts/{target}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"sent carousel, post and stories for {target}")

if __name__ == "__main__":
    main()
