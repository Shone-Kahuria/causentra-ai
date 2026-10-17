import os
import json

os.environ["CAUSENTRA_DB"] = ":memory:"  # replaced with a temporary file in fixture
os.environ["CAUSENTRA_ANALYST_TOKEN"] = "test-analyst-token"
os.environ["CAUSENTRA_MANAGER_TOKEN"] = "test-manager-token"

import pytest
from fastapi.testclient import TestClient
from app import main


@pytest.fixture
def client(tmp_path):
    main.DB_PATH = tmp_path / "test.db"
    with TestClient(main.app) as test_client:
        yield test_client


def auth(role="analyst"):
    return {"Authorization": f"Bearer test-{role}-token"}


def event():
    return {"external_id": "demo-delay-001", "type": "supplier_delivery_delayed",
            "supplier_id": "SUP-01", "purchase_order_id": "PO-01", "delay_days": 3,
            "occurred_at": "2026-10-18T00:00:00Z"}


def test_full_sandbox_path_and_idempotency(client):
    assert "Command Center" in client.get("/").text
    assert client.get("/api/v1/dashboard").status_code == 401
    first = client.post("/api/v1/events", json=event(), headers=auth())
    assert first.status_code == 202
    second = client.post("/api/v1/events", json=event(), headers=auth())
    assert second.json()["duplicate"] is True
    assert second.json()["incident_id"] == first.json()["incident_id"]
    incident_id = first.json()["incident_id"]

    evidence = client.get(f"/api/v1/incidents/{incident_id}/evidence", headers=auth()).json()
    assert len(evidence["paths"]) == 2
    assert first.json()["event_id"] in {item["id"] for item in evidence["evidence"]}

    simulation = client.get(f"/api/v1/incidents/{incident_id}/simulations", headers=auth()).json()
    assert simulation["demand_units"] == 24
    assert simulation["forecast"]["history_units"] == [7, 9, 8, 8, 7, 9, 8]
    assert simulation["forecast"]["lower_units"] == 21
    assert simulation["forecast"]["upper_units"] == 27
    assert simulation["available_units"] == 16
    assert simulation["projected_shortage_units"] == 8
    assert simulation["scenarios"][0]["revenue_exposure_cents"] == 50000
    assert simulation["scenarios"][1]["revenue_exposure_cents"] == 30000
    assert simulation["scenarios"][2]["incremental_cost_cents"] == 6000
    assert simulation["scenarios"][2]["shortfall_units"] == 0

    investigation = client.post(f"/api/v1/incidents/{incident_id}/investigate", headers=auth()).json()
    assert investigation["amd_inference_invoked"] is False
    assert set(investigation["hypotheses"][0]["evidence_ids"]).issubset(
        {item["id"] for item in evidence["evidence"]})

    proposal = client.post(f"/api/v1/incidents/{incident_id}/proposals", headers=auth()).json()
    proposal_id = proposal["id"]
    assert client.post(f"/api/v1/actions/{proposal_id}/execute", headers=auth("manager")).status_code == 403
    assert client.post(f"/api/v1/actions/{proposal_id}/approve", headers=auth()).status_code == 403
    assert client.post(f"/api/v1/actions/{proposal_id}/approve", headers=auth("manager")).json()["status"] == "approved"
    execution = client.post(f"/api/v1/actions/{proposal_id}/execute", headers=auth("manager"))
    assert execution.status_code == 202
    assert execution.json()["status"] == "executed"
    assert execution.json()["sandbox_receipt"]["residual_shortfall_units"] == 0
    assert execution.json()["sandbox_receipt"]["result"] == "simulated_covered"
    assert client.post(f"/api/v1/actions/{proposal_id}/execute", headers=auth("manager")).json()["duplicate"] is True
    assert client.get("/api/v1/dashboard", headers=auth()).json()["open_incidents"] == 0
    assert len(client.get("/api/v1/audit", headers=auth()).json()) == 4


def test_event_validation_and_tenant_reference(client):
    bad = event()
    bad["delay_days"] = -1
    assert client.post("/api/v1/events", json=bad, headers=auth()).status_code == 422
    bad = event()
    bad["purchase_order_id"] = "PO-OTHER"
    assert client.post("/api/v1/events", json=bad, headers=auth()).status_code == 422
    assert client.post("/api/v1/events", json=event(), headers=auth()).status_code == 202
    changed = event()
    changed["delay_days"] = 4
    assert client.post("/api/v1/events", json=changed, headers=auth()).status_code == 409


def test_adjustable_simulation_and_incident_pagination(client, monkeypatch):
    first_id = client.post("/api/v1/events", json=event(), headers=auth()).json()["incident_id"]
    second = event()
    second["external_id"] = "demo-delay-002"
    second_id = client.post("/api/v1/events", json=second, headers=auth()).json()["incident_id"]
    page = client.get("/api/v1/incidents?limit=1&offset=0&status=open", headers=auth()).json()
    assert page["total"] == 2 and len(page["items"]) == 1
    next_page = client.get("/api/v1/incidents?limit=1&offset=1&status=open", headers=auth()).json()
    assert {page["items"][0]["id"], next_page["items"][0]["id"]} == {first_id, second_id}
    assert client.get("/api/v1/incidents?limit=0", headers=auth()).status_code == 422

    custom = client.post("/api/v1/simulations", headers=auth(), json={
        "incident_id": first_id, "horizon_days": 4, "expedite_units": 2,
        "expedite_unit_cost_cents": 900}).json()
    assert custom["demand_units"] == 32
    assert custom["projected_shortage_units"] == 16
    expedited = custom["scenarios"][2]
    assert expedited["shortfall_units"] == 14
    assert expedited["incremental_cost_cents"] == 1800
    assert expedited["revenue_exposure_cents"] == 15000
    assert expedited["orders_delayed"] == 1
    assert expedited["score_cents"] == 19300
    assert client.post("/api/v1/simulations", headers=auth(), json={
        "incident_id": first_id, "horizon_days": 1}).status_code == 422
    monkeypatch.setenv("CAUSENTRA_TOKENS_JSON", json.dumps({
        "other-token": {"role": "manager", "actor": "other", "organization_id": "other-org"}}))
    other = {"Authorization": "Bearer other-token"}
    assert client.post("/api/v1/simulations", headers=other, json={"incident_id": first_id}).status_code == 404
    assert client.get("/api/v1/incidents", headers=other).json()["total"] == 0


def test_tenant_boundaries_and_auditor_read_only(client, monkeypatch):
    monkeypatch.setenv("CAUSENTRA_TOKENS_JSON", json.dumps({
        "other-token": {"role": "manager", "actor": "other-manager", "organization_id": "other-org"},
        "audit-token": {"role": "auditor", "actor": "demo-auditor", "organization_id": "demo-retailer"}}))
    incident_id = client.post("/api/v1/events", json=event(), headers=auth()).json()["incident_id"]
    other = {"Authorization": "Bearer other-token"}
    auditor = {"Authorization": "Bearer audit-token"}
    assert client.get("/api/v1/dashboard", headers=other).json()["open_incidents"] == 0
    assert client.get(f"/api/v1/incidents/{incident_id}", headers=other).status_code == 404
    assert client.post(f"/api/v1/incidents/{incident_id}/proposals", headers=other).status_code == 404
    assert client.post("/api/v1/events", json=event(), headers=other).status_code == 422
    assert client.get(f"/api/v1/incidents/{incident_id}", headers=auditor).status_code == 200
    assert client.post(f"/api/v1/incidents/{incident_id}/proposals", headers=auditor).status_code == 403
    assert client.post("/api/v1/events", json=event(), headers=auditor).status_code == 403


def test_manager_cannot_self_approve(client):
    incident_id = client.post("/api/v1/events", json=event(), headers=auth("manager")).json()["incident_id"]
    proposal_id = client.post(f"/api/v1/incidents/{incident_id}/proposals", headers=auth("manager")).json()["id"]
    assert client.post(f"/api/v1/actions/{proposal_id}/approve", headers=auth("manager")).status_code == 403


def test_rejection_and_sandbox_rollback(client):
    incident_id = client.post("/api/v1/events", json=event(), headers=auth()).json()["incident_id"]
    proposal_id = client.post(f"/api/v1/incidents/{incident_id}/proposals", headers=auth()).json()["id"]
    assert client.post(f"/api/v1/actions/{proposal_id}/reject", headers=auth()).status_code == 403
    assert client.post(f"/api/v1/actions/{proposal_id}/reject", headers=auth("manager")).json()["status"] == "rejected"
    assert client.post(f"/api/v1/actions/{proposal_id}/execute", headers=auth("manager")).status_code == 403

    # A fresh proposal is required after rejection; use a separate seeded incident.
    second = event()
    second["external_id"] = "demo-delay-002"
    second_id = client.post("/api/v1/events", json=second, headers=auth()).json()["incident_id"]
    action_id = client.post(f"/api/v1/incidents/{second_id}/proposals", headers=auth()).json()["id"]
    client.post(f"/api/v1/actions/{action_id}/approve", headers=auth("manager"))
    client.post(f"/api/v1/actions/{action_id}/execute", headers=auth("manager"))
    assert client.post(f"/api/v1/actions/{action_id}/rollback", headers=auth("manager")).json()["status"] == "rolled_back"
    assert client.get(f"/api/v1/incidents/{second_id}", headers=auth()).json()["status"] == "open"
