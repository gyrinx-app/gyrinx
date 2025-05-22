"""
Mixin to add SimpleHistory tracking with proper user tracking to models.
"""

from django.db import models


class HistoryMixin(models.Model):
    """
    Mixin that adds history tracking to models with proper user tracking.

    This mixin ensures that:
    1. All changes are tracked in history
    2. The user who made the change is recorded (when available from request)
    3. Provides helper methods for working with history

    Note: If your model already has `history = HistoricalRecords()` defined,
    this mixin will not override it. The mixin just provides the helper methods.
    """

    class Meta:
        abstract = True

    def save_with_user(self, user=None, **kwargs):
        """
        Save the model and explicitly set the history user.

        If no user is provided and the object has an owner, the owner will be
        used as the history user.

        This is useful when saving outside of a request context where
        the middleware can't determine the user.
        """
        # If no user provided but object has an owner, use the owner
        if user is None and hasattr(self, "owner") and self.owner:
            user = self.owner

        # Save the model first
        super().save(**kwargs)

        # If a user was provided, update the history record
        if user and hasattr(self, "history"):
            # Get the most recent history record
            history_record = self.history.first()
            if history_record and not history_record.history_user:
                history_record.history_user = user
                history_record.save()

    def get_history_diff(self, history_record=None):
        """
        Get the differences between this history record and the previous one.

        Returns a dict of {field_name: (old_value, new_value)} for changed fields.
        """
        if history_record is None:
            history_record = self.history.first()

        if not history_record:
            return {}

        # Get the previous record
        previous = self.history.filter(
            history_date__lt=history_record.history_date
        ).first()

        if not previous:
            # This is the first record, show all fields as changed
            diff = {}
            for field in self._meta.fields:
                if field.name not in ["id", "created", "modified"]:
                    diff[field.name] = (None, getattr(history_record, field.name))
            return diff

        # Compare fields
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
        """
        Perform bulk_create but also create history records.

        If no user is provided and the objects have owners, the owner will be
        used as the history user for each object.

        Django's bulk_create doesn't trigger save() signals, so SimpleHistory
        doesn't track these by default. This method creates the objects and
        then manually creates history records.
        """
        # Import here to avoid circular imports
        from simple_history.utils import bulk_create_with_history

        # Use SimpleHistory's utility if available
        if hasattr(cls, "history"):
            # Set the history user on each object
            for obj in objs:
                # If no user provided but object has an owner, use the owner
                history_user = user
                if history_user is None and hasattr(obj, "owner") and obj.owner:
                    history_user = obj.owner

                if history_user:
                    obj._history_user = history_user

            return bulk_create_with_history(objs, cls, **kwargs)
        else:
            # Fallback to regular bulk_create
            return cls.objects.bulk_create(objs, **kwargs)

    @classmethod
    def bulk_update_with_history(cls, objs, fields, user=None, **kwargs):
        """
        Perform bulk_update but also create history records.

        Similar to bulk_create_with_history, this ensures history is tracked
        for bulk updates.
        """
        # Import here to avoid circular imports
        from simple_history.utils import bulk_update_with_history

        # Use SimpleHistory's utility if available
        if hasattr(cls, "history"):
            # Set the history user on each object if provided
            if user:
                for obj in objs:
                    obj._history_user = user

            return bulk_update_with_history(objs, cls, fields, **kwargs)
        else:
            # Fallback to regular bulk_update
            return cls.objects.bulk_update(objs, fields, **kwargs)
