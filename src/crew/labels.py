"""The crew label set. Every label starts with ``crew:``."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Label:
    """One GitHub label: name, 6-digit hex color without ``#``, and a description."""

    name: str
    color: str
    description: str


LABELS: list[Label] = [
    # Work state.
    Label("crew:rough", "d4c5f9", "Not yet refined to the definition of ready."),
    Label("crew:ready", "0e8a16", "Meets the definition of ready; a worker may take it."),
    Label("crew:in-progress", "fbca04", "A worker is implementing it."),
    Label("crew:in-review", "1d76db", "Waiting for the agent review gate."),
    Label("crew:changes-requested", "e99695", "Review or owner feedback must be addressed."),
    # Waiting on the owner.
    Label("crew:owner-accept", "b60205", "Waiting for the owner to accept the work."),
    Label("crew:owner-decision", "b60205", "Waiting for the owner to decide a question."),
    Label("crew:owner-stuck", "b60205", "Failed review three times and needs the owner."),
    Label("crew:owner-proposal", "b60205", "A proposal waiting for the owner's pitch challenge."),
    # Priority and kind.
    Label("crew:do-first", "5319e7", "The owner wants this before anything else."),
    Label("crew:owner-facing", "c5def5", "Needs the owner's acceptance before merging."),
    Label("crew:internal", "bfdadc", "Merges after review and CI without the owner."),
]
