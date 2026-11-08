# ADR 0001: Use SQLite for recipe storage

- **Status:** Accepted
- **Date:** 2026-01-15
- **Deciders:** The product owner

## Context and problem statement

The app stores recipes, tags and shopping lists. Which database should hold them?

## Decision drivers

- **Operations:** one small server, no separate database service to run.
- **Cost:** storage should cost nothing beyond the server.

## Considered options

1. SQLite
2. PostgreSQL

## Decision outcome

Chosen option: SQLite, because it needs no extra service and handles the expected load.

### Consequences

- Good, because backups are a single file copy.
- Bad, because writes are serialized.

### Confirmation

A review checks that no code depends on PostgreSQL-only features.

## Pros and cons of the options

### SQLite

- Good, because it is embedded and free.
- Bad, because concurrent writers wait for each other.

### PostgreSQL

- Good, because it scales to many writers.
- Bad, because it is one more service to run and back up.
