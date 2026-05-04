#region Using declarations
using System;
using System.Collections.Generic;
using System.Linq;
using NinjaTrader.NinjaScript.Strategies.Flux.Core;
#endregion

namespace NinjaTrader.NinjaScript.Strategies.Flux.Modules.Range
{
    /// <summary>
    /// Range Module for Flux v1.
    /// Implements IModule contract - emits TradeIntents only, never places orders.
    /// 
    /// IMPORTANT: This module adapts the validated Phase 3 Iteration 04 Range logic.
    /// The trading logic is NOT modified - only refactored to emit intents.
    /// </summary>
    public class RangeModule : IModule
    {
        #region Module Identity

        public string ModuleId => "Range";

        #endregion

        #region Configuration

        private readonly Config _config;
        private readonly Logger _logger;

        // Range parameters (from validated Phase 3 Iter 04)
        private readonly int _atrPeriod;
        private readonly int _compressionLookback;
        private readonly double _compressionPercentile;
        private readonly int _rangeLookback;
        private readonly double _trendThreshold;
        private readonly int _displacementThreshold;
        private readonly int _maxRangeAge;

        // Entry parameters
        private readonly int _probeBufferTicks;
        private readonly int _confirmOffsetTicks;
        private readonly double _wickMinRatio;
        private readonly double _minBodyRatio;
        private readonly int _hardBreakBufferTicks;
        private readonly int _recalcDriftLimit;
        private readonly int _cooldownBars;

        // Exit parameters
        private readonly double _stopDistanceMultiplier;
        private readonly double _targetDistanceMultiplier;

        // Reject reason tracking (PHASE 6: Range Reject Diagnostics)
        private readonly System.Collections.Generic.Dictionary<string, int> _rejectCounts;

        #endregion

        #region Internal State

        // Range tracking
        private double _rangeHigh = double.MinValue;
        private double _rangeLow = double.MaxValue;
        private double _rangeMid = 0;
        private int _rangeAge = 0;
        private int _rangeStartBar = -1;
        private bool _rangeValid = false;
        private List<double> _recentATR = new List<double>();

        // Probe/confirm tracking
        private int _probeBarIndex = -1;
        private double _probeBarHigh = 0;
        private double _probeBarLow = 0;
        private double _probeBarClose = 0;
        private bool _probeBarFormed = false;
        private string _probeBarSide = "";

        // Cooldown tracking
        private bool _entryCooldownActive = false;
        private int _entryCooldownRemaining = 0;
        private bool _longSideLockout = false;
        private bool _shortSideLockout = false;
        private int _longFailedAttempts = 0;
        private int _shortFailedAttempts = 0;

        // Internal tracking
        private int _lastEvaluatedBar = -1;
        private int _consecutiveLosses = 0;
        private const int MAX_CONSECUTIVE_LOSSES = 3;

        // Price data cache (populated by caller)
        private double[] _highs;
        private double[] _lows;
        private double[] _opens;
        private double[] _closes;
        private double[] _atrValues;
        private double[] _ema9Values;
        private double[] _ema21Values;

        #endregion

        #region Constructor

        public RangeModule(Config config, Logger logger)
        {
            _config = config ?? throw new ArgumentNullException(nameof(config));
            _logger = logger ?? throw new ArgumentNullException(nameof(logger));

            // Initialize parameters from config (Phase 3 Iter 04 validated values)
            _atrPeriod = _config.ATRPeriod;
            _compressionLookback = _config.RangeCompressionLookback;
            _compressionPercentile = _config.RangeCompressionPercentile;
            _rangeLookback = _config.RangeLookback;
            _trendThreshold = 1.5; // ATR multiplier for trend detection
            _displacementThreshold = 5; // Ticks beyond range
            _maxRangeAge = 50;

            _probeBufferTicks = 3;
            _confirmOffsetTicks = 2;
            _wickMinRatio = 0.5;
            _minBodyRatio = 0.3;
            _hardBreakBufferTicks = 5;
            _recalcDriftLimit = 3;
            _cooldownBars = 5;

            _stopDistanceMultiplier = _config.RangeStopMultiplier;
            _targetDistanceMultiplier = _config.RangeTargetMultiplier;

            // Initialize reject reason tracking
            _rejectCounts = new System.Collections.Generic.Dictionary<string, int>();
        }

        #endregion

        #region IModule Implementation

        /// <summary>
        /// Evaluates the current bar for a Range trading opportunity.
        /// Returns TradeIntent.None if no valid setup, or a Long/Short intent.
        ///
        /// CRITICAL: This method must be deterministic and side-effect free (except internal state).
        /// </summary>
        public TradeIntent Evaluate(Context context)
        {
            // Generate EvaluationId for this evaluation cycle (direction unknown)
            string tradingDay = context.Timestamp.ToString("yyyyMMdd");
            string currentTime = context.Timestamp.ToString("HHmm");
            string evaluationId = $"{tradingDay}-{currentTime}|EVAL|{context.CurrentBar}";

            // PHASE 6.6: Log evaluation start with EvaluationId
            _logger.LogInfo($"[FLUX][RANGE][EVAL_START] EvaluationId={evaluationId}, CurrentBar={context.CurrentBar}, IsFlat={context.IsFlat}, IsHighVol={context.IsHighVol}, AllowRangeStrategy={!context.IsHighVol}, ConsecutiveLosses={_consecutiveLosses}, CooldownActive={_entryCooldownActive}");

            // Prevent double-evaluation on same bar
            if (_lastEvaluatedBar == context.CurrentBar)
                return Reject(evaluationId, "BAR_ALREADY_EVALUATED");

            _lastEvaluatedBar = context.CurrentBar;

            // 1. Self-gate: Range module must return None in HIGH volatility
            if (context.IsHighVol)
            {
                return Reject(evaluationId, "HIGH_VOLATILITY_SELF_GATE");
            }

            // 2. Must be flat to generate entry signals
            if (!context.IsFlat)
            {
                return Reject(evaluationId, "POSITION_NOT_FLAT");
            }

            // 3. Update cooldowns
            UpdateCooldowns();

            // 4. Check if suppressed due to consecutive losses
            if (_consecutiveLosses >= MAX_CONSECUTIVE_LOSSES)
            {
                return Reject(evaluationId, "CONSECUTIVE_LOSSES_SUPPRESSION");
            }

            // 5. Update range and regime
            UpdateRangeAndRegime(context);

            // 6. Range eligibility is handled upstream by RegimeGate
            // Do not self-gate here


            // 7. Evaluate entry opportunities
            return EvaluateEntries(context, evaluationId);
        }

        /// <summary>
        /// Notification when a trade is opened.
        /// </summary>
        public void OnTradeOpened(TradeMetadata trade)
        {
            // Reset probe tracking when trade opens
            ResetProbeTracking();
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
            }
            else
            {
                _consecutiveLosses = 0;
            }

            // Apply cooldown after trade
            _entryCooldownActive = true;
            _entryCooldownRemaining = _cooldownBars;
        }

        /// <summary>
        /// Record a reject reason and return TradeIntent.None
        /// </summary>
        private TradeIntent Reject(string evaluationId, string reason)
        {
            if (!_rejectCounts.ContainsKey(reason))
                _rejectCounts[reason] = 0;
            _rejectCounts[reason]++;

            // PHASE 6.6: Log rejection with EvaluationId
            _logger.LogInfo($"[FLUX][RANGE][REJECT] EvaluationId={evaluationId}, CurrentBar={_lastEvaluatedBar}, RejectionReason={reason}, IsFlat=true, IsHighVol=false, AllowRangeStrategy=true");

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
            ResetRange();
            ResetProbeTracking();
            _entryCooldownActive = false;
            _entryCooldownRemaining = 0;
            _longSideLockout = false;
            _shortSideLockout = false;
            _longFailedAttempts = 0;
            _shortFailedAttempts = 0;
            _consecutiveLosses = 0;
            _lastEvaluatedBar = -1;
            _recentATR.Clear();
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
            _atrValues = atrValues;
            _ema9Values = ema9Values;
            _ema21Values = ema21Values;
        }

        #endregion

        #region Range Detection (Adapted from Phase 3 Iter 04)

        private void UpdateRangeAndRegime(Context context)
        {
            // Update ATR history
            if (_atrValues != null && _atrValues.Length > 0 && _atrValues[0] > 0)
            {
                _recentATR.Add(_atrValues[0]);
                if (_recentATR.Count > _compressionLookback)
                    _recentATR.RemoveAt(0);
            }

            // Update range boundaries
            UpdateRangeBoundaries(context);

            // Validate range structure
            ValidateRangeStructure(context);

            // Evaluate regime conditions
            EvaluateRegimeConditions(context);
        }

        private void UpdateRangeBoundaries(Context context)
        {
            if (_highs == null || _lows == null || _highs.Length < _rangeLookback)
                return;

            double currentHigh = double.MinValue;
            double currentLow = double.MaxValue;

            int lookback = Math.Min(_rangeLookback, _highs.Length);
            for (int i = 0; i < lookback; i++)
            {
                if (_highs[i] > currentHigh)
                    currentHigh = _highs[i];
                if (_lows[i] < currentLow)
                    currentLow = _lows[i];
            }

            // Initialize range
            if (_rangeStartBar < 0)
            {
                _rangeHigh = currentHigh;
                _rangeLow = currentLow;
                _rangeMid = (_rangeHigh + _rangeLow) / 2.0;
                _rangeStartBar = context.CurrentBar;
                _rangeAge = 0;
                return;
            }

            // Check for drift
            double highDrift = Math.Abs(_rangeHigh - currentHigh);
            double lowDrift = Math.Abs(_rangeLow - currentLow);
            bool hasDrift = highDrift > (_recalcDriftLimit * context.TickSize) ||
                           lowDrift > (_recalcDriftLimit * context.TickSize);

            if (hasDrift && !_rangeValid)
            {
                // Reset range
                _rangeHigh = currentHigh;
                _rangeLow = currentLow;
                _rangeMid = (_rangeHigh + _rangeLow) / 2.0;
                _rangeStartBar = context.CurrentBar;
                _rangeAge = 0;
            }
            else
            {
                // Update range (expand, don't shrink)
                _rangeHigh = Math.Max(_rangeHigh, currentHigh);
                _rangeLow = Math.Min(_rangeLow, currentLow);
                _rangeMid = (_rangeHigh + _rangeLow) / 2.0;
                _rangeAge = context.CurrentBar - _rangeStartBar;
            }
        }

        private void ValidateRangeStructure(Context context)
        {
            bool wasValid = _rangeValid;

            if (_rangeHigh <= _rangeLow)
            {
                _rangeValid = false;
                if (wasValid) ResetRange();
                return;
            }

            if (_rangeAge > _maxRangeAge)
            {
                _rangeValid = false;
                if (wasValid) ResetRange();
                return;
            }

            double rangeSize = _rangeHigh - _rangeLow;
            double minRangeSize = context.TickSize * 2;
            if (rangeSize < minRangeSize)
            {
                _rangeValid = false;
                if (wasValid) ResetRange();
                return;
            }

            _rangeValid = true;
        }

        private void EvaluateRegimeConditions(Context context)
        {
            // Compression detection
            bool compressionDetected = IsCompressionDetected();

            // Trend detection
            bool isTrending = IsTrendingConditions(context);

            // Range broken detection
            bool rangeBroken = IsRangeBroken(context);

        }

        private bool IsCompressionDetected()
        {
            if (_recentATR.Count < _compressionLookback / 2)
                return false;

            if (_atrValues == null || _atrValues.Length == 0)
                return false;

            double currentATR = _atrValues[0];
            if (currentATR <= 0)
                return false;

            var sortedATR = _recentATR.OrderBy(x => x).ToList();
            int percentileIndex = (int)(sortedATR.Count * _compressionPercentile);
            percentileIndex = Math.Max(0, Math.Min(percentileIndex, sortedATR.Count - 1));
            double percentileATR = sortedATR[percentileIndex];

            return currentATR < percentileATR;
        }

        private bool IsTrendingConditions(Context context)
        {
            if (_ema9Values == null || _ema21Values == null || _atrValues == null)
                return false;

            if (_ema9Values.Length == 0 || _ema21Values.Length == 0 || _atrValues.Length == 0)
                return false;

            double ema9Value = _ema9Values[0];
            double ema21Value = _ema21Values[0];
            double atrValue = _atrValues[0];

            if (atrValue <= 0)
                return false;

            double separation = Math.Abs(ema9Value - ema21Value);
            double threshold = atrValue * _trendThreshold;

            return separation > threshold;
        }

        private bool IsRangeBroken(Context context)
        {
            double displacement = _displacementThreshold * context.TickSize;
            bool brokenHigh = context.Close > (_rangeHigh + displacement);
            bool brokenLow = context.Close < (_rangeLow - displacement);

            return brokenHigh || brokenLow;
        }

        private void ResetRange()
        {
            _rangeHigh = double.MinValue;
            _rangeLow = double.MaxValue;
            _rangeMid = 0;
            _rangeAge = 0;
            _rangeStartBar = -1;
            _rangeValid = false;
        }

        #endregion

        #region Entry Logic (Adapted from Phase 3 Iter 04)

        private TradeIntent EvaluateEntries(Context context, string evaluationId)
        {
            // Check cooldown
            if (_entryCooldownActive)
            {
                return Reject(evaluationId, "ENTRY_COOLDOWN_ACTIVE");
            }

            // Check for long entry
            if (!_longSideLockout)
            {
                var longIntent = EvaluateLongEntry(context, evaluationId);
                if (longIntent.Direction == TradeDirection.Long)
                    return longIntent;
            }

            // Check for short entry
            if (!_shortSideLockout)
            {
                var shortIntent = EvaluateShortEntry(context, evaluationId);
                if (shortIntent.Direction == TradeDirection.Short)
                    return shortIntent;
            }

            // No valid entry found
            return Reject(evaluationId, "NO_VALID_ENTRY_OPPORTUNITY");
        }

        private TradeIntent EvaluateLongEntry(Context context, string evaluationId)
        {
            // Trigger Zone: Price trades within lower trigger band
            double triggerBandUpper = _rangeLow + (_probeBufferTicks * context.TickSize);
            bool withinTriggerBand = context.Low <= triggerBandUpper;

            if (!withinTriggerBand)
            {
                if (_probeBarFormed && _probeBarSide == "LONG")
                    ResetProbeTracking();
                return TradeIntent.None;
            }

            // Check for probe bar formation
            if (!_probeBarFormed || _probeBarSide != "LONG")
            {
                if (IsProbeBarLong(context))
                {
                    _probeBarFormed = true;
                    _probeBarSide = "LONG";
                    _probeBarIndex = context.CurrentBar;
                    _probeBarHigh = context.High;
                    _probeBarLow = context.Low;
                    _probeBarClose = context.Close;
                }
            }
            else if (_probeBarSide == "LONG")
            {
                // Confirmation bar must be the immediate next bar
                if (context.CurrentBar != _probeBarIndex + 1)
                {
                    ResetProbeTracking();
                    return TradeIntent.None;
                }

                // Check for confirmation bar
                if (IsConfirmationBarLong(context))
                {
                    // Entry signal fires - emit TradeIntent
                    int stopTicks = CalculateStopTicks(context);
                    int targetTicks = CalculateTargetTicks(context);

                    ResetProbeTracking();

                    // PHASE 6.6: Generate SetupId with known direction and log intent emission
                    string setupId = evaluationId.Replace("|EVAL|", "|LONG|");
                    double entryPrice = context.Close;
                    double stopPrice = entryPrice - (stopTicks * context.TickSize);
                    double targetPrice = entryPrice + (targetTicks * context.TickSize);

                    _logger.LogInfo($"[FLUX][RANGE][INTENT] EvaluationId={evaluationId}, SetupId={setupId}, Direction=LONG, TriggerBar={context.CurrentBar}, EntryPrice={entryPrice:F2}, StopPrice={stopPrice:F2}, TargetPrice={targetPrice:F2}, PlanName=Range_Trail_1R");

                    return TradeIntent.Long(
                        ModuleId,
                        stopTicks,
                        targetTicks,
                        "Range_Trail_1R",
                        "LONG_CONFIRM",
                        evaluationId,
                        setupId);
                }
                else
                {
                    // Check if probe was invalidated
                    if (IsProbeInvalidatedLong(context))
                    {
                        _longFailedAttempts++;
                        if (_longFailedAttempts >= 2)
                        {
                            _longSideLockout = true;
                        }
                        else
                        {
                            _entryCooldownActive = true;
                            _entryCooldownRemaining = _cooldownBars;
                        }
                        ResetProbeTracking();
                    }
                }
            }

            return TradeIntent.None;
        }

        private TradeIntent EvaluateShortEntry(Context context, string evaluationId)
        {
            // Trigger Zone: Price trades within upper trigger band
            double triggerBandLower = _rangeHigh - (_probeBufferTicks * context.TickSize);
            bool withinTriggerBand = context.High >= triggerBandLower;

            if (!withinTriggerBand)
            {
                if (_probeBarFormed && _probeBarSide == "SHORT")
                    ResetProbeTracking();
                return TradeIntent.None;
            }

            // Check for probe bar formation
            if (!_probeBarFormed || _probeBarSide != "SHORT")
            {
                if (IsProbeBarShort(context))
                {
                    _probeBarFormed = true;
                    _probeBarSide = "SHORT";
                    _probeBarIndex = context.CurrentBar;
                    _probeBarHigh = context.High;
                    _probeBarLow = context.Low;
                    _probeBarClose = context.Close;
                }
            }
            else if (_probeBarSide == "SHORT")
            {
                // Confirmation bar must be the immediate next bar
                if (context.CurrentBar != _probeBarIndex + 1)
                {
                    ResetProbeTracking();
                    return TradeIntent.None;
                }

                // Check for confirmation bar
                if (IsConfirmationBarShort(context))
                {
                    // Entry signal fires - emit TradeIntent
                    int stopTicks = CalculateStopTicks(context);
                    int targetTicks = CalculateTargetTicks(context);

                    ResetProbeTracking();

                    // PHASE 6.6: Generate SetupId with known direction and log intent emission
                    string setupId = evaluationId.Replace("|EVAL|", "|SHORT|");
                    double entryPrice = context.Close;
                    double stopPrice = entryPrice + (stopTicks * context.TickSize);
                    double targetPrice = entryPrice - (targetTicks * context.TickSize);

                    _logger.LogInfo($"[FLUX][RANGE][INTENT] EvaluationId={evaluationId}, SetupId={setupId}, Direction=SHORT, TriggerBar={context.CurrentBar}, EntryPrice={entryPrice:F2}, StopPrice={stopPrice:F2}, TargetPrice={targetPrice:F2}, PlanName=Range_Trail_1R");

                    return TradeIntent.Short(
                        ModuleId,
                        stopTicks,
                        targetTicks,
                        "Range_Trail_1R",
                        "SHORT_CONFIRM",
                        evaluationId,
                        setupId);
                }
                else
                {
                    // Check if probe was invalidated
                    if (IsProbeInvalidatedShort(context))
                    {
                        _shortFailedAttempts++;
                        if (_shortFailedAttempts >= 2)
                        {
                            _shortSideLockout = true;
                        }
                        else
                        {
                            _entryCooldownActive = true;
                            _entryCooldownRemaining = _cooldownBars;
                        }
                        ResetProbeTracking();
                    }
                }
            }

            return TradeIntent.None;
        }

        #endregion

        #region Entry Helpers (Adapted from Phase 3 Iter 04)

        private bool IsProbeBarLong(Context context)
        {
            double triggerBandUpper = _rangeLow + (_probeBufferTicks * context.TickSize);
            bool makesLow = context.Low <= triggerBandUpper;
            bool closesInside = context.Close > _rangeLow;

            double upperWick = context.High - Math.Max(context.Open, context.Close);
            double lowerWick = Math.Min(context.Open, context.Close) - context.Low;
            double atrValue = _atrValues != null && _atrValues.Length > 0 ? _atrValues[0] : 1.0;
            bool wickDominance = lowerWick >= upperWick && lowerWick >= (_wickMinRatio * atrValue);

            return makesLow && closesInside && wickDominance;
        }

        private bool IsProbeBarShort(Context context)
        {
            double triggerBandLower = _rangeHigh - (_probeBufferTicks * context.TickSize);
            bool makesHigh = context.High >= triggerBandLower;
            bool closesInside = context.Close < _rangeHigh;

            double upperWick = context.High - Math.Max(context.Open, context.Close);
            double lowerWick = Math.Min(context.Open, context.Close) - context.Low;
            double atrValue = _atrValues != null && _atrValues.Length > 0 ? _atrValues[0] : 1.0;
            bool wickDominance = upperWick >= lowerWick && upperWick >= (_wickMinRatio * atrValue);

            return makesHigh && closesInside && wickDominance;
        }

        private bool IsConfirmationBarLong(Context context)
        {
            bool opensInside = context.Open >= _probeBarLow && context.Open <= _probeBarHigh;
            double confirmLevel = _rangeLow + (_confirmOffsetTicks * context.TickSize);
            bool closesAbove = context.Close > _probeBarClose && context.Close > confirmLevel;

            double bodySize = Math.Abs(context.Close - context.Open);
            double rangeSize = context.High - context.Low;
            bool bodyRatio = rangeSize > 0 && (bodySize / rangeSize) >= _minBodyRatio;

            bool notAboveMid = context.Close <= _rangeMid;

            return opensInside && closesAbove && bodyRatio && notAboveMid;
        }

        private bool IsConfirmationBarShort(Context context)
        {
            bool opensInside = context.Open >= _probeBarLow && context.Open <= _probeBarHigh;
            double confirmLevel = _rangeHigh - (_confirmOffsetTicks * context.TickSize);
            bool closesBelow = context.Close < _probeBarClose && context.Close < confirmLevel;

            double bodySize = Math.Abs(context.Close - context.Open);
            double rangeSize = context.High - context.Low;
            bool bodyRatio = rangeSize > 0 && (bodySize / rangeSize) >= _minBodyRatio;

            bool notBelowMid = context.Close >= _rangeMid;

            return opensInside && closesBelow && bodyRatio && notBelowMid;
        }

        private bool IsProbeInvalidatedLong(Context context)
        {
            double hardBreakLevel = _rangeLow - (_hardBreakBufferTicks * context.TickSize);
            return context.Close < hardBreakLevel;
        }

        private bool IsProbeInvalidatedShort(Context context)
        {
            double hardBreakLevel = _rangeHigh + (_hardBreakBufferTicks * context.TickSize);
            return context.Close > hardBreakLevel;
        }

        #endregion

        #region Stop/Target Calculation

        private int CalculateStopTicks(Context context)
        {
            double rangeSize = _rangeHigh - _rangeLow;
            double stopDistance = rangeSize * _stopDistanceMultiplier;
            int stopTicks = (int)Math.Ceiling(stopDistance / context.TickSize);

            // Clamp to reasonable values
            stopTicks = Math.Max(4, Math.Min(stopTicks, 100));
            return stopTicks;
        }

        private int CalculateTargetTicks(Context context)
        {
            double rangeSize = _rangeHigh - _rangeLow;
            double targetDistance = rangeSize * _targetDistanceMultiplier;
            int targetTicks = (int)Math.Ceiling(targetDistance / context.TickSize);

            // Clamp to reasonable values
            targetTicks = Math.Max(4, Math.Min(targetTicks, 200));
            return targetTicks;
        }

        #endregion

        #region Cooldown Tracking

        private void UpdateCooldowns()
        {
            if (_entryCooldownActive && _entryCooldownRemaining > 0)
            {
                _entryCooldownRemaining--;
                if (_entryCooldownRemaining <= 0)
                {
                    _entryCooldownActive = false;
                }
            }
        }

        private void ResetProbeTracking()
        {
            _probeBarFormed = false;
            _probeBarSide = "";
            _probeBarIndex = -1;
            _probeBarHigh = 0;
            _probeBarLow = 0;
            _probeBarClose = 0;
        }

        #endregion
    }
}

