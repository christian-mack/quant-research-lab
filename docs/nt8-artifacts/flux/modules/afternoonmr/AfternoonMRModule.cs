#region Using declarations
using System;
using System.Collections.Generic;
using System.Linq;
using NinjaTrader.NinjaScript.Strategies.Flux.Core;
#endregion

namespace NinjaTrader.NinjaScript.Strategies.Flux.Modules.AfternoonMR
{
    /// <summary>
    /// Afternoon Mean Reversion Module for Flux v1.
    /// 
    /// Fades VWAP deviations during the afternoon session (12:00-15:00 CT)
    /// when NQ transitions from morning trend to mean-reverting regime.
    /// 
    /// Design:
    /// - Win-rate driven (~60-70% WR) with conservative VWAP reversion targets
    /// - Session-isolated: operates exclusively in the afternoon gap (0 coverage from existing modules)
    /// - Self-contained VWAP + WPR computation, same patterns as ORB/Momentum modules
    /// - Targets 50% reversion toward VWAP with fixed stop and auto break-even
    /// - Max 3 trades per day to limit damage on trend afternoons
    /// </summary>
    public class AfternoonMRModule : IModule
    {
        #region Module Identity

        public string ModuleId => "AfternoonMR";

        #endregion

        #region Configuration

        private readonly Config _config;
        private readonly Logger _logger;

        // Time gates (Central Time — Context.Timestamp is CT)
        private readonly int _startHourCT;
        private readonly int _endHourCT;
        private readonly int _timeExitHourCT;
        private readonly int _timeExitMinuteCT;

        // Signal parameters
        private readonly double _minVWAPDeviation;
        private readonly double _maxVWAPDeviation;
        private readonly double _stopDistancePoints;
        private readonly double _targetVWAPFraction;
        private readonly double _maxATR;

        // Trade management
        private readonly bool _enableBreakEven;
        private readonly double _beTriggerR;
        private readonly int _maxDailyTrades;

        #endregion

        #region Internal State

        // State machine
        private AfternoonMRState _state;

        // Trade tracking
        private int _tradesToday;

        // Session date tracking
        private DateTime _lastSessionDate;

        // VWAP state (session-based, self-contained)
        private double _sessionVWAP;
        private double _cumulativePriceVolume;
        private double _cumulativeVolume;

        // Price data cache (populated by caller via SetPriceData)
        private double[] _highs;
        private double[] _lows;
        private double[] _opens;
        private double[] _closes;
        private double[] _atrValues;
        private double[] _volumes;
        private bool _isFirstBarOfSession;

        // Reject reason tracking
        private readonly Dictionary<string, int> _rejectCounts;

        #endregion

        #region State Enum

        private enum AfternoonMRState
        {
            WaitingForSession,  // Before afternoon window
            Active,             // Within 12:00-15:00 CT, scanning for setups
            DailyCapReached,    // Hit max trades for today
            SessionEnded        // Past afternoon window
        }

        #endregion

        #region Constructor

        public AfternoonMRModule(Config config, Logger logger)
        {
            _config = config ?? throw new ArgumentNullException(nameof(config));
            _logger = logger ?? throw new ArgumentNullException(nameof(logger));

            // Load parameters from config
            _startHourCT = _config.AfternoonMRStartHourCT;
            _endHourCT = _config.AfternoonMREndHourCT;
            _timeExitHourCT = _config.AfternoonMRTimeExitHourCT;
            _timeExitMinuteCT = _config.AfternoonMRTimeExitMinuteCT;
            _minVWAPDeviation = _config.AfternoonMRMinVWAPDeviation;
            _maxVWAPDeviation = _config.AfternoonMRMaxVWAPDeviation;
            _stopDistancePoints = _config.AfternoonMRStopDistancePoints;
            _targetVWAPFraction = _config.AfternoonMRTargetVWAPFraction;
            _maxATR = _config.AfternoonMRMaxATR;
            _enableBreakEven = _config.AfternoonMREnableBreakEven;
            _beTriggerR = _config.AfternoonMRBETriggerR;
            _maxDailyTrades = _config.AfternoonMRMaxDailyTrades;

            // Initialize state
            _state = AfternoonMRState.WaitingForSession;
            _tradesToday = 0;
            _rejectCounts = new Dictionary<string, int>();

            _logger.LogDebug($"[FLUX][AFTERNOON_MR][INIT] StartHour={_startHourCT}, EndHour={_endHourCT}, " +
                $"MinVWAPDev={_minVWAPDeviation:F1}, MaxVWAPDev={_maxVWAPDeviation:F1}, " +
                $"StopDist={_stopDistancePoints:F1}, TargetFrac={_targetVWAPFraction:F2}, " +
                $"MaxATR={_maxATR:F1}, MaxDailyTrades={_maxDailyTrades}");
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

            // Always update VWAP (needed for signal generation)
            UpdateVWAP(context);

            // Get current hour in CT (Context.Timestamp is already CT)
            int currentHourCT = evaluationTime.Hour;
            int currentMinuteCT = evaluationTime.Minute;

            // State machine transitions
            switch (_state)
            {
                case AfternoonMRState.WaitingForSession:
                    return HandleWaitingForSession(context, evaluationId, currentHourCT);

                case AfternoonMRState.Active:
                    return HandleActive(context, evaluationId, currentHourCT, currentMinuteCT);

                case AfternoonMRState.DailyCapReached:
                    return Reject(evaluationId, "DAILY_CAP_REACHED");

                case AfternoonMRState.SessionEnded:
                    return Reject(evaluationId, "SESSION_ENDED");

                default:
                    return Reject(evaluationId, "UNKNOWN_STATE");
            }
        }

        public void OnTradeOpened(TradeMetadata trade)
        {
            _logger.LogDebug($"[FLUX][AFTERNOON_MR] Trade opened: {trade.Direction} @ {trade.EntryPrice:F2}");
        }

        public void OnTradeClosed(TradeResult result)
        {
            _logger.LogDebug($"[FLUX][AFTERNOON_MR] Trade closed: PnL={result.RealizedPnL:F2}, R={result.RMultiple:F2}");
        }

        public void ResetDaily()
        {
            ResetSessionState();
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
            double[] atrValues, double[] volumes, bool isFirstBarOfSession)
        {
            _highs = highs;
            _lows = lows;
            _opens = opens;
            _closes = closes;
            _atrValues = atrValues;
            _volumes = volumes;
            _isFirstBarOfSession = isFirstBarOfSession;
        }

        #endregion

        #region State Machine Handlers

        /// <summary>
        /// WAITING: Before the afternoon window opens.
        /// </summary>
        private TradeIntent HandleWaitingForSession(Context context, string evaluationId, int currentHourCT)
        {
            if (currentHourCT >= _startHourCT)
            {
                _state = AfternoonMRState.Active;
                _logger.LogInfo($"[FLUX][AFTERNOON_MR][SESSION_OPEN] Hour={currentHourCT}, VWAP={_sessionVWAP:F2}");
                return HandleActive(context, evaluationId, currentHourCT, context.Timestamp.Minute);
            }

            return Reject(evaluationId, "BEFORE_SESSION");
        }

        /// <summary>
        /// ACTIVE: Within the afternoon window, evaluating bars for VWAP fade setups.
        /// </summary>
        private TradeIntent HandleActive(Context context, string evaluationId, int currentHourCT, int currentMinuteCT)
        {
            // Check if past the entry window
            if (currentHourCT >= _endHourCT)
            {
                _state = AfternoonMRState.SessionEnded;
                _logger.LogInfo($"[FLUX][AFTERNOON_MR][SESSION_END] Hour={currentHourCT}, Trades={_tradesToday}");
                return Reject(evaluationId, "PAST_SESSION_END");
            }

            // Must be flat
            if (!context.IsFlat)
                return Reject(evaluationId, "POSITION_NOT_FLAT");

            // Check daily trade cap
            if (_tradesToday >= _maxDailyTrades)
            {
                _state = AfternoonMRState.DailyCapReached;
                return Reject(evaluationId, "DAILY_CAP_REACHED");
            }

            // Evaluate for mean reversion setup
            return EvaluateMeanReversion(context, evaluationId);
        }

        #endregion

        #region Mean Reversion Detection

        /// <summary>
        /// Evaluates current bar for a VWAP mean reversion fade opportunity.
        /// 
        /// Entry conditions (ALL must be true):
        /// 1. VWAP is valid (cumulative volume > 0)
        /// 2. Price deviates MinVWAPDeviation to MaxVWAPDeviation points from VWAP
        /// 3. WPR(14) confirms extreme (oversold for longs, overbought for shorts)
        /// 4. ATR is below ceiling (not a volatility spike day)
        /// 5. Momentum stalling: Close is not at the bar's extreme (price pulling back toward VWAP)
        /// </summary>
        private TradeIntent EvaluateMeanReversion(Context context, string evaluationId)
        {
            double close = context.Close;
            double high = context.High;
            double low = context.Low;

            // Condition 1: VWAP must be valid
            if (_sessionVWAP <= 0 || _cumulativeVolume <= 0)
                return Reject(evaluationId, "VWAP_INVALID");

            double vwapDeviation = close - _sessionVWAP;
            double absDeviation = Math.Abs(vwapDeviation);

            // Condition 2: Deviation within range
            if (absDeviation < _minVWAPDeviation)
                return Reject(evaluationId, "DEVIATION_TOO_SMALL");

            if (absDeviation > _maxVWAPDeviation)
                return Reject(evaluationId, "DEVIATION_TOO_LARGE");

            // Condition 3: WPR extreme confirmation
            double wprValue = CalculateWilliamsR(14);
            if (double.IsNaN(wprValue))
                return Reject(evaluationId, "WPR_CALCULATION_FAILED");

            bool wprOversold = wprValue < -80.0;   // OS threshold for long fade
            bool wprOverbought = wprValue > -20.0;  // OB threshold for short fade

            // Condition 4: ATR ceiling
            double currentATR = (_atrValues != null && _atrValues.Length > 0) ? _atrValues[0] : 0;
            if (_maxATR > 0 && currentATR > _maxATR)
                return Reject(evaluationId, "ATR_TOO_HIGH");

            // Determine direction based on deviation + WPR
            bool longSignal = vwapDeviation < 0 && wprOversold;   // Price below VWAP + oversold → fade long
            bool shortSignal = vwapDeviation > 0 && wprOverbought; // Price above VWAP + overbought → fade short

            // Condition 5: Momentum stalling (Close pulling back toward VWAP)
            if (longSignal)
            {
                // For longs: Close should be above the bar's low (bounce forming)
                if (close <= low)
                {
                    longSignal = false;
                }
            }
            if (shortSignal)
            {
                // For shorts: Close should be below the bar's high (rejection forming)
                if (close >= high)
                {
                    shortSignal = false;
                }
            }

            // Diagnostic logging (non-spammy: only when we pass deviation filter)
            _logger.LogInfo($"[FLUX][AFTERNOON_MR][DIAGNOSTIC] EvaluationId={evaluationId}, " +
                $"Close={close:F2}, VWAP={_sessionVWAP:F2}, Deviation={vwapDeviation:F2}, AbsDev={absDeviation:F2}, " +
                $"WPR={wprValue:F2}, ATR={currentATR:F2}, " +
                $"LongSignal={longSignal}, ShortSignal={shortSignal}");

            // LONG fade: price below VWAP, oversold, momentum stalling
            if (longSignal)
            {
                return EmitLongIntent(context, evaluationId, absDeviation);
            }

            // SHORT fade: price above VWAP, overbought, momentum stalling
            if (shortSignal)
            {
                return EmitShortIntent(context, evaluationId, absDeviation);
            }

            // Determine specific reject reason
            if (vwapDeviation < 0 && !wprOversold)
                return Reject(evaluationId, "BELOW_VWAP_BUT_WPR_NOT_OVERSOLD");
            if (vwapDeviation > 0 && !wprOverbought)
                return Reject(evaluationId, "ABOVE_VWAP_BUT_WPR_NOT_OVERBOUGHT");

            return Reject(evaluationId, "MOMENTUM_NOT_STALLING");
        }

        #endregion

        #region Intent Emission

        private TradeIntent EmitLongIntent(Context context, string evaluationId, double absDeviation)
        {
            double entryPrice = context.Close;

            // Stop: fixed distance below entry
            double stopPrice = entryPrice - _stopDistancePoints;

            // Target: partial reversion toward VWAP
            // TargetVWAPFraction=0.5 means target halfway between entry and VWAP
            double targetDistance = absDeviation * _targetVWAPFraction;
            double targetPrice = entryPrice + targetDistance;

            // Tick conversions for TradeIntent
            int stopTicks = (int)Math.Round(_stopDistancePoints / context.TickSize);
            int targetTicks = (int)Math.Round(targetDistance / context.TickSize);

            // Sanity: target must be positive
            if (targetTicks <= 0)
                return Reject(evaluationId, "TARGET_TOO_SMALL");

            string setupId = evaluationId.Replace("|EVAL|", "|LONG|");

            _logger.LogInfo($"[FLUX][AFTERNOON_MR][INTENT] EvaluationId={evaluationId}, SetupId={setupId}, Direction=LONG, " +
                $"TriggerBar={context.CurrentBar}, " +
                $"EntryPrice={entryPrice:F2}, StopPrice={stopPrice:F2}, TargetPrice={targetPrice:F2}, " +
                $"VWAPDeviation={absDeviation:F2}, TargetDistance={targetDistance:F2}, " +
                $"StopDistancePoints={_stopDistancePoints:F2}, VWAP={_sessionVWAP:F2}");

            _tradesToday++;

            return TradeIntent.Long(
                ModuleId,
                stopTicks,
                targetTicks,
                "AfternoonMR_VWAP_Fade",
                "AFTERNOON_MR_LONG",
                evaluationId,
                setupId,
                stopPrice,
                targetPrice);
        }

        private TradeIntent EmitShortIntent(Context context, string evaluationId, double absDeviation)
        {
            double entryPrice = context.Close;

            // Stop: fixed distance above entry
            double stopPrice = entryPrice + _stopDistancePoints;

            // Target: partial reversion toward VWAP
            double targetDistance = absDeviation * _targetVWAPFraction;
            double targetPrice = entryPrice - targetDistance;

            // Tick conversions for TradeIntent
            int stopTicks = (int)Math.Round(_stopDistancePoints / context.TickSize);
            int targetTicks = (int)Math.Round(targetDistance / context.TickSize);

            // Sanity: target must be positive
            if (targetTicks <= 0)
                return Reject(evaluationId, "TARGET_TOO_SMALL");

            string setupId = evaluationId.Replace("|EVAL|", "|SHORT|");

            _logger.LogInfo($"[FLUX][AFTERNOON_MR][INTENT] EvaluationId={evaluationId}, SetupId={setupId}, Direction=SHORT, " +
                $"TriggerBar={context.CurrentBar}, " +
                $"EntryPrice={entryPrice:F2}, StopPrice={stopPrice:F2}, TargetPrice={targetPrice:F2}, " +
                $"VWAPDeviation={absDeviation:F2}, TargetDistance={targetDistance:F2}, " +
                $"StopDistancePoints={_stopDistancePoints:F2}, VWAP={_sessionVWAP:F2}");

            _tradesToday++;

            return TradeIntent.Short(
                ModuleId,
                stopTicks,
                targetTicks,
                "AfternoonMR_VWAP_Fade",
                "AFTERNOON_MR_SHORT",
                evaluationId,
                setupId,
                stopPrice,
                targetPrice);
        }

        #endregion

        #region Williams %R Calculation

        /// <summary>
        /// Self-contained Williams %R calculation using price data arrays.
        /// Same implementation as MomentumModule for consistency.
        /// </summary>
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

        #region VWAP Calculation

        /// <summary>
        /// Session-based VWAP using real bar volume.
        /// Resets on IsFirstBarOfSession. Same pattern as ORBModule.
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

        #region Session Management

        private void CheckSessionReset(Context context)
        {
            if (_isFirstBarOfSession || context.SessionDate != _lastSessionDate)
            {
                if (_lastSessionDate != DateTime.MinValue)
                {
                    _logger.LogDebug($"[FLUX][AFTERNOON_MR][SESSION_RESET] PrevDate={_lastSessionDate:yyyy-MM-dd}, NewDate={context.SessionDate:yyyy-MM-dd}");
                }
                _lastSessionDate = context.SessionDate;
                ResetSessionState();
            }
        }

        private void ResetSessionState()
        {
            _state = AfternoonMRState.WaitingForSession;
            _tradesToday = 0;

            // Do NOT reset VWAP here — it resets on IsFirstBarOfSession
            // VWAP needs to accumulate from session open through afternoon
        }

        #endregion

        #region Rejection Tracking

        private TradeIntent Reject(string evaluationId, string reason)
        {
            if (!_rejectCounts.ContainsKey(reason))
                _rejectCounts[reason] = 0;
            _rejectCounts[reason]++;

            // Only log non-spammy rejections at Info level
            bool isRoutine = reason == "BEFORE_SESSION" || reason == "SESSION_ENDED"
                || reason == "DAILY_CAP_REACHED" || reason == "DEVIATION_TOO_SMALL"
                || reason == "POSITION_NOT_FLAT";

            if (isRoutine)
            {
                _logger.LogDebug($"[FLUX][AFTERNOON_MR][REJECT] EvaluationId={evaluationId}, Reason={reason}");
            }
            else
            {
                _logger.LogInfo($"[FLUX][AFTERNOON_MR][REJECT] EvaluationId={evaluationId}, Reason={reason}");
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