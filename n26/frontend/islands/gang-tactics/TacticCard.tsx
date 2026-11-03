import { useRef, type CSSProperties } from "react";
import { Icon } from "../../ui";
import { useFittedRules } from "./useFittedRules";
import { TacticNotes } from "./TacticNotes";

export type Card = {
    pk: string;
    name: string;
    table_name: string;
    dice_label: string;
    roll: number;
    /** The tactic the notes are kept against. */
    tactic: string;
    /** The owner's saved tactics notes, cleaned by the server. */
    notes: string;
    /** A suggested summary to start notes from, escaped by the server. */
    suggested_notes: string;
    developed: boolean;
    reference: string;
    tableKey: string;
    /** Drawn as a bonus, outside the ranks' allowance. */
    bonus?: boolean;
    gangIcon?: string;
};
const referenceText = (reference: string) =>
    reference.replace(/^(Pages?\s+[\d/–—, -]+?)\s+-\s+(.+)$/i, "$2 · $1");

export function TacticCard({
    card,
    selected,
    printView,
    onToggle,
    notes,
}: {
    card: Card;
    selected: boolean;
    printView: boolean;
    onToggle: () => void;
    /** For the owner: where and how this card's notes are saved. */
    notes?: {
        saveUrl: string;
        csrfToken: string;
        editorScript: string;
        onSaved: (notes: string) => void;
    };
}) {
    const content = useRef<HTMLDivElement>(null);
    // A printed card shrinks its notes to fit; on screen the box scrolls,
    // and a printed card without notes has only lines to draw.
    useFittedRules(content, card.notes, printView && Boolean(card.notes));
    const gangIcon = card.gangIcon ? (
        <span
            className="n26-tactic-gang-icon"
            role="img"
            aria-label={
                card.table_name === "Universal"
                    ? "Custom gang"
                    : `${card.table_name} gang`
            }
            title={
                card.table_name === "Universal"
                    ? "Universal tactics"
                    : `${card.table_name} tactics`
            }
            style={
                {
                    "--tactic-gang-icon": `url("${card.gangIcon}")`,
                } as CSSProperties
            }
        />
    ) : null;
    const gangDetails = (
        <div className="n26-tactic-identity">
            {gangIcon}
            <div className="n26-tactic-identity-copy">
                <span>{card.table_name} gang tactics</span>
                <span
                    className="n26-tactic-roll"
                    aria-label={`${card.dice_label} roll ${card.roll}`}
                >
                    <span>{card.dice_label}</span>
                    <span aria-hidden="true">·</span>
                    <span>{card.roll}</span>
                    {card.developed && <span>· Developed</span>}
                </span>
            </div>
        </div>
    );
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
            <header className="n26-tactic-header">
                <div className="n26-tactic-nameplate">
                    <h3 id={`tactic-${card.pk}`} title={card.name}>
                        {card.name}
                    </h3>
                    {card.bonus && (
                        <span className="n26-tactic-bonus">Bonus card</span>
                    )}
                </div>
            </header>
            <div className="n26-tactic-content" ref={content}>
                <div className="n26-tactic-rules">
                    {printView ? (
                        card.notes ? (
                            // Cleaned by the server (clean_tactics_notes).
                            <div
                                className="n26-tactic-notes-box"
                                dangerouslySetInnerHTML={{ __html: card.notes }}
                            />
                        ) : (
                            <div
                                className="n26-tactic-notes-lines"
                                aria-label="Space for notes"
                            />
                        )
                    ) : (
                        <TacticNotes
                            name={card.name}
                            notes={card.notes}
                            suggested={card.suggested_notes}
                            saveUrl={notes?.saveUrl}
                            csrfToken={notes?.csrfToken}
                            editorScript={notes?.editorScript}
                            onSaved={notes?.onSaved}
                            gangDetails={gangDetails}
                        />
                    )}
                </div>
                {printView && (
                    <div className="n26-tactic-print-gang">{gangDetails}</div>
                )}
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
