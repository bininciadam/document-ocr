# Privacy and data handling

`document-ocr` processes identity documents and can extract highly sensitive
personal data.

## Local mode

The Python library and the npm package's default local mode process documents
on the machine where they run. The project does not include analytics,
telemetry, or document storage.

RapidOCR model files may be downloaded from its configured model source during
initial setup. Document images are not sent with that model download.

## Hosted modes

HTTP, Cloud Run, and Lambda modes transmit documents to infrastructure
controlled by the operator. Operators are responsible for:

- obtaining a lawful basis and user consent;
- authenticating and authorizing every request;
- encrypting data in transit and at rest;
- avoiding document contents and extracted fields in logs;
- defining short retention and deletion periods;
- restricting administrative access; and
- complying with applicable privacy, identity, and KYC regulations.

The included server logs request identifiers, status, page type, confidence,
processing time, and error codes. It does not intentionally log extracted
fields or uploaded document bytes.

## Public contributions

Never submit real identity documents or personal information to this
repository. Use synthetic fixtures that cannot be mistaken for genuine IDs.
