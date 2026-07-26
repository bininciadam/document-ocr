# document-ocr

Local-first document OCR for Node.js. It extracts structured fields from
passports and Indian PAN, Aadhaar, driving-licence, and voter-ID documents
using a bundled Python/RapidOCR pipeline.

> This is beta extraction software. It does not verify document authenticity,
> detect fraud, query issuing authorities, or by itself satisfy KYC obligations.

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
  }
}

await ocr.stop()
```

Local mode starts the bundled FastAPI process on `127.0.0.1`, reuses it across
scans, and stops it when `ocr.stop()` is called. Documents stay on the local
machine.

`PassportOCR` remains available as a compatibility alias for `DocumentOCR`.

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
