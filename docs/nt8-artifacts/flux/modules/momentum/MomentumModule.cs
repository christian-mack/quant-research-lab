#region Using declarations
using System;
using System.Collections.Generic;
using System.Linq;
using NinjaTrader.NinjaScript.Strategies.Flux.Core;
#endregion

namespace NinjaTrader.NinjaScript.Strategies.Flux.Modules.Momentum
{
    /// <summary>
    /// Momentum Module for Flux v1.
    /// Implements Williams %R mean reversion strategy.
    /// 
    /// PHASE 12.10: PARITY MODE
    /// This module implements EXACT semantic parity with standalone MomentumRegime.
    /// Entry logic is LEVEL-BASED (not cross-based).
    /// Stop/target uses PRICE-SPACE (not tick quantization with clamps).
    /// </summary>
    public class MomentumModule : IModule
    {
        #region Module Identity

        public string ModuleId => "Momentum";

        #endregion

        #region Configuration

        private readonly Config _config;
        private readonly Logger _logger;

        // Momentum parameters (Williams %R) - PHASE 12.10: Match standalone defaults
        private readonly int _wprPeriod;
        private readonly double _overbought;
        private readonly double _oversold;
        private readonly int _emaPeriod;
        private readonly int _atrPeriod;
        private readonly double _stopLossAtrMultiplier;
        private readonly double _profitTargetAtrMultiplier;

        // PHASE 12.10: Parity mode flag - disables Flux-specific behavior
        private readonly bool _parityMode;

        // PHASE 12.10: Parity mode parameters - match standalone exactly
        private readonly double _fixedStopDistance;   // TrailingDistance = 80 points
        private readonly bool _enableAutoBreakEven;   // EnableAutoBE = true
        private readonly double _beTriggerR;          // BETriggerR = 1.5

        // PHASE 12.10: Session filter parameters (from standalone screenshot)
        // Standalone uses manual ET time filtering: 09:30-15:30 ET
        // Narrowed to 09:30-14:30 ET: validated OOS (Oct-Dec 2025) — removes 21 trades
        // with net -$208 PnL and reduces max drawdown by $320
        private readonly TimeSpan _sessionStartET = new TimeSpan(9, 30, 0);   // 09:30 ET
        private readonly TimeSpan _sessionEndET = new TimeSpan(14, 30, 0);    // 14:30 ET
        private readonly TimeZoneInfo _easternTimeZone;

        // VWAP filter parameters (Phase 12.6: from config, default OFF)
        private readonly bool _enableVWAPFilter;
        private readonly double _vwapDeviation;  // PHASE 12.10: Price units, not ATR mult

        // PHASE 13: Hour exclusion filter
        private readonly System.Collections.Generic.HashSet<int> _blockedHoursET;

        #endregion

        #region Internal State

        // Price data cache (populated by caller)
        private double[] _highs;
        private double[] _lows;
        private double[] _opens;
        private double[] _closes;
        private double[] _atrValues;
        private double[] _ema9Values;
        private double[] _ema21Values;
        private double[] _ema200Values;
        private double[] _volumes;  // PHASE 12.10: Real volume for VWAP

        // PHASE 19: 15-minute ATR(14) value, supplied by FluxV1Strategy from BarsArray[1].
        // Used for the secondary regime-volatility ceiling gate.
        private double _atr15mValue;

        // State tracking - removed _lastEvaluatedBar per Phase 12.5 canonical context
        private bool _warmupCompleteLogged = false;
        private bool _isFirstBarOfSession = false;  // PHASE 12.10: Session reset flag

        // VWAP state tracking (session-based) - PHASE 12.10: Uses real volume
        private double _sessionVWAP = 0.0;
        private double _cumulativePriceVolume = 0.0;
        private double _cumulativeVolume = 0.0;
        private DateTime _lastSessionDate = DateTime.MinValue;

        // Reject reason tracking
        private readonly Dictionary<string, int> _rejectCounts;

        #endregion

        #region Constructor

        public MomentumModule(Config config, Logger logger)
        {
            _config = config ?? throw new ArgumentNullException(nameof(config));
            _logger = logger ?? throw new ArgumentNullException(nameof(logger));

            // PHASE 12.10: Parity mode from config
            _parityMode = _config.MomentumParityMode;

            // PHASE 12.10: Parameters match standalone backtest values exactly
            // These are the actual values used in standalone backtests (from NT8 screenshot)
            _wprPeriod = 14;
            _overbought = -15;   // From screenshot
            _oversold = -85;     // From screenshot
            _emaPeriod = 200;
            _atrPeriod = 14;
            _stopLossAtrMultiplier = 2.0;
            _profitTargetAtrMultiplier = 6.0;  // From screenshot: Profit Target ATR Multiplier = 6

            // PHASE 12.10: Parity mode stop/break-even parameters from config
            _fixedStopDistance = _config.MomentumFixedStopDistance;     // 80 points from standalone
            _enableAutoBreakEven = _config.MomentumEnableAutoBreakEven; // true from standalone
            _beTriggerR = _config.MomentumBETriggerR;                   // 1.5 from standalone

            // Phase 12.10: VWAP parameters from config (default: disabled)
            // VWAP deviation is now in price units (matching standalone), not ATR multiples
            _enableVWAPFilter = _config.MomentumEnableVWAPFilter;
            _vwapDeviation = _config.MomentumVWAPDeviation;

            // PHASE 13: Blocked hours from config
            _blockedHoursET = _config.MomentumBlockedHoursSet ?? new System.Collections.Generic.HashSet<int>();

            // PHASE 12.10: Initialize Eastern timezone for session filtering
            try
            {
                _easternTimeZone = TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");
            }
            catch
            {
                // Fallback for non-Windows systems
                _easternTimeZone = TimeZoneInfo.FindSystemTimeZoneById("America/New_York");
            }

            // Initialize reject reason tracking
            _rejectCounts = new Dictionary<string, int>();
        }

        #endregion


        #region IModule Implementation

        /// <summary>
        /// Evaluates the current bar for a Momentum trading opportunity.
        /// Uses router-provided canonical context only. No implicit bar/time state.
        /// Returns TradeIntent.None if no valid setup, or a Long/Short intent.
        /// </summary>
        public TradeIntent Evaluate(Context context)
        {
            // PHASE 12.5: Canonical bar & time ownership - router provides single source of truth
            DateTime evaluationTime = context.Timestamp;
            int evaluationBar = context.CurrentBar;

            // Generate EvaluationId using canonical context
            string tradingDay = evaluationTime.ToString("yyyyMMdd");
            string currentTime = evaluationTime.ToString("HHmm");
            string evaluationId = $"{tradingDay}-{currentTime}|EVAL|{evaluationBar}";

            // Log evaluation start with canonical context
            _logger.LogInfo($"[FLUX][MOMENTUM][EVAL_START] EvaluationId={evaluationId}, CurrentBar={evaluationBar}, IsFlat={context.IsFlat}");

            // PHASE 12.10: Session gate - use explicit ET time filtering to match standalone
            // Standalone uses IsWithinTradingHours() which checks 09:30-15:30 ET
            bool sessionValid = IsWithinTradingHoursET(evaluationTime);
            
            // Convert to ET for logging
            DateTime timeET = TimeZoneInfo.ConvertTime(evaluationTime, _easternTimeZone);
            string barTimeET = timeET.ToString("HH:mm");
            _logger.LogInfo($"[FLUX][MOMENTUM][SESSION_INTERNAL] BarTimeET={barTimeET}, SessionValid={sessionValid}, SessionWindow=09:30-14:30");
            
            if (!sessionValid)
            {
                return Reject(evaluationId, "REJECT_OUTSIDE_SESSION_WINDOW_ET");
            }

            // PHASE 13: Hour exclusion filter - block entries during specified hours (ET)
            if (_blockedHoursET.Count > 0)
            {
                int currentHourET = timeET.Hour;
                if (_blockedHoursET.Contains(currentHourET))
                {
                    return Reject(evaluationId, $"REJECT_BLOCKED_HOUR_ET_{currentHourET}");
                }
            }

            // Update VWAP for current bar (only if VWAP filter is enabled)
            if (_enableVWAPFilter)
            {
                UpdateVWAP(context);
            }

            // PHASE 12.5: Remove stale bar state - use router bar index for de-duplication
            // De-duplication logic removed per canonical context requirements

            // Must be flat to generate entry signals
            if (!context.IsFlat)
                return Reject(evaluationId, "POSITION_NOT_FLAT");

            // Check if we have enough bars for all indicators (using context.CurrentBar ONLY)
            int requiredLookback = Math.Max(_wprPeriod, Math.Max(_emaPeriod, _atrPeriod));
            
            // TEMPORARY DIAGNOSTIC: Log warmup state
            _logger.LogInfo(
                $"[FLUX][MOMENTUM][DEBUG_WARMUP] " +
                $"CurrentBar={context.CurrentBar}, " +
                $"RequiredLookback={requiredLookback}");

            if (context.CurrentBar < requiredLookback)
                return Reject(evaluationId, "INSUFFICIENT_BARS");

            // Log warmup completion once per session
            if (!_warmupCompleteLogged)
            {
                _warmupCompleteLogged = true;
                _logger.LogInfo($"[FLUX][MOMENTUM][WARMUP_COMPLETE] CurrentBar={context.CurrentBar}");
            }

            // Validate price data availability
            if (_highs == null || _lows == null || _closes == null || _atrValues == null)
                return Reject(evaluationId, "PRICE_DATA_NOT_AVAILABLE");

            // Calculate Williams %R
            double wprValue = CalculateWilliamsR(_wprPeriod);
            if (double.IsNaN(wprValue))
                return Reject(evaluationId, "WPR_CALCULATION_FAILED");

            // Get EMA200 value (canonical Momentum trend filter)
            double emaValue = _ema200Values != null && _ema200Values.Length > 0 ? _ema200Values[0] : 0;
            if (emaValue <= 0)
                return Reject(evaluationId, "EMA200_NOT_AVAILABLE");

            // Get ATR value
            double atrValue = _atrValues[0];
            if (atrValue <= 0)
                return Reject(evaluationId, "ATR_NOT_AVAILABLE");

            // ATR ceiling gate: skip entries when volatility is too high for the fixed 80-point stop.
            // When ATR > 30, the stop is < 2.7× ATR — normal price noise exceeds it.
            // Validated OOS (Oct-Jan) and IS (Jan-Feb): ATR 30-40 bucket shows ~18% WR in both periods.
            if (_parityMode && _config.MomentumMaxATR > 0 && atrValue > _config.MomentumMaxATR)
                return Reject(evaluationId, $"ATR_CEILING_EXCEEDED:{atrValue:F2}>{_config.MomentumMaxATR:F0}");

            // PHASE 19: 15-minute ATR ceiling gate.
            // Filters regime-level volatility that the 1-min gate misses (e.g. wide
            // 15-min ranges with calm individual minutes that still grind through the
            // fixed 80-pt stop). Validated 6-year IS/OOS at threshold 40.
            if (_parityMode && _config.MomentumMaxATR15m > 0 && _atr15mValue > _config.MomentumMaxATR15m)
                return Reject(evaluationId,
                    $"ATR15M_CEILING_EXCEEDED:{_atr15mValue:F2}>{_config.MomentumMaxATR15m:F0}");

            // Evaluate entry opportunities
            return EvaluateEntries(context, evaluationId, evaluationTime, wprValue, emaValue, atrValue);
        }

        /// <summary>
        /// Notification when a trade is opened.
        /// </summary>
        public void OnTradeOpened(TradeMetadata trade)
        {
            // No specific action needed
            _logger.LogDebug($"[FLUX][MOMENTUM] Trade opened: {trade.Direction} @ {trade.EntryPrice:F2}");
        }

        /// <summary>
        /// Notification when a trade is closed.
        /// NOTE: Loss-streak tracking is done at the Flux routing layer, not here.
        /// </summary>
        public void OnTradeClosed(TradeResult result)
        {
            // No specific action needed - loss tracking done by ModuleRouter
            _logger.LogDebug($"[FLUX][MOMENTUM] Trade closed: PnL={result.RealizedPnL:F2}, R={result.RMultiple:F2}");
        }

        /// <summary>
        /// Resets module state for new session.
        /// </summary>
        public void ResetDaily()
        {
            // PHASE 12.5: Removed _lastEvaluatedBar reset - using canonical context only
            _warmupCompleteLogged = false;
            _rejectCounts.Clear();
        }

        #endregion

        #region Price Data Interface

        /// <summary>
        /// Sets the price data arrays for evaluation.
        /// Called by FluxV1Strategy before Evaluate.
        /// PHASE 12.10: Now includes volume for proper VWAP calculation.
        /// </summary>
        public void SetPriceData(
            double[] highs, double[] lows, double[] opens, double[] closes,
            double[] atrValues, double[] ema9Values, double[] ema21Values, double[] ema200Values,
            double[] volumes = null, bool isFirstBarOfSession = false,
            double atr15mValue = 0.0)
        {
            _highs = highs;
            _lows = lows;
            _opens = opens;
            _closes = closes;
            _atrValues = atrValues;
            _ema9Values = ema9Values;
            _ema21Values = ema21Values;
            _ema200Values = ema200Values;
            _volumes = volumes;  // PHASE 12.10: Real volume data
            _isFirstBarOfSession = isFirstBarOfSession;  // PHASE 12.10: Session reset flag
            _atr15mValue = atr15mValue;  // PHASE 19: 15-min ATR(14) for regime-volatility gate
        }

        #endregion

        #region VWAP Calculation

        /// <summary>
        /// Updates session-based VWAP calculation.
        /// PHASE 12.10: Uses real bar volume and resets on IsFirstBarOfSession.
        /// Matches standalone SimpleVWAP.Update() semantics exactly.
        /// </summary>
        private void UpdateVWAP(Context context)
        {
            // PHASE 12.10: Reset on first bar of session (matching standalone Bars.IsFirstBarOfSession)
            if (_isFirstBarOfSession)
            {
                _sessionVWAP = 0.0;
                _cumulativePriceVolume = 0.0;
                _cumulativeVolume = 0.0;
                _lastSessionDate = context.SessionDate;

                _logger.LogDebug($"[FLUX][MOMENTUM][VWAP_RESET] IsFirstBarOfSession=true, VWAP reset to 0");
            }

            // PHASE 12.10: Use real volume from bar data (not placeholder)
            double volume = (_volumes != null && _volumes.Length > 0) ? _volumes[0] : 1.0;
            double priceVolume = context.Close * volume;

            _cumulativePriceVolume += priceVolume;
            _cumulativeVolume += volume;

            if (_cumulativeVolume > 0)
            {
                _sessionVWAP = _cumulativePriceVolume / _cumulativeVolume;
            }
        }

        /// <summary>
        /// Gets the current session VWAP value.
        /// </summary>
        private double GetVWAP() => _sessionVWAP;

        #endregion

        #region Session Filtering

        /// <summary>
        /// PHASE 12.10: Check if current time is within trading hours.
        /// Matches standalone IsWithinTradingHours() exactly: 09:30-15:30 ET
        /// </summary>
        private bool IsWithinTradingHoursET(DateTime timestamp)
        {
            // Convert to Eastern Time (matching standalone behavior)
            DateTime timeET = TimeZoneInfo.ConvertTime(timestamp, _easternTimeZone);
            TimeSpan currentTimeET = timeET.TimeOfDay;

            // Check if within 09:30-14:30 ET window
            return currentTimeET >= _sessionStartET && currentTimeET <= _sessionEndET;
        }

        #endregion

        #region Williams %R Calculation

        private double CalculateWilliamsR(int period, int barOffset = 0)
        {
            if (_highs == null || _lows == null || _closes == null)
                return double.NaN;

            if (_highs.Length < period + barOffset || _lows.Length < period + barOffset || _closes.Length < period + barOffset)
                return double.NaN;

            double highestHigh = double.MinValue;
            double lowestLow = double.MaxValue;

            for (int i = barOffset; i < period + barOffset; i++)
            {
                if (_highs[i] > highestHigh)
                    highestHigh = _highs[i];
                if (_lows[i] < lowestLow)
                    lowestLow = _lows[i];
            }

            double currentClose = _closes[barOffset];
            double range = highestHigh - lowestLow;

            if (range <= 0)
                return double.NaN;

            double williamsR = ((highestHigh - currentClose) / range) * -100.0;
            return williamsR;
        }

        #endregion

        #region Entry Logic

        private TradeIntent EvaluateEntries(Context context, string evaluationId, DateTime evaluationTime, double wprValue, double emaValue, double atrValue)
        {
            // PHASE 12.10: PARITY MODE - Entry logic matches standalone EXACTLY
            // Standalone uses LEVEL-BASED entries, not cross-based

            string timestampET = context.Timestamp.ToString("yyyy-MM-dd HH:mm:ss");

            // PHASE 12.10: Calculate LEVEL-BASED predicates (not cross-based)
            // Standalone logic from OnBarUpdate:
            //   LONG:  wprValue < Oversold && Close > emaValue
            //   SHORT: wprValue > Overbought && Close < emaValue
            bool IsBullTrend = context.Close > emaValue;
            bool IsBearTrend = context.Close < emaValue;
            bool WPROversold = wprValue < _oversold;      // Level-based: WPR < Oversold
            bool WPROverbought = wprValue > _overbought;   // Level-based: WPR > Overbought

            // PHASE 12.10: VWAP filter logic (matches standalone exactly)
            // Standalone: Close < sessionVWAP - VWAPDeviation (for long)
            // Standalone: Close > sessionVWAP + VWAPDeviation (for short)
            bool vwapLongBias = true;   // Default: pass when VWAP disabled
            bool vwapShortBias = true;  // Default: pass when VWAP disabled
            double vwapValue = 0.0;

            if (_enableVWAPFilter)
            {
                vwapValue = GetVWAP();
                // PHASE 12.10: VWAP deviation in price units (not ATR multiples)
                vwapLongBias = context.Close < vwapValue - _vwapDeviation;
                vwapShortBias = context.Close > vwapValue + _vwapDeviation;
            }

            // Session validity (already checked earlier)
            bool sessionValid = context.SessionGateOpen;

            // PHASE 12.10: LEVEL-BASED entry signals (not cross-based)
            // This matches standalone OnBarUpdate exactly:
            //   if (wprValue < Oversold && Position.MarketPosition == Flat && Close > emaValue && vwapLongBias)
            //   if (wprValue > Overbought && Position.MarketPosition == Flat && Close < emaValue && vwapShortBias)
            bool CanonicalLongEntry = sessionValid && WPROversold && IsBullTrend && vwapLongBias;
            bool CanonicalShortEntry = sessionValid && WPROverbought && IsBearTrend && vwapShortBias;

            // Log mandatory diagnostic instrumentation (PHASE 12.10: Includes all required fields)
            string vwapInfo = _enableVWAPFilter 
                ? $"VWAP={vwapValue:F2}, VWAPDeviation={_vwapDeviation:F2}, VWAPLongBias={vwapLongBias}, VWAPShortBias={vwapShortBias}"
                : "VWAP=DISABLED";
            
            _logger.LogInfo($"[FLUX][MOMENTUM][DIAGNOSTIC] TimestampET={timestampET}, CurrentBar={context.CurrentBar}, " +
                $"WPR={wprValue:F2}, EMA200={emaValue:F2}, ATR1m={atrValue:F2}, ATR15m={_atr15mValue:F2}, Close={context.Close:F2}, " +
                $"{vwapInfo}, " +
                $"SessionValid={sessionValid}, IsBullTrend={IsBullTrend}, IsBearTrend={IsBearTrend}, " +
                $"WPROversold={WPROversold}, WPROverbought={WPROverbought}, " +
                $"CanonicalLongEntry={CanonicalLongEntry}, CanonicalShortEntry={CanonicalShortEntry}");

            // Determine first failing predicate for detailed rejection logging
            string firstFailingPredicate = "NONE";
            string rejectReason = "UNKNOWN";

            if (!CanonicalLongEntry && !CanonicalShortEntry)
            {
                // PHASE 12.10: Check predicates in standalone evaluation order
                if (!sessionValid)
                {
                    firstFailingPredicate = "SESSION_INVALID";
                    rejectReason = "REJECT_OUTSIDE_SESSION_WINDOW";
                }
                else if (!WPROversold && !WPROverbought)
                {
                    firstFailingPredicate = "WPR_NOT_IN_ZONE";
                    rejectReason = "WPR_NOT_OVERSOLD_OR_OVERBOUGHT";
                }
                else if (WPROversold && !IsBullTrend)
                {
                    firstFailingPredicate = "OVERSOLD_BUT_BEAR_TREND";
                    rejectReason = "OVERSOLD_REQUIRES_BULL_TREND";
                }
                else if (WPROverbought && !IsBearTrend)
                {
                    firstFailingPredicate = "OVERBOUGHT_BUT_BULL_TREND";
                    rejectReason = "OVERBOUGHT_REQUIRES_BEAR_TREND";
                }
                else if (_enableVWAPFilter && (WPROversold && !vwapLongBias))
                {
                    firstFailingPredicate = "VWAP_LONG_FILTER_FAIL";
                    rejectReason = "VWAP_FILTER_REJECT_LONG";
                }
                else if (_enableVWAPFilter && (WPROverbought && !vwapShortBias))
                {
                    firstFailingPredicate = "VWAP_SHORT_FILTER_FAIL";
                    rejectReason = "VWAP_FILTER_REJECT_SHORT";
                }
                else
                {
                    firstFailingPredicate = "UNKNOWN_CONDITION";
                    rejectReason = "NO_VALID_ENTRY_OPPORTUNITY";
                }
            }

            // Log final eligibility decision with first failing predicate
            _logger.LogInfo($"[FLUX][MOMENTUM][ELIGIBILITY] EvaluationId={evaluationId}, " +
                $"FinalDecision={(!CanonicalLongEntry && !CanonicalShortEntry ? "REJECTED" : "ELIGIBLE")}, " +
                $"FirstFailingPredicate={firstFailingPredicate}, RejectReason={rejectReason}");

            // PHASE 12.10: Long entry - WPR < Oversold AND Close > EMA200 (level-based)
            if (CanonicalLongEntry)
            {
                // PHASE 12.10: Calculate stop/target in PRICE SPACE (no tick quantization)
                // In parity mode, use FIXED stop distance (80 points) to match standalone
                // Standalone uses: stopPrice = Close[0] - TrailingDistance (TrailingDistance = 80)
                double stopDistance = _parityMode ? _fixedStopDistance : atrValue * _stopLossAtrMultiplier;
                double targetDistance = atrValue * _profitTargetAtrMultiplier;
                double entryPrice = context.Close;
                double stopPrice = entryPrice - stopDistance;
                double targetPrice = entryPrice + targetDistance;

                // Convert to ticks for TradeIntent (but these are for logging/validation only)
                int stopTicks = (int)Math.Round(stopDistance / context.TickSize);
                int targetTicks = (int)Math.Round(targetDistance / context.TickSize);

                string setupId = evaluationId.Replace("|EVAL|", "|LONG|");

                _logger.LogInfo($"[FLUX][MOMENTUM][INTENT] EvaluationId={evaluationId}, SetupId={setupId}, Direction=LONG, " +
                    $"TriggerBar={context.CurrentBar}, WPR={wprValue:F2}, " +
                    $"EntryPrice={entryPrice:F2}, StopPrice={stopPrice:F2}, TargetPrice={targetPrice:F2}, " +
                    $"StopDistance={stopDistance:F4}, TargetDistance={targetDistance:F4}");

                return TradeIntent.Long(
                    ModuleId,
                    stopTicks,
                    targetTicks,
                    "Momentum_WPR_Mean_Reversion",
                    "WPR_LEVEL_LONG",
                    evaluationId,
                    setupId,
                    stopPrice,      // PHASE 12.10: Explicit stop price
                    targetPrice);   // PHASE 12.10: Explicit target price
            }

            // PHASE 12.10: Short entry - WPR > Overbought AND Close < EMA200 (level-based)
            if (CanonicalShortEntry)
            {
                // PHASE 12.10: Calculate stop/target in PRICE SPACE (no tick quantization)
                // In parity mode, use FIXED stop distance (80 points) to match standalone
                // Standalone uses: stopPrice = Close[0] + TrailingDistance (TrailingDistance = 80)
                double stopDistance = _parityMode ? _fixedStopDistance : atrValue * _stopLossAtrMultiplier;
                double targetDistance = atrValue * _profitTargetAtrMultiplier;
                double entryPrice = context.Close;
                double stopPrice = entryPrice + stopDistance;
                double targetPrice = entryPrice - targetDistance;

                // Convert to ticks for TradeIntent (but these are for logging/validation only)
                int stopTicks = (int)Math.Round(stopDistance / context.TickSize);
                int targetTicks = (int)Math.Round(targetDistance / context.TickSize);

                string setupId = evaluationId.Replace("|EVAL|", "|SHORT|");

                _logger.LogInfo($"[FLUX][MOMENTUM][INTENT] EvaluationId={evaluationId}, SetupId={setupId}, Direction=SHORT, " +
                    $"TriggerBar={context.CurrentBar}, WPR={wprValue:F2}, " +
                    $"EntryPrice={entryPrice:F2}, StopPrice={stopPrice:F2}, TargetPrice={targetPrice:F2}, " +
                    $"StopDistance={stopDistance:F4}, TargetDistance={targetDistance:F4}");

                return TradeIntent.Short(
                    ModuleId,
                    stopTicks,
                    targetTicks,
                    "Momentum_WPR_Mean_Reversion",
                    "WPR_LEVEL_SHORT",
                    evaluationId,
                    setupId,
                    stopPrice,      // PHASE 12.10: Explicit stop price
                    targetPrice);   // PHASE 12.10: Explicit target price
            }

            // No valid entry - log detailed rejection
            return Reject(evaluationId, rejectReason);
        }

        #endregion

        #region Stop/Target Calculation

        // PHASE 12.10: Stop/target calculation methods removed.
        // Stop and target prices are now calculated in PRICE SPACE directly in EvaluateEntries().
        // No tick quantization, no ceiling/floor, no clamps.
        // This matches standalone behavior: SetStopLoss(signal, CalculationMode.Price, stopPrice, false)

        #endregion

        #region Rejection Tracking

        private TradeIntent Reject(string evaluationId, string reason)
        {
            if (!_rejectCounts.ContainsKey(reason))
                _rejectCounts[reason] = 0;
            _rejectCounts[reason]++;

            // PHASE 12.5: Extract bar index from evaluationId for consistent logging
            // Format: {tradingDay}-{currentTime}|EVAL|{barIndex}
            string[] parts = evaluationId.Split('|');
            string barIndexStr = parts.Length >= 3 ? parts[2] : "UNKNOWN";

            _logger.LogInfo($"[FLUX][MOMENTUM][REJECT] EvaluationId={evaluationId}, CurrentBar={barIndexStr}, RejectionReason={reason}");

            return TradeIntent.None;
        }

        /// <summary>
        /// Get reject reason summary for logging.
        /// </summary>
        public string GetRejectSummary()
        {
            if (_rejectCounts.Count == 0)
                return "No rejections recorded";

            var sorted = _rejectCounts.OrderByDescending(kvp => kvp.Value);
            var top5 = sorted.Take(5);
            return string.Join(", ", top5.Select(kvp => $"{kvp.Key}={kvp.Value}"));
        }

        #endregion
    }
}