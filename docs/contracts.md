# Contracts Reference

This document is the canonical reference for all inter-agent data contracts used in the
Multi-Agent AI Framework for Intelligent Network Fault Diagnosis.

---

## StructuredEvent (Ingestion Agent → Correlation Agent)

| Field | Type | Required | Description |
|---|---|---|---|
| `event_id` | string | ✅ | Unique event identifier |
| `timestamp` | datetime (UTC) | ✅ | Normalized UTC timestamp |
| `device_id` | string | ✅ | Normalized device identifier |
| `interface` | string | ❌ | Affected interface, if applicable |
| `event_type` | EventType enum | ✅ | Normalized event type |
| `severity` | Severity enum | ✅ | Normalized severity level |
| `normalized_fields` | dict | ✅ | Protocol-specific key-value pairs |
| `raw_reference` | string | ✅ | Reference to original raw record |

---

## IncidentTimeline (Correlation Agent → Topology Agent)

| Field | Type | Required | Description |
|---|---|---|---|
| `incident_id` | string | ✅ | Unique incident identifier |
| `time_window` | TimeWindow | ✅ | Start and end of incident window |
| `events` | list[StructuredEvent] | ✅ | Ordered correlated events |
| `affected_devices` | list[string] | ✅ | Distinct device IDs involved |
| `suspected_protocols` | list[string] | ❌ | Suspected protocols |

---

## TopologyContext (Topology Agent → Diagnostic Agent)

| Field | Type | Required | Description |
|---|---|---|---|
| `nodes` | list[TopologyNode] | ✅ | Nodes relevant to the incident |
| `links` | list[TopologyLink] | ✅ | Links between relevant nodes |
| `affected_path` | list[string] | ❌ | Ordered node IDs on affected path |
| `neighbors` | dict | ❌ | Adjacency map |
| `protocol_relationships` | dict | ❌ | Protocol-level relationships |

---

## RetrievedEvidence (RAG Agent → Diagnostic Agent)

| Field | Type | Required | Description |
|---|---|---|---|
| `query` | string | ✅ | Query used for retrieval |
| `passages` | list[EvidencePassage] | ❌ | Retrieved passages |
| `source_ids` | list[string] | ❌ | Distinct source identifiers |
| `metadata` | dict | ❌ | Additional metadata |
| `relevance_scores` | list[float] | ❌ | Score per passage |

---

## DiagnosisResult (Diagnostic Agent → Remediation Agent)

| Field | Type | Required | Description |
|---|---|---|---|
| `hypotheses` | list[Hypothesis] | ✅ | All hypotheses considered |
| `probable_root_cause` | string | ✅ | Most probable root cause |
| `evidence_ids` | list[string] | ❌ | Supporting evidence IDs |
| `confidence` | float [0,1] | ✅ | Overall confidence |
| `affected_components` | list[string] | ❌ | Root-cause component IDs |

---

## RemediationProposal (Remediation Agent → Oversight Agent)

| Field | Type | Required | Description |
|---|---|---|---|
| `action_id` | string | ✅ | Unique action identifier |
| `target` | string | ✅ | Target device or interface |
| `operation` | string | ✅ | Allow-listed operation name |
| `parameters` | dict | ❌ | Operation parameters |
| `risk` | RiskLevel enum | ✅ | Classified risk level |
| `expected_effect` | string | ✅ | Human-readable expected outcome |
| `verification_condition` | string | ✅ | Post-execution check condition |

---

## ApprovalState (Oversight Agent ↔ Human Reviewer)

| Field | Type | Required | Description |
|---|---|---|---|
| `status` | ApprovalStatus enum | ✅ | Current approval status |
| `reviewer_action` | ReviewerAction enum | ❌ | Human reviewer's action |
| `timestamp` | datetime | ❌ | Time of review decision |
| `comments` | string | ❌ | Reviewer notes |
| `policy_violations` | list[string] | ❌ | Failed policy checks |
| `requires_human_approval` | bool | ✅ | Always true for state-changing ops |

---

## VerificationResult (Post-Executor Verification)

| Field | Type | Required | Description |
|---|---|---|---|
| `checks` | list[VerificationCheck] | ❌ | Individual verification checks |
| `observed_state` | dict | ❌ | Actual network state observed |
| `expected_state` | dict | ❌ | Expected network state |
| `success` | bool | ✅ | True only if ALL checks pass |
| `failure_reason` | string | ❌ | Explanation if success=False |

> **Critical**: `success=True` on the executor does NOT imply `success=True` here.
> Execution success ≠ network recovery. Verification determines recovery.

---

## Enumerations

### EventType
`bgp_neighbor_down`, `bgp_neighbor_up`, `bgp_anomaly`, `port_flap`, `port_down`,
`port_up`, `port_admin_shutdown`, `ospf_neighbor_down`, `ospf_neighbor_up`,
`ospf_adjacency_failure`, `vlan_fault`, `connectivity_fault`, `unknown`

### Severity
`critical`, `high`, `medium`, `low`, `info`

### RiskLevel
`low`, `medium`, `high`, `critical`

### ReviewerAction
`approve`, `reject`, `edit`, `request_more_diagnosis`

### ApprovalStatus
`pending`, `approved`, `rejected`, `needs_more_diagnosis`
