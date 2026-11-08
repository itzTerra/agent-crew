Target: docs/specs/imports/spec.md

## ADDED Requirements

### Requirement: Accept PDF

When a cook imports a PDF file, the system shall import its text as a recipe.

Satisfies: REQ-ARCH-1

#### Scenario: Import a PDF

- WHEN the cook imports `soup.pdf`
- THEN the cookbook lists one recipe

## MODIFIED Requirements

### Requirement: Reject locked files

When a cook imports a password-protected file, the system shall refuse it, say why and link to help.

#### Scenario: Import a locked PDF

- WHEN the cook imports a locked PDF
- THEN an error explains that locked files are not accepted
- AND the error links to the help page

## REMOVED Requirements

### Requirement: Accept plain text

## RENAMED Requirements

- FROM: Reject locked files TO: Refuse locked files
