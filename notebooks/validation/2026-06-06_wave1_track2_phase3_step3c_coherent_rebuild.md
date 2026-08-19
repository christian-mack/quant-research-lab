# Wave 1 Track 2 — Phase 3 step 3c: Coherent entry rebuilds

**Date:** 2026-06-06  
**git_sha:** `0db224fc2bd1ef320064fb04c9a9a3d9d095e366`  
**Protocol:** 2020-01-01 → 2026-04-19  

## Deflation N (running configuration count)

- Step 3 incoherent logs: **5**
- Step 3b unique adds: **1**
- Step 3c coherent configs: **9**
- **Total standalone-OTE search N: 15**

## Cost model

Commission $1.98/RT. Slippage: $0.5 (1 tick) on stop/time exits; $0.25 (half-tick) on target. Limit entry: no entry slippage. Targets/stops always resolved from actual entry price.

## Executive verdict

**No configuration is cleared for step-4 screening.**

| Config | Net annual (comm+slip) | Net ticks/trade | DLL @ $30K/yr sizing |
|---|---:|---:|---|
| C1 OTE 70.5% full | **−$2,410** | −2.59 | No |
| C1 OTE 62% full | **+$5,099** | +5.71 | No (max session −$3,409) |
| C2 best window (W2 OTE 62%) | **+$4,355** | +7.09 | No |
| C3 FVG-only full | **+$26,185** | **+45.37** | Yes (qty 1.15) |

**C1 anchor note:** Step 3b reported −$1,186/yr by simulating OTE fills on **combined** scans (9,557 setups requiring FVG). True OTE-only scan yields **13,012** setups — additional marginal setups are net-negative, producing −$2,410/yr here.

**C3 FVG-only:** Correct target pairing barely changes economics vs step-3b mis-paired FVG-only ($26,185 vs $28,549; 45.4 vs 46.5 net ticks/trade). The step-3 **counterfactual** inflation was price-substitution on combined logs; dedicated FVG-only with coherent pairing still shows implausibly large edge. **30/30** top-trade bar audit passed, but magnitude remains suspect (median target distance 89 ticks; simulation may be optimistic). **Not authorized for step 4** without independent validation.

**OTE 62%** is the only OTE-band config with sustained positive net P&L, but fails Apex DLL at $30K/yr sizing and remains a separate definitional choice from FVG-only.

### C1_OTE705_full_RTH

- Trades: **13,012** (1859/yr)
- Net annual (comm only): **$-1,632/MNQ**
- Net annual (comm+slip): **$-2,410/MNQ**
- Net ticks/trade: **-2.59**
- WR: **46.6%** | R:R **1.05**

**Year-by-year net (comm+slip):**
- 2020: $-3,955 *(partial)*
- 2021: $-4,471
- 2022: $-322
- 2023: $-3,967
- 2024: $-1,619
- 2025: $-1,416
- 2026: $-1,117 *(partial)*
- DLL fit ($30K/yr sizing): qty=None, max session loss=$None, fits tier-1=False

### C1_OTE62_full_RTH

- Trades: **12,491** (1784/yr)
- Net annual (comm only): **$5,867/MNQ**
- Net annual (comm+slip): **$5,099/MNQ**
- Net ticks/trade: **5.71**
- WR: **49.9%** | R:R **1.22**

**Year-by-year net (comm+slip):**
- 2020: $2,796 *(partial)*
- 2021: $3,790
- 2022: $9,029
- 2023: $3,128
- 2024: $7,311
- 2025: $8,272
- 2026: $1,363 *(partial)*
- DLL fit ($30K/yr sizing): qty=5.88, max session loss=$-3408.73, fits tier-1=False

### C2_W1_0930_1100_OTE705

- Trades: **2,914** (416/yr)
- Net annual (comm only): **$-1,596/MNQ**
- Net annual (comm+slip): **$-1,776/MNQ**
- Net ticks/trade: **-8.53**
- WR: **40.4%** | R:R **1.21**

**Year-by-year net (comm+slip):**
- 2020: $-2,101 *(partial)*
- 2021: $-2,396
- 2022: $-1,723
- 2023: $-3,412
- 2024: $-644
- 2025: $-1,244
- 2026: $-915 *(partial)*
- DLL fit ($30K/yr sizing): qty=None, max session loss=$None, fits tier-1=False

### C2_W1_0930_1100_OTE62

- Trades: **2,776** (397/yr)
- Net annual (comm only): **$785/MNQ**
- Net annual (comm+slip): **$609/MNQ**
- Net ticks/trade: **3.07**
- WR: **46.2%** | R:R **1.25**

**Year-by-year net (comm+slip):**
- 2020: $-10 *(partial)*
- 2021: $368
- 2022: $-58
- 2023: $-590
- 2024: $2,881
- 2025: $1,947
- 2026: $-278 *(partial)*
- DLL fit ($30K/yr sizing): qty=49.28, max session loss=$-18069.44, fits tier-1=False

### C2_W2_1000_1500_OTE705

- Trades: **8,886** (1269/yr)
- Net annual (comm only): **$-802/MNQ**
- Net annual (comm+slip): **$-1,334/MNQ**
- Net ticks/trade: **-2.10**
- WR: **46.7%** | R:R **1.06**

**Year-by-year net (comm+slip):**
- 2020: $-2,673 *(partial)*
- 2021: $-3,361
- 2022: $252
- 2023: $-2,354
- 2024: $-1,974
- 2025: $757
- 2026: $12 *(partial)*
- DLL fit ($30K/yr sizing): qty=None, max session loss=$None, fits tier-1=False

### C2_W2_1000_1500_OTE62

- Trades: **8,601** (1229/yr)
- Net annual (comm only): **$4,886/MNQ**
- Net annual (comm+slip): **$4,355/MNQ**
- Net ticks/trade: **7.09**
- WR: **50.6%** | R:R **1.25**

**Year-by-year net (comm+slip):**
- 2020: $1,977 *(partial)*
- 2021: $3,103
- 2022: $7,530
- 2023: $2,429
- 2024: $5,432
- 2025: $8,335
- 2026: $1,681 *(partial)*
- DLL fit ($30K/yr sizing): qty=6.89, max session loss=$-2865.67, fits tier-1=False

### C2_W3_1300_1600_OTE705

- Trades: **6,756** (965/yr)
- Net annual (comm only): **$208/MNQ**
- Net annual (comm+slip): **$-189/MNQ**
- Net ticks/trade: **-0.39**
- WR: **48.9%** | R:R **1.03**

**Year-by-year net (comm+slip):**
- 2020: $-490 *(partial)*
- 2021: $-529
- 2022: $918
- 2023: $-658
- 2024: $-226
- 2025: $-943
- 2026: $607 *(partial)*
- DLL fit ($30K/yr sizing): qty=None, max session loss=$None, fits tier-1=False

### C2_W3_1300_1600_OTE62

- Trades: **6,503** (929/yr)
- Net annual (comm only): **$3,157/MNQ**
- Net annual (comm+slip): **$2,763/MNQ**
- Net ticks/trade: **5.95**
- WR: **50.9%** | R:R **1.23**

**Year-by-year net (comm+slip):**
- 2020: $1,737 *(partial)*
- 2021: $2,496
- 2022: $5,802
- 2023: $2,255
- 2024: $3,156
- 2025: $2,738
- 2026: $1,160 *(partial)*
- DLL fit ($30K/yr sizing): qty=10.86, max session loss=$-2759.34, fits tier-1=False

### C3_FVG_only_full_RTH

- Trades: **8,080** (1154/yr)
- Net annual (comm only): **$26,708/MNQ**
- Net annual (comm+slip): **$26,185/MNQ**
- Net ticks/trade: **45.37**
- WR: **63.1%** | R:R **2.03**

**Year-by-year net (comm+slip):**
- 2020: $22,551 *(partial)*
- 2021: $24,196
- 2022: $37,545
- 2023: $24,664
- 2024: $29,010
- 2025: $37,608
- 2026: $7,718 *(partial)*
- DLL fit ($30K/yr sizing): qty=1.15, max session loss=$-492.52, fits tier-1=True

## Config 3 FVG audit (>10 ticks/trade trigger)

- Audited: 30, reachable: 30/30
- Verdict: All top-30 bar-reachable; edge magnitude still requires scrutiny

## Stop conditions

- **fvg_gt_10_ticks_audit:** True
- **any_step4_candidate:** False
- **all_negative_or_marginal:** False