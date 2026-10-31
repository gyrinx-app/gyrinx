import { useRef } from "react";
import { Icon } from "../../ui";
import { useFittedRules } from "./useFittedRules";

type Words = { text: string; keyword: boolean };
export type Card = {
    pk: string;
    name: string;
    table_name: string;
    dice_label: string;
    roll: number;
    timing: Words[];
    effect: Words[];
    developed: boolean;
    reference: string;
    tableKey: string;
    /** Drawn as a bonus, outside the ranks' allowance. */
    bonus?: boolean;
};
const words = (runs: Words[]) => runs.map((run) => run.text).join("");
const referenceText = (reference: string) =>
    reference.replace(/^(Pages?\s+[\d/–—, -]+?)\s+-\s+(.+)$/i, "$2 · $1");

export function TacticCard({
    card,
    selected,
    printView,
    onToggle,
}: {
    card: Card;
    selected: boolean;
    printView: boolean;
    onToggle: () => void;
}) {
    const content = useRef<HTMLDivElement>(null);
    useFittedRules(content, card);
    return (
        <article
            className="n26-tactic-card"
            data-tactic-card={card.name}
            aria-labelledby={`tactic-${card.pk}`}
            role={printView ? undefined : "checkbox"}
            aria-checked={printView ? undefined : selected}
            tabIndex={printView ? undefined : 0}
            onClick={printView ? undefined : () => onToggle()}
            onKeyDown={
                printView
                    ? undefined
                    : (event) => {
                          if (event.key === " " || event.key === "Enter") {
                              event.preventDefault();
                              event.stopPropagation();
                              onToggle();
                          }
                      }
            }
        >
            <header className="n26-tactic-nameplate">
                <h3 id={`tactic-${card.pk}`} title={card.name}>
                    {card.name}
                </h3>
            </header>
            <div className="n26-tactic-content" ref={content}>
                <div className="n26-tactic-rules">
                    {card.timing.length > 0 && (
                        <div className="n26-tactic-rule">
                            <h4>Timing</h4>
                            <p>{words(card.timing)}</p>
                        </div>
                    )}
                    {card.effect.length > 0 && (
                        <div className="n26-tactic-rule">
                            <h4>Effect</h4>
                            <p>{words(card.effect)}</p>
                        </div>
                    )}
                    {card.bonus && (
                        <p className="n26-tactic-bonus">Bonus card</p>
                    )}
                </div>
            </div>
            <div className="n26-tactic-strip">
                <span>
                    {card.table_name} gang tactics
                    {card.developed ? " · Developed" : ""}
                </span>
                <span className="n26-tactic-roll">
                    {card.dice_label} <strong>{card.roll}</strong>
                </span>
            </div>
            {card.reference && (
                <footer className="n26-tactic-footer">
                    <Icon name="book-open" strokeWidth={1.7} />
                    <p>{referenceText(card.reference)}</p>
                </footer>
            )}
        </article>
    );
}
