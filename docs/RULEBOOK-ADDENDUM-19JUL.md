# RULEBOOK ADDENDUM — 19 July 2026

यह हिस्सा `youtube-channel-rulebook` skill में paste करना है। नीचे हर
section के आगे लिखा है कि rulebook के किस Part में जाएगा। जब तक paste
नहीं हुआ, इस file को rulebook के बराबर मानो।

---

## Part B में जोड़ो — B-STOCK: बाहर की footage के नियम

Stock/borrowed footage सिर्फ़ B-roll है — video की जान कभी नहीं।
YouTube की reused-content policy का जवाब "transformation" है, और हमारा
transformation तीन चीज़ों से आता है: अपनी narration, अपनी editing, और
अपने बनाए visuals। इसलिए:

1. **Ledger अनिवार्य।** हर बाहरी clip `fetchclips.py` के `ledger.json`
2.    में होनी चाहिए — license, license_class, creator, source URL, sha1 के
3.   साथ। बिना ledger entry वाली clip video में गई तो video reject।
4.   2. **License classes का नियम:**
     3.    - `NC` या `ND` — **कभी नहीं।** Monetised channel पर non-commercial
           -      license का इस्तेमाल ग़ैर-क़ानूनी है।
           -     - `BY-SA` (share-alike) — default में नहीं। SA video पर कैसे लागू
           -      होता है यह legally साफ़ नहीं है; जोखिम क्यों लेना।
           -     - `VERIFY` (license unclear) — manual check के बिना नहीं।
           -    - `PD` / `FREE` / `BY` — allowed। `BY` वाली हर clip का credit
                -      description में जाएगा (fetchclips का `CREDITS.txt` block paste करो)।
                -  3. **Transformation minimums (यह हमारी policy है, YouTube का लिखा
                   4.    नियम नहीं — §6 वाली ग़लती दोबारा नहीं):**
                   5.   - Stock clip हमेशा narration के नीचे चलेगी — stock अपने-आप में
                        -      content कभी नहीं।
                        -     - एक stock clip लगातार **10 second से ज़्यादा untouched** नहीं
                        -      (बिना cut/zoom/overlay/caption के)।
                        -     - हर video में **कम-से-कम ~40% screen-time अपने बनाए visuals**
                        -      (diagram / animation / text-card) का — यही channel की पहचान है।
                        -  4. **Source की सफ़ाई:**
                           5.    - जिस clip पर किसी और का watermark/logo है — मत लो।
                                 -    - NASA की clips पर caveat: कुछ items में third-party footage होती
                                      -      है; item page पर एक नज़र डालो (ledger में caveat लिखा आता है)।
                                      -     - Scraper-आधारित sources (Mixkit, Coverr, ESA, JAXA, NOAA, Dareful)
                                      -      v1 में इस्तेमाल नहीं — ToS और license ambiguity। JAXA तो
                                      -       educational-use license है, monetised channel के लिए असुरक्षित।
                                      -   5. **Music पर यही classes लागू** — जब भी music आए, वही
                                          6.    PD/FREE/BY/NC-ND जाँच, वही credits नियम।
                                       
                                          7.## Part B में जोड़ो — B-DISCLOSURE: synthetic content का बटन

                                          Upload checklist में हर बार यह सवाल: *"क्या इस video में realistic
                                          लगने वाला AI-generated हिस्सा है?"* हमारी AI आवाज़ + असली जैसी दिखने
                                          वाली कोई भी generated visual = YouTube का altered/synthetic disclosure
                                          बटन on करो। Diagram/animation साफ़-साफ़ बनावटी हैं, उन पर आम तौर पर
                                          ज़रूरी नहीं — पर **YouTube का exact current wording upload वाले दिन
                                          help page पर पढ़ो**, यह text बदलता रहता है। (Flag: यह नियम policy की
                                          हमारी समझ है, verbatim quote नहीं।)

                                          ## Part B/gatekeeper में जोड़ो — B-ADVICE: sensitive सलाह का 3-split

                                          (CLAUDE-OWNS §3 से; 15–16 July 2026 के policy update की reports पर
                                          आधारित — **official page पर अभी unverified**, इसलिए conservative रहो।)

                                          - हमारी AI आवाज़ "expert" बनकर **health, पैसा/investment, क़ानून,
                                          -   राजनीति की सलाह** नहीं देगी। यह monetisation के लिए सीधा ख़तरा
                                          -     बताया जा रहा है।
                                          - - Explainer/history/how-it-works allowed है — फ़र्क़ "सलाह" का है।
                                            -   Intake form का Q5 ही यह gate है; उसका जवाब "हाँ" है तो script में
                                            -     साफ़ disclaimer + सलाह वाले वाक्य हटाओ या video मत बनाओ।
                                            - - gatekeeper का topic+advice वाला check इसी नियम को enforce करता है।
                                             
                                              - ## Part C में जोड़ो — C-QC: बिना QC pass के approval नहीं
                                             
                                              - `wordedit.py` के बाद, Telegram approval message से **पहले**, हर video
                                              - पर `qc.py` चलेगा:
                                             
                                              - ```
                                                python qc.py out/VIDEO_16x9.mp4 --vo vo.wav --script script.txt
                                                ```

                                                - Verdict `REJECT` = re-render, approval message भेजना ही नहीं।
                                                - - `PASS with warnings` = warnings पढ़कर इंसान तय करे।
                                                  - - qc की `frames/` folder ही visual review का सबसे तेज़ तरीक़ा है —
                                                    -   8 तस्वीरें देखो, पूरा video बाद में।
                                                    -   - 9:16 cut पर भी qc चलाओ (captions के कटने की जाँच frames से होती है)।
                                                        - 
