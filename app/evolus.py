"""Optional Evolus partner-track adapter. Workspace configuration is external."""
from __future__ import annotations

import os

import httpx


class EvolusError(Exception):
    pass


def configured() -> bool:
    return all(os.getenv(name) for name in
               ("EVOLUS_API_KEY", "EVOLUS_APPLICATION_ID", "EVOLUS_WORKFLOW_ID", "EVOLUS_AI_TOOL"))


def run_two_blocks(text: str, trace_id: str) -> dict:
    """Call an event-workspace workflow and AI Tool; only redacted metadata returns."""
    if not configured():
        raise EvolusError("Evolus workspace is not configured")
    if os.getenv("EVOLUS_SANDBOX_CONFIRMED") != "true":
        raise EvolusError("Confirm Evolus workflow is sandbox-only before invoking it")
    base = os.getenv("EVOLUS_BASE_URL", "https://api.evolus.ai/api/v1").rstrip("/")
    headers = {"X-ApiKey": os.environ["EVOLUS_API_KEY"],
               "X-Application-Id": os.environ["EVOLUS_APPLICATION_ID"],
               "X-Trace-Id": trace_id}
    try:
        with httpx.Client(timeout=20.0) as client:
            workflow = client.post(f"{base}/workflows/{os.environ['EVOLUS_WORKFLOW_ID']}/execute",
                                   headers=headers, json={"text": text})
            workflow.raise_for_status()
            tool = client.post(f"{base}/ai-tools/{os.environ['EVOLUS_AI_TOOL']}/run",
                               headers=headers, json={"text": text})
            tool.raise_for_status()
        workflow_data = workflow.json()
        tool_data = tool.json()
        return {"trace_id": trace_id, "blocks_invoked": ["workflow", "ai_tool"],
                "workflow_execution_id": workflow_data.get("id") or workflow_data.get("executionId"),
                "ai_tool_run_id": tool_data.get("id") or tool_data.get("runId"),
                "workflow_http_status": workflow.status_code, "ai_tool_http_status": tool.status_code}
    except (httpx.HTTPError, ValueError) as exc:
        raise EvolusError(f"Evolus API call failed: {type(exc).__name__}") from exc
