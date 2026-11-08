from crew.graph import (
    Unit,
    build_units,
    dependents_count,
    find_cycles,
    next_ready,
    owns_overlap,
)


def issue(
    number, deps=(), labels=(), owns=("src/x/**",), created="2026-01-01T00:00:00Z", body=None
):
    if body is None:
        dep_lines = "\n".join(f"- #{d}" for d in deps) or "none"
        own_lines = "\n".join(f"- {o}" for o in owns)
        body = (
            f"## Goal\n\nUnit {number}.\n\n## Owns\n\n{own_lines}\n\n"
            f"## Depends on\n\n{dep_lines}\n\n## Kind\n\ninternal\n"
        )
    return {
        "number": number,
        "title": f"Unit {number}",
        "body": body,
        "labels": [{"name": name} for name in labels],
        "state": "OPEN",
        "createdAt": created,
        "url": f"https://github.com/example/app/issues/{number}",
    }


def units_of(*issues):
    return build_units(list(issues))


def test_build_units_parses_body_and_skips_closed():
    closed = issue(9) | {"state": "CLOSED"}
    units = units_of(issue(1, deps=[9], labels=["crew:ready"]), closed)
    assert list(units) == [1]
    unit = units[1]
    assert isinstance(unit, Unit)
    assert (unit.depends_on, unit.owns, unit.kind, unit.labels) == (
        [9],
        ["src/x/**"],
        "internal",
        {"crew:ready"},
    )


def test_dependents_count_transitive():
    units = units_of(issue(1), issue(2, deps=[1]), issue(3, deps=[2]))
    assert dependents_count(units) == {1: 2, 2: 1, 3: 0}


def test_dependents_count_survives_cycle():
    units = units_of(issue(3, deps=[4]), issue(4, deps=[3]), issue(5, deps=[4]))
    assert dependents_count(units) == {3: 2, 4: 2, 5: 0}
    assert find_cycles(units) == [[3, 4]]


def test_self_dependency_is_a_cycle():
    assert find_cycles(units_of(issue(7, deps=[7]), issue(8))) == [[7]]


def test_owns_overlap():
    assert owns_overlap(["src/api/**"], ["src/api/auth.py"])
    assert owns_overlap(["src/api/auth.py"], ["src/api/**"])
    assert not owns_overlap(["src/api/**"], ["src/ui/**"])
    assert owns_overlap([], ["src/ui/**"])
    assert owns_overlap(["docs/*.md"], ["docs/specs/a/spec.md"])


def test_next_ready_respects_deps_and_overlap():
    units = units_of(
        issue(1, labels=["crew:ready"], owns=["src/api/**"]),
        issue(2, labels=["crew:ready"], owns=["src/api/auth.py"]),
        issue(3, labels=["crew:ready"], owns=["src/ui/**"]),
        issue(4, labels=["crew:ready"], deps=[1], owns=["src/db/**"]),
        issue(5, labels=["crew:ready"], deps=[99], owns=["src/jobs/**"]),
        issue(6, owns=["src/other/**"]),
    )
    assert next_ready(units, running=[], max_agents=5) == [1, 3, 5]
    assert next_ready(units, running=[3], max_agents=5) == [1, 5]


def test_next_ready_order_and_cycles():
    units = units_of(
        issue(1, labels=["crew:ready"], owns=["a/"], created="2026-01-02T00:00:00Z"),
        issue(2, labels=["crew:ready"], owns=["b/"], created="2026-01-01T00:00:00Z"),
        issue(3, labels=["crew:ready", "crew:do-first"], owns=["c/"]),
        issue(4, deps=[1], owns=["d/"]),
        issue(5, labels=["crew:ready"], deps=[6], owns=["e/"]),
        issue(6, labels=["crew:ready"], deps=[5], owns=["f/"]),
    )
    assert next_ready(units, running=[], max_agents=9) == [3, 1, 2]


def test_next_ready_skips_parked_units():
    units = units_of(issue(1, labels=["crew:ready", "crew:owner-decision"]))
    assert next_ready(units, running=[], max_agents=2) == []


def test_next_ready_respects_max_agents():
    units = units_of(*(issue(n, labels=["crew:ready"], owns=[f"m{n}/"]) for n in range(1, 6)))
    assert next_ready(units, running=[], max_agents=2) == [1, 2]
    assert next_ready(units, running=[1], max_agents=2) == [2]
    assert next_ready(units, running=[1, 2], max_agents=2) == []
