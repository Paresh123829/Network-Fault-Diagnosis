import React, { useState } from "react";
import { Radio, Play, Pause, Trash2, Filter } from "lucide-react";

export function LiveStreamPage({ events, isConnected, onClearEvents }) {
  const [filterType, setFilterType] = useState("ALL");
  const [isPaused, setIsPaused] = useState(false);

  const displayedEvents = events.filter((ev) => {
    if (filterType === "ALL") return true;
    return ev.event.toLowerCase().includes(filterType.toLowerCase());
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      
      {/* Header & Controls */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Radio style={{ width: "1.2rem", height: "1.2rem", color: isConnected ? "#10b981" : "#ef4444" }} />
            <h1 style={{ fontSize: "1.5rem", fontWeight: 700, margin: 0, color: "#f8fafc" }}>
              Live Telemetry & Event Stream
            </h1>
          </div>
          <p style={{ fontSize: "0.85rem", color: "#94a3b8", margin: "0.25rem 0 0" }}>
            Real-time event distribution via Socket.IO & WebSocket Gateway ({events.length} captured)
          </p>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          
          {/* Event Filter */}
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            style={{
              padding: "0.45rem 0.75rem",
              backgroundColor: "#1e293b",
              border: "1px solid #334155",
              borderRadius: "0.375rem",
              color: "#f8fafc",
              fontSize: "0.85rem",
            }}
          >
            <option value="ALL">All Event Types</option>
            <option value="incident">Incidents</option>
            <option value="diagnosis">Diagnosis</option>
            <option value="remediation">Remediation</option>
            <option value="execution">Execution</option>
            <option value="kill_switch">Kill Switch</option>
          </select>

          {/* Pause / Resume */}
          <button
            onClick={() => setIsPaused(!isPaused)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.35rem",
              padding: "0.45rem 0.75rem",
              backgroundColor: isPaused ? "#f59e0b" : "#334155",
              color: "#ffffff",
              border: "none",
              borderRadius: "0.375rem",
              fontSize: "0.85rem",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            {isPaused ? <Play style={{ width: "0.9rem", height: "0.9rem" }} /> : <Pause style={{ width: "0.9rem", height: "0.9rem" }} />}
            {isPaused ? "Resume" : "Pause"}
          </button>

          {/* Clear */}
          <button
            onClick={onClearEvents}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.35rem",
              padding: "0.45rem 0.75rem",
              backgroundColor: "transparent",
              color: "#94a3b8",
              border: "1px solid #334155",
              borderRadius: "0.375rem",
              fontSize: "0.85rem",
              cursor: "pointer",
            }}
          >
            <Trash2 style={{ width: "0.9rem", height: "0.9rem" }} />
            Clear
          </button>
        </div>
      </div>

      {/* Events Stream Feed */}
      <div style={{ backgroundColor: "#0b1329", border: "1px solid #334155", borderRadius: "0.5rem", padding: "1rem", minHeight: "450px", maxHeight: "650px", overflowY: "auto", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        {displayedEvents.length === 0 ? (
          <div style={{ padding: "4rem", textAlign: "center", color: "#64748b" }}>
            {isConnected ? "Listening for real-time network domain events..." : "Connecting to Socket.IO gateway..."}
          </div>
        ) : (
          displayedEvents.map((ev) => {
            const isKillSwitch = ev.event.includes("kill_switch");
            const isRemediation = ev.event.includes("remediation") || ev.event.includes("execution");
            const isIncident = ev.event.includes("incident");

            const badgeColor = isKillSwitch ? "#ef4444" : (isRemediation ? "#10b981" : (isIncident ? "#f59e0b" : "#38bdf8"));

            return (
              <div
                key={ev.id}
                style={{
                  backgroundColor: "#111827",
                  border: "1px solid #1e293b",
                  borderRadius: "0.375rem",
                  padding: "0.85rem 1rem",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.4rem",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <span style={{ fontSize: "0.75rem", fontFamily: "monospace", fontWeight: 700, color: badgeColor, backgroundColor: "rgba(255,255,255,0.05)", padding: "0.15rem 0.4rem", borderRadius: "0.25rem", border: `1px solid ${badgeColor}33` }}>
                      {ev.event}
                    </span>
                  </div>
                  <span style={{ fontSize: "0.75rem", color: "#64748b", fontFamily: "monospace" }}>
                    {ev.timestamp}
                  </span>
                </div>

                <div style={{ backgroundColor: "#020617", padding: "0.5rem 0.75rem", borderRadius: "0.25rem", border: "1px solid #1e293b", fontSize: "0.8rem", fontFamily: "monospace", color: "#a5f3fc", overflowX: "auto" }}>
                  <pre style={{ margin: 0 }}>
                    {JSON.stringify(ev.payload, null, 2)}
                  </pre>
                </div>
              </div>
            );
          })
        )}
      </div>

    </div>
  );
}

