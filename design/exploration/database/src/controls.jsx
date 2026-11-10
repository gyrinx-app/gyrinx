import React from "react";
import cotton from "./cotton.json";
export function Icon({ icon: Component, size = 18 }) {
    return <Component size={size} strokeWidth={1.7} aria-hidden="true" />;
}
export function Button({
    variant = "ghost",
    icon,
    iconSize = 16,
    children,
    ...props
}) {
    return (
        <button type="button" className={cotton.button[variant]} {...props}>
            {icon && <Icon icon={icon} size={iconSize} />} {children}
        </button>
    );
}
