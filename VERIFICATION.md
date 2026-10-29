# Verification record

## Cashless and theme update — 2026-10-30

- Backend suite: **37 tests passed**, including the 21 original regression cases and new existing-policy/cashless coverage.
- Strict TypeScript and Vite production build passed for the cashless components and blue/white theme.
- Real Google Cloud cashless integration passed: Document AI OCR and Vertex AI extracted four evidence-linked admission-advice fields and three cost-estimate fields; deterministic validation passed; all simulated timeline transitions completed; a policy-linked answer and handoff PDF were produced.
- Retained cashless application: `528c8784-16fa-416b-9d31-91a68218dea7`, titled **Cashless cloud check - simulation**.
- Tests cover protected preloaded schedules, member selection, different reimbursement/cashless uploads, unavailable/unverified hospitals, missing or conflicting clinical evidence, invalid estimates/dates, required clarification, illegal state transitions, caller-supplied authorization amount rejection, persistence, decline, and resets after changed evidence.
- **Visual browser QA of this revision was blocked by the browser URL security policy.** No screenshot or visual pass is claimed for the new theme. Earlier screenshots below describe the previous revision.

The cashless integration uses real Google OCR/model calls with synthetic documents. It does not contact an insurer/TPA or create a real authorization or payment. The official wording is used for cited process summaries; full policy/endorsement ingestion remains future work.

---

Verified locally on 2026-10-30 (Asia/Calcutta).

## Automated checks

- Backend: **21 tests passed** (`.venv\Scripts\python.exe -m pytest -q`).
- Frontend: TypeScript strict type check and Vite production build passed.
- Coverage includes readiness gating, source provenance, exact numeric evidence, invalid dates/amounts, unsupported policies, missing documents, cross-document conflict recovery, document replacement/removal, review invalidation, reload persistence, SDK request construction, and SQLite connection closure.

## Real Google Cloud integration

Project: `project-b222a5e1-4bfe-4261-a4e`.

Document AI processor: `projects/611341613317/locations/us/processors/8dfc522a55da9b0b`, display name `oneflow-poc-ocr`, type `OCR_PROCESSOR`.

Vertex AI: Google Gen AI SDK in Vertex mode, model `gemini-2.5-flash`, location `global`, local ADC. No credentials copied into source files.

The explicit cloud smoke test passed with real APIs:

| Synthetic document | Extracted fields with page/quote evidence |
|---|---:|
| Policy schedule | 4 |
| Hospital bill | 5 |
| Discharge summary | 4 |
| Bank account proof | 2 |

The workflow filtered fields by expected document role, passed deterministic validation, produced a Vertex answer citing clause C5, required explicit review, and exported a valid ZIP containing the summary PDF, four original documents, source policy, evidence JSON, and audit history.

Retained application: `07c9ea66-1961-453c-b9db-36517d7b17ed`, titled **Cloud integration test - synthetic**.

## Browser checks

Checked the actual built React app in the in-app browser: dashboard rendering, sample-case selection, complete claim review, confirmation checkbox gating, and export availability after review. A short-height sidebar flex issue was found and corrected during browser QA. Browser console had no application errors in the inspected run.

Reopened the retained cloud-verified claim through the sidebar after the fix, confirmed cloud mode and 100% readiness, and downloaded its ZIP through the browser. Checked the dashboard and review at a 390px mobile viewport, including navigation; neither had horizontal page overflow. Rendered and visually inspected the exported summary PDF with no clipping or overlapping text.

## Limits

This validates a synthetic POC, not production claim adjudication, real insurer policy support, OCR accuracy across arbitrary documents, or production security. The Dockerfile is provided but has not been built in this environment. Real cloud tests incur API usage; they are separate from the standard test suite.
