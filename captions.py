#!/usr/bin/env python3
"""TikTok-style word-highlight captions -> captions.ass

Text comes from the brief's script (exact spelling); timing comes from the audio:
  1. faster-whisper word timestamps on ./voice, aligned to the script words (difflib)
  2. fallback: proportional estimate from word length + punctuation pauses
Usage: SCRIPT="..." python3 captions.py voice captions.ass
Prints: caption_timing=<whisper|estimate>
"""
import difflib
import json
import os
import re
import subprocess
import sys

VOICE, OUT = sys.argv[1], sys.argv[2]
SCRIPT = os.environ.get("SCRIPT", "").strip()
MAX_WORDS = 3          # words per on-screen chunk
MAX_CHARS = 14         # keep chunks short enough for one big line
FONT = os.environ.get("CAPTION_FONT", "Anton")
HIGHLIGHT = "&H00F2FF&"   # active word (ASS BGR) - TikTok yellow
WHITE = "&HFFFFFF&"


def duration(path):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                   "-of", "csv=p=0", path], text=True)
    return float(out.strip())


def norm(w):
    return re.sub(r"[^\w']", "", w.lower())


def whisper_words(path):
    from faster_whisper import WhisperModel  # installed in the Action
    model = WhisperModel(os.environ.get("WHISPER_MODEL", "base.en"), device="cpu", compute_type="int8")
    segments, _ = model.transcribe(path, word_timestamps=True, vad_filter=False, beam_size=1)
    return [(w.word.strip(), w.start, w.end) for s in segments for w in (s.words or []) if w.word.strip()]


def align(script_words, heard, total):
    """Give every script word a (start, end) from matching heard words; interpolate the rest."""
    a = [norm(w) for w in script_words]
    b = [norm(w) for w, _, _ in heard]
    times = [None] * len(script_words)
    for blk in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            _, s, e = heard[blk.b + k]
            times[blk.a + k] = (s, e)
    matched = sum(t is not None for t in times)
    if matched < max(2, len(script_words) * 0.5):
        raise ValueError(f"only {matched}/{len(script_words)} words aligned")
    # interpolate gaps between known anchors
    i = 0
    while i < len(times):
        if times[i] is not None:
            i += 1
            continue
        j = i
        while j < len(times) and times[j] is None:
            j += 1
        left = times[i - 1][1] if i > 0 else 0.0
        right = times[j][0] if j < len(times) else min(total, left + 0.4 * (j - i))
        step = max(right - left, 0.05) / (j - i)
        for k in range(i, j):
            times[k] = (left + step * (k - i), left + step * (k - i + 1))
        i = j
    return times


def estimate(script_words, total):
    """No ASR: spread words over the voice duration by length, with pauses at punctuation."""
    weights = []
    for w in script_words:
        wt = 0.25 + 0.06 * len(norm(w))
        if re.search(r"[.!?]$", w):
            wt += 0.35
        elif re.search(r"[,;:—-]$", w):
            wt += 0.15
        weights.append(wt)
    speak = max(total - 0.3, 0.5)
    scale = speak / sum(weights)
    t, out = 0.15, []
    for wt in weights:
        out.append((t, t + wt * scale * 0.85))
        t += wt * scale
    return out


def chunks(words, times):
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(i)
        text_len = len(" ".join(words[j] for j in cur))
        if len(cur) >= MAX_WORDS or text_len >= MAX_CHARS or re.search(r"[.!?,;:]$", w):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def ts(sec):
    sec = max(sec, 0)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def clean(w):
    # strip ASS control characters and trailing punctuation for display
    w = w.replace("{", "(").replace("}", ")").replace("\\", "")
    return re.sub(r"[,;:.]+$", "", w).upper()  # keep ! and ?, drop the rest


def main():
    if not SCRIPT:
        print("caption_timing=none")
        return
    total = duration(VOICE)
    words = SCRIPT.split()
    timing = "estimate"
    try:
        times = align(words, whisper_words(VOICE), total)
        timing = "whisper"
    except Exception as e:  # missing package, model download, poor match...
        print(f"whisper alignment unavailable ({e}); using estimate", file=sys.stderr)
        times = estimate(words, total)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{FONT},132,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,2,0,1,11,5,2,70,70,600,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    groups = chunks(words, times)
    for g_i, g in enumerate(groups):
        g_end = times[groups[g_i + 1][0]][0] if g_i + 1 < len(groups) else times[g[-1]][1] + 0.35
        for k, idx in enumerate(g):
            start = times[idx][0]
            end = times[g[k + 1]][0] if k + 1 < len(g) else g_end
            if end - start < 0.05:
                end = start + 0.05
            parts = []
            for j in g:
                colour = HIGHLIGHT if j == idx else WHITE
                parts.append(f"{{\\c{colour}}}{clean(words[j])}")
            pop = r"{\fscx82\fscy82\t(0,90,\fscx100\fscy100)}" if k == 0 else ""
            lines.append(f"Dialogue: 0,{ts(start)},{ts(end)},Cap,,0,0,0,,{pop}{' '.join(parts)}")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(lines) + "\n")
    print(f"caption_timing={timing}")
    print(json.dumps({"words": len(words), "chunks": len(groups), "timing": timing}), file=sys.stderr)


if __name__ == "__main__":
    main()
