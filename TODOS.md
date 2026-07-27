# TODOs

_Five of the original six items (model-init error handling, Lambda deploy,
TypeScript SDK tests, back-page accuracy, Cloud Run deploy) were completed in
1.2.0 — see CHANGELOG.md._

## Open

1. **Build a licence-clean evaluation dataset.** Source consented, properly
   anonymized documents or unmistakably synthetic specimens for the private
   `benchmark-data/` suite. Do not commit identity documents to this repository.

2. **Populate and lock the KYC image benchmark.** The versioned evaluator,
   manifest schema, variant slices, and release gates now exist, but the
   repository intentionally contains no identity-document images. Build the
   consented private dataset, establish baselines for all six non-passport
   document types, and require the locked split before release.

3. **Regional-script OCR coverage.** KYC-only model selection can now be
   configured with `DOCUMENT_OCR_KYC_LANGS`, but automatic selection and
   Bengali recognition are unavailable. Measure every configured language
   slice and add models only where the locked dataset demonstrates a gain.

4. **Deskew in the preprocessor.** `core/preprocessor.py` does document-boundary
   perspective correction but no text-line deskew, so rotated/tilted inputs shift
   the spatial label→value relationships the extractors rely on. A Hough /
   projection-profile deskew step would harden real-world phone-photo accuracy.

5. **Multi-page non-passport documents.** PDF preprocessing currently evaluates
   the first page. Add a KYC-only page aggregation contract before claiming
   complete support for multi-page NPR letters or job-card continuations.

6. **Explicit KYC routing for ambiguous documents.** To preserve the existing
   passport-positive path, `scan()` does not override a positive passport-page
   classification. Some driving licences and voter cards containing multiple
   passport-like labels can therefore remain on the passport path. Add a
   separate KYC-only entry point or independent router without changing
   passport OCR behavior.

7. **Driving licence layout variance.** The DL extractor is best-effort; layouts
   differ substantially by issuing state. Gather fixtures from more states
   (especially Smart Card DLs and the newer Parivahan format) and tune
   `core/driving_licence_extractor.py`. The DL identifier format check in
   `core/validators.py` is also loose — tighten per-state if needed.

8. **Aadhaar name detection.** Aadhaar has no Latin label for the holder name, so
   `_find_name` infers it spatially relative to the DOB line. Validate against
   more real layouts (vertical/horizontal cards, masked Aadhaar, mAadhaar PDF).

9. **SDK retry semantics for 4xx.** Thread structured HTTP status information
   through retry handling rather than inferring retryability from error-message
   text.

## Completed in 3.0.0

- Added NREGA job-card and NPR-letter extraction, classification, public result
  contracts, and deterministic variation tests.
- Added fail-closed non-passport completeness/identifier/semantic assessment.
- Added the private KYC benchmark framework with versioned manifests,
  per-document/per-field metrics, variation slices, and threshold gates.
- Kept dedicated passport modules and passport-positive routing unchanged; new
  KYC families use only the existing unknown/no-text routing boundary.
