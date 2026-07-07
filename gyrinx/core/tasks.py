import logging
from collections import defaultdict

import requests
from django.conf import settings
from django.tasks import task

logger = logging.getLogger(__name__)


@task
def hello_world(name: str = "World"):
    """Demo task for testing the task framework."""
    logger.info(f"Hello, {name}!")
    return f"Greeted {name}"


@task
def refresh_list_facts(list_id: str):
    """
    Refresh the cached facts for a list by recalculating from database.

    Called asynchronously when facts_with_fallback detects a dirty cache.
    """
    from gyrinx.core.models import List

    try:
        lst: List = List.objects.with_related_data(with_fighters=True).get(pk=list_id)
        lst.facts_from_db(update=True)
        logger.info(f"Refreshed facts for list {list_id}")
    except List.DoesNotExist:
        logger.warning(f"List {list_id} not found for facts refresh")


@task
def propagate_content_cost_change(
    content_type_id: int,
    object_id: str,
    before_snapshots: dict | None = None,
    old_cost: int | None = None,
):
    """Recalculate cached costs and create audit actions for a content cost change.

    Enqueued (after commit) when a content model's cost field changes. Re-fetches
    the instance via its ContentType + pk, then runs the existing
    ``_create_content_cost_change_actions`` helper, which finds every affected
    list, recalculates its facts with the new cost, and creates a
    CONTENT_COST_CHANGE action (applying credit adjustments in campaign mode).

    ``before_snapshots`` is the ``{str(list_id): [rating, stash]}`` map captured
    synchronously at enqueue time (pre-change baselines). The helper uses it as
    the delta baseline so a list viewed (and lazily recalculated) before this
    task runs doesn't cause a zero delta — which would silently drop the action
    and the campaign credit adjustment.

    Running this off the request thread is the whole point: a popular base item
    can touch thousands of lists, and the recalculation walks each list's full
    fighter suite. Doing it inline in the admin save blew the request budget.

    Idempotent within a delta branch: the per-row path's second rewrite is a
    zero delta and skips out; the snapshot path skips a list that already has
    a matching applied action (same subject + same pre-change baseline). A
    redelivery that FLIPS branches — a mid-window mutation changed which rows
    are pinned — can still book a second action. Robust cross-branch
    idempotency needs a delivery token on the action; that is deliberately
    NOT bundled into a cost-programme phase — it is a redelivery-hardening
    job in its own right. Operationally: run the Phase 8 backfill (the
    largest branch-flip window there is) in a quiet window, away from
    content edits. References to deleted instances are handled gracefully
    (the instance lookup returns and the task is a no-op).
    """
    from django.contrib.contenttypes.models import ContentType

    from gyrinx.content.models.signal_handlers import (
        _create_content_cost_change_actions,
    )

    try:
        content_type = ContentType.objects.get_for_id(content_type_id)
    except ContentType.DoesNotExist:
        logger.warning(
            "propagate_content_cost_change: unknown content_type_id %s",
            content_type_id,
        )
        return

    model_class = content_type.model_class()
    if model_class is None:
        logger.warning(
            "propagate_content_cost_change: content_type %s has no model class",
            content_type_id,
        )
        return

    # Use all_content() where available so pack-scoped content still resolves
    # (the default ContentManager excludes pack items); fall back to the default
    # manager for any sender without it.
    manager = model_class._default_manager
    base_qs = (
        manager.all_content() if hasattr(manager, "all_content") else manager.all()
    )
    try:
        instance = base_qs.get(pk=object_id)
    except model_class.DoesNotExist:
        logger.warning(
            "propagate_content_cost_change: %s %s no longer exists",
            content_type,
            object_id,
        )
        return

    _create_content_cost_change_actions(
        instance, before_snapshots=before_snapshots, old_cost=old_cost
    )


@task
def propagate_default_child_fighter_assignment(default_assignment_id: str):
    """Propagate a newly-created child-spawning default to existing gangs.

    When a pack author adds a ``ContentFighterDefaultAssignment`` whose
    equipment spawns a child fighter (a vehicle / exotic beast), every gang
    already subscribed to a pack containing that fighter type — and holding a
    list-fighter of that type — should get the child fighter materialised, not
    just gangs created after the change (issue #1725).

    Idempotent: re-running is safe (the materialisation helper skips disabled
    and already-materialised defaults).
    """
    from django.contrib.contenttypes.models import ContentType
    from django.db import transaction

    from gyrinx.content.models.default_assignment import (
        ContentFighterDefaultAssignment,
    )
    from gyrinx.content.models.fighter import ContentFighter
    from gyrinx.core.models.action import ListActionType
    from gyrinx.core.models.list import (
        ListFighter,
        _materialise_child_fighter_defaults,
    )
    from gyrinx.core.models.pack import CustomContentPackItem

    try:
        default = ContentFighterDefaultAssignment.objects.get(pk=default_assignment_id)
    except ContentFighterDefaultAssignment.DoesNotExist:
        logger.warning(
            f"Default assignment {default_assignment_id} not found for propagation"
        )
        return

    # Re-verify at execution time: the profile may have been removed between
    # enqueue and run. Only child-spawning defaults need materialising.
    if not default.equipment.contentequipmentfighterprofile_set.exists():
        return

    # Packs containing this fighter type. This is a subscriber read path, so we
    # must NOT filter `archived` on the pack or pack item — archived content
    # stays visible to gangs already subscribed (see CLAUDE.md "Content packs:
    # archive semantics", issue #1742).
    fighter_ct = ContentType.objects.get_for_model(ContentFighter)
    pack_ids = list(
        CustomContentPackItem.objects.filter(
            content_type=fighter_ct, object_id=default.fighter_id
        )
        .values_list("pack_id", flat=True)
        .distinct()
    )
    if not pack_ids:
        return

    # Affected list-fighters: of this fighter type, on lists subscribed to a
    # pack that contains the fighter. Legacy-only fighters
    # (legacy_content_fighter) are a documented gap — the materialisation
    # helper acts on content_fighter defaults only, matching the hire-time
    # path.
    affected = (
        ListFighter.objects.filter(
            content_fighter=default.fighter,
            archived=False,
            list__packs__in=pack_ids,
        )
        .select_related("list")
        .distinct()
    )

    # Group by list so we create at most one action per affected gang.
    fighters_by_list: dict[str, list] = defaultdict(list)
    for fighter in affected:
        fighters_by_list[fighter.list_id].append(fighter)

    equipment_name = default.equipment.name

    propagated_count = 0
    for list_id, fighters in fighters_by_list.items():
        try:
            with transaction.atomic():
                created_total = 0
                for fighter in fighters:
                    created_total += _materialise_child_fighter_defaults(fighter)

                # Idempotent no-op: already materialised on every fighter.
                if created_total == 0:
                    continue

                # affected is select_related("list"), so reuse the loaded
                # instance rather than re-fetching the list.
                lst = fighters[0].list

                # Keep the list's cached rating/stash consistent.
                old_rating = lst.rating_current
                old_stash = lst.stash_current
                facts = lst.facts_from_db(update=True)
                rating_delta = facts.rating - old_rating
                stash_delta = facts.stash - old_stash

                # Awareness-only action. Materialising a child-spawning default
                # has a net-zero cost impact (the default is virtual/0-cost, the
                # direct assignment uses cost_override=0, and child fighters
                # don't contribute to list cost), so we never charge or refund
                # credits — even in campaign mode. We still log it so gang
                # owners see why a new fighter appeared.
                lst.create_action(
                    action_type=ListActionType.CONTENT_COST_CHANGE,
                    description=f"Pack added a default {equipment_name}",
                    rating_before=old_rating,
                    stash_before=old_stash,
                    rating_delta=rating_delta,
                    stash_delta=stash_delta,
                    credits_delta=0,
                    update_credits=False,
                    skip_apply=["rating", "stash"],
                )
                propagated_count += 1
        except Exception:
            logger.exception(
                f"Failed to propagate default {default_assignment_id} to list {list_id}"
            )

    logger.info(
        f"Propagated default {default_assignment_id}: "
        f"materialised on {propagated_count} list(s), "
        f"checked {len(fighters_by_list)}"
    )


@task
def trigger_discord_issue_action(
    channel_id: str,
    message_id: str,
    guild_id: str,
    interaction_token: str,
    application_id: str,
    message_content: str,
    message_author: str,
    requesting_user: str,
):
    """
    Trigger a GitHub Action to create an issue from a Discord message.

    Adds a 👀 reaction to the original message, then sends a repository_dispatch
    event to gyrinx-app/gyrinx. The GitHub Action fetches the full thread/reply
    chain, calls Claude to summarise, creates the issue, posts a visible reply
    with the link, and deletes the ephemeral "thinking" message (or updates it
    on failure).
    """
    # React with 👀 to signal the message is being processed
    _add_discord_reaction(channel_id, message_id)

    token = settings.GITHUB_DISPATCH_TOKEN
    if not token:
        logger.error("No GITHUB_DISPATCH_TOKEN configured")
        _update_discord_message(
            application_id,
            interaction_token,
            "Failed to create issue: GitHub integration not configured.",
        )
        return

    try:
        response = requests.post(
            "https://api.github.com/repos/gyrinx-app/gyrinx/dispatches",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={
                "event_type": "discord-issue-request",
                "client_payload": {
                    "channel_id": channel_id,
                    "message_id": message_id,
                    "guild_id": guild_id,
                    "interaction_token": interaction_token,
                    "application_id": application_id,
                    "message_content": message_content,
                    "message_author": message_author,
                    "requesting_user": requesting_user,
                },
            },
            timeout=30,
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to reach GitHub API: {e}")
        _update_discord_message(
            application_id,
            interaction_token,
            "Failed to create issue: could not reach GitHub.",
        )
        return

    if response.status_code == 204:
        logger.info(
            f"Triggered GitHub Action for Discord message {message_id} "
            f"in channel {channel_id}"
        )
    else:
        logger.error(
            f"Failed to trigger GitHub Action: {response.status_code} {response.text}"
        )
        _update_discord_message(
            application_id,
            interaction_token,
            "Failed to create issue: could not trigger GitHub Action.",
        )


def _add_discord_reaction(channel_id: str, message_id: str):
    """Add a 👀 reaction to a Discord message to signal processing."""
    bot_token = settings.DISCORD_BOT_TOKEN
    if not bot_token:
        logger.warning("No DISCORD_BOT_TOKEN configured, skipping reaction")
        return

    try:
        response = requests.put(
            f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}/reactions/%F0%9F%91%80/@me",
            headers={"Authorization": f"Bot {bot_token}"},
            timeout=10,
        )
        if response.status_code not in (200, 204):
            logger.warning(
                f"Failed to add reaction: {response.status_code} {response.text}"
            )
    except Exception as e:
        logger.warning(f"Failed to add Discord reaction: {e}")


def _update_discord_message(application_id: str, interaction_token: str, content: str):
    """Update a deferred Discord interaction response."""
    try:
        requests.patch(
            f"https://discord.com/api/v10/webhooks/{application_id}/{interaction_token}/messages/@original",
            json={"content": content},
            timeout=10,
        )
    except Exception as e:
        logger.error(f"Failed to update Discord message: {e}")


def _update_backfill(
    backfill_id, summary_patch=None, status=None, error="", summary_extend=None
):
    """Merge progress into a Backfill audit record's summary.

    Maintenance operations run as self-re-enqueueing task chains; the
    Backfill row (created by the admin trigger) is their progress surface —
    the /admin/maintenance/backfill/<id>/ page shows the merged summary.

    ``summary_patch`` replaces keys; ``summary_extend`` *appends* rows to
    list-valued keys (e.g. the growing per-list detail), accumulated under the
    same row lock so re-enqueue forks don't race. Appends stay idempotent in
    practice: a redelivered batch re-reconciles already-corrected lists, which
    no longer move, so they contribute no new rows.

    Returns ``True`` only when this call actually transitions the record from a
    non-terminal state to DONE — i.e. the first, real completion. Callers use
    that to fire one-shot completion work (e.g. notifications) exactly once, so
    a redelivered final batch re-entering the DONE path doesn't repeat it.
    """
    if backfill_id is None:
        return False
    from django.db import transaction as db_transaction

    from gyrinx.core.models import Backfill

    with db_transaction.atomic():
        try:
            # Locked: Pub/Sub is at-least-once, so a redelivered batch can
            # fork the chain — two copies writing this record concurrently.
            backfill = Backfill.objects.select_for_update().get(pk=backfill_id)
        except Backfill.DoesNotExist:
            logger.warning("Backfill record %s missing; progress dropped", backfill_id)
            return False
        if backfill.status == Backfill.Status.CANCELLED:
            # CANCELLED is sticky: once an operator stops a run, NOTHING may
            # overwrite it — not even a lagging final batch's DONE/FAILED write
            # (that batch passed its top-of-batch cancel check before the cancel
            # landed, so it still tries to complete). Cancel always wins.
            logger.info(
                "Backfill %s is cancelled; dropping write (attempted status=%s)",
                backfill_id,
                status or "progress",
            )
            return False
        was_terminal = backfill.status in (Backfill.Status.DONE, Backfill.Status.FAILED)
        if was_terminal and (status is None or status == Backfill.Status.RUNNING):
            # Never let a lagging fork's progress write un-terminate a
            # DONE/FAILED record.
            logger.warning(
                "Backfill %s already %s; dropping non-terminal progress write",
                backfill_id,
                backfill.status,
            )
            return False
        if summary_patch:
            backfill.summary = {**backfill.summary, **summary_patch}
        if summary_extend:
            for key, rows in summary_extend.items():
                backfill.summary[key] = backfill.summary.get(key, []) + list(rows)
        if status:
            backfill.status = status
        if error:
            backfill.error = error
        backfill.save()
        return status == Backfill.Status.DONE and not was_terminal


def _is_cancelled(backfill_id):
    """True if an operator has cancelled this run (records the stop request on
    the Backfill row). The self-re-enqueueing task chains check this at the top
    of each batch and bail, so a cancel takes effect within one batch —
    no infra intervention needed."""
    if backfill_id is None:
        return False
    from gyrinx.core.models import Backfill

    return Backfill.objects.filter(
        pk=backfill_id, status=Backfill.Status.CANCELLED
    ).exists()


@task
def reconcile_all_lists(
    after_id: str | None = None,
    batch_size: int = 25,
    backfill_id: str | None = None,
    user_id: int | None = None,
    list_id: str | None = None,
    lists_done: int = 0,
    corrected: int = 0,
    clamped: int = 0,
):
    """Audited cache reconciliation across every list (#1826 §4.8.2).

    The task-runner twin of `manage reconcile_lists`, for environments with
    no shell (Cloud Run): triggered from /admin/maintenance/, walks lists in
    pk order in small batches, runs the reconcile core on each, and reports
    progress into the Backfill record. RECONCILE actions attribute to the
    triggering admin via ``user_id``.

    Self-re-enqueues with a pk cursor; the counters ride the kwargs so the
    summary is cumulative. Each list whose cached totals actually changed (a
    player-visible change) is appended to the Backfill record's ``per_list``
    summary — the audit surface the /admin/maintenance detail page renders, and
    the source the completion step reads to notify each affected owner and
    arbitrator exactly once (#721). Persisting it on the record (rather than
    threading it through the task payload) keeps the payload bounded and makes
    the run auditable while it's still in flight.
    """
    from django.contrib.auth import get_user_model

    from gyrinx.core.cost.reconcile import reconcile_list
    from gyrinx.core.models import Backfill
    from gyrinx.core.models.list import List

    user = None
    if user_id is not None:
        user = get_user_model().objects.filter(pk=user_id).first()

    # Cooperative cancel: bail before doing any work if an operator stopped the
    # run. The chain dies here rather than re-enqueueing the next batch.
    if _is_cancelled(backfill_id):
        logger.info(
            "reconcile_all_lists: cancelled (backfill %s); stopping", backfill_id
        )
        return

    qs = List.objects.order_by("id")
    if list_id:
        # Incremental rollout: scope the whole run to one list.
        qs = qs.filter(pk=list_id)
    if after_id:
        qs = qs.filter(id__gt=after_id)
    batch = list(qs.values_list("id", flat=True)[:batch_size])

    batch_moved = []  # per-list detail for the lists THIS batch actually moved
    try:
        for batch_list_id in batch:
            lst_obj = List.objects.get(pk=batch_list_id)
            result = reconcile_list(lst_obj, user=user)
            lists_done += 1
            if result.moved or result.action:
                corrected += 1
            if result.moved:
                # Player-visible change: record before/after so the detail page
                # and the notifications can show what moved. An action without
                # `moved` is a ledger-only alignment nobody sees, so it's excluded.
                batch_moved.append(
                    {
                        "list_id": str(batch_list_id),
                        "list_name": lst_obj.name,
                        "rating_before": result.rating_before,
                        "rating_after": result.rating_after,
                        "stash_before": result.stash_before,
                        "stash_after": result.stash_after,
                        "audit_action_id": str(result.action.id)
                        if result.action
                        else None,
                    }
                )
            if result.clamped:
                clamped += 1
                logger.warning(
                    "reconcile_all_lists: zero-floor clamp fired on list %s "
                    "— computed total was negative; investigate.",
                    batch_list_id,
                )
    except Exception as e:
        logger.exception("reconcile_all_lists: failed on batch after %s", after_id)
        # Mark FAILED and RETURN (ack): raising would 500 the push handler
        # and Pub/Sub — with no dead-letter topic — would redeliver the batch
        # forever, contradicting the "re-trigger" instruction below. The
        # chain genuinely stops here; re-triggering starts a fresh run.
        _update_backfill(
            backfill_id,
            {"lists": lists_done, "corrected": corrected, "clamped": clamped},
            status=Backfill.Status.FAILED,
            error=f"Failed in batch after cursor {after_id}: {e}. "
            "Fix the cause and re-trigger.",
            summary_extend={"per_list": batch_moved},
        )
        return

    progress = {
        "lists": lists_done,
        "corrected": corrected,
        "clamped": clamped,
        "cursor": str(batch[-1]) if batch else None,
    }
    if len(batch) == batch_size:
        _update_backfill(
            backfill_id, progress, summary_extend={"per_list": batch_moved}
        )
        reconcile_all_lists.enqueue(
            after_id=str(batch[-1]),
            batch_size=batch_size,
            backfill_id=backfill_id,
            user_id=user_id,
            list_id=list_id,
            lists_done=lists_done,
            corrected=corrected,
            clamped=clamped,
        )
    else:
        just_completed = _update_backfill(
            backfill_id,
            progress,
            status=Backfill.Status.DONE,
            summary_extend={"per_list": batch_moved},
        )
        logger.info(
            "reconcile_all_lists: complete — %s lists, %s corrected, %s clamped",
            lists_done,
            corrected,
            clamped,
        )
        # Tell affected people once, aggregated: one notification per owner and
        # one per arbitrator, each summarising every gang that actually changed
        # (#721). Read the whole run's per-list detail back off the record, so a
        # player who owns several corrected gangs gets a single message.
        #
        # Gate on the real RUNNING->DONE transition: Pub/Sub is at-least-once,
        # so a redelivered final batch re-enters this branch — `just_completed`
        # is False the second time, so nobody is notified twice. This is also
        # why notifications require a Backfill record (the admin trigger always
        # creates one; the dev-only management command reconciles directly and
        # doesn't notify). Never let a notification failure undo the reconcile.
        if just_completed:
            try:
                from gyrinx.core.cost.reconcile_notify import notify_lists_reconciled

                record = Backfill.objects.filter(pk=backfill_id).first()
                per_list = record.summary.get("per_list", []) if record else []
                deltas = {
                    row["list_id"]: [
                        row["rating_after"] - row["rating_before"],
                        row["stash_after"] - row["stash_before"],
                    ]
                    for row in per_list
                }
                owners, arbs = notify_lists_reconciled(deltas)
                logger.info(
                    "reconcile_all_lists: notified %s owner(s), %s arbitrator(s)",
                    owners,
                    arbs,
                )
            except Exception:
                logger.exception(
                    "reconcile_all_lists: notification fan-out failed (reconcile "
                    "itself completed)"
                )


@task
def backfill_pins(
    after_id: str | None = None,
    batch_size: int = 250,
    failed_so_far: int = 0,
    backfill_id: str | None = None,
    processed_so_far: int = 0,
    pinned_so_far: int = 0,
    list_id: str | None = None,
):
    """Write acquisition receipts onto every legacy assignment (#1826 §4.8.4).

    Walks all assignments in pk order (archived included — a later unarchive
    must find correct amounts), calling the same `pin_assignment` choke point
    acquisition uses, so there is exactly one pinning implementation. The
    choke point is idempotent (already-pinned rows untouched) and skips the
    anchored/frozen rows that must stay UNPINNED, so re-running is safe and
    "resume" is just re-enqueueing with the cursor.

    Value- and cache-neutral by construction: each amount equals what live
    resolution returns at that instant, so no ListActions and no wealth
    movement. Run the audited reconcile (core/cost/reconcile.py) across
    lists FIRST — freezing amounts on top of drifted caches would enshrine
    the drift (§4.8.2).

    Self-re-enqueues with a pk cursor until the table is exhausted.
    """
    from gyrinx.core.cost.pinning import pin_assignment
    from gyrinx.core.models.list import ListFighterEquipmentAssignment

    # Cooperative cancel: bail before doing any work if an operator stopped the
    # run. The chain dies here rather than re-enqueueing the next batch.
    if _is_cancelled(backfill_id):
        logger.info("backfill_pins: cancelled (backfill %s); stopping", backfill_id)
        return

    qs = ListFighterEquipmentAssignment.objects.order_by("id")
    if list_id:
        # Incremental rollout: scope the walk to one list's gear.
        qs = qs.filter(list_fighter__list_id=list_id)
    if after_id:
        qs = qs.filter(id__gt=after_id)
    batch = list(qs.values_list("id", flat=True)[:batch_size])

    pinned = 0
    failed = 0
    attempted = 0
    consecutive_failures = 0
    last_success_id = after_id
    for assignment_id in batch:
        attempted += 1
        try:
            pinned += pin_assignment(assignment_id)
            consecutive_failures = 0
            last_success_id = assignment_id
        except Exception:
            failed += 1
            consecutive_failures += 1
            logger.exception("backfill_pins: failed to pin %s", assignment_id)
            if consecutive_failures >= 25:
                # A systemic pinning bug should stop the walk, not log its
                # way through the whole table. The advertised resume cursor
                # is the last SUCCESS: after_id is exclusive (id__gt), so
                # resuming from the failed id would skip it.
                logger.error(
                    "backfill_pins: aborting after %s consecutive failures "
                    "at %s. Fix the cause, then re-enqueue with "
                    "after_id=%s (idempotent).",
                    consecutive_failures,
                    assignment_id,
                    last_success_id,
                )
                from gyrinx.core.models import Backfill

                _update_backfill(
                    backfill_id,
                    {
                        "processed": processed_so_far + attempted,
                        "rows_pinned": pinned_so_far + pinned,
                        "failed": failed_so_far + failed,
                        "cursor": str(last_success_id) if last_success_id else None,
                    },
                    status=Backfill.Status.FAILED,
                    error=(
                        f"Aborted: {consecutive_failures} consecutive "
                        f"failures at {assignment_id}. Fix the cause and "
                        f"re-trigger (idempotent; resumes past pinned rows)."
                    ),
                )
                return

    total_failed = failed_so_far + failed
    total_processed = processed_so_far + len(batch)
    total_pinned = pinned_so_far + pinned
    progress = {
        "processed": total_processed,
        "rows_pinned": total_pinned,
        "failed": total_failed,
        "cursor": str(batch[-1]) if batch else None,
    }
    if len(batch) == batch_size:
        logger.info(
            "backfill_pins: processed %s assignments (%s rows pinned, "
            "%s failed so far), cursor %s",
            len(batch),
            pinned,
            total_failed,
            batch[-1],
        )
        # Failed rows stay UNPINNED and are deliberately walked past — the
        # cursor must not stall on a poisoned row (that would livelock the
        # chain). The recovery path is the idempotent re-run, which retries
        # exactly the still-unpinned rows; the consecutive-failure breaker
        # above handles systemic breakage.
        # Prod (Pub/Sub): fire-and-forget publish — flat chain. Dev/test
        # (ImmediateBackend): this recurses, one frame per batch; fine for
        # dev-sized tables, use the management command for bulk local runs.
        _update_backfill(backfill_id, progress)
        backfill_pins.enqueue(
            after_id=str(batch[-1]),
            batch_size=batch_size,
            failed_so_far=total_failed,
            backfill_id=backfill_id,
            processed_so_far=total_processed,
            pinned_so_far=total_pinned,
            list_id=list_id,
        )
    elif total_failed:
        logger.warning(
            "backfill_pins: walk COMPLETE with %s failed row(s) left "
            "UNPINNED — check the per-row exceptions above, fix the cause, "
            "and re-run (idempotent: only still-unpinned rows are retried).",
            total_failed,
        )
        from gyrinx.core.models import Backfill

        _update_backfill(
            backfill_id,
            progress,
            status=Backfill.Status.FAILED,
            error=(
                f"Walk complete but {total_failed} row(s) failed and remain "
                "unpinned. Fix the cause and re-trigger (idempotent)."
            ),
        )
    else:
        logger.info(
            "backfill_pins: walk complete, %s rows pinned total.",
            total_pinned,
        )
        from gyrinx.core.models import Backfill

        _update_backfill(backfill_id, progress, status=Backfill.Status.DONE)
