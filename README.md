# 1930 Saathi

**When the 1930 cyber-fraud helpline is busy, Saathi answers.** It is a voice agent built on Gnani AI. It listens to a panicked victim over a real phone line or in the browser, in Hindi, Hinglish, Punjabi, Tamil or English, and captures every number a complaint needs. It reads those numbers back to catch mistakes, then hands a ready-to-act case to a logged-in officer while the money can still be frozen.

> Student prototype for Gnani AI's *Great Indian AI Internship Challenge*. Not an official government service. Synthetic data only.
>
> **📄 One-page solution pitch: [PITCH.md](PITCH.md)** · 🎬 Demo video: *(https://youtu.be/bYyRllCvj4g)*

---

## The problem

- **The golden hour decides recovery.** 1930 operators have reported a 70–80% success rate when fraud is reported within two hours, and only 15–20% after that (Times of India).
- **The line is overloaded.** 1930 handled about 3.24 crore calls in 2025, roughly one every second (The Mainstream), and lines are busy at times, especially in the evening.
- **A complaint needs exact numbers,** such as the UTR and the suspect's UPI ID, account or mobile (Punjab Police). One wrong digit points the freeze request at the wrong transaction.

## What it does

| | Feature |
|---|---|
| 🎙 **Voice** | Gnani **Prisma** speech-to-text (REST or realtime WebSocket, 8 kHz phone audio; Prisma v3 `indic-auto` detects the caller's language), Gnani **Timbre** text-to-speech |
| 📞 **Real phone calls** | **Twilio Media Streams** and **Exotel Voicebot** over WebSocket: G.711 μ-law codec, energy voice-activity detection, barge-in. The caller's number comes from caller ID |
| 🔢 **Indian number engine** | "saade teen hazaar", "dedh lakh", "paune do lakh", "ਪੰਤਾਲੀ ਹਜ਼ਾਰ", "naarpathi anjaayiram", "चार एक दो…", "double five", "oh"; digits written in Devanagari, Gurmukhi and Tamil script |
| 🔤 **UPI IDs from any script** | Turns Devanagari, Gurmukhi and Tamil transcripts back into Latin IDs (रमेश डॉट कुमार एट द रेट वाई बी एल → ramesh.kumar@ybl). Names that can only be guessed from sound are **read back letter by letter**, and the caller can **spell** them |
| ✋ **Validator re-prompts** | "I heard 11 digits, a UTR has 12." Every UTR, UPI ID, mobile and account number is checked in code |
| 🔁 **Read-back** | The UTR and fraudster ID are confirmed one by one, plus a final summary read-back with targeted fixes ("rakam 46 hazaar thi") |
| ⚠ **Live-threat interrupt** | A "digital arrest" call still in progress, or AnyDesk still open, triggers safety instructions first |
| 🧠 **Evon fallback** | When the rules fail on a field, Evon v3.3 extracts it as strict JSON. It is **accepted only if the validators pass**, and Evon can never invent UTR digits the caller didn't say |
| 🌐 **5 languages** | Hindi, Hinglish, English, **Punjabi** (Gurmukhi) and **Tamil** prompts, number words, yes/no, time phrases, bank names and payment apps |
| ⏱ **Golden-hour queue** | Cases ranked by recoverable money still inside the window, with live countdowns |
| 💸 **Money-at-risk counter** | The top of the console shows the rupees still inside the golden window and not yet sent for freeze, updated every second. When a window closes, that money drops out of the number, and the "next to run out" button jumps to the case about to expire |
| 👁 **Supervisor live view** | While a caller is still talking, the console shows an "On call now" card whose fields (scam, amount, UTR, fraudster ID, bank, threat) fill in turn by turn |
| 🕒 **Case timeline** | Debit → call to 1930 → filed → freeze requested → now → window closes, on one line, so the officer sees at a glance how much time is gone and how much is left |
| 🔗 **Mule-ring detection** | Union-find over UPI IDs, mobiles and accounts across complaints. Two reports of the same UTR are flagged as a duplicate, not counted as two victims |
| 📝 **Actions** | Portal-style complaint JSON, a bank freeze-request draft, and an SMS acknowledgement in the caller's language |
| 🔐 **Backend** | SQLite; officer login (PBKDF2, HttpOnly SameSite=Strict session cookie); a JSON-only POST rule against cross-site form attacks; per-IP rate limits; full **audit trail**; **caller verification** by OTP SMS after filing (it never blocks the victim); data-retention purge |
| 🗣 **Real-voice testing** | `/collect.html` lets volunteers read synthetic cards; `eval/run_real.py` scores Prisma + Saathi on those recordings |

## Weaknesses found in review, and what was done

| Weakness | Fix | Status |
|---|---|---|
| UPI ID breaks when Prisma writes Devanagari | Indic→Latin transliteration, spelled-letter parsing, a list of handle spellings in each script, fuzzy handle matching, and **letter-by-letter read-back plus caller spelling** for phonetic names | ✅ built and tested; real Prisma output still to confirm |
| Evaluation uses self-written phrasings | 5 transcript styles, disfluency (fillers, digit stutters), a 48-item **blind set run once and reported as-is**, and a **real-recording pipeline** | ✅ built; real recordings need volunteers |
| Rule-based NLU misses unseen phrasing | Evon slot fallback behind the validators | ✅ built; needs an Evon host |
| No real phone call | Twilio Media Streams and Exotel Voicebot | ✅ Twilio fully tested with a simulated stream; Exotel message format still to check against Exotel's docs |
| Only Hindi and English | Punjabi and Tamil added end to end | ✅ prompts need native-speaker review; Prisma/Timbre `pa-IN`/`ta-IN` support still to confirm |
| No ground research | `docs/GROUND_RESEARCH.md` (interview guides, consent, 5-user test plan), feedback collection, real-voice scorer | ⏳ **you** have to do the interviews |
| Prototype backend | SQLite, login, audit, OTP verification, rate limits, retention | ✅ |

## Quick start

```bash
SAATHI_ADMIN_PASSWORD=choose-a-long-password python -m saathi.server     # http://127.0.0.1:8930
```

- **/caller.html**: pick a demo script (Hinglish, Punjabi, Tamil, English) and press ▶ Auto-play, or hold the mic.
- **/console.html**: log in as `admin`, press **Load demo complaints**. You'll see the queue, RING-01, drafts, audit trail and SMS outbox.
- **/verify.html**: the caller confirms the OTP from the SMS. In the demo, the code is in the console's SMS outbox.

Add officers with `python -m saathi.admin create-user NAME`. Purge old data with `python -m saathi.admin purge --days 30`.

**Mock mode** (no key): the full engine and UI run, the caller's words are typed, and the voice is a labelled browser voice.

### Live Gnani

```bash
cp .env.example .env            # GNANI_API_KEY=...; PRISMA_MODEL=prisma-v3.0 for language auto-detect
python scripts/check_gnani.py   # Timbre -> 8 kHz + noise -> Prisma -> engine
```

**Live run, 10 Nov 2026** (Prisma v3.0, Timbre v2.5 voice Nalini, real API key):

| Step | Result |
|---|---|
| Timbre synthesises a Hindi complaint sentence | 6.7 s of audio in 1.6 s |
| Audio cut to 8 kHz phone quality with street noise at 10 dB SNR | — |
| Prisma REST transcribes it | 0.8 s; "मेरे ₹45,000 कट गए, यू टी आर है 412356789012" |
| Prisma realtime (WebSocket) transcribes it | same amount and UTR |
| Engine extracts amount and UTR | ₹45,000 and `412356789012` |
| Full demo call in the browser with Timbre replies | all 8 fields captured, UTR and account read back |

The live run found one real bug: Prisma writes the amount and the UTR as digits in one sentence, and the
engine glued them into a 17-digit "UTR". Amount-shaped numbers (next to ₹, rupaye, hazaar) are now kept out
of the UTR, and the exact Prisma output is a regression test (`tests/test_extract.py`).

The API sits behind Cloudflare, which rejects Python's default user agent with `error code: 1010`. Every
request now sends a normal `User-Agent` (override with `GNANI_USER_AGENT`).

### Real phone calls

**Twilio:** set the number's *Voice webhook* to `POST https://<public-host>/twilio/voice`. The server must be reachable over HTTPS/WSS, for example through a tunnel. The webhook returns TwiML connecting the call to `wss://<host>/twilio/stream`, with a signed stream token.

**Exotel:** add a *Voicebot* applet pointing to `wss://<host>/exotel/stream?key=<EXOTEL_STREAM_KEY>`.

### Evon v3.3 (optional)

Serve `gnani/gnani-evon-v3.3-30B-A3B` with vLLM (OpenAI-compatible) and set `EVON_BASE_URL`. Every field Evon fills shows an `Evon:` badge in the console.

## Evaluation

```bash
python -m eval.run_eval --calls 500 --asr-error 0 0.25 --disfluency   # synthetic calls, 5 transcript styles
python -m eval.stress    # regression set (38 items)
python -m eval.blind2    # blind set #2 (48 items, first-run score kept)
python -m eval.run_real  # REAL volunteer recordings through Prisma (needs key + recordings)
```

**500 synthetic calls** with disfluent speech and simulated recognition errors on 25% of number turns:

| Metric | Result |
|---|---|
| UTR correct as first heard → after validator + read-back | 72.7% → **99.3%**, wrong UTR filed **0%** |
| Fraudster ID, first heard → final | 75.4% → **99.4%** |
| Fraudster ID by transcript style (Hinglish / Devanagari / English / Punjabi / Tamil) | 100 / 99.2 / 97.4 / 100 / 100% |
| Live-threat recall / false positives | 96.2% / 0% |
| Turns per call / estimated length | 12.7 / ~2.5 min |

**Read these honestly:**

- **The synthetic calls come from this project's own generator.** They measure the dialog's ability to *recover* from errors, not real-world accuracy.
- **Blind set #2** (48 new phrasings in all 5 languages) scored **40/48 (83%) on its first run**, saved in `eval/blind2_first_run.md`. Three general gaps were then fixed. The remaining misses are names like "gurpreet" and "karthik" whose English spelling can't be recovered from script sounds, which is exactly what the spelling mode is for.
- The number that matters is `eval/run_real.py` on real voices.

## Verified vs not verified

| ✅ Verified (117 automated tests + live Gnani run) | ⏳ Still needs accounts or people |
|---|---|
| **Live:** Prisma v3.0 REST and realtime on 8 kHz noisy audio, Timbre v2.5 voice in a full browser call | Prisma accuracy across many real voices (`eval/run_real.py` with volunteers) |
| Number engine, extraction, dialog, Punjabi and Tamil calls, the spelling flow | Timbre voices for `pa-IN` and `ta-IN` (Prisma lists both languages) |
| A Twilio call end to end, with a simulated media stream (μ-law, VAD, replies, bad-token rejection) | A live Twilio number; Exotel's message format |
| Login, rate limits, OTP, audit trail, persistence across restarts, collection consent | Evon v3.3 on a GPU |
| UI flow in headless Chrome | Native-speaker review of the Punjabi and Tamil prompts; real interviews |

## Layout

```
saathi/  numbers · translit · validators · extract · dialog · prompts (hi/en/pa/ta) · priority · clusters · outputs
         db (SQLite) · security (auth, OTP, rate limit) · sms · telephony (Twilio/Exotel) · server · admin · demo
         providers/ gnani.py (Prisma REST+realtime, Timbre) · llm.py (Evon) · ws.py (WebSocket client)
web/     caller · console · login · verify (+feedback) · collect (volunteers) · overview
eval/    scenarios · run_eval · stress · blind · blind2 · run_real
docs/    GROUND_RESEARCH.md · screens/
tests/   117 tests incl. a fake Gnani API and a simulated Twilio/Exotel stream
```

## Safety

- Synthetic data only; volunteers read invented cards, after giving consent.
- Every draft is for officer review; nothing is sent to any bank or government system.
- The AI never rejects a complaint, and every officer action is audited.
- OTP verification never blocks a victim. The complaint is acted on immediately, and the badge tells the officer whether the caller's number was confirmed.
