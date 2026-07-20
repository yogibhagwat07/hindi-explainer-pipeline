#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetchclips.py — free stock footage fetcher with a license ledger.

Answers the pipeline's visuals question for the B-ROLL layer:
search several free stock/archive sources for each shot query, download
the best candidates, save a thumbnail per clip, and write a per-clip
LICENSE LEDGER plus a ready-to-paste CREDITS block for the YouTube
description. gatekeeper can later refuse any video whose clips are not
in the ledger.

Sources (v1)
------------
  pexels     needs PEXELS_API_KEY   (free signup, no card)
  pixabay    needs PIXABAY_API_KEY  (free signup, no card)
  nasa       no key                 (public domain; per-item caveat)
  wikimedia  no key                 (per-file license read from API)
  archive    no key                 (archive.org; license URL when present)

License classes and default policy
----------------------------------
  PD       public domain / CC0                    -> allowed
  FREE     platform free license (Pexels/Pixabay) -> allowed
  BY       CC BY, attribution required            -> allowed, credit written
  BY-SA    share-alike                            -> SKIPPED unless --allow-sa
  NC / ND  non-commercial / no-derivatives        -> ALWAYS rejected
  VERIFY   license unknown/unclear                -> SKIPPED unless --allow-verify

Usage
-----
  python fetchclips.py "monsoon mumbai street" "server room" --out clips_raw
  python fetchclips.py --from-json shots.json --out clips_raw
       shots.json = [{"slot": "intro", "query": "sunrise over city"}, ...]
  python fetchclips.py --doctor         # environment check, no network
  python fetchclips.py --self-test      # full offline run with a mock source

Notes
-----
* Endpoints were taken from working adapters in the OpenMontage project
  (repo state July 2026) and re-implemented here from scratch. They are
  UNVERIFIED from this machine (written in an offline sandbox); the
  first online run is the real test. --doctor --net does a light probe.
* Design of the Candidate/source-adapter split follows OpenMontage's
  stock_sources protocol (AGPL-3.0). This file is an independent
  implementation for private, local use in this pipeline.
* Windows-safe: UTF-8 everywhere, ASCII-only console output.
Dependencies: requests, ffmpeg on PATH (ffmpeg only for thumbnails).
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import quote

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # --doctor reports this instead of crashing

USER_AGENT = "HindiExplainerPipeline/1.0 (personal channel tool; contact via source page)"
HTTP_TIMEOUT = 30
DOWNLOAD_TIMEOUT = 300

# ---------------------------------------------------------------------------
# License classification
# ---------------------------------------------------------------------------

PD, FREE, BY, BY_SA, NC_ND, VERIFY = "PD", "FREE", "BY", "BY-SA", "NC/ND", "VERIFY"


def classify_license(text: str) -> str:
    """Map a license string/URL to a policy class. Unknown -> VERIFY."""
    t = (text or "").lower()
    if not t.strip():
        return VERIFY
    if "nc" in re.findall(r"\bnc\b", t) or "noncommercial" in t or "non-commercial" in t or "-nc" in t:
        return NC_ND
    if re.search(r"\bnd\b", t) or "noderiv" in t or "no-deriv" in t or "-nd" in t:
        return NC_ND
    if "publicdomain" in t or "public domain" in t or "cc0" in t or "pdm" in t \
       or "zero/1.0" in t or "mark/1.0" in t:
        return PD
    if "pexels" in t or "pixabay" in t:
        return FREE
    if "sa" in re.findall(r"\bsa\b", t) or "sharealike" in t or "share-alike" in t or "by-sa" in t:
        return BY_SA
    if re.search(r"\bcc\s*by\b", t) or "creativecommons.org/licenses/by/" in t or "attribution" in t:
        return BY
    return VERIFY


def license_allowed(cls: str, allow_sa: bool, allow_verify: bool) -> tuple[bool, str]:
    if cls == NC_ND:
        return False, "NC/ND license - never usable on a monetised channel"
    if cls == BY_SA and not allow_sa:
        return False, "BY-SA (share-alike) skipped by policy (use --allow-sa to override)"
    if cls == VERIFY and not allow_verify:
        return False, "license unclear - skipped (use --allow-verify to keep for manual check)"
    return True, ""


# ---------------------------------------------------------------------------
# Candidate model
# ---------------------------------------------------------------------------

@dataclass
class Candidate:
    source: str
    source_id: str
    source_url: str          # human landing page (for attribution links)
    download_url: str
    title: str = ""
    creator: str = ""
    license: str = ""        # raw license string
    license_class: str = VERIFY
    width: int = 0
    height: int = 0
    duration: float = 0.0    # 0 = unknown
    tags: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def clip_id(self) -> str:
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", str(self.source_id))[:60]
        return f"{self.source}_{safe}"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _get_json(url: str, *, params=None, headers=None) -> Any:
    h = {"User-Agent": USER_AGENT}
    if headers:
        h.update(headers)
    r = requests.get(url, params=params, headers=h, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _download(url: str, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT,
                      headers={"User-Agent": USER_AGENT}) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                if chunk:
                    f.write(chunk)
    return out_path


def _strip_html(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


# ---------------------------------------------------------------------------
# Source: Pexels  (videos/search, Authorization header)
# ---------------------------------------------------------------------------

def search_pexels(query: str, per: int, orientation: str) -> list[Candidate]:
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key:
        return []
    params = {"query": query, "per_page": max(1, min(per, 80))}
    if orientation in ("landscape", "portrait", "square"):
        params["orientation"] = orientation
    data = _get_json("https://api.pexels.com/videos/search",
                     params=params, headers={"Authorization": key})
    out: list[Candidate] = []
    for v in data.get("videos", []) or []:
        files = v.get("video_files") or []
        pick = _pick_pexels_file(files)
        if not pick:
            continue
        out.append(Candidate(
            source="pexels", source_id=str(v.get("id")),
            source_url=v.get("url", "") or "",
            download_url=pick.get("link", "") or "",
            title="", creator=((v.get("user") or {}).get("name") or ""),
            license="Pexels License (free, no attribution required)",
            license_class=FREE,
            width=int(pick.get("width") or 0), height=int(pick.get("height") or 0),
            duration=float(v.get("duration") or 0),
            tags="",
        ))
    return out


def _pick_pexels_file(files: list[dict]) -> Optional[dict]:
    """Prefer the smallest file whose height >= 1080; else the largest."""
    mp4s = [f for f in files if (f.get("file_type") or "").endswith("mp4") and f.get("link")]
    if not mp4s:
        return None
    hd = sorted((f for f in mp4s if (f.get("height") or 0) >= 1080),
                key=lambda f: (f.get("height") or 0))
    if hd:
        return hd[0]
    return max(mp4s, key=lambda f: (f.get("height") or 0))


# ---------------------------------------------------------------------------
# Source: Pixabay videos
# ---------------------------------------------------------------------------

def search_pixabay(query: str, per: int, orientation: str) -> list[Candidate]:
    key = os.environ.get("PIXABAY_API_KEY", "").strip()
    if not key:
        return []
    data = _get_json("https://pixabay.com/api/videos/",
                     params={"key": key, "q": query,
                             "per_page": max(3, min(per, 200)), "safesearch": "true"})
    out: list[Candidate] = []
    for h in data.get("hits", []) or []:
        rend = _pick_pixabay_rendition(h.get("videos") or {})
        if not rend:
            continue
        w, ht = int(rend.get("width") or 0), int(rend.get("height") or 0)
        if orientation == "landscape" and ht > w:
            continue
        if orientation == "portrait" and w > ht:
            continue
        out.append(Candidate(
            source="pixabay", source_id=str(h.get("id")),
            source_url=h.get("pageURL", "") or "",
            download_url=rend.get("url", "") or "",
            title="", creator=h.get("user", "") or "",
            license="Pixabay Content License (free, no attribution required)",
            license_class=FREE,
            width=w, height=ht,
            duration=float(h.get("duration") or 0),
            tags=h.get("tags", "") or "",
        ))
    return out


def _pick_pixabay_rendition(videos: dict) -> Optional[dict]:
    for name in ("large", "medium", "small", "tiny"):
        r = videos.get(name)
        if r and r.get("url"):
            return r
    return None


# ---------------------------------------------------------------------------
# Source: NASA images-api (no key; PD with per-item caveat)
# ---------------------------------------------------------------------------

def search_nasa(query: str, per: int, orientation: str) -> list[Candidate]:
    data = _get_json("https://images-api.nasa.gov/search",
                     params=[("q", query), ("media_type", "video"),
                             ("page_size", str(max(1, min(per, 100)))), ("page", "1")])
    items = ((data.get("collection") or {}).get("items") or [])
    out: list[Candidate] = []
    for item in items:
        meta = (item.get("data") or [{}])[0]
        nasa_id = meta.get("nasa_id") or ""
        href = item.get("href") or ""
        if not nasa_id or not href:
            continue
        try:
            manifest = _get_json(href)  # collection.json -> list of file URLs
        except Exception:
            continue
        dl = _pick_nasa_url(manifest if isinstance(manifest, list) else [])
        if not dl:
            continue
        kw = meta.get("keywords") or []
        out.append(Candidate(
            source="nasa", source_id=nasa_id,
            source_url=f"https://images.nasa.gov/details/{quote(str(nasa_id), safe='')}",
            download_url=dl,
            title=(meta.get("title") or "").strip(),
            creator=(meta.get("photographer") or meta.get("center") or "NASA").strip(),
            license="Public domain (NASA) - CAVEAT: some items include third-party footage; check the item page",
            license_class=PD,
            tags=" ".join(str(k) for k in kw)[:300] if isinstance(kw, list) else str(kw)[:300],
        ))
    return out


def _pick_nasa_url(urls: list) -> str:
    urls = [str(u) for u in urls if str(u).lower().endswith(".mp4")]
    for pref in ("~orig", "~large", "~medium"):
        for u in urls:
            if pref in u:
                return _encode_path(u)
    return _encode_path(urls[0]) if urls else ""


def _encode_path(url: str) -> str:
    # NASA asset paths sometimes contain raw spaces.
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    host, _, path = rest.partition("/")
    return f"{scheme}://{host}/" + quote(path, safe="/%~.-_()")


# ---------------------------------------------------------------------------
# Source: Wikimedia Commons (no key; per-file license via extmetadata)
# ---------------------------------------------------------------------------

_WM_STOP = {"the", "and", "for", "with", "from", "into", "over", "under"}


def search_wikimedia(query: str, per: int, orientation: str) -> list[Candidate]:
    # Commons search ANDs all tokens; cascade full -> 2 longest tokens -> 1.
    tokens = [t for t in re.findall(r"\w+", query) if len(t) >= 3 and t.lower() not in _WM_STOP]
    tokens.sort(key=len, reverse=True)
    cascade = [query]
    if len(tokens) >= 2:
        cascade.append(" ".join(tokens[:2]))
    if tokens:
        cascade.append(tokens[0])
    for q in cascade:
        cands = _wm_one_search(q, per)
        if cands:
            return cands
    return []


def _wm_one_search(q: str, per: int) -> list[Candidate]:
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"filetype:video {q}", "gsrnamespace": 6,
        "gsrlimit": max(1, min(per, 50)),
        "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata|mediatype",
    }
    try:
        data = _get_json("https://commons.wikimedia.org/w/api.php", params=params)
    except Exception:
        return []
    pages = list(((data.get("query") or {}).get("pages") or {}).values())
    pages.sort(key=lambda p: int(p.get("index", 0)))
    out: list[Candidate] = []
    for p in pages:
        info = (p.get("imageinfo") or [{}])[0]
        if (info.get("mediatype") or "").upper() not in ("VIDEO", ""):
            continue
        url = info.get("url") or ""
        if not url:
            continue
        meta = info.get("extmetadata") or {}
        lic_short = _strip_html(((meta.get("LicenseShortName") or {}).get("value")) or "")
        usage = _strip_html(((meta.get("UsageTerms") or {}).get("value")) or "")
        artist = _strip_html(((meta.get("Artist") or {}).get("value")) or "")
        lic = lic_short or usage or "Wikimedia Commons (license unstated)"
        out.append(Candidate(
            source="wikimedia", source_id=str(p.get("pageid") or p.get("title") or ""),
            source_url=info.get("descriptionurl") or "",
            download_url=url,
            title=str(p.get("title") or "").replace("File:", ""),
            creator=artist, license=lic, license_class=classify_license(lic),
            width=int(info.get("width") or 0), height=int(info.get("height") or 0),
        ))
    return out


# ---------------------------------------------------------------------------
# Source: archive.org (no key)
# ---------------------------------------------------------------------------

def search_archive(query: str, per: int, orientation: str) -> list[Candidate]:
    params = {
        "q": f"({query}) AND mediatype:(movies)",
        "fl[]": ["identifier", "title", "creator", "licenseurl"],
        "rows": max(1, min(per, 50)), "page": 1, "output": "json",
    }
    data = _get_json("https://archive.org/advancedsearch.php", params=params)
    docs = ((data.get("response") or {}).get("docs") or [])
    out: list[Candidate] = []
    for d in docs:
        ident = d.get("identifier") or ""
        if not ident:
            continue
        try:
            meta = _get_json(f"https://archive.org/metadata/{quote(ident, safe='')}")
        except Exception:
            continue
        fname, length = _pick_archive_file(meta.get("files") or [])
        if not fname:
            continue
        licurl = d.get("licenseurl") or (meta.get("metadata") or {}).get("licenseurl") or ""
        lic = licurl or "archive.org item (license unstated - verify on item page)"
        creator = d.get("creator")
        if isinstance(creator, list):
            creator = ", ".join(str(c) for c in creator[:2])
        out.append(Candidate(
            source="archive", source_id=ident,
            source_url=f"https://archive.org/details/{ident}",
            download_url=f"https://archive.org/download/{quote(ident, safe='')}/{quote(fname, safe='')}",
            title=str(d.get("title") or ident), creator=str(creator or ""),
            license=lic, license_class=classify_license(lic),
            duration=length,
        ))
    return out


def _pick_archive_file(files: list[dict]) -> tuple[str, float]:
    """Pick a reasonable mp4: prefer h.264/512Kb derivatives (small, playable)."""
    mp4s = [f for f in files if str(f.get("name", "")).lower().endswith(".mp4")]
    if not mp4s:
        return "", 0.0

    def rank(f: dict) -> tuple:
        fmt = str(f.get("format", "")).lower()
        return (0 if "h.264" in fmt or "512" in fmt else 1, _to_float(f.get("size"), 1e15))

    best = sorted(mp4s, key=rank)[0]
    return str(best.get("name")), _to_float(best.get("length"), 0.0)


def _to_float(v, default=0.0) -> float:
    try:
        if isinstance(v, str) and ":" in v:  # "mm:ss" style lengths
            parts = [float(p) for p in v.split(":")]
            s = 0.0
            for p in parts:
                s = s * 60 + p
            return s
        return float(v)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Source: mock (offline self-test only)
# ---------------------------------------------------------------------------

def search_mock(query: str, per: int, orientation: str) -> list[Candidate]:
    lic_by_q = {
        "sa_case": ("CC BY-SA 4.0", None),
        "nc_case": ("CC BY-NC 4.0", None),
        "verify_case": ("", None),
    }
    lic, _ = lic_by_q.get(query, ("CC BY 4.0", None))
    return [Candidate(
        source="mock", source_id=f"{query}_{i}",
        source_url=f"https://example.org/{query}/{i}",
        download_url="mock://color", title=f"Mock clip {i} for {query}",
        creator="Mock Creator", license=lic, license_class=classify_license(lic),
        width=1280, height=720, duration=3.0, tags=query,
    ) for i in range(1, min(per, 2) + 1)]


SOURCES: dict[str, Callable[[str, int, str], list[Candidate]]] = {
    "pexels": search_pexels,
    "pixabay": search_pixabay,
    "nasa": search_nasa,
    "wikimedia": search_wikimedia,
    "archive": search_archive,
    "mock": search_mock,   # offline testing only; not in DEFAULT_SOURCES
}
DEFAULT_SOURCES = ["pexels", "pixabay", "nasa", "wikimedia", "archive"]


# ---------------------------------------------------------------------------
# Pipeline: search -> filter -> download -> thumbnail -> ledger -> credits
# ---------------------------------------------------------------------------

def _mock_download(out_path: Path) -> Path:
    """Create a tiny local test clip with ffmpeg instead of the network."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y",
         "-f", "lavfi", "-i", "color=c=steelblue:s=640x360:d=3",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
         "-shortest", "-pix_fmt", "yuv420p", str(out_path)],
        check=True)
    return out_path


def make_thumbnail(video: Path, thumb: Path) -> bool:
    thumb.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", str(video),
         "-frames:v", "1", "-vf", "scale=480:-2", str(thumb)],
        capture_output=True)
    if r.returncode != 0:  # very short clips: retry at t=0
        r = subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(video),
             "-frames:v", "1", "-vf", "scale=480:-2", str(thumb)],
            capture_output=True)
    return r.returncode == 0 and thumb.exists()


def sha1_of(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_env_files() -> None:
    """Tiny .env loader (KEY=VALUE lines) so no python-dotenv dependency."""
    for name in (".env", "keys.env"):
        p = Path(name)
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def run(shots: list[dict], outdir: Path, sources: list[str], per_query: int,
        min_dur: float, max_dur: float, orientation: str,
        allow_sa: bool, allow_verify: bool, no_download: bool) -> int:
    clips_dir, thumbs_dir = outdir / "clips", outdir / "thumbs"
    ledger_path = outdir / "ledger.json"
    ledger: dict[str, dict] = {}
    if ledger_path.exists():
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))

    report: list[str] = []
    downloaded = skipped = failed = 0

    for shot in shots:
        slot, query = shot.get("slot", ""), shot["query"]
        print(f"[shot] {slot or '-'} :: {query}")
        cands: list[Candidate] = []
        for sname in sources:
            fn = SOURCES.get(sname)
            if not fn:
                print(f"  [warn] unknown source '{sname}' skipped")
                continue
            try:
                got = fn(query, per_query, orientation)
            except Exception as e:  # keep other sources alive
                print(f"  [warn] {sname}: search failed: {e}")
                report.append(f"SEARCH-FAIL {sname} '{query}': {e}")
                continue
            print(f"  [{sname}] {len(got)} candidates")
            cands.extend(got)

        kept = 0
        for c in cands:
            if kept >= per_query:
                break
            if c.duration and (c.duration < min_dur or (max_dur and c.duration > max_dur)):
                continue
            ok, why = license_allowed(c.license_class, allow_sa, allow_verify)
            if not ok:
                skipped += 1
                report.append(f"SKIP {c.clip_id} [{c.license_class}] {why} :: {c.source_url}")
                continue
            if c.clip_id in ledger:
                print(f"  [dup ] {c.clip_id} already in ledger")
                kept += 1
                continue
            if no_download:
                print(f"  [find] {c.clip_id} [{c.license_class}] {int(c.duration)}s "
                      f"{c.width}x{c.height} :: {c.source_url}")
                kept += 1
                continue
            dest = clips_dir / f"{c.clip_id}.mp4"
            try:
                if c.download_url == "mock://color":
                    _mock_download(dest)
                else:
                    _download(c.download_url, dest)
            except Exception as e:
                failed += 1
                print(f"  [fail] {c.clip_id}: download: {e}")
                report.append(f"DL-FAIL {c.clip_id}: {e}")
                continue
            thumb = thumbs_dir / f"{c.clip_id}.jpg"
            if not make_thumbnail(dest, thumb):
                report.append(f"THUMB-FAIL {c.clip_id}")
            rec = asdict(c)
            rec.update({
                "clip_id": c.clip_id, "slot": slot, "query": query,
                "file": str(dest.relative_to(outdir)).replace("\\", "/"),
                "sha1": sha1_of(dest),
                "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            ledger[c.clip_id] = rec
            downloaded += 1
            kept += 1
            print(f"  [ ok ] {c.clip_id} [{c.license_class}] -> {dest.name}")

        if kept == 0:
            report.append(f"NO-CLIP for shot '{slot or query}' - widen query or sources")
            print(f"  [none] nothing usable for this shot")

    outdir.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    write_credits(ledger, outdir / "CREDITS.txt")
    (outdir / "report.txt").write_text(
        "\n".join(report) + ("\n" if report else "nothing to report\n"),
        encoding="utf-8")

    print(f"\ndone: {downloaded} downloaded, {skipped} skipped by license, {failed} failed")
    print(f"ledger : {ledger_path}")
    print(f"credits: {outdir / 'CREDITS.txt'}  (paste into the YouTube description)")
    print(f"thumbs : {thumbs_dir}  (pick clips by eye from here)")
    return 0 if failed == 0 else 1


def write_credits(ledger: dict[str, dict], path: Path) -> None:
    """Description-ready credits. Attribution-REQUIRED lines first."""
    required, courtesy = [], []
    for rec in sorted(ledger.values(), key=lambda r: r.get("clip_id", "")):
        cls = rec.get("license_class", VERIFY)
        who = rec.get("creator") or rec.get("source", "")
        title = rec.get("title") or rec.get("clip_id", "")
        line = f'- "{title}" by {who} - {rec.get("license", "")} - {rec.get("source_url", "")}'
        if cls in (BY, BY_SA):
            required.append(line)
        elif cls == PD:
            courtesy.append(f'- "{title}" - {rec.get("license", "")} - {rec.get("source_url", "")}')
        else:  # FREE / VERIFY(kept manually)
            courtesy.append(f'- {rec.get("source", "")}: {rec.get("source_url", "")}')
    lines = ["Footage credits", "==============="]
    if required:
        lines += ["", "Attribution (required by license):", *required]
    if courtesy:
        lines += ["", "Additional footage sources:", *courtesy]
    if not required and not courtesy:
        lines += ["", "(no external footage used)"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Doctor & self-test
# ---------------------------------------------------------------------------

def doctor(net: bool) -> int:
    ok = True

    def check(name: str, cond: bool, hint: str = "") -> None:
        nonlocal ok
        print(f"  [{'OK  ' if cond else 'MISS'}] {name}" + (f" -> {hint}" if hint and not cond else ""))
        ok = ok and cond

    print("fetchclips doctor")
    check("python >= 3.9", sys.version_info >= (3, 9), "install newer Python")
    check("requests installed", requests is not None, "pip install requests")
    check("ffmpeg on PATH", shutil.which("ffmpeg") is not None, "install ffmpeg, add to PATH")
    load_env_files()
    check("PEXELS_API_KEY set (free key, no card)",
          bool(os.environ.get("PEXELS_API_KEY")), "https://www.pexels.com/api/  -> put in .env")
    check("PIXABAY_API_KEY set (free key, no card)",
          bool(os.environ.get("PIXABAY_API_KEY")), "https://pixabay.com/api/docs/  -> put in .env")
    print("  [info] nasa / wikimedia / archive need no key")
    if net and requests is not None:
        for name, url in [("wikimedia reachable", "https://commons.wikimedia.org/w/api.php"),
                          ("archive.org reachable", "https://archive.org/advancedsearch.php?q=test&rows=0&output=json"),
                          ("nasa reachable", "https://images-api.nasa.gov/search?q=moon&page_size=1")]:
            try:
                r = requests.get(url, timeout=10, headers={"User-Agent": USER_AGENT})
                check(name, r.status_code < 500, f"HTTP {r.status_code}")
            except Exception as e:
                check(name, False, str(e))
    else:
        print("  [info] network probe skipped (add --net to test connectivity)")
    print("RESULT:", "READY" if ok else "FIX THE ITEMS ABOVE")
    return 0 if ok else 1


def self_test() -> int:
    """Full offline run using the mock source. Verifies the plumbing:
    filtering, download path, thumbnails, ledger, credits, report."""
    import tempfile
    ok = True

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" -- {detail}" if detail and not cond else ""))
        ok = ok and cond

    print("fetchclips self-test (offline, mock source)")
    check("classify PD", classify_license("Public Domain") == PD)
    check("classify CC0", classify_license("https://creativecommons.org/publicdomain/zero/1.0/") == PD)
    check("classify BY", classify_license("CC BY 4.0") == BY)
    check("classify BY-SA", classify_license("CC BY-SA 3.0") == BY_SA)
    check("classify NC", classify_license("CC BY-NC 4.0") == NC_ND)
    check("classify ND", classify_license("CC BY-ND 2.0") == NC_ND)
    check("classify empty -> VERIFY", classify_license("") == VERIFY)
    check("classify pexels -> FREE", classify_license("Pexels License") == FREE)

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "clips_raw"
        shots = [{"slot": "s1", "query": "good_case"},
                 {"slot": "s2", "query": "sa_case"},
                 {"slot": "s3", "query": "nc_case"},
                 {"slot": "s4", "query": "verify_case"}]
        rc = run(shots, out, ["mock"], per_query=1, min_dur=0, max_dur=0,
                 orientation="any", allow_sa=False, allow_verify=False,
                 no_download=False)
        check("run exits 0", rc == 0)
        ledger = json.loads((out / "ledger.json").read_text(encoding="utf-8"))
        check("only BY clip downloaded (SA/NC/VERIFY skipped)",
              len(ledger) == 1 and next(iter(ledger)).startswith("mock_good_case"),
              f"ledger keys: {list(ledger)}")
        rec = next(iter(ledger.values()))
        check("ledger has sha1 + license + url",
              bool(rec.get("sha1")) and bool(rec.get("license")) and bool(rec.get("source_url")))
        clip = out / rec["file"]
        check("clip file exists", clip.exists() and clip.stat().st_size > 0)
        check("thumbnail exists", (out / "thumbs" / (rec["clip_id"] + ".jpg")).exists())
        credits = (out / "CREDITS.txt").read_text(encoding="utf-8")
        check("credits lists BY attribution", "Attribution (required" in credits and "Mock Creator" in credits)
        report = (out / "report.txt").read_text(encoding="utf-8")
        check("report explains the skips",
              "BY-SA" in report and "NC/ND" in report and "unclear" in report)
        # second run must dedupe, not redownload
        rc2 = run([{"slot": "s1", "query": "good_case"}], out, ["mock"], 1, 0, 0,
                  "any", False, False, False)
        ledger2 = json.loads((out / "ledger.json").read_text(encoding="utf-8"))
        check("rerun dedupes via ledger", rc2 == 0 and len(ledger2) == 1)

    print("RESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
    print("NOTE: network sources are NOT exercised here; first online run is the real test.")
    return 0 if ok else 1


# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("queries", nargs="*", help="one search query per shot")
    ap.add_argument("--from-json", metavar="SHOTS_JSON",
                    help='[{"slot":"intro","query":"..."}]')
    ap.add_argument("--out", default="clips_raw", help="output folder (default clips_raw)")
    ap.add_argument("--sources", default=",".join(DEFAULT_SOURCES),
                    help=f"comma list (default {','.join(DEFAULT_SOURCES)})")
    ap.add_argument("--per-query", type=int, default=3, help="clips to keep per shot (default 3)")
    ap.add_argument("--min-dur", type=float, default=3.0, help="skip clips shorter than this (default 3)")
    ap.add_argument("--max-dur", type=float, default=90.0, help="skip clips longer than this; 0 = no cap")
    ap.add_argument("--orientation", choices=["landscape", "portrait", "square", "any"],
                    default="landscape")
    ap.add_argument("--allow-sa", action="store_true", help="also keep CC BY-SA clips")
    ap.add_argument("--allow-verify", action="store_true",
                    help="also keep unclear-license clips FOR MANUAL CHECK")
    ap.add_argument("--no-download", action="store_true", help="search + print only")
    ap.add_argument("--doctor", action="store_true", help="environment check")
    ap.add_argument("--net", action="store_true", help="with --doctor: probe connectivity")
    ap.add_argument("--self-test", action="store_true", help="offline end-to-end test (mock source)")
    args = ap.parse_args(argv)

    if args.doctor:
        return doctor(args.net)
    if args.self_test:
        return self_test()
    if requests is None:
        print("ERROR: 'requests' is not installed. Run: pip install requests")
        return 2

    load_env_files()
    shots: list[dict] = []
    if args.from_json:
        data = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
        for item in data:
            shots.append({"slot": str(item.get("slot", "")), "query": str(item["query"])})
    shots += [{"slot": "", "query": q} for q in args.queries]
    if not shots:
        ap.print_help()
        return 2

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    return run(shots, Path(args.out), sources, args.per_query,
               args.min_dur, args.max_dur, args.orientation,
               args.allow_sa, args.allow_verify, args.no_download)


if __name__ == "__main__":
    raise SystemExit(main())
