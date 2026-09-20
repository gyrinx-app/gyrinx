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
    """Usage guidance and constraints that the prop list does not show."""

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
        "Controls that run an action on click: buttons, menus and the message composer.",
        [
            Component(
                slug="button",
                tag="c-ui.button",
                template="button.html",
                summary=(
                    "The standard action control: a <button>, or an <a> when href "
                    "is set."
                ),
                notes=(
                    "Set href to navigate. Omit it and you get a <button "
                    'type="button">; pass type="submit" when it submits a form. '
                    "There is no disabled prop. A plain disabled attribute disables "
                    "the button, but a link has no disabled state and stays "
                    "clickable. A control "
                    "that submits, fetches over htmx or navigates shows a spinner "
                    "and blocks a second click until the work ends, from "
                    'n26/core/static/n26/busy.js. data-busy="off" on the control or '
                    'its form opts out; a plain link opts in with data-busy="link". '
                    "Inside a data-busy-replaces container, a link takes the "
                    "container's appearance and replaces the selected content with "
                    "its data-busy-wait template."
                ),
            ),
            Component(
                slug="share",
                tag="c-n26.share",
                template="n26/share.html",
                summary=(
                    "A share control that opens the device's share sheet, or copies "
                    "the link."
                ),
                needs=(ALPINE,),
                notes=(
                    "url is the href of a real link, so the control still navigates "
                    "with no script. Alpine takes the click and calls "
                    "navigator.share where the browser has it, and "
                    "navigator.clipboard.writeText otherwise, then shows the message "
                    "for a few seconds. The clipboard API needs a secure origin, so "
                    "over plain http, or when the write fails, the browser follows "
                    "the link instead. The padding holds the control to 20px so it "
                    "fits on a breadcrumb line; changing size requires re-tuning the padding."
                ),
            ),
            Component(
                slug="dropdown",
                tag="c-ui.dropdown",
                template="dropdown/index.html",
                summary=("A menu of actions opened from a trigger."),
                needs=(ALPINE, KIT_JS, FOCUS),
                notes=(
                    "Pass either a trigger slot or trigger_text; with neither, the "
                    'component renders a visible error. Set strategy="fixed" where '
                    "the menu sits inside a scrolling ancestor that would clip it, "
                    "and load n26/menu-position.js on the page shell or opening "
                    'that menu throws. Set overflow="hidden" when the panel\'s own '
                    "content scrolls, because two nested overflow-y-auto boxes "
                    "break touch scrolling on a phone. :collapsible renders the "
                    "items inline below the md breakpoint instead of as a popover. "
                    "class is not declared, so a caller class lands in attrs and "
                    "the positioning wrapper loses it."
                ),
                parts=(
                    Part(
                        "c-ui.dropdown.item",
                        "dropdown/item.html",
                        (
                            "An action in the menu: an <a> when href is set, "
                            "otherwise a <button>."
                        ),
                    ),
                    Part(
                        "c-ui.dropdown.group",
                        "dropdown/group.html",
                        "A labelled cluster of items in the menu.",
                    ),
                    Part(
                        "c-ui.dropdown.separator",
                        "dropdown/separator.html",
                        "A dividing rule between items.",
                    ),
                ),
            ),
            Component(
                slug="composer",
                tag="c-ui.composer",
                template="composer.html",
                summary=(
                    "A chat-style box: an auto-growing textarea with a row of actions."
                ),
                needs=(ALPINE,),
                notes=(
                    "There is no default slot; the initial text is the value prop. "
                    "The leading and trailing slots hold the action controls, and "
                    "that line renders only when at least one is filled. The shell "
                    "carries the focus ring through focus-within, so focusing "
                    "anything inside rings the whole box. The textarea grows to "
                    "320px and then scrolls."
                ),
            ),
        ],
    ),
    Group(
        "Forms",
        (
            "Input controls, each wrapped in the c-ui.field label, description and "
            "error scaffold."
        ),
        [
            Component(
                slug="field",
                tag="c-ui.field",
                template="field.html",
                summary=(
                    "The label, description and error scaffold the other form "
                    "components are built on."
                ),
                notes=(
                    "Use it directly to wrap a control the kit does not ship. "
                    "Errors render through c-ui.error, so error, form and name must "
                    "all be set, and the error string's own content is ignored. "
                    'variant="toggle" stacks the label and description on the left '
                    "with the control pushed right."
                ),
            ),
            Component(
                slug="input",
                tag="c-ui.input",
                template="input/index.html",
                summary="A text input, with optional leading and trailing addons.",
                notes=(
                    "left_addon and right_addon are positioned absolutely and take "
                    "pointer-events-none, so they hold icons, units and currency "
                    "marks rather than controls. Everything not named in c-vars "
                    "passes through to the <input>, so type, size, placeholder and "
                    "disabled all work on the outer tag."
                ),
            ),
            Component(
                slug="textarea",
                tag="c-ui.textarea",
                template="textarea/index.html",
                summary="A multi-line text input, at a fixed height or auto-growing.",
                notes=(
                    "size sets the padding and type size; height is a separate "
                    "scale setting a fixed height, from h-16 at xs to h-80 at 2xl. "
                    ":autoresize turns that height into a floor and needs Alpine. "
                    ':resizable="False" removes the drag handle.'
                ),
            ),
            Component(
                slug="select",
                tag="c-ui.select",
                template="select/index.html",
                summary="A list of options: the native <select>, or a styled listbox.",
                needs=(ALPINE, KIT_JS),
                notes=(
                    'variant="native" is the default, needs no JavaScript and gets '
                    'the platform picker. variant="listbox" routes to c-ui.menu, '
                    "and the slot must then hold c-ui.menu.item rather than "
                    "c-ui.select.option. A native multiple select marks its chosen "
                    "options with option:checked, because the kit's filled-option "
                    "style hides which are selected."
                ),
                parts=(
                    Part(
                        "c-ui.select.native",
                        "select/native.html",
                        (
                            "The plain <select>, usable on its own; put option or "
                            "optgroup elements in its slot."
                        ),
                    ),
                    Part(
                        "c-ui.select.option",
                        "select/option.html",
                        "An <option> for the native variant.",
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
                    "Use it directly where you need search or per-option "
                    'descriptions; c-ui.select variant="listbox" renders this same '
                    "component. Usually you write only the items, because the "
                    "trigger and content wrappers render themselves when those "
                    "slots are omitted. It submits through a hidden input and "
                    "dispatches select-change with {value, label}."
                ),
                parts=(
                    Part(
                        "c-ui.menu.item",
                        "menu/item.html",
                        (
                            "An option in the panel, carrying its value, label, "
                            "description and group."
                        ),
                        required=True,
                    ),
                    Part(
                        "c-ui.menu.trigger",
                        "menu/trigger.html",
                        (
                            "The closed-state button. Rendered automatically when "
                            "the slot is omitted."
                        ),
                    ),
                    Part(
                        "c-ui.menu.content",
                        "menu/content.html",
                        (
                            "The popover panel holding the options. Rendered "
                            "automatically when the slot is omitted."
                        ),
                    ),
                    Part(
                        "c-ui.menu.group",
                        "menu/group.html",
                        "A labelled cluster of options in the panel.",
                    ),
                    Part(
                        "c-ui.menu.search",
                        "menu/search.html",
                        (
                            "A sticky filter box at the top of the panel, focused "
                            "when the menu opens."
                        ),
                    ),
                ),
            ),
            Component(
                slug="combobox",
                tag="c-ui.combobox",
                template="combobox/index.html",
                summary=(
                    "Multi-select entry, showing each chosen value as a removable tag."
                ),
                needs=(ALPINE, KIT_JS),
                notes=(
                    "Options come from the :options prop rather than a slot. "
                    ":writable lets a reader enter values that were not in the "
                    "list, and :searchable adds a filter box. It submits through a "
                    "hidden <select multiple>. Alpine builds the whole control, so "
                    "use c-n26.filter-select where a picker has to work with "
                    "scripting off."
                ),
            ),
            Component(
                slug="checkbox",
                tag="c-ui.checkbox.group",
                template="checkbox/group/index.html",
                summary=(
                    "A multiple-choice group, as a stacked list, a segmented "
                    "control or cards."
                ),
                needs=(ALPINE, KIT_JS),
                notes=(
                    "c-ui.checkbox works only inside the group: it reads its state "
                    "and its styling from the group's Alpine scope. Set the "
                    "initially ticked boxes on the group with :values, not on each "
                    "box with :checked."
                ),
                parts=(
                    Part(
                        "c-ui.checkbox",
                        "checkbox/index.html",
                        "A checkbox and its label. Must sit inside c-ui.checkbox.group.",
                        required=True,
                    ),
                ),
            ),
            Component(
                slug="radio",
                tag="c-ui.radio.group",
                template="radio/group/index.html",
                summary=(
                    "A single-choice group, as a stacked list, a segmented control, "
                    "pills or cards."
                ),
                needs=(ALPINE, KIT_JS),
                notes=(
                    "c-ui.radio works only inside the group, and the selected value "
                    "is set on the group with :value. Arrow keys move between "
                    "options. Unlike the checkbox group, this one also offers a "
                    "pill variant."
                ),
                parts=(
                    Part(
                        "c-ui.radio",
                        "radio/index.html",
                        "A radio and its label. Must sit inside c-ui.radio.group.",
                        required=True,
                    ),
                ),
            ),
            Component(
                slug="switch",
                tag="c-ui.switch",
                template="switch/index.html",
                summary=(
                    "An on/off toggle, standalone or as a settings line with the "
                    "label on the left."
                ),
                needs=(ALPINE, KIT_JS),
                notes=(
                    ":inline uses the field's toggle variant: the label sits left "
                    "and the switch is pushed to the far right of a full-width "
                    "line. For a toggle sized to its own label, as a toolbar needs, "
                    "use c-n26.toggle."
                ),
            ),
            Component(
                slug="range",
                tag="c-ui.range",
                template="range/index.html",
                summary=(
                    "A slider over a numeric range, with the live value beside or "
                    "below the track."
                ),
                needs=(ALPINE,),
                notes=(
                    "value is the starting position, which the wrapper passes to "
                    "the implementation as initial. The value is bound with "
                    "x-modelable, which carries a drag out to the caller but does "
                    "not take a programmatic change back in. Use c-n26.range-slider "
                    "where code outside the slider has to move the thumb."
                ),
            ),
            Component(
                slug="datepicker",
                tag="c-ui.datepicker",
                template="datepicker/index.html",
                summary=(
                    "A date field that opens a calendar: one date, a range, or several."
                ),
                needs=(ALPINE, KIT_JS),
                notes=(
                    "It wraps c-ui.calendar in a popover and owns form submission "
                    "and value_format. In range mode it submits name['from'] and "
                    "name['to'] unless fromName and toName are given."
                ),
            ),
            Component(
                slug="calendar",
                tag="c-ui.calendar",
                template="calendar.html",
                summary="The month grid on its own, with day, month and year views.",
                needs=(ALPINE, KIT_JS),
                notes=(
                    "Usable inline, not only inside the datepicker. Hidden inputs, "
                    "and so form submission, appear only once name (or fromName and "
                    "toName) is passed; the datepicker wrapper otherwise owns "
                    "serialising. It is x-modelable, so x-model works on it, and it "
                    "also emits a change event."
                ),
            ),
            Component(
                slug="label",
                tag="c-ui.label",
                template="label.html",
                summary="The caption for a control, with an optional badge beside it.",
                notes=(
                    'The slot is the caption, not the control. Set for="<control-id>" '
                    "to associate the label with its control. A control placed in "
                    "the slot sits on the caption line beside the badge."
                ),
            ),
            Component(
                slug="description",
                tag="c-ui.description",
                template="description.html",
                summary="Muted helper text under a label or heading.",
                notes=(
                    "It declares no props of its own. class merges with the muted "
                    "defaults through attrs rather than replacing them."
                ),
            ),
            Component(
                slug="error",
                tag="c-ui.error",
                template="error.html",
                summary=(
                    "A validation message, from a string or from a Django form's "
                    "errors."
                ),
                notes=(
                    "It resolves message first, then the form's errors for name, "
                    'then the slot, so the slot is only a fallback. name="__all__" '
                    "renders non-field errors; any other name is looked up in "
                    "form.errors. It renders nothing when all three are empty, so "
                    "it is safe to leave in place unconditionally."
                ),
            ),
        ],
    ),
    Group(
        "Data display",
        (
            "Read-only presentation: surfaces, tables, status pills, avatars and "
            "progress indicators."
        ),
        [
            Component(
                slug="card",
                tag="c-ui.card",
                template="card.html",
                summary="A surface panel, with an optional header band above its body.",
                notes=(
                    "Setting title, subheading or the header slot switches it to "
                    'the two-part layout with a divider. Use padding="none" for '
                    "flush content such as a table or an accordion. "
                    'variant="outline" drops the fill and shadow for a panel that '
                    "sits flat on the page background."
                ),
            ),
            Component(
                slug="table",
                tag="c-ui.table",
                template="table.html",
                summary="Styling and horizontal overflow for a plain HTML table.",
                notes=(
                    "Write ordinary thead, tbody, tr, th and td inside; the "
                    "component styles its descendants. There is no JavaScript, no "
                    "sorting and no pagination, so compose it with c-ui.pagination. "
                    "Because the styling reaches cells by descendant selector, a "
                    "class on a cell cannot win against it."
                ),
            ),
            Component(
                slug="badge",
                tag="c-ui.badge",
                template="badge.html",
                summary="A compact pill for a status, category or count.",
                notes=(
                    "pill and solid are both values of variant, so they cannot be "
                    'combined. inset takes edge names (inset="top bottom") and '
                    "pulls the pill tight against surrounding text with a negative "
                    "margin on those edges. Setting href renders it as a link."
                ),
            ),
            Component(
                slug="avatar",
                tag="c-ui.avatar",
                template="avatar/index.html",
                summary=(
                    "A user image, falling back to initials and then to a silhouette."
                ),
                needs=(ALPINE,),
                notes=(
                    "It falls back in that order: src, then initials, then the "
                    'silhouette. color="auto" hashes the initials so one person '
                    "always draws the same colour. Only the inner span is clipped "
                    "to the circle, so content in the default slot, which is where "
                    "a status dot goes, is not cut off."
                ),
                parts=(
                    Part(
                        "c-ui.avatar.group",
                        "avatar/group.html",
                        "Overlaps a run of avatars, each with a ring around it.",
                    ),
                ),
            ),
            Component(
                slug="progress",
                tag="c-ui.progress",
                template="progress.html",
                summary="A determinate progress bar.",
                notes=(
                    "No JavaScript: :value is rendered server-side. bar_class "
                    "replaces the bar colour outright where the palette in color "
                    "has nothing suitable."
                ),
            ),
            Component(
                slug="spinner",
                tag="c-ui.spinner",
                template="spinner.html",
                summary="An indeterminate loading spinner.",
                notes=(
                    'color="current" takes the surrounding text colour, which is '
                    "what a spinner inside a button needs."
                ),
            ),
        ],
    ),
    Group(
        "Feedback",
        (
            "Messages about an outcome or a state: inline alerts, event-raised toasts "
            "and hover labels."
        ),
        [
            Component(
                slug="alert",
                tag="c-ui.alert",
                template="alert.html",
                summary="An inline message box for status, feedback or errors.",
                needs=(ALPINE,),
                notes=(
                    "variant sets the tone and its icon together; appearance picks "
                    "soft, solid or outline. Alpine is needed only for "
                    ":dismissible, so a static alert is plain markup. Pass "
                    ':icon="False" to drop the icon.'
                ),
            ),
            Component(
                slug="toast",
                tag="c-ui.toast.container",
                template="toast/container.html",
                summary=(
                    "Transient notifications, raised from anywhere by a window event."
                ),
                needs=(ALPINE,),
                notes=(
                    "There is no c-ui.toast: drop this container once in your base "
                    "layout. It registers the $store.toasts Alpine store and "
                    "renders a stack in each corner. Raise one with "
                    "$dispatch('toast', {variant, title, message}); anything passed "
                    "there overrides the container's props for that toast, and "
                    'duration="0" makes it stay until it is dismissed.'
                ),
            ),
            Component(
                slug="tooltip",
                tag="c-ui.tooltip",
                template="tooltip.html",
                summary="A small label shown on hover or focus.",
                needs=(ALPINE,),
                notes=(
                    "The default slot is the trigger and content is the bubble. It "
                    "teleports to <body> and positions in document coordinates, so "
                    "overflow on an ancestor cannot clip it, and it flips when it "
                    "does not fit. :delay is a hover-intent open delay in "
                    "milliseconds. Each tooltip is its own Alpine component, so use "
                    "a title attribute where a page draws hundreds of the same "
                    "cell."
                ),
            ),
        ],
    ),
    Group(
        "Navigation",
        (
            "Link sets that move a reader between pages: top bars, tab strips, "
            "sidebars, trails and page links."
        ),
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
                    "The default slot and actions are copied into the mobile menu, "
                    "so write them once; the mobile slot holds content only that "
                    "menu shows. variant styles the desktop items alone. :drawer "
                    "opens the mobile menu as a slide-over rather than an inline "
                    "collapse, which also needs the Alpine focus plugin."
                ),
                parts=(
                    Part(
                        "c-ui.navbar.item",
                        "navbar/item.html",
                        (
                            "A link in the bar, styled by the navbar's variant "
                            "through descendant selectors."
                        ),
                        required=True,
                    ),
                ),
            ),
            Component(
                slug="nav",
                tag="c-ui.nav",
                template="nav/index.html",
                summary="A horizontal strip of underline tabs linking to other pages.",
                notes=(
                    "These are real links rather than in-page state: use c-ui.tabs "
                    "to switch panels already on the page. Items are structural, "
                    "and the container styles them by descendant selector keyed on "
                    "the .is-current marker."
                ),
                parts=(
                    Part(
                        "c-ui.nav.item",
                        "nav/item.html",
                        "A tab link, marked by :current and carrying an optional badge.",
                        required=True,
                    ),
                ),
            ),
            Component(
                slug="navlist",
                tag="c-ui.navlist",
                template="navlist/index.html",
                summary=(
                    "A vertical sidebar navigation, with collapsible grouped sections."
                ),
                needs=(ALPINE, COLLAPSE),
                notes=(
                    ":persist_scroll restores the scroll position across page "
                    "loads, but only when the navlist is its own scroll container, "
                    "so give it a max height and overflow-y-auto. It restores only "
                    "after arriving from a link inside the same navlist, and keys "
                    'the stored position on scroll_key. variant="sidebar" draws an '
                    "accent rail instead of filled current items."
                ),
                parts=(
                    Part(
                        "c-ui.navlist.item",
                        "navlist/item.html",
                        (
                            "A sidebar link, marked by :current and carrying an "
                            "optional badge."
                        ),
                        required=True,
                    ),
                    Part(
                        "c-ui.navlist.group",
                        "navlist/group.html",
                        "A headed section of items, optionally collapsible.",
                    ),
                ),
            ),
            Component(
                slug="breadcrumbs",
                tag="c-ui.breadcrumbs",
                template="breadcrumbs/index.html",
                summary="A trail of links back up the hierarchy.",
                notes=(
                    'With no separator slot the "/" is drawn in CSS and needs no '
                    "JavaScript. Supply that slot and Alpine clones its content "
                    "between items, switching the CSS separator off so the two do "
                    "not double up."
                ),
                parts=(
                    Part(
                        "c-ui.breadcrumbs.item",
                        "breadcrumbs/item.html",
                        "A crumb in the trail: an <a>, or plain text when :current.",
                        required=True,
                    ),
                ),
            ),
            Component(
                slug="pagination",
                tag="c-ui.pagination",
                template="pagination/index.html",
                summary="Page links, generated from a Django Page or composed by hand.",
                notes=(
                    "Pass :page_obj and it renders the previous link, elided page "
                    "numbers and the next link by itself, with param naming the "
                    "query parameter it writes. The slot is used only when page_obj "
                    "is None, which is the escape hatch for cursor pagination and "
                    "other non-Page sources."
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
                        "The previous-page chevron.",
                    ),
                    Part(
                        "c-ui.pagination.next",
                        "pagination/next.html",
                        "The next-page chevron.",
                    ),
                    Part(
                        "c-ui.pagination.ellipsis",
                        "pagination/ellipsis.html",
                        "The gap marker between elided page numbers.",
                    ),
                ),
            ),
            Component(
                slug="scrollspy",
                tag="c-ui.scrollspy",
                template="scrollspy.html",
                summary="Marks the navigation item for whichever section is on screen.",
                needs=(ALPINE,),
                notes=(
                    "Wrap the navigation, not the content. It tracks the ids in the "
                    'nav\'s own a[href^="#"] links, so the sections need only a '
                    "matching id anywhere in the layout, and [data-spy-section] "
                    "covers a section with no link. Pair it with spy= on c-ui.nav "
                    "or c-ui.navlist items. The scroll container is detected "
                    "automatically; root is a CSS-selector escape hatch for the "
                    "cases detection cannot resolve."
                ),
            ),
        ],
    ),
    Group(
        "Disclosure",
        (
            "Show and hide content already in the document: tab panels, accordions and "
            "single collapses."
        ),
        [
            Component(
                slug="tabs",
                tag="c-ui.tabs",
                template="tabs/index.html",
                summary=(
                    "In-page panels, with a tab bar generated from the panels "
                    "themselves."
                ),
                needs=(ALPINE, KIT_JS),
                notes=(
                    "Write only the panels: each registers itself and its name "
                    "becomes its button label. The first panel is open unless "
                    ":default_tab names another exactly, and a name matching "
                    "nothing leaves every panel hidden once Alpine runs. param "
                    "copies the open tab into the query string, so nested strips on "
                    "one page must leave it empty. The default variant draws "
                    "through c-n26.tab-strip and never wraps: below the sm "
                    "breakpoint, three or more tabs collapse to the open one plus a "
                    "quick-switcher. The segmented variant keeps the kit's single "
                    "strip, which .n26-card-tabs in app.css selects by position, so "
                    "nothing may wrap it."
                ),
                parts=(
                    Part(
                        "c-ui.tabs.tab",
                        "tabs/tab.html",
                        (
                            "A panel. name is both its identity and its label on "
                            "the strip."
                        ),
                        required=True,
                    ),
                ),
            ),
            Component(
                slug="accordion",
                tag="c-ui.accordion",
                template="accordion/index.html",
                summary="Stacked expandable sections, one open at a time or several.",
                needs=(ALPINE, KIT_JS),
                notes=(
                    'type="single" allows one open section; any other value allows '
                    "several. Sections are flush, so put padding on the item and "
                    "compose insets at the call site."
                ),
                parts=(
                    Part(
                        "c-ui.accordion.item",
                        "accordion/item.html",
                        "An expandable section. Must sit inside c-ui.accordion.",
                        required=True,
                    ),
                ),
            ),
            Component(
                slug="collapse",
                tag="c-ui.collapse",
                template="collapse.html",
                summary="A single show and hide toggle with an animated body.",
                needs=(ALPINE, COLLAPSE),
                notes=(
                    "Use it for one disclosure and c-ui.accordion for a set of "
                    "them. trigger_text or the trigger slot draws the control, and "
                    ":expanded starts it open."
                ),
            ),
        ],
    ),
    Group(
        "Overlays",
        (
            "Panels drawn above the page: centred modals, edge drawers and floating "
            "popovers."
        ),
        [
            Component(
                slug="dialog",
                tag="c-ui.dialog",
                template="dialog/index.html",
                summary="A centred modal with header, body and footer slots.",
                needs=(ALPINE, KIT_JS),
                notes=(
                    "It teleports the overlay to <body>, and a close button "
                    "always renders. Note the spelling: :dismissable here, but "
                    ":dismissible on c-ui.drawer. Its open state is client "
                    "state, so use c-n26.dialog where the open state comes from "
                    "the server."
                ),
                parts=(
                    Part(
                        "c-ui.dialog.title",
                        "dialog/title.html",
                        "The accessible title. Must sit inside the dialog.",
                    ),
                    Part(
                        "c-ui.dialog.description",
                        "dialog/description.html",
                        "The accessible description for the dialog.",
                    ),
                ),
            ),
            Component(
                slug="drawer",
                tag="c-ui.drawer",
                template="drawer.html",
                summary="A panel that slides in from any edge of the window.",
                needs=(ALPINE, FOCUS),
                notes=(
                    "The default slot is the trigger and content is the body. The "
                    "root is display:contents, so the trigger sits in your layout "
                    "as though the drawer were not there; open it with "
                    '@click="drawerOpen = true", or drive the open state from a '
                    "parent with x-model, which x-modelable exposes. It traps focus "
                    "and locks page scroll while open, so it needs the Alpine focus "
                    "plugin."
                ),
            ),
            Component(
                slug="popover",
                tag="c-ui.popover",
                template="popover.html",
                summary="A floating panel on click or hover, holding any content.",
                needs=(ALPINE, KIT_JS),
                notes=(
                    'open_on="hover" honours open_delay and close_delay so a quick '
                    "pass does not open it. trigger_text renders a button with its "
                    "expanded state, panel connection and keyboard focus handling. "
                    "Use the trigger slot when the caller owns the trigger. Unlike "
                    "c-ui.tooltip, the panel can hold interactive content. class "
                    "styles the panel, not the root."
                ),
            ),
        ],
    ),
    Group(
        "Theming",
        ("Controls that switch the page's colour scheme and edit its theme tokens."),
        [
            Component(
                slug="mode-toggle",
                tag="c-ui.mode-toggle",
                template="mode_toggle/index.html",
                summary=(
                    "A control for switching between light, dark and system colour "
                    "schemes."
                ),
                needs=(ALPINE,),
                notes=(
                    "Pair it with c-ui.mode-toggle.head in <head>, with the same "
                    "storage_key and default, or the page paints the wrong theme "
                    "before Alpine boots. It sets the dark class on <html>, stores "
                    "the choice, follows the OS in system mode and syncs across "
                    'tabs. variant="headless" hands the scope to the call site so '
                    "it can draw its own control, which is what "
                    "c-n26.site.nav.theme does."
                ),
                parts=(
                    Part(
                        "c-ui.mode-toggle.head",
                        "mode_toggle/head.html",
                        (
                            "The blocking <head> script that applies the stored "
                            "scheme before first paint."
                        ),
                        required=True,
                    ),
                ),
            ),
            Component(
                slug="theme-builder-widget",
                tag="c-ui.theme-builder-widget",
                template="theme_builder_widget.html",
                summary=(
                    "A floating development tool for editing theme tokens live, "
                    "with CSS export."
                ),
                needs=(ALPINE, KIT_JS),
                notes=(
                    "Drop it once on a page. It writes the tokens onto <html>, so "
                    "the page you are looking at is the preview and stays "
                    "scrollable and interactive. The working theme is saved to "
                    "localStorage under storage_key unless :persist is off; to keep "
                    "a theme, copy the :root and .dark block it generates into your "
                    "own stylesheet. It is mounted on every page of this gallery, "
                    "at the bottom right."
                ),
            ),
        ],
    ),
    Group(
        "Compositions",
        (
            "This project's own components, in n26/core/templates/cotton/n26/, "
            "mostly assembled from the kit primitives above."
        ),
        [
            Component(
                slug="icon",
                tag="c-n26.icon",
                template="n26/icon.html",
                summary="A Lucide or brand icon, inlined as SVG.",
                notes=(
                    "name is required, and must be a canonical Lucide name or "
                    "github, discord or patreon; an unknown name raises and the "
                    "page does not render. There is no colour prop: a line drawing "
                    "takes currentColor and its size comes from a class, while the "
                    "brand marks are filled and ignore stroke_width. Raise "
                    "stroke_width as the rendered size falls, since an icon at "
                    "size-3 needs 2 or more. Pass label where the icon carries "
                    "meaning that no adjacent text does."
                ),
            ),
            Component(
                slug="search-bar",
                tag="c-n26.search-bar",
                template="n26/search_bar.html",
                summary=(
                    "A search field with its submit button, as a GET form or a live "
                    "filter."
                ),
                notes=(
                    "By default it is a real form and submits with no JavaScript. "
                    ":live binds x-model to the parent Alpine field named by model, "
                    "and that parent must own the state. Set :nested inside an "
                    "existing form: a browser discards a nested <form> tag and "
                    "reparents its children, which stops the field and the button "
                    "being one control. A live bar with no action, or a live nested "
                    "bar, captures Enter so it cannot submit the surrounding form. "
                    "A live bar with an action does not. The input id is "
                    "search-<name>, so two bars sharing a name on one page collide."
                ),
            ),
            Component(
                slug="filter-menu",
                tag="c-n26.filter-menu",
                template="n26/filter_menu.html",
                summary=(
                    "A dropdown of checkboxes that applies a named set of values."
                ),
                needs=(ALPINE, KIT_JS, FOCUS),
                notes=(
                    "OK dispatches filter-apply on the window with name and values, "
                    "and a parent must listen or the ticks do nothing; name must "
                    "match that listener and any filter-reset. With :select_all, an "
                    "empty :selected becomes every option on init, so the menu "
                    "cannot open on none. Cancel restores the snapshot taken when "
                    "the panel opened, not the last applied set. The checkbox group "
                    "wraps the whole dropdown rather than sitting in the panel, so "
                    "the closed trigger can show a count."
                ),
            ),
            Component(
                slug="range-menu",
                tag="c-n26.range-menu",
                template="n26/range_menu.html",
                summary=("A dropdown holding a slider that sets a bound on a number."),
                needs=(ALPINE, KIT_JS),
                notes=(
                    "model, model_min and model_max are Alpine names in an "
                    "ancestor scope, not numbers. Pass model_min and model_max "
                    "together for a two-thumb range; if either is empty the "
                    "single-thumb path runs. Unlike c-n26.filter-menu there is "
                    "no OK or Cancel, because the list responds as the reader "
                    "drags. The trigger states the bound rather than the label, "
                    "and at_min_label and at_max_label replace the figure at "
                    "either end where the number alone is not clear."
                ),
                parts=(
                    Part(
                        "c-n26.range-slider",
                        "n26/range_slider.html",
                        (
                            "The one or two native range inputs overlaid on a "
                            "shared track, used instead of c-ui.range because its "
                            "thumb has to be movable from outside."
                        ),
                    ),
                ),
            ),
            Component(
                slug="tab-links",
                tag="c-n26.tab-links",
                template="n26/tab_links.html",
                summary="A tab strip whose tabs are links to whole pages.",
                needs=(ALPINE, KIT_JS),
                notes=(
                    "Use it where the server renders the choice, so it is a URL, "
                    "linkable and in the history; c-ui.tabs is the one that "
                    "switches panels already on the page. Every tab in :tabs needs "
                    "label, href and current, and exactly one must be current. The "
                    "linked pages must be side-effect-free GETs, because speculate "
                    "lets the browser fetch them before anyone clicks. Do not put a "
                    "count on a tab: only the current tab's contents have been "
                    "built. Set :htmx only on a page that hosts every id the "
                    "response swaps out of band."
                ),
            ),
            Component(
                slug="tab-strip",
                tag="c-n26.tab-strip",
                template="n26/tab_strip.html",
                summary="The two-copy skeleton that keeps a tab strip from wrapping.",
                notes=(
                    "Fill the full and narrow slots with the same tabs drawn two "
                    "ways. Both stay in the HTML, and sm:flex and sm:hidden pick "
                    "which shows, so the split follows the window rather than the "
                    "width of this box. Give every slotted tab a border-b-2: the "
                    "rule under the strip is the tabs' own bottom borders plus a "
                    "trailing spacer, so a tab without one leaves a gap in the "
                    "line. There is no single root element, so put the landmark "
                    "around this component and adjust each copy with full_class or "
                    "narrow_class."
                ),
            ),
            Component(
                slug="deferred",
                tag="c-n26.deferred",
                template="n26/deferred.html",
                summary=(
                    "A fragment fetched from a URL and injected when it is first "
                    "needed."
                ),
                needs=(ALPINE,),
                notes=(
                    "The fetch runs on this component's init, so placement chooses "
                    "the moment: dropped straight on the page it fetches on load, "
                    "and inside a <template x-if> it fetches when that template "
                    "first instantiates. url must be a side-effect-free GET "
                    "returning a trusted HTML fragment with no doctype and no "
                    "shell, because the response is injected with x-html. With "
                    "follows set, a change of address fetches again, the drawn "
                    "fragment stays up until the new one lands, and a late response "
                    "for an older address is dropped. Nothing is cached here; cache "
                    "headers on the fragment are what make a reopened disclosure "
                    "instant."
                ),
            ),
            Component(
                slug="collection-picker",
                tag="c-n26.collection-picker",
                template="n26/collection_picker/index.html",
                summary=(
                    "A long categorised list of priced lines, filtered in the page "
                    "and acted on inline."
                ),
                needs=(ALPINE, KIT_JS, COLLAPSE),
                notes=(
                    "Nest section, category and item children; they register with "
                    "this Alpine scope on init, and the counts and each group's "
                    "visibility follow from that. Put the filter controls in the "
                    "filters slot and name the filter menu category, so "
                    "filter-apply and filter-reset match. Every control that "
                    "narrows the list sits in one sticky box, which reads "
                    "--n26-sticky-top from the page; without that variable the bar "
                    "sits under the nav. Lowering the trade-points cap treats the "
                    "picker as a trading post and hides the Exclusive lines, which "
                    "are equipment-list only."
                ),
                parts=(
                    Part(
                        "c-n26.collection-picker.section",
                        "n26/collection_picker/section.html",
                        (
                            "A named band of the list, hidden when nothing inside "
                            "it matches the filter."
                        ),
                        required=True,
                    ),
                    Part(
                        "c-n26.collection-picker.category",
                        "n26/collection_picker/category.html",
                        (
                            "A named group of items inside a section; its "
                            "disclosure opens and closes with the search."
                        ),
                    ),
                    Part(
                        "c-n26.collection-picker.item",
                        "n26/collection_picker/item.html",
                        (
                            "A priced line: its name, price, rarity, notes and buy "
                            "controls."
                        ),
                        required=True,
                    ),
                ),
            ),
            Component(
                slug="profile-picker",
                tag="c-n26.profile-picker",
                template="n26/profile_picker/index.html",
                summary=(
                    "A collection picker preset for the profiles a gang can hire."
                ),
                needs=(ALPINE, KIT_JS, COLLAPSE, FOCUS),
                notes=(
                    "It forwards filters, the default slot and empty to "
                    "c-n26.collection-picker, and still needs that picker's "
                    "nested section and item children. tabs is forwarded "
                    "explicitly, because an empty value here would override the "
                    "picker and untab the list. The trade-points filter is "
                    "gone: tp_ceiling is neither declared nor forwarded, so a "
                    "call site cannot lower the fixed cap of 99. limited on a "
                    "profile states a composition limit; nothing here enforces "
                    "it, because that check belongs at the operation boundary."
                ),
                parts=(
                    Part(
                        "c-n26.profile-picker.row",
                        "n26/profile_picker/row.html",
                        (
                            "A hireable profile: its name, live price, option "
                            "groups and the Hire submit."
                        ),
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
                summary="A form in a dialog whose open state is decided by the server.",
                needs=(ALPINE,),
                notes=(
                    "Use it where the URL holds the open state: that is what makes "
                    "the panel linkable, survive a reload, and work with scripting "
                    "off. It renders a native <dialog open> in the flow of the "
                    "page, then promotes it with showModal() where Alpine is there "
                    "to call it, which brings the top layer, the backdrop, Escape "
                    "and a focus trap. Dismissing navigates to cancel_url rather "
                    "than hiding in place. Give every panel its own id, because the "
                    "open event matches on it and the heading id derives from it. "
                    "Put the CSRF token in the default slot."
                ),
            ),
            Component(
                slug="hire-dialog",
                tag="c-n26.hire-dialog",
                template="n26/hire_dialog.html",
                summary=(
                    "The hire form: what a model is called, and the price the gang "
                    "pays."
                ),
                needs=(ALPINE,),
                notes=(
                    "Render it only when the hire question is open, since it "
                    "always draws the dialog open. The profile and its options "
                    "go in :fields as hidden inputs, because they were chosen "
                    "on the listing that was clicked. price is what that "
                    "listing was configured to, not the advertised figure. "
                    ":rate_at_paid controls whether a price typed over the "
                    "quote also becomes the model's rating, and must be passed "
                    "back from the posted form so a redraw keeps an untick. Put "
                    "the CSRF token in the default slot."
                ),
            ),
            Component(
                slug="owned-dialog",
                tag="c-n26.owned-dialog",
                template="n26/owned_dialog.html",
                summary=("A confirmation panel for an act on equipment a gang holds."),
                needs=(ALPINE,),
                notes=(
                    "Pass the dict owned_dialog() builds as :dialog. One panel "
                    "covers selling, moving, refunding, removing, fitting an "
                    "accessory, detaching one and changing what a copy was bought "
                    "with; a kind this template does not name falls back to the "
                    "delete wording. Each wording states what the page does not "
                    "show: a sale its arithmetic, a move that it charges nothing, a "
                    "refund what was paid. Pass open, redrawn, htmx and id through "
                    "to c-n26.dialog. A page drawing one panel per weapon must pass "
                    "a distinct id, because the accessory field is named from it."
                ),
            ),
            Component(
                slug="owned-actions",
                tag="c-n26.owned-actions",
                template="n26/owned_actions.html",
                summary=(
                    "Sell, and the other acts available on one copy a model holds."
                ),
                needs=(ALPINE,),
                notes=(
                    "Sell is shown directly and the rest sit behind a chevron, "
                    "drawn from the :sell, :more and :add structures the view "
                    "builds, so an act added there appears here with nothing "
                    'edited. :add is drawn only when layout="menu". Use size sm '
                    "on a listing line and xs on a model card. Set :htmx only "
                    "on a screen that hosts the update panels, as "
                    "n26/includes/equip_hosts.html does; the included snippets "
                    "read it from context."
                ),
            ),
            Component(
                slug="owned-lines",
                tag="c-n26.owned-lines",
                template="n26/owned_lines.html",
                summary=(
                    "The equip lines for what a model already holds, with parts, "
                    "rating and controls."
                ),
                notes=(
                    "It draws the inside of an equip line the way a model card "
                    "draws the same lines: the assignment, what it added to the "
                    "rating, and its parts indented under it. A weapon's own "
                    "profile is not one of those parts, and a rating of zero draws "
                    "nothing. Every control is a link, because this sits inside the "
                    "catalogue's form and HTML cannot nest forms. Accessorise links "
                    "to a dialog whose id is n26-accessorise-<copy id>, which the "
                    "page must already host. A part offers no move, because "
                    "Operation.move does not accept an assignment with a parent."
                ),
            ),
            Component(
                slug="choice-menu",
                tag="c-n26.choice-menu",
                template="n26/choice_menu.html",
                summary=("A dropdown of radios that applies one named value."),
                needs=(ALPINE, KIT_JS, FOCUS),
                notes=(
                    "Use it where only one value applies at a time, a sort order "
                    "being the usual case. c-n26.filter-menu is the many-of-a-set "
                    "sibling, and c-ui.menu applies the moment you pick. OK "
                    "dispatches choice-apply on the window with name and value, and "
                    "a parent must listen or nothing is applied. Cancel restores "
                    "the snapshot taken when the panel opened. The trigger shows "
                    "the chosen label rather than a count."
                ),
            ),
            Component(
                slug="toggle",
                tag="c-n26.toggle",
                template="n26/toggle.html",
                summary="A switch with its label beside it, sized to its content.",
                needs=(ALPINE, KIT_JS),
                notes=(
                    "Use it in a toolbar, where the kit switch does not fit: "
                    "c-ui.switch stacks its label above the control, and :inline "
                    "pushes the switch to the far right of a full-width line. The "
                    "wrapping <label> does the work: it toggles the hidden checkbox "
                    "with no extra JavaScript, and becomes the switch's accessible "
                    "name. Clicking the switch dispatches checkedChange while "
                    "clicking the text fires change, so listen for both if another "
                    "control must stay in step."
                ),
            ),
            Component(
                slug="link",
                tag="c-n26.link",
                template="n26/link.html",
                summary="An inline text link, with tones and underline modes.",
                notes=(
                    "The kit has no link component, since c-ui.button "
                    'variant="text" is still a <button>. The other link-like '
                    "components here are built on this one. Set the colour with "
                    "tone rather than class, because two utilities of equal "
                    "specificity are settled by whichever order Tailwind emitted "
                    "them. Without href it renders a <span>, and tone and underline "
                    "do not apply. Pass markup through the leading and trailing "
                    "slots, which sit outside the underline."
                ),
            ),
            Component(
                slug="color-swatch",
                tag="c-n26.color-swatch",
                template="n26/color_swatch.html",
                summary="A colour as a small round mark before a name.",
                notes=(
                    "color takes a theme token or a literal: a hex is fixed, while "
                    "a token resolves through var() and follows a theme change. The "
                    "colour goes on a style attribute, because Tailwind never emits "
                    "a class name built from a variable. A blank color draws "
                    "nothing rather than holding space, and an unknown token gives "
                    "a transparent disc rather than an error. It is hidden from "
                    "assistive tech unless label is set, and it is sized in em, so "
                    "one call works in a table cell and in a heading."
                ),
            ),
            Component(
                slug="color-link",
                tag="c-n26.color-link",
                template="n26/color_link.html",
                summary="A text link with a colour swatch in front of it.",
                notes=(
                    "c-n26.link with a c-n26.color-swatch in the leading slot, "
                    "outside the underline; c-n26.flair-link is the sibling that "
                    "puts a badge in the trailing one. label names the swatch for "
                    "assistive tech, not the link. Where the heading or cell "
                    "already has an anchor of its own, draw the swatch directly "
                    "rather than wrapping a second link."
                ),
            ),
            Component(
                slug="flair-link",
                tag="c-n26.flair-link",
                template="n26/flair_link.html",
                summary="Text with a small SVG badge after it, linked or not.",
                notes=(
                    "The words go on text and the default slot holds the badge as "
                    "sanitised SVG; an empty slot draws no wrapper. The badge sits "
                    "in the trailing slot, outside the underline, and is sized in "
                    "em on descendant svg, so one component works in a table cell "
                    "and in a heading with no size prop. Without :wrap the text and "
                    "badge are held on one line and centred on its cap height. "
                    ":wrap lets the words break and skips that alignment, the "
                    "tooltip and the accessible name. Leave label empty where the "
                    "text already carries the same wording."
                ),
                parts=(
                    Part(
                        "c-n26.flair.staff",
                        "n26/flair/staff.html",
                        (
                            "The staff badge artwork, from the platform's badge "
                            "registry, in a fixed palette."
                        ),
                    ),
                    Part(
                        "c-n26.flair.house",
                        "n26/flair/house.html",
                        (
                            "The Goliath house mark, drawn in currentColor so it "
                            "follows the surrounding text."
                        ),
                    ),
                    Part(
                        "c-n26.flair.gang-type",
                        "n26/flair/gang_type.html",
                        (
                            "A gang type's own stored artwork, sanitised on the way "
                            "out and drawing nothing when it is missing."
                        ),
                    ),
                ),
            ),
            Component(
                slug="user-link",
                tag="c-n26.user-link",
                template="n26/user_link.html",
                summary="A person's username with the badge they hold.",
                notes=(
                    "Pass a User as user. The username is read here; the badge is "
                    "read off the person's profile, which returns the badge they "
                    "picked, or the highest-ranked one they qualify for "
                    "automatically. Deriving it from is_staff instead would miss "
                    "supporter tiers, granted badges and the person's own choice. A "
                    "lapsed supporter, an explicit opt-out, and anyone whose only "
                    "badge is opt-in and unpicked all draw the name alone. There is "
                    "no label prop, because the registry wording is both the "
                    "accessible name and the tooltip. Prefetch profile and "
                    "badge_grants where you draw many of these, or you get one "
                    "query per user."
                ),
            ),
            Component(
                slug="page-header",
                tag="c-n26.page-header",
                template="n26/page_header.html",
                summary=(
                    "A page title, with optional breadcrumb, lead text and controls."
                ),
                notes=(
                    "title and lead each take an attribute or a slot of the same "
                    "name; the attribute wins if both are passed, and markup in the "
                    "attribute prints as source. Page controls go in actions, and "
                    "anything beside the title in trailing, which sits outside the "
                    "<h1> so it is not read as part of the page name. leading is "
                    "prepended inside the heading and is read as part of it, so put "
                    "nothing meaningful there. breadcrumb_actions must stand no "
                    "taller than a line of trail text, or it pushes the heading "
                    "down."
                ),
            ),
            Component(
                slug="section",
                tag="c-n26.section",
                template="n26/section.html",
                summary="A titled block of a page, with an optional count and controls.",
                notes=(
                    "The title renders as an h2, the same rank c-n26.form-section "
                    "gives a form's groups, so a detail section and a form group "
                    "read at the same rank. The count sits inside the heading, so "
                    "it is announced with the title. id lands on the section and is "
                    "the fragment target; omit it and the section cannot be linked "
                    "to."
                ),
            ),
            Component(
                slug="about",
                tag="c-n26.about",
                template="n26/about/index.html",
                summary=(
                    "The explanation column for a library entry, built from a Prose "
                    "object."
                ),
                notes=(
                    "It draws the three lists n26.library.prose compiles: "
                    "Referenced by, how anyone comes to have it; Does, what it does "
                    "once they have it, in the order the rules apply it; and "
                    "Assigned to, the player-side tally. It renders nothing when "
                    ":prose is missing or every list is empty, so do not wrap it in "
                    "a layout that assumes an aside. The compiler holds no URLs, so "
                    "views fill the addresses in, and a sentence whose subject has "
                    "no page renders as plain words."
                ),
                parts=(
                    Part(
                        "c-n26.about.sentence",
                        "n26/about/sentence.html",
                        (
                            "A statement about a piece of content, linked where its "
                            "subject has a page, with its hint behind hover or "
                            "focus."
                        ),
                        required=True,
                    ),
                ),
            ),
            Component(
                slug="prose",
                tag="c-n26.prose",
                template="n26/prose.html",
                summary="A block of authored HTML copy, styled as readable rich text.",
                notes=(
                    "Use it for copy a template writes and c-n26.rich-text for copy "
                    "the database stores; both go through the same .rich-text rules "
                    "in app.css. Put already-safe HTML in the slot, because this "
                    "wrapper does not sanitise. Write plain HTML tags rather than "
                    "components, since the styling reaches them by descendant "
                    "selector. It caps at max-w-prose unless :measure is False, "
                    "which is what to pass where a card, column or dialog already "
                    "constrains the width."
                ),
            ),
            Component(
                slug="form-actions",
                tag="c-n26.form-actions",
                template="n26/form_actions.html",
                summary="A form's footer: Cancel, any extra controls, then the submit.",
                notes=(
                    "cancel_url draws Cancel as a link, so it never submits; a form "
                    "with nowhere to go back to passes none and gets none. No "
                    "submit_label means no submit button. Extra controls go in the "
                    "default slot, between Cancel and the submit, and a second "
                    "submit there needs its own name and value, because only the "
                    "clicked one is sent. c-n26.form-page draws its footer with "
                    "this, so a page form and a dialog end the same way."
                ),
            ),
            Component(
                slug="form-page",
                tag="c-n26.form-page",
                template="n26/form_page.html",
                summary=(
                    "The wrapper for a form screen: heading, non-field errors, "
                    "fields and footer."
                ),
                notes=(
                    "It draws the <form> tag itself, so put the CSRF token in the "
                    "default slot and pass the fields. header_actions is the "
                    "heading's controls; actions is extra footer controls beside "
                    "the submit. The footer draws only when actions, submit_label "
                    "or cancel_url is set. Declare every slot you intend to fill: a "
                    "slot this wrapper does not declare is not empty when nobody "
                    "fills it, it holds whatever the page has under that name. "
                    "max-w-3xl is a cap, so nothing inside may set a measure of its "
                    "own."
                ),
            ),
            Component(
                slug="form-section",
                tag="c-n26.form-section",
                template="n26/form_section.html",
                summary="A titled group of fields inside a form.",
                notes=(
                    "title renders as an h2, so a run of sections gives the "
                    "form a real document outline. Sections are separated by "
                    "space and a heading rather than boxed, and c-ui.card is "
                    "there for the cases that need a container. Spacing is "
                    "space-y rather than flex gap, so a field the view left out "
                    "cannot leave an empty box collecting space."
                ),
            ),
            Component(
                slug="colour-picker",
                tag="c-n26.colour-picker",
                template="n26/colour_picker.html",
                summary=(
                    "A grid of colour swatches to pick one from, plus a none choice."
                ),
                notes=(
                    "Each radio is visually hidden with its swatch styled "
                    "through peer-checked, so it stays a real input in a real "
                    "label: keyboard-reachable, submitting with no JavaScript, "
                    "and announcing its colour's name. None is a real radio "
                    "with an empty value, which is how a picker can be returned "
                    "to no colour and how a redrawn form distinguishes 'no "
                    "colour' from 'not chosen yet'. Every entry in :colours "
                    "needs a key in :swatches, written as literal class names, "
                    "because Tailwind never emits a class built from a "
                    "variable."
                ),
            ),
            Component(
                slug="filter-select",
                tag="c-n26.filter-select",
                template="n26/filter_select.html",
                summary=(
                    "A native select upgraded to a searchable list once it has "
                    "enough options."
                ),
                needs=(ALPINE,),
                notes=(
                    "Put a real <select> in the default slot: that select is what "
                    "posts, untouched, and the panel sets selectedIndex on it, so "
                    "with scripting off the plain select still works. It hides the "
                    "select only once it counts min_options or more, so short lists "
                    "are left alone. The slot must hold a select; anything else and "
                    "this does nothing, with no error. c-ui.combobox cannot serve "
                    "here, because its name is an Alpine binding and its options "
                    "are a <template>, so unscripted it posts nothing."
                ),
            ),
            Component(
                slug="radio-cards",
                tag="c-n26.radio-cards",
                template="n26/radio_cards/index.html",
                summary=(
                    "A fieldset of radio options, laid out as a wrapping grid of cards."
                ),
                parts=(
                    Part(
                        "c-n26.radio-cards.card",
                        "n26/radio_cards/card.html",
                        "An option card: a radio, a name, a badge and a line of detail.",
                        required=True,
                    ),
                ),
                notes=(
                    "Put c-n26.radio-cards.card children in the default slot, all "
                    "sharing one name; the browser's own single-selection rule over "
                    "that shared name is the state, and has-[:checked] styles the "
                    "chosen card, so the page is right before any script runs. min "
                    "is the CSS minmax track size, not a column count. Pass form "
                    "and name together or neither, or no field error is drawn. Use "
                    "c-n26.checkbox-card where a card's body holds controls of its "
                    "own."
                ),
            ),
            Component(
                slug="choice-offer",
                tag="c-n26.choice-offer",
                template="n26/choice_offer.html",
                summary="Radio cards for a ChoiceOffer that is settled in one submit.",
                parts=(
                    Part(
                        "c-n26.radio-cards",
                        "n26/radio_cards/index.html",
                        "A group heading and the option cards under it.",
                        required=True,
                    ),
                ),
                notes=(
                    "Pass a ChoiceOffer as :offer, and use c-n26.choice-picks "
                    "instead where the offer has takes_several. Every group shares "
                    "one input name, which keeps a single selection across the "
                    "whole list: the headings are how it reads, not separate "
                    "questions. labelled_by prefixes each group's id so an external "
                    "heading can name the list. Nothing here is specific to what is "
                    "being picked, so a skill, a pick and an affiliation can share "
                    "a screen. The caller supplies the empty state."
                ),
            ),
            Component(
                slug="choice-picks",
                tag="c-n26.choice-picks",
                template="n26/choice_picks.html",
                summary=(
                    "Add and remove controls for a ChoiceOffer settled one pick at "
                    "a time."
                ),
                notes=(
                    "Pass a ChoiceOffer with takes_several as :offer, and use "
                    "c-n26.choice-offer where the whole list is settled in one "
                    "submit. Each option draws Add, Remove or both, as plain "
                    "submits drawn like links, so sit it inside the page's form: "
                    "Add submits name, Remove submits remove_name, and only the "
                    "clicked button is sent. When the choice is full, only what it "
                    "already holds is listed."
                ),
            ),
            Component(
                slug="arrival-block",
                tag="c-n26.arrival-block",
                template="n26/arrival_block.html",
                summary=(
                    "A headed block of the questions an author attached to a newly "
                    "arrived slot."
                ),
                parts=(
                    Part(
                        "c-n26.arrival-question",
                        "n26/arrival_question.html",
                        (
                            "An arriving choice: the same picker the pick screen "
                            "draws, with a line naming what is chosen."
                        ),
                        required=True,
                    ),
                ),
                notes=(
                    "Put the questions in the default slot. This draws no form and "
                    "no control of its own: the page's form wraps every block so "
                    "Continue submits them together, and Continue and Skip sit once "
                    "at the foot of the screen. The heading and words are the "
                    "author's."
                ),
            ),
            Component(
                slug="roll-table",
                tag="c-n26.roll-table",
                template="n26/roll_table.html",
                summary=(
                    "The controls that roll on a choice's table, or record a roll "
                    "made at the table."
                ),
                notes=(
                    "It must sit inside the pick form and draws plain submits with "
                    "no form of its own. The visually hidden Enter submit comes "
                    "first, because HTML's default submit is the first in the form "
                    "and Enter in the number field must post enter, not roll. That "
                    "field carries no min or max: HTML validation on one field "
                    "would block every other button on the page's form, and the "
                    "server does not accept a number the die cannot produce."
                ),
            ),
            Component(
                slug="roll-result",
                tag="c-n26.roll-result",
                template="n26/roll_result.html",
                summary=(
                    "The outcome of a recorded roll, above the table it was rolled on."
                ),
                parts=(
                    Part(
                        "c-n26.die",
                        "n26/die.html",
                        (
                            "A six-sided die face drawn as pips, with its number "
                            "announced in words."
                        ),
                    ),
                ),
                notes=(
                    "It is built from the ledger event that recorded the roll, so a "
                    "reload draws the same result and nothing is rolled by drawing. "
                    "It shows the dice faces where the total says which they were, "
                    "and the figure alone otherwise. It then states where the roll "
                    "landed on the table, that the table has no result for that "
                    "number, or that the result has already been applied. It must "
                    "sit inside the pick form, which has to carry the roll key in a "
                    "hidden field; a spent roll draws no buttons."
                ),
            ),
            Component(
                slug="pick-list",
                tag="c-n26.pick-list",
                template="n26/pick_list/index.html",
                summary=(
                    "A ticked list of options, with a searchable panel for adding more."
                ),
                notes=(
                    "Use it for a library too long to scan, such as every subtype "
                    "or every special rule. What is held is ticked boxes, and "
                    "add_label opens the rest as a c-n26.quick-switcher panel. That "
                    "panel only ticks boxes already on the page and adds no input "
                    "of its own, so no value can arrive that nobody chose. Pass "
                    "commit controls in the actions slot, which renders inside this "
                    'Alpine scope, so a Save button can bind ::disabled="!dirty". A '
                    "disabled box submits nothing, so whatever applies the "
                    "difference must not read that silence as a clearing. :grouped "
                    "draws each group under its own name."
                ),
                parts=(
                    Part(
                        "c-n26.pick-list.box",
                        "n26/pick_list/box.html",
                        (
                            "A tickable option, the same line whether held or "
                            "offered, bound to the list's picked state."
                        ),
                    ),
                ),
            ),
            Component(
                slug="tick-list",
                tag="c-n26.tick-list",
                template="n26/tick_list.html",
                summary="A grouped list of options to tick, as native checkboxes.",
                notes=(
                    "It must sit inside a form and runs no script, so what arrives "
                    "ticked is what the server rendered. Every box submits under "
                    "one name across every group: the headings are how the list "
                    "reads, not a question each. An option a rule grants is ticked "
                    "and disabled, naming what grants it. A disabled box posts "
                    "nothing, so whatever applies the difference must leave granted "
                    "options out rather than read that silence as a clearing. An "
                    "empty offer draws nothing, so the page has to explain why it "
                    "is empty."
                ),
            ),
            Component(
                slug="checkbox-card",
                tag="c-n26.checkbox-card",
                template="n26/checkbox_card.html",
                summary="A checkbox drawn as a card whose body stays interactive.",
                needs=(ALPINE,),
                notes=(
                    "Use it where the card holds controls of its own: the kit's "
                    "checkbox cards make the whole surface the toggle, so a click "
                    "on an inner control would toggle the card. While the box is "
                    "clear the body is dimmed and inert, which blocks interaction "
                    "and focus but not submission, so bind :disabled on any inner "
                    "input that must not post, reading the picked value this card "
                    "puts in Alpine scope."
                ),
            ),
            Component(
                slug="divider",
                tag="c-n26.divider",
                template="n26/divider.html",
                summary=(
                    "A horizontal rule that can carry a label or icons in the middle."
                ),
                notes=(
                    "Use the label to state the relationship the rule marks, so "
                    'that "or" makes the block below an alternative to the one '
                    "above rather than a continuation. The lines are flex spans "
                    "rather than a styled <hr>, so the label sits in the rule with "
                    "no background patch behind it and works over any page colour. "
                    "With nothing in the middle it draws a plain rule and adds no "
                    "gap."
                ),
            ),
            Component(
                slug="coming-soon",
                tag="c-n26.coming-soon",
                template="n26/coming_soon.html",
                summary=(
                    "A centred placeholder for a section that exists but is not "
                    "built yet."
                ),
                notes=(
                    "Do not use it for an empty list: a list's own empty slot tells "
                    "the reader that a different search may help, while this states "
                    "that the section is not built yet. It draws no illustration "
                    "and nothing to click. Whitespace-only slot content counts as "
                    "empty, so the subtitle line is dropped."
                ),
            ),
            Component(
                slug="count-badge",
                tag="c-n26.count-badge",
                template="n26/count_badge.html",
                summary="A small filled pill saying how many are waiting.",
                notes=(
                    'Pass the count as :count. Written count="{{ n }}" it arrives '
                    'as the string "0", which is truthy, so a control with nothing '
                    "waiting still gets a badge. The visible face caps at max, "
                    "since three digits would widen the pill past whatever it "
                    "rides. The number is hidden from assistive tech and label is "
                    "what makes it announced, so do not pass one inside a control "
                    "whose own aria-label already carries the count. Placement is "
                    "the caller's: the same pill rides a button's corner and sits "
                    "in a line of text."
                ),
            ),
            Component(
                slug="statline",
                tag="c-n26.statline",
                template="n26/statline/index.html",
                summary=(
                    "A profile's characteristics as a compact strip, or as the "
                    "book's stacked groups."
                ),
                notes=(
                    "build_statline() in n26/core/render.py serves a model profile "
                    "and a weapon profile alike, and the divider and the tint come "
                    "from is_first_of_group and is_highlighted on StatlineTypeStat. "
                    "The arith tag library is required: sub and at_least are not "
                    "Django built-ins, and a missing load raises "
                    'TemplateSyntaxError. layout="book" pads Type and XP onto the '
                    "last group, with type_line as the switch; xp without it is "
                    "dropped. It is not built on c-ui.table, so a class on a cell "
                    "still applies."
                ),
                needs=(ALPINE, KIT_JS),
                parts=(
                    Part(
                        "c-n26.statline.header",
                        "n26/statline/header.html",
                        (
                            "The <th> cells for one group, with optional leading "
                            "and trailing cells."
                        ),
                        required=True,
                    ),
                    Part(
                        "c-n26.statline.cells",
                        "n26/statline/cells.html",
                        (
                            "The <td> cells for one group, marking a modified value "
                            "and naming what changed it."
                        ),
                        required=True,
                    ),
                    Part(
                        "c-n26.statline.edit",
                        "n26/statline/edit.html",
                        (
                            "The same characteristics as boxes to type in, for the "
                            "authoring pages."
                        ),
                    ),
                ),
            ),
            Component(
                slug="record-table",
                tag="c-n26.record-table",
                template="n26/record_table/index.html",
                summary=(
                    "A searchable list of gangs or campaigns, each listing a link "
                    "to one."
                ),
                needs=(ALPINE, KIT_JS),
                parts=(
                    Part(
                        "c-n26.record-table.gang-row",
                        "n26/record_table/gang_row.html",
                        "A gang listing: its name, type, wealth and controls.",
                    ),
                    Part(
                        "c-n26.record-table.campaign-row",
                        "n26/record_table/campaign_row.html",
                        (
                            "A campaign listing: its name, its arbitrator, and Edit "
                            "where the reader runs it."
                        ),
                    ),
                ),
                notes=(
                    "Child listings go in the default slot so they share this "
                    "Alpine scope, and each must register on init or the count "
                    "stays at zero. Typing filters only the listings already on "
                    "the page, while submitting the search, or anything in the "
                    "filters slot, goes to the server and reloads the page. The "
                    "type filter listens only for filter-apply events named "
                    "type. The listings wrapper is a query container, so a gang "
                    "listing's wide layout keys off that rather than the "
                    "viewport."
                ),
            ),
            Component(
                slug="changelog",
                tag="c-n26.changelog",
                template="n26/changelog/index.html",
                summary="A headed list of changelog entries, newest first.",
                parts=(
                    Part(
                        "c-n26.changelog.entry",
                        "n26/changelog/entry.html",
                        "An entry: a title, a two-line body preview and a date.",
                    ),
                ),
                notes=(
                    "Slot the entries; whitespace-only content counts as empty "
                    "and draws the empty message instead. The header renders "
                    "when heading or href is set, and the view-all link sits in "
                    "the heading rather than as a last line, so every line in "
                    "the list opens an entry. Nothing loads more entries, so "
                    "slot everything that should show."
                ),
            ),
            Component(
                slug="tally",
                tag="c-n26.tally",
                template="n26/tally.html",
                summary=(
                    "A stack of labelled figures that add up, label left and value "
                    "right."
                ),
                notes=(
                    "Each fact carries its own ruled and strong flags. Read them "
                    "off the fact and never off its position, because a tally may "
                    "hold more than one total. A rule above a fact is how a total "
                    "is marked off, and the two flags usually travel together."
                ),
            ),
            Component(
                slug="activity-card",
                tag="c-n26.activity-card",
                template="n26/activity_card/index.html",
                summary="An open action, its figures, and the button that completes it.",
                parts=(
                    Part(
                        "c-n26.activity-card.body",
                        "n26/activity_card/body.html",
                        (
                            "The tally, any extra body content, and the form that "
                            "completes the action, drawn the same boxed or not."
                        ),
                    ),
                ),
                notes=(
                    "Only an open action reaches it: starting one belongs to "
                    "whatever holds the card, which on the gang sheet is "
                    "c-n26.activities-square. The title, mark, help and tally all "
                    "come from :card. Extra markup goes in the named body slot and "
                    "sits above the complete form, so fields there do not submit. "
                    "Pass :boxed as a boolean, not the string False; boxed=False "
                    "drops the card and the eyebrow for a caller that has drawn its "
                    "own box. The complete button posts and is never a link, "
                    "because following a link must not end an action."
                ),
            ),
            Component(
                slug="activities-square",
                tag="c-n26.activities-square",
                template="n26/activities_square/index.html",
                summary=(
                    "A gang's open actions, its waiting steps, and the control that "
                    "starts a new one."
                ),
                notes=(
                    "It is the first square of the gang sheet's grid, drawn only "
                    "for the owner and always drawn: a square that came and went "
                    "would move every card after it. The nothing-open message shows "
                    "only when nothing is running and nothing is waiting. The start "
                    "control is a form, as is any waiting step that acts on the "
                    "click, because following a link must not change the roster. "
                    "The acts listed are built by n26.core.history, and their times "
                    "are relative, so the template loads humanize."
                ),
            ),
            Component(
                slug="founding-mark",
                tag="c-n26.founding-mark",
                template="n26/founding_mark.html",
                summary="The violet flag that marks a founding action or allowance.",
                notes=(
                    "Use the same mark wherever founding Trade Points appear, so "
                    "those places read as one feature. The colour lives on the "
                    "wrapper, so every call site draws the same violet; class is "
                    "forwarded to the inner icon, and a colour utility there "
                    "overrides the mark. Do not draw it in the accent colour or the "
                    "green a completing button takes, or it reads as a control. "
                    "Pass label where the flag is the only marker of founding."
                ),
            ),
            Component(
                slug="wealth",
                tag="c-n26.wealth",
                template="n26/wealth/index.html",
                summary=(
                    "A gang's Trade Points, rating, credits, stash and wealth as a "
                    "figure strip."
                ),
                needs=(ALPINE, KIT_JS),
                parts=(
                    Part(
                        "c-n26.wealth.figure",
                        "n26/wealth/figure.html",
                        (
                            "A labelled figure in the strip: the short name over "
                            "its value, or a dash when unset."
                        ),
                    ),
                ),
                notes=(
                    "Pass the whole GangSheet as :sheet rather than loose integers, "
                    "which in the same units are easy to swap and hard to notice. "
                    "Rating, credits, stash and wealth read left to right as the "
                    "sum they make. Trade Points lead, behind a rule, because they "
                    "are not money and not part of that sum. A zero is a real "
                    "figure and only an unset value draws a dash, which is how a "
                    "shut trading post and unlimited credits are shown. It is a "
                    "definition list, and its short names carry real tooltips."
                ),
            ),
            Component(
                slug="gang-figures",
                tag="c-n26.gang-figures",
                template="n26/gang_figures/index.html",
                summary=("The roster count beside a gang's wealth strip."),
                needs=(ALPINE, KIT_JS),
                notes=(
                    "Draw it wherever a spending decision is being made: the "
                    "gang sheet, above the hire list, and in the corner of the "
                    "model screens' header. The count is c-n26.roster-summary "
                    "rather than a figure cell, so it is a control, and a rule "
                    "separates it from the money. It takes the tally and reads "
                    "the count off it, so a call site cannot state a count the "
                    "breakdown disagrees with. Keep the count outside the "
                    "wealth wrapper, so a purchase that replaces the money "
                    "figures does not rebuild it."
                ),
            ),
            Component(
                slug="roster-summary",
                tag="c-n26.roster-summary",
                template="n26/roster_summary.html",
                summary=(
                    "A gang's model count, which opens a breakdown of the roster."
                ),
                needs=(ALPINE, KIT_JS),
                notes=(
                    "The count is the trigger: it opens two readings of that roster "
                    "in two tabs, one by profile and rank and one of every model "
                    "with its pinned rating, both in the roster's own order, pets "
                    "after their keepers. The ratings total is the sum of the "
                    "models listed, which the gang's own rating figure need not "
                    "equal, since a gang's worth can include stashed gear no model "
                    "holds. The number carries no unit: it counts models, not "
                    "credits. It is usually drawn through c-n26.gang-figures rather "
                    "than on its own."
                ),
            ),
            Component(
                slug="detail-list",
                tag="c-n26.detail-list",
                template="n26/detail_list/index.html",
                summary=(
                    "A wrapping strip of labelled facts, each value also the "
                    "control that edits it."
                ),
                needs=(ALPINE, KIT_JS, FOCUS),
                parts=(
                    Part(
                        "c-n26.detail-list.row",
                        "n26/detail_list/row.html",
                        (
                            "A labelled fact, as text or as a button that opens "
                            "what edits it."
                        ),
                    ),
                    Part(
                        "c-n26.detail-list.heading",
                        "n26/detail_list/heading.html",
                        "A group title marking where the next run of facts starts.",
                    ),
                ),
                notes=(
                    "Put c-n26.detail-list.row and .heading children inside; "
                    "other markup breaks the dt and dd pairing. One fact gets "
                    "one control however much it holds: three skill sets are "
                    "one question, and three buttons would read as three. "
                    "Spacing lives on the list, so a fact hidden by a "
                    "permission check cannot leave a gap. It is a wrapping flex "
                    "list rather than a grid, which would align every value to "
                    "the widest label on the sheet."
                ),
            ),
            Component(
                slug="choice-slots",
                tag="c-n26.choice-slots",
                template="n26/choice_slots.html",
                summary=(
                    "Detail-list lines for a model's choice slots, settled or still "
                    "open."
                ),
                needs=(ALPINE, KIT_JS, FOCUS),
                notes=(
                    "It emits lines and no container, so it must sit inside a "
                    "c-n26.detail-list, and class lands on every line. A "
                    "settled slot and an open one are the same control leading "
                    "to the same page, so clicking a settled one is how a "
                    "reader changes their mind, and an open one is never marked "
                    "as missing. A line with no address, such as a card built "
                    "from a profile's default equipment, draws as text with a "
                    "dash rather than a button that goes nowhere. A dismissed "
                    "line is marked as dismissed and offers Restore."
                ),
            ),
            Component(
                slug="campaign-block",
                tag="c-n26.campaign-block",
                template="n26/campaign_block.html",
                summary=(
                    "A gang's campaign assets and holdings, as detail-list lines."
                ),
                needs=(ALPINE, KIT_JS, FOCUS),
                notes=(
                    "It emits a heading and facts rather than its own container, so "
                    "it must sit inside a c-n26.detail-list, and class lands on "
                    "every heading and fact. An asset's line is labelled with the "
                    "campaign type's word for its asset type. A holding links to "
                    "the campaign's assets, because another gang may hold it next, "
                    "and adds nothing to the gang's rating. Counter controls draw "
                    "only where the line carries an address, which "
                    "n26.core.views.owned.link_counters fills for the gang's owner "
                    "alone. Do not build campaign links from a URL name here."
                ),
            ),
            Component(
                slug="campaign-figures",
                tag="c-n26.campaign-figures",
                template="n26/campaign_figures.html",
                summary="A campaign's headline counts as a figure strip.",
                needs=(ALPINE, KIT_JS),
                notes=(
                    "It is built from c-n26.wealth.figure, so the campaign page and "
                    "the gang sheet draw one strip from one place. Every figure "
                    "passes an empty unit, because none of these counts is money "
                    "and the figure otherwise defaults to a credits sign. It takes "
                    "the whole sheet and reads the gang count off its own property, "
                    "since a :value attribute takes a variable and never a filter. "
                    "The strip does not wrap: overflow scrolls sideways instead."
                ),
            ),
            Component(
                slug="campaign-gangs",
                tag="c-n26.campaign-gangs",
                template="n26/campaign_gangs.html",
                summary=(
                    "Every gang in the campaign, with its counters, labels and "
                    "assets, as one table."
                ),
                needs=(ALPINE, KIT_JS),
                notes=(
                    "Counters, labels and assets are laid out by position against "
                    "the sheet's column lists, never by name, so a value lands "
                    "under its heading by index. Every empty value draws a dash, "
                    "never a blank, which would look like a failed number. Counter "
                    "controls appear only where the line carries an address, which "
                    "the view fills for the arbitrator and for a gang's own owner. "
                    "It sits in c-ui.table, which already scrolls sideways, so do "
                    "not add another wrapper or a wide campaign widens the page."
                ),
            ),
            Component(
                slug="campaign-assets",
                tag="c-n26.campaign-assets",
                template="n26/campaign_assets.html",
                summary=(
                    "Every asset of one asset type, showing who holds each and its "
                    "available actions."
                ),
                needs=(ALPINE, KIT_JS),
                notes=(
                    "Call it once per transferable asset type. A control is drawn "
                    "only where the structure carries its address, "
                    "so a reader who may not act sees no controls rather than "
                    "disabled ones; n26.core.views.campaigns fills them for the "
                    "arbitrator and the holding gang's owner. Roll is the primary "
                    "control because it begins a form, and it fetches with "
                    'hx-swap="none" so the response opens a dialog; without '
                    "JavaScript it is a plain link."
                ),
            ),
            Component(
                slug="stash",
                tag="c-n26.stash",
                template="n26/stash/index.html",
                summary="A gang's stored gear, as a card in the roster's grid.",
                parts=(
                    Part(
                        "c-n26.stash.group",
                        "n26/stash/group.html",
                        "A labelled list of one kind of stored gear.",
                    ),
                ),
                notes=(
                    "It takes a slot among the model cards, so moving equipment "
                    "between a card and the stash happens on one screen. An empty "
                    "stash still draws the card, because a slot that came and went "
                    "with the contents would move every model after it around the "
                    "grid. :total is the stash rating and has to be passed, since a "
                    "stacked line shows the rating for one copy. Stashed gear "
                    "counts in the gang's wealth, not in the models' rating."
                ),
            ),
            Component(
                slug="model-header",
                tag="c-n26.model-header",
                template="n26/model_header.html",
                summary=(
                    "A model's name and rank, above the tab strip for that model's "
                    "screens."
                ),
                needs=(ALPINE, FOCUS),
                notes=(
                    "Every per-model screen renders it, so Edit, Equip and Options "
                    "read as tabs of one place. The strip is built by the "
                    "model_screen_tabs tag rather than passed in, so a screen "
                    "cannot invent one of its own and adding a screen is one edit "
                    "to n26.core.navigation. active names the tab being drawn "
                    "rather than the URL and defaults to edit, so Equip and Options "
                    "must pass it or the wrong tab looks current. The card slot "
                    "sits between the page header and the strip."
                ),
            ),
            Component(
                slug="model-card",
                tag="c-n26.model-card",
                template="n26/model_card/index.html",
                summary="A model's card: characteristics, weapons, skills, gear and XP.",
                notes=(
                    "It renders an n26.render.ModelCard the backend assembles in "
                    "one query, so the template computes nothing and nothing here "
                    "changes a statline or a weapon. Every control is drawn from an "
                    "href on the structure, so a print sheet or a hire preview that "
                    "passes none draws none. mode is gang for an owner's roster, "
                    "view for a read-only roster, and edit for the model's own page. "
                    "Wrap a region only one mode draws in "
                    "c-n26.model-card.mode. Only a stored model has an id, so a "
                    'preview must not render an empty anchor, and :tabs="False" '
                    "draws the body without the Card, Lore and Notes strip."
                ),
                needs=(ALPINE, KIT_JS),
                parts=(
                    Part(
                        "c-n26.assignable-lines",
                        "n26/assignable_lines.html",
                        (
                            "A run of assignables, marking the ones that were "
                            "granted rather than bought and writing repeats of one "
                            "as Name (x2)."
                        ),
                        required=True,
                    ),
                    Part(
                        "c-n26.model-card.mode",
                        "n26/model_card/mode.html",
                        (
                            "A region of the card drawn only when the enclosing "
                            "card's mode matches."
                        ),
                    ),
                    Part(
                        "c-n26.model-card.body",
                        "n26/model_card/body.html",
                        (
                            "The rules half of the card, statline, lines and weapon "
                            "table, shared by the tabbed card and the tabless "
                            "preview."
                        ),
                        required=True,
                    ),
                    Part(
                        "c-n26.model-card.prose",
                        "n26/model_card/prose.html",
                        (
                            "A written section of the card, used for the Lore and "
                            "Notes panels."
                        ),
                    ),
                    Part(
                        "c-n26.counter-controls",
                        "n26/counter_controls.html",
                        (
                            "The plus and minus that post a change of one on a "
                            "counter line, drawn only where that line carries an "
                            "address."
                        ),
                    ),
                    Part(
                        "c-n26.choice-dismiss",
                        "n26/choice_dismiss.html",
                        (
                            "The control that dismisses an open offer, or restores "
                            "a dismissed one, drawn only where that line carries an "
                            "address."
                        ),
                    ),
                ),
            ),
            Component(
                slug="picture-box",
                tag="c-n26.picture-box",
                template="n26/picture_box.html",
                summary=(
                    "An edit page's picture section: the picture, its removal and "
                    "its upload."
                ),
                needs=("n26/imagecrop.js", "Cropper.js"),
                notes=(
                    "It draws its own forms, both posting act=picture to action, so "
                    "do not nest it inside another form. crop and max are str() of "
                    "the server's own constants in n26/core/images.py, and a call "
                    "site hands them through from its view rather than spelling the "
                    "shape itself. n26/imagecrop.js redraws this wrapper in place "
                    "after a background save, so the page that action renders must "
                    "carry the same box."
                ),
            ),
            Component(
                slug="picture-input",
                tag="c-n26.picture-input",
                template="n26/picture_input.html",
                summary="A picture upload whose crop is chosen in a dialog.",
                needs=("n26/imagecrop.js", "Cropper.js"),
                notes=(
                    "Picking a file opens a dialog holding a rectangle of the "
                    "declared crop over the picture, dragged and resized with "
                    "Cropper.js. Confirming stages that window on the input so the "
                    "form's own save sends what the dialog showed, and leaving any "
                    "other way clears the pick. Without Cropper.js and "
                    "n26/imagecrop.js it is an ordinary file input, and either way "
                    "the server centre-crops every upload to the same ratio. "
                    ":submit_on_crop saves from the open dialog, so set it only on "
                    "a form that is the picture's own, paired with "
                    "data-crop-fallback."
                ),
            ),
            Component(
                slug="rich-text",
                tag="c-n26.rich-text",
                template="n26/rich_text.html",
                summary=(
                    "A TinyMCE editor field, and the safe renderer for what it "
                    "produces."
                ),
                needs=(ALPINE, "TinyMCE", "form.media"),
                notes=(
                    "Pass a bound field to render the editor with its Edit and "
                    "Preview switch. Pass only value to render the saved article, "
                    "which runs through safe_rich_text; do not add a safe filter on "
                    "that path. "
                    "It is wrapped in c-ui.field, so label, description and errors "
                    "work as they do on c-ui.input. The page must render {{ "
                    "form.media }} once, and load n26/richtext.js before it, or the "
                    "widget stays a plain textarea."
                ),
            ),
            Component(
                slug="action-bar",
                tag="c-n26.action-bar",
                template="n26/action_bar.html",
                summary=(
                    "A wrapping line of controls, with a trailing group pushed to "
                    "the far end."
                ),
                notes=(
                    "Layout only: it keeps controls of differing heights on one "
                    "centre line, and the trailing slot stays at the far end even "
                    "when the bar wraps. :surface puts it on a tinted strip, for a "
                    "secondary bar inside a card rather than at the top of a page. "
                    "Use it for a run of filters too rather than adding a second "
                    "component with the same markup."
                ),
            ),
            Component(
                slug="button-group",
                tag="c-n26.button-group",
                template="n26/button_group.html",
                summary="Buttons and links joined into one segmented control.",
                notes=(
                    "The kit has no button group. The group owns the outer radius "
                    "and its children give up theirs, joined in app.css outside any "
                    "layer so it beats the radius utilities on kit buttons. "
                    "Anything can join the run, a dropdown trigger included, which "
                    "is how a split caret ends a toolbar. A wrapper around a "
                    "trigger must be a direct child, or the heights do not match."
                ),
            ),
            Component(
                slug="quick-switcher",
                tag="c-n26.quick-switcher",
                template="n26/quick_switcher/index.html",
                summary=(
                    "A filtered menu of places to go or states to switch to, beside "
                    "the current one."
                ),
                needs=(ALPINE, KIT_JS, FOCUS),
                notes=(
                    "Fill the default slot with item or choice children, which "
                    "register on this scope. That slot is drawn twice: the panel is "
                    "built from a <template> and does not exist without script, so "
                    "a <noscript> strip repeats the same destinations flat. "
                    "Filtering narrows the items already on the page and makes no "
                    "request. Focus lands in the filter box and stays there, with "
                    "Down and Up moving a highlight through aria-activedescendant, "
                    "Enter following it, and Escape clearing a filter before a "
                    "second Escape closes the panel. hotkey is one letter, bound "
                    "page-wide as Alt+Shift+that letter."
                ),
                parts=(
                    Part(
                        "c-n26.quick-switcher.item",
                        "n26/quick_switcher/item.html",
                        (
                            "A destination: an icon, a label, and a tick when it is "
                            "the current page."
                        ),
                        required=True,
                    ),
                    Part(
                        "c-n26.quick-switcher.choice",
                        "n26/quick_switcher/choice.html",
                        (
                            "An in-page option rather than a destination: a button "
                            "that reports its value and closes the panel."
                        ),
                    ),
                    Part(
                        "c-n26.quick-switcher.of",
                        "n26/quick_switcher/of.html",
                        (
                            "The whole control built from one Switcher structure, "
                            "which is how the application draws every one of them."
                        ),
                    ),
                ),
            ),
            Component(
                slug="action-links",
                tag="c-n26.action-links",
                template="n26/action_links.html",
                summary="A wrapping run of text links separated by middle dots.",
                notes=(
                    "Do not write the separators: app.css draws a dot before every "
                    "child but the first, so adding, reordering or "
                    "permission-hiding a link cannot leave a stray one behind. The "
                    "icon slot is one icon for the whole run, and the dot that "
                    "would follow it is suppressed."
                ),
                parts=(
                    Part(
                        "c-n26.action-link",
                        "n26/action_link.html",
                        (
                            "A text link in the run, with an optional leading icon "
                            "and a danger tone."
                        ),
                        required=True,
                    ),
                ),
            ),
        ],
    ),
    Group(
        "Print",
        (
            "Components for printed sheets, where sizes are physical and a page "
            "break can split what should stay whole."
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
                    "Exactly one per document. @page is a document-level rule with "
                    "no element to scope it to, so a second sheet's page size wins "
                    "for both; a nested or sibling sheet must pass an empty "
                    "owns_page. page must be a4, a5 or letter and orientation "
                    "portrait or landscape. Any other value keeps A4 portrait "
                    "geometry on the box while @page emits the value you passed. It "
                    "publishes the printable area as --print-content-w and "
                    "--print-content-h, which the grid divides into cells that "
                    "cannot overflow the paper. fit and auto_print load "
                    "print-fit.js; without it, data-print-fit on a card clips "
                    "instead of shrinking the type. Theme tokens do not reach "
                    "inside it, because the print palette is fixed."
                ),
                parts=(
                    Part(
                        "c-n26.print.grid",
                        "n26/print/grid.html",
                        (
                            "Tiles children N-up as inline blocks, which is "
                            "what keeps a page break from cutting one in half."
                        ),
                    ),
                    Part(
                        "c-n26.print.card",
                        "n26/print/card.html",
                        (
                            "A unit kept on a single page: grid-cell width, "
                            "optional fixed height, and a footer on the bottom "
                            "edge."
                        ),
                    ),
                    Part(
                        "c-n26.print.statline",
                        "n26/print/statline.html",
                        (
                            "Characteristics in the book's two-row layout, with "
                            "Type and XP filling the last group."
                        ),
                    ),
                    Part(
                        "c-n26.print.table",
                        "n26/print/table.html",
                        (
                            "A long table whose head and foot repeat on every page "
                            "and whose rows never split."
                        ),
                    ),
                    Part(
                        "c-n26.print.weapons",
                        "n26/print/weapons.html",
                        (
                            "A card's weapons as one grouped print table, built "
                            "from the card's weapon columns."
                        ),
                    ),
                    Part(
                        "c-n26.print.columns",
                        "n26/print/columns.html",
                        (
                            "Columns side by side as flex, never CSS multicol, "
                            "which WebKit collapses when printing."
                        ),
                    ),
                    Part(
                        "c-n26.print.column",
                        "n26/print/column.html",
                        (
                            "A column, optionally spreading its children down the "
                            "full height."
                        ),
                    ),
                    Part(
                        "c-n26.print.entry",
                        "n26/print/entry.html",
                        (
                            "A labelled value, beside or above, laid out as one box "
                            "so no engine may split it."
                        ),
                    ),
                    Part(
                        "c-n26.print.field",
                        "n26/print/field.html",
                        (
                            "A labelled box to write in by hand, with whatever is "
                            "already known printed inside."
                        ),
                    ),
                    Part(
                        "c-n26.print.break",
                        "n26/print/break.html",
                        "An empty box that forces a page break after it.",
                    ),
                ),
            ),
        ],
    ),
    Group(
        "Site chrome",
        (
            "The frame around the application: the announcement bar, the top "
            "navigation and the footer, which share one container."
        ),
        [
            Component(
                slug="site-announcement",
                tag="c-n26.site.announcement",
                template="n26/site/announcement.html",
                summary="A bar across the top of the site, carrying one message.",
                needs=(ALPINE,),
                notes=(
                    "It sits above the nav rather than inside it, so it pushes the "
                    "whole application down. tone is a data-tone attribute setting "
                    "the background, border, ink and icon together; pass "
                    'icon="none" to draw no icon. A CTA needs both cta_text and '
                    "cta_url, and the action slot holds extra controls, typically a "
                    "form, which must stay outside the message span. Dismissing "
                    "hides the bar for this visit only: on_dismiss is where a "
                    "server call or a localStorage flag goes."
                ),
            ),
            Component(
                slug="site-nav",
                tag="c-n26.site.nav",
                template="n26/site/nav/index.html",
                summary=(
                    "The bar across the top of every page, and the drawer behind "
                    "its menu button."
                ),
                needs=(ALPINE, KIT_JS, FOCUS),
                notes=(
                    "The links live in the drawer and nowhere else, which leaves "
                    "the space beside the brand to the page's own name. heading "
                    "must be a slot, because a Django block inside a Cotton "
                    "attribute never runs. The default slot is drawn twice, once in "
                    "the drawer and once in a <noscript> strip: Alpine builds the "
                    "drawer from a <template>, so without script the panel does not "
                    "exist and the links would be nowhere. Pass :unread with the "
                    'colon, because written unread="{{ count }}" it arrives as the '
                    'string "0", which is truthy, and an empty inbox gets a badge.'
                ),
                parts=(
                    Part(
                        "c-n26.site.nav.gang",
                        "n26/site/nav/gang.html",
                        "A link to one of the reader's own gangs, in the drawer.",
                    ),
                    Part(
                        "c-n26.site.nav.theme",
                        "n26/site/nav/theme.html",
                        (
                            "Light, dark and the machine's own setting, as one "
                            "segmented control in the account menu."
                        ),
                    ),
                ),
            ),
            Component(
                slug="site-edition-toggle",
                tag="c-n26.site.edition-toggle",
                template="n26/site/edition_toggle.html",
                summary=(
                    "A two-segment pill marking the current edition and linking to "
                    "the other."
                ),
                notes=(
                    "The filled segment is the edition this bar belongs to, and "
                    "the hollow one is a plain link to the other's front page, "
                    "so nothing toggles in place and no script is needed. The "
                    "N23 href must keep ?edition=n23, because a bare root link "
                    "redirects back here: the last edition is held in a cookie. "
                    "Draw it only where the reader can follow both links, which "
                    "means signed in."
                ),
            ),
            Component(
                slug="site-footer",
                tag="c-n26.site.footer",
                template="n26/site/footer/index.html",
                summary=("The bottom of every page: a grid of link columns."),
                notes=(
                    "Put c-n26.site.footer.column children in the slot. app.css "
                    "sets three columns from 48rem, so the shape comes from the "
                    "grid rather than from anything the caller passes, and a "
                    "two-column footer still lines up with a three-column one. "
                    "It uses n26-site-container, the same measure as the nav "
                    "and the announcement, so the logos line up. Print CSS "
                    "hides it."
                ),
                parts=(
                    Part(
                        "c-n26.site.footer.column",
                        "n26/site/footer/column.html",
                        (
                            "A column: a heading over a list of links, or free "
                            "content instead of the list."
                        ),
                        required=True,
                    ),
                ),
            ),
        ],
    ),
    Group(
        "Views",
        (
            "Whole screens assembled from the components above, without the site "
            "chrome or the routing around them."
        ),
        [
            Component(
                slug="view-gang-sheet",
                tag="c-n26.view.gang-sheet",
                template="n26/view/gang_sheet.html",
                summary="The gang screen: header, facts, stash and the model cards.",
                needs=(ALPINE, KIT_JS, FOCUS),
                notes=(
                    "Everything above the models is a header: whose gang it is, its "
                    "name and type, its wealth, its standing facts and its "
                    "controls. The model cards are a CSS grid to three columns, so "
                    "a wider screen draws more cards abreast rather than one wide "
                    "column. Every slot is declared, and the header actions slot "
                    "has to be filled, or Cotton draws the page's own Hire controls "
                    "beside the title. Put the switcher in trailing, not leading: "
                    "leading sits inside the h1 and is read as part of the page "
                    "name. Pass activities_square only for the owner."
                ),
            ),
            Component(
                slug="view-campaign-sheet",
                tag="c-n26.view.campaign-sheet",
                template="n26/view/campaign_sheet.html",
                summary=(
                    "The campaign screen: header, figures, gangs, assets, players, "
                    "battles and the log."
                ),
                needs=(ALPINE, KIT_JS, FOCUS),
                notes=(
                    "It has the gang sheet's shape: the type and the arbitrator as "
                    "the lead, the headline figures in the corner, the facts beside "
                    "the page's controls, then the sections at one heading scale. "
                    "The gangs and assets tables are drawn from :sheet, while "
                    "players, battles and log arrive as slots because each names "
                    "addresses. Those slots must be declared, because the page "
                    "filling this calls its own context battles and players. What "
                    "the arbitrator adds sits where it shows: Add asset type on the "
                    "Assets heading, Add counter and Add label on the Gangs "
                    "heading."
                ),
            ),
            Component(
                slug="view-model-edit",
                tag="c-n26.view.model-edit",
                template="n26/view/model_edit.html",
                summary=(
                    "The Edit face of a model's page: the card, the forms and the "
                    "notes."
                ),
                needs=(ALPINE, KIT_JS, FOCUS, "n26/imagecrop.js", "Cropper.js"),
                notes=(
                    "The model card fills the header's card slot in edit mode, "
                    "above the tab strip, where the Equip and Options faces draw it "
                    "too. Under the strip is a grid, one column on a phone and two "
                    "above it, with nothing spanning both. Each form arrives as a "
                    "slot, fields and submit together, because saving is the page's "
                    "business. The editors are siblings of the card, not children, "
                    "so replacing the card leaves them in place. Set :htmx only on "
                    "a page that also draws the dialog hosts, since an out-of-band "
                    "swap whose id is missing is dropped silently."
                ),
            ),
            Component(
                slug="view-dashboard",
                tag="c-n26.view.dashboard",
                template="n26/view/dashboard.html",
                summary=(
                    "The signed-in home screen: your gangs and campaigns, and what "
                    "changed."
                ),
                needs=(ALPINE, KIT_JS),
                notes=(
                    "The gangs and campaigns you own come first, then what has "
                    "changed since you last looked. Founding a gang is the only "
                    "primary button on the screen, since everything else reaches a "
                    "record that already exists. An empty gangs slot draws nothing, "
                    "while Campaigns and Content Packs fall back to "
                    "c-n26.coming-soon. default_tab is the open panel, which the "
                    "home page reads from ?tab=."
                ),
            ),
            Component(
                slug="view-fighter-hire",
                tag="c-n26.view.fighter-hire",
                template="n26/view/fighter_hire.html",
                summary=(
                    "The hire screen: the gang's figures, any notice, and the list "
                    "of profiles."
                ),
                needs=(ALPINE, KIT_JS, COLLAPSE, FOCUS),
                notes=(
                    "There is no footer submit: every Hire button in the list "
                    "submits this form, carrying which profile or which option was "
                    "clicked, so passing submit_label would hire with no profile. "
                    "Naming is asked after the click, by c-n26.hire-dialog, rather "
                    "than above the list. A hire lands back here rather than on the "
                    "gang sheet, so the notice slot draws the confirmation beside "
                    "the list it was clicked in."
                ),
            ),
            Component(
                slug="view-create-gang",
                tag="c-n26.view.create-gang",
                template="n26/view/create_gang.html",
                summary=(
                    "The founding form: name, gang type, and optional starting "
                    "credits and colour."
                ),
                notes=(
                    "The fields are split into required and optional groups, so a "
                    "reader can stop after the first and have a gang. Pass "
                    "gang_types yourself, because the radio cards do not read the "
                    "form field, and put the CSRF token in the default slot. Keep "
                    "the starting credits help text: blank means no limit, which an "
                    "empty number field otherwise reads as zero."
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
