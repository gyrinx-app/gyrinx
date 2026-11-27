import React, { useEffect, useId, useRef, useState, useMemo } from "react";
import {
    EllipsisVertical,
    X,
    Search,
    Dice1,
    Dice2,
    Dice3,
    Dice4,
    Dice5,
    Dice6,
} from "lucide-react";
import { Button, Icon, TextInput, useModal } from "./controls.jsx";
import cotton from "./cotton.json";
import * as M from "./history-model.js";
import { base, viewerLink } from "./history-format.js";
const C = cotton.history;
const diceIcons = [null, Dice1, Dice2, Dice3, Dice4, Dice5, Dice6];
export function UserLink({ id }) {
    const p = M.people[id];
    return (
        <a className="identity-user" href={viewerLink(`${base}users/${id}/`)}>
            {p.name}
            <img
                src={`/static/history/${p.badge}.svg`}
                alt={p.badgeLabel}
                title={p.badgeLabel}
            />
        </a>
    );
}
export function GangLink({ id = "nightshade" }) {
    const g = M.gangs[id];
    return (
        <a
            className="identity-gang"
            href={viewerLink(`${base}gang/${id}/`)}
            style={{ "--gang-colour": `var(--color-${g.colour}-500)` }}
        >
            <span className="gang-colour-dot" />
            <span
                className="house-icon"
                style={{ maskImage: `url(/static/history/${g.icon}.svg)` }}
                role="img"
                aria-label={g.house}
            />
            {g.name}
        </a>
    );
}
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
export function PageHeader({ title, lead, children, actions }) {
    const c = C.pageHeader;
    return (
        <header className={c.root}>
            <div className={c.breadcrumbRow}>
                <div className={c.breadcrumb}>
                    <nav aria-label="Breadcrumb" className="history-breadcrumb">
                        {children}
                    </nav>
                </div>
            </div>
            <div className={c.row}>
                <div className={c.column}>
                    <h1 className={c.title}>{title}</h1>
                    {lead && <p className={c.lead}>{lead}</p>}
                </div>
                {actions && <div className={c.actions}>{actions}</div>}
            </div>
        </header>
    );
}
export function SearchBar({ value, onChange }) {
    return (
        <div className={C.search.root} role="search">
            <div className={C.search.field}>
                <span className={C.search.icon}>
                    <Icon icon={Search} size={16} />
                </span>
                <input
                    className={C.search.input}
                    type="search"
                    aria-label="Search the history"
                    placeholder="Search the history"
                    value={value}
                    onChange={(e) => onChange(e.target.value)}
                />
            </div>
        </div>
    );
}
export function Dice({ values, mode, modifier = 0 }) {
    const figure =
        (mode === "D66"
            ? Number(values.join(""))
            : values.reduce((a, b) => a + b, 0)) + modifier;
    return (
        <span
            className="history-dice"
            aria-label={`Rolled ${mode || `${values.length}D6`}: ${values.join(", ")}; result ${figure}`}
        >
            <span aria-hidden="true">{mode || `${values.length}D6`}</span>
            {values.map((n, i) => (
                <Icon key={i} icon={diceIcons[n]} size={18} />
            ))}
            <strong aria-hidden="true">
                {modifier !== 0 && `${modifier > 0 ? "+" : ""}${modifier} = `}
                {figure}
            </strong>
        </span>
    );
}
export function Snapshot({ snapshot }) {
    return (
        <section className="snapshot-details" aria-label="Gang snapshot">
            <dl className="snapshot-figures">
                <div>
                    <dt>Gang rating</dt>
                    <dd data-testid="snapshot-rating">
                        {snapshot.rating.toLocaleString()}
                    </dd>
                </div>
                <div>
                    <dt>Credits</dt>
                    <dd>{snapshot.credits}¢</dd>
                </div>
                <div>
                    <dt>Models</dt>
                    <dd>{snapshot.models.length}</dd>
                </div>
            </dl>
            <div className="snapshot-roster">
                {snapshot.models.map((m) => (
                    <article
                        className={`${cotton.card} snapshot-model`}
                        key={m.id}
                    >
                        <header>
                            <h2>{m.name}</h2>
                            <span className={cotton.badge}>{m.status}</span>
                        </header>
                        <p className="text-sm text-muted">{m.profile}</p>
                        <dl>
                            <div>
                                <dt>Equipment</dt>
                                <dd>{m.equipment.join(", ") || "None"}</dd>
                            </div>
                            <div>
                                <dt>Skills</dt>
                                <dd>{m.skills.join(", ") || "None"}</dd>
                            </div>
                        </dl>
                    </article>
                ))}
            </div>
            <section className="snapshot-holdings">
                <div>
                    <h2>Stash</h2>
                    <p>{snapshot.stash.join(", ") || "Empty"}</p>
                </div>
                <div>
                    <h2>Territories</h2>
                    <p>{snapshot.territories.join(", ") || "None"}</p>
                </div>
                {snapshot.notes && (
                    <div>
                        <h2>Notes</h2>
                        <p>{snapshot.notes}</p>
                    </div>
                )}
            </section>
        </section>
    );
}

export function DateFilters({ values, onChange }) {
    return (
        <div className="date-filter-grid">
            {[
                ["from_date", "From date"],
                ["to_date", "To date"],
            ].map(([key, label]) => (
                <Input
                    key={key}
                    label={label}
                    type="date"
                    value={values[key] || ""}
                    onChange={(value) => onChange(key, value)}
                />
            ))}
        </div>
    );
}

export function useHistoryIndexes(root) {
    return useMemo(
        () =>
            new Map(
                [root, ...Object.values(root.otherHistories || {})].map(
                    (state) => [state.gangId, M.historyIndex(state)],
                ),
            ),
        [root],
    );
}
