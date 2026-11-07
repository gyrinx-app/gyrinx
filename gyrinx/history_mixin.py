"""Explicit attribution and bulk-write helpers for models with SimpleHistory."""

from django.db import models


class HistoryMixin(models.Model):
    """Helpers for models that declare their own HistoricalRecords field.

    This abstract mixin does not install history tracking itself.
    """

    class Meta:
        abstract = True

    def save_with_user(self, user=None, **kwargs):
        """Save, then fill an unattributed latest history record with the acting user.

        Default to the model's owner when no user is supplied.
        """
        if user is None and hasattr(self, "owner") and self.owner:
            user = self.owner

        super().save(**kwargs)

        if user and hasattr(self, "history"):
            history_record = self.history.first()
            if history_record and not history_record.history_user:
                history_record.history_user = user
                history_record.save()

    def get_history_diff(self, history_record=None):
        """Return changed fields as {name: (old, new)}, excluding id and timestamps.

        Default to the latest history record. Without a previous record, compare
        all included fields against None.
        """
        if history_record is None:
            history_record = self.history.first()

        if not history_record:
            return {}

        previous = self.history.filter(
            history_date__lt=history_record.history_date
        ).first()

        if not previous:
            diff = {}
            for field in self._meta.fields:
                if field.name not in ["id", "created", "modified"]:
                    diff[field.name] = (None, getattr(history_record, field.name))
            return diff

        diff = {}
        for field in self._meta.fields:
            if field.name not in ["id", "created", "modified"]:
                old_value = getattr(previous, field.name)
                new_value = getattr(history_record, field.name)
                if old_value != new_value:
                    diff[field.name] = (old_value, new_value)

        return diff

    @classmethod
    def bulk_create_with_history(cls, objs, user=None, **kwargs):
        """Use SimpleHistory's bulk creation when the model has history, otherwise ordinary bulk_create.

        Set each object's history user from the supplied user or its owner.
        """
        from simple_history.utils import bulk_create_with_history

        if hasattr(cls, "history"):
            for obj in objs:
                history_user = user
                if history_user is None and hasattr(obj, "owner") and obj.owner:
                    history_user = obj.owner

                if history_user:
                    obj._history_user = history_user

            return bulk_create_with_history(objs, cls, **kwargs)
        else:
            return cls.objects.bulk_create(objs, **kwargs)

    @classmethod
    def bulk_update_with_history(cls, objs, fields, user=None, **kwargs):
        """Use SimpleHistory's bulk update when the model has history, otherwise ordinary bulk_update.

        Apply the supplied user to each object before the history-aware update.
        """
        from simple_history.utils import bulk_update_with_history

        if hasattr(cls, "history"):
            if user:
                for obj in objs:
                    obj._history_user = user

            return bulk_update_with_history(objs, cls, fields, **kwargs)
        else:
            return cls.objects.bulk_update(objs, fields, **kwargs)
