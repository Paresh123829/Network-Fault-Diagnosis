import React, { useState } from "react";
import { ShieldCheck, ShieldAlert, X, Terminal, CheckCircle2, AlertTriangle, Key } from "lucide-react";

export function ApprovalModal({ proposal, isOpen, onClose, onApprove, onReject, killSwitchActive }) {
  if (!isOpen || !proposal) return null;

  const [operatorId, setOperatorId] = useState("operator_lead");
  const [reason, setReason] = useState("Authorized automated remediation following root cause review");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const handleApprove = async () => {
    if (killSwitchActive) {
      setErrorMessage("Action rejected: Emergency Kill Switch is currently ACTIVE.");
      return;
    }
    if (!operatorId.trim()) {
      setErrorMessage("Operator ID is required for cryptographic sign-off.");
      return;
    }
    setIsSubmitting(true);
    setErrorMessage("");
    try {
      await onApprove(proposal.proposal_id, {
        operator_id: operatorId,
        proposal_hash: proposal.proposal_hash,
        reason,
      });
      onClose();
    } catch (err) {
      setErrorMessage(err.message || "Failed to approve proposal");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReject = async () => {
    if (!reason.trim()) {
      setErrorMessage("A rejection reason is required for the audit trail.");
      return;
    }
    setIsSubmitting(true);
    setErrorMessage("");
    try {
      await onReject(proposal.proposal_id, {
        operator_id: operatorId,
        reason,
      });
      onClose();
    } catch (err) {
      setErrorMessage(err.message || "Failed to reject proposal");
    } finally {
      setIsSubmitting(false);
    }
  };

  const riskColor = proposal.risk_level === "LOW" ? "#10b981" : proposal.risk_level === "MEDIUM" ? "#f59e0b" : "#ef4444";

  return (
    <div style={{ position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.75)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100, padding: "1rem" }}>
      <div style={{ backgroundColor: "#0f172a", border: "1px solid #334155", borderRadius: "0.75rem", maxWidth: "42rem", width: "100%", maxHeight: "90vh", overflowY: "auto", boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.5)" }}>
        
        {/* Header */}
        <div style={{ padding: "1.25rem 1.5rem", borderBottom: "1px solid #334155", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <div style={{ width: "2.25rem", height: "2.25rem", borderRadius: "0.375rem", backgroundColor: "rgba(59, 130, 246, 0.15)", border: "1px solid rgba(59, 130, 246, 0.4)", display: "flex", alignItems: "center", justifyContent: "center", color: "#38bdf8" }}>
              <ShieldCheck style={{ width: "1.25rem", height: "1.25rem" }} />
            </div>
            <div>
              <h2 style={{ fontSize: "1.1rem", fontWeight: 700, margin: 0, color: "#f8fafc" }}>Remediation Approval Gate</h2>
              <p style={{ fontSize: "0.8rem", color: "#94a3b8", margin: 0 }}>Cryptographically Hash-Bound Human Authorization</p>
            </div>
          </div>
          <button onClick={onClose} style={{ background: "transparent", border: "none", color: "#94a3b8", cursor: "pointer", padding: "0.25rem" }}>
            <X style={{ width: "1.25rem", height: "1.25rem" }} />
          </button>
        </div>

        {/* Content */}
        <div style={{ padding: "1.5rem", display: "flex", flexDirection: "column", gap: "1.25rem" }}>
          
          {killSwitchActive && (
            <div style={{ backgroundColor: "rgba(239, 68, 68, 0.15)", border: "1px solid #ef4444", borderRadius: "0.5rem", padding: "0.75rem 1rem", display: "flex", alignItems: "center", gap: "0.75rem", color: "#fca5a5", fontSize: "0.85rem" }}>
              <ShieldAlert style={{ width: "1.25rem", height: "1.25rem", flexShrink: 0, color: "#ef4444" }} />
              <div>
                <strong>Emergency Freeze Active:</strong> Global Kill Switch is locked. All remediation actions are frozen and cannot be executed until deactivated.
              </div>
            </div>
          )}

          {errorMessage && (
            <div style={{ backgroundColor: "rgba(239, 68, 68, 0.1)", border: "1px solid #ef4444", borderRadius: "0.375rem", padding: "0.75rem", color: "#f87171", fontSize: "0.85rem" }}>
              {errorMessage}
            </div>
          )}

          {/* Proposal Meta Cards */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.75rem" }}>
            <div style={{ backgroundColor: "#1e293b", padding: "0.75rem", borderRadius: "0.5rem", border: "1px solid #334155" }}>
              <div style={{ fontSize: "0.7rem", color: "#94a3b8", textTransform: "uppercase", fontWeight: 600 }}>Proposal ID</div>
              <div style={{ fontSize: "0.95rem", fontWeight: 700, color: "#f8fafc", marginTop: "0.2rem" }}>{proposal.proposal_id}</div>
            </div>
            <div style={{ backgroundColor: "#1e293b", padding: "0.75rem", borderRadius: "0.5rem", border: "1px solid #334155" }}>
              <div style={{ fontSize: "0.7rem", color: "#94a3b8", textTransform: "uppercase", fontWeight: 600 }}>Risk / Safety</div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginTop: "0.2rem" }}>
                <span style={{ fontSize: "0.8rem", fontWeight: 700, color: riskColor }}>{proposal.risk_level}</span>
                <span style={{ fontSize: "0.75rem", color: "#94a3b8" }}>Score: {proposal.safety_score * 100}%</span>
              </div>
            </div>
            <div style={{ backgroundColor: "#1e293b", padding: "0.75rem", borderRadius: "0.5rem", border: "1px solid #334155" }}>
              <div style={{ fontSize: "0.7rem", color: "#94a3b8", textTransform: "uppercase", fontWeight: 600 }}>Target Device</div>
              <div style={{ fontSize: "0.95rem", fontWeight: 700, color: "#38bdf8", marginTop: "0.2rem" }}>{proposal.target_node}</div>
            </div>
          </div>

          {/* Planned Actions / Commands */}
          <div>
            <div style={{ fontSize: "0.8rem", fontWeight: 600, color: "#cbd5e1", marginBottom: "0.5rem", display: "flex", alignItems: "center", gap: "0.35rem" }}>
              <Terminal style={{ width: "0.9rem", height: "0.9rem", color: "#38bdf8" }} />
              Deterministic Action Commands (Allow-List Enforced)
            </div>
            <div style={{ backgroundColor: "#020617", border: "1px solid #334155", borderRadius: "0.5rem", padding: "0.75rem", display: "flex", flexDirection: "column", gap: "0.35rem" }}>
              {proposal.actions && proposal.actions.length > 0 ? (
                proposal.actions.map((act, idx) => (
                  <div key={idx} style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8rem", fontFamily: "monospace" }}>
                    <span style={{ color: "#64748b" }}>[{act.phase || "apply"}]</span>
                    <span style={{ color: "#a5f3fc" }}>{act.command}</span>
                  </div>
                ))
              ) : (
                <div style={{ fontSize: "0.8rem", fontFamily: "monospace", color: "#a5f3fc" }}>
                  {proposal.operation} ({JSON.stringify(proposal.parameters)})
                </div>
              )}
            </div>
          </div>

          {/* Cryptographic Hash Verification Card */}
          <div style={{ backgroundColor: "rgba(30, 41, 59, 0.6)", border: "1px solid #334155", borderRadius: "0.5rem", padding: "0.75rem" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.75rem", fontWeight: 600, color: "#94a3b8", marginBottom: "0.35rem" }}>
              <Key style={{ width: "0.85rem", height: "0.85rem", color: "#fbbf24" }} />
              Canonical Proposal Hash (SHA-256 Anti-Tamper Invariant)
            </div>
            <div style={{ fontSize: "0.75rem", fontFamily: "monospace", color: "#fbbf24", wordBreak: "break-all", backgroundColor: "#020617", padding: "0.4rem 0.6rem", borderRadius: "0.25rem", border: "1px solid #1e293b" }}>
              {proposal.proposal_hash}
            </div>
          </div>

          {/* Form Inputs */}
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <div>
              <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "#94a3b8", marginBottom: "0.25rem" }}>
                Operator Identity (for Tamper-Evident Audit Record)
              </label>
              <input
                type="text"
                value={operatorId}
                onChange={(e) => setOperatorId(e.target.value)}
                style={{ width: "100%", padding: "0.5rem 0.75rem", backgroundColor: "#1e293b", border: "1px solid #334155", borderRadius: "0.375rem", color: "#f8fafc", fontSize: "0.85rem", boxSizing: "border-box" }}
              />
            </div>
            <div>
              <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "#94a3b8", marginBottom: "0.25rem" }}>
                Authorization Justification / Reason
              </label>
              <textarea
                rows={2}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                style={{ width: "100%", padding: "0.5rem 0.75rem", backgroundColor: "#1e293b", border: "1px solid #334155", borderRadius: "0.375rem", color: "#f8fafc", fontSize: "0.85rem", boxSizing: "border-box", resize: "none" }}
              />
            </div>
          </div>

        </div>

        {/* Footer Actions */}
        <div style={{ padding: "1rem 1.5rem", borderTop: "1px solid #334155", display: "flex", alignItems: "center", justifyContent: "space-between", backgroundColor: "#0b1329" }}>
          <button
            onClick={handleReject}
            disabled={isSubmitting}
            style={{ padding: "0.5rem 1rem", backgroundColor: "transparent", border: "1px solid #f43f5e", color: "#fb7185", borderRadius: "0.375rem", fontSize: "0.85rem", fontWeight: 600, cursor: isSubmitting ? "not-allowed" : "pointer" }}
          >
            Reject Proposal
          </button>

          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button
              onClick={onClose}
              disabled={isSubmitting}
              style={{ padding: "0.5rem 1rem", backgroundColor: "#334155", border: "none", color: "#cbd5e1", borderRadius: "0.375rem", fontSize: "0.85rem", fontWeight: 500, cursor: "pointer" }}
            >
              Cancel
            </button>
            <button
              onClick={handleApprove}
              disabled={isSubmitting || killSwitchActive}
              style={{ padding: "0.5rem 1.25rem", backgroundColor: killSwitchActive ? "#475569" : "#10b981", border: "none", color: "#ffffff", borderRadius: "0.375rem", fontSize: "0.85rem", fontWeight: 700, cursor: killSwitchActive || isSubmitting ? "not-allowed" : "pointer", display: "flex", alignItems: "center", gap: "0.4rem" }}
            >
              <CheckCircle2 style={{ width: "1rem", height: "1rem" }} />
              {isSubmitting ? "Committing..." : "Approve & Execute"}
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}

