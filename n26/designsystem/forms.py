from django import forms

from n26.core.widgets import RichText

#: The gang types offered on the create form. The real one reads
#: ``n26.library.GangType``; a gallery has to render on an empty database, so this
#: is the same list the dashboard's filter uses, kept here rather than imported
#: from sampledata so the form is a form and not a fixture.
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


class CreateGangForm(forms.Form):
    """Founding a gang: what it is called, what it is, and two optional things.

    Four fields, and the interesting one is ``starting_credits``. Blank does not
    mean zero and does not mean "use a default" — it means no limit, which is how
    people play a first game before anyone has agreed a budget. So it is
    ``required=False`` with no ``initial``: a default of 1000 would quietly pick
    a house rule for the reader, and ``min_value=0`` still lets someone say a
    deliberate nothing.
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
            "What the gang is, which fixes who you can hire and what they may carry."
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
        help_text="Shown against the gang wherever it is listed.",
    )


def create_gang_form():
    """Unbound, for the gallery. The page is a blank form, so it shows one."""
    return CreateGangForm()


def failed_create_gang_form():
    """The same form with the mistakes people actually make.

    A name left empty and credits typed as a negative — both real validation,
    read off ``form.errors`` by c-ui.field, so the demo cannot claim an error
    state the components do not really produce.
    """
    form = CreateGangForm(
        data={"name": "", "gang_type": "escher", "starting_credits": "-50"}
    )
    form.is_valid()  # populate .errors
    return form


class HireFighterForm(forms.Form):
    """Naming a fighter on the way in. One field, and it is optional.

    Blocking a hire on a name would slow the common case, which is buying three
    Gangers and naming them once they have done something worth naming. So
    ``required=False`` — and the label says so, because a reader cannot tell an
    optional field from one they have not reached yet.

    The profile is not a field here. It arrives as the name and value of
    whichever Hire button was pressed, which is why this form has no submit of
    its own; see <c-n26.view.fighter-hire>.
    """

    name = forms.CharField(
        max_length=100,
        required=False,
        label="Name",
        help_text="Optional — you can name them later.",
    )


def hire_fighter_form():
    """Unbound, for the gallery."""
    return HireFighterForm()


def create_gang_context():
    """Everything the create-gang demos need, in one place.

    Two views render them — the component page and the bare view preview — and
    a form built in one and forgotten in the other is a page that renders an
    empty select and looks like a bug in the component.
    """
    return {
        "create_gang_form": create_gang_form(),
        "failed_create_gang_form": failed_create_gang_form(),
        "gang_types": GANG_TYPES,
        "hire_fighter_form": hire_fighter_form(),
    }


class SignupForm(forms.Form):
    """A deliberately-failing form, so the error demos show real Django errors.

    c-ui.error and c-ui.field read straight off a form instance, and a
    hand-written string wouldn't exercise that path — including the ``__all__``
    lookup for non-field errors.
    """

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
    """The editor demos' form.

    Unbound and never submitted — the gallery only needs a widget to render. Its
    ``media`` is what carries TinyMCE onto the page, which is why the view hands
    the whole form to the template rather than just the field.
    """

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

    # One field per demo on purpose. A bound field carries its own id, so
    # rendering the same one twice puts two textareas with the same id on the
    # page — and TinyMCE keys editors by id, so the second silently loses.
    preview = forms.CharField(
        widget=RichText(),
        required=False,
        label="Try switching",
        initial=(
            "<p>Edit this, then hit <strong>Preview</strong>. The preview reads "
            "the editor's live content, so it follows what you type.</p>"
        ),
    )

    notes = forms.CharField(widget=RichText(), required=False)


# What a hostile editor payload looks like on the way out. Rendered through
# safe_rich_text in the demo, beside the raw source, so the difference is the
# point rather than a claim.
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
