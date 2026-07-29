"""PCS command-line interface.

``pcs {reindex,search,pinned,status,doctor,hook-test}`` — the CLI is the fallback and
debugging surface for the system (the MCP server is the primary agent
integration, added in D6). Only ``doctor`` is implemented in the D1 slice;
the remaining subcommands are scaffolded and land in later milestones.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

import psycopg

from quant_research.context.config import SCHEMA_VERSION, PCSConfig, get_config, repo_root
from quant_research.context.manifest import (
    MANIFEST_PATH_REL,
    ManifestError,
    assert_manifest_valid,
    iter_latent_split,
    iter_split_required,
    load_manifest,
    write_scaffold,
)
from quant_research.context.migrate import _current_version


def _check(label: str, ok: bool, detail: str = "") -> bool:
    """Print a single doctor check line and return its status."""
    mark = "PASS" if ok else "FAIL"
    suffix = f" - {detail}" if detail else ""
    print(f"  [{mark}] {label}{suffix}")
    return ok


def doctor(config: PCSConfig | None = None) -> int:
    """Report on database health. Returns a process exit code (0 = healthy)."""
    config = config or get_config()
    print(f"PCS doctor - {config.db_host}:{config.db_port}/{config.db_name}")

    checks: list[bool] = []
    try:
        with psycopg.connect(config.dsn(), connect_timeout=5) as conn:
            checks.append(_check("database connection", True))

            with conn.cursor() as cur:
                cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'")
                row = cur.fetchone()
            checks.append(
                _check("pgvector extension present", row is not None, row[0] if row else "missing")
            )

            version = _current_version(conn)
            checks.append(
                _check(
                    f"schema at version {SCHEMA_VERSION}",
                    version == SCHEMA_VERSION,
                    f"found {version}" if version != SCHEMA_VERSION else "",
                )
            )

            with conn.cursor() as cur:
                cur.execute(
                    "SELECT to_regclass('public.pcs_index_run'), "
                    "to_regclass('public.pcs_document'), "
                    "to_regclass('public.pcs_chunk')"
                )
                tables = cur.fetchone()
            checks.append(
                _check("core tables present", all(t is not None for t in tables))
            )

            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM pcs_chunk")
                (chunk_count,) = cur.fetchone()
            _check(f"chunk rows indexed: {chunk_count}", True)
    except psycopg.OperationalError as exc:
        _check("database connection", False, str(exc).strip().splitlines()[0])
        checks.append(False)

    # Manifest gate (D2): stays RED until every Tier-2 target is classified.
    try:
        assert_manifest_valid()
        checks.append(_check("manifest fully classified", True))
        manifest_path = repo_root() / MANIFEST_PATH_REL
        manifest_doc = load_manifest(manifest_path) if manifest_path.exists() else {}
        pending = iter_split_required(manifest_doc) if manifest_doc else []
        if pending:
            _check(f"split_required pending for D3: {len(pending)}", True)
        latent = iter_latent_split(manifest_doc) if manifest_doc else []
        if latent:
            _check(f"latent_split_note recorded (off-surface): {len(latent)}", True)
    except ManifestError as exc:
        detail = f"{len(exc.errors)} issue(s); run 'pcs manifest-check'" if exc.errors else str(exc)
        checks.append(_check("manifest fully classified", False, detail))

    healthy = all(checks)
    print("\nPCS doctor: " + ("healthy" if healthy else "UNHEALTHY"))
    return 0 if healthy else 1


def _print_split_required() -> None:
    """Print entries flagged split_required — the debt D3's chunker must clear."""
    manifest_path = repo_root() / MANIFEST_PATH_REL
    if not manifest_path.exists():
        return
    manifest = load_manifest(manifest_path)
    pending = iter_split_required(manifest)
    if pending:
        print(
            f"\nsplit_required (D3 must split these {len(pending)}; golden query #1 is the test):"
        )
        for item in pending:
            print(f"  - {item.location}")
    latent = iter_latent_split(manifest)
    if latent:
        print(
            f"\nlatent_split_note (off-surface; {len(latent)}; no D3 obligation, "
            "split only if promoted/recalled):"
        )
        for item in latent:
            print(f"  - {item.location}")


def manifest_check() -> int:
    """Validate the manifest and print every issue. Returns 0 when clean."""
    try:
        assert_manifest_valid()
    except ManifestError as exc:
        print(f"manifest: FAIL - {exc}")
        for err in exc.errors:
            print(f"  - {err}")
        _print_split_required()
        return 1
    print("manifest: OK - every Tier-2 file and dated entry is classified")
    _print_split_required()
    return 0


def manifest_scaffold(force: bool) -> int:
    """Write the draft manifest worklist to docs/context-manifest.yml."""
    try:
        path = write_scaffold(force=force)
    except ManifestError as exc:
        print(str(exc))
        return 1
    print(f"wrote draft manifest: {path}")
    return 0


def reindex(force: bool) -> int:
    """Walk, chunk, embed, and upsert the Tier-2 corpus (D4)."""
    from quant_research.context.indexer import reindex as run_reindex

    try:
        result = run_reindex(force=force)
    except ManifestError as exc:
        print(f"reindex aborted - manifest not clean: {exc}")
        for err in exc.errors:
            print(f"  - {err}")
        return 1
    except psycopg.OperationalError as exc:
        print(f"reindex failed - database: {str(exc).strip().splitlines()[0]}")
        return 1

    if result.up_to_date:
        print(f"reindex: up to date - {result.files_skipped} file(s) unchanged, 0 rows written")
    else:
        print(
            f"reindex: run {result.run_id} - {result.files_indexed} file(s) indexed, "
            f"{result.files_skipped} skipped, {result.chunks_written} chunk(s) written"
        )
    return 0


def search_cmd(query: str, top_k: int, include_superseded: bool) -> int:
    """Hybrid search with inline provenance (§5.2)."""
    if not query.strip():
        print('usage: pcs search "<query>" [--top-k N] [--include-superseded]')
        return 2
    from quant_research.context.retriever import search as run_search

    try:
        results = run_search(query, top_k=top_k, include_superseded=include_superseded)
    except psycopg.OperationalError as exc:
        print(f"search failed - database: {str(exc).strip().splitlines()[0]}")
        return 1

    if not results:
        print("no results")
        return 0
    for i, r in enumerate(results, start=1):
        entry = r.entry_date.isoformat() if r.entry_date else "-"
        sha = r.git_sha[:12]
        print(
            f"[{i}] score={r.score:.4f}  status={r.status}  {r.file_path}  "
            f"date={entry}  sha={sha}"
        )
        first_line = r.text.splitlines()[0] if r.text else r.breadcrumb
        print(f"    {first_line}")
    return 0


def pinned_cmd(full: bool) -> int:
    """Print Tier-1 pinned docs whole (or headers), with git SHA — no vector path."""
    from quant_research.context.pinned import get_pinned_context

    ctx = get_pinned_context()
    for doc in ctx.docs:
        dirty = " (dirty)" if doc.git_dirty else ""
        size = len(doc.text)
        print(f"===== {doc.file_path}  sha={doc.git_sha[:12]}{dirty}  {size} chars =====")
        if full:
            print(doc.text)
            print()
    for rel in ctx.missing:
        print(
            f"WARNING: pinned doc listed in spec 4.1 but not found in repo: {rel}",
            file=sys.stderr,
        )
    return 1 if ctx.missing else 0


def status_cmd() -> int:
    """Show the latest index run and working-tree staleness vs the index."""
    from quant_research.context.indexer import index_status

    try:
        st = index_status()
    except psycopg.OperationalError as exc:
        print(f"status unavailable - database: {str(exc).strip().splitlines()[0]}")
        return 1

    if st.latest_run is None:
        print("no index runs yet; run 'pcs reindex --all'")
        return 0
    run = st.latest_run
    dirty = " (dirty)" if run["git_dirty"] else ""
    print(
        f"latest run: {run['id']}  completed={run['completed_at']}  "
        f"sha={run['git_sha'][:12]}{dirty}"
    )
    print(f"  files_indexed={run['files_indexed']}  chunks_written={run['chunks_written']}")
    print(f"  chunk rows currently in index: {st.total_chunks}")

    if st.stale_files:
        print(f"  STALE ({len(st.stale_files)} file(s) changed since index; run 'pcs reindex'):")
        for rel in st.stale_files:
            print(f"    - {rel}")
    else:
        print("  index is up to date with the working tree")
    return 0


def hook_test_cmd() -> int:
    """Run the sessionStart hook the way Cursor would; show stdout/stderr/errors."""
    root = repo_root()
    hooks_path = root / ".cursor/hooks.json"
    hook_script = root / ".cursor/hooks/session_start.py"

    if not hooks_path.is_file():
        print(f"hook-test: missing {hooks_path}", file=sys.stderr)
        return 1
    if not hook_script.is_file():
        print(f"hook-test: missing {hook_script}", file=sys.stderr)
        return 1

    hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
    session_hooks = hooks.get("hooks", {}).get("sessionStart") or []
    if not session_hooks:
        print("hook-test: hooks.json has no sessionStart entries", file=sys.stderr)
        return 1

    command = session_hooks[0].get("command", "")
    print(f"hook command (from hooks.json): {command}")
    print(f"cwd: {root}")
    print(f"hook script: {hook_script}")
    print()

    env = os.environ.copy()
    env["PCS_HOOK_TEST"] = "1"
    env.pop("PCS_HOOK_REEXEC", None)
    stdin_payload = json.dumps(
        {
            "session_id": "pcs-hook-test",
            "hook_event_name": "sessionStart",
            "composer_mode": "agent",
            "is_background_agent": False,
        }
    )

    proc = subprocess.run(
        command,
        cwd=root,
        input=stdin_payload,
        capture_output=True,
        text=True,
        env=env,
        shell=True,
        check=False,
    )

    print(f"=== exit code: {proc.returncode} ===")
    print("=== stdout ===")
    print(proc.stdout.rstrip() if proc.stdout else "(empty)")
    print("=== stderr ===")
    print(proc.stderr.rstrip() if proc.stderr else "(empty)")
    print()

    if proc.returncode != 0:
        print("hook-test: FAIL — non-zero exit", file=sys.stderr)
        return proc.returncode

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        print(f"hook-test: FAIL — stdout is not valid JSON: {exc}", file=sys.stderr)
        return 1

    context = payload.get("additional_context", "")
    if not str(context).strip():
        print("hook-test: FAIL — additional_context missing or empty", file=sys.stderr)
        return 1

    print("=== additional_context (rendered) ===")
    print(context)
    print()
    if "docs/program-charter.md" not in context:
        print("hook-test: FAIL — charter doc missing from index", file=sys.stderr)
        return 1

    print("hook-test: PASS — compact pinned index emitted correctly")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argument parser."""
    parser = argparse.ArgumentParser(prog="pcs", description="Program Context System CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="report database health")

    sub.add_parser("manifest-check", help="validate the status manifest; list issues")
    p_scaffold = sub.add_parser(
        "manifest-scaffold", help="write a draft context-manifest.yml worklist"
    )
    p_scaffold.add_argument(
        "--force", action="store_true", help="overwrite an existing manifest"
    )

    p_reindex = sub.add_parser("reindex", help="(D4) walk, chunk, embed, upsert the corpus")
    p_reindex.add_argument("--all", action="store_true", help="full rebuild from repo")

    p_search = sub.add_parser("search", help="hybrid search over the corpus")
    p_search.add_argument("query", nargs="?", default="")
    p_search.add_argument("--top-k", type=int, default=8, help="number of results (default 8)")
    p_search.add_argument(
        "--include-superseded",
        action="store_true",
        help="also return superseded chunks (labeled [SUPERSEDED by ...]); "
        "historical/deprecated stay excluded",
    )

    p_pinned = sub.add_parser("pinned", help="print Tier-1 pinned context + git SHA")
    p_pinned.add_argument(
        "--full", action="store_true", help="dump full document text (default: headers only)"
    )

    sub.add_parser("status", help="show index runs and working-tree staleness")

    sub.add_parser(
        "hook-test",
        help="run sessionStart hook like Cursor; print stdout/stderr and payload",
    )
    return parser


def _force_utf8_output() -> None:
    """Make stdout/stderr UTF-8 so unicode (em-dashes, $ figures) prints on Windows."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    _force_utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        return doctor()
    if args.command == "manifest-check":
        return manifest_check()
    if args.command == "manifest-scaffold":
        return manifest_scaffold(force=args.force)
    if args.command == "reindex":
        return reindex(force=args.all)
    if args.command == "search":
        return search_cmd(args.query, top_k=args.top_k, include_superseded=args.include_superseded)
    if args.command == "pinned":
        return pinned_cmd(full=args.full)
    if args.command == "status":
        return status_cmd()
    if args.command == "hook-test":
        return hook_test_cmd()
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
