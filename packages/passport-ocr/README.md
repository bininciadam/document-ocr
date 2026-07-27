# document-ocr

Local-first document OCR for Node.js. It extracts structured fields from
passports and Indian PAN, Aadhaar, driving-licence, voter-ID,
MGNREGA/NREGA-job-card, and NPR-letter documents using a bundled
Python/RapidOCR pipeline.

> This is beta extraction software. It does not verify document authenticity,
> detect fraud, query issuing authorities, or by itself satisfy KYC obligations.
> NREGA and NPR extraction is experimental until measured against a
> representative private image dataset.

## Install

```bash
npm install document-ocr
```

Python 3.12 or 3.13 is required. If [`uv`](https://docs.astral.sh/uv/) is
available, the postinstall script can create the local environment
automatically.

## Local mode

```typescript
import { DocumentOCR } from 'document-ocr'

const ocr = new DocumentOCR()
const result = await ocr.scan(imageBuffer)

if (result.status === 'success') {
  switch (result.documentType) {
    case 'passport':
      console.log(result.fields?.passportNumber)
      break
    case 'pan':
      console.log(result.panFields?.panNumber)
      break
    case 'aadhaar':
      console.log(result.aadhaarFields?.aadhaarLast4)
      break
    case 'nrega_job_card':
      console.log(result.nregaJobCardFields?.jobCardNumber)
      break
    case 'npr_letter':
      console.log(result.nprLetterFields?.referenceNumber)
      break
  }
}

await ocr.stop()
```

Local mode starts the bundled FastAPI process on `127.0.0.1`, reuses it across
scans, and stops it when `ocr.stop()` is called. Documents stay on the local
machine.

`PassportOCR` remains available as a compatibility alias for `DocumentOCR`.

For non-passport results, `status: 'success'` requires the document-specific
minimum fields and a conservative OCR-region confidence gate.
`identifierValid` reports only a local format/checksum check, not authenticity;
`missingRequiredFields` explains partial failures. In HTTP mode these
structured partial results use status `422` and are returned by the client
rather than thrown.

Set `DOCUMENT_OCR_KYC_LANGS=en,devanagari` (or `latin`, `ka`, `ta`, `te`) to
run known recognition models on the non-passport path. Each additional model
adds latency and memory, so choose the list from measured language slices.
Unsupported names or more than four models fail server readiness.

## Other modes

### HTTP

```typescript
const ocr = new DocumentOCR({
  mode: 'http',
  endpoint: 'https://ocr.example.com',
  apiKey: process.env.DOCUMENT_OCR_API_TOKEN,
})
```

`apiKey` is sent as a Bearer token. The included Python server enforces it when
`DOCUMENT_OCR_API_TOKEN` is configured.

### AWS Lambda

```typescript
const ocr = new DocumentOCR({
  mode: 'lambda',
  functionName: 'document-ocr-prod',
})
```

Lambda mode uses IAM-authenticated direct invocation through the AWS SDK.

## Options

| Option | Type | Default | Description |
|---|---|---|---|
| `mode` | `local \| http \| lambda` | `local` | Invocation mode |
| `endpoint` | `string` | — | Required in HTTP mode |
| `functionName` | `string` | — | Required in Lambda mode |
| `timeoutMs` | `number` | `30000` | Per-attempt timeout |
| `retries` | `number` | `2` | Retry count |
| `apiKey` | `string` | — | Bearer token for HTTP mode |

Accepted image inputs are `File`, `Blob`, `Buffer`, `ArrayBuffer`, base64
strings, and HTTP(S) URLs.

Set `PASSPORT_OCR_SKIP_PYTHON=1` during installation to skip local Python setup
when only HTTP or Lambda mode is required.

## Privacy

HTTP and Lambda modes transmit identity documents to the configured
infrastructure. Protect the endpoint, avoid logging extracted personal data,
and define an appropriate retention policy. Never submit real identity
documents to public issues or test fixtures.

## License

[MIT](LICENSE)
