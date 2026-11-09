# The lead watches the run

## Why

Today the lead starts `crew run` in its own herdr tab and forgets about it. The owner, back from
being away, has to find the run tab, read terse log lines, and then still ask the lead for the
inbox to learn where things stand. The owner wants to keep the lead open (for example on a second
monitor) and have it say, as things happen, what needs them, and at the end, what the run did and
what is left.

## Goals

1. **Live items.** While a run is going, each time an issue or PR starts waiting on the owner
   (`accept`, `decision`, `stuck`, `proposal`), the lead tells the owner in its pane: the item,
   its full URL and what the owner is asked to do (the same wording the `crew:inbox` skill uses
   per ask). The owner may act on it right away (relay, record a decision, open the PR) while the
   run keeps going, or leave it for later. The supervisor picks up what the owner did on its next
   poll, as it already does.
2. **End of run.** When the run ends, the lead says why it ended (end time, budget cap, everything
   waits on the owner, Ctrl-C, error) and lists what was started, finished, stuck and paused,
   with URLs. Then it runs the `crew:inbox` skill (plain `crew inbox`, the owner's session) and
   offers to work through it.
3. **Cleanup.** After a run that ended without an error, the lead closes the run's herdr pane
   (the tab it created in the `crew:run` skill). After an error it leaves the pane open and says
   so, so the owner can read it.
4. **Re-attach.** If the lead session starts while a run is active (live pid in
   `.crew/run.json`), the lead says so and offers to watch it again. On re-attach it first gives
   one short catch-up list of every item that came in since the run started (the owner may
   already have handled some; that is accepted), then goes live with new items only.
5. **Unwatched end.** If the lead session starts after a run ended and nobody reported that end,
   the lead gives the end-of-run report (goal 2, with cleanup) as if it had been watching. An
   end is reported once: a later session doesn't repeat it.

## Non-goals

- No push, desktop or phone notifications. The message in the lead's pane is enough.
- The lead never acts on an item without the owner's say-so, same as the inbox rules.
- Live items don't mark the inbox as seen; only the owner's `crew inbox` pass does.
- No change to what the supervisor does with agents, or to when a run ends.
- Closing the lead session stops only the watching; the run goes on.

## Anti-goals

- The lead flooding the owner: one message per item that newly waits, not a repeat every poll,
  and nothing for items that were already waiting when the run started (the end-of-run inbox
  covers those).
- The watcher costing GitHub calls of its own on top of the supervisor's polling.

## How (decided)

- **The supervisor reports, the watcher relays.** The supervisor already takes a GitHub snapshot
  every tick. It computes the owner's inbox from that snapshot (`crew.inbox.owner_inbox`) and
  appends an event to a gitignored file `.crew/run-events.jsonl` whenever an `(number, ask)` pair
  appears that wasn't there on the previous tick. The first tick records the starting set as a
  baseline without events. When the run ends (any end, including errors and Ctrl-C, after the
  wind-down), it appends an `end` event carrying the reason and the summary lists (started,
  finished, stuck, paused) that `_print_summary` prints today. Each new run truncates the file.
  Dry runs write nothing.
- **A new command, `crew run watch`** (or `crew watch`; builder's call on the name, it must
  fit the CLI's style), prints one human-readable line per event as it is appended, and exits
  after printing the `end` event. If no run is active and the file has no `end` event, it says
  so and exits non-zero. It reads only the local file: no GitHub calls.
- **The lead uses Claude Code's Monitor tool** (a background command whose output lines wake the
  session) on that command right after starting the run, so the owner can keep talking to the
  lead meanwhile. An event that arrives mid-turn shows up when the turn ends.
- **Skill and agent text.** The `crew:run` skill gains the watch step, what to say per live
  item, the end-of-run steps (summary, cleanup, `crew:inbox`), and the re-attach check. The lead
  agent's *Runs* section points to it. The README and `docs/workflow.md` mention that the lead
  reports live items and the end of the run.

## Calls made in design (not discussed with the owner)

- **Truncation and stale events.** The events file is truncated only once a run has really
  started (after `_adopt` succeeds, not in a dry run), so a rejected second `crew run` never
  wipes a live run's events. Each event carries a run id (for example the pid and start time,
  also written to `run.json`) so the watcher ignores events from an earlier run.
- **Runs that end without an `end` event** (start-up failure, crash, kill): the watcher exits
  non-zero when the run's pid is gone and no `end` event for this run was written. The lead
  treats that as an error: says the run stopped without a report, leaves the pane open and
  points the owner at it, then runs `crew:inbox`.
- **Catch-up and "reported once".** The watcher can replay the run's events from the start
  (for the re-attach catch-up, which the lead condenses into one list) or follow only new ones.
  Printing the `end` event marks it reported (in a local `.crew` file), so the session-start
  check finds an unreported end at most once.
- **Runs the lead didn't start.** The watch also works for a run the owner started in their own
  terminal (it reads only `.crew` files); there is just no pane to close. Non-dry `--once` runs
  aren't watched.

## Left to the builder

- The event line format, as long as each line names the item (`#N`), its ask, its title and its
  full URL, and the `end` line carries the reason and the summary.
- How the lead learns the run's pane id on re-attach (for example `crew run` recording it in
  `run.json` when herdr exposes it), or skipping cleanup when it isn't known.
- How the watcher follows the file (polling interval, handling a truncated file).
- Tests, following the existing `tests/supervisor` fakes.
