import React, { useEffect, useState } from "react";
import { ShieldAlert, ShieldCheck, Key, RefreshCw, CheckCircle2, AlertOctagon } from "lucide-react";
import { api } from "../api/client";

export function KillSwitchAuditPage({ killSwitchActive, onToggleKillSwitch }) {
  const [auditRecords, setAuditRecords] = useState([]);
  const [verification, setVerification] = useState(null);
  const [isVerifying, setIsVerifying] = useState(false);
  const [loading, setLoading] = useState(true);
  const [operatorId, setOperatorId] = useState("sec_lead");
  const [reason, setReason] = useState("Manual fail-closed safety trigger");

  const loadData = async () => {
    try {
      const [records, verif] = await Promise.all([
        api.getAuditRecords(),
        api.getAuditVerification(),
      ]);
      setAuditRecords(records);
      setVerification(verif);
    } catch (err) {
      console.error("Error loading audit data:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleVerifyChain = async () => {
    setIsVerifying(true);
    try {
      const res = await api.getAuditVerification();
      setVerification(res);
    } catch (err) {
      alert("Verification failed: " + err.message);
    } finally {
      setIsVerifying(false);
    }
  };

  const handleKillSwitchAction = async () => {
    const actionName = killSwitchActive ? "DEACTIVATE" : "ACTIVATE";
    if (!confirm(`Are you sure you want to ${actionName} the Global Remediation Kill Switch?`)) {
      return;
    }
    try {
      await onToggleKillSwitch(killSwitchActive, { operator_id: operatorId, reason });
      await loadData();
    } catch (err) {
      alert("Kill switch toggle error: " + err.message);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      
      {/* Header */}
      <div>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700, margin: 0, color: "#f8fafc" }}>
          Emergency Kill Switch & Cryptographic Audit Trail
        </h1>
        <p style={{ fontSize: "0.85rem", color: "#94a3b8", margin: "0.25rem 0 0" }}>
          Fail-Closed Safety Controller & SHA-256 Tamper-Evident Hash-Chained Audit Ledger
        </p>
      </div>

      {/* Kill Switch Card */}
      <div style={{ backgroundColor: killSwitchActive ? "rgba(239, 68, 68, 0.12)" : "#111827", border: `1px solid ${killSwitchActive ? "#ef4444" : "#334155"}`, borderRadius: "0.5rem", padding: "1.5rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "1rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <div style={{ width: "2.5rem", height: "2.5rem", borderRadius: "0.5rem", backgroundColor: killSwitchActive ? "rgba(239, 68, 68, 0.2)" : "rgba(16, 185, 129, 0.15)", border: `1px solid ${killSwitchActive ? "#ef4444" : "#10b981"}`, display: "flex", alignItems: "center", justifyContent: "center", color: killSwitchActive ? "#ef4444" : "#10b981" }}>
              {killSwitchActive ? <AlertOctagon style={{ width: "1.5rem", height: "1.5rem" }} /> : <ShieldCheck style={{ width: "1.5rem", height: "1.5rem" }} />}
            </div>
            <div>
              <div style={{ fontSize: "1.1rem", fontWeight: 700, color: killSwitchActive ? "#f87171" : "#f8fafc" }}>
                Global Remediation Kill Switch: {killSwitchActive ? "ACTIVE (HALTED)" : "DISARMED (FAIL-CLOSED READY)"}
              </div>
              <div style={{ fontSize: "0.8rem", color: "#94a3b8" }}>
                {killSwitchActive
                  ? "All automated and manual remediation actions, executions, and rollbacks are FROZEN."
                  : "Normal policy evaluation and operator authorization gates active."}
              </div>
            </div>
          </div>

          <button
            onClick={handleKillSwitchAction}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              padding: "0.7rem 1.5rem",
              backgroundColor: killSwitchActive ? "#10b981" : "#dc2626",
              color: "#ffffff",
              border: "none",
              borderRadius: "0.375rem",
              fontSize: "0.9rem",
              fontWeight: 700,
              cursor: "pointer",
              boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.3)",
            }}
          >
            {killSwitchActive ? "DEACTIVATE KILL SWITCH" : "ACTIVATE EMERGENCY KILL SWITCH"}
          </button>
        </div>

        {/* Inputs */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: "0.75rem", paddingTop: "0.5rem", borderTop: "1px solid #1e293b" }}>
          <div>
            <label style={{ display: "block", fontSize: "0.75rem", color: "#94a3b8", fontWeight: 600, marginBottom: "0.2rem" }}>
              Authorizing Operator
            </label>
            <input
              type="text"
              value={operatorId}
              onChange={(e) => setOperatorId(e.target.value)}
              style={{ width: "100%", padding: "0.45rem 0.6rem", backgroundColor: "#0f172a", border: "1px solid #334155", borderRadius: "0.25rem", color: "#f8fafc", fontSize: "0.8rem", boxSizing: "border-box" }}
            />
          </div>
          <div>
            <label style={{ display: "block", fontSize: "0.75rem", color: "#94a3b8", fontWeight: 600, marginBottom: "0.2rem" }}>
              Kill Switch Reason / Trigger Note
            </label>
            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              style={{ width: "100%", padding: "0.45rem 0.6rem", backgroundColor: "#0f172a", border: "1px solid #334155", borderRadius: "0.25rem", color: "#f8fafc", fontSize: "0.8rem", boxSizing: "border-box" }}
            />
          </div>
        </div>

      </div>

      {/* Audit Chain Verification Status */}
      {verification && (
        <div style={{ backgroundColor: "#1e293b", border: "1px solid #334155", borderRadius: "0.5rem", padding: "1.25rem", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "1rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <div style={{ width: "2.25rem", height: "2.25rem", borderRadius: "0.375rem", backgroundColor: verification.is_valid ? "rgba(16, 185, 129, 0.15)" : "rgba(239, 68, 68, 0.15)", border: `1px solid ${verification.is_valid ? "#10b981" : "#ef4444"}`, display: "flex", alignItems: "center", justifyContent: "center", color: verification.is_valid ? "#10b981" : "#ef4444" }}>
              <Key style={{ width: "1.2rem", height: "1.2rem" }} />
            </div>
            <div>
              <div style={{ fontSize: "1rem", fontWeight: 700, color: verification.is_valid ? "#34d399" : "#fb7185" }}>
                Audit Chain Status: {verification.is_valid ? "CRYPTOGRAPHICALLY VALID" : "TAMPERING DETECTED"}
              </div>
              <div style={{ fontSize: "0.8rem", color: "#94a3b8" }}>
                Genesis Verified: {verification.genesis_verified ? "True" : "False"} | Records Traversed: <strong>{verification.total_records}</strong> | Violations: <strong>{verification.detected_violations?.length || 0}</strong>
              </div>
            </div>
          </div>

          <button
            onClick={handleVerifyChain}
            disabled={isVerifying}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.4rem",
              padding: "0.5rem 1rem",
              backgroundColor: "#2563eb",
              color: "#ffffff",
              border: "none",
              borderRadius: "0.375rem",
              fontSize: "0.85rem",
              fontWeight: 600,
              cursor: isVerifying ? "not-allowed" : "pointer",
            }}
          >
            <RefreshCw style={{ width: "0.85rem", height: "0.85rem" }} className={isVerifying ? "animate-spin" : ""} />
            {isVerifying ? "Verifying..." : "Verify Hash Chain Integrity"}
          </button>
        </div>
      )}

      {/* Audit Chain Table */}
      <div style={{ backgroundColor: "#111827", border: "1px solid #334155", borderRadius: "0.5rem", overflow: "hidden" }}>
        <div style={{ padding: "0.85rem 1.25rem", borderBottom: "1px solid #334155", fontWeight: 600, fontSize: "0.95rem", color: "#f8fafc" }}>
          Immutable Audit Records (Sequence 0 to {auditRecords.length - 1})
        </div>

        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "0.8rem" }}>
            <thead>
              <tr style={{ backgroundColor: "#0f172a", borderBottom: "1px solid #334155", color: "#94a3b8" }}>
                <th style={{ padding: "0.6rem 0.75rem", fontWeight: 600 }}>Seq #</th>
                <th style={{ padding: "0.6rem 0.75rem", fontWeight: 600 }}>Action</th>
                <th style={{ padding: "0.6rem 0.75rem", fontWeight: 600 }}>Operator</th>
                <th style={{ padding: "0.6rem 0.75rem", fontWeight: 600 }}>Entity</th>
                <th style={{ padding: "0.6rem 0.75rem", fontWeight: 600 }}>Record Hash (SHA-256)</th>
                <th style={{ padding: "0.6rem 0.75rem", fontWeight: 600 }}>Previous Hash Pointer</th>
              </tr>
            </thead>
            <tbody>
              {auditRecords.map((r) => (
                <tr key={r.record_id} style={{ borderBottom: "1px solid #1e293b" }}>
                  <td style={{ padding: "0.6rem 0.75rem", fontFamily: "monospace", fontWeight: 700, color: "#38bdf8" }}>
                    #{r.sequence_number}
                  </td>
                  <td style={{ padding: "0.6rem 0.75rem", fontWeight: 600, color: "#f8fafc" }}>
                    {r.action}
                  </td>
                  <td style={{ padding: "0.6rem 0.75rem", color: "#cbd5e1" }}>
                    {r.operator_id}
                  </td>
                  <td style={{ padding: "0.6rem 0.75rem", color: "#94a3b8" }}>
                    {r.entity_type}: <strong style={{ color: "#cbd5e1" }}>{r.entity_id}</strong>
                  </td>
                  <td style={{ padding: "0.6rem 0.75rem", fontFamily: "monospace", color: "#a5f3fc", fontSize: "0.75rem" }}>
                    {r.record_hash?.slice(0, 16)}...
                  </td>
                  <td style={{ padding: "0.6rem 0.75rem", fontFamily: "monospace", color: "#64748b", fontSize: "0.75rem" }}>
                    {r.previous_hash?.slice(0, 16)}...
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

    </div>
  );
}

