#region Using declarations
using System;
using System.Collections.Generic;
#endregion

namespace NinjaTrader.NinjaScript.Strategies.Flux.Core
{
    /// <summary>
    /// Log level enumeration.
    /// </summary>
    public enum LogLevel
    {
        Error = 0,
        Warn = 1,
        Info = 2,
        Debug = 3,
        Trace = 4
    }

    /// <summary>
    /// Volatility gating mode.
    /// </summary>
    public enum VolGateMode
    {
        ATR,
        RangeWidth,
        MAEProxy
    }

    /// <summary>
    /// Volatility classification result.
    /// </summary>
    public enum VolatilityRegime
    {
        Low,
        Mid,
        High
    }

    /// <summary>
    /// Immutable configuration for Flux v1.
    /// Loaded during OnStateChange(State.DataLoaded) and never mutated at runtime.
    /// </summary>
    public class Config
    {
        #region Logging Configuration

        /// <summary>
        /// Master switch for all log emission.
        /// </summary>
        public bool EnableLogging { get; private set; }

        /// <summary>
        /// Verbosity level for logging.
        /// </summary>
        public LogLevel LogLevel { get; private set; }

        /// <summary>
        /// Enable low-overhead telemetry counters even when logs are off.
        /// </summary>
        public bool EnableTelemetryCounters { get; private set; }

        /// <summary>
        /// Enable file-based audit logging for parity analysis.
        /// When enabled, mirrors all [FLUX][...] logs to a file.
        /// </summary>
        public bool EnableFileAuditLogging { get; private set; }

        #endregion

        #region Session Configuration

        /// <summary>
        /// Session timezone (e.g., America/Chicago).
        /// </summary>
        public string SessionTimeZone { get; private set; }

        /// <summary>
        /// Allow trading during RTH only (true) or include ETH (false).
        /// </summary>
        public bool RTHOnly { get; private set; }

        #endregion

        #region Risk Limits (Prop-Firm Safe)

        /// <summary>
        /// Maximum daily loss in currency before lockout.
        /// </summary>
        public double MaxDailyLossCurrency { get; private set; }

        /// <summary>
        /// Maximum trailing drawdown in currency before lockout.
        /// </summary>
        public double MaxTrailingDrawdownCurrency { get; private set; }

        /// <summary>
        /// System-level cap on trades per day.
        /// </summary>
        public int MaxTradesPerDay { get; private set; }

        #endregion

        #region Position Rules

        /// <summary>
        /// Only one position at a time (v1 default: true).
        /// </summary>
        public bool OnePositionAtATime { get; private set; }

        /// <summary>
        /// Only one module active at a time (v1 default: true).
        /// </summary>
        public bool OneModuleAtATime { get; private set; }

        #endregion

        #region Volatility Gating

        /// <summary>
        /// Enable volatility-based gating.
        /// </summary>
        public bool EnableVolatilityGate { get; private set; }

        /// <summary>
        /// Mode for volatility classification.
        /// </summary>
        public VolGateMode VolGateMode { get; private set; }

        /// <summary>
        /// ATR lookback period for volatility calculations.
        /// </summary>
        public int ATRPeriod { get; private set; }

        /// <summary>
        /// Lookback bars for volatility baseline.
        /// </summary>
        public int VolLookbackBars { get; private set; }

        /// <summary>
        /// High volatility percentile threshold (e.g., 0.7 = top 30%).
        /// </summary>
        public double VolHighPercentile { get; private set; }

        /// <summary>
        /// Low volatility percentile threshold (e.g., 0.3 = bottom 30%).
        /// </summary>
        public double VolLowPercentile { get; private set; }

        #endregion

        #region Module Configuration

        /// <summary>
        /// Enable Range module.
        /// </summary>
        public bool EnableRangeModule { get; private set; }

        /// <summary>
        /// Enable Momentum module (future).
        /// </summary>
        public bool EnableMomentumModule { get; private set; }

        /// <summary>
        /// Module priority order (first = highest priority).
        /// </summary>
        public IReadOnlyList<string> ModulePriorities { get; private set; }

        /// <summary>
        /// Position size (number of contracts) for Momentum module.
        /// Default: 1. Range: 1-10.
        /// </summary>
        public int MomentumQuantity { get; private set; }

        /// <summary>
        /// Position size (number of contracts) for ORB module.
        /// Default: 1. Range: 1-10.
        /// </summary>
        public int ORBQuantity { get; private set; }

        /// <summary>
        /// Position size (number of contracts) for Range module.
        /// Default: 1. Range: 1-10.
        /// </summary>
        public int RangeQuantity { get; private set; }

        /// <summary>
        /// Cooldown bars after trade close before module can trade again.
        /// </summary>
        public int ModuleCooldownBars { get; private set; }

        #endregion

        #region Execution Defaults

        /// <summary>
        /// Fixed position size (e.g., 1 micro).
        /// </summary>
        public int DefaultQuantity { get; private set; }

        /// <summary>
        /// Minimum stop distance in ticks.
        /// </summary>
        public int MinStopTicks { get; private set; }

        /// <summary>
        /// Maximum stop distance in ticks.
        /// </summary>
        public int MaxStopTicks { get; private set; }

        /// <summary>
        /// Minimum target distance in ticks.
        /// </summary>
        public int MinTargetTicks { get; private set; }

        #endregion

        #region Range Module Specific (for signal extraction)

        /// <summary>
        /// Compression lookback for Range regime.
        /// </summary>
        public int RangeCompressionLookback { get; private set; }

        /// <summary>
        /// Compression percentile threshold.
        /// </summary>
        public double RangeCompressionPercentile { get; private set; }

        /// <summary>
        /// Range lookback bars.
        /// </summary>
        public int RangeLookback { get; private set; }

        /// <summary>
        /// Stop distance multiplier (range size).
        /// </summary>
        public double RangeStopMultiplier { get; private set; }

        /// <summary>
        /// Target distance multiplier (range size).
        /// </summary>
        public double RangeTargetMultiplier { get; private set; }

        /// <summary>
        /// Trailing activation threshold in R-multiples.
        /// </summary>
        public double RangeTrailingActivation { get; private set; }

        /// <summary>
        /// Trailing distance in R-multiples.
        /// </summary>
        public double RangeTrailingDistance { get; private set; }

        /// <summary>
        /// PHASE 16: Enable ratcheting trail multiplier for Range trades.
        /// When disabled, uses flat RangeTrailingDistance. When enabled, trail tightens in phases.
        /// </summary>
        public bool RangeTrailRatchetEnabled { get; private set; }

        /// <summary>
        /// PHASE 16: Trail multiplier for Phase 1 (0 to Threshold1R profit). Default: 0.45R.
        /// </summary>
        public double RangeTrailMultiplierInitial { get; private set; }

        /// <summary>
        /// PHASE 16: Trail multiplier for Phase 2 (Threshold1R to Threshold2R profit). Default: 0.35R.
        /// </summary>
        public double RangeTrailMultiplierMid { get; private set; }

        /// <summary>
        /// PHASE 16: Trail multiplier for Phase 3 (above Threshold2R profit). Default: 0.25R.
        /// </summary>
        public double RangeTrailMultiplierTight { get; private set; }

        /// <summary>
        /// PHASE 16: Profit/R threshold to enter Phase 2 trailing. Default: 1.0.
        /// </summary>
        public double RangeTrailRatchetThreshold1R { get; private set; }

        /// <summary>
        /// PHASE 16: Profit/R threshold to enter Phase 3 trailing. Default: 2.0.
        /// </summary>
        public double RangeTrailRatchetThreshold2R { get; private set; }

        /// <summary>
        /// PHASE 13.1: Comma-separated hours (CT, 24h) to block Range entries.
        /// 7AM CT: -$205, 30% WR | 20PM CT: -$160, 40% WR | 22PM CT: -$164, 42% WR
        /// Default: "7,20,22"
        /// </summary>
        public string RangeBlockedHoursCT { get; private set; }

        /// <summary>
        /// Parsed set of blocked hours for Range module (CT).
        /// </summary>
        public System.Collections.Generic.HashSet<int> RangeBlockedHoursSet { get; private set; }

        #endregion

        #region Momentum Module Configuration (Phase 12.10)

        /// <summary>
        /// PHASE 12.10: Parity mode flag.
        /// When true, Momentum module uses EXACT standalone semantics:
        /// - Level-based entry (not cross-based)
        /// - Price-space stop/target (no tick quantization or clamps)
        /// - Fixed stop distance (not ATR-based)
        /// - Auto break-even at 1.5R
        /// Default: true (parity mode enabled)
        /// </summary>
        public bool MomentumParityMode { get; private set; }

        /// <summary>
        /// Enable VWAP filtering for Momentum module.
        /// Default: false (disabled to match standalone behavior).
        /// </summary>
        public bool MomentumEnableVWAPFilter { get; private set; }

        /// <summary>
        /// PHASE 12.10: VWAP deviation in PRICE UNITS (not ATR multiples).
        /// Matches standalone VWAPDeviation parameter.
        /// Only used when MomentumEnableVWAPFilter is true.
        /// </summary>
        public double MomentumVWAPDeviation { get; private set; }

        /// <summary>
        /// PHASE 12.10: Fixed stop distance in POINTS (not ATR-based).
        /// Matches standalone TrailingDistance = 80 parameter.
        /// Only used when MomentumParityMode is true.
        /// Default: 80.0 points
        /// </summary>
        public double MomentumFixedStopDistance { get; private set; }

        /// <summary>
        /// PHASE 12.10: Enable auto break-even for Momentum trades.
        /// Matches standalone EnableAutoBE = true parameter.
        /// Default: true (to match standalone)
        /// </summary>
        public bool MomentumEnableAutoBreakEven { get; private set; }

        /// <summary>
        /// PHASE 12.10: Break-even trigger in R-multiples.
        /// When profit reaches this multiple of initial risk, stop moves to entry.
        /// Matches standalone BETriggerR = 1.5 parameter.
        /// Default: 1.5
        /// </summary>
        public double MomentumBETriggerR { get; private set; }

        /// <summary>
        /// PHASE 13: Maximum ATR value allowed for Momentum entries.
        /// Rejects entries when ATR exceeds this ceiling (filters extreme volatility).
        /// 0 = disabled (no ATR ceiling).
        /// Default: 30.0
        /// </summary>
        public double MomentumMaxATR { get; private set; }

        /// <summary>
        /// PHASE 19: Secondary ATR ceiling computed on 15-minute bars (ATR(14)).
        /// Filters regime-level volatility that the 1-min ATR gate misses.
        /// Validated 6-year IS/OOS: WR 51.3% -> 57.8% at threshold 40.
        /// 0 = disabled. Default: 40.0
        /// </summary>
        public double MomentumMaxATR15m { get; private set; }

        /// <summary>
        /// PHASE 13: Daily profit cap for Momentum module in dollars.
        /// Once realized Momentum P&L for the day reaches this level,
        /// no new Momentum entries are allowed for the rest of the session.
        /// 0 = disabled (no cap).
        /// Default: 200.0
        /// </summary>
        public double MomentumDailyProfitCap { get; private set; }

        /// <summary>
        /// PHASE 13.1: Maximum Momentum trades per day. 0 = unlimited.
        /// Trade #4+ is negative EV based on backtest analysis.
        /// Default: 3
        /// </summary>
        public int MomentumMaxDailyTrades { get; private set; }

        /// <summary>
        /// Hour (CT, 24h) at which open Momentum positions are force-exited.
        /// Frees the execution slot for AfternoonMR. 0 = disabled.
        /// Default: 0 (disabled)
        /// </summary>
        public int MomentumHardExitHourCT { get; private set; }

        /// <summary>
        /// PHASE 13: Comma-separated list of blocked hours (ET) for Momentum entries.
        /// Hours in this list will reject all Momentum entry signals.
        /// Uses 24-hour format ET (e.g., "9,13,14" blocks 9:00-9:59, 13:00-13:59, 14:00-14:59 ET).
        /// Note: ET = CT+1. So blocking hour 9 ET blocks 8:00-8:59 CT.
        /// Empty string = no hour blocking.
        /// Default: "9,13,14" (blocks 8AM, 12PM, 1PM CT — worst-performing hours)
        /// </summary>
        public string MomentumBlockedHoursET { get; private set; }

        /// <summary>
        /// PHASE 13: Parsed blocked hours as a HashSet for fast lookup.
        /// Populated from MomentumBlockedHoursET during Build().
        /// </summary>
        public System.Collections.Generic.HashSet<int> MomentumBlockedHoursSet { get; private set; }

        #endregion

        #region ORB Module Configuration

        /// <summary>
        /// Enable ORB (Opening Range Breakout) module.
        /// </summary>
        public bool EnableORBModule { get; private set; }

        /// <summary>
        /// Minimum opening range size in points.
        /// Ranges smaller than this are not traded (insufficient volatility).
        /// Default: 10.0
        /// </summary>
        public double ORBMinRangePoints { get; private set; }

        /// <summary>
        /// Maximum opening range size in points.
        /// Ranges larger than this are not traded (too volatile/wide stops).
        /// Default: 100.0
        /// </summary>
        public double ORBMaxRangePoints { get; private set; }

        /// <summary>
        /// Maximum stop distance in points.
        /// Caps the stop when entry-to-rangeLow exceeds this value.
        /// Locked value: 80.0 (from optimization)
        /// </summary>
        public double ORBMaxStopPoints { get; private set; }

        /// <summary>
        /// Buffer added to stop distance beyond opposite range boundary.
        /// Default: 2.0 points
        /// </summary>
        public double ORBStopBuffer { get; private set; }

        /// <summary>
        /// Target distance as multiplier of range size, measured from breakout side.
        /// Locked value: 0.8 (from optimization - best PF, edge, and drawdown)
        /// </summary>
        public double ORBTargetMultiplier { get; private set; }

        /// <summary>
        /// Enable VWAP alignment filter for breakout confirmation.
        /// Long: Close > VWAP. Short: Close < VWAP.
        /// Default: true
        /// </summary>
        public bool ORBEnableVWAPFilter { get; private set; }

        /// <summary>
        /// Enable auto break-even for ORB trades.
        /// Default: true
        /// </summary>
        public bool ORBEnableBreakEven { get; private set; }

        /// <summary>
        /// Break-even trigger in R-multiples for ORB trades.
        /// Default: 1.0
        /// </summary>
        public double ORBBETriggerR { get; private set; }

        /// <summary>
        /// Buffer above/below range boundary required to confirm breakout.
        /// Filters noise on 1-minute bars.
        /// Default: 0.0 (no buffer)
        /// </summary>
        public double ORBBreakoutBuffer { get; private set; }

        /// <summary>
        /// PHASE 13.1: Earliest hour (ET, 24h) for ORB entries.
        /// 8AM CT entries are breakeven; 9AM+ entries are 82.6% WR.
        /// Value of 10 means entries only at 10:00 ET (=9:00 CT) and later.
        /// 0 = no restriction. Default: 10 (=9AM CT)
        /// </summary>
        public int ORBEarliestEntryHourET { get; private set; }

        // ----------------------------------------------------------------
        // PHASE 5: ORB Optimization Knobs (orb-optimization-spec.md)
        // All defaults preserve baseline behavior (toggles default off / 0).
        // ----------------------------------------------------------------

        /// <summary>
        /// PHASE 5 / Opt 1: Toggle ATR-scaled range filter.
        /// When false, the existing ORBMinRangePoints / ORBMaxRangePoints
        /// fixed-point filter is used (baseline). When true, the range is
        /// validated against ORBMinRangeATR / ORBMaxRangeATR multiples of
        /// the 15m ATR(14).
        /// Default: false (baseline behavior).
        /// </summary>
        public bool ORBUseATRRangeFilter { get; private set; }

        /// <summary>
        /// PHASE 5 / Opt 1: Minimum opening range as a fraction of 15m ATR(14).
        /// Only used when ORBUseATRRangeFilter is true.
        /// Default: 0.25
        /// </summary>
        public double ORBMinRangeATR { get; private set; }

        /// <summary>
        /// PHASE 5 / Opt 1: Maximum opening range as a fraction of 15m ATR(14).
        /// Only used when ORBUseATRRangeFilter is true.
        /// Default: 2.5
        /// </summary>
        public double ORBMaxRangeATR { get; private set; }

        /// <summary>
        /// PHASE 5 / Opt 2: Toggle ATR-scaled max-stop cap.
        /// When false, ORBMaxStopPoints (fixed) is used (baseline).
        /// When true, max stop is capped at ORBMaxStopATR x 15m ATR(14).
        /// Default: false (baseline behavior).
        /// </summary>
        public bool ORBUseATRStop { get; private set; }

        /// <summary>
        /// PHASE 5 / Opt 2: Max stop distance as a fraction of 15m ATR(14).
        /// Only used when ORBUseATRStop is true.
        /// Default: 1.5
        /// </summary>
        public double ORBMaxStopATR { get; private set; }

        /// <summary>
        /// PHASE 5 / Opt 3: Latest hour (ET, 24h) for ORB entries.
        /// Entries at or after this hour are rejected. Hour 11 = 11:00 ET
        /// (=10:00 CT). 0 = disabled (no upper bound).
        /// Default: 0 (baseline; disabled).
        /// </summary>
        public int ORBLatestEntryHourET { get; private set; }

        /// <summary>
        /// PHASE 5 / Opt 4: Maximum 15m ATR(14) for ORB entries.
        /// Filters extreme-volatility regimes that produce wide ranges and
        /// failed breakouts. 0 = disabled.
        /// Default: 0 (baseline; disabled).
        /// </summary>
        public double ORBMaxATR15m { get; private set; }

        /// <summary>
        /// PHASE 5 / Opt 5: Maximum hold time (minutes) for an ORB position
        /// before forced market exit. The exit fires from ExecutionEngine
        /// per-bar management. 0 = disabled.
        /// Default: 0 (baseline; disabled).
        /// </summary>
        public int ORBMaxHoldMinutes { get; private set; }

        #endregion

        #region AfternoonMR Module (Phase 15)

        public bool EnableAfternoonMRModule { get; private set; }
        public int AfternoonMRStartHourCT { get; private set; }
        public int AfternoonMREndHourCT { get; private set; }
        public double AfternoonMRMinVWAPDeviation { get; private set; }
        public double AfternoonMRMaxVWAPDeviation { get; private set; }
        public double AfternoonMRStopDistancePoints { get; private set; }
        public double AfternoonMRTargetVWAPFraction { get; private set; }
        public double AfternoonMRMaxATR { get; private set; }
        public bool AfternoonMREnableBreakEven { get; private set; }
        public double AfternoonMRBETriggerR { get; private set; }
        public int AfternoonMRMaxDailyTrades { get; private set; }
        public int AfternoonMRTimeExitHourCT { get; private set; }
        public int AfternoonMRTimeExitMinuteCT { get; private set; }
        public int AfternoonMRQuantity { get; private set; }

        #endregion

        #region CloseCont Module (Phase 17)

        public bool EnableCloseContModule { get; private set; }
        public int CloseContStartHourCT { get; private set; }
        public int CloseContStartMinuteCT { get; private set; }
        public int CloseContEndHourCT { get; private set; }
        public int CloseContEndMinuteCT { get; private set; }
        public int CloseContHardExitHourCT { get; private set; }
        public int CloseContHardExitMinuteCT { get; private set; }
        public double CloseContMinSetupMagnitude { get; private set; }
        public double CloseContStopDistancePoints { get; private set; }
        public double CloseContTargetDistancePoints { get; private set; }
        public double CloseContMaxATR { get; private set; }
        public bool CloseContEnableBreakEven { get; private set; }
        public double CloseContBETriggerR { get; private set; }
        public int CloseContMaxDailyTrades { get; private set; }
        public int CloseContQuantity { get; private set; }

        #endregion

        #region Dynamic Sizing (Phase 14)

        /// <summary>
        /// Master toggle for two-tier dynamic position sizing.
        /// When false, static per-module quantities are used (baseline-identical).
        /// </summary>
        public bool EnableDynamicSizer { get; private set; }

        /// <summary>
        /// Qty multiplier during Initial phase (building buffer).
        /// Default: 0.5
        /// </summary>
        public double DynamicSizerInitialMultiplier { get; private set; }

        /// <summary>
        /// Qty multiplier during Full phase (buffer established).
        /// Default: 1.25
        /// </summary>
        public double DynamicSizerFullMultiplier { get; private set; }

        /// <summary>
        /// Cumulative realized profit ($) required to transition Initial -> Full.
        /// Default: 1000.0
        /// </summary>
        public double DynamicSizerBufferThreshold { get; private set; }

        #endregion

        #region Debug Toggles (Phase 6 - Isolation Mode)

        /// <summary>
        /// Debug: Disable session gate for isolation testing.
        /// </summary>
        public bool DebugDisableSessionGate { get; private set; }

        /// <summary>
        /// Debug: Disable volatility gate for isolation testing.
        /// </summary>
        public bool DebugDisableVolatilityGate { get; private set; }

        /// <summary>
        /// Debug: Disable risk gate for new entries (flatten rules still active).
        /// </summary>
        public bool DebugDisableRiskGate { get; private set; }

        /// <summary>
        /// Debug: Force Range module eligible even if gates block it.
        /// </summary>
        public bool DebugForceRangeEnabled { get; private set; }

        /// <summary>
        /// PHASE 12.3: Disable Momentum-specific gating for semantic parity verification.
        /// </summary>
        public bool DebugDisableMomentumGates { get; private set; }

        /// <summary>
        /// PHASE 12.5: Disable Momentum session gate for validation testing.
        /// </summary>
        public bool DebugDisableMomentumSessionGate { get; private set; }

        #endregion

        /// <summary>
        /// Private constructor - use Builder to create instances.
        /// </summary>
        private Config() { }

        /// <summary>
        /// Creates a default configuration suitable for Flux v1 validation.
        /// </summary>
        public static Config CreateDefault()
        {
            return new Builder().Build();
        }

        /// <summary>
        /// Builder pattern for creating immutable Config instances.
        /// </summary>
        public class Builder
        {
            private Config _config = new Config();

            public Builder()
            {
                // Set sensible defaults
                _config.EnableLogging = true;
                _config.LogLevel = LogLevel.Info;
                _config.EnableTelemetryCounters = true;

                _config.SessionTimeZone = "America/Chicago";
                _config.RTHOnly = true;

                _config.MaxDailyLossCurrency = 500.0;
                _config.MaxTrailingDrawdownCurrency = 1000.0;
                _config.MaxTradesPerDay = 10;

                _config.OnePositionAtATime = true;
                _config.OneModuleAtATime = true;

                _config.EnableVolatilityGate = true;
                _config.VolGateMode = VolGateMode.ATR;
                _config.ATRPeriod = 14;
                _config.VolLookbackBars = 50;
                _config.VolHighPercentile = 0.7;
                _config.VolLowPercentile = 0.3;

                _config.EnableRangeModule = true;
                _config.EnableMomentumModule = true;
                _config.EnableORBModule = true;
                _config.ModulePriorities = new List<string> { "ORB", "Momentum", "AfternoonMR", "Range", "CloseCont" };
                _config.MomentumQuantity = 1;
                _config.ORBQuantity = 1;
                _config.RangeQuantity = 1;

                // PHASE 15: AfternoonMR defaults (disabled by default)
                _config.EnableAfternoonMRModule = false;
                _config.AfternoonMRStartHourCT = 12;
                _config.AfternoonMREndHourCT = 15;
                _config.AfternoonMRMinVWAPDeviation = 15.0;
                _config.AfternoonMRMaxVWAPDeviation = 60.0;
                _config.AfternoonMRStopDistancePoints = 25.0;
                _config.AfternoonMRTargetVWAPFraction = 0.5;
                _config.AfternoonMRMaxATR = 35.0;
                _config.AfternoonMREnableBreakEven = true;
                _config.AfternoonMRBETriggerR = 1.0;
                _config.AfternoonMRMaxDailyTrades = 3;
                _config.AfternoonMRTimeExitHourCT = 15;
                _config.AfternoonMRTimeExitMinuteCT = 15;
                _config.AfternoonMRQuantity = 1;

                // PHASE 17: CloseCont defaults (disabled by default)
                _config.EnableCloseContModule = false;
                _config.CloseContStartHourCT = 14;       // 14:00 CT = 15:00 ET
                _config.CloseContStartMinuteCT = 0;
                _config.CloseContEndHourCT = 15;          // 15:00 CT = 16:00 ET
                _config.CloseContEndMinuteCT = 0;
                _config.CloseContHardExitHourCT = 15;     // Hard exit at 15:00 CT = 16:00 ET
                _config.CloseContHardExitMinuteCT = 0;
                _config.CloseContMinSetupMagnitude = 5.0;  // Min 5-pt move to confirm direction
                _config.CloseContStopDistancePoints = 25.0;
                _config.CloseContTargetDistancePoints = 25.0;
                _config.CloseContMaxATR = 35.0;
                _config.CloseContEnableBreakEven = false;
                _config.CloseContBETriggerR = 1.0;
                _config.CloseContMaxDailyTrades = 1;
                _config.CloseContQuantity = 1;

                // PHASE 14: Two-tier dynamic sizer defaults (disabled by default)
                _config.EnableDynamicSizer = false;
                _config.DynamicSizerInitialMultiplier = 0.5;
                _config.DynamicSizerFullMultiplier = 1.25;
                _config.DynamicSizerBufferThreshold = 1000.0;

                _config.ModuleCooldownBars = 5;

                _config.DefaultQuantity = 1;
                _config.MinStopTicks = 4;
                _config.MaxStopTicks = 100;
                _config.MinTargetTicks = 4;

                // Range module defaults (from Phase 3 Iter 04)
                _config.RangeCompressionLookback = 50;
                _config.RangeCompressionPercentile = 0.3;
                _config.RangeLookback = 50;
                _config.RangeStopMultiplier = 0.5;
                _config.RangeTargetMultiplier = 1.5;
                _config.RangeTrailingActivation = 0.5;
                _config.RangeTrailingDistance = 0.5;
                _config.RangeTrailRatchetEnabled = true;
                _config.RangeTrailMultiplierInitial = 0.50;
                _config.RangeTrailMultiplierMid = 0.40;
                _config.RangeTrailMultiplierTight = 0.30;
                _config.RangeTrailRatchetThreshold1R = 1.0;
                _config.RangeTrailRatchetThreshold2R = 2.0;
                _config.RangeBlockedHoursCT = "7,20,22";       // PHASE 13.1: Block losing Range hours (CT)
                _config.RangeBlockedHoursSet = new System.Collections.Generic.HashSet<int>();

                // Momentum module defaults (Phase 12.10: Parity mode enabled by default)
                _config.MomentumParityMode = true;
                _config.MomentumEnableVWAPFilter = false;
                _config.MomentumVWAPDeviation = 0.0;
                _config.MomentumFixedStopDistance = 80.0;       // Reverted from Phase 16 experiment (55)
                _config.MomentumEnableAutoBreakEven = true;    // From standalone: EnableAutoBE = true
                _config.MomentumBETriggerR = 1.5;              // From standalone: BETriggerR = 1.5

                // PHASE 13: Momentum optimization filters
                _config.MomentumDailyProfitCap = 0;            // Disabled (data showed $200 cap hurts)
                _config.MomentumMaxDailyTrades = 3;            // PHASE 13.1: Max 3/day (trade #4+ is -EV)
                _config.MomentumHardExitHourCT = 0;            // Disabled by default (0 = no forced exit)
                _config.MomentumBlockedHoursET = "9,13,14";    // Block 9AM, 1PM, 2PM ET (= 8AM, 12PM, 1PM CT)
                _config.MomentumBlockedHoursSet = new System.Collections.Generic.HashSet<int>();
                _config.MomentumMaxATR = 30.0;                 // ATR ceiling (0 = disabled)
                _config.MomentumMaxATR15m = 40.0;              // PHASE 19: 15-min ATR ceiling (0 = disabled)

                // ORB module defaults (locked from optimization: target=0.8, maxStop=80)
                _config.ORBMinRangePoints = 10.0;
                _config.ORBMaxRangePoints = 100.0;
                _config.ORBMaxStopPoints = 80.0;       // Locked: 80-point max stop
                _config.ORBStopBuffer = 2.0;
                _config.ORBTargetMultiplier = 0.8;     // Locked: best PF (1.35), edge (6.8pp), lowest DD
                _config.ORBEnableVWAPFilter = true;
                _config.ORBEnableBreakEven = true;
                _config.ORBBETriggerR = 1.0;            // Reverted from Phase 16 experiment (0.75)
                _config.ORBBreakoutBuffer = 0.0;
                _config.ORBEarliestEntryHourET = 10;           // PHASE 13.1: 10:00 ET = 9:00 CT

                // PHASE 5: ORB optimization knobs (all default OFF / baseline behavior)
                _config.ORBUseATRRangeFilter = false;
                _config.ORBMinRangeATR = 0.25;
                _config.ORBMaxRangeATR = 2.5;
                _config.ORBUseATRStop = false;
                _config.ORBMaxStopATR = 1.5;
                _config.ORBLatestEntryHourET = 0;              // 0 = disabled
                _config.ORBMaxATR15m = 0;                       // 0 = disabled
                _config.ORBMaxHoldMinutes = 0;                  // 0 = disabled

                // Debug toggles default to false (isolation mode disabled)
                _config.DebugDisableSessionGate = false;
                _config.DebugDisableVolatilityGate = false;
                _config.DebugDisableRiskGate = false;
                _config.DebugForceRangeEnabled = false;
                _config.DebugDisableMomentumGates = false;
                _config.DebugDisableMomentumSessionGate = false;

                // Audit logging defaults to false (opt-in for performance)
                _config.EnableFileAuditLogging = false;
            }

            /// <summary>
            /// Creates a Builder that copies all values from an existing Config.
            /// Useful for creating modified versions of existing configurations.
            /// </summary>
            public Builder(Config existingConfig)
            {
                _config = new Config();
                CopyFrom(existingConfig);
            }

            private void CopyFrom(Config source)
            {
                _config.EnableLogging = source.EnableLogging;
                _config.LogLevel = source.LogLevel;
                _config.EnableTelemetryCounters = source.EnableTelemetryCounters;
                _config.EnableFileAuditLogging = source.EnableFileAuditLogging;
                _config.SessionTimeZone = source.SessionTimeZone;
                _config.RTHOnly = source.RTHOnly;
                _config.MaxDailyLossCurrency = source.MaxDailyLossCurrency;
                _config.MaxTrailingDrawdownCurrency = source.MaxTrailingDrawdownCurrency;
                _config.MaxTradesPerDay = source.MaxTradesPerDay;
                _config.OnePositionAtATime = source.OnePositionAtATime;
                _config.OneModuleAtATime = source.OneModuleAtATime;
                _config.EnableVolatilityGate = source.EnableVolatilityGate;
                _config.VolGateMode = source.VolGateMode;
                _config.ATRPeriod = source.ATRPeriod;
                _config.VolLookbackBars = source.VolLookbackBars;
                _config.VolHighPercentile = source.VolHighPercentile;
                _config.VolLowPercentile = source.VolLowPercentile;
                _config.EnableRangeModule = source.EnableRangeModule;
                _config.EnableMomentumModule = source.EnableMomentumModule;
                _config.EnableORBModule = source.EnableORBModule;
                _config.ModulePriorities = new List<string>(source.ModulePriorities);
                _config.MomentumQuantity = source.MomentumQuantity;
                _config.ORBQuantity = source.ORBQuantity;
                _config.RangeQuantity = source.RangeQuantity;
                _config.ModuleCooldownBars = source.ModuleCooldownBars;
                _config.DefaultQuantity = source.DefaultQuantity;
                _config.MinStopTicks = source.MinStopTicks;
                _config.MaxStopTicks = source.MaxStopTicks;
                _config.MinTargetTicks = source.MinTargetTicks;
                _config.RangeCompressionLookback = source.RangeCompressionLookback;
                _config.RangeCompressionPercentile = source.RangeCompressionPercentile;
                _config.RangeLookback = source.RangeLookback;
                _config.RangeStopMultiplier = source.RangeStopMultiplier;
                _config.RangeTargetMultiplier = source.RangeTargetMultiplier;
                _config.RangeTrailingActivation = source.RangeTrailingActivation;
                _config.RangeTrailingDistance = source.RangeTrailingDistance;
                _config.RangeTrailRatchetEnabled = source.RangeTrailRatchetEnabled;
                _config.RangeTrailMultiplierInitial = source.RangeTrailMultiplierInitial;
                _config.RangeTrailMultiplierMid = source.RangeTrailMultiplierMid;
                _config.RangeTrailMultiplierTight = source.RangeTrailMultiplierTight;
                _config.RangeTrailRatchetThreshold1R = source.RangeTrailRatchetThreshold1R;
                _config.RangeTrailRatchetThreshold2R = source.RangeTrailRatchetThreshold2R;
                _config.RangeBlockedHoursCT = source.RangeBlockedHoursCT;
                _config.RangeBlockedHoursSet = source.RangeBlockedHoursSet != null
                    ? new System.Collections.Generic.HashSet<int>(source.RangeBlockedHoursSet)
                    : new System.Collections.Generic.HashSet<int>();
                _config.MomentumParityMode = source.MomentumParityMode;
                _config.MomentumEnableVWAPFilter = source.MomentumEnableVWAPFilter;
                _config.MomentumVWAPDeviation = source.MomentumVWAPDeviation;
                _config.MomentumFixedStopDistance = source.MomentumFixedStopDistance;
                _config.MomentumEnableAutoBreakEven = source.MomentumEnableAutoBreakEven;
                _config.MomentumBETriggerR = source.MomentumBETriggerR;
                _config.MomentumDailyProfitCap = source.MomentumDailyProfitCap;
                _config.MomentumMaxDailyTrades = source.MomentumMaxDailyTrades;
                _config.MomentumHardExitHourCT = source.MomentumHardExitHourCT;
                _config.MomentumBlockedHoursET = source.MomentumBlockedHoursET;
                _config.MomentumBlockedHoursSet = source.MomentumBlockedHoursSet != null 
                    ? new System.Collections.Generic.HashSet<int>(source.MomentumBlockedHoursSet) 

                    : new System.Collections.Generic.HashSet<int>();
                _config.MomentumMaxATR = source.MomentumMaxATR;
                _config.MomentumMaxATR15m = source.MomentumMaxATR15m;
                _config.ORBMinRangePoints = source.ORBMinRangePoints;
                _config.ORBMaxRangePoints = source.ORBMaxRangePoints;
                _config.ORBMaxStopPoints = source.ORBMaxStopPoints;
                _config.ORBStopBuffer = source.ORBStopBuffer;
                _config.ORBTargetMultiplier = source.ORBTargetMultiplier;
                _config.ORBEnableVWAPFilter = source.ORBEnableVWAPFilter;
                _config.ORBEnableBreakEven = source.ORBEnableBreakEven;
                _config.ORBBETriggerR = source.ORBBETriggerR;
                _config.ORBBreakoutBuffer = source.ORBBreakoutBuffer;
                _config.ORBEarliestEntryHourET = source.ORBEarliestEntryHourET;

                // PHASE 5: ORB optimization knobs
                _config.ORBUseATRRangeFilter = source.ORBUseATRRangeFilter;
                _config.ORBMinRangeATR = source.ORBMinRangeATR;
                _config.ORBMaxRangeATR = source.ORBMaxRangeATR;
                _config.ORBUseATRStop = source.ORBUseATRStop;
                _config.ORBMaxStopATR = source.ORBMaxStopATR;
                _config.ORBLatestEntryHourET = source.ORBLatestEntryHourET;
                _config.ORBMaxATR15m = source.ORBMaxATR15m;
                _config.ORBMaxHoldMinutes = source.ORBMaxHoldMinutes;

                // PHASE 15: AfternoonMR copy
                _config.EnableAfternoonMRModule = source.EnableAfternoonMRModule;
                _config.AfternoonMRStartHourCT = source.AfternoonMRStartHourCT;
                _config.AfternoonMREndHourCT = source.AfternoonMREndHourCT;
                _config.AfternoonMRMinVWAPDeviation = source.AfternoonMRMinVWAPDeviation;
                _config.AfternoonMRMaxVWAPDeviation = source.AfternoonMRMaxVWAPDeviation;
                _config.AfternoonMRStopDistancePoints = source.AfternoonMRStopDistancePoints;
                _config.AfternoonMRTargetVWAPFraction = source.AfternoonMRTargetVWAPFraction;
                _config.AfternoonMRMaxATR = source.AfternoonMRMaxATR;
                _config.AfternoonMREnableBreakEven = source.AfternoonMREnableBreakEven;
                _config.AfternoonMRBETriggerR = source.AfternoonMRBETriggerR;
                _config.AfternoonMRMaxDailyTrades = source.AfternoonMRMaxDailyTrades;
                _config.AfternoonMRTimeExitHourCT = source.AfternoonMRTimeExitHourCT;
                _config.AfternoonMRTimeExitMinuteCT = source.AfternoonMRTimeExitMinuteCT;
                _config.AfternoonMRQuantity = source.AfternoonMRQuantity;

                // PHASE 17: CloseCont copy
                _config.EnableCloseContModule = source.EnableCloseContModule;
                _config.CloseContStartHourCT = source.CloseContStartHourCT;
                _config.CloseContStartMinuteCT = source.CloseContStartMinuteCT;
                _config.CloseContEndHourCT = source.CloseContEndHourCT;
                _config.CloseContEndMinuteCT = source.CloseContEndMinuteCT;
                _config.CloseContHardExitHourCT = source.CloseContHardExitHourCT;
                _config.CloseContHardExitMinuteCT = source.CloseContHardExitMinuteCT;
                _config.CloseContMinSetupMagnitude = source.CloseContMinSetupMagnitude;
                _config.CloseContStopDistancePoints = source.CloseContStopDistancePoints;
                _config.CloseContTargetDistancePoints = source.CloseContTargetDistancePoints;
                _config.CloseContMaxATR = source.CloseContMaxATR;
                _config.CloseContEnableBreakEven = source.CloseContEnableBreakEven;
                _config.CloseContBETriggerR = source.CloseContBETriggerR;
                _config.CloseContMaxDailyTrades = source.CloseContMaxDailyTrades;
                _config.CloseContQuantity = source.CloseContQuantity;

                // PHASE 14: Dynamic sizer copy
                _config.EnableDynamicSizer = source.EnableDynamicSizer;
                _config.DynamicSizerInitialMultiplier = source.DynamicSizerInitialMultiplier;
                _config.DynamicSizerFullMultiplier = source.DynamicSizerFullMultiplier;
                _config.DynamicSizerBufferThreshold = source.DynamicSizerBufferThreshold;

                _config.DebugDisableSessionGate = source.DebugDisableSessionGate;
                _config.DebugDisableVolatilityGate = source.DebugDisableVolatilityGate;
                _config.DebugDisableRiskGate = source.DebugDisableRiskGate;
                _config.DebugForceRangeEnabled = source.DebugForceRangeEnabled;
                _config.DebugDisableMomentumGates = source.DebugDisableMomentumGates;
            }

            public Builder WithLogging(bool enable, LogLevel level)
            {
                _config.EnableLogging = enable;
                _config.LogLevel = level;
                return this;
            }

            public Builder WithFileAuditLogging(bool enable)
            {
                _config.EnableFileAuditLogging = enable;
                return this;
            }

            public Builder WithRiskLimits(double dailyLoss, double trailingDrawdown, int maxTrades)
            {
                _config.MaxDailyLossCurrency = dailyLoss;
                _config.MaxTrailingDrawdownCurrency = trailingDrawdown;
                _config.MaxTradesPerDay = maxTrades;
                return this;
            }

            public Builder WithVolatilityGate(bool enable, double highPercentile, double lowPercentile)
            {
                _config.EnableVolatilityGate = enable;
                _config.VolHighPercentile = highPercentile;
                _config.VolLowPercentile = lowPercentile;
                return this;
            }

            public Builder WithDefaultQuantity(int quantity)
            {
                _config.DefaultQuantity = quantity;
                return this;
            }

            public Builder WithModulePriorities(List<string> priorities)
            {
                _config.ModulePriorities = priorities;
                return this;
            }

            public Builder WithMomentumQuantity(int quantity)
            {
                _config.MomentumQuantity = Math.Max(1, Math.Min(quantity, 100));
                return this;
            }

            public Builder WithORBQuantity(int quantity)
            {
                _config.ORBQuantity = Math.Max(1, Math.Min(quantity, 100));
                return this;
            }

            public Builder WithRangeQuantity(int quantity)
            {
                _config.RangeQuantity = Math.Max(1, Math.Min(quantity, 100));
                return this;
            }

            public Builder WithRTHOnly(bool rthOnly)
            {
                _config.RTHOnly = rthOnly;
                return this;
            }

            public Builder WithDebugDisableMomentumGates(bool disable)
            {
                _config.DebugDisableMomentumGates = disable;
                return this;
            }

            public Builder WithDebugDisableMomentumSessionGate(bool disable)
            {
                _config.DebugDisableMomentumSessionGate = disable;
                return this;
            }

            public Builder WithMomentumVWAP(bool enable, double deviation)
            {
                _config.MomentumEnableVWAPFilter = enable;
                _config.MomentumVWAPDeviation = deviation;
                return this;
            }

            public Builder WithMomentumParityMode(bool enable)
            {
                _config.MomentumParityMode = enable;
                return this;
            }

            public Builder WithMomentumFixedStopDistance(double distance)
            {
                _config.MomentumFixedStopDistance = distance;
                return this;
            }

            public Builder WithMomentumAutoBreakEven(bool enable, double triggerR)
            {
                _config.MomentumEnableAutoBreakEven = enable;
                _config.MomentumBETriggerR = triggerR;
                return this;
            }

            /// <summary>
            /// PHASE 13: Configure Momentum daily profit cap.
            /// </summary>
            public Builder WithMomentumDailyProfitCap(double cap)
            {
                _config.MomentumDailyProfitCap = cap;
                return this;
            }

            public Builder WithMomentumMaxDailyTrades(int maxTrades)
            {
                _config.MomentumMaxDailyTrades = maxTrades;
                return this;
            }

            public Builder WithMomentumHardExitHour(int hourCT)
            {
                _config.MomentumHardExitHourCT = Math.Max(0, Math.Min(hourCT, 16));
                return this;
            }

            /// <summary>
            /// PHASE 13: Configure Momentum blocked hours (ET).
            /// </summary>
            public Builder WithMomentumBlockedHours(string blockedHoursET)
            {
                _config.MomentumBlockedHoursET = blockedHoursET ?? "";
                return this;
            }

            /// <summary>
            /// PHASE 13: Configure Momentum max ATR ceiling.
            /// </summary>
            public Builder WithMomentumMaxATR(double maxATR)
            {
                _config.MomentumMaxATR = maxATR;
                return this;
            }

            /// <summary>
            /// PHASE 19: Configure Momentum 15-minute ATR ceiling.
            /// </summary>
            public Builder WithMomentumMaxATR15m(double maxATR15m)
            {
                _config.MomentumMaxATR15m = maxATR15m;
                return this;
            }

            public Builder WithORBModule(bool enable)
            {
                _config.EnableORBModule = enable;
                return this;
            }

            public Builder WithORBParameters(double minRange, double maxRange, double maxStop,
                double stopBuffer, double targetMultiplier, double breakoutBuffer)
            {
                _config.ORBMinRangePoints = minRange;
                _config.ORBMaxRangePoints = maxRange;
                _config.ORBMaxStopPoints = maxStop;
                _config.ORBStopBuffer = stopBuffer;
                _config.ORBTargetMultiplier = targetMultiplier;
                _config.ORBBreakoutBuffer = breakoutBuffer;
                return this;
            }

            public Builder WithORBVWAPFilter(bool enable)
            {
                _config.ORBEnableVWAPFilter = enable;
                return this;
            }

            public Builder WithORBBreakEven(bool enable, double triggerR)
            {
                _config.ORBEnableBreakEven = enable;
                _config.ORBBETriggerR = triggerR;
                return this;
            }

            public Builder WithORBEarliestEntryHour(int hourET)
            {
                _config.ORBEarliestEntryHourET = hourET;
                return this;
            }

            // ----------------------------------------------------------------
            // PHASE 5: ORB optimization knob builders
            // ----------------------------------------------------------------

            /// <summary>
            /// PHASE 5 / Opt 1: Configure ATR-scaled range filter.
            /// </summary>
            public Builder WithORBATRRangeFilter(bool enable, double minATR, double maxATR)
            {
                _config.ORBUseATRRangeFilter = enable;
                _config.ORBMinRangeATR = minATR;
                _config.ORBMaxRangeATR = maxATR;
                return this;
            }

            /// <summary>
            /// PHASE 5 / Opt 2: Configure ATR-scaled max-stop cap.
            /// </summary>
            public Builder WithORBATRStop(bool enable, double maxStopATR)
            {
                _config.ORBUseATRStop = enable;
                _config.ORBMaxStopATR = maxStopATR;
                return this;
            }

            /// <summary>
            /// PHASE 5 / Opt 3: Configure latest entry hour gate (ET).
            /// </summary>
            public Builder WithORBLatestEntryHour(int hourET)
            {
                _config.ORBLatestEntryHourET = hourET;
                return this;
            }

            /// <summary>
            /// PHASE 5 / Opt 4: Configure 15m ATR ceiling.
            /// </summary>
            public Builder WithORBMaxATR15m(double maxATR15m)
            {
                _config.ORBMaxATR15m = maxATR15m;
                return this;
            }

            /// <summary>
            /// PHASE 5 / Opt 5: Configure max-hold-minutes time exit.
            /// </summary>
            public Builder WithORBMaxHoldMinutes(int maxHoldMinutes)
            {
                _config.ORBMaxHoldMinutes = maxHoldMinutes;
                return this;
            }

            // PHASE 15: AfternoonMR builders
            public Builder WithAfternoonMRModule(bool enable)
            {
                _config.EnableAfternoonMRModule = enable;
                return this;
            }

            public Builder WithAfternoonMRParameters(int startHour, int endHour,
                double minDeviation, double maxDeviation, double stopDistance,
                double targetFraction, double maxATR, int maxDailyTrades)
            {
                _config.AfternoonMRStartHourCT = startHour;
                _config.AfternoonMREndHourCT = endHour;
                _config.AfternoonMRMinVWAPDeviation = minDeviation;
                _config.AfternoonMRMaxVWAPDeviation = maxDeviation;
                _config.AfternoonMRStopDistancePoints = stopDistance;
                _config.AfternoonMRTargetVWAPFraction = targetFraction;
                _config.AfternoonMRMaxATR = maxATR;
                _config.AfternoonMRMaxDailyTrades = maxDailyTrades;
                return this;
            }

            public Builder WithAfternoonMRBreakEven(bool enable, double triggerR)
            {
                _config.AfternoonMREnableBreakEven = enable;
                _config.AfternoonMRBETriggerR = triggerR;
                return this;
            }

            public Builder WithAfternoonMRTimeExit(int hour, int minute)
            {
                _config.AfternoonMRTimeExitHourCT = hour;
                _config.AfternoonMRTimeExitMinuteCT = minute;
                return this;
            }

            public Builder WithAfternoonMRQuantity(int quantity)
            {
                _config.AfternoonMRQuantity = Math.Max(1, Math.Min(quantity, 100));
                return this;
            }

            public Builder WithRangeBlockedHours(string blockedHoursCT)
            {
                _config.RangeBlockedHoursCT = blockedHoursCT;
                return this;
            }

            // PHASE 17: CloseCont builders
            public Builder WithCloseContModule(bool enable)
            {
                _config.EnableCloseContModule = enable;
                return this;
            }

            public Builder WithCloseContParameters(int startHour, int startMinute,
                int endHour, int endMinute, double minSetupMag, double stopDistance,
                double targetDistance, double maxATR, int maxDailyTrades)
            {
                _config.CloseContStartHourCT = startHour;
                _config.CloseContStartMinuteCT = startMinute;
                _config.CloseContEndHourCT = endHour;
                _config.CloseContEndMinuteCT = endMinute;
                _config.CloseContMinSetupMagnitude = minSetupMag;
                _config.CloseContStopDistancePoints = stopDistance;
                _config.CloseContTargetDistancePoints = targetDistance;
                _config.CloseContMaxATR = maxATR;
                _config.CloseContMaxDailyTrades = maxDailyTrades;
                return this;
            }

            public Builder WithCloseContBreakEven(bool enable, double triggerR)
            {
                _config.CloseContEnableBreakEven = enable;
                _config.CloseContBETriggerR = triggerR;
                return this;
            }

            public Builder WithCloseContHardExit(int hour, int minute)
            {
                _config.CloseContHardExitHourCT = hour;
                _config.CloseContHardExitMinuteCT = minute;
                return this;
            }

            public Builder WithCloseContQuantity(int quantity)
            {
                _config.CloseContQuantity = Math.Max(1, Math.Min(quantity, 100));
                return this;
            }

            public Builder WithRangeTrailRatchet(bool enabled, double initial, double mid, double tight,
                double threshold1R, double threshold2R)
            {
                _config.RangeTrailRatchetEnabled = enabled;
                _config.RangeTrailMultiplierInitial = initial;
                _config.RangeTrailMultiplierMid = mid;
                _config.RangeTrailMultiplierTight = tight;
                _config.RangeTrailRatchetThreshold1R = threshold1R;
                _config.RangeTrailRatchetThreshold2R = threshold2R;
                return this;
            }

            // PHASE 14: Two-tier dynamic sizer
            public Builder WithDynamicSizerSettings(bool enable, double initialMultiplier,
                double fullMultiplier, double bufferThreshold)
            {
                _config.EnableDynamicSizer = enable;
                _config.DynamicSizerInitialMultiplier = initialMultiplier;
                _config.DynamicSizerFullMultiplier = fullMultiplier;
                _config.DynamicSizerBufferThreshold = bufferThreshold;
                return this;
            }

            public Config Build()
            {
                // Create a deep copy to ensure immutability
                var config = new Config
                {
                    EnableLogging = _config.EnableLogging,
                    LogLevel = _config.LogLevel,
                    EnableTelemetryCounters = _config.EnableTelemetryCounters,
                    EnableFileAuditLogging = _config.EnableFileAuditLogging,
                    SessionTimeZone = _config.SessionTimeZone,
                    RTHOnly = _config.RTHOnly,
                    MaxDailyLossCurrency = _config.MaxDailyLossCurrency,
                    MaxTrailingDrawdownCurrency = _config.MaxTrailingDrawdownCurrency,
                    MaxTradesPerDay = _config.MaxTradesPerDay,
                    OnePositionAtATime = _config.OnePositionAtATime,
                    OneModuleAtATime = _config.OneModuleAtATime,
                    EnableVolatilityGate = _config.EnableVolatilityGate,
                    VolGateMode = _config.VolGateMode,
                    ATRPeriod = _config.ATRPeriod,
                    VolLookbackBars = _config.VolLookbackBars,
                    VolHighPercentile = _config.VolHighPercentile,
                    VolLowPercentile = _config.VolLowPercentile,
                    EnableRangeModule = _config.EnableRangeModule,
                    EnableMomentumModule = _config.EnableMomentumModule,
                    EnableORBModule = _config.EnableORBModule,
                    ModulePriorities = new List<string>(_config.ModulePriorities),
                    MomentumQuantity = _config.MomentumQuantity,
                    ORBQuantity = _config.ORBQuantity,
                    RangeQuantity = _config.RangeQuantity,
                    ModuleCooldownBars = _config.ModuleCooldownBars,
                    DefaultQuantity = _config.DefaultQuantity,
                    MinStopTicks = _config.MinStopTicks,
                    MaxStopTicks = _config.MaxStopTicks,
                    MinTargetTicks = _config.MinTargetTicks,
                    RangeCompressionLookback = _config.RangeCompressionLookback,
                    RangeCompressionPercentile = _config.RangeCompressionPercentile,
                    RangeLookback = _config.RangeLookback,
                    RangeStopMultiplier = _config.RangeStopMultiplier,
                    RangeTargetMultiplier = _config.RangeTargetMultiplier,
                    RangeTrailingActivation = _config.RangeTrailingActivation,
                    RangeTrailingDistance = _config.RangeTrailingDistance,
                    RangeTrailRatchetEnabled = _config.RangeTrailRatchetEnabled,
                    RangeTrailMultiplierInitial = _config.RangeTrailMultiplierInitial,
                    RangeTrailMultiplierMid = _config.RangeTrailMultiplierMid,
                    RangeTrailMultiplierTight = _config.RangeTrailMultiplierTight,
                    RangeTrailRatchetThreshold1R = _config.RangeTrailRatchetThreshold1R,
                    RangeTrailRatchetThreshold2R = _config.RangeTrailRatchetThreshold2R,
                    RangeBlockedHoursCT = _config.RangeBlockedHoursCT ?? "",
                    MomentumParityMode = _config.MomentumParityMode,
                    MomentumEnableVWAPFilter = _config.MomentumEnableVWAPFilter,
                    MomentumVWAPDeviation = _config.MomentumVWAPDeviation,
                    MomentumFixedStopDistance = _config.MomentumFixedStopDistance,
                    MomentumEnableAutoBreakEven = _config.MomentumEnableAutoBreakEven,
                    MomentumBETriggerR = _config.MomentumBETriggerR,
                    MomentumMaxATR = _config.MomentumMaxATR,
                    MomentumMaxATR15m = _config.MomentumMaxATR15m,
                    MomentumDailyProfitCap = _config.MomentumDailyProfitCap,
                    MomentumMaxDailyTrades = _config.MomentumMaxDailyTrades,
                    MomentumHardExitHourCT = _config.MomentumHardExitHourCT,
                    MomentumBlockedHoursET = _config.MomentumBlockedHoursET ?? "",
                    ORBMinRangePoints = _config.ORBMinRangePoints,
                    ORBMaxRangePoints = _config.ORBMaxRangePoints,
                    ORBMaxStopPoints = _config.ORBMaxStopPoints,
                    ORBStopBuffer = _config.ORBStopBuffer,
                    ORBTargetMultiplier = _config.ORBTargetMultiplier,
                    ORBEnableVWAPFilter = _config.ORBEnableVWAPFilter,
                    ORBEnableBreakEven = _config.ORBEnableBreakEven,
                    ORBBETriggerR = _config.ORBBETriggerR,
                    ORBBreakoutBuffer = _config.ORBBreakoutBuffer,
                    ORBEarliestEntryHourET = _config.ORBEarliestEntryHourET,
                    // PHASE 5: ORB optimization knobs
                    ORBUseATRRangeFilter = _config.ORBUseATRRangeFilter,
                    ORBMinRangeATR = _config.ORBMinRangeATR,
                    ORBMaxRangeATR = _config.ORBMaxRangeATR,
                    ORBUseATRStop = _config.ORBUseATRStop,
                    ORBMaxStopATR = _config.ORBMaxStopATR,
                    ORBLatestEntryHourET = _config.ORBLatestEntryHourET,
                    ORBMaxATR15m = _config.ORBMaxATR15m,
                    ORBMaxHoldMinutes = _config.ORBMaxHoldMinutes,
                    // PHASE 15: AfternoonMR
                    EnableAfternoonMRModule = _config.EnableAfternoonMRModule,
                    AfternoonMRStartHourCT = _config.AfternoonMRStartHourCT,
                    AfternoonMREndHourCT = _config.AfternoonMREndHourCT,
                    AfternoonMRMinVWAPDeviation = _config.AfternoonMRMinVWAPDeviation,
                    AfternoonMRMaxVWAPDeviation = _config.AfternoonMRMaxVWAPDeviation,
                    AfternoonMRStopDistancePoints = _config.AfternoonMRStopDistancePoints,
                    AfternoonMRTargetVWAPFraction = _config.AfternoonMRTargetVWAPFraction,
                    AfternoonMRMaxATR = _config.AfternoonMRMaxATR,
                    AfternoonMREnableBreakEven = _config.AfternoonMREnableBreakEven,
                    AfternoonMRBETriggerR = _config.AfternoonMRBETriggerR,
                    AfternoonMRMaxDailyTrades = _config.AfternoonMRMaxDailyTrades,
                    AfternoonMRTimeExitHourCT = _config.AfternoonMRTimeExitHourCT,
                    AfternoonMRTimeExitMinuteCT = _config.AfternoonMRTimeExitMinuteCT,
                    AfternoonMRQuantity = _config.AfternoonMRQuantity,
                    // PHASE 17: CloseCont
                    EnableCloseContModule = _config.EnableCloseContModule,
                    CloseContStartHourCT = _config.CloseContStartHourCT,
                    CloseContStartMinuteCT = _config.CloseContStartMinuteCT,
                    CloseContEndHourCT = _config.CloseContEndHourCT,
                    CloseContEndMinuteCT = _config.CloseContEndMinuteCT,
                    CloseContHardExitHourCT = _config.CloseContHardExitHourCT,
                    CloseContHardExitMinuteCT = _config.CloseContHardExitMinuteCT,
                    CloseContMinSetupMagnitude = _config.CloseContMinSetupMagnitude,
                    CloseContStopDistancePoints = _config.CloseContStopDistancePoints,
                    CloseContTargetDistancePoints = _config.CloseContTargetDistancePoints,
                    CloseContMaxATR = _config.CloseContMaxATR,
                    CloseContEnableBreakEven = _config.CloseContEnableBreakEven,
                    CloseContBETriggerR = _config.CloseContBETriggerR,
                    CloseContMaxDailyTrades = _config.CloseContMaxDailyTrades,
                    CloseContQuantity = _config.CloseContQuantity,
                    // PHASE 14: Dynamic sizer
                    EnableDynamicSizer = _config.EnableDynamicSizer,
                    DynamicSizerInitialMultiplier = _config.DynamicSizerInitialMultiplier,
                    DynamicSizerFullMultiplier = _config.DynamicSizerFullMultiplier,
                    DynamicSizerBufferThreshold = _config.DynamicSizerBufferThreshold,
                    DebugDisableSessionGate = _config.DebugDisableSessionGate,
                    DebugDisableVolatilityGate = _config.DebugDisableVolatilityGate,
                    DebugDisableRiskGate = _config.DebugDisableRiskGate,
                    DebugForceRangeEnabled = _config.DebugForceRangeEnabled,
                    DebugDisableMomentumGates = _config.DebugDisableMomentumGates,
                    DebugDisableMomentumSessionGate = _config.DebugDisableMomentumSessionGate
                };
                // PHASE 13: Parse blocked hours string into HashSet
                config.MomentumBlockedHoursSet = new System.Collections.Generic.HashSet<int>();
                if (!string.IsNullOrWhiteSpace(config.MomentumBlockedHoursET))
                {
                    foreach (var part in config.MomentumBlockedHoursET.Split(','))
                    {
                        if (int.TryParse(part.Trim(), out int hour) && hour >= 0 && hour <= 23)
                        {
                            config.MomentumBlockedHoursSet.Add(hour);
                        }
                    }
                }

                // PHASE 13.1: Parse Range blocked hours (CT) string into HashSet
                config.RangeBlockedHoursSet = new System.Collections.Generic.HashSet<int>();
                if (!string.IsNullOrWhiteSpace(config.RangeBlockedHoursCT))
                {
                    foreach (var part in config.RangeBlockedHoursCT.Split(','))
                    {
                        if (int.TryParse(part.Trim(), out int hour) && hour >= 0 && hour <= 23)
                        {
                            config.RangeBlockedHoursSet.Add(hour);
                        }
                    }
                }

                return config;
            }
        }
    }
}