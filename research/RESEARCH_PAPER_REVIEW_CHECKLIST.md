# Research Paper Review Checklist — MARP D3 Final (November 25, 2026)

Manuscript: `MARP_Research_Paper_D3_Final.tex` + `references.bib` →
`MARP_Research_Paper_D3_Final.pdf` (this directory). Compiler: Tectonic 0.17.0.

## Format (college paper rules, provisional — original Samyak template not found)

- [x] Abstract present, 224 words (limit 300). Counted programmatically.
- [x] Keywords: exactly 5, semicolon-separated.
- [x] Required sections present: Abstract, Keywords, Introduction (+Objectives,
      Gap), Design/Methods/Modelling, Results and Discussion, Conclusions,
      Acknowledgements, References. Numbered sections 1–4 + subsections.
- [x] References alphabetical with numeric identifiers ([1]–[7], plainnat).
- [x] 8 pages (limit 8), A4, 11pt, single spacing, justified-ready layout.
- [x] Title, author, affiliation, date on page 1; running header + page numbers.

## Citations and references

- [x] All 7 bib entries cited; no undefined citation keys; no uncited entries.
- [x] Every in-text citation numeric (`[1]`, `[2]`, `[1, 7]`, `[1, 3]`).
- [x] All 5 DOIs resolve (doi.org HTTP 200 chains, Nov 2026).
- [x] Metadata cross-checked vs OpenAlex: years, venues, titles, author lists.
- [x] Basiri author list corrected (removed erroneous Wohlin; Kosewski fixed).
- [x] Sculley has no DOI (correct — NeurIPS proceedings carry none).
- [x] Kubernetes docs URL verified reachable (HTTP 200, Nov 2026).
- [x] No author-year/numbered mixing. No claim of systematic review.

## Figures, tables, numbering

- [x] Figure 1 (architecture), Figure 2 (readiness flow), Figure 3
      (experiment workflow) — all TikZ-native, no external images, all
      captioned, numbered, and referenced in body text.
- [x] Table 1 (scenarios/measurements), Table 2 (evidence/provenance) —
      captioned, referenced, fit within margins.
- [x] No orphaned captions, no empty pages, no duplicate headings
      (one bib-heading defect found and fixed before final compile).

## Evidence honesty

- [x] No invented accuracy/FAR/FRR/ROC/latency/capacity numbers anywhere.
- [x] R12 reruns stated with provenance (Nov 2026 gate, exit 0); fault/latency
      figures marked reported-only; browser mocking disclosed.
- [x] Threshold 0.85 stated as uncalibrated default; pixel baseline stated as
      not-a-learned-embedding; liveness/photo-spoof limits stated.
- [x] K8s described as possible target only; Compose as verified path.
- [x] Limitations and future-work sections present and specific.

## Remaining author actions (NOT done here)

- [ ] Confirm author list, affiliations, supervisor acknowledgement, funding.
- [ ] Obtain the actual Samyak/college template and re-check margins, line
      spacing, justification, reference ordering, and any page-fee rules.
- [ ] Reconfirm all numbers against the final submission commit before filing.
- [ ] Decide on license/publication venue; do not submit without them.
