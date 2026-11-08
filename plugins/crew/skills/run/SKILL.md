---
name: run
description: "Start an automated crew run with the owner: agree the end time, show the budget and a dry run, then start crew run in its own herdr tab. Run by the lead."
---

# Run

Run by the lead, with the owner. A run keeps up to `max_agents` agents busy until an end time
or the weekly budget cap, whichever comes first.

1. **End time.** Ask the owner when the run should stop, for example `07:00`, `Mon 07:00` (when
   starting on a Friday) or an ISO 8601 time. Repeat it back as a date and time and confirm it.
2. **Budget.** Run `crew budget` and show its output unchanged: the cap in force and the
   latest usage reading. If the owner wants a higher cap for this week, use the `crew:budget`
   skill. A one-off cap for this run only is `--cap N`.
3. **Dry run.** Run `crew run --until <when> --dry-run --once` in the project root and show its
   output unchanged: the housekeeping it would do, the agents it would start, and why the rest
   waits. If it says nothing would start, say why (the `waiting:` lines) before going on.
4. **Start**, only with the owner's go-ahead in this session. In herdr, open a tab for it and
   start the run there:

   ```sh
   herdr tab create --label "crew run" --no-focus
   herdr pane run <pane-id> "crew run --until <when>"
   ```

   Use the pane id the first command prints. Outside herdr, ask the owner to start
   `crew run --until <when>` in a terminal of their own.

Never start a run without the owner's say-so in this session. Tell the owner:

- the run stops by itself at the end time or the budget cap, and ends early when everything
  waits on them; work in progress is committed and pushed, and the next run resumes it;
- it waits out a full 5-hour usage window and continues;
- Ctrl-C in the run's tab stops it the same way;
- the run's own log is in that tab; what needs them shows up in `crew inbox`.
