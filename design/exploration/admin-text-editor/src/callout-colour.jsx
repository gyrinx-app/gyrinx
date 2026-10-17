import React, { useEffect, useId, useRef, useState } from "react";
import cotton from "./cotton.json";

const colours = [
    { name: "Gyrinx default", value: "default" },
    ...cotton.colours.map((colour) => ({
        ...colour,
        value: colour.name.toLowerCase(),
    })),
];
export function CalloutColour({ value, onChange, ...props }) {
    const [open, setOpen] = useState(false),
        [active, setActive] = useState(0);
    const menuID = useId();
    const root = useRef(null),
        trigger = useRef(null),
        options = useRef([]);
    const selected =
        colours.find((colour) => colour.value === value) || colours[0];
    const close = () => {
        setOpen(false);
        trigger.current.focus();
    };
    const choose = (colour) => {
        onChange(colour.value);
        close();
    };
    useEffect(() => {
        if (!open) return;
        options.current[active]?.focus();
        const outside = (event) => {
            if (!event.composedPath().includes(root.current)) setOpen(false);
        };
        document.addEventListener("pointerdown", outside, true);
        return () => document.removeEventListener("pointerdown", outside, true);
    }, [open, active]);
    function show() {
        setActive(
            Math.max(
                0,
                colours.findIndex((colour) => colour.value === value),
            ),
        );
        setOpen(true);
    }
    return (
        <div
            ref={root}
            className="callout-colour"
            onBlur={(event) => {
                if (
                    event.relatedTarget &&
                    !root.current.contains(event.relatedTarget)
                )
                    setOpen(false);
            }}
        >
            <button
                ref={trigger}
                type="button"
                className={`${cotton.select.className} callout-colour-trigger`}
                style={{
                    ...cotton.select.style,
                    color: selected.token
                        ? `var(${selected.token})`
                        : "inherit",
                }}
                role="combobox"
                aria-haspopup="listbox"
                aria-expanded={open}
                aria-controls={open ? menuID : undefined}
                {...props}
                onClick={() => (open ? close() : show())}
                onKeyDown={(event) => {
                    if (["ArrowDown", "ArrowUp"].includes(event.key)) {
                        event.preventDefault();
                        show();
                    }
                }}
            >
                {selected.name}
            </button>
            {open && (
                <div
                    id={menuID}
                    className="callout-colour-options"
                    role="listbox"
                    aria-label="Callout colours"
                    onKeyDown={(event) => {
                        const moves = {
                            ArrowDown: Math.min(colours.length - 1, active + 1),
                            ArrowUp: Math.max(0, active - 1),
                            Home: 0,
                            End: colours.length - 1,
                        };
                        if (Object.hasOwn(moves, event.key)) {
                            event.preventDefault();
                            setActive(moves[event.key]);
                        }
                        if (event.key === "Escape") {
                            event.preventDefault();
                            event.stopPropagation();
                            close();
                        }
                    }}
                >
                    {colours.map((colour, index) => (
                        <button
                            ref={(element) =>
                                (options.current[index] = element)
                            }
                            key={colour.value}
                            type="button"
                            role="option"
                            aria-selected={value === colour.value}
                            tabIndex={index === active ? 0 : -1}
                            className={cotton.button.ghost}
                            style={{
                                color: colour.token
                                    ? `var(${colour.token})`
                                    : "inherit",
                            }}
                            onFocus={() => setActive(index)}
                            onClick={() => choose(colour)}
                        >
                            {colour.name}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}
