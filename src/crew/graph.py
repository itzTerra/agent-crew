"""The dependency graph of open units and the order workers pick them in."""

import re
from dataclasses import dataclass

from crew.units import parse_unit_body

READY = "crew:ready"
DO_FIRST = "crew:do-first"
OWNER_PREFIX = "crew:owner-"
OWNER_ASKS = ("accept", "decision", "stuck", "proposal")
WAITING_ON_OWNER = frozenset(f"{OWNER_PREFIX}{ask}" for ask in OWNER_ASKS)
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


def next_ready(
    units: dict[int, Unit], running: list[int], max_agents: int, busy: list[int] = ()
) -> list[int]:
    """The units to start now, in pick order.

    A unit is eligible when it is labeled ready, waits on nothing from the owner, every
    dependency is closed, and it is not in a dependency cycle. Units whose owned paths
    overlap a running, busy or already chosen unit are skipped. ``running`` units use
    agent slots; ``busy`` units (in review or waiting on the owner) only hold their paths.
    """
    in_cycle = {n for cycle in find_cycles(units) for n in cycle}
    counts = dependents_count(units)
    eligible = [
        unit
        for unit in units.values()
        if READY in unit.labels
        and not unit.labels & WAITING_ON_OWNER
        and unit.number not in running
        and unit.number not in busy
        and unit.number not in in_cycle
        and not any(dep in units for dep in unit.depends_on)
    ]
    eligible.sort(
        key=lambda u: priority_key(DO_FIRST in u.labels, counts[u.number], u.created_at, u.number)
    )

    taken = [units[n].owns for n in [*running, *busy] if n in units]
    chosen: list[int] = []
    for unit in eligible:
        if len(chosen) >= max_agents - len(running):
            break
        if any(owns_overlap(unit.owns, owns) for owns in taken):
            continue
        chosen.append(unit.number)
        taken.append(unit.owns)
    return chosen
