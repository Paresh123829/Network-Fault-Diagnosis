import React, { useState } from "react";
import { Search, Filter, ShieldAlert, ArrowRight } from "lucide-react";

export function IncidentsPage({ incidents, onSelectIncident }) {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [severityFilter, setSeverityFilter] = useState("ALL");

  const filtered = incidents.filter((inc) => {
    const matchesSearch =
      inc.title.toLowerCase().includes(search.toLowerCase()) ||
      inc.target_node.toLowerCase().includes(search.toLowerCase()) ||
      inc.incident_id.toLowerCase().includes(search.toLowerCase()) ||
      inc.protocol.toLowerCase().includes(search.toLowerCase());

    const matchesStatus = statusFilter === "ALL" || inc.status.toUpperCase() === statusFilter;
    const matchesSeverity = severityFilter === "ALL" || inc.severity.toUpperCase() === severityFilter;

    return matchesSearch && matchesStatus && matchesSeverity;
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, margin: 0, color: "#f8fafc" }}>
            Network Incidents ({filtered.length})
          </h1>
          <p style={{ fontSize: "0.85rem", color: "#94a3b8", margin: "0.25rem 0 0" }}>
            Real-time telemetry anomaly detections and automated diagnosis candidates
          </p>
        </div>

        {/* Filter Controls */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
          
          {/* Search Box */}
          <div style={{ position: "relative" }}>
            <Search style={{ position: "absolute", left: "0.75rem", top: "50%", transform: "translateY(-50%)", width: "0.9rem", height: "0.9rem", color: "#64748b" }} />
            <input
              type="text"
              placeholder="Search node, ID, protocol..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                padding: "0.45rem 0.75rem 0.45rem 2.2rem",
                backgroundColor: "#1e293b",
                border: "1px solid #334155",
                borderRadius: "0.375rem",
                color: "#f8fafc",
                fontSize: "0.85rem",
                width: "220px",
              }}
            />
          </div>

          {/* Status Select */}
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
            <option value="ALL">Status: All</option>
            <option value="ACTIVE">Active</option>
            <option value="RESOLVED">Resolved</option>
          </select>

          {/* Severity Select */}
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            style={{
              padding: "0.45rem 0.75rem",
              backgroundColor: "#1e293b",
              border: "1px solid #334155",
              borderRadius: "0.375rem",
              color: "#f8fafc",
              fontSize: "0.85rem",
            }}
          >
            <option value="ALL">Severity: All</option>
            <option value="CRITICAL">Critical</option>
            <option value="HIGH">High</option>
            <option value="MEDIUM">Medium</option>
          </select>

        </div>
      </div>

      {/* Incidents Table */}
      <div style={{ backgroundColor: "#111827", borderRadius: "0.5rem", border: "1px solid #334155", overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "0.85rem" }}>
          <thead>
            <tr style={{ backgroundColor: "#0f172a", borderBottom: "1px solid #334155", color: "#94a3b8" }}>
              <th style={{ padding: "0.75rem 1rem", fontWeight: 600 }}>Incident ID</th>
              <th style={{ padding: "0.75rem 1rem", fontWeight: 600 }}>Title & Description</th>
              <th style={{ padding: "0.75rem 1rem", fontWeight: 600 }}>Target Node</th>
              <th style={{ padding: "0.75rem 1rem", fontWeight: 600 }}>Protocol</th>
              <th style={{ padding: "0.75rem 1rem", fontWeight: 600 }}>Severity</th>
              <th style={{ padding: "0.75rem 1rem", fontWeight: 600 }}>Status</th>
              <th style={{ padding: "0.75rem 1rem", fontWeight: 600, textAlign: "right" }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ padding: "2rem", textAlign: "center", color: "#64748b" }}>
                  No incidents match the selected filters.
                </td>
              </tr>
            ) : (
              filtered.map((inc) => (
                <tr
                  key={inc.incident_id}
                  onClick={() => onSelectIncident(inc.incident_id)}
                  style={{
                    borderBottom: "1px solid #1e293b",
                    cursor: "pointer",
                    transition: "background-color 0.15s ease",
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "#1e293b")}
                  onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
                >
                  <td style={{ padding: "0.85rem 1rem", fontFamily: "monospace", fontWeight: 700, color: "#38bdf8" }}>
                    {inc.incident_id}
                  </td>
                  <td style={{ padding: "0.85rem 1rem" }}>
                    <div style={{ fontWeight: 600, color: "#f8fafc" }}>{inc.title}</div>
                    <div style={{ fontSize: "0.75rem", color: "#94a3b8", marginTop: "0.15rem" }}>
                      {inc.description}
                    </div>
                  </td>
                  <td style={{ padding: "0.85rem 1rem", fontWeight: 600, color: "#f1f5f9" }}>
                    {inc.target_node}
                  </td>
                  <td style={{ padding: "0.85rem 1rem", fontFamily: "monospace", textTransform: "uppercase", color: "#cbd5e1" }}>
                    {inc.protocol}
                  </td>
                  <td style={{ padding: "0.85rem 1rem" }}>
                    <span style={{ fontSize: "0.7rem", padding: "0.2rem 0.5rem", borderRadius: "0.25rem", fontWeight: 700, backgroundColor: inc.severity === "CRITICAL" ? "rgba(239, 68, 68, 0.2)" : "rgba(245, 158, 11, 0.2)", color: inc.severity === "CRITICAL" ? "#f87171" : "#fbbf24" }}>
                      {inc.severity}
                    </span>
                  </td>
                  <td style={{ padding: "0.85rem 1rem" }}>
                    <span style={{ fontSize: "0.7rem", padding: "0.2rem 0.5rem", borderRadius: "0.25rem", fontWeight: 600, backgroundColor: inc.status === "ACTIVE" ? "rgba(239, 68, 68, 0.15)" : "rgba(16, 185, 129, 0.15)", color: inc.status === "ACTIVE" ? "#f87171" : "#34d399" }}>
                      {inc.status}
                    </span>
                  </td>
                  <td style={{ padding: "0.85rem 1rem", textAlign: "right" }}>
                    <span style={{ color: "#38bdf8", fontWeight: 600, display: "inline-flex", alignItems: "center", gap: "0.25rem" }}>
                      Inspect <ArrowRight style={{ width: "0.85rem", height: "0.85rem" }} />
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

    </div>
  );
}

