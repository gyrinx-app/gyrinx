from django.apps import AppConfig


class LibraryConfig(AppConfig):
    #: The app label must stay fixed because migrations and string model references use it.
    name = "n26.library"
    label = "library"
    #: The admin index uses an edition-specific display name.
    verbose_name = "N26 · Library"
