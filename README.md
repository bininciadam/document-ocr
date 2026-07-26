# document-ocr

Local-first OCR pipeline for passports and Indian KYC documents. It
preprocesses scans, classifies the document, runs targeted OCR with RapidOCR
(PP-OCRv5), and extracts structured fields—including passport MRZ data, Indian
passport back-page fields, and identifier/holder fields for PAN, Aadhaar,
driving licences, and voter IDs.

Ships as a Python package with a FastAPI server, plus an npm wrapper at [`packages/passport-ocr`](packages/passport-ocr) that auto-spawns the Python server for Node.js consumers.

> [!IMPORTANT]
> This project is beta software for data extraction. It does not establish
> document authenticity, verify identity against an issuing authority, detect
> fraud, or by itself satisfy KYC obligations. Evaluate it on your own legally
> obtained dataset before production use.

## Supported documents

| Document | Key fields extracted | Identifier validation |
|---|---|---|
| Passport (biodata) | name, passport no., nationality, DOB, sex, expiry/issue dates, place of birth | TD3 MRZ ICAO check digits |
| Passport (back page) | father/mother/spouse, address, file no., old passport details | — |
| PAN card | PAN, name, father's name, DOB | PAN format + holder-type char |
| Aadhaar (front/back) | Aadhaar no. (+ VID, masked-card support), name, DOB/YOB, gender, address, pincode | Verhoeff checksum |
| Driving licence | DL no., name, DOB, issue/validity dates (NT + TR), address, blood group, vehicle class | DL format |
| Voter ID (EPIC) | EPIC no., name, relation name + type, gender, DOB/age | EPIC format |

The document type is detected automatically; `/scan` returns the matching field block (`fields`/`backPageFields` for passports, `panFields`/`aadhaarFields`/`drivingLicenceFields`/`voterIdFields` for the others) keyed by `documentType`.

## Quickstart

### Python

Requires Python 3.12+ and [`uv`](https://github.com/astral-sh/uv).

```bash
make install
make dev          # uvicorn on :8000 with reload
```

Scan a document:

```bash
curl -F image=@/path/to/document.jpg \
  http://localhost:8000/scan
```

### Docker

```bash
make docker-build
docker run --rm -p 8000:8000 passport-ocr
```

The image pre-downloads PP-OCRv5 models at build time so the first request is fast.

### Node.js (npm package)

```bash
npm install document-ocr
```

```ts
import { DocumentOCR } from 'document-ocr';

const ocr = new DocumentOCR();
const result = await ocr.scan(imageBuffer);

if (result.status === 'success' && result.documentType === 'passport') {
  console.log(result.fields.passportNumber, result.mrzValid);
}
await ocr.stop();
```

The package auto-creates a `.venv`, installs the Python deps, and manages the local server lifecycle. See [`packages/passport-ocr/README.md`](packages/passport-ocr/README.md) for full options including HTTP mode.

## HTTP API

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness |
| GET | `/ready` | `503` until OCR models finish loading |
| POST | `/scan` | Multipart image upload, returns scan result JSON |

`/scan` accepts images and PDFs up to 10 MB. Concurrency is serialized
internally. Set `DOCUMENT_OCR_API_TOKEN` to require
`Authorization: Bearer <token>` on `/scan`. For internet-facing deployments,
use platform IAM or an API gateway in addition to application-level controls.

## Output

```jsonc
{
  "status": "success",                  // success | failure | unsupported_page
  "documentType": "passport",           // passport | pan | aadhaar | driving_licence | voter_id | unknown
  "pageType": "passport_biodata",       // passport_biodata | passport_non_biodata | pan | aadhaar | driving_licence | voter_id | unknown
  "confidence": 0.91,
  "fields": {
    "surname": "...", "givenNames": "...", "fullName": "...",
    "passportNumber": "...", "nationality": "IND",
    "dateOfBirth": "1990-05-21", "sex": "M",
    "expiryDate": "2030-04-12", "issueDate": "2020-04-13",
    "placeOfBirth": "...", "countryCode": "IND"
  },
  "backPageFields": {
    "fatherName": "...", "motherName": "...", "spouseName": "...",
    "address": "...", "pincode": "...", "city": "...", "state": "...",
    "fileNumber": "...", "oldPassportNumber": "...",
    "oldPassportDateOfIssue": "...", "oldPassportPlaceOfIssue": "..."
  },
  // Exactly one document block is populated, keyed by documentType; the rest
  // are null. (passport uses fields/backPageFields above.)
  "panFields":            { "panNumber": "...", "name": "...", "fatherName": "...", "dateOfBirth": "..." },
  "aadhaarFields":        { "aadhaarNumber": "...", "name": "...", "dateOfBirth": "...", "yearOfBirth": null,
                            "gender": "...", "address": "...", "pincode": "...", "checksumValid": true,
                            "aadhaarMasked": false, "aadhaarLast4": "...", "vid": null },
  "drivingLicenceFields": { "dlNumber": "...", "name": "...", "dateOfBirth": "...", "issueDate": "...",
                            "validityDate": "...", "address": "...", "relationName": "...", "bloodGroup": "...",
                            "classOfVehicle": "...", "validityDateTransport": null },
  "voterIdFields":        { "epicNumber": "...", "name": "...", "relationName": "...", "relationType": "father",
                            "gender": "...", "dateOfBirth": "...", "age": null },
  "mrzRaw": ["P<IND...", "..."], "mrzValid": true,
  "lowConfidence": false,
  "errors": [], "warnings": [],
  "processingMs": 412
}
```

## Pipeline

1. `preprocess` — orientation, document boundary detection, perspective correction, quality checks
2. `classify_passport_page` — biodata vs non-biodata vs not-a-passport (cheap bottom-crop probe)
3. passport path: `run_ocr` (RapidOCR PP-OCRv5, full-page fallback when MRZ is missing) → `parse_mrz` (TD3 MRZ with per-field + overall checksum validation) → `extract_back_page` (bilingual label-aware extraction) → `validate` (cross-checks MRZ vs visual fields, computes confidence)
4. non-passport path: `classify_document` routes full-page OCR to the matching extractor (`pan` / `aadhaar` / `driving_licence` / `voter_id`), validating each document's identifier (PAN format, Verhoeff for Aadhaar, EPIC/DL format)

Single entry point: `core.pipeline.scan(image_input)`.

## Deployment

The same pipeline runs as a container, on Cloud Run, or on AWS Lambda. Copy
`.env.deploy.example` to `.env.deploy.<env>` and fill in the relevant values
first (Docker Hub and/or GCP).

Cloud Run and Lambda deployments are authenticated by default. Do not expose
an identity-document endpoint publicly without authentication, authorization,
rate limiting, encrypted transport, and an explicit data-retention policy.

### Cloud Run (recommended)

```bash
# Build deploy/docker/Dockerfile, push to Artifact Registry, deploy the service.
bash deploy/cloudrun/deploy.sh production
# or via Cloud Build:
gcloud builds submit --config deploy/cloudrun/cloudbuild.yaml \
  --substitutions=_REGION=asia-south1,_SERVICE=document-ocr
```

Service config lives in [`deploy/cloudrun/service.yaml`](deploy/cloudrun/service.yaml)
(2 GiB / 2 vCPU, `containerConcurrency: 1` since OCR is serialized, scale-to-zero).

### AWS Lambda (container image)

The SDK's `mode: 'lambda'` invokes a function that takes `{ "image_base64": "..." }`.

```bash
cd deploy/lambda
sam build && sam deploy --guided   # uses Dockerfile.lambda + template.yaml
```

The handler ([`deploy/lambda/handler.py`](deploy/lambda/handler.py)) returns the
raw scan result on success and an `{statusCode, body}` envelope for errors.
The included SAM template supports IAM-authenticated direct invocation and does
not create a public API Gateway endpoint.

## Tests & benchmarks

```bash
make test
make build
```

The per-document extractors are covered by deterministic `TextRegion` fixtures
under `tests/python/test_*_extractor.py`. These tests verify parsing and
validation behavior; they are not a claim of real-world OCR accuracy.

For image-level evaluation, place a private dataset and `manifest.json` under
`benchmark-data/` and run:

```bash
make benchmark
```

The directory is ignored by Git. Never commit identity documents or personal
data. See [CONTRIBUTING.md](CONTRIBUTING.md) for fixture rules.

## Privacy and security

Local Python and npm-local modes process documents on the same machine and do
not include telemetry or document storage. HTTP and Lambda modes transmit
documents to infrastructure controlled by the operator.

Read [PRIVACY.md](PRIVACY.md) before deploying and report vulnerabilities using
[SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE). Dependencies retain their own licenses; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
