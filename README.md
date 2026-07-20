# hindi-explainer-pipeline

Faceless Hindi explainer channel ka local pipeline. Sab kuch owner ke apne
Windows PC par chalta hai — koi server nahi, koi paid subscription nahi,
credit card kahin nahi chahiye.

> **Sabse pehle padho:** [`docs/PROJECT-STATE.md`](docs/PROJECT-STATE.md) —
> wahi is project ka single source of truth hai. README sirf naksha hai.

---

## Pipeline

```
topic + angle          <- INSAAN. optional nahi.
      |
script.txt             <- Claude, insaan ke angle se
      |                   (tools/hindi_text.py se lambai ka andaza)
narrate.py             <- Kokoro voice + faster-whisper word timings
      v
vo.wav + vo_timings.json
      |
VISUALS                <- A) apne banaye diagram/animation (primary)
      |                   B) free stock b-roll (tools/fetchclips.py)
      |                   C) local image-gen (abhi tala hua)
wordedit.py            <- word-snapped assembly, 16:9 + 9:16
      v
out/*_16x9.mp4  out/*_9x16.mp4
      |
tools/qc.py            <- post-render gate. REJECT => dobara render
gatekeeper.py          <- compliance + variation gate
      |
Telegram approval      <- INSAAN
      |
manual upload          <- INSAAN (2 video/week par yahi sahi hai)
```

## Is repo mein kya hai

| Path | Kya karta hai | Test hua? |
|---|---|---|
| `tools/hindi_text.py` | Devanagari sentence split + bolne ke time ka estimate + calibration | Haan, self-test sab pass |
| `tools/qc.py` | Render ke baad quality gate: audio hai ya nahi, duration, lambi silence, black screen, loudness, review frames, script round-trip | Haan — self-test jaan-boojh kar kharab video banata hai aur har check verify karta hai. `--script` wala path abhi nahi chala |
| `tools/fetchclips.py` | Free stock b-roll + license ledger + CREDITS.txt + thumbnails | License logic, ledger, credits, dedupe: haan (offline mock end-to-end). **Network adapters: NAHI chale** |
| `docs/PROJECT-STATE.md` | Project ka asli state, locked decisions, untested list | — |
| `docs/RULEBOOK-ADDENDUM-19JUL.md` | Rulebook skill mein paste karne wale naye niyam | — |
| `docs/STUDY-REPORT-19JUL.md` | 3 repo ka study, kya liya / kya chhoda aur kyun | — |

`narrate.py`, `wordedit.py`, `gatekeeper.py`, `project.example.json` aur
`setup_windows.bat` abhi is repo mein **nahi** hain — woh owner ke PC par hain.
Unhe yahan laana agla kaam hai (issue #1 dekho).

## Chalane ka tareeka

```bash
pip install requests

python tools/hindi_text.py script.txt
python tools/hindi_text.py script.txt --calibrate vo_timings.json

python tools/fetchclips.py --doctor            # keys aur env check
python tools/fetchclips.py --doctor --net      # asli network check
python tools/fetchclips.py --from-json shots.json --out clips_raw

python tools/qc.py out/VIDEO_16x9.mp4 --vo vo.wav --script script.txt
```

Har tool mein `--self-test` hai. Naya PC ho ya zara bhi shak ho — pehle wahi
chalao, phir asli kaam.

## Zaroori: ye cheezein abhi verify NAHI hui

Inko chhupana is project ki sabse badi galti maani jaati hai.

1. `fetchclips.py` ke network adapters kabhi internet par nahi chale.
2. `qc.py` ka script round-trip check faster-whisper maangta hai — abhi sirf
   SKIP wala raasta chala hai.
3. Kokoro ki Hindi awaaz kaafi achhi hai ya nahi — nahi pata.
4. `hindi_text.py` ka 45 ms/unit constant abhi andaza hai; pehli asli narration
   par `--calibrate` chala kar theek karna hai.
5. Manim (apne visuals ke liye) kisi Windows machine par install nahi hua.

Poori list: `docs/PROJECT-STATE.md` section 4.

## License

Code: MIT (`LICENSE`). Ye repo original code hai — studied repos se sirf
**ideas** liye gaye, unka code copy nahi kiya gaya. Wajah aur details:
`docs/PROJECT-STATE.md` section 3.
