from django import forms

from n26.core.forms import NOTES_EDITOR_HEIGHT
from n26.core.widgets import RichText

from . import sampledata

#: Static gang types let the gallery render without library records.
GANG_TYPES = [
    ("ash-waste-nomads", "Ash Wastes Nomads (BotO)"),
    ("delaque", "Delaque (HoS)"),
    ("escher", "Escher (HoB)"),
    ("goliath", "Goliath (HoC)"),
    ("ironhead-squats", "Ironhead Squats (HotA)"),
    ("underhive-outcasts", "Underhive Outcasts"),
    ("van-saar", "Van Saar (HoA)"),
    ("venators", "Venators (AN)"),
]

#: Include cards with and without artwork to exercise both layouts.
GANG_TYPE_ICONS = {"goliath": sampledata.SAMPLE_GANG_ICON}

#: Omit two budgets to exercise cards with no budget description.
GANG_TYPE_BUDGETS = {
    "ash-waste-nomads": 1000,
    "delaque": 1000,
    "escher": 1000,
    "goliath": 1000,
    "ironhead-squats": 1200,
    "van-saar": 1000,
}


def gang_type_cards(chosen=""):
    """Build gallery type cards without querying the library, using the production context
    structure.
    """
    return [
        {
            "value": value,
            "label": label,
            "icon": GANG_TYPE_ICONS.get(value, ""),
            "description": (
                f"Founding budget {GANG_TYPE_BUDGETS[value]:,}¢"
                if value in GANG_TYPE_BUDGETS
                else ""
            ),
            "checked": value == chosen,
        }
        for value, label in GANG_TYPES
    ]


class CreateGangForm(forms.Form):
    """Gallery founding form. Blank starting credits means no spending limit; zero remains
    a valid explicit limit.
    """

    name = forms.CharField(
        max_length=100,
        label="Gang name",
        help_text="You can change this later.",
    )
    gang_type = forms.ChoiceField(
        choices=GANG_TYPES,
        label="Gang type",
        help_text=(
            "What the gang is. It decides who you can hire and what they can carry."
        ),
    )
    starting_credits = forms.IntegerField(
        required=False,
        min_value=0,
        label="Starting credits",
        help_text="Leave blank to spend as much as you like.",
    )
    colour = forms.CharField(
        required=False,
        label="Colour",
        help_text="Shown next to the gang's name wherever it is listed.",
    )


def create_gang_form():
    """Return an unbound gallery founding form."""
    return CreateGangForm()


def failed_create_gang_form():
    """Bind invalid name and credit values so field components display Django's validation
    errors.
    """
    form = CreateGangForm(
        data={"name": "", "gang_type": "escher", "starting_credits": "-50"}
    )
    form.is_valid()  # populate .errors
    return form


class HireFighterForm(forms.Form):
    """Optional fighter name for gallery hire forms. The selected profile comes from the
    clicked Hire button in c-n26.view.fighter-hire.
    """

    name = forms.CharField(
        max_length=100,
        required=False,
        label="Name",
        help_text="Optional — you can name them later.",
    )


def hire_fighter_form():
    """Return an unbound gallery hire form."""
    return HireFighterForm()


def create_gang_context():
    """Share form and type-card context between the component gallery and standalone
    preview.
    """
    return {
        "create_gang_form": create_gang_form(),
        "failed_create_gang_form": failed_create_gang_form(),
        "gang_types": gang_type_cards(),
        # Preserve the selected type in the validation-error demo.
        "failed_gang_types": gang_type_cards(chosen="escher"),
        "hire_fighter_form": hire_fighter_form(),
    }


class SignupForm(forms.Form):
    """Produce field and non-field Django errors for c-ui.error and c-ui.field demos."""

    email = forms.EmailField()
    password = forms.CharField(min_length=12, widget=forms.PasswordInput)

    def clean(self):
        raise forms.ValidationError(
            "That email and password combination isn't recognised."
        )


def bound_signup_form():
    form = SignupForm(data={"email": "not-an-email", "password": "short"})  # nosec B105 - demo data
    form.is_valid()  # populate .errors
    return form


class RichTextForm(forms.Form):
    """Provide unbound editor widgets and TinyMCE media for gallery previews."""

    body = forms.CharField(
        widget=RichText(),
        required=False,
        initial=(
            "<h2>Rust in Peace</h2>"
            "<p>A <strong>Goliath</strong> gang working the eastern sumps. "
            "Six fighters, two in recovery.</p>"
            "<ul><li>Kaine — Leader, 145 credits</li>"
            "<li>Vex — Champion, 110 credits</li></ul>"
            "<blockquote>Nobody digs deeper.</blockquote>"
        ),
    )

    # Use a distinct field per demo because TinyMCE identifies editors by their textarea
    # IDs.
    preview = forms.CharField(
        widget=RichText(),
        required=False,
        label="Try switching",
        initial=(
            "<p>Edit this, then hit <strong>Preview</strong>. The preview reads "
            "the editor's live content, so it follows what you type.</p>"
        ),
    )

    # Match the model page's separate notes and lore editors, including the notes height
    # limit.
    notes = forms.CharField(widget=RichText(height=NOTES_EDITOR_HEIGHT), required=False)
    lore = forms.CharField(widget=RichText(), required=False)


# Display this payload beside its safe_rich_text output to demonstrate sanitisation.
UNSAFE_HTML = (
    "<h3>Perfectly ordinary heading</h3>"
    '<p>Body text with a <a href="https://example.com">real link</a>.</p>'
    "<script>alert('stolen cookies')</script>"
    '<p><a href="javascript:alert(1)">Click me</a></p>'
    '<img src="x" onerror="alert(\'xss\')" alt="broken image">'
    '<iframe src="https://evil.example"></iframe>'
    '<p style="color: green; behavior: url(evil.htc)">Styled, mostly allowed.</p>'
    "<!-- an internal comment nobody should see -->"
)
