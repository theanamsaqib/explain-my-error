"""generate_diff tool: a human-readable, UI-friendly diff between original and fixed code."""

from __future__ import annotations

import difflib
import re

from app.models.schemas import DiffLine, DiffResult

_HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def generate_diff(original: str, fixed: str, context: int = 2) -> DiffResult:
    a = original.splitlines()
    b = fixed.splitlines()
    raw = list(
        difflib.unified_diff(a, b, fromfile="original.py", tofile="fixed.py", lineterm="", n=context)
    )

    lines: list[DiffLine] = []
    old_no = new_no = 0
    for row in raw:
        if row.startswith(("---", "+++")):
            continue
        hunk = _HUNK.match(row)
        if hunk:
            old_no, new_no = int(hunk.group(1)), int(hunk.group(2))
            continue
        if row.startswith("+"):
            lines.append(DiffLine(type="add", text=row[1:], new_no=new_no))
            new_no += 1
        elif row.startswith("-"):
            lines.append(DiffLine(type="remove", text=row[1:], old_no=old_no))
            old_no += 1
        else:
            lines.append(DiffLine(type="context", text=row[1:], old_no=old_no, new_no=new_no))
            old_no += 1
            new_no += 1

    return DiffResult(
        unified_diff="\n".join(raw),
        lines=lines,
        added=sum(1 for ln in lines if ln.type == "add"),
        removed=sum(1 for ln in lines if ln.type == "remove"),
        changed=bool(raw),
    )
