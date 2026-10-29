# OneFlow AI

A local full-stack proof of concept for health insurance cashless assistance and reimbursement against an existing customer policy. React + TypeScript + Tailwind, FastAPI, LangGraph, Vertex AI Gemini, and Google Document AI.

**Cloud mode uses real Document AI OCR and Vertex AI calls. Demo mode uses deterministic sample parsing. Customer schedules, hospital arrangements, and cashless responses are fictional. Insurer process guidance is linked to official HDFC ERGO wording. No journey submits a claim, grants coverage, or transfers funds.**

This workspace is configured in **cloud mode** in the ignored `backend/.env`, using project `project-b222a5e1-4bfe-4261-a4e` and approved OCR processor `8dfc522a55da9b0b` in `us`. Credentials remain in local ADC. The distributable `.env.example` defaults to demo mode.

## Run on Windows

Requirements: Python 3.11+, Node 20.11+ (or a current Node LTS).

```powershell
cd C:\Paytm-Hackathon
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd frontend
npm ci
npm run build
cd ..
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. FastAPI serves the production frontend and API from one origin. API docs: http://127.0.0.1:8000/docs.

After initial setup, `.\start.ps1` builds the frontend and runs the backend. For exact tested Python versions, install `backend/requirements.lock.txt` instead of the version-range requirements file.

For frontend development, run `npm run dev` inside `frontend` in another terminal and use http://localhost:5173. Vite proxies `/api` to the backend. Restart the backend if `frontend/dist` was built after the backend started.

## Test the customer journeys

Click **Start a claim** or **New journey**. Select the existing demo policy and insured patient, then choose **Cashless assistance** or **Reimbursement**. New customer journeys preload the fictional issued schedule; users upload claim evidence, not the policy wording.

### Cashless assistance

1. Choose **Aarav Sharma**, then **Cashless assistance**. The reference product is HDFC ERGO my:Optima Secure; the issued customer schedule and hospital directory are fictional fixtures.
2. Select **Fill sample details**. This selects Sunrise Care Hospital in Pune, admission on `2026-10-31`, and an INR 80000 estimate. You can also enter these details manually.
3. Confirm identity/policy readiness and select **Save admission details**. Planned and emergency choices show different notification guidance with an official wording citation.
4. Download the synthetic **Admission advice** and **Cost estimate** files, then upload each in its matching row. Cloud mode uses real Document AI + Vertex AI processing; demo mode uses deterministic parsing.
5. Expand **Document evidence** to inspect extracted quotes and page links. Patient, hospital, admission date, and estimated amount mismatches block the simulator.
6. Select **Start simulated hospital request**. Try **Simulate more information**, add a clarification, and resubmit. Then simulate authorization, discharge review, and settlement. Every status and amount is clearly simulated; no insurer/TPA request or payment occurs.
7. Download the hospital handoff brief. Changing admission details or replacing evidence resets a previously advanced simulated request.
8. To test a blocked hospital arrangement, choose the Delhi sample hospital. It is explicitly unverified; the simulator cannot advance.

The retained case **Cashless cloud check - simulation** has passed through the real cloud extraction pipeline and the full simulator timeline.

### Reimbursement

1. Start a new **Reimbursement** journey for Aarav. The issued schedule is already loaded.
2. Download the sample hospital bill, discharge summary, and bank proof from **My documents**. Upload the bill and discharge summary first; bank proof remains a blocker.
3. Upload bank proof and inspect **Review details**. Patient and policy identity fields come from the existing schedule and cannot be overwritten; replace mismatched claim documents or start a journey for the correct member.
4. Ask the assistant about the required documents or cashless process. Follow the citation to the original insurer wording or the separately labeled OneFlow POC rule.
5. Confirm review and download a preliminary packet. The POC core checklist is not the insurer's complete submission checklist; additional claim-form, identity, clinical, receipt, and conditional evidence may be required.
6. Change an editable claim field after review. Export becomes blocked until a new review.

Existing legacy synthetic-policy applications remain readable with their original policy context. New frontend journeys use the existing-customer policy flow. The customer policy fixture is not a real insurance contract or a live insurer account.

## Connect Vertex AI + Document AI

1. Choose a billing-enabled Google Cloud project. Enable Vertex AI and Document AI APIs:

   ```powershell
   gcloud services enable aiplatform.googleapis.com documentai.googleapis.com --project YOUR_PROJECT_ID
   gcloud auth application-default login
   gcloud auth application-default set-quota-project YOUR_PROJECT_ID
   ```

2. Create an **Enterprise Document OCR** processor in Document AI. Record its processor ID and location (`us` or `eu`). This location is independent of Vertex AI's location.
3. Your local ADC principal needs access to Vertex AI and Document AI processing (typically `roles/aiplatform.user` and `roles/documentai.apiUser`, plus service usage/quota permissions where required). Have the project administrator grant the appropriate project-scoped roles. For hosting, use a service identity; do not ship service-account JSON files to the frontend.
4. Copy `backend/.env.example` to `backend/.env` and set:

   ```dotenv
   ONEFLOW_MODE=cloud
   GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
   GOOGLE_CLOUD_LOCATION=global
   VERTEX_MODEL=gemini-2.5-flash
   DOCUMENT_AI_LOCATION=us
   DOCUMENT_AI_PROCESSOR_ID=YOUR_PROCESSOR_ID
   ```

   Use a model available to your project and supported in the configured location. Model IDs are configurable. The SDK is initialized with `vertexai=True`; this does not use an AI Studio API key.

5. Restart FastAPI. `/api/health` reports mode and missing configuration. This configuration check does not prove IAM/API access; the first upload exercises those permissions.
6. Create a new journey and upload the downloaded sample documents. In cloud mode every upload goes through Document AI, then Vertex AI structured extraction. There is **no silent fallback** to demo responses when cloud calls fail. Cloud API usage may incur charges.

Cloud mode still uses the explicitly configured synthetic policy rules; arbitrary uploaded policies are not automatically trusted or supported. Adding an insurer requires reviewed policy clauses and deterministic journey rules.

## Validation

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q
cd frontend
npm run build
```

Tests cover complete export, missing-document recovery, cross-document conflicts, retained provenance, review invalidation after changes, persistence, invalid dates/amounts/bank values, unsupported policies, per-document omissions, failed uploads, grounded answers, cloud configuration errors, and SDK adapters with mocked cloud responses. Actual cloud calls require configured project access and are a separate integration check.

Run the explicit cloud integration check with `.\.venv\Scripts\python.exe backend\scripts\cloud_smoke.py`. It uploads four synthetic PDFs through real cloud APIs, asks a cited policy question, confirms review, and validates the exported ZIP. Add `--keep` to retain that application in the normal workspace. This command incurs cloud API usage and is intentionally separate from the default test suite.

## Architecture

```text
React / TypeScript / Tailwind
             |
       FastAPI REST API
             |
  Upload -> Document AI OCR -> Vertex AI extraction -> evidence gate
             |                         |
       server-side files       LangGraph workflow
                                 assemble -> validate -> status
                                         |
                          SQLite application snapshot + audit
                                         |
                  policy retrieval -> Vertex AI explanation
                                         |
                         human review -> PDF + ZIP export
```

- `backend/app/providers.py`: ADC-based Vertex client, regional Document AI client, demo parser, and grounded explanations.
- `backend/app/workflow.py`: deterministic document and field rules orchestrated by LangGraph. State is persisted in SQLite after each completed operation; this is not a long-running autonomous agent.
- `backend/app/policies.py`: immutable, versioned synthetic clause corpus and small lexical retrieval index. No external vector service is needed for five clauses.
- `backend/app/main.py`: API endpoints, upload validation, review gating, and frontend serving.
- `frontend/src/App.tsx`: dashboard, documents, evidence review, policy viewer, chat, and audit screens.
- `backend/data/`: ignored local SQLite database and uploaded files. No uploaded file paths are exposed by API responses.

## POC boundaries / next deployment step

Run on loopback with synthetic data. This build has no authentication, tenant isolation, encrypted object storage, malware scanning, retention scheduler, or distributed transaction handling. It is not ready to expose publicly or to accept real customer financial/medical data. For a pilot, add authenticated users and ownership checks, PostgreSQL, private GCS storage with retention controls, a durable processing queue, reviewed institution-specific rules, and cloud integration/evaluation tests. BigQuery can be added for aggregate analytics later.

RAG and JSON schemas do not guarantee factual correctness. Extracted values require source quotes and page evidence; unsupported questions abstain; backend checks decide readiness; users confirm the final packet. User corrections remain visible alongside original sources. Modifying or replacing a document invalidates final review.

See `IMPLEMENTATION_PLAN.md` for scope and milestones.

## Cashless implementation notes

- `backend/app/customer.py`: fictional customer schedule and hospital fixtures, official wording references, and separately labeled POC checklist rules.
- `backend/app/cashless.py`: preparation validation, document consistency checks, permitted simulation transitions, and invalidation when supporting data changes.
- `frontend/src/JourneyStart.tsx`: existing-policy/member selection and cashless/reimbursement entry.
- `frontend/src/CashlessJourney.tsx`: planned/emergency admission, sample hospital selection, evidence review, handoff checklist, query recovery, and simulated authorization timeline.
- `frontend/src/paytm-theme.css`: predominantly white surfaces with Paytm-inspired navy `#002970` and cyan `#00baf2` accents. OneFlow is an independent POC.
- `backend/scripts/cloud_cashless_smoke.py`: optional real-cloud test using two synthetic PDFs. Add `--keep` to retain the verified simulation. Cloud API usage incurs charges.

The hospital directory is not live network data. The illustrative authorization amount is 80% of the entered estimate solely to demonstrate state presentation; it is not calculated from insurer benefits. The app currently indexes concise process summaries with original page references, not the full policy or all endorsements. Production integration requires authenticated customer policy APIs, a maintained hospital directory, real hospital/TPA authorization events, and reviewed policy-specific rules.
