// MongoDB initialization schema — runs once when the container first starts.
// File is placed in /docker-entrypoint-initdb.d/ inside the MongoDB container.

db = db.getSiblingDB("cnt_fault_diagnosis");

// ─── Collections ─────────────────────────────────────────────────────────────

db.createCollection("incidents");
db.createCollection("events");
db.createCollection("incident_timelines");
db.createCollection("diagnoses");
db.createCollection("remediation_proposals");
db.createCollection("approvals");
db.createCollection("execution_results");
db.createCollection("verification_results");
db.createCollection("audit_records");

// ─── Indexes ──────────────────────────────────────────────────────────────────

// incidents
db.incidents.createIndex({ incident_id: 1 }, { unique: true });
db.incidents.createIndex({ created_at: -1 });
db.incidents.createIndex({ status: 1 });

// events
db.events.createIndex({ event_id: 1 }, { unique: true });
db.events.createIndex({ incident_id: 1 });
db.events.createIndex({ timestamp: -1 });
db.events.createIndex({ device_id: 1 });

// incident_timelines
db.incident_timelines.createIndex({ incident_id: 1 }, { unique: true });

// diagnoses
db.diagnoses.createIndex({ incident_id: 1 });
db.diagnoses.createIndex({ created_at: -1 });

// remediation_proposals
db.remediation_proposals.createIndex({ action_id: 1 }, { unique: true });
db.remediation_proposals.createIndex({ incident_id: 1 });

// approvals
db.approvals.createIndex({ action_id: 1 });
db.approvals.createIndex({ status: 1 });

// audit_records
db.audit_records.createIndex({ timestamp: -1 });
db.audit_records.createIndex({ incident_id: 1 });
db.audit_records.createIndex({ action_type: 1 });

print("CNT database initialized with collections and indexes.");
