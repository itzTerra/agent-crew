# Imports

## Purpose

Cooks bring their own recipes.

## Requirements

### Requirement: Keep recipes private

When a cook imports a recipe, the system shall show it only to that cook.

Satisfies: REQ-ARCH-1

#### Scenario: Another cook opens the link

- WHEN another cook opens the recipe's link
- THEN access is refused

### Requirement: Refuse locked files

When a cook imports a password-protected file, the system shall refuse it and say why.

Satisfies: REQ-SRC-1

#### Scenario: Import a locked PDF

- WHEN the cook imports a locked PDF
- THEN an error explains that locked files are not accepted
