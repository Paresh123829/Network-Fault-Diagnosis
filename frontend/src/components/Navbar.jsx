import React from "react";
import { Activity, ShieldAlert, Cpu, Network, Radio, CheckSquare, Terminal, FileText } from "lucide-react";

export function Navbar({ activeTab, setActiveTab, isConnected, killSwitchActive }) {
  const navItems = [
    { id: "overview", label: "Overview", icon: Activity },
    { id: "incidents", label: "Incidents", icon: ShieldAlert },
    { id: "topology", label: "Topology", icon: Network },
    { id: "stream", label: "Live Stream", icon: Radio },
    { id: "remediation", label: "Remediation Gate", icon: CheckSquare },
    { id: "executions", label: "Execution Monitor", icon: Terminal },
    { id: "audit", label: "Kill Switch & Audit", icon: FileText },
  ];

  return (
    <header style={{ backgroundColor: "#0f172a", borderBottom: "1px solid #334155", position: "sticky", top: 0, zIndex: 50 }}>
      <div style={{ maxWidth: "1600px", margin: "0 auto", padding: "0 1.5rem", display: "flex", alignItems: "center", justifyContent: "space-between", height: "4.25rem" }}>
        
        {/* Brand / Logo */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", cursor: "pointer" }} onClick={() => setActiveTab("overview")}>
          <div style={{ width: "2.5rem", height: "2.5rem", borderRadius: "0.5rem", background: "linear-gradient(135deg, #3b82f6, #06b6d4)", display: "flex", alignItems: "center", justifyContent: "justify", padding: "0.5rem" }}>
            <Cpu style={{ width: "100%", height: "100%", color: "#ffffff" }} />
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: "1.05rem", letterSpacing: "-0.025em", color: "#f8fafc" }}>
              CNT Autonomous Network Engine
            </div>
            <div style={{ fontSize: "0.75rem", color: "#94a3b8", display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <span>Multi-Agent Fault Diagnosis & Safe Remediation</span>
              <span style={{ backgroundColor: "#1e293b", padding: "0.1rem 0.4rem", borderRadius: "0.25rem", color: "#38bdf8", fontSize: "0.65rem", fontWeight: 600 }}>v0.8.0</span>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.5rem",
                  padding: "0.5rem 0.85rem",
                  borderRadius: "0.375rem",
                  fontSize: "0.85rem",
                  fontWeight: isActive ? 600 : 500,
                  color: isActive ? "#ffffff" : "#94a3b8",
                  backgroundColor: isActive ? "#2563eb" : "transparent",
                  border: "none",
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                }}
              >
                <Icon style={{ width: "1rem", height: "1rem" }} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        {/* Status Indicators */}
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          {/* Real-time streaming badge */}
          <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", padding: "0.35rem 0.75rem", borderRadius: "9999px", backgroundColor: isConnected ? "rgba(16, 185, 129, 0.15)" : "rgba(239, 68, 68, 0.15)", border: `1px solid ${isConnected ? "rgba(16, 185, 129, 0.4)" : "rgba(239, 68, 68, 0.4)"}` }}>
            <span style={{ width: "0.5rem", height: "0.5rem", borderRadius: "9999px", backgroundColor: isConnected ? "#10b981" : "#ef4444" }}></span>
            <span style={{ fontSize: "0.75rem", fontWeight: 600, color: isConnected ? "#34d399" : "#f87171" }}>
              {isConnected ? "STREAM ACTIVE" : "OFFLINE"}
            </span>
          </div>

          {/* Kill Switch Banner Pill */}
          {killSwitchActive && (
            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", padding: "0.35rem 0.75rem", borderRadius: "0.375rem", backgroundColor: "#ef4444", color: "#ffffff", fontSize: "0.75rem", fontWeight: 700, animation: "pulse 2s infinite" }}>
              <ShieldAlert style={{ width: "0.9rem", height: "0.9rem" }} />
              KILL SWITCH ACTIVE
            </div>
          )}
        </div>

      </div>
    </header>
  );
}

