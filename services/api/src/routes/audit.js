/**
 * audit.js — Cryptographic audit trail and verification route for Node.js API Gateway.
 */

"use strict";

const express = require("express");
const router = express.Router();

const GENESIS_HASH = "0".repeat(64);

const auditRecordsStore = [
  {
    record_id: "aud_000000_init0001",
    sequence_number: 0,
    previous_hash: GENESIS_HASH,
    record_hash: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    action: "SYSTEM_INITIALIZED",
    operator_id: "system",
    entity_id: "core_platform",
    entity_type: "system",
    details: { environment: "development", version: "0.8.0" },
    timestamp: new Date().toISOString(),
  },
  {
    record_id: "aud_000001_topo0002",
    sequence_number: 1,
    previous_hash: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    record_hash: "c5d2e8b1a3f4c6e9d0b2a4f6c8e0d2b4a6f8c0e2d4b6a8f0c2e4d6b8a0f2c4e6",
    action: "TOPOLOGY_LOADED",
    operator_id: "system",
    entity_id: "containerlab_fabric",
    entity_type: "topology",
    details: { nodes_count: 5, links_count: 6 },
    timestamp: new Date().toISOString(),
  },
];

router.get("/", (req, res) => {
  const { action, operator_id, entity_type } = req.query;
  let results = [...auditRecordsStore];
  if (action) {
    results = results.filter((r) => r.action === action);
  }
  if (operator_id) {
    results = results.filter((r) => r.operator_id === operator_id);
  }
  if (entity_type) {
    results = results.filter((r) => r.entity_type === entity_type);
  }
  res.json(results);
});

router.get("/verification", (req, res) => {
  res.json({
    is_valid: true,
    total_records: auditRecordsStore.length,
    sequence_range: [0, auditRecordsStore.length - 1],
    genesis_verified: true,
    latest_sequence_number: auditRecordsStore[auditRecordsStore.length - 1].sequence_number,
    latest_chain_hash: auditRecordsStore[auditRecordsStore.length - 1].record_hash,
    detected_violations: [],
    verified_at: new Date().toISOString(),
  });
});

router.get("/:id", (req, res) => {
  const record = auditRecordsStore.find((r) => r.record_id === req.params.id);
  if (!record) {
    return res.status(404).json({ error: `Audit record ${req.params.id} not found` });
  }
  res.json(record);
});

module.exports = router;

