"""``crew init``: write the project's crew files, never overwriting existing ones."""

from importlib.resources import files
from pathlib import Path

from crew import __version__

GITIGNORE_ENTRIES = (".crew/state.json", ".crew/run.json")

# Target path in the project -> template path inside the crew package.
TEMPLATES = {
    ".crew/config.yaml": "crew/config.yaml",
    ".github/ISSUE_TEMPLATE/unit.md": "github/ISSUE_TEMPLATE/unit.md",
    ".github/pull_request_template.md": "github/pull_request_template.md",
    ".github/workflows/crew-docs.yml": "github/workflows/crew-docs.yml",
    "docs/specs/README.md": "docs/specs/README.md",
    "docs/specs/TEMPLATE.md": "docs/specs/TEMPLATE.md",
    "docs/pitches/README.md": "docs/pitches/README.md",
    "docs/pitches/TEMPLATE.md": "docs/pitches/TEMPLATE.md",
    "docs/adr/TEMPLATE.md": "docs/adr/TEMPLATE.md",
}


def read_template(name: str) -> str:
    """Return a template file shipped in the crew package."""
    return files("crew").joinpath("templates", name).read_text(encoding="utf-8")


def init_project(root: Path, repo: str, owner: str, agent: str) -> list[Path]:
    """Write the missing crew files under ``root`` and return the paths written.

    Existing files are left byte-identical; ``.gitignore`` only gets the local state
    entries appended when it lacks them.
    """
    written: list[Path] = []
    for target, template in TEMPLATES.items():
        path = root / target
        if path.exists():
            continue
        text = read_template(template)
        text = text.replace("{version}", __version__) if target.endswith("crew-docs.yml") else text
        if target == ".crew/config.yaml":
            text = text.replace("{repo}", repo).replace("{owner}", owner).replace("{agent}", agent)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.append(path)
    if _ensure_gitignore(root / ".gitignore"):
        written.append(root / ".gitignore")
    return written


def _ensure_gitignore(path: Path) -> bool:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    present = {line.strip() for line in text.splitlines()}
    missing = [entry for entry in GITIGNORE_ENTRIES if entry not in present]
    if not missing:
        return False
    if text and not text.endswith("\n"):
        text += "\n"
    path.write_text(text + "".join(f"{entry}\n" for entry in missing), encoding="utf-8")
    return True
