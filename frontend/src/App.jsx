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
      setIncidents((prev) => [payload, ...prev]);
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
      const prop = await api.getProposal(proposalId);
      setActiveModalProposal(prop);
    } catch (err) {
      console.error("Failed to fetch proposal:", err);
    }
  };

  const handleApproveProposal = async (proposalId, data) => {
    const updated = await api.approveProposal(proposalId, data);
    setProposals((prev) => prev.map((p) => (p.proposal_id === proposalId ? updated : p)));
    await loadInitialData();
  };

  const handleRejectProposal = async (proposalId, data) => {
    const updated = await api.rejectProposal(proposalId, data);
    setProposals((prev) => prev.map((p) => (p.proposal_id === proposalId ? updated : p)));
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

  const handleTriggerFault = async (data) => {
    const newInc = await api.triggerIncident(data);
    setIncidents((prev) => [newInc, ...prev]);
    setSelectedIncidentId(newInc.incident_id);
    setActiveTab("incident_detail");
  };

  return (
    <div style={{ minHeight: "100vh", backgroundColor: "#0a0f1d", color: "#f8fafc", display: "flex", flexDirection: "column" }}>
      {/* Navbar */}
      <Navbar
        activeTab={activeTab === "incident_detail" ? "incidents" : activeTab}
        setActiveTab={setActiveTab}
        isConnected={isConnected}
        killSwitchActive={killSwitchActive}
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
            onTriggerFault={handleTriggerFault}
          />
        )}

        {activeTab === "incidents" && (
          <IncidentsPage incidents={incidents} onSelectIncident={handleSelectIncident} />
        )}

        {activeTab === "incident_detail" && (
          <IncidentDetailPage
            incidentId={selectedIncidentId}
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

