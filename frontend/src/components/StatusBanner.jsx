import React from "react";
import { Server, ShieldAlert, Database, Info } from "lucide-react";

export function StatusBanner({ systemStatus, killSwitchActive }) {
  const isMock = systemStatus?.mock_provider ?? true;
  const providerName = systemStatus?.provider_name || "ContainerlabMockProvider";

  return (
    <div style={{ backgroundColor: "#1e293b", borderBottom: "1px solid #334155", padding: "0.5rem 1.5rem" }}>
      <div style={{ maxWidth: "1600px", margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.75rem", fontSize: "0.8rem" }}>
        
        {/* Provider Mode Banner */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.35rem", padding: "0.2rem 0.5rem", borderRadius: "0.25rem", backgroundColor: isMock ? "rgba(245, 158, 11, 0.15)" : "rgba(16, 185, 129, 0.15)", border: `1px solid ${isMock ? "rgba(245, 158, 11, 0.4)" : "rgba(16, 185, 129, 0.4)"}`, color: isMock ? "#fbbf24" : "#34d399", fontWeight: 600 }}>
            <Server style={{ width: "0.85rem", height: "0.85rem" }} />
            <span>MODE: {isMock ? "HIGH-FIDELITY SIMULATION" : "LIVE CONTAINERLAB"}</span>
          </div>
          <span style={{ color: "#94a3b8" }}>
            Network Provider: <strong style={{ color: "#f1f5f9" }}>{providerName}</strong>
          </span>
        </div>

        {/* Component Health & Invariants */}
        <div style={{ display: "flex", alignItems: "center", gap: "1.25rem", color: "#94a3b8" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
            <span style={{ width: "0.45rem", height: "0.45rem", borderRadius: "50%", backgroundColor: systemStatus?.qdrant_connected ? "#10b981" : "#38bdf8" }}></span>
            <span>Qdrant RAG: <strong style={{ color: "#cbd5e1" }}>Memory/Hybrid</strong></span>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
            <span style={{ width: "0.45rem", height: "0.45rem", borderRadius: "50%", backgroundColor: systemStatus?.active_incidents_count > 0 ? "#f43f5e" : "#10b981" }}></span>
            <span>Active Incidents: <strong style={{ color: systemStatus?.active_incidents_count > 0 ? "#fb7185" : "#cbd5e1" }}>{systemStatus?.active_incidents_count ?? 0}</strong></span>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
            <span style={{ width: "0.45rem", height: "0.45rem", borderRadius: "50%", backgroundColor: killSwitchActive ? "#ef4444" : "#10b981" }}></span>
            <span>Remediation Gate: <strong style={{ color: killSwitchActive ? "#ef4444" : "#34d399" }}>{killSwitchActive ? "LOCKED (FROZEN)" : "FAIL-CLOSED (READY)"}</strong></span>
          </div>
        </div>

      </div>
    </div>
  );
}

