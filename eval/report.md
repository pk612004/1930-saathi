# 1930 Saathi evaluation

All calls are synthetic (random amounts, UTRs, UPI IDs and phone numbers).
Text-mode numbers measure the understanding + dialog layer with *simulated* recognition errors;
audio-mode numbers (when present) include real Gnani Timbre -> 8 kHz noisy audio -> Gnani Prisma.

## text (simulated ASR errors) · 500 calls · disfluent speech (fillers, digit stutters) · simulated digit-error rate 0.0

| Metric | Value |
|---|---|
| Complaints filed | 100.0% |
| UTR correct as first heard | 96.7% |
| UTR correct after validator + read-back | **100.0%** |
| Wrong UTR filed | 0.0% |
| UTR left 'not known' (safe fallback) | 0.0% |
| Fraudster ID correct, first heard → final | 86.2% → **99.4%** |
| Amount / time / bank correct | 100.0% / 100.0% / 100.0% |
| Fraud pattern correct | 99.0% |
| Live-threat recall / false positives | 96.2% / 0.0% |
| Turns per call (mean / p90) | 12.0 / 16 |
| Estimated call length (mean / p90) | 139 s / 178 s |

| Language (transcript style) | Calls | Filed | Amount | UTR final | Wrong UTR | Fraudster ID | Bank | Fraud type |
|---|---|---|---|---|---|---|---|---|
| Hindi (Devanagari, like Prisma hi-IN) | 123 | 100.0% | 100.0% | 100.0% | 0.0% | 99.2% | 100.0% | 100.0% |
| English | 77 | 100.0% | 100.0% | 100.0% | 0.0% | 98.7% | 100.0% | 100.0% |
| Hinglish (Latin) | 201 | 100.0% | 100.0% | 100.0% | 0.0% | 100.0% | 100.0% | 100.0% |
| Punjabi (Gurmukhi) | 50 | 100.0% | 100.0% | 100.0% | 0.0% | 98.0% | 100.0% | 100.0% |
| Tamil (Tamil script) | 49 | 100.0% | 100.0% | 100.0% | 0.0% | 100.0% | 100.0% | 89.8% |

## text (simulated ASR errors) · 500 calls · disfluent speech (fillers, digit stutters) · simulated digit-error rate 0.25

| Metric | Value |
|---|---|
| Complaints filed | 100.0% |
| UTR correct as first heard | 72.7% |
| UTR correct after validator + read-back | **99.3%** |
| Wrong UTR filed | 0.0% |
| UTR left 'not known' (safe fallback) | 0.7% |
| Fraudster ID correct, first heard → final | 75.4% → **99.4%** |
| Amount / time / bank correct | 100.0% / 100.0% / 100.0% |
| Fraud pattern correct | 99.0% |
| Live-threat recall / false positives | 96.2% / 0.0% |
| Turns per call (mean / p90) | 12.7 / 16 |
| Estimated call length (mean / p90) | 146 s / 188 s |

| Language (transcript style) | Calls | Filed | Amount | UTR final | Wrong UTR | Fraudster ID | Bank | Fraud type |
|---|---|---|---|---|---|---|---|---|
| Hindi (Devanagari, like Prisma hi-IN) | 123 | 100.0% | 100.0% | 99.1% | 0.0% | 99.2% | 100.0% | 100.0% |
| English | 77 | 100.0% | 100.0% | 100.0% | 0.0% | 97.4% | 100.0% | 100.0% |
| Hinglish (Latin) | 201 | 100.0% | 100.0% | 98.9% | 0.0% | 100.0% | 100.0% | 100.0% |
| Punjabi (Gurmukhi) | 50 | 100.0% | 100.0% | 100.0% | 0.0% | 100.0% | 100.0% | 100.0% |
| Tamil (Tamil script) | 49 | 100.0% | 100.0% | 100.0% | 0.0% | 100.0% | 100.0% | 89.8% |

Estimated call length assumes 2.4 spoken words per second for both sides plus 0.8 s per turn.
