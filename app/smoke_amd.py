"""Run a real, schema-validated AMD endpoint smoke test without printing secrets."""
from __future__ import annotations

import json
from uuid import uuid4

from app.inference import InferenceError, configured, investigate


def main():
    if not configured():
        raise SystemExit("Set AMD_CHAT_COMPLETIONS_URL, AMD_MODEL_ID and AMD_API_KEY first")
    trace_id = str(uuid4())
    evidence = [{"id": "smoke-event-001", "type": "supplier_delay_event", "content": {"delay_days": 3}},
                {"id": "smoke-order-001", "type": "purchase_order", "content": {"quantity": 40, "expected_in_days": 2}}]
    try:
        result, metadata = investigate(evidence, trace_id)
    except InferenceError as exc:
        raise SystemExit(f"Smoke test failed: {exc}") from exc
    print(json.dumps({"trace_id": trace_id, "model_id": metadata["model_id"],
                      "provider_request_id": metadata["provider_request_id"],
                      "usage": metadata["usage"], "schema_valid": True,
                      "cited_evidence_ids": [h.evidence_ids for h in result.hypotheses]}, indent=2))


if __name__ == "__main__":
    main()
