import React, { useEffect, useState } from "react";
import { Network, Server, ShieldAlert, Cpu, Activity, Info } from "lucide-react";
import { api } from "../api/client";

export function TopologyPage() {
  const [topology, setTopology] = useState(null);
  const [selectedNode, setSelectedNode] = useState("leaf-01");
  const [blastReport, setBlastReport] = useState(null);
  const [pathsReport, setPathsReport] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadTopology() {
      try {
        const data = await api.getTopology();
        setTopology(data);
      } catch (err) {
        console.error("Error loading topology:", err);
      } finally {
        setLoading(false);
      }
    }
    loadTopology();
  }, []);

  useEffect(() => {
    async function loadAnalysis() {
      if (!selectedNode) return;
      try {
        const [blast, paths] = await Promise.all([
          api.getBlastRadius(selectedNode),
          api.getPaths(selectedNode, "border-01"),
        ]);
        setBlastReport(blast);
        setPathsReport(paths);
      } catch (err) {
        console.error("Error loading blast radius/paths:", err);
      }
    }
    loadAnalysis();
  }, [selectedNode]);

  // Coordinate layout for 5-node Clos fabric
  const nodePositions = {
    "border-01": { x: 350, y: 70, role: "border" },
    "spine-01": { x: 230, y: 190, role: "spine" },
    "spine-02": { x: 470, y: 190, role: "spine" },
    "leaf-01": { x: 230, y: 330, role: "leaf" },
    "leaf-02": { x: 470, y: 330, role: "leaf" },
  };

  const isImpacted = (nodeId) => {
    if (!blastReport) return false;
    return (
      blastReport.originating_devices?.includes(nodeId) ||
      blastReport.direct_impact_devices?.includes(nodeId) ||
      blastReport.adjacent_exposure_devices?.includes(nodeId)
    );
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      
      {/* Top Header */}
      <div>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700, margin: 0, color: "#f8fafc" }}>
          Interactive Topology Visualizer & Blast Radius Engine
        </h1>
        <p style={{ fontSize: "0.85rem", color: "#94a3b8", margin: "0.25rem 0 0" }}>
          Spine-Leaf Fabric Interconnects, Real-Time Failure Domains & Exposure Mapping
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.7fr 1fr", gap: "1.25rem" }}>
        
        {/* Left: SVG Canvas */}
        <div style={{ backgroundColor: "#111827", border: "1px solid #334155", borderRadius: "0.5rem", padding: "1.25rem", position: "relative" }}>
          
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.75rem" }}>
            <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "#f8fafc" }}>
              Fabric Clos Graph (Containerlab Mock Provider)
            </span>
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", fontSize: "0.75rem" }}>
              <span style={{ display: "flex", alignItems: "center", gap: "0.25rem", color: "#10b981" }}>
                <span style={{ width: "0.45rem", height: "0.45rem", borderRadius: "50%", backgroundColor: "#10b981" }}></span> UP
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: "0.25rem", color: "#fb7185" }}>
                <span style={{ width: "0.45rem", height: "0.45rem", borderRadius: "50%", backgroundColor: "#fb7185" }}></span> Exposed/Failed
              </span>
            </div>
          </div>

          <svg viewBox="0 0 700 420" style={{ width: "100%", height: "auto", backgroundColor: "#0b1329", borderRadius: "0.375rem", border: "1px solid #1e293b" }}>
            
            {/* Draw Links */}
            {topology?.links?.map((link, idx) => {
              const src = nodePositions[link.source] || { x: 100, y: 100 };
              const tgt = nodePositions[link.target] || { x: 200, y: 200 };
              const isSelectedLink =
                (selectedNode === link.source || selectedNode === link.target);
              return (
                <g key={idx}>
                  <line
                    x1={src.x}
                    y1={src.y}
                    x2={tgt.x}
                    y2={tgt.y}
                    stroke={isSelectedLink ? "#38bdf8" : "#334155"}
                    strokeWidth={isSelectedLink ? 3 : 2}
                    strokeDasharray={isSelectedLink ? "4" : "none"}
                  />
                </g>
              );
            })}

            {/* Draw Nodes */}
            {Object.entries(nodePositions).map(([id, pos]) => {
              const isSelected = selectedNode === id;
              const impacted = isImpacted(id);
              const nodeColor = impacted ? "#f43f5e" : (isSelected ? "#38bdf8" : "#10b981");

              return (
                <g
                  key={id}
                  transform={`translate(${pos.x}, ${pos.y})`}
                  onClick={() => setSelectedNode(id)}
                  style={{ cursor: "pointer" }}
                >
                  <circle
                    r={isSelected ? 26 : 22}
                    fill="#1e293b"
                    stroke={nodeColor}
                    strokeWidth={isSelected ? 3.5 : 2}
                  />
                  <text
                    textAnchor="middle"
                    dy="-2"
                    fill="#f8fafc"
                    fontSize="11"
                    fontWeight="700"
                    fontFamily="Inter, sans-serif"
                  >
                    {id}
                  </text>
                  <text
                    textAnchor="middle"
                    dy="12"
                    fill="#94a3b8"
                    fontSize="9"
                    fontWeight="600"
                    textTransform="uppercase"
                  >
                    {pos.role}
                  </text>
                </g>
              );
            })}
          </svg>

          <div style={{ marginTop: "0.75rem", fontSize: "0.75rem", color: "#94a3b8", textAlign: "center" }}>
            Click on any device node above to simulate failure impact and calculate quantitative blast radius.
          </div>
        </div>

        {/* Right: Blast Radius & Path Redundancy Panel */}
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          
          {/* Selected Node Details Card */}
          <div style={{ backgroundColor: "#111827", border: "1px solid #334155", borderRadius: "0.5rem", padding: "1.25rem" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.75rem" }}>
              <span style={{ fontSize: "0.8rem", color: "#94a3b8", textTransform: "uppercase", fontWeight: 600 }}>Selected Device</span>
              <span style={{ fontSize: "0.75rem", padding: "0.15rem 0.5rem", borderRadius: "0.25rem", fontWeight: 700, backgroundColor: "rgba(56, 189, 248, 0.15)", color: "#38bdf8" }}>
                ACTIVE NODE
              </span>
            </div>
            <div style={{ fontSize: "1.3rem", fontWeight: 700, color: "#f8fafc" }}>
              {selectedNode}
            </div>
            <div style={{ fontSize: "0.8rem", color: "#94a3b8", marginTop: "0.25rem" }}>
              Role: <strong>{nodePositions[selectedNode]?.role.toUpperCase()}</strong> | Management IP: 10.0.1.1
            </div>
          </div>

          {/* Quantitative Blast Radius Card */}
          {blastReport && (
            <div style={{ backgroundColor: "#1e293b", border: "1px solid #334155", borderRadius: "0.5rem", padding: "1.25rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.95rem", fontWeight: 600, color: "#f8fafc", marginBottom: "0.75rem" }}>
                <ShieldAlert style={{ width: "1.05rem", height: "1.05rem", color: "#f59e0b" }} />
                Quantitative Blast Radius (M5.1 Engine)
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem", marginBottom: "0.75rem" }}>
                <div style={{ backgroundColor: "#0f172a", padding: "0.75rem", borderRadius: "0.375rem" }}>
                  <div style={{ fontSize: "0.7rem", color: "#94a3b8", fontWeight: 600 }}>Impact Exposure (IER)</div>
                  <div style={{ fontSize: "1.2rem", fontWeight: 700, color: "#fbbf24", marginTop: "0.2rem" }}>
                    {(blastReport.impact_exposure_ratio * 100).toFixed(0)}%
                  </div>
                  <div style={{ fontSize: "0.7rem", color: "#64748b" }}>Direct + Adjacent Exposed</div>
                </div>

                <div style={{ backgroundColor: "#0f172a", padding: "0.75rem", borderRadius: "0.375rem" }}>
                  <div style={{ fontSize: "0.7rem", color: "#94a3b8", fontWeight: 600 }}>Unreachability (NUR)</div>
                  <div style={{ fontSize: "1.2rem", fontWeight: 700, color: "#34d399", marginTop: "0.2rem" }}>
                    {(blastReport.network_unreachability_ratio * 100).toFixed(0)}%
                  </div>
                  <div style={{ fontSize: "0.7rem", color: "#64748b" }}>0% unreachable (Dual Homed)</div>
                </div>
              </div>

              <div style={{ fontSize: "0.8rem", color: "#cbd5e1", display: "flex", flexDirection: "column", gap: "0.35rem" }}>
                <div>Direct Impact: <strong>{blastReport.direct_impact_devices?.join(", ")}</strong></div>
                <div>Adjacent Exposure: <strong>{blastReport.adjacent_exposure_devices?.join(", ")}</strong></div>
                <div>Surviving Alternate Paths: <strong>{blastReport.surviving_alternate_paths_count} paths</strong></div>
              </div>
            </div>
          )}

          {/* Path Redundancy Card */}
          {pathsReport && (
            <div style={{ backgroundColor: "#111827", border: "1px solid #334155", borderRadius: "0.5rem", padding: "1.25rem" }}>
              <div style={{ fontSize: "0.85rem", fontWeight: 600, color: "#f8fafc", marginBottom: "0.5rem" }}>
                Forwarding Paths to Border (DCI)
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                {pathsReport.shortest_paths?.map((path, idx) => (
                  <div key={idx} style={{ backgroundColor: "#020617", padding: "0.4rem 0.6rem", borderRadius: "0.25rem", fontSize: "0.75rem", fontFamily: "monospace", color: "#38bdf8" }}>
                    Path #{idx + 1}: {path.join(" → ")}
                  </div>
                ))}
              </div>
            </div>
          )}

        </div>

      </div>

    </div>
  );
}

