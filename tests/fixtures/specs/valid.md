# Imports

## Purpose

Cooks bring their own recipes into the cookbook.

## Requirements

### Requirement: Accept plain text

When a cook imports a TXT file, the system shall import it as a recipe.

Satisfies: REQ-ARCH-1, REQ-SRC-2

#### Scenario: Import a small file

- GIVEN an empty cookbook
- **WHEN** the cook imports `soup.txt`
- **THEN** the cookbook lists one recipe
- AND the recipe's title is "soup"

### Requirement: Reject locked files

When a cook imports a password-protected file, the system shall refuse it and say why.

#### Scenario: Import a locked PDF

- WHEN the cook imports a locked PDF
- THEN an error explains that locked files are not accepted
