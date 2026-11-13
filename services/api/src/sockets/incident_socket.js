/**
 * incident_socket.js — Socket.IO Real-Time Streaming Gateway for Network Incidents.
 */

"use strict";

const { Server } = require("socket.io");

let ioInstance = null;

/**
 * Initialize Socket.IO on the provided HTTP server.
 * @param {import("http").Server} server
 * @param {object} [options]
 * @returns {Server}
 */
function initSocketServer(server, options = {}) {
  const io = new Server(server, {
    cors: {
      origin: "*",
      methods: ["GET", "POST"],
    },
    ...options,
  });

  io.on("connection", (socket) => {
    const clientId = socket.id;
    console.log(`[Socket.IO] Client connected: ${clientId}`);

    // Welcome payload
    socket.emit("connection:ready", {
      status: "connected",
      clientId,
      timestamp: new Date().toISOString(),
      rooms: ["incidents", "remediation", "topology", "audit", "kill_switch"],
    });

    // Client subscribes to room or topic
    socket.on("subscribe", (data) => {
      const topic = (data && data.topic) || "general";
      socket.join(topic);
      socket.emit("subscription:acknowledged", {
        topic,
        timestamp: new Date().toISOString(),
      });
      console.log(`[Socket.IO] Client ${clientId} subscribed to topic: ${topic}`);
    });

    // Client unsubscribes
    socket.on("unsubscribe", (data) => {
      const topic = (data && data.topic) || "general";
      socket.leave(topic);
      socket.emit("unsubscription:acknowledged", { topic });
    });

    // Ping / Pong
    socket.on("ping", () => {
      socket.emit("pong", { timestamp: new Date().toISOString() });
    });

    socket.on("disconnect", (reason) => {
      console.log(`[Socket.IO] Client disconnected: ${clientId} (${reason})`);
    });
  });

  ioInstance = io;
  return io;
}

/**
 * Get active Socket.IO server instance.
 * @returns {Server|null}
 */
function getSocketServer() {
  return ioInstance;
}

/**
 * Broadcast an event to all connected clients or a specific room.
 * @param {string} event
 * @param {object} payload
 * @param {string} [room]
 */
function broadcastEvent(event, payload, room = null) {
  if (!ioInstance) {
    return;
  }
  const envelope = {
    event,
    timestamp: new Date().toISOString(),
    payload,
  };
  if (room) {
    ioInstance.to(room).emit(event, envelope);
  } else {
    ioInstance.emit(event, envelope);
  }
}

module.exports = {
  initSocketServer,
  getSocketServer,
  broadcastEvent,
};

