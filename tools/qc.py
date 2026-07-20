#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qc.py — post-render quality gate for finished videos.

Runs AFTER wordedit.py and BEFORE the Telegram approval. Catches the
failures that look fine in code but ruin an upload: missing audio
stream, narration cut off, long dead silences, black stretches, and
loudness far from YouTube's -14 LUFS.

Checklist ported from OpenMontage's mandatory post-render self-review
(skills/pipelines/explainer/compose-director.md, step 6), re-implemented
for this pipeline with plain ffmpeg/ffprobe.

Checks
------
  probe      FAIL if file unreadable / no video stream / NO AUDIO STREAM
  duration   FAIL if far from --vo audio length (default tolerance 5% or 2s)
  silence    WARN for silences > --silence-sec (default 1.5s) inside the video
  black      WARN for black stretches > 0.4s
  loudness   WARN if integrated loudness outside -14 +/- 3 LUFS (EBU R128)
  peak       WARN if true peak above -1 dBTP (clipping risk)
  frames     writes N evenly spaced JPGs to <outdir>/frames/ for human review
  script     (optional, needs faster-whisper) transcribe the rendered audio
             and compare against --script: FAIL if < 60% of script words
             covered, WARN if 60-85%; also checks the script's ending words
             actually occur near the end (catches cut-off endings).

Usage
-----
  python qc.py out/video_16x9.mp4 --vo vo.wav --script script.txt
  python qc.py out/video_16x9.mp4 --outdir qc_video1
  python qc.py --self-test          # offline: builds defect videos, verifies detection

Exit code 0 = no FAIL (WARNs allowed), 1 = at least one FAIL, 2 = usage error.
Writes <outdir>/qc_report.txt and qc_report.json.
Windows-safe: UTF-8 files, ASCII console.
Dependencies: ffmpeg + ffprobe on PATH. faster-whisper optional.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"


@dataclass
class Check:
    name: str
    status: str
    detail: str


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def probe(video: Path) -> tuple[dict, list[Check]]:
    checks: list[Check] = []
    r = _run(["ffprobe", "-v", "quiet", "-print_format", "json",
              "-show_format", "-show_streams", str(video)])
    if r.returncode != 0 or not r.stdout.strip():
        checks.append(Check("probe", FAIL, "ffprobe cannot read the file"))
        return {}, checks
    info = json.loads(r.stdout)
    streams = info.get("streams", [])
    v = [s for s in streams if s.get("codec_type") == "video"]
    a = [s for s in streams if s.get("codec_type") == "audio"]
    size = int((info.get("format") or {}).get("size") or 0)
    dur = float((info.get("format") or {}).get("duration") or 0)
    if not v:
        checks.append(Check("probe", FAIL, "no video stream"))
    if not a:
        checks.append(Check("probe", FAIL,
                            "NO AUDIO STREAM - render did not embed audio; fix and re-render"))
    if size <= 0:
        checks.append(Check("probe", FAIL, "zero-byte file"))
    if v and a and size > 0:
        w = v[0].get("width")
        h = v[0].get("height")
        checks.append(Check("probe", PASS,
                            f"{w}x{h}, {dur:.1f}s, {size/1e6:.1f} MB, audio present"))
    meta = {"duration": dur, "width": v[0].get("width") if v else 0,
            "height": v[0].get("height") if v else 0, "has_audio": bool(a)}
    return meta, checks


def duration_vs_vo(video_dur: float, vo: Path | None, tol_pct: float, tol_abs: float) -> Check:
    if vo is None:
        return Check("duration", SKIP, "no --vo given; duration not compared")
    r = _run(["ffprobe", "-v", "quiet", "-print_format", "json",
              "-show_format", str(vo)])
    if r.returncode != 0:
        return Check("duration", WARN, f"could not probe {vo}")
    vo_dur = float((json.loads(r.stdout).get("format") or {}).get("duration") or 0)
    if vo_dur <= 0:
        return Check("duration", WARN, f"{vo} has zero duration")
    diff = abs(video_dur - vo_dur)
    tol = max(vo_dur * tol_pct / 100.0, tol_abs)
    detail = f"video {video_dur:.1f}s vs narration {vo_dur:.1f}s (diff {diff:.1f}s, tol {tol:.1f}s)"
    return Check("duration", PASS if diff <= tol else FAIL, detail)


def detect_silence(video: Path, min_sec: float) -> Check:
    r = _run(["ffmpeg", "-v", "info", "-i", str(video),
              "-af", f"silencedetect=noise=-30dB:d={min_sec}",
              "-f", "null", "-"])
    spans = re.findall(r"silence_start:\s*([0-9.]+)", r.stderr)
    durs = [float(x) for x in re.findall(r"silence_duration:\s*([0-9.]+)", r.stderr)]
    # ignore a silence that begins in the last second (natural fade-out)
    total = _media_duration(video)
    keep = [(float(s), d) for s, d in zip(spans, durs) if float(s) < max(0.0, total - 1.0)]
    if not keep:
        return Check("silence", PASS, f"no silence >= {min_sec:g}s")
    desc = ", ".join(f"{d:.1f}s@{s:.1f}s" for s, d in keep[:5])
    more = "" if len(keep) <= 5 else f" (+{len(keep)-5} more)"
    return Check("silence", WARN, f"{len(keep)} long silence(s): {desc}{more}")


def detect_black(video: Path, min_sec: float = 0.4) -> Check:
    r = _run(["ffmpeg", "-v", "info", "-i", str(video),
              "-vf", f"blackdetect=d={min_sec}:pic_th=0.98",
              "-f", "null", "-"])
    spans = re.findall(r"black_start:([0-9.]+).*?black_duration:([0-9.]+)", r.stderr)
    if not spans:
        return Check("black", PASS, f"no black stretch >= {min_sec:g}s")
    desc = ", ".join(f"{float(d):.1f}s@{float(s):.1f}s" for s, d in spans[:5])
    more = "" if len(spans) <= 5 else f" (+{len(spans)-5} more)"
    return Check("black", WARN, f"{len(spans)} black stretch(es): {desc}{more}")


def loudness(video: Path) -> list[Check]:
    r = _run(["ffmpeg", "-v", "info", "-i", str(video),
              "-af", "ebur128=peak=true", "-f", "null", "-"])
    checks: list[Check] = []
    # ffmpeg prints many running "I: x LUFS" lines and then a final
    # summary line - the LAST match is the integrated value we want.
    all_I = re.findall(r"I:\s*(-?[0-9.]+)\s*LUFS", r.stderr)
    if all_I:
        i = float(all_I[-1])
        st = PASS if -17.0 <= i <= -11.0 else WARN
        hint = "" if st == PASS else " (YouTube target ~ -14 LUFS; adjust gain in wordedit)"
        checks.append(Check("loudness", st, f"integrated {i:.1f} LUFS{hint}"))
    else:
        checks.append(Check("loudness", SKIP, "could not parse EBU R128 output"))
    peaks = re.findall(r"Peak:\s*(-?[0-9.]+)\s*dBFS", r.stderr)
    if peaks:
        p = max(float(x) for x in peaks)
        st = PASS if p <= -1.0 else WARN
        hint = "" if st == PASS else " (true peak above -1 dBTP - clipping risk)"
        checks.append(Check("peak", st, f"true peak {p:.1f} dBFS{hint}"))
    else:
        checks.append(Check("peak", SKIP, "could not parse true peak"))
    return checks


def sample_frames(video: Path, outdir: Path, n: int) -> Check:
    total = _media_duration(video)
    if total <= 0:
        return Check("frames", SKIP, "unknown duration; no frames sampled")
    frames_dir = outdir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    made = 0
    for i in range(n):
        t = total * (i + 0.5) / n
        dest = frames_dir / f"frame_{i+1:02d}_{t:05.1f}s.jpg"
        r = _run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video),
                  "-frames:v", "1", "-vf", "scale=640:-2", str(dest)])
        if r.returncode == 0 and dest.exists():
            made += 1
    st = PASS if made == n else (WARN if made else FAIL)
    return Check("frames", st, f"{made}/{n} review frames in {frames_dir}")


def _media_duration(path: Path) -> float:
    r = _run(["ffprobe", "-v", "quiet", "-print_format", "json",
              "-show_format", str(path)])
    if r.returncode != 0:
        return 0.0
    return float((json.loads(r.stdout).get("format") or {}).get("duration") or 0)


# ---------------------------------------------------------------------------
# Optional: round-trip transcription vs script (needs faster-whisper)
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"[\w\u0900-\u097F]+", re.UNICODE)


def _words(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(text)]


def script_roundtrip(video: Path, script: Path | None, outdir: Path,
                     lang: str, model_size: str) -> Check:
    if script is None:
        return Check("script", SKIP, "no --script given; round-trip check not run")
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError:
        return Check("script", SKIP,
                     "faster-whisper not installed - round-trip check NOT run "
                     "(pip install faster-whisper)")
    wav = outdir / "qc_audio.wav"
    r = _run(["ffmpeg", "-v", "error", "-y", "-i", str(video),
              "-vn", "-ac", "1", "-ar", "16000", str(wav)])
    if r.returncode != 0:
        return Check("script", FAIL, "could not extract audio for transcription")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(str(wav), language=lang or None)
    hyp = " ".join(seg.text for seg in segments)
    ref_words = _words(Path(script).read_text(encoding="utf-8"))
    hyp_words = _words(hyp)
    if not ref_words:
        return Check("script", SKIP, "script file has no words")
    ratio = len(hyp_words) / len(ref_words)
    tail_ok = _tail_present(ref_words, hyp_words)
    detail = (f"transcribed {len(hyp_words)} vs script {len(ref_words)} words "
              f"({ratio*100:.0f}%); ending {'found' if tail_ok else 'NOT found'} near end")
    if ratio < 0.60 or not tail_ok:
        return Check("script", FAIL, detail + " - narration likely cut off or missing")
    if ratio < 0.85:
        return Check("script", WARN, detail)
    return Check("script", PASS, detail)


def _tail_present(ref: list[str], hyp: list[str], n: int = 3) -> bool:
    """Do any of the script's last n words occur in the last 20% of the
    transcript? Loose on purpose - ASR mangles words but rarely position."""
    if not hyp:
        return False
    tail_ref = set(ref[-n:])
    tail_hyp = hyp[-max(5, len(hyp) // 5):]
    return any(w in tail_ref for w in tail_hyp)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_qc(video: Path, vo: Path | None, script: Path | None, outdir: Path,
           frames: int, silence_sec: float, tol_pct: float, tol_abs: float,
           lang: str, model_size: str) -> int:
    outdir.mkdir(parents=True, exist_ok=True)
    checks: list[Check] = []

    meta, probe_checks = probe(video)
    checks += probe_checks
    hard_broken = any(c.status == FAIL for c in probe_checks)

    if not hard_broken:
        checks.append(duration_vs_vo(meta.get("duration", 0.0), vo, tol_pct, tol_abs))
        checks.append(detect_silence(video, silence_sec))
        checks.append(detect_black(video))
        checks += loudness(video)
        checks.append(sample_frames(video, outdir, frames))
        checks.append(script_roundtrip(video, script, outdir, lang, model_size))
    else:
        checks.append(Check("rest", SKIP, "probe failed hard; remaining checks skipped"))

    fails = [c for c in checks if c.status == FAIL]
    warns = [c for c in checks if c.status == WARN]
    verdict = "REJECT - fix and re-render" if fails else \
              ("PASS with warnings - review before approving" if warns else "PASS")

    lines = [f"QC report for {video}", "=" * 60]
    for c in checks:
        lines.append(f"[{c.status:<4}] {c.name:<9} {c.detail}")
    lines += ["-" * 60, f"VERDICT: {verdict}",
              f"({len(fails)} fail, {len(warns)} warn)"]
    report = "\n".join(lines)
    print(report)
    (outdir / "qc_report.txt").write_text(report + "\n", encoding="utf-8")
    (outdir / "qc_report.json").write_text(
        json.dumps({"video": str(video), "verdict": verdict,
                    "checks": [asdict(c) for c in checks]},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")
    return 1 if fails else 0


# ---------------------------------------------------------------------------
# Self-test: build defect videos with ffmpeg, verify each check fires
# ---------------------------------------------------------------------------

def self_test() -> int:
    import tempfile
    ok = True

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" -- {detail}" if detail and not cond else ""))
        ok = ok and cond

    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        print("ffmpeg/ffprobe missing - cannot self-test")
        return 1

    print("qc self-test (builds defect videos, verifies detection)")
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)

        # A) good video: tone throughout, colour frames, 6s
        good = tdp / "good.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y",
                        "-f", "lavfi", "-i", "testsrc2=s=640x360:d=6",
                        "-f", "lavfi", "-i",
                        "sine=frequency=300:duration=6,volume=0.5",
                        "-shortest", "-pix_fmt", "yuv420p", str(good)], check=True)
        vo6 = tdp / "vo6.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                        "-i", "sine=frequency=300:duration=6", str(vo6)], check=True)
        rc = run_qc(good, vo6, None, tdp / "qc_good", frames=4,
                    silence_sec=1.5, tol_pct=5, tol_abs=2, lang="hi", model_size="base")
        print()
        check("good video exits 0", rc == 0)
        rep = json.loads((tdp / "qc_good" / "qc_report.json").read_text(encoding="utf-8"))
        by = {c["name"]: c for c in rep["checks"]}

        def last(name):  # loudness/peak appear once; helper for clarity
            return by.get(name, {"status": "?", "detail": ""})
        check("good: probe PASS", last("probe")["status"] == PASS, last("probe")["detail"])
        check("good: duration PASS", last("duration")["status"] == PASS, last("duration")["detail"])
        check("good: silence PASS", last("silence")["status"] == PASS, last("silence")["detail"])
        check("good: frames written",
              last("frames")["status"] == PASS and
              len(list((tdp / "qc_good" / "frames").glob("*.jpg"))) == 4)
        check("good: script check SKIP (no faster-whisper here or no --script)",
              last("script")["status"] == SKIP, last("script")["detail"])

        # B) no-audio video -> probe must FAIL and gate the rest
        noaud = tdp / "noaudio.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y",
                        "-f", "lavfi", "-i", "testsrc2=s=640x360:d=4",
                        "-pix_fmt", "yuv420p", str(noaud)], check=True)
        rc = run_qc(noaud, None, None, tdp / "qc_noaud", 2, 1.5, 5, 2, "hi", "base")
        print()
        check("no-audio video exits 1 (REJECT)", rc == 1)

        # C) defects: 2s dead silence in the middle + 1s black + short vs vo
        defect = tdp / "defect.mp4"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y",
             "-f", "lavfi", "-i",
             "testsrc2=s=640x360:d=6,drawbox=enable='between(t,2,3)':c=black:t=fill",
             "-f", "lavfi", "-i",
             "sine=frequency=300:duration=6,volume='if(between(t,2,4.4),0,0.5)':eval=frame",
             "-shortest", "-pix_fmt", "yuv420p", str(defect)], check=True)
        vo9 = tdp / "vo9.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                        "-i", "sine=frequency=300:duration=9", str(vo9)], check=True)
        rc = run_qc(defect, vo9, None, tdp / "qc_defect", 2, 1.5, 5, 2, "hi", "base")
        print()
        rep = json.loads((tdp / "qc_defect" / "qc_report.json").read_text(encoding="utf-8"))
        by = {c["name"]: c for c in rep["checks"]}
        check("defect: duration FAIL (6s video vs 9s vo)", by["duration"]["status"] == FAIL,
              by["duration"]["detail"])
        check("defect: long silence detected", by["silence"]["status"] == WARN,
              by["silence"]["detail"])
        check("defect: black stretch detected", by["black"]["status"] == WARN,
              by["black"]["detail"])
        check("defect: overall exit 1", rc == 1)

    print("RESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
    print("NOTE: the script round-trip path needs faster-whisper; on the real PC run "
          "once with --script to exercise it.")
    return 0 if ok else 1


# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", nargs="?", help="rendered video (out/xxx.mp4)")
    ap.add_argument("--vo", help="narration wav to compare duration against")
    ap.add_argument("--script", help="script .txt for the round-trip transcription check")
    ap.add_argument("--outdir", help="report folder (default <video>_qc)")
    ap.add_argument("--frames", type=int, default=8, help="review frames to sample (default 8)")
    ap.add_argument("--silence-sec", type=float, default=1.5,
                    help="flag silences longer than this (default 1.5)")
    ap.add_argument("--tol-pct", type=float, default=5.0, help="duration tolerance %% (default 5)")
    ap.add_argument("--tol-abs", type=float, default=2.0, help="duration tolerance seconds (default 2)")
    ap.add_argument("--lang", default="hi", help="ASR language for round-trip (default hi)")
    ap.add_argument("--model-size", default="base", help="faster-whisper size (default base)")
    ap.add_argument("--self-test", action="store_true", help="offline self-test with defect videos")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.video:
        ap.print_help()
        return 2
    video = Path(args.video)
    if not video.exists():
        print(f"ERROR: {video} not found")
        return 2
    outdir = Path(args.outdir) if args.outdir else video.with_name(video.stem + "_qc")
    return run_qc(video, Path(args.vo) if args.vo else None,
                  Path(args.script) if args.script else None,
                  outdir, args.frames, args.silence_sec,
                  args.tol_pct, args.tol_abs, args.lang, args.model_size)


if __name__ == "__main__":
    raise SystemExit(main())
