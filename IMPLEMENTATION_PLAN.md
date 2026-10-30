# OneFlow AI implementation plan

## Cashless and existing-policy update

Implemented a consumer entry point that selects a preloaded fictional issued policy and insured member. Cashless assistance and reimbursement now use separate document requirements and workflows. Cashless covers planned/emergency admission, a fictional hospital directory, source-linked admission advice and cost-estimate extraction, readiness checks, hospital handoff export, and a strictly simulated pre-authorization/query/resubmission/authorization/discharge/settlement timeline. Invalid transitions and changed evidence are checked by the backend.

Insurer process guidance uses the supplied two-page OneFlow Care Plus testing policy with page references. Internal POC checklist rules are labeled separately. The schedule, customer, hospitals, authorization status, and illustrative amounts remain fictional. No insurer/TPA request is made.

The UI now uses a predominantly white canvas, navy #002970 sidebar and feature areas, and cyan #00baf2 controls and accents, targeting the requested approximate 70% white / 30% blue balance.

## POC goal

Complete a synthetic health reimbursement preparation journey: understand requirements, collect documents, extract facts, check consistency, explain cited policy rules, recover from errors, review, and export. Lending and claim adjudication are outside this first journey.

## Implemented scope

1. Application workspace with persistent journeys, document checklist, progress, and next action.
2. Four document types: policy schedule, hospital bill, discharge summary, and bank proof. Replacement and removal rebuild validation state.
3. Demo sample parser and a real configurable Google Cloud pipeline: Document AI OCR -> Vertex AI Gemini structured extraction -> evidence gate.
4. Field provenance with original filename, document ID, page, quote, extracted value, and separately retained user confirmation.
5. Deterministic requirements, per-document omissions, cross-document conflicts, valid dates, policy period, positive amounts, sum-insured review limit, bank suffix, and supported policy checks.
6. LangGraph orchestration with completed application snapshots stored in SQLite after each operation.
7. Grounded explanations over a versioned five-clause synthetic corpus, source viewer, and unknown-question abstention.
8. Human review gate; edits invalidate review. ZIP export includes PDF summary, originals, policy source, evidence, and audit data.
9. Responsive React interface, loading and error states, empty states, source comparison, assistant drawer, and activity timeline.
10. API integration tests, mocked cloud adapter tests, frontend type check and production build.

## Acceptance scenarios

- Complete case reaches review and exports only after explicit confirmation.
- Missing bank proof blocks readiness; upload repairs the same application.
- Name conflict blocks readiness; explicit correction retains sources and a reviewer warning, or replacement removes the conflict.
- Wrong dates, invalid numeric amounts, missing fields, and unsupported policies cannot reach ready.
- Refresh restores progress; changing data after review blocks export until a new review.
- OCR/model failure preserves prior state and never silently falls back to demo parsing in cloud mode.
- Policy questions link to verified clause IDs; unsupported topics produce an abstention.

## Cloud setup and integration completed

- Configured project `project-b222a5e1-4bfe-4261-a4e` using existing local ADC.
- Created approved Document AI OCR processor `8dfc522a55da9b0b` in `us`.
- Verified real Document AI OCR, Vertex extraction, deterministic validation, cited explanation, explicit review, and ZIP export with four synthetic PDFs.
- Retained the cloud-verified application in the workspace. See `VERIFICATION.md`.

## Next evaluation work

- Measure field accuracy against a labeled document set. Evaluate answer support and unknown-question abstention; do not claim zero hallucination.
- Expand tests to noisy scans, photographed bills, alternate date formats, and supported languages before onboarding real users.

## Pilot phase

Introduce user authentication and per-application authorization before any public exposure. Add PostgreSQL, private GCS storage, retention/deletion controls, async jobs, audit access controls, document scanning, optimistic concurrency, and monitoring. Onboard a reviewed insurer policy with configurable versioned rules. Evaluate noisy scans and supported language variants. Add lending only after the claim preparation acceptance scenarios pass against the pilot corpus.
