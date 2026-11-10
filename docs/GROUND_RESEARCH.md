# Ground research kit

The code cannot do this part for you. It only takes about **3 hours**, and it is the strongest proof you can show a jury that the problem is real and that you understood it. Do these three things, in this order.

## 1. Bank side: 15 minutes with someone in banking (your sister counts)

**Goal:** learn what a bank needs, and how quickly, to hold money after a 1930 complaint.

Ask (and write the answers down word for word):

1. When a cyber-fraud complaint reaches the bank, what arrives? Which fields do you actually look at first?
2. Which missing or wrong detail most often delays a hold? (UTR? beneficiary account? time?)
3. How quickly does money usually leave the first beneficiary (mule) account?
4. Is anything in our freeze-request draft wrong or missing? Show them the *Bank freeze request* tab in the console.
5. Do you see repeat beneficiary accounts across complaints? How do you find out today?
6. Can I quote one sentence from you in my demo video? (Get a yes. Name optional, e.g. "a bank collections manager".)

Then update `saathi/outputs.py` (`bank_freeze_request`) to match what they said, and mention the change in your post.

## 2. Helpline / police side: one call or visit

**Goal:** one real data point from the people who answer the phone.

Options, from easiest to hardest:
- **A cyber-cell awareness event** at college. Police often run these. Ask the officer 3 questions after the talk.
- **A retired or serving police contact** in your family or network.
- **Your district cyber cell**, during working hours, introducing yourself as a student building a prototype.

Questions:
1. What is the hardest part of taking a complaint on the phone from a panicked person?
2. Which details do callers most often not have, or get wrong?
3. Would an AI that answers when lines are busy (and never rejects a complaint) help or worry you? Why?

Never ask for real complaint data, recordings or victim details, and never record anyone without permission.

## 3. Users: 5 people, 20 minutes each

Use friends or family, ideally including one person over 55 and one who prefers Punjabi.

1. Start the server with a collection key:
   `COLLECT_KEY=mysecret python -m saathi.server`
2. Share `http://<your-laptop-ip>:8930/collect.html?key=mysecret`. Each person reads about 10 synthetic cards in their language, about 3 minutes each.
3. Then give each person a full mock call on `/caller.html`, using a **made-up story**, and ask them to rate it on `/verify.html` (the feedback box).
4. Run `python -m eval.run_real` (needs `GNANI_API_KEY`). This creates `eval/real_report.md`: **real accuracy from real voices**.

### Consent script (read before recording)

> "This is a student project. You'll read made-up numbers from a card, never your own. Your recording is used only to test accuracy and is deleted after the hackathon. You can stop anytime. Is that okay?"

## What to put in the video and the post

| Evidence | Where it comes from |
|---|---|
| "A bank collections manager told me ___" | Step 1 quote |
| "An officer said the hardest part is ___" | Step 2 |
| "Tested with N volunteers in Hindi, Punjabi, English: UTR accuracy X%" | `eval/real_report.md` |
| "Average caller rating Y★" | console → Feedback panel |

## Results template (fill it in)

| Date | Who (role only) | Key insight | What I changed in the code |
|---|---|---|---|
| | | | |
| | | | |
