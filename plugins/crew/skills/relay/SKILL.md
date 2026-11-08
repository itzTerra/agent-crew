---
name: relay
description: "Post the owner's feedback on a pull request, quoted and marked as the owner's words, and request changes. Run by the lead when the owner gives feedback in a session."
---

# Relay

Run by the lead, when the owner tells you feedback for a PR instead of writing it on GitHub.

1. Confirm which PR it is for (`gh pr view N`).
2. Post the owner's words **verbatim** as a quote, with this header and nothing added to the
   quote:

   ```
   Owner feedback (relayed):

   > <the owner's words, line by line>
   ```

   If you need to add context (for example which checklist step it refers to), put it after the
   quote under `Context (lead):`, clearly as yours.
   Use `gh pr comment N --body-file <file>` so line breaks and quotes survive.
3. Set the labels: add `crew:changes-requested` and remove `crew:owner-accept` or
   `crew:in-review` if present:
   `gh pr edit N --add-label crew:changes-requested --remove-label crew:owner-accept`.
4. Tell the owner it is posted, with the comment link.

If the feedback is an approval, ask the owner to approve the PR on GitHub themselves: only
approvals from `owner_login` count as the owner's acceptance.
