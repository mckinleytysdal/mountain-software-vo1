"""Hard wording rule (CLAUDE.md): never write safe, unsafe, go, or no-go in
code, comments, labels or our own docs. SPEC.md, CLAUDE.md and the first
prompt state the rule itself, so they are exempt."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXEMPT = {"SPEC.md", "CLAUDE.md", "docs/first-prompt.md", "tests/test_wording.py"}
BANNED = re.compile(r"\b(safe|unsafe|no-go|go/no-go|safety rating)\b", re.IGNORECASE)


def _files():
    for pattern in ("src/**/*.py", "tests/**/*.py", "docs/**/*.md", "*.md", "data/routes/*.toml"):
        for p in ROOT.glob(pattern):
            rel = p.relative_to(ROOT).as_posix()
            if rel not in EXEMPT:
                yield rel, p


def test_no_banned_words():
    hits = []
    for rel, p in _files():
        for n, line in enumerate(p.read_text().splitlines(), 1):
            if BANNED.search(line):
                hits.append(f"{rel}:{n}: {line.strip()}")
    assert hits == []
