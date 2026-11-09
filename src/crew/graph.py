"""The dependency graph of open units and the order workers pick them in."""

import re
from dataclasses import dataclass

from crew.labels import IDEA
from crew.units import parse_unit_body

READY = "crew:ready"
ROUGH = "crew:rough"
DO_FIRST = "crew:do-first"
OWNER_PREFIX = "crew:owner-"
OWNER_ASKS = ("accept", "decision", "stuck", "proposal")
WAITING_ON_OWNER = frozenset(f"{OWNER_PREFIX}{ask}" for ask in OWNER_ASKS)
RUNNING = "crew:in-progress"
# Units with an open PR: they hold their owned paths but no agent slot.
BUSY_ORDER = ("crew:in-review", "crew:changes-requested", "crew:owner-accept", "crew:owner-stuck")
BUSY = frozenset(BUSY_ORDER)
_WILDCARD = re.compile(r"[*?\[]")


@dataclass
class Unit:
    """An open issue, with the parts of its body the graph needs."""

    number: int
    title: str
    labels: set[str]
    url: str
    created_at: str
    depends_on: list[int]
    owns: list[str]
    kind: str | None


@dataclass(frozen=True)
class Skipped:
    """A ready unit ``crew next`` leaves out, and why."""

    number: int
    reason: str


def label_names(item: dict) -> set[str]:
    """Label names of a gh issue or PR dict."""
    return {label["name"] for label in item.get("labels") or []}


def build_units(issues: list[dict]) -> dict[int, Unit]:
    """Turn gh issue dicts into units, keeping open issues only.

    A body without the unit sections still gives a unit, with no dependencies or owned paths.
    """
    units: dict[int, Unit] = {}
    for item in issues:
        if str(item.get("state", "OPEN")).upper() != "OPEN":
            continue
        body = parse_unit_body(item.get("body") or "")
        units[item["number"]] = Unit(
            number=item["number"],
            title=item.get("title", ""),
            labels=label_names(item),
            url=item.get("url", ""),
            created_at=item.get("createdAt") or "",
            depends_on=body.depends_on,
            owns=body.owns,
            kind=body.kind,
        )
    return units


def _dependents(units: dict[int, Unit]) -> dict[int, set[int]]:
    """Reverse edges: unit -> open units that depend on it directly."""
    reverse: dict[int, set[int]] = {number: set() for number in units}
    for unit in units.values():
        for dep in unit.depends_on:
            if dep in units:
                reverse[dep].add(unit.number)
    return reverse


def dependents_count(units: dict[int, Unit]) -> dict[int, int]:
    """For each open unit, how many open units depend on it directly or indirectly."""
    reverse = _dependents(units)
    counts: dict[int, int] = {}
    for start in units:
        seen = {start}
        stack = [start]
        while stack:
            for dependent in reverse[stack.pop()]:
                if dependent not in seen:
                    seen.add(dependent)
                    stack.append(dependent)
        counts[start] = len(seen) - 1
    return counts


def find_cycles(units: dict[int, Unit]) -> list[list[int]]:
    """Dependency cycles among open units, each sorted, as a sorted list.

    Uses Tarjan's strongly connected components, iteratively.
    """
    edges = {n: [d for d in u.depends_on if d in units] for n, u in units.items()}
    index: dict[int, int] = {}
    low: dict[int, int] = {}
    on_stack: set[int] = set()
    stack: list[int] = []
    cycles: list[list[int]] = []
    counter = 0

    for root in sorted(units):
        if root in index:
            continue
        work = [(root, 0)]
        while work:
            node, child = work.pop()
            if child == 0:
                index[node] = low[node] = counter
                counter += 1
                stack.append(node)
                on_stack.add(node)
            targets = edges[node]
            if child < len(targets):
                work.append((node, child + 1))
                target = targets[child]
                if target not in index:
                    work.append((target, 0))
                elif target in on_stack:
                    low[node] = min(low[node], index[target])
                continue
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                component = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                if len(component) > 1 or node in edges[node]:
                    cycles.append(sorted(component))
    return sorted(cycles)


def owns_overlap(a: list[str], b: list[str]) -> bool:
    """Whether two owned-path lists may touch the same files.

    Each glob is cut at its first wildcard to a path prefix; an empty list overlaps everything.
    """
    if not a or not b:
        return True
    prefixes_a = [_prefix(glob) for glob in a]
    prefixes_b = [_prefix(glob) for glob in b]
    return any(x.startswith(y) or y.startswith(x) for x in prefixes_a for y in prefixes_b)


def _prefix(glob: str) -> str:
    match = _WILDCARD.search(glob)
    return glob[: match.start()] if match else glob


def priority_key(do_first: bool, blocks: int, created_at: str, number: int) -> tuple:
    """Sort key shared by the inbox and the pick order."""
    return (not do_first, -blocks, created_at or "~", number)


def rough_order(units: dict[int, Unit]) -> list[int]:
    """Rough units in the order to refine them, the same order workers will pick them.

    Units waiting on the owner and parked ideas are left out. Open dependencies don't hold a
    unit back: refining ahead of the workers is the point.
    """
    counts = dependents_count(units)
    rough = [
        u
        for u in units.values()
        if ROUGH in u.labels and IDEA not in u.labels and not u.labels & WAITING_ON_OWNER
    ]
    rough.sort(
        key=lambda u: priority_key(DO_FIRST in u.labels, counts[u.number], u.created_at, u.number)
    )
    return [u.number for u in rough]


def next_ready(
    units: dict[int, Unit], running: list[int], max_agents: int, busy: list[int] = ()
) -> list[int]:
    """The units to start now, in pick order; see ``ready_report``."""
    return ready_report(units, running, max_agents, busy)[0]


def ready_report(
    units: dict[int, Unit], running: list[int], max_agents: int, busy: list[int] = ()
) -> tuple[list[int], list[Skipped]]:
    """The units to start now, in pick order, and why every other ready unit is left out.

    A unit is eligible when it is labeled ready, is not a parked idea, waits on nothing from
    the owner, every dependency is closed, and it is not in a dependency cycle. Units whose
    owned paths overlap a running, busy or already chosen unit are skipped. ``running`` units
    use agent slots; ``busy`` units (in review or waiting on the owner) only hold their paths.

    Returns:
        ``(picks, skipped)``: each ready unit not picked gets one ``Skipped`` with the
        first reason that applies, ordered by unit number.
    """
    in_cycle = {n for cycle in find_cycles(units) for n in cycle}
    counts = dependents_count(units)
    skipped: list[Skipped] = []
    eligible: list[Unit] = []
    for unit in units.values():
        if READY not in unit.labels:
            continue
        reason = _ineligible_reason(unit, units, running, busy, in_cycle)
        if reason:
            skipped.append(Skipped(unit.number, reason))
        else:
            eligible.append(unit)
    eligible.sort(
        key=lambda u: priority_key(DO_FIRST in u.labels, counts[u.number], u.created_at, u.number)
    )

    taken = [(n, units[n].owns) for n in [*running, *busy] if n in units]
    chosen: list[int] = []
    for unit in eligible:
        overlap = next((n for n, owns in taken if owns_overlap(unit.owns, owns)), None)
        if overlap is not None:
            skipped.append(Skipped(unit.number, f"owns overlap with #{overlap}"))
        elif len(chosen) >= max_agents - len(running):
            used = len(running) + len(chosen)
            skipped.append(
                Skipped(unit.number, f"WIP limit reached ({used} of {max_agents} agents)")
            )
        else:
            chosen.append(unit.number)
            taken.append((unit.number, unit.owns))
    skipped.sort(key=lambda s: s.number)
    return chosen, skipped


def _ineligible_reason(
    unit: Unit, units: dict[int, Unit], running, busy, in_cycle: set[int]
) -> str | None:
    if unit.number in running:
        return "already running"
    if unit.number in busy:
        label = next((name for name in BUSY_ORDER if name in unit.labels), None)
        return f"has an open PR ({label})" if label else "has an open PR"
    if IDEA in unit.labels:
        return f"is a parked idea ({IDEA})"
    if waiting := sorted(unit.labels & WAITING_ON_OWNER):
        return f"waits on the owner ({waiting[0]})"
    if unit.number in in_cycle:
        return "in a dependency cycle"
    if open_deps := [dep for dep in unit.depends_on if dep in units]:
        return "depends on open " + ", ".join(f"#{dep}" for dep in open_deps)
    return None
