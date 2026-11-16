"""Prompts for the script (NCERT-grounded) and for LLM-written scene animations."""
import json
import re

LANG_RULES = {
    "hinglish": (
        "Narration language: HINGLISH, the way a friendly Indian teacher talks in class: Hindi sentence structure with "
        "the English technical terms students use in exams. `say` is written ONLY in Devanagari script: English terms "
        "written as they are spoken (\"सिलेंडर\", \"सरफेस एरिया\"), every number written as words (\"तीन\", \"बाईस बटा सात\"), "
        "every symbol spelt out (\"πr²\" → \"पाई आर स्क्वेयर\", \"=\" → \"इज़ इक्वल टू\"). NO digits, NO Latin letters, NO "
        "symbols (= + − × ÷ / ^ ² ³ √ π % °) inside `say`. `caps` is the same line in Roman Hinglish with proper English "
        "spelling for terms (\"Cylinder ka *surface area* 2πrh hota hai\"); digits and symbols ARE allowed in caps."),
    "hindi": (
        "Narration language: HINDI (simple, school Hindi; keep the English exam term in brackets on screen only). `say` "
        "is ONLY Devanagari: numbers as words, symbols spelt out, no digits, no Latin letters, no maths symbols. `caps` is "
        "the same line in Devanagari, digits and symbols allowed."),
    "english": (
        "Narration language: simple Indian-classroom ENGLISH. In `say`, write maths the way it is spoken (\"pi r squared\", "
        "\"two by three\"); no maths symbols or superscripts in `say` (digits are fine). `caps` may use symbols."),
}

SCENE_DOC = """
Scene kinds and the fields each one uses (every on-screen text is {"en": "...", "hi": "..."}; Hindi on-screen text is
proper Devanagari Hindi, names and units unchanged, "cm" → "सेमी", an exam term may follow in brackets: "उत्तल (convex)").
On-screen text is SHORT (a label, a phrase, maths), never a copy of the narration.
- "title": the opening. tag (e.g. "Class 9 · Maths · Ch 11"), subtitle (one line), objectives (2-3 short goals).
- "concept": an idea in 2-4 points. points: [{text, tex?, line, word}] each revealed when its words are spoken.
- "board": a derivation or formula worked on the board. steps: [{tex, text?, line, word, key?}] (LaTeX, one line
  each, key=true on the final/most important step). Use real LaTeX: \\frac{22}{7}, r^2, \\pi, \\times, \\text{cm}^2.
- "figure": a labelled drawing. shapes: [{type, ...geometry, label, color, fill, dashed, line, word}] in a 160 x 90
  unit box (x right, y down; keep 6 units of margin). Types: point(x,y,label) · segment/line/arrow(x,y,x2,y2,label) ·
  circle(x,y,r) · arc(x,y,r,a1,a2 degrees) · rect(x,y,w,h) · polygon(pts) · cylinder/cone/hemisphere(x=centre of base,
  y=base line, r=radius, h=height) · sphere(x,y,r) · cuboid(x,y,w,h,r=depth) · angle(x,y,r,a1,a2,label) ·
  axes(x,y,w,h) · curve(pts) · label(x,y,label) · brace/dim(x,y,x2,y2,label = a measurement like "7 cm").
  Labels only (letters, values, "r", "h = 10 cm"), never sentences. Colors: ink, primary, start, good, flame, gold, muted.
- "solid": a real 3D solid the engine animates (Class 9 Ch 11 / Class 10 Ch 12 style surface areas and volumes, or
  any lesson about 3D shapes). Use it for every scene where a 3D shape is formed, measured, opened up, filled or cut;
  never draw solids as a flat "figure". solid: {shape: cylinder | cone | sphere | hemisphere | cuboid | cube | frustum,
  r, h (and r2 = top radius of a frustum; l, b, h for a cuboid; l = side of a cube), unit, color, labels?} with the
  lesson's real numbers (labels default to "r = 7 cm"; give labels {"r": "r", "h": "h"} when the scene is about
  letters, not numbers). moves: [{do, line, word, ...}], each starts when its word is spoken:
    revolve (a flat profile turns round the axis and sweeps out the solid: cylinder, cone, sphere, hemisphere,
    frustum) · unroll (the curved surface opens into its net: cylinder → rectangle, cone → sector; for curved/total
    surface area) · fill {level 0-1} (liquid rises inside: volume, capacity) · cut {axis "h" across | "v" down
    through the axis, at 0.1-0.9} (cross-section) · orbit {turn degrees} (the camera walks round it) ·
    show {dims ["r","h","l","b","r2"]} (dimension lines + labels; l is the slant height of a cone) ·
    paint {part "curved" | "base" | "top" | "all", color} (highlights the surface being talked about).
  When a line describes a shape being formed (a triangle or rectangle spun round a side), opened up, filled or cut,
  THAT scene is a "solid", never a concept or figure. The next scene about the same solid does not revolve it again:
  it starts from the finished solid (show, paint, unroll, cut).
  2-5 moves per scene, spread over its lines. points (optional, 1-4): [{text, tex, line, word}] formula notes shown
  beside the solid ({"text": {"en": "Curved surface"}, "tex": "2\\pi r h"}).
- "example": a solved NCERT-style example. question, steps: [{text, tex?, line, word}], answer, answer_tex.
- "check": a pause-and-try question. question, options (exactly 4, short), correct (0-3), hint, explain, pause_s
  (5-10). lines: line 0 asks the question and says "pause karke try karo" (or the language equivalent);
  line 1+ reveal and explain the answer. The player stops at the end of line 0 and the student answers.
- "summary": the close. points (3-4 key takeaways), next (what comes next).
Never an empty screen: in concept, board and figure scenes the first point / step / shape is anchored to line 0 with
word "" (or one of its first four words); later items follow the narration.
Anchors: `line` = index of the line in THIS scene's `lines` when the item appears; `word` = the first few letters
of a word in that line's `say` exactly as written there (Devanagari for Hinglish/Hindi), or "" to appear at the line start.
"""

# lessons about 3D shapes (English and Hindi terms): only these get "solid" scenes offered in the plan
SOLID_WORDS = re.compile(r"cylind|\bcones?\b|conical|spher|cuboid|\bcubes?\b|frustum|surface area|volume|"
                         r"सिलेंडर|बेलन|शंकु|गोला|गोले|अर्धगोल|घनाभ|\bघन\b|आयतन|पृष्ठीय", re.I)

SCRIPT_SYSTEM = """You are an expert NCERT teacher and educational video scriptwriter for Indian school students.
You write narrated lesson videos that a bright child enjoys and a subject teacher would sign off.

Rules:
1. Ground every fact, definition, formula, value and example ONLY in the NCERT material provided. Do not invent facts.
   You may rephrase and explain, and add everyday Indian examples (roti, cricket, train, market) as illustrations.
   Never copy long textbook passages verbatim.
2. One idea per scene. Lines are short (one breath, 6-18 words); a line is a visual beat.
3. Warm, encouraging, conversational; ask the viewer questions; no lecturing.
4. Maths/science must be exactly correct. Show units. Check every calculation twice.
5. Reply with ONE JSON object only, matching the schema. No prose, no code fences."""


def script_prompt(units: list[dict], pasted: str, settings: dict, glossary: list[dict]) -> list[dict]:
    lang = settings.get("language", "hinglish")
    minutes = float(settings.get("minutes", 3))
    kinds = settings.get("kinds") or ["title", "concept", "board", "figure", "solid", "example", "check", "summary"]
    checks = int(settings.get("checks", 2))
    screen = settings.get("screen_lang", "en")
    words = int(minutes * (115 if lang != "english" else 135))
    material = []
    for u in units:
        material.append(f"### Teaching unit: {u['name']} (Class {u.get('grade')}, {u.get('subject')}, "
                        f"Chapter {u.get('chapter_number')}: {u.get('chapter')}, section {u.get('section_code')} "
                        f"{u.get('section_name')}; Bloom: {u.get('bloom')}, difficulty: {u.get('difficulty')}; "
                        f"unit id {u['id']})\n{u.get('description') or ''}\n\n{u.get('context') or ''}")
    if pasted.strip():
        material.append("### Teacher-provided material\n" + pasted.strip()[:20000])
    gl = ""
    if glossary and lang != "english":
        rows = [f"{g['term_en']} → say \"{g['hinglish_say'] if lang == 'hinglish' else g['hindi_say']}\", "
                f"caption \"{g['caption'] if lang == 'hinglish' else g['hindi_term']}\"" for g in glossary[:120]]
        gl = "\nGlossary (use these spoken forms for these terms):\n" + "\n".join(rows) + "\n"
    extra = settings.get("instructions", "").strip()
    if "solid" in kinds and not SOLID_WORDS.search(" ".join(material) + " " + extra):
        kinds = [k for k in kinds if k != "solid"]          # not a lesson about 3D shapes
    n_scenes = scene_target(minutes)
    plan = [k for k in ("title", "concept", "solid", "board", "example", "check", "concept", "board", "example",
                        "check", "figure", "concept", "example", "check", "summary") if k in kinds]
    L = lambda: [{"say": "…", "caps": "…", "en": "…"}, {"say": "…", "caps": "…", "en": "…"}]
    schema = {
        "title": {"en": "…", "hi": "…"}, "language": lang, "screen_lang": screen,
        "scenes": [
            {"kind": "title", "title": {"en": "…", "hi": "…"}, "lines": L(), "tag": {"en": "…", "hi": "…"},
             "subtitle": {"en": "…", "hi": "…"}, "objectives": [{"en": "…", "hi": "…"}], "custom_brief": "…"},
            {"kind": "concept", "title": {"en": "…", "hi": "…"}, "lines": L(), "custom_brief": "…",
             "points": [{"text": {"en": "…", "hi": "…"}, "tex": "", "line": 0, "word": "…"}]},
            {"kind": "board", "title": {"en": "…", "hi": "…"}, "lines": L(), "custom_brief": "…",
             "steps": [{"tex": "…", "text": {"en": "…", "hi": "…"}, "line": 0, "word": ""}]},
            {"kind": "solid", "title": {"en": "…", "hi": "…"}, "lines": L(),
             "solid": {"shape": "cylinder", "r": 7, "h": 10, "unit": "cm"},
             "moves": [{"do": "revolve", "line": 0, "word": "…"}, {"do": "show", "line": 1, "word": "…", "dims": ["r", "h"]},
                       {"do": "unroll", "line": 2, "word": "…"}],
             "points": [{"text": {"en": "…", "hi": "…"}, "tex": "2\\pi r h", "line": 2, "word": "…"}]},
            {"kind": "check", "title": {"en": "…", "hi": "…"}, "lines": L(), "question": {"en": "…", "hi": "…"},
             "options": [{"en": "…", "hi": "…"}] * 4, "correct": 0, "hint": {"en": "…", "hi": "…"},
             "explain": {"en": "…", "hi": "…"}, "pause_s": 7},
            "… more scenes …"],
        "sources": ["unit id or section code for each fact you used"]}
    user = f"""Write a narrated lesson video script.

Audience: Class {units[0].get('grade') if units else settings.get('grade', '')} students. Length: about {minutes:g} minutes
(about {words} spoken words in total). Visual frames show on-screen text in {"English" if screen == "en" else "Hindi"}.
{LANG_RULES[lang]}
Every line has: "say" (spoken, rules above), "caps" (caption in the video language; split long captions into 2-3 chunks
with " | "), "en" (the same line in plain English, for the English caption track).
Scene kinds to use: {", ".join(kinds)}. Start with "title" and end with "summary" if they are allowed.
Write about {n_scenes} scenes (a rough plan: {", ".join(plan[:n_scenes - 1] + plan[-1:])}), each with 2-6 lines.
Include exactly {checks} "check" scene(s) placed after the idea they test.
The whole script must be a complete lesson that teaches the material below, not an outline: about {words} spoken words.
{SCENE_DOC}
{gl}
{("Teacher's extra instructions: " + extra) if extra else ""}

NCERT material (the only source of facts):
{chr(10).join(material) if material else "(none provided: use standard NCERT content for the topic in the title)"}

JSON schema (fill every field the scene kind uses; omit unused fields):
{json.dumps(schema, ensure_ascii=False)}"""
    return [{"role": "system", "content": SCRIPT_SYSTEM}, {"role": "user", "content": user}]


def scene_target(minutes: float) -> int:
    return max(4, min(30, round(minutes * 2.4)))


def fix_prompt(messages: list[dict], reply: dict, problems: list[str]) -> list[dict]:
    return messages + [
        {"role": "assistant", "content": json.dumps(reply, ensure_ascii=False)[:60000]},
        {"role": "user", "content": "Fix these problems and reply with the complete corrected JSON object only:\n- "
                                    + "\n- ".join(problems[:40])}]


def scene_regen_prompt(script: dict, scene_index: int, note: str, units: list[dict], lang: str) -> list[dict]:
    ctx = "\n\n".join(f"### {u['name']}\n{(u.get('context') or '')[:6000]}" for u in units)
    user = f"""Here is a lesson video script (JSON). Rewrite ONLY scene index {scene_index} following the note, keep its kind
unless the note asks otherwise, keep it consistent with the scenes around it, and keep every rule of the original.
{LANG_RULES[lang]}
{SCENE_DOC}
Note from the teacher: {note or "make it clearer and more engaging"}

Script:
{json.dumps(script, ensure_ascii=False)[:50000]}

NCERT material:
{ctx}

Reply with the single rewritten scene object as JSON only."""
    return [{"role": "system", "content": SCRIPT_SYSTEM}, {"role": "user", "content": user}]


CUSTOM_API = """
You write the body of a JavaScript function `draw(ctx, t, A)` that draws ONE frame of an educational animation on a
2D canvas. It is called for every frame with `t` = seconds since the scene started (0 … A.dur). It must be a PURE
function of t: same t → same picture; no state between calls, no randomness (use A.rand(i) for fixed pseudo-random).
The engine has already painted the paper background and the scene heading at the top. Below the heading you own
A.stage {x, y, w, h} (full width, down to the bottom of the frame). Keep text and key drawings inside A.box {x, y, w, h}
(inside the stage, clear of the captions); backgrounds and decoration may fill the whole stage.
Canvas size A.W × A.H (1920×1080 for 16:9, 1080×1920 for 9:16). Pixel units.

Timing (seconds, scene-relative):  A.dur · A.L(i) start of line i · A.Le(i) end of line i ·
  A.T('word', i?) start of the first spoken word starting with 'word' (in line i if given) – words are exactly as in `say`.
Easing: A.clamp(x,a=0,b=1) · A.prog(t, start, len) → 0..1 · A.eo(x) ease-out · A.eio(x) ease-in-out · A.spring(x) springy
  overshoot · A.lerp(a,b,x) · A.rand(i) fixed 0..1.
Colors A.c: ink ink2 muted faint primary primaryDeep primarySoft brand brandSoft start startSoft good goodBg flame
  flameBg gold goldBg paper frame line surface bad (never use bad).
Drawing helpers (all take an options object o; `progress` 0..1 draws a stroke partially, for "being drawn" reveals):
  A.text(str, x, y, o)  o: size(px) weight('400'..'800') color align('left'|'center'|'right') display(true = Baloo 2
      headings/numbers, false = Mukta body) maxW alpha baseline
  A.tex(latex, x, y, o)  LaTeX maths, o: size color align alpha — a string literal with DOUBLED backslashes, exactly
      like A.tex('\\frac{1}{2} \\times 2\\pi r', 960, 500, {size: 64}). Never put LaTeX in A.text.
  A.line(x1,y1,x2,y2,o) A.arrow(x1,y1,x2,y2,o) A.circle(x,y,r,o) A.arc(x,y,r,a0,a1,o) (radians) A.rect(x,y,w,h,o)
  A.poly([[x,y],…],o) A.curve([[x,y],…],o)   o: color width fill(color) dash([a,b]) progress alpha radius close
  A.card(x,y,w,h,o) white rounded card with the soft "ledge" · A.pill(text,x,y,o) rounded tag · A.chip(n,x,y,o) number
  circle · A.bk(x,y,h,pose) Bal Krishna (pose 'calm'|'wave'), x,y = feet centre · A.bubble(text,x,y,o) speech bubble
  A.pop(t, t0) scale 0→1 with a soft spring starting at t0 · A.fade(t, t0, len=.3) alpha 0→1
  A.grad(x0,y0,x1,y1,stops) linear gradient · A.radial(x,y,r,stops) radial gradient (stops: ['#fff','#9bf'] or
      [[0,'#fff'],[1,'#9bf']]); use them as `fill`/`color` or ctx.fillStyle to shade solids so they look round.
  A.bg(fill) paints the whole stage (a colour or a gradient). Call it FIRST if you want a stage background.
  A.camera(t, [{at, x, y, zoom, len}, …]) moves the camera: from time `at` it glides (len s, default 0.7) until point
      (x, y) sits at the stage centre, magnified `zoom` (1 = as drawn, max 1.8). Call it after A.bg and BEFORE
      drawing; draw everything in normal canvas coordinates and the camera frames it. Clipped to the stage.
      A framing shows only a window of A.stage.w/zoom × A.stage.h/zoom px around (x, y) (moved inward if it would
      leave the stage). Every label, number and formula that matters at that moment must lie inside that window
      with 40 px to spare, or it is cut off: put the labels next to the part you zoom on, not at the far edges.
  ctx is a normal CanvasRenderingContext2D for anything else (save/restore around transforms).
This is the ANIMATED version of the lesson. A separate template version already shows the same scene as white cards,
  numbered chips, pills and bullet lists on off-white paper with flat outline drawings, and the viewer compares the
  two. Do NOT rebuild that: no bullet lists, no stacks of cards, no chips or pills, no copy of the template's layout.
  The scene content below gives the facts, labels and maths to show, not a layout to copy.
Show the idea instead:
  - Draw the real thing the narration is about (an ice-cream cone, a tin can, a ladoo, a tent, a clock, a cricket
    ball, a field, a river) and turn it into the maths: the object becomes its shape, the shape gets its labels.
  - Make the change visible: things build up piece by piece, rotate, roll, fill with colour or water, unfold into a
    net, split and recombine, grow along a motion path. Use arrows and moving highlights to lead the eye.
  - Camera: plan 2-4 framings with A.camera. Start wide on the whole picture; move in (zoom 1.2-1.5) on the part being
    talked about at the word that names it (at: A.T('word', line) - 0.2); pull back out (zoom 1) for the conclusion.
    Before you finish, check each framing's window against every text you draw while it is active.
  - Keep it alive: something always moves gently (a slow turn, a pulse, a drifting light), and 2-3 coordinated motions
    at the key moment. Smooth easing, nothing jitters or flashes.
  - Colour and light: give the scene its own mood with A.bg (sky, water, chalkboard green, night blue, warm table).
    Shade solid objects with A.grad / A.radial, light from the top left. Keep text dark on light areas, white on dark.
Readable on a phone: text ≥ 40 px, key labels and maths ≥ 56 px (at 1920×1080; the same pixel sizes for 9:16).
  Labels, numbers and maths only on the drawing, no sentences. Keep 24 px between texts so nothing overlaps. Every fact,
  number and label must match the scene content and the narration exactly. Things appear on the word that names them.
Forbidden: while loops, recursion, document, window, fetch, XMLHttpRequest, import, eval, Function, setTimeout,
  setInterval, requestAnimationFrame, globalThis, localStorage. `for` loops must have a small fixed bound (≤ 500).
"""

CUSTOM_SYSTEM = ("You are a senior motion designer and creative coder who makes clear, beautiful maths and science "
                 "animations for children. You reply with JSON only.")


def custom_prompt(script: dict, scene: dict, aspect: str, error: str = "") -> list[dict]:
    W, H = (1920, 1080) if aspect == "16:9" else (1080, 1920)
    lines = "\n".join(f"  line {i}: say: {ln['say']}  |  meaning: {ln.get('en') or ln.get('caps')}"
                      for i, ln in enumerate(scene["lines"]))
    data = {k: v for k, v in scene.items() if k not in ("lines", "custom_code", "custom_brief", "id") and v}
    retry = f"\nYour previous code failed with this error, fix it:\n{error}\n" if error else ""
    user = f"""{CUSTOM_API}
Canvas: {W}×{H}. Video title: {script['title'].get('en')}. On-screen text language: {"English" if script.get('screen_lang', 'en') == 'en' else "Hindi"}.
Scene {scene['id']} (kind "{scene['kind']}"): {scene['title'].get('en')}
What the animation should show: {scene.get('custom_brief') or scene['title'].get('en')}
Narration of this scene (time anchors come from these words):
{lines}
Scene content (use it; text fields are {{en, hi}}):
{json.dumps(data, ensure_ascii=False)[:6000]}
{retry}
Reply as JSON: {{"code": "<the function body only, no function header>"}}"""
    return [{"role": "system", "content": CUSTOM_SYSTEM}, {"role": "user", "content": user}]


FORBIDDEN = ("while", "document", "window", "fetch", "XMLHttpRequest", "import", "eval", "Function(", "setTimeout",
             "setInterval", "requestAnimationFrame", "globalThis", "localStorage", "constructor", "__proto__")


_TEX_LIT = __import__("re").compile(r"""(A\.tex\(\s*)(['"`])((?:\\.|(?!\2).)*)\2""", __import__("re").S)


def fix_tex_literals(code: str) -> str:
    """Double the single backslashes inside A.tex('…') string literals (models often write '\\frac' as '\frac',
    which JavaScript turns into a form feed + 'rac', or drops: '\\pi' → 'pi'). Already-doubled ones stay."""
    import re

    def fix(m):
        # walk escapes pairwise: "\\\\" and escaped quotes stay; any other single backslash is doubled
        body = re.sub(r"\\(.)", lambda e: e.group(0) if e.group(1) in "\\'\"`" else "\\\\" + e.group(1),
                      m.group(3), flags=re.S)
        return m.group(1) + m.group(2) + body + m.group(2)
    return _TEX_LIT.sub(fix, code)


# comments and '…' / "…" strings: words inside them never run (eval and Function are forbidden), so a comment like
# "// swept surface while rotating" must not cost a retry. Template literals stay: `${…}` inside them is code.
_INERT = __import__("re").compile(
    r"""//[^\n]*|/\*.*?\*/|'(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*\"""", __import__("re").S)


def code_problems(code: str) -> list[str]:
    import re
    anywhere = {"constructor", "__proto__", "prototype"}     # reachable as .x or ['x'] from any object → Function
    live = _INERT.sub(" ", code)
    out = [f"uses forbidden '{w}'" for w in (*FORBIDDEN, "prototype")
           if (w in code if w in anywhere else
               re.search(r"(?<![\w.$])" + re.escape(w) + (r"(?![\w$])" if w[-1].isalnum() else ""), live))]
    if len(code) > 30000:
        out.append("code is longer than 30000 characters")
    return out
