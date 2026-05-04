#region Using declarations
using System;
using NinjaTrader.Cbi;
#endregion

namespace NinjaTrader.NinjaScript.Strategies.Flux.Core
{
    /// <summary>
    /// Exit reason classification.
    /// </summary>
    public enum ExitReason
    {
        None,
        StopLoss,
        ProfitTarget,
        TrailingStop,
        RiskLockout,
        ExecutionProtectionFailure,
        ManualClose,
        SessionClose
    }

    /// <summary>
    /// Management plan for trade execution.
    /// </summary>
    public class ManagementPlan
    {
        public string PlanId { get; set; }
        public int InitialStopTicks { get; set; }
        public int InitialTargetTicks { get; set; }
        public double TrailingActivationR { get; set; }
        public double TrailingDistanceR { get; set; }
        public bool EnableTrailing { get; set; }
        // PHASE 12.10: Auto break-even parameters
        public bool EnableAutoBreakEven { get; set; }
        public double BreakEvenTriggerR { get; set; }
    }

    /// <summary>
    /// Current position management state.
    /// </summary>
    public class PositionManagementState
    {
        public string ModuleId { get; set; }
        public string ManagementPlanId { get; set; }
        public TradeDirection Direction { get; set; }
        public double EntryPrice { get; set; }
        public double InitialStopPrice { get; set; }
        public double CurrentStopPrice { get; set; }
        public double TargetPrice { get; set; }
        public double RiskAmount { get; set; }
        public int EntryBar { get; set; }
        public DateTime EntryTime { get; set; }
        public double MaxFavorablePrice { get; set; }
        public bool TrailingActivated { get; set; }
        public bool IsActive { get; set; }
        // PHASE 6.5: Add SetupId for parity audit logging
        public string SetupId { get; set; }
        // PHASE 12.10: Break-even state tracking
        public bool BreakEvenActivated { get; set; }
        // PHASE 12.11a: Explicit trade quantity - single source of truth for position sizing
        // This is set at trade open and never changes, ensuring quantity invariance.
        // PnL calculations must use this, not Position.Quantity or execution fills.
        public int TradeQuantity { get; set; }
    }

    /// <summary>
    /// Centralized execution engine for Flux v1.
    /// The only component allowed to interact with NinjaTrader orders.
    /// Modules never place orders - ExecutionEngine is the sole order authority.
    /// </summary>
    public class ExecutionEngine
    {
        private readonly Strategy _strategy;
        private readonly Config _config;
        private readonly Logger _logger;

        // PHASE 14: Optional two-tier dynamic sizer (null when disabled)
        private DynamicSizer _dynamicSizer;

        // Position management state
        private PositionManagementState _positionState;

        // Fill price tracking state (PHASE 6: Exit Fill Price Capture)
        private double _entryFillPrice;
        private int _entryQty;
        private double _exitFillPrice;
        private int _exitQty;
        private bool _hasOpenTrade;
        private bool _hasExitFill;

        // Order name constants
        private const string EXIT_NAME = "FluxExit";
        
        /// <summary>
        /// Builds module-attributed entry name per Phase 12.8 requirements.
        /// Format: Flux_&lt;ModuleName&gt;_&lt;Direction&gt;
        /// </summary>
        private string BuildEntryName(string moduleId, TradeDirection direction)
        {
            string directionStr = direction == TradeDirection.Long ? "LONG" : "SHORT";
            return $"Flux_{moduleId}_{directionStr}";
        }

        /// <summary>
        /// Resolves the position size for a given module.
        /// When DynamicSizer is active, delegates to it; otherwise uses static config.
        /// </summary>
        private int ResolveModuleQuantity(string moduleId)
        {
            if (_dynamicSizer != null)
                return _dynamicSizer.GetModuleQty(moduleId);

            switch (moduleId)
            {
                case "Momentum":
                    return Math.Max(1, Math.Min(_config.MomentumQuantity, 100));
                case "ORB":
                    return Math.Max(1, Math.Min(_config.ORBQuantity, 100));
                case "Range":
                    return Math.Max(1, Math.Min(_config.RangeQuantity, 100));
                case "AfternoonMR":
                    return Math.Max(1, Math.Min(_config.AfternoonMRQuantity, 100));
                case "CloseCont":
                    return Math.Max(1, Math.Min(_config.CloseContQuantity, 100));
                default:
                    _logger.LogInfo($"[FLUX][QUANTITY] Unknown module '{moduleId}', using default quantity=1");
                    return 1;
            }
        }

        // Management plans registry
        private readonly System.Collections.Generic.Dictionary<string, ManagementPlan> _plans;

        public ExecutionEngine(Strategy strategy, Config config, Logger logger)
        {
            _strategy = strategy ?? throw new ArgumentNullException(nameof(strategy));
            _config = config ?? throw new ArgumentNullException(nameof(config));
            _logger = logger ?? throw new ArgumentNullException(nameof(logger));
            _plans = new System.Collections.Generic.Dictionary<string, ManagementPlan>();

            // Initialize fill tracking state
            ResetFillState();

            // Register default plans
            RegisterPlan(new ManagementPlan
            {
                PlanId = "Range_Trail_1R",
                InitialStopTicks = 0, // Will be set from intent
                InitialTargetTicks = 0, // Will be set from intent
                TrailingActivationR = _config.RangeTrailingActivation,
                TrailingDistanceR = _config.RangeTrailingDistance,
                EnableTrailing = true,
                EnableAutoBreakEven = false, // Range uses trailing, not BE
                BreakEvenTriggerR = 0
            });

            // PHASE 12.10: Register Momentum execution plan with parity mode settings
            RegisterPlan(new ManagementPlan
            {
                PlanId = "Momentum_WPR_Mean_Reversion",
                InitialStopTicks = 0, // Will be set from intent
                InitialTargetTicks = 0, // Will be set from intent
                TrailingActivationR = 0, // Not used (trailing disabled in parity mode)
                TrailingDistanceR = 0, // Not used (trailing disabled in parity mode)
                EnableTrailing = false, // No trailing - standalone doesn't actually call UpdateTrailingStops()
                EnableAutoBreakEven = _config.MomentumEnableAutoBreakEven, // From config (default: true)
                BreakEvenTriggerR = _config.MomentumBETriggerR // From config (default: 1.5)
            });

            // Register ORB execution plan (locked parameters from optimization)
            RegisterPlan(new ManagementPlan
            {
                PlanId = "ORB_Breakout",
                InitialStopTicks = 0, // Will be set from intent
                InitialTargetTicks = 0, // Will be set from intent
                TrailingActivationR = 0, // Not used - ORB uses break-even, not trailing
                TrailingDistanceR = 0,
                EnableTrailing = false,
                EnableAutoBreakEven = _config.ORBEnableBreakEven, // From config (default: true)
                BreakEvenTriggerR = _config.ORBBETriggerR // From config (default: 1.0)
            });

            // PHASE 15: AfternoonMR execution plan
            RegisterPlan(new ManagementPlan
            {
                PlanId = "AfternoonMR_VWAP_Fade",
                InitialStopTicks = 0,
                InitialTargetTicks = 0,
                TrailingActivationR = 0,
                TrailingDistanceR = 0,
                EnableTrailing = false,
                EnableAutoBreakEven = _config.AfternoonMREnableBreakEven,
                BreakEvenTriggerR = _config.AfternoonMRBETriggerR
            });

            // PHASE 17: CloseCont execution plan
            RegisterPlan(new ManagementPlan
            {
                PlanId = "CloseCont_MOC_Continuation",
                InitialStopTicks = 0,
                InitialTargetTicks = 0,
                TrailingActivationR = 0,
                TrailingDistanceR = 0,
                EnableTrailing = false,
                EnableAutoBreakEven = _config.CloseContEnableBreakEven,
                BreakEvenTriggerR = _config.CloseContBETriggerR
            });
        }

        /// <summary>
        /// PHASE 14: Attaches the two-tier dynamic sizer for position scaling.
        /// When set, ResolveModuleQuantity delegates to the sizer instead of static config.
        /// </summary>
        public void SetDynamicSizer(DynamicSizer sizer)
        {
            _dynamicSizer = sizer;
        }

        /// <summary>
        /// Registers a management plan.
        /// </summary>
        public void RegisterPlan(ManagementPlan plan)
        {
            _plans[plan.PlanId] = plan;
        }

        /// <summary>
        /// Resets fill tracking state.
        /// </summary>
        private void ResetFillState()
        {
            _entryFillPrice = 0.0;
            _entryQty = 0;
            _exitFillPrice = 0.0;
            _exitQty = 0;
            _hasOpenTrade = false;
            _hasExitFill = false;
        }

        /// <summary>
        /// Validates a trade intent before execution.
        /// Returns true if valid, false with reason if invalid.
        /// </summary>
        public (bool IsValid, string Reason) ValidateIntent(TradeIntent intent, Context context)
        {
            // 1. Direction must be valid
            if (intent.Direction == TradeDirection.None)
            {
                return (false, "DIRECTION_NONE");
            }

            // 2. Must be flat to enter
            if (!context.IsFlat)
            {
                return (false, "POSITION_EXISTS");
            }

            // PHASE 12.10: Skip tick-based validation if intent has explicit prices
            if (!intent.HasExplicitPrices)
            {
                // 3. Stop distance validation
                if (intent.ProposedStopTicks < _config.MinStopTicks)
                {
                    return (false, $"STOP_TOO_TIGHT:{intent.ProposedStopTicks}<{_config.MinStopTicks}");
                }

                if (intent.ProposedStopTicks > _config.MaxStopTicks)
                {
                    return (false, $"STOP_TOO_WIDE:{intent.ProposedStopTicks}>{_config.MaxStopTicks}");
                }

                // 4. Target distance validation
                if (intent.ProposedTargetTicks < _config.MinTargetTicks)
                {
                    return (false, $"TARGET_TOO_TIGHT:{intent.ProposedTargetTicks}<{_config.MinTargetTicks}");
                }
            }
            else
            {
                // PHASE 12.10: Basic sanity check for explicit prices
                if (intent.ExplicitStopPrice <= 0 || intent.ExplicitTargetPrice <= 0)
                {
                    return (false, "EXPLICIT_PRICE_INVALID");
                }
            }

            // 5. Management plan must exist
            if (!_plans.ContainsKey(intent.ManagementPlanId))
            {
                return (false, $"PLAN_NOT_FOUND:{intent.ManagementPlanId}");
            }

            return (true, "VALID");
        }

        /// <summary>
        /// Executes a validated trade intent.
        /// Submits entry order with attached stop and target (atomic).
        /// </summary>
        public bool ExecuteIntent(TradeIntent intent, Context context)
        {
            // PHASE 6.6: Use SetupId from TradeIntent
            string setupId = intent.SetupId;

            // Validate first
            var (isValid, reason) = ValidateIntent(intent, context);
            if (!isValid)
            {
                _logger.LogIntentRejected(intent.ModuleId, reason);
                return false;
            }

            // Log plan resolution
            _logger.LogInfo($"[FLUX][EXEC] PLAN_RESOLVED Plan={intent.ManagementPlanId} SetupId={intent.SetupId}");

            // PHASE 12.10: Calculate prices - use explicit prices if available (parity mode)
            double entryPrice = context.Close;
            double stopPrice;
            double targetPrice;
            double tickSize = context.TickSize;

            // Check if intent has explicit price-space stop/target (from Momentum parity mode)
            if (intent.HasExplicitPrices)
            {
                // PHASE 12.10: Use explicit prices (no tick quantization)
                stopPrice = intent.ExplicitStopPrice;
                targetPrice = intent.ExplicitTargetPrice;
                _logger.LogInfo($"[FLUX][EXEC] PARITY_MODE Using explicit prices: Stop={stopPrice:F2}, Target={targetPrice:F2}");
            }
            else
            {
                // Standard tick-based calculation
                if (intent.Direction == TradeDirection.Long)
                {
                    stopPrice = entryPrice - (intent.ProposedStopTicks * tickSize);
                    targetPrice = entryPrice + (intent.ProposedTargetTicks * tickSize);
                }
                else // Short
                {
                    stopPrice = entryPrice + (intent.ProposedStopTicks * tickSize);
                    targetPrice = entryPrice - (intent.ProposedTargetTicks * tickSize);
                }
            }

            // Initialize fill tracking state
            ResetFillState();
            _hasOpenTrade = true;

            // Resolve per-module position size from config
            int tradeQuantity = ResolveModuleQuantity(intent.ModuleId);

            // Initialize position management state BEFORE placing orders
            _positionState = new PositionManagementState
            {
                ModuleId = intent.ModuleId,
                ManagementPlanId = intent.ManagementPlanId,
                Direction = intent.Direction,
                EntryPrice = entryPrice,
                InitialStopPrice = stopPrice,
                CurrentStopPrice = stopPrice,
                TargetPrice = targetPrice,
                RiskAmount = intent.ProposedStopTicks * tickSize * context.PointValue,
                EntryBar = context.CurrentBar,
                EntryTime = context.Timestamp,
                MaxFavorablePrice = entryPrice,
                TrailingActivated = false,
                IsActive = true,
                SetupId = setupId,
                TradeQuantity = tradeQuantity
            };

            try
            {
                // Build module-attributed entry name (Phase 12.8)
                string entryName = BuildEntryName(intent.ModuleId, intent.Direction);
                
                // Log execution start with attribution
                _logger.LogInfo($"[FLUX][EXEC] EXECUTE Plan={intent.ManagementPlanId} StopTicks={intent.ProposedStopTicks} TargetTicks={intent.ProposedTargetTicks} Quantity={tradeQuantity}");

                // Set stop and target BEFORE entry (managed approach)
                _strategy.SetStopLoss(CalculationMode.Price, stopPrice);
                _strategy.SetProfitTarget(CalculationMode.Price, targetPrice);

                // Submit entry with per-module quantity
                if (intent.Direction == TradeDirection.Long)
                {
                    _strategy.EnterLong(tradeQuantity, entryName);
                }
                else
                {
                    _strategy.EnterShort(tradeQuantity, entryName);
                }

                // Phase 12.8: Log execution confirmation with module attribution
                string directionStr = intent.Direction == TradeDirection.Long ? "LONG" : "SHORT";
                _logger.LogInfo($"[FLUX][EXECUTE] Module={intent.ModuleId}, Direction={directionStr}, EntryName={entryName}");
                
                _logger.LogOrderSubmitted(intent.ModuleId, intent.Direction, entryPrice);
                return true;
            }
            catch (Exception ex)
            {
                _logger.LogError($"Order submission failed: {ex.Message}", ex);
                _positionState = null;
                return false;
            }
        }

        /// <summary>
        /// Called when an order is filled.
        /// Verifies protective orders and updates state.
        /// </summary>
        public void OnOrderFilled(double fillPrice, int quantity)
        {
            if (_positionState == null)
            {
                _logger.LogError("Order filled but no position state exists");
                return;
            }

            int executedQty = Math.Abs(quantity);

            // Update position state with executed quantity
            _positionState.TradeQuantity = executedQty;

            // DEBUG: Log the executed quantity
            _logger.LogInfo($"[FLUX][QUANTITY][EXECUTED] Quantity={executedQty}");

            // Capture entry fill price (PHASE 6: Exit Fill Price Capture)
            _entryFillPrice = fillPrice;
            _entryQty = executedQty;

            // Update entry price to actual fill
            _positionState.EntryPrice = fillPrice;
            _positionState.MaxFavorablePrice = fillPrice;

            // Recalculate stop/target based on actual fill
            double tickSize = _strategy.TickSize;
            double originalRiskDistance = Math.Abs(_positionState.EntryPrice - _positionState.InitialStopPrice);

            if (_positionState.Direction == TradeDirection.Long)
            {
                // Maintain same risk distance from actual fill price
                _positionState.InitialStopPrice = fillPrice - originalRiskDistance;
                _positionState.CurrentStopPrice = _positionState.InitialStopPrice;
            }
            else // Short
            {
                // Maintain same risk distance from actual fill price
                _positionState.InitialStopPrice = fillPrice + originalRiskDistance;
                _positionState.CurrentStopPrice = _positionState.InitialStopPrice;
            }

            // PHASE 6.5: Log position opened with SetupId
            int logQuantity = _positionState.Direction == TradeDirection.Long ? 1 : -1;
            _logger.LogInfo($"[FLUX][EXECUTE][OPEN] SetupId={_positionState.SetupId}, EntryPrice={fillPrice:F2}, Quantity={logQuantity}");
            
            // PHASE 12.11a: Diagnostic log for quantity invariance validation
            // This log can be diff'd across quantity settings to verify identical trade timing
            _logger.LogInfo($"[FLUX][INVARIANCE][ENTRY] Bar={_positionState.EntryBar}, Time={_positionState.EntryTime:yyyy-MM-dd HH:mm}, " +
                $"Module={_positionState.ModuleId}, Direction={_positionState.Direction}, " +
                $"EntryPrice={fillPrice:F2}, StopPrice={_positionState.CurrentStopPrice:F2}, " +
                $"TargetPrice={_positionState.TargetPrice:F2}, TradeQty={_positionState.TradeQuantity}");

            _logger.LogPositionOpened(
                _positionState.ModuleId,
                _positionState.Direction,
                fillPrice,
                _positionState.CurrentStopPrice,
                _positionState.TargetPrice);
        }

        /// <summary>
        /// Called when an exit order is filled.
        /// Captures exit fill price for accurate PnL calculation.
        /// </summary>
        public void OnExitFilled(double fillPrice, int quantity)
        {
            if (!_hasOpenTrade)
            {
                _logger.LogError("Exit filled but no open trade exists");
                return;
            }

            // Capture exit fill price (PHASE 6: Exit Fill Price Capture)
            _exitFillPrice = fillPrice;
            _exitQty = Math.Abs(quantity);
            _hasExitFill = true;

            _logger.LogDebug($"Exit fill captured: price={fillPrice:F2}, qty={quantity}, hasExitFill={_hasExitFill}");
        }

        /// <summary>
        /// Manages open position each bar.
        /// Implements trailing stop and break-even logic per management plan.
        /// </summary>
        public void ManagePosition(Context context)
        {
            if (_positionState == null || !_positionState.IsActive)
                return;

            // Verify position exists
            if (context.IsFlat)
            {
                // Position closed externally - this shouldn't happen
                _logger.LogError("Position closed externally - state mismatch");
                _positionState = null;
                return;
            }

            // PHASE 5 / Opt 5: ORB time-based exit. Force-flatten at market
            // when an ORB position has been held for at least
            // ORBMaxHoldMinutes. 0 = disabled (baseline).
            // Runs before BE / trailing so we don't waste a tick adjusting a
            // stop on a bar we're about to close on anyway.
            if (_config.ORBMaxHoldMinutes > 0
                && _positionState.ModuleId == "ORB")
            {
                TimeSpan holdDuration = context.Timestamp - _positionState.EntryTime;
                if (holdDuration.TotalMinutes >= _config.ORBMaxHoldMinutes)
                {
                    _logger.LogInfo($"[FLUX][ORB][TIME_EXIT] Holding={holdDuration.TotalMinutes:F1}m, " +
                        $"Max={_config.ORBMaxHoldMinutes}m, EntryTime={_positionState.EntryTime:HH:mm}, " +
                        $"NowTime={context.Timestamp:HH:mm}");
                    FlattenForRisk(context, "ORB_TIME_EXIT");
                    return;
                }
            }

            // Update MFE tracking
            UpdateMaxFavorable(context);

            // Get management plan
            var plan = _plans[_positionState.ManagementPlanId];

            // PHASE 12.10: Apply auto break-even logic if enabled (before trailing)
            if (plan.EnableAutoBreakEven && !_positionState.BreakEvenActivated)
            {
                ManageAutoBreakEven(context, plan);
            }

            // Apply trailing stop logic if enabled
            if (plan.EnableTrailing)
            {
                ManageTrailingStop(context, plan);
            }

        }

        /// <summary>
        /// Handles position closure.
        /// Classifies exit reason and returns trade result.
        /// </summary>
        public TradeResult OnPositionClosed(Context context, double exitPrice)
        {
            if (_positionState == null)
            {
                _logger.LogError("Position closed but no position state exists");
                return null;
            }

            // Resolve actual exit price: captured fill > NinjaTrader SystemPerformance > classification fallback
            double actualExitPrice = exitPrice;
            string exitPriceSource = "PARAM";
            if (_hasExitFill)
            {
                actualExitPrice = _exitFillPrice;
                exitPriceSource = "EXIT_FILL";
            }
            else
            {
                // OnExitFilled may not fire if OnPositionUpdate runs before OnExecutionUpdate.
                // Use NinjaTrader's own trade tracking as authoritative fallback.
                bool resolvedFromSystem = false;
                try
                {
                    var allTrades = _strategy.SystemPerformance.AllTrades;
                    if (allTrades != null && allTrades.Count > 0)
                    {
                        var lastTrade = allTrades[allTrades.Count - 1];
                        // Validate the trade matches our position (entry price within 1 tick)
                        double entryDiff = Math.Abs(lastTrade.Entry.Price - _entryFillPrice);
                        bool entryMatches = _entryFillPrice > 0
                            && entryDiff <= context.TickSize * 2;

                        if (entryMatches && lastTrade.Exit != null && lastTrade.Exit.Price > 0)
                        {
                            actualExitPrice = lastTrade.Exit.Price;
                            resolvedFromSystem = true;
                            exitPriceSource = "SYSTEM_PERF";
                        }
                    }
                }
                catch
                {
                    // SystemPerformance unavailable — continue to classification fallback
                }

                if (!resolvedFromSystem)
                {
                    ExitReason preliminaryExitReason = ClassifyExitReason(context, exitPrice);
                    if (preliminaryExitReason == ExitReason.StopLoss || preliminaryExitReason == ExitReason.TrailingStop)
                    {
                        actualExitPrice = _positionState.CurrentStopPrice;
                    }
                    else if (preliminaryExitReason == ExitReason.ProfitTarget)
                    {
                        actualExitPrice = _positionState.TargetPrice;
                    }
                    exitPriceSource = "CLASSIFY_FALLBACK";
                    _logger.LogInfo($"[FLUX][EXEC] EXIT_PRICE_FALLBACK: classified_exit={actualExitPrice:F2}, param_exit={exitPrice:F2}");
                }
            }

            // Determine exit reason using actual exit price
            ExitReason exitReason = ClassifyExitReason(context, actualExitPrice);

            // Calculate PnL (REQUIRED: DOLLARS) using actual exit fill price
            double realizedPnLDollars;
            double pointValue = _strategy.Instrument.MasterInstrument.PointValue;
            // PHASE 12.11a FIX: Use executed quantity from fills, not intended quantity
            // For quantity invariance, PnL should reflect actual execution, not intent
            int quantity = _entryQty;

            if (_positionState.Direction == TradeDirection.Long)
            {
                realizedPnLDollars = (actualExitPrice - _entryFillPrice) * pointValue * quantity;
            }
            else // SHORT
            {
                realizedPnLDollars = (_entryFillPrice - actualExitPrice) * pointValue * quantity;
            }

            // Calculate initial risk (REQUIRED: DOLLARS) using entry fill price
            double initialRiskDollars = Math.Abs(_entryFillPrice - _positionState.InitialStopPrice)
                * pointValue
                * quantity;

            // PHASE 12.11a: Update TradeQuantity to match executed quantity for consistency
            _positionState.TradeQuantity = quantity;

            // Calculate R-multiple (REQUIRED: DIMENSIONLESS)
            double rMultiple = initialRiskDollars > 0 ? realizedPnLDollars / initialRiskDollars : 0;

            var result = new TradeResult
            {
                ModuleId = _positionState.ModuleId,
                Direction = _positionState.Direction,
                EntryPrice = _positionState.EntryPrice,
                ExitPrice = actualExitPrice,
                RealizedPnL = realizedPnLDollars,
                RMultiple = rMultiple,
                ExitReason = exitReason.ToString(),
                EntryTime = _positionState.EntryTime,
                ExitTime = context.Timestamp,
                DurationBars = context.CurrentBar - _positionState.EntryBar
            };

            // DEBUG: Enhanced sanity guards with fill price details (PHASE 6)
            if (Math.Abs(realizedPnLDollars) > 1000)
            {
                _logger.LogInfo($"[FLUX][EXEC] PNL_SANITY_CHECK: PnL={realizedPnLDollars:F2}, entryFill={_entryFillPrice:F2}, exitFill={actualExitPrice:F2}, source={exitPriceSource}, stop={_positionState.InitialStopPrice:F2}, target={_positionState.TargetPrice:F2}, qty={quantity}");
            }

            if (Math.Abs(rMultiple) > 20)
            {
                _logger.LogError($"ABNORMAL_R_DETECTED: R={rMultiple:F2}, PnL={realizedPnLDollars:F2}, initialRisk={initialRiskDollars:F2}, entryFillPrice={_entryFillPrice:F2}, exitFillPrice={actualExitPrice:F2}, stopPrice={_positionState.InitialStopPrice:F2}, targetPrice={_positionState.TargetPrice:F2}, qty={quantity}, pointValue={pointValue:F2}, direction={_positionState.Direction}, module={_positionState.ModuleId}");
            }

            _logger.LogInfo($"[FLUX][EXECUTE][CLOSE] SetupId={_positionState.SetupId}, ExitReason={result.ExitReason}, ExitPrice={actualExitPrice:F2}, PnL={realizedPnLDollars:F2}, RMultiple={rMultiple:F2}, Source={exitPriceSource}");
            
            // PHASE 12.11a: Diagnostic log for quantity invariance validation
            // This log can be diff'd across quantity settings to verify identical trade timing
            // PnL scales linearly with quantity; timing should be identical
            double perContractPnL = quantity > 0 ? realizedPnLDollars / quantity : 0;
            _logger.LogInfo($"[FLUX][INVARIANCE][EXIT] Bar={context.CurrentBar}, Time={context.Timestamp:yyyy-MM-dd HH:mm}, " +
                $"Module={_positionState.ModuleId}, Direction={_positionState.Direction}, " +
                $"ExitPrice={actualExitPrice:F2}, ExitReason={exitReason}, " +
                $"DurationBars={result.DurationBars}, TradeQty={quantity}, " +
                $"TotalPnL={realizedPnLDollars:F2}, PerContractPnL={perContractPnL:F2}");

            _logger.LogPositionClosed(_positionState.ModuleId, result.ExitReason, realizedPnLDollars, rMultiple);

            // Clear state and reset fill tracking
            _positionState = null;
            ResetFillState();

            return result;
        }

        /// <summary>
        /// Forces immediate flatten due to risk breach.
        /// Uses the correct entry signal reference so NinjaTrader can match
        /// the exit to the open position (required for named entry orders).
        /// </summary>
        public void FlattenForRisk(Context context, string reason)
        {
            if (context.IsFlat)
                return;

            if (_positionState == null || !_positionState.IsActive)
            {
                _logger.LogInfo($"[FLUX][EXEC] FLATTEN_SKIP: no active position state, reason={reason}");
                return;
            }

            _logger.LogExecutionProtectionFailure(_positionState.ModuleId, reason);

            string entryName = BuildEntryName(_positionState.ModuleId, _positionState.Direction);
            int qty = _positionState.TradeQuantity;

            try
            {
                if (_positionState.Direction == TradeDirection.Long)
                    _strategy.ExitLong(0, qty, EXIT_NAME, entryName);
                else
                    _strategy.ExitShort(0, qty, EXIT_NAME, entryName);

                _logger.LogInfo($"[FLUX][EXEC] FLATTEN_SUBMITTED: reason={reason}, direction={_positionState.Direction}, entry={entryName}, qty={qty}");
            }
            catch (Exception ex)
            {
                _logger.LogInfo($"[FLUX][EXEC] FLATTEN_FAILED: {ex.Message}, reason={reason}");
            }
        }

        /// <summary>
        /// Checks if position management state is active.
        /// </summary>
        public bool HasActivePosition()
        {
            return _positionState != null && _positionState.IsActive;
        }

        /// <summary>
        /// Gets current position management state (read-only).
        /// </summary>
        public PositionManagementState GetPositionState()
        {
            return _positionState;
        }

        /// <summary>
        /// Creates trade metadata for module notification.
        /// </summary>
        public TradeMetadata CreateTradeMetadata()
        {
            if (_positionState == null)
                return null;

            return new TradeMetadata
            {
                ModuleId = _positionState.ModuleId,
                Direction = _positionState.Direction,
                EntryPrice = _positionState.EntryPrice,
                StopPrice = _positionState.CurrentStopPrice,
                TargetPrice = _positionState.TargetPrice,
                EntryTime = _positionState.EntryTime,
                EntryBar = _positionState.EntryBar
            };
        }

        #region Auto Break-Even Logic (Phase 12.10)

        /// <summary>
        /// PHASE 12.10: Manages auto break-even for Momentum parity mode.
        /// Matches standalone behavior:
        ///   - When profit reaches BETriggerR Ã— initial risk, move stop to entry price
        ///   - Only moves stop tighter, never loosens
        /// </summary>
        private void ManageAutoBreakEven(Context context, ManagementPlan plan)
        {
            // Calculate initial risk (distance from entry to initial stop)
            double initialRisk = Math.Abs(_positionState.EntryPrice - _positionState.InitialStopPrice);
            
            // Calculate trigger distance (1.5R by default)
            double triggerDistance = initialRisk * plan.BreakEvenTriggerR;
            
            // Calculate current profit
            double currentProfit;
            if (_positionState.Direction == TradeDirection.Long)
            {
                currentProfit = context.Close - _positionState.EntryPrice;
            }
            else // Short
            {
                currentProfit = _positionState.EntryPrice - context.Close;
            }
            
            // Check if profit has reached trigger level
            if (currentProfit >= triggerDistance)
            {
                // Check if moving to break-even would tighten the stop (not loosen)
                bool wouldTighten;
                if (_positionState.Direction == TradeDirection.Long)
                {
                    // For longs, break-even (entry price) must be above current stop
                    wouldTighten = _positionState.EntryPrice > _positionState.CurrentStopPrice;
                }
                else // Short
                {
                    // For shorts, break-even (entry price) must be below current stop
                    wouldTighten = _positionState.EntryPrice < _positionState.CurrentStopPrice;
                }
                
                if (wouldTighten)
                {
                    double oldStop = _positionState.CurrentStopPrice;
                    double newStop = _positionState.EntryPrice;
                    
                    _positionState.CurrentStopPrice = newStop;
                    _positionState.BreakEvenActivated = true;
                    
                    UpdateStopOrder(newStop);
                    
                    _logger.LogInfo($"[FLUX][EXEC][BREAK_EVEN] Module={_positionState.ModuleId}, " +
                        $"OldStop={oldStop:F2}, NewStop={newStop:F2}, " +
                        $"Profit={currentProfit:F2}, TriggerDistance={triggerDistance:F2}, " +
                        $"TriggerR={plan.BreakEvenTriggerR:F2}");
                }
            }
        }

        #endregion

        #region Trailing Stop Logic

        private void UpdateMaxFavorable(Context context)
        {
            if (_positionState.Direction == TradeDirection.Long)
            {
                if (context.High > _positionState.MaxFavorablePrice)
                    _positionState.MaxFavorablePrice = context.High;
            }
            else // Short
            {
                if (context.Low < _positionState.MaxFavorablePrice)
                    _positionState.MaxFavorablePrice = context.Low;
            }
        }

        private void ManageTrailingStop(Context context, ManagementPlan plan)
        {
            double initialRisk = Math.Abs(_positionState.EntryPrice - _positionState.InitialStopPrice);
            double tickSize = context.TickSize;

            // Calculate current MFE in R-multiples
            double mfe;
            if (_positionState.Direction == TradeDirection.Long)
            {
                mfe = (_positionState.MaxFavorablePrice - _positionState.EntryPrice) / initialRisk;
            }
            else // Short
            {
                mfe = (_positionState.EntryPrice - _positionState.MaxFavorablePrice) / initialRisk;
            }

            // Check if trailing should activate
            if (!_positionState.TrailingActivated && mfe >= plan.TrailingActivationR)
            {
                _positionState.TrailingActivated = true;
                _logger.LogDebug($"Trailing activated at MFE={mfe:F2}R");
            }

            // Apply trailing if activated
            if (_positionState.TrailingActivated)
            {
                double trailingMultiplier = plan.TrailingDistanceR;

                // PHASE 16: Range ratcheting — tighten trail as profit grows
                if (_config.RangeTrailRatchetEnabled
                    && _positionState.ModuleId == "Range")
                {
                    double profitInR = mfe;
                    string phase;
                    if (profitInR >= _config.RangeTrailRatchetThreshold2R)
                    {
                        trailingMultiplier = _config.RangeTrailMultiplierTight;
                        phase = "3-Tight";
                    }
                    else if (profitInR >= _config.RangeTrailRatchetThreshold1R)
                    {
                        trailingMultiplier = _config.RangeTrailMultiplierMid;
                        phase = "2-Mid";
                    }
                    else
                    {
                        trailingMultiplier = _config.RangeTrailMultiplierInitial;
                        phase = "1-Initial";
                    }
                    _logger.LogDebug($"Range trail ratchet: Phase {phase}, multiplier={trailingMultiplier:F2}, profitR={profitInR:F2}");
                }

                double trailingDistance = initialRisk * trailingMultiplier;
                double newStop;

                if (_positionState.Direction == TradeDirection.Long)
                {
                    newStop = _positionState.MaxFavorablePrice - trailingDistance;
                    // Normalize to tick size
                    newStop = Math.Floor(newStop / tickSize) * tickSize;
                    // Never loosen the stop
                    if (newStop > _positionState.CurrentStopPrice)
                    {
                        double oldStop = _positionState.CurrentStopPrice;
                        _positionState.CurrentStopPrice = newStop;
                        UpdateStopOrder(newStop);
                        _logger.LogStopUpdated(_positionState.ModuleId, oldStop, newStop);
                    }
                }
                else // Short
                {
                    newStop = _positionState.MaxFavorablePrice + trailingDistance;
                    // Normalize to tick size
                    newStop = Math.Ceiling(newStop / tickSize) * tickSize;
                    // Never loosen the stop
                    if (newStop < _positionState.CurrentStopPrice)
                    {
                        double oldStop = _positionState.CurrentStopPrice;
                        _positionState.CurrentStopPrice = newStop;
                        UpdateStopOrder(newStop);
                        _logger.LogStopUpdated(_positionState.ModuleId, oldStop, newStop);
                    }
                }
            }
        }

        private void UpdateStopOrder(double newStopPrice)
        {
            try
            {
                _strategy.SetStopLoss(CalculationMode.Price, newStopPrice);
            }
            catch (Exception ex)
            {
                _logger.LogError($"Failed to update stop: {ex.Message}", ex);
            }
        }

        #endregion

        #region Exit Classification

        private ExitReason ClassifyExitReason(Context context, double exitPrice)
        {
            if (_positionState == null)
                return ExitReason.None;

            double tolerance = context.TickSize * 2;

            // Check if exit was at stop
            if (Math.Abs(exitPrice - _positionState.CurrentStopPrice) <= tolerance)
            {
                if (_positionState.TrailingActivated)
                    return ExitReason.TrailingStop;
                return ExitReason.StopLoss;
            }

            // Check if exit was at target
            if (Math.Abs(exitPrice - _positionState.TargetPrice) <= tolerance)
            {
                return ExitReason.ProfitTarget;
            }

            // Default to stop loss if we can't determine
            return ExitReason.StopLoss;
        }

        #endregion

        /// <summary>
        /// Resets execution engine state for new session.
        /// </summary>
        public void ResetDaily()
        {
            _positionState = null;
            ResetFillState();
        }
    }
}