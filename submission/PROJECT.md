# Causentra AI — submission copy

**Challenge:** Reinvent Commerce
**Status:** Submitted to the AMD Developer Hackathon ACT III on lablab.ai. Local working prototype and public source repository; AMD live trace pending Token Factory access. No public app hosting requested.

**Published submission:** https://lablab.ai/ai-hackathons/amd-developer-hackathon-act-iii/causentra-ai/causentra-ai

## Short description

Causentra AI turns supplier delays into evidence-linked inventory forecasts, comparable interventions, and manager-approved sandbox actions.

## Long description

Retail teams see delayed shipments in one system, stock levels in another, and customer orders elsewhere. Causentra AI connects those records into a supplier-to-order impact path. Its deterministic forecast estimates a shortfall and an observed-history range. An AMD-hosted open model, once connected through the event Token Factory, investigates the curated evidence and must cite record IDs; the backend rejects unknown IDs and labels semantic support for human review. The operator compares waiting, prioritizing high-value orders, and expedited supply. Expedited purchasing remains a sandbox proposal until a separate manager approves it, and every action gets an audit record and verification receipt.

The prototype uses synthetic data and makes no live supplier purchase. The demo starts with a three-day delivery delay. It projects an eight-unit shortfall over three days, with a 21–27 unit demand range. Allocation choices put either $500 of high-priority order revenue or $300 of normal-order revenue at risk. The sandbox expedited option covers eight units at $60 incremental cost. These are scenario estimates, not realized savings.

## Technology tags

AMD Developer Cloud / Token Factory (pending live verification), Python, FastAPI, SQLite, Docker, deterministic forecasting, evidence-grounded AI, operational graph, human approval.

## Four-minute demo sequence

1. Open the Command Center and show the clean synthetic dashboard.
2. Inject the fixed supplier delay; show the event receipt and incident.
3. Open dependency paths and evidence IDs. Run investigation; show the AMD trace only after a real call has succeeded.
4. Compare the three deterministic scenarios and their assumptions, exposure, costs, and score.
5. Create an expedite proposal as analyst; show execution blocked before approval.
6. Approve and execute as manager; show sandbox receipt, incident resolution, audit log, and optional rollback.
7. Show the seven-case rules baseline and its limitations, including the payment-failure false negative.

## Evidence to capture before submission

- Successful `python -m app.smoke_amd` output with trace ID, model ID, citation IDs, and token usage.
- Screenshot or recording of a completed AMD investigation and `GET /api/v1/agent-runs/{id}` metadata.
- Public GitHub repository, captioned demo video, and locally runnable prototype.
- Container build result and `python -m pytest -q` result.
- If selecting the Evolus partner track: event workspace with connected AMD model, two building blocks, and API execution IDs.

## Known limits

Data are synthetic; the demand range is not a statistical confidence interval. The rules baseline has seven cases and does not establish real-world accuracy. Current credentials are demo bearer tokens and persistence is SQLite. The app does not make real purchases.
