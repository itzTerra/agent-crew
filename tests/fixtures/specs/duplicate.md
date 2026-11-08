# Imports

## Purpose

Cooks bring their own recipes.

## Requirements

### Requirement: Accept plain text

When a cook imports a TXT file, the system shall import it as a recipe.

#### Scenario: Import a small file

- WHEN the cook imports `soup.txt`
- THEN the cookbook lists one recipe

### Requirement: Accept Plain Text

When a cook imports a TXT file twice, the system shall keep one copy.

#### Scenario: Import twice

- WHEN the cook imports `soup.txt` twice
- THEN the cookbook lists one recipe
