/**
 * system.js — System status and health route for Node.js API Gateway.
 */

"use strict";

const express = require("express");
const router = express.Router();

router.get("/status", (req, res) => {
  res.json({
    service: "api_gateway",
    status: "healthy",
    version: "0.8.0",
    timestamp: new Date().toISOString(),
    environment: process.env.NODE_ENV || "development",
    network_provider_mode: "containerlab_mock",
    mock_provider: true,
    provider_name: "ContainerlabMockProvider",
    mongodb_connected: false,
    kill_switch_active: false,
  });
});

router.get("/health", (req, res) => {
  res.json({
    service: "api",
    status: "ok",
    version: "0.8.0",
    timestamp: new Date().toISOString(),
    network_provider: "ContainerlabMockProvider",
  });
});

module.exports = router;

