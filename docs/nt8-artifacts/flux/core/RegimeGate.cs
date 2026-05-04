#region Using declarations
using System;
#endregion

namespace NinjaTrader.NinjaScript.Strategies.Flux.Core
{
    /// <summary>
    /// Gate result with reason.
    /// </summary>
    public class GateResult
    {
        public bool IsOpen { get; private set; }
        public string Reason { get; private set; }

        private GateResult(bool isOpen, string reason)
        {
            IsOpen = isOpen;
            Reason = reason;
        }

        public static GateResult Open() => new GateResult(true, "ALLOWED");
        public static GateResult Blocked(string reason) => new GateResult(false, reason);
    }

    /// <summary>
    /// Evaluates regime-level gating rules.
    /// Enforces session/time rules and volatility rules.
    /// </summary>
    public class RegimeGate
    {
        private readonly Config _config;
        private readonly Logger _logger;

        // Session gate diagnostics removed - session gating delegated to TradingHours

        public RegimeGate(Config config, Logger logger)
        {
            _config = config ?? throw new ArgumentNullException(nameof(config));
            _logger = logger ?? throw new ArgumentNullException(nameof(logger));
        }

        /// <summary>
        /// Evaluates all regime gates for the current bar.
        /// Returns combined gate result.
        /// </summary>
        public GateResult Evaluate(Context context)
        {
            return EvaluateWithDebug(context, null);
        }

        /// <summary>
        /// Evaluates all regime gates with debug toggle support.
        /// </summary>
        public GateResult EvaluateWithDebug(Context context, Config config)
        {
            // PHASE 6: Session gating REMOVED - TradingHours is sole authority
            // Session filtering now handled exclusively by NinjaTrader TradingHours template

            // 1. Volatility Gate - with debug toggle
            var volatilityResult = EvaluateVolatilityGate(context);
            bool volatilityBlocked = !volatilityResult.IsOpen && (config == null || !config.DebugDisableVolatilityGate);
            if (volatilityBlocked)
            {
                _logger.LogGateBlocked("Volatility", volatilityResult.Reason);
                return volatilityResult;
            }

            return GateResult.Open();
        }

        /// <summary>
        /// Checks if a specific module is allowed to trade under current volatility.
        /// Range module is explicitly disabled in HIGH volatility per brain-decision.md.
        /// </summary>
        public GateResult EvaluateModuleVolatility(Context context, string moduleId)
        {
            if (moduleId == "Range")
            {
                // Range module: Allowed in LOW_VOL and MID_VOL, disabled in HIGH_VOL
                if (context.IsHighVol)
                {
                    // PHASE 6: Add sampled logging for volatility gate skips
                    if (context.CurrentBar % 1000 == 0) // Sample every 1000 bars to avoid spam
                    {
                        _logger.LogDebug($"VOL_GATE_SKIP: classification=HIGH, atr={context.ATR:F4}, time={context.Timestamp:HH:mm:ss}");
                    }
                    return GateResult.Blocked("VOLATILITY_HIGH_RANGE_DISABLED");
                }
            }

            // Future: MomentumModule expected to be allowed in MID_VOL and HIGH_VOL

            return GateResult.Open();
        }

        #region Session Gate

        private GateResult EvaluateSessionGate(Context context)
        {
            // PHASE 6: Session gating REMOVED - TradingHours is sole authority
            // All session/time filtering now handled by NinjaTrader TradingHours template
            // RegimeGate no longer enforces session rules to prevent double-gating
            return GateResult.Open();
        }

        #endregion

        #region Volatility Gate

        private GateResult EvaluateVolatilityGate(Context context)
        {
            if (!_config.EnableVolatilityGate)
            {
                return GateResult.Open();
            }

            // System-level volatility gate (affects all modules)
            // Individual module volatility checks are done in EvaluateModuleVolatility

            // For v1, we don't block at system level based on volatility alone
            // Module-specific gating handles this via EvaluateModuleVolatility

            return GateResult.Open();
        }

        #endregion
    }
}

