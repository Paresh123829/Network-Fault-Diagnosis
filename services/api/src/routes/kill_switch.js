/**
 * kill_switch.js — Emergency kill switch route for Node.js API Gateway.
 */

"use strict";

const express = require("express");
const router = express.Router();
const { broadcastEvent } = require("../sockets/incident_socket");
const { setKillSwitchState, getKillSwitchState } = require("./approvals");

let killSwitchDetails = {
  active: false,
  activated_at: null,
  activated_by: null,
  reason: null,
};

router.get("/", (req, res) => {
  res.json({
    active: getKillSwitchState(),
    activated_at: killSwitchDetails.activated_at,
    activated_by: killSwitchDetails.activated_by,
    reason: killSwitchDetails.reason,
    timestamp: new Date().toISOString(),
  });
});

router.post("/activate", (req, res) => {
  const { operator_id, reason } = req.body;
  const now = new Date().toISOString();

  setKillSwitchState(true);
  killSwitchDetails = {
    active: true,
    activated_at: now,
    activated_by: operator_id || "operator",
    reason: reason || "Emergency network freeze",
  };

  broadcastEvent("kill_switch:changed", killSwitchDetails, "kill_switch");

  res.json({
    active: true,
    activated_at: now,
    activated_by: killSwitchDetails.activated_by,
    reason: killSwitchDetails.reason,
    timestamp: now,
  });
});

router.post("/deactivate", (req, res) => {
  const { operator_id, reason } = req.body;
  const now = new Date().toISOString();

  setKillSwitchState(false);
  killSwitchDetails = {
    active: false,
    activated_at: null,
    activated_by: null,
    reason: null,
  };

  broadcastEvent("kill_switch:changed", {
    active: false,
    deactivated_at: now,
    deactivated_by: operator_id || "operator",
    reason: reason || "Operator sign-off",
  }, "kill_switch");

  res.json({
    active: false,
    activated_at: null,
    activated_by: null,
    reason: null,
    timestamp: now,
  });
});

module.exports = router;

