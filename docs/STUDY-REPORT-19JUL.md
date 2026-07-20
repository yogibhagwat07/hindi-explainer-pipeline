# STUDY REPORT — 19 July 2026

तीन repo पढ़े गए और अपने pipeline से मिलाए गए। यह file बताती है: क्या
लिया, क्या छोड़ा, और **क्यों**।

---

## 1 — एक नज़र में

| Repo | License | फ़ैसला | क्यों |
|---|---|---|---|
| **gstack** (Garry Tan) | MIT | **नहीं अपनाया** | Claude Code के लिए 23 agents वाला dev-workflow pack. web-app teams के लिए बना (Bun, browser QA, deploy). हमारा domain अलग है और owner developer नहीं. सिर्फ़ एक आदत ली: "ship से पहले QC ज़रूरी" |
| **OmniVoice-Studio** | app AGPL-3.0, अंदर का `omnivoice` package Apache-2.0 | **app नहीं, knowledge ली** | Desktop TTS studio चाहिए ही नहीं — हमें CLI stage चाहिए. इससे निकाला: Devanagari chunking + duration weights (अब `hindi_text.py`), और Kokoro का named fallback |
| **OpenMontage** | AGPL-3.0 | **framework नहीं, 4 ideas लीं** | Agent-driven, भारी, कई paid providers. लेकिन इसके अंदर के डिज़ाइन सबसे क़ीमती निकले |

## 2 — OpenMontage से क्या लिया (सबसे ज़्यादा फ़ायदा यहीं से)

चारों चीज़ें **दोबारा अपने हाथ से लिखी गईं**, उनका code copy नहीं किया —
इसलिए AGPL की कोई शर्त हम पर नहीं आती।

1. **Stock sources + license ledger** → `tools/fetchclips.py`
   उनके पास 18 source adapters थे। हमने v1 में सिर्फ़ 5 रखे:
   Pexels, Pixabay (free key, card नहीं), NASA, Wikimedia, archive.org
   (कोई key नहीं). बाक़ी छोड़े — नीचे §4.
2. **Render के बाद खुद की जाँच** → `tools/qc.py`
   उनकी checklist का असली दम इस बात में था कि audio stream है या नहीं,
   duration मेल खाती है या नहीं, और सुनी हुई आवाज़ script से मिलती है या
   नहीं. यही तीन हमारी सबसे संभावित ग़लतियाँ हैं.
3. **Export bundle** → हमारा "upload pack" (mp4 + metadata + credits +
   disclosure checklist एक folder में).
4. **अपने visuals बनाने के tools** (Mermaid diagram, Manim animation) →
   यही हमारे Q1 (visuals का blocker) का असली जवाब बना.

एक और अहम बात: उनके `tools/publishers` में **YouTube uploader है ही नहीं**,
सिर्फ़ export bundle है. जिस project ने पूरा agentic system बनाया उसने भी
upload इंसान पर छोड़ा — इसी से हमारा Q2 "manual upload" पर बंद हुआ.

## 3 — OmniVoice से क्या लिया

- **Devanagari का danda (। ॥)** वाक्य का अंत है — पहले हमारा code सिर्फ़
  `.` देखता, इसलिए पूरा Hindi paragraph एक ही वाक्य बन जाता.
- **बोलने के समय का हिसाब** — Devanagari अक्षर अंग्रेज़ी letter से धीमे
  बोले जाते हैं, अंक सबसे धीमे. यह weights `hindi_text.py` में गए.
- **Voice fallback:** `omnivoice` pip package (Apache-2.0 code) owner की
  **अपनी आवाज़ clone** कर सकता है — Kokoro यह नहीं कर सकता.
  *Flags:* Hindi की quality unverified, 2.4 GB diffusion model की CPU speed
  unverified, और **model weights का license Hugging Face पर verify करना
  बाक़ी है** (code का Apache-2.0 होना weights पर लागू हो, ज़रूरी नहीं).
  इसलिए यह fallback है — बदलाव नहीं.

## 4 — जानबूझकर क्या छोड़ा

| छोड़ा | क्यों |
|---|---|
| JAXA footage | License **educational use** — monetised channel के लिए असुरक्षित |
| ESA footage | CC BY-SA — share-alike का video पर असर legally साफ़ नहीं |
| Mixkit, Coverr, Dareful, NOAA adapters | Scraping पर टिके हैं — ToS का जोखिम + page बदलते ही टूटेंगे |
| gstack के 23 agents | ग़लत domain, भारी setup |
| OpenMontage का पूरा framework | Agent-driven + कई paid API, हमारे "no card, offline" नियम के ख़िलाफ़ |
| Local Stable Diffusion (अभी) | CPU पर धीमा, और कुछ models (जैसे SDXL-Turbo) **research-only** license हैं — commercial नहीं |
| Postiz publishing | Card के बिना verify नहीं हो सका; disclosure flag सेट करता है या नहीं, पता नहीं |

## 5 — License की साफ़ बात

AGPL वाले tool अपने PC पर चलाकर बनी **video बेचना/monetise करना क़ानूनी
है**. AGPL की शर्तें तब लगती हैं जब आप वह *software* बाँटें या network पर
सेवा के रूप में चलाएँ — हम दोनों नहीं कर रहे. फिर भी हमने उनका code
vendor करने के बजाय अपना लिखा, ताकि सवाल ही न उठे.

*Flag: यह license की आम समझ है, वकील की राय नहीं.*

## 6 — Owner के लिए काम की list

1. दो free API keys बनाओ (card नहीं लगेगा): pexels.com/api और
   pixabay.com/api/docs → `.env` में डालो (`.env.example` copy कर लो).
2. `pip install requests` (अगर पहले से न हो).
3. `python tools/fetchclips.py --doctor` → फिर `--doctor --net`.
4. पहला असली run छोटा रखो — देखो पाँचों source सच में clip देते हैं या नहीं.
5. `python tools/qc.py --self-test` एक बार Windows पर चलाओ (ffmpeg चाहिए).
6. वैकल्पिक: `pip install manim` — Tier-A अपने visuals इसी पर टिके हैं.
7. CLAUDE-OWNS §3 वाला policy update official page पर confirm करो.

## 7 — जो इस study में साबित नहीं हुआ

- fetchclips के network adapters कभी चले नहीं (sandbox offline था).
- OmniVoice के weights का license नहीं देखा गया.
- Kokoro बनाम OmniVoice की Hindi quality नहीं सुनी गई — मैं audio सुन
  नहीं सकता, यह फ़ैसला owner के कान का है.
- Manim कहीं install नहीं हुआ.
