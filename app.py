import warnings
warnings.filterwarnings("ignore")
import uvicorn
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from api.routes.endpoints import app
import os
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter
# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
"""
AI Data Explorer Entrypoint
"""
def start_app():
    """Starts the FastAPI application using Uvicorn."""
    print("Application Starting ")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000
    )
instrumentation_key = os.getenv("APPLICATION_INSIGHTS_INSTRUMENTATION_KEY")
if instrumentation_key:
    trace.set_tracer_provider(
            TracerProvider(
                resource=Resource.create({SERVICE_NAME: "data-explorer-api","cloud.role": "data-explorer-api",})
            )
        )
    tracer_provider = trace.get_tracer_provider()
    exporter = AzureMonitorTraceExporter(connection_string=f'InstrumentationKey={instrumentation_key}', enable_live_metrics=True)
    span_processor = BatchSpanProcessor(exporter)
    tracer_provider.add_span_processor(span_processor)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider)
if __name__ == "__main__":
    start_app()
