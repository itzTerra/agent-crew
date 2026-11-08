# Imports

## Purpose

Cooks bring their own recipes.

## Requirements

### Requirement: Accept plain text

When a cook imports a TXT file, the system shall import it as a recipe.

#### Scenario: Import a small file

- WHEN the cook imports `soup.txt`
- THEN the cookbook lists one recipe

## ADDED Requirements

### Requirement: Accept PDF

When a cook imports a PDF file, the system shall import its text.

#### Scenario: Import a PDF

- WHEN the cook imports `soup.pdf`
- THEN the cookbook lists one recipe
