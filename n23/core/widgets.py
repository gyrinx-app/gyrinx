from django import forms


class ColorRadioSelect(forms.RadioSelect):
    """
    Custom radio select widget for choosing colors from a predefined palette.
    """

    template_name = "core/widgets/color_radio_select.html"
    option_template_name = "core/widgets/color_radio_option.html"

    # Predefined color palette — dark / base / light per hue, paired in rows of 6
    COLOR_PALETTE = [
        # Row 1: None + White
        ("", "None (Default)"),
        ("#fefdfb", "White"),
        # Row 2: Red + Yellow
        ("#90101a", "Dark Red"),
        ("#f14d4c", "Red"),
        ("#ffbab3", "Light Red"),
        ("#6c4300", "Dark Yellow"),
        ("#c57d00", "Yellow"),
        ("#f8c384", "Light Yellow"),
        # Row 3: Green + Teal
        ("#4c5300", "Dark Green"),
        ("#8d9900", "Green"),
        ("#cbd689", "Light Green"),
        ("#005c3b", "Dark Teal"),
        ("#00aa6f", "Teal"),
        ("#92e2b7", "Light Teal"),
        # Row 4: Cyan + Blue
        ("#005860", "Dark Cyan"),
        ("#00a2af", "Cyan"),
        ("#76e1ed", "Light Cyan"),
        ("#004f8b", "Dark Blue"),
        ("#0092f9", "Blue"),
        ("#a8d2ff", "Light Blue"),
        # Row 5: Violet + Rose
        ("#563199", "Dark Violet"),
        ("#9b6efa", "Violet"),
        ("#d1c4ff", "Light Violet"),
        ("#811968", "Dark Rose"),
        ("#da52b5", "Rose"),
        ("#fbb4e2", "Light Rose"),
    ]

    def __init__(self, attrs=None):
        super().__init__(attrs=attrs, choices=self.COLOR_PALETTE)

    def create_option(
        self, name, value, label, selected, index, subindex=None, attrs=None
    ):
        option = super().create_option(
            name, value, label, selected, index, subindex, attrs
        )
        # Add the color value to the option context for use in the template
        option["color"] = value
        option["label"] = label  # Ensure label is available for tooltip
        return option
