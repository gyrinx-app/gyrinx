import { useState } from "react";
import { Badge, Button, RadioCard, RadioCards } from "../../ui";

type KindCard = {
    value: string;
    label: string;
    description: string;
    example: string;
    checked: boolean;
};

type ScopeCard = KindCard & {
    produces: string;
    disabled: boolean;
    reason: string;
    deprecated: boolean;
};

type EffectCard = KindCard & {
    accepts: string[];
};

function checked(cards: KindCard[]) {
    return cards.find((card) => card.checked)?.value ?? "";
}

export type ModifierKindPickerProps = {
    submitLabel: string;
    served: {
        scope: string;
        effect: string;
    };
    scope: {
        name: string;
        legend: string;
        cards: ScopeCard[];
    };
    effect: {
        name: string;
        legend: string;
        cards: EffectCard[];
    };
};

export function ModifierKindPicker({
    submitLabel,
    served,
    scope,
    effect,
}: ModifierKindPickerProps) {
    const producesOf = (value: string) =>
        scope.cards.find((card) => card.value === value)?.produces ?? "";
    const fits = (value: string, produces: string) => {
        const card = effect.cards.find((entry) => entry.value === value);
        return !card || !produces || card.accepts.includes(produces);
    };
    const initialScope = checked(scope.cards);
    const [scopeValue, setScopeValue] = useState(initialScope);
    const [effectValue, setEffectValue] = useState(() => {
        const value = checked(effect.cards);
        return fits(value, producesOf(initialScope)) ? value : "";
    });
    const produces = producesOf(scopeValue);

    function chooseScope(value: string) {
        setScopeValue(value);
        setEffectValue((current) =>
            fits(current, producesOf(value)) ? current : "",
        );
    }

    return (
        <div className="space-y-4">
            <RadioCards legend={scope.legend} min="15rem">
                {scope.cards.map((card) => (
                    <RadioCard
                        key={card.value}
                        name={scope.name}
                        value={card.value}
                        label={card.label}
                        description={card.description}
                        example={card.example}
                        reason={card.reason}
                        disabled={card.disabled}
                        checked={scopeValue === card.value}
                        onChange={() => chooseScope(card.value)}
                        className="h-full"
                        flair={
                            card.deprecated ? (
                                <Badge>Deprecated</Badge>
                            ) : undefined
                        }
                    />
                ))}
            </RadioCards>
            <RadioCards legend={effect.legend} min="15rem">
                {effect.cards.map((card) => {
                    const allowed = fits(card.value, produces);
                    return (
                        <div
                            key={card.value}
                            className={
                                allowed ? "" : "pointer-events-none opacity-40"
                            }
                            aria-disabled={!allowed}
                        >
                            <RadioCard
                                name={effect.name}
                                value={card.value}
                                label={card.label}
                                description={card.description}
                                example={card.example}
                                checked={effectValue === card.value}
                                onChange={() => {
                                    if (allowed) setEffectValue(card.value);
                                }}
                                className="h-full"
                            />
                        </div>
                    );
                })}
            </RadioCards>
            <div className="flex flex-wrap items-center justify-end gap-2">
                <Button
                    type="submit"
                    variant="primary"
                    size="sm"
                    disabled={
                        scopeValue === served.scope &&
                        effectValue === served.effect
                    }
                >
                    {submitLabel}
                </Button>
            </div>
        </div>
    );
}
