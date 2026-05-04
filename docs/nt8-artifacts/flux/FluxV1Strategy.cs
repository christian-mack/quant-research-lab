#region Using declarations
using System;
using System.ComponentModel.DataAnnotations;
using System.IO;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Strategies;
using NinjaTrader.NinjaScript.Indicators;
using NinjaTrader.NinjaScript.Strategies.Flux.Core;
using NinjaTrader.NinjaScript.Strategies.Flux.Modules.Range;
using NinjaTrader.NinjaScript.Strategies.Flux.Modules.Momentum;
using NinjaTrader.NinjaScript.Strategies.Flux.Modules.ORB;
using NinjaTrader.NinjaScript.Strategies.Flux.Modules.AfternoonMR;
using NinjaTrader.NinjaScript.Strategies.Flux.Modules.CloseCont;
#endregion

namespace NinjaTrader.NinjaScript.Strategies.Flux
{
    /// <summary>
    /// Flux v1 Strategy - Single NT8 Strategy that orchestrates trading modules.
    /// 
    /// Flux v1 is NOT a standalone alpha strategy - it is a routing and risk system
    /// that turns validated regime modules into a coordinated system.
    /// 
    /// Key properties:
    /// - One module active at a time (v1 constraint)
    /// - One position at a time (v1 constraint)
    /// - Centralized risk management (prop-firm safe)
    /// - Modules emit TradeIntents; Flux executes
    /// - Deterministic Strategy Analyzer behavior
    /// - Fail-closed philosophy
    /// </summary>
    public class FluxV1Strategy : Strategy
    {
        #region Strategy Parameters

        // Logging
        [NinjaScriptProperty]
        [Display(Name = "Enable Logging", Order = 1, GroupName = "Logging")]
        public bool EnableLogging { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Log Level (0=Error, 3=Debug)", Order = 2, GroupName = "Logging")]
        [Range(0, 4)]
        public int LogLevelValue { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Enable File Audit Logging", Description = "Save [FLUX] logs to file for parity analysis", Order = 3, GroupName = "Logging")]
        public bool EnableFileAuditLogging { get; set; }

        // Risk Limits
        [NinjaScriptProperty]
        [Display(Name = "Max Daily Loss ($)", Order = 10, GroupName = "Risk")]
        public double MaxDailyLoss { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Max Trailing Drawdown ($)", Order = 11, GroupName = "Risk")]
        public double MaxTrailingDrawdown { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Max Trades Per Day", Order = 12, GroupName = "Risk")]
        [Range(1, 50)]
        public int MaxTradesPerDay { get; set; }


        // Session
        [NinjaScriptProperty]
        [Display(Name = "RTH Only", Order = 30, GroupName = "Session")]
        public bool RTHOnly { get; set; }

        // Modules
        [NinjaScriptProperty]
        [Display(Name = "Enable Range Module", Order = 40, GroupName = "Modules")]
        public bool EnableRangeModule { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Enable Momentum Module", Order = 41, GroupName = "Modules")]
        public bool EnableMomentumModule { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Enable ORB Module", Order = 43, GroupName = "Modules")]
        public bool EnableORBModule { get; set; }

        // Per-Module Position Sizing
        [NinjaScriptProperty]
        [Display(Name = "Momentum Quantity", Order = 44, GroupName = "Modules", Description = "Number of contracts for Momentum trades. Default: 1.")]
        [Range(0, 100)]
        public int MomentumQuantity { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ORB Quantity", Order = 45, GroupName = "Modules", Description = "Number of contracts for ORB trades. Default: 1.")]
        [Range(1, 100)]
        public int ORBQuantity { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Range Quantity", Order = 46, GroupName = "Modules", Description = "Number of contracts for Range trades. Default: 1.")]
        [Range(1, 100)]
        public int RangeQuantity { get; set; }

        // Volatility
        [NinjaScriptProperty]
        [Display(Name = "Enable Volatility Gate", Order = 50, GroupName = "Volatility")]
        public bool EnableVolatilityGate { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Vol High Percentile", Order = 51, GroupName = "Volatility")]
        [Range(0.5, 0.95)]
        public double VolHighPercentile { get; set; }

        // Momentum Module Configuration (Phase 12.10: Parity Mode)
        [NinjaScriptProperty]
        [Display(Name = "Parity Mode", Order = 59, GroupName = "Momentum", Description = "Enable exact parity with standalone MomentumRegime. Default: true.")]
        public bool MomentumParityMode { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Enable VWAP Filter", Order = 60, GroupName = "Momentum", Description = "Enable VWAP filtering for Momentum module. Default: false (disabled to match standalone behavior).")]
        public bool MomentumEnableVWAPFilter { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "VWAP Deviation (Price)", Order = 61, GroupName = "Momentum", Description = "VWAP deviation in price units (matching standalone VWAPDeviation). Only used when VWAP filter is enabled.")]
        [Range(0.0, double.MaxValue)]
        public double MomentumVWAPDeviation { get; set; }

        // PHASE 12.10: Stop and Break-Even parity parameters
        [NinjaScriptProperty]
        [Display(Name = "Fixed Stop Distance", Order = 62, GroupName = "Momentum", Description = "Fixed stop distance in POINTS (matches standalone TrailingDistance=80). Only used when Parity Mode is enabled.")]
        [Range(1.0, 500.0)]
        public double MomentumFixedStopDistance { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Enable Auto Break-Even", Order = 63, GroupName = "Momentum", Description = "Enable auto break-even (matches standalone EnableAutoBE=true). Default: true.")]
        public bool MomentumEnableAutoBreakEven { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Break-Even Trigger (R)", Order = 64, GroupName = "Momentum", Description = "Break-even trigger in R-multiples (matches standalone BETriggerR=1.5). Default: 1.5.")]
        [Range(0.1, 10.0)]
        public double MomentumBETriggerR { get; set; }

        // PHASE 13: Momentum Optimization Filters
        [NinjaScriptProperty]
        [Display(Name = "Daily Profit Cap ($)", Order = 70, GroupName = "Momentum", Description = "Stop Momentum entries after this daily realized profit. 0 = disabled. Default: 200.")]
        [Range(0.0, 10000.0)]
        public double MomentumDailyProfitCap { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Blocked Hours (ET)", Order = 71, GroupName = "Momentum", Description = "Comma-separated hours to block entries (24h ET). e.g. '9,13,14' blocks 9AM,1PM,2PM ET (=8AM,12PM,1PM CT). Empty = none.")]
        public string MomentumBlockedHoursET { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Max ATR Ceiling", Order = 72, GroupName = "Momentum", Description = "Reject Momentum entries when ATR exceeds this value. 0 = disabled. Default: 30.")]
        [Range(0.0, 200.0)]
        public double MomentumMaxATR { get; set; }

        // PHASE 19: Secondary 15-minute ATR ceiling
        [NinjaScriptProperty]
        [Display(Name = "Max ATR15m Ceiling", Order = 75, GroupName = "Momentum",
            Description = "Reject Momentum entries when ATR(14) on 15-min bars exceeds this value. 0 = disabled. Default: 40.")]
        [Range(0.0, 500.0)]
        public double MomentumMaxATR15m { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Max Daily Trades", Order = 73, GroupName = "Momentum", Description = "Max Momentum trades per day. Trade #4+ is negative EV. 0 = unlimited. Default: 3.")]
        [Range(0, 20)]
        public int MomentumMaxDailyTrades { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Hard Exit Hour (CT)", Order = 74, GroupName = "Momentum",
            Description = "Force-exit Momentum positions at this hour (CT, 24h). Frees slot for AMR. 0 = disabled. Default: 0")]
        [Range(0, 16)]
        public int MomentumHardExitHourCT { get; set; }

        // ORB Module Configuration (Locked from optimization)
        [NinjaScriptProperty]
        [Display(Name = "ORB Target Multiplier", Order = 70, GroupName = "ORB", Description = "Target as multiplier of range size. Locked: 0.8")]
        [Range(0.1, 5.0)]
        public double ORBTargetMultiplier { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ORB Max Stop Points", Order = 71, GroupName = "ORB", Description = "Max stop distance in points. Locked: 80")]
        [Range(10.0, 200.0)]
        public double ORBMaxStopPoints { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ORB Enable VWAP Filter", Order = 72, GroupName = "ORB", Description = "Require VWAP alignment for breakout. Default: true")]
        public bool ORBEnableVWAPFilter { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ORB Enable Break-Even", Order = 73, GroupName = "ORB", Description = "Enable auto break-even for ORB trades. Default: true")]
        public bool ORBEnableBreakEven { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ORB BE Trigger (R)", Order = 74, GroupName = "ORB", Description = "Break-even trigger in R-multiples. Default: 1.0")]
        [Range(0.1, 10.0)]
        public double ORBBETriggerR { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ORB Earliest Entry Hour (ET)", Order = 75, GroupName = "ORB", Description = "Earliest hour (ET, 24h) for ORB entries. 10 = 9AM CT. 0 = no restriction. Default: 10.")]
        [Range(0, 23)]
        public int ORBEarliestEntryHourET { get; set; }

        // PHASE 5: ORB Optimization Knobs (orb-optimization-spec.md)
        [NinjaScriptProperty]
        [Display(Name = "ORB Latest Entry Hour (ET)", Order = 76, GroupName = "ORB",
            Description = "Latest hour (ET, 24h) for ORB entries. Entries at/after this hour are rejected. 0 = disabled. Default: 0.")]
        [Range(0, 23)]
        public int ORBLatestEntryHourET { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ORB Max ATR15m Ceiling", Order = 77, GroupName = "ORB",
            Description = "Reject ORB entries when 15-min ATR(14) exceeds this value. 0 = disabled. Default: 0.")]
        [Range(0.0, 500.0)]
        public double ORBMaxATR15m { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ORB Use ATR Range Filter", Order = 78, GroupName = "ORB",
            Description = "Use ATR-scaled range bounds instead of fixed points. Default: false.")]
        public bool ORBUseATRRangeFilter { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ORB Min Range (xATR15m)", Order = 79, GroupName = "ORB",
            Description = "Minimum opening range as a multiple of 15m ATR(14). Only used when ATR Range Filter is on. Default: 0.25.")]
        [Range(0.0, 10.0)]
        public double ORBMinRangeATR { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ORB Max Range (xATR15m)", Order = 80, GroupName = "ORB",
            Description = "Maximum opening range as a multiple of 15m ATR(14). Only used when ATR Range Filter is on. Default: 2.5.")]
        [Range(0.0, 20.0)]
        public double ORBMaxRangeATR { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ORB Use ATR Stop Cap", Order = 81, GroupName = "ORB",
            Description = "Use ATR-scaled max-stop cap (in addition to fixed cap). Default: false.")]
        public bool ORBUseATRStop { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ORB Max Stop (xATR15m)", Order = 82, GroupName = "ORB",
            Description = "Max stop distance as a multiple of 15m ATR(14). Only used when ATR Stop Cap is on. Default: 1.5.")]
        [Range(0.1, 10.0)]
        public double ORBMaxStopATR { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ORB Max Hold Minutes", Order = 83, GroupName = "ORB",
            Description = "Force-exit ORB positions held this many minutes. 0 = disabled. Default: 0.")]
        [Range(0, 1440)]
        public int ORBMaxHoldMinutes { get; set; }

        // Range Module Configuration
        [NinjaScriptProperty]
        [Display(Name = "Range Trail Ratchet Enabled", Order = 80, GroupName = "Range", Description = "Enable ratcheting trail multiplier. Default: true")]
        public bool RangeTrailRatchetEnabled { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Trail Multiplier Initial", Order = 81, GroupName = "Range", Description = "Trail multiplier Phase 1 (0 to 1R). Default: 0.45")]
        [Range(0.05, 1.0)]
        public double RangeTrailMultiplierInitial { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Trail Multiplier Mid", Order = 82, GroupName = "Range", Description = "Trail multiplier Phase 2 (1R to 2R). Default: 0.35")]
        [Range(0.05, 1.0)]
        public double RangeTrailMultiplierMid { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Trail Multiplier Tight", Order = 83, GroupName = "Range", Description = "Trail multiplier Phase 3 (2R+). Default: 0.25")]
        [Range(0.05, 1.0)]
        public double RangeTrailMultiplierTight { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Ratchet Threshold 1R", Order = 84, GroupName = "Range", Description = "Profit/R to enter Phase 2. Default: 1.0")]
        [Range(0.1, 5.0)]
        public double RangeTrailRatchetThreshold1R { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Ratchet Threshold 2R", Order = 85, GroupName = "Range", Description = "Profit/R to enter Phase 3. Default: 2.0")]
        [Range(0.5, 10.0)]
        public double RangeTrailRatchetThreshold2R { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Range Blocked Hours (CT)", Order = 86, GroupName = "Range", Description = "Comma-separated hours to block Range entries (24h CT). e.g. '7,20,22'. Empty = none.")]
        public string RangeBlockedHoursCT { get; set; }

        // PHASE 15: AfternoonMR Module Configuration
        [NinjaScriptProperty]
        [Display(Name = "Enable AfternoonMR Module", Order = 50, GroupName = "AfternoonMR",
            Description = "Enable Afternoon Mean Reversion module (12-15 CT VWAP fade). Default: false")]
        public bool EnableAfternoonMRModule { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Start Hour (CT)", Order = 51, GroupName = "AfternoonMR",
            Description = "Earliest hour to take entries (CT, 24h). Default: 13")]
        [Range(10, 15)]
        public int AfternoonMRStartHour { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "End Hour (CT)", Order = 52, GroupName = "AfternoonMR",
            Description = "Stop taking entries at this hour (CT, 24h). Default: 15")]
        [Range(13, 16)]
        public int AfternoonMREndHour { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Min VWAP Deviation (pts)", Order = 53, GroupName = "AfternoonMR",
            Description = "Minimum points from VWAP to trigger. Default: 15.0")]
        [Range(5.0, 50.0)]
        public double AfternoonMRMinVWAPDev { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Max VWAP Deviation (pts)", Order = 54, GroupName = "AfternoonMR",
            Description = "Maximum points from VWAP (beyond = breakout). Default: 60.0")]
        [Range(20.0, 150.0)]
        public double AfternoonMRMaxVWAPDev { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Stop Distance (pts)", Order = 55, GroupName = "AfternoonMR",
            Description = "Fixed stop loss distance in NQ points. Default: 25.0")]
        [Range(5.0, 80.0)]
        public double AfternoonMRStopDistance { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Target VWAP Fraction", Order = 56, GroupName = "AfternoonMR",
            Description = "Target as fraction of VWAP distance (0.5=halfway). Default: 0.5")]
        [Range(0.1, 1.5)]
        public double AfternoonMRTargetFraction { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Max ATR", Order = 57, GroupName = "AfternoonMR",
            Description = "ATR ceiling filter (0=disabled). Default: 35.0")]
        [Range(0.0, 100.0)]
        public double AfternoonMRMaxATR { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Max Daily Trades", Order = 58, GroupName = "AfternoonMR",
            Description = "Maximum afternoon trades per day. Default: 3")]
        [Range(1, 10)]
        public int AfternoonMRMaxDailyTrades { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Enable Break-Even", Order = 59, GroupName = "AfternoonMR",
            Description = "Enable auto break-even. Default: true")]
        public bool AfternoonMREnableBE { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "BE Trigger (R)", Order = 60, GroupName = "AfternoonMR",
            Description = "Break-even trigger in R-multiples. Default: 1.0")]
        [Range(0.1, 5.0)]
        public double AfternoonMRBETriggerR { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "AfternoonMR Quantity", Order = 61, GroupName = "AfternoonMR",
            Description = "Contracts per AfternoonMR trade. Default: 1")]
        [Range(1, 100)]
        public int AfternoonMRQuantity { get; set; }

        // PHASE 17: CloseCont Module Configuration
        [NinjaScriptProperty]
        [Display(Name = "Enable CloseCont Module", Order = 70, GroupName = "CloseCont",
            Description = "Enable Close Continuation module (14-15 CT MOC flow). Default: false")]
        public bool EnableCloseContModule { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "CC Stop Distance (pts)", Order = 71, GroupName = "CloseCont",
            Description = "Fixed stop distance in points. Default: 25.0")]
        [Range(5.0, 80.0)]
        public double CloseContStopDistance { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "CC Target Distance (pts)", Order = 72, GroupName = "CloseCont",
            Description = "Fixed target distance in points. Default: 25.0")]
        [Range(5.0, 80.0)]
        public double CloseContTargetDistance { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "CC Min Setup Magnitude (pts)", Order = 73, GroupName = "CloseCont",
            Description = "Minimum directional move to confirm setup. Default: 5.0")]
        [Range(1.0, 50.0)]
        public double CloseContMinSetupMag { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "CC Max ATR", Order = 74, GroupName = "CloseCont",
            Description = "ATR ceiling filter (0=disabled). Default: 35.0")]
        [Range(0.0, 100.0)]
        public double CloseContMaxATR { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "CC Quantity", Order = 75, GroupName = "CloseCont",
            Description = "Contracts per CloseCont trade. Default: 1")]
        [Range(1, 100)]
        public int CloseContQuantity { get; set; }

        // PHASE 14: Two-Tier Dynamic Sizing
        [NinjaScriptProperty]
        [Display(Name = "Enable Dynamic Sizer", Order = 10, GroupName = "Dynamic Sizing",
            Description = "Two-tier position sizing: conservative until buffer, then scaled up. Default: false")]
        public bool EnableDynamicSizer { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Initial Multiplier", Order = 20, GroupName = "Dynamic Sizing",
            Description = "Qty multiplier during Initial phase (building buffer). Default: 0.5")]
        [Range(0.1, 2.0)]
        public double DynamicSizerInitialMultiplier { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Full Multiplier", Order = 30, GroupName = "Dynamic Sizing",
            Description = "Qty multiplier during Full phase (buffer established). Default: 1.25")]
        [Range(0.5, 3.0)]
        public double DynamicSizerFullMultiplier { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Buffer Threshold ($)", Order = 40, GroupName = "Dynamic Sizing",
            Description = "Cumulative realized profit to trigger Full phase. Default: 1000")]
        [Range(100.0, 10000.0)]
        public double DynamicSizerBufferThreshold { get; set; }

        #endregion

        #region Internal Components

        // Core components
        private Config _config;
        private Logger _logger;
        private ContextBuilder _contextBuilder;
        private RegimeGate _regimeGate;
        private ModuleRouter _moduleRouter;
        private RiskManager _riskManager;
        private ExecutionEngine _executionEngine;
        private DynamicSizer _dynamicSizer;  // PHASE 14: null when disabled

        // Indicators
        private ATR _atr;
        private EMA _ema9;
        private EMA _ema21;
        private EMA _ema200;

        // PHASE 19: ATR(14) on 15-min secondary series for Momentum regime gate
        private ATR _atr15m;

        // Price data arrays for modules
        private double[] _highs;
        private double[] _lows;
        private double[] _opens;
        private double[] _closes;
        private double[] _atrValues;
        private double[] _ema9Values;
        private double[] _ema21Values;
        private double[] _ema200Values;
        private double[] _volumes;  // PHASE 12.10: Real volume for Momentum VWAP

        // State tracking
        private DateTime _lastSessionDate;
        private bool _initialized = false;
        private int _lastProcessedBar = -1;

        // Diagnostic counters (PHASE 6: Trade Count Diagnostics)
        private long _barsTotal;
        private long _barsRiskBlocked;
        private long _barsSessionBlocked;
        private long _barsVolatilityBlocked;
        private long _barsRouterNoEligible;
        private long _barsRangeEvaluated;
        private long _barsRangeReturnedNone;
        private long _barsIntentSubmitted;
        private long _tradesOpened;
        private long _tradesClosed;

        #endregion

        #region Strategy Lifecycle

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Flux v1 Strategy - Module-based Trading System";
                Name = "FluxV1";
                Calculate = Calculate.OnBarClose;
                EntriesPerDirection = 1;
                EntryHandling = EntryHandling.AllEntries;
                IsExitOnSessionCloseStrategy = false;
                ExitOnSessionCloseSeconds = 30;
                IsFillLimitOnTouch = false;
                MaximumBarsLookBack = MaximumBarsLookBack.TwoHundredFiftySix;
                OrderFillResolution = OrderFillResolution.Standard;
                Slippage = 0;
                StartBehavior = StartBehavior.WaitUntilFlat;
                TimeInForce = TimeInForce.Gtc;
                RealtimeErrorHandling = RealtimeErrorHandling.StopCancelClose;
                // PHASE 12.11a: Changed from PerEntryExecution to ByStrategyPosition
                // PerEntryExecution creates separate stops/targets per execution fill,
                // causing quantity-dependent behavior (partial fills = multiple exit orders).
                // ByStrategyPosition ensures one stop + one target per strategy position,
                // guaranteeing quantity invariance.
                StopTargetHandling = StopTargetHandling.ByStrategyPosition;
                BarsRequiredToTrade = 50;

                // Default parameters
                EnableLogging = true;
                LogLevelValue = 2; // Info
                MaxDailyLoss = 500;
                MaxTrailingDrawdown = 1000;
                MaxTradesPerDay = 10;
                RTHOnly = false;  // PHASE 12.5: Disable RTH filtering - Momentum handles its own session logic
                EnableRangeModule = true;
                EnableMomentumModule = true;
                EnableORBModule = true;
                MomentumQuantity = 1;
                ORBQuantity = 1;
                RangeQuantity = 1;
                EnableVolatilityGate = true;
                VolHighPercentile = 0.7;
                
                // Phase 12.10: Momentum parity mode defaults (match standalone exactly)
                MomentumParityMode = true;
                MomentumEnableVWAPFilter = false;
                MomentumVWAPDeviation = 0.0;
                MomentumFixedStopDistance = 80.0;      // Reverted from Phase 16 experiment (55)
                MomentumEnableAutoBreakEven = true;    // From standalone: EnableAutoBE = true
                MomentumBETriggerR = 1.5;              // From standalone: BETriggerR = 1.5
                
                // PHASE 13: Momentum optimization filters
                MomentumDailyProfitCap = 0;            // Disabled (data showed $200 cap hurts)
                MomentumMaxDailyTrades = 3;            // PHASE 13.1: Max 3/day (trade #4+ is -EV)
                MomentumHardExitHourCT = 0;            // Disabled (0 = no forced exit)
                MomentumBlockedHoursET = "9,13,14";    // Block 9AM, 1PM, 2PM ET (= 8AM, 12PM, 1PM CT)
                MomentumMaxATR = 30.0;                 // ATR ceiling (0 = disabled)
                MomentumMaxATR15m = 40.0;              // PHASE 19: 15-min ATR ceiling (0 = disabled)
                // ORB module defaults (locked from optimization)
                ORBTargetMultiplier = 0.8;             // Locked: best PF, edge, lowest DD
                ORBMaxStopPoints = 80.0;               // Locked: 80-point max stop
                ORBEnableVWAPFilter = true;
                ORBEnableBreakEven = true;
                ORBBETriggerR = 1.0;                   // Reverted from Phase 16 experiment (0.75)
                ORBEarliestEntryHourET = 10;           // PHASE 13.1: 10 ET = 9 CT

                // PHASE 5: ORB optimization knobs (defaults preserve baseline)
                ORBLatestEntryHourET = 0;               // 0 = disabled
                ORBMaxATR15m = 0;                        // 0 = disabled
                ORBUseATRRangeFilter = false;
                ORBMinRangeATR = 0.25;
                ORBMaxRangeATR = 2.5;
                ORBUseATRStop = false;
                ORBMaxStopATR = 1.5;
                ORBMaxHoldMinutes = 0;                   // 0 = disabled
                RangeTrailRatchetEnabled = true;
                RangeTrailMultiplierInitial = 0.50;
                RangeTrailMultiplierMid = 0.40;
                RangeTrailMultiplierTight = 0.30;
                RangeTrailRatchetThreshold1R = 1.0;
                RangeTrailRatchetThreshold2R = 2.0;
                RangeBlockedHoursCT = "7,20,22";       // PHASE 13.1: Block losing hours (CT)

                // PHASE 15: AfternoonMR defaults (disabled by default)
                EnableAfternoonMRModule = false;
                AfternoonMRStartHour = 13;     // Config A optimization: was 12, now 13
                AfternoonMREndHour = 15;
                AfternoonMRMinVWAPDev = 15.0;
                AfternoonMRMaxVWAPDev = 60.0;
                AfternoonMRStopDistance = 20.0; // Config A optimization: was 25, now 20
                AfternoonMRTargetFraction = 0.5;
                AfternoonMRMaxATR = 35.0;
                AfternoonMRMaxDailyTrades = 3;
                AfternoonMREnableBE = true;
                AfternoonMRBETriggerR = 1.0;
                AfternoonMRQuantity = 1;

                // PHASE 17: CloseCont defaults (disabled by default)
                EnableCloseContModule = false;
                CloseContStopDistance = 25.0;
                CloseContTargetDistance = 25.0;
                CloseContMinSetupMag = 5.0;
                CloseContMaxATR = 35.0;
                CloseContQuantity = 1;

                // PHASE 14: Two-tier dynamic sizer (disabled by default)
                EnableDynamicSizer = false;
                DynamicSizerInitialMultiplier = 0.5;
                DynamicSizerFullMultiplier = 1.25;
                DynamicSizerBufferThreshold = 1000.0;
            }
            else if (State == State.Configure)
            {
                // PHASE 19: Add 15-minute secondary series for Momentum regime ATR gate.
                // BarsArray[1] -> 15-min bars; primary 1-min series remains BarsArray[0].
                AddDataSeries(BarsPeriodType.Minute, 15);
            }
            else if (State == State.DataLoaded)
            {
                // Initialize configuration (immutable after this point)
                // Quantity is handled by Order Properties panel - use default value for config
                _config = new Config.Builder()
                    .WithLogging(EnableLogging, (Core.LogLevel)LogLevelValue)
                    .WithFileAuditLogging(EnableFileAuditLogging)
                    .WithRiskLimits(MaxDailyLoss, MaxTrailingDrawdown, MaxTradesPerDay)
                    .WithDefaultQuantity(1)  // Default value - Order Properties panel will override
                    .WithMomentumQuantity(MomentumQuantity)
                    .WithORBQuantity(ORBQuantity)
                    .WithRangeQuantity(RangeQuantity)
                    .WithRTHOnly(RTHOnly)
                    .WithVolatilityGate(EnableVolatilityGate, VolHighPercentile, 0.3)
                    .WithMomentumParityMode(MomentumParityMode)
                    .WithMomentumVWAP(MomentumEnableVWAPFilter, MomentumVWAPDeviation)
                    .WithMomentumFixedStopDistance(MomentumFixedStopDistance)
                    .WithMomentumAutoBreakEven(MomentumEnableAutoBreakEven, MomentumBETriggerR)
                    .WithMomentumDailyProfitCap(MomentumDailyProfitCap)
                    .WithMomentumBlockedHours(MomentumBlockedHoursET)
                    .WithMomentumMaxATR(MomentumMaxATR)
                    .WithMomentumMaxATR15m(MomentumMaxATR15m)
                    .WithMomentumMaxDailyTrades(MomentumMaxDailyTrades)
                    .WithMomentumHardExitHour(MomentumHardExitHourCT)
                    .WithORBModule(EnableORBModule)
                    .WithORBParameters(10.0, 80.0, ORBMaxStopPoints, 2.0, ORBTargetMultiplier, 2.0)
                    .WithORBVWAPFilter(ORBEnableVWAPFilter)
                    .WithORBBreakEven(ORBEnableBreakEven, ORBBETriggerR)
                    .WithORBEarliestEntryHour(ORBEarliestEntryHourET)
                    // PHASE 5: ORB optimization knobs
                    .WithORBLatestEntryHour(ORBLatestEntryHourET)
                    .WithORBMaxATR15m(ORBMaxATR15m)
                    .WithORBATRRangeFilter(ORBUseATRRangeFilter, ORBMinRangeATR, ORBMaxRangeATR)
                    .WithORBATRStop(ORBUseATRStop, ORBMaxStopATR)
                    .WithORBMaxHoldMinutes(ORBMaxHoldMinutes)
                    .WithRangeBlockedHours(RangeBlockedHoursCT)
                    .WithRangeTrailRatchet(RangeTrailRatchetEnabled, RangeTrailMultiplierInitial,
                        RangeTrailMultiplierMid, RangeTrailMultiplierTight,
                        RangeTrailRatchetThreshold1R, RangeTrailRatchetThreshold2R)
                    .WithAfternoonMRModule(EnableAfternoonMRModule)
                    .WithAfternoonMRParameters(AfternoonMRStartHour, AfternoonMREndHour,
                        AfternoonMRMinVWAPDev, AfternoonMRMaxVWAPDev,
                        AfternoonMRStopDistance, AfternoonMRTargetFraction,
                        AfternoonMRMaxATR, AfternoonMRMaxDailyTrades)
                    .WithAfternoonMRBreakEven(AfternoonMREnableBE, AfternoonMRBETriggerR)
                    .WithAfternoonMRTimeExit(15, 15)
                    .WithAfternoonMRQuantity(AfternoonMRQuantity)
                    .WithCloseContModule(EnableCloseContModule)
                    .WithCloseContParameters(14, 0, 15, 0, CloseContMinSetupMag,
                        CloseContStopDistance, CloseContTargetDistance, CloseContMaxATR, 1)
                    .WithCloseContQuantity(CloseContQuantity)
                    .WithDynamicSizerSettings(EnableDynamicSizer,
                        DynamicSizerInitialMultiplier, DynamicSizerFullMultiplier,
                        DynamicSizerBufferThreshold)
                    .Build();

                // PHASE 12.3: Temporarily disable Momentum gating for semantic parity verification
                _config = new Config.Builder(_config)
                    .WithDebugDisableMomentumGates(true)
                    // PHASE 12.5: Session gate re-enabled after validation - should now work correctly
                    .WithDebugDisableMomentumSessionGate(false)
                    .Build();

                // Initialize indicators
                _atr = ATR(14);
                _ema9 = EMA(9);
                _ema21 = EMA(21);
                _ema200 = EMA(200);

                // PHASE 19: ATR(14) bound to the 15-minute secondary series (BarsArray[1]).
                // Powers the regime-volatility ceiling gate inside MomentumModule.
                _atr15m = ATR(BarsArray[1], 14);

                // Initialize core components
                _logger = new Logger(this, _config);
                _contextBuilder = new ContextBuilder(this, _config, _atr);
                _regimeGate = new RegimeGate(_config, _logger);
                _moduleRouter = new ModuleRouter(_config, _logger, _regimeGate);
                _riskManager = new RiskManager(_config, _logger);
                _executionEngine = new ExecutionEngine(this, _config, _logger);

                // PHASE 14: Initialize dynamic sizer if enabled
                if (_config.EnableDynamicSizer)
                {
                    _dynamicSizer = new DynamicSizer(_config, _logger);
                    _executionEngine.SetDynamicSizer(_dynamicSizer);
                }

                // Register modules
                if (EnableRangeModule)
                {
                    var rangeModule = new RangeModule(_config, _logger);
                    _moduleRouter.RegisterModule(rangeModule);

                    // PHASE 6: Log RangeModule settings verification
                    _logger.LogDebug("RANGE_SETTINGS: " +
                        $"atrPeriod={_config.ATRPeriod}, " +
                        $"compressionLookback={_config.RangeCompressionLookback}, " +
                        $"compressionPercentile={_config.RangeCompressionPercentile:F2}, " +
                        $"rangeLookback={_config.RangeLookback}, " +
                        $"stopMultiplier={_config.RangeStopMultiplier:F2}, " +
                        $"targetMultiplier={_config.RangeTargetMultiplier:F2}, " +
                        $"trailingActivation={_config.RangeTrailingActivation:F2}, " +
                        $"trailingDistance={_config.RangeTrailingDistance:F2}, " +
                        $"barsRequired={BarsRequiredToTrade}");
                }

                if (EnableMomentumModule)
                {
                    var momentumModule = new MomentumModule(_config, _logger);
                    _moduleRouter.RegisterModule(momentumModule);

                    // PHASE 12.1: Log MomentumModule settings verification
                    _logger.LogDebug("MOMENTUM_SETTINGS: " +
                        $"wprPeriod={14}, " +
                        $"overbought={-20}, " +
                        $"oversold={-80}, " +
                        $"emaPeriod={200}, " +
                        $"atrPeriod={14}, " +
                        $"stopLossAtrMultiplier={2.0:F1}, " +
                        $"profitTargetAtrMultiplier={3.0:F1}, " +
                        $"powerHourBlock=14:00-15:00, " +
                        $"lossStreakCooldown=3losses/60min, " +
                        $"barsRequired={BarsRequiredToTrade}");
                }

                if (EnableORBModule)
                {
                    var orbModule = new ORBModule(_config, _logger);
                    _moduleRouter.RegisterModule(orbModule);

                    // Log ORBModule settings verification
                    _logger.LogDebug("ORB_SETTINGS: " +
                        $"minRangePoints={_config.ORBMinRangePoints:F1}, " +
                        $"maxRangePoints={_config.ORBMaxRangePoints:F1}, " +
                        $"maxStopPoints={_config.ORBMaxStopPoints:F1}, " +
                        $"stopBuffer={_config.ORBStopBuffer:F1}, " +
                        $"targetMultiplier={_config.ORBTargetMultiplier:F2}, " +
                        $"enableVWAP={_config.ORBEnableVWAPFilter}, " +
                        $"enableBE={_config.ORBEnableBreakEven}, " +
                        $"beTriggerR={_config.ORBBETriggerR:F1}, " +
                        $"breakoutBuffer={_config.ORBBreakoutBuffer:F1}, " +
                        $"barsRequired={BarsRequiredToTrade}");
                }

                // PHASE 15: AfternoonMR module
                if (EnableAfternoonMRModule)
                {
                    var afternoonMRModule = new AfternoonMRModule(_config, _logger);
                    _moduleRouter.RegisterModule(afternoonMRModule);

                    _logger.LogDebug("AFTERNOON_MR_SETTINGS: " +
                        $"startHourCT={_config.AfternoonMRStartHourCT}, " +
                        $"endHourCT={_config.AfternoonMREndHourCT}, " +
                        $"minVWAPDev={_config.AfternoonMRMinVWAPDeviation:F1}, " +
                        $"maxVWAPDev={_config.AfternoonMRMaxVWAPDeviation:F1}, " +
                        $"stopDist={_config.AfternoonMRStopDistancePoints:F1}, " +
                        $"targetFrac={_config.AfternoonMRTargetVWAPFraction:F2}, " +
                        $"maxATR={_config.AfternoonMRMaxATR:F1}, " +
                        $"maxDailyTrades={_config.AfternoonMRMaxDailyTrades}");
                }

                // PHASE 17: CloseCont module
                if (EnableCloseContModule)
                {
                    var closeContModule = new CloseContModule(_config, _logger);
                    _moduleRouter.RegisterModule(closeContModule);

                    _logger.LogDebug("CLOSE_CONT_SETTINGS: " +
                        $"startCT={_config.CloseContStartHourCT}:{_config.CloseContStartMinuteCT:D2}, " +
                        $"endCT={_config.CloseContEndHourCT}:{_config.CloseContEndMinuteCT:D2}, " +
                        $"minSetup={_config.CloseContMinSetupMagnitude:F1}, " +
                        $"stop={_config.CloseContStopDistancePoints:F1}, " +
                        $"target={_config.CloseContTargetDistancePoints:F1}, " +
                        $"maxATR={_config.CloseContMaxATR:F1}");
                }

                // Allocate price data arrays
                int lookback = 50;
                _highs = new double[lookback];
                _lows = new double[lookback];
                _opens = new double[lookback];
                _closes = new double[lookback];
                _atrValues = new double[lookback];
                _ema9Values = new double[lookback];
                _ema21Values = new double[lookback];
                _ema200Values = new double[lookback];
                _volumes = new double[lookback];  // PHASE 12.10: Real volume

                // Initialize diagnostic counters
                ResetDiagnosticCounters();

                _logger.LogInit("Flux v1 initialized successfully");
                _initialized = true;
            }
            else if (State == State.Terminated)
            {
                if (_logger != null)
                {
                    if (_config.EnableTelemetryCounters)
                    {
                        _logger.LogDebug("Flux v1 terminated", _logger.GetTelemetrySummary());
                    }
                    // Always log final diagnostic stats
                    LogFinalStatsSummary();
                }
            }
        }

        #endregion

        #region Main Bar Update (Decision Pipeline)

        protected override void OnBarUpdate()
        {
            if (!_initialized)
                return;

            if (CurrentBar < BarsRequiredToTrade)
                return;

            // PHASE 12.5: BarsInProgress safety - only evaluate on primary series
            if (BarsInProgress != 0)
                return;

            // Prevent double-processing on same bar
            if (CurrentBar == _lastProcessedBar)
                return;
            _lastProcessedBar = CurrentBar;

            // Write heartbeat on every bar
            WriteHeartbeat();

            // Update price data arrays for modules
            UpdatePriceDataArrays();

            // Build context snapshot
            Context context = _contextBuilder.Build();

            // Check for session reset
            CheckSessionReset(context);

            // Run the Flux Brain decision pipeline
            RunDecisionPipeline(context);

            // Log stats summary periodically
            LogStatsSummaryIfNeeded();
        }

        /// <summary>
        /// Flux Brain decision pipeline - runs in order per brain-decision.md.
        /// </summary>
        private void RunDecisionPipeline(Context context)
        {
            _barsTotal++; // Increment total bars processed

            // 1. Risk hard-stop evaluation (highest priority)
            if (!context.IsFlat)
            {
                var riskDecision = _riskManager.EvaluateOpenPosition(context);
                if (riskDecision.RequiresFlatten)
                {
                    _executionEngine.FlattenForRisk(context, riskDecision.Reason);
                    return;
                }
            }

            // 1b. Momentum time partition: force-exit at configured hour to free slot for AMR
            if (!context.IsFlat && _config.MomentumHardExitHourCT > 0)
            {
                string owningModule = _moduleRouter.GetOwningModuleId();
                if (owningModule == "Momentum" && context.Timestamp.Hour >= _config.MomentumHardExitHourCT)
                {
                    _logger.LogInfo($"[FLUX][MOMENTUM][TIME_PARTITION] Force-exit at {context.Timestamp:HH:mm}, HardExitHour={_config.MomentumHardExitHourCT}");
                    _executionEngine.FlattenForRisk(context, "MOMENTUM_TIME_PARTITION");
                    return;
                }
            }

            // 1c. CloseCont hard exit: force-exit at configured time (session close)
            if (!context.IsFlat)
            {
                string owningModule = _moduleRouter.GetOwningModuleId();
                if (owningModule == "CloseCont")
                {
                    int ccExitMinutes = _config.CloseContHardExitHourCT * 60 + _config.CloseContHardExitMinuteCT;
                    int currentMinutes = context.Timestamp.Hour * 60 + context.Timestamp.Minute;
                    if (currentMinutes >= ccExitMinutes)
                    {
                        _logger.LogInfo($"[FLUX][CLOSE_CONT][HARD_EXIT] Force-exit at {context.Timestamp:HH:mm}");
                        _executionEngine.FlattenForRisk(context, "CLOSE_CONT_SESSION_EXIT");
                        return;
                    }
                }
            }

            // 2. Manage existing position
            if (!context.IsFlat)
            {
                if (context.Timestamp.Hour >= 17)
                    _logger.LogInfo($"[FLUX][EVENING_DIAG] POSITION_OPEN Time={context.Timestamp:yyyy-MM-dd HH:mm}, Owner={_moduleRouter.GetOwningModuleId() ?? "NULL"}");
                _executionEngine.ManagePosition(context);
                return; // No new entries while in position
            }

            // 3. Check if we can trade (risk gate) - with debug toggle
            var newTradeRisk = _riskManager.EvaluateNewTrade(context);
            bool riskGateBlocked = !newTradeRisk.IsTradingAllowed && !_config.DebugDisableRiskGate;
            if (riskGateBlocked)
            {
                if (context.Timestamp.Hour >= 17)
                    _logger.LogInfo($"[FLUX][EVENING_DIAG] RISK_BLOCKED Time={context.Timestamp:yyyy-MM-dd HH:mm}, Reason={newTradeRisk.Reason}, DailyPnL={context.DailyPnL:F2}, Trades={context.TradesToday}");
                _barsRiskBlocked++;
                _logger.LogGateBlocked("Risk", newTradeRisk.Reason);
                return;
            }

            // 4. Regime gate evaluation (volatility only - session delegated to TradingHours)
            var regimeResult = _regimeGate.EvaluateWithDebug(context, _config);
            if (!regimeResult.IsOpen)
            {
                // PHASE 6: Session gating removed from RegimeGate - only volatility blocks now
                // Session filtering handled by TradingHours template (bars filtered before OnBarUpdate)
                if (regimeResult.Reason.Contains("VOLATILITY"))
                    _barsVolatilityBlocked++;
                return; // Already logged by RegimeGate
            }

            // 5. Route to modules for trade intent - with debug toggles
            SetModulePriceData();
            var routingResult = _moduleRouter.RouteWithDebug(context, _config);

            if (!routingResult.HasIntent)
            {
                // Track router-level blocking
                _barsRouterNoEligible++;
                return; // No valid intent
            }

            _barsIntentSubmitted++;

            // 6. Validate and execute intent
            var intent = routingResult.Intent;
            var (isValid, reason) = _executionEngine.ValidateIntent(intent, context);

            if (!isValid)
            {
                _logger.LogIntentRejected(intent.ModuleId, reason);
                return;
            }

            // 7. Execute the trade
            bool executed = _executionEngine.ExecuteIntent(intent, context);

            if (executed)
            {
                _tradesOpened++;
                _moduleRouter.SetOwningModule(intent.ModuleId);

                // Notify module
                var metadata = _executionEngine.CreateTradeMetadata();
                if (metadata != null)
                {
                    _moduleRouter.NotifyTradeOpened(metadata);
                }

                _contextBuilder.RecordTradeOpened(intent.ModuleId);
            }
        }

        #endregion

        #region Order Events

        protected override void OnExecutionUpdate(Execution execution, string executionId, double price, int quantity, MarketPosition marketPosition, string orderId, DateTime time)
        {
            if (execution.Order == null)
                return;

            // Entry fill (PHASE 6: Exit Fill Price Capture)
            // Phase 12.8: Updated to handle module-attributed entry names (Flux_<ModuleName>_<Direction>)
            string orderName = execution.Order.Name ?? "";
            bool isEntryOrder = orderName.StartsWith("Flux_") && (orderName.EndsWith("_LONG") || orderName.EndsWith("_SHORT"));
            if (isEntryOrder)
            {
                if (execution.Order.OrderState == OrderState.Filled)
                {
                    _executionEngine.OnOrderFilled(price, quantity);
                }
            }
            // Exit fill — capture fill price as soon as a non-entry order fills.
            // Removed marketPosition==Flat gate: in Strategy Analyzer, the position state
            // may not yet reflect Flat when OnExecutionUpdate fires for managed exits.
            else if (execution.Order.OrderState == OrderState.Filled)
            {
                if (execution.Order.OrderAction == OrderAction.Sell
                    || execution.Order.OrderAction == OrderAction.BuyToCover)
                {
                    _executionEngine.OnExitFilled(price, quantity);
                }

                // Process trade closure if position went flat
                if (marketPosition == MarketPosition.Flat && _executionEngine.HasActivePosition())
                {
                    Context context = _contextBuilder.Build();
                    var result = _executionEngine.OnPositionClosed(context, price);

                    if (result != null)
                    {
                        _tradesClosed++;

                        _riskManager.RecordTradeClosed(result.RealizedPnL);
                        _contextBuilder.RecordTradeClosed(result.RealizedPnL);
                        _dynamicSizer?.OnTradeClosed(result.RealizedPnL);

                        _moduleRouter.NotifyTradeClosed(result);
                        _moduleRouter.ClearOwningModule(CurrentBar);
                        _contextBuilder.RecordPositionClosed();
                    }
                }
            }
        }

        protected override void OnPositionUpdate(Position position, double averagePrice, int quantity, MarketPosition marketPosition)
        {
            // Position closed
            if (marketPosition == MarketPosition.Flat && _executionEngine.HasActivePosition())
            {
                Context context = _contextBuilder.Build();
                var result = _executionEngine.OnPositionClosed(context, averagePrice);

                if (result != null)
                {
                    _tradesClosed++; // Track trade closed

                    // Update risk tracking
                    _riskManager.RecordTradeClosed(result.RealizedPnL);
                    _contextBuilder.RecordTradeClosed(result.RealizedPnL);
                    _dynamicSizer?.OnTradeClosed(result.RealizedPnL);

                    // Notify module
                    _moduleRouter.NotifyTradeClosed(result);
                    _moduleRouter.ClearOwningModule(CurrentBar);
                    _contextBuilder.RecordPositionClosed();
                }
            }
        }

        #endregion

        #region Helper Methods

        /// <summary>
        /// Write heartbeat timestamp to C:\NT8\heartbeat.txt
        /// Creates the directory if it doesn't exist
        /// </summary>
        private void WriteHeartbeat()
        {
            try
            {
                string heartbeatPath = @"C:\NT8\heartbeat.txt";
                string directoryPath = Path.GetDirectoryName(heartbeatPath);

                // Create directory if it doesn't exist
                if (!Directory.Exists(directoryPath))
                {
                    Directory.CreateDirectory(directoryPath);
                }

                File.WriteAllText(heartbeatPath, Time[0].ToString("yyyy-MM-dd HH:mm:ss"));
            }
            catch (Exception ex)
            {
                // Log heartbeat write failure but don't crash the strategy
                if (_logger != null)
                    _logger.LogError($"Failed to write heartbeat: {ex.Message}");
            }
        }

        private void UpdatePriceDataArrays()
        {
            int lookback = Math.Min(50, CurrentBar);

            for (int i = 0; i < lookback; i++)
            {
                _highs[i] = High[i];
                _lows[i] = Low[i];
                _opens[i] = Open[i];
                _closes[i] = Close[i];
                _atrValues[i] = _atr[i];
                _ema9Values[i] = _ema9[i];
                _ema21Values[i] = _ema21[i];
                _ema200Values[i] = _ema200[i];
                _volumes[i] = Volume[i];  // PHASE 12.10: Real volume
            }
        }

        private void SetModulePriceData()
        {
            // Get the Range module and set its price data
            var rangeModule = _moduleRouter.GetModule("Range") as RangeModule;
            if (rangeModule != null)
            {
                rangeModule.SetPriceData(
                    _highs, _lows, _opens, _closes,
                    _atrValues, _ema9Values, _ema21Values);
            }

            // Get the Momentum module and set its price data
            // PHASE 12.10: Include volume and isFirstBarOfSession for VWAP parity
            // PHASE 19: Include current 15-min ATR(14) for the regime-volatility gate.
            // ATR is bound to BarsArray[1] and updates as the 15-min series ticks; we
            // simply read the latest value here. Falls back to 0 (gate disabled) until
            // the 15-min series has produced enough bars to compute ATR.
            var momentumModule = _moduleRouter.GetModule("Momentum") as MomentumModule;
            if (momentumModule != null)
            {
                double atr15mValue = 0.0;
                if (_atr15m != null && BarsArray.Length > 1 && BarsArray[1] != null
                    && CurrentBars[1] >= 14)
                {
                    atr15mValue = _atr15m[0];
                }

                momentumModule.SetPriceData(
                    _highs, _lows, _opens, _closes,
                    _atrValues, _ema9Values, _ema21Values, _ema200Values,
                    _volumes, Bars.IsFirstBarOfSession,
                    atr15mValue);
            }

            // Get the ORB module and set its price data
            // PHASE 5: Pass current 15-min ATR(14) to drive the new ATR-scaled
            // range filter, stop cap, and ATR ceiling (Opts 1, 2, 4 in
            // orb-optimization-spec.md). 0 means the 15-min series isn't warm
            // yet; the module fail-closes those gates when it sees a 0.
            var orbModule = _moduleRouter.GetModule("ORB") as ORBModule;
            if (orbModule != null)
            {
                double orbAtr15mValue = 0.0;
                if (_atr15m != null && BarsArray.Length > 1 && BarsArray[1] != null
                    && CurrentBars[1] >= 14)
                {
                    orbAtr15mValue = _atr15m[0];
                }

                orbModule.SetPriceData(
                    _highs, _lows, _opens, _closes,
                    _atrValues, _volumes, Bars.IsFirstBarOfSession,
                    orbAtr15mValue);
            }

            // PHASE 15: AfternoonMR price data
            var afternoonMRModule = _moduleRouter.GetModule("AfternoonMR") as AfternoonMRModule;
            if (afternoonMRModule != null)
            {
                afternoonMRModule.SetPriceData(
                    _highs, _lows, _opens, _closes,
                    _atrValues, _volumes, Bars.IsFirstBarOfSession);
            }

            // PHASE 17: CloseCont price data
            var closeContModule = _moduleRouter.GetModule("CloseCont") as CloseContModule;
            if (closeContModule != null)
            {
                closeContModule.SetPriceData(
                    _highs, _lows, _opens, _closes,
                    _atrValues, _volumes, Bars.IsFirstBarOfSession);
            }
        }

        private void CheckSessionReset(Context context)
        {
            if (context.SessionDate != _lastSessionDate)
            {
                _lastSessionDate = context.SessionDate;
                ResetDaily();
                _logger.LogDebug("Session reset", context.SessionDate.ToShortDateString());
            }
        }

        private void ResetDaily()
        {
            _contextBuilder.ResetDaily();
            _moduleRouter.ResetDaily();
            _riskManager.ResetDaily();
            _executionEngine.ResetDaily();
            _dynamicSizer?.ResetDaily();
            _logger.ResetTelemetry();
            ResetDiagnosticCounters();
        }

        /// <summary>
        /// Reset diagnostic counters for new session.
        /// </summary>
        private void ResetDiagnosticCounters()
        {
            _barsTotal = 0;
            _barsRiskBlocked = 0;
            _barsSessionBlocked = 0;
            _barsVolatilityBlocked = 0;
            _barsRouterNoEligible = 0;
            _barsRangeEvaluated = 0;
            _barsRangeReturnedNone = 0;
            _barsIntentSubmitted = 0;
            _tradesOpened = 0;
            _tradesClosed = 0;
        }

        /// <summary>
        /// Log diagnostic stats summary every 10,000 bars.
        /// </summary>
        private void LogStatsSummaryIfNeeded()
        {
            if (_barsTotal % 10000 == 0 && _barsTotal > 0)
            {
                long rangeEval = _moduleRouter.BarsRangeEvaluated;
                long rangeNone = _moduleRouter.BarsRangeReturnedNone;
                _logger.LogDebug($"STATS: total={_barsTotal}, riskBlocked={_barsRiskBlocked}, sessionBlocked={_barsSessionBlocked}, volBlocked={_barsVolatilityBlocked}, routerNoEligible={_barsRouterNoEligible}, rangeEval={rangeEval}, rangeNone={rangeNone}, intents={_barsIntentSubmitted}, opened={_tradesOpened}, closed={_tradesClosed}");
            }
        }

        /// <summary>
        /// Log final diagnostic stats summary on termination.
        /// </summary>
        private void LogFinalStatsSummary()
        {
            long rangeEval = _moduleRouter.BarsRangeEvaluated;
            long rangeNone = _moduleRouter.BarsRangeReturnedNone;

            // Get Range reject summary
            var rangeModule = _moduleRouter.GetModule("Range") as RangeModule;
            string rangeRejects = rangeModule?.GetRejectSummary() ?? "Range module not found";

            _logger.LogDebug($"FINAL STATS: total={_barsTotal}, riskBlocked={_barsRiskBlocked}, sessionBlocked={_barsSessionBlocked}, volBlocked={_barsVolatilityBlocked}, routerNoEligible={_barsRouterNoEligible}, rangeEval={rangeEval}, rangeNone={rangeNone}, intents={_barsIntentSubmitted}, opened={_tradesOpened}, closed={_tradesClosed}");
            _logger.LogDebug($"RANGE_REJECTS: {rangeRejects}");
        }

        #endregion
    }
}