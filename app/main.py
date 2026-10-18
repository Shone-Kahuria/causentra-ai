"""First Causentra vertical slice: synthetic supplier delay, decisions and audit."""
from __future__ import annotations

import hmac
import hashlib
import json
import os
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from app import config  # loads local .env before DB_PATH and request handling
from app import evolus, inference
from app.evaluation import evaluate

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("CAUSENTRA_DB", str(ROOT / "causentra.db")))
ORG = "demo-retailer"

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Causentra AI", version="0.1.0", lifespan=lifespan)


@contextmanager
def db():
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    if DB_PATH != Path(":memory:"):
        connection.execute("PRAGMA journal_mode = WAL")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def row_dict(row):
    return dict(row) if row else None


def audit(conn, organization_id: str, actor: str, action: str, object_ref: str, result: str):
    conn.execute(
        "INSERT INTO audit_logs (id, organization_id, actor, action, object_ref, result, created_at) VALUES (?,?,?,?,?,?,?)",
        (str(uuid4()), organization_id, actor, action, object_ref, result, now()),
    )


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS suppliers (
            id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, name TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS products (
            id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, supplier_id TEXT NOT NULL,
            name TEXT NOT NULL, FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
        );
        CREATE TABLE IF NOT EXISTS inventory (
            product_id TEXT PRIMARY KEY, on_hand INTEGER NOT NULL CHECK(on_hand >= 0),
            reserved INTEGER NOT NULL CHECK(reserved >= 0), daily_demand INTEGER NOT NULL CHECK(daily_demand >= 0),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );
        CREATE TABLE IF NOT EXISTS demand_history (
            organization_id TEXT NOT NULL, product_id TEXT NOT NULL, day_index INTEGER NOT NULL,
            units INTEGER NOT NULL CHECK(units >= 0),
            PRIMARY KEY (organization_id, product_id, day_index),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );
        CREATE TABLE IF NOT EXISTS purchase_orders (
            id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, supplier_id TEXT NOT NULL,
            product_id TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity >= 0),
            expected_in_days INTEGER NOT NULL, status TEXT NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products(id)
        );
        CREATE TABLE IF NOT EXISTS customer_orders (
            id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, product_id TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity >= 0), unit_price_cents INTEGER NOT NULL CHECK(unit_price_cents >= 0),
            priority TEXT NOT NULL, FOREIGN KEY (product_id) REFERENCES products(id)
        );
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, external_id TEXT NOT NULL,
            type TEXT NOT NULL, supplier_id TEXT NOT NULL, purchase_order_id TEXT NOT NULL,
            delay_days INTEGER NOT NULL CHECK(delay_days >= 0), occurred_at TEXT NOT NULL,
            UNIQUE(organization_id, external_id)
        );
        CREATE TABLE IF NOT EXISTS incidents (
            id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, source_event_id TEXT NOT NULL UNIQUE,
            severity TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
            FOREIGN KEY (source_event_id) REFERENCES events(id)
        );
        CREATE TABLE IF NOT EXISTS proposals (
            id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, incident_id TEXT NOT NULL,
            type TEXT NOT NULL, quantity INTEGER NOT NULL, incremental_cost_cents INTEGER NOT NULL,
            status TEXT NOT NULL, created_by TEXT, approved_by TEXT, executed_at TEXT,
            UNIQUE(incident_id, type), FOREIGN KEY (incident_id) REFERENCES incidents(id)
        );
        CREATE TABLE IF NOT EXISTS audit_logs (
            id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, actor TEXT NOT NULL,
            action TEXT NOT NULL, object_ref TEXT NOT NULL, result TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS action_receipts (
            id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL UNIQUE, organization_id TEXT NOT NULL,
            quantity INTEGER NOT NULL, residual_shortfall_units INTEGER NOT NULL,
            result TEXT NOT NULL, created_at TEXT NOT NULL,
            FOREIGN KEY (proposal_id) REFERENCES proposals(id)
        );
        CREATE TABLE IF NOT EXISTS agent_runs (
            id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, incident_id TEXT NOT NULL,
            trace_id TEXT NOT NULL UNIQUE, status TEXT NOT NULL, model_id TEXT,
            latency_ms INTEGER, response_json TEXT, error_code TEXT, created_at TEXT NOT NULL,
            provider_request_id TEXT, usage_json TEXT, evidence_hash TEXT, prompt_version TEXT,
            FOREIGN KEY (incident_id) REFERENCES incidents(id)
        );
        """)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(proposals)")}
        if "created_by" not in columns:
            conn.execute("ALTER TABLE proposals ADD COLUMN created_by TEXT")
        run_columns = {row["name"] for row in conn.execute("PRAGMA table_info(agent_runs)")}
        for name in ("provider_request_id", "usage_json", "evidence_hash", "prompt_version"):
            if name not in run_columns:
                conn.execute(f"ALTER TABLE agent_runs ADD COLUMN {name} TEXT")
        if not conn.execute("SELECT 1 FROM suppliers WHERE id='SUP-01'").fetchone():
            conn.execute("INSERT INTO suppliers VALUES (?,?,?)", ("SUP-01", ORG, "Northstar Components"))
            conn.execute("INSERT INTO products VALUES (?,?,?,?)", ("SKU-01", ORG, "SUP-01", "Sensor Module"))
            conn.execute("INSERT INTO inventory VALUES (?,?,?,?)", ("SKU-01", 20, 4, 8))
            conn.execute("INSERT INTO purchase_orders VALUES (?,?,?,?,?,?,?)", ("PO-01", ORG, "SUP-01", "SKU-01", 40, 2, "confirmed"))
            conn.execute("INSERT INTO customer_orders VALUES (?,?,?,?,?,?)", ("CO-01", ORG, "SKU-01", 12, 12500, "high"))
            conn.execute("INSERT INTO customer_orders VALUES (?,?,?,?,?,?)", ("CO-02", ORG, "SKU-01", 8, 7500, "normal"))
        for day_index, units in enumerate((7, 9, 8, 8, 7, 9, 8), start=1):
            conn.execute("INSERT OR IGNORE INTO demand_history VALUES (?,?,?,?)", (ORG, "SKU-01", day_index, units))
        # The demo dataset is versioned; keep its two synthetic prices fixed.
        conn.execute("UPDATE customer_orders SET unit_price_cents=12500 WHERE id='CO-01' AND organization_id=?", (ORG,))
        conn.execute("UPDATE customer_orders SET unit_price_cents=7500 WHERE id='CO-02' AND organization_id=?", (ORG,))


def identity(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Bearer token required")
    token = authorization[7:]
    if not token or token != token.strip() or " " in token:
        raise HTTPException(401, "Invalid bearer token")
    try:
        extra_tokens = json.loads(os.getenv("CAUSENTRA_TOKENS_JSON", "{}"))
        if not isinstance(extra_tokens, dict):
            raise ValueError("token map must be an object")
    except ValueError:
        raise HTTPException(500, "Invalid token configuration")
    for secret, details in extra_tokens.items():
        if hmac.compare_digest(token, secret):
            if not isinstance(details, dict) or details.get("role") not in ("manager", "analyst", "auditor") or not details.get("organization_id"):
                raise HTTPException(500, "Invalid token configuration")
            return {"role": details["role"], "actor": details.get("actor", "configured-user"),
                    "organization_id": details["organization_id"]}
    for role in ("manager", "analyst"):
        expected = os.getenv(f"CAUSENTRA_{role.upper()}_TOKEN")
        if expected and hmac.compare_digest(token, expected):
            return {"role": role, "actor": f"demo-{role}", "organization_id": ORG}
    raise HTTPException(401, "Invalid bearer token")


def manager(user=Depends(identity)):
    if user["role"] != "manager":
        raise HTTPException(403, "Manager role required")
    return user


def operator(user=Depends(identity)):
    if user["role"] not in ("analyst", "manager"):
        raise HTTPException(403, "Operator role required")
    return user


class DelayEvent(BaseModel):
    external_id: str = Field(min_length=1, max_length=120)
    type: Literal["supplier_delivery_delayed"]
    supplier_id: str
    purchase_order_id: str
    delay_days: int = Field(ge=0, le=365)
    occurred_at: datetime


class SimulationRequest(BaseModel):
    incident_id: str
    horizon_days: int = Field(default=3, ge=2, le=14)
    expedite_units: int | None = Field(default=None, ge=0, le=1000)
    expedite_unit_cost_cents: int = Field(default=750, ge=0, le=100000)
    revenue_exposure_weight: int = Field(default=1, ge=0, le=10)
    intervention_cost_weight: int = Field(default=1, ge=0, le=10)
    order_delay_penalty_cents: int = Field(default=2500, ge=0, le=100000)


def find_incident(conn, incident_id: str, organization_id: str):
    row = conn.execute("""SELECT i.*, e.supplier_id, e.purchase_order_id, e.delay_days, e.occurred_at,
                          e.external_id, p.product_id, p.quantity AS inbound_quantity,
                          p.expected_in_days FROM incidents i JOIN events e ON e.id=i.source_event_id
                          JOIN purchase_orders p ON p.id=e.purchase_order_id
                          WHERE i.id=? AND i.organization_id=?""", (incident_id, organization_id)).fetchone()
    if not row:
        raise HTTPException(404, "Incident not found")
    return dict(row)


def calculate(conn, incident, organization_id: str, options: SimulationRequest | None = None):
    inventory = conn.execute("SELECT * FROM inventory WHERE product_id=?", (incident["product_id"],)).fetchone()
    orders = conn.execute("SELECT * FROM customer_orders WHERE product_id=? AND organization_id=? ORDER BY priority", (incident["product_id"], organization_id)).fetchall()
    options = options or SimulationRequest(incident_id=incident["id"])
    horizon = options.horizon_days
    history = [r["units"] for r in conn.execute("SELECT units FROM demand_history WHERE product_id=? AND organization_id=? ORDER BY day_index", (incident["product_id"], organization_id))]
    daily = round(sum(history) / len(history)) if history else inventory["daily_demand"]
    demand = daily * horizon
    backtest_errors = [abs(history[index] - sum(history[index-3:index]) / 3) for index in range(3, len(history))]
    forecast = {"method": "seven-day moving average" if history else "inventory fallback",
                "history_units": history, "point_units": demand,
                "lower_units": (min(history) if history else daily) * horizon,
                "upper_units": (max(history) if history else daily) * horizon,
                "backtest_mae_daily_units": round(sum(backtest_errors) / len(backtest_errors), 3) if backtest_errors else None,
                "range_note": "Observed-history scenario range, not a statistical confidence interval"}
    available = inventory["on_hand"] - inventory["reserved"]
    receipt_day = incident["expected_in_days"] + incident["delay_days"]
    if receipt_day <= horizon:
        available += incident["inbound_quantity"]
    shortage = max(0, demand - available)
    def order_exposure(supply: int, priority_first: bool):
        allocation = max(0, supply)
        ordered = sorted(orders, key=lambda item: (item["priority"] != "high") if priority_first else (item["priority"] == "high"))
        exposure, delayed = 0, 0
        for order in ordered:
            covered = min(allocation, order["quantity"])
            missing = order["quantity"] - covered
            allocation -= covered
            exposure += missing * order["unit_price_cents"]
            delayed += int(missing > 0)
        return exposure, delayed
    wait_exposure, wait_delayed = order_exposure(available, False)
    priority_exposure, priority_delayed = order_exposure(available, True)
    expedite_qty = shortage if options.expedite_units is None else options.expedite_units
    expedite_exposure, expedite_delayed = order_exposure(available + expedite_qty, True)
    scenarios = [
        {"id": "wait", "name": "Wait for supplier", "shortfall_units": shortage,
         "incremental_cost_cents": 0, "revenue_exposure_cents": wait_exposure,
         "orders_delayed": wait_delayed,
         "assumption": f"Confirmed receipt arrives on day {receipt_day}; normal orders receive current stock first."},
        {"id": "prioritize", "name": "Prioritize high-value orders", "shortfall_units": shortage,
         "incremental_cost_cents": 0, "revenue_exposure_cents": priority_exposure,
         "orders_delayed": priority_delayed,
         "assumption": "High-priority orders receive current stock first; total supply is unchanged."},
        {"id": "expedite", "name": "Sandbox expedited supply", "shortfall_units": max(0, shortage - expedite_qty),
         "incremental_cost_cents": expedite_qty * options.expedite_unit_cost_cents,
         "revenue_exposure_cents": expedite_exposure, "orders_delayed": expedite_delayed,
         "assumption": f"Alternative supplies {expedite_qty} units by day 2 at ${options.expedite_unit_cost_cents / 100:.2f} incremental cost per unit; high-priority orders receive supply first."},
    ]
    for scenario in scenarios:
        scenario["score_cents"] = (scenario["revenue_exposure_cents"] * options.revenue_exposure_weight
                                   + scenario["incremental_cost_cents"] * options.intervention_cost_weight
                                   + scenario["orders_delayed"] * options.order_delay_penalty_cents)
    return {"horizon_days": horizon, "daily_demand_units": daily, "forecast": forecast,
            "demand_units": demand, "available_units": available, "projected_shortage_units": shortage,
            "currency": "USD", "score_weights": {"revenue_exposure": options.revenue_exposure_weight,
                "incremental_cost": options.intervention_cost_weight,
                "order_delay_penalty_cents": options.order_delay_penalty_cents},
            "scenarios": scenarios}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def home():
    return FileResponse(ROOT / "app" / "static" / "index.html")


@app.post("/api/v1/events", status_code=202)
def ingest(event: DelayEvent, user=Depends(operator)):
    org = user["organization_id"]
    with db() as conn:
        existing = conn.execute("SELECT * FROM events WHERE organization_id=? AND external_id=?", (org, event.external_id)).fetchone()
        if existing:
            if (existing["type"] != event.type or existing["supplier_id"] != event.supplier_id or
                existing["purchase_order_id"] != event.purchase_order_id or existing["delay_days"] != event.delay_days or
                datetime.fromisoformat(existing["occurred_at"]) != event.occurred_at):
                raise HTTPException(409, "Idempotency key already used with different event data")
            incident = conn.execute("SELECT id FROM incidents WHERE source_event_id=?", (existing["id"],)).fetchone()
            return {"event_id": existing["id"], "incident_id": incident["id"], "duplicate": True}
        po = conn.execute("SELECT * FROM purchase_orders WHERE id=? AND supplier_id=? AND organization_id=?", (event.purchase_order_id, event.supplier_id, org)).fetchone()
        if not po:
            raise HTTPException(422, "Supplier and purchase order do not match")
        event_id, incident_id = str(uuid4()), str(uuid4())
        conn.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?)", (event_id, org, event.external_id, event.type, event.supplier_id, event.purchase_order_id, event.delay_days, event.occurred_at.isoformat()))
        severity = "high" if event.delay_days >= 2 else "medium"
        conn.execute("INSERT INTO incidents VALUES (?,?,?,?,?,?)", (incident_id, org, event_id, severity, "open", now()))
        audit(conn, org, user["actor"], "event.ingest", event_id, "created")
        return {"event_id": event_id, "incident_id": incident_id, "duplicate": False}


@app.get("/api/v1/dashboard")
def dashboard(user=Depends(identity)):
    org = user["organization_id"]
    with db() as conn:
        incidents = [dict(r) for r in conn.execute("SELECT * FROM incidents WHERE organization_id=? ORDER BY created_at DESC", (org,))]
        exposure = sum(calculate(conn, find_incident(conn, i["id"], org), org)["scenarios"][0]["revenue_exposure_cents"] for i in incidents if i["status"] != "resolved")
        queue = conn.execute("SELECT COUNT(*) FROM proposals WHERE organization_id=? AND status='pending'", (org,)).fetchone()[0]
        return {"synthetic": True, "organization_id": org, "open_incidents": sum(i["status"] != "resolved" for i in incidents),
                "revenue_exposure_cents": exposure, "currency": "USD", "pending_approvals": queue,
                "inference_status": "AMD endpoint configured; live call not yet verified" if inference.configured() else "AMD endpoint not configured", "incidents": incidents}


@app.get("/api/v1/incidents/{incident_id}")
def incident_detail(incident_id: str, user=Depends(identity)):
    with db() as conn:
        return find_incident(conn, incident_id, user["organization_id"])


@app.get("/api/v1/incidents")
def list_incidents(limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0),
                   status: Literal["open", "resolved"] | None = None, user=Depends(identity)):
    org = user["organization_id"]
    where = "WHERE organization_id=?" + (" AND status=?" if status else "")
    params = (org, status) if status else (org,)
    with db() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM incidents {where}", params).fetchone()[0]
        items = [dict(row) for row in conn.execute(
            f"SELECT * FROM incidents {where} ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?",
            (*params, limit, offset))]
    next_offset = offset + len(items) if offset + len(items) < total else None
    return {"items": items, "total": total, "limit": limit, "offset": offset,
            "next_offset": next_offset}


@app.get("/api/v1/incidents/{incident_id}/evidence")
def evidence(incident_id: str, user=Depends(identity)):
    with db() as conn:
        incident = find_incident(conn, incident_id, user["organization_id"])
        return evidence_for(conn, incident, user["organization_id"])


def evidence_for(conn, incident, organization_id: str):
        inv = row_dict(conn.execute("SELECT * FROM inventory WHERE product_id=?", (incident["product_id"],)).fetchone())
        orders = [dict(r) for r in conn.execute("SELECT * FROM customer_orders WHERE product_id=? AND organization_id=?", (incident["product_id"], organization_id))]
        return {"incident_id": incident["id"], "evidence": [
            {"id": incident["source_event_id"], "type": "supplier_delay_event", "content": {"delay_days": incident["delay_days"], "occurred_at": incident["occurred_at"]}},
            {"id": incident["purchase_order_id"], "type": "purchase_order", "content": {"quantity": incident["inbound_quantity"], "expected_in_days": incident["expected_in_days"]}},
            {"id": incident["product_id"], "type": "inventory", "content": inv},
            *({"id": o["id"], "type": "customer_order", "content": o} for o in orders)],
            "paths": [[incident["supplier_id"], incident["purchase_order_id"], incident["product_id"], o["id"]] for o in orders]}


@app.post("/api/v1/incidents/{incident_id}/investigate")
def investigate(incident_id: str, user=Depends(operator)):
    org = user["organization_id"]
    with db() as conn:
        incident = find_incident(conn, incident_id, org)
        result = calculate(conn, incident, org)
        packet = evidence_for(conn, incident, org)["evidence"]
        evidence_hash = hashlib.sha256(json.dumps(packet, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if inference.configured():
            import time
            run_id, trace_id = str(uuid4()), str(uuid4())
            started = time.monotonic()
            try:
                report, metadata = inference.investigate(packet, trace_id)
                output = {"mode": "amd_inference", "amd_inference_invoked": True,
                          "run_id": run_id, "trace_id": trace_id, **report.model_dump(),
                          "projected_shortage_units": result["projected_shortage_units"],
                          "model_id": metadata["model_id"], "provider_request_id": metadata["provider_request_id"],
                          "evidence_hash": evidence_hash, "prompt_version": inference.PROMPT_VERSION,
                          "grounding_status": "citation_ids_validated; semantic_support_requires_review"}
                conn.execute("""INSERT INTO agent_runs
                             (id,organization_id,incident_id,trace_id,status,model_id,latency_ms,response_json,error_code,created_at,provider_request_id,usage_json,evidence_hash,prompt_version)
                             VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                             (run_id, org, incident_id, trace_id, "completed", metadata["model_id"],
                              int((time.monotonic()-started)*1000), json.dumps(output), None, now(),
                              metadata["provider_request_id"], json.dumps(metadata["usage"]), evidence_hash, inference.PROMPT_VERSION))
                audit(conn, org, user["actor"], "investigation.run", run_id, "completed")
                return output
            except inference.InferenceError as exc:
                conn.execute("""INSERT INTO agent_runs
                             (id,organization_id,incident_id,trace_id,status,model_id,latency_ms,response_json,error_code,created_at,evidence_hash,prompt_version)
                             VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                             (run_id, org, incident_id, trace_id, "failed", os.getenv("AMD_MODEL_ID"),
                              int((time.monotonic()-started)*1000), None, str(exc), now(), evidence_hash, inference.PROMPT_VERSION))
                audit(conn, org, user["actor"], "investigation.run", run_id, "failed")
                conn.commit()  # Keep the failed trace even though the request returns 502.
                raise HTTPException(502, {"message": str(exc), "run_id": run_id, "trace_id": trace_id})
        return {"mode": "deterministic_precheck", "amd_inference_invoked": False,
                "summary": "Supplier delivery delay may cause a three-day inventory shortfall.",
                "hypotheses": [{"claim": "The delayed inbound delivery contributes to projected shortfall.",
                                "evidence_ids": [incident["source_event_id"], incident["purchase_order_id"], incident["product_id"]],
                                "confidence": "rule_based", "alternatives": ["Demand may differ from the fixed daily baseline."]}],
                "missing_information": ["Verified AMD endpoint and organizer workflow", "Observed demand history"],
                "projected_shortage_units": result["projected_shortage_units"]}


@app.get("/api/v1/agent-runs/{run_id}")
def agent_run(run_id: str, user=Depends(identity)):
    with db() as conn:
        row = conn.execute("SELECT * FROM agent_runs WHERE id=? AND organization_id=?", (run_id, user["organization_id"])).fetchone()
        if not row:
            raise HTTPException(404, "Run not found")
        data = dict(row)
        data["response"] = json.loads(data.pop("response_json")) if data["response_json"] else None
        data["usage"] = json.loads(data.pop("usage_json")) if data["usage_json"] else None
        return data


@app.post("/api/v1/incidents/{incident_id}/evolus")
def run_evolus(incident_id: str, user=Depends(manager)):
    org = user["organization_id"]
    with db() as conn:
        incident = find_incident(conn, incident_id, org)
        simulation = calculate(conn, incident, org)
        text = (f"Synthetic sandbox incident {incident_id}: supplier {incident['supplier_id']} delayed "
                f"purchase order {incident['purchase_order_id']} by {incident['delay_days']} days. "
                f"Projected three-day shortfall: {simulation['projected_shortage_units']} units. "
                "Summarize for human review. Do not make a real purchase.")
        trace_id = str(uuid4())
        try:
            result = evolus.run_two_blocks(text, trace_id)
            audit(conn, org, user["actor"], "evolus.invoke", incident_id, "two blocks accepted")
            return result
        except evolus.EvolusError as exc:
            audit(conn, org, user["actor"], "evolus.invoke", incident_id, "failed")
            conn.commit()
            raise HTTPException(502, {"message": str(exc), "trace_id": trace_id})


@app.get("/api/v1/incidents/{incident_id}/simulations")
def simulations(incident_id: str, user=Depends(identity)):
    with db() as conn:
        org = user["organization_id"]
        return calculate(conn, find_incident(conn, incident_id, org), org)


@app.post("/api/v1/simulations")
def simulate(request: SimulationRequest, user=Depends(identity)):
    with db() as conn:
        org = user["organization_id"]
        return calculate(conn, find_incident(conn, request.incident_id, org), org, request)


@app.post("/api/v1/incidents/{incident_id}/proposals", status_code=201)
def create_proposal(incident_id: str, user=Depends(operator)):
    org = user["organization_id"]
    with db() as conn:
        incident = find_incident(conn, incident_id, org)
        if incident["status"] == "resolved":
            raise HTTPException(409, "Incident is resolved")
        existing = conn.execute("SELECT * FROM proposals WHERE incident_id=? AND type='expedite'", (incident_id,)).fetchone()
        if existing:
            return dict(existing)
        scenario = calculate(conn, incident, org)["scenarios"][2]
        if scenario["shortfall_units"] == 0 and scenario["incremental_cost_cents"] == 0:
            raise HTTPException(409, "No shortfall to address")
        proposal_id = str(uuid4())
        conn.execute("INSERT INTO proposals (id,organization_id,incident_id,type,quantity,incremental_cost_cents,status,created_by,approved_by,executed_at) VALUES (?,?,?,?,?,?,?,?,?,?)", (proposal_id, org, incident_id, "expedite", calculate(conn, incident, org)["projected_shortage_units"], scenario["incremental_cost_cents"], "pending", user["actor"], None, None))
        audit(conn, org, user["actor"], "proposal.create", proposal_id, "pending")
        return dict(conn.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone())


def proposal(conn, proposal_id, organization_id: str):
    row = conn.execute("SELECT * FROM proposals WHERE id=? AND organization_id=?", (proposal_id, organization_id)).fetchone()
    if not row:
        raise HTTPException(404, "Proposal not found")
    return dict(row)


@app.get("/api/v1/actions")
def actions(user=Depends(identity)):
    with db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM proposals WHERE organization_id=? ORDER BY rowid DESC", (user["organization_id"],))]


@app.post("/api/v1/actions/{proposal_id}/approve")
def approve(proposal_id: str, user=Depends(manager)):
    org = user["organization_id"]
    with db() as conn:
        item = proposal(conn, proposal_id, org)
        if item["status"] == "approved":
            return item
        if item["status"] != "pending":
            raise HTTPException(409, "Proposal cannot be approved")
        if item["created_by"] == user["actor"]:
            raise HTTPException(403, "Proposer cannot approve their own action")
        if item["incremental_cost_cents"] > 100000:
            audit(conn, org, user["actor"], "proposal.approve", proposal_id, "denied: exceeds $1,000 limit")
            conn.commit()
            raise HTTPException(403, "Demo manager approval limit is $1,000")
        conn.execute("UPDATE proposals SET status='approved', approved_by=? WHERE id=?", (user["actor"], proposal_id))
        audit(conn, org, user["actor"], "proposal.approve", proposal_id, "approved")
        return proposal(conn, proposal_id, org)


@app.post("/api/v1/actions/{proposal_id}/execute", status_code=202)
def execute(proposal_id: str, user=Depends(manager)):
    org = user["organization_id"]
    with db() as conn:
        item = proposal(conn, proposal_id, org)
        if item["status"] == "executed":
            receipt = row_dict(conn.execute("SELECT * FROM action_receipts WHERE proposal_id=?", (proposal_id,)).fetchone())
            return {**item, "duplicate": True, "sandbox_receipt": receipt}
        if item["status"] != "approved":
            raise HTTPException(403, "Approval required before execution")
        incident = find_incident(conn, item["incident_id"], org)
        # Sandbox only: record a reproducible simulated verification, no external purchase.
        projected = calculate(conn, incident, org)["projected_shortage_units"]
        residual = max(0, projected - item["quantity"])
        receipt = {"id": str(uuid4()), "proposal_id": proposal_id, "organization_id": org,
                   "quantity": item["quantity"], "residual_shortfall_units": residual,
                   "result": "simulated_covered" if residual == 0 else "simulated_shortfall_remains", "created_at": now()}
        conn.execute("INSERT INTO action_receipts VALUES (?,?,?,?,?,?,?)", tuple(receipt.values()))
        conn.execute("UPDATE proposals SET status='executed', executed_at=? WHERE id=?", (now(), proposal_id))
        conn.execute("UPDATE incidents SET status=? WHERE id=?", ("resolved" if residual == 0 else "needs_review", incident["id"]))
        audit(conn, org, user["actor"], "sandbox.execute", proposal_id, receipt["result"])
        return {**proposal(conn, proposal_id, org), "duplicate": False, "sandbox_receipt": receipt}


@app.post("/api/v1/actions/{proposal_id}/reject")
def reject(proposal_id: str, user=Depends(manager)):
    org = user["organization_id"]
    with db() as conn:
        item = proposal(conn, proposal_id, org)
        if item["status"] == "rejected":
            return item
        if item["status"] != "pending":
            raise HTTPException(409, "Only pending proposals can be rejected")
        conn.execute("UPDATE proposals SET status='rejected' WHERE id=?", (proposal_id,))
        audit(conn, org, user["actor"], "proposal.reject", proposal_id, "rejected")
        return proposal(conn, proposal_id, org)


@app.post("/api/v1/actions/{proposal_id}/rollback")
def rollback(proposal_id: str, user=Depends(manager)):
    org = user["organization_id"]
    with db() as conn:
        item = proposal(conn, proposal_id, org)
        if item["status"] == "rolled_back":
            return item
        if item["status"] != "executed":
            raise HTTPException(409, "Only executed sandbox actions can be rolled back")
        conn.execute("UPDATE proposals SET status='rolled_back' WHERE id=?", (proposal_id,))
        conn.execute("UPDATE incidents SET status='open' WHERE id=? AND organization_id=?", (item["incident_id"], org))
        audit(conn, org, user["actor"], "sandbox.rollback", proposal_id, "incident reopened")
        return proposal(conn, proposal_id, org)


@app.get("/api/v1/audit")
def audit_log(user=Depends(identity)):
    with db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM audit_logs WHERE organization_id=? ORDER BY created_at DESC", (user["organization_id"],))]


@app.get("/api/v1/evaluations")
def evaluations(user=Depends(identity)):
    return evaluate()
