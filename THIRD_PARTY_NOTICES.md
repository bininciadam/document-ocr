# Third-party notices

This project is MIT-licensed, but it depends on separately licensed software.
The dependency versions installed in a given environment determine the exact
notices that apply.

Major runtime dependencies include:

| Dependency | Upstream license |
|---|---|
| RapidOCR | Apache-2.0 |
| ONNX Runtime | MIT |
| OpenCV | Apache-2.0 |
| Pillow | HPND |
| NumPy | BSD-3-Clause |
| RapidFuzz | MIT |
| FastAPI | MIT |
| Uvicorn | BSD-3-Clause |
| python-multipart | Apache-2.0 |
| pypdfium2 | Apache-2.0 OR BSD-3-Clause |
| pillow-heif | BSD-3-Clause, with separately licensed native dependencies |

pypdfium2 wheels include PDFium and other components with their own notices.
When redistributing binaries or containers, retain the license files shipped
with the installed wheels and review the resulting dependency bundle.

This file is informational and is not legal advice. Consult each dependency's
distribution for its authoritative license text.
