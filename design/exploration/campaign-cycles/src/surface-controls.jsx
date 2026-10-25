import React, { useEffect, useId, useRef, useState } from "react";
import { EllipsisVertical, X } from "lucide-react";
import { Button, Icon, TextInput, useModal } from "./controls.jsx";
import cotton from "./cotton.json";

export function Menu({
    label = "Entry actions",
    icon = EllipsisVertical,
    text,
    children,
    viewport = false,
}) {
    const ref = useRef();
    const [open, setOpen] = useState(false);
    useEffect(() => {
        if (!open) return;
        const outside = (e) => {
            if (!e.composedPath().includes(ref.current))
                ref.current?.removeAttribute("open");
        };
        const escape = (e) => {
            if (e.key === "Escape" && ref.current?.open) {
                ref.current.removeAttribute("open");
                ref.current.querySelector("summary").focus();
            }
        };
        document.addEventListener("pointerdown", outside);
        document.addEventListener("keydown", escape);
        return () => {
            document.removeEventListener("pointerdown", outside);
            document.removeEventListener("keydown", escape);
        };
    }, [open]);
    function toggle(event) {
        const details = event.currentTarget;
        setOpen(details.open);
        if (!viewport || !details.open) return;
        const menu = details.querySelector(".history-menu-panel"),
            trigger = details.querySelector("summary");
        const box = trigger.getBoundingClientRect();
        Object.assign(menu.style, {
            position: "fixed",
            maxHeight: `${innerHeight - 32}px`,
            overflowY: "auto",
            zIndex: "100",
            right: "auto",
            bottom: "auto",
        });
        const width = menu.getBoundingClientRect().width,
            height = menu.scrollHeight;
        menu.style.left = `${Math.max(16, Math.min(box.right - width, innerWidth - width - 16))}px`;
        menu.style.top = `${box.bottom + height + 8 <= innerHeight - 16 ? box.bottom + 8 : Math.max(16, box.top - height - 8)}px`;
    }
    return (
        <details className="history-menu" ref={ref} onToggle={toggle}>
            <summary
                className={cotton.button.ghost}
                aria-label={label}
                title={label}
            >
                <Icon icon={icon} size={16} />
                {text}
            </summary>
            <div
                className="history-menu-panel"
                onClick={(e) => {
                    if (e.target.closest("button,a"))
                        ref.current.removeAttribute("open");
                }}
            >
                {children}
            </div>
        </details>
    );
}
export function Modal({ title, onClose, children }) {
    const ref = useModal(),
        id = useId();
    return (
        <dialog
            className={`${cotton.dialog.root} history-dialog`}
            ref={ref}
            aria-labelledby={id}
            onCancel={(e) => {
                e.preventDefault();
                onClose();
            }}
        >
            <header>
                <h2 id={id} className={cotton.dialog.title}>
                    {title}
                </h2>
                <Button
                    icon={X}
                    title="Close"
                    aria-label="Close"
                    onClick={onClose}
                />
            </header>
            {children}
        </dialog>
    );
}
export function Select({ label, value, onChange, options, compact = false }) {
    const id = useId();
    return (
        <label className="history-field" htmlFor={id}>
            <span className={compact ? "sr-only" : cotton.label}>{label}</span>
            <select
                id={id}
                aria-label={label}
                className={cotton.select.className}
                style={cotton.select.style}
                value={value}
                onChange={(e) => onChange(e.target.value)}
            >
                {options.map(([v, t]) => (
                    <option key={v} value={v}>
                        {t}
                    </option>
                ))}
            </select>
        </label>
    );
}
export function Input({ label, value, onChange, ...props }) {
    return (
        <label className="history-field">
            <span className={cotton.label}>{label}</span>
            <TextInput value={value} onChange={onChange} {...props} />
        </label>
    );
}
