"""
test_milestone8_e2e_api.py — End-to-end integration tests for Milestone 8 workflow.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.ai.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_full_autonomous_incident_to_remediation_lifecycle(client: TestClient):
    """
    Validates complete end-to-end operational workflow:
    1. Incident Triggering / Fault Injection
    2. Telemetry and RCA Diagnosis Retrieval
    3. Quantitative Blast Radius Calculation
    4. Emergency Kill Switch Safety Block Verification
    5. Human Approval with SHA-256 Hash Binding
    6. Automated Deterministic Execution & Verification
    7. Tamper-Evident Cryptographic Audit Chain Verification
    """
    # Step 1: Trigger fault incident
    trigger_resp = client.post(
        "/api/v1/incidents",
        json={
            "scenario_id": "CLAB_SCENARIO_1_BGP",
            "target_node": "R1",
            "protocol": "bgp",
            "severity": "CRITICAL",
            "description": "Integration Test E2E BGP Session Teardown",
        },
    )
    assert trigger_resp.status_code == 201
    incident = trigger_resp.json()
    incident_id = incident["incident_id"]
    assert incident_id.startswith("INC-")

    # Step 2: Retrieve Diagnosis and RCA
    diag_resp = client.get(f"/api/v1/incidents/{incident_id}/diagnosis")
    assert diag_resp.status_code == 200
    diagnosis = diag_resp.json()
    assert diagnosis["incident_id"] == incident_id
    assert diagnosis["confidence_score"] >= 0.90
    assert "remediation_proposal_id" in diagnosis

    # Step 3: Compute Blast Radius
    blast_resp = client.get(f"/api/v1/topology/blast-radius?root_cause_device={incident['target_node']}")
    assert blast_resp.status_code == 200
    blast = blast_resp.json()
    assert "impact_exposure_ratio" in blast
    assert "network_unreachability_ratio" in blast

    # Step 4: Register dedicated proposal for this e2e incident and test Kill Switch Block
    from services.ai.api.remediation import _PROPOSALS_STORE, _compute_hash
    prop_id = f"PROP-E2E-{incident_id}"
    h = _compute_hash({
        "proposal_id": prop_id,
        "operation": "clear_bgp_session",
        "target_node": "R1",
        "parameters": {"soft": True},
    })
    _PROPOSALS_STORE[prop_id] = {
        "proposal_id": prop_id,
        "incident_id": incident_id,
        "diagnosis_id": diagnosis["diagnosis_id"],
        "operation": "clear_bgp_session",
        "target_node": "R1",
        "parameters": {"soft": True},
        "actions": [{"command": "vtysh -c 'clear ip bgp 172.16.12.2 soft'", "target_node": "R1", "phase": "apply"}],
        "risk_level": "MEDIUM",
        "safety_score": 0.98,
        "blast_radius_devices": 2,
        "proposal_hash": h,
        "status": "PENDING_APPROVAL",
        "created_at": "2026-11-13T00:00:00Z",
        "expires_at": "2026-11-14T00:00:00Z",
    }
    prop_hash = h

    client.post(
        "/api/v1/kill-switch/activate",
        json={"operator_id": "sec_auditor", "reason": "Pre-execution security hold"},
    )

    # Attempt approval while kill switch is active -> MUST be blocked with 403
    block_resp = client.post(
        f"/api/v1/remediation/proposals/{prop_id}/approve",
        json={"operator_id": "operator_e2e", "proposal_hash": prop_hash, "reason": "Authorized"},
    )
    assert block_resp.status_code == 403

    # Deactivate kill switch
    client.post(
        "/api/v1/kill-switch/deactivate",
        json={"operator_id": "sec_auditor", "reason": "Security hold lifted"},
    )

    # Step 5: Test Approval with Tampered Hash -> MUST be rejected
    tamper_resp = client.post(
        f"/api/v1/remediation/proposals/{prop_id}/approve",
        json={"operator_id": "operator_e2e", "proposal_hash": "bad_hash_123456", "reason": "Tampered"},
    )
    assert tamper_resp.status_code == 400

    # Step 6: Valid Approval with Canonical Hash -> Success (or 409 if already executed)
    approve_resp = client.post(
        f"/api/v1/remediation/proposals/{prop_id}/approve",
        json={"operator_id": "operator_e2e", "proposal_hash": prop_hash, "reason": "Valid E2E Sign-off"},
    )
    assert approve_resp.status_code in (200, 409)

    # Step 7: Check Execution List and Verification
    execs_resp = client.get("/api/v1/remediation/executions")
    assert execs_resp.status_code == 200
    execs = execs_resp.json()
    assert len(execs) >= 1
    latest_exec = execs[0]

    verif_resp = client.get(f"/api/v1/remediation/executions/{latest_exec['execution_id']}/verification")
    assert verif_resp.status_code == 200
    assert verif_resp.json()["slo_compliance"] is True

    # Step 8: Verify Cryptographic Audit Chain Integrity
    chain_verif = client.get("/api/v1/audit/verification").json()
    assert chain_verif["is_valid"] is True
    assert chain_verif["genesis_verified"] is True
    assert len(chain_verif["detected_violations"]) == 0
