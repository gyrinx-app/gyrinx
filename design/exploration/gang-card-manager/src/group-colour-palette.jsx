import React from "react";
import { Check, CircleSlash2 } from "lucide-react";
import { Icon } from "./controls.jsx";
import { groupColours } from "./group-colours.js";

export function GroupColourPalette({ selected, onChange }) {
    return (
        <div className="cm-colour-swatches">
            {groupColours.map((colour) => {
                const checked =
                    selected.length > 0 &&
                    selected.every((value) => value === colour.value);
                return (
                    <button
                        type="button"
                        key={colour.value}
                        aria-label={
                            colour.value === "none"
                                ? "No colour"
                                : `${colour.name} group colour`
                        }
                        title={colour.name}
                        aria-pressed={checked}
                        style={{
                            backgroundColor: colour.token
                                ? `var(${colour.token})`
                                : "transparent",
                        }}
                        onClick={() => onChange(colour.value)}
                    >
                        {checked ? (
                            <Icon icon={Check} size={13} />
                        ) : colour.value === "none" ? (
                            <Icon icon={CircleSlash2} size={15} />
                        ) : null}
                    </button>
                );
            })}
        </div>
    );
}
