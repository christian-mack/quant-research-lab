#region Using declarations
using System;
using System.Collections.Generic;
using System.Linq;
using NinjaTrader.NinjaScript.Strategies.Flux.Core;
#endregion

namespace NinjaTrader.NinjaScript.Strategies.Flux.Modules.CloseCont
{
    /// <summary>
    /// Close Continuation Module for Flux v1 (Phase 17).
    /// 
    /// Trades continuation of a confirmed 30-minute directional move into the close.
    /// Exploits MOC (market-on-close) institutional order flow that creates
    /// sustained directional pressure in the final 30-60 minutes of RTH.
    /// 
    /// Design:
    /// - Session window: 14:00-15:00 CT (15:00-16:00 ET)
    /// - Setup phase:    14:00-14:30 CT — measures directional move, NO entries
    /// - Entry phase:    14:30-15:00 CT — enters continuation if setup confirmed
    /// - Setup confirmation: at 14:30 CT, checks if |Close - WindowOpenPrice| >= MinSetupMagnitude
    /// - Win-rate driven (~70% WR) with fixed stop and target
    /// - Max 1 trade per day (MOC flow is a once-per-day phenomenon)
    /// - Hard exit at 15:00 CT (16:00 ET) if still open
    /// - Lower priority than AfternoonMR — fires on days AMR doesn't trade
    /// 
    /// CRITICAL DESIGN NOTE (Phase 17 Fix):
    /// The original implementation entered as soon as a small price deviation was detected,
    /// causing 86% of entries within 2-3 minutes on noise. The edge comes from CONFIRMED
    /// half-hour directional moves, not instantaneous wiggles. The setup phase must complete
    /// its full 30-minute measurement before any entry is permitted.
    /// </summary>
    public class CloseContModule : IModule
    {
        #region Module Identity

        public string ModuleId => "CloseCont";

        #endregion

        #region Configuration

        private readonly Config _config;
        private readonly Logger _logger;

        // Time gates (Central Time — Context.Timestamp is CT)
        private readonly int _startHourCT;
        private readonly int _startMinuteCT;
        private readonly int _endHourCT;
        private readonly int _endMinuteCT;
        private readonly int _hardExitHourCT;
        private readonly int _hardExitMinuteCT;

        // Setup phase end = 30 minutes after start (hardcoded — this is the structural edge)
        private readonly int _setupPhaseMinutes;

        // Signal parameters
        private readonly double _minSetupMagnitude;
        private readonly double _stopDistancePoints;
        private readonly double _targetDistancePoints;
        private readonly double _maxATR;

        // Trade management
        private readonly bool _enableBreakEven;
        private readonly double _beTriggerR;
        private readonly int _maxDailyTrades;

        #endregion

        #region Internal State

        private CloseContState _state;
        private int _tradesToday;
        private DateTime _lastSessionDate;

        // Setup tracking
        private double _windowOpenPrice;
        private bool _windowOpenCaptured;
        private int _setupDirection;      // +1 = bullish, -1 = bearish, 0 = undetermined
        private double _confirmedSetupMove; // Magnitude of confirmed move at setup phase end
        private bool _setupEvaluated;      // Whether the 14:30 evaluation has occurred

        // Price data cache (populated by caller via SetPriceData)
        private double[] _highs;
        private double[] _lows;
        private double[] _opens;
        private double[] _closes;
        private double[] _atrValues;
        private double[] _volumes;
        private bool _isFirstBarOfSession;

        private readonly Dictionary<string, int> _rejectCounts;

        #endregion

        #region State Enum

        private enum CloseContState
        {
            WaitingForSession,      // Before 14:00 CT
            MeasuringSetup,         // 14:00-14:30 CT — observing, NO entries
            ReadyToEnter,           // 14:30-15:00 CT — setup confirmed, looking to enter
            SetupFailed,            // Setup phase ended but magnitude not met
            DailyCapReached,        // Hit max trades
            SessionEnded            // Past 15:00 CT
        }

        #endregion

        #region Constructor

        public CloseContModule(Config config, Logger logger)
        {
            _config = config ?? throw new ArgumentNullException(nameof(config));
            _logger = logger ?? throw new ArgumentNullException(nameof(logger));

            _startHourCT = _config.CloseContStartHourCT;
            _startMinuteCT = _config.CloseContStartMinuteCT;
            _endHourCT = _config.CloseContEndHourCT;
            _endMinuteCT = _config.CloseContEndMinuteCT;
            _hardExitHourCT = _config.CloseContHardExitHourCT;
            _hardExitMinuteCT = _config.CloseContHardExitMinuteCT;
            _minSetupMagnitude = _config.CloseContMinSetupMagnitude;
            _stopDistancePoints = _config.CloseContStopDistancePoints;
            _targetDistancePoints = _config.CloseContTargetDistancePoints;
            _maxATR = _config.CloseContMaxATR;
            _enableBreakEven = _config.CloseContEnableBreakEven;
            _beTriggerR = _config.CloseContBETriggerR;
            _maxDailyTrades = _config.CloseContMaxDailyTrades;

            // Hardcoded: setup phase is always 30 minutes from window open.
            // This is the structural source of edge — do not make configurable.
            _setupPhaseMinutes = 30;

            _state = CloseContState.WaitingForSession;
            _tradesToday = 0;
            _rejectCounts = new Dictionary<string, int>();

            _logger.LogDebug($"[FLUX][CLOSE_CONT][INIT] Start={_startHourCT}:{_startMinuteCT:D2}, " +
                $"End={_endHourCT}:{_endMinuteCT:D2}, HardExit={_hardExitHourCT}:{_hardExitMinuteCT:D2}, " +
                $"SetupPhase={_setupPhaseMinutes}min, " +
                $"MinSetup={_minSetupMagnitude:F1}, Stop={_stopDistancePoints:F1}, " +
                $"Target={_targetDistancePoints:F1}, MaxATR={_maxATR:F1}, MaxTrades={_maxDailyTrades}");
        }

        #endregion

        #region IModule Implementation

        public TradeIntent Evaluate(Context context)
        {
            DateTime evalTime = context.Timestamp;
            int evalBar = context.CurrentBar;

            string tradingDay = evalTime.ToString("yyyyMMdd");
            string currentTime = evalTime.ToString("HHmm");
            string evaluationId = $"{tradingDay}-{currentTime}|EVAL|{evalBar}";

            CheckSessionReset(context);

            int hourCT = evalTime.Hour;
            int minuteCT = evalTime.Minute;
            int timeAsMinutes = hourCT * 60 + minuteCT;
            int startAsMinutes = _startHourCT * 60 + _startMinuteCT;
            int endAsMinutes = _endHourCT * 60 + _endMinuteCT;
            int setupEndAsMinutes = startAsMinutes + _setupPhaseMinutes;

            switch (_state)
            {
                case CloseContState.WaitingForSession:
                    return HandleWaitingForSession(context, evaluationId, timeAsMinutes, startAsMinutes, endAsMinutes, setupEndAsMinutes);

                case CloseContState.MeasuringSetup:
                    return HandleMeasuringSetup(context, evaluationId, timeAsMinutes, endAsMinutes, setupEndAsMinutes);

                case CloseContState.ReadyToEnter:
                    return HandleReadyToEnter(context, evaluationId, timeAsMinutes, endAsMinutes);

                case CloseContState.SetupFailed:
                    return Reject(evaluationId, "SETUP_FAILED");

                case CloseContState.DailyCapReached:
                    return Reject(evaluationId, "DAILY_CAP_REACHED");

                case CloseContState.SessionEnded:
                    return Reject(evaluationId, "SESSION_ENDED");

                default:
                    return Reject(evaluationId, "UNKNOWN_STATE");
            }
        }

        public void OnTradeOpened(TradeMetadata trade)
        {
            _logger.LogDebug($"[FLUX][CLOSE_CONT] Trade opened: {trade.Direction} @ {trade.EntryPrice:F2}");
        }

        public void OnTradeClosed(TradeResult result)
        {
            _logger.LogDebug($"[FLUX][CLOSE_CONT] Trade closed: PnL={result.RealizedPnL:F2}, R={result.RMultiple:F2}");
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

        private TradeIntent HandleWaitingForSession(Context context, string evaluationId,
            int timeAsMinutes, int startAsMinutes, int endAsMinutes, int setupEndAsMinutes)
        {
            if (timeAsMinutes >= startAsMinutes)
            {
                // Capture window open price on first bar of session window
                _windowOpenPrice = context.Close;
                _windowOpenCaptured = true;
                _setupDirection = 0;
                _confirmedSetupMove = 0;
                _setupEvaluated = false;

                _logger.LogInfo($"[FLUX][CLOSE_CONT][SESSION_OPEN] Time={context.Timestamp:HH:mm}, " +
                    $"WindowOpen={_windowOpenPrice:F2}, SetupEnds={_startHourCT}:{(_startMinuteCT + _setupPhaseMinutes):D2} CT");

                // If we're already past setup phase end (e.g., strategy loaded late),
                // jump directly to setup evaluation
                if (timeAsMinutes >= setupEndAsMinutes)
                {
                    _state = CloseContState.MeasuringSetup;
                    return EvaluateSetupCompletion(context, evaluationId, timeAsMinutes, endAsMinutes);
                }

                _state = CloseContState.MeasuringSetup;
                return Reject(evaluationId, "SETUP_PHASE_ACTIVE");
            }

            return Reject(evaluationId, "BEFORE_SESSION");
        }

        private TradeIntent HandleMeasuringSetup(Context context, string evaluationId,
            int timeAsMinutes, int endAsMinutes, int setupEndAsMinutes)
        {
            // Check if entire session is over
            if (timeAsMinutes >= endAsMinutes)
            {
                _state = CloseContState.SessionEnded;
                _logger.LogInfo($"[FLUX][CLOSE_CONT][SESSION_END] Time={context.Timestamp:HH:mm}, " +
                    $"Trades={_tradesToday}, SetupNeverCompleted");
                return Reject(evaluationId, "PAST_SESSION_END");
            }

            // Capture window open on first bar if not done (safety net)
            if (!_windowOpenCaptured)
            {
                _windowOpenPrice = context.Close;
                _windowOpenCaptured = true;
            }

            // ========================================================================
            // CRITICAL: Do NOT enter during setup phase. Only observe.
            // The edge comes from waiting for the full 30-minute move to confirm.
            // ========================================================================
            if (timeAsMinutes < setupEndAsMinutes)
            {
                return Reject(evaluationId, "SETUP_PHASE_ACTIVE");
            }

            // Setup phase just ended — evaluate the confirmed move
            return EvaluateSetupCompletion(context, evaluationId, timeAsMinutes, endAsMinutes);
        }

        /// <summary>
        /// Called exactly once when the setup phase ends (14:30 CT).
        /// Evaluates whether the 30-minute directional move meets the threshold.
        /// This is the structural edge: only confirmed, sustained moves qualify.
        /// </summary>
        private TradeIntent EvaluateSetupCompletion(Context context, string evaluationId,
            int timeAsMinutes, int endAsMinutes)
        {
            if (_setupEvaluated)
            {
                // Already evaluated and setup was confirmed — should be in ReadyToEnter
                // If we're here, something unexpected happened
                return Reject(evaluationId, "SETUP_ALREADY_EVALUATED");
            }

            _setupEvaluated = true;

            double setupMove = context.Close - _windowOpenPrice;
            _confirmedSetupMove = setupMove;

            // Check if confirmed move meets magnitude threshold
            if (Math.Abs(setupMove) < _minSetupMagnitude)
            {
                _state = CloseContState.SetupFailed;
                _logger.LogInfo($"[FLUX][CLOSE_CONT][SETUP_FAILED] Time={context.Timestamp:HH:mm}, " +
                    $"SetupMove={setupMove:F2} (need +/-{_minSetupMagnitude:F1}), " +
                    $"WindowOpen={_windowOpenPrice:F2}, Close={context.Close:F2}");
                return Reject(evaluationId, "SETUP_MAGNITUDE_NOT_MET");
            }

            // Setup confirmed — determine direction
            _setupDirection = setupMove > 0 ? 1 : -1;
            _state = CloseContState.ReadyToEnter;

            _logger.LogInfo($"[FLUX][CLOSE_CONT][SETUP_CONFIRMED] Time={context.Timestamp:HH:mm}, " +
                $"Direction={(_setupDirection > 0 ? "LONG" : "SHORT")}, " +
                $"SetupMove={setupMove:F2}, WindowOpen={_windowOpenPrice:F2}, Close={context.Close:F2}");

            // Immediately attempt entry on this bar (first bar of entry phase)
            return HandleReadyToEnter(context, evaluationId, timeAsMinutes, endAsMinutes);
        }

        private TradeIntent HandleReadyToEnter(Context context, string evaluationId,
            int timeAsMinutes, int endAsMinutes)
        {
            // Check if past entry window
            if (timeAsMinutes >= endAsMinutes)
            {
                _state = CloseContState.SessionEnded;
                _logger.LogInfo($"[FLUX][CLOSE_CONT][SESSION_END] Time={context.Timestamp:HH:mm}, " +
                    $"Trades={_tradesToday}, SetupWasConfirmed=true, NoEntryBeforeClose");
                return Reject(evaluationId, "PAST_SESSION_END");
            }

            // Must be flat
            if (!context.IsFlat)
                return Reject(evaluationId, "POSITION_NOT_FLAT");

            // Check daily trade cap
            if (_tradesToday >= _maxDailyTrades)
            {
                _state = CloseContState.DailyCapReached;
                return Reject(evaluationId, "DAILY_CAP_REACHED");
            }

            // ATR ceiling
            double currentATR = (_atrValues != null && _atrValues.Length > 0) ? _atrValues[0] : 0;
            if (_maxATR > 0 && currentATR > _maxATR)
                return Reject(evaluationId, "ATR_TOO_HIGH");

            // Verify current price hasn't reversed past window open (setup invalidation).
            // If price has crossed back through window open, the continuation thesis is dead.
            double currentMove = context.Close - _windowOpenPrice;
            if (_setupDirection > 0 && currentMove <= 0)
            {
                _state = CloseContState.SetupFailed;
                _logger.LogInfo($"[FLUX][CLOSE_CONT][SETUP_INVALIDATED] Direction=LONG but currentMove={currentMove:F2}, " +
                    $"price reversed through WindowOpen={_windowOpenPrice:F2}");
                return Reject(evaluationId, "SETUP_REVERSED");
            }
            if (_setupDirection < 0 && currentMove >= 0)
            {
                _state = CloseContState.SetupFailed;
                _logger.LogInfo($"[FLUX][CLOSE_CONT][SETUP_INVALIDATED] Direction=SHORT but currentMove={currentMove:F2}, " +
                    $"price reversed through WindowOpen={_windowOpenPrice:F2}");
                return Reject(evaluationId, "SETUP_REVERSED");
            }

            // Emit entry intent
            if (_setupDirection > 0)
                return EmitLongIntent(context, evaluationId);
            else
                return EmitShortIntent(context, evaluationId);
        }

        #endregion

        #region Intent Emission

        private TradeIntent EmitLongIntent(Context context, string evaluationId)
        {
            double entryPrice = context.Close;
            double stopPrice = entryPrice - _stopDistancePoints;
            double targetPrice = entryPrice + _targetDistancePoints;

            int stopTicks = (int)Math.Round(_stopDistancePoints / context.TickSize);
            int targetTicks = (int)Math.Round(_targetDistancePoints / context.TickSize);

            if (targetTicks <= 0)
                return Reject(evaluationId, "TARGET_TOO_SMALL");

            string setupId = evaluationId.Replace("|EVAL|", "|LONG|");

            _logger.LogInfo($"[FLUX][CLOSE_CONT][INTENT] EvaluationId={evaluationId}, SetupId={setupId}, Direction=LONG, " +
                $"TriggerBar={context.CurrentBar}, EntryPrice={entryPrice:F2}, " +
                $"StopPrice={stopPrice:F2}, TargetPrice={targetPrice:F2}, " +
                $"ConfirmedSetupMove={_confirmedSetupMove:F2}, CurrentMove={context.Close - _windowOpenPrice:F2}");

            _tradesToday++;

            return TradeIntent.Long(
                ModuleId,
                stopTicks,
                targetTicks,
                "CloseCont_MOC_Continuation",
                "CLOSE_CONT_LONG",
                evaluationId,
                setupId,
                stopPrice,
                targetPrice);
        }

        private TradeIntent EmitShortIntent(Context context, string evaluationId)
        {
            double entryPrice = context.Close;
            double stopPrice = entryPrice + _stopDistancePoints;
            double targetPrice = entryPrice - _targetDistancePoints;

            int stopTicks = (int)Math.Round(_stopDistancePoints / context.TickSize);
            int targetTicks = (int)Math.Round(_targetDistancePoints / context.TickSize);

            if (targetTicks <= 0)
                return Reject(evaluationId, "TARGET_TOO_SMALL");

            string setupId = evaluationId.Replace("|EVAL|", "|SHORT|");

            _logger.LogInfo($"[FLUX][CLOSE_CONT][INTENT] EvaluationId={evaluationId}, SetupId={setupId}, Direction=SHORT, " +
                $"TriggerBar={context.CurrentBar}, EntryPrice={entryPrice:F2}, " +
                $"StopPrice={stopPrice:F2}, TargetPrice={targetPrice:F2}, " +
                $"ConfirmedSetupMove={_confirmedSetupMove:F2}, CurrentMove={context.Close - _windowOpenPrice:F2}");

            _tradesToday++;

            return TradeIntent.Short(
                ModuleId,
                stopTicks,
                targetTicks,
                "CloseCont_MOC_Continuation",
                "CLOSE_CONT_SHORT",
                evaluationId,
                setupId,
                stopPrice,
                targetPrice);
        }

        #endregion

        #region Session Management

        private void CheckSessionReset(Context context)
        {
            if (_isFirstBarOfSession || context.SessionDate != _lastSessionDate)
            {
                if (_lastSessionDate != DateTime.MinValue)
                {
                    _logger.LogDebug($"[FLUX][CLOSE_CONT][SESSION_RESET] PrevDate={_lastSessionDate:yyyy-MM-dd}, " +
                        $"NewDate={context.SessionDate:yyyy-MM-dd}");
                }
                _lastSessionDate = context.SessionDate;
                ResetSessionState();
            }
        }

        private void ResetSessionState()
        {
            _state = CloseContState.WaitingForSession;
            _tradesToday = 0;
            _windowOpenPrice = 0;
            _windowOpenCaptured = false;
            _setupDirection = 0;
            _confirmedSetupMove = 0;
            _setupEvaluated = false;
        }

        #endregion

        #region Rejection Tracking

        private TradeIntent Reject(string evaluationId, string reason)
        {
            if (!_rejectCounts.ContainsKey(reason))
                _rejectCounts[reason] = 0;
            _rejectCounts[reason]++;

            bool isRoutine = reason == "BEFORE_SESSION" || reason == "SESSION_ENDED"
                || reason == "DAILY_CAP_REACHED" || reason == "SETUP_PHASE_ACTIVE"
                || reason == "SETUP_NOT_CONFIRMED" || reason == "POSITION_NOT_FLAT"
                || reason == "SETUP_FAILED" || reason == "SETUP_ALREADY_EVALUATED";

            if (isRoutine)
                _logger.LogDebug($"[FLUX][CLOSE_CONT][REJECT] EvaluationId={evaluationId}, Reason={reason}");
            else
                _logger.LogInfo($"[FLUX][CLOSE_CONT][REJECT] EvaluationId={evaluationId}, Reason={reason}");

            return TradeIntent.None;
        }

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