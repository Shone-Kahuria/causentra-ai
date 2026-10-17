import httpx
import pytest

from app import evolus


def test_evolus_two_blocks_require_sandbox_and_call_expected_paths(monkeypatch):
    monkeypatch.setenv("EVOLUS_API_KEY", "test-key")
    monkeypatch.setenv("EVOLUS_APPLICATION_ID", "test-app")
    monkeypatch.setenv("EVOLUS_WORKFLOW_ID", "wf-1")
    monkeypatch.setenv("EVOLUS_AI_TOOL", "summary")
    with pytest.raises(evolus.EvolusError):
        evolus.run_two_blocks("Synthetic test", "trace-1")
    monkeypatch.setenv("EVOLUS_SANDBOX_CONFIRMED", "true")
    seen = []
    def handler(request):
        seen.append(request.url.path)
        assert request.headers["x-apikey"] == "test-key"
        assert request.headers["x-application-id"] == "test-app"
        return httpx.Response(200, json={"id": "run-1"})
    transport = httpx.MockTransport(handler)
    original = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=transport, **kw))
    result = evolus.run_two_blocks("Synthetic test", "trace-1")
    assert result["blocks_invoked"] == ["workflow", "ai_tool"]
    assert seen == ["/api/v1/workflows/wf-1/execute", "/api/v1/ai-tools/summary/run"]
