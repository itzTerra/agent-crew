"""Guards the public repo against references to private projects, people or machines."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXED_PATTERNS = ["/home/", "~/Projects", "@gmail.com", "@fi."]
PRIVATE_WORDS_FILE = ROOT / ".private-words"


def _tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    return [ROOT / name for name in out.split("\0") if name]


def _private_words() -> list[str]:
    if not PRIVATE_WORDS_FILE.exists():
        return []
    lines = PRIVATE_WORDS_FILE.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip()]


def test_no_private_references():
    patterns = [re.escape(p) for p in FIXED_PATTERNS + _private_words()]
    pattern = re.compile("|".join(patterns), re.IGNORECASE)
    hits = []
    for path in _tracked_files():
        if not path.is_file() or path == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for number, line in enumerate(text.splitlines(), start=1):
            match = pattern.search(line)
            if match:
                hits.append(f"{path.relative_to(ROOT)}:{number}: {match.group(0)!r}")
    assert not hits, "private references found:\n" + "\n".join(hits)
