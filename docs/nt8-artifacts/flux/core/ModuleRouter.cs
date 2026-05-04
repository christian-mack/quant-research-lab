#region Using declarations
using System;
using System.Collections.Generic;
using System.Linq;
#endregion

namespace NinjaTrader.NinjaScript.Strategies.Flux.Core
{
    /// <summary>
    /// Routing result containing selected intent and metadata.
    /// </summary>
    public class RoutingResult
    {
        public bool HasIntent { get; private set; }
        public TradeIntent Intent { get; private set; }
        public string SelectedModuleId { get; private set; }
        public string BlockReason { get; private set; }

        private RoutingResult() { }

        public static RoutingResult Selected(TradeIntent intent)
        {
            return new RoutingResult
            {
                HasIntent = true,
                Intent = intent,
                SelectedModuleId = intent.ModuleId,
                BlockReason = null
            };
        }

        public static RoutingResult NoIntent(string reason)
        {
            return new RoutingResult
            {
                HasIntent = false,
                Intent = TradeIntent.None,
                SelectedModuleId = null,
                BlockReason = reason
            };
        }
    }

    /// <summary>
    /// Routes trade decisions to modules in priority order.
    /// Enforces one module active at a time (v1 constraint).
    /// </summary>
    public class ModuleRouter
    {
        private readonly Config _config;
        private readonly Logger _logger;
        private readonly RegimeGate _regimeGate;
        private readonly List<IModule> _modules;
        private readonly Dictionary<string, IModule> _moduleIndex;

        // Cooldown tracking per module
        private readonly Dictionary<string, int> _moduleCooldownUntilBar;

        // Active trade ownership
        private string _owningModuleId;

        // Diagnostic counters (PHASE 6: Trade Count Diagnostics)
        public long BarsRangeEvaluated { get; private set; }
        public long BarsRangeReturnedNone { get; private set; }

        // PHASE 12.1: Momentum surgical gating
        private int _momentumConsecutiveLosses = 0;
        private DateTime _momentumCooldownExpiryTime = DateTime.MinValue;
        private long _momentumPowerHourRejects = 0;
        private long _momentumCooldownRejects = 0;

        // PHASE 13: Momentum daily profit cap tracking
        private double _momentumDailyRealizedPnL = 0.0;
        private long _momentumProfitCapRejects = 0;

        // PHASE 13.1: Momentum daily trade counter
        private int _momentumDailyTradeCount = 0;
        private long _momentumMaxTradesRejects = 0;

        public ModuleRouter(Config config, Logger logger, RegimeGate regimeGate)
        {
            _config = config ?? throw new ArgumentNullException(nameof(config));
            _logger = logger ?? throw new ArgumentNullException(nameof(logger));
            _regimeGate = regimeGate ?? throw new ArgumentNullException(nameof(regimeGate));
            _modules = new List<IModule>();
            _moduleIndex = new Dictionary<string, IModule>();
            _moduleCooldownUntilBar = new Dictionary<string, int>();
        }

        /// <summary>
        /// Registers a module with the router.
        /// </summary>
        public void RegisterModule(IModule module)
        {
            if (module == null)
                throw new ArgumentNullException(nameof(module));

            if (_moduleIndex.ContainsKey(module.ModuleId))
                throw new InvalidOperationException($"Module {module.ModuleId} already registered");

            _modules.Add(module);
            _moduleIndex[module.ModuleId] = module;
            _moduleCooldownUntilBar[module.ModuleId] = 0;

            _logger.LogDebug($"Module registered: {module.ModuleId}");
        }

        /// <summary>
        /// Routes to modules in priority order and returns first valid intent.
        /// </summary>
        public RoutingResult Route(Context context)
        {
            return RouteWithDebug(context, null);
        }

        /// <summary>
        /// Routes to modules with debug toggle support.
        /// </summary>
        public RoutingResult RouteWithDebug(Context context, Config config)
        {
            // 1. If position is open, only the owning module can manage it
            if (!context.IsFlat && !string.IsNullOrEmpty(_owningModuleId))
            {
                if (context.Timestamp.Hour >= 17)
                    _logger.LogInfo($"[FLUX][EVENING_DIAG] ROUTER_POSITION_BLOCK Time={context.Timestamp:yyyy-MM-dd HH:mm}, Owner={_owningModuleId}");
                return RoutingResult.NoIntent("POSITION_OPEN_OWNED");
            }

            // 2. Check module cooldown
            if (context.IsModuleCooldown)
            {
                if (context.Timestamp.Hour >= 17)
                    _logger.LogInfo($"[FLUX][EVENING_DIAG] ROUTER_COOLDOWN_BLOCK Time={context.Timestamp:yyyy-MM-dd HH:mm}, CooldownBars={context.CooldownBarsRemaining}");
                return RoutingResult.NoIntent("MODULE_COOLDOWN");
            }

            // 3. Evaluate modules in priority order
            foreach (var moduleId in _config.ModulePriorities)
            {
                if (!_moduleIndex.TryGetValue(moduleId, out var module))
                    continue;

                // Check if module is enabled
                if (!IsModuleEnabled(moduleId))
                    continue;

                // PHASE 12.1: Momentum surgical gating
                // PHASE 12.3: Bypass Momentum gating for semantic parity verification
                // PHASE 12.10: Disable all Flux-specific gating in parity mode
                if (moduleId == "Momentum" && 
                    (config == null || !config.DebugDisableMomentumGates) &&
                    (config == null || !config.MomentumParityMode))
                {
                    // Gate 1: Power Hour Time Block (14:00-15:00 CT)
                    if (IsPowerHourBlock(context))
                    {
                        _momentumPowerHourRejects++;
                        _logger.LogInfo($"[FLUX][MOMENTUM][REJECT_TIME_BLOCK_POWER_HOUR] Timestamp={context.Timestamp:HH:mm}, CurrentBar={context.CurrentBar}");
                        continue;
                    }
                }

                // PHASE 13.1: Momentum loss-streak cooldown — INDEPENDENT of parity mode
                // After 3 consecutive losses, pause Momentum for 60 minutes.
                // This gate must work regardless of parity mode since it directly drives DD.
                if (moduleId == "Momentum" && IsMomentumCooldownActive(context))
                {
                    _momentumCooldownRejects++;
                    if (_momentumCooldownRejects <= 5)
                    {
                        _logger.LogInfo($"[FLUX][MOMENTUM][REJECT_COOLDOWN_LOSS_STREAK] Timestamp={context.Timestamp:HH:mm}, CurrentBar={context.CurrentBar}, CooldownExpiry={_momentumCooldownExpiryTime:HH:mm}");
                    }
                    continue;
                }

                // PHASE 13: Momentum daily profit cap gate (always active when cap > 0)
                // This is independent of parity mode — it's a risk/optimization filter
                if (moduleId == "Momentum" && config != null && config.MomentumDailyProfitCap > 0)
                {
                    if (_momentumDailyRealizedPnL >= config.MomentumDailyProfitCap)
                    {
                        _momentumProfitCapRejects++;
                        if (_momentumProfitCapRejects <= 5) // Log first 5 per day, then suppress
                        {
                            _logger.LogInfo($"[FLUX][MOMENTUM][REJECT_DAILY_PROFIT_CAP] Timestamp={context.Timestamp:HH:mm}, " +
                                $"CurrentBar={context.CurrentBar}, DailyPnL=${_momentumDailyRealizedPnL:F2}, Cap=${config.MomentumDailyProfitCap:F2}");
                        }
                        continue;
                    }
                }

                // PHASE 13.1: Momentum max daily trades gate (0 = unlimited)
                if (moduleId == "Momentum" && config != null && config.MomentumMaxDailyTrades > 0)
                {
                    if (_momentumDailyTradeCount >= config.MomentumMaxDailyTrades)
                    {
                        _momentumMaxTradesRejects++;
                        if (_momentumMaxTradesRejects <= 3)
                        {
                            _logger.LogInfo($"[FLUX][MOMENTUM][REJECT_MAX_DAILY_TRADES] Timestamp={context.Timestamp:HH:mm}, " +
                                $"CurrentBar={context.CurrentBar}, DailyTrades={_momentumDailyTradeCount}, Max={config.MomentumMaxDailyTrades}");
                        }
                        continue;
                    }
                }

                // PHASE 13.1: Range blocked hours gate (CT)
                if (moduleId == "Range" && config != null && config.RangeBlockedHoursSet != null && config.RangeBlockedHoursSet.Count > 0)
                {
                    int rangeBarHourCT = context.Timestamp.Hour;
                    if (config.RangeBlockedHoursSet.Contains(rangeBarHourCT))
                    {
                        if (context.Timestamp.Hour >= 17)
                            _logger.LogInfo($"[FLUX][EVENING_DIAG] RANGE_BLOCKED_HOUR Time={context.Timestamp:yyyy-MM-dd HH:mm}, BlockedHour={rangeBarHourCT}");
                        continue;
                    }
                }

                // Check if module is in cooldown
                if (_moduleCooldownUntilBar.TryGetValue(moduleId, out var cooldownUntil))
                {
                    if (context.CurrentBar < cooldownUntil)
                    {
                        if (moduleId == "Range" && context.Timestamp.Hour >= 17)
                            _logger.LogInfo($"[FLUX][EVENING_DIAG] RANGE_MODULE_COOLDOWN Time={context.Timestamp:yyyy-MM-dd HH:mm}, Bar={context.CurrentBar}, CooldownUntil={cooldownUntil}");
                        continue;
                    }
                }

                // Check module-specific volatility gate - with debug toggle
                var volResult = _regimeGate.EvaluateModuleVolatility(context, moduleId);
                bool volatilityBlocked = !volResult.IsOpen && (config == null || !config.DebugForceRangeEnabled || moduleId != "Range");
                if (volatilityBlocked)
                {
                    if (moduleId == "Range" && context.Timestamp.Hour >= 17)
                        _logger.LogInfo($"[FLUX][EVENING_DIAG] RANGE_VOL_BLOCKED Time={context.Timestamp:yyyy-MM-dd HH:mm}, Reason={volResult.Reason}");
                    _logger.LogGateBlocked($"ModuleVol_{moduleId}", volResult.Reason);
                    continue;
                }

                // Evaluate module
                TradeIntent intent;
                try
                {
                    intent = module.Evaluate(context);
                }
                catch (Exception ex)
                {
                    _logger.LogError($"Module {moduleId} evaluation failed", ex);
                    continue;
                }

                // Track Range module evaluation (PHASE 6: Trade Count Diagnostics)
                if (moduleId == "Range")
                {
                    BarsRangeEvaluated++;
                    if (intent == null || intent.Direction == TradeDirection.None)
                    {
                        BarsRangeReturnedNone++;
                    }
                }

                _logger.LogModuleEvaluated(moduleId, intent);

                // PHASE 6.6: Log routing decision
                bool isEligible = intent != null && intent.Direction != TradeDirection.None;
                string rejectionReason = isEligible ? null : "MODULE_RETURNED_NONE";

                if (isEligible)
                {
                    // Module produced valid intent - log with SetupId
                    _logger.LogInfo($"[FLUX][ROUTER] SetupId={intent.SetupId}, ModuleName={moduleId}, Eligible=true, RejectionReason=NONE");
                }
                else
                {
                    // Module returned NONE - log with EvaluationId if available
                    string evaluationId = intent?.EvaluationId ?? "UNKNOWN";
                    string rejectionReasonStr = rejectionReason ?? "NONE";
                    _logger.LogInfo($"[FLUX][ROUTER] EvaluationId={evaluationId}, ModuleName={moduleId}, Eligible=false, RejectionReason={rejectionReasonStr}");
                }

                // Check if intent is valid
                if (intent != null && intent.Direction != TradeDirection.None)
                {
                    _logger.LogModuleSelected(moduleId, intent);
                    return RoutingResult.Selected(intent);
                }
            }

            return RoutingResult.NoIntent("NO_VALID_INTENT");
        }

        /// <summary>
        /// Sets the owning module for the current position.
        /// </summary>
        public void SetOwningModule(string moduleId)
        {
            _owningModuleId = moduleId;
        }

        /// <summary>
        /// Clears position ownership and applies cooldown.
        /// </summary>
        public void ClearOwningModule(int currentBar)
        {
            if (!string.IsNullOrEmpty(_owningModuleId))
            {
                _moduleCooldownUntilBar[_owningModuleId] = currentBar + _config.ModuleCooldownBars;
            }
            _owningModuleId = null;
        }

        /// <summary>
        /// Gets the module that owns the current position.
        /// </summary>
        public string GetOwningModuleId()
        {
            return _owningModuleId;
        }

        /// <summary>
        /// Gets a module by ID.
        /// </summary>
        public IModule GetModule(string moduleId)
        {
            _moduleIndex.TryGetValue(moduleId, out var module);
            return module;
        }

        /// <summary>
        /// Notifies the owning module that a trade was opened.
        /// </summary>
        public void NotifyTradeOpened(TradeMetadata trade)
        {
            if (_moduleIndex.TryGetValue(trade.ModuleId, out var module))
            {
                try
                {
                    module.OnTradeOpened(trade);
                }
                catch (Exception ex)
                {
                    _logger.LogError($"Module {trade.ModuleId} OnTradeOpened failed", ex);
                }
            }
        }

        /// <summary>
        /// Notifies the owning module that a trade was closed.
        /// </summary>
        public void NotifyTradeClosed(TradeResult result)
        {
            if (_moduleIndex.TryGetValue(result.ModuleId, out var module))
            {
                try
                {
                    module.OnTradeClosed(result);
                }
                catch (Exception ex)
                {
                    _logger.LogError($"Module {result.ModuleId} OnTradeClosed failed", ex);
                }
            }

            // PHASE 12.1: Track Momentum consecutive losses for surgical gating
            if (result.ModuleId == "Momentum")
            {
                // PHASE 13: Accumulate daily realized P&L for profit cap
                _momentumDailyRealizedPnL += result.RealizedPnL;
                
                // PHASE 13.1: Increment daily trade counter
                _momentumDailyTradeCount++;
                
                _logger.LogInfo($"[FLUX][MOMENTUM][DAILY_PNL] TradeResult={result.RealizedPnL:F2}, DailyTotal={_momentumDailyRealizedPnL:F2}, DailyTrades={_momentumDailyTradeCount}, Cap={_config.MomentumDailyProfitCap:F2}");

                if (result.RealizedPnL < 0)
                {
                    _momentumConsecutiveLosses++;
                    _logger.LogDebug($"[FLUX][MOMENTUM] Consecutive losses: {_momentumConsecutiveLosses}");

                    // Activate 60-minute cooldown after 3rd consecutive loss
                    if (_momentumConsecutiveLosses >= 3)
                    {
                        _momentumCooldownExpiryTime = result.ExitTime.AddMinutes(60);
                        _logger.LogInfo($"[FLUX][MOMENTUM][COOLDOWN_START] ConsecutiveLosses={_momentumConsecutiveLosses}, ExitTime={result.ExitTime:HH:mm}, CooldownExpiry={_momentumCooldownExpiryTime:HH:mm}, Duration=60m");
                    }
                }
                else
                {
                    // Win resets the loss counter
                    _momentumConsecutiveLosses = 0;
                }
            }
        }

        /// <summary>
        /// Resets all modules for new session.
        /// </summary>
        public void ResetDaily()
        {
            foreach (var module in _modules)
            {
                try
                {
                    module.ResetDaily();
                }
                catch (Exception ex)
                {
                    _logger.LogError($"Module {module.ModuleId} ResetDaily failed", ex);
                }
            }

            _owningModuleId = null;
            var moduleIds = new List<string>(_moduleCooldownUntilBar.Keys);
            foreach (var moduleId in moduleIds)
            {
                _moduleCooldownUntilBar[moduleId] = 0;
            }

            // Reset diagnostic counters
            BarsRangeEvaluated = 0;
            BarsRangeReturnedNone = 0;

            // PHASE 12.1: Reset Momentum surgical gating state
            _momentumConsecutiveLosses = 0;
            _momentumCooldownExpiryTime = DateTime.MinValue;
            _momentumPowerHourRejects = 0;
            _momentumCooldownRejects = 0;

            // PHASE 13: Reset Momentum daily profit cap tracking
            _momentumDailyRealizedPnL = 0.0;
            _momentumProfitCapRejects = 0;
            _momentumDailyTradeCount = 0;
            _momentumMaxTradesRejects = 0;
        }

        private bool IsModuleEnabled(string moduleId)
        {
            switch (moduleId)
            {
                case "Range":
                    return _config.EnableRangeModule;
                case "Momentum":
                    return _config.EnableMomentumModule;
                case "ORB":
                    return _config.EnableORBModule;
                case "AfternoonMR":
                    return _config.EnableAfternoonMRModule;
                case "CloseCont":
                    return _config.EnableCloseContModule;
                default:
                    return false;
            }
        }

        #region PHASE 12.1: Momentum Surgical Gating

        /// <summary>
        /// Checks if current time is within Power Hour block (14:00-15:00 CT).
        /// </summary>
        private bool IsPowerHourBlock(Context context)
        {
            // Context.Timestamp is in Central Time (CT)
            int hour = context.Timestamp.Hour;
            int minute = context.Timestamp.Minute;

            // Block window: 14:00 to 15:00 CT (inclusive start, exclusive end)
            bool isInBlock = (hour == 14) || (hour == 15 && minute == 0);
            return isInBlock;
        }

        /// <summary>
        /// Checks if Momentum module is in loss-streak cooldown.
        /// </summary>
        private bool IsMomentumCooldownActive(Context context)
        {
            // If no cooldown has been set, not in cooldown
            if (_momentumCooldownExpiryTime == DateTime.MinValue)
                return false;

            // Check if cooldown has expired
            if (context.Timestamp >= _momentumCooldownExpiryTime)
            {
                // Cooldown expired - reset state
                _momentumCooldownExpiryTime = DateTime.MinValue;
                _momentumConsecutiveLosses = 0;
                _logger.LogInfo($"[FLUX][MOMENTUM][COOLDOWN_EXPIRED] Timestamp={context.Timestamp:HH:mm}, MomentumTradingResumed=true");
                return false;
            }

            // Still in cooldown
            return true;
        }

        #endregion

    }
}