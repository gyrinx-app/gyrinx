"""
Custom manager that ensures history user is tracked even outside request context.
"""

from django.db import models


class HistoryAwareManager(models.Manager):
    """
    A custom manager that works with SimpleHistory to ensure user tracking.

    This manager provides methods that automatically track the user who made
    changes, even when operating outside of a request context.
    """

    def create_with_user(self, user=None, **kwargs):
        """
        Create an object and ensure the history user is set.

        If no user is provided and the object has an owner, the owner will be
        used as the history user.

        Args:
            user: The user making the change (optional)
            **kwargs: Fields for the new object

        Returns:
            The created object
        """
        obj = self.model(**kwargs)

        # If no user provided but object has an owner, use the owner
        if user is None and hasattr(obj, "owner") and obj.owner:
            user = obj.owner

        # If model has save_with_user method, use it
        if hasattr(obj, "save_with_user"):
            obj.save_with_user(user=user)
        else:
            obj.save()

        return obj

    def bulk_create_with_history(self, objs, user=None, **kwargs):
        """
        Bulk create objects with history tracking.

        Uses SimpleHistory's bulk_create_with_history if available.
        """
        # Try to use the model's method if it exists
        if hasattr(self.model, "bulk_create_with_history"):
            return self.model.bulk_create_with_history(objs, user=user, **kwargs)

        # Otherwise fall back to regular bulk_create
        return super().bulk_create(objs, **kwargs)

    def update_with_user(self, user=None, **kwargs):
        """
        Update objects and track the user who made the change.

        This is a QuerySet-level update that also creates history records.
        """
        # Get the objects that will be updated
        objects_to_update = list(self.all())

        # Perform the update
        count = super().update(**kwargs)

        # Create history records for each updated object
        if user and objects_to_update:
            for obj in objects_to_update:
                # Refresh from DB to get updated values
                obj.refresh_from_db()

                # Create a history record with the user
                if hasattr(obj, "history"):
                    # Force a save to create history record
                    obj.save()

                    # Update the history record with user
                    history_record = obj.history.first()
                    if history_record and not history_record.history_user:
                        history_record.history_user = user
                        history_record.save()

        return count


class HistoryAwareQuerySet(models.QuerySet):
    """
    Custom QuerySet that provides history-aware methods.
    """

    def update_with_user(self, user=None, **kwargs):
        """
        Update objects in the queryset and track the user.
        """
        # Get the objects that will be updated
        objects_to_update = list(self.all())

        # Perform the update
        count = super().update(**kwargs)

        # Create history records for each updated object
        if user and objects_to_update:
            for obj in objects_to_update:
                # Refresh from DB to get updated values
                obj.refresh_from_db()

                # Create a history record with the user
                if hasattr(obj, "history"):
                    # Force a save to create history record
                    obj.save()

                    # Update the history record with user
                    history_record = obj.history.first()
                    if history_record and not history_record.history_user:
                        history_record.history_user = user
                        history_record.save()

        return count

    def delete_with_user(self, user=None):
        """
        Delete objects and track the user who deleted them.
        """
        # Get the objects that will be deleted
        objects_to_delete = list(self.all())

        # Create history records before deletion
        if user and objects_to_delete:
            for obj in objects_to_delete:
                if hasattr(obj, "history"):
                    # The delete signal will create a history record
                    # We need to set up the user before deletion
                    obj._history_user = user

        # Perform the deletion
        return super().delete()


# Combine manager and queryset
HistoryAwareManager = HistoryAwareManager.from_queryset(HistoryAwareQuerySet)
