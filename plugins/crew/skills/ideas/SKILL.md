---
name: ideas
description: "Park one or many ideas as crew:idea issues without the pitch challenge, or go through the parked ideas with the owner and promote one to a pitch. Use when the owner wants an idea recorded for later, or asks to go through the ideas. Run by the lead."
---

# Ideas

Run by the lead, with the owner. A parked idea is an issue labeled `crew:idea` and one priority label
(`crew:must`, `crew:should` or `crew:later`), no other crew label: not a bet, not work, not
waiting on the owner.

## Park

For each idea the owner gives, one or a list:

1. Search the open issues for one that already covers it:
   `gh issue list --state open --search "<a few words of the idea>"`.
2. If one covers it, comment the owner's words there, quoted as theirs.
3. Otherwise pick its priority: the highest priority of the requirements it serves, if it links
   any; else suggest one with a one-line reason and let the owner confirm or change it.
4. File an issue labeled only `crew:idea` and that priority, with a short title and a body of:
   - the owner's words, quoted as theirs;
   - where it came from (this session, a PR link, the baseline).

No challenge and no brainstorming. Ask only what you need to tell two ideas apart. Then report
each issue you filed or commented on, with its full URL.

## Go through

1. List the parked ideas: `gh issue list --label crew:idea --state open`. Show them by
   priority (`crew:must` first, then `crew:should`, then `crew:later`; oldest first within one),
   each with its priority and full URL, and suggest the top one.
2. The owner picks one. Run the `crew:pitch` skill on it.
3. If the owner drops it, close the issue with their reason quoted.
4. If it survives, the pitch PR body says `From idea #N`, never `Closes #N`: a closing reference
   would make the run treat the idea as the PR's unit. Once the pitch PR is open, close the idea
   issue with a comment linking the PR. From then on the pitch PR is the only record.
5. If the owner later declines the bet:
   - "not now": reopen the idea issue, make sure it still has `crew:idea`, and comment a link
     to the closed pitch PR;
   - "no": leave it closed.

Never promote an idea without the owner's say-so in this session.
