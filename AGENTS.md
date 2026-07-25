# Agent instructions

This repository keeps its agent instructions in **[CLAUDE.md](CLAUDE.md)**, with
directory-specific notes in nested `CLAUDE.md` files (notably
[gyrinx/core/templates/CLAUDE.md](gyrinx/core/templates/CLAUDE.md) for template and
component work, and [gyrinx/core/CLAUDE.md](gyrinx/core/CLAUDE.md) for models,
views and tests).

Read those. This file exists only so tools that look for `AGENTS.md` find their way
there — deliberately a pointer rather than a copy, so the two cannot drift apart.

GitHub Copilot additionally reads [.github/copilot-instructions.md](.github/copilot-instructions.md)
and the path-scoped files under [.github/instructions/](.github/instructions/).
