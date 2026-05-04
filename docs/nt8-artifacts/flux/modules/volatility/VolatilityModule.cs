#region Using declarations
using System;
using System.Collections.Generic;
using System.Linq;
using NinjaTrader.NinjaScript.Strategies.Flux.Core;
#endregion

namespace NinjaTrader.NinjaScript.Strategies.Flux.Modules.Volatility
{
    /// <summary>
    /// Volatility Module for Flux v1.
    /// Implements IModule contract - emits TradeIntents only, never places orders.
    ///
    /// IMPORTANT: This module adapts the validated standalone VolatilityRegime logic.
    /// The trading logic is NOT modified - only refactored to emit intents.
    ///
    /// Core logic: NR5 compression breakout with long-only entries.
    /// </summary>
    public class VolatilityModule : IModule
    {
        #region Module Identity

        public string ModuleId => "Volatility";

        #endregion

        #region Configuration

        private readonly Config _config;
        private readonly Logger _logger;

        // Volatility parameters (from standalone VolatilityRegime)
        private readonly int _compressionLookback = 5; // NR5 detection
        private readonly double _takeProfitR = 2.0;

        // Reject reason tracking (for diagnostics)
        private readonly System.Collections.Generic.Dictionary<string, int> _rejectCounts;

        #endregion

        #region Internal State

        // Compression box state (from standalone)
        private double _boxHigh = 0;
        private double _boxLow = 0;
        private bool _boxActive = false;
        private int _boxStartBar = -1;

        // Post-loss cooldown tracking (bar-based, from standalone)
        private int _barsSinceLastLoss = -1;
        private readonly int _postLossCooldownBars = 30;

        // Internal tracking
        private int _lastEvaluatedBar = -1;
        private int _consecutiveLosses = 0;

        // Price data cache (populated by Flux)
        private double[] _highs;
        private double[] _lows;
        private double[] _opens;
        private double[] _closes;

        #endregion

        #region Constructor

        public VolatilityModule(Config config, Logger logger)
        {
            _config = config ?? throw new ArgumentNullException(nameof(config));
            _logger = logger ?? throw new ArgumentNullException(nameof(logger));

            // Initialize reject reason tracking
            _rejectCounts = new System.Collections.Generic.Dictionary<string, int>();
        }

        #endregion

        #region IModule Implementation

        /// <summary>
        /// Evaluates the current bar for a Volatility trading opportunity.
        /// Returns TradeIntent.None if no valid setup, or a Long intent.
        ///
        /// CRITICAL: This method must be deterministic and side-effect free (except internal state).
        /// </summary>
        public TradeIntent Evaluate(Context context)
        {
            // Generate EvaluationId for this evaluation cycle
            string tradingDay = context.Timestamp.ToString("yyyyMMdd");
            string currentTime = context.Timestamp.ToString("HHmm");
            string evaluationId = $"{tradingDay}-{currentTime}|EVAL|{context.CurrentBar}";

            // Log evaluation start
            _logger.LogInfo($"[FLUX][VOL][EVAL_START] EvaluationId={evaluationId}, CurrentBar={context.CurrentBar}, IsFlat={context.IsFlat}, IsHighVol={context.IsHighVol}, ConsecutiveLosses={_consecutiveLosses}");

            // Prevent double-evaluation on same bar
            if (_lastEvaluatedBar == context.CurrentBar)
                return Reject(evaluationId, "BAR_ALREADY_EVALUATED");

            _lastEvaluatedBar = context.CurrentBar;

            try
            {
                // 0. Minimum bar requirement for evaluation
                if (context.CurrentBar < _compressionLookback)
                {
                    return Reject(evaluationId, "REJECT_INSUFFICIENT_BARS", $"required={_compressionLookback}, current={context.CurrentBar}");
                }

                // 1. Must be flat to generate entry signals
                if (!context.IsFlat)
                {
                    return Reject(evaluationId, "REJECT_NOT_FLAT");
                }

                // 2. Check post-loss cooldown
                if (_barsSinceLastLoss >= 0 && _barsSinceLastLoss < _postLossCooldownBars)
                {
                    int cooldownRemaining = _postLossCooldownBars - _barsSinceLastLoss;
                    return Reject(evaluationId, "REJECT_COOLDOWN", $"cooldownRemaining={cooldownRemaining}");
                }

                // 3. Update compression box state
                UpdateCompressionBox(context);

                // 4. Evaluate breakout opportunity (long-only)
                return EvaluateBreakout(context, evaluationId);
            }
            catch (Exception ex)
            {
                // Final safety net - log exception and return safe rejection
                _logger.LogInfo($"[FLUX][VOL][EXCEPTION] EvaluationId={evaluationId}, CurrentBar={context.CurrentBar}, Exception={ex.Message}");
                return Reject(evaluationId, "REJECT_EXCEPTION", $"exception={ex.Message}");
            }
        }

        /// <summary>
        /// Notification when a trade is opened.
        /// </summary>
        public void OnTradeOpened(TradeMetadata trade)
        {
            // Reset box after entry (standalone behavior)
            _boxActive = false;
        }

        /// <summary>
        /// Notification when a trade is closed.
        /// </summary>
        public void OnTradeClosed(TradeResult result)
        {
            // Track consecutive losses
            if (result.RealizedPnL < 0)
            {
                _consecutiveLosses++;
                // Activate post-loss cooldown (standalone behavior)
                _barsSinceLastLoss = 0;
            }
            else
            {
                _consecutiveLosses = 0;
            }
        }

        /// <summary>
        /// Record a reject reason and return TradeIntent.None
        /// </summary>
        private TradeIntent Reject(string evaluationId, string reason, string additionalInfo = "")
        {
            if (!_rejectCounts.ContainsKey(reason))
                _rejectCounts[reason] = 0;
            _rejectCounts[reason]++;

            // Log rejection with required format
            string logMessage = $"[FLUX][VOL][{reason}] bar={_lastEvaluatedBar} time={DateTime.Now:yyyy-MM-dd HH:mm:ss}";
            if (!string.IsNullOrEmpty(additionalInfo))
                logMessage += $" {additionalInfo}";

            _logger.LogInfo(logMessage);

            return TradeIntent.None;
        }

        /// <summary>
        /// Get reject reason summary for logging
        /// </summary>
        public string GetRejectSummary()
        {
            if (_rejectCounts.Count == 0)
                return "No rejections recorded";

            var sorted = _rejectCounts.OrderByDescending(kvp => kvp.Value);
            var top5 = sorted.Take(5);
            return string.Join(", ", top5.Select(kvp => $"{kvp.Key}={kvp.Value}"));
        }

        /// <summary>
        /// Resets module state for new session.
        /// </summary>
        public void ResetDaily()
        {
            _boxHigh = 0;
            _boxLow = 0;
            _boxActive = false;
            _boxStartBar = -1;
            _barsSinceLastLoss = -1;
            _lastEvaluatedBar = -1;
            _consecutiveLosses = 0;
            _rejectCounts.Clear();
        }

        #endregion

        #region Price Data Interface

        /// <summary>
        /// Sets the price data arrays for evaluation.
        /// Called by FluxV1Strategy before Evaluate.
        /// </summary>
        public void SetPriceData(
            double[] highs, double[] lows, double[] opens, double[] closes,
            double[] atrValues, double[] ema9Values, double[] ema21Values)
        {
            _highs = highs;
            _lows = lows;
            _opens = opens;
            _closes = closes;
            // Volatility module doesn't use ATR/EMAs for its logic
        }

        #endregion

        #region Compression Box Logic (Ported from VolatilityRegime)

        private void UpdateCompressionBox(Context context)
        {
            // Ensure sufficient bars for NR5 detection and arrays have data
            if (context.CurrentBar < _compressionLookback ||
                _highs == null || _lows == null ||
                _highs.Length < _compressionLookback ||
                _lows.Length < _compressionLookback)
                return;

            // Step 1: Detect NR5 compression and create box
            if (!_boxActive)
            {
                if (IsNR5(context))
                {
                    CreateCompressionBox(context);
                }
            }
        }

        /// <summary>
        /// Checks if current bar has the narrowest range of the last N bars (NR5-style).
        /// </summary>
        private bool IsNR5(Context context)
        {
            // Arrays are 0-indexed: index 0 = current bar, index 1 = previous bar, etc.
            // We need _compressionLookback bars total (current + N-1 previous)
            if (_highs == null || _lows == null ||
                _highs.Length < _compressionLookback ||
                _lows.Length < _compressionLookback)
                return false;

            double currentRange = context.High - context.Low;

            // Check if current bar has the narrowest range of last N bars
            for (int i = 1; i < _compressionLookback; i++)
            {
                double pastRange = _highs[i] - _lows[i];
                if (pastRange <= currentRange)
                    return false;
            }

            return true;
        }

        /// <summary>
        /// Creates a static compression box from the last N bars.
        /// Box boundaries are the highest high and lowest low of the lookback period.
        /// </summary>
        private void CreateCompressionBox(Context context)
        {
            // Arrays are 0-indexed: index 0 = current bar, index 1 = previous bar, etc.
            if (_highs == null || _lows == null ||
                _highs.Length < _compressionLookback ||
                _lows.Length < _compressionLookback)
                return;

            // Calculate box boundaries from last N bars (inclusive of current bar)
            _boxHigh = context.High;
            _boxLow = context.Low;

            for (int i = 1; i < _compressionLookback; i++)
            {
                if (_highs[i] > _boxHigh)
                    _boxHigh = _highs[i];
                if (_lows[i] < _boxLow)
                    _boxLow = _lows[i];
            }

            _boxActive = true;
            _boxStartBar = context.CurrentBar;

            // Log box creation
            _logger.LogInfo($"[FLUX][VOL][BOX_CREATED] bar={context.CurrentBar} time={context.Timestamp:yyyy-MM-dd HH:mm:ss} boxHigh={_boxHigh:F2} boxLow={_boxLow:F2}");
        }

        #endregion

        #region Breakout Logic (Ported from VolatilityRegime)

        private TradeIntent EvaluateBreakout(Context context, string evaluationId)
        {
            // Must have active compression box
            if (!_boxActive)
            {
                return Reject(evaluationId, "REJECT_ENTRY_CONDITIONS_NOT_MET", "reason=NO_ACTIVE_BOX");
            }

            // Long breakout: close above box high (LONG-ONLY)
            if (context.Close > _boxHigh)
            {
                // Calculate stop and target (standalone logic)
                double stopPrice = _boxLow;
                double risk = Math.Abs(context.Close - stopPrice);
                double targetDistance = risk * _takeProfitR;
                double targetPrice = context.Close + targetDistance;

                // Convert to ticks for Flux
                int stopTicks = (int)Math.Ceiling(risk / context.TickSize);
                int targetTicks = (int)Math.Ceiling(targetDistance / context.TickSize);

                // Clamp to reasonable values
                stopTicks = Math.Max(4, Math.Min(stopTicks, 100));
                targetTicks = Math.Max(4, Math.Min(targetTicks, 200));

                // Generate SetupId with known direction
                string setupId = evaluationId.Replace("|EVAL|", "|LONG|");

                // Log intent emission
                _logger.LogInfo($"[FLUX][VOL][INTENT_LONG] EvaluationId={evaluationId}, SetupId={setupId}, bar={context.CurrentBar}, time={context.Timestamp:yyyy-MM-dd HH:mm:ss}, entryPrice={context.Close:F2}, stopPrice={stopPrice:F2}, targetPrice={targetPrice:F2}, stopTicks={stopTicks}, targetTicks={targetTicks}");

                return TradeIntent.Long(
                    ModuleId,
                    stopTicks,
                    targetTicks,
                    "Volatility_NR5_1R",
                    "LONG_BREAKOUT",
                    evaluationId,
                    setupId);
            }

            // No breakout conditions met
            return Reject(evaluationId, "REJECT_ENTRY_CONDITIONS_NOT_MET", $"reason=CLOSE_NOT_ABOVE_BOX_HIGH close={context.Close:F2} boxHigh={_boxHigh:F2}");
        }

        #endregion
    }
}