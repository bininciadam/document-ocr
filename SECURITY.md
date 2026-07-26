# Security policy

## Reporting a vulnerability

Please report vulnerabilities through GitHub's private security-advisory
feature for this repository. Do not open a public issue for an unpatched
security problem.

Include the affected version, reproduction steps, impact, and any suggested
mitigation. You should receive an acknowledgement within seven days.

## Identity-document data

Do not attach real passports, Aadhaar cards, PAN cards, driving licences,
voter IDs, or extracted personal data to issues, pull requests, discussions,
CI logs, or public test fixtures.

Use generated documents with an obvious `SPECIMEN — NOT A REAL ID` watermark.
If a private reproduction document is unavoidable, redact it and agree on a
secure transfer method with the maintainer first.

## Deployment

The local library does not upload documents. Hosted deployments are the
operator's responsibility and must use authentication, encryption in transit,
minimal retention, access controls, and appropriate consent. The included
Cloud Run and Lambda templates default to authenticated invocation.
