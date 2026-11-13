/**
 * socket.test.js — Jest test for Socket.IO event streaming and rooms.
 */

"use strict";

const http = require("http");
const { io: ioClient } = require("socket.io-client");
const { app, server, broadcastEvent } = require("../src/index");

describe("Socket.IO Event Streaming", () => {
  let clientSocket;
  let testPort;

  beforeAll((done) => {
    // Start listening on ephemeral port
    server.listen(0, () => {
      testPort = server.address().port;
      done();
    });
  });

  afterAll((done) => {
    if (clientSocket && clientSocket.connected) {
      clientSocket.disconnect();
    }
    server.close(done);
  });

  it("connects client and receives welcome ready event", (done) => {
    clientSocket = ioClient(`http://localhost:${testPort}`);

    clientSocket.on("connection:ready", (payload) => {
      expect(payload.status).toBe("connected");
      expect(payload.rooms).toContain("incidents");
      done();
    });
  });

  it("subscribes to incident topic and receives subscription ack", (done) => {
    clientSocket.emit("subscribe", { topic: "incidents" });

    clientSocket.on("subscription:acknowledged", (payload) => {
      expect(payload.topic).toBe("incidents");
      done();
    });
  });

  it("broadcasts domain event and delivers to subscribed client", (done) => {
    clientSocket.on("incident:alert", (envelope) => {
      expect(envelope.event).toBe("incident:alert");
      expect(envelope.payload.incident_id).toBe("INC-9999");
      done();
    });

    broadcastEvent("incident:alert", { incident_id: "INC-9999", severity: "CRITICAL" });
  });

  it("responds to ping with pong", (done) => {
    clientSocket.emit("ping");
    clientSocket.on("pong", (payload) => {
      expect(payload).toHaveProperty("timestamp");
      done();
    });
  });
});

