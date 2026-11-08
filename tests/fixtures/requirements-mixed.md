# Example recipe app — hard requirements

Each row is one requirement. Pri is Must, Should or Later.

## AREA ARCH — architecture constraints

| ID | Pri | Requirement | Why |
|---|---|---|---|
| REQ-ARCH-1 | Must | Every recipe change is saved within one second of the last edit. | Decision D2. |
| REQ-ARCH-2 | Must | All payment calls go through one gateway that can switch providers. | Decision D4. |
| REQ-ARCH-3 | Should | The gateway logs no request bodies \| only sizes and timings. | Retention note R1. |

## AREA SRC — accepted files

| ID | Pri | Requirement | Why |
|---|---|---|---|
| REQ-SRC-1 | Must | The system accepts only plain-text, Markdown and PDF files. | Source note L3. |
| REQ-SRC-2 | Must | A password-protected file is refused with a message that says why. | Source note L3. |
| REQ-SRC-3 | Later | The system detects scanned PDFs and runs text recognition on them. [covered: OCR setting in the server config] | Source note L4. |

## AREA DOC — published texts

| ID | Pri | Requirement |
|---|---|---|
| REQ-DOC-1 | Must | Terms of service are published before the first sale. |
| REQ-DOC-2 | Should | A privacy page lists every processing activity. |
| REQ-DOC-3 | Must | Every published text keeps its version history in the repo. |

## AREA LATER — triggers

These apply only once their trigger happens.

| ID | Trigger | Action |
|---|---|---|
| REQ-LATER-1 | Revenue passes the small-business threshold | Register for VAT. |
| REQ-LATER-2 | A second person joins | Write a contributor agreement. |
| REQ-LATER-3 | Sales start in a new store | Review that store's content rules. |
