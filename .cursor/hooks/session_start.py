"""PCS sessionStart hook — inject the compact pinned index into a new IDE session.

Cursor runs this at the start of every composer conversation (project root cwd),
passing an event JSON on stdin. We ignore the input and emit
``{"additional_context": "<compact pinned index>"}`` — doc titles, one-line
purpose, and git SHA per Tier-1 doc (NOT the full text; the agent pulls whole
docs on demand via the PCS ``get_pinned_context`` tool).

``hooks.json`` invokes ``.venv/Scripts/python.exe`` directly (repo-root-relative,
Windows venv layout). Do not use bare ``python`` (stdout lost on Windows when
this script re-execs) or ``uv run`` (``uv`` is often absent from Cursor's hook
subprocess PATH). Revisit this command if the venv layout changes (fresh clone
on Linux, server deployment).

sessionStart is fire-and-forget and does not run in cloud agents, so this hook
**fails open** on stdout: on any error it emits no context rather than blocking
startup. Failures are still logged to stderr for the Hooks output channel.
Set ``PCS_HOOK_TEST=1`` (``pcs hook-test``) to bypass fail-open and surface errors.
The cloud fallback (agent calls ``get_pinned_context`` itself when it sees no
index) lives in the alwaysApply rule, not here.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import traceback
from pathlib import Path

_HOOK_PATH = Path(__file__).resolve()
_REPO_ROOT = _HOOK_PATH.parents[2]
_VENV_PYTHON_CANDIDATES = (
    _REPO_ROOT / ".venv" / "Scripts" / "python.exe",
    _REPO_ROOT / ".venv" / "bin" / "python",
)


def _ensure_project_python() -> None:
    """Re-exec with the project venv when the hook runner's Python lacks deps.

    Cursor's hook subprocess often has a minimal PATH (``uv`` may be missing).
    System ``python`` without the editable install then fail-opens with ``{}`` —
    silent and indistinguishable from a hook that never loaded.
    """
    if os.environ.get("PCS_HOOK_REEXEC") == "1":
        return
    try:
        import quant_research.context.pinned  # noqa: F401
    except ImportError:
        pass
    else:
        return

    for candidate in _VENV_PYTHON_CANDIDATES:
        if candidate.is_file():
            env = os.environ.copy()
            env["PCS_HOOK_REEXEC"] = "1"
            argv = [str(candidate), str(_HOOK_PATH), *sys.argv[1:]]
            os.execve(str(candidate), argv, env)

    if os.environ.get("PCS_HOOK_TEST") == "1":
        searched = ", ".join(str(p) for p in _VENV_PYTHON_CANDIDATES)
        raise RuntimeError(
            f"PCS sessionStart: quant_research not importable and no venv python found "
            f"(searched: {searched}). Run `uv sync` from the repo root."
        )


def _hook_test_mode() -> bool:
    return os.environ.get("PCS_HOOK_TEST") == "1"


def build_session_start_payload() -> dict[str, str]:
    """Build the sessionStart JSON payload Cursor reads from stdout."""
    from quant_research.context.pinned import get_pinned_index, render_pinned_index

    context = render_pinned_index(get_pinned_index(_REPO_ROOT))
    if not context.strip():
        raise RuntimeError("PCS sessionStart: pinned index rendered empty")
    return {"additional_context": context}


def main() -> int:
    _ensure_project_python()

    with contextlib.suppress(Exception):
        sys.stdin.read()  # consume and ignore the event payload
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8")
    with contextlib.suppress(Exception):
        sys.stderr.reconfigure(encoding="utf-8")

    fail_open = not _hook_test_mode()
    payload: dict[str, str] = {}

    try:
        payload = build_session_start_payload()
    except Exception as exc:
        detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        if fail_open:
            print(f"PCS sessionStart hook failed (fail-open): {detail}", file=sys.stderr)
            payload = {}
        else:
            print(f"PCS sessionStart hook FAILED: {detail}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            return 1

    print(json.dumps(payload))
    if _hook_test_mode():
        if not payload.get("additional_context", "").strip():
            print("PCS sessionStart: additional_context is empty", file=sys.stderr)
            return 1
        print("PCS sessionStart: OK — additional_context present", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
