#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hindi_text.py — Hindi/Hinglish script helpers for the pipeline.

Two jobs:
  1. split_sentences(text)      -> sentence list that understands the
     Devanagari danda (। ॥) as well as . ! ? …  (for TTS chunking and
     for per-sentence duration tables).
  2. estimate_speech_seconds()  -> rough narration length from raw text,
     using per-script character weights (Devanagari base letters count
     ~1.8x a Latin letter, digits ~3.5x, combining matras 0).

The weight model is adapted from the OmniVoice project's
RuleDurationEstimator (Apache-2.0, k2-fsa/OmniVoice). The default
calibration (45 ms per weight unit) is a STARTING GUESS — after the
first real narration, run:

    python hindi_text.py script.txt --calibrate vo_timings.json

and it prints the measured ms-per-unit for THIS voice. Use that number
with --ms-per-unit from then on.

CLI:
    python hindi_text.py script.txt
    python hindi_text.py script.txt --ms-per-unit 52
    python hindi_text.py script.txt --calibrate vo_timings.json
    python hindi_text.py --self-test

No dependencies outside the standard library. Windows-safe: every file
is opened with encoding="utf-8".
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

# --------------------------------------------------------------------------
# Sentence splitting
# --------------------------------------------------------------------------

# Hard sentence terminators. Includes the Devanagari danda and double
# danda, which standard "split on . ! ?" logic silently ignores — the
# single biggest chunking bug for Hindi scripts.
_TERMINATORS = ".!?…।॥"

# Abbreviations whose trailing dot must NOT end a sentence. Lowercased,
# without the dot. Hindi scripts mix in English tech terms constantly,
# so these show up even in Devanagari text.
_ABBREVIATIONS = {
    "e.g", "i.e", "vs", "etc", "dr", "mr", "mrs", "ms", "st",
    "approx", "no", "fig", "vol", "min", "max", "sec", "hrs",
}


def split_sentences(text: str) -> list[str]:
    """Split text into sentences, Devanagari-aware.

    Rules:
      - . ! ? … । ॥ end a sentence when followed by whitespace or EOL.
      - A dot between two digits (3.14) never splits.
      - A dot right after a known abbreviation never splits.
      - Runs of terminators ("?!", "।।") stay attached to the sentence.
    Returns stripped, non-empty sentences in order.
    """
    sentences: list[str] = []
    buf: list[str] = []
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        buf.append(ch)
        if ch in _TERMINATORS:
            # absorb a run of terminators + closing quotes/brackets
            j = i + 1
            while j < n and (text[j] in _TERMINATORS or text[j] in "\"')]}»”’"):
                buf.append(text[j])
                j += 1
            nxt = text[j] if j < n else ""
            if ch == "." and _protected_dot(text, i):
                i += 1
                continue
            if nxt == "" or nxt.isspace():
                s = "".join(buf).strip()
                if s:
                    sentences.append(s)
                buf = []
                i = j
                continue
            i = j
            continue
        i += 1
    tail = "".join(buf).strip()
    if tail:
        sentences.append(tail)
    return sentences


def _protected_dot(text: str, i: int) -> bool:
    """True if the '.' at index i is a decimal point or an abbreviation dot."""
    prev = text[i - 1] if i > 0 else ""
    nxt = text[i + 1] if i + 1 < len(text) else ""
    if prev.isdigit() and nxt.isdigit():
        return True
    # word immediately before the dot
    m = re.search(r"([A-Za-z][A-Za-z.]{0,7})$", text[max(0, i - 9):i])
    if m and m.group(1).lower().rstrip(".") in _ABBREVIATIONS:
        return True
    return False


# --------------------------------------------------------------------------
# Duration estimation
# --------------------------------------------------------------------------

# Weight per character class, relative to one Latin letter (~1.0).
# Adapted from k2-fsa/OmniVoice omnivoice/utils/duration.py (Apache-2.0):
#   indic base letters 1.8, digits 3.5 (they are read out as words),
#   punctuation 0.5 (pause), space 0.2 (word gap), combining marks 0.
_W_LATIN = 1.0
_W_DEVANAGARI = 1.8
_W_DIGIT = 3.5
_W_PUNCT = 0.5
_W_SPACE = 0.2
_W_MARK = 0.0

DEFAULT_MS_PER_UNIT = 45.0  # STARTING GUESS. Calibrate against real audio.


def text_units(text: str) -> float:
    """Sum of character weights for `text` (the abstract 'speech length')."""
    total = 0.0
    for ch in text:
        if ch.isspace():
            total += _W_SPACE
        elif unicodedata.category(ch).startswith("M"):
            # Devanagari matras are category Mn/Mc but combining class 0,
            # so category — not unicodedata.combining() — is the right test.
            total += _W_MARK
        elif ch.isdigit():
            total += _W_DIGIT
        elif "\u0900" <= ch <= "\u097F":
            total += _W_DEVANAGARI
        elif ch.isalpha():
            total += _W_LATIN
        else:
            total += _W_PUNCT
    return total


def estimate_speech_seconds(text: str, ms_per_unit: float = DEFAULT_MS_PER_UNIT) -> float:
    return text_units(text) * ms_per_unit / 1000.0


def word_count(text: str) -> int:
    return len(re.findall(r"[\w\u0900-\u097F]+", text, flags=re.UNICODE))


# --------------------------------------------------------------------------
# Calibration against real narration timings
# --------------------------------------------------------------------------

def _audio_seconds_from_timings(path: Path) -> float:
    """Best-effort audio length from a vo_timings.json.

    ASSUMPTION (flagged, verify against your narrate.py output): the file
    is either a list of word objects, or an object holding such a list
    under "words" / "segments" / "timings", each word carrying an end
    time under one of: end / e / end_time / until. A top-level
    "duration" field, if present, wins outright.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for k in ("duration", "audio_duration", "total_seconds"):
            v = data.get(k)
            if isinstance(v, (int, float)) and v > 0:
                return float(v)
        for k in ("words", "segments", "timings", "items"):
            if isinstance(data.get(k), list):
                data = data[k]
                break
    if not isinstance(data, list):
        raise ValueError("timings JSON shape not recognised (see --help)")
    end = 0.0
    for w in data:
        if not isinstance(w, dict):
            continue
        for k in ("end", "e", "end_time", "until"):
            v = w.get(k)
            if isinstance(v, (int, float)):
                end = max(end, float(v))
    if end <= 0:
        raise ValueError("no usable end-times found in timings JSON")
    return end


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _fmt_mmss(seconds: float) -> str:
    m, s = divmod(int(round(seconds)), 60)
    return f"{m:d}:{s:02d}"


def _self_test() -> int:
    ok = True

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" -- {detail}" if detail and not cond else ""))
        ok = ok and cond

    print("hindi_text self-test")
    s = split_sentences("यह पहला वाक्य है। दूसरा भी! Third one? हाँ॥")
    check("danda + latin split -> 4 sentences", len(s) == 4, repr(s))
    s2 = split_sentences("Pi की value 3.14 होती है. ठीक है।")
    check("decimal 3.14 not split", len(s2) == 2 and "3.14" in s2[0], repr(s2))
    s2b = split_sentences("approx. के बाद वाक्य चलता रहता है यहाँ तक।")
    check("'approx.' protected as abbreviation", len(s2b) == 1, repr(s2b))
    s3 = split_sentences("e.g. यह example है। बस।")
    check("abbrev 'e.g.' not split", len(s3) == 2, repr(s3))
    s4 = split_sentences("सच में?! हाँ।")
    check("terminator run ?! stays attached", len(s4) == 2 and s4[0].endswith("?!"), repr(s4))

    hi = "नमस्ते दुनिया"       # base letters + matras
    en = "hello world"
    check("devanagari weighs more than latin (same idea-length)",
          text_units(hi) > text_units(en),
          f"hi={text_units(hi):.1f} en={text_units(en):.1f}")
    check("digits weigh heavy", text_units("2026") > text_units("abcd"))
    check("combining matras weigh 0",
          abs(text_units("कि") - (_W_DEVANAGARI + _W_MARK)) < 1e-6,
          f"units={text_units('कि')}")
    est = estimate_speech_seconds("नमस्ते, यह एक छोटा टेस्ट वाक्य है।")
    check("estimate is a sane positive number", 0.5 < est < 10.0, f"{est:.2f}s")
    print("RESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    try:  # Windows console: force UTF-8 so Devanagari prints
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script", nargs="?", help="script .txt file (UTF-8)")
    ap.add_argument("--ms-per-unit", type=float, default=DEFAULT_MS_PER_UNIT,
                    help=f"calibration constant (default {DEFAULT_MS_PER_UNIT}; measure with --calibrate)")
    ap.add_argument("--calibrate", metavar="VO_TIMINGS_JSON",
                    help="measure ms-per-unit from a real narration's timings JSON")
    ap.add_argument("--self-test", action="store_true", help="run offline self-tests and exit")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()
    if not args.script:
        ap.print_help()
        return 2

    text = Path(args.script).read_text(encoding="utf-8")
    units = text_units(text)
    words = word_count(text)
    sents = split_sentences(text)

    if args.calibrate:
        secs = _audio_seconds_from_timings(Path(args.calibrate))
        measured = secs * 1000.0 / units if units else 0.0
        print(f"script units      : {units:,.0f}")
        print(f"real audio length : {secs:,.1f} s  ({_fmt_mmss(secs)})")
        print(f"MEASURED ms/unit  : {measured:.1f}")
        print(f"next time run with: --ms-per-unit {measured:.1f}")
        return 0

    est = units * args.ms_per_unit / 1000.0
    print(f"file        : {args.script}")
    print(f"words       : {words:,}")
    print(f"sentences   : {len(sents)}")
    print(f"est. length : {_fmt_mmss(est)}  ({est:,.0f} s at {args.ms_per_unit:g} ms/unit)")
    print(f"NOTE: estimate only. Calibrate after first real narration (--calibrate).")
    print()
    print(f"{'#':>3}  {'sec':>5}  {'cum':>6}  sentence")
    cum = 0.0
    for i, s in enumerate(sents, 1):
        d = estimate_speech_seconds(s, args.ms_per_unit)
        cum += d
        head = s.replace("\n", " ")
        if len(head) > 48:
            head = head[:47] + "…"
        print(f"{i:>3}  {d:>5.1f}  {_fmt_mmss(cum):>6}  {head}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
