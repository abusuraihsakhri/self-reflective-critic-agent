"use strict";

/* These browser rules mirror agents/workers.py; they are not a clinical model. */
function evaluateLocal(payload) {
  const alerts = [];
  if (payload.primary_metric > 25) {
    alerts.push({
      origin_worker: "InvariantQCWorker", urgency: "ELEVATED_RISK",
      summary: "Primary Metric Threshold Exceeded",
      technical_details: "Primary measurement exceeds illustrative threshold 25.",
      actionable_remediation: "Review the primary metric and its configured threshold."
    });
  }
  if (payload.is_critical_flag || payload.secondary_metric > 12) {
    alerts.push({
      origin_worker: "SafetyEscalationWorker",
      urgency: payload.is_critical_flag ? "CRITICAL_STAT_PANIC" : "ELEVATED_RISK",
      summary: "Critical Safety Interlock Triggered",
      technical_details: "Critical flag or secondary metric above illustrative threshold 12.",
      actionable_remediation: "Review the alert and escalate if warranted."
    });
  }
  if (["DISCORDANT", "ANOMALY", "MUTANT", "VIOLATION", "FAIL", "REJECT"]
      .some(term => payload.status_descriptor.toUpperCase().includes(term))) {
    alerts.push({
      origin_worker: "ProtocolConformanceWorker", urgency: "ELEVATED_RISK",
      summary: "Protocol Conformance Discordance Detected",
      technical_details: "Status descriptor contains an anomaly keyword.",
      actionable_remediation: "Review the status descriptor."
    });
  }
  const critical = alerts.filter(x => x.urgency === "CRITICAL_STAT_PANIC").length;
  const elevated = alerts.some(x => x.urgency === "ELEVATED_RISK");
  const urgency = critical ? "CRITICAL_STAT_PANIC" : elevated ? "ELEVATED_RISK" : "ROUTINE";
  return {
    source: "browser-local (unsigned)",
    task_id: payload.task_id,
    target_identifier: payload.target_identifier,
    overall_urgency: urgency,
    integrity_status: critical ? "RECALIBRATION_REQUIRED" : elevated ? "DISCORDANT_ANOMALY" : "VALIDATED_OPTIMAL",
    total_alerts: alerts.length,
    critical_alerts_count: critical,
    alerts
  };
}

function parsePayload(form) {
  const data = new FormData(form);
  const primary = Number(data.get("primary_metric"));
  const secondary = Number(data.get("secondary_metric"));
  if (!Number.isFinite(primary) || !Number.isFinite(secondary)) {
    throw new Error("Metrics must be finite numbers.");
  }
  const payload = {
    task_id: String(data.get("task_id")).trim(),
    target_identifier: String(data.get("target_identifier")).trim(),
    primary_metric: primary,
    secondary_metric: secondary,
    status_descriptor: String(data.get("status_descriptor") || ""),
    is_critical_flag: data.has("is_critical_flag")
  };
  if (!payload.task_id || !payload.target_identifier) {
    throw new Error("Task ID and target ID are required.");
  }
  return payload;
}

if (typeof module !== "undefined" && module.exports) module.exports = {evaluateLocal};

if (typeof document !== "undefined") {
  const form = document.getElementById("audit-form");
  const mode = document.getElementById("mode");
  const status = document.getElementById("result-status");
  const output = document.getElementById("output");
  const download = document.getElementById("download");
  const submit = document.getElementById("submit");
  let backend = false;
  let latest = null;
  mode.textContent = "Browser-only evaluation — no upload";
  // Probe the server identity before transmitting any task data.
  if (location.protocol !== "file:" && !location.hostname.endsWith(".github.io")) {
    fetch("./health", {cache: "no-store"})
      .then(response => response.ok ? response.json() : null)
      .then(data => {
        if (data && data.service === "self-reflective-critic-agent") {
          backend = true;
          mode.textContent = "Server API (with local fallback)";
        }
      }).catch(() => {});
  }
  form.addEventListener("submit", async event => {
    event.preventDefault();
    submit.disabled = true;
    try {
      const payload = parsePayload(form);
      let result;
      if (backend) {
        try {
          const response = await fetch("./api/audit", {
            method: "POST", headers: {"Content-Type": "application/json"},
            body: JSON.stringify(payload)
          });
          if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || "HTTP " + response.status);
          }
          result = await response.json();
          result.source = "server API (signed, process-local audit)";
        } catch (error) {
          // Do not silently replace rejected requests with local results.
          if (error instanceof TypeError) {
            backend = false;
            mode.textContent = "Browser-only evaluation — server unreachable";
            result = evaluateLocal(payload);
          } else {
            throw error;
          }
        }
      } else {
        result = evaluateLocal(payload);
      }
      latest = result;
      output.textContent = JSON.stringify(result, null, 2);
      status.textContent = "Completed: " + result.overall_urgency;
      download.disabled = false;
    } catch (error) {
      latest = null;
      output.textContent = "Evaluation failed: " + error.message;
      status.textContent = "Evaluation failed";
      download.disabled = true;
    } finally {
      submit.disabled = false;
    }
  });
  download.addEventListener("click", () => {
    if (!latest) return;
    const objectUrl = URL.createObjectURL(new Blob([JSON.stringify(latest, null, 2) + "\n"], {type:"application/json"}));
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = "critic-audit.json";
    link.click();
    URL.revokeObjectURL(objectUrl);
  });
}
