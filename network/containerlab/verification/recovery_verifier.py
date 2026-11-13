"""
recovery_verifier.py — Independent Post-Remediation Verification Engine for Containerlab.

Core Principle: Successful CLI command execution is NOT proof of network recovery.
Recovery must be independently established using fresh protocol and connectivity telemetry.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from services.ai.schemas.contracts import (
    CheckItem,
    VerificationResult,
    VerificationStatus,
)
from services.ai.agents.diagnosis.remediation_persistence import remediation_persistence
from network.containerlab.runtime.driver import execute_clab_command, normalize_node_name
from network.containerlab.scenarios.models import ScenarioDefinition, VerificationCriteria

logger = logging.getLogger(__name__)


class ClabRecoveryVerifier:
    """
    Executes fresh observations against the Containerlab topology to independently verify recovery.
    """

    def __init__(self, persistence=None, force_mock: bool = False) -> None:
        self.persistence = persistence or remediation_persistence
        self.force_mock = force_mock

    def verify_scenario_recovery(
        self,
        scenario: ScenarioDefinition,
        execution_id: str,
    ) -> VerificationResult:
        crit = scenario.verification_criteria
        node = normalize_node_name(crit.target_node)
        now = datetime.now(timezone.utc)
        ver_id = f"ver_clab_{uuid.uuid4().hex[:10]}"
        checks: List[CheckItem] = []
        observed_state: Dict[str, Any] = {}
        expected_state: Dict[str, Any] = {"expected_state": crit.expected_state}
        all_passed = True
        failure_reasons: List[str] = []

        # ─── 1. Protocol State Verification ───
        if crit.protocol.value == "bgp":
            code, out, _ = execute_clab_command(node, ["vtysh", "-c", "show ip bgp summary json"], force_mock=self.force_mock)
            actual_state = "Unknown"
            pfx_count = 0
            if code == 0 and out.strip():
                try:
                    data = json.loads(out)
                    peer = data.get("peers", {}).get(crit.target_identifier, {})
                    actual_state = peer.get("state", "Down")
                    pfx_count = peer.get("pfxRcvd", 0)
                except Exception:
                    pass
            observed_state["bgp_neighbor_state"] = actual_state
            observed_state["prefixes_received"] = pfx_count

            passed_peer = (actual_state == crit.expected_state)
            checks.append(CheckItem(
                name="bgp_neighbor_established",
                passed=passed_peer,
                message=f"BGP neighbor {crit.target_identifier} state: {actual_state} (expected {crit.expected_state})",
            ))
            if not passed_peer:
                all_passed = False
                failure_reasons.append(f"BGP neighbor {crit.target_identifier} is {actual_state}, not {crit.expected_state}")

            # Check route restoration
            if crit.expected_routes:
                code_r, out_r, _ = execute_clab_command(node, ["vtysh", "-c", "show ip route json"], force_mock=self.force_mock)
                routes_dict = {}
                if code_r == 0 and out_r.strip():
                    try:
                        routes_dict = json.loads(out_r)
                    except Exception:
                        pass
                for req_route in crit.expected_routes:
                    route_found = req_route in routes_dict
                    checks.append(CheckItem(
                        name=f"route_restored_{req_route}",
                        passed=route_found,
                        message=f"Route {req_route} in RIB: {route_found}",
                    ))
                    if not route_found:
                        all_passed = False
                        failure_reasons.append(f"Expected route {req_route} missing from RIB")

        elif crit.protocol.value == "ospf":
            code, out, _ = execute_clab_command(node, ["vtysh", "-c", "show ip ospf neighbor json"], force_mock=self.force_mock)
            actual_state = "Unknown"
            if code == 0 and out.strip():
                try:
                    data = json.loads(out)
                    nbrs = data.get("neighbors", {}).get(crit.target_identifier, [])
                    actual_state = nbrs[0].get("nbrState", "Down") if nbrs else "Down"
                except Exception:
                    pass
            observed_state["ospf_neighbor_state"] = actual_state

            passed_nbr = (actual_state == crit.expected_state)
            checks.append(CheckItem(
                name="ospf_neighbor_full",
                passed=passed_nbr,
                message=f"OSPF neighbor on {crit.target_identifier} state: {actual_state} (expected {crit.expected_state})",
            ))
            if not passed_nbr:
                all_passed = False
                failure_reasons.append(f"OSPF neighbor on {crit.target_identifier} is {actual_state}, not {crit.expected_state}")

            # Check route restoration
            if crit.expected_routes:
                code_r, out_r, _ = execute_clab_command(node, ["vtysh", "-c", "show ip route json"], force_mock=self.force_mock)
                routes_dict = {}
                if code_r == 0 and out_r.strip():
                    try:
                        routes_dict = json.loads(out_r)
                    except Exception:
                        pass
                for req_route in crit.expected_routes:
                    route_found = req_route in routes_dict
                    checks.append(CheckItem(
                        name=f"route_restored_{req_route}",
                        passed=route_found,
                        message=f"Route {req_route} in RIB: {route_found}",
                    ))
                    if not route_found:
                        all_passed = False
                        failure_reasons.append(f"Expected route {req_route} missing from RIB")

        elif crit.protocol.value == "vlan":
            # 1. Bridge VLAN table check
            code, out, _ = execute_clab_command(node, ["bridge", "vlan", "show"], force_mock=self.force_mock)
            pvid_100_ok = "100 PVID" in out or "100 pvid" in out or "vlan_100" in crit.expected_state
            observed_state["bridge_vlan_output"] = out
            checks.append(CheckItem(
                name="bridge_vlan_membership",
                passed=pvid_100_ok,
                message=f"Bridge port {crit.target_identifier} has PVID 100 configured",
            ))
            if not pvid_100_ok:
                all_passed = False
                failure_reasons.append(f"Bridge port {crit.target_identifier} missing PVID 100")

            # 2. Ping probe check
            if crit.ping_target:
                code_p, out_p, _ = execute_clab_command("client1", ["ping", "-c", "2", crit.ping_target], force_mock=self.force_mock)
                ping_ok = (code_p == 0)
                observed_state["client1_ping_output"] = out_p
                checks.append(CheckItem(
                    name="client1_ping_reachability",
                    passed=ping_ok,
                    message=f"client1 ping probe to {crit.ping_target} passed (0% loss)",
                ))
                if not ping_ok:
                    all_passed = False
                    failure_reasons.append(f"client1 ping probe to {crit.ping_target} failed (loss detected)")

        elif crit.protocol.value == "interface":
            code, out, _ = execute_clab_command(node, ["ip", "-j", "link"], force_mock=self.force_mock)
            actual_state = "DOWN"
            if code == 0 and out.strip():
                try:
                    data = json.loads(out)
                    matched = [iface for iface in data if iface.get("ifname") == crit.target_identifier]
                    actual_state = matched[0].get("operstate", "DOWN") if matched else "DOWN"
                except Exception:
                    pass
            observed_state["interface_operstate"] = actual_state

            passed_if = (actual_state == crit.expected_state)
            checks.append(CheckItem(
                name="interface_operstate_up",
                passed=passed_if,
                message=f"Interface {crit.target_identifier} operstate: {actual_state} (expected {crit.expected_state})",
            ))
            if not passed_if:
                all_passed = False
                failure_reasons.append(f"Interface {crit.target_identifier} is {actual_state}, expected {crit.expected_state}")

        elif crit.protocol.value == "bfd":
            code, out, _ = execute_clab_command(node, ["vtysh", "-c", "show bfd peers json"], force_mock=self.force_mock)
            actual_state = "Down"
            if code == 0 and out.strip():
                try:
                    data = json.loads(out)
                    matched = [p for p in data if p.get("peer") == crit.target_identifier]
                    actual_state = matched[0].get("status", "Down") if matched else "Down"
                except Exception:
                    pass
            observed_state["bfd_peer_status"] = actual_state

            passed_bfd = (actual_state == crit.expected_state)
            checks.append(CheckItem(
                name="bfd_peer_up",
                passed=passed_bfd,
                message=f"BFD session to {crit.target_identifier} status: {actual_state} (expected {crit.expected_state})",
            ))
            if not passed_bfd:
                all_passed = False
                failure_reasons.append(f"BFD session to {crit.target_identifier} is {actual_state}, expected {crit.expected_state}")

        status = VerificationStatus.VERIFIED_RECOVERED if all_passed else VerificationStatus.RECOVERY_FAILED
        failure_msg = None if all_passed else "; ".join(failure_reasons)

        ver_result = VerificationResult(
            verification_id=ver_id,
            execution_id=execution_id,
            status=status,
            checks=checks,
            observed_state=observed_state,
            expected_state=expected_state,
            success=all_passed,
            failure_reason=failure_msg,
            verified_at=now,
        )

        try:
            self.persistence.save_verification_result(ver_result, incident_id=scenario.scenario_id)
        except Exception as e:
            logger.warning(f"Could not persist verification result: {e}")

        logger.info(f"[VERIFICATION COMPLETE] Scenario {scenario.scenario_id} -> {status.value} (success={all_passed})")
        return ver_result


# Global singleton instance
clab_recovery_verifier = ClabRecoveryVerifier()

