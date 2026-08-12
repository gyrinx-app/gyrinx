"""The project's icon set, named and stated once.

There is no icon library to install. django-cotton-ui ships components, tokens
and a stylesheet, but no icons at all — so every SVG here was pasted inline at
the point it was needed, and the same artwork ended up in several files at once:
one chevron in five templates, one pencil in four. Nothing named it, nothing
listed it, and a sixth chevron would have been pasted rather than reused.

The drawings are Heroicons v2 outline (MIT), on a 24x24 canvas with round caps
and joins, so one set of <svg> attributes suits all of them and only the path
data differs. That uniformity is why the registry can be path data alone.

Four entries are *local* redrawings rather than the upstream Heroicons path.
They were drawn by hand before this file existed, and they are kept exactly as
they are, because they are what these pages already look like — renaming the set
should not silently redraw it. LOCAL marks them: they are what to revisit if the
set is ever taken from upstream wholesale.

Each name maps to a list of subpaths, not one string. Several icons are drawn as
distinct strokes, and separate <path> elements say so more clearly than one
concatenated `d`; a single-stroke icon is simply a list of one.
"""

ICONS: dict[str, list[str]] = {
    # ------------------------------------------------------------- navigation
    "chevron-down": ["m19.5 8.25-7.5 7.5-7.5-7.5"],
    "chevron-right": ["m8.25 4.5 7.5 7.5-7.5 7.5"],
    "bars-3": ["M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5"],
    "ellipsis-vertical": [
        "M12 6.75h.008v.008H12V6.75Zm0 5.25h.008v.008H12V12Zm0 5.25h.008v.008H12v-.008Z"
    ],
    "arrow-uturn-left": ["M9 15 3 9m0 0 6-6M3 9h12a6 6 0 0 1 0 12h-3"],
    "arrow-top-right-on-square": [
        "M13.5 6H5.25A2.25 2.25 0 0 0 3 8.25v10.5A2.25 2.25 0 0 0 5.25 21h10.5"
        "A2.25 2.25 0 0 0 18 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25"
    ],
    # ----------------------------------------------------------------- action
    "plus": ["M12 4.5v15m7.5-7.5h-15"],
    "minus": ["M5 12h14"],
    "check": ["m4.5 12.75 6 6 9-13.5"],
    "x-mark": ["M6 18 18 6M6 6l12 12"],
    "magnifying-glass": [
        "m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z"
    ],
    # LOCAL — a simplified pencil; upstream's has a separate nib stroke.
    "pencil": [
        "m16.86 4.49 2.65 2.65m-1.06-3.71a1.5 1.5 0 0 1 2.12 2.12L7.5 19.5l-4 1 1-4Z"
    ],
    # LOCAL — a plain tray-and-arrow, where upstream's tray is a deeper box.
    "arrow-up-tray": ["m9 6.75 3-3 3 3M12 3.75v9.5m-6 6.5h12"],
    # LOCAL — squarer than upstream's printer, which has a rounded body.
    "printer": [
        "M6.72 13.83V4.5h10.56v9.33m-10.56 0H4.5v4.42h2.22m10.56-4.42h2.22v4.42h-2.22"
        "m-10.56 0v3.42h10.56v-3.42m-10.56 0h10.56"
    ],
    # LOCAL — a five-point star with a flatter rise than upstream's.
    "star": [
        "M11.48 3.5a.56.56 0 0 1 1.04 0l2.12 4.4 4.84.7c.47.07.66.65.32.98l-3.5 3.4"
        ".83 4.82c.8.47-.4.83-.82.6L12 16.13l-4.31 2.27c-.42.23-.9-.13-.82-.6l.82-4.82"
        "-3.5-3.4a.56.56 0 0 1 .32-.97l4.84-.71 2.13-4.4Z"
    ],
    "calculator": [
        "M15.75 15.75V18m-7.5-6.75h.008v.008H8.25v-.008Zm0 2.25h.008v.008H8.25V13.5Z"
        "m0 2.25h.008v.008H8.25v-.008Zm0 2.25h.008v.008H8.25V18Zm2.498-6.75h.007v"
        ".008h-.007v-.008Zm0 2.25h.007v.008h-.007V13.5Zm0 2.25h.007v.008h-.007v-.008Z"
        "m0 2.25h.007v.008h-.007V18Zm2.504-6.75h.008v.008h-.008v-.008Zm0 2.25h.008v"
        ".008h-.008V13.5Zm0 2.25h.008v.008h-.008v-.008Zm0 2.25h.008v.008h-.008V18Z"
        "m2.498-6.75h.008v.008h-.008v-.008Zm0 2.25h.008v.008h-.008V13.5ZM8.25 6h7.5"
        "v2.25h-7.5V6ZM12 2.25c-1.892 0-3.758.11-5.593.322C5.307 2.7 4.5 3.65 4.5 "
        "4.757V19.5a2.25 2.25 0 0 0 2.25 2.25h10.5a2.25 2.25 0 0 0 2.25-2.25V4.757"
        "c0-1.108-.806-2.057-1.907-2.185A48.507 48.507 0 0 0 12 2.25Z"
    ],
    # ------------------------------------------------------------------ thing
    "user-plus": [
        "M18 7.5v3m0 0v3m0-3h3m-3 0h-3m-2.25-4.125a3.375 3.375 0 1 1-6.75 0 3.375 "
        "3.375 0 0 1 6.75 0ZM3 19.235v-.11a6.375 6.375 0 0 1 12.75 0v.109A12.318 "
        "12.318 0 0 1 9.374 21c-2.331 0-4.512-.645-6.374-1.766Z"
    ],
    "truck": [
        "M8.25 18.75a1.5 1.5 0 0 1-3 0m3 0a1.5 1.5 0 0 0-3 0m3 0h6m-9 0H3.375a1.125 "
        "1.125 0 0 1-1.125-1.125V14.25m17.25 4.5a1.5 1.5 0 0 1-3 0m3 0a1.5 1.5 0 0 "
        "0-3 0m3 0h1.125c.621 0 1.129-.504 1.09-1.124a17.902 17.902 0 0 0-3.213-9.193 "
        "2.056 2.056 0 0 0-1.58-.86H14.25M16.5 18.75h-2.25m0-11.177v-.958c0-.568-.422"
        "-1.048-.987-1.106a48.554 48.554 0 0 0-10.026 0 1.106 1.106 0 0 0-.987 1.106"
        "v7.635m12-6.677v6.677m0 4.5v-4.5m0 0h-12"
    ],
    # ------------------------------------------------------------ status
    "question-mark-circle": [
        "M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 "
        "2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 "
        "1.827v.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 5.25h.008v.008H12v-.008Z"
    ],
    "information-circle": [
        "m11.25 11.25.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 "
        "1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9-3.75h.008v"
        ".008H12V8.25Z"
    ],
    "check-circle": ["M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"],
    "exclamation-triangle": [
        "M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 "
        "2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 "
        "16.126ZM12 15.75h.007v.008H12v-.008Z"
    ],
    "heart": [
        "M21 8.25c0-2.485-2.099-4.5-4.688-4.5-1.935 0-3.597 1.126-4.312 2.733"
        "-.715-1.607-2.377-2.733-4.313-2.733C5.1 3.75 3 5.765 3 8.25c0 7.22 9 "
        "12 9 12s9-4.78 9-12Z"
    ],
    "bell": [
        "M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75"
        "V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 "
        "5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0m5.714 0a3 3 0 1 1-5.714 "
        "0"
    ],
    "cog-6-tooth": [
        "M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 "
        "1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 "
        "1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 "
        "0 0 1-.26 1.431l-1.003.827c-.293.24-.438.613-.43.992a7.723 7.723 0 0 1 "
        "0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 "
        "2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076"
        ".124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c"
        "-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c"
        "-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72"
        "-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a"
        "1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 "
        "6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 "
        "0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356"
        ".133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644"
        "-.869l.214-1.28Z",
        "M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z",
    ],
    "arrow-right": ["M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3"],
    # ------------------------------------------------------------------ scheme
    #
    # The three colour schemes a reader can pick, one drawing each. The rays and
    # the disc of the sun are separate strokes, as are the screen and the stand.
    "sun": [
        "M12 3v2.25m6.364.386-1.591 1.591M21 12h-2.25m-.386 6.364-1.591-1.591M12 "
        "18.75V21m-4.773-4.227-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636",
        "M15.75 12a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0Z",
    ],
    "moon": [
        "M21.752 15.002A9.72 9.72 0 0 1 18 15.75c-5.385 0-9.75-4.365-9.75-9.75 0"
        "-1.33.266-2.597.748-3.752A9.753 9.753 0 0 0 3 11.25C3 16.635 7.365 21 "
        "12.75 21a9.753 9.753 0 0 0 9.002-5.998Z"
    ],
    "computer-desktop": [
        "M9 17.25v1.007a3 3 0 0 1-.879 2.122L7.5 21h9l-.621-.621A3 3 0 0 1 15 "
        "18.257V17.25",
        "M21 5.25V15a2.25 2.25 0 0 1-2.25 2.25H5.25A2.25 2.25 0 0 1 3 15V5.25m18 "
        "0A2.25 2.25 0 0 0 18.75 3H5.25A2.25 2.25 0 0 0 3 5.25m18 0V12a2.25 2.25 "
        "0 0 1-2.25 2.25H5.25A2.25 2.25 0 0 1 3 12V5.25",
    ],
    # ------------------------------------------------------------------ brands
    #
    # SOLID, not stroked. A brand mark is a shape, not a line drawing, and the
    # only faithful way to draw one is the artwork its owner publishes — so
    # these are the marks as they ship (simple-icons, CC0) and the only two
    # entries in the file that are not a 1.7-weight stroke on a 24 grid.
    "github": [
        "M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113"
        ".82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042"
        "-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 "
        "1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108"
        "-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465"
        "-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 "
        "1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 "
        "3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 "
        "1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 "
        "1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 "
        "17.592 24 12.297c0-6.627-5.373-12-12-12"
    ],
    "discord": [
        "M20.317 4.3698a19.7913 19.7913 0 0 0-4.8851-1.5152.0741.0741 0 0 0"
        "-.0785.0371c-.211.3753-.4447.8648-.6083 1.2495-1.8447-.2762-3.68-.2762"
        "-5.4868 0-.1636-.3933-.4058-.8742-.6177-1.2495a.077.077 0 0 0-.0785"
        "-.037 19.7363 19.7363 0 0 0-4.8852 1.515.0699.0699 0 0 0-.0321.0277C"
        ".5334 9.0458-.319 13.5799.0992 18.0578a.0824.0824 0 0 0 .0312.0561c"
        "2.0528 1.5076 4.0413 2.4228 5.9929 3.0294a.0777.0777 0 0 0 .0842"
        "-.0276c.4616-.6304.8731-1.2952 1.226-1.9942a.076.076 0 0 0-.0416"
        "-.1057c-.6528-.2476-1.2743-.5495-1.8722-.8923a.077.077 0 0 1-.0076"
        "-.1277c.1258-.0943.2517-.1923.3718-.2914a.0743.0743 0 0 1 .0776"
        "-.0105c3.9278 1.7933 8.18 1.7933 12.0614 0a.0739.0739 0 0 1 .0785"
        ".0095c.1202.099.246.1981.3728.2924a.077.077 0 0 1-.0066.1276 12.2986 "
        "12.2986 0 0 1-1.873.8914.0766.0766 0 0 0-.0407.1067c.3604.698.7719 "
        "1.3628 1.225 1.9932a.076.076 0 0 0 .0842.0286c1.961-.6067 3.9495"
        "-1.5219 6.0023-3.0294a.077.077 0 0 0 .0313-.0552c.5004-5.177-.8382"
        "-9.6739-3.5485-13.6604a.061.061 0 0 0-.0312-.0286zM8.02 15.3312c"
        "-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9555-2.4189 2.157-2.4189 "
        "1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.9555 2.4189-2.1569 "
        "2.4189zm7.9748 0c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9554"
        "-2.4189 2.1569-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332"
        "-.946 2.4189-2.1568 2.4189Z"
    ],
}

# The names that are ours rather than upstream's, so the gallery can say so and a
# test can check the list has not quietly grown.
LOCAL = frozenset({"pencil", "arrow-up-tray", "printer", "star"})

# The brand marks, which are filled shapes rather than strokes.
#
# Everything else here is one line drawing on a 24 grid, which is what lets a
# single set of <svg> attributes serve the whole set. A logo is not a line
# drawing and cannot be redrawn as one without becoming a different logo, so
# these two are filled and <c-n26.icon> switches its attributes for them.
# stroke_width means nothing on a solid icon and is ignored.
SOLID = frozenset({"github", "discord"})


def paths(name: str) -> list[str]:
    """The subpaths for `name`, or a loud error naming what is available.

    Loud because the alternative is an <svg> with no <path> in it: a silent gap
    in a toolbar that renders perfectly and shows nothing, which is the kind of
    thing that reaches a screenshot before it reaches anyone's attention.
    """
    try:
        return ICONS[name]
    except KeyError:
        raise KeyError(
            f"no icon {name!r}; available: {', '.join(sorted(ICONS))}"
        ) from None


def is_solid(name: str) -> bool:
    """Whether this drawing is filled rather than stroked."""
    return name in SOLID


def names() -> list[str]:
    """Every icon name, in the order the registry declares them.

    Declaration order groups them by what they are for, which is more use to
    someone reading the gallery than the alphabet would be.
    """
    return list(ICONS)
