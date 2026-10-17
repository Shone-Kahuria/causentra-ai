import os

from fastapi.testclient import TestClient

os.environ["CAUSENTRA_ANALYST_TOKEN"] = "test-analyst-token"

from app import inference, main


def test_api_persists_success_and_failure_traces(tmp_path, monkeypatch):
    main.DB_PATH = tmp_path / "trace.db"
    monkeypatch.setenv("AMD_CHAT_COMPLETIONS_URL", "https://amd.example/v1/chat/completions")
    monkeypatch.setenv("AMD_MODEL_ID", "open-model")
    monkeypatch.setenv("AMD_API_KEY", "test-secret")
    headers = {"Authorization": "Bearer test-analyst-token"}
    event = {"external_id": "trace-event", "type": "supplier_delivery_delayed",
             "supplier_id": "SUP-01", "purchase_order_id": "PO-01", "delay_days": 3,
             "occurred_at": "2026-10-18T00:00:00Z"}
    with TestClient(main.app) as client:
        incident_id = client.post("/api/v1/events", json=event, headers=headers).json()["incident_id"]
        def success(packet, trace_id):
            return inference.Investigation(summary="Supplier delay risks orders.", hypotheses=[
                inference.Hypothesis(claim="Inbound is late.", evidence_ids=[packet[0]["id"]],
                                     confidence=0.9, alternatives=[])],
                missing_information=[], recommended_next_step="Review simulations."), {
                    "model_id": "open-model", "provider_request_id": "amd-request-1", "usage": {"total_tokens": 42}}
        monkeypatch.setattr(inference, "investigate", success)
        response = client.post(f"/api/v1/incidents/{incident_id}/investigate", headers=headers)
        assert response.status_code == 200
        result = response.json()
        assert result["amd_inference_invoked"] is True
        trace = client.get(f"/api/v1/agent-runs/{result['run_id']}", headers=headers).json()
        assert trace["provider_request_id"] == "amd-request-1"
        assert trace["usage"]["total_tokens"] == 42
        assert len(trace["evidence_hash"]) == 64

        def fail(_packet, _trace_id):
            raise inference.InferenceError("Model cited an unknown evidence ID")
        monkeypatch.setattr(inference, "investigate", fail)
        bad = client.post(f"/api/v1/incidents/{incident_id}/investigate", headers=headers)
        assert bad.status_code == 502
        failed_id = bad.json()["detail"]["run_id"]
        assert client.get(f"/api/v1/agent-runs/{failed_id}", headers=headers).json()["status"] == "failed"
