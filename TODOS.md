# TODOs

_Five of the original six items (model-init error handling, Lambda deploy,
TypeScript SDK tests, back-page accuracy, Cloud Run deploy) were completed in
1.2.0 — see CHANGELOG.md._

## Open

1. **Build a licence-clean evaluation dataset.** Source consented, properly
   anonymized documents or unmistakably synthetic specimens for the private
   `benchmark-data/` suite. Do not commit identity documents to this repository.

2. **End-to-end image benchmark for the new document types.** The PAN / Aadhaar /
   driving-licence / voter-ID extractors are covered only by deterministic
   `TextRegion` fixtures (`tests/python/test_*_extractor.py`) — they never run
   real OCR. Add an image-level benchmark (anonymized real cards with ground-truth
   labels) to measure true end-to-end accuracy.

3. **Deskew in the preprocessor.** `core/preprocessor.py` does document-boundary
   perspective correction but no text-line deskew, so rotated/tilted inputs shift
   the spatial label→value relationships the extractors rely on. A Hough /
   projection-profile deskew step would harden real-world phone-photo accuracy.

4. **Passport probe over-eagerly claims KYC cards.** The cheap bottom-crop
   passport probe (`core/pipeline._extract_targeted_regions` + `classify_passport_page`)
   treats "SEX" and "DATE OF BIRTH" as biodata hints, so a voter/DL card showing
   those exact labels in its lower ~55% can mis-route to the passport path before
   `classify_document` runs. Fix: require an MRZ (or a passport keyword) before
   committing to the passport path, or run `classify_document` first and only
   treat as passport when it agrees.

5. **Driving licence layout variance.** The DL extractor is best-effort; layouts
   differ substantially by issuing state. Gather fixtures from more states
   (especially Smart Card DLs and the newer Parivahan format) and tune
   `core/driving_licence_extractor.py`. The DL identifier format check in
   `core/validators.py` is also loose — tighten per-state if needed.

6. **Aadhaar name detection.** Aadhaar has no Latin label for the holder name, so
   `_find_name` infers it spatially relative to the DOB line. Validate against
   more real layouts (vertical/horizontal cards, masked Aadhaar, mAadhaar PDF).

7. **SDK retry semantics for 4xx.** Thread structured HTTP status information
   through retry handling rather than inferring retryability from error-message
   text.
