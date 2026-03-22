import os
import logging
from dotenv import load_dotenv

load_dotenv()
instrumentation_key = os.getenv("APPLICATION_INSIGHTS_INSTRUMENTATION_KEY")
from opentelemetry.sdk.resources import SERVICE_NAME, Resource


from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import (
    LoggerProvider,
    LoggingHandler,
)
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

from azure.monitor.opentelemetry.exporter import AzureMonitorLogExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
logger_provider = LoggerProvider()
set_logger_provider(logger_provider)



import logging.handlers
# Configure logging to console and rotating file for all loggers
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
file_handler = logging.handlers.TimedRotatingFileHandler(
    "app.log", when="midnight", interval=1, backupCount=2,encoding="utf-8"
)
file_handler.setLevel(logging.INFO)
file_handler.suffix = "%Y-%m-%d"

# Get root logger and set handlers
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(console_handler)
root_logger.addHandler(file_handler)

# Also configure Uvicorn and FastAPI loggers
for logger_name in ["uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"]:
    lgr = logging.getLogger(logger_name)
    lgr.setLevel(logging.INFO)
    lgr.addHandler(console_handler)
    lgr.addHandler(file_handler)

# Set Azure SDK internal HTTP loggers to WARNING to suppress verbose logs
for azure_logger in ["azure", "azure.monitor", "azure.monitor.opentelemetry.exporter", "azure.core.pipeline.policies.http_logging_policy"]:
    logging.getLogger(azure_logger).setLevel(logging.WARNING)

# Your app logger for custom logs
logger = logging.getLogger(__name__)
if instrumentation_key:
    logger.info("APPLICATION_INSIGHTS_INSTRUMENTATION_KEY is set in the environment.")
else:
    logger.error("APPLICATION_INSIGHTS_INSTRUMENTATION_KEY is not set in the environment. Application Insights logging will not work.")

# Set up OpenTelemetry tracing for FastAPI and Azure Monitor
if instrumentation_key:

    # ----Console Logs ---- 
    logger_provider = LoggerProvider( 
        resource=Resource.create({ 
            SERVICE_NAME: "data-explorer-api", 
            "cloud.role": "data-explorer-api", 
        }) 
    )
    set_logger_provider(logger_provider) 

    log_exporter = AzureMonitorLogExporter( 
        connection_string=f"InstrumentationKey={instrumentation_key}" 
    ) 
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter)) 

    # ERROR-only OpenTelemetry log handler (keeps correlation via context) 
    otel_error_handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider) 

    logging.getLogger().addHandler(otel_error_handler) 
    logger_provider.force_flush()

