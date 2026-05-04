# M5 ORB+Opt3 — MNQ month smoke (not M6 parity)

**Purpose:** Record a **representative** Python backtest run: ``BacktestEngine`` + ``OrbStrategy`` (production ORB+Opt3 parameters) on **RTH-only** continuous MNQ, without comparing to NT8.

**Git:** Commit **2026-05-04** — reproducible via ``tests/backtest/test_orb_mnq_month_smoke.py::test_orb_march_2024_mnq_smoke``.

## Window

| Field | Value |
|-------|--------|
| Calendar month | **March 2024** (America/Chicago session dates; RTH bars only) |
| Rationale | Single month with routine trend/chop variety; no NT8 alignment attempted. |

## Environment (authoritative when re-run)

- Research repo continuous MNQ from NT8 ``MNQ MM-YY.Last.txt`` under ``data/raw/`` (gitignored).
- ``commission`` default **$0**; ``OrbStrategy`` funded row **3** contracts.

## Observed run (developer workstation, 2026-05-04)

Values are **illustrative** — re-running on a different slice or data export may differ.

| Metric | Value |
|--------|--------|
| RTH bars in window | 7,800 |
| Closed trades | 17 |
| Sum ``net_pnl`` | **−1,102.50** USD |
| Sum ``gross_pnl`` | −1,102.50 (same; $0 commission) |
| Exit reasons | ``orb_exit_target``: 10; ``orb_exit_stop``: 7 |
| Directions | long: 8; short: 9 |
| ``flatten`` exits | 0 (no end-of-series flatten in this window) |

## Structural sanity (automated asserts)

- Every row: ``module_id == "orb"``, ``quantity == 3``, ``entry_time <= exit_time``.
- ``exit_reason`` in ``{orb_exit_target, orb_exit_stop, flatten}``.
- ``|gross_pnl|`` per row **> 0** and **< 60,000** USD (sanity band for MNQ × 3 contracts).
- Fill count **≥** 2 × trade count (round-trips).

## NT8 artifact path (**resolved**)

Commit **d2259f5** added ``docs/nt8-backtest-methodology.md`` only. The **Flux C# tree and CSV exports** referenced throughout PT3 live under ``docs/nt8-artifacts/`` and were **committed to git** in **2026-05-04** so M6 can cite a stable on-disk path (no longer “methodology-only” without sources).
