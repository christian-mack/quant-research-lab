#region Using declarations
using System;
#endregion

namespace NinjaTrader.NinjaScript.Strategies.Flux.Core
{
    /// <summary>
    /// Two-tier sizing phase for eval accounts.
    /// Initial = conservative (building buffer), Full = scaled up (buffer established).
    /// Transition is ONE-WAY during eval: once Full, stays Full.
    /// </summary>
    public enum SizingPhase
    {
        Initial,
        Full
    }

    /// <summary>
    /// Two-tier dynamic position sizer for Flux.
    ///
    /// Starts at InitialMultiplier (0.5x) to protect against early drawdown,
    /// then transitions to FullMultiplier (1.25x) once a profit buffer is established.
    /// The transition is one-way during eval — once Full is reached, it stays Full
    /// even if balance drops back below threshold. Rationale: the trailing DD has
    /// locked favorably once the buffer is hit; reducing size after that hurts more
    /// than it helps.
    ///
    /// Balance is tracked internally via cumulative realized P&amp;L, so behavior
    /// is identical in backtest and live.
    /// </summary>
    public class DynamicSizer
    {
        private readonly Config _config;
        private readonly Logger _logger;

        private SizingPhase _phase;
        private double _cumulativeRealizedPnL;

        public SizingPhase CurrentPhase => _phase;
        public double CumulativeRealizedPnL => _cumulativeRealizedPnL;

        public DynamicSizer(Config config, Logger logger)
        {
            _config = config ?? throw new ArgumentNullException(nameof(config));
            _logger = logger ?? throw new ArgumentNullException(nameof(logger));
            _phase = SizingPhase.Initial;
            _cumulativeRealizedPnL = 0;

            _logger.LogInfo($"[FLUX][SIZER][INIT] Phase=Initial, " +
                $"InitialMult={_config.DynamicSizerInitialMultiplier:F2}, " +
                $"FullMult={_config.DynamicSizerFullMultiplier:F2}, " +
                $"BufferThreshold={_config.DynamicSizerBufferThreshold:F2}");
        }

        /// <summary>
        /// Returns the current sizing multiplier based on phase.
        /// </summary>
        public double GetMultiplier()
        {
            return _phase == SizingPhase.Initial
                ? _config.DynamicSizerInitialMultiplier
                : _config.DynamicSizerFullMultiplier;
        }

        /// <summary>
        /// Returns the scaled contract quantity for a given module.
        /// Applies the current multiplier to the module's base qty from config,
        /// with a floor of 1 contract.
        /// </summary>
        public int GetModuleQty(string moduleId)
        {
            int baseQty = ResolveBaseQty(moduleId);
            double multiplier = GetMultiplier();
            int scaled = (int)Math.Max(1, Math.Round(baseQty * multiplier));

            _logger.LogDebug($"[FLUX][SIZER][QTY] Module={moduleId}, Base={baseQty}, " +
                $"Mult={multiplier:F2}, Scaled={scaled}, Phase={_phase}");

            return scaled;
        }

        /// <summary>
        /// Called after every trade close to accumulate realized P&amp;L
        /// and check for phase transition.
        /// </summary>
        public void OnTradeClosed(double realizedPnL)
        {
            _cumulativeRealizedPnL += realizedPnL;

            if (_phase == SizingPhase.Initial
                && _cumulativeRealizedPnL >= _config.DynamicSizerBufferThreshold)
            {
                _phase = SizingPhase.Full;
                _logger.LogInfo($"[FLUX][SIZER][PHASE_TRANSITION] Initial->Full, " +
                    $"CumulativePnL={_cumulativeRealizedPnL:F2}, " +
                    $"Threshold={_config.DynamicSizerBufferThreshold:F2}");
            }
        }

        /// <summary>
        /// No-op for two-tier: phase persists across days during eval.
        /// </summary>
        public void ResetDaily()
        {
        }

        private int ResolveBaseQty(string moduleId)
        {
            switch (moduleId)
            {
                case "Momentum":  return _config.MomentumQuantity;
                case "ORB":       return _config.ORBQuantity;
                case "Range":     return _config.RangeQuantity;
                case "AfternoonMR": return _config.AfternoonMRQuantity;
                default:          return 1;
            }
        }
    }
}
