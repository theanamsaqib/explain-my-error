"""analyze_code tool: static analysis (no LLM) that grounds the agent in facts.

It parses the error text, finds the failing line, and uses Python's `ast` module to look for
the classic patterns behind each common error type. The output is a structured hint for the
LLM, not a final answer.
"""

from __future__ import annotations

import ast
import difflib
import re

from app.models.schemas import CodeAnalysis, SuspiciousLine

_TYPE_LINE = re.compile(r"^(?:[\w.]+\.)?([A-Z]\w*(?:Error|Exception|Warning|Exit|Interrupt))\b\s*:?\s*(.*)$")
_FILE_LINE = re.compile(r'File "([^"]+)", line (\d+)')
_STDLIB_MARKERS = ("site-packages", "/lib/python", "\\Lib\\", "<frozen")

CONCEPTS = {
    "IndexError": "Zero-based indexing and list bounds",
    "KeyError": "Dictionary keys and safe lookups",
    "NameError": "Variable scope and defining names before use",
    "UnboundLocalError": "Local vs global scope",
    "TypeError": "Type compatibility and function signatures",
    "ValueError": "Input validation and type conversion",
    "AttributeError": "Objects, attributes and methods",
    "ZeroDivisionError": "Guarding against division by zero",
    "SyntaxError": "Python syntax rules",
    "IndentationError": "Python indentation rules",
    "ImportError": "Modules and imports",
    "ModuleNotFoundError": "Modules and imports",
    "TimeoutError": "Loop termination conditions",
    "LogicError": "Program logic and expected behaviour",
}

_BUILTIN_TYPES = {"list": list, "str": str, "dict": dict, "int": int, "float": float, "tuple": tuple, "set": set}


def parse_error(error: str) -> tuple[str, str]:
    """Return (error_type, message) from a traceback or a bare error line."""
    lines = [ln.strip() for ln in error.strip().splitlines() if ln.strip()]
    for ln in reversed(lines):
        m = _TYPE_LINE.match(ln)
        if m:
            return m.group(1), m.group(2).strip()
    low = error.lower()
    if "timed out" in low or "infinite loop" in low or "too much output" in low:
        return "TimeoutError", (lines[-1] if lines else "")
    if "wrong output" in low or "expected output" in low:
        return "LogicError", (lines[0] if lines else "")
    return "Unknown", (lines[-1] if lines else "")


def find_error_line(error: str) -> int | None:
    found = [(f, int(n)) for f, n in _FILE_LINE.findall(error)]
    user = [n for f, n in found if not any(m in f for m in _STDLIB_MARKERS)]
    if user:
        return user[-1]
    if found:
        return found[-1][1]
    plain = re.findall(r"\bline (\d+)\b", error)
    return int(plain[-1]) if plain else None


class _Finder:
    def __init__(self, code: str, tree: ast.AST | None) -> None:
        self.code = code
        self.lines = code.splitlines()
        self.tree = tree
        self.found: dict[int, SuspiciousLine] = {}

    def text(self, line: int) -> str:
        return self.lines[line - 1].rstrip() if 1 <= line <= len(self.lines) else ""

    def add(self, line: int | None, reason: str) -> None:
        if line is None or not (1 <= line <= len(self.lines)) or line in self.found:
            return
        self.found[line] = SuspiciousLine(line=line, code=self.text(line), reason=reason)

    def nodes(self, kind: type) -> list:
        return [n for n in ast.walk(self.tree) if isinstance(n, kind)] if self.tree else []

    def segment(self, node: ast.AST) -> str:
        return ast.get_source_segment(self.code, node) or ""


def _is_len_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "len"


def _plus_positive(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Add)
        and _is_len_call(node.left)
        and isinstance(node.right, ast.Constant)
        and isinstance(node.right.value, int)
        and node.right.value >= 1
    )


def _heuristics(f: _Finder, err_type: str, msg: str) -> tuple[str, list[str]]:
    """Add suspicious lines to f; return (likely_cause, extra_notes)."""
    cause = ""

    if err_type == "IndexError":
        for call in f.nodes(ast.Call):
            if isinstance(call.func, ast.Name) and call.func.id == "range":
                for arg in call.args:
                    if _plus_positive(arg):
                        f.add(call.lineno, f"`{f.segment(call)}` produces the index len(...)+k, which is past the last valid index.")
                        cause = "A loop range runs one step past the end of the sequence (off-by-one)."
        for sub in f.nodes(ast.Subscript):
            if _is_len_call(sub.slice):
                f.add(sub.lineno, "Indexing with len(x) is one past the last element; the last index is len(x) - 1.")
                cause = cause or "Indexing with len(x) instead of len(x) - 1."
        cause = cause or "An index is outside the valid range 0 .. len(sequence) - 1."

    elif err_type == "KeyError":
        key = msg.strip()
        try:
            key_val = ast.literal_eval(key)
        except (ValueError, SyntaxError):
            key_val = None
        for sub in f.nodes(ast.Subscript):
            if isinstance(sub.slice, ast.Constant) and sub.slice.value == key_val:
                f.add(sub.lineno, f"Looks up key {key} directly; it raises KeyError if the key is missing.")
        cause = f"The dictionary has no key {key}. Check the spelling or use .get() / an `in` check."

    elif err_type == "NameError":
        m = re.search(r"name '(\w+)'", msg)
        name = m.group(1) if m else ""
        defined = _defined_names(f)
        close = difflib.get_close_matches(name, defined, n=1, cutoff=0.6) if name else []
        for n in f.nodes(ast.Name):
            if n.id == name and isinstance(n.ctx, ast.Load):
                hint = f" Did you mean '{close[0]}'?" if close else ""
                f.add(n.lineno, f"'{name}' is used here but never defined before this point.{hint}")
        cause = f"'{name}' is used before it is defined" + (f" (maybe a typo for '{close[0]}')." if close else ".")

    elif err_type == "UnboundLocalError":
        m = re.search(r"variable '(\w+)'", msg)
        name = m.group(1) if m else ""
        for fn in f.nodes(ast.FunctionDef):
            assigns = [n for n in ast.walk(fn) if isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Store)]
            if assigns:
                f.add(assigns[0].lineno, f"Assigning '{name}' inside '{fn.name}' makes it local to the whole function.")
        cause = f"'{name}' is assigned inside the function, so Python treats it as local, but it is read before that assignment."

    elif err_type == "AttributeError":
        m = re.search(r"'(\w+)' object has no attribute '(\w+)'", msg)
        tname, attr = (m.group(1), m.group(2)) if m else ("", "")
        close = []
        if tname in _BUILTIN_TYPES and attr:
            close = difflib.get_close_matches(attr, dir(_BUILTIN_TYPES[tname]), n=2, cutoff=0.5)
        for node in f.nodes(ast.Attribute):
            if node.attr == attr:
                hint = f" Similar methods: {', '.join(close)}." if close else ""
                f.add(node.lineno, f"`.{attr}` is not an attribute of a '{tname}' object.{hint}")
        cause = f"A '{tname}' object has no attribute '{attr}'." + (f" Did you mean {close[0]}?" if close else "")

    elif err_type == "TypeError":
        cause = f"An operation or call received a value of the wrong type or the wrong number of arguments ({msg})."
        m = re.search(r"(\w+)\(\) (?:takes|missing)", msg)
        if m:
            fname = m.group(1)
            for fn in f.nodes(ast.FunctionDef):
                if fn.name == fname:
                    f.add(fn.lineno, f"Definition of '{fname}' expects {len(fn.args.args)} parameter(s).")
            for call in f.nodes(ast.Call):
                if isinstance(call.func, ast.Name) and call.func.id == fname:
                    f.add(call.lineno, f"Call to '{fname}' passes {len(call.args) + len(call.keywords)} argument(s).")
            cause = f"'{fname}' was called with a different number of arguments than it defines."
        if "NoneType" in msg:
            for fn in f.nodes(ast.FunctionDef):
                returns = [r for r in ast.walk(fn) if isinstance(r, ast.Return) and r.value is not None]
                if not returns:
                    f.add(fn.lineno, f"'{fn.name}' never returns a value, so calling it gives None.")
                    cause = f"A value is None; function '{fn.name}' has no `return <value>`."
        if "unsupported operand" in msg or "can only concatenate" in msg or "must be str" in msg:
            cause = f"Two values of incompatible types were combined ({msg})."

    elif err_type == "ZeroDivisionError":
        for node in f.nodes(ast.BinOp):
            if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)):
                f.add(node.lineno, f"Divisor `{f.segment(node.right)}` can be zero here.")
        cause = "A division or modulo operation has a divisor that is zero."

    elif err_type == "ValueError":
        for call in f.nodes(ast.Call):
            if isinstance(call.func, ast.Name) and call.func.id in ("int", "float"):
                f.add(call.lineno, f"`{f.segment(call)}` raises ValueError if the text is not a valid number.")
        cause = f"A function got a value of the right type but an unacceptable content ({msg})."

    elif err_type in ("ImportError", "ModuleNotFoundError"):
        for node in f.nodes(ast.Import) + f.nodes(ast.ImportFrom):
            f.add(node.lineno, "Import statement that fails.")
        cause = f"Python cannot import the requested module or name ({msg})."

    elif err_type == "TimeoutError":
        for loop in f.nodes(ast.While):
            test_names = {n.id for n in ast.walk(loop.test) if isinstance(n, ast.Name)}
            changed = {
                t.id
                for n in ast.walk(loop)
                for t in ([n.target] if isinstance(n, ast.AugAssign) else getattr(n, "targets", []) if isinstance(n, ast.Assign) else [])
                if isinstance(t, ast.Name)
            }
            has_exit = any(isinstance(n, (ast.Break, ast.Return)) for n in ast.walk(loop))
            always_true = isinstance(loop.test, ast.Constant) and bool(loop.test.value)
            if (always_true and not has_exit) or (test_names and not (test_names & changed) and not has_exit):
                f.add(loop.lineno, "This loop's condition can never become false: nothing in the body changes it.")
        cause = "The program never finished: a loop probably has no way to stop."

    elif err_type == "LogicError":
        cause = "The program ran without an exception, but its output is not what was expected."

    return cause, []


def _defined_names(f: _Finder) -> list[str]:
    names: set[str] = set()
    for n in f.nodes(ast.Name):
        if isinstance(n.ctx, ast.Store):
            names.add(n.id)
    for n in f.nodes(ast.FunctionDef) + f.nodes(ast.ClassDef):
        names.add(n.name)
    for n in f.nodes(ast.arg):
        names.add(n.arg)
    for n in f.nodes(ast.Import) + f.nodes(ast.ImportFrom):
        for alias in n.names:
            names.add((alias.asname or alias.name).split(".")[0])
    return sorted(names)


def analyze_code(code: str, error: str) -> CodeAnalysis:
    err_type, msg = parse_error(error)
    line_no = find_error_line(error)

    tree: ast.AST | None = None
    syntax_ok = True
    syntax_info: tuple[int | None, str] | None = None
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        syntax_ok = False
        syntax_info = (exc.lineno, exc.msg)
        if err_type in ("Unknown",):
            err_type, msg = "SyntaxError", exc.msg

    finder = _Finder(code, tree)

    # The line Python itself reported always comes first.
    if line_no is not None:
        finder.add(line_no, f"Python reported {err_type} on this line." if err_type != "Unknown" else "Reported by the error message.")

    cause = ""
    if not syntax_ok and syntax_info:
        finder.add(syntax_info[0], f"Syntax problem: {syntax_info[1]}")
        cause = f"The code cannot be parsed: {syntax_info[1]}."
        if err_type not in ("SyntaxError", "IndentationError", "TabError"):
            err_type = "SyntaxError"
    elif tree is not None:
        cause, _ = _heuristics(finder, err_type, msg)

    if not cause:
        cause = msg or "Could not determine a cause from the error text."

    ordered = sorted(finder.found.values(), key=lambda s: (s.line != line_no, s.line))[:6]
    return CodeAnalysis(
        error_type=err_type,
        error_message=msg,
        line_number=line_no if line_no is not None else (ordered[0].line if ordered else None),
        suspicious_lines=ordered,
        likely_cause=cause,
        concept_hint=CONCEPTS.get(err_type, "General debugging"),
        syntax_ok=syntax_ok,
    )
