import React, { useEffect, useState } from "react";
import { ArrowLeft, ShieldAlert, Cpu, CheckCircle2, Terminal, FileText, ExternalLink } from "lucide-react";
import { api } from "../api/client";

export function IncidentDetailPage({ incidentId, onBack, onOpenProposal }) {
  const [incident, setIncident] = useState(null);
  const [diagnosis, setDiagnosis] = useState(null);
  const [evidence, setEvidence] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      setLoading(true);
      try {
        const [inc, diag, ev, hist] = await Promise.all([
          api.getIncident(incidentId),
          api.getIncidentDiagnosis(incidentId),
          api.getIncidentEvidence(incidentId),
          api.getIncidentHistory(incidentId),
        ]);
        setIncident(inc);
        setDiagnosis(diag);
        setEvidence(ev);
        setHistory(hist);
      } catch (err) {
        console.error("Error loading incident details:", err);
      } finally {
        setLoading(false);
      }
    }
    if (incidentId) loadData();
  }, [incidentId]);

  if (loading) {
    return (
      <div style={{ padding: "3rem", textAlign: "center", color: "#94a3b8" }}>
        Loading incident and diagnostic telemetry...
      </div>
    );
  }

  if (!incident) {
    return (
      <div style={{ padding: "3rem", textAlign: "center", color: "#ef4444" }}>
        Incident {incidentId} not found.
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      
      {/* Top Bar with Back Link */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <button
          onClick={onBack}
          style={{ display: "flex", alignItems: "center", gap: "0.4rem", background: "transparent", border: "none", color: "#38bdf8", cursor: "pointer", fontSize: "0.85rem", fontWeight: 600 }}
        >
          <ArrowLeft style={{ width: "1rem", height: "1rem" }} />
          Back to Incidents List
        </button>

        {incident.remediation_proposal_id && (
          <button
            onClick={() => onOpenProposal(incident.remediation_proposal_id)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.4rem",
              padding: "0.5rem 1rem",
              backgroundColor: "#10b981",
              color: "#ffffff",
              border: "none",
              borderRadius: "0.375rem",
              fontSize: "0.85rem",
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            Review Remediation Proposal ({incident.remediation_proposal_id})
            <ExternalLink style={{ width: "0.9rem", height: "0.9rem" }} />
          </button>
        )}
      </div>

      {/* Incident Title & Severity Banner */}
      <div style={{ backgroundColor: "#111827", border: "1px solid #334155", borderRadius: "0.5rem", padding: "1.25rem", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <span style={{ fontFamily: "monospace", fontSize: "0.9rem", fontWeight: 700, color: "#38bdf8" }}>
              {incident.incident_id}
            </span>
            <span style={{ fontSize: "0.75rem", padding: "0.15rem 0.5rem", borderRadius: "0.25rem", fontWeight: 700, backgroundColor: incident.severity === "CRITICAL" ? "rgba(239, 68, 68, 0.2)" : "rgba(245, 158, 11, 0.2)", color: incident.severity === "CRITICAL" ? "#f87171" : "#fbbf24" }}>
              {incident.severity}
            </span>
            <span style={{ fontSize: "0.75rem", padding: "0.15rem 0.5rem", borderRadius: "0.25rem", fontWeight: 600, backgroundColor: incident.status === "ACTIVE" ? "rgba(239, 68, 68, 0.15)" : "rgba(16, 185, 129, 0.15)", color: incident.status === "ACTIVE" ? "#f87171" : "#34d399" }}>
              {incident.status}
            </span>
          </div>
          <h1 style={{ fontSize: "1.35rem", fontWeight: 700, margin: "0.35rem 0 0", color: "#f8fafc" }}>
            {incident.title}
          </h1>
          <p style={{ fontSize: "0.85rem", color: "#94a3b8", margin: "0.25rem 0 0" }}>
            {incident.description}
          </p>
        </div>

        <div style={{ display: "flex", gap: "1.5rem" }}>
          <div>
            <div style={{ fontSize: "0.7rem", color: "#94a3b8", textTransform: "uppercase", fontWeight: 600 }}>Target Node</div>
            <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "#38bdf8", marginTop: "0.15rem" }}>{incident.target_node}</div>
          </div>
          <div>
            <div style={{ fontSize: "0.7rem", color: "#94a3b8", textTransform: "uppercase", fontWeight: 600 }}>Protocol</div>
            <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "#f8fafc", textTransform: "uppercase", marginTop: "0.15rem" }}>{incident.protocol}</div>
          </div>
        </div>
      </div>

      {/* Diagnosis & Root Cause Card */}
      {diagnosis && (
        <div style={{ backgroundColor: "#1e293b", border: "1px solid #334155", borderRadius: "0.5rem", padding: "1.25rem" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: "1px solid #334155", paddingBottom: "0.75rem", marginBottom: "1rem" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <Cpu style={{ width: "1.1rem", height: "1.1rem", color: "#38bdf8" }} />
              <h2 style={{ fontSize: "1rem", fontWeight: 700, margin: 0, color: "#f8fafc" }}>
                Multi-Agent Root Cause Analysis (RCA)
              </h2>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <span style={{ fontSize: "0.8rem", color: "#94a3b8" }}>Confidence Score:</span>
              <span style={{ fontSize: "0.95rem", fontWeight: 700, color: "#34d399", padding: "0.2rem 0.5rem", backgroundColor: "rgba(16, 185, 129, 0.15)", borderRadius: "0.25rem" }}>
                {(diagnosis.confidence_score * 100).toFixed(1)}%
              </span>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "1rem" }}>
            <div>
              <div style={{ fontSize: "0.8rem", color: "#94a3b8", fontWeight: 600 }}>Primary Root Cause Hypothesis:</div>
              <div style={{ fontSize: "1.05rem", fontWeight: 700, color: "#f8fafc", marginTop: "0.25rem" }}>
                {diagnosis.root_cause}
              </div>
              <div style={{ fontSize: "0.8rem", color: "#94a3b8", marginTop: "0.5rem" }}>
                Affected Component: <code style={{ color: "#38bdf8" }}>{diagnosis.target_component || incident.target_component || "N/A"}</code>
              </div>
            </div>

            <div style={{ backgroundColor: "#0f172a", padding: "0.75rem", borderRadius: "0.375rem", border: "1px solid #334155" }}>
              <div style={{ fontSize: "0.75rem", color: "#94a3b8", fontWeight: 600 }}>Blast Radius Exposure</div>
              <div style={{ fontSize: "1.2rem", fontWeight: 700, color: "#f8fafc", marginTop: "0.2rem" }}>
                {diagnosis.blast_radius_devices} Node(s)
              </div>
              <div style={{ fontSize: "0.75rem", color: "#94a3b8", marginTop: "0.25rem" }}>
                Impacted: {diagnosis.impacted_devices?.join(", ")}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Telemetry Evidence & Syslog Snippets */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.25rem" }}>
        
        {/* Left: Telemetry & Metrics */}
        <div style={{ backgroundColor: "#111827", border: "1px solid #334155", borderRadius: "0.5rem", padding: "1.25rem" }}>
          <div style={{ fontSize: "0.95rem", fontWeight: 600, color: "#f8fafc", marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <FileText style={{ width: "1rem", height: "1rem", color: "#38bdf8" }} />
            Telemetry Metrics & Anomaly Slices
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {evidence?.evidence?.anomalous_metrics?.map((m, idx) => (
              <div key={idx} style={{ backgroundColor: "#1e293b", padding: "0.6rem 0.75rem", borderRadius: "0.375rem", display: "flex", justifyContent: "space-between", fontSize: "0.8rem" }}>
                <span style={{ color: "#94a3b8" }}>{m.metric}:</span>
                <span style={{ fontWeight: 600, color: "#fb7185", fontFamily: "monospace" }}>
                  actual: {String(m.actual || m.value)} {m.threshold ? `(threshold: ${m.threshold})` : ""}
                </span>
              </div>
            )) || <div style={{ color: "#64748b", fontSize: "0.8rem" }}>No metrics recorded</div>}
          </div>
        </div>

        {/* Right: Syslog Snippets */}
        <div style={{ backgroundColor: "#111827", border: "1px solid #334155", borderRadius: "0.5rem", padding: "1.25rem" }}>
          <div style={{ fontSize: "0.95rem", fontWeight: 600, color: "#f8fafc", marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <Terminal style={{ width: "1rem", height: "1rem", color: "#38bdf8" }} />
            Syslog & Event Captures
          </div>
          <div style={{ backgroundColor: "#020617", border: "1px solid #334155", borderRadius: "0.375rem", padding: "0.75rem", display: "flex", flexDirection: "column", gap: "0.4rem", maxHeight: "160px", overflowY: "auto" }}>
            {evidence?.evidence?.syslog_snippets?.map((line, idx) => (
              <div key={idx} style={{ fontSize: "0.75rem", fontFamily: "monospace", color: "#cbd5e1" }}>
                {line}
              </div>
            )) || <div style={{ color: "#64748b", fontSize: "0.8rem" }}>No syslog events recorded</div>}
          </div>
        </div>

      </div>

      {/* Incident Lifecycle Timeline */}
      <div style={{ backgroundColor: "#111827", border: "1px solid #334155", borderRadius: "0.5rem", padding: "1.25rem" }}>
        <div style={{ fontSize: "0.95rem", fontWeight: 600, color: "#f8fafc", marginBottom: "1rem" }}>
          Incident Lifecycle Timeline
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {history.map((event, idx) => (
            <div key={idx} style={{ display: "flex", alignItems: "flex-start", gap: "0.75rem", fontSize: "0.85rem" }}>
              <div style={{ width: "0.5rem", height: "0.5rem", borderRadius: "50%", backgroundColor: "#38bdf8", marginTop: "0.4rem" }}></div>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <strong style={{ color: "#f8fafc" }}>{event.event}</strong>
                  <span style={{ fontSize: "0.75rem", color: "#64748b" }}>by {event.actor}</span>
                  <span style={{ fontSize: "0.75rem", color: "#64748b", marginLeft: "auto" }}>{event.timestamp}</span>
                </div>
                <div style={{ color: "#94a3b8", fontSize: "0.8rem", marginTop: "0.15rem" }}>
                  {event.details}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}

