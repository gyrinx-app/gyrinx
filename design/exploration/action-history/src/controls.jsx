import React, { useEffect, useRef } from "react";
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

export function TextInput({ value, onChange, ...props }) {
    return (
        <div className={`${cotton.input.root} history-input-border`}>
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
