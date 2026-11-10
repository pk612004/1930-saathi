"""Day-1 check: is your Gnani key working, and does Prisma understand Timbre's Hindi on a phone line?

    python scripts/check_gnani.py

1. Timbre speaks a Hindi complaint sentence.
2. The audio is converted to 8 kHz telephone quality with street noise.
3. Prisma transcribes it (REST, then realtime WebSocket).
4. The 1930 Saathi engine extracts amount and UTR from what Prisma heard.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from saathi import audio as A  # noqa: E402
from saathi import extract as X  # noqa: E402
from saathi.config import settings  # noqa: E402
from saathi.providers.gnani import PrismaRealtimeSTT, PrismaSTT, ProviderError, TimbreTTS  # noqa: E402

SENTENCE = "मेरे पैंतालीस हज़ार रुपये कट गए। यूटीआर है चार एक दो तीन पाँच छह सात आठ नौ शून्य एक दो।"


def main():
    if not settings.gnani_api_key:
        sys.exit("Set GNANI_API_KEY in .env first (copy .env.example).")
    out = Path(settings.data_dir) / "check"
    out.mkdir(parents=True, exist_ok=True)
    print("1) Timbre ...", end=" ", flush=True)
    try:
        r = TimbreTTS().synthesize(SENTENCE, language="hi-IN")
    except ProviderError as e:
        sys.exit(f"FAILED: {e}")
    (out / "timbre.wav").write_bytes(r["audio"])
    print(f"ok, {A.duration_s(r['audio']):.1f}s audio in {r['latency_ms']:.0f} ms -> data/check/timbre.wav")

    phone = A.to_telephone(r["audio"], 8000)
    x, sr = A.read_wav(phone)
    noisy = A.write_wav(A.mix_at_snr(x, A.make_noise(len(x), sr, "street", 1), 10), sr)
    (out / "phone_noisy.wav").write_bytes(noisy)
    print("2) 8 kHz phone line + street noise at 10 dB SNR -> data/check/phone_noisy.wav")

    for name, stt in (("Prisma REST", PrismaSTT()), ("Prisma realtime", PrismaRealtimeSTT(sample_rate=8000))):
        print(f"3) {name} ...", end=" ", flush=True)
        try:
            res = stt.transcribe(noisy, language="hi-IN")
        except ProviderError as e:
            print(f"FAILED: {e}")
            continue
        print(f"{res.latency_ms:.0f} ms\n   heard: {res.text}")
        ex = X.extract_all(res.text, expecting="utr")
        amt = X.N.parse_amount(res.text, expecting_amount=True)
        print(f"   engine -> amount: {amt}  UTR: {ex.utr or ex.utr_partial}")


if __name__ == "__main__":
    main()
