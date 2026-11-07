import { useState, type FormEvent } from "react";
import { mount as mountRoot } from "../../runtime/mount";
import { ModelCard, type ModelCardData } from "../../ui";

function Demo({ card: initial }: { card: ModelCardData }) {
    const [card, setCard] = useState(initial);
    const [notice, setNotice] = useState("");
    function dismiss(event: FormEvent) {
        event.preventDefault();
        setNotice("This is a gallery example. No player data was changed.");
    }
    return (
        <div onSubmit={dismiss}>
            <ModelCard
                card={card}
                csrfToken="gallery"
                frozen={false}
                onTally={(assignment, change) => {
                    setCard((previous) => ({
                        ...previous,
                        details: previous.details.map((row) => ({
                            ...row,
                            parts: row.parts.map((part) =>
                                part.kind === "counter" &&
                                part.control?.assignment === assignment
                                    ? {
                                          ...part,
                                          value: part.value + change,
                                          control: {
                                              ...part.control,
                                              tallied:
                                                  part.control.tallied + change,
                                          },
                                      }
                                    : part,
                            ),
                        })),
                    }));
                }}
            />
            {notice && <p role="status">{notice}</p>}
        </div>
    );
}

export function mount(element: HTMLElement, props: { card: ModelCardData }) {
    return mountRoot(element, Demo, props);
}
