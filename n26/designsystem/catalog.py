"""The gallery's table of contents.

Deliberately thin: this file says what exists, how it is grouped and what it is
*for*. It does not restate any component's props — those are read from the
installed package at runtime (see :mod:`designsystem.introspect`), so they cannot
fall out of date with the version you have installed.

Every public component in django-cotton-ui appears here. The internal ``impl.html``
templates do not: they have no public tag, and their props are documented on the
wrapper that forwards to them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace

from django.utils.text import slugify

from . import introspect
from .demos import Demo, demos_for


@dataclass(frozen=True)
class Part:
    """A subcomponent: its own tag, documented on its parent's page."""

    tag: str
    template: str
    summary: str
    required: bool = False
    """True when the parent does not work without it."""


@dataclass(frozen=True)
class Component:
    slug: str
    tag: str
    template: str
    summary: str
    group: str = ""
    notes: str = ""
    """Gotchas worth knowing that aren't obvious from the prop list."""

    needs: tuple[str, ...] = ()
    """Runtime requirements beyond the base CSS — Alpine plugins, kit JS factories."""

    parts: tuple[Part, ...] = ()

    @property
    def api(self) -> introspect.ComponentApi | None:
        return introspect.api_for(self.template)

    @property
    def part_apis(self) -> list[tuple[Part, introspect.ComponentApi | None]]:
        return [(part, introspect.api_for(part.template)) for part in self.parts]

    @property
    def demos(self) -> tuple[Demo, ...]:
        return demos_for(self.slug)

    @property
    def search_term(self) -> str:
        """What the sidebar filter matches against."""
        return f"{self.slug} {self.tag} {self.group}".lower()


@dataclass(frozen=True)
class Group:
    name: str
    blurb: str
    components: list[Component] = field(default_factory=list)

    @property
    def anchor(self) -> str:
        return slugify(self.name)

    @property
    def search_terms(self) -> str:
        """Its components' search terms as a JSON array.

        The sidebar hides a whole group when the filter excludes every component
        in it. Handing the group its members' terms lets that be one predicate
        over data, rather than the group inspecting the DOM to see how many
        children are still visible — which couples it to how the children happen
        to be hidden.
        """
        return json.dumps([component.search_term for component in self.components])


ALPINE = "Alpine.js"
KIT_JS = "cotton-ui.js"
COLLAPSE = "@alpinejs/collapse"
FOCUS = "@alpinejs/focus"


GROUPS: list[Group] = [
    Group(
        "Actions",
        "Things you click.",
        [
            Component(
                slug="button",
                tag="c-ui.button",
                template="button.html",
                summary="The standard action control, in seven variants and six sizes.",
                notes=(
                    "Renders an <a> when href is set, otherwise a <button>. There is "
                    "no disabled prop — pass disabled as a plain attribute; the styles "
                    'for it already exist. type="button" is hardcoded, but because {{ '
                    'attrs }} is emitted first, your own type="submit" still wins. '
                    "The seventh variant, success, is this repository's: three of the "
                    "fills carry a meaning rather than a mood — success makes "
                    "something, danger destroys something, primary does neither — so "
                    "the button that creates a gang or hires a fighter is always the "
                    "green one and can be found without reading it. Added through a "
                    "local override of the kit's template, which is also why the "
                    "shadow rule in app.css lists .bg-green-700 alongside the other "
                    "solid fills."
                ),
            ),
            Component(
                slug="dropdown",
                tag="c-ui.dropdown",
                template="dropdown/index.html",
                summary=(
                    "A menu of actions hung off a trigger, with optional keyboard "
                    "shortcuts."
                ),
                needs=(ALPINE, KIT_JS, FOCUS),
                notes=(
                    "Needs either a trigger slot or trigger_text — with neither it "
                    "renders a visible red error rather than failing silently. Set "
                    ":collapsible to have it render inline below the md breakpoint "
                    "instead of as a popover."
                ),
                parts=(
                    Part(
                        "c-ui.dropdown.item",
                        "dropdown/item.html",
                        "One action. Renders <a> with href, else <button>.",
                    ),
                    Part(
                        "c-ui.dropdown.group",
                        "dropdown/group.html",
                        "A labelled cluster of items.",
                    ),
                    Part(
                        "c-ui.dropdown.separator",
                        "dropdown/separator.html",
                        "A divider rule.",
                    ),
                ),
            ),
            Component(
                slug="composer",
                tag="c-ui.composer",
                template="composer.html",
                summary="A chat-style box: auto-growing textarea with action rows.",
                needs=(ALPINE,),
                notes=(
                    "No default slot — the initial text is the value prop. The leading "
                    "and trailing slots form the action row, which only renders if you "
                    "fill at least one. The textarea grows to 320px, then scrolls."
                ),
            ),
        ],
    ),
    Group(
        "Forms",
        (
            "Every field wrapper takes the same label / description / "
            "description_trailing / error / badge / form / name props and passes "
            "everything else through to the control underneath, so type, size, "
            "placeholder and disabled all work on the outer tag."
        ),
        [
            Component(
                slug="field",
                tag="c-ui.field",
                template="field.html",
                summary=(
                    "The label-and-description scaffold every other form component is "
                    "built on."
                ),
                notes=(
                    "Reach for this directly when wrapping a control the kit does not "
                    "ship. Errors only render when error, form and name are all set — "
                    "it delegates to c-ui.error with the form and name, so the error "
                    "string's own content is ignored."
                ),
            ),
            Component(
                slug="input",
                tag="c-ui.input",
                template="input/index.html",
                summary="A text input, with optional leading and trailing addons.",
                notes=(
                    "Addons are positioned absolutely and pointer-events-none, so they "
                    "are for decoration — icons, units, currency symbols — not buttons."
                ),
            ),
            Component(
                slug="textarea",
                tag="c-ui.textarea",
                template="textarea/index.html",
                summary="A multi-line input, fixed height or auto-growing.",
                notes=(
                    "size sets padding and font; height sets the fixed height (h-16 to "
                    "h-80) and is a separate scale. :autoresize makes height a floor "
                    "and needs Alpine."
                ),
            ),
            Component(
                slug="select",
                tag="c-ui.select",
                template="select/index.html",
                summary="A list of options — the real <select>, or a styled listbox.",
                needs=(ALPINE, KIT_JS),
                notes=(
                    'variant="native" (the default) needs no JS and gets the platform '
                    'picker. variant="listbox" routes to c-ui.menu, and its slot must '
                    "then contain c-ui.menu.item — not c-ui.select.option."
                ),
                parts=(
                    Part(
                        "c-ui.select.native",
                        "select/native.html",
                        "The plain <select>, usable on its own.",
                    ),
                    Part(
                        "c-ui.select.option",
                        "select/option.html",
                        "An option for the native variant.",
                    ),
                ),
            ),
            Component(
                slug="menu",
                tag="c-ui.menu",
                template="menu/index.html",
                summary=(
                    "A searchable listbox with descriptions, groups and keyboard "
                    "navigation."
                ),
                needs=(ALPINE, KIT_JS),
                notes=(
                    'The engine behind select variant="listbox", and worth using '
                    "directly when you want search or option descriptions. The trigger "
                    "and content wrappers render themselves if you omit those slots, "
                    "so usually you write only items. Submits through a hidden input "
                    "and dispatches select-change with {value, label}."
                ),
                parts=(
                    Part(
                        "c-ui.menu.item",
                        "menu/item.html",
                        "One option: value, label, description, group.",
                        required=True,
                    ),
                    Part(
                        "c-ui.menu.trigger",
                        "menu/trigger.html",
                        "The closed-state button. Auto-rendered if omitted.",
                    ),
                    Part(
                        "c-ui.menu.content",
                        "menu/content.html",
                        "The popover panel. Auto-rendered if omitted.",
                    ),
                    Part(
                        "c-ui.menu.group",
                        "menu/group.html",
                        "A labelled cluster of options.",
                    ),
                    Part(
                        "c-ui.menu.search",
                        "menu/search.html",
                        "A sticky filter box, focused on open.",
                    ),
                ),
            ),
            Component(
                slug="combobox",
                tag="c-ui.combobox",
                template="combobox/index.html",
                summary=(
                    "Multi-select as removable tags, optionally searchable and free- "
                    "text."
                ),
                needs=(ALPINE, KIT_JS),
                notes=(
                    "Options come from the :options prop, not from a slot. :writable "
                    "lets people invent values that weren't in the list. Submits via a "
                    "hidden <select multiple>."
                ),
            ),
            Component(
                slug="checkbox",
                tag="c-ui.checkbox.group",
                template="checkbox/group/index.html",
                summary=(
                    "Multi-choice, as plain rows, a segmented control or selectable "
                    "cards."
                ),
                needs=(ALPINE, KIT_JS),
                notes=(
                    "c-ui.checkbox only works inside a group — it reads its state and "
                    "its styling from the group's Alpine scope. Initially-checked "
                    "boxes are set on the group with :values, not on the box with "
                    ":checked."
                ),
                parts=(
                    Part(
                        "c-ui.checkbox",
                        "checkbox/index.html",
                        "One box. Must be inside the group.",
                        required=True,
                    ),
                ),
            ),
            Component(
                slug="radio",
                tag="c-ui.radio.group",
                template="radio/group/index.html",
                summary="Single-choice, as rows, a segmented control, pills or cards.",
                needs=(ALPINE, KIT_JS),
                notes=(
                    "Same rule as checkbox: c-ui.radio must be inside the group. The "
                    "selected value is set on the group with :value. Arrow keys move "
                    "between options. Unlike the checkbox group, this one also offers "
                    "a pill variant."
                ),
                parts=(
                    Part(
                        "c-ui.radio",
                        "radio/index.html",
                        "One radio. Must be inside the group.",
                        required=True,
                    ),
                ),
            ),
            Component(
                slug="switch",
                tag="c-ui.switch",
                template="switch/index.html",
                summary="An on/off toggle, standalone or as a label-left settings row.",
                needs=(ALPINE, KIT_JS),
                notes=(
                    ":inline uses the field's toggle variant — label left, switch "
                    "pushed right."
                ),
            ),
            Component(
                slug="range",
                tag="c-ui.range",
                template="range/index.html",
                summary="A slider, with the live value beside or below the track.",
                needs=(ALPINE,),
                notes=(
                    "The starting position is value, which the wrapper forwards as the "
                    "impl's initial."
                ),
            ),
            Component(
                slug="datepicker",
                tag="c-ui.datepicker",
                template="datepicker/index.html",
                summary=(
                    "A date field that opens a calendar — single date, range or "
                    "multiple."
                ),
                needs=(ALPINE, KIT_JS),
                notes=(
                    "Wraps c-ui.calendar in a popover. In range mode it submits "
                    "name['from'] and name['to'] unless you give fromName and toName."
                ),
            ),
            Component(
                slug="calendar",
                tag="c-ui.calendar",
                template="calendar.html",
                summary="The month grid on its own, with day, month and year views.",
                needs=(ALPINE, KIT_JS),
                notes=(
                    "Usable inline, not just inside the datepicker. Hidden inputs — "
                    "and so form submission — appear only once you pass name (or "
                    "fromName/toName). x-modelable means x-model works on it."
                ),
            ),
            Component(
                slug="label",
                tag="c-ui.label",
                template="label.html",
                summary="A form label, with an optional badge alongside it.",
            ),
            Component(
                slug="description",
                tag="c-ui.description",
                template="description.html",
                summary="Muted helper text under a control.",
                notes=(
                    "No props of its own; everything passes through and class merges "
                    "with the defaults."
                ),
            ),
            Component(
                slug="error",
                tag="c-ui.error",
                template="error.html",
                summary=(
                    "A validation message, from a string or straight off a Django form."
                ),
                notes=(
                    "Resolves in order: message, then form errors for name, then the "
                    'slot. name="__all__" renders non-field errors. Renders nothing '
                    "when they are all empty, so it is safe to leave in place "
                    "unconditionally."
                ),
            ),
        ],
    ),
    Group(
        "Data display",
        "Presenting content.",
        [
            Component(
                slug="card",
                tag="c-ui.card",
                template="card.html",
                summary="A surface with an optional header band.",
                notes=(
                    "Setting any of title, subheading or the header slot switches it "
                    'to the two-part layout with a divider. padding="none" for flush '
                    "content like a table."
                ),
            ),
            Component(
                slug="table",
                tag="c-ui.table",
                template="table.html",
                summary="Styling for a plain HTML table, plus horizontal overflow.",
                notes=(
                    "You write ordinary thead/tbody/tr/th/td; it styles descendants. "
                    "No JS, no sorting, no pagination — compose it with "
                    "c-ui.pagination."
                ),
            ),
            Component(
                slug="badge",
                tag="c-ui.badge",
                template="badge.html",
                summary="A small status or count pill in nineteen colours.",
                notes=(
                    "pill and solid are both spellings of variant, so they cannot be "
                    'combined. inset takes edge names (inset="top bottom") to pull it '
                    "tight against surrounding text."
                ),
            ),
            Component(
                slug="avatar",
                tag="c-ui.avatar",
                template="avatar/index.html",
                summary="A user image, initials, or a fallback silhouette.",
                needs=(ALPINE,),
                notes=(
                    'Falls back src → initials → silhouette. color="auto" hashes the '
                    "initials to a stable colour. The default slot renders outside the "
                    "clipped circle, which is where a status dot goes."
                ),
                parts=(
                    Part(
                        "c-ui.avatar.group",
                        "avatar/group.html",
                        "Overlaps a row of avatars with rings.",
                    ),
                ),
            ),
            Component(
                slug="progress",
                tag="c-ui.progress",
                template="progress.html",
                summary="A determinate progress bar.",
                notes=(
                    "No JS. bar_class overrides the colour entirely if the palette "
                    "doesn't have what you want."
                ),
            ),
            Component(
                slug="spinner",
                tag="c-ui.spinner",
                template="spinner.html",
                summary="An indeterminate loading spinner.",
                notes=(
                    'color="current" inherits the surrounding text colour, which is '
                    "what you want inside a button."
                ),
            ),
        ],
    ),
    Group(
        "Feedback",
        "Telling people what happened.",
        [
            Component(
                slug="alert",
                tag="c-ui.alert",
                template="alert.html",
                summary="An inline message box in four tones and three appearances.",
                needs=(ALPINE,),
                notes=(
                    "Alpine is only needed for :dismissible; a static alert is pure "
                    "markup."
                ),
            ),
            Component(
                slug="toast",
                tag="c-ui.toast.container",
                template="toast/container.html",
                summary="Transient notifications, fired from anywhere by event.",
                needs=(ALPINE,),
                notes=(
                    "There is no c-ui.toast — only the container, which you drop once "
                    "in your base layout. It registers the $store.toasts Alpine store "
                    "and renders a stack in every corner. Raise one with "
                    "$dispatch('toast', {variant, title, message}); anything you pass "
                    'overrides the container\'s props for that toast. duration="0" '
                    "makes it sticky."
                ),
            ),
            Component(
                slug="tooltip",
                tag="c-ui.tooltip",
                template="tooltip.html",
                summary="A small label on hover or focus.",
                needs=(ALPINE,),
                notes=(
                    "The default slot is the trigger; the content slot is the bubble. "
                    "Teleports to <body> and positions in document coordinates, so it "
                    "escapes overflow clipping. Auto-flips when it won't fit."
                ),
            ),
        ],
    ),
    Group(
        "Navigation",
        "Getting around.",
        [
            Component(
                slug="navbar",
                tag="c-ui.navbar",
                template="navbar/index.html",
                summary=(
                    "A responsive top bar with a brand, links, actions and a mobile "
                    "menu."
                ),
                needs=(ALPINE, COLLAPSE),
                notes=(
                    "The default slot and actions are duplicated into the mobile menu, "
                    "so write them once. :drawer makes the mobile menu a slide-over "
                    "rather than an inline collapse, and then it also needs the focus "
                    "plugin."
                ),
                parts=(
                    Part(
                        "c-ui.navbar.item",
                        "navbar/item.html",
                        "A link. Styled by the navbar's variant.",
                        required=True,
                    ),
                ),
            ),
            Component(
                slug="nav",
                tag="c-ui.nav",
                template="nav/index.html",
                summary="A horizontal row of underline tabs, for page navigation.",
                notes=(
                    "Navigation, not state: these are real links. For in-page panels "
                    "use c-ui.tabs. Items are structural — the parent styles them via "
                    "descendant selectors."
                ),
                parts=(
                    Part(
                        "c-ui.nav.item",
                        "nav/item.html",
                        "A link, with :current and an optional badge.",
                        required=True,
                    ),
                ),
            ),
            Component(
                slug="navlist",
                tag="c-ui.navlist",
                template="navlist/index.html",
                summary="A vertical sidebar nav, with collapsible grouped sections.",
                needs=(ALPINE, COLLAPSE),
                notes=(
                    ":persist_scroll remembers the scroll position across navigations, "
                    "but only works if the navlist is its own scroll container — give "
                    "it a max height and overflow-y-auto."
                ),
                parts=(
                    Part(
                        "c-ui.navlist.item",
                        "navlist/item.html",
                        "A link, with :current and an optional badge.",
                        required=True,
                    ),
                    Part(
                        "c-ui.navlist.group",
                        "navlist/group.html",
                        "A headed, optionally collapsible section.",
                    ),
                ),
            ),
            Component(
                slug="breadcrumbs",
                tag="c-ui.breadcrumbs",
                template="breadcrumbs/index.html",
                summary="A trail back up the hierarchy.",
                notes=(
                    "With no separator slot the “/” is pure CSS and needs no JS; "
                    "supply one and Alpine clones it between items."
                ),
                parts=(
                    Part(
                        "c-ui.breadcrumbs.item",
                        "breadcrumbs/item.html",
                        "One crumb. Renders <a> unless :current.",
                        required=True,
                    ),
                ),
            ),
            Component(
                slug="pagination",
                tag="c-ui.pagination",
                template="pagination/index.html",
                summary="Page links — automatic from a Django Page, or hand-composed.",
                notes=(
                    "Pass :page_obj and it renders prev, elided numbers and next by "
                    "itself. The slot is only used when page_obj is None, which is the "
                    "escape hatch for cursor pagination and other non-Page sources."
                ),
                parts=(
                    Part(
                        "c-ui.pagination.item",
                        "pagination/item.html",
                        "A numbered page link.",
                    ),
                    Part(
                        "c-ui.pagination.prev",
                        "pagination/prev.html",
                        "Previous-page chevron.",
                    ),
                    Part(
                        "c-ui.pagination.next",
                        "pagination/next.html",
                        "Next-page chevron.",
                    ),
                    Part(
                        "c-ui.pagination.ellipsis",
                        "pagination/ellipsis.html",
                        "The gap marker.",
                    ),
                ),
            ),
            Component(
                slug="scrollspy",
                tag="c-ui.scrollspy",
                template="scrollspy.html",
                summary="Highlights the nav item for whichever section is on screen.",
                needs=(ALPINE,),
                notes=(
                    "Wrap the nav, not the content. It tracks the ids in the nav's own "
                    'a[href^="#"] plus anything marked [data-spy-section]. Pair with '
                    "spy= on nav or navlist items. This page's own sidebar uses it."
                ),
            ),
        ],
    ),
    Group(
        "Disclosure",
        "Showing and hiding.",
        [
            Component(
                slug="tabs",
                tag="c-ui.tabs",
                template="tabs/index.html",
                summary="In-page panels with a generated tab bar.",
                needs=(ALPINE, KIT_JS),
                notes=(
                    "You write only the panels — the buttons are generated from the "
                    "panels that register themselves, using each one's name as its "
                    "label. The first panel wins unless you set :default_tab."
                ),
                parts=(
                    Part(
                        "c-ui.tabs.tab",
                        "tabs/tab.html",
                        "One panel. name is both its id and its button label.",
                        required=True,
                    ),
                ),
            ),
            Component(
                slug="accordion",
                tag="c-ui.accordion",
                template="accordion/index.html",
                summary="Stacked expandable rows, one at a time or many.",
                needs=(ALPINE, KIT_JS),
                notes=(
                    'type="single" allows one open row; any other value allows '
                    "several. Rows are flush by design — padding belongs on the item, "
                    "so you can compose insets."
                ),
                parts=(
                    Part(
                        "c-ui.accordion.item",
                        "accordion/item.html",
                        "One row. Must be inside the accordion.",
                        required=True,
                    ),
                ),
            ),
            Component(
                slug="collapse",
                tag="c-ui.collapse",
                template="collapse.html",
                summary="A single show/hide toggle with an animated body.",
                needs=(ALPINE, COLLAPSE),
                notes=(
                    "For one disclosure. Use the accordion when you have a set of them."
                ),
            ),
        ],
    ),
    Group(
        "Overlays",
        "Layered on top.",
        [
            Component(
                slug="dialog",
                tag="c-ui.dialog",
                template="dialog/index.html",
                summary="A centred modal with header, body and footer slots.",
                needs=(ALPINE, KIT_JS),
                notes=(
                    "Teleports the overlay to <body>. Note the spelling: :dismissable "
                    "here, but :dismissible on the drawer. A close button always "
                    "renders."
                ),
                parts=(
                    Part(
                        "c-ui.dialog.title",
                        "dialog/title.html",
                        "The accessible title. Must be inside the dialog.",
                    ),
                    Part(
                        "c-ui.dialog.description",
                        "dialog/description.html",
                        "The accessible description.",
                    ),
                ),
            ),
            Component(
                slug="drawer",
                tag="c-ui.drawer",
                template="drawer.html",
                summary="A panel that slides in from any edge.",
                needs=(ALPINE, FOCUS),
                notes=(
                    "The default slot is the trigger and the content slot is the body "
                    "— the root is display:contents, so the trigger sits in your "
                    "layout as though the drawer weren't there. Open it with "
                    '@click="drawerOpen = true".'
                ),
            ),
            Component(
                slug="popover",
                tag="c-ui.popover",
                template="popover.html",
                summary="A floating panel on click or hover, holding any content.",
                needs=(ALPINE, KIT_JS),
                notes=(
                    'open_on="hover" honours open_delay and close_delay so it does not '
                    "flicker on a quick pass. Unlike tooltip, it can hold interactive "
                    "content. Note that class styles the panel, not the root."
                ),
            ),
        ],
    ),
    Group(
        "Theming",
        "Controls for the theme itself. Both are wired up on this site — see Theming.",
        [
            Component(
                slug="mode-toggle",
                tag="c-ui.mode-toggle",
                template="mode_toggle/index.html",
                summary="Light / dark / system switching, in four presentations.",
                needs=(ALPINE,),
                notes=(
                    "Pair it with c-ui.mode-toggle.head in <head>, with matching "
                    "props, or the page flashes the wrong theme before Alpine boots. "
                    'Syncs across tabs. variant="headless" hands you the scope so you '
                    "can build your own control."
                ),
                parts=(
                    Part(
                        "c-ui.mode-toggle.head",
                        "mode_toggle/head.html",
                        "Blocking script for <head>. Prevents the flash.",
                        required=True,
                    ),
                ),
            ),
            Component(
                slug="theme-builder-widget",
                tag="c-ui.theme-builder-widget",
                template="theme_builder_widget.html",
                summary=(
                    "A floating devtool for editing theme tokens live, with CSS export."
                ),
                needs=(ALPINE, KIT_JS),
                notes=(
                    "A development tool rather than a UI primitive: drop it once, and "
                    "it edits the tokens on <html> so the page you are already looking "
                    "at is the preview. It is mounted on every page of this gallery — "
                    "the paintbrush, bottom right. Copy the CSS it generates into your "
                    "own stylesheet to keep a theme."
                ),
            ),
        ],
    ),
    Group(
        "Compositions",
        (
            "This project's own components, in templates/cotton/n26/ rather than the "
            "kit. Most are assembled from the primitives above and add no "
            "JavaScript of their own — where they need behaviour, they drive the "
            "Alpine scope a kit component already provides. The exception is icon, "
            "which is a primitive: the kit ships none, so we keep our own."
        ),
        [
            Component(
                slug="icon",
                tag="c-n26.icon",
                template="n26/icon.html",
                summary="The whole icon set, from one named registry.",
                notes=(
                    "django-cotton-ui ships no icons at all, so until this existed "
                    "every SVG was pasted inline where it was wanted — one chevron in "
                    "five templates, one pencil in four, and nothing anywhere that "
                    "listed what the project already had. The drawings are Heroicons "
                    "v2 outline, on a 24x24 canvas with round caps and no fill, which "
                    "is uniform enough that the registry in core/icons.py can be path "
                    "data alone and this component supplies everything else. The brand "
                    "marks are what that uniformity costs: a logo is a filled shape "
                    "rather than a line drawing, and one of them is published on a "
                    "1080 canvas, so the registry names which are solid and which keep "
                    "a canvas of their own — rescaling a mark's numbers by hand would "
                    "be redrawing it. Four are "
                    "our own redrawings, kept as they are because naming a set should "
                    "not silently redraw it; the gallery marks them. Colour is never a "
                    "prop — currentColor means an icon is the colour of its text — and "
                    "stroke weight is, because weight is a function of rendered size "
                    "rather than of the drawing."
                ),
            ),
            Component(
                slug="search-bar",
                tag="c-n26.search-bar",
                template="n26/search_bar.html",
                summary="A search field, with its submit button beside it.",
                notes=(
                    "The field and its icon are one joined control, which the kit has "
                    "no input group for: the wrapper owns the border, radius and focus "
                    "ring, and the field is a plain <input> carrying the kit's own "
                    "token classes, because c-ui.input would put a second border "
                    "inside this one. The submit is deliberately *not* in that group — "
                    "joined and filled it fought the group's border, joined and "
                    "outlined it drew a second box inside it, both symptoms of a "
                    "primary action not wanting to be a segment of the control it acts "
                    "on. It is a real form, so it submits without JavaScript."
                ),
            ),
            Component(
                slug="filter-menu",
                tag="c-n26.filter-menu",
                template="n26/filter_menu.html",
                summary=(
                    "Multi-select filtering in a dropdown: All / None, "
                    "per-row only, apply or cancel."
                ),
                needs=(ALPINE, KIT_JS, FOCUS),
                notes=(
                    "No new state. The checkbox group keeps its selection in a plain, "
                    "assignable values array and the dropdown exposes close(), both "
                    "above this content in the scope chain — so All, None and only are "
                    "one assignment each. The group wraps the whole dropdown rather "
                    "than sitting in its panel, which is what lets the trigger show a "
                    "count while the panel is shut. Cancel reverts to a snapshot taken "
                    "when the panel opened."
                ),
            ),
            Component(
                slug="range-menu",
                tag="c-n26.range-menu",
                template="n26/range_menu.html",
                summary=(
                    "A bound on a number, as a slider in a dropdown. One thumb or two."
                ),
                needs=(ALPINE, KIT_JS),
                notes=(
                    "The numeric member of the menu family, after filter-menu (many "
                    "of a set) and choice-menu (one of a set). A slider is the wrong "
                    "shape for a toolbar — it wants width — and the right shape for "
                    "'how much', because the useful gesture is drag-until-the-list-"
                    "looks-right rather than typing a number; a dropdown gives it "
                    "width when open and leaves a button behind when shut. The "
                    "trigger states the bound rather than the label, so a bar can be "
                    "read without opening anything, and swaps in a word at either end "
                    "for the cases where the number does not say what it means. Pass "
                    "model_min and model_max instead of model and it becomes a "
                    "two-thumb range. No OK or Cancel, unlike filter-menu: you are "
                    "watching the list respond as you drag, and confirming something "
                    "you have already seen happen is a step for nothing. The slider "
                    "underneath is c-n26.range-slider, not c-ui.range: the kit's "
                    "binds with x-modelable, which carries a drag out to the caller "
                    "but will not carry a programmatic change back in — so Clear "
                    "moved the model and left the filled track behind."
                ),
                parts=(
                    Part(
                        "c-n26.range-slider",
                        "n26/range_slider.html",
                        "The slider itself, one thumb or two. Ours rather than "
                        "c-ui.range, which cannot be moved from outside.",
                    ),
                ),
            ),
            Component(
                slug="tab-links",
                tag="c-n26.tab-links",
                template="n26/tab_links.html",
                summary="A tab strip whose tabs are links, for a choice the server answers.",
                notes=(
                    "The other kind of tab. c-ui.tabs switches panels already on the "
                    "page; these navigate, because what is behind one is a whole "
                    "render — which makes the choice a URL, so it is linkable, in the "
                    "history and available to a browser that has run no JavaScript. "
                    "That is also why a tab carries no count: only the current one has "
                    "been fetched, and numbering the rest would cost a query per tab "
                    "on a strip whose whole job is to offer more of them. Drawn as a "
                    "nav with aria-current rather than role=tablist, which promises "
                    "arrow keys and a panel that swaps underneath. It wraps rather "
                    "than scrolling sideways, because names come from content and a "
                    "horizontal scroller hides tabs past the edge of a phone behind a "
                    "gesture nobody is told about."
                ),
            ),
            Component(
                slug="deferred",
                tag="c-n26.deferred",
                template="n26/deferred.html",
                summary=(
                    "A fragment fetched when first needed, instead of shipped "
                    "with the page."
                ),
                needs=(ALPINE,),
                notes=(
                    "For the heavy tail of a page: detail behind a disclosure "
                    "that most readers never open. A hire list prices hundreds "
                    "of options, and shipping every option's drawn card makes "
                    "the document megabytes and the render minutes — where a "
                    "card fetched on the first open costs one small request, "
                    "for exactly the rows somebody reads. The fetch happens on "
                    "this component's own init, so the call site chooses the "
                    "moment by placement: inside a template x-if it fetches "
                    "when the template first instantiates. The alternative — "
                    "an IntersectionObserver watching for visibility — answers "
                    "a different question (near the viewport, not asked for) "
                    "and fires for everything as a reader scrolls a long list. "
                    "Given follows, the address becomes a question the page "
                    "keeps answering: a hire row rebuilds it from the options "
                    "ticked on it and the fragment is fetched again, with the "
                    "card already drawn staying up until the new one lands. "
                    "That is how a surface follows a choice with too many "
                    "combinations to ship — the address says which one, and "
                    "the server draws the one that was asked for."
                ),
            ),
            Component(
                slug="collection-picker",
                tag="c-n26.collection-picker",
                template="n26/collection_picker/index.html",
                summary=(
                    "A long categorised list, filtered from a sticky bar and acted "
                    "on inline. Built for a phone."
                ),
                needs=(ALPINE, KIT_JS, COLLAPSE),
                notes=(
                    "The filter bar sticks, because a filter you have to scroll back "
                    "up to reach is one you use once — and everything a reader steers "
                    "with sticks in the same box: the filters slot, the readout and "
                    "the section strip. One box rather than several, because each "
                    "sticky band after the first would have to be told how tall the "
                    "ones above it are, and a wrong number either overlaps a band or "
                    "leaves a stripe of scrolling list wedged between two. Stacked "
                    "inside one box they just follow each other and the page sets a "
                    "single offset. The section strip comes in two shapes and the "
                    "width picks one: from sm up every section is a tab, below it "
                    "the section on screen stands alone with the rest behind a "
                    "chevron. A breakpoint rather than a measurement — how many "
                    "names fit is a fact about these names at this width, but not "
                    "one worth a ResizeObserver and a ghost copy of the strip. They "
                    "are two blocks of markup rather than one that adapts, because "
                    "what they do differs: a full strip must not move when a tab is "
                    "clicked, and a strip of one is the current section followed by "
                    "the way to the others. One block serving both pulled the active "
                    "tab to the front, which is the second shape's rule imposed on "
                    "the first, where it reorders the whole row on every click. "
                    "Categories collapse, because "
                    "thirty rows is a lot of thumb; and every control applies on "
                    "touch, so the loop is filter, look, adjust rather than filter, "
                    "wait, go back. Items register their own facets on init, so the "
                    "counts, the readout and each group's visibility are one array "
                    "read three ways and no total can fall out of date — and the "
                    "readout counts what the tab strip is showing rather than "
                    "everything registered, because a total spanning the sections a "
                    "tab is hiding is a number that contradicts the list under it. "
                    "An empty "
                    "category hides itself rather than leaving a header behind, and a "
                    "search forces every group open without overwriting what the "
                    "reader had chosen. The controls are not built in: they go in a "
                    "slot and write to this component's state by name, which is why "
                    "the same shell serves a trading post and anything else long "
                    "enough to need one."
                ),
                parts=(
                    Part(
                        "c-n26.collection-picker.section",
                        "n26/collection_picker/section.html",
                        "One collapsible tier, hiding itself when nothing under "
                        "it matches.",
                        required=True,
                    ),
                    Part(
                        "c-n26.collection-picker.category",
                        "n26/collection_picker/category.html",
                        "The fine tier inside a section: a heading and its rows. "
                        "Not collapsible — the section above it already is.",
                    ),
                    Part(
                        "c-n26.collection-picker.item",
                        "n26/collection_picker/item.html",
                        "One row: name, cost, rarity and its buttons. One line at "
                        "every width.",
                        required=True,
                    ),
                ),
            ),
            Component(
                slug="profile-picker",
                tag="c-n26.profile-picker",
                template="n26/profile_picker/index.html",
                summary=(
                    "The models a gang could buy: in sections, filtered, and "
                    "hireable without opening a row."
                ),
                needs=(ALPINE, KIT_JS, COLLAPSE, FOCUS),
                notes=(
                    "The same screen as the trading post, because it is the same "
                    "kind of screen — Profile is an Assignable, so a gang list is "
                    "a collection like any other, and this is "
                    "c-n26.collection-picker with hiring's vocabulary on it. "
                    "Which keeps it thin: it sets the noun, drops the filters "
                    "that mean nothing here (nothing you hire has a trade-points "
                    "price or an Exclusive flag), and adds the one thing the "
                    "shell has no business knowing — the composition limit. That "
                    "limit is stated and never enforced, for three reasons "
                    "pointing the same way: the rulebook treats going over as "
                    "something to correct in the Post-cycle rather than "
                    "something that cannot happen, n26.notes is explicit that "
                    "nothing blocks on a note, and refusing belongs at the "
                    "operation boundary where main puts overspend. Options are "
                    "behind the disclosure only — a split button on the row "
                    "would put a second decision in front of a reader who has "
                    "not decided to hire at all."
                ),
                parts=(
                    Part(
                        "c-n26.profile-picker.row",
                        "n26/profile_picker/row.html",
                        "One profile: name, price and Hire on a line, with the "
                        "whole card and the other options behind it.",
                        required=True,
                    ),
                ),
            ),
            Component(
                # Not "dialog": the kit's own c-ui.dialog has that slug, and a
                # second component answering to it would take its page.
                slug="server-dialog",
                tag="c-n26.dialog",
                template="n26/dialog.html",
                summary="A question the server decided to ask, and the form that answers it.",
                needs=(ALPINE,),
                notes=(
                    "The panel every server-decided dialog is built from, and "
                    "the only kind of dialog here whose open state is a server "
                    "state: the page draws it when the URL says so, which is "
                    "what makes it a link, makes it survive a reload, and makes "
                    "the click that opened it work with scripting off. "
                    "c-ui.dialog is the other shape — a trigger beside content "
                    "teleported into a <template> and revealed by Alpine — and "
                    "with the answer already decided by the server and no "
                    "script running it draws nothing at all. So this is a "
                    "native <dialog open>: a panel in the flow of the page on "
                    "its own, promoted to a real modal by showModal() where "
                    "Alpine is there to call it, which brings the top layer, "
                    "the backdrop, Escape and a focus trap without any of them "
                    "being written here. Dismissing navigates rather than "
                    "hiding, because a dialog closed in place would leave the "
                    "page on screen while the URL still named what it was "
                    "asking about. It was two copies of that dance before this "
                    "existed — hiring's and the equip page's — which is one copy more "
                    "than a promotion this fiddly can survive."
                ),
            ),
            Component(
                slug="hire-dialog",
                tag="c-n26.hire-dialog",
                template="n26/hire_dialog.html",
                summary=(
                    "What a click leaves to answer: what this fighter is "
                    "called, and what the gang pays for them."
                ),
                needs=(ALPINE,),
                notes=(
                    "c-n26.dialog with hiring's questions in it. What is left "
                    "here is the questions and the fields under them: the "
                    "profile and its options are hidden fields rather than "
                    "controls, because they were picked on the listing that "
                    "was clicked and the way to change them is to go back to "
                    "it. The price in the lead is everything the listing was "
                    "configured to and not the advertised one — an option "
                    "ticked upstairs is charged here, so it is named here. "
                    "The box under the price is the edition's one place a "
                    "rating can be argued with: gear haggled down still counts "
                    "at the quote, while a fighter taken on cheap may be a "
                    "bargain or may be worth less than the book asks, and only "
                    "the table knows which. It starts ticked, because typing a "
                    "price over the quote is most of the way to saying what "
                    "the fighter is worth and the bargain reading is the one "
                    "worth an extra click. It is drawn whether or not the "
                    "price has been typed over, because a control that appears "
                    "under the reader's hands is one they did not know was "
                    "coming."
                ),
            ),
            Component(
                slug="owned-dialog",
                tag="c-n26.owned-dialog",
                template="n26/owned_dialog.html",
                summary=(
                    "Confirm a sale, a move, a refund or a removal of "
                    "something the gang owns — or ask which accessory to "
                    "fit to a weapon."
                ),
                needs=(ALPINE,),
                notes=(
                    "One panel for five questions, because the difference "
                    "between them is a sentence and, for three of them, one "
                    "control — five files "
                    "would be five copies of the same dialog drifting apart a "
                    "fix at a time. Each says the thing a reader cannot work "
                    "out from the page: a sale states its arithmetic, because "
                    "the figure comes from rows nobody can see and it is money; "
                    "a move states what it does not do, since the question "
                    "anyone moving a gun between fighters has is whether it "
                    "costs anything; a removal states that the money stays "
                    "spent, because the Sell button directly above it says "
                    "otherwise; and a refund names what was paid, which is the "
                    "one number that tells it apart from the other two acts "
                    "that also take the thing away. The stash is a button and the roster a select "
                    "because they are not the same kind of choice — one place "
                    "that is always there, against a list that may be long — "
                    "and only the clicked submit is sent, which is the whole of "
                    "how the view tells the two apart. Selling a gun with "
                    "something bolted to it is two sales at two prices, so the "
                    "answers carry a figure each rather than the lead carrying "
                    "one; and fitting an accessory is the question here that "
                    "confirms nothing, sharing the panel because it is the same "
                    "sort of state — one row of a card, open because the "
                    "address says so."
                ),
            ),
            Component(
                slug="owned-lines",
                tag="c-n26.owned-lines",
                template="n26/owned_lines.html",
                summary="What a model is already carrying, and what can happen to it.",
                notes=(
                    "The inside of an equip row for something the fighter already "
                    "has. Drawn the way a card draws the same rows — the thing, "
                    "what it contributed, its parts indented under it — so a "
                    "reader recognises what they are looking at; the weapon's "
                    "own firing line is not among them for the same reason the "
                    "card gives it no row, which is that it *is* the weapon. "
                    "Sell leads, because it is what anybody came here to do, "
                    "and the rarer acts share a chevron. Which of them is red "
                    "is the row's own word rather than this component's, so an "
                    "act added to the structure appears here in the right "
                    "colour with nothing edited. A part offers no move: "
                    "it belongs to the thing it hangs off, and Operation.move "
                    "refuses an assignment with a parent, so a control for it "
                    "would be a click that cannot work. Every control is a link "
                    "to a real address — the dialog is a server state, and the "
                    "catalogue's own form wraps every row on the page, so a form "
                    "in here would be a form inside a form."
                ),
            ),
            Component(
                slug="choice-menu",
                tag="c-n26.choice-menu",
                template="n26/choice_menu.html",
                summary=(
                    "The same panel for one-of choices: radios, no All / None, no only."
                ),
                needs=(ALPINE, KIT_JS, FOCUS),
                notes=(
                    "For the things that are never several at once — a sort order "
                    "being the obvious one. All / None and the per-row only go with "
                    "the checkboxes, since they only mean anything when more than one "
                    "row can be on; what is left is the list and OK / Cancel. The "
                    "trigger shows the chosen label rather than a count, a count "
                    "always being one. If you want a menu that commits the moment you "
                    "pick, the kit's own c-ui.menu is the better fit."
                ),
            ),
            Component(
                slug="toggle",
                tag="c-n26.toggle",
                template="n26/toggle.html",
                summary="A switch with its label beside it, sized to its content.",
                needs=(ALPINE, KIT_JS),
                notes=(
                    "The kit stacks a switch's label above it, and :inline pushes the "
                    "switch to the far right of a full-width row — neither suits a "
                    "toolbar. The wrapping label is load-bearing rather than "
                    "decorative: the kit's switch hides a checkbox bound with x-model, "
                    "so label activation toggles it with no new JavaScript, and the "
                    "switch then picks the label up as its accessible name."
                ),
            ),
            Component(
                slug="link",
                tag="c-n26.link",
                template="n26/link.html",
                summary="An inline text link, with tones and underline modes.",
                notes=(
                    'The kit has no link — c-ui.button variant="text" is still a '
                    "button — so this is the plain one, and what the link-ish "
                    "components are built from. Colour is a prop rather than a class "
                    'because class="text-muted" against a default of text-accent is '
                    "two utilities of equal specificity, and which wins depends on the "
                    "order Tailwind emitted them. Without an href it renders a span, "
                    "not a dead anchor. The text sits in its own span, so the trailing "
                    "slot stays outside the underline."
                ),
            ),
            Component(
                slug="color-swatch",
                tag="c-n26.color-swatch",
                template="n26/color_swatch.html",
                summary="A colour, as a small round mark before a name.",
                notes=(
                    "One component for the mark a gang's colour makes, because the "
                    "gang table, the gang's own heading and the drawer would "
                    "otherwise each answer three questions for themselves and come "
                    "to different answers. One prop takes the colour whether it is a "
                    "literal or a theme name: a hex is frozen because someone chose "
                    "it, while a token resolves through var() and follows a theme "
                    "change. It has to be a style attribute — Tailwind reads class "
                    "names as literal strings, so a class built from a variable is "
                    "one it never emits, while every --color-* variable is emitted "
                    "for exactly this lookup. No colour draws nothing at all: a "
                    "reserved space would be an empty gutter down a list where most "
                    "gangs have none, and a neutral ring would be indistinguishable "
                    "from a gang that picked ink. Aria-hidden unless given a label, "
                    "because a colour on its own tells a reader who cannot see it "
                    "nothing they can use and the name is already beside it."
                ),
            ),
            Component(
                slug="color-link",
                tag="c-n26.color-link",
                template="n26/color_link.html",
                summary="Text with a colour swatch in front of it.",
                notes=(
                    "The sibling of flair-link: both are c-n26.link with something "
                    "in a slot that sits outside the underline — a swatch before the "
                    "text here, a badge after it there. The swatch is "
                    "c-n26.color-swatch, so this owns only the placing of it; a "
                    "heading or a drawer row that already has an anchor of its own "
                    "draws the swatch directly rather than taking a link it does not "
                    "want."
                ),
            ),
            Component(
                slug="flair-link",
                tag="c-n26.flair-link",
                template="n26/flair_link.html",
                summary="Text with a small SVG badge after it, linked or not.",
                notes=(
                    "c-n26.link with a badge in its trailing slot, so everything about "
                    "being a link lives there and this only owns the badge. The "
                    "trailing slot is outside the underline, which is the point — a "
                    "rule running under the artwork reads as a mistake. The badge is "
                    "sized in em rather than px, so one component works in a table "
                    "cell and in a heading with no size prop, and the rule is applied "
                    "to descendant svg because the artwork belongs to the caller."
                ),
                parts=(
                    Part(
                        "c-n26.flair.staff",
                        "n26/flair/staff.html",
                        "The pixel-art staff badge, drawn from the platform's own "
                        "badge asset. Fixed palette by design.",
                    ),
                    Part(
                        "c-n26.flair.house",
                        "n26/flair/house.html",
                        "The Goliath house icon. Drawn with currentColor, so it "
                        "follows the text.",
                    ),
                    Part(
                        "c-n26.flair.gang-type",
                        "n26/flair/gang_type.html",
                        "A gang type's own artwork, sanitised on the way out. The "
                        "only badge here that is content rather than a drawing we "
                        "ship — so the only one that can be absent, and the only "
                        "one that is untrusted.",
                    ),
                ),
            ),
            Component(
                slug="user-link",
                tag="c-n26.user-link",
                template="n26/user_link.html",
                summary="A person's name with the badge they actually hold.",
                notes=(
                    "flair-link with the badge decided rather than passed in, "
                    "because the alternative is every page deciding for itself and "
                    "the pages disagreeing. Which mark someone shows belongs to the "
                    "person, not to the screen they appear on: it is derived from "
                    "their live supporter standing and staff flag against the "
                    "platform's registry, plus their own pick among what that "
                    "leaves them. Drawing it from is_staff — which one page did — "
                    "gives every supporter no badge at all. There is no label prop "
                    "for the same reason: the wording comes from the registry, so a "
                    "call site cannot guess wrong about what someone else's badge "
                    "means, and a new tier needs no edition change."
                ),
            ),
            Component(
                slug="page-header",
                tag="c-n26.page-header",
                template="n26/page_header.html",
                summary="What this page is, at the top of it.",
                notes=(
                    "Exists because two screens had already disagreed: the gang "
                    "sheet set its name at text-2xl and the hire form set its at "
                    "text-xl, for no reason either template could have told you. "
                    "One scale, decided here. The trail, the lead and the page's "
                    "controls are all optional and compose around it. The lead "
                    "takes one name for either shape — pass a string for a few "
                    "words or open a slot for markup — because `.strip` is a "
                    "method on a string as much as on slot content, so the "
                    "template never has to know which it got, and the common case "
                    "stays a bare attribute."
                ),
            ),
            Component(
                slug="about",
                tag="c-n26.about",
                template="n26/about/index.html",
                summary="What a piece of content does, and how anyone comes to have it, in sentences.",
                notes=(
                    "The authoring pages' explanation column. It draws the "
                    "structure n26.library.prose compiles — how a thing is "
                    "referenced (built into, given by, offered by…), what it "
                    "does in the order the rules apply it, and how much of the "
                    "player side is assigned to it. Each sentence's hint sits "
                    "behind a hover or keyboard focus, CSS-only, with the "
                    "browser's title as the touch fallback; a sentence whose "
                    "subject has a page is a link, and one without is plain "
                    "words, which is an answer rather than a gap. Views fill "
                    "the addresses in — the compiler knows no URLs."
                ),
                parts=(
                    Part(
                        "c-n26.about.sentence",
                        "n26/about/sentence.html",
                        "One sentence: linked where its subject has a page, "
                        "its hint behind hover or focus.",
                        required=True,
                    ),
                ),
            ),
            Component(
                slug="prose",
                tag="c-n26.prose",
                template="n26/prose.html",
                summary="A run of authored copy: headings, paragraphs, lists.",
                notes=(
                    "For prose a template writes, where c-n26.rich-text is for "
                    "prose a database stores. The library had one and not the "
                    "other, so anything hand-written in a page fell back to "
                    "whatever utilities its author reached for — which is how two "
                    "screens ended up with two heading scales. Both go through the "
                    "same .rich-text rules, so a page's own copy and a description "
                    "typed into the editor are the same typography. Plain HTML "
                    "inside, not components: the tags are the vocabulary, a "
                    "paragraph component would be a paragraph with extra steps, "
                    "and the styling reaches them by descendant selector precisely "
                    "so an author can write ordinary markup. Capped at max-w-prose "
                    "unless something else already constrains the width."
                ),
            ),
            Component(
                slug="form-actions",
                tag="c-n26.form-actions",
                template="n26/form_actions.html",
                summary="How a form ends: the way out, then the act.",
                notes=(
                    "Every form's footer, decided once. The screens had already "
                    "disagreed — an outlined Cancel beside a green Hire here, a "
                    "text link after a red Delete there — and none of that was "
                    "anybody's decision; it was four footers written by hand. "
                    "So the order and the alignment are not props: the way out "
                    "is left of the act, the pair is right-aligned where the "
                    "eye finishes the last field, and the act is last because "
                    "it is what the form is for. Cancel is an href and never a "
                    "submit, because leaving is not a submission and a reader "
                    "clicking it should land where they already were; a form "
                    "with nowhere to go back to passes no cancel_url and gets "
                    "no cancel, which beats one that leads somewhere "
                    "arbitrary. It is ghost so the two do not compete — the act "
                    "carries the colour that says what it does, and a cancel of "
                    "equal weight beside it makes a reader read both to find "
                    "the one they want. c-n26.form-page draws its footer with "
                    "this rather than repeating it, so a page form and a dialog "
                    "end the same way."
                ),
            ),
            Component(
                slug="form-page",
                tag="c-n26.form-page",
                template="n26/form_page.html",
                summary="The wrapper every form screen shares.",
                notes=(
                    "There is one of these and every form uses it, which is the "
                    "whole point: there were briefly two, and create-gang had "
                    "drifted to max-w-2xl with space-y-8 while hire was "
                    "max-w-3xl with space-y-4. Nobody decided that — they were "
                    "written a week apart. So the measure, the vertical rhythm, "
                    "the header and the footer live here and a form view "
                    "supplies its fields and nothing about the frame. The "
                    "measure is about 42em, because a text input a foot wide is "
                    "harder to aim at and harder to read back than one the width "
                    "of a paragraph; the gap between sections is visibly larger "
                    "than the gap between fields, which is what makes a group "
                    "read as a group without a box round it. The footer is "
                    "optional: a form whose submit lives elsewhere passes no "
                    "submit_label and gets none, which is how the hire screen "
                    "avoids a Create button under a list of Hire buttons. What "
                    "it does draw is c-n26.form-actions, so the wrapper owns "
                    "the rule above the footer and nothing about the footer "
                    "itself — a form that is a section of somebody else's page "
                    "reaches for the same component and ends identically. The "
                    "heading is c-n26.page-header, and everything that header "
                    "takes is handed on rather than reinvented: the trail, a "
                    "mark before the title, the page's own controls, and a "
                    "switcher on the title's line — because a form screen is a "
                    "page and a reader on one of five fighters' skills wants "
                    "the same way to the next that the kit screen gives them. "
                    "The one prop that had to be renamed is the header's "
                    "`actions`, which arrives as `header_actions`: this "
                    "wrapper already had an `actions` meaning the extra "
                    "control beside the submit, and the two are a screen "
                    "apart. Every one of them is declared, which is the whole "
                    "of the mechanism — a slot this wrapper did not declare "
                    "would not be empty when nobody filled it, it would be "
                    "whatever the page happened to hold under that name."
                ),
            ),
            Component(
                slug="form-section",
                tag="c-n26.form-section",
                template="n26/form_section.html",
                summary="A titled group of fields inside a form.",
                notes=(
                    "The unit a form is built from. Eight fields in one run is a "
                    "wall; the same eight under two headings is two short "
                    "questions, and a reader can tell before starting which "
                    "parts they can skip. Separated by space and a heading "
                    "rather than boxed — four lines around every group makes a "
                    "short form look like a settings screen, and the gap after "
                    "the last field is already saying where the group ended. "
                    "c-ui.card is there for the cases that genuinely want a "
                    "container. The title renders as an h2, so a form of these "
                    "has a real document outline rather than a run of bold "
                    "text. A description is better absent than restating the "
                    "labels underneath it."
                ),
            ),
            Component(
                slug="colour-picker",
                tag="c-n26.colour-picker",
                template="n26/colour_picker.html",
                summary="Pick a colour from the palette, or none.",
                notes=(
                    "Radios and not a select, because the question is entirely "
                    "'which of these looks right' and a dropdown makes you open "
                    "it, read twenty words and close it again to compare two. "
                    "Each radio is sr-only with the swatch styled through "
                    "peer-checked, so it is a real input in a real label: "
                    "keyboard-reachable, arrow-keys between options, submits "
                    "with no JavaScript, and reads its colour's name aloud. "
                    "None is the first swatch and a real value rather than the "
                    "absence of one — a picker defaulting to nothing-selected "
                    "cannot be returned to nothing once touched, and cannot "
                    "tell 'no colour' from 'not answered yet' when a form comes "
                    "back after an error. The swatch classes are a lookup "
                    "because Tailwind reads class names as literal strings and "
                    "never emits one built from a variable. The grid is "
                    "auto-fill, so how many fit a row is not a decision anybody "
                    "has to maintain."
                ),
            ),
            Component(
                slug="filter-select",
                tag="c-n26.filter-select",
                template="n26/filter_select.html",
                summary="A long select, with a box to search it.",
                needs=(ALPINE,),
                notes=(
                    "Wraps a real <select> rather than replacing it. The kit's "
                    "own c-ui.combobox was the obvious thing to reach for and "
                    "cannot be used here: it submits through a <select> whose "
                    "name is an Alpine binding and whose options are a "
                    "<template>, so with scripting off it has neither a name "
                    "nor an option and posts nothing — and the options it does "
                    "render carry their label text as their value, which cannot "
                    "say which row an author picked. Here the select handed in "
                    "is what posts, untouched, and the panel sets selectedIndex "
                    "on it; turn scripting off and you get the plain select, "
                    "working. Short lists are left alone, counted in the "
                    "browser because the options are already on the page — "
                    "asking the database means a COUNT per picker, and an "
                    "authoring form draws about a dozen."
                ),
            ),
            Component(
                slug="radio-cards",
                tag="c-n26.radio-cards",
                template="n26/radio_cards/index.html",
                summary="Pick exactly one of a handful of things, as a grid of cards.",
                parts=(
                    Part(
                        "c-n26.radio-cards.card",
                        "n26/radio_cards/card.html",
                        "One option: a radio, a name, a badge and a line of detail.",
                        required=True,
                    ),
                ),
                notes=(
                    "A sibling of checkbox-card rather than a mode of it. That "
                    "card dims and inerts its body while unticked, because "
                    "choices inside an unselected card are choices about "
                    "something that is not happening — but in a group where "
                    "exactly one thing is picked, every card but one is "
                    "unpicked at all times, so the same treatment would grey "
                    "out the options the reader is trying to compare and make "
                    "the whole group read as disabled. It also cannot own its "
                    "state: one-of-many is the browser's rule over a shared "
                    "name, not something a card decides about itself. Cards "
                    "and not a select for the colour picker's reason — a "
                    "dropdown makes you open it, read the options and close it "
                    "again to weigh two of them — and because an option is one "
                    "string, so a badge and a line of detail have nowhere to "
                    "go. Selected state is has-[:checked] on the label rather "
                    "than script, so the page is right before anything runs "
                    "and stays right if nothing ever does. The grid is "
                    "auto-fill off a track floor, so how many fit a row "
                    "follows from how wide a card has to be to stay readable."
                ),
            ),
            Component(
                slug="choice-offer",
                tag="c-n26.choice-offer",
                template="n26/choice_offer.html",
                summary="A whole list of things to pick one of, under its headings.",
                parts=(
                    Part(
                        "c-n26.radio-cards",
                        "n26/radio_cards/index.html",
                        "One heading and the cards under it.",
                        required=True,
                    ),
                ),
                notes=(
                    "The pick screen, minus the page. It exists because two "
                    "screens draw the same list for different reasons — "
                    "choosing for a slot a rule offered, and browsing everything "
                    "a fighter may learn — and the alternative was a second "
                    "template that looked identical and would drift the first "
                    "time one of them grew a badge. Every group shares one input "
                    "name, so the browser keeps a single selection across the lot: "
                    "the headings are how the list is read, not four separate "
                    "questions. Nothing here knows what is being picked; the "
                    "view has already flattened it into groups and options, "
                    "which is what lets a skill, an archetype and an affiliation "
                    "share a screen. An empty list is a thing to say rather than "
                    "a page to hide, and what to say is the caller's — why it is "
                    "empty is something the page knows and this does not."
                ),
            ),
            Component(
                slug="choice-picks",
                tag="c-n26.choice-picks",
                template="n26/choice_picks.html",
                summary="A list of things to choose and unchoose one at a time.",
                notes=(
                    "The third way to draw the same structure, and a sibling of "
                    "the other two for the reason they are siblings of each "
                    "other: radios ask which one, boxes ask which of these, and "
                    "a choice holding three picks asks neither. A mode of "
                    "choice-offer is the obvious saving and the wrong one: the "
                    "single selection a shared name keeps across the lot is "
                    "exactly what must not happen here, so every branch in that "
                    "template would be undoing what its radios do. Each option "
                    "carries its own submit instead: the one that "
                    "was clicked is the only one sent, which is how adding and "
                    "taking back tell themselves apart with no script and no "
                    "state to keep. What the choice holds draws with the act "
                    "that takes it back; when it is full the rest are not listed "
                    "at all, because the alternative is a click that silently "
                    "drops a pick the reader made earlier. Which act an option "
                    "gets is decided in Python and read off the option, so this "
                    "never works out for itself what the choice is holding."
                ),
            ),
            Component(
                slug="tick-list",
                tag="c-n26.tick-list",
                template="n26/tick_list.html",
                summary="A list of things to tick, grouped under its headings.",
                notes=(
                    "The same structure choice-offer draws, and a sibling of it "
                    "rather than a mode: one of many is the browser's rule over a "
                    "shared name, any number is the absence of that rule, and the "
                    "two say different things about what leaving a box alone "
                    "means. Rows and not cards, because this draws in a box beside "
                    "a model's card where a grid of cards would be a second page — "
                    "and a list read down a column is how a set of ticks is read. "
                    "Checkboxes and no script: what arrives ticked is what the "
                    "server said, so the form is right before anything runs. An "
                    "option a rule grants is drawn ticked and fixed, saying what "
                    "grants it, because nothing stored is behind it and a click "
                    "could not take it away; a fixed box submits nothing, which is "
                    "why whatever applies the difference must leave granted things "
                    "out of it rather than read their silence as a clearing. An "
                    "empty offer draws nothing — why it is empty is the page's to "
                    "say, not this component's."
                ),
            ),
            Component(
                slug="checkbox-card",
                tag="c-n26.checkbox-card",
                template="n26/checkbox_card.html",
                summary="A selectable card whose body stays interactive.",
                needs=(ALPINE,),
                notes=(
                    "The kit's checkbox cards make the whole surface the toggle, "
                    "which is right up until the card holds controls of its own — "
                    "then a click on any of them would toggle the card. This one "
                    "confines the toggle to its header and keeps the body live, "
                    "which is the difference that justifies a second component; "
                    "the presentation is deliberately the kit's, so the two read "
                    "as one family. While unticked the body is dimmed and inert — "
                    "choices inside an unselected card are choices about something "
                    "that is not happening. inert stops interaction and focus but "
                    "not submission, so an input that must not submit while the "
                    "card is unticked binds :disabled to the `picked` the card "
                    "puts in scope."
                ),
            ),
            Component(
                slug="divider",
                tag="c-n26.divider",
                template="n26/divider.html",
                summary="A rule with words in it, saying why it separates.",
                notes=(
                    "A bare rule between two blocks makes a reader work out the "
                    'relationship; this one states it — "or …" marks the block '
                    "below as an alternative to the one above, not a continuation. "
                    "The lines are flex spans rather than a styled <hr>, so the "
                    "label sits in the rule without a background patch over a line "
                    "— the trick that breaks the moment the page behind it is not "
                    "one flat colour. Muted and small on purpose: a divider is "
                    "wayfinding, not content, and one that draws the eye competes "
                    "with the headings it sits between. With nothing to say it "
                    "degrades to a plain rule."
                ),
            ),
            Component(
                slug="coming-soon",
                tag="c-n26.coming-soon",
                template="n26/coming_soon.html",
                summary="A section that exists but is not built yet.",
                notes=(
                    "Not an empty state, and the difference is the whole point of "
                    "having both. A table's empty slot says the reader can fix this "
                    "by searching for something else; this says there is nothing to "
                    "fix and no reason to come back today. Wiring a tab to one of "
                    "these is how a nav gets to be honest about what is coming "
                    "without the tab having to appear later and surprise people. "
                    "Deliberately plain — no illustration, no button, nothing "
                    "actionable — because a placeholder that draws the eye draws it "
                    "again on every load. Body copy at the normal size: it is read "
                    "once and then skipped, which is the right outcome, and small "
                    "print would only make that one reading harder."
                ),
            ),
            Component(
                slug="statline",
                tag="c-n26.statline",
                template="n26/statline/index.html",
                summary="A set of characteristics as a compact strip.",
                notes=(
                    "One component for two jobs, because build_statline() in "
                    "core/render.py serves a fighter profile and a weapon profile "
                    "alike. The divider and the tint come from is_first_of_group and "
                    "is_highlighted on StatlineTypeStat, so where a row breaks is "
                    "content rather than a decision in the template. Header and "
                    "cells are separate parts that emit cells rather than rows, "
                    "which is what lets the weapon table put a name column in front "
                    "of the same stats. Not built on c-ui.table: a statline is a "
                    "centred strip where that is a left-aligned data grid, and its "
                    "descendant-variant styling outranks any class on a cell, so it "
                    "cannot be adjusted from the call site. The editor is a fourth "
                    "template rather than a mode on this one: a card is drawn in its "
                    "hundreds on a gang sheet and carries no form, so sharing would "
                    "put a branch in every cell of the hot path to serve the one page "
                    "that edits. It reuses the header unchanged, which is what keeps "
                    "the columns, the divider and the tint identical to the card "
                    "being edited."
                ),
                needs=(ALPINE, KIT_JS),
                parts=(
                    Part(
                        "c-n26.statline.header",
                        "n26/statline/header.html",
                        "The <th> cells, with an optional leading column.",
                        required=True,
                    ),
                    Part(
                        "c-n26.statline.cells",
                        "n26/statline/cells.html",
                        "The <td> cells. Marks a modified value and names what "
                        "changed it.",
                        required=True,
                    ),
                    Part(
                        "c-n26.statline.edit",
                        "n26/statline/edit.html",
                        "The same strip as boxes to type in, for the authoring pages.",
                    ),
                ),
            ),
            Component(
                slug="gang-table",
                tag="c-n26.gang-table",
                template="n26/gang_table/index.html",
                summary="The gangs you own, searchable, each row clickable.",
                needs=(ALPINE, KIT_JS),
                parts=(
                    Part(
                        "c-n26.gang-table.row",
                        "n26/gang_table/row.html",
                        "One gang: name, type, what it is worth, and its actions.",
                    ),
                ),
                notes=(
                    "Called a table because that is what it is to a reader, and "
                    "built as a list of grid rows because a real one cannot "
                    "survive a phone: four columns, one of them a four-figure "
                    "wealth strip and one a pair of buttons, is more than 390px "
                    "holds, and the usual escape — display:block on the cells — "
                    "throws away the alignment that made it a table. A grid keeps "
                    "both, and drops nothing at either width. The whole row is one "
                    "link by way of exactly one real <a>, on the name, whose "
                    "::after is stretched over the row: wrapping the row in an "
                    "anchor would put two buttons inside a link, and a click "
                    "handler on a div would lose the URL, middle-click and "
                    "keyboard focus. The buttons are lifted above the stretch, "
                    "which is the row's decision and so lives on the markup. Type "
                    "is a plain select rather than c-n26.filter-menu: one question "
                    "with one answer does not need Apply and Cancel."
                ),
            ),
            Component(
                slug="changelog",
                tag="c-n26.changelog",
                template="n26/changelog/index.html",
                summary="What changed lately, newest first.",
                parts=(
                    Part(
                        "c-n26.changelog.entry",
                        "n26/changelog/entry.html",
                        "One update: a short title, two lines of it, a date.",
                    ),
                ),
                notes=(
                    "A list, not a feed: nothing loads more, and the point of it "
                    "on a dashboard is seeing at a glance whether anything has "
                    "happened since last time. Summaries clamp at two lines — one "
                    "is a headline and the entry already has a headline, and the "
                    "full text is a click away, so it cuts where reading it here "
                    "stops being cheaper than opening it. The way through to "
                    "everything is in the heading rather than a last row: a row "
                    "that opens an index is the one row in a list that does not "
                    "behave like the list. Rows are clickable by the same means "
                    "the gang table uses."
                ),
            ),
            Component(
                slug="wealth",
                tag="c-n26.wealth",
                template="n26/wealth/index.html",
                summary="What a gang is worth, as a figure strip.",
                needs=(ALPINE, KIT_JS),
                parts=(
                    Part(
                        "c-n26.wealth.figure",
                        "n26/wealth/figure.html",
                        "One labelled figure: the short name over the value.",
                    ),
                ),
                notes=(
                    "Four figures in the order they answer questions about each "
                    "other — rating is what the gang fields, credits what is left, "
                    "stash what the gang owns and nobody carries, wealth the three "
                    "added up — so "
                    "reading left to right is reading the sum. Badges would put "
                    "them in no relation at all. Takes the whole GangSheet rather "
                    "than four numbers, because four positional integers in the "
                    "same units are four chances to swap two and never find out. "
                    "A definition list, not a table: a table needs its headers and "
                    "values in separate rows, so each label and figure would be "
                    "written twice and kept in step by hand. Real tooltips here "
                    "where the statline uses a title attribute — that component "
                    "spends nothing per cell because a gang sheet carries "
                    "hundreds, and this strip is four cells once on a page, so it "
                    "can afford the thing that works without a mouse."
                ),
            ),
            Component(
                slug="gang-figures",
                tag="c-n26.gang-figures",
                template="n26/gang_figures.html",
                summary=(
                    "The numbers a spending decision is made against: the "
                    "roster count beside the wealth strip."
                ),
                needs=(ALPINE, KIT_JS),
                notes=(
                    "The hire list draws this above its rows and the model "
                    "screens keep it in their header's far corner, because "
                    "hiring and buying are decided against how many models the "
                    "gang fields and what it has left to spend — and a reader "
                    "mid-decision should not have to go back to the sheet to "
                    "check. The count wears the wealth strip's own cell so the "
                    "row reads as one system, but it is not wealth, so it "
                    "stands in a strip of its own with the money fenced off "
                    "behind the rule. It takes no ¢, being a count — the one "
                    "place the figure cell's unit is turned off rather than "
                    "assumed."
                ),
            ),
            Component(
                slug="roster-summary",
                tag="c-n26.roster-summary",
                template="n26/roster_summary.html",
                summary="The roster's arithmetic behind a calculator: counts and ratings.",
                needs=(ALPINE, KIT_JS),
                notes=(
                    "The two sums a player does on their fingers mid-decision: "
                    "which profiles at which ranks and how many of each, and "
                    "every model with its pinned rating, totalled. A dropdown "
                    "beside the gang's figures rather than a block of the page, "
                    "because these are numbers checked in passing — a page that "
                    "printed the whole tally would spend a screen of every "
                    "visit on what most visits skim. Two small tabs of one "
                    "panel, because they are two readings of one list; both "
                    "keep the roster's own order, pets after their keepers, so "
                    "the tally reads down the way the sheet does. The totals "
                    "row is the check: the count is the M figure beside the "
                    "trigger, and the ratings total is the sum of the models "
                    "listed — which the gang's own rating figure need not "
                    "equal, since a gang can carry worth no single model does."
                ),
            ),
            Component(
                slug="detail-list",
                tag="c-n26.detail-list",
                template="n26/detail_list/index.html",
                summary="Labelled values, dense, each value a control.",
                needs=(ALPINE, KIT_JS, FOCUS),
                parts=(
                    Part(
                        "c-n26.detail-list.row",
                        "n26/detail_list/row.html",
                        "One label and its value, as an xs button.",
                    ),
                ),
                notes=(
                    "A gang has a dozen small standing facts and every one of them "
                    "is something you can change, so the value is also the way to "
                    "edit it. One control however much it holds: three skill trees "
                    "are one choice, and three buttons would "
                    "say there were three questions. Built along action-links' "
                    "lines — the rhythm belongs to the container, so hiding a row "
                    "behind a permission check cannot leave a gap — but with no "
                    "separator between pairs, because a mark between one pair and "
                    "the next reads as being inside the pair. Flex wrap rather "
                    "than a grid: a grid aligns every value to the widest label on "
                    "the sheet, which spends most of a phone on nothing. The "
                    "control keeps its border, because a ghost button is a value "
                    "that only looks clickable once you are already pointing at "
                    "it, which on a phone is never."
                ),
            ),
            Component(
                slug="choice-slots",
                tag="c-n26.choice-slots",
                template="n26/choice_slots.html",
                summary="Open questions as rows: what was chosen, or a Choose control.",
                needs=(ALPINE, KIT_JS, FOCUS),
                notes=(
                    "Rows rather than a container of its own, so a gang's choices "
                    "and its counters sit in one detail list. Two containers side "
                    "by side would set one run of labelled facts at two rhythms "
                    "with a gap between them that means nothing. Settled and "
                    "open are the same control leading to the same page, "
                    "because they are the same question — clicking a settled "
                    "slot is how you change your mind, and giving it a different "
                    "shape would say it could not be revisited. An open one is "
                    "never marked as missing: nothing counts it, nothing refuses "
                    "to proceed without it. A line with no address — a card built "
                    "from a profile's default equipment has real offers and no "
                    "rows to choose against — draws as text with an em dash "
                    "rather than as a button that goes nowhere."
                ),
            ),
            Component(
                slug="stash",
                tag="c-n26.stash",
                template="n26/stash/index.html",
                summary="The gang's storage, as a card in the roster's grid.",
                parts=(
                    Part(
                        "c-n26.stash.group",
                        "n26/stash/group.html",
                        "One kind of thing, and the things.",
                    ),
                ),
                notes=(
                    "A card among the fighters' cards, because the stash is a "
                    "place gear lives the way a fighter is: it takes the grid's "
                    "first slot, so what the gang holds and who holds what read "
                    "as one layout, and moving something between a card and the "
                    "stash is a move between two like things on one screen. "
                    "Grouped by what kind each item is, because that is the "
                    "question actually asked of a stash: you scan it for "
                    "armour, not for the thing called Mesh armour, and a flat "
                    "alphabetical list makes that a read of every line. Items run "
                    "on and wrap rather than taking a row each — the stash is a "
                    "footnote on a gang sheet, not the point of it — and ratings "
                    "sit against their own item, since nothing is being compared "
                    "down a stash. The total sits on the header line, where a "
                    "fighter's card puts its rating and for the same reason. An "
                    "empty stash still draws the card: it holds a grid slot "
                    "either way, and a slot that comes and goes with the "
                    "contents moves every fighter after it around the grid. "
                    "Drawn through c-n26.assignable-lines, so something a "
                    "modifier put there carries the mark it would on a card."
                ),
            ),
            Component(
                slug="model-header",
                tag="c-n26.model-header",
                template="n26/model_header.html",
                summary="One model's name and rank, and the tabs of their screens.",
                needs=(ALPINE, FOCUS),
                notes=(
                    "The one header every per-model screen wears. Edit and Equip "
                    "are two faces of the same model, so they share a header and "
                    "read as tabs of one place — a component rather than a "
                    "convention, because two screens each writing the same header "
                    "by hand are two screens free to drift about what a model's "
                    "page looks like. The title is the model's name plain, not "
                    "the verb: the tab strip already says which face is open, and "
                    "a title that repeated it would say it twice while making the "
                    "name harder to scan for. The tab strip is built by the "
                    "model_screen_tabs tag rather than passed in, so a screen "
                    "cannot invent a strip of its own; adding a screen to a model "
                    "is one edit to n26.core.navigation."
                ),
            ),
            Component(
                slug="model-card",
                tag="c-n26.model-card",
                template="n26/model_card/index.html",
                summary="A fighter's card: characteristics, weapons, skills, gear, XP.",
                notes=(
                    "Renders a n26.render.ModelCard, which the backend already "
                    "assembles in one query — the template computes nothing. It "
                    "follows the rulebook's Model Card anatomy and then keeps going "
                    "where digital allows: every line on the card carries its "
                    "provenance, so a modified characteristic says what changed it "
                    "and a granted skill or trait is marked apart from a bought one. "
                    "Paid ammo is priced under its weapon, and a choice draws as its "
                    "own row — resolved or not, because an open one is "
                    "information rather than an error. Read-only about the fighter's "
                    "numbers: nothing here changes a statline or a weapon. Three rows "
                    "carry controls, each because it is the row a reader is already "
                    "looking at for the thing it does — Notes and lore take an Edit "
                    "each, being the only parts of a card a player writes rather than "
                    "earns, and Skills takes two: the question a rule asked, and the "
                    "way to what this fighter may learn. A skill question is drawn "
                    "there rather than among the other slots because a skill has a "
                    "row already; filed with the archetype it reads as one more "
                    "field to fill in. Every control is drawn from an href on the "
                    "structure, so a print sheet and a hire preview draw none of "
                    "them without asking. Almost nothing is greyed "
                    "out: hierarchy is weight and size, and an empty value is an "
                    "em dash. The two exceptions are captions rather than "
                    "content — the profile name under the model's, and the XP "
                    "target beside the current one. The card renders in one of "
                    "two modes: gang, the sheet's — dense, read-mostly, the open "
                    "questions shown but their buttons held back, because eleven "
                    "cards abreast should not be eleven rows of controls — and "
                    "edit, the model's own page, where the choice buttons come "
                    "out outlined and the Gear and Weapons rows carry the way to "
                    "the Equip tab. Inside the template a mode-only region is a "
                    "wrap in c-n26.model-card.mode, not a flag threaded through "
                    "every region between it and the call site."
                ),
                needs=(ALPINE, KIT_JS),
                parts=(
                    Part(
                        "c-n26.assignable-lines",
                        "n26/assignable_lines.html",
                        "A run of assignables — skills, gear, weapon traits — "
                        "marking the ones that were granted rather than bought.",
                        required=True,
                    ),
                    Part(
                        "c-n26.model-card.mode",
                        "n26/model_card/mode.html",
                        "A region of the card that one mode draws — reads the "
                        "enclosing card's mode from context, so the call sites "
                        "stay one line.",
                    ),
                    Part(
                        "c-n26.model-card.prose",
                        "n26/model_card/prose.html",
                        "A written section at the foot of a card: Notes, Lore.",
                    ),
                ),
            ),
            Component(
                slug="rich-text",
                tag="c-n26.rich-text",
                template="n26/rich_text.html",
                summary=(
                    "A TinyMCE editor that behaves like the other fields, and the "
                    "safe renderer for what it produces."
                ),
                needs=(ALPINE, "TinyMCE", "form.media"),
                notes=(
                    "Two modes because they are two views of the same content: pass a "
                    "bound field for the editor with an Edit / Preview switch, or just "
                    "a value for the rendered article. Wrapped in c-ui.field, so "
                    "label, "
                    "description and errors work as they do on c-ui.input. Rendering "
                    "always goes through safe_rich_text — editor output is user input "
                    "that has been round-tripped through a database, so it is "
                    "sanitised on the way out rather than trusted. You must render "
                    "{{ form.media }} once on the page or no editor appears; the "
                    "widget "
                    "is only a textarea until that script runs."
                ),
            ),
            Component(
                slug="action-bar",
                tag="c-n26.action-bar",
                template="n26/action_bar.html",
                summary=(
                    "The inline row that buttons, groups, dropdowns and links sit in."
                ),
                notes=(
                    "Layout only: a wrapping flex row keeping controls of differing "
                    "heights on one centre line, with a trailing slot pushed to the "
                    "far end. This was filter-bar, which was the same row under a "
                    "narrower name — filtering is an action, and two components with "
                    "identical markup is how a design system starts drifting. "
                    ":surface puts it on a tinted strip, for a secondary bar inside a "
                    "card rather than at the top of a page."
                ),
            ),
            Component(
                slug="button-group",
                tag="c-n26.button-group",
                template="n26/button_group.html",
                summary="Buttons joined into one control.",
                notes=(
                    "The kit has no button group. The group owns the outer radius, its "
                    "children give up theirs, and each after the first pulls left a "
                    "pixel so touching borders read as one line. Done in CSS because "
                    "rounded-none on a c-ui.button would only tie with the "
                    "rounded-button already there, and ties are settled by whichever "
                    "order Tailwind happened to emit. Anything can join the run — a "
                    "dropdown trigger included, which is how you get the split caret "
                    "at the end of a toolbar."
                ),
            ),
            Component(
                slug="quick-switcher",
                tag="c-n26.quick-switcher",
                template="n26/quick_switcher/index.html",
                summary=(
                    "What you are looking at, joined to a filtered list of what "
                    "you could look at instead."
                ),
                needs=(ALPINE, KIT_JS, FOCUS),
                notes=(
                    "One component in two shapes — a lone chevron, or a ghost "
                    "button group with the linked thing in front of it — and the "
                    "leading button being optional is the whole shape of the API: "
                    "half the places that want a switcher already name the current "
                    "thing in a heading a foot away, and repeating it in a button "
                    "is furniture. With no label the chevron is the only child of "
                    "the group, which rounds both its ends rather than leaving a "
                    "shape cut in half. Ghost, both halves, and that carries the "
                    "affordance: at rest they are the text colour of whatever they "
                    "sit in, so the control reads as words in a bar rather than as "
                    "furniture competing with the page's own name, and the hover "
                    "fill is what says a half can be clicked — the name is the way "
                    "to the thing, the chevron the way to the rest. The padding is "
                    "cut well below what a button this size asks for so nothing "
                    "sits between the halves, but the text is not: a name should "
                    "be the size of the words around it. The panel is the "
                    "kit's dropdown, so the outside click and the placement are "
                    "its. A native <details> was "
                    "the alternative — it opens with no script and would need no "
                    "second copy of the list — and it was not taken because the "
                    "joining is done by CSS matching button and a, and a <summary> "
                    "is neither: the chevron would take none of the group's radius "
                    "or border handling, and everything the dropdown gets right "
                    "would have to be rebuilt beside it. The price of that choice "
                    "is a <noscript> strip drawing the same destinations flat, "
                    "which is what the navigation drawer already does. Filtering "
                    "narrows rows that are already on the page and never asks the "
                    "server; the rows register their own text, so the count behind "
                    "the empty message and the list itself are one array. Focus "
                    "lands in that box on open and never leaves it: Down and Up "
                    "move a highlight, Enter goes to the highlighted row, and "
                    "Escape empties a filter that has something in it before a "
                    "second click closes the panel. The highlight walks only the "
                    "rows the filter is showing — a position in the whole list "
                    "counts rows nobody can see and lands on one of them — and it "
                    "is a tint plus a name, because the box carries "
                    "aria-activedescendant and so announces the row it is on. "
                    "Real focus was the alternative and is the wrong one here: "
                    "moving focus to a row takes the caret out of the box, and "
                    "the next letter typed goes nowhere. The pointer moves the "
                    "highlight as well, so there is only ever one answer on "
                    "screen to where Enter goes. Rows "
                    "carry their own bottom rule rather than the list dividing "
                    "between them, because a divide counts hidden rows and the "
                    "first one left showing would draw a rule under nothing. The "
                    "panel is kept inside the window whatever the trigger is doing: "
                    "CSS caps its width at the window less a gutter, and a margin "
                    "the kit's placement never touches nudges it back in from "
                    "whichever edge it crosses. Nudged rather than flipped to the "
                    "trigger's other side, because flipping helps a trigger near an "
                    "edge and does nothing for one in the middle of a phone with a "
                    "panel wider than either side of it. A hotkey letter turns on "
                    "a page-wide chord — ⌥⇧ plus it opens the panel from wherever "
                    "focus is, with the caret landing in the filter — and the "
                    "chevron's tooltip and aria-keyshortcuts both say so. The "
                    "application spends two: ⌥⇧F for the bar's switcher on every "
                    "screen, ⌥⇧R for the one beside a page's own heading."
                ),
                parts=(
                    Part(
                        "c-n26.quick-switcher.item",
                        "n26/quick_switcher/item.html",
                        "One destination: icon, label, and a tick when it is the "
                        "one you are on.",
                        required=True,
                    ),
                    Part(
                        "c-n26.quick-switcher.choice",
                        "n26/quick_switcher/choice.html",
                        "One answer rather than one destination: a button that "
                        "reports its own label, for a switcher whose "
                        "alternatives are states of the page.",
                    ),
                    Part(
                        "c-n26.quick-switcher.of",
                        "n26/quick_switcher/of.html",
                        "The whole control from one Switcher structure, which is "
                        "how the application draws every one of them.",
                    ),
                ),
            ),
            Component(
                slug="action-links",
                tag="c-n26.action-links",
                template="n26/action_links.html",
                summary="A run of links separated by middle dots.",
                notes=(
                    "The dots are drawn by CSS on every child but the first, not "
                    "written at each call site — so adding, reordering or "
                    "permission-hiding a link cannot leave a stray separator behind. "
                    "The icon slot is one icon for the whole run, which is the shape "
                    "these rows usually take."
                ),
                parts=(
                    Part(
                        "c-n26.action-link",
                        "n26/action_link.html",
                        "One link in the run, with an optional icon and a danger tone.",
                        required=True,
                    ),
                ),
            ),
        ],
    ),
    Group(
        "Print",
        (
            "Paper, which is a different medium and behaves like one. These are the "
            "only components in the library that are not about a screen, and the "
            "constraints are much tighter: fixed physical sizes in millimetres, a "
            "page fold you do not control, and engines — iOS Safari above all — that "
            "quietly ignore the layout you asked for. The rule that governs the whole "
            "family is that a printed grid must not be a CSS grid, or a flexbox: "
            "neither takes part in WebKit page fragmentation, so break-inside: avoid "
            "is discarded without a word and a card comes off the printer in two "
            "halves. Read the top of print.css before changing any of it."
        ),
        [
            Component(
                slug="print-sheet",
                tag="c-n26.print.sheet",
                template="n26/print/sheet.html",
                summary=(
                    "The paper: page size, margins, and the geometry everything "
                    "else measures from."
                ),
                notes=(
                    "Exactly one per document. @page is a document-level rule with no "
                    "element to scope it to, so a second sheet's page size silently "
                    "wins for both. It publishes the printable area as custom "
                    "properties, which is what lets the grid derive a cell width that "
                    "cannot overflow the paper — v1 kept a hardcoded 204mm in step "
                    "with a 3mm margin by hand, two numbers for one fact. The sheet "
                    "renders at true physical size on screen as well, so the preview "
                    "is the artefact rather than an impression of it; that costs a "
                    "sideways scroll on a phone and is worth it. Its palette is "
                    "deliberately not the app's theme tokens — there is no dark mode "
                    "on a sheet of paper."
                ),
                parts=(
                    Part(
                        "c-n26.print.grid",
                        "n26/print/grid.html",
                        "Tiles items N-up as atomic inlines, so none can be cut by the "
                        "page fold.",
                    ),
                    Part(
                        "c-n26.print.card",
                        "n26/print/card.html",
                        "One unit that arrives whole: grid-cell width, optional fixed "
                        "height, footer on the bottom edge.",
                    ),
                    Part(
                        "c-n26.print.statline",
                        "n26/print/statline.html",
                        "Characteristics in the book's two-row layout, with Type "
                        "and XP filling the second row.",
                    ),
                    Part(
                        "c-n26.print.table",
                        "n26/print/table.html",
                        "A long table whose header repeats on every page and whose "
                        "rows never split.",
                    ),
                    Part(
                        "c-n26.print.weapons",
                        "n26/print/weapons.html",
                        "A card's weapon table: the model-card's naming rule, in "
                        "the print table's clothes.",
                    ),
                    Part(
                        "c-n26.print.columns",
                        "n26/print/columns.html",
                        "Side-by-side columns, filled server-side — never CSS "
                        "multicol, which WebKit collapses when printing.",
                    ),
                    Part(
                        "c-n26.print.column",
                        "n26/print/column.html",
                        "One column, optionally spreading its children down the full "
                        "height.",
                    ),
                    Part(
                        "c-n26.print.entry",
                        "n26/print/entry.html",
                        "A labelled value, beside or above; monolithic, so no engine "
                        "may split it.",
                    ),
                    Part(
                        "c-n26.print.field",
                        "n26/print/field.html",
                        "A box to write in by hand, with whatever is already known "
                        "printed inside.",
                    ),
                    Part(
                        "c-n26.print.break",
                        "n26/print/break.html",
                        "End the page here.",
                    ),
                ),
            ),
        ],
    ),
    Group(
        "Site chrome",
        (
            "The frame around an application rather than anything inside one: a "
            "bar across the top saying one thing, the navigation under it, and "
            "the footer at the bottom. Rebuilt from Gyrinx v1, which is where "
            "the shape of each comes from. They share one container, which is "
            "the least interesting and most load-bearing thing about them — "
            "three separate max-widths is how a logo ends up two pixels off the "
            "heading below it."
        ),
        [
            Component(
                slug="site-announcement",
                tag="c-n26.site.announcement",
                template="n26/site/announcement.html",
                summary="A bar across the top of the site, saying one thing.",
                needs=(ALPINE,),
                notes=(
                    "Above the nav rather than below it, because it is about the "
                    "site rather than the page, and a bar that pushes the whole "
                    "application down is harder to ignore than one tucked inside "
                    "it — which is the point of the thing. It does not remember "
                    "being dismissed, deliberately: persistence is a decision "
                    "only the application can make, and the two reasonable "
                    "answers pull opposite ways. A server that stores the "
                    "dismissal can also count it, which is what you want if the "
                    "bar is advertising something; a localStorage flag cannot be "
                    "counted but survives a logged-out visitor. on_dismiss is "
                    "where either goes. Tone sets the colours and the icon "
                    "together, because they say the same thing and a red bar "
                    "with no icon reads as an unexplained mistake."
                ),
            ),
            Component(
                slug="site-nav",
                tag="c-n26.site.nav",
                template="n26/site/nav/index.html",
                summary=(
                    "The bar across the top of every page, and the drawer behind "
                    "its burger."
                ),
                needs=(ALPINE, KIT_JS, FOCUS),
                notes=(
                    "The links are in the drawer and nowhere else, which is what "
                    "buys the bar its one good idea: the space beside the brand "
                    "belongs to the page, so every page can say its own name "
                    "there after a middle dot. A bar that held both had to choose, "
                    "and the page that most needed naming — a half-filled form, "
                    "whose title is the first thing to scroll away — was exactly "
                    "the page whose links then went missing. The burger is the "
                    "last thing in the bar, past the account menu with a hairline "
                    'between them — they are the bar\'s two "more" controls, and '
                    "side by side with nothing between them they read as one — "
                    "and the panel arrives from the right, the side its control "
                    "lives on. It is the same control at every width rather than "
                    "one that appears below md: a burger is only predictable if "
                    "you already know the window is narrow. Items stay the kit's c-ui.navbar.item "
                    "— a bare <a> its container styles, which is what lets one "
                    "list be drawn in the drawer and again in the noscript strip "
                    "under the bar. That strip is not decoration: Alpine builds "
                    "the drawer out of a <template>, so with no script the panel "
                    "does not exist and the links would be nowhere. What narrows "
                    "away is the wordmark, not the page: the mark beside it is "
                    "still a link home, and a word naming the site on every screen "
                    "of the site is the least of what a phone's bar can hold — so "
                    "the page's name, and the switcher that acts on it, survive to "
                    "the narrowest width. The colour scheme lives in the account "
                    "menu for the same reason: it is clicked once in a reader's "
                    "life, and a bar's one row of space is wanted by the page on "
                    "every screen. It is a segmented control of three there, not "
                    "three rows — three rows would carry the weight of the places "
                    "the menu leads to, and cost the panel half its height again "
                    "on a phone."
                ),
                parts=(
                    Part(
                        "c-n26.site.nav.gang",
                        "n26/site/nav/gang.html",
                        "One of the reader's own gangs, in the drawer.",
                    ),
                    Part(
                        "c-n26.site.nav.theme",
                        "n26/site/nav/theme.html",
                        "Light, dark or the machine's own setting, as one "
                        "segmented control in the account menu.",
                    ),
                ),
            ),
            Component(
                slug="site-edition-toggle",
                tag="c-n26.site.edition-toggle",
                template="n26/site/edition_toggle.html",
                summary=("Which edition you are in, and the way to the other."),
                notes=(
                    "A two-segment pill: the filled segment is the edition this "
                    "bar belongs to, the hollow one is a plain link to the "
                    "other's front page — nothing toggles in place, because "
                    "changing edition is going somewhere, and two links need no "
                    "script. Quiet on purpose: the filled half is a fact rather "
                    "than a control competing with the page, and the hollow half "
                    "only says it can be clicked when the pointer is on it. It "
                    "is drawn only where a reader can follow both links — both "
                    "editions want a signed-in account, so the classic bar's "
                    "copy asks for one before drawing the pill."
                ),
            ),
            Component(
                slug="site-footer",
                tag="c-n26.site.footer",
                template="n26/site/footer/index.html",
                summary=(
                    "The bottom of every page: columns of links, and the odd one out."
                ),
                notes=(
                    "Columns rather than a links prop taking a list, because "
                    "footers are where the odd one out lives — two columns of "
                    "tidy links and a third holding a picture. A data-driven "
                    "footer handles the two and grows an escape hatch for the "
                    "third, and the escape hatch is this. Three across on a wide "
                    "screen and one down on a phone, from the grid rather than "
                    "from anything the caller says, so a two-column footer and a "
                    "three-column one still line up with the nav. The Patreon "
                    "card carries .n26-img-tilt, the one piece of deliberate fun "
                    "on the page: it lifts and turns towards the pointer as if "
                    "it were a physical thing on the desk. The transform is on "
                    "the image and the hover on the link, so the target does not "
                    "move out from under the pointer, and anyone who has asked "
                    "for reduced motion gets the shadow without the tilt."
                ),
                parts=(
                    Part(
                        "c-n26.site.footer.column",
                        "n26/site/footer/column.html",
                        "One column: a heading, a list of links, or a picture "
                        "instead of one.",
                        required=True,
                    ),
                ),
            ),
        ],
    ),
    Group(
        "Views",
        (
            "Whole screens, assembled from everything above. Not pages — no "
            "chrome, no routing, just the part between the nav and the footer — "
            "because the questions a screen raises are not the ones a component "
            "raises. How much fits above the fold on a phone, whether two "
            "components repeat each other, where the submit button went: none "
            "of those can be answered by looking at either piece on its own."
        ),
        [
            Component(
                slug="view-gang-sheet",
                tag="c-n26.view.gang-sheet",
                template="n26/view/gang_sheet.html",
                summary="A gang, whole: what it is worth and who is in it.",
                needs=(ALPINE, KIT_JS, FOCUS),
                notes=(
                    "The order down the page is the order a reader asks: whose "
                    "gang and where am I, what is it called, what kind, what is it "
                    "worth, what are its standing facts, what can I do to it, what "
                    "is in the stash, who is in it. Everything above the fighters "
                    "is a header, small and over quickly, because every row of it "
                    "is a row of fighters you cannot see. Two action runs and not "
                    "one: hiring is what the screen is for and it is safe, "
                    "printing is a detour, deleting is irreversible — and one row "
                    "would sort them by nothing while putting a Delete in thumb "
                    "range of a Hire. The dropboard around Delete is not "
                    "decoration; it is the second deliberate click an irreversible "
                    "thing should cost. The cards are a CSS grid to three columns, "
                    "because a card holds a fixed amount of information: as the "
                    "screen widens the answer is more cards abreast, not one wide "
                    "column setting a statline's M and Sv a hand's width apart. "
                    "The switcher beside the name is a slot rather than something "
                    "the view builds: which other gangs there are is a question "
                    "about the reader, and this component knows about one gang. It "
                    "sits after the name and not before it, because the mark "
                    "before a title is inside the h1 and is read out as part of "
                    "the page's name — which a control must not be."
                ),
            ),
            Component(
                slug="view-model-edit",
                tag="c-n26.view.model-edit",
                template="n26/view/model_edit.html",
                summary="One model, whole: their card, editable, and the notes.",
                needs=(ALPINE, KIT_JS, FOCUS),
                notes=(
                    "The Edit face of a model's own page; Equip is the same "
                    "header's second tab, so the two screens read as one place. "
                    "Under the header, a grid that is one column on a phone: the "
                    "card first, in edit mode — the same card the sheet draws, "
                    "same structure and renderer, so the two screens cannot "
                    "disagree about what the model is — and the notes box after "
                    "it. Notes are a box of the grid rather than a section of "
                    "the card because they are a form: a card is read in "
                    "numbers, and a paragraph being written wants elbow room "
                    "beside it rather than a slot inside it. Save is the page's "
                    "only filled commit, which is why the card's own controls "
                    "are outlined: on a page that edits, the thing that ends the "
                    "form should be findable without reading any button's words. "
                    "The form arrives as a slot, fields and submit together, "
                    "because saving is the page's business and the gallery has "
                    "no database to save to. The skills are a square of the grid "
                    "beside the notes, because a list of things to tick is read "
                    "down a column and one stretched across the page would set a "
                    "set's name a hand's width from its own boxes. The "
                    "characteristics an owner sets "
                    "by hand sit under the grid, full width and in the same "
                    "columns the card's own strip draws: a strip squeezed into "
                    "half the page would wrap where the card's does not, and it "
                    "belongs below the card because it is read against it — "
                    "what is set shows there, marked as changed."
                ),
            ),
            Component(
                slug="view-dashboard",
                tag="c-n26.view.dashboard",
                template="n26/view/dashboard.html",
                summary="Where you land: your gangs, and what changed.",
                needs=(ALPINE, KIT_JS),
                notes=(
                    "Two things, in the order they matter: what you own, and what "
                    "has changed since you last looked. A dashboard that tries to "
                    "summarise everything is a page nobody reads twice. The "
                    "greeting states a fact rather than asking a question — no "
                    "prompt, no exclamation mark: someone came here to get on with "
                    "something, and a page that opens by asking how they are is "
                    "one they learn to scroll past. Founding a gang is the only "
                    "primary button on the screen, because everything else here is "
                    "a way to reach something that already exists. The gangs get no "
                    "heading of their own — they are what the page is — where the "
                    "changelog needs one, since a reader has to be told the list "
                    "has stopped being about them. The Patreon and Discord marks "
                    "sit in the same row as the buttons, quiet and at the height "
                    "of their text: the footer holds both already, but the footer "
                    "is a scroll away from the screen someone is actually on when "
                    "they go looking. They lead the row at width and follow the "
                    "buttons once it wraps, so the primary is never the second "
                    "thing on a phone."
                ),
            ),
            Component(
                slug="view-fighter-hire",
                tag="c-n26.view.fighter-hire",
                template="n26/view/fighter_hire.html",
                summary="Pick what a fighter is, one click at a time.",
                needs=(ALPINE, KIT_JS, COLLAPSE, FOCUS),
                notes=(
                    "Optimised for finding the profile and nothing else. "
                    "Everything above the list is there under protest, because "
                    "on a phone every row of chrome is a row of fighters you "
                    "cannot see — so the screen is a list, and nothing above it "
                    "asks a question the reader has not reached yet. Naming is "
                    "one of those questions: it is asked after the click, by "
                    "c-n26.hire-dialog, because a name field at the top is a "
                    "field answered once and then in the way, and blocking a "
                    "hire on it would slow the common case, which is buying "
                    "three Gangers and naming them once they have done "
                    "something worth naming. There is no submit button. Every "
                    "Hire in the list is this form's submit, carrying which "
                    "profile or which option was clicked, which is what the "
                    "row's `value` is for — and the form should not grow a "
                    "primary action of its own, because a Hire at the bottom of "
                    "a list of Hire buttons is a second answer to a question "
                    "already answered. A hire lands back here rather than on "
                    "the gang sheet, so the notice slot draws the confirmation "
                    "beside the list it was clicked in."
                ),
            ),
            Component(
                slug="view-create-gang",
                tag="c-n26.view.create-gang",
                template="n26/view/create_gang.html",
                summary="Found a gang: name it, say what it is, and start.",
                notes=(
                    "The library's form pattern, and the one the others should "
                    "follow: a heading, a line of help under it, fields in "
                    "titled groups, one primary action at the end. Every field "
                    "is c-ui.field over a kit control, so the label, the help "
                    "text and the error come from one place rather than being "
                    "rebuilt per screen. Two groups rather than one run of four, "
                    "split by required and optional — a reader can stop after "
                    "the first and have a gang, and saying that with a heading "
                    "is cheaper than saying it four times in four labels. "
                    "Required is marked with an asterisk and stated once at the "
                    "top; marking the optional ones instead would leave the "
                    "mandatory fields bare and teach the reader nothing. No "
                    "Cancel beside Create: leaving is what the back button is "
                    "for, and a button whose job is to discard what somebody "
                    "typed does not belong a thumb-width from the one that "
                    "keeps it. Blank starting credits means no limit, which is "
                    "the one place where leaving something out is a decision "
                    "rather than a deferral — so it is the one the help text "
                    "explains."
                ),
            ),
        ],
    ),
]


# Each component is declared inside its group, so stamp the group name back onto it
# rather than repeating it on every entry.
for _group in GROUPS:
    _group.components[:] = [
        replace(component, group=_group.name) for component in _group.components
    ]

COMPONENTS: list[Component] = [c for g in GROUPS for c in g.components]
BY_SLUG = {c.slug: c for c in COMPONENTS}


def get(slug: str) -> Component | None:
    return BY_SLUG.get(slug)
