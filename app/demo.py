"""Reset and replay the fixed synthetic incident from the command line."""
from __future__ import annotations

import argparse
import json

from app import main


def reset():
    main.init_db()
    with main.db() as conn:
        for table in ("action_receipts", "agent_runs", "audit_logs", "proposals", "incidents", "events"):
            conn.execute(f"DELETE FROM {table}")


def replay():
    reset()
    with main.db() as conn:
        event_id = "demo-event-001"
        incident_id = "demo-incident-001"
        conn.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?)",
                     (event_id, main.ORG, "demo-delay-001", "supplier_delivery_delayed", "SUP-01", "PO-01", 3, "2026-10-18T00:00:00+00:00"))
        conn.execute("INSERT INTO incidents VALUES (?,?,?,?,?,?)",
                     (incident_id, main.ORG, event_id, "high", "open", "2026-10-18T00:00:00+00:00"))
        return main.calculate(conn, main.find_incident(conn, incident_id, main.ORG), main.ORG)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["reset", "replay"])
    args = parser.parse_args()
    if args.command == "reset":
        reset()
        print("Demo reset complete")
    else:
        print(json.dumps(replay(), indent=2))
