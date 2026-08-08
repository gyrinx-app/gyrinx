from django.apps import AppConfig


class DesignSystemConfig(AppConfig):
    name = "n26.designsystem"
    #: Pinned like the others — the label is the contract.
    label = "designsystem"
    verbose_name = "N26 · Design system"
