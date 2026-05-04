#region Using declarations
using System;
using System.Text;
#endregion

namespace NinjaTrader.NinjaScript.Strategies.Flux.Core
{
    /// <summary>
    /// Event types for structured logging.
    /// </summary>
    public enum EventType
    {
        Init,
        ContextBuild,
        GateBlocked,
        ModuleEvaluated,
        ModuleSelected,
        IntentRejected,
        OrderSubmitted,
        OrderFilled,
        PositionOpened,
        PositionClosed,
        StopUpdated,
        RiskLockout,
        ExecutionRejected,
        ExecutionProtectionFailure,
        Error
    }

    /// <summary>
    /// Structured log event.
    /// </summary>
    public class LogEvent
    {
        public DateTime Timestamp { get; set; }
        public int Bar { get; set; }
        public EventType EventType { get; set; }
        public string ModuleId { get; set; }
        public string Message { get; set; }
        public string Details { get; set; }
    }

    /// <summary>
    /// Structured, toggleable logging for Flux v1.
    /// Logging is non-blocking and safe to disable entirely.
    /// </summary>
    public class Logger
    {
        private readonly Config _config;
        private readonly Strategy _strategy;
        private readonly string _auditLogPath;
        private bool _auditLogWriteFailed;
        private bool _fileWriteConfirmed;

        // Telemetry counters (lightweight, always-on if enabled)
        private int _gateBlockedCount;
        private int _intentsEvaluatedCount;
        private int _intentsRejectedCount;
        private int _tradesOpenedCount;
        private int _tradesClosedCount;
        private int _riskLockoutCount;
        private int _errorCount;

        public Logger(Strategy strategy, Config config)
        {
            _strategy = strategy ?? throw new ArgumentNullException(nameof(strategy));
            _config = config ?? throw new ArgumentNullException(nameof(config));

            // Initialize audit log path for file logging
            if (_config.EnableFileAuditLogging)
            {
                string instrument = _strategy.Instrument?.MasterInstrument?.Name ?? "UNKNOWN";
                string dateStr = DateTime.Now.ToString("yyyyMMdd");
                string logDir = System.IO.Path.Combine(NinjaTrader.Core.Globals.UserDataDir, "log", "flux");

                try
                {
                    System.IO.Directory.CreateDirectory(logDir);
                    _auditLogPath = System.IO.Path.Combine(logDir, $"flux_audit_{dateStr}_{instrument}.log");
                    _strategy.Print($"[FLUX][AUDIT_LOG_INIT] Initialized audit logging to: {_auditLogPath}");
                }
                catch (Exception ex)
                {
                    // Log warning but don't fail initialization
                    _strategy.Print($"[FLUX][AUDIT_LOG_INIT_FAILED] {ex.Message}");
                    _auditLogPath = null;
                }
            }
            else
            {
                _strategy.Print($"[FLUX][AUDIT_LOG_DISABLED] File audit logging is disabled");
            }
        }

        #region Structured Event Logging

        /// <summary>
        /// Log initialization event.
        /// </summary>
        public void LogInit(string message)
        {
            Log(LogLevel.Info, EventType.Init, null, message, null);
        }

        /// <summary>
        /// Log gate blocked event.
        /// </summary>
        public void LogGateBlocked(string gateName, string reason)
        {
            _gateBlockedCount++;
            Log(LogLevel.Debug, EventType.GateBlocked, null, $"Gate blocked: {gateName}", reason);
        }

        /// <summary>
        /// Log module evaluation.
        /// </summary>
        public void LogModuleEvaluated(string moduleId, TradeIntent intent)
        {
            _intentsEvaluatedCount++;
            string details = intent.Direction == TradeDirection.None
                ? "No signal"
                : $"Direction={intent.Direction}, Stop={intent.ProposedStopTicks}, Target={intent.ProposedTargetTicks}, Reason={intent.ReasonCode}";
            Log(LogLevel.Trace, EventType.ModuleEvaluated, moduleId, "Module evaluated", details);
        }

        /// <summary>
        /// Log module selected for execution.
        /// </summary>
        public void LogModuleSelected(string moduleId, TradeIntent intent)
        {
            Log(LogLevel.Info, EventType.ModuleSelected, moduleId,
                $"Module selected: {intent.Direction}",
                $"Stop={intent.ProposedStopTicks}, Target={intent.ProposedTargetTicks}, Plan={intent.ManagementPlanId}, Reason={intent.ReasonCode}");
        }

        /// <summary>
        /// Log intent rejection.
        /// </summary>
        public void LogIntentRejected(string moduleId, string reason)
        {
            _intentsRejectedCount++;
            Log(LogLevel.Warn, EventType.IntentRejected, moduleId, "Intent rejected", reason);
        }

        /// <summary>
        /// Log informational message.
        /// </summary>
        public void LogInfo(string message)
        {
            Log(LogLevel.Info, EventType.Init, null, message, null);
        }

        /// <summary>
        /// Log order submitted.
        /// </summary>
        public void LogOrderSubmitted(string moduleId, TradeDirection direction, double price)
        {
            Log(LogLevel.Info, EventType.OrderSubmitted, moduleId,
                $"Order submitted: {direction}",
                $"Price={price:F2}");
        }

        /// <summary>
        /// Log order filled.
        /// </summary>
        public void LogOrderFilled(string moduleId, TradeDirection direction, double price, int quantity)
        {
            Log(LogLevel.Info, EventType.OrderFilled, moduleId,
                $"Order filled: {direction}",
                $"Price={price:F2}, Qty={quantity}");
        }

        /// <summary>
        /// Log position opened.
        /// </summary>
        public void LogPositionOpened(string moduleId, TradeDirection direction, double entryPrice, double stopPrice, double targetPrice)
        {
            _tradesOpenedCount++;
            Log(LogLevel.Info, EventType.PositionOpened, moduleId,
                $"Position opened: {direction}",
                $"Entry={entryPrice:F2}, Stop={stopPrice:F2}, Target={targetPrice:F2}");
        }

        /// <summary>
        /// Log position closed.
        /// </summary>
        public void LogPositionClosed(string moduleId, string exitReason, double realizedPnL, double rMultiple)
        {
            _tradesClosedCount++;
            Log(LogLevel.Info, EventType.PositionClosed, moduleId,
                $"Position closed: {exitReason}",
                $"PnL={realizedPnL:F2}, R={rMultiple:F2}");
        }

        /// <summary>
        /// Log stop updated (trailing).
        /// </summary>
        public void LogStopUpdated(string moduleId, double oldStop, double newStop)
        {
            Log(LogLevel.Debug, EventType.StopUpdated, moduleId,
                "Stop updated (trailing)",
                $"Old={oldStop:F2}, New={newStop:F2}");
        }

        /// <summary>
        /// Log risk lockout.
        /// </summary>
        public void LogRiskLockout(string reason, double currentPnL, double limit)
        {
            _riskLockoutCount++;
            Log(LogLevel.Warn, EventType.RiskLockout, null,
                $"Risk lockout activated: {reason}",
                $"Current={currentPnL:F2}, Limit={limit:F2}");
        }

        /// <summary>
        /// Log execution rejection.
        /// </summary>
        public void LogExecutionRejected(string moduleId, string reason)
        {
            Log(LogLevel.Warn, EventType.ExecutionRejected, moduleId, "Execution rejected", reason);
        }

        /// <summary>
        /// Log execution protection failure.
        /// </summary>
        public void LogExecutionProtectionFailure(string moduleId, string reason)
        {
            _errorCount++;
            Log(LogLevel.Error, EventType.ExecutionProtectionFailure, moduleId, "Execution protection failure", reason);
        }

        /// <summary>
        /// Log error.
        /// </summary>
        public void LogError(string message, Exception ex = null)
        {
            _errorCount++;
            string details = ex != null ? $"{ex.GetType().Name}: {ex.Message}" : null;
            Log(LogLevel.Error, EventType.Error, null, message, details);
        }

        /// <summary>
        /// Log debug message.
        /// </summary>
        public void LogDebug(string message, string details = null)
        {
            Log(LogLevel.Debug, EventType.ContextBuild, null, message, details);
        }

        /// <summary>
        /// Log trace message.
        /// </summary>
        public void LogTrace(string message, string details = null)
        {
            Log(LogLevel.Trace, EventType.ContextBuild, null, message, details);
        }

        #endregion

        #region Core Logging

        private void Log(LogLevel level, EventType eventType, string moduleId, string message, string details)
        {
            if (!_config.EnableLogging)
                return;

            if ((int)level > (int)_config.LogLevel)
                return;

            var sb = new StringBuilder();
            sb.Append($"[{DateTime.Now:HH:mm:ss.fff}]");
            sb.Append($"[{level}]");
            sb.Append($"[Bar {_strategy.CurrentBar}]");
            sb.Append($"[{eventType}]");

            if (!string.IsNullOrEmpty(moduleId))
                sb.Append($"[{moduleId}]");

            sb.Append($" {message}");

            if (!string.IsNullOrEmpty(details))
                sb.Append($" | {details}");

            string logMessage = sb.ToString();
            _strategy.Print(logMessage);

            // PHASE 6.6: Write to audit log file if enabled and this is a FLUX log
            if (_config.EnableFileAuditLogging && !string.IsNullOrEmpty(_auditLogPath) && logMessage.Contains("[FLUX]["))
            {
                try
                {
                    System.IO.File.AppendAllText(_auditLogPath, logMessage + Environment.NewLine);
                    // Debug: confirm file write
                    if (!_fileWriteConfirmed)
                    {
                        _strategy.Print($"[FLUX][AUDIT_LOG_WRITTEN] Successfully wrote to: {_auditLogPath}");
                        _fileWriteConfirmed = true;
                    }
                }
                catch (Exception ex)
                {
                    // Only log failure once to avoid spam
                    if (!_auditLogWriteFailed)
                    {
                        _strategy.Print($"[FLUX][AUDIT_LOG_WRITE_FAILED] {ex.Message}");
                        _auditLogWriteFailed = true;
                    }
                }
            }
        }

        #endregion

        #region Telemetry

        /// <summary>
        /// Get telemetry summary.
        /// </summary>
        public string GetTelemetrySummary()
        {
            if (!_config.EnableTelemetryCounters)
                return "Telemetry disabled";

            return $"GateBlocked={_gateBlockedCount}, " +
                   $"IntentsEval={_intentsEvaluatedCount}, " +
                   $"IntentsRejected={_intentsRejectedCount}, " +
                   $"TradesOpened={_tradesOpenedCount}, " +
                   $"TradesClosed={_tradesClosedCount}, " +
                   $"RiskLockouts={_riskLockoutCount}, " +
                   $"Errors={_errorCount}";
        }

        /// <summary>
        /// Reset telemetry counters.
        /// </summary>
        public void ResetTelemetry()
        {
            _gateBlockedCount = 0;
            _intentsEvaluatedCount = 0;
            _intentsRejectedCount = 0;
            _tradesOpenedCount = 0;
            _tradesClosedCount = 0;
            _riskLockoutCount = 0;
            _errorCount = 0;
        }

        #endregion
    }
}

