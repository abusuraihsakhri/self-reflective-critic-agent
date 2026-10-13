"use strict";
const {test} = require("node:test");
const assert = require("node:assert/strict");
const {evaluateLocal} = require("./app.js");
const input = (primary, secondary, critical, status) => ({
  task_id:"T-1",target_identifier:"TARGET-1",
  primary_metric:primary,secondary_metric:secondary,
  is_critical_flag:critical,status_descriptor:status
});

test("routine result has no alerts", () => {
  const actual = evaluateLocal(input(10, 3, false, "NOMINAL"));
  assert.equal(actual.overall_urgency, "ROUTINE");
  assert.equal(actual.total_alerts, 0);
  assert.equal(actual.source, "browser-local (unsigned)");
});
test("elevated for primary or secondary threshold", () => {
  assert.equal(evaluateLocal(input(30, 3, false, "NOMINAL")).overall_urgency,"ELEVATED_RISK");
  assert.equal(evaluateLocal(input(10, 14, false, "NOMINAL")).overall_urgency,"ELEVATED_RISK");
});
test("critical takes precedence, without synthetic audit signature", () => {
  const actual = evaluateLocal(input(30, 18, true, "DISCORDANT"));
  assert.equal(actual.overall_urgency,"CRITICAL_STAT_PANIC");
  assert.equal(actual.critical_alerts_count,1);
  assert.equal(actual.total_alerts,3);
  assert.equal(actual.audit_hash,undefined);
});
test("boundaries are strict", () => {
  assert.equal(evaluateLocal(input(25, 12, false, "NOMINAL")).total_alerts,0);
});
