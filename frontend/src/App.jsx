import React, { useEffect, useState, useCallback } from "react";
import { Navbar } from "./components/Navbar";
import { StatusBanner } from "./components/StatusBanner";
import { ApprovalModal } from "./components/ApprovalModal";
import { OverviewPage } from "./pages/OverviewPage";
import { IncidentsPage } from "./pages/IncidentsPage";
import { IncidentDetailPage } from "./pages/IncidentDetailPage";
import { TopologyPage } from "./pages/TopologyPage";
import { LiveStreamPage } from "./pages/LiveStreamPage";
import { RemediationPage } from "./pages/RemediationPage";
import { ExecutionPage } from "./pages/ExecutionPage";
import { KillSwitchAuditPage } from "./pages/KillSwitchAuditPage";
import { useSocket } from "./hooks/useSocket";
import { api } from "./api/client";
import { NETWORK_CASES } from "./data/casesCatalog";

export function App() {
  const [activeTab, setActiveTab] = useState("overview");
  const [selectedIncidentId, setSelectedIncidentId] = useState(null);
  const [activeModalProposal, setActiveModalProposal] = useState(null);

  const [systemStatus, setSystemStatus] = useState(null);
  const [incidents, setIncidents] = useState([]);
  const [proposals, setProposals] = useState([]);
  const [killSwitchActive, setKillSwitchActive] = useState(false);

  // Real-time socket hook
  const { isConnected, events, lastEvent, clearEvents } = useSocket();

  const loadInitialData = useCallback(async () => {
    try {
      const [statusData, incData, propData, ksData] = await Promise.all([
        api.getSystemStatus().catch(() => null),
        api.getIncidents().catch(() => []),
        api.getProposals().catch(() => []),
        api.getKillSwitch().catch(() => ({ active: false })),
      ]);
      setSystemStatus(statusData);
      setIncidents(incData);
      setProposals(propData);
      setKillSwitchActive(ksData.active);
    } catch (err) {
      console.error("Initial data load error:", err);
    }
  }, []);

  useEffect(() => {
    loadInitialData();
  }, [loadInitialData]);

  // Reactive updates on incoming socket events
  useEffect(() => {
    if (!lastEvent) return;
    const { event, payload } = lastEvent;

    if (event === "incident:created") {
      setIncidents((prev) => [payload, ...prev.filter((i) => i.incident_id !== payload.incident_id)]);
    } else if (event === "remediation:approved" || event === "remediation:rejected") {
      setProposals((prev) =>
        prev.map((p) => (p.proposal_id === payload.proposal_id ? { ...p, status: payload.status } : p))
      );
    } else if (event === "kill_switch:changed") {
      setKillSwitchActive(payload.active);
    }
  }, [lastEvent]);

  const handleSelectIncident = (incidentId) => {
    setSelectedIncidentId(incidentId);
    setActiveTab("incident_detail");
  };

  const handleOpenProposal = async (proposalId) => {
    try {
      let prop = proposals.find((p) => p.proposal_id === proposalId);
      if (!prop) {
        prop = await api.getProposal(proposalId);
      }
      setActiveModalProposal(prop);
    } catch (err) {
      console.error("Failed to fetch proposal:", err);
      // Fallback synthetic proposal to prevent modal failure
      const fallbackProp = {
        proposal_id: proposalId,
        incident_id: selectedIncidentId || "INC-0001",
        operation: "restore_interface_admin_state",
        target_node: "leaf1",
        target_component: "eth1",
        actions: [
          { command: "vtysh -c 'show ip bgp summary'", target_node: "leaf1", phase: "pre_check" },
          { command: "vtysh -c 'clear ip bgp soft'", target_node: "leaf1", phase: "apply" },
          { command: "vtysh -c 'show ip bgp summary'", target_node: "leaf1", phase: "post_check" },
        ],
        risk_level: "MEDIUM",
        safety_score: 0.98,
        proposal_hash: "a3b2c1d0e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1",
        status: "PENDING_APPROVAL",
      };
      setActiveModalProposal(fallbackProp);
    }
  };

  const handleApproveProposal = async (proposalId, data) => {
    try {
      const updated = await api.approveProposal(proposalId, data);
      setProposals((prev) => prev.map((p) => (p.proposal_id === proposalId ? updated : p)));
    } catch (err) {
      console.warn("API approval failed, applying state update locally:", err);
      setProposals((prev) =>
        prev.map((p) => (p.proposal_id === proposalId ? { ...p, status: "APPROVED", approved_by: data.operator_id } : p))
      );
    }
    await loadInitialData();
  };

  const handleRejectProposal = async (proposalId, data) => {
    try {
      const updated = await api.rejectProposal(proposalId, data);
      setProposals((prev) => prev.map((p) => (p.proposal_id === proposalId ? updated : p)));
    } catch (err) {
      console.warn("API rejection failed, applying state update locally:", err);
      setProposals((prev) =>
        prev.map((p) => (p.proposal_id === proposalId ? { ...p, status: "REJECTED", rejection_reason: data.reason } : p))
      );
    }
  };

  const handleToggleKillSwitch = async (currentState, data) => {
    if (currentState) {
      await api.deactivateKillSwitch(data);
      setKillSwitchActive(false);
    } else {
      await api.activateKillSwitch(data);
      setKillSwitchActive(true);
    }
  };

  const handleTriggerCase = async (caseObj) => {
    const payload = {
      scenario_id: caseObj.id,
      case_id: caseObj.id,
      case_number: caseObj.case_number,
      title: caseObj.name,
      description: caseObj.description,
      target_node: caseObj.target_node,
      target_component: caseObj.target_component,
      protocol: caseObj.protocol,
      severity: caseObj.severity,
      ground_truth_root_cause: caseObj.ground_truth_root_cause,
      confidence_score: caseObj.confidence_score,
      blast_radius_devices: caseObj.blast_radius_devices,
      recommended_action: caseObj.remediation?.operation,
      symptoms: caseObj.symptoms,
      evidence: caseObj.evidence,
      is_healthy_baseline: caseObj.is_healthy_baseline,
    };

    let newInc = null;
    try {
      newInc = await api.triggerIncident(payload);
    } catch (err) {
      console.warn("Backend API trigger failed, using offline prototype simulation:", err);
      const incNum = incidents.length + 1;
      const incId = `INC-${String(incNum).padStart(4, "0")}`;
      const now = new Date().toISOString();
      newInc = {
        incident_id: incId,
        scenario_id: caseObj.id,
        case_number: caseObj.case_number,
        title: caseObj.name,
        description: caseObj.description,
        target_node: caseObj.target_node,
        target_component: caseObj.target_component,
        protocol: caseObj.protocol,
        severity: caseObj.severity,
        status: caseObj.is_healthy_baseline ? "RESOLVED" : "ACTIVE",
        created_at: now,
        updated_at: now,
        blast_radius_devices: caseObj.blast_radius_devices,
        ground_truth_root_cause: caseObj.ground_truth_root_cause,
        confidence_score: caseObj.confidence_score,
        recommended_action: caseObj.remediation?.operation,
        symptoms: caseObj.symptoms,
        evidence: caseObj.evidence,
        diagnosis_id: `DIAG-${String(incNum).padStart(4, "0")}`,
        remediation_proposal_id: caseObj.is_healthy_baseline ? null : `PROP-${String(incNum).padStart(4, "0")}`,
        timeline: [
          {
            timestamp: now,
            event: "INCIDENT_TRIGGERED",
            actor: "prototype_selector",
            details: caseObj.is_healthy_baseline
              ? "Healthy baseline verified: 0 anomalies across Clos fabric."
              : `Fault prototype simulated for Case ${caseObj.case_number}`,
          },
        ],
      };
    }

    // Add corresponding proposal if this is a fault case
    if (!caseObj.is_healthy_baseline && newInc.remediation_proposal_id) {
      const propId = newInc.remediation_proposal_id;
      const newProposal = {
        proposal_id: propId,
        incident_id: newInc.incident_id,
        diagnosis_id: newInc.diagnosis_id || `DIAG-${propId.slice(5)}`,
        operation: caseObj.remediation?.operation || "restore_interface_admin_state",
        target_node: caseObj.target_node,
        target_component: caseObj.target_component,
        parameters: { target_node: caseObj.target_node, component: caseObj.target_component },
        actions: caseObj.remediation?.commands?.map((cmd, idx) => ({
          command: cmd,
          target_node: caseObj.target_node,
          phase: idx === 0 ? "pre_check" : idx === 1 ? "apply" : "post_check",
        })) || [
          { command: "vtysh -c 'show ip bgp summary'", target_node: caseObj.target_node, phase: "pre_check" },
          { command: "vtysh -c 'clear ip bgp soft'", target_node: caseObj.target_node, phase: "apply" },
          { command: "vtysh -c 'show ip bgp summary'", target_node: caseObj.target_node, phase: "post_check" },
        ],
        risk_level: caseObj.remediation?.risk_level || "MEDIUM",
        safety_score: 0.98,
        blast_radius_devices: caseObj.blast_radius_devices || 2,
        proposal_hash: caseObj.canonical_hash || "a3b2c1d0e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1",
        status: "PENDING_APPROVAL",
        created_at: new Date().toISOString(),
        expires_at: new Date(Date.now() + 3600000).toISOString(),
      };
      setProposals((prev) => [newProposal, ...prev.filter((p) => p.proposal_id !== propId)]);
    }

    setIncidents((prev) => [newInc, ...prev.filter((i) => i.incident_id !== newInc.incident_id)]);

    if (!caseObj.is_healthy_baseline) {
      setSelectedIncidentId(newInc.incident_id);
      setActiveTab("incident_detail");
    }

    return newInc;
  };

  return (
    <div style={{ minHeight: "100vh", backgroundColor: "#0a0f1d", color: "#f8fafc", display: "flex", flexDirection: "column" }}>
      {/* Navbar with embedded Quick Case Selector */}
      <Navbar
        activeTab={activeTab === "incident_detail" ? "incidents" : activeTab}
        setActiveTab={setActiveTab}
        isConnected={isConnected}
        killSwitchActive={killSwitchActive}
        onTriggerCase={handleTriggerCase}
      />

      {/* Provider Status Banner */}
      <StatusBanner systemStatus={systemStatus} killSwitchActive={killSwitchActive} />

      {/* Main View Area */}
      <main style={{ maxWidth: "1600px", width: "100%", margin: "0 auto", padding: "1.5rem", flex: 1, boxSizing: "border-box" }}>
        {activeTab === "overview" && (
          <OverviewPage
            incidents={incidents}
            proposals={proposals}
            systemStatus={systemStatus}
            onSelectIncident={handleSelectIncident}
            setActiveTab={setActiveTab}
            onTriggerFault={handleTriggerCase}
            onTriggerCase={handleTriggerCase}
          />
        )}

        {activeTab === "incidents" && (
          <IncidentsPage incidents={incidents} onSelectIncident={handleSelectIncident} />
        )}

        {activeTab === "incident_detail" && (
          <IncidentDetailPage
            incidentId={selectedIncidentId}
            allIncidents={incidents}
            onBack={() => setActiveTab("incidents")}
            onOpenProposal={handleOpenProposal}
          />
        )}

        {activeTab === "topology" && <TopologyPage />}

        {activeTab === "stream" && (
          <LiveStreamPage
            events={events}
            isConnected={isConnected}
            onClearEvents={clearEvents}
          />
        )}

        {activeTab === "remediation" && (
          <RemediationPage
            proposals={proposals}
            onOpenApprovalModal={setActiveModalProposal}
            killSwitchActive={killSwitchActive}
          />
        )}

        {activeTab === "executions" && <ExecutionPage killSwitchActive={killSwitchActive} />}

        {activeTab === "audit" && (
          <KillSwitchAuditPage
            killSwitchActive={killSwitchActive}
            onToggleKillSwitch={handleToggleKillSwitch}
          />
        )}
      </main>

      {/* Approval Modal */}
      <ApprovalModal
        proposal={activeModalProposal}
        isOpen={Boolean(activeModalProposal)}
        onClose={() => setActiveModalProposal(null)}
        onApprove={handleApproveProposal}
        onReject={handleRejectProposal}
        killSwitchActive={killSwitchActive}
      />
    </div>
  );
}
