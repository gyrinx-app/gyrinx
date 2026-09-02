"""The gallery's table of contents: what exists, how it is grouped, what it is for.

Props are never restated here — they are read from each component's own
``<c-vars>`` block at runtime (see :mod:`designsystem.introspect`). Internal
``impl.html`` templates get no entry: they have no public tag, and their props are
documented on the wrapper that forwards to them.
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
        in it. Handing the group its members' terms keeps that one predicate over
        data, rather than the group inspecting the DOM.
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
                    "The success variant is a local override of the kit's template, "
                    "so app.css must list .bg-green-700 alongside the other solid "
                    "fills for the shadow rule to reach it. A button that submits, "
                    "fetches over htmx or navigates goes busy on click — spinner, "
                    "hidden label, no second click — until the work ends; that comes "
                    "from n26/core/static/n26/busy.js and the [data-busy] rules in "
                    'app.css, and data-busy="off" on the button or its form opts a '
                    "control out."
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
                    'instead of as a popover. Set strategy="fixed" where the menu '
                    "sits inside something that scrolls, which otherwise cuts it off "
                    "at the box's edges."
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
                    "label. The first panel wins unless you set :default_tab. The "
                    "default variant's strip never wraps: below the sm breakpoint "
                    "the open tab stands alone with the rest behind a "
                    "quick-switcher. The segmented variant keeps the kit's own "
                    "single strip — .n26-card-tabs in app.css addresses its DOM "
                    "shape by position, so nothing may wrap it."
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
                    "A development tool rather than a UI primitive: drop it once and "
                    "it edits the tokens on <html>, so the page you are looking at is "
                    "the preview. It is mounted on every page of this gallery — the "
                    "paintbrush, bottom right. Nothing is stored: copy the CSS it "
                    "generates into your own stylesheet to keep a theme."
                ),
            ),
        ],
    ),
    Group(
        "Compositions",
        (
            "This project's own components, in templates/cotton/n26/ rather than the "
            "kit. Most are assembled from the primitives above and add no JavaScript "
            "of their own, driving the Alpine scope a kit component already provides."
        ),
        [
            Component(
                slug="icon",
                tag="c-n26.icon",
                template="n26/icon.html",
                summary="The whole icon set, from one named registry.",
                notes=(
                    "The drawings live in the registry at n26/core/icons.py as path "
                    "data alone — Heroicons v2 outline, 24x24, round caps, no fill — "
                    "and this component supplies everything else. Brand marks break "
                    "that uniformity, so the registry says which are solid fills and "
                    "which keep a canvas of their own. There is no colour prop: an "
                    "icon draws in currentColor. Stroke weight is a prop, weight being "
                    "a function of rendered size rather than of the drawing."
                ),
            ),
            Component(
                slug="search-bar",
                tag="c-n26.search-bar",
                template="n26/search_bar.html",
                summary="A search field, with its submit button beside it.",
                notes=(
                    "The field and its icon are one joined control: the wrapper owns "
                    "the border, radius and focus ring, and the field is a plain "
                    "<input> carrying the kit's own token classes — c-ui.input would "
                    "draw a second border inside this one. The submit button sits "
                    "outside that group. It is a real form, so it submits without "
                    "JavaScript."
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
                    "No state of its own: All, None and the per-row only are single "
                    "assignments into the checkbox group's values array, with the "
                    "dropdown's close() from the same scope chain. The group wraps the "
                    "whole dropdown rather than sitting in its panel, which is what "
                    "lets the trigger show a count while the panel is shut. Cancel "
                    "reverts to a snapshot taken when the panel opened."
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
                    "The numeric member of the menu family, beside filter-menu (many "
                    "of a set) and choice-menu (one of a set). Pass model_min and "
                    "model_max instead of model and it becomes a two-thumb range. The "
                    "trigger states the bound rather than the label, and swaps in a "
                    "word at either end where the number does not say what it means. "
                    "No OK or Cancel, unlike filter-menu — the list responds as you "
                    "drag. The slider underneath is c-n26.range-slider, not "
                    "c-ui.range: the kit's binds with x-modelable, which carries a "
                    "drag out to the caller but will not carry a programmatic change "
                    "back in, so Clear moves the model and leaves the filled track "
                    "behind."
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
                summary="A tab strip whose tabs are links, for a choice the server makes.",
                needs=(ALPINE, KIT_JS),
                notes=(
                    "These navigate — c-ui.tabs is the one that switches panels "
                    "already on the page — so the choice is a URL, linkable and in "
                    "the history. Only the current tab has been rendered, so a tab "
                    "carries no count. Drawn as a nav with aria-current rather than "
                    "role=tablist, which would promise arrow keys and a panel swapping "
                    "underneath. Built on c-n26.tab-strip, so it never wraps: below "
                    "the sm breakpoint the current tab stands alone with the rest "
                    "behind a quick-switcher, whose panel needs script — a noscript "
                    "strip repeats the same links flat."
                ),
            ),
            Component(
                slug="tab-strip",
                tag="c-n26.tab-strip",
                template="n26/tab_strip.html",
                summary="The never-wrap skeleton behind a tab strip.",
                notes=(
                    "Two containers switched at the sm breakpoint — the window's "
                    "width, not the box it sits in: every tab in the full slot from "
                    "sm up, the current tab plus a c-n26.quick-switcher in the "
                    "narrow slot below it. Owns no tab markup and no state; the "
                    "caller fills both slots and wires the switcher. The rule under "
                    "each strip comes from the tabs' own 2px bottom borders plus a "
                    "trailing spacer — give every slotted tab a border-b-2 or the "
                    "line breaks under it."
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
                    "that most readers never open. The fetch happens on this "
                    "component's own init, so the call site chooses the moment "
                    "by placement — inside a template x-if it fetches when the "
                    "template first instantiates. With follows set, a change of "
                    "address fetches again and the fragment already drawn stays "
                    "up until the new one lands."
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
                    "Everything a reader steers with sits in one sticky box — the "
                    "filters slot, the readout and the section strip — so the page "
                    "sets a single offset rather than each band having to be told "
                    "how tall the ones above it are. The section strip is two "
                    "blocks of markup switched at the sm breakpoint: every section "
                    "as a tab above it, the section on screen standing alone with "
                    "the rest behind a chevron below it. Items register their own "
                    "facets on init, so the counts, the readout and each group's "
                    "visibility are one array read three ways; the readout counts "
                    "what the section strip is showing rather than everything "
                    "registered. An empty category hides itself rather than leaving "
                    "a header behind, and a search forces every group open without "
                    "overwriting what the reader had collapsed. The controls are "
                    "not built in: they go in a slot and write to this component's "
                    "state by name."
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
                        "One row: name, price, rarity and its buttons. One line at "
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
                    "c-n26.collection-picker with hiring's vocabulary on it: it "
                    "sets the noun, drops the filters that mean nothing here "
                    "(nothing you hire has a trade-points price or an Exclusive "
                    "flag), and adds the composition limit, which the shell has "
                    "no business knowing about. That limit is stated and never "
                    "enforced — nothing blocks on a note, and refusing belongs "
                    "at the operation boundary. A row's options are behind its "
                    "disclosure only."
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
                summary="A dialog the server decided to open, and the form inside it.",
                needs=(ALPINE,),
                notes=(
                    "The panel every server-decided dialog is built from, and "
                    "the only dialog here whose open state is server state: the "
                    "page draws it when the URL says so, which is what makes it "
                    "a link, makes it survive a reload, and makes the click that "
                    "opened it work with scripting off. It is a native <dialog "
                    "open> — a panel in the flow of the page, promoted to a real "
                    "modal by showModal() where Alpine is there to call it, "
                    "which brings the top layer, the backdrop, Escape and a "
                    "focus trap with it. Dismissing navigates rather than "
                    "hiding: closing in place would leave the page on screen "
                    "while the URL still named what the dialog was asking about."
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
                    "c-n26.dialog with hiring's questions in it. The profile "
                    "and its options are hidden fields rather than controls: "
                    "they were picked on the listing that was clicked, and the "
                    "way to change them is to go back to it. The price in the "
                    "lead is what the listing was configured to, not the "
                    "advertised one — an option ticked upstairs is charged "
                    "here, so it is named here. The box under the price decides "
                    "whether a price typed over the quote also becomes the "
                    "fighter's rating; it starts ticked, and is drawn whether "
                    "or not the price has been typed over."
                ),
            ),
            Component(
                slug="owned-dialog",
                tag="c-n26.owned-dialog",
                template="n26/owned_dialog.html",
                summary=(
                    "Confirm a sale, a move, a refund or a removal of "
                    "something the gang owns — or ask which accessory to "
                    "fit to a weapon, whether to take one off, or which "
                    "alternatives it is taken with."
                ),
                needs=(ALPINE,),
                notes=(
                    "One panel for the owned questions: sell, move, refund, "
                    "remove, fit an accessory, take one off, and change what "
                    "a thing was bought with. Each states what a reader "
                    "cannot work out from the page — a sale states its "
                    "arithmetic, a move that it charges nothing, a removal "
                    "that the money stays spent, a refund what was paid, a "
                    "detach that the fighter still holds it. The stash is a "
                    "button and the roster a select, and only the clicked "
                    "submit is sent, which is the whole of how the view tells "
                    "those two apart. Selling something with a part bolted to "
                    "it is two sales at two prices, so each option carries "
                    "its own figure rather than the lead carrying one. "
                    "Changing what a thing was bought with draws the buying "
                    "row's own controls rather than a second set, with the "
                    "loader deciding which starts picked."
                ),
            ),
            Component(
                slug="owned-actions",
                tag="c-n26.owned-actions",
                template="n26/owned_actions.html",
                summary=(
                    "Sell and the rest of what can happen to one copy the model holds."
                ),
                needs=(ALPINE,),
                notes=(
                    "The pair the listing draws next to something owned: Sell "
                    "out in the open, everything else behind a chevron. Which "
                    "acts those are is the structure's word, so an act added "
                    "there appears here with nothing edited. size is sm on a "
                    "listing row and xs on a model card. A line with nothing "
                    "to click draws nothing. Only a screen holding the "
                    "update's hosts may set :htmx — see "
                    "n26/includes/equip_hosts.html."
                ),
            ),
            Component(
                slug="owned-lines",
                tag="c-n26.owned-lines",
                template="n26/owned_lines.html",
                summary="What a model is already carrying, and what can happen to it.",
                notes=(
                    "The inside of an equip row for something the fighter "
                    "already has, drawn the way a card draws the same lines — "
                    "the thing, what it contributed, its parts indented under "
                    "it. The weapon's own firing line is not among them: it "
                    "*is* the weapon. Which act is red comes from the structure "
                    "rather than from this component, so an act added there "
                    "appears here in the right colour with nothing edited. A "
                    "part offers no move — Operation.move refuses an assignment "
                    "with a parent, so the control would be a click that cannot "
                    "work. Every control is a link to a real address: the "
                    "dialog is a server state, and the catalogue's own form "
                    "already wraps every row on the page, so a form in here "
                    "would be a form inside a form."
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
                    "being the obvious one. All / None and the per-row only belong "
                    "to the checkboxes and are absent here; what is left is the list "
                    "and OK / Cancel. The trigger shows the chosen label rather than "
                    "a count. For a menu that commits the moment you pick, use the "
                    "kit's own c-ui.menu."
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
                    "components are built from. Colour is a prop rather than a class: "
                    'class="text-muted" against a default of text-accent is two '
                    "utilities of equal specificity, and which wins depends on the "
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
                    "One prop takes the colour whether it is a literal or a theme "
                    "name: a hex is frozen, while a token resolves through var() and "
                    "follows a theme change. It has to be a style attribute — "
                    "Tailwind reads class names as literal strings, so a class built "
                    "from a variable is one it never emits, while every --color-* "
                    "variable is emitted for exactly this lookup. With no colour it "
                    "draws nothing at all rather than reserving space. Aria-hidden "
                    "unless given a label."
                ),
            ),
            Component(
                slug="color-link",
                tag="c-n26.color-link",
                template="n26/color_link.html",
                summary="Text with a colour swatch in front of it.",
                notes=(
                    "c-n26.link with a c-n26.color-swatch in a leading slot, outside "
                    "the underline; the sibling of c-n26.flair-link, which puts a "
                    "badge in the trailing one. Somewhere that already has an anchor "
                    "of its own draws the swatch directly instead."
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
                    "trailing slot sits outside the underline. The badge is sized in "
                    "em rather than px, so one component works in a table cell and in "
                    "a heading with no size prop, and the sizing is applied to "
                    "descendant svg because the artwork belongs to the caller."
                ),
                parts=(
                    Part(
                        "c-n26.flair.staff",
                        "n26/flair/staff.html",
                        "The pixel-art staff badge, from the platform's own badge "
                        "asset. Fixed palette.",
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
                        "A gang type's own artwork, sanitised on the way out. "
                        "Content rather than a drawing we ship, so it is the one "
                        "badge that may be absent and the one that is untrusted.",
                    ),
                ),
            ),
            Component(
                slug="user-link",
                tag="c-n26.user-link",
                template="n26/user_link.html",
                summary="A person's name with the badge they actually hold.",
                notes=(
                    "c-n26.flair-link with the badge derived rather than passed in: "
                    "which mark someone shows comes from their live supporter "
                    "standing and staff flag against the platform's registry, plus "
                    "their own pick among what that leaves them. Drawing it from "
                    "is_staff instead gives every supporter no badge at all. There "
                    "is no label prop — the wording comes from the registry, so a "
                    "new tier needs no edition change."
                ),
            ),
            Component(
                slug="page-header",
                tag="c-n26.page-header",
                template="n26/page_header.html",
                summary="What this page is, at the top of it.",
                notes=(
                    "One scale for a page's name, so screens cannot disagree "
                    "about it. The trail, the lead and the page's controls are "
                    "all optional and compose around it. The lead takes one name "
                    "for either shape — a string for a few words, or a slot for "
                    "markup — since `.strip` is a method on a string as much as "
                    "on slot content."
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
                    "behind hover or keyboard focus, CSS-only, with the "
                    "browser's title as the touch fallback. Views fill the "
                    "addresses in — the compiler knows no URLs, so a sentence "
                    "whose subject has no page renders as plain words."
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
                    "For prose a template writes; c-n26.rich-text is for prose a "
                    "database stores. Both go through the same .rich-text rules, so "
                    "a page's own copy and a description typed into the editor are "
                    "the same typography. Write plain HTML inside, not components — "
                    "the styling reaches the tags by descendant selector. Capped at "
                    "max-w-prose unless something else already constrains the width."
                ),
            ),
            Component(
                slug="form-actions",
                tag="c-n26.form-actions",
                template="n26/form_actions.html",
                summary="How a form ends: the way out, then the act.",
                notes=(
                    "Every form's footer. The order and the alignment are not "
                    "props: the way out is left of the act, the pair is "
                    "right-aligned, and the act is last. Cancel is an href and "
                    "never a submit; a form with nowhere to go back to passes no "
                    "cancel_url and gets no cancel at all. It is ghost, so only "
                    "the act carries a colour. c-n26.form-page draws its footer "
                    "with this rather than repeating it, so a page form and a "
                    "dialog end the same way."
                ),
            ),
            Component(
                slug="form-page",
                tag="c-n26.form-page",
                template="n26/form_page.html",
                summary="The wrapper every form screen shares.",
                notes=(
                    "The measure, the vertical rhythm, the header and the footer "
                    "live here; a form view supplies its fields and nothing about "
                    "the frame. The footer is optional — a form whose submit "
                    "lives elsewhere passes no submit_label and gets none, which "
                    "is how the hire screen avoids a Create button under a list "
                    "of Hire buttons. It draws c-n26.form-actions for the footer "
                    "and c-n26.page-header for the heading, handing on everything "
                    "that header takes; the header's `actions` arrives here as "
                    "`header_actions`, this wrapper's own `actions` being the "
                    "extra control beside the submit. Every slot is declared, "
                    "which is load-bearing: a slot this wrapper did not declare "
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
                    "The unit a form is built from, separated by space and a "
                    "heading rather than boxed — c-ui.card is there for the cases "
                    "that genuinely want a container. The title renders as an h2, "
                    "so a form of these has a real document outline rather than a "
                    "run of bold text. A description is better absent than "
                    "restating the labels underneath it."
                ),
            ),
            Component(
                slug="colour-picker",
                tag="c-n26.colour-picker",
                template="n26/colour_picker.html",
                summary="Pick a colour from the palette, or none.",
                notes=(
                    "Each radio is sr-only with its swatch styled through "
                    "peer-checked, so it stays a real input in a real label: "
                    "keyboard-reachable, arrow keys between options, submitting "
                    "with no JavaScript, and reading its colour's name aloud. "
                    "None is the first swatch and a real value rather than the "
                    "absence of one, so a picker can be returned to nothing once "
                    "touched and a form coming back after an error can tell 'no "
                    "colour' from 'not chosen yet'. The swatch classes are a "
                    "lookup — Tailwind reads class names as literal strings and "
                    "never emits one built from a variable. The grid is auto-fill."
                ),
            ),
            Component(
                slug="filter-select",
                tag="c-n26.filter-select",
                template="n26/filter_select.html",
                summary="A long select, with a box to search it.",
                needs=(ALPINE,),
                notes=(
                    "Wraps a real <select> rather than replacing it: the select "
                    "handed in is what posts, untouched, and the panel sets "
                    "selectedIndex on it, so with scripting off you get the plain "
                    "select, working. The kit's c-ui.combobox cannot serve here — "
                    "its name is an Alpine binding and its options are a "
                    "<template>, so unscripted it posts nothing, and the options "
                    "it renders carry their label text as their value. Short "
                    "lists are left alone, counted in the browser from the "
                    "options already on the page."
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
                    "A sibling of c-n26.checkbox-card rather than a mode of it: "
                    "that card dims and inerts its body while unticked, which "
                    "here would grey out every card but the one picked. A card "
                    "cannot own its state either — one-of-many is the browser's "
                    "rule over a shared name. Selected state is has-[:checked] on "
                    "the label rather than script, so the page is right before "
                    "anything runs and stays right if nothing ever does. The grid "
                    "is auto-fill off a track floor."
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
                    "The pick screen, minus the page. Every group shares one "
                    "input name, so the browser keeps a single selection across "
                    "the lot: the headings are how the list is read, not separate "
                    "questions. Nothing here knows what is being picked — the "
                    "view has already flattened it into groups and options, which "
                    "is what lets a skill, a pick and an affiliation share "
                    "a screen. What to say when the list is empty is the "
                    "caller's; why it is empty is something the page knows and "
                    "this does not."
                ),
            ),
            Component(
                slug="choice-picks",
                tag="c-n26.choice-picks",
                template="n26/choice_picks.html",
                summary="A list of things to choose and unchoose one at a time.",
                notes=(
                    "A flat list of options, one per row: the name, an "
                    "optional muted remark, and a button. Options the choice "
                    "already holds show a red Remove — and a green Add again, "
                    "where the slot type allows repeats and there is room; "
                    "the rest show a green Add. When the choice is full, only "
                    "what it holds is "
                    "listed. Plain submit buttons and no script: the page "
                    "wraps this in its own form, and only the clicked button "
                    "is sent, so the view knows which option to add or take "
                    "back. Use c-n26.choice-offer for a single-pick choice; "
                    "use this where a choice holds several picks."
                ),
            ),
            Component(
                slug="pick-list",
                tag="c-n26.pick-list",
                template="n26/pick_list/index.html",
                summary="What a thing has, and a searchable way to add to it.",
                notes=(
                    "For a library too long to scan — every subtype, every "
                    "special rule — without becoming a different control: the "
                    "held things are ticked boxes, and a button opens the rest "
                    "as a c-n26.quick-switcher panel, the shape a reader has "
                    "already met. Click a row and its box appears above, "
                    "ticked; clear a box and the row is offered again. Nothing "
                    "reloads, because every box was already on the page — the "
                    "panel only ticks them, so it adds no input of its own and "
                    "no value can arrive that nobody chose. Its rows report a "
                    "key rather than their words, because two rows can read "
                    "alike and mean different rows. With no script the addable "
                    "boxes are put back by a noscript rule and the panel is "
                    "cloaked, so what is left is one plain list of every "
                    "option that works. Save is disabled until the ticked set "
                    "differs from the one the page opened with: the actions "
                    "slot renders inside this component's scope, which is what "
                    'lets a caller bind ::disabled="!dirty" on its own button. '
                    "Left alone the groups are drawn as one run of boxes, since "
                    "a heading over each would be the same word down the page; "
                    "`grouped` draws each under its own name and tier where the "
                    "groups are the point, as c-n26.tick-list does."
                ),
                parts=(
                    Part(
                        "c-n26.pick-list.box",
                        "n26/pick_list/box.html",
                        "One option as a box to tick — the same row whether the "
                        "thing is held or is one the panel offers, so the two "
                        "runs cannot come to look different. Binds to `picked` "
                        "above it in the Alpine scope, which is what lets the "
                        "panel tick a box and the list read what is ticked.",
                    ),
                ),
            ),
            Component(
                slug="tick-list",
                tag="c-n26.tick-list",
                template="n26/tick_list.html",
                summary="A list of things to tick, grouped under its headings.",
                notes=(
                    "The structure c-n26.choice-offer draws, ticked any number of "
                    "times rather than once. Checkboxes and no script: what "
                    "arrives ticked is what the server said, so the form is right "
                    "before anything runs. An option a rule grants is drawn ticked "
                    "and fixed, saying what grants it — and a fixed box submits "
                    "nothing, so whatever applies the difference must leave "
                    "granted things out of it rather than read their silence as a "
                    "clearing. An empty offer draws nothing; why it is empty is "
                    "the page's to say."
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
                    "so a click on a control inside one toggles the card. This one "
                    "confines the toggle to its header and keeps the body live. "
                    "While unticked the body is dimmed and inert — and inert stops "
                    "interaction and focus but not submission, so an input that "
                    "must not submit while the card is unticked binds :disabled to "
                    "the `picked` the card puts in scope."
                ),
            ),
            Component(
                slug="divider",
                tag="c-n26.divider",
                template="n26/divider.html",
                summary="A rule with words in it, saying why it separates.",
                notes=(
                    'A rule that states the relationship it marks — "or …" makes '
                    "the block below an alternative to the one above, not a "
                    "continuation. The lines are flex spans rather than a styled "
                    "<hr>, so the label sits in the rule without a background "
                    "patch over a line, which breaks the moment the page behind it "
                    "is not one flat colour. With nothing to say it degrades to a "
                    "plain rule."
                ),
            ),
            Component(
                slug="coming-soon",
                tag="c-n26.coming-soon",
                template="n26/coming_soon.html",
                summary="A section that exists but is not built yet.",
                notes=(
                    "Not an empty state: a table's empty slot says the reader can "
                    "fix this by searching for something else, and this says there "
                    "is nothing to fix. Deliberately plain — no illustration, no "
                    "button, nothing actionable — and body copy at the normal size."
                ),
            ),
            Component(
                slug="count-badge",
                tag="c-n26.count-badge",
                template="n26/count_badge.html",
                summary="How many are waiting, as a small filled pill.",
                notes=(
                    "Pass the count as :count, because written "
                    'count="{{ n }}" it arrives the string "0", which is true, '
                    "and something with nothing waiting gets a badge. Placement "
                    "is the caller's — the same pill rides a button's corner "
                    "and sits in a line of text. The number is never announced; "
                    "`label` is what decides whether anything is, and it is "
                    "wrong to give one inside a control whose aria-label "
                    "already carries the count."
                ),
            ),
            Component(
                slug="statline",
                tag="c-n26.statline",
                template="n26/statline/index.html",
                summary="A set of characteristics as a compact strip.",
                notes=(
                    "One component for two jobs: build_statline() in "
                    "n26/core/render.py serves a fighter profile and a weapon "
                    "profile alike. The divider and the tint come from "
                    "is_first_of_group and is_highlighted on StatlineTypeStat, so "
                    "where a row breaks is content rather than a decision in the "
                    "template. Header and cells are separate parts emitting cells "
                    "rather than rows, which is what lets the weapon table put a "
                    "name column in front of the same stats. Not built on "
                    "c-ui.table, whose descendant-variant styling outranks any "
                    "class on a cell and so cannot be adjusted from the call site. "
                    "The editor is a fourth template rather than a mode on this "
                    "one, reusing the header unchanged so the columns, the divider "
                    "and the tint match the card being edited."
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
                        "The <td> cells. Marks a modified value and says what "
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
                slug="record-table",
                tag="c-n26.record-table",
                template="n26/record_table/index.html",
                summary="A searchable list of one kind of thing, each row clickable.",
                needs=(ALPINE, KIT_JS),
                parts=(
                    Part(
                        "c-n26.record-table.gang-row",
                        "n26/record_table/gang_row.html",
                        "One gang: name, type, what it is worth, and its actions.",
                    ),
                    Part(
                        "c-n26.record-table.campaign-row",
                        "n26/record_table/campaign_row.html",
                        "One campaign: its name, who arbitrates it, and — where the reader runs it — Edit.",
                    ),
                ),
                notes=(
                    "A list of grid rows rather than a real table: four columns do "
                    "not fit 390px, and the usual escape — display:block on the "
                    "cells — throws away the alignment that made it a table. The "
                    "whole row is one link by way of exactly one real <a>, on the "
                    "name, whose ::after is stretched over the row; wrapping the "
                    "row in an anchor would put two buttons inside a link, and a "
                    "click handler on a div would lose the URL, middle-click and "
                    "keyboard focus. The buttons are lifted above that stretch in "
                    "the row's own markup. Type is a plain select rather than "
                    "c-n26.filter-menu, one choice needing no Apply and Cancel."
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
                    "A list, not a feed: nothing loads more. Summaries clamp at "
                    "two lines, the full text being a click away. The way through "
                    "to everything is in the heading rather than a last row, which "
                    "would be the one row in the list that does not behave like "
                    "the list. The title opens the full entry; links in a rich-text "
                    "summary keep their own destinations. The entry component "
                    "sanitises its body rather than relying on each caller."
                ),
            ),
            Component(
                slug="tally",
                tag="c-n26.tally",
                template="n26/tally.html",
                summary="Figures that add up, label left and value right.",
                notes=(
                    "A row states its own emphasis and its own rule rather "
                    "than the component reading them off its position: a tally "
                    "may hold more than one total, as the overspend "
                    "confirmation does, and a component that emboldened its "
                    "last row could not say so. Drawn by the Visit Trading "
                    "Post card and by that confirmation, which is what stops "
                    "the two showing one arithmetic two ways."
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
                    "Four money figures in the order they answer questions about "
                    "each other — rating is what the gang fields, credits what is "
                    "left, stash what the gang owns and nobody carries, wealth the "
                    "three added up — so reading left to right is reading the sum. "
                    "Trade Points lead, behind a rule: they are not money and not "
                    "part of that sum, being what the gang may spend at a trading "
                    "post until the trip ends, so they must not sit inside a run "
                    "of figures a reader adds up. It takes the whole GangSheet "
                    "rather than a handful of numbers, since positional integers "
                    "in the same units are that many chances to swap two and never "
                    "find out. A definition list, not a table. Real tooltips here "
                    "where c-n26.statline uses a title attribute: cells drawn once "
                    "on a page can afford what a cell drawn hundreds of times "
                    "cannot."
                ),
            ),
            Component(
                slug="gang-figures",
                tag="c-n26.gang-figures",
                template="n26/gang_figures/index.html",
                summary=(
                    "The numbers a spending decision is made against: the "
                    "roster count beside the wealth strip."
                ),
                needs=(ALPINE, KIT_JS),
                notes=(
                    "Drawn on the gang sheet, above the hire list's rows and in "
                    "the far corner of the model screens' header, wherever a "
                    "spending decision is being made. The count is "
                    "c-n26.roster-summary rather than a figure cell, so it is a "
                    "control; the money is fenced off behind a rule. Takes the "
                    "tally rather than a number, and reads the count off it — a "
                    "call site cannot tell it a count the breakdown disagrees "
                    "with."
                ),
            ),
            Component(
                slug="roster-summary",
                tag="c-n26.roster-summary",
                template="n26/roster_summary.html",
                summary="How many models, and the arithmetic behind the count.",
                needs=(ALPINE, KIT_JS),
                notes=(
                    "The count is the trigger: the number of models the gang "
                    "fields, opening two readings of that roster in two tabs — "
                    "which profiles at which ranks and how many of each, and "
                    "every model with its pinned rating, totalled. Both keep the "
                    "roster's own order, pets after their keepers. The ratings "
                    "total is the sum of the models listed, which the gang's own "
                    "rating figure need not equal — a gang can carry worth no "
                    "single model does. Usually drawn through "
                    "c-n26.gang-figures rather than on its own."
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
                    "Labelled facts where the value is also the way to edit it, "
                    "and one control however much it holds — three skill sets are "
                    "one choice, and three buttons would say there were three "
                    "questions. The rhythm belongs to the container, so hiding a "
                    "row behind a permission check cannot leave a gap. Flex wrap "
                    "rather than a grid, which would align every value to the "
                    "widest label on the sheet. The control keeps its border "
                    "rather than going ghost, which on a phone would look "
                    "clickable to nobody."
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
                    "and its counters sit in one c-n26.detail-list at one rhythm. "
                    "Settled and open are the same control leading to the same "
                    "page — clicking a settled slot is how you change your mind. "
                    "An open one is never marked as missing: nothing counts it and "
                    "nothing refuses to proceed without it. A line with no address "
                    "— a card built from a profile's default equipment has real "
                    "offers and nothing to choose against — draws as text with an "
                    "em dash rather than a button that goes nowhere."
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
                    "A card among the fighters' cards, taking the roster grid's "
                    "first slot, so moving something between a card and the stash "
                    "is a move between two like things on one screen. Items are "
                    "grouped by kind, run on and wrap rather than taking a row "
                    "each, with each rating against its own item and the total on "
                    "the header line. An empty stash still draws the card — a slot "
                    "that came and went with the contents would move every fighter "
                    "after it around the grid. Drawn through "
                    "c-n26.assignable-lines, so something a modifier put there "
                    "carries the mark it would on a card."
                ),
            ),
            Component(
                slug="model-header",
                tag="c-n26.model-header",
                template="n26/model_header.html",
                summary="One model's name and rank, and the tabs of their screens.",
                needs=(ALPINE, FOCUS),
                notes=(
                    "The one header every per-model screen wears, so Edit and "
                    "Equip read as tabs of one place. The title is the model's "
                    "name plain, not the verb — the tab strip already says which "
                    "face is open. The strip is built by the model_screen_tabs tag "
                    "rather than passed in, so a screen cannot invent one of its "
                    "own; adding a screen to a model is one edit to "
                    "n26.core.navigation."
                ),
            ),
            Component(
                slug="model-card",
                tag="c-n26.model-card",
                template="n26/model_card/index.html",
                summary="A fighter's card: characteristics, weapons, skills, gear, XP.",
                notes=(
                    "Renders a n26.render.ModelCard, which the backend assembles "
                    "in one query — the template computes nothing, and nothing "
                    "here changes a statline or a weapon. Every line carries its "
                    "provenance: a modified characteristic says what changed it, "
                    "and a granted skill or trait is marked apart from a bought "
                    "one. A choice draws as its own row whether or not it has been "
                    "settled, an open one being information rather than an error. "
                    "Every control is drawn from an href on the structure, so a "
                    "print sheet and a hire preview draw none of them without "
                    "asking — the counter lines included, which draw as settled "
                    "numbers wherever nobody may move them. XP is both a line "
                    "and a cell in the statline: the cell carries the target "
                    "beside it, the line is where the number is changed. A stored model's card is three segmented tabs — Card, "
                    "then Lore and Notes, the sections a player writes; a card with "
                    "no id (a preview, a picker option) draws the body plain. "
                    "Two modes: gang, the sheet's — dense, with the open "
                    "questions shown but their buttons held back — and edit, the "
                    "model's own page, where those buttons come out outlined, "
                    "the Gear and Weapons rows carry the way to the Equip tab, "
                    "and kit the model holds offers the same Sell and more-menu "
                    "the listing does, at xs so they sit with Choose and Equip. A "
                    "mode-only region is a wrap in c-n26.model-card.mode, not a "
                    "flag threaded through every region between it and the call "
                    "site."
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
                        "c-n26.model-card.body",
                        "n26/model_card/body.html",
                        "The rules' half of the card — statline, rows, weapon "
                        "table — split out so the tabbed card and the tabless "
                        "preview draw the same thing.",
                        required=True,
                    ),
                    Part(
                        "c-n26.model-card.prose",
                        "n26/model_card/prose.html",
                        "A written section of a card: the Lore and Notes panels.",
                    ),
                    Part(
                        "c-n26.counter-controls",
                        "n26/counter_controls.html",
                        "The pair that moves one counter a step either way. "
                        "Drawn only where the line carries an address, and "
                        "without the minus at zero.",
                    ),
                ),
            ),
            Component(
                slug="picture-box",
                tag="c-n26.picture-box",
                template="n26/picture_box.html",
                summary="An edit page's picture section: the picture, its removal, and its upload.",
                needs=("n26/imagecrop.js", "Cropper.js"),
                notes=(
                    "Two forms posting act=picture to the same address: a "
                    "one-click Remove drawn only while a picture is stored, "
                    "and an upload through <c-n26.picture-input> whose "
                    "confirmed crop saves at once. The wrapper is what "
                    "n26/imagecrop.js redraws in place after a background "
                    "save, so the page the action renders must carry the "
                    "same box. The crop and max props are str() of the "
                    "server's own constants (n26/core/images.py) — a call "
                    "site hands them through from its view rather than "
                    "spelling the shape itself."
                ),
            ),
            Component(
                slug="picture-input",
                tag="c-n26.picture-input",
                template="n26/picture_input.html",
                summary="A picture upload whose crop is chosen in a dialog.",
                needs=("n26/imagecrop.js", "Cropper.js"),
                notes=(
                    "A plain file input and the dialog its crop is chosen in. "
                    "Picking a file opens the dialog: a rectangle of the "
                    "declared shape — 4:5 for a model, 16:9 for a gang — over "
                    "the picture, opening at the largest window the picture "
                    "holds, dragged and resized by its handles (Cropper.js, "
                    "vendored beside Alpine). Confirming stages the chosen "
                    "window on the input, so the form's own save sends "
                    "exactly what the dialog showed; leaving the dialog any "
                    "other way clears the pick. Without the scripts the "
                    "input is an ordinary file box, and either way the "
                    "server centre-crops every upload to the same shape "
                    "(n26/core/images.py): the dialog chooses, it is not "
                    "trusted. With submit_on_crop the save runs from the "
                    "open dialog, and a refusal is drawn into the alert the "
                    "dialog carries for it — the script reads it off the "
                    "data-message hook that n26/includes/messages.html "
                    "stamps on every alert, so a page that renders its "
                    "messages some other way would leave that alert empty."
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
                    "Two views of the same content: pass a bound field for the "
                    "editor with an Edit / Preview switch, or just a value for the "
                    "rendered article. Wrapped in c-ui.field, so label, description "
                    "and errors work as they do on c-ui.input. Rendering always "
                    "goes through safe_rich_text — editor output is user input "
                    "round-tripped through a database, so it is sanitised on the "
                    "way out rather than trusted. You must render {{ form.media }} "
                    "once on the page or no editor appears; the widget is only a "
                    "textarea until that script runs."
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
                    "far end. :surface puts it on a tinted strip, for a secondary "
                    "bar inside a card rather than at the top of a page."
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
                    "Two shapes: a lone chevron, or a ghost button group with the "
                    "linked thing in front of it. With no label the chevron is the "
                    "only child of the group and rounds both its ends. The panel "
                    "is the kit's dropdown, so the outside click and the placement "
                    "are its — which means the panel is built from a <template> "
                    "and does not exist without script, so a <noscript> strip "
                    "draws the same destinations flat. Filtering narrows rows "
                    "already on the page and never asks the server; the rows "
                    "register their own text, so the count behind the empty "
                    "message and the list itself are one array. Focus lands in the "
                    "filter box on open and never leaves it: Down and Up move a "
                    "highlight over the rows the filter is showing, Enter goes to "
                    "the highlighted row, and Escape empties a filter with "
                    "something in it before a second Escape closes the panel. The "
                    "highlight is a tint plus aria-activedescendant rather than "
                    "real focus, which would take the caret out of the box. Rows "
                    "carry their own bottom rule rather than the list dividing "
                    "between them, since a divide counts hidden rows and would "
                    "draw a rule under nothing. The panel is kept inside the "
                    "window by a CSS width cap and a margin the kit's placement "
                    "never touches. A hotkey letter turns on a page-wide ⌥⇧ chord "
                    "that opens the panel with the caret in the filter, named in "
                    "the chevron's tooltip and aria-keyshortcuts; the application "
                    "spends ⌥⇧F on the bar's switcher and ⌥⇧R on the one beside a "
                    "page's own heading."
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
                        "One state of the page rather than one destination: a "
                        "button that reports its own label, for a switcher whose "
                        "alternatives are states rather than places.",
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
            "Paper: fixed physical sizes in millimetres and a page fold you do not "
            "control. A printed grid must not be a CSS grid or a flexbox — neither "
            "takes part in WebKit page fragmentation, so break-inside: avoid is "
            "discarded without a word and a card comes off the printer in two "
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
                    "cannot overflow the paper. The sheet renders at true physical "
                    "size on screen as well, so the preview is the artefact rather "
                    "than an impression of it — which means a sideways scroll on a "
                    "phone. Its palette is deliberately not the app's theme tokens; "
                    "there is no dark mode on a sheet of paper."
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
            "the footer at the bottom. They share one container — three separate "
            "max-widths is how a logo ends up two pixels off the heading below it."
        ),
        [
            Component(
                slug="site-announcement",
                tag="c-n26.site.announcement",
                template="n26/site/announcement.html",
                summary="A bar across the top of the site, saying one thing.",
                needs=(ALPINE,),
                notes=(
                    "Sits above the nav rather than inside it, so it pushes the "
                    "whole application down. It does not remember being "
                    "dismissed: persistence is a decision only the application "
                    "can make, and on_dismiss is where a server call or a "
                    "localStorage flag goes. Tone sets the colours and the icon "
                    "together."
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
                    "The links live in the drawer and nowhere else, which is what "
                    "leaves the space beside the brand to the page: every page "
                    "says its own name there after a middle dot. The burger is the "
                    "last thing in the bar, past the account menu with a hairline "
                    "between them, and the drawer arrives from the right — the "
                    "same control at every width rather than one appearing below "
                    "md. Items stay the kit's c-ui.navbar.item, a bare <a> its "
                    "container styles, which is what lets one list be drawn in the "
                    "drawer and again in the noscript strip under the bar. That "
                    "strip is load-bearing: Alpine builds the drawer out of a "
                    "<template>, so with no script the panel does not exist and "
                    "the links would be nowhere. What narrows away is the "
                    "wordmark, not the page's name or the switcher beside it; the "
                    "mark is still a link home. The colour scheme is a segmented "
                    "control of three in the account menu, where it takes no room "
                    "the page wants. `unread` puts a count on the corner of the "
                    "account button and into its accessible name; pass it as "
                    ':unread, because written unread="{{ count }}" it arrives '
                    'the string "0", which is true, and an empty inbox gets a '
                    "badge."
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
                    "other's front page. Nothing toggles in place — changing "
                    "edition is going somewhere, and two links need no script. It "
                    "is drawn only where a reader can follow both links; both "
                    "editions want a signed-in account, so the classic bar's copy "
                    "asks for one before drawing the pill."
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
                    "Columns rather than a links prop taking a list, because a "
                    "footer is where the odd one out lives — two columns of tidy "
                    "links and a third holding a picture. Three across on a wide "
                    "screen and one down on a phone, from the grid rather than "
                    "from anything the caller says, so a two-column footer and a "
                    "three-column one still line up with the nav. The Patreon "
                    "card carries .n26-img-tilt: the transform is on the image "
                    "and the hover on the link, so the target does not move out "
                    "from under the pointer, and anyone who has asked for reduced "
                    "motion gets the shadow without the tilt."
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
            "chrome, no routing, just the part between the nav and the footer. "
            "How much fits above the fold on a phone, and whether two components "
            "repeat each other, cannot be seen from either piece on its own."
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
                    "is a header, small and over quickly. Two action runs rather "
                    "than one, so Delete is not in thumb range of Hire, and it "
                    "takes a second deliberate click. The cards are a CSS grid to "
                    "three columns — as the screen widens the answer is more cards "
                    "abreast, not one wide column setting a statline's M and Sv a "
                    "hand's width apart. The switcher beside the name is a slot "
                    "rather than something the view builds, since which other "
                    "gangs there are is a question about the reader. It sits after "
                    "the name because the mark before a title is inside the h1 and "
                    "is read out as part of the page's name, which a control must "
                    "not be."
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
                    "card in edit mode — the same card, structure and renderer "
                    "the gang sheet draws — then the notes box, with the skills "
                    "beside it. The form arrives as a slot, fields and submit "
                    "together, because saving is the page's business and the "
                    "gallery has no database to save to. Save is the page's only "
                    "filled commit, which is why the card's own controls are "
                    "outlined. The characteristics an owner sets by hand sit "
                    "under the grid, full width and in the same columns the "
                    "card's own strip draws, since what is set shows there "
                    "marked as changed."
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
                    "has changed since you last looked. The greeting states a fact "
                    "rather than asking a question. Founding a gang is the only "
                    "primary button on the screen, everything else being a way to "
                    "reach something that already exists. The gangs get no heading "
                    "of their own — they are what the page is — where the "
                    "changelog needs one. The Patreon and Discord marks lead the "
                    "button row at width and follow the buttons once it wraps, so "
                    "the primary is never the second thing on a phone."
                ),
            ),
            Component(
                slug="view-fighter-hire",
                tag="c-n26.view.fighter-hire",
                template="n26/view/fighter_hire.html",
                summary="Pick what a fighter is, one click at a time.",
                needs=(ALPINE, KIT_JS, COLLAPSE, FOCUS),
                notes=(
                    "A list, with as little above it as the screen can manage: "
                    "nothing up there asks a question the reader has not reached "
                    "yet. Naming is one of those questions, asked after the click "
                    "by c-n26.hire-dialog. There is no submit button — every Hire "
                    "in the list is this form's submit, carrying which profile or "
                    "which option was clicked, which is what the row's `value` is "
                    "for. A hire lands back here rather than on the gang sheet, so "
                    "the notice slot draws the confirmation beside the list it was "
                    "clicked in."
                ),
            ),
            Component(
                slug="view-create-gang",
                tag="c-n26.view.create-gang",
                template="n26/view/create_gang.html",
                summary="Found a gang: name it, say what it is, and start.",
                notes=(
                    "The form pattern the other screens should follow: a heading, "
                    "a line of help under it, fields in titled groups, one primary "
                    "action at the end. Every field is c-ui.field over a kit "
                    "control, so the label, the help text and the error come from "
                    "one place. Two groups split by required and optional, so a "
                    "reader can stop after the first and have a gang; required is "
                    "marked with an asterisk and stated once at the top. No Cancel "
                    "beside Create — leaving is what the back button is for. Blank "
                    "starting credits means no limit, which is why that is the "
                    "field the help text explains."
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
