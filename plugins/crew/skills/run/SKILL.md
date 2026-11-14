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
4. **Pending end.** Run `crew watch --status`. If it says `ended`, a finished run was never
   reported: run `crew watch` and do step 8 for it before going on.
5. **Start**, only with the owner's go-ahead in this session. In herdr, open a tab for it and
   start the run there:

   ```sh
   herdr tab create --label "crew run" --no-focus
   herdr pane run <pane-id> "crew run --until <when> --pane <pane-id>"
   ```

   Use the pane id the first command prints. Outside herdr, ask the owner to start
   `crew run --until <when>` in a terminal of their own.
6. **Watch.** Right after starting, start `crew watch` with the Monitor tool and `timeout_ms`
   1800000, so each line it prints reaches you while you and the owner keep talking. When the
   Monitor expires (you get a notice), re-arm with plain `crew watch`: it resumes where the last
   one stopped. Without Monitor, run it in the background: then only the end arrives.
7. **Each `waiting on you:` line.** Tell the owner the item, its full URL (at least once in
   every message, repeated reports and summaries included) and what they are asked to do, in
   the per-ask wording of the `crew:inbox` skill. Offer to act on it now, with the owner's
   say-so, or to leave it for the end. Don't run `crew inbox` for this.
8. **The end lines.** Say why the run ended and list Started, Finished, Stuck and Paused with
   their URLs. Then:
   - if `crew watch` exited 2, or the reason starts with `error:`, leave the pane open and tell
     the owner to read it;
   - if `crew watch` exited 1 (`nothing to watch`) right after the start, the run didn't start:
     leave the pane open and tell the owner what it says and to look at the run tab;
   - otherwise close the pane with `herdr pane close <pane>`, using only the `run pane:` line;
     with no such line, there is nothing to close;
   - then use the `crew:inbox` skill.

Never start a run without the owner's say-so in this session. Tell the owner:

- the run stops by itself at the end time or the budget cap, and ends early when everything
  waits on them; work in progress is committed and pushed, and the next run resumes it;
- it waits out a full 5-hour usage window and continues;
- Ctrl-C in the run's tab stops it the same way;
- you report each item that newly waits on them, and the run's end.
