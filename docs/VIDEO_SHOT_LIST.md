# 1930 Saathi: video shot list (what to open, what to click, what to say)

Length: about 90 seconds after editing. You speak in simple English. When Saathi (the Gnani voice) speaks, stay quiet.

## A. Before recording (10 minutes, not on camera)

1. **Terminal (VS Code):**
   ```
   del data\saathi.db
   python -m saathi.server
   ```
   Check the line says `STT: gnani-prisma  TTS: gnani-timbre  mock=False`.
2. **Browser clean-up:**
   - Close every other tab (especially the Claude tabs).
   - Hide the bookmarks bar (Ctrl+Shift+B).
   - Turn on Windows Focus / Do not disturb so no pop-ups appear.
   - Do **not** open `.env` at any point.
3. **Make two browser windows:**
   - Window 1: `127.0.0.1:8930` (Overview). You will use this window for the Overview and Caller pages.
   - Window 2: `127.0.0.1:8930/console.html` → log in `admin` / `saathi-demo-1930`.
     If it opens without asking, that's fine (you're still logged in).
   - In Window 2, click **Load demo complaints** now. Check the top counter shows about **₹4,23,500** and RING-01 shows **3 victims**.
4. **Caller settings (Window 1, Caller page):** "Play agent voice" ✅ ticked, Language: Auto-detect. Laptop volume ~60%. **No earphones.**
5. **Recorder:** press **Win + Shift + R** (Snipping Tool) → select the full screen → in its toolbar turn **Mic ON** and **System audio ON**. Do one 5-second test recording and play it back: you should hear yourself and the Saathi voice.

Record each clip separately. If you make a mistake, just redo that clip.

---

## Clip 1: The problem (Window 1, Overview page) ~15 s

| Do | Say |
|---|---|
| Window 1 full screen on the **Overview** page. Start recording | "Hi, I'm Prakash. When someone loses money to online fraud in India, they call the 1930 helpline." |
| Slowly scroll down to **Why it matters** | "If the fraud is reported in the first two hours, 70 to 80 percent of the money can be stopped. After that, only 15 to 20 percent. But the line is often busy." |
| Scroll back up, move the mouse over the green badges **STT: gnani-prisma** and **TTS: gnani-timbre** | "So I built 1930 Saathi, a voice agent on Gnani's Prisma speech-to-text and Timbre text-to-speech. It is running live right now." |

Stop recording.

## Clip 2: Saving the caller first (Window 1, Caller page, mic) ~20 s

| Do | Say |
|---|---|
| Click **Caller** at the top. Start recording | "Let me be the victim." |
| Click **Start call**. Wait for Saathi's greeting to finish | (quiet) |
| **Press and hold** the round mic button, say clearly: *"CBI wale video call pe hain, abhi bhi call chal raha hai"*, then **release** | (that line is you acting as the caller) |
| Saathi's text appears with "gnani-prisma" under your line, then Saathi speaks the safety warning | (quiet until it finishes) |
| Point the mouse at **Scam still going on? → Live threat** on the right | "Prisma understood my Hinglish. The scam is still going on, so Saathi first tells me to cut that call and not share any OTP." |
| Click **End call** | |

Stop recording. (If the mic shows an error, do it again; speak 1 second after pressing.)

## Clip 3: Every number checked + officer sees it live (split screen) ~40 s before speed-up

| Do | Say |
|---|---|
| Put **Window 1 (Caller)** on the left: click it, press **Win + ←**. Put **Window 2 (Console)** on the right: click it, press **Win + →**. If text is cut, press **Ctrl + −** once in each window | |
| In the Caller window, pick **"KYC call, UTR said with a missing digit (validator demo)"** in the Demo scripts box. Start recording | "Now a second caller. On the right is the officer's screen." |
| Click **Play script** | (quiet for a few seconds) |
| On the console, the **On call now** card appears and fills in | "The officer can watch the case being built while the caller is still talking." |
| When Saathi says it heard 11 digits | "The caller missed one digit of the UTR. Saathi noticed it needs 12 digits and asked again." |
| When Saathi reads back the UTR and the UPI ID | "Every number is read back and confirmed before it is saved." |
| Call ends. On the console the toast **"RING-01 now has 4 victims"** appears | "This is the fourth victim who paid the same UPI ID, so the system raises a mule-ring alert." |

Stop recording. (In editing, speed the middle part up 2×.)

## Clip 4: What the officer does (Window 2, Console) ~25 s

| Do | Say |
|---|---|
| Click Window 2 and press **Win + ↑** to make it full screen. Start recording. Point at the big number at the top | "At the top, the officer sees how much money can still be saved inside the golden window." |
| Point at **Next to run out** (orange) | "And which case will run out of time next." |
| Click the ₹55,000 case in the queue. Point at the timeline line under the title | "Each case has a timeline: when the money left, when they called, and how much time is left." |
| Click **Mark freeze request sent**. The big number goes down | "When the officer sends the freeze request, that money moves out of the at-risk number." |
| Click the **Bank freeze request** tab, then **SMS to caller** | "The bank freeze request and the SMS to the victim are already drafted." |
| (end) | "In 500 test calls, not a single wrong UTR was filed. This is 1930 Saathi, built on Gnani AI. Thank you." |

Stop recording.

---

## B. Editing (Clipchamp, comes with Windows)

1. Open **Clipchamp** → **Create a new video** → drag in the 4 clips in order 1, 2, 3, 4.
2. Cut the silent start and end of each clip (select clip → drag its edges).
3. Clip 3: split it where the waiting part starts and ends, select the middle part → **Speed** → 2×.
4. Optional: add a text at the very end: `#GnaniAI #GreatIndianAIInternshipChallenge`.
5. **Export → 1080p**. Watch it once fully with sound.

Target: about 90 seconds.
