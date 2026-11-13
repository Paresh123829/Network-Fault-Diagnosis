/**
 * topology.js — Network topology and blast radius route for Node.js API Gateway.
 */

"use strict";

const express = require("express");
const router = express.Router();

const mockTopology = {
  topology_id: "containerlab_fabric",
  nodes: [
    { id: "spine-01", label: "spine-01", role: "spine", tier: 1, status: "UP", ip: "10.0.0.1", vendor: "cisco", model: "n9k" },
    { id: "spine-02", label: "spine-02", role: "spine", tier: 1, status: "UP", ip: "10.0.0.2", vendor: "cisco", model: "n9k" },
    { id: "leaf-01", label: "leaf-01", role: "leaf", tier: 2, status: "UP", ip: "10.0.1.1", vendor: "cisco", model: "n9k" },
    { id: "leaf-02", label: "leaf-02", role: "leaf", tier: 2, status: "UP", ip: "10.0.1.2", vendor: "cisco", model: "n9k" },
    { id: "border-01", label: "border-01", role: "border", tier: 0, status: "UP", ip: "10.0.2.1", vendor: "cisco", model: "n9k" },
  ],
  links: [
    { id: "link-01", source: "leaf-01", target: "spine-01", source_port: "eth1", target_port: "eth1", bandwidth: "100G", status: "UP", loss: 0.0 },
    { id: "link-02", source: "leaf-01", target: "spine-02", source_port: "eth2", target_port: "eth1", bandwidth: "100G", status: "UP", loss: 0.0 },
    { id: "link-03", source: "leaf-02", target: "spine-01", source_port: "eth1", target_port: "eth2", bandwidth: "100G", status: "UP", loss: 0.0 },
    { id: "link-04", source: "leaf-02", target: "spine-02", source_port: "eth2", target_port: "eth2", bandwidth: "100G", status: "UP", loss: 0.0 },
    { id: "link-05", source: "border-01", target: "spine-01", source_port: "eth1", target_port: "eth3", bandwidth: "100G", status: "UP", loss: 0.0 },
    { id: "link-06", source: "border-01", target: "spine-02", source_port: "eth2", target_port: "eth3", bandwidth: "100G", status: "UP", loss: 0.0 },
  ],
  provider_mode: "containerlab_mock",
  device_count: 5,
  link_count: 6,
};

router.get("/", (req, res) => {
  res.json(mockTopology);
});

router.get("/devices", (req, res) => {
  res.json(mockTopology.nodes);
});

router.get("/links", (req, res) => {
  res.json(mockTopology.links);
});

router.get("/blast-radius", (req, res) => {
  const rootCause = req.query.root_cause_device || "leaf-01";
  res.json({
    originating_devices: [rootCause],
    blast_radius_device_count: 2,
    total_nodes_in_topology: 5,
    impact_exposure_ratio: 0.40,
    network_unreachability_ratio: 0.0,
    severity_assessment: "MEDIUM",
    direct_impact_devices: [rootCause],
    adjacent_exposure_devices: ["spine-01", "spine-02"],
    lost_paths_count: 2,
    surviving_alternate_paths_count: 4,
    degraded_ecmp_groups_count: 1,
    spofs_triggered: [],
  });
});

router.get("/paths", (req, res) => {
  const { source, destination } = req.query;
  res.json({
    source: source || "leaf-01",
    destination: destination || "border-01",
    shortest_paths: [
      [source || "leaf-01", "spine-01", destination || "border-01"],
      [source || "leaf-01", "spine-02", destination || "border-01"],
    ],
    paths_count: 2,
    is_reachable: true,
    redundancy_level: "HIGH",
  });
});

module.exports = router;

