# Contributing to FACEATTEND

Small, reviewable, evidence-backed contributions. No CLA, no board, no
bot — just the rules below.

## Workflow

1. Fork (or branch from `main` if you have access — never push to `main`
   directly; open a PR instead).
2. Keep PRs focused: one concern per PR (feature, fix, docs, or tests).
3. Run the relevant suites from [Testing](TESTING.md) and paste the exact
   command + exit code into the PR description.
4. Request review; address feedback; a maintainer merges.

## Rules

- **Never commit**: `.env`, real credentials, tokens, private keys, student
  records, face images, database files/volumes, model weights (`*.pt`,
  `*.onnx`), logs, test-run artifacts (`fault_report.json`,
  `fault_samples.csv`, `marp_research_data.csv`), `node_modules/`, `build/`.
  `.gitignore` already excludes these — do not force-add them.
- **Do not weaken security** to make a demo easier (no default secrets, no
  open CORS, no skipped auth) — CI and the R1 suite will reject it.
- **Do not change tested UI copy silently**: the browser suite asserts exact
  labels, roles, and texts (locked list in [Testing](TESTING.md)). Rename
  copy and tests together, or not at all.
- **Do not claim unverified behavior**: no accuracy numbers without a labelled
  dataset and the registered protocol (`docs/CV_EVALUATION_PROTOCOL.md`); no
  production claims without a staging boot; no CI claims without an Actions run.
- Match the existing design system (`docs/FRONTEND_DESIGN_SYSTEM.md`): tokens
  first, reuse `fa/` primitives, respect `prefers-reduced-motion`, keep
  touch targets ≥40px and visible focus states.
- Backend changes need focused regression tests in the same PR
  (`backend/tests/test_r*.py` + R10 concurrency tests where DDL is touched).

## What good PRs look like here

- A one-screen UI polish + its browser-selector check passing.
- A chaos knob end-to-end (config → endpoint → UI control → test).
- A docs correction with the command output that proves the corrected claim.

## License and redistribution

**No license file exists in this repository yet.** Do not assume one. Public
redistribution, template publication, or release requires the owner to choose
and commit a license first — this is a tracked blocker, not an oversight.
