"""Rockwell ladder (RLL) rung text -> the condition each output instruction runs under.

A rung is instructions in series (``XIC(a)XIO(b)OTE(c);``) with parallel branches in brackets
(``[XIC(a) ,XIC(b) ]``).  Input instructions (contacts, comparisons, one-shots) narrow the rung
condition; every other instruction is an output that runs under the condition in force where it
stands, and passes it on.  A branch's condition is the OR of its legs.

    >>> rung_logic("[XIC(Start) ,XIC(Run) ]XIO(Stop)OTE(Run);")
    [('OTE(Run)', '(Start OR Run) AND NOT Stop')]

This lets a diff say *what changed in the logic* of a rung ("Run now also needs NOT Jam")
instead of only which instructions were added or removed.
"""

from __future__ import annotations

COMPARE = {"EQU": "=", "NEQ": "<>", "LES": "<", "LEQ": "<=", "GRT": ">", "GEQ": ">="}
INPUTS = {"XIC", "XIO", "ONS", "AFI", "CMP", "LIM", "MEQ", "NOP", *COMPARE}

TRUE = "TRUE"


class RungSyntaxError(ValueError):
    """The rung text could not be parsed (unbalanced brackets or parentheses)."""


def split_args(args: str) -> list[str]:
    """Split instruction operands at top-level commas (``Arr[i,j]`` and ``f(a,b)`` stay whole)."""
    out: list[str] = []
    depth = 0
    cur = ""
    for ch in args:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip() or out:
        out.append(cur.strip())
    return out


def _tokens(text: str) -> list[tuple[str, str]]:
    """("instr", "XIC(a)") / ("[", "") / (",", "") / ("]", "")."""
    out: list[tuple[str, str]] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in " \t\r\n;":
            i += 1
        elif ch in "[],":
            out.append((ch, ""))
            i += 1
        else:
            start = i
            while i < n and text[i] not in "(;[], \t\r\n":
                i += 1
            if i >= n or text[i] != "(":
                # an instruction without operands (rare: e.g. "NOP")
                out.append(("instr", text[start:i] + "()"))
                continue
            depth = 0
            while i < n:
                if text[i] == "(":
                    depth += 1
                elif text[i] == ")":
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
            else:
                raise RungSyntaxError(f"unbalanced parentheses in {text!r}")
            out.append(("instr", text[start:i].strip()))
    return out


def _wrap(term: str, op: str) -> str:
    depth = 0
    for i, ch in enumerate(term):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and term.startswith(op, i):
            return f"({term})"
    return term


def AND(*terms: str) -> str:
    parts = [t for t in terms if t and t != TRUE]
    if "FALSE" in parts:
        return "FALSE"
    if not parts:
        return TRUE
    return " AND ".join(_wrap(t, " OR ") for t in parts)


def OR(*terms: str) -> str:
    parts = [t for t in terms if t]
    if TRUE in parts:
        return TRUE
    parts = [t for t in parts if t != "FALSE"]
    if not parts:
        return "FALSE"
    return " OR ".join(_wrap(t, " AND ") if len(parts) > 1 else t for t in parts)


def _input(mnemonic: str, args: list[str]) -> str:
    if mnemonic == "XIC":
        return args[0] if args else "?"
    if mnemonic == "XIO":
        return f"NOT {args[0]}" if args else "NOT ?"
    if mnemonic == "AFI":
        return "FALSE"
    if mnemonic == "NOP":
        return TRUE
    if mnemonic in COMPARE and len(args) == 2:
        return f"{args[0]} {COMPARE[mnemonic]} {args[1]}"
    if mnemonic == "CMP" and args:
        return args[0]
    if mnemonic == "LIM" and len(args) == 3:
        return f"{args[0]} <= {args[1]} <= {args[2]}"
    return f"{mnemonic}({','.join(args)})"


def rung_logic(text: str) -> list[tuple[str, str]]:
    """(output instruction, condition) for every output on the rung, in rung order."""
    outputs: list[tuple[str, str]] = []
    _walk(_tokens(text), text, outputs)
    return outputs


def _walk(tokens: list[tuple[str, str]], text: str, outputs: list[tuple[str, str]]) -> None:
    pos = 0

    def series(cond: str, stop: set[str]) -> str:
        nonlocal pos
        while pos < len(tokens) and tokens[pos][0] not in stop:
            kind, value = tokens[pos]
            if kind == "[":
                pos += 1
                legs: list[str] = []
                while True:
                    legs.append(series(cond, {",", "]"}))
                    if pos >= len(tokens):
                        raise RungSyntaxError(f"unclosed branch in {text!r}")
                    sep = tokens[pos][0]
                    pos += 1
                    if sep == "]":
                        break
                cond = _merge(cond, legs)
                continue
            if kind in ",]":
                raise RungSyntaxError(f"unexpected {kind!r} in {text!r}")
            pos += 1
            mnemonic, _, rest = value.partition("(")
            args = split_args(rest[:-1]) if rest.endswith(")") else []
            if mnemonic in INPUTS:
                cond = AND(cond, _input(mnemonic, args))
            else:
                outputs.append((value, cond))
        return cond

    series(TRUE, set())
    if pos != len(tokens):
        raise RungSyntaxError(f"unbalanced branch in {text!r}")


def _merge(before: str, legs: list[str]) -> str:
    """Condition after a branch whose legs all started from ``before``."""
    if before == TRUE:
        return OR(*legs)
    prefix = before + " AND "
    rests: list[str] = []
    for leg in legs:
        if leg == before:
            return before  # one leg added nothing: the branch is always passed
        if not leg.startswith(prefix):
            return OR(*(_wrap(x, " OR ") for x in legs))
        rests.append(leg[len(prefix) :])
    return AND(before, OR(*rests))


def logic_delta(old: str, new: str) -> list[tuple[str, str | None, str | None]]:
    """Outputs whose condition differs between two rung texts: (output, old, new).

    An output on one side only has ``None`` on the other.  Outputs are matched by instruction
    text, in order, so a rung with two ``OTE(x)`` pairs them up one by one.
    """
    try:
        a, b = rung_logic(old), rung_logic(new)
    except RungSyntaxError:
        return []
    out: list[tuple[str, str | None, str | None]] = []
    remaining = list(b)
    for instr, cond in a:
        match = next((i for i, (ins, _) in enumerate(remaining) if ins == instr), None)
        if match is None:
            out.append((instr, cond, None))
            continue
        _, new_cond = remaining.pop(match)
        if new_cond != cond:
            out.append((instr, cond, new_cond))
    out += [(instr, None, cond) for instr, cond in remaining]
    return out
