/**
 * health.test.js — Jest test for the Node.js API /health endpoint.
 * Run with: npm test (from services/api/)
 *
 * Supertest automatically binds the app to an ephemeral port,
 * so no port conflicts occur even if 4000 is already in use.
 */

"use strict";

const request = require("supertest");
const { app } = require("../src/index");

describe("GET /health", () => {
  it("returns 200 with status ok", async () => {
    const res = await request(app).get("/health");
    expect(res.statusCode).toBe(200);
    expect(res.body.status).toBe("ok");
    expect(res.body.service).toBe("api");
    expect(res.body.timestamp).toBeDefined();
  });

  it("returns 404 for unknown routes", async () => {
    const res = await request(app).get("/unknown-route");
    expect(res.statusCode).toBe(404);
  });
});
