# LLM Integration Testing Framework

Design document for adding LLM-driven browser integration tests to Gyrinx.

## Problem Statement

Gyrinx has 1,952 pytest tests using the Django test client for HTTP-level assertions, plus a
manual test plan generator (`/manual-test-plan`) for Claude for Chrome. What's missing is
**automated browser-level integration tests** that verify UI behaviour, form interactions, and
end-to-end workflows as a real user would experience them.

LLM-driven testing is a new category that sits between:
- **Django test client tests** (fast, no JS, no real browser)
- **Manual QA** (slow, high-fidelity, human-driven)

The goal is to get high-fidelity browser testing that can be authored in natural language and
executed automatically.

## Landscape Analysis

### Tools Evaluated

| Tool | What It Is | Maturity | Fit for Gyrinx |
|------|-----------|----------|----------------|
| **Playwright MCP** | Microsoft's MCP server exposing Playwright browser automation via accessibility snapshots | Production-ready, active development | **Best fit** - accessibility-first, deterministic, token-efficient |
| **Chrome DevTools MCP** | Google's MCP server wrapping Chrome DevTools Protocol (26 tools) | Stable, official | Good alternative - richer DevTools integration (performance traces, network inspection) |
| **Rodney** | Simon Willison's CLI wrapper around Rod (Go CDP library) for multi-turn browser sessions | New (Feb 2026), lightweight | Interesting for demo/verification workflows, not for CI |
| **Showboat** | CLI tool for agents to build Markdown demo documents with embedded screenshots | New (Feb 2026), 172 lines of Go | Complementary - for capturing evidence of test runs |
| **WebMCP** | W3C proposed standard (`navigator.modelContext`) for websites to expose tools to LLMs | Chrome 146 flag-gated preview | Future potential - requires app-side instrumentation |

### Recommendation

**Primary: Playwright MCP** for automated browser tests in CI.

Rationale:
- Uses accessibility tree snapshots (2-5KB structured data) instead of screenshots, making it
  token-efficient and deterministic
- Playwright is already installed in the project (`playwright==1.58.0`)
- Works with any MCP client including Claude, Cursor, and custom scripts
- Supports headless execution for CI, headed for development
- Microsoft-maintained, active community

**Complementary: Showboat + Rodney** for development-time verification.

Rationale:
- Agents building features can use Rodney to interact with the running dev server
- Showboat captures screenshots and results into reviewable Markdown documents
- Lightweight alternative when full Playwright MCP setup isn't needed
- Useful for the existing `/manual-test-plan` workflow - plans could be executed by Rodney
  instead of requiring Claude for Chrome

**Watch: WebMCP** for future app-side integration.

Rationale:
- Once WebMCP stabilises, Gyrinx could expose its own tools (e.g., "create a list", "add a
  fighter") directly to LLM agents, enabling richer testing without DOM interaction
- Requires Chrome 146+ and is still behind a feature flag
- Worth tracking but not ready for production use

## Architecture

### Layer 1: Test Fixtures & Server Management

Extend the existing pytest fixture system to manage a live Django dev server and browser
instance for integration tests.

```
conftest.py (integration)
├── live_server        # Django LiveServer on a random port (pytest-django built-in)
├── playwright_browser # Playwright browser instance (headed or headless)
├── page               # Fresh Playwright page per test
└── mcp_client         # Optional: MCP client connected to Playwright MCP server
```

**Key design decisions:**
- Use `pytest-django`'s built-in `live_server` fixture (already available)
- Use `pytest-playwright` for browser lifecycle management
- Integration tests are opt-in via a `pytest.mark.integration` marker
- CI runs them separately from the fast unit test suite

### Layer 2: Natural Language Test Specifications

Tests can be authored in two modes:

**Mode A: Conventional Playwright tests** (deterministic, fast)
```python
@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_create_list(live_server, page, user):
    """User can create a new list from the dashboard."""
    page.goto(f"{live_server.url}/")
    page.get_by_role("link", name="Login").click()
    page.get_by_label("Username").fill("testuser")
    page.get_by_label("Password").fill("password")
    page.get_by_role("button", name="Login").click()
    page.get_by_role("link", name="New List").click()
    page.get_by_label("Name").fill("Test Gang")
    page.get_by_role("button", name="Create").click()
    expect(page.get_by_text("Test Gang")).to_be_visible()
```

**Mode B: LLM-driven tests** (flexible, natural language)
```python
@pytest.mark.integration
@pytest.mark.llm_driven
@pytest.mark.django_db(transaction=True)
def test_equipment_assignment(live_server, llm_tester, user):
    """LLM navigates the UI to assign equipment to a fighter."""
    llm_tester.execute(
        base_url=live_server.url,
        credentials={"username": "testuser", "password": "password"},
        instructions="""
        1. Log in and navigate to an existing list
        2. Click on any fighter
        3. Add a weapon to the fighter
        4. Verify the fighter's cost increased
        5. Verify the weapon appears in the equipment list
        """,
        assertions=[
            "fighter cost should be higher than before adding equipment",
            "equipment list should contain the added weapon",
        ],
    )
```

Mode B works by:
1. Sending instructions to an LLM (Claude) via the API
2. The LLM plans and executes browser actions via Playwright MCP
3. The LLM evaluates assertions against the page state
4. Results are returned as structured pass/fail with evidence

### Layer 3: MCP Integration

For Mode B (LLM-driven) tests, the framework connects to Playwright MCP:

```
Test Runner (pytest)
    │
    ├── Starts Playwright MCP server (stdio transport)
    │
    ├── Connects MCP client
    │
    ├── Sends test instructions to Claude API
    │   └── Claude uses MCP tools to:
    │       ├── browser_navigate
    │       ├── browser_snapshot (accessibility tree)
    │       ├── browser_click
    │       ├── browser_type
    │       └── browser_take_screenshot (evidence)
    │
    └── Evaluates Claude's structured response against assertions
```

### Layer 4: Evidence Collection (Showboat-inspired)

Every integration test run produces an evidence document:

```
.claude/test-evidence/
└── 2026-02-13-14-30-integration-run/
    ├── summary.md          # Overall pass/fail with screenshots
    ├── test_create_list/
    │   ├── steps.md        # Step-by-step actions taken
    │   └── screenshots/    # PNG captures at key points
    └── test_equipment_assignment/
        ├── steps.md
        └── screenshots/
```

This is inspired by Showboat's approach of building reviewable Markdown artefacts, but
integrated directly into the test runner rather than requiring a separate CLI tool.

## Implementation Plan

### Phase 1: Conventional Playwright Integration Tests

**Goal:** Get browser tests running in pytest alongside existing tests.

1. Add `pytest-playwright` to requirements
2. Create `gyrinx/integration_tests/conftest.py` with browser fixtures
3. Add `pytest.mark.integration` marker configuration
4. Write 5-10 critical-path tests covering:
   - Login flow
   - List creation
   - Fighter creation and editing
   - Equipment assignment
   - Campaign mode basics
5. Add CI job for integration tests (separate from unit tests)
6. Configure Playwright browser installation in CI

**Files to create/modify:**
- `gyrinx/integration_tests/__init__.py`
- `gyrinx/integration_tests/conftest.py`
- `gyrinx/integration_tests/test_auth.py`
- `gyrinx/integration_tests/test_list_crud.py`
- `gyrinx/integration_tests/test_fighter_equipment.py`
- `pyproject.toml` (marker config, integration test paths)
- `requirements.txt` (pytest-playwright)
- `.github/workflows/integration-test.yaml`

### Phase 2: LLM-Driven Test Runner

**Goal:** Enable natural language test specifications executed by Claude via Playwright MCP.

1. Create `LLMTester` class that:
   - Manages Playwright MCP server lifecycle
   - Connects to Claude API for test execution
   - Translates natural language instructions into MCP tool calls
   - Evaluates assertions against page state
   - Collects evidence (screenshots, accessibility snapshots)
2. Create `llm_tester` pytest fixture
3. Add `pytest.mark.llm_driven` marker (skipped when no API key)
4. Write LLM-driven tests for complex, hard-to-script scenarios:
   - Multi-step campaign workflows
   - Equipment upgrade chains
   - Visual layout verification
   - Error handling and validation messages

**Files to create/modify:**
- `gyrinx/integration_tests/llm_tester.py`
- `gyrinx/integration_tests/test_llm_driven.py`
- `gyrinx/integration_tests/conftest.py` (add llm_tester fixture)

### Phase 3: Evidence Collection & Reporting

**Goal:** Produce reviewable artefacts from every integration test run.

1. Create evidence collector that captures:
   - Screenshots at assertion points
   - Accessibility snapshots
   - Network requests (for debugging)
   - Step-by-step action logs
2. Generate Markdown summary documents
3. Integrate with CI to upload evidence as build artefacts

### Phase 4: Development Workflow Integration (Rodney + Showboat)

**Goal:** Let Claude Code verify features during development.

1. Add Rodney as a development dependency
2. Create a `/verify-feature` slash command that:
   - Starts the dev server if not running
   - Uses Rodney to navigate the feature
   - Captures screenshots with Showboat
   - Produces a verification document
3. Extend `/manual-test-plan` to optionally auto-execute plans via Rodney

## Configuration

### pytest marker configuration (pyproject.toml)

```toml
[tool.pytest.ini_options]
markers = [
    "integration: Browser integration tests (require live server)",
    "llm_driven: LLM-driven tests (require ANTHROPIC_API_KEY)",
]

# Default: skip integration tests (run with pytest -m integration)
addopts = "--import-mode=importlib -p no:warnings --reuse-db -n auto --nomigrations -m 'not integration'"
```

### Environment variables

```bash
# Required for LLM-driven tests (Phase 2)
ANTHROPIC_API_KEY=sk-ant-...

# Optional: headed browser for development
PLAYWRIGHT_HEADED=1

# Optional: slow down actions for debugging
PLAYWRIGHT_SLOW_MO=500
```

### CI configuration

Integration tests run as a separate job, after unit tests pass:

```yaml
integration-tests:
  needs: [unit-tests]
  steps:
    - uses: actions/setup-python@v5
    - run: npx playwright install chromium
    - run: pytest -m integration --headed=false
    - uses: actions/upload-artifact@v4
      with:
        name: test-evidence
        path: .claude/test-evidence/
```

## Cost & Performance Considerations

### Conventional Playwright tests (Mode A)
- **Cost:** Free (no API calls)
- **Speed:** 2-5 seconds per test
- **Reliability:** High (deterministic)
- **When to use:** Critical paths, regression tests, CI gates

### LLM-driven tests (Mode B)
- **Cost:** ~$0.02-0.10 per test (depending on complexity and model)
- **Speed:** 10-30 seconds per test
- **Reliability:** Medium (LLM variability, retry logic needed)
- **When to use:** Complex workflows, exploratory testing, hard-to-script scenarios

### Recommendation
- Phase 1 (conventional) should be the CI gate
- Phase 2 (LLM-driven) should run on a schedule (nightly) or on-demand
- Keep LLM-driven tests focused on scenarios that are genuinely hard to script

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Playwright browser installation bloats CI | Medium | Install only Chromium, cache aggressively |
| LLM-driven tests are flaky | High | Retry logic, assertion tolerance, run nightly not on every PR |
| API costs for LLM-driven tests | Medium | Rate limit, run on schedule, use haiku for simple assertions |
| Integration tests slow down dev workflow | Medium | Separate marker, don't run by default |
| Playwright version drift | Low | Pin version, update with dependencies |

## Relationship to Existing Infrastructure

### Builds on
- **pytest** - Same test runner, same fixtures, same patterns
- **conftest.py fixtures** - Reuse `user`, `make_list`, `make_list_fighter` etc. for test data
- **`/manual-test-plan`** - Same test scenarios, now automatable
- **Playwright** - Already installed (`playwright==1.58.0`)

### Does not replace
- **Django test client tests** - These remain the fast, reliable backbone (1,952 tests)
- **Manual QA** - Still needed for visual/aesthetic review
- **Code review** - Integration tests complement, not replace, review

### New capabilities
- **Real browser verification** - JS execution, CSS rendering, responsive layout
- **LLM-authored tests** - Natural language test specifications
- **Visual evidence** - Screenshot-based test artefacts
- **End-to-end workflow testing** - Multi-page flows with real form submissions

## References

- [Playwright MCP](https://github.com/microsoft/playwright-mcp) - Microsoft's MCP server for browser automation
- [Chrome DevTools MCP](https://github.com/nicholasgriffintn/chrome-devtools-mcp) - Google's DevTools MCP server
- [Showboat and Rodney](https://simonwillison.net/2026/Feb/10/showboat-and-rodney/) - Simon Willison's agent demo tools
- [WebMCP specification](https://github.com/webmachinelearning/webmcp) - W3C proposed standard
- [WebMCP in Chrome 146](https://bug0.com/blog/webmcp-chrome-146-guide) - Implementation guide
- [Playwright MCP in 2026](https://bug0.com/blog/playwright-mcp-changes-ai-testing-2026) - Ecosystem analysis
