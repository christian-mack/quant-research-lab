"""D7 formal golden-set scorer — uses the correct PCS tool path per query."""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass

from quant_research.context.config import repo_root
from quant_research.context.indexer import index_status
from quant_research.context.pinned import get_pinned_context
from quant_research.context.retriever import search


@dataclass
class Case:
    num: int
    query: str
    tool: str  # search | pinned
    pinned_doc: str | None
    must_have: list[str]
    must_not: list[str]
    trap: bool = False
    preserve: bool = False


CASES = [
    Case(1, "What is the graded ORB+Opt3 per-contract figure?", "search", None,
         ["2026-05-13", "1,088"], ["$10,885/yr per contract"], trap=True),
    Case(2, "Why was production cut to ORB+Opt3?", "search", None,
         ["2026-04-28", "displacement", "tri-module"], ["flux-v1-development-roadmap"], trap=True, preserve=True),
    Case(3, "What is the max sustainable qty rule?", "pinned", "docs/phase-2-kickoff.md",
         ["R(q)", "max(1.5", "sustainable"], []),
    Case(4, "What timezone is the NT8 export in?", "search", None,
         ["2026-04-27", "UTC"], [], trap=True),
    Case(5, "When does Phase 1b start?", "search", None,
         ["2026-04-30", "after Phase 1", "not", "parallel"], [], trap=True),
    Case(6, "What are the Apex EOD constraints?", "pinned", "docs/ai-project-instructions.md",
         ["$2,000", "trailing", "DLL", "$3,000"], []),
    Case(7, "Is the +$500 in R(q) the DLL?", "pinned", "docs/phase-2-kickoff.md",
         ["R(q)", "$500", "DLL"], []),
    Case(8, "What happened with M6 bracket re-arm?", "search", None,
         ["re-arm", "2026-04-28", "M6"], [], preserve=True),
    Case(9, "Which engine is trusted for backtests?", "search", None,
         ["M4", "engine"], []),
    Case(10, "What is Wave 0 and has it completed?", "pinned", "docs/current-working-plan.md",
         ["Wave 0", "complete"], []),
    Case(11, "What are the current pre-registered hypotheses?", "search", None,
         ["research-log", "hypoth"], []),
    Case(12, "Why was volume-crossover roll methodology abandoned?", "search", None,
         ["2026-04-26", "volume", "crossover"], []),
]

PRESERVE_INCOME = Case(
    0, "per-account income gap research priority ORB Opt3", "search", None,
    ["65", "100", "priority", "income"], ["$10,885/yr per contract"], preserve=True,
)


def _doc_text(ctx, rel: str) -> str:
    for d in ctx.docs:
        if d.file_path.replace("\\", "/") == rel.replace("\\", "/"):
            return d.text
    return ""


def eval_case(c: Case) -> dict:
    if c.tool == "pinned":
        ctx = get_pinned_context()
        text = _doc_text(ctx, c.pinned_doc or "")
        top = [{"rank": 1, "file_path": c.pinned_doc, "status": "pinned", "score": 1.0,
                "snippet": text.splitlines()[0][:100] if text else "(missing doc)"}]
        blob = text.lower()
        hit = all(m.lower() in blob for m in c.must_have) if c.must_have else bool(text)
        bad = any(m.lower() in blob for m in c.must_not)
        return {"pass": bool(text) and hit and not bad, "hit": hit, "bad": bad, "top": top}

    results = search(c.query, top_k=3)
    top = []
    blob = ""
    current_blob = ""
    for i, r in enumerate(results, 1):
        top.append({"rank": i, "file_path": r.file_path, "status": r.status,
                    "score": round(r.score, 4), "breadcrumb": r.breadcrumb,
                    "snippet": (r.text.splitlines()[0][:100] if r.text else "")})
        part = f"{r.file_path} {r.breadcrumb} {r.text}".lower()
        blob += part
        if r.status == "current":
            current_blob += part

    hit = all(any(m.lower() in blob for m in [mh]) for mh in c.must_have) if c.must_have else bool(results)
    # simpler: any must_have in blob
    hit = all(m.lower() in blob for m in c.must_have) if c.must_have else bool(results)
    bad = any(m.lower() in current_blob for m in c.must_not)
    if c.num == 1:
        # Correction entry quotes the misread while negating it — that is not a trap fail.
        bad = any(
            "$10,885/yr per contract" in t.get("snippet", "") + t.get("breadcrumb", "")
            and "correction" not in t.get("breadcrumb", "").lower()
            for t in top
            if t.get("status") == "current"
        )

    # Trap #4: superseded DST wrong-rationale chunk must not appear in default results
    if c.num == 4:
        bad = bad or any("dst-gap timestamps" in t.get("breadcrumb", "").lower() for t in top)

    # Trap #5: must not surface parallel-track-as-current framing
    if c.num == 5:
        bad = bad or ("parallel with phase 1" in current_blob or "in parallel with it" in current_blob
                      and "not" not in current_blob[:current_blob.find("parallel")+20])

    return {"pass": hit and not bad and bool(results), "hit": hit, "bad": bad, "top": top}


def staleness_test() -> dict:
    root = repo_root()
    target = root / "docs" / "lessons-log.md"
    original = target.read_bytes()
    st_before = index_status()
    before_stale = list(st_before.stale_files)
    # mutate content without reindex
    target.write_bytes(original + b"\n")
    st_after = index_status()
    target.write_bytes(original)
    drifted = "docs/lessons-log.md" in st_after.stale_files
    return {
        "pass": drifted and "docs/lessons-log.md" not in before_stale,
        "before_stale": before_stale,
        "after_stale": st_after.stale_files,
    }


def main() -> int:
    ok = True
    print("D7 GOLDEN QUERY SCORING\n")
    for c in CASES:
        r = eval_case(c)
        flag = "PASS" if r["pass"] else "FAIL"
        if not r["pass"]:
            ok = False
        tags = []
        if c.trap:
            tags.append("TRAP")
        if c.preserve:
            tags.append("PRESERVE")
        t = f" [{','.join(tags)}]" if tags else ""
        print(f"#{c.num:02d} {flag}{t} | tool={c.tool} | {c.query}")
        print(f"     hit={r['hit']} bad={r['bad']}")
        for h in r["top"]:
            print(f"     [{h['rank']}] {h.get('score','-')} {h['status']} {h['file_path']}")
            if h.get("breadcrumb"):
                print(f"          {h['breadcrumb'][:95]}")
            print(f"          {h.get('snippet','')[:95]}")

    pr = eval_case(PRESERVE_INCOME)
    if not pr["pass"]:
        ok = False
    print(f"\nPRESERVE income-gap: {'PASS' if pr['pass'] else 'FAIL'}")
    for h in pr["top"]:
        print(f"     [{h['rank']}] {h['file_path']} — {h.get('snippet','')[:90]}")

    # Q11 also needs working plan (pinned)
    ctx = get_pinned_context()
    wp = _doc_text(ctx, "docs/current-working-plan.md").lower()
    q11_wp = "hypoth" in wp or "wave 1" in wp or "pre-register" in wp
    print(f"\nQ11 working-plan (pinned) supplement: {'PASS' if q11_wp else 'FAIL'}")
    if not q11_wp:
        ok = False

    st = staleness_test()
    print(f"\nstatus() staleness test: {'PASS' if st['pass'] else 'FAIL'}")
    print(f"  before stale: {st['before_stale']}")
    print(f"  after mutate: {st['after_stale']}")
    if not st["pass"]:
        ok = False

    print(f"\nOVERALL: {'ALL PASS' if ok else 'FAILURES'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
