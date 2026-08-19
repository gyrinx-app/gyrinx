"""A spreadsheet an author has uploaded, waiting to be previewed and imported.

Not content. Nothing here belongs to a pack, nothing here is ever shown to a
player, and deleting everything an import wrote leaves these rows untouched —
they are the files, not the rows the files became.

They exist because a preview and the import that follows it have to read the
same bytes. A browser will not let a server fill a file input back in, so a
page that previewed an upload and then asked for the file again was asking the
author to promise it was the same one, once per sheet, for as long as it took
to read the preview. Holding the upload makes preview and import two readings
of one thing, and it lets a preview be looked at twice, or tomorrow.

An upload belongs to whoever sent it: two authors working at once each get
their own set of sheets rather than one quietly replacing the other's. One
sheet of each kind is held at a time — uploading the Equipment sheet again is
how a corrected export replaces a wrong one, which is the whole working
rhythm while an edition is being built.
"""

from django.db import models

from n26.core.models import Base, Owned
from n26.library.sheets import SHEET_CHOICES

#: Where a held sheet is written inside the site's storage. Uploads land on a
#: name of their own, so replacing a sheet never overwrites the bytes a
#: preview somewhere else is still reading.
UPLOAD_PREFIX = "ingest-sheets/"

#: What one sheet may weigh. The whole catalogue is a few hundred kilobytes of
#: text, so this refuses the mistaken upload — a workbook, an image, a video —
#: long before anything tries to read it as CSV.
MAX_SHEET_BYTES = 8 * 1024 * 1024


class UploadedSheet(Base, Owned):
    """One pre-ingest spreadsheet, held between being uploaded and imported."""

    sheet = models.CharField(
        max_length=32,
        choices=SHEET_CHOICES,
        help_text="Which of the pre-ingest sheets this file is.",
    )
    filename = models.CharField(
        max_length=255,
        help_text="The name the file arrived under, shown so an author can "
        "tell one export from another.",
    )
    file = models.FileField(
        upload_to=UPLOAD_PREFIX,
        help_text="The uploaded CSV, kept so a preview and the import after "
        "it read the same bytes.",
    )
    lines = models.PositiveIntegerField(
        default=0,
        help_text="Data lines the file holds, counted when it arrived.",
    )

    class Meta:
        verbose_name = "uploaded sheet"
        verbose_name_plural = "uploaded sheets"
        ordering = ["sheet"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "sheet"],
                name="one_held_sheet_of_each_kind_per_author",
            )
        ]

    def __str__(self):
        return f"{self.sheet}: {self.filename}"

    def text(self):
        """The file's contents as text.

        ``utf-8-sig`` because a spreadsheet exported from a desktop program
        writes a byte order mark, and it would otherwise arrive stuck to the
        first column heading, where no sheet reader would recognise it.
        """
        with self.file.open("rb") as handle:
            return handle.read().decode("utf-8-sig")

    def delete(self, *args, **kwargs):
        """Take the stored file with the row.

        A queryset delete goes round this, so held sheets are removed one at a
        time — five files is not worth a bulk path that leaks bytes.
        """
        stored = self.file.name
        result = super().delete(*args, **kwargs)
        if stored:
            self.file.storage.delete(stored)
        return result
