"""Generate a larger, deterministic benchmark catalog so the engine does
measurable work (non-zero step durations). Reproducible — no randomness.

This is a LOAD/benchmark dataset (generated test data), not customer data.
The engine runs on it for real, so the durations the run report shows are
genuinely measured — only the catalog content is synthetic.

    python samples/gen_benchmark.py            # writes samples/benchmark-1500.csv
    python samples/gen_benchmark.py 3000       # custom work count
"""
import sys
from pathlib import Path

N = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
OUT = Path(__file__).resolve().parent / f"benchmark-{N}.csv"

FIRST = ["Anna", "Erik", "Maria", "Johan", "Sara", "Lars", "Emma", "Nils",
         "Karin", "Olof", "Linnea", "Gustav", "Elsa", "Sven", "Astrid", "Per"]
LAST = ["Lindqvist", "Berg", "Holm", "Sandberg", "Ek", "Lund", "Falk", "Ros",
        "Strand", "Vinter", "Norén", "Dahl", "Hallin", "Sjö", "Brandt", "Ohlsson"]
SOC = ["STIM", "TONO", "GEMA", "SACEM", "PRS", "KODA", "TEOSTO"]
ROLES_OK = ["CA", "C", "A", "AR"]


def main():
    lines = ["title,name,role,share_percent,ipi,society,iswc,isrc"]
    for i in range(N):
        title = f"Work {i+1:04d} — {LAST[i % len(LAST)]}sången"
        # two contributors per work
        a_first = FIRST[i % len(FIRST)]
        a_last = LAST[(i // 3) % len(LAST)]
        b_first = FIRST[(i + 7) % len(FIRST)]
        b_last = LAST[(i + 5) % len(LAST)]

        # Deterministic, varied defects so detect_issues does real work:
        bad_split = (i % 4 == 0)          # 25% have split != 100
        miss_iswc = (i % 3 == 0)          # ~33% missing ISWC
        miss_ipi = (i % 5 == 0)           # 20% second writer missing IPI
        foreign = (i % 6 == 0)            # ~17% foreign society, no declaration
        bad_role = (i % 9 == 0)           # ~11% invalid role

        share_a, share_b = ("60", "30") if bad_split else ("50", "50")
        soc_a = "STIM"
        soc_b = SOC[i % len(SOC)] if foreign else "STIM"
        role_a = "XX" if bad_role else "CA"
        iswc_a = "" if miss_iswc else f"T-{900000000 + i}-1"
        ipi_b = "" if miss_ipi else f"{500000000 + i:09d}"
        isrc = f"SE-A1A-{24:02d}-{i:05d}"

        lines.append(f'"{title}","{a_first} {a_last}",{role_a},{share_a},{600000000+i:09d},{soc_a},{iswc_a},{isrc}')
        lines.append(f'"{title}","{b_first} {b_last}",CA,{share_b},{ipi_b},{soc_b},{iswc_a},{isrc}')

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT}  ({N} works, {N*2} contributor rows)")


if __name__ == "__main__":
    main()
