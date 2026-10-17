import json

import httpx
import pytest

from app import inference


def test_amd_adapter_validates_citations_and_records_model(monkeypatch):
    monkeypatch.setenv("AMD_CHAT_COMPLETIONS_URL", "https://amd.example/v1/chat/completions")
    monkeypatch.setenv("AMD_MODEL_ID", "open-model")
    monkeypatch.setenv("AMD_API_KEY", "test-secret")
    report = {"summary": "Shipment is delayed.", "hypotheses": [
        {"claim": "Inbound stock misses the horizon.", "evidence_ids": ["E-1"],
         "confidence": 0.8, "alternatives": ["Demand may vary."]}],
        "missing_information": [], "recommended_next_step": "Review simulations."}
    def handler(request):
        assert request.headers["authorization"] == "Bearer test-secret"
        assert request.headers["x-trace-id"] == "trace-1"
        return httpx.Response(200, json={"model": "open-model", "choices": [
            {"message": {"content": json.dumps(report)}}], "usage": {"total_tokens": 42}})
    transport = httpx.MockTransport(handler)
    original = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=transport, **kw))
    result, metadata = inference.investigate([{"id": "E-1", "type": "event", "content": {"delay_days": 3}}], "trace-1")
    assert result.hypotheses[0].evidence_ids == ["E-1"]
    assert metadata["usage"]["total_tokens"] == 42
    report["hypotheses"][0]["evidence_ids"] = ["invented"]
    with pytest.raises(inference.InferenceError):
        inference.investigate([{"id": "E-1", "type": "event", "content": {"delay_days": 3}}], "trace-1")
