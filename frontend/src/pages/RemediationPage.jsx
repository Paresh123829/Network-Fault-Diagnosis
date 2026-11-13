import React, { useState } from "react";
import { CheckSquare, ShieldCheck, Terminal, AlertTriangle, Key } from "lucide-react";

export function RemediationPage({ proposals, onOpenApprovalModal, killSwitchActive }) {
  const [statusFilter, setStatusFilter] = useState("ALL");

  const filtered = proposals.filter((p) => {
    if (statusFilter === "ALL") return true;
    return p.status.toUpperCase() === statusFilter.toUpperCase();
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, margin: 0, color: "#f8fafc" }}>
            Remediation Approval Gate ({filtered.length})
          </h1>
          <p style={{ fontSize: "0.85rem", color: "#94a3b8", margin: "0.25rem 0 0" }}>
            Deterministic Allow-List Proposals with Cryptographic SHA-256 Hash Binding
          </p>
        </div>

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          style={{
            padding: "0.45rem 0.75rem",
            backgroundColor: "#1e293b",
            border: "1px solid #334155",
            borderRadius: "0.375rem",
            color: "#f8fafc",
            fontSize: "0.85rem",
          }}
        >
          <option value="ALL">All Statuses</option>
          <option value="PENDING_APPROVAL">Pending Approval</option>
          <option value="VERIFIED">Verified Executed</option>
          <option value="APPROVED">Approved</option>
          <option value="REJECTED">Rejected</option>
        </select>
      </div>

      {/* Proposals Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(380px, 1fr))", gap: "1.25rem" }}>
        {filtered.map((prop) => {
          const isPending = prop.status === "PENDING_APPROVAL";
          const riskColor = prop.risk_level === "LOW" ? "#10b981" : (prop.risk_level === "MEDIUM" ? "#f59e0b" : "#ef4444");

          return (
            <div
              key={prop.proposal_id}
              style={{
                backgroundColor: "#111827",
                border: "1px solid #334155",
                borderRadius: "0.5rem",
                padding: "1.25rem",
                display: "flex",
                flexDirection: "column",
                gap: "1rem",
              }}
            >
              {/* Card Header */}
              <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                    <span style={{ fontFamily: "monospace", fontSize: "0.85rem", fontWeight: 700, color: "#38bdf8" }}>
                      {prop.proposal_id}
                    </span>
                    <span style={{ fontSize: "0.7rem", padding: "0.15rem 0.4rem", borderRadius: "0.25rem", fontWeight: 700, backgroundColor: `${riskColor}22`, color: riskColor }}>
                      {prop.risk_level}
                    </span>
                  </div>
                  <div style={{ fontSize: "1.05rem", fontWeight: 700, color: "#f8fafc", marginTop: "0.25rem" }}>
                    {prop.operation}
                  </div>
                  <div style={{ fontSize: "0.75rem", color: "#94a3b8", marginTop: "0.15rem" }}>
                    Target: <strong style={{ color: "#f1f5f9" }}>{prop.target_node}</strong> {prop.target_component ? `(${prop.target_component})` : ""}
                  </div>
                </div>

                <div style={{ textAlign: "right" }}>
                  <span style={{ fontSize: "0.75rem", padding: "0.2rem 0.5rem", borderRadius: "0.25rem", fontWeight: 600, backgroundColor: isPending ? "rgba(245, 158, 11, 0.15)" : "rgba(16, 185, 129, 0.15)", color: isPending ? "#fbbf24" : "#34d399" }}>
                    {prop.status}
                  </span>
                  <div style={{ fontSize: "0.7rem", color: "#64748b", marginTop: "0.25rem" }}>
                    Safety: {((prop.safety_score || 0.95) * 100).toFixed(0)}%
                  </div>
                </div>
              </div>

              {/* Exact Actions List */}
              <div style={{ backgroundColor: "#020617", border: "1px solid #1e293b", borderRadius: "0.375rem", padding: "0.75rem", display: "flex", flexDirection: "column", gap: "0.35rem" }}>
                <div style={{ fontSize: "0.7rem", color: "#64748b", textTransform: "uppercase", fontWeight: 600, marginBottom: "0.2rem" }}>
                  Planned Execution Commands:
                </div>
                {prop.actions && prop.actions.length > 0 ? (
                  prop.actions.map((act, idx) => (
                    <div key={idx} style={{ fontSize: "0.75rem", fontFamily: "monospace", color: "#a5f3fc" }}>
                      <span style={{ color: "#64748b" }}>[{act.phase}]</span> {act.command}
                    </div>
                  ))
                ) : (
                  <div style={{ fontSize: "0.75rem", fontFamily: "monospace", color: "#a5f3fc" }}>
                    {prop.operation}
                  </div>
                )}
              </div>

              {/* Cryptographic Hash Snippet */}
              <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.7rem", color: "#94a3b8", fontFamily: "monospace", backgroundColor: "#0f172a", padding: "0.4rem 0.6rem", borderRadius: "0.25rem" }}>
                <Key style={{ width: "0.75rem", height: "0.75rem", color: "#fbbf24", flexShrink: 0 }} />
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {prop.proposal_hash}
                </span>
              </div>

              {/* Action Button */}
              {isPending && (
                <button
                  onClick={() => onOpenApprovalModal(prop)}
                  disabled={killSwitchActive}
                  style={{
                    width: "100%",
                    padding: "0.6rem",
                    backgroundColor: killSwitchActive ? "#475569" : "#2563eb",
                    color: "#ffffff",
                    border: "none",
                    borderRadius: "0.375rem",
                    fontSize: "0.85rem",
                    fontWeight: 700,
                    cursor: killSwitchActive ? "not-allowed" : "pointer",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "0.4rem",
                    marginTop: "auto",
                  }}
                >
                  <ShieldCheck style={{ width: "1rem", height: "1rem" }} />
                  {killSwitchActive ? "Execution Frozen (Kill Switch Active)" : "Review & Authorize Action"}
                </button>
              )}
            </div>
          );
        })}
      </div>

    </div>
  );
}

