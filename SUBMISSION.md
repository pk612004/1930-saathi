# Submission kit: 1930 Saathi

## Written project explanation (the fields the form asks for)

**Project title:** 1930 Saathi: golden-hour voice intake for cyber-fraud victims

**Problem being solved:** India's cyber-fraud helpline 1930 handled about 3.24 crore calls in 2025. Recovery depends on reporting within the first one to two hours, but lines get busy and a complaint needs exact numbers (UTR, suspect UPI ID, account). Panicked victims struggle to give these, and one wrong digit sends a freeze request to the wrong transaction.

**Intended users:** Fraud victims calling 1930, especially elderly and Hindi or Hinglish speakers, and the cyber-cell officers who must act on complaints within the golden hour.

**Gnani AI models / APIs used:**
- Prisma v2.5 / v3.0 speech-to-text (REST `/stt/v3`; realtime `/stt/v3/stream`; `indic-auto` language detection) for 8 kHz phone audio, including real Twilio/Exotel calls
- Timbre v2.5 text-to-speech (`/api/v1/tts/inference`) for questions and digit-by-digit read-backs
- Evon v3.3 (self-hosted, OpenAI-compatible) for officer summaries, fraud-pattern second opinions and validator-gated field extraction *(write "not used" if you don't get it running)*

**Each member's contribution:** *(fill in: solo, or name + what you built)*

## 60-second demo video script (also targets the Demo Day Drop award)

| Time | Screen | Voice-over / on-screen text |
|---|---|---|
| 0–5 s | Phone dialling 1930, "all lines busy" tone, timer ticking 5… 10… 15 min | "Fraud ke pehle 2 ghante mein report karo toh paisa wapas aane ka sabse zyada chance hai. Line busy ho toh?" |
| 5–25 s | Caller page: live call in Hinglish. Saathi interrupts: "वो कॉल अभी काट दीजिए…" | "Saathi turant uthata hai. Scam abhi chal raha ho toh pehle caller ko bachata hai." |
| 25–38 s | UTR said with a missing digit → "मुझे 11 अंक सुनाई दिए…" → read-back ✓ | "Har number code se check hota hai aur Timbre se wapas padha jaata hai." |
| 38–50 s | Officer console: case jumps to the top, countdown 1:39:20, RING-01 toast "3 victims, same UPI" | "Officer ko golden-hour countdown aur mule-ring alert milta hai." |
| 50–60 s | Bank freeze draft + SMS, then the stats card (UTR read-back 76% → 99.6%) | "Prisma, Timbre, Evon par bana. 1930 Saathi." Hashtags on screen. |

Record the real Gnani voice (live mode), not the browser preview voice. Show the "synthetic data" badge once.

## LinkedIn / X post draft

> 1930 pe har second ek call aati hai. Fraud ke pehle 2 ghante mein report karo toh recovery 70–80% tak (operators ke reported numbers), baad mein sirf 15–20%. Aur line busy ho toh?
>
> I built **1930 Saathi** for the #GreatIndianAIInternshipChallenge on @Gnani AI's models:
> 🎙 Prisma understands panicked Hinglish on 8 kHz phone audio
> 🔢 A custom number engine understands "saade teen hazaar", "dedh lakh", "chaar ek do teen…"
> 🔁 Timbre reads every UTR back digit by digit. In 300 synthetic calls with simulated recognition errors, read-back raised UTR accuracy from 76% to 99.6%, with zero wrong UTRs filed
> ⚠ If you're still on a "digital arrest" call, it tells you to hang up first
> ⏱ Officers get a golden-hour queue, mule-ring alerts and a ready bank-freeze draft
>
> Synthetic data only. Prototype, not an official service. Demo 👇
> #GnaniAI #GreatIndianAIInternshipChallenge

Replace the 76% → 99.6% with your **audio-mode** numbers once you have them. They are stronger because they use real Prisma.

## Four-day plan

| Day | Do this | Done when |
|---|---|---|
| **1 (today)** | Register; put the key in `.env`; run `python scripts/check_gnani.py`; ask on Discord for Evon access and for the Prisma realtime final-event name | Timbre → Prisma round-trip works and the engine reads the UTR |
| **2** | `python -m eval.run_eval --audio --calls 30 --snr 10`; fix whatever real Prisma output breaks (e.g. Devanagari number words); try Evon on a GPU (HF endpoint) or drop it honestly | Audio-mode report with real numbers |
| **3** | Follow `docs/GROUND_RESEARCH.md`: a 15-min talk with your sister (bank side), 5 volunteers on `/collect.html` + mock calls, then `python -m eval.run_real`. Adjust `outputs.py` from her feedback | Quote, real-voice accuracy table, updated freeze draft |
| **4** | Record the 60 s video (live voice), post on LinkedIn and X, nominate the posts, submit before **11:59 PM IST, 10 Nov**. Share genuinely with your network; no engagement swaps | Submitted |

## Interview: likely questions and honest answers

- **"Why not just use the LLM to extract everything?"** Numbers are where LLMs and ASR slip, and a wrong UTR is worse than none. Deterministic validators plus read-back give guarantees, and the LLM adds summaries on top.
- **"What did you verify, and what didn't you?"** 117 automated tests cover the engine, dialog, UI and request formats. A live run with my key put Timbre audio through an 8 kHz noisy phone line into Prisma v3.0 and the engine got the amount and UTR right; that run also exposed a real bug (amount and UTR glued into one number), which I fixed and turned into a regression test. Not yet measured: accuracy across many real voices.
- **"What breaks first in production?"** Real telephony (SIP/Exotel), caller verification, integration with the national reporting portal, and languages beyond Hindi and English.
- **"How is this different from a form-filling bot?"** Golden-hour prioritisation, a live-threat interrupt, mule-ring linking across calls, and the action drafts. It's built for the officer's next step, not just data entry.
