"""Narration for $0 on this computer: Kokoro-82M or VoiceStudio TTS. No cloud fees, no API keys.

  scripts/py scripts/voice.py <project>          script.json -> data/narration.wav + data/lines.json (exact line times)
  scripts/py scripts/voice.py --list             voices that narrate well
  scripts/py scripts/voice.py --download         only fetch Kokoro model files (~340 MB, once)

script.json:
  {
    "tts": "kokoro" | "voicestudio" | "omnivoice",
    "omnivoice": { "language": "Hindi", "instruct": "female, indian accent" }   (OmniVoice on a GPU, e.g. Kaggle: see kaggle/)
    "voice": "am_michael" (Kokoro) or "Hindi Storyteller" / "narrator" / "profile:<id>" (VoiceStudio),
    "lang": "en-us" | "en-gb" | "hi" | ...  (default: from the Kokoro voice's first letter: a=US, b=UK, h=Hindi, e, f, i, p),
    "speed": 1.05, "lead": 0.12, "outro": 0.45, "gap": 0.32,
    "lines": [ { "text": "What if you swallow gum?", "caps": "...", "gap": 0.3 }, ... ]
  }

One line = one CUT, not one sentence: a sentence can run across several lines ("It slides down your throat and lands
in your stomach," / "where acid gets to work on it."). Lines are grouped into whole sentences and each sentence is
spoken in ONE pass, so the intonation flows naturally; every cut inside a sentence is first placed by text length and
snapped to the nearest pause here, then words.py moves it onto the exact word Whisper heard. "gap" (on a sentence's last line) = the pause after that sentence.
Write numbers the way they're SAID. Then run words.py for the word timings.
"""
import argparse, io, json, math, os, re, sys, urllib.request
from pathlib import Path
import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

HOME = Path(os.environ.get('FACELESS_HOME', Path.home() / '.faceless-shorts'))
KDIR = HOME / 'kokoro'
FILES = {
    'kokoro-v1.0.onnx': 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx',
    'voices-v1.0.bin': 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin',
}
GOOD = {
    'am_michael': 'US male, steady explainer (default)', 'am_puck': 'US male, lively, playful', 'am_fenrir': 'US male, deeper',
    'am_onyx': 'US male, low', 'af_heart': 'US female, warm (best overall)', 'af_bella': 'US female, bright',
    'af_nicole': 'US female, soft and close', 'bm_george': 'UK male, documentary', 'bm_fable': 'UK male, storyteller',
    'bf_emma': 'UK female, calm',
    'hf_alpha': 'Hindi female', 'hf_beta': 'Hindi female, softer', 'hm_omega': 'Hindi male', 'hm_psi': 'Hindi male, deeper',
}
KOKORO_VOICE = re.compile(r'^[abefhijpz][fm]_[a-z]+$')          # every Kokoro v1.0 voice id looks like this
KOKORO_LANG = {'a': 'en-us', 'b': 'en-gb', 'h': 'hi', 'e': 'es', 'f': 'fr-fr', 'i': 'it', 'p': 'pt-br', 'j': 'ja', 'z': 'cmn'}
SENTENCE_END = re.compile(r'[.?!।॥]["\')]*$')                      # Latin and Devanagari full stops
SR = 24000


def ensure_models():
    KDIR.mkdir(parents=True, exist_ok=True)
    for name, url in FILES.items():
        p = KDIR / name
        if p.exists() and p.stat().st_size > 1_000_000: continue
        print(f'downloading {name} (once)...', flush=True)
        tmp = p.with_suffix('.part'); urllib.request.urlretrieve(url, tmp); tmp.rename(p)


def trim(x, thr=0.008):
    """cut leading/trailing silence so line start/end times are exact"""
    idx = np.where(np.abs(x) > thr)[0]
    if not len(idx): return x
    a = max(0, idx[0] - int(0.01 * SR)); b = min(len(x), idx[-1] + int(0.03 * SR)); return x[a:b]


def silences(x, thr=0.012, min_len=0.06):
    """pauses inside speech: [(start_s, end_s)] where the 10 ms RMS stays under thr for >= min_len"""
    hop = int(0.01 * SR); n = len(x) // hop
    rms = np.sqrt(np.mean(x[:n * hop].reshape(n, hop) ** 2, axis=1)); quiet = rms < thr * np.abs(x).max()
    out, st = [], None
    for f, q in enumerate(quiet):
        if q and st is None: st = f
        if (not q or f == n - 1) and st is not None:
            if (f - st) * 0.01 >= min_len: out.append((st * 0.01, f * 0.01))
            st = None
    return out


def voicestudio_is_running(ports=(3900, 58391)):
    """Check if VoiceStudio local backend is currently responding (instant socket check)"""
    import socket
    for p in ports:
        try:
            with socket.create_connection(('127.0.0.1', p), timeout=0.08):
                return p
        except Exception:
            pass
    return None


def voicestudio_say(text, voice='narrator', speed=1.0, lang='en-us', style=None):
    """Synthesize speech using local VoiceStudio via HTTP or core.tools"""
    errors = []
    # 1. Try running local HTTP endpoint first
    for port in [3900, 58391]:
        try:
            req_data = json.dumps({
                "input": text,
                "voice": voice,
                "speed": speed,
                "response_format": "wav"
            }).encode('utf-8')
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/v1/audio/speech",
                data=req_data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                in_sr, raw = wavfile.read(io.BytesIO(resp.read()))
                if raw.ndim > 1: raw = raw.mean(axis=1)
                data = raw.astype(np.float64)
                if raw.dtype == np.int16: data /= 32768.0
                elif raw.dtype == np.int32: data /= 2147483648.0
                if in_sr != SR:
                    gcd = math.gcd(in_sr, SR)
                    data = resample_poly(data, SR // gcd, in_sr // gcd)
                return trim(data)
        except Exception as e:
            errors.append(f'http://127.0.0.1:{port}: {type(e).__name__}: {e}')
            continue

    # 2. Try python core.tools bridge
    try:
        from core import tools
        if str(voice).startswith('profile:'):
            pid = int(str(voice).split(':')[1])
            res = tools.generate_with_profile(text=text, profile_id=pid, language=lang, style=style)
        else:
            res = tools.generate_speech(text=text, voice=voice, language=lang, style=style)
        in_sr, raw = wavfile.read(io.BytesIO(res.audio_bytes))
        if raw.ndim > 1: raw = raw.mean(axis=1)
        data = raw.astype(np.float64)
        if raw.dtype == np.int16: data /= 32768.0
        elif raw.dtype == np.int32: data /= 2147483648.0
        if in_sr != SR:
            gcd = math.gcd(in_sr, SR)
            data = resample_poly(data, SR // gcd, in_sr // gcd)
        return trim(data)
    except Exception as e:
        errors.append(f'core.tools: {type(e).__name__}: {e}')
        raise RuntimeError('VoiceStudio speech generation failed (is the VoiceStudio app running?):\n  ' + '\n  '.join(errors))


def omnivoice_engine(cfg):
    """OmniVoice (k2-fsa, the multilingual model behind VoiceStudio's voices) on a local GPU. pip install omnivoice"""
    import torch
    from omnivoice import OmniVoice
    dev = 'cuda:0' if torch.cuda.is_available() else 'cpu'
    print(f'[voice] loading OmniVoice on {dev}...', flush=True)
    m = OmniVoice.from_pretrained('k2-fsa/OmniVoice', device_map=dev, dtype=torch.float16 if dev != 'cpu' else torch.float32, load_asr=False)
    in_sr = int(getattr(m, 'sampling_rate', 0) or getattr(getattr(m, 'config', None), 'sampling_rate', 0) or 24000)
    # Warmup generation to prime CUDA kernels and avoid cold-start glitch on line 0
    try:
        m.generate(text="नमस्ते", language=cfg.get('language', 'Hindi'), instruct=cfg.get('instruct', 'female, indian accent'))
    except Exception as e:
        print(f'[voice] warmup note: {e}')
    def say(text):
        audio = m.generate(text=text, language=cfg.get('language', 'Hindi'), instruct=cfg.get('instruct', 'female, indian accent'))
        raw = audio[0] if isinstance(audio, (list, tuple)) else audio
        if hasattr(raw, 'detach'): raw = raw.detach().float().cpu().numpy()
        x = np.asarray(raw, dtype=np.float64).squeeze()
        if in_sr != SR: g = math.gcd(in_sr, SR); x = resample_poly(x, SR // g, in_sr // g)
        if len(x) > 0: x = x - np.mean(x)
        return trim(x)
    return say


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('project', nargs='?')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--download', action='store_true')
    ap.add_argument('--tts', choices=['kokoro', 'voicestudio', 'omnivoice', 'auto'], default=None,
                    help='TTS engine to use: kokoro (local onnx) or voicestudio (local AI studio)')
    ap.add_argument('--voice')
    ap.add_argument('--speed', type=float)
    a = ap.parse_args()

    if a.list:
        print('=== Kokoro-82M Voices (Fast, local ONNX, English) ===')
        for k, v in GOOD.items(): print(f'  {k:12s} {v}')
        print('\n=== VoiceStudio (Local AI Studio: 646 languages, Hindi, Voice Cloning) ===')
        vs_port = voicestudio_is_running()
        if vs_port:
            print(f'  [Active on port {vs_port}] Available voices/profiles:')
            try:
                from core import tools
                for v in tools.list_voices():
                    print(f'  {v.id:16s} ({v.language or "any"}) {v.name}')
            except Exception as e:
                print(f'  (connect error: {e})')
        else:
            print('  Launch VoiceStudio desktop app to enable custom cloned voices & Hindi models.')
        return

    if a.download:
        ensure_models()
        return

    if not a.project: ap.error('project folder missing')

    P = Path(a.project); S = json.loads((P / 'script.json').read_text(encoding='utf-8'))
    engine = a.tts or S.get('tts', 'auto')
    voice = a.voice or S.get('voice', 'am_michael')
    speed = a.speed or S.get('speed', 1.0)
    lang = S.get('lang', 'en-us')
    style = S.get('style')

    # Resolve engine: any Kokoro voice id goes to Kokoro (not just the shortlist); anything else is a VoiceStudio voice
    if engine == 'omnivoice':
        cfg = S.get('omnivoice', {}); print(f"[voice] Using OmniVoice ({cfg.get('language', 'Hindi')}, {cfg.get('instruct', 'female, indian accent')})")
        say = omnivoice_engine(cfg); voice = 'omnivoice:' + cfg.get('instruct', 'female')
    is_kokoro = bool(KOKORO_VOICE.match(str(voice)))
    use_vs = engine == 'voicestudio' or (engine == 'auto' and not is_kokoro)
    if engine == 'omnivoice': use_vs = False
    if use_vs and not voicestudio_is_running():
        raise SystemExit(f'"{voice}" is not a Kokoro voice, so it needs VoiceStudio, which is not running. '
                         'Open the VoiceStudio app, or pick a Kokoro voice (voice.py --list).')
    if engine == 'kokoro' and not is_kokoro:
        raise SystemExit(f'"{voice}" is not a Kokoro voice id (voice.py --list)')

    if engine == 'omnivoice': pass
    elif use_vs:
        print(f'[voice] Using VoiceStudio TTS (voice: {voice}, lang: {lang}, speed: {speed})')
        say = lambda text: voicestudio_say(text, voice=voice, speed=speed, lang=lang, style=style)
    else:
        print(f'[voice] Using Kokoro-82M TTS (voice: {voice}, speed: {speed})')
        ensure_models()
        from kokoro_onnx import Kokoro
        k = Kokoro(str(KDIR / 'kokoro-v1.0.onnx'), str(KDIR / 'voices-v1.0.bin'))
        k_lang = S.get('lang') or KOKORO_LANG.get(voice[0], 'en-us')
        if k_lang == 'en': k_lang = 'en-us'
        say = lambda text: trim(np.asarray(k.create(text, voice=voice, speed=speed, lang=k_lang)[0], dtype=np.float64))

    # group the lines into whole sentences (a line ending in . ? ! closes one; "break": true forces a close)
    groups, cur = [], []
    for i, ln in enumerate(S['lines']):
        cur.append(i)
        if SENTENCE_END.search(ln['text'].strip()) or ln.get('break') or i == len(S['lines']) - 1:
            groups.append(cur)
            cur = []
    out = [np.zeros(int(S.get('lead', 0.12) * SR))]; t = len(out[0]) / SR; lines = [None] * len(S['lines'])
    for gi, g in enumerate(groups):
        x = say(' '.join(S['lines'][i]['text'] for i in g))
        cuts = [0.0]
        if len(g) > 1:                                    # find each cut inside the sentence (no second synthesis:
            # place it by spoken-text length, snap to the nearest pause; words.py then refines it from Whisper)
            lens = np.array([len(re.sub(r'[^\w]', '', S['lines'][i]['text'])) + 1 for i in g], dtype=float)
            pauses = silences(x)
            for c in np.cumsum(lens)[:-1] / lens.sum() * len(x) / SR:
                near = [p for p in pauses if abs((p[0] + p[1]) / 2 - c) < 0.4]
                if near: p = min(near, key=lambda p: abs((p[0] + p[1]) / 2 - c)); cuts.append((p[0], p[1]))
                else: cuts.append((c, c))
        n = len(x) / SR
        for j, i in enumerate(g):
            a = 0.0 if j == 0 else cuts[j][1]; b = n if j == len(g) - 1 else cuts[j + 1][0]
            lines[i] = {'i': i, 'text': S['lines'][i]['text'], 'start': round(t + a, 3), 'end': round(t + b, 3),
                        'group': gi, 'group_start': round(t, 3), 'group_end': round(t + n, 3)}
            print(f'{i:2d} {lines[i]["start"]:6.2f}-{lines[i]["end"]:6.2f}  {S["lines"][i]["text"]}', flush=True)
        gap = np.zeros(int(float(S['lines'][g[-1]].get('gap', S.get('gap', 0.3))) * SR))
        out += [x, gap]; t += (len(x) + len(gap)) / SR
    outro = np.zeros(int(float(S.get('outro', 0.45)) * SR)); out.append(outro)
    y = np.concatenate(out); y = y / (np.abs(y).max() + 1e-9) * 0.9
    (P / 'data').mkdir(exist_ok=True)
    wavfile.write(P / 'data/narration.wav', SR, (y * 32767).astype(np.int16))
    dur = len(y) / SR
    (P / 'data/lines.json').write_text(json.dumps({'duration': round(dur, 3), 'voice': voice, 'speed': speed, 'lines': lines}, indent=1))
    print(f'data/narration.wav ({dur:.2f} s, {voice} x{speed}) + data/lines.json. Next: words.py')


if __name__ == '__main__':
    main()
