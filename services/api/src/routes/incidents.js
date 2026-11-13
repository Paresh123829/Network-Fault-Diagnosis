/**
 * incidents.js — Incident querying and triggering route for Node.js API Gateway.
 */

"use strict";

const express = require("express");
const router = express.Router();
const { broadcastEvent } = require("../sockets/incident_socket");

// Mock/fallback store
const incidentsStore = [
  {
    incident_id: "INC-0001",
    scenario_id: "CLAB_SCENARIO_1_BGP",
    title: "BGP Neighbor Session Failure & Recovery",
    description: "Clears the eBGP session between R1 and R2, verifying route withdrawal.",
    target_node: "R1",
    target_component: "172.16.12.2",
    protocol: "bgp",
    severity: "HIGH",
    status: "ACTIVE",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    blast_radius_devices: 2,
    symptoms: [
      {
        event_type: "BGP_NEIGHBOR_DOWN",
        severity: "HIGH",
        description: "BGP neighbor 172.16.12.2 state dropped from Established to Idle",
        target_node: "R1",
      },
    ],
    diagnosis_id: "DIAG-0001",
    remediation_proposal_id: "PROP-0001",
  },
  {
    incident_id: "INC-0002",
    scenario_id: "CLAB_SCENARIO_2_OSPF",
    title: "OSPF Adjacency Failure & Recovery",
    description: "Simulates OSPF adjacency failure due to hello timeout or MTU mismatch.",
    target_node: "R1",
    target_component: "GigabitEthernet0/0/0/1",
    protocol: "ospf",
    severity: "HIGH",
    status: "RESOLVED",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    blast_radius_devices: 2,
    symptoms: [
      {
        event_type: "OSPF_NEIGHBOR_DOWN",
        severity: "HIGH",
        description: "OSPF adjacency dropped from Full to Down",
        target_node: "R1",
      },
    ],
    diagnosis_id: "DIAG-0002",
    remediation_proposal_id: "PROP-0002",
  },
];

// GET /api/v1/incidents
router.get("/", (req, res) => {
  const { status, severity } = req.query;
  let results = [...incidentsStore];
  if (status) {
    results = results.filter((i) => i.status.toUpperCase() === status.toUpperCase());
  }
  if (severity) {
    results = results.filter((i) => i.severity.toUpperCase() === severity.toUpperCase());
  }
  res.json(results);
});

// GET /api/v1/incidents/:id
router.get("/:id", (req, res) => {
  const incident = incidentsStore.find((i) => i.incident_id === req.params.id);
  if (!incident) {
    return res.status(404).json({ error: `Incident ${req.params.id} not found` });
  }
  res.json(incident);
});

// GET /api/v1/incidents/:id/diagnosis
router.get("/:id/diagnosis", (req, res) => {
  const incident = incidentsStore.find((i) => i.incident_id === req.params.id);
  if (!incident) {
    return res.status(404).json({ error: `Incident ${req.params.id} not found` });
  }
  res.json({
    diagnosis_id: incident.diagnosis_id || `DIAG-${incident.incident_id}`,
    incident_id: incident.incident_id,
    status: "COMPLETED",
    root_cause: "eBGP Session Down / Keepalive Expired",
    fault_family: incident.protocol,
    target_device: incident.target_node,
    target_component: incident.target_component,
    confidence_score: 0.985,
    blast_radius_devices: incident.blast_radius_devices,
    impacted_devices: [incident.target_node, "leaf-01"],
    recommended_action: "clear_bgp_session",
    remediation_proposal_id: incident.remediation_proposal_id,
  });
});

// GET /api/v1/incidents/:id/evidence
router.get("/:id/evidence", (req, res) => {
  const incident = incidentsStore.find((i) => i.incident_id === req.params.id);
  if (!incident) {
    return res.status(404).json({ error: `Incident ${req.params.id} not found` });
  }
  res.json({
    incident_id: incident.incident_id,
    evidence: {
      telemetry_samples: 45,
      anomalous_metrics: [{ metric: "interface_oper_status", actual: "down" }],
      syslog_snippets: ["%BGP-5-ADJCHANGE: neighbor 172.16.12.2 Down"],
      provider_mode: "containerlab_mock",
    },
  });
});

// GET /api/v1/incidents/:id/history
router.get("/:id/history", (req, res) => {
  const incident = incidentsStore.find((i) => i.incident_id === req.params.id);
  if (!incident) {
    return res.status(404).json({ error: `Incident ${req.params.id} not found` });
  }
  res.json([
    {
      timestamp: incident.created_at,
      event: "INCIDENT_DETECTED",
      actor: "telemetry_ingestor",
      details: `Fault symptoms recorded on ${incident.target_node}`,
    },
    {
      timestamp: incident.updated_at,
      event: "DIAGNOSIS_COMPLETED",
      actor: "diagnosis_orchestrator",
      details: "RCA verified with 98.5% confidence",
    },
  ]);
});

// POST /api/v1/incidents (Trigger new incident)
router.post("/", (req, res) => {
  const { scenario_id, target_node, protocol, severity, description } = req.body;
  const incNum = incidentsStore.length + 1;
  const incId = `INC-${String(incNum).padStart(4, "0")}`;
  const now = new Date().toISOString();

  const newIncident = {
    incident_id: incId,
    scenario_id: scenario_id || "CLAB_SCENARIO_1_BGP",
    title: description || `Fault Injection on ${target_node || "R1"}`,
    description: description || "Simulated test fault",
    target_node: target_node || "R1",
    target_component: "eth1",
    protocol: protocol || "bgp",
    severity: severity || "HIGH",
    status: "ACTIVE",
    created_at: now,
    updated_at: now,
    blast_radius_devices: 2,
    symptoms: [
      {
        event_type: `${(protocol || "bgp").toUpperCase()}_FAULT`,
        severity: severity || "HIGH",
        description: `Anomaly detected on ${target_node || "R1"}`,
        target_node: target_node || "R1",
      },
    ],
    diagnosis_id: `DIAG-${String(incNum).padStart(4, "0")}`,
    remediation_proposal_id: `PROP-${String(incNum).padStart(4, "0")}`,
  };

  incidentsStore.unshift(newIncident);

  // Broadcast real-time Socket.IO event
  broadcastEvent("incident:created", newIncident, "incidents");

  res.status(201).json(newIncident);
});

module.exports = router;

