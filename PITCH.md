# 1930 Saathi: one-page solution pitch

**Golden-hour voice intake for cyber-fraud victims, built on Gnani AI Prisma + Timbre.**
Prakash Kumar · Thapar Institute of Engineering & Technology, Patiala · solo entry

## The problem
- India's cyber-fraud helpline **1930** received about **3.24 crore calls in 2025**, roughly one every second.
- Reported recovery is **70–80% if the fraud is reported in the first two hours, 15–20% after**. Lines get busy, and every minute on hold is money moving to the next mule account.
- A complaint needs exact numbers: the **12-digit UTR**, the fraudster's UPI ID or account, the bank. Panicked callers speak Hinglish and get digits wrong, and **one wrong digit sends the freeze request to the wrong transaction**.

## The solution
A voice agent that answers the victim immediately and hands the officer a ready case.

| For the victim (on the phone) | For the officer (console) |
|---|---|
| **Gnani Prisma** transcribes Hindi, Hinglish, English, Punjabi, Tamil on noisy 8 kHz phone audio | **Money-at-risk counter**: rupees still inside the golden window, live, plus what runs out next |
| A custom engine understands "saade teen hazaar", "dedh lakh", "chaar ek do teen…", digits in Devanagari, Gurmukhi and Tamil script | **Queue ranked by recoverable money** with a countdown per case |
| Every UTR, UPI ID, account and mobile is **validated in code** ("I heard 11 digits, a UTR has 12") | **Supervisor live view**: the case fills in while the victim is still talking |
| **Gnani Timbre** reads critical numbers back for the caller to confirm | **Mule-ring detection**: victims paying the same UPI ID or account are linked; repeat reports of one debit are flagged, not double-counted |
| **Live-threat interrupt**: still on a "digital arrest" video call or AnyDesk open → safety first | **Drafts ready**: bank freeze request, portal complaint, SMS to the caller, case timeline, audit trail |

## Proof
- **Live Gnani run** (10 Nov 2026): Timbre audio cut to 8 kHz with street noise at 10 dB SNR → Prisma v3.0 got the amount and UTR right. It also exposed a real bug (amount and UTR glued into one number), now fixed and tested.
- **500 synthetic calls**, 25% of digits deliberately misheard: UTR correct **72.7% on first hearing → 99.3% after validation and read-back, 0 wrong UTRs filed**. Live-threat recall 96.2%, 0 false positives.
- 118 automated tests; held-out phrasing sets 16/16 and 38/38.

## Gnani AI technology
- **Prisma v3.0**: REST `/stt/v3` and realtime WebSocket, language auto-detect
- **Timbre v2.5**: questions, safety warning, digit-by-digit read-back (voice Nalini)
- Evon v3.3 integration written (validator-gated fallback) but not used in the demo, as Evon is not on the API platform yet

## What's next
Pilot with a cyber cell on a real phone number (Twilio/Exotel streaming already implemented), accuracy study with real voices, native review of Punjabi and Tamil prompts, Timbre streaming for faster read-backs.

*Prototype with synthetic data only. Not an official government service.*
