"""Loader for vendor-exported futures contract files.

Reads NT8-style semicolon-delimited per-contract files (e.g. ``MNQ 03-26.Last.txt``)
into polars DataFrames in a canonical schema.

The source format is documented in ``docs/ai-project-instructions.md`` Section 7:
``YYYYMMDD HHMMSS;Open;High;Low;Close;Volume``, no header. Empirically the
timestamps are in **UTC** (despite earlier documentation that assumed CME
native time — see lessons-log 2026-04-26 entry on the UTC discovery for the
investigation that established this). The loader parses timestamps as naive,
labels them as UTC, then converts to ``America/Chicago`` so downstream code
can reason in CME-native wall-clock time without per-call tz conversion.

This module is the entry point for the M2 data pipeline. It deliberately does
not yet handle: session classification (M2 deliverable, builds on the
CT-converted timestamps from this module) or gap detection (M2 deliverable).
Continuous-contract construction is in :mod:`quant_research.data.continuous_contract`.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import polars as pl

SOURCE_TIMEZONE = "UTC"
"""Empirical timezone the NT8 export uses for its naive wall-clock numbers.

Established by inspection (see lessons-log 2026-04-26 UTC discovery entry):
the export's friday-close hour shifts between 21:00 (CDT) and 22:00 (CST) in
labeled-CT view, and the daily maintenance gap shifts in lockstep — both
patterns require the underlying values to be UTC, not CT.
"""

CME_TIMEZONE = "America/Chicago"
"""Canonical user-facing timezone for loaded data.

Loaded timestamps are converted from :data:`SOURCE_TIMEZONE` to this
timezone so downstream code reasons in CME native wall-clock (RTH 08:30-15:00
CT, daily maintenance break 16:00-17:00 CT, weekly close Friday 16:00 CT).
DST is handled by polars' ``convert_time_zone``.
"""

DEFAULT_CONTRACT_GLOB = "MNQ *.Last.txt"
"""Default glob pattern matching the NT8-exported MNQ contract files.

Spaces and the literal ``.Last.txt`` suffix are intentional and match the
NT8 default export naming. Other futures symbols (MES, NQ, ES) follow the
same shape; pass an alternate pattern to :func:`discover_contract_files` to
load them.
"""

CANONICAL_COLUMNS = (
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "contract_symbol",
)
"""Column order returned by :func:`load_contract_file`.

Downstream code (continuous-contract builder, indicators, backtest engine)
should rely on this column set being present and in this order.
"""


def default_data_root() -> Path:
    """Return the repo-relative ``data/raw/`` directory.

    Resolved by walking up from this module's location:
    ``src/quant_research/data/data_loader.py`` -> ``<repo_root>/data/raw/``.

    This default is convenient for development checkouts. For installed-package
    or deployed use, callers should pass an explicit ``data_root`` argument
    instead of relying on this resolution, since the on-disk layout will not
    match the source tree.

    Returns:
        Absolute path to ``<repo_root>/data/raw/``.
    """
    return Path(__file__).resolve().parents[3] / "data" / "raw"


def discover_contract_files(
    data_root: str | Path | None = None,
    *,
    pattern: str = DEFAULT_CONTRACT_GLOB,
) -> list[Path]:
    """List contract files under ``data_root`` matching ``pattern``.

    Args:
        data_root: Directory to search. If ``None``, uses
            :func:`default_data_root`.
        pattern: Glob pattern, relative to ``data_root``. Defaults to the
            NT8 MNQ export naming convention.

    Returns:
        Lexicographically sorted list of matching file paths. Empty list if
        no files match. Order is not guaranteed to be chronological — callers
        that need chronological order should parse the contract code from
        each filename and sort accordingly.
    """
    root = Path(data_root) if data_root is not None else default_data_root()
    return sorted(root.glob(pattern))


def _contract_symbol_from_filename(path: Path) -> str:
    """Extract the contract symbol from a vendor export filename.

    Example: ``MNQ 03-26.Last.txt`` -> ``"MNQ 03-26"``.
    """
    return path.name.removesuffix(".Last.txt")


def load_contract_file(
    path: str | Path,
    *,
    timezone: str = CME_TIMEZONE,
) -> pl.DataFrame:
    """Load a single vendor-exported contract file into a polars DataFrame.

    The source format is NT8 default: semicolon-delimited
    ``YYYYMMDD HHMMSS;Open;High;Low;Close;Volume`` with no header row.
    Timestamps in the source file are **UTC** (see lessons-log 2026-04-26
    UTC discovery entry). The loader parses them naive, labels as UTC,
    then converts to ``timezone`` (defaulting to :data:`CME_TIMEZONE`),
    so rows in the returned DataFrame have CME-native wall-clock by
    default. DST is handled by polars' ``convert_time_zone`` —
    transitions are unambiguous since the source is UTC.

    Args:
        path: Path to the contract ``.txt`` file.
        timezone: Target IANA timezone name. The conversion source is
            always :data:`SOURCE_TIMEZONE` (UTC); this parameter chooses
            the wall-clock the caller wants to see. Defaults to
            :data:`CME_TIMEZONE` for the standard CME-aligned analysis flow.

    Returns:
        DataFrame with the columns listed in :data:`CANONICAL_COLUMNS`,
        in that order. ``timestamp`` is a tz-aware ``Datetime("us", tz)``
        in the requested ``timezone``. Numeric columns are ``Float64``
        for prices and ``Int64`` for volume. No rows are dropped by the
        loader — out-of-trading-hours filtering, if needed, is the
        responsibility of session-classification code downstream.

    Raises:
        FileNotFoundError: If ``path`` does not point to an existing file.
        polars.exceptions.ComputeError: If the file cannot be parsed in the
            expected format.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Contract file not found: {p}")

    raw = pl.read_csv(
        p,
        separator=";",
        has_header=False,
        new_columns=["raw_timestamp", "open", "high", "low", "close", "volume"],
        schema_overrides={
            "raw_timestamp": pl.String,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Int64,
        },
    )

    return raw.with_columns(
        pl.col("raw_timestamp")
        .str.strptime(pl.Datetime, "%Y%m%d %H%M%S")
        .dt.replace_time_zone(SOURCE_TIMEZONE)
        .dt.convert_time_zone(timezone)
        .alias("timestamp"),
        pl.lit(_contract_symbol_from_filename(p)).alias("contract_symbol"),
    ).select(*CANONICAL_COLUMNS)


def _empty_canonical_dataframe(timezone: str) -> pl.DataFrame:
    """Return a zero-row DataFrame with the canonical schema."""
    return pl.DataFrame(
        schema={
            "timestamp": pl.Datetime("us", timezone),
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Int64,
            "contract_symbol": pl.String,
        }
    )


def load_contracts(
    paths: Iterable[str | Path],
    *,
    timezone: str = CME_TIMEZONE,
) -> pl.DataFrame:
    """Load multiple contract files and concatenate into one canonical DataFrame.

    Each path is handed to :func:`load_contract_file` individually; the per-file
    DataFrames are then stacked vertically. Rows from the first path appear
    first; within each path the original file order is preserved. The result
    is **not** chronologically sorted across files — adjacent quarterly
    contracts overlap in time during the roll window. Callers that need
    chronological order should ``sort("timestamp")`` after loading, or
    delegate to a continuous-contract builder (forthcoming in M2).

    Args:
        paths: Iterable of paths to contract ``.txt`` files. Order matters:
            output row order follows input path order.
        timezone: IANA timezone name; propagated to every per-file call.

    Returns:
        DataFrame with the :data:`CANONICAL_COLUMNS` schema. Distinct
        contracts are distinguishable via ``contract_symbol``. Empty input
        returns a zero-row DataFrame with the same schema rather than
        raising.
    """
    paths_list = list(paths)
    if not paths_list:
        return _empty_canonical_dataframe(timezone)
    return pl.concat(
        [load_contract_file(p, timezone=timezone) for p in paths_list],
        how="vertical",
    )


def load_all_contracts(
    data_root: str | Path | None = None,
    *,
    pattern: str = DEFAULT_CONTRACT_GLOB,
    timezone: str = CME_TIMEZONE,
) -> pl.DataFrame:
    """Discover and load every matching contract file under ``data_root``.

    Convenience wrapper composing :func:`discover_contract_files` with
    :func:`load_contracts`. Equivalent to::

        load_contracts(discover_contract_files(data_root, pattern=pattern),
                       timezone=timezone)

    Args:
        data_root: Directory to search. ``None`` uses :func:`default_data_root`.
        pattern: Glob pattern, relative to ``data_root``. Defaults to
            :data:`DEFAULT_CONTRACT_GLOB`.
        timezone: IANA timezone name.

    Returns:
        DataFrame with the :data:`CANONICAL_COLUMNS` schema. Empty if no
        files match.
    """
    paths = discover_contract_files(data_root, pattern=pattern)
    return load_contracts(paths, timezone=timezone)
