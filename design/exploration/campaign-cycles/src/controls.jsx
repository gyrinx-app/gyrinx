import React, { useEffect, useId, useRef } from "react";
import cotton from "./cotton.json";

export function Icon({ icon: Component, size = 18 }) {
    return <Component size={size} strokeWidth={1.7} aria-hidden="true" />;
}

export function Button({
    variant = "ghost",
    icon,
    iconSize = 16,
    preserveSelection = false,
    children,
    ...props
}) {
    return (
        <button
            type="button"
            className={cotton.button[variant]}
            onMouseDown={
                preserveSelection
                    ? (event) => event.preventDefault()
                    : undefined
            }
            {...props}
        >
            {icon && <Icon icon={icon} size={iconSize} />}
            {children}
        </button>
    );
}

// A separate label avoids nesting a colour menu's buttons inside a label.
// Passing the same ID through custom controls preserves native label focus.
export function Field({ label, children }) {
    const id = useId();
    return (
        <div className={cotton.label}>
            <label htmlFor={id}>{label}</label>
            {React.cloneElement(children, { id, "aria-label": label })}
        </div>
    );
}

export function TextInput({ value, onChange, ...props }) {
    return (
        <div className={`${cotton.input.root} callout-input-border`}>
            <input
                className={cotton.input.control}
                value={value}
                onChange={(event) => onChange(event.target.value)}
                {...props}
            />
        </div>
    );
}

export function useModal() {
    const ref = useRef(null);
    useEffect(() => {
        const dialog = ref.current;
        dialog.showModal();
        return () => dialog.close();
    }, []);
    return ref;
}
