"""Populate an empty local database with clearly synthetic incidents.

Usage: python -m app.seed_demo
This never clears existing records or overwrites a populated database.
"""
from .db import connection, event, initialize, utcnow

SAMPLES = [
    ("Checkout API returning 503 responses", "Synthetic: elevated 5xx error rate during checkout.", "Checkout API", "P1", "investigating", "Platform Support"),
    ("Delayed order processing jobs", "Synthetic: background queue backlog above normal levels.", "Order Worker", "P2", "mitigated", "Backend Team"),
    ("Intermittent DNS lookup failures", "Synthetic: resolver errors reported for test endpoints.", "DNS Gateway", "P2", "open", "Cloud Support"),
    ("Certificate renewal reminder", "Synthetic: test TLS certificate approaching expiry.", "Edge Proxy", "P3", "open", "Infrastructure"),
    ("Database connections exhausted", "Synthetic: connection pool saturation in staging.", "Customer Database", "P1", "resolved", "Database Operations"),
    ("Monitoring agent timeout", "Synthetic: polling delayed by a test collector.", "Metrics Agent", "P3", "investigating", "Site Reliability"),
    ("Dashboard styling regression", "Synthetic: non-critical UI layout issue after release.", "Admin Dashboard", "P4", "resolved", "Frontend Team"),
    ("Email notification delay", "Synthetic: outbound notifications queued beyond target latency.", "Mail Relay", "P3", "open", ""),
]


def main() -> int:
    initialize()
    now = utcnow()
    with connection() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
        if existing:
            print(f"Database already contains {existing} incident(s). No seed changes made.")
            return 0
        for title, description, service, severity, status, owner in SAMPLES:
            resolved = now if status == "resolved" else None
            cursor = conn.execute(
                """INSERT INTO incidents
                   (title,description,service,severity,status,owner,created_at,updated_at,resolved_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (title, description, service, severity, status, owner, now, now, resolved),
            )
            incident_id = cursor.lastrowid
            event(conn, incident_id, "created", "Synthetic demo incident created")
            if status != "open":
                event(conn, incident_id, "updated", f"Demo lifecycle status: {status}")
    print(f"Added {len(SAMPLES)} synthetic incident records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
