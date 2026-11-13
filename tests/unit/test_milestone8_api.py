"""
test_milestone8_api.py — Unit tests for Milestone 8 FastAPI REST & Streaming APIs.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.ai.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


class TestMilestone8SystemAndMeta:
    def test_health_check(self, client: TestClient):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "ai"
        assert data["status"] == "ok"
        assert "network_provider" in data
        assert data["mock_mode"] is True

    def test_system_status_provider_transparency(self, client: TestClient):
        response = client.get("/api/v1/system/status")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "ai_engine"
        assert data["mock_provider"] is True
        assert data["provider_name"] == "ContainerlabMockProvider"
        assert data["network_provider_mode"] == "containerlab_mock"
        assert isinstance(data["active_incidents_count"], int)
        assert "kill_switch_active" in data


class TestMilestone8Incidents:
    def test_list_incidents(self, client: TestClient):
        response = client.get("/api/v1/incidents")
        assert response.status_code == 200
        incidents = response.json()
        assert isinstance(incidents, list)
        assert len(incidents) >= 2
        assert "incident_id" in incidents[0]
        assert "severity" in incidents[0]

    def test_filter_incidents_by_status(self, client: TestClient):
        response = client.get("/api/v1/incidents?status=ACTIVE")
        assert response.status_code == 200
        for inc in response.json():
            assert inc["status"] == "ACTIVE"

    def test_get_incident_detail_and_diagnosis(self, client: TestClient):
        response = client.get("/api/v1/incidents/INC-0001")
        assert response.status_code == 200
        inc = response.json()
        assert inc["incident_id"] == "INC-0001"
        assert "target_node" in inc

        diag_resp = client.get("/api/v1/incidents/INC-0001/diagnosis")
        assert diag_resp.status_code == 200
        diag = diag_resp.json()
        assert diag["incident_id"] == "INC-0001"
        assert diag["confidence_score"] > 0.90
        assert "root_cause" in diag

    def test_get_incident_evidence_and_history(self, client: TestClient):
        ev_resp = client.get("/api/v1/incidents/INC-0001/evidence")
        assert ev_resp.status_code == 200
        assert "evidence" in ev_resp.json()

        hist_resp = client.get("/api/v1/incidents/INC-0001/history")
        assert hist_resp.status_code == 200
        history = hist_resp.json()
        assert isinstance(history, list)
        assert len(history) >= 1

    def test_trigger_new_fault_incident(self, client: TestClient):
        payload = {
            "scenario_id": "CLAB_SCENARIO_1_BGP",
            "target_node": "R1",
            "protocol": "bgp",
            "severity": "HIGH",
            "description": "Automated unit test fault",
        }
        response = client.post("/api/v1/incidents", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["incident_id"].startswith("INC-")
        assert data["status"] == "ACTIVE"
        assert data["target_node"] == "R1"


class TestMilestone8TopologyAndBlastRadius:
    def test_get_topology_graph(self, client: TestClient):
        response = client.get("/api/v1/topology")
        assert response.status_code == 200
        topo = response.json()
        assert "nodes" in topo
        assert "links" in topo
        assert topo["device_count"] >= 3
        assert topo["provider_mode"] == "containerlab_mock"

    def test_list_devices_and_links(self, client: TestClient):
        devs_resp = client.get("/api/v1/topology/devices")
        assert devs_resp.status_code == 200
        assert isinstance(devs_resp.json(), list)

        links_resp = client.get("/api/v1/topology/links")
        assert links_resp.status_code == 200
        assert isinstance(links_resp.json(), list)

    def test_calculate_blast_radius(self, client: TestClient):
        response = client.get("/api/v1/topology/blast-radius?root_cause_device=R1")
        assert response.status_code == 200
        report = response.json()
        assert "impact_exposure_ratio" in report
        assert "network_unreachability_ratio" in report
        assert report["impact_exposure_ratio"] >= 0.0

    def test_path_analysis(self, client: TestClient):
        response = client.get("/api/v1/topology/paths?source=r1&destination=r2")
        assert response.status_code == 200
        data = response.json()
        assert data["is_reachable"] is True


class TestMilestone8RemediationApprovalGate:
    def test_list_proposals(self, client: TestClient):
        response = client.get("/api/v1/remediation/proposals")
        assert response.status_code == 200
        proposals = response.json()
        assert len(proposals) >= 1
        assert "proposal_hash" in proposals[0]

    def test_approval_rejects_on_hash_mismatch(self, client: TestClient):
        response = client.post(
            "/api/v1/remediation/proposals/PROP-0001/approve",
            json={
                "operator_id": "operator_alice",
                "proposal_hash": "invalid_tampered_hash_0000000000000000000000",
                "reason": "Test approval",
            },
        )
        assert response.status_code == 400
        assert "Cryptographic proposal hash verification failed" in response.json()["detail"]

    def test_approval_with_valid_hash(self, client: TestClient):
        prop = client.get("/api/v1/remediation/proposals/PROP-0001").json()
        valid_hash = prop["proposal_hash"]

        response = client.post(
            "/api/v1/remediation/proposals/PROP-0001/approve",
            json={
                "operator_id": "operator_alice",
                "proposal_hash": valid_hash,
                "reason": "Authorized test remediation",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "VERIFIED"
        assert data["approved_by"] == "operator_alice"

    def test_anti_replay_prevents_duplicate_approval(self, client: TestClient):
        prop = client.get("/api/v1/remediation/proposals/PROP-0001").json()
        response = client.post(
            "/api/v1/remediation/proposals/PROP-0001/approve",
            json={
                "operator_id": "operator_alice",
                "proposal_hash": prop["proposal_hash"],
                "reason": "Replay attempt",
            },
        )
        assert response.status_code == 409
        assert "Anti-replay" in response.json()["detail"]

    def test_rejection_of_proposal(self, client: TestClient):
        response = client.post(
            "/api/v1/remediation/proposals/PROP-0002/reject",
            json={"operator_id": "operator_bob", "reason": "Requires further investigation"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "REJECTED"


class TestMilestone8KillSwitchAndAudit:
    def test_kill_switch_lifecycle_and_freeze_enforcement(self, client: TestClient):
        # 1. Activate kill switch
        act_resp = client.post(
            "/api/v1/kill-switch/activate",
            json={"operator_id": "sec_officer", "reason": "Emergency freeze test"},
        )
        assert act_resp.status_code == 200
        assert act_resp.json()["active"] is True

        # 2. Verify kill switch status
        stat_resp = client.get("/api/v1/kill-switch")
        assert stat_resp.json()["active"] is True

        # 3. Verify approval is blocked
        blocked_resp = client.post(
            "/api/v1/remediation/proposals/PROP-0001/approve",
            json={"operator_id": "operator", "proposal_hash": "any", "reason": "test"},
        )
        assert blocked_resp.status_code == 403
        assert "Kill Switch is currently ACTIVE" in blocked_resp.json()["detail"]

        # 4. Deactivate kill switch
        deact_resp = client.post(
            "/api/v1/kill-switch/deactivate",
            json={"operator_id": "sec_officer", "reason": "Testing ended"},
        )
        assert deact_resp.status_code == 200
        assert deact_resp.json()["active"] is False

    def test_audit_chain_integrity_verification(self, client: TestClient):
        records_resp = client.get("/api/v1/audit")
        assert records_resp.status_code == 200
        records = records_resp.json()
        assert len(records) >= 3

        verif_resp = client.get("/api/v1/audit/verification")
        assert verif_resp.status_code == 200
        verif = verif_resp.json()
        assert verif["is_valid"] is True
        assert verif["genesis_verified"] is True
        assert len(verif["detected_violations"]) == 0
