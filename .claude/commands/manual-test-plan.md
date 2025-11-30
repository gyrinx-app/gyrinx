---
description: Generate a manual test plan for code changes, formatted for Claude for Chrome
---

# Manual Test Plan Generator

You are helping generate a manual test plan for recent code changes. The test plan will be executed by Claude for Chrome, which can:
- View and interact with web pages
- Click buttons, fill forms, check checkboxes
- Navigate between pages
- Verify visual content on screen

Claude for Chrome CANNOT:
- Run terminal commands or access local files
- Access the codebase directly
- Make purchases or access financial sites without confirmation

## Your Task

Analyze the recent code changes and generate a manual test plan that can be executed in a browser.

**First, check what has changed:**

!`git diff main --name-only | head -20`

!`git log main..HEAD --oneline | head -10`

## Instructions for Generating the Test Plan

Based on the changes above, create a test plan with these sections:

### 1. Prerequisites
- What pages/URLs need to be visited
- What test data needs to exist (e.g., "a list with fighters", "a campaign")
- Any setup steps the tester needs to do first

### 2. Test Cases
For each test case, provide:
- **Name**: Brief description
- **Steps**: Numbered list of exact UI actions (click, type, select, etc.)
- **Expected Result**: What should be visible on screen after the action

### 3. Format Requirements

Format the test plan so Claude for Chrome can execute it step-by-step:

- Use explicit UI element descriptions (e.g., "Click the 'Delete' button next to the equipment name")
- Include what to look for to verify success (e.g., "The credits value in the header should increase from X to Y")
- Note any checkboxes or form fields to interact with
- Specify page navigation clearly (e.g., "Navigate to the fighter's detail page by clicking on their name")

### 4. Context: This Application

This is Gyrinx, a list-building application for tabletop gaming. Key concepts:
- **Lists**: Collections of fighters and equipment
- **Fighters**: Characters with stats and equipment
- **Equipment**: Items assigned to fighters (weapons, wargear)
- **Campaign Mode**: Lists attached to campaigns track credits (currency)
- **List Building Mode**: Lists not attached to campaigns (no credits)
- **Rating**: Total cost of all fighters and equipment in a list
- **Stash**: Equipment held in reserve (separate from rating)
- **Refunds**: In campaign mode, removing items can optionally refund credits

### 5. Output Format

Structure your output as a numbered checklist that Claude for Chrome can follow:

```
## Test Plan: [Feature/Change Name]

### Setup
1. Navigate to [URL]
2. Ensure you have [prerequisites]

### Test 1: [Test Name]
**Purpose**: [What this tests]

Steps:
1. [Action to take]
2. [Action to take]
3. [Action to take]

**Verify**:
- [ ] [Expected visual result]
- [ ] [Expected visual result]

### Test 2: [Test Name]
...
```

Now analyze the changes shown above and generate the test plan.
