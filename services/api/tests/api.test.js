/**
 * api.test.js — Comprehensive Jest tests for Node.js API Gateway endpoints.
 */

"use strict";

const request = require("supertest");
const { app } = require("../src/index");

describe("API Gateway REST Endpoints", () => {
  describe("GET /api/v1/system/status", () => {
    it("returns system status with mock provider transparency", async () => {
      const res = await request(app).get("/api/v1/system/status");
      expect(res.statusCode).toBe(200);
      expect(res.body.service).toBe("api_gateway");
      expect(res.body.status).toBe("healthy");
      expect(res.body.mock_provider).toBe(true);
      expect(res.body.provider_name).toBe("ContainerlabMockProvider");
    });
  });

  describe("Incidents Endpoints", () => {
    it("GET /api/v1/incidents returns list of incidents", async () => {
      const res = await request(app).get("/api/v1/incidents");
      expect(res.statusCode).toBe(200);
      expect(Array.isArray(res.body)).toBe(true);
      expect(res.body.length).toBeGreaterThanOrEqual(2);
      expect(res.body[0]).toHaveProperty("incident_id");
      expect(res.body[0]).toHaveProperty("severity");
    });

    it("GET /api/v1/incidents/:id returns specific incident", async () => {
      const res = await request(app).get("/api/v1/incidents/INC-0001");
      expect(res.statusCode).toBe(200);
      expect(res.body.incident_id).toBe("INC-0001");
      expect(res.body.protocol).toBe("bgp");
    });

    it("GET /api/v1/incidents/:id/diagnosis returns RCA details", async () => {
      const res = await request(app).get("/api/v1/incidents/INC-0001/diagnosis");
      expect(res.statusCode).toBe(200);
      expect(res.body.diagnosis_id).toBe("DIAG-0001");
      expect(res.body.root_cause).toContain("BGP");
      expect(res.body.confidence_score).toBeGreaterThan(0.9);
    });

    it("POST /api/v1/incidents triggers new incident", async () => {
      const res = await request(app)
        .post("/api/v1/incidents")
        .send({
          scenario_id: "CLAB_SCENARIO_1_BGP",
          target_node: "R1",
          protocol: "bgp",
          severity: "HIGH",
          description: "Test injected fault",
        });
      expect(res.statusCode).toBe(201);
      expect(res.body).toHaveProperty("incident_id");
      expect(res.body.status).toBe("ACTIVE");
    });
  });

  describe("Remediation & Approval Gate", () => {
    it("GET /api/v1/remediation/proposals returns proposals", async () => {
      const res = await request(app).get("/api/v1/remediation/proposals");
      expect(res.statusCode).toBe(200);
      expect(res.body.length).toBeGreaterThanOrEqual(1);
      expect(res.body[0]).toHaveProperty("proposal_hash");
    });

    it("POST /api/v1/remediation/proposals/:id/approve rejects with invalid hash", async () => {
      const res = await request(app)
        .post("/api/v1/remediation/proposals/PROP-0001/approve")
        .send({
          operator_id: "operator_alice",
          proposal_hash: "invalid_tampered_hash_value",
          reason: "Approved remediation",
        });
      expect(res.statusCode).toBe(400);
      expect(res.body.error).toContain("Cryptographic proposal hash verification failed");
    });

    it("POST /api/v1/remediation/proposals/:id/approve approves with valid hash", async () => {
      const propRes = await request(app).get("/api/v1/remediation/proposals/PROP-0001");
      const validHash = propRes.body.proposal_hash;

      const res = await request(app)
        .post("/api/v1/remediation/proposals/PROP-0001/approve")
        .send({
          operator_id: "operator_alice",
          proposal_hash: validHash,
          reason: "Authorized by test operator",
        });
      expect(res.statusCode).toBe(200);
      expect(res.body.status).toBe("VERIFIED");
      expect(res.body.approved_by).toBe("operator_alice");
    });

    it("POST /api/v1/remediation/proposals/:id/reject rejects pending proposal", async () => {
      const res = await request(app)
        .post("/api/v1/remediation/proposals/PROP-0002/reject")
        .send({
          operator_id: "operator_bob",
          reason: "Manual inspection preferred",
        });
      expect(res.statusCode).toBe(200);
      expect(res.body.status).toBe("REJECTED");
      expect(res.body.rejection_reason).toBe("Manual inspection preferred");
    });
  });

  describe("Kill Switch & Safety Gate", () => {
    it("GET /api/v1/kill-switch returns current status", async () => {
      const res = await request(app).get("/api/v1/kill-switch");
      expect(res.statusCode).toBe(200);
      expect(res.body).toHaveProperty("active");
    });

    it("POST /api/v1/kill-switch/activate triggers emergency freeze", async () => {
      const res = await request(app)
        .post("/api/v1/kill-switch/activate")
        .send({ operator_id: "security_officer", reason: "Emergency test freeze" });
      expect(res.statusCode).toBe(200);
      expect(res.body.active).toBe(true);

      // Verify approvals are blocked when kill switch is active
      const apprRes = await request(app)
        .post("/api/v1/remediation/proposals/PROP-0001/approve")
        .send({ operator_id: "operator", proposal_hash: "any", reason: "test" });
      expect(apprRes.statusCode).toBe(403);

      // Deactivate kill switch to restore normal state
      const deactRes = await request(app)
        .post("/api/v1/kill-switch/deactivate")
        .send({ operator_id: "security_officer", reason: "Test ended" });
      expect(deactRes.statusCode).toBe(200);
      expect(deactRes.body.active).toBe(false);
    });
  });

  describe("Topology & Blast Radius", () => {
    it("GET /api/v1/topology returns nodes and links", async () => {
      const res = await request(app).get("/api/v1/topology");
      expect(res.statusCode).toBe(200);
      expect(res.body.nodes.length).toBe(5);
      expect(res.body.links.length).toBe(6);
      expect(res.body.provider_mode).toBe("containerlab_mock");
    });

    it("GET /api/v1/topology/blast-radius computes IER and NUR", async () => {
      const res = await request(app).get("/api/v1/topology/blast-radius?root_cause_device=leaf-01");
      expect(res.statusCode).toBe(200);
      expect(res.body.impact_exposure_ratio).toBe(0.40);
      expect(res.body.network_unreachability_ratio).toBe(0.0);
    });
  });

  describe("Audit Trail & Verification", () => {
    it("GET /api/v1/audit returns immutable records", async () => {
      const res = await request(app).get("/api/v1/audit");
      expect(res.statusCode).toBe(200);
      expect(Array.isArray(res.body)).toBe(true);
      expect(res.body.length).toBeGreaterThanOrEqual(1);
    });

    it("GET /api/v1/audit/verification verifies hash chain", async () => {
      const res = await request(app).get("/api/v1/audit/verification");
      expect(res.statusCode).toBe(200);
      expect(res.body.is_valid).toBe(true);
      expect(res.body.genesis_verified).toBe(true);
    });
  });
});

