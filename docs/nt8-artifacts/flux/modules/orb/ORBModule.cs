#region Using declarations
using System;
using System.Collections.Generic;
using System.Linq;
using NinjaTrader.NinjaScript.Strategies.Flux.Core;
#endregion

namespace NinjaTrader.NinjaScript.Strategies.Flux.Modules.ORB
{
    /// <summary>
    /// ORB (Opening Range Breakout) Module for Flux v1.
    /// 
    /// Captures directional momentum from the first 15-minute range of the NY session.
    /// Records 9:30-9:45 ET high/low, then trades breakouts with VWAP alignment.
    /// 
    /// Design:
    /// - Win-rate driven (~60-70% WR, ~1:1 R:R) complements Momentum's R:R profile
    /// - Max 1 trade per day
    /// - Works on 1-minute bars (accumulates 15-min range internally)
    /// - Self-contained VWAP calculation
    /// - Explicit price-space stop/target (no tick quantization)
    /// </summary>
    public class ORBModule : IModule
    {
        #region Module Identity

        public string ModuleId => "ORB";

        #endregion

        #region Configuration

        private readonly Config _config;
        private readonly Logger _logger;

        // Time windows (Eastern Time)
        private readonly TimeSpan _rangeStartET = new TimeSpan(9, 30, 0);    // 09:30 ET
        private readonly TimeSpan _rangeEndET = new TimeSpan(9, 45, 0);      // 09:45 ET
        private readonly TimeSpan _sessionEndET = new TimeSpan(14, 30, 0);   // 14:30 ET - stop taking new entries
        private readonly TimeZoneInfo _easternTimeZone;

        // Parameters from config
        private readonly double _minRangePoints;
        private readonly double _maxRangePoints;
        private readonly double _maxStopPoints;
        private readonly double _stopBuffer;
        private readonly double _targetMultiplier;
        private readonly bool _enableVWAPFilter;
        private readonly bool _enableBreakEven;
        private readonly double _beTriggerR;
        private readonly double _breakoutBuffer;

        #endregion

        #region Internal State

        // State machine
        private ORBState _state;

        // Opening range tracking
        private double _rangeHigh;
        private double _rangeLow;
        private double _rangeSize;
        private double _rangeMid;
        private bool _rangeFormed;

        // Trade tracking
        private bool _tradedToday;

        // Session date tracking
        private DateTime _lastSessionDate;

        // VWAP state (session-based, self-contained)
        private double _sessionVWAP;
        private double _cumulativePriceVolume;
        private double _cumulativeVolume;

        // Price data cache (populated by caller)
        private double[] _highs;
        private double[] _lows;
        private double[] _opens;
        private double[] _closes;
        private double[] _atrValues;
        private double[] _volumes;
        private bool _isFirstBarOfSession;

        // PHASE 5: 15-min ATR(14) for ATR-scaled filters / stops / ceiling.
        // 0 = not yet warm; ATR-dependent gates fail-closed (skip / reject)
        // when this is non-positive.
        private double _atr15m;

        // Warmup tracking
        private bool _warmupCompleteLogged;

        // Reject reason tracking
        private readonly Dictionary<string, int> _rejectCounts;

        #endregion

        #region State Enum

        private enum ORBState
        {
            Idle,           // Waiting for session start
            FormingRange,   // Accumulating 9:30-9:45 range
            Watching,       // Range formed, watching for breakout
            Triggered,      // Trade emitted for today
            NoTrigger       // No trade today (range invalid or session ended)
        }

        #endregion

        #region Constructor

        public ORBModule(Config config, Logger logger)
        {
            _config = config ?? throw new ArgumentNullException(nameof(config));
            _logger = logger ?? throw new ArgumentNullException(nameof(logger));

            // Load parameters from config
            _minRangePoints = _config.ORBMinRangePoints;
            _maxRangePoints = _config.ORBMaxRangePoints;
            _maxStopPoints = _config.ORBMaxStopPoints;
            _stopBuffer = _config.ORBStopBuffer;
            _targetMultiplier = _config.ORBTargetMultiplier;
            _enableVWAPFilter = _config.ORBEnableVWAPFilter;
            _enableBreakEven = _config.ORBEnableBreakEven;
            _beTriggerR = _config.ORBBETriggerR;
            _breakoutBuffer = _config.ORBBreakoutBuffer;

            // Initialize Eastern timezone
            try
            {
                _easternTimeZone = TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");
            }
            catch
            {
                _easternTimeZone = TimeZoneInfo.FindSystemTimeZoneById("America/New_York");
            }

            _rejectCounts = new Dictionary<string, int>();

            // Initialize to idle
            ResetSessionState();
        }

        #endregion

        #region IModule Implementation

        public TradeIntent Evaluate(Context context)
        {
            DateTime evaluationTime = context.Timestamp;
            int evaluationBar = context.CurrentBar;

            string tradingDay = evaluationTime.ToString("yyyyMMdd");
            string currentTime = evaluationTime.ToString("HHmm");
            string evaluationId = $"{tradingDay}-{currentTime}|EVAL|{evaluationBar}";

            // Check for session reset
            CheckSessionReset(context);

            // Update VWAP on every bar (needed for filter)
            if (_enableVWAPFilter)
            {
                UpdateVWAP(context);
            }

            // Convert to ET for time-based logic
            DateTime timeET = TimeZoneInfo.ConvertTime(evaluationTime, _easternTimeZone);
            TimeSpan currentTimeET = timeET.TimeOfDay;

            // State machine transitions
            switch (_state)
            {
                case ORBState.Idle:
                    return HandleIdle(context, evaluationId, currentTimeET);

                case ORBState.FormingRange:
                    return HandleFormingRange(context, evaluationId, currentTimeET);

                case ORBState.Watching:
                    return HandleWatching(context, evaluationId, currentTimeET);

                case ORBState.Triggered:
                    return Reject(evaluationId, "ALREADY_TRIGGERED_TODAY");

                case ORBState.NoTrigger:
                    return Reject(evaluationId, "NO_TRIGGER_TODAY");

                default:
                    return Reject(evaluationId, "UNKNOWN_STATE");
            }
        }

        public void OnTradeOpened(TradeMetadata trade)
        {
            _logger.LogDebug($"[FLUX][ORB] Trade opened: {trade.Direction} @ {trade.EntryPrice:F2}");
        }

        public void OnTradeClosed(TradeResult result)
        {
            _logger.LogDebug($"[FLUX][ORB] Trade closed: PnL={result.RealizedPnL:F2}, R={result.RMultiple:F2}");
        }

        public void ResetDaily()
        {
            ResetSessionState();
            _warmupCompleteLogged = false;
            _rejectCounts.Clear();
        }

        #endregion

        #region Price Data Interface

        /// <summary>
        /// Sets the price data arrays for evaluation.
        /// Called by FluxV1Strategy before Evaluate.
        /// </summary>
        /// <param name="atr15m">
        /// PHASE 5: Latest 15-min ATR(14) value (or 0 if the 15-min series
        /// is not yet warm). Used by Opt 1 (range filter), Opt 2 (stop cap),
        /// and Opt 4 (15m ATR ceiling).
        /// </param>
        public void SetPriceData(
            double[] highs, double[] lows, double[] opens, double[] closes,
            double[] atrValues, double[] volumes, bool isFirstBarOfSession,
            double atr15m = 0.0)
        {
            _highs = highs;
            _lows = lows;
            _opens = opens;
            _closes = closes;
            _atrValues = atrValues;
            _volumes = volumes;
            _isFirstBarOfSession = isFirstBarOfSession;
            _atr15m = atr15m;
        }

        #endregion

        #region State Machine Handlers

        /// <summary>
        /// IDLE: Waiting for 9:30 ET to start forming the range.
        /// </summary>
        private TradeIntent HandleIdle(Context context, string evaluationId, TimeSpan currentTimeET)
        {
            if (currentTimeET >= _rangeStartET && currentTimeET < _rangeEndET)
            {
                // Transition to FormingRange
                _state = ORBState.FormingRange;
                _rangeHigh = context.High;
                _rangeLow = context.Low;

                _logger.LogInfo($"[FLUX][ORB][RANGE_START] EvaluationId={evaluationId}, " +
                    $"TimeET={currentTimeET}, InitialHigh={_rangeHigh:F2}, InitialLow={_rangeLow:F2}");

                return Reject(evaluationId, "RANGE_FORMING");
            }

            // If we're already past 9:45 and never formed, no trade today
            if (currentTimeET >= _rangeEndET)
            {
                _state = ORBState.NoTrigger;
                _logger.LogInfo($"[FLUX][ORB][MISSED_RANGE] TimeET={currentTimeET}, missed formation window");
                return Reject(evaluationId, "MISSED_RANGE_WINDOW");
            }

            return Reject(evaluationId, "BEFORE_RANGE_WINDOW");
        }

        /// <summary>
        /// FORMING_RANGE: Accumulating high/low during 9:30-9:45 ET.
        /// </summary>
        private TradeIntent HandleFormingRange(Context context, string evaluationId, TimeSpan currentTimeET)
        {
            // Still within formation window - update range
            if (currentTimeET < _rangeEndET)
            {
                if (context.High > _rangeHigh)
                    _rangeHigh = context.High;
                if (context.Low < _rangeLow)
                    _rangeLow = context.Low;

                return Reject(evaluationId, "RANGE_FORMING");
            }

            // Range formation complete (first bar at or after 9:45)
            _rangeSize = _rangeHigh - _rangeLow;
            _rangeMid = (_rangeHigh + _rangeLow) / 2.0;
            _rangeFormed = true;

            _logger.LogInfo($"[FLUX][ORB][RANGE_COMPLETE] EvaluationId={evaluationId}, " +
                $"RangeHigh={_rangeHigh:F2}, RangeLow={_rangeLow:F2}, " +
                $"RangeSize={_rangeSize:F2}, RangeMid={_rangeMid:F2}");

            // PHASE 5 / Opt 1: Resolve effective range bounds.
            // When ORBUseATRRangeFilter is true, scale bounds by 15m ATR(14).
            // If ATR15m is not yet warm (==0), fall back to fixed-point bounds
            // for this session so we don't silently disable the filter.
            double effectiveMinRange;
            double effectiveMaxRange;
            string rangeMode;

            if (_config.ORBUseATRRangeFilter && _atr15m > 0)
            {
                effectiveMinRange = _atr15m * _config.ORBMinRangeATR;
                effectiveMaxRange = _atr15m * _config.ORBMaxRangeATR;
                rangeMode = $"ATR15m={_atr15m:F2}xMin{_config.ORBMinRangeATR:F2}/Max{_config.ORBMaxRangeATR:F2}";
            }
            else
            {
                effectiveMinRange = _minRangePoints;
                effectiveMaxRange = _maxRangePoints;
                rangeMode = _config.ORBUseATRRangeFilter
                    ? "FIXED_FALLBACK_ATR_NOT_WARM"
                    : "FIXED";
            }

            if (_rangeSize < effectiveMinRange)
            {
                _state = ORBState.NoTrigger;
                _logger.LogInfo($"[FLUX][ORB][RANGE_TOO_SMALL] Size={_rangeSize:F2}, Min={effectiveMinRange:F2}, Mode={rangeMode}");
                return Reject(evaluationId, $"RANGE_TOO_SMALL_{_rangeSize:F1}");
            }

            if (_rangeSize > effectiveMaxRange)
            {
                _state = ORBState.NoTrigger;
                _logger.LogInfo($"[FLUX][ORB][RANGE_TOO_LARGE] Size={_rangeSize:F2}, Max={effectiveMaxRange:F2}, Mode={rangeMode}");
                return Reject(evaluationId, $"RANGE_TOO_LARGE_{_rangeSize:F1}");
            }

            // Range is valid - transition to watching
            _state = ORBState.Watching;
            _logger.LogInfo($"[FLUX][ORB][WATCHING] Range validated, watching for breakout");

            // PHASE 13.1: Block same-bar breakout if before earliest entry hour
            if (_config.ORBEarliestEntryHourET > 0 && currentTimeET.Hours < _config.ORBEarliestEntryHourET)
            {
                return Reject(evaluationId, $"RANGE_COMPLETE_BEFORE_ENTRY_HOUR_{_config.ORBEarliestEntryHourET}ET");
            }

            // Evaluate this bar for breakout (it could break out on the same bar range completes)
            return EvaluateBreakout(context, evaluationId, currentTimeET);
        }

        /// <summary>
        /// WATCHING: Range formed, evaluating each bar for breakout.
        /// </summary>
        private TradeIntent HandleWatching(Context context, string evaluationId, TimeSpan currentTimeET)
        {
            // Check if past the entry window
            if (currentTimeET > _sessionEndET)
            {
                _state = ORBState.NoTrigger;
                _logger.LogInfo($"[FLUX][ORB][SESSION_END] No breakout before {_sessionEndET}");
                return Reject(evaluationId, "PAST_SESSION_END");
            }

            // PHASE 5 / Opt 3: Latest entry hour gate (ET).
            // When configured, reject and lock out the rest of the day so we
            // don't keep evaluating breakout conditions on bars we'd never act
            // on. 0 = disabled.
            if (_config.ORBLatestEntryHourET > 0 && currentTimeET.Hours >= _config.ORBLatestEntryHourET)
            {
                _state = ORBState.NoTrigger;
                _logger.LogInfo($"[FLUX][ORB][PAST_LATEST_ENTRY_HOUR] TimeET={currentTimeET}, LatestHour={_config.ORBLatestEntryHourET}");
                return Reject(evaluationId, $"PAST_LATEST_ENTRY_HOUR_{_config.ORBLatestEntryHourET}ET");
            }

            // PHASE 13.1: Block entries before earliest entry hour (ET)
            // 8AM CT entries (9AM ET) are breakeven; 9AM CT entries (10AM ET) are 82.6% WR
            if (_config.ORBEarliestEntryHourET > 0 && currentTimeET.Hours < _config.ORBEarliestEntryHourET)
            {
                return Reject(evaluationId, $"BEFORE_EARLIEST_ENTRY_HOUR_{_config.ORBEarliestEntryHourET}ET");
            }

            // PHASE 5 / Opt 4: 15-min ATR ceiling. Filters extreme-volatility
            // regimes that produce wide ranges and failed breakouts. We reject
            // for the bar but stay in Watching so a calmer later bar can still
            // trade. Fail-open if ATR isn't warm yet (==0).
            if (_config.ORBMaxATR15m > 0 && _atr15m > 0 && _atr15m > _config.ORBMaxATR15m)
            {
                return Reject(evaluationId, $"ATR15M_CEILING_{_atr15m:F1}>{_config.ORBMaxATR15m:F1}");
            }

            // Must be flat
            if (!context.IsFlat)
                return Reject(evaluationId, "POSITION_NOT_FLAT");

            return EvaluateBreakout(context, evaluationId, currentTimeET);
        }

        #endregion

        #region Breakout Detection

        /// <summary>
        /// Evaluates current bar for a breakout beyond the opening range.
        /// Uses Close (bar close) to confirm breakout, with buffer to filter noise.
        /// </summary>
        private TradeIntent EvaluateBreakout(Context context, string evaluationId, TimeSpan currentTimeET)
        {
            // PHASE 5 / Opt 3 + Opt 4: Mirror the gates from HandleWatching so
            // the same-bar breakout path that runs immediately after the range
            // forms gets the same treatment.
            if (_config.ORBLatestEntryHourET > 0 && currentTimeET.Hours >= _config.ORBLatestEntryHourET)
            {
                _state = ORBState.NoTrigger;
                return Reject(evaluationId, $"PAST_LATEST_ENTRY_HOUR_{_config.ORBLatestEntryHourET}ET");
            }
            if (_config.ORBMaxATR15m > 0 && _atr15m > 0 && _atr15m > _config.ORBMaxATR15m)
            {
                return Reject(evaluationId, $"ATR15M_CEILING_{_atr15m:F1}>{_config.ORBMaxATR15m:F1}");
            }

            double close = context.Close;
            double vwapValue = _enableVWAPFilter ? _sessionVWAP : 0.0;

            // Breakout conditions with buffer (noise filter for 1-min bars)
            bool longBreakout = close > (_rangeHigh + _breakoutBuffer);
            bool shortBreakout = close < (_rangeLow - _breakoutBuffer);

            // VWAP alignment filter
            bool vwapLongOk = !_enableVWAPFilter || (vwapValue > 0 && close > vwapValue);
            bool vwapShortOk = !_enableVWAPFilter || (vwapValue > 0 && close < vwapValue);

            // Composite signals
            bool longSignal = longBreakout && vwapLongOk;
            bool shortSignal = shortBreakout && vwapShortOk;

            // Diagnostic logging
            string vwapInfo = _enableVWAPFilter
                ? $"VWAP={vwapValue:F2}, VWAPLongOk={vwapLongOk}, VWAPShortOk={vwapShortOk}"
                : "VWAP=DISABLED";

            _logger.LogInfo($"[FLUX][ORB][DIAGNOSTIC] EvaluationId={evaluationId}, " +
                $"TimeET={currentTimeET}, Close={close:F2}, " +
                $"RangeHigh={_rangeHigh:F2}, RangeLow={_rangeLow:F2}, RangeSize={_rangeSize:F2}, " +
                $"BreakoutBuffer={_breakoutBuffer:F2}, " +
                $"LongBreakout={longBreakout}, ShortBreakout={shortBreakout}, " +
                $"{vwapInfo}, " +
                $"LongSignal={longSignal}, ShortSignal={shortSignal}");

            // LONG breakout
            if (longSignal)
            {
                return EmitLongIntent(context, evaluationId);
            }

            // SHORT breakout
            if (shortSignal)
            {
                return EmitShortIntent(context, evaluationId);
            }

            // No breakout - determine reason
            if (longBreakout && !vwapLongOk)
                return Reject(evaluationId, "LONG_BREAKOUT_VWAP_REJECTED");
            if (shortBreakout && !vwapShortOk)
                return Reject(evaluationId, "SHORT_BREAKOUT_VWAP_REJECTED");

            return Reject(evaluationId, "NO_BREAKOUT");
        }

        #endregion

        #region Intent Emission

        private TradeIntent EmitLongIntent(Context context, string evaluationId)
        {
            double entryPrice = context.Close;

            // Stop: opposite side of range + buffer, capped at max.
            // PHASE 5 / Opt 2: When ORBUseATRStop is true, cap is the smaller
            // of the fixed-points cap and ATR-scaled cap (1.5x ATR15m by
            // default). This keeps the cap conservative when ATR is unusually
            // high. Falls back to the fixed cap when ATR isn't warm.
            double rawStopDistance = (entryPrice - _rangeLow) + _stopBuffer;
            double effectiveMaxStop = ResolveMaxStopDistance();
            double stopDistance = Math.Min(rawStopDistance, effectiveMaxStop);
            double stopPrice = entryPrice - stopDistance;

            // Target: range size × multiplier from breakout side of range
            double targetDistance = _rangeSize * _targetMultiplier;
            double targetPrice = _rangeHigh + targetDistance;

            // Tick conversions for TradeIntent (logging/validation)
            int stopTicks = (int)Math.Round(stopDistance / context.TickSize);
            int targetTicks = (int)Math.Round((targetPrice - entryPrice) / context.TickSize);

            string setupId = evaluationId.Replace("|EVAL|", "|LONG|");

            _logger.LogInfo($"[FLUX][ORB][INTENT] EvaluationId={evaluationId}, SetupId={setupId}, Direction=LONG, " +
                $"TriggerBar={context.CurrentBar}, " +
                $"EntryPrice={entryPrice:F2}, StopPrice={stopPrice:F2}, TargetPrice={targetPrice:F2}, " +
                $"StopDistance={stopDistance:F2}, TargetDistance={targetPrice - entryPrice:F2}, " +
                $"RangeSize={_rangeSize:F2}, RawStopDistance={rawStopDistance:F2}, " +
                $"MaxStopUsed={effectiveMaxStop:F2}, StopCapped={rawStopDistance > effectiveMaxStop}, " +
                $"ATRStopMode={(_config.ORBUseATRStop ? "ATR" : "FIXED")}, ATR15m={_atr15m:F2}");

            _state = ORBState.Triggered;
            _tradedToday = true;

            return TradeIntent.Long(
                ModuleId,
                stopTicks,
                targetTicks,
                "ORB_Breakout",
                "ORB_LONG",
                evaluationId,
                setupId,
                stopPrice,
                targetPrice);
        }

        private TradeIntent EmitShortIntent(Context context, string evaluationId)
        {
            double entryPrice = context.Close;

            // Stop: opposite side of range + buffer, capped at max.
            // PHASE 5 / Opt 2: ATR-aware cap (see EmitLongIntent).
            double rawStopDistance = (_rangeHigh - entryPrice) + _stopBuffer;
            double effectiveMaxStop = ResolveMaxStopDistance();
            double stopDistance = Math.Min(rawStopDistance, effectiveMaxStop);
            double stopPrice = entryPrice + stopDistance;

            // Target: range size × multiplier from breakout side of range
            double targetDistance = _rangeSize * _targetMultiplier;
            double targetPrice = _rangeLow - targetDistance;

            // Tick conversions for TradeIntent (logging/validation)
            int stopTicks = (int)Math.Round(stopDistance / context.TickSize);
            int targetTicks = (int)Math.Round((entryPrice - targetPrice) / context.TickSize);

            string setupId = evaluationId.Replace("|EVAL|", "|SHORT|");

            _logger.LogInfo($"[FLUX][ORB][INTENT] EvaluationId={evaluationId}, SetupId={setupId}, Direction=SHORT, " +
                $"TriggerBar={context.CurrentBar}, " +
                $"EntryPrice={entryPrice:F2}, StopPrice={stopPrice:F2}, TargetPrice={targetPrice:F2}, " +
                $"StopDistance={stopDistance:F2}, TargetDistance={entryPrice - targetPrice:F2}, " +
                $"RangeSize={_rangeSize:F2}, RawStopDistance={rawStopDistance:F2}, " +
                $"MaxStopUsed={effectiveMaxStop:F2}, StopCapped={rawStopDistance > effectiveMaxStop}, " +
                $"ATRStopMode={(_config.ORBUseATRStop ? "ATR" : "FIXED")}, ATR15m={_atr15m:F2}");

            _state = ORBState.Triggered;
            _tradedToday = true;

            return TradeIntent.Short(
                ModuleId,
                stopTicks,
                targetTicks,
                "ORB_Breakout",
                "ORB_SHORT",
                evaluationId,
                setupId,
                stopPrice,
                targetPrice);
        }

        /// <summary>
        /// PHASE 5 / Opt 2: Resolves the effective max-stop distance.
        /// When ORBUseATRStop is true and ATR15m is warm, returns the
        /// tighter of the fixed cap and (ATR15m * ORBMaxStopATR). When ATR
        /// isn't warm, falls back to the fixed cap (fail-safe to baseline).
        /// </summary>
        private double ResolveMaxStopDistance()
        {
            if (_config.ORBUseATRStop && _atr15m > 0)
            {
                double atrCap = _atr15m * _config.ORBMaxStopATR;
                return Math.Min(_maxStopPoints, atrCap);
            }
            return _maxStopPoints;
        }

        #endregion

        #region Session Management

        private void CheckSessionReset(Context context)
        {
            // Reset on new session date or first bar of session
            if (_isFirstBarOfSession || context.SessionDate != _lastSessionDate)
            {
                if (_lastSessionDate != DateTime.MinValue)
                {
                    _logger.LogDebug($"[FLUX][ORB][SESSION_RESET] PrevDate={_lastSessionDate:yyyy-MM-dd}, NewDate={context.SessionDate:yyyy-MM-dd}");
                }
                _lastSessionDate = context.SessionDate;
                ResetSessionState();
            }
        }

        private void ResetSessionState()
        {
            _state = ORBState.Idle;
            _rangeHigh = double.MinValue;
            _rangeLow = double.MaxValue;
            _rangeSize = 0;
            _rangeMid = 0;
            _rangeFormed = false;
            _tradedToday = false;

            // Reset VWAP
            _sessionVWAP = 0;
            _cumulativePriceVolume = 0;
            _cumulativeVolume = 0;
        }

        #endregion

        #region VWAP Calculation

        /// <summary>
        /// Session-based VWAP using real bar volume.
        /// Resets on IsFirstBarOfSession.
        /// </summary>
        private void UpdateVWAP(Context context)
        {
            if (_isFirstBarOfSession)
            {
                _sessionVWAP = 0;
                _cumulativePriceVolume = 0;
                _cumulativeVolume = 0;
            }

            double volume = (_volumes != null && _volumes.Length > 0) ? _volumes[0] : 1.0;
            double priceVolume = context.Close * volume;

            _cumulativePriceVolume += priceVolume;
            _cumulativeVolume += volume;

            if (_cumulativeVolume > 0)
            {
                _sessionVWAP = _cumulativePriceVolume / _cumulativeVolume;
            }
        }

        #endregion

        #region Rejection Tracking

        private TradeIntent Reject(string evaluationId, string reason)
        {
            if (!_rejectCounts.ContainsKey(reason))
                _rejectCounts[reason] = 0;
            _rejectCounts[reason]++;

            // Only log non-spammy rejections at Info level
            bool isRoutine = reason == "BEFORE_RANGE_WINDOW" || reason == "RANGE_FORMING"
                || reason == "NO_BREAKOUT" || reason == "ALREADY_TRIGGERED_TODAY"
                || reason == "NO_TRIGGER_TODAY";

            if (isRoutine)
            {
                _logger.LogDebug($"[FLUX][ORB][REJECT] EvaluationId={evaluationId}, Reason={reason}");
            }
            else
            {
                _logger.LogInfo($"[FLUX][ORB][REJECT] EvaluationId={evaluationId}, Reason={reason}");
            }

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