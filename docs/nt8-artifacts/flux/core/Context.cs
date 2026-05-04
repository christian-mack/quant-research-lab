#region Using declarations
using System;
#endregion

namespace NinjaTrader.NinjaScript.Strategies.Flux.Core
{
    /// <summary>
    /// Position state enumeration.
    /// </summary>
    public enum PositionState
    {
        Flat,
        Long,
        Short
    }

    /// <summary>
    /// Time-of-day trading bucket.
    /// </summary>
    public enum TimeOfDayBucket
    {
        PreOpen,
        Open,
        MidDay,
        Close,
        AfterHours,
        Unknown
    }

    /// <summary>
    /// Read-only context snapshot built each bar by ContextBuilder.
    /// Modules may read Context but must never modify it.
    /// </summary>
    public class Context
    {
        #region Instrument Metadata

        /// <summary>
        /// Minimum price movement (e.g., 0.25 for ES).
        /// </summary>
        public double TickSize { get; internal set; }

        /// <summary>
        /// Dollar value per point (e.g., 50 for ES, 5 for MES).
        /// </summary>
        public double PointValue { get; internal set; }

        /// <summary>
        /// Instrument symbol (e.g., "ES", "MES").
        /// </summary>
        public string Symbol { get; internal set; }

        #endregion

        #region Time Context

        /// <summary>
        /// Current bar timestamp.
        /// </summary>
        public DateTime Timestamp { get; internal set; }

        /// <summary>
        /// Current bar index.
        /// </summary>
        public int CurrentBar { get; internal set; }

        /// <summary>
        /// Session type (true = RTH, false = ETH).
        /// </summary>
        public bool IsRTH { get; internal set; }

        /// <summary>
        /// Time-of-day trading bucket.
        /// </summary>
        public TimeOfDayBucket TimeOfDay { get; internal set; }

        /// <summary>
        /// Session date (for daily reset tracking).
        /// </summary>
        public DateTime SessionDate { get; internal set; }

        #endregion

        #region Volatility Metrics

        /// <summary>
        /// Current ATR value.
        /// </summary>
        public double ATR { get; internal set; }

        /// <summary>
        /// Current range width (High - Low over lookback).
        /// </summary>
        public double RangeWidth { get; internal set; }

        /// <summary>
        /// Volatility classification (Low/Mid/High).
        /// </summary>
        public VolatilityRegime VolatilityRegime { get; internal set; }

        /// <summary>
        /// High volatility flag (for module gating).
        /// </summary>
        public bool IsHighVol { get; internal set; }

        /// <summary>
        /// Low volatility flag.
        /// </summary>
        public bool IsLowVol { get; internal set; }

        #endregion

        #region Price Data

        /// <summary>
        /// Current bar open.
        /// </summary>
        public double Open { get; internal set; }

        /// <summary>
        /// Current bar high.
        /// </summary>
        public double High { get; internal set; }

        /// <summary>
        /// Current bar low.
        /// </summary>
        public double Low { get; internal set; }

        /// <summary>
        /// Current bar close.
        /// </summary>
        public double Close { get; internal set; }

        #endregion

        #region Position State (Read-Only)

        /// <summary>
        /// Current position state (Flat/Long/Short).
        /// </summary>
        public PositionState PositionState { get; internal set; }

        /// <summary>
        /// True if flat.
        /// </summary>
        public bool IsFlat => PositionState == PositionState.Flat;

        /// <summary>
        /// True if long.
        /// </summary>
        public bool IsLong => PositionState == PositionState.Long;

        /// <summary>
        /// True if short.
        /// </summary>
        public bool IsShort => PositionState == PositionState.Short;

        /// <summary>
        /// Entry price (if in position).
        /// </summary>
        public double EntryPrice { get; internal set; }

        /// <summary>
        /// Unrealized PnL in currency (if in position).
        /// </summary>
        public double UnrealizedPnL { get; internal set; }

        /// <summary>
        /// Current position quantity.
        /// </summary>
        public int PositionQuantity { get; internal set; }

        #endregion

        #region Risk State (Read-Only)

        /// <summary>
        /// Realized PnL today.
        /// </summary>
        public double DailyPnL { get; internal set; }

        /// <summary>
        /// Remaining daily loss buffer before lockout.
        /// </summary>
        public double RemainingDailyLossBuffer { get; internal set; }

        /// <summary>
        /// Remaining trailing drawdown buffer before lockout.
        /// </summary>
        public double RemainingDrawdownBuffer { get; internal set; }

        /// <summary>
        /// Trades taken today.
        /// </summary>
        public int TradesToday { get; internal set; }

        /// <summary>
        /// Remaining trades allowed today.
        /// </summary>
        public int RemainingTradesAllowed { get; internal set; }

        /// <summary>
        /// True if daily loss lockout is active.
        /// </summary>
        public bool IsDailyLossLockout { get; internal set; }

        /// <summary>
        /// True if trailing drawdown lockout is active.
        /// </summary>
        public bool IsDrawdownLockout { get; internal set; }

        /// <summary>
        /// True if any risk lockout is active.
        /// </summary>
        public bool IsRiskLockout => IsDailyLossLockout || IsDrawdownLockout;

        #endregion

        #region Router State (Read-Only)

        /// <summary>
        /// ModuleId of the last active (trading) module.
        /// </summary>
        public string LastActiveModuleId { get; internal set; }

        /// <summary>
        /// ModuleId of the module that owns the current position (if any).
        /// </summary>
        public string OwningModuleId { get; internal set; }

        /// <summary>
        /// True if module cooldown is active.
        /// </summary>
        public bool IsModuleCooldown { get; internal set; }

        /// <summary>
        /// Bars remaining in cooldown.
        /// </summary>
        public int CooldownBarsRemaining { get; internal set; }

        #endregion

        #region Gating Flags

        /// <summary>
        /// True if session/time gate allows trading.
        /// </summary>
        public bool SessionGateOpen { get; internal set; }

        /// <summary>
        /// True if volatility gate allows trading.
        /// </summary>
        public bool VolatilityGateOpen { get; internal set; }

        /// <summary>
        /// True if risk gate allows trading.
        /// </summary>
        public bool RiskGateOpen { get; internal set; }

        /// <summary>
        /// True if all gates allow trading.
        /// </summary>
        public bool AllGatesOpen => SessionGateOpen && VolatilityGateOpen && RiskGateOpen;

        #endregion

        /// <summary>
        /// Context is built by ContextBuilder only.
        /// </summary>
        internal Context() { }
    }
}

