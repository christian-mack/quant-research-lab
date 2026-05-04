#region Using declarations
using System;
#endregion

namespace NinjaTrader.NinjaScript.Strategies.Flux.Core
{
    /// <summary>
    /// Trade direction for module intents.
    /// </summary>
    public enum TradeDirection
    {
        None,
        Long,
        Short
    }

    /// <summary>
    /// Immutable trade intent emitted by modules.
    /// Modules emit intents; Flux decides whether to execute.
    /// </summary>
    public class TradeIntent
    {
        /// <summary>
        /// Singleton for no-trade intent.
        /// </summary>
        public static readonly TradeIntent None = new TradeIntent
        {
            ModuleId = "None",
            Direction = TradeDirection.None,
            Confidence = 0.0,
            ProposedStopTicks = 0,
            ProposedTargetTicks = 0,
            ManagementPlanId = "",
            ReasonCode = "NO_SIGNAL",
            EvaluationId = "NONE",
            SetupId = "NONE"
        };

        /// <summary>
        /// Unique identifier of the module that generated this intent.
        /// </summary>
        public string ModuleId { get; set; }

        /// <summary>
        /// Proposed trade direction.
        /// </summary>
        public TradeDirection Direction { get; set; }

        /// <summary>
        /// Confidence level (0.0 - 1.0). Optional in v1, defaults to 1.0.
        /// </summary>
        public double Confidence { get; set; }

        /// <summary>
        /// Proposed stop distance in ticks from entry.
        /// </summary>
        public int ProposedStopTicks { get; set; }

        /// <summary>
        /// Proposed target distance in ticks from entry.
        /// </summary>
        public int ProposedTargetTicks { get; set; }

        /// <summary>
        /// PHASE 12.10: Explicit stop price in price-space.
        /// When set (non-zero), this takes precedence over ProposedStopTicks.
        /// Used for parity mode where stop is computed in price-space without tick quantization.
        /// </summary>
        public double ExplicitStopPrice { get; set; }

        /// <summary>
        /// PHASE 12.10: Explicit target price in price-space.
        /// When set (non-zero), this takes precedence over ProposedTargetTicks.
        /// Used for parity mode where target is computed in price-space without tick quantization.
        /// </summary>
        public double ExplicitTargetPrice { get; set; }

        /// <summary>
        /// Execution plan identifier (e.g., "Range_Trail_1R").
        /// </summary>
        public string ManagementPlanId { get; set; }

        /// <summary>
        /// Short diagnostic label for logging/analytics.
        /// </summary>
        public string ReasonCode { get; set; }

        /// <summary>
        /// Evaluation identifier for setup evaluation (before direction is known).
        /// Format: YYYYMMDD-HHMM|EVAL|BarNumber
        /// </summary>
        public string EvaluationId { get; set; }

        /// <summary>
        /// Setup identifier for trade execution (after direction is known).
        /// Format: YYYYMMDD-HHMM|LONG|BarNumber or YYYYMMDD-HHMM|SHORT|BarNumber
        /// </summary>
        public string SetupId { get; set; }

        /// <summary>
        /// Creates a Long trade intent.
        /// </summary>
        public static TradeIntent Long(
            string moduleId,
            int stopTicks,
            int targetTicks,
            string managementPlanId,
            string reasonCode,
            string evaluationId,
            string setupId,
            double explicitStopPrice = 0.0,
            double explicitTargetPrice = 0.0,
            double confidence = 1.0)
        {
            return new TradeIntent
            {
                ModuleId = moduleId,
                Direction = TradeDirection.Long,
                Confidence = confidence,
                ProposedStopTicks = stopTicks,
                ProposedTargetTicks = targetTicks,
                ExplicitStopPrice = explicitStopPrice,
                ExplicitTargetPrice = explicitTargetPrice,
                ManagementPlanId = managementPlanId,
                ReasonCode = reasonCode,
                EvaluationId = evaluationId,
                SetupId = setupId
            };
        }

        /// <summary>
        /// Creates a Short trade intent.
        /// </summary>
        public static TradeIntent Short(
            string moduleId,
            int stopTicks,
            int targetTicks,
            string managementPlanId,
            string reasonCode,
            string evaluationId,
            string setupId,
            double explicitStopPrice = 0.0,
            double explicitTargetPrice = 0.0,
            double confidence = 1.0)
        {
            return new TradeIntent
            {
                ModuleId = moduleId,
                Direction = TradeDirection.Short,
                Confidence = confidence,
                ProposedStopTicks = stopTicks,
                ProposedTargetTicks = targetTicks,
                ExplicitStopPrice = explicitStopPrice,
                ExplicitTargetPrice = explicitTargetPrice,
                ManagementPlanId = managementPlanId,
                ReasonCode = reasonCode,
                EvaluationId = evaluationId,
                SetupId = setupId
            };
        }

        /// <summary>
        /// PHASE 12.10: Returns true if this intent has explicit price-space stop/target.
        /// </summary>
        public bool HasExplicitPrices => ExplicitStopPrice > 0 && ExplicitTargetPrice > 0;
    }

    /// <summary>
    /// Metadata about an opened trade, passed to modules for bookkeeping.
    /// </summary>
    public class TradeMetadata
    {
        public string ModuleId { get; set; }
        public TradeDirection Direction { get; set; }
        public double EntryPrice { get; set; }
        public double StopPrice { get; set; }
        public double TargetPrice { get; set; }
        public DateTime EntryTime { get; set; }
        public int EntryBar { get; set; }
    }

    /// <summary>
    /// Result of a closed trade, passed to modules for bookkeeping.
    /// </summary>
    public class TradeResult
    {
        public string ModuleId { get; set; }
        public TradeDirection Direction { get; set; }
        public double EntryPrice { get; set; }
        public double ExitPrice { get; set; }
        public double RealizedPnL { get; set; }
        public double RMultiple { get; set; }
        public string ExitReason { get; set; }
        public DateTime EntryTime { get; set; }
        public DateTime ExitTime { get; set; }
        public int DurationBars { get; set; }
    }

    /// <summary>
    /// Module contract for Flux v1.
    /// Modules emit TradeIntents; they never place orders.
    /// </summary>
    public interface IModule
    {
        /// <summary>
        /// Unique, stable identifier for logging/routing.
        /// </summary>
        string ModuleId { get; }

        /// <summary>
        /// Called every bar when the module is eligible.
        /// Must be deterministic and side-effect free.
        /// Returns TradeIntent.None when no valid setup exists.
        /// </summary>
        TradeIntent Evaluate(Context context);

        /// <summary>
        /// Notification hook when a trade is opened. For bookkeeping only.
        /// </summary>
        void OnTradeOpened(TradeMetadata trade);

        /// <summary>
        /// Notification hook when a trade is closed. For bookkeeping only.
        /// </summary>
        void OnTradeClosed(TradeResult result);

        /// <summary>
        /// Called at session reset to clear module-local counters/state.
        /// </summary>
        void ResetDaily();
    }
}

