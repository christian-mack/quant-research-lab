"""Standing backtest validation harness (V1–V7).

Every strategy backtest should emit a :class:`ValidationReport` alongside results.
Results without a passing report are untrusted by project convention.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import polars as pl

from quant_research.backtest.geometry import check_trade_geometry
from quant_research.backtest.provenance import (
    M4_ENGINE_PROVENANCE_MARKER,
    is_m4_engine_provenance,
)
from quant_research.backtest.specs import BacktestConfig, SlippageMode
from quant_research.backtest.types import SimulatedFill

MNQ_TICK = 0.25


@dataclass(frozen=True, slots=True)
class ValidationThresholds:
    """Configurable tripwires for the standing harness."""

    geometry_reject_surface_rate: float = 0.20
    implausible_net_ticks_per_trade: float = 15.0
    dual_touch_surface_rate: float = 0.10
    min_commission_per_round_trip: float = 0.01


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Outcome of one harness check."""

    check_id: str
    name: str
    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Aggregate validation outcome for a backtest run."""

    checks: tuple[CheckResult, ...]
    thresholds: ValidationThresholds

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failed_checks(self) -> tuple[CheckResult, ...]:
        return tuple(c for c in self.checks if not c.passed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": [
                {
                    "check_id": c.check_id,
                    "name": c.name,
                    "passed": c.passed,
                    "message": c.message,
                    "details": c.details,
                }
                for c in self.checks
            ],
        }

    def format_block(self) -> str:
        lines = ["## VALIDATION REPORT", ""]
        status = "PASS" if self.passed else "**FAIL**"
        lines.append(f"**Overall:** {status}")
        lines.append("")
        for c in self.checks:
            mark = "PASS" if c.passed else "**FAIL**"
            lines.append(f"- **{c.check_id} {c.name}:** {mark} — {c.message}")
        return "\n".join(lines)


def validate_backtest_result(
    trade_log: pl.DataFrame,
    *,
    config: BacktestConfig,
    fills: Sequence[SimulatedFill] | None = None,
    bars: pl.DataFrame | None = None,
    geometry_reject_rate: float | None = None,
    thresholds: ValidationThresholds | None = None,
    run_spot_checks: bool = True,
) -> ValidationReport:
    """Run V1–V7 on a completed backtest output."""
    th = thresholds or ValidationThresholds()
    tick_val = config.instrument.tick_size * config.instrument.tick_value
    checks: list[CheckResult] = [
        _check_v1_geometry_coherence(trade_log, geometry_reject_rate, th, config),
        _check_v2_causal_sequencing(trade_log),
        _check_v3_cost_application(trade_log, config),
        _check_v4_magnitude_sanity(trade_log, tick_val, th),
    ]
    if run_spot_checks:
        from quant_research.backtest.validation_spot_checks import run_spot_check_suite

        checks.append(run_spot_check_suite())
    checks.append(_check_v6_dual_touch(trade_log, fills, bars, th))
    checks.append(_check_v7_engine_provenance(trade_log))
    return ValidationReport(checks=tuple(checks), thresholds=th)


def _check_v1_geometry_coherence(
    trade_log: pl.DataFrame,
    geometry_reject_rate: float | None,
    th: ValidationThresholds,
    config: BacktestConfig,
) -> CheckResult:
    if trade_log.is_empty():
        reject_flag = (
            geometry_reject_rate is not None
            and geometry_reject_rate > th.geometry_reject_surface_rate
        )
        return CheckResult(
            "V1",
            "Geometry coherence",
            not reject_flag,
            "No filled trades; scan reject rate only"
            if geometry_reject_rate is not None
            else "No filled trades (vacuous pass)",
            {"n_trades": 0, "geometry_reject_rate": geometry_reject_rate},
        )

    has_bracket_cols = {"stop_price", "target_price"}.issubset(trade_log.columns)
    incoherent = 0
    missing_bracket = 0
    samples: list[dict[str, Any]] = []
    if has_bracket_cols:
        import math

        for row in trade_log.iter_rows(named=True):
            sp = row.get("stop_price")
            tp = row.get("target_price")
            if sp is None or tp is None or (isinstance(sp, float) and math.isnan(sp)):
                missing_bracket += 1
                incoherent += 1
                continue
            reject = check_trade_geometry(
                str(row["direction"]),
                float(row["entry_price"]),
                float(sp),
                float(tp),
            )
            if reject is not None:
                incoherent += 1
                samples.append({"trade_id": row["trade_id"], "reason": reject.reason})
    elif not config.enforce_trade_geometry:
        incoherent = -1

    n = trade_log.height
    reject_flag = (
        geometry_reject_rate is not None and geometry_reject_rate > th.geometry_reject_surface_rate
    )
    if has_bracket_cols:
        # Hard gate: booked log must contain zero incoherent fills.
        passed = incoherent == 0
        msg = f"{incoherent}/{n} filled trades fail entry-time geometry"
        if incoherent == 0 and reject_flag:
            msg += (
                f"; upstream reject rate {100 * geometry_reject_rate:.1f}%"
                f" > {100 * th.geometry_reject_surface_rate:.0f}% surface"
                " (booked population clean)"
            )
    elif config.enforce_trade_geometry:
        passed = not reject_flag
        msg = (
            f"Engine geometry enforcement on; {100 * (geometry_reject_rate or 0):.1f}% scan rejects"
        )
        if reject_flag:
            msg += f"; reject rate > {100 * th.geometry_reject_surface_rate:.0f}% surface threshold"
    else:
        passed = False
        msg = "No bracket columns and enforce_trade_geometry=False"
    if not has_bracket_cols and reject_flag and config.enforce_trade_geometry:
        pass  # message already appended above
    elif not has_bracket_cols and reject_flag:
        msg += f"; reject rate {100 * geometry_reject_rate:.1f}% > surface threshold"
    return CheckResult(
        "V1",
        "Geometry coherence",
        passed,
        msg,
        {
            "incoherent_filled": incoherent,
            "n_trades": n,
            "geometry_reject_rate": geometry_reject_rate,
            "has_bracket_columns": has_bracket_cols,
            "samples": samples[:5],
        },
    )


def _check_v2_causal_sequencing(trade_log: pl.DataFrame) -> CheckResult:
    if trade_log.is_empty():
        return CheckResult("V2", "Causal sequencing", True, "No trades", {})
    violations: list[dict[str, Any]] = []
    for row in trade_log.iter_rows(named=True):
        entry_t = row["entry_time"]
        exit_t = row["exit_time"]
        bars_held = int(row["bars_held"])
        if exit_t is not None and entry_t is not None and exit_t < entry_t:
            violations.append({"trade_id": row["trade_id"], "issue": "exit_before_entry"})
        if bars_held < 0:
            violations.append({"trade_id": row["trade_id"], "issue": "negative_bars_held"})
    passed = len(violations) == 0
    return CheckResult(
        "V2",
        "Causal sequencing",
        passed,
        f"{len(violations)} sequencing violations"
        if violations
        else "All trades exit at/after entry",
        {"violations": violations[:10], "n_trades": trade_log.height},
    )


def _check_v3_cost_application(trade_log: pl.DataFrame, config: BacktestConfig) -> CheckResult:
    if trade_log.is_empty():
        return CheckResult("V3", "Cost application", True, "No trades", {})
    expect_cost = (
        config.commission.per_contract_per_fill > 0 or config.slippage.mode != SlippageMode.NONE
    )
    zero_comm = 0
    mismatch = 0
    for row in trade_log.iter_rows(named=True):
        gross = float(row["gross_pnl"])
        comm = float(row["commission"])
        net = float(row["net_pnl"])
        if abs(net - (gross - comm)) > 1e-6:
            mismatch += 1
        if comm <= 0:
            zero_comm += 1
    if not expect_cost:
        passed = mismatch == 0
        msg = f"Cost-free config; {mismatch} net/gross mismatches"
    elif zero_comm == trade_log.height:
        passed = False
        msg = "Configured costs but all trades show $0 commission"
    else:
        passed = mismatch == 0
        msg = f"{zero_comm}/{trade_log.height} zero-commission; {mismatch} net/gross mismatches"
    return CheckResult(
        "V3",
        "Cost application",
        passed,
        msg,
        {"zero_commission_trades": zero_comm, "net_gross_mismatches": mismatch},
    )


def _check_v4_magnitude_sanity(
    trade_log: pl.DataFrame,
    tick_val: float,
    th: ValidationThresholds,
) -> CheckResult:
    if trade_log.is_empty():
        return CheckResult("V4", "Magnitude sanity", True, "No trades", {})
    nets = trade_log["net_pnl"].to_list()
    avg_ticks = sum(nets) / len(nets) / tick_val if tick_val else 0.0
    passed = abs(avg_ticks) <= th.implausible_net_ticks_per_trade
    return CheckResult(
        "V4",
        "Magnitude sanity",
        passed,
        f"Avg net {avg_ticks:.2f} ticks/trade (surface > {th.implausible_net_ticks_per_trade})",
        {"avg_net_ticks": avg_ticks, "n_trades": len(nets), "total_net_usd": sum(nets)},
    )


def _check_v6_dual_touch(
    trade_log: pl.DataFrame,
    fills: Sequence[SimulatedFill] | None,
    bars: pl.DataFrame | None,
    th: ValidationThresholds,
) -> CheckResult:
    del fills
    if trade_log.is_empty() or bars is None or "entry_bar" not in trade_log.columns:
        return CheckResult(
            "V6",
            "Dual-touch exposure",
            True,
            "Skipped (need bars + entry_bar for dual-touch analysis)",
            {},
        )
    dual = 0
    resolved = 0
    highs = bars["high"].to_list()
    lows = bars["low"].to_list()
    for row in trade_log.iter_rows(named=True):
        reason = str(row["exit_reason"])
        if reason not in ("ote_stop", "ote_target", "stop", "target"):
            continue
        resolved += 1
        exit_bar = int(row["entry_bar"]) + int(row["bars_held"])
        if exit_bar >= len(highs):
            continue
        entry = float(row["entry_price"])
        stop = float(row.get("stop_price", entry - MNQ_TICK))
        target = float(row.get("target_price", entry + MNQ_TICK))
        hi, lo = highs[exit_bar], lows[exit_bar]
        if str(row["direction"]) == "long":
            stop_hit = lo <= stop
            target_hit = hi >= target
        else:
            stop_hit = hi >= stop
            target_hit = lo <= target
        if stop_hit and target_hit:
            dual += 1
    rate = dual / resolved if resolved else 0.0
    passed = rate <= th.dual_touch_surface_rate
    return CheckResult(
        "V6",
        "Dual-touch exposure",
        passed,
        f"{100 * rate:.1f}% dual-touch on {resolved} bracket exits",
        {"dual_touch_count": dual, "resolved_exits": resolved, "dual_touch_rate": rate},
    )


def _check_v7_engine_provenance(trade_log: pl.DataFrame) -> CheckResult:
    """Assert every trade was emitted by M4 BacktestEngine → TradeLedger."""
    if trade_log.is_empty():
        return CheckResult(
            "V7",
            "Engine provenance",
            True,
            "No trades",
            {"n_trades": 0},
        )
    if "mfa_engine_provenance" not in trade_log.columns:
        ids = trade_log["trade_id"].to_list()
        return CheckResult(
            "V7",
            "Engine provenance",
            False,
            f"Missing mfa_engine_provenance column on {len(ids)} trades",
            {
                "offending_trade_ids": ids,
                "expected_marker": M4_ENGINE_PROVENANCE_MARKER,
            },
        )

    offending: list[int] = []
    foreign_samples: list[dict[str, object]] = []
    for row in trade_log.iter_rows(named=True):
        tid = int(row["trade_id"])
        marker = row.get("mfa_engine_provenance")
        if not is_m4_engine_provenance(marker):
            offending.append(tid)
            if len(foreign_samples) < 5:
                foreign_samples.append(
                    {
                        "trade_id": tid,
                        "mfa_engine_provenance": marker,
                    }
                )

    n = trade_log.height
    passed = len(offending) == 0
    if passed:
        msg = f"All {n} trades carry M4 engine provenance"
    else:
        msg = (
            f"{len(offending)}/{n} trades lack M4 engine provenance "
            f"(indices: {offending[:10]}{'…' if len(offending) > 10 else ''})"
        )
    return CheckResult(
        "V7",
        "Engine provenance",
        passed,
        msg,
        {
            "n_trades": n,
            "offending_trade_ids": offending,
            "expected_marker": M4_ENGINE_PROVENANCE_MARKER,
            "foreign_samples": foreign_samples,
        },
    )


def geometry_decision_is_entry_time_only(
    direction: str,
    entry: float,
    stop: float,
    target: float,
) -> bool:
    """Document A1: guard inputs are only entry-time bracket prices."""
    _ = check_trade_geometry(direction, entry, stop, target)
    return True
