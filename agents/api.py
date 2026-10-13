"""FastAPI endpoints for the deterministic worker and audit pipeline."""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from .base import AuditLogger, SecurityException
from .metrics import GLOBAL_METRICS
from .models import SystemTaskPayload
from .supervisor import SystemSupervisor

supervisor = SystemSupervisor(model_provider="mock")

app = FastAPI(
    title="Self Reflective Critic Agent API",
    description="Deterministic metric checks and in-memory audit trail (not clinical validation)",
    version="3.0.0",
)


class ChatRequest(BaseModel):
    query: str


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(Path(__file__).resolve().parent.parent / "web" / "index.html")


@app.get("/app.js", include_in_schema=False)
def browser_script():
    return FileResponse(Path(__file__).resolve().parent.parent / "web" / "app.js", media_type="text/javascript")


@app.get("/health")
def health():
    return {"status": "HEALTHY", "service": "self-reflective-critic-agent", "version": "3.0.0"}


@app.get("/metrics")
def metrics():
    # Retain the existing JSON contract.
    return {
        "dossiers_processed_total": GLOBAL_METRICS.tasks_total,
        "audit_blocks_total": len(AuditLogger.get_trail()),
        "phi_blocks_total": GLOBAL_METRICS.phi_blocks_total,
        "system_status": "NOMINAL",
    }


@app.get("/metrics/prometheus", response_class=PlainTextResponse)
def prometheus_metrics():
    GLOBAL_METRICS.audit_blocks_total = len(AuditLogger.get_trail())
    return GLOBAL_METRICS.export_prometheus_text()


@app.post("/api/audit")
def api_audit(payload: SystemTaskPayload):
    try:
        return supervisor.process_task(payload).to_dict()
    except SecurityException:
        raise HTTPException(status_code=400, detail="Potential sensitive identifier detected")


@app.post("/api/chat")
def api_chat(req: ChatRequest):
    try:
        return {"response": supervisor.query_supervisory_chat(req.query)}
    except SecurityException:
        GLOBAL_METRICS.record_phi_block()
        raise HTTPException(status_code=400, detail="Potential sensitive identifier detected")


@app.get("/api/audit/logs")
def api_audit_logs():
    return {"audit_trail": AuditLogger.get_trail(), "verified": AuditLogger.verify_integrity()}
