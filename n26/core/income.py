"""Income breakdowns from the contributions that remain after computation."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class IncomePart:
    label: str
    amount: int
    detail: str = ""
    replaced: bool = False


@dataclass(frozen=True)
class IncomeSource:
    name: str
    value: int
    parts: tuple[IncomePart, ...]


def income_explanation(value, *, sources=(), adjustment=0, asset=False):
    props = {
        "value": value,
        "contributed": value - adjustment,
        "adjustment": adjustment,
        "sources": [
            {
                "name": source.name,
                "value": source.value,
                "parts": [asdict(part) for part in source.parts],
            }
            for source in sources
        ],
    }
    if asset:
        props.update(currency=True, showAdjustment=False)
    return props


def _income_contributions(contributions):
    from n26.library.income import is_income_counter

    return [
        contribution
        for contribution in contributions
        if is_income_counter(contribution.counter)
    ]


def is_base_income_contribution(asset, contribution, *, direct):
    """The declared baseline, or an ordinary baseline carried directly."""
    from n26.library.income import income_modifiers

    modifier_id = getattr(contribution.modifier, "pk", None)
    declared = getattr(asset, "base_income_modifier_id", None)
    if declared is not None and modifier_id == declared:
        return True
    return contribution.carrier_key == direct and modifier_id in {
        modifier.pk for modifier in income_modifiers(asset)
    }


def _asset_source(
    asset, name, contributions, *, direct, override_id=None, counter=None
):
    from n26.core.effects import ModifierIndex
    from n26.library.income import income_modifiers

    base_modifiers = income_modifiers(asset)
    if counter is not None:
        base_modifiers = [
            modifier
            for modifier in base_modifiers
            if ModifierIndex.key(modifier.contributes_to_counter.counter)
            == ModifierIndex.key(counter)
        ]
    base = []
    overrides = []
    boons = []
    for contribution in contributions:
        modifier_id = getattr(contribution.modifier, "pk", None)
        if is_base_income_contribution(asset, contribution, direct=direct):
            if contribution.applied_override is not None:
                overrides.append(contribution)
            else:
                base.append(contribution)
        elif (
            contribution.carrier_key == direct
            and override_id
            and modifier_id == override_id
        ):
            overrides.append(contribution)
        else:
            detail = (
                str(contribution.modifier)
                if contribution.carrier_key == direct and contribution.modifier
                else contribution.source
            )
            boons.append(IncomePart("Boon", contribution.amount, detail=detail))
    parts = []
    if overrides:
        parts.append(
            IncomePart(
                "Base income",
                sum(
                    modifier.contributes_to_counter.amount
                    for modifier in base_modifiers
                ),
                replaced=True,
            )
        )
        parts.append(
            IncomePart("Income override", sum(item.amount for item in overrides))
        )
    elif base:
        parts.append(IncomePart("Base income", sum(item.amount for item in base)))
    parts.extend(sorted(boons, key=lambda part: (part.detail.casefold(), part.amount)))
    if not parts:
        parts.append(IncomePart("Base income", 0))
    return IncomeSource(
        name=name,
        value=sum(contribution.amount for contribution in contributions),
        parts=tuple(parts),
    )


def _holding_source(holding, contributions, *, counter=None):
    from n26.core.effects import ModifierIndex

    return _asset_source(
        holding.asset,
        str(holding),
        contributions,
        direct=ModifierIndex.key(holding),
        override_id=holding.income_override_id,
        counter=counter,
    )


def asset_assignment_income_sources(computed):
    """Each owned asset occurrence, including its selected and derived effects."""
    from n26.core.effects import (
        ModifierIndex,
        counter_contributions_by_asset_assignment,
    )
    from n26.library.models import Asset

    grouped = counter_contributions_by_asset_assignment(computed)
    return {
        node.key: _asset_source(
            node.assignable,
            node.name,
            _income_contributions(grouped.get(node.key, ())),
            direct=ModifierIndex.key(node.assignable),
        )
        for node in computed.card.all_nodes()
        if isinstance(node.assignable, Asset)
        and not node.suppressed
        and not node.broadcast
    }


def holding_income_sources(computed):
    """Every current holding, using its hydrated catalogue and settled effects."""
    from n26.core.effects import counter_contributions_by_holding

    grouped = counter_contributions_by_holding(computed)
    return {
        (holding.pk, holding.ownership_revision): _holding_source(
            holding,
            _income_contributions(
                grouped.get((holding.pk, holding.ownership_revision), ())
            ),
        )
        for holding in computed.card.holdings
    }


def income_sources(computed, contributions, *, counter):
    """Named sources for one exact counter reading, including possessions."""
    from n26.core.effects import (
        ModifierIndex,
        counter_contributions_by_asset_assignment,
        counter_contributions_by_holding,
    )
    from n26.library.income import is_income_contribution
    from n26.library.models import Asset

    selected = {
        id(contribution): contribution
        for contribution in contributions
        if ModifierIndex.key(contribution.counter) == ModifierIndex.key(counter)
    }
    by_holding = counter_contributions_by_holding(computed)
    sources = []
    for holding in computed.card.holdings:
        address = (holding.pk, holding.ownership_revision)
        held = [
            selected.pop(id(contribution))
            for contribution in by_holding.get(address, ())
            if id(contribution) in selected
        ]
        if held:
            sources.append(
                (str(address), _holding_source(holding, held, counter=counter))
            )
    by_assignment = counter_contributions_by_asset_assignment(computed)
    for node in computed.card.all_nodes():
        if not isinstance(node.assignable, Asset) or node.suppressed or node.broadcast:
            continue
        owned = [
            selected.pop(id(contribution))
            for contribution in by_assignment.get(node.key, ())
            if id(contribution) in selected
        ]
        if owned:
            sources.append(
                (
                    str(node.key),
                    _asset_source(
                        node.assignable,
                        node.name,
                        owned,
                        direct=ModifierIndex.key(node.assignable),
                        counter=counter,
                    ),
                )
            )
    other = {}
    for contribution in selected.values():
        key = (contribution.carrier_key, contribution.root_key, contribution.source)
        other.setdefault(key, []).append(contribution)
    for key, contributed in other.items():
        base = []
        parts = []
        for contribution in contributed:
            if (
                contribution.carrier_key
                and contribution.carrier_key[0] == Asset._meta.label_lower
                and contribution.modifier
                and is_income_contribution(contribution.modifier)
            ):
                base.append(contribution)
            else:
                if contribution.per_counter is not None:
                    parts.append(
                        IncomePart(
                            str(contribution.per_counter),
                            contribution.amount,
                            detail=f"{contribution.per_counter_value} × {contribution.modifier.contributes_to_counter.amount}¢",
                        )
                    )
                else:
                    parts.append(
                        IncomePart(
                            "Modifier",
                            contribution.amount,
                            detail=str(contribution.modifier)
                            if contribution.modifier
                            else contribution.source,
                        )
                    )
        if base:
            parts.insert(
                0, IncomePart("Base income", sum(item.amount for item in base))
            )
        sources.append(
            (
                str(key),
                IncomeSource(
                    name=contributed[0].source,
                    value=sum(item.amount for item in contributed),
                    parts=tuple(parts),
                ),
            )
        )
    return [
        source
        for _, source in sorted(
            sources, key=lambda pair: (pair[1].name.casefold(), pair[0])
        )
    ]


def unclaimed_income_source(holding, modifiers=None):
    """An unclaimed holding has catalogue Income or its explicit override."""
    from n26.library.income import income_of

    base = income_of(holding.asset, modifiers)
    parts = [IncomePart("Base income", base, replaced=bool(holding.income_override_id))]
    value = base
    if holding.income_override_id:
        value = holding.income_override.contributes_to_counter.amount
        parts.append(IncomePart("Income override", value))
    return IncomeSource(str(holding), value, tuple(parts))
