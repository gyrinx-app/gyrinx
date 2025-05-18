from django import forms


class BsCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    template_name = "pages/forms/widgets/bs_checkbox_select.html"
    option_template_name = "pages/forms/widgets/bs_checkbox_option.html"
