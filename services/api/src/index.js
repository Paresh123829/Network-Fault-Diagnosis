/**
 * index.js — Entry point for the Node.js API Gateway & Real-Time Streaming service.
 */

"use strict";

require("dotenv").config();

const express = require("express");
const cors = require("cors");
const http = require("http");

const { initSocketServer, getSocketServer, broadcastEvent } = require("./sockets/incident_socket");
const systemRouter = require("./routes/system");
const incidentsRouter = require("./routes/incidents");
const { router: approvalsRouter } = require("./routes/approvals");
const killSwitchRouter = require("./routes/kill_switch");
const topologyRouter = require("./routes/topology");
const auditRouter = require("./routes/audit");

const app = express();
const server = http.createServer(app);

// Initialize Socket.IO on HTTP server
const io = initSocketServer(server);

const PORT = process.env.API_PORT || 4000;
const NODE_ENV = process.env.NODE_ENV || "development";

// ─── Middleware ───────────────────────────────────────────────────────────────
app.use(cors());
app.use(express.json());

// ─── Logging helper ───────────────────────────────────────────────────────────
function log(level, message, meta = {}) {
  const entry = {
    timestamp: new Date().toISOString(),
    level,
    message,
    ...meta,
  };
  console.log(JSON.stringify(entry));
}

// ─── Health check ─────────────────────────────────────────────────────────────
app.get("/health", (req, res) => {
  log("info", "Health check requested");
  res.json({
    service: "api",
    status: "ok",
    version: "0.8.0",
    timestamp: new Date().toISOString(),
    environment: NODE_ENV,
    network_provider: "ContainerlabMockProvider",
    mock_mode: true,
  });
});

app.get("/api/v1/health", (req, res) => {
  res.json({
    service: "api",
    status: "ok",
    version: "0.8.0",
    timestamp: new Date().toISOString(),
    environment: NODE_ENV,
    network_provider: "ContainerlabMockProvider",
  });
});

// ─── API v1 Routers ───────────────────────────────────────────────────────────
app.use("/api/v1/system", systemRouter);
app.use("/api/v1/incidents", incidentsRouter);
app.use("/api/v1/remediation", approvalsRouter);
app.use("/api/v1/kill-switch", killSwitchRouter);
app.use("/api/v1/topology", topologyRouter);
app.use("/api/v1/audit", auditRouter);

// ─── 404 handler ─────────────────────────────────────────────────────────────
app.use((req, res) => {
  res.status(404).json({ error: "Not found", path: req.path });
});

// ─── Global error handler ─────────────────────────────────────────────────────
app.use((err, req, res, _next) => {
  log("error", "Unhandled error", { message: err.message, stack: err.stack });
  res.status(500).json({ error: "Internal server error" });
});

// ─── Start server (only when run directly) ────────────────────────────────────
if (require.main === module) {
  server.listen(PORT, () => {
    log("info", `API Gateway listening with Socket.IO`, { port: PORT, environment: NODE_ENV });
  });
}

module.exports = { app, server, io, broadcastEvent };
