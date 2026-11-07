"""Manager and queryset helpers for explicit history attribution."""

from django.db import models


class HistoryAwareManager(models.Manager):
    """Create and update records with explicit history attribution when supported."""

    def create_with_user(self, user=None, **kwargs):
        """Create a record through save_with_user when available, otherwise save normally.

        Default the acting user to the owner. Plain saves have no explicit
        attribution override here.
        """
        obj = self.model(**kwargs)

        if user is None and hasattr(obj, "owner") and obj.owner:
            user = obj.owner

        if hasattr(obj, "save_with_user"):
            obj.save_with_user(user=user)
        else:
            obj.save()

        return obj

    def bulk_create_with_history(self, objs, user=None, **kwargs):
        """Delegate to the model's history-aware bulk creation, or use ordinary bulk_create."""
        if hasattr(self.model, "bulk_create_with_history"):
            return self.model.bulk_create_with_history(objs, user=user, **kwargs)

        return super().bulk_create(objs, **kwargs)

    def update_with_user(self, user=None, **kwargs):
        """Update matching records; resave history-enabled instances when given a user."""
        objects_to_update = list(self.all())

        count = super().update(**kwargs)

        if user and objects_to_update:
            for obj in objects_to_update:
                obj.refresh_from_db()

                if hasattr(obj, "history"):
                    obj.save()

                    history_record = obj.history.first()
                    if history_record and not history_record.history_user:
                        history_record.history_user = user
                        history_record.save()

        return count


class HistoryAwareQuerySet(models.QuerySet):
    """Queryset helpers for explicit update and deletion attribution."""

    def update_with_user(self, user=None, **kwargs):
        """Update matching records; resave history-enabled instances when given a user."""
        objects_to_update = list(self.all())

        count = super().update(**kwargs)

        if user and objects_to_update:
            for obj in objects_to_update:
                obj.refresh_from_db()

                if hasattr(obj, "history"):
                    obj.save()

                    history_record = obj.history.first()
                    if history_record and not history_record.history_user:
                        history_record.history_user = user
                        history_record.save()

        return count

    def delete_with_user(self, user=None):
        """Delete matching records after setting _history_user on the loaded instances."""
        objects_to_delete = list(self.all())

        if user and objects_to_delete:
            for obj in objects_to_delete:
                if hasattr(obj, "history"):
                    obj._history_user = user

        return super().delete()


HistoryAwareManager = HistoryAwareManager.from_queryset(HistoryAwareQuerySet)
