# Causentra AI

Runnable vertical slice of the synthetic supplier delay scenario. It demonstrates event ingestion, an evidence path, deterministic simulation, manager approval, sandbox execution, an audit trail, replay, and a small rules baseline evaluation. An AMD inference adapter is implemented but needs an approved endpoint and credentials before it can be called live. Without these, the investigation endpoint explicitly reports a rules-only precheck.

## Run locally

Requires Python 3.12+.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:CAUSENTRA_ANALYST_TOKEN = 'choose-a-long-random-analyst-token'
$env:CAUSENTRA_MANAGER_TOKEN = 'choose-a-different-long-random-manager-token'
python -m uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. Connect with an analyst token to inject the example delay, review evidence, compare scenarios, and create a proposal. Connect with the manager token to approve and execute it. The database is created at `causentra.db` on first start. API documentation is at `/docs`. For tests, install `requirements-dev.txt` and run `python -m pytest -q`.

Use `CAUSENTRA_DB` to place the SQLite database elsewhere. The seeded data belongs to the synthetic `demo-retailer` tenant. `CAUSENTRA_TOKENS_JSON` can map additional random bearer tokens to an `organization_id`, `actor`, and `analyst`, `manager`, or read-only `auditor` role; all business reads and writes are tenant-filtered. The demo token system is not a production OIDC replacement. PostgreSQL, queue workers, and live AMD verification remain future deployment work.

Container run: set the two token variables in your shell, then run `docker compose up --build`. Do not commit real keys. The container keeps demo data in a named Docker volume.

## AMD integration

Sign in to the [event Token Factory](https://notebooks.amd.com/tokenfactory) with your AMD account. Set `AMD_CHAT_COMPLETIONS_URL` to the complete chat completions URL shown there, plus its model ID and API key in `AMD_MODEL_ID` and `AMD_API_KEY`. `POST /api/v1/incidents/{id}/investigate` then sends only the curated evidence packet, checks JSON structure and cited evidence IDs, and stores a trace at `GET /api/v1/agent-runs/{id}`. The trace includes model ID, provider request ID when available, token usage, latency, evidence hash, and prompt version. Unknown evidence IDs are rejected; semantic claim support remains a human review step. Transport or validation errors are recorded and returned; they are not silently labeled successful. The adapter first requests JSON mode and retries once without it if the gateway returns 400 or 422. Confirm the endpoint's contract before claiming live integration.

The app also reads an ignored `.env` file in the project root. Open it locally and fill `AMD_CHAT_COMPLETIONS_URL`, `AMD_MODEL_ID`, and `AMD_API_KEY`; never commit it or paste the key into chat. Run `python -m app.smoke_amd` after filling them. It makes one real request and prints a trace ID, model ID, usage, and validated citation IDs without printing the key.

The [official Act III brief](https://lablab.ai/ai-hackathons/amd-developer-hackathon-act-iii?track=evolus-business-agents-on-amd) requires a meaningful AMD workload in the judged product. Evolus is optional for the main challenge; its partner track requires an event workspace, an open model served through your own vLLM endpoint on AMD Developer Cloud, two Evolus building blocks, and app-driven API calls. These external requirements still need workspace setup and live verification.

For the optional Evolus track, set `EVOLUS_API_KEY`, `EVOLUS_APPLICATION_ID`, `EVOLUS_WORKFLOW_ID`, and `EVOLUS_AI_TOOL` for an event workspace where a workflow and AI Tool have been created and the AMD model is connected. Confirm that the workflow cannot make live purchases, then set `EVOLUS_SANDBOX_CONFIRMED=true`. A manager can invoke both blocks with `POST /api/v1/incidents/{id}/evolus`; the response records trace and execution IDs. The adapter request bodies are based on the public brief and must be checked against the workspace's interactive API reference before live use.

## Replay and measured baseline

`python -m app.demo replay` resets the local synthetic incident and prints deterministic simulation outputs. `python -m app.demo reset` clears event, incident, action and audit records. `python -m app.evaluation` exports the seven-case rules baseline as JSON; `GET /api/v1/evaluations` serves the same report. The payment-failure case is an intentional false negative for the inventory-only rule. This baseline does not claim model or multi-agent benchmark results.

## Deterministic demo calculation

The seeded product starts with 20 units on hand, 4 reserved, seven days of synthetic demand history `[7, 9, 8, 8, 7, 9, 8]`, and a confirmed inbound 40 units due in 2 days. The seven-day moving average forecasts 8 units per day. A 3 day supplier delay moves the receipt to day 5. Across a 3 day horizon, forecast demand is 24 units (observed-history range 21-27) and available supply is 16, yielding an 8 unit projected shortfall. The range is not a statistical confidence interval. Only 20 units belong to placed customer orders, so 4 of those order units are delayed. Standard allocation puts $500 of high-priority order revenue at risk; priority allocation puts $300 of normal-order revenue at risk. The sandbox expedited option adds 8 units at $7.50 incremental cost each. These are synthetic planning estimates, not realized financial outcomes.

## Remaining external gates

1. Set the three Token Factory variables and run `python -m app.smoke_amd`; save the non-secret trace metadata as proof of a real AMD call.
2. Add the deployed application URL and public repository to the hackathon submission. Live hosting and publication require the user's account access.
3. If entering the Evolus partner track, configure its event workspace and verify two live building-block calls. The main challenge does not require Evolus.

The current application is a synthetic hackathon demo, not a production ERP. OIDC, PostgreSQL, queue workers, and larger held-out evaluations remain outside this local deliverable.
