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
    root_cause: incident.ground_truth_root_cause || incident.description || "Protocol / Interface Anomaly Identified",
    fault_family: incident.protocol || "interface",
    target_device: incident.target_node,
    target_component: incident.target_component,
    confidence_score: incident.confidence_score !== undefined ? incident.confidence_score : 0.985,
    blast_radius_devices: incident.blast_radius_devices || 1,
    impacted_devices: [incident.target_node, "spine-01"],
    recommended_action: incident.recommended_action || "restore_interface_admin_state",
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
    evidence: incident.evidence || {
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
  res.json(
    incident.timeline || [
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
    ]
  );
});

// POST /api/v1/incidents (Trigger new incident / case prototype)
router.post("/", (req, res) => {
  const {
    scenario_id,
    case_number,
    case_id,
    target_node,
    target_component,
    protocol,
    severity,
    description,
    title,
    ground_truth_root_cause,
    confidence_score,
    blast_radius_devices,
    recommended_action,
    symptoms,
    evidence,
    is_healthy_baseline,
  } = req.body;

  const incNum = incidentsStore.length + 1;
  const incId = `INC-${String(incNum).padStart(4, "0")}`;
  const now = new Date().toISOString();

  const isHealthy = is_healthy_baseline || case_number === 0 || case_number === 1;

  const newIncident = {
    incident_id: incId,
    scenario_id: scenario_id || case_id || `CASE_${case_number !== undefined ? case_number : 1}`,
    case_number: case_number !== undefined ? case_number : null,
    title: title || description || `Case ${case_number !== undefined ? case_number : 1}: Fault Injection on ${target_node || "R1"}`,
    description: description || `Simulated prototype execution for Case ${case_number !== undefined ? case_number : 1}`,
    target_node: target_node || "leaf1",
    target_component: target_component || "eth1",
    protocol: protocol || "bgp",
    severity: isHealthy ? "LOW" : (severity || "HIGH"),
    status: isHealthy ? "RESOLVED" : "ACTIVE",
    created_at: now,
    updated_at: now,
    blast_radius_devices: blast_radius_devices !== undefined ? blast_radius_devices : 2,
    ground_truth_root_cause: ground_truth_root_cause || description,
    confidence_score: confidence_score !== undefined ? confidence_score : 0.985,
    recommended_action: recommended_action || "restore_interface_admin_state",
    symptoms: symptoms || [
      {
        event_type: `${(protocol || "bgp").toUpperCase()}_FAULT`,
        severity: severity || "HIGH",
        description: `Anomaly detected on ${target_node || "leaf1"}`,
        target_node: target_node || "leaf1",
      },
    ],
    diagnosis_id: `DIAG-${String(incNum).padStart(4, "0")}`,
    remediation_proposal_id: isHealthy ? null : `PROP-${String(incNum).padStart(4, "0")}`,
    timeline: [
      {
        timestamp: now,
        event: "INCIDENT_TRIGGERED",
        actor: "operator_prototype_api",
        details: isHealthy
          ? `Healthy baseline verified: 0 anomalies across fabric.`
          : `Fault prototype triggered for Case ${case_number !== undefined ? case_number : 1}`,
      },
    ],
    evidence: evidence || {
      telemetry_samples: 45,
      anomalous_metrics: isHealthy ? [] : [{ metric: "interface_oper_status", actual: "down" }],
      syslog_snippets: isHealthy
        ? ["SYS-5-CONFIG_I: Normal healthy baseline telemetry"]
        : [`%${(protocol || "bgp").toUpperCase()}-5-FAULT: Anomaly detected on ${target_node || "leaf1"}`],
      provider_mode: "prototype_simulation",
    },
  };

  incidentsStore.unshift(newIncident);

  // Broadcast real-time Socket.IO event
  broadcastEvent("incident:created", newIncident, "incidents");

  res.status(201).json(newIncident);
});

module.exports = router;

