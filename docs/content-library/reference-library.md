# Reference Library

## Overview

The Reference Library tracks the published source material behind the game content in Gyrinx. Every fighter type, skill, scenario, and rule in Necromunda originates from a specific book and page number. The Reference Library stores these book and page reference entries so the application can cite them automatically when displaying content to users.

A list represents a user's collection of fighters (called a "gang" in Necromunda). When a user hovers over a fighter type, skill name, or rule on a list or fighter card, the application looks up matching page references and shows a tooltip with the book shortname and page number (for example, "Core p256"). This gives players a quick way to find the original rule text in their physical or digital rulebooks without cluttering the interface.

The Reference Library consists of two active models -- `ContentBook` for publications and `ContentPageRef` for individual page citations -- plus a deprecated `ContentPolicy` model that is no longer in use.

## Key Concepts

**Book** -- A published Necromunda rulebook, supplement, or expansion. Each book has a short identifier (like "Core" or "HoB") used in compact citations.

**Page Reference** -- A pointer to a specific topic within a book, identified by title, page number, and category. Page references can be nested: a parent reference (such as a chapter heading) can have child references (such as individual skills within that chapter) that inherit its page number.

**Category** -- A free-text label on a page reference that groups related entries. Common categories include "Skills", "Fighters", "Scenarios", and "Other". Categories are used to narrow down searches when the application looks up references by title.

**Obsolete Book** -- A book that has been superseded by a newer publication. Marking a book as obsolete does not remove its page references, but signals to administrators that its content may be outdated.

**Book Reference String** -- The compact citation format shown to users, combining a book's `shortname` and resolved page number. For example, a page reference in the Core Rulebook on page 256 produces the string "Core p256".

## Models

### `ContentBook`

Represents a published rulebook or supplement. Books are the top-level organisational unit for all page references.

| Field | Type | Description |
|-------|------|-------------|
| `name` | CharField (255) | Full name of the book (e.g. "Core Rulebook", "House of Blades") |
| `shortname` | CharField (50) | Abbreviated name used in citations (e.g. "Core", "HoB"). Can be blank |
| `year` | CharField | Year of publication. Stored as text to allow values like "2018" or ranges |
| `description` | TextField | Optional longer description of the book's contents |
| `type` | CharField (50) | Type of publication (e.g. "Rulebook", "Supplement"). Free text |
| `obsolete` | BooleanField | Whether this book has been superseded by a newer publication. Defaults to `False` |

The string representation of a book displays as `"{name} ({type}, {year})"`, for example "Core Rulebook (Rulebook, 2023)".

Books are ordered alphabetically by `name` in the admin.

**Admin interface:** The `ContentBook` admin includes a search over `title`, `shortname`, and `description`. Each book's detail page shows an inline table of its `ContentPageRef` entries, ordered by page number, so you can see all references for a book at a glance.

### `ContentPageRef`

Represents a reference to a specific topic within a book. This is the core model of the Reference Library -- it connects game content (by title) to a location in a published book (by page number).

| Field | Type | Description |
|-------|------|-------------|
| `book` | ForeignKey to `ContentBook` | The book this reference belongs to |
| `title` | CharField (255) | The name of the referenced content, used to match against other entities like skills, fighter types, and rules |
| `page` | CharField (50) | Page number within the book. Can be blank if the reference inherits its page from a parent |
| `parent` | ForeignKey to self (nullable) | Optional parent reference, used for hierarchical grouping |
| `category` | CharField (255) | Grouping label such as "Skills", "Fighters", or "Scenarios". Can be blank |
| `description` | TextField | Optional description of the referenced content |

The string representation combines all key fields: `"{book.shortname} - {category} - p{resolved_page} - {title}"`, for example "Core - Skills - p256 - Agility".

Default ordering is by `category`, then `book name`, then `title`.

#### Hierarchical Structure

Page references support a parent-child relationship through the `parent` field. This is useful when a section of a book covers multiple related items on the same page. For example:

- A parent reference titled "Agility Skills" might point to page 256 of the Core Rulebook.
- Child references for individual skills ("Catfall", "Dodge", "Sprint") can omit their `page` field and inherit page 256 from the parent.

This avoids duplicating page numbers across many entries and keeps maintenance simpler when page numbers change in a new printing.

#### Key Methods

**`resolve_page()`** -- Returns the page number for this reference. If the `page` field is set, it returns that value directly. If `page` is blank, it walks up the parent chain to find a page number. Returns `None` if no page can be resolved at any level.

**`bookref()`** -- Returns a compact human-readable citation string. Combines the book's `shortname` with the resolved page number, producing output like "Core p256" or "HoB p42". This is the format users see in tooltips.

**`children_ordered()`** -- Returns the child references of this page reference that have an explicit `page` value, ordered with Core Rulebook entries first, then alphabetically by book shortname, then numerically by page number, then by title.

**`children_no_page()`** -- Returns child references that do not have a page value (they inherit from this parent), ordered by book shortname and title.

**`find_similar(title, **kwargs)`** -- A class method that searches for page references whose titles contain the given string (case-insensitive). Accepts additional filter keyword arguments such as `category="Skills"`. Results are cached in a dedicated `content_page_ref_cache` to avoid repeated database lookups, since page references rarely change.

**`all_ordered()`** -- A class method that returns all top-level page references (those without a parent) that have an explicit page number. Results are ordered with Core Rulebook entries first, then by book shortname, then numerically by page number.

**`find()`** -- A class method that returns the first page reference matching the given filter arguments, or `None`.

**Admin interface:** The `ContentPageRef` admin includes search over `title`, `page`, and `description`. Each page reference's detail page shows an inline table of its child references, allowing you to manage the hierarchy from either direction -- from the book down, or from a parent reference down.

### `ContentPolicy` (Deprecated)

**Deprecated:** `ContentPolicy` is no longer in active use. Do not create new policy records. This model is retained for historical data only.

`ContentPolicy` was designed to capture rules for restricting or allowing certain equipment to specific fighters. It is not currently in use and is considered legacy code.

| Field | Type | Description |
|-------|------|-------------|
| `fighter` | ForeignKey to `ContentFighter` | The fighter this policy applies to |
| `rules` | JSONField | A JSON structure of allow/deny rules for equipment |

The `rules` field was intended to hold a list of rule objects with `allow` and `deny` keys, each containing equipment category and name filters. The `allows()` method evaluates these rules in reverse order to determine whether a piece of equipment is permitted for the fighter.

This model should be treated as read-only. Equipment availability is now managed through the Equipment List system described in other areas of the content library documentation.

## How It Works in the Application

### Tooltip Citations

The primary user-facing feature powered by the Reference Library is the `{% ref %}` template tag. When the application renders a fighter card, skill name, or rule, it wraps the text in a call to this tag. The tag works as follows:

1. It takes the displayed text (such as a skill name "Agility" or a fighter type "Charter Master") and searches for matching `ContentPageRef` entries using `find_similar()`.
2. If matches are found, it calls `bookref()` on each matching reference to build a citation string (e.g. "Core p256").
3. It wraps the original text in a `<span>` with a Bootstrap tooltip containing the citation string.
4. When the user hovers over the text, they see where to find the rule in their rulebook.

If multiple books contain a reference with the same title (for example, "Settlement Raid" appears in both the Core Rulebook and Book of the Outcast), the tooltip shows all matching citations separated by commas.

The tag caches its results so that repeated lookups for the same text within a page do not cause additional database queries.

### Where Tooltips Appear

- **Fighter type names** on fighter cards (e.g. hovering over "Prospector Digger" shows the book reference)
- **Skill names** in a fighter's skill list
- **Rule names** in a fighter's special rules section

Tooltips are only rendered in the interactive web view. When content is displayed in print mode, the raw text is shown without tooltip markup.

### Visual Styling

Referenced text is styled with an underline decoration (using the `tooltipped` CSS class) to indicate that hovering will reveal a citation. This gives users a subtle visual cue that source information is available without adding visual clutter.

## Common Admin Tasks

### Adding a New Book

1. Navigate to the Book list in the admin.
2. Click "Add Book".
3. Fill in the `name` (full title), `shortname` (abbreviated form for citations), `year`, and `type`.
4. Leave `obsolete` unchecked unless you are adding a historical reference that has been replaced.
5. Save the book. You can then add page references either through the inline on the book's detail page or through the Page Reference list.

When choosing a `shortname`, keep it short and distinctive. Existing conventions include "Core" for the Core Rulebook and abbreviations like "HoB" (House of Blades), "HoC" (House of Chains), and "Outcast" (Book of the Outcast). The shortname appears directly in user-facing tooltips.

### Adding Page References

**From a book's detail page:** Open the book in the admin. At the bottom you will see the "Page References" inline. Add rows with the `title`, `page` number, `category`, and optional `description`. This is the fastest way to add multiple references for the same book.

**From the Page Reference list:** Navigate to the Page Reference list, click "Add Page Reference", and fill in all fields including the `book` selection. This approach is useful when you need to set a `parent` reference, which is not available in the book inline.

### Creating Hierarchical References

To group several related references under a single parent:

1. Create the parent reference first, setting its `title` (e.g. "Agility Skills"), `book`, `page`, and `category`.
2. Save the parent.
3. Create child references for each individual item. Set their `title`, `book`, and `category`, but leave the `page` field blank. Select the parent reference in the `parent` dropdown.
4. The children will automatically inherit the page number from the parent when displayed.

You can also add children directly from a parent's detail page using the inline table.

### Marking a Book as Obsolete

Open the book in the admin and check the `obsolete` field. This flags the book for administrators but does not remove or hide its page references. You may want to review whether any page references from the obsolete book should be replaced with references to a newer publication.

### Finding and Updating References

The Page Reference admin supports search by `title`, `page`, and `description`. If you need to update page numbers after a new printing, search for the book's references, update the parent references first (since children inherit from them), and the child page numbers will update automatically.

### Understanding the Title Matching

The `title` field on a page reference is the key used for matching against content displayed in the application. When the `{% ref %}` template tag looks up "Agility", it searches for page references whose title contains "Agility" (case-insensitive). To ensure accurate matches:

- Use the exact name as it appears in the game content. For fighter types, use the full type name (e.g. "Ironhead Squat Prospectors Charter Master").
- Use the `category` field to disambiguate when the same title might appear in multiple contexts.
- Be aware that partial matches will also be returned. A reference titled "Spring" would match a search for "Sprint" through substring matching.
