"""Regressions for audit signatures, privacy checks, CSV parsing and API."""
import csv
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agents.base import AuditTrail, SecurityException
from agents.api import app
from agents.models import SystemTaskPayload
from agents.supervisor import SystemSupervisor
from cli import main as enterprise_cli, parse_csv_bool as enterprise_bool
from reflect_critic.cli import main as legacy_cli, parse_csv_bool as legacy_bool


def test_hmac_detects_in_place_tampering():
    trail = AuditTrail(secret_key="test-signing-key")
    original = trail.log("actor", "tier", "EVENT", {"task_id": "TEST"})
    assert original["current_hash"]
    assert trail.verify_integrity()
    # The accessor does not expose mutable internal records.
    trail.get_trail()[0]["actor"] = "external-change"
    assert trail.verify_integrity()
    trail.logs[0]["actor"] = "internal-change"
    assert not trail.verify_integrity()


def test_hmac_detects_truncated_or_modified_link():
    trail = AuditTrail(secret_key="test-key")
    trail.log("actor", "tier", "EVENT", {"status": "one"})
    trail.log("actor", "tier", "EVENT", {"status": "two"})
    trail.logs[1]["prev_hash"] = "forged"
    assert not trail.verify_integrity()


def test_sensitive_nested_attributes_rejected_without_audit():
    supervisor = SystemSupervisor()
    request = SystemTaskPayload(
        task_id="T-1", target_identifier="TARGET-1", primary_metric=1,
        attributes={"nested": {"notes": "MRN-123456"}},
    )
    with pytest.raises(SecurityException):
        supervisor.process_task(request)


def test_nonfinite_metrics_rejected():
    with pytest.raises(ValidationError):
        SystemTaskPayload(task_id="T", target_identifier="X", primary_metric=float("nan"))
    with pytest.raises(ValidationError):
        SystemTaskPayload(task_id="T", target_identifier="X", primary_metric=1, secondary_metric=float("inf"))


@pytest.mark.parametrize("parser", [enterprise_bool, legacy_bool])
def test_csv_flag_conversion(parser):
    for text in ("False", "false", "0", "No", ""):
        assert parser(text) is False
    for text in ("True", "true", "1", "YES"):
        assert parser(text) is True
    with pytest.raises(ValueError):
        parser("definitely")


@pytest.mark.parametrize("runner,result_column,nominal_label", [
    (enterprise_cli, "overall_urgency", "ROUTINE"),
    (legacy_cli, "overall_status", "NOMINAL_OPTIMAL"),
])
def test_batch_false_string_not_critical(tmp_path, runner, result_column, nominal_label):
    source = tmp_path / "in.csv"
    destination = tmp_path / "out.csv"
    source.write_text(
        "task_id,target_identifier,primary_metric,secondary_metric,is_critical_flag,status_descriptor\n"
        "T-1,X-1,1,1,False,NOMINAL\n", encoding="utf-8"
    )
    assert runner(["batch", "-i", str(source), "-o", str(destination)]) == 0
    with destination.open(newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    assert row[result_column] == nominal_label


def test_http_endpoints_and_rejections():
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/").status_code == 200
    assert client.get("/app.js").status_code == 200
    response = client.post("/api/audit", json={
        "task_id": "HTTP-1", "target_identifier": "X-1",
        "primary_metric": 30, "secondary_metric": 0,
    })
    assert response.status_code == 200
    assert response.json()["overall_urgency"] == "ELEVATED_RISK"
    assert client.get("/metrics").json()["dossiers_processed_total"] >= 1
    assert 'system_tasks_total{' in client.get("/metrics/prometheus").text
    rejected = client.post("/api/audit", json={
        "task_id": "HTTP-2", "target_identifier": "X-1",
        "primary_metric": 0, "attributes": {"comments": "MRN-234567"}
    })
    assert rejected.status_code == 400
    assert "MRN-234567" not in rejected.text
    assert client.get("/api/audit/logs").json()["verified"] is True
