# P2-W2 forensic — verdict validity check

**Date:** 2026-06-08  
**git_sha:** `b833904965ee273e67933ee31e6209eaba0fd9fe`  
**Type:** Diagnosis only — no screen rerun, no OOS unseal, no strategy edits.

## Part A — Sign convention (reversion cluster)

### H-3 sample trades (IS)

#### Sample 1 — 2020-01-02 @ 2020-01-02T10:25:00-05:00

- Signal 5m OHLC: O=8808.00 H=8817.75 L=8803.25 C=8815.75
- OR: hi=8852.25 lo=8815.50 mid=8833.88
- False breakout: **below_or_low** extreme=8802.50
- Thesis says: 5m closed back inside OR after false breakdown below OR-low → LONG failure back toward OR mid.
- Actual: Entry LONG at 8815.75 after reclaim above OR-low 8815.50.
- Direction: **long** (thesis expects **long**) → **SIGN CORRECT**
- Entry/stop/target: 8815.75 / 8805.75 / 8833.88
- Exit: stop | net P&L: **$-22.48**

#### Sample 2 — 2020-05-25 @ 2020-05-25T11:00:00-04:00

- Signal 5m OHLC: O=9528.25 H=9528.75 L=9524.00 C=9525.25
- OR: hi=9528.00 lo=9513.50 mid=9520.75
- False breakout: **above_or_high** extreme=9532.00
- Thesis says: 5m closed back inside OR after false breakout above OR-high → SHORT failure back toward OR mid.
- Actual: Entry SHORT at 9525.25 after reclaim below OR-high 9528.00.
- Direction: **short** (thesis expects **short**) → **SIGN CORRECT**
- Entry/stop/target: 9525.25 / 9534.00 / 9520.75
- Exit: stop | net P&L: **$-19.98**

#### Sample 3 — 2020-10-02 @ 2020-10-02T10:35:00-04:00

- Signal 5m OHLC: O=11441.00 H=11461.00 L=11421.75 C=11422.75
- OR: hi=11429.50 lo=11300.75 mid=11365.12
- False breakout: **above_or_high** extreme=11468.75
- Thesis says: 5m closed back inside OR after false breakout above OR-high → SHORT failure back toward OR mid.
- Actual: Entry SHORT at 11422.75 after reclaim below OR-high 11429.50.
- Direction: **short** (thesis expects **short**) → **SIGN CORRECT**
- Entry/stop/target: 11422.75 / 11432.75 / 11365.12
- Exit: stop | net P&L: **$-22.48**

#### Sample 4 — 2021-02-26 @ 2021-02-26T10:40:00-05:00

- Signal 5m OHLC: O=12835.50 H=12912.75 L=12828.75 C=12896.75
- OR: hi=13031.75 lo=12859.25 mid=12945.50
- False breakout: **below_or_low** extreme=12751.50
- Thesis says: 5m closed back inside OR after false breakdown below OR-low → LONG failure back toward OR mid.
- Actual: Entry LONG at 12896.75 after reclaim above OR-low 12859.25.
- Direction: **long** (thesis expects **long**) → **SIGN CORRECT**
- Entry/stop/target: 12896.75 / 12886.75 / 12945.50
- Exit: stop | net P&L: **$-22.48**

#### Sample 5 — 2021-07-26 @ 2021-07-26T10:10:00-04:00

- Signal 5m OHLC: O=15111.00 H=15117.25 L=15091.00 C=15100.75
- OR: hi=15101.00 lo=15040.25 mid=15070.62
- False breakout: **above_or_high** extreme=15116.50
- Thesis says: 5m closed back inside OR after false breakout above OR-high → SHORT failure back toward OR mid.
- Actual: Entry SHORT at 15100.75 after reclaim below OR-high 15101.00.
- Direction: **short** (thesis expects **short**) → **SIGN CORRECT**
- Entry/stop/target: 15100.75 / 15110.75 / 15070.62
- Exit: stop | net P&L: **$-22.48**

#### Sample 6 — 2021-12-28 @ 2021-12-28T10:20:00-05:00

- Signal 5m OHLC: O=16508.25 H=16536.00 L=16491.25 C=16535.25
- OR: hi=16611.50 lo=16520.75 mid=16566.12
- False breakout: **below_or_low** extreme=16504.25
- Thesis says: 5m closed back inside OR after false breakdown below OR-low → LONG failure back toward OR mid.
- Actual: Entry LONG at 16535.25 after reclaim above OR-low 16520.75.
- Direction: **long** (thesis expects **long**) → **SIGN CORRECT**
- Entry/stop/target: 16535.25 / 16525.25 / 16566.12
- Exit: stop | net P&L: **$-22.48**

#### Sample 7 — 2022-05-27 @ 2022-05-27T10:05:00-04:00

- Signal 5m OHLC: O=12544.75 H=12547.00 L=12515.00 C=12532.25
- OR: hi=12532.25 lo=12401.50 mid=12466.88
- False breakout: **above_or_high** extreme=12546.00
- Thesis says: 5m closed back inside OR after false breakout above OR-high → SHORT failure back toward OR mid.
- Actual: Entry SHORT at 12532.25 after reclaim below OR-high 12532.25.
- Direction: **short** (thesis expects **short**) → **SIGN CORRECT**
- Entry/stop/target: 12532.25 / 12542.25 / 12466.88
- Exit: stop | net P&L: **$-22.48**

#### Sample 8 — 2022-10-19 @ 2022-10-19T10:50:00-04:00

- Signal 5m OHLC: O=11231.00 H=11231.00 L=11195.25 C=11207.75
- OR: hi=11213.25 lo=11110.25 mid=11161.75
- False breakout: **above_or_high** extreme=11284.50
- Thesis says: 5m closed back inside OR after false breakout above OR-high → SHORT failure back toward OR mid.
- Actual: Entry SHORT at 11207.75 after reclaim below OR-high 11213.25.
- Direction: **short** (thesis expects **short**) → **SIGN CORRECT**
- Entry/stop/target: 11207.75 / 11217.75 / 11161.75
- Exit: stop | net P&L: **$-22.48**

#### Sample 9 — 2023-03-17 @ 2023-03-17T10:10:00-04:00

- Signal 5m OHLC: O=12778.50 H=12781.25 L=12749.25 C=12758.00
- OR: hi=12763.75 lo=12691.00 mid=12727.38
- False breakout: **above_or_high** extreme=12810.00
- Thesis says: 5m closed back inside OR after false breakout above OR-high → SHORT failure back toward OR mid.
- Actual: Entry SHORT at 12758.00 after reclaim below OR-high 12763.75.
- Direction: **short** (thesis expects **short**) → **SIGN CORRECT**
- Entry/stop/target: 12758.00 / 12768.00 / 12727.38
- Exit: stop | net P&L: **$-22.48**

#### Sample 10 — 2023-08-17 @ 2023-08-17T10:20:00-04:00

- Signal 5m OHLC: O=14897.75 H=14913.75 L=14896.00 C=14910.25
- OR: hi=15008.00 lo=14907.50 mid=14957.75
- False breakout: **below_or_low** extreme=14888.25
- Thesis says: 5m closed back inside OR after false breakdown below OR-low → LONG failure back toward OR mid.
- Actual: Entry LONG at 14910.25 after reclaim above OR-low 14907.50.
- Direction: **long** (thesis expects **long**) → **SIGN CORRECT**
- Entry/stop/target: 14910.25 / 14900.25 / 14957.75
- Exit: stop | net P&L: **$-22.48**

**H-3 aggregate sign verdict:** SIGN CORRECT

### Cluster flip table (IS trades, arithmetic direction flip)

_Caveat: flipped P&L negates gross on the same entry/exit prices and keeps the same commission; it does **not** re-walk bars. Stops become targets and vice versa in reality, so any positive flipped expectancy is an **upper-biased** signal to fix-and-rerun, not a tradable edge._

| ID | IS n | As-is net $/tr | Flipped net $/tr |
|----|------|-----------------|------------------|
| H-2 | 726 | $-5.34 | $1.38 |
| H-3 | 738 | $-19.61 | $15.65 |
| H-4 | 46 | $-3.34 | $-0.62 |
| H-6 | 282 | $-12.79 | $8.83 |

## Part B — Frequency funnel

### H-1

- S1: session has >=40 RTH bars
- S2: 09:30–10:30 window has >=20 bars
- S3: trend day — >=12pt extension by 10:30, dominant side, no full retrace through open
- S4: 10:00–12:00 scan window >=5 bars
- S5: micro-pullback 25–60% of leg + resumption close (continuation entry)

| Stage | Passing | Pass vs prior |
|-------|---------|---------------|
| S1_min_session_bars_ge_40 | 1561 | 100.0% |
| S2_open_window_bars_ge_20 | 1561 | 100.0% |
| S3_trend_day_gate | 41 | 2.6% |
| S4_scan_window_ge_5_bars | 41 | 100.0% |
| S5_pullback_trigger_fired | 12 | 29.3% |

**Choke point:** S3_trend_day_gate — **too_strict_threshold**

S3 collapses ~87% of sessions: requires >=12pt one-sided move by 10:30 with no material cross-back through open — far stricter than 'trend micro-pullback' in pre-reg (~300–500/yr). S5 adds another ~30% drop. Choke is (a) too-strict threshold on trend-day definition, not a sign bug.

### H-4

- S1: session >=30 RTH bars
- S2: 09:30–09:45 opening window >=5 bars (evaluated every session)
- S3: >=09:45 bar exists for entry
- S4: |close_0944 - open_0930| >= 10pt
- S5: close within 2pt of window extreme (imbalance efficiency)
- S6: fade entry at first post-0945 close

| Stage | Passing | Pass vs prior |
|-------|---------|---------------|
| S1_min_session_bars_ge_30 | 1561 | 100.0% |
| S2_opening_5_15_bars_ge_5 | 1560 | 99.9% |
| S3_post_open_bar_exists | 1560 | 100.0% |
| S4_abs_move_ge_10pt | 1270 | 81.4% |
| S5_close_near_extreme_efficiency | 81 | 6.4% |
| S6_trade_fired | 81 | 100.0% |

**Choke point:** S5_close_near_extreme_efficiency — **too_strict_threshold**

Window is evaluated every session (S2 passes ~100% of viable sessions). S4 (10pt move) passes 81% of sessions; S5 (close within 2pt of extreme) collapses 1270→81 (6.4%) — primary choke. Combined ~5% session pass → ~77 trades/6yr vs ~250/yr projected. Choke is (a) tunable thresholds (especially S5 efficiency), not wrong session boundary.

Sessions with zero candidates: **1480** (move<10pt: 290, efficiency: 1189, thin: 1)

## Summary — verdict trustworthiness

- **H-1:** verdict **VOID** — needs fix+rerun (frequency choke: thesis never tested at projected rate; 12 fires vs ~1,800+ projected)
- **H-2:** verdict **TRUSTWORTHY (true negative)** — sign correct (fade VWAP excursion); 726 IS trades; flipped net $1.38/tr (weak / not sign-bug corroboration)
- **H-3:** verdict **TRUSTWORTHY (true negative)** — SIGN CORRECT on all 10 samples; low WR is failed fade mechanics (95% stop-out in samples), not sign inversion; flipped IS net $15.65/tr is arithmetic artifact (upper-biased; sign audit says CORRECT)
- **H-4:** verdict **VOID** — needs fix+rerun (frequency choke: 10pt+efficiency filters; 81 fires vs ~1,500 projected)
- **H-6:** verdict **TRUSTWORTHY (true negative)** — sign correct (short PDH rejection / long PDL rejection); flipped IS net $8.83/tr (upper-biased; rejection-fade loses with correct sign, not inversion)
