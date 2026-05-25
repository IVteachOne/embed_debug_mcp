"""Default log filter patterns for embedded debugging."""

import re


DEFAULT_PATTERNS = [
    r"panic",
    r"Oops",
    r"BUG:",
    r"WARNING",
    r"ERROR",
    r"error",
    r"fail",
    r"fault",
    r"traceback",
    r"exception",
    r"segfault",
    r"assert",
]


def compile_patterns(patterns: list[str]) -> list[re.Pattern]:
    """Compile regex patterns, ignoring invalid ones."""
    compiled = []
    for p in patterns:
        try:
            compiled.append(re.compile(p, re.IGNORECASE))
        except re.error:
            pass
    return compiled


def matches_any(line: str, patterns: list[re.Pattern]) -> bool:
    """Check if a line matches any pattern."""
    return any(p.search(line) for p in patterns)
