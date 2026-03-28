#!/usr/bin/env python3
"""Template linter for Gyrinx design system conventions.

Scans Django templates for deprecated patterns and design system violations.
Run: python scripts/lint_templates.py
"""

import re
import sys
from pathlib import Path

# Directories to scan
TEMPLATE_DIRS = [
    Path("gyrinx/core/templates"),
    Path("gyrinx/templates"),
    Path("gyrinx/pages/templates"),
]

# Files/dirs to skip
SKIP_PATTERNS = [
    "debug/design_system.html",  # Design system page intentionally shows deprecated patterns
    "__pycache__",
]

# Rules: (pattern, message, severity)
RULES = [
    # Deprecated class migrations
    (
        r'class="[^"]*\btext-muted\b',
        "text-muted is deprecated — use text-secondary",
        "error",
    ),
    (
        r'class="[^"]*\bsmall\b(?!-)',
        ".small class is deprecated — use fs-7 (check it's not <small> tag or form-control-sm)",
        "warning",
    ),
    # Badge format
    (
        r'class="[^"]*\bbadge\b[^"]*(?<!text-)bg-(?:primary|secondary|success|danger|warning|info)(?![-\w])',
        "Badge uses bg-* — migrate to text-bg-* format",
        "error",
    ),
    # Icon format
    (
        r'class="[^"]*\bbi bi-',
        "Icon uses space-separated format (bi bi-*) — use hyphenated (bi-*)",
        "error",
    ),
    # Removed icons
    (
        r"\bbi-check-circle\b",
        "bi-check-circle is removed — use bi-check-lg",
        "error",
    ),
    (
        r"\bbi-plus-circle\b",
        "bi-plus-circle is removed — use bi-plus-lg",
        "error",
    ),
    # Alert without alert-icon
    (
        r'class="[^"]*\balert\b[^"]*\balert-(?:success|danger|warning|info|secondary|primary)\b(?![^"]*\balert-icon\b)',
        "Alert without alert-icon class — add alert-icon for consistent layout",
        "warning",
    ),
    # Inline styles
    (
        r'\bstyle="[^"]*(?:color|background|font-size|margin|padding)',
        "Inline style with CSS property — use Bootstrap classes or design tokens",
        "warning",
    ),
]


def should_skip(path: Path) -> bool:
    """Check if a file should be skipped."""
    path_str = str(path)
    return any(skip in path_str for skip in SKIP_PATTERNS)


def lint_file(path: Path) -> list[tuple[int, str, str, str]]:
    """Lint a single template file. Returns list of (line_num, line, message, severity)."""
    violations = []
    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return violations

    for line_num, line in enumerate(content.splitlines(), 1):
        for pattern, message, severity in RULES:
            if re.search(pattern, line):
                # Skip if it's in a comment
                stripped = line.strip()
                if stripped.startswith("{#") or stripped.startswith("<!--"):
                    continue
                violations.append((line_num, line.strip(), message, severity))

    return violations


def main():
    """Run the template linter."""
    total_violations = 0
    total_errors = 0
    total_warnings = 0
    files_with_violations = 0

    for template_dir in TEMPLATE_DIRS:
        if not template_dir.exists():
            continue

        for path in sorted(template_dir.rglob("*.html")):
            if should_skip(path):
                continue

            violations = lint_file(path)
            if violations:
                files_with_violations += 1
                rel_path = path
                print(f"\n{rel_path}")
                for line_num, line, message, severity in violations:
                    marker = "ERROR" if severity == "error" else "WARN "
                    print(f"  {marker} L{line_num}: {message}")
                    if severity == "error":
                        total_errors += 1
                    else:
                        total_warnings += 1
                    total_violations += 1

    print(f"\n{'=' * 60}")
    print(
        f"Files scanned: {sum(1 for d in TEMPLATE_DIRS if d.exists() for _ in d.rglob('*.html'))}"
    )
    print(f"Files with violations: {files_with_violations}")
    print(
        f"Total violations: {total_violations} ({total_errors} errors, {total_warnings} warnings)"
    )

    if total_errors > 0:
        print("\nFix errors before merging. Warnings are advisory.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
