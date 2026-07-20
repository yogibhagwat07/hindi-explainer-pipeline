# PROJECT STATE — read this first

Faceless AI YouTube explainer channel, aiming at YPP monetisation.
Owner works in Hindi (Devanagari), on Windows, 20 GB RAM, **no credit card**.

Last updated: 20 July 2026 (§2 fetchclips row and §5.4 brought in line
with the §4.5 live-verification note that was committed the same day).
Previous update: 19 July 2026 (after the 3-repo study: gstack,
OmniVoice-Studio, OpenMontage — see docs/STUDY-REPORT-19JUL.md and §3/§6).

---

## 1 — The pipeline as it actually stands

```
topic + angle          <- HUMAN. Not optional. See rulebook Part A.
      |
script.txt             <- Claude, from the human's angle
      |                   (hindi_text.py estimates length BEFORE narration)
narrate.py             <- Kokoro voice + faster-whisper word timings
      v
vo.wav + vo_timings.json
      |
[ VISUALS ]            <- DECIDED 19 Jul (layered, see §3):
      |                   A) OWN diagrams/animations  (primary; Manim/Mermaid/Pillow)
      |                   B) free stock b-roll        (fetchclips.py + license ledger)
      |                   C) local image-gen          (deferred)
      |
wordedit.py            <- word-snapped assembly, 16:9 + 9:16 from one timeline
      v
out/*_16x9.mp4  out/*_9x16.mp4
      |
qc.py                  <- NEW: post-render gate (audio present, duration,
      |                   silence, black, loudness, review frames,
      |                   script round-trip). REJECT => re-render.
gatekeeper.py          <- compliance + variation gate, writes the Telegram message
      |
Telegram approval      <- HUMAN
      |
publish                <- DECIDED 19 Jul: MANUAL upload (see §3),
                          with an "upload pack" folder per video
```

Everything runs on the owner's own Windows PC. No server, no API key
required (two OPTIONAL free keys unlock Pexels/Pixabay in fetchclips).
Offline after the one-time install — except fetchclips, which by nature
goes online to download footage.

## 2 — Files that exist

| File | Does what | Tested? |
|---|---|---|
| `narrate.py` | text -> Kokoro voice -> faster-whisper timings | plumbing yes, models NO |
| `wordedit.py` | word-snapped assembly, captions, both cuts | yes, end to end |
| `gatekeeper.py` | compliance + variation gate, ledger | yes, 5 cases |
| `qc.py` | **NEW** post-render quality gate | yes — self-test builds defect videos and verifies every check fires; the optional script round-trip path needs faster-whisper and is **NOT yet run** |
| `fetchclips.py` | **NEW** free stock b-roll + license ledger + CREDITS.txt + thumbnails | license logic, ledger, credits, thumbnails, dedupe: yes (offline mock end-to-end). Network: **3 of 5 sources verified live 20 Jul** (Wikimedia, NASA, archive.org) — see §4.5. Pexels/Pixabay unverified (need free keys); the real download + thumbnail + ledger path is still unverified |
| `hindi_text.py` | **NEW** Devanagari-aware sentence split + speech-length estimate + calibration | yes, self-test all pass |
| `setup_windows.bat` | one-click installer | **NO — never run on Windows**; also does not yet install the new files' needs (requests) |
| `project.example.json` | scene/overlay format template | yes |

Skills (uploaded by the owner into Claude):
- `youtube-channel-rulebook` — compliance + growth, single source of truth.
  **Pending: paste in docs/RULEBOOK-ADDENDUM-19JUL.md** (stock-footage rules,
  QC gate, disclosure checklist, sensitive-advice 3-split).
- `word-based-editing` — the edit stage, updated for this stack.

Turned OFF and replaced: `youtube-ai-content-rules`, `youtube-growth-tactics`.
`motion-design`: recommendation is now **turn OFF** — unrelated to this
channel (Higgsfield ads) and only adds prompt noise. Owner's call.

Run order:
```
python hindi_text.py  script.txt                  # length check before narrating
python narrate.py     script.txt
python fetchclips.py  --from-json shots.json --out clips_raw    # b-roll layer
python wordedit.py    project.json --check-only   # read the warnings
python wordedit.py    project.json
python qc.py          out/VIDEO_16x9.mp4 --vo vo.wav --script script.txt
python gatekeeper.py  project.json --script script.json --thumb thumb.jpg
# only after the video is actually published:
python gatekeeper.py  project.json --script script.json --record
```

## 3 — Decisions locked (do not re-open without new evidence)

**Voice: Kokoro-82M.** Apache 2.0, so commercial use is legal — this is
the deciding factor. XTTS v2 and F5-TTS are non-commercial licences and
therefore *illegal* for a monetised channel. Free, offline, CPU-only.
Cannot clone: pick one of its 54 voices and keep it every video.
**Named fallback (19 Jul), only if Kokoro fails the Hindi ear test:**
the `omnivoice` pip package (k2-fsa/OmniVoice, Apache-2.0 code) — can
clone the owner's OWN recorded voice for brand consistency, 117 h Hindi
in its training set. Costs: ~2.4 GB model, diffusion-based so CPU speed
unknown, and the **model-weights licence on Hugging Face is unverified**.
Do not switch without checking both. Third option: Piper (local, free;
per-voice licence must be checked).

**Timings: faster-whisper (MIT), local.** Unchanged.

**Hosting: the owner's own PC. No server.** Unchanged.

**Cadence: 2 long-form/week.** Our choice, not YouTube policy. Unchanged.

**Visuals (19 Jul, closes old open-question #1). Layered:**
- **Tier A — OWN visuals, primary.** Diagrams and animations generated
  locally per script: Manim CE (the 3Blue1Brown engine — free, CPU-ok),
  Mermaid/Graphviz diagrams, Pillow text-cards. Reason: 100% owned, so
  the rulebook Part B "transformation" question does not even arise for
  this layer; zero licence risk; and it gives the channel a look that a
  stock-slideshow channel cannot copy. This is also the strongest
  possible answer to YouTube's repetitive-content policy. *Caveat: Manim
  has never been installed on the owner's Windows machine, and Hindi
  text in Manim needs a Devanagari font set explicitly — both unverified.*
- **Tier B — free stock b-roll via `fetchclips.py`.** Sources v1:
  Pexels + Pixabay (free keys, no card), NASA, Wikimedia Commons,
  archive.org (no keys). Every clip lands in `ledger.json` with its
  licence, class (PD/FREE/BY/BY-SA/NC-ND/VERIFY), creator and URL;
  NC/ND always rejected, BY-SA and unknown skipped by default;
  `CREDITS.txt` is generated ready for the description. Scraper-based
  sources (Mixkit, Coverr, ESA, JAXA, NOAA, Dareful) were **excluded**
  from v1: ToS ambiguity, fragility, and in JAXA's case an
  educational-use licence that is unsafe for a monetised channel.
- **Tier C — local Stable-Diffusion-class image gen: deferred.** CPU
  speed and per-model licences (some, e.g. SDXL-Turbo, are
  research-only) both need checking. Not a blocker now.

**Publishing (19 Jul, closes old open-question #2): manual upload.**
At 2 videos/week the upload takes minutes and keeps the human where
YouTube's policy wants a human. Postiz is dropped: unverifiable without
a card, and whether it sets the synthetic-content disclosure flag is
unknown. Each video ships as one "upload pack" folder: both mp4s,
metadata pack, thumbnail, `CREDITS.txt`, qc report, and the disclosure
checklist. (Idea adapted from OpenMontage's export_bundle.)

**The repo `github.com/darkzOGx/youtube-automation-agent` was rejected.**
Unchanged; do not revisit.

**Three studied repos — verdicts (19 Jul), do not re-litigate:**
- **gstack (MIT)** — Garry Tan's Claude-Code software-factory skill
  pack. REJECTED for adoption: built for web-app teams (Bun, browser
  QA, deploy); wrong domain, heavy footprint. Its review-before-ship
  discipline is the same idea our qc.py gate now enforces.
- **OmniVoice-Studio (AGPL-3.0 app)** — desktop TTS suite. NOT adopted
  as an app (we need a CLI stage, not a Tauri studio). Extracted:
  Devanagari chunking + duration weights (now `hindi_text.py`), the
  engine-licence matrix knowledge, and the named Kokoro fallback above.
- **OpenMontage (AGPL-3.0)** — agentic video-production framework. NOT
  adopted as a framework (agent-driven, many paid providers, heavy).
  Extracted, as independent re-implementations: the stock-source list +
  licence-ledger design (`fetchclips.py`), the mandatory post-render
  self-review checklist (`qc.py`), the credits/export-bundle idea, and
  the owned-visuals (Manim/Mermaid) idea.
- **Licence note:** running AGPL tools locally and monetising the
  *videos* is legal — AGPL obligations trigger on distributing or
  network-serving the *software*, which we do not do. We still wrote
  our own code rather than vendoring theirs.

## 4 — What has NOT been tested

Be honest about these; do not let them get quietly assumed:

1. **Kokoro and faster-whisper have never actually run** (no internet in
   the sandbox they were written in). Same status as before.
2. **`setup_windows.bat` has never run on Windows**, and it predates the
   new files (does not `pip install requests`, does not mention Manim).
3. **espeak-ng** must be installed by hand on Windows for Kokoro.
4. **Kokoro's Hindi quality** — unverified; the fallback path exists but
   its own three unknowns (weights licence, CPU speed, Hindi quality)
   are also unverified.
5. **fetchclips.py network adapters** — PARTLY VERIFIED 20 Jul
   2026, live from a browser: the three keyless sources all answered and
   returned a real playable file. Wikimedia search -> imageinfo URL +
   LicenseShortName (first hit was "CC BY-SA 4.0", which our default rule
   skips — expect fewer usable Wikimedia clips than the hit count
   suggests). NASA search -> collection.json -> mp4 list; the item tested
   had no `~orig.mp4`, so the `~orig`/`~large`/`~medium`/first fallback
   chain matters and works. archive.org advancedsearch -> /metadata/{id}
   -> .mp4 + licenseurl, all present. STILL UNVERIFIED: Pexels and
   Pixabay (need the free API keys), and the download + thumbnail +
   ledger path against real remote files. First real command remains
   `python fetchclips.py --doctor --net`.
6. **qc.py script round-trip** — the transcription-vs-script check needs
   faster-whisper and has only been exercised down its SKIP path.
7. **Manim on Windows** — not installed anywhere yet; Devanagari font
   handling in Manim unverified.
8. **hindi_text.py calibration constant** — 45 ms/unit is a guess until
   `--calibrate` runs against the first real narration.

First real commands remain: `python narrate.py --doctor`, then
`--selftest`, then `python fetchclips.py --doctor --net`,
then `python qc.py --self-test`.

## 5 — Open questions, in priority order

1. **Which Kokoro voice, and is it good in Hindi?** (Old Q3, now the top
   blocker.) Claude shortlists 3; the owner's ear decides. If all fail:
   fallback path in §3, with its checks.
2. **Manim install + first two scene templates.** Tier-A visuals depend
   on it. Verify `pip install manim` works on the owner's machine, that
   a Devanagari font renders, and build two reusable scene templates
   (title-card, labelled-diagram).
3. **Confirm the 15–16 July policy 3-split on the official page.**
   Carried from CLAUDE-OWNS §3 — reports say monetisation policy now
   separately names "AI personas giving advice on sensitive topics".
   The official page still showed the July-2025 text when last checked.
   Until confirmed, behave as if it is true (it is the conservative
   reading anyway).
4. **fetchclips first live run from the machine.** The search/metadata
   half of Wikimedia, NASA and archive.org answered live on 20 Jul
   (§4.5) — but from a browser, not from fetchclips.py itself.
   Remaining: the two free keys (Pexels, Pixabay), then one real
   end-to-end download that writes a clip, a thumbnail and a ledger
   entry to disk.
5. ~~Where do visuals come from?~~ **Closed 19 Jul** (§3).
6. ~~How does publishing happen?~~ **Closed 19 Jul** (§3).
7. ~~Telegram bot?~~ Closed earlier: no bot at 2/week.
8. ~~motion-design skill?~~ Recommendation recorded: turn OFF (§2).

## 6 — Mistakes already made here. Do not repeat them.

**Claimed YouTube demonetises daily uploads.** It does not. The risk is
sameness, not frequency. Never state a cadence number as YouTube policy.
(The same rule now applies to the new stock-footage numbers in the
rulebook addendum — the "10-second max run" and "40% own visuals" are
OUR policy, not YouTube's text.)

**`gatekeeper.py` sensitive-topic check was wrong in both directions.**
A keyword scanner cannot read intent — never claim a script
"automatically catches" something without testing both the false
positive and the false negative.

**Over-trusted a tool's description instead of testing it.** Test
before claiming.

**19 Jul, new instance of the same lesson: both new tools shipped with
a bug that only self-tests caught.** `hindi_text.py` used
`unicodedata.combining()` to spot matras — but Devanagari matras have
combining-class 0, so every matra was being counted as a full letter;
the correct test is Unicode category `M*`. `qc.py` parsed the FIRST
"I: … LUFS" line from ffmpeg — a running value near silence — instead
of the LAST (the summary), reporting -70 LUFS for normal audio. Both
found and fixed the same day because the self-tests existed. Rule
stands: no tool ships without a self-test, and no claim ships without
running it.

## 7 — How to work on this

- Answer in Devanagari Hindi (owner's set preference); technical terms
  stay in English where natural.
- Never state a name, date, number or policy as fact without checking.
  Flag anything unverified explicitly.
- Prefer working code that has been run over explanations of code.
- The owner will say "do whatever is best" — real delegation, but not
  permission to skip the honest caveats. Give the decision *and* the
  reason, and say plainly what could not be done.
- Some things genuinely cannot be done from a chat sandbox: no internet
  in the code environment, no access to the owner's PC, and
  passwords/API keys are never to be entered. Say so directly.
