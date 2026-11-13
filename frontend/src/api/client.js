/**
 * client.js — Centralized API Client for CNT Network Fault Diagnosis & Safe Remediation.
 */

const API_BASE = "/api/v1";

async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const headers = {
    "Content-Type": "application/json",
    ...options.headers,
  };

  try {
    const res = await fetch(url, { ...options, headers });
    if (!res.ok) {
      let errorMsg = `HTTP ${res.status}: ${res.statusText}`;
      try {
        const errorData = await res.json();
        errorMsg = errorData.error || errorData.detail || errorMsg;
      } catch (_) {}
      throw new Error(errorMsg);
    }
    return await res.json();
  } catch (err) {
    console.error(`API Error on ${endpoint}:`, err);
    throw err;
  }
}

export const api = {
  // System
  getSystemStatus: () => request("/system/status"),

  // Incidents
  getIncidents: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return request(`/incidents${query ? `?${query}` : ""}`);
  },
  getIncident: (id) => request(`/incidents/${id}`),
  getIncidentDiagnosis: (id) => request(`/incidents/${id}/diagnosis`),
  getIncidentEvidence: (id) => request(`/incidents/${id}/evidence`),
  getIncidentHistory: (id) => request(`/incidents/${id}/history`),
  triggerIncident: (data) => request("/incidents", { method: "POST", body: JSON.stringify(data) }),

  // Topology
  getTopology: () => request("/topology"),
  getDevices: () => request("/topology/devices"),
  getLinks: () => request("/topology/links"),
  getBlastRadius: (rootCauseDevice) => request(`/topology/blast-radius?root_cause_device=${encodeURIComponent(rootCauseDevice)}`),
  getPaths: (source, destination) => request(`/topology/paths?source=${encodeURIComponent(source)}&destination=${encodeURIComponent(destination)}`),

  // Remediation Proposals
  getProposals: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return request(`/remediation/proposals${query ? `?${query}` : ""}`);
  },
  getProposal: (id) => request(`/remediation/proposals/${id}`),
  approveProposal: (id, data) => request(`/remediation/proposals/${id}/approve`, {
    method: "POST",
    body: JSON.stringify(data),
  }),
  rejectProposal: (id, data) => request(`/remediation/proposals/${id}/reject`, {
    method: "POST",
    body: JSON.stringify(data),
  }),

  // Executions
  getExecutions: () => request("/remediation/executions"),
  getExecution: (id) => request(`/remediation/executions/${id}`),
  getExecutionVerification: (id) => request(`/remediation/executions/${id}/verification`),
  rollbackExecution: (id, data = {}) => request(`/remediation/executions/${id}/rollback`, {
    method: "POST",
    body: JSON.stringify(data),
  }),

  // Kill Switch
  getKillSwitch: () => request("/kill-switch"),
  activateKillSwitch: (data) => request("/kill-switch/activate", {
    method: "POST",
    body: JSON.stringify(data),
  }),
  deactivateKillSwitch: (data) => request("/kill-switch/deactivate", {
    method: "POST",
    body: JSON.stringify(data),
  }),

  // Audit
  getAuditRecords: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return request(`/audit${query ? `?${query}` : ""}`);
  },
  getAuditVerification: () => request("/audit/verification"),
  getAuditRecord: (id) => request(`/audit/${id}`),
};

