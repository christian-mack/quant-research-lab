#region Using declarations
using System;
using System.Collections.Generic;
using System.Linq;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Indicators;
#endregion

namespace NinjaTrader.NinjaScript.Strategies.Flux.Core
{
    /// <summary>
    /// Builds read-only Context snapshots each bar.
    /// Owned by FluxV1Strategy; modules cannot access this directly.
    /// </summary>
    public class ContextBuilder
    {
        private readonly Config _config;
        private readonly Strategy _strategy;
        private readonly ATR _atr;
        private readonly List<double> _atrHistory;

        // State tracking
        private DateTime _lastSessionDate;
        private double _dailyPnL;
        private double _peakEquity;
        private double _trailingDrawdown;
        private int _tradesToday;
        private bool _dailyLossLockout;
        private bool _drawdownLockout;
        private string _lastActiveModuleId;
        private string _owningModuleId;
        private int _cooldownBarsRemaining;
        private int _lastCooldownBar;

        public ContextBuilder(Strategy strategy, Config config, ATR atr)
        {
            _strategy = strategy ?? throw new ArgumentNullException(nameof(strategy));
            _config = config ?? throw new ArgumentNullException(nameof(config));
            _atr = atr ?? throw new ArgumentNullException(nameof(atr));
            _atrHistory = new List<double>();
            _lastSessionDate = DateTime.MinValue;
            _peakEquity = 0;
        }

        /// <summary>
        /// Builds a context snapshot for the current bar.
        /// </summary>
        public Context Build()
        {
            var context = new Context();

            // Instrument metadata
            context.TickSize = _strategy.TickSize;
            context.PointValue = _strategy.Instrument.MasterInstrument.PointValue;
            context.Symbol = _strategy.Instrument.MasterInstrument.Name;

            // Time context
            context.Timestamp = _strategy.Time[0];
            context.CurrentBar = _strategy.CurrentBar;
            context.SessionDate = _strategy.Time[0].Date;
            context.IsRTH = IsRegularTradingHours();
            context.TimeOfDay = ClassifyTimeOfDay();

            // Price data
            context.Open = _strategy.Open[0];
            context.High = _strategy.High[0];
            context.Low = _strategy.Low[0];
            context.Close = _strategy.Close[0];

            // Volatility metrics
            UpdateATRHistory();
            context.ATR = _atr[0];
            context.RangeWidth = CalculateRangeWidth();
            context.VolatilityRegime = ClassifyVolatility();
            context.IsHighVol = context.VolatilityRegime == VolatilityRegime.High;
            context.IsLowVol = context.VolatilityRegime == VolatilityRegime.Low;

            // Position state
            context.PositionState = GetPositionState();
            context.EntryPrice = _strategy.Position.AveragePrice;
            context.PositionQuantity = Math.Abs(_strategy.Position.Quantity);
            context.UnrealizedPnL = CalculateUnrealizedPnL(context);

            // Risk state
            UpdateDailyTracking(context);
            context.DailyPnL = _dailyPnL;
            // PHASE 12.11a FIX: Use absolute dollar limits (no scaling by DefaultQuantity)
            // Scaling was causing non-invariance when actual traded quantity != DefaultQuantity
            context.RemainingDailyLossBuffer = _config.MaxDailyLossCurrency + _dailyPnL;
            context.RemainingDrawdownBuffer = _config.MaxTrailingDrawdownCurrency - _trailingDrawdown;
            context.TradesToday = _tradesToday;
            context.RemainingTradesAllowed = Math.Max(0, _config.MaxTradesPerDay - _tradesToday);
            context.IsDailyLossLockout = _dailyLossLockout;
            context.IsDrawdownLockout = _drawdownLockout;

            // Router state
            context.LastActiveModuleId = _lastActiveModuleId ?? "";
            context.OwningModuleId = _owningModuleId ?? "";
            UpdateCooldown(context);
            context.IsModuleCooldown = _cooldownBarsRemaining > 0;
            context.CooldownBarsRemaining = _cooldownBarsRemaining;

            // Gating flags
            context.SessionGateOpen = EvaluateSessionGate(context);
            context.VolatilityGateOpen = EvaluateVolatilityGate(context);
            context.RiskGateOpen = EvaluateRiskGate(context);

            return context;
        }

        #region Time Classification

        private bool IsRegularTradingHours()
        {
            // PHASE 6 FIX: Adjust hardcoded times for correct timezone
            // Original code assumed EST (9:30-16:00), but futures data uses exchange time
            // For CME futures like ES: use CST session times (8:30 AM - 3:00 PM CST)
            var time = _strategy.Time[0];
            var hour = time.Hour;
            var minute = time.Minute;

            // CME futures regular trading hours: 8:30 AM - 3:00 PM CST
            bool isRTH = (hour >= 8 && hour < 15) || (hour == 8 && minute >= 30) || (hour == 15 && minute == 0);
            return isRTH;
        }

        private TimeOfDayBucket ClassifyTimeOfDay()
        {
            // PHASE 6 FIX: Adjust time classification for CST session times
            var time = _strategy.Time[0];
            var hour = time.Hour;
            var minute = time.Minute;

            // CST-based classification for CME futures
            if (hour < 8 || (hour == 8 && minute < 30))
                return TimeOfDayBucket.PreOpen;
            if (hour == 8 && minute >= 30)
                return TimeOfDayBucket.Open;
            if (hour >= 9 && hour < 14)
                return TimeOfDayBucket.MidDay;
            if (hour >= 14 && hour < 15)
                return TimeOfDayBucket.Close;
            if (hour >= 15)
                return TimeOfDayBucket.AfterHours;

            return TimeOfDayBucket.Unknown;
        }

        #endregion

        #region Volatility Classification

        private void UpdateATRHistory()
        {
            if (_atr[0] > 0)
            {
                _atrHistory.Add(_atr[0]);
                if (_atrHistory.Count > _config.VolLookbackBars)
                    _atrHistory.RemoveAt(0);
            }
        }

        private double CalculateRangeWidth()
        {
            if (_strategy.CurrentBar < _config.RangeLookback)
                return 0;

            double high = double.MinValue;
            double low = double.MaxValue;

            int lookback = Math.Min(_config.RangeLookback, _strategy.CurrentBar);
            for (int i = 0; i < lookback; i++)
            {
                if (_strategy.High[i] > high)
                    high = _strategy.High[i];
                if (_strategy.Low[i] < low)
                    low = _strategy.Low[i];
            }

            return high - low;
        }

        private VolatilityRegime ClassifyVolatility()
        {
            if (!_config.EnableVolatilityGate)
                return VolatilityRegime.Mid;

            double currentATR = _atr[0];
            if (currentATR <= 0)
                return VolatilityRegime.Mid;

            // PHASE 6 FIX: Use deterministic ATR thresholds instead of percentiles
            // For ES micro, ATR values are typically 1-5 points normal, 10+ during high vol
            // This prevents over-classification of normal volatility as HIGH

            const double HIGH_VOL_THRESHOLD = 8.0;  // ATR > 8 points = HIGH
            const double LOW_VOL_THRESHOLD = 2.0;   // ATR < 2 points = LOW

            if (currentATR > HIGH_VOL_THRESHOLD)
                return VolatilityRegime.High;
            if (currentATR < LOW_VOL_THRESHOLD)
                return VolatilityRegime.Low;

            return VolatilityRegime.Mid;
        }

        #endregion

        #region Position State

        private PositionState GetPositionState()
        {
            switch (_strategy.Position.MarketPosition)
            {
                case MarketPosition.Long:
                    return PositionState.Long;
                case MarketPosition.Short:
                    return PositionState.Short;
                default:
                    return PositionState.Flat;
            }
        }

        private double CalculateUnrealizedPnL(Context context)
        {
            if (context.PositionState == PositionState.Flat)
                return 0;

            double priceDiff = context.Close - context.EntryPrice;
            if (context.PositionState == PositionState.Short)
                priceDiff = -priceDiff;

            return priceDiff * context.PointValue * context.PositionQuantity;
        }

        #endregion

        #region Daily Tracking

        private void UpdateDailyTracking(Context context)
        {
            if (context.SessionDate != _lastSessionDate)
            {
                ResetDaily();
                _lastSessionDate = context.SessionDate;
            }
        }

        /// <summary>
        /// Called by FluxV1Strategy when a trade closes.
        /// </summary>
        public void RecordTradeClosed(double realizedPnL)
        {
            _dailyPnL += realizedPnL;
            _tradesToday++;

            // Update peak equity and drawdown
            if (_dailyPnL > _peakEquity)
                _peakEquity = _dailyPnL;

            _trailingDrawdown = _peakEquity - _dailyPnL;

            // Check lockouts
            // PHASE 12.11a FIX: Use absolute dollar limits (no scaling)
            if (_dailyPnL < -_config.MaxDailyLossCurrency)
                _dailyLossLockout = true;

            if (_trailingDrawdown > _config.MaxTrailingDrawdownCurrency)
                _drawdownLockout = true;
        }

        /// <summary>
        /// Called when a position is opened.
        /// </summary>
        public void RecordTradeOpened(string moduleId)
        {
            _owningModuleId = moduleId;
            _lastActiveModuleId = moduleId;
        }

        /// <summary>
        /// Called when a position is closed.
        /// </summary>
        public void RecordPositionClosed()
        {
            _owningModuleId = null;
            _cooldownBarsRemaining = _config.ModuleCooldownBars;
            _lastCooldownBar = _strategy.CurrentBar;
        }

        private void UpdateCooldown(Context context)
        {
            if (_cooldownBarsRemaining > 0 && context.CurrentBar > _lastCooldownBar)
            {
                _cooldownBarsRemaining = Math.Max(0, _cooldownBarsRemaining - (context.CurrentBar - _lastCooldownBar));
                _lastCooldownBar = context.CurrentBar;
            }
        }

        #endregion

        #region Gate Evaluation

        private bool EvaluateSessionGate(Context context)
        {
            // PHASE 12.6: Use NinjaTrader session engine instead of manual time logic
            // Use SessionIterator to check if the timestamp is within trading hours
            SessionIterator sessionIterator = new SessionIterator(_strategy.Bars);
            return sessionIterator.IsInSession(context.Timestamp, true, true);
        }

        private bool EvaluateVolatilityGate(Context context)
        {
            // For Range module in v1: disable in HIGH volatility
            // This is a system-level check; module-specific checks are in RegimeGate
            return true;
        }

        private bool EvaluateRiskGate(Context context)
        {
            if (context.IsDailyLossLockout)
                return false;

            if (context.IsDrawdownLockout)
                return false;

            if (context.RemainingTradesAllowed <= 0)
                return false;

            return true;
        }

        #endregion

        /// <summary>
        /// Reset for new session.
        /// </summary>
        public void ResetDaily()
        {
            _dailyPnL = 0;
            _tradesToday = 0;
            _dailyLossLockout = false;
            _drawdownLockout = false;
            _peakEquity = 0;
            _trailingDrawdown = 0;
            _cooldownBarsRemaining = 0;
        }
    }
}

