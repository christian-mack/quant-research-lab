"""One-off extractor for Phase 3 step 0 definition passages."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPTS = ROOT / "data" / "processed" / "transcripts"

KEYWORD_QUERIES = [
    "optimal trade entry",
    "ote",
    "retracement",
    "62",
    "70",
    "79",
    "fib",
    "dealing range",
    "equilibrium",
    "fair value gap",
    "imbalance",
    "displacement",
    "market structure",
    "short term",
    "swing",
    "target",
    "liquidity pool",
    "take profit",
    "objective",
    "one tick",
    "two tick",
    "stop",
    "lower low",
    "higher high",
]


def extract_window(video_id: str, timestamps: list[int], window: float = 25.0) -> None:
    path = TRANSCRIPTS / f"{video_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    print(f"\n{'=' * 72}")
    print(f"{video_id}: {data.get('title', '')}")
    print("=" * 72)
    for ts in timestamps:
        print(f"\n--- @{ts}s (+-{window}s) ---")
        hits = [
            seg
            for seg in data["segments"]
            if seg["start"] >= ts - window and seg["start"] <= ts + window
        ]
        if not hits:
            print("  (no segments)")
            continue
        for seg in hits:
            print(f"  [{seg['start']:7.1f}] {seg['text']}")


def keyword_search(video_id: str, keywords: list[str]) -> None:
    path = TRANSCRIPTS / f"{video_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    print(f"\n{'=' * 72}")
    print(f"KEYWORD SEARCH: {video_id}")
    print("=" * 72)
    for kw in keywords:
        pat = re.compile(re.escape(kw), re.IGNORECASE)
        matches = [seg for seg in data["segments"] if pat.search(seg["text"])]
        if matches:
            print(f"\n  >> '{kw}' ({len(matches)} hits)")
            for seg in matches[:8]:
                print(f"     [{seg['start']:7.1f}] {seg['text']}")
            if len(matches) > 8:
                print(f"     ... +{len(matches) - 8} more")


def main() -> None:
    windows = {
        "Bkt8B3kLATQ": [
            1110,
            1416,
            1048,
            1156,
            1210,
            1215,
            1267,
            1275,
            1258,
            1729,
            2152,
            2308,
            2506,
            2729,
        ],
        "8GkQfdAXZP0": [2247, 1913, 1920, 1931, 1969, 2764, 2788, 2872],
        "CnTXwAuDi9Y": [1574, 1951, 1971, 2006, 2171, 2235, 2259, 2426, 2533, 2612],
        "36184dDAqtM": [
            645,
            846,
            1231,
            1310,
            1346,
            1982,
            2557,
            2568,
            2587,
            2596,
            2610,
            2620,
            2743,
        ],
        "2XhDi5GoNUI": [447, 985, 1000, 1011, 1017, 1110, 1120, 1127, 1179, 2554, 2567],
    }
    for vid, tss in windows.items():
        extract_window(vid, tss)


if __name__ == "__main__":
    main()
