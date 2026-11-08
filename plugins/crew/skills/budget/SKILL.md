---
name: budget
description: "Show the weekly budget cap and usage, or raise or reset this week's cap for crew runs. Run by the lead with the owner."
---

# Budget

Run by the lead, with the owner. The cap counts the whole account's weekly usage, the owner's own
sessions included.

- **Show:** `crew budget`. Show its output unchanged: the cap in force (the default from
  `budget_cap_percent`, or this week's raise and when it ends) and the latest usage reading with
  its age.
- **Raise for this week:** only when the owner asks ("this week, up to 95%"):
  `crew budget --week 95`. It lasts until the weekly limit resets, then the default applies
  again. It needs a usage reading for the reset time; if there is none yet, start any crew agent
  session first (`crew agent lead --check` is not enough: the reading comes from a session's
  status line).
- **Back to the default:** `crew budget --reset`.

Never change the cap without the owner's say-so in this session.
