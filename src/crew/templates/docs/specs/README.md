# Living specs

How the product works **now**, one spec per feature area, at `docs/specs/<area>/spec.md`.
Copy `TEMPLATE.md` to start a new area.

- Each requirement is one EARS statement containing "shall", optionally followed by
  `Satisfies: REQ-…` with the requirement IDs it meets.
- Each requirement has at least one `#### Scenario:` with WHEN and THEN lines (GIVEN and AND
  are optional).
- A spec is edited in place by the PR that changes the behavior. It is never duplicated.
- Delta headings (`## ADDED Requirements` and the like) belong in issues, never here.

`crew check-docs` validates these rules in CI.
