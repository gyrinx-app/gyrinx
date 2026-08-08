from django.apps import AppConfig


class LibraryConfig(AppConfig):
    #: The label is pinned so relocating this package (top-level today,
    #: perhaps under gyrinx/ at the merge) never touches migrations or
    #: the "library.Profile" string references — labels are what those
    #: care about, not import paths.
    name = "n26.library"
    label = "library"
    #: Edition-prefixed for the admin index, as on N26Config. Display
    #: only — the label above is the contract.
    verbose_name = "N26 · Library"
