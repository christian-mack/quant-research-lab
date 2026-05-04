#region Using declarations
using System;
#endregion

namespace NinjaTrader.NinjaScript.Strategies.Flux.Core
{
    /// <summary>
    /// Risk decision result.
    /// </summary>
    public class RiskDecision
    {
        public bool IsTradingAllowed { get; private set; }
        public bool RequiresFlatten { get; private set; }
        public string Reason { get; private set; }

        private RiskDecision() { }

        public static RiskDecision Allowed() => new RiskDecision
        {
            IsTradingAllowed = true,
            RequiresFlatten = false,
            Reason = "ALLOWED"
        };

        public static RiskDecision Blocked(string reason) => new RiskDecision
        {
            IsTradingAllowed = false,
            RequiresFlatten = false,
            Reason = reason
        };

        public static RiskDecision FlattenRequired(string reason) => new RiskDecision
        {
            IsTradingAllowed = false,
            RequiresFlatten = true,
            Reason = reason
        };
    }

    /// <summary>
    /// Prop-firm safe risk manager.
    /// Enforces daily loss limit, trailing drawdown limit, and max trades per day.
    /// RiskManager decisions override all signals.
    /// 
    /// PHASE 12.11a FIX: Risk limits are absolute dollar values.
    /// We do NOT scale by DefaultQuantity because:
    /// 1. Actual traded quantity may differ from DefaultQuantity (NT8 Order Properties override)
    /// 2. Risk limits are prop-firm rules - they don't scale with position size
    /// 3. Quantity invariance is achieved by ensuring DefaultQuantity doesn't affect control flow
    /// </summary>
    public class RiskManager
    {
        private readonly Config _config;
        private readonly Logger _logger;

        // Internal state (tracked independently for safety)
        private double _dailyPnL;
        private double _peakDailyPnL;
        private double _trailingDrawdown;
        private int _tradesToday;
        private bool _dailyLossLockout;
        private bool _drawdownLockout;
        private bool _maxTradesLockout;
        private DateTime _lastSessionDate;

        public RiskManager(Config config, Logger logger)
        {
            _config = config ?? throw new ArgumentNullException(nameof(config));
            _logger = logger ?? throw new ArgumentNullException(nameof(logger));
            ResetDaily();
        }

        /// <summary>
        /// Evaluates risk constraints before allowing a new trade.
        /// </summary>
        public RiskDecision EvaluateNewTrade(Context context)
        {
            // Check for session reset
            CheckSessionReset(context);

            // 1. Daily loss lockout
            if (_dailyLossLockout)
            {
                return RiskDecision.Blocked("DAILY_LOSS_LOCKOUT");
            }

            // 2. Trailing drawdown lockout
            if (_drawdownLockout)
            {
                return RiskDecision.Blocked("DRAWDOWN_LOCKOUT");
            }

            // 3. Max trades per day
            if (_maxTradesLockout)
            {
                return RiskDecision.Blocked("MAX_TRADES_LOCKOUT");
            }

            // 4. Check if approaching limits (soft warning)
            if (_dailyPnL < -(_config.MaxDailyLossCurrency * 0.8))
            {
                _logger.LogDebug("Approaching daily loss limit", $"PnL={_dailyPnL:F2}, Limit={-_config.MaxDailyLossCurrency:F2}");
            }

            return RiskDecision.Allowed();
        }

        /// <summary>
        /// Evaluates risk constraints for an open position.
        /// May require immediate flatten if limits are breached.
        /// </summary>
        public RiskDecision EvaluateOpenPosition(Context context)
        {
            // Check for session reset
            CheckSessionReset(context);

            // Include unrealized PnL in assessment
            double totalPnL = _dailyPnL + context.UnrealizedPnL;

            // 1. Check daily loss limit with unrealized
            if (totalPnL < -_config.MaxDailyLossCurrency)
            {
                ActivateDailyLossLockout();
                _logger.LogRiskLockout("DAILY_LOSS_BREACH", totalPnL, -_config.MaxDailyLossCurrency);
                return RiskDecision.FlattenRequired("DAILY_LOSS_BREACH");
            }

            // 2. Check trailing drawdown with unrealized
            double peakWithUnrealized = Math.Max(_peakDailyPnL, totalPnL);
            double currentDrawdown = peakWithUnrealized - totalPnL;

            if (currentDrawdown > _config.MaxTrailingDrawdownCurrency)
            {
                ActivateDrawdownLockout();
                _logger.LogRiskLockout("DRAWDOWN_BREACH", currentDrawdown, _config.MaxTrailingDrawdownCurrency);
                return RiskDecision.FlattenRequired("DRAWDOWN_BREACH");
            }

            return RiskDecision.Allowed();
        }

        /// <summary>
        /// Records a closed trade and updates risk state.
        /// </summary>
        public void RecordTradeClosed(double realizedPnL)
        {
            _dailyPnL += realizedPnL;
            _tradesToday++;

            // Update peak
            if (_dailyPnL > _peakDailyPnL)
            {
                _peakDailyPnL = _dailyPnL;
            }

            // Calculate trailing drawdown
            _trailingDrawdown = _peakDailyPnL - _dailyPnL;

            // Check lockouts
            if (_dailyPnL < -_config.MaxDailyLossCurrency)
            {
                ActivateDailyLossLockout();
            }

            if (_trailingDrawdown > _config.MaxTrailingDrawdownCurrency)
            {
                ActivateDrawdownLockout();
            }

            if (_tradesToday >= _config.MaxTradesPerDay)
            {
                ActivateMaxTradesLockout();
            }
        }

        /// <summary>
        /// Gets current risk state summary.
        /// </summary>
        public string GetRiskSummary()
        {
            return $"DailyPnL={_dailyPnL:F2}, " +
                   $"Peak={_peakDailyPnL:F2}, " +
                   $"Drawdown={_trailingDrawdown:F2}, " +
                   $"Trades={_tradesToday}/{_config.MaxTradesPerDay}, " +
                   $"Limits=[DL={_config.MaxDailyLossCurrency:F0},DD={_config.MaxTrailingDrawdownCurrency:F0}], " +
                   $"Lockouts=[DL={_dailyLossLockout},DD={_drawdownLockout},MT={_maxTradesLockout}]";
        }

        /// <summary>
        /// Checks if any lockout is active.
        /// </summary>
        public bool IsLockedOut()
        {
            return _dailyLossLockout || _drawdownLockout || _maxTradesLockout;
        }

        /// <summary>
        /// Resets risk state for new session.
        /// </summary>
        public void ResetDaily()
        {
            _dailyPnL = 0;
            _peakDailyPnL = 0;
            _trailingDrawdown = 0;
            _tradesToday = 0;
            _dailyLossLockout = false;
            _drawdownLockout = false;
            _maxTradesLockout = false;
        }

        private void CheckSessionReset(Context context)
        {
            if (context.SessionDate != _lastSessionDate)
            {
                ResetDaily();
                _lastSessionDate = context.SessionDate;
                _logger.LogDebug("Risk manager reset for new session", context.SessionDate.ToShortDateString());
            }
        }

        private void ActivateDailyLossLockout()
        {
            if (!_dailyLossLockout)
            {
                _dailyLossLockout = true;
                _logger.LogRiskLockout("DAILY_LOSS", _dailyPnL, -_config.MaxDailyLossCurrency);
            }
        }

        private void ActivateDrawdownLockout()
        {
            if (!_drawdownLockout)
            {
                _drawdownLockout = true;
                _logger.LogRiskLockout("TRAILING_DRAWDOWN", _trailingDrawdown, _config.MaxTrailingDrawdownCurrency);
            }
        }

        private void ActivateMaxTradesLockout()
        {
            if (!_maxTradesLockout)
            {
                _maxTradesLockout = true;
                _logger.LogRiskLockout("MAX_TRADES", _tradesToday, _config.MaxTradesPerDay);
            }
        }
    }
}

