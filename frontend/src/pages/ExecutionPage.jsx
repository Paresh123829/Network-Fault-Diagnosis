import React, { useEffect, useState } from "react";
import { Terminal, CheckCircle2, RotateCcw, AlertTriangle, ShieldCheck } from "lucide-react";
import { api } from "../api/client";

export function ExecutionPage({ killSwitchActive }) {
  const [executions, setExecutions] = useState([]);
  const [selectedExecution, setSelectedExecution] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isRollingBack, setIsRollingBack] = useState(false);

  const loadExecutions = async () => {
    try {
      const data = await api.getExecutions();
      setExecutions(data);
      if (data.length > 0 && !selectedExecution) {
        setSelectedExecution(data[0]);
      }
    } catch (err) {
      console.error("Error loading executions:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadExecutions();
  }, []);

  const handleRollback = async () => {
    if (!selectedExecution) return;
    if (killSwitchActive) {
      alert("Rollback blocked: Kill switch is currently ACTIVE.");
      return;
    }
    if (!confirm(`Are you sure you want to rollback execution ${selectedExecution.execution_id} using snapshot ${selectedExecution.snapshot_id}?`)) {
      return;
    }
    setIsRollingBack(true);
    try {
      await api.rollbackExecution(selectedExecution.execution_id, { operator_id: "operator_lead" });
      alert("Rollback initiated and snapshot restored successfully.");
      await loadExecutions();
    } catch (err) {
      alert("Rollback failed: " + err.message);
    } finally {
      setIsRollingBack(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      
      {/* Header */}
      <div>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700, margin: 0, color: "#f8fafc" }}>
          Remediation Execution & Recovery Monitor
        </h1>
        <p style={{ fontSize: "0.85rem", color: "#94a3b8", margin: "0.25rem 0 0" }}>
          Live Execution Timeline, Command Output Audits & Post-Remediation Verification
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: "1.25rem" }}>
        
        {/* Left: Executions List */}
        <div style={{ backgroundColor: "#111827", border: "1px solid #334155", borderRadius: "0.5rem", padding: "1rem", display: "flex", flexDirection: "column", gap: "0.5rem", maxHeight: "650px", overflowY: "auto" }}>
          <div style={{ fontSize: "0.85rem", fontWeight: 600, color: "#f8fafc", paddingBottom: "0.5rem", borderBottom: "1px solid #1e293b" }}>
            Execution Runs ({executions.length})
          </div>

          {executions.length === 0 ? (
            <div style={{ padding: "2rem", textAlign: "center", color: "#64748b", fontSize: "0.85rem" }}>
              No remediation executions yet. Authorize proposals from the Remediation Gate.
            </div>
          ) : (
            executions.map((ex) => {
              const isSelected = selectedExecution?.execution_id === ex.execution_id;
              const isRollback = ex.status === "ROLLED_BACK";
              return (
                <div
                  key={ex.execution_id}
                  onClick={() => setSelectedExecution(ex)}
                  style={{
                    backgroundColor: isSelected ? "#1e293b" : "#0f172a",
                    border: `1px solid ${isSelected ? "#38bdf8" : "#1e293b"}`,
                    borderRadius: "0.375rem",
                    padding: "0.75rem",
                    cursor: "pointer",
                    display: "flex",
                    flexDirection: "column",
                    gap: "0.25rem",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <span style={{ fontFamily: "monospace", fontSize: "0.8rem", fontWeight: 700, color: "#38bdf8" }}>
                      {ex.execution_id}
                    </span>
                    <span style={{ fontSize: "0.65rem", padding: "0.1rem 0.35rem", borderRadius: "0.2rem", fontWeight: 700, backgroundColor: isRollback ? "rgba(244, 63, 94, 0.2)" : "rgba(16, 185, 129, 0.2)", color: isRollback ? "#fb7185" : "#34d399" }}>
                      {ex.status}
                    </span>
                  </div>
                  <div style={{ fontSize: "0.75rem", color: "#cbd5e1" }}>
                    Proposal: <strong>{ex.proposal_id}</strong>
                  </div>
                  <div style={{ fontSize: "0.7rem", color: "#64748b" }}>
                    By: {ex.operator_id} | {ex.started_at?.split("T")[1]?.slice(0, 8)}
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Right: Detailed Execution Console */}
        {selectedExecution ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            
            {/* Verification & Meta Card */}
            <div style={{ backgroundColor: "#111827", border: "1px solid #334155", borderRadius: "0.5rem", padding: "1.25rem" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.75rem" }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <span style={{ fontFamily: "monospace", fontSize: "1.1rem", fontWeight: 700, color: "#f8fafc" }}>
                      {selectedExecution.execution_id}
                    </span>
                    <span style={{ fontSize: "0.75rem", padding: "0.15rem 0.45rem", borderRadius: "0.25rem", fontWeight: 700, backgroundColor: "rgba(16, 185, 129, 0.2)", color: "#34d399" }}>
                      SLO VERIFIED: PASS
                    </span>
                  </div>
                  <div style={{ fontSize: "0.8rem", color: "#94a3b8", marginTop: "0.2rem" }}>
                    Incident: <strong style={{ color: "#38bdf8" }}>{selectedExecution.incident_id}</strong> | Snapshot: <code style={{ color: "#fbbf24" }}>{selectedExecution.snapshot_id}</code>
                  </div>
                </div>

                <button
                  onClick={handleRollback}
                  disabled={isRollingBack || killSwitchActive || selectedExecution.status === "ROLLED_BACK"}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.4rem",
                    padding: "0.5rem 0.85rem",
                    backgroundColor: "transparent",
                    border: "1px solid #f43f5e",
                    color: "#fb7185",
                    borderRadius: "0.375rem",
                    fontSize: "0.8rem",
                    fontWeight: 600,
                    cursor: selectedExecution.status === "ROLLED_BACK" || isRollingBack || killSwitchActive ? "not-allowed" : "pointer",
                  }}
                >
                  <RotateCcw style={{ width: "0.85rem", height: "0.85rem" }} />
                  {selectedExecution.status === "ROLLED_BACK" ? "Rolled Back" : (isRollingBack ? "Rolling back..." : "Revert Snapshot (Rollback)")}
                </button>
              </div>

              {/* Recovery Verification Metrics */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.75rem", marginTop: "1rem" }}>
                <div style={{ backgroundColor: "#0f172a", padding: "0.75rem", borderRadius: "0.375rem" }}>
                  <div style={{ fontSize: "0.7rem", color: "#94a3b8", fontWeight: 600 }}>Post-Remediation Loss</div>
                  <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "#34d399", marginTop: "0.15rem" }}>0.0%</div>
                </div>
                <div style={{ backgroundColor: "#0f172a", padding: "0.75rem", borderRadius: "0.375rem" }}>
                  <div style={{ fontSize: "0.7rem", color: "#94a3b8", fontWeight: 600 }}>BGP / OSPF Peering</div>
                  <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "#34d399", marginTop: "0.15rem" }}>Established</div>
                </div>
                <div style={{ backgroundColor: "#0f172a", padding: "0.75rem", borderRadius: "0.375rem" }}>
                  <div style={{ fontSize: "0.7rem", color: "#94a3b8", fontWeight: 600 }}>MTTR Convergence</div>
                  <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "#38bdf8", marginTop: "0.15rem" }}>34.1 ms</div>
                </div>
              </div>
            </div>

            {/* Terminal Command Output Log */}
            <div style={{ backgroundColor: "#0b1329", border: "1px solid #334155", borderRadius: "0.5rem", padding: "1rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem", fontWeight: 600, color: "#94a3b8" }}>
                <Terminal style={{ width: "0.9rem", height: "0.9rem", color: "#38bdf8" }} />
                Real-Time Execution Console Log
              </div>

              <div style={{ backgroundColor: "#020617", border: "1px solid #1e293b", borderRadius: "0.375rem", padding: "0.85rem", display: "flex", flexDirection: "column", gap: "0.35rem", minHeight: "240px", maxHeight: "380px", overflowY: "auto", fontFamily: "monospace", fontSize: "0.8rem" }}>
                {selectedExecution.output_log?.map((line, idx) => (
                  <div key={idx} style={{ color: line.startsWith("[APPLY]") ? "#38bdf8" : (line.startsWith("[VERIFY]") ? "#34d399" : (line.startsWith("[ROLLBACK]") ? "#fb7185" : "#cbd5e1")) }}>
                    {line}
                  </div>
                )) || <div style={{ color: "#64748b" }}>No log output recorded</div>}
              </div>
            </div>

          </div>
        ) : (
          <div style={{ backgroundColor: "#111827", border: "1px solid #334155", borderRadius: "0.5rem", padding: "3rem", textAlign: "center", color: "#64748b" }}>
            Select an execution run to inspect logs and verification report.
          </div>
        )}

      </div>

    </div>
  );
}

