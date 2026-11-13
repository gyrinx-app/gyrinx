import React, {
    useEffect,
    useLayoutEffect,
    useRef,
    useState,
    useId,
} from "react";
import { View, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "./controls.jsx";
import { GroupBoxes } from "./group-boxes.jsx";
import * as M from "./card-manager-model.js";
import { readRosterView } from "./roster-view-model.js";
export { rosterRows } from "./roster-view-model.js";

const STORAGE = "gyrinx-roster-view-v1";
export function useRosterView(onNotice) {
    const [view, update] = useState(() => {
        try {
            return readRosterView(localStorage.getItem(STORAGE));
        } catch {
            return readRosterView(null);
        }
    });
    function setView(next) {
        update(next);
        try {
            localStorage.setItem(STORAGE, JSON.stringify(next));
        } catch {
            onNotice(
                "View settings last for this visit only. Browser storage is unavailable.",
            );
        }
    }
    return [view, setView];
}

export function ViewControls({ view, onChange }) {
    const [open, setOpen] = useState(false);
    const root = useRef(null),
        trigger = useRef(null),
        panel = useRef(null);
    const id = useId();
    useEffect(() => {
        if (!open) return;
        [...panel.current.querySelectorAll("input:not(:disabled), button")]
            .find((control) => control.getClientRects().length)
            ?.focus();
        const outside = (event) => {
            if (!event.composedPath().includes(root.current)) setOpen(false);
        };
        document.addEventListener("pointerdown", outside);
        return () => document.removeEventListener("pointerdown", outside);
    }, [open]);
    return (
        <div
            className="roster-view-control"
            ref={root}
            onBlur={(event) => {
                if (
                    event.relatedTarget &&
                    !event.currentTarget.contains(event.relatedTarget)
                )
                    setOpen(false);
            }}
            onKeyDown={(event) => {
                if (event.key === "Escape") {
                    event.stopPropagation();
                    setOpen(false);
                    trigger.current.focus();
                }
            }}
        >
            <Button
                ref={trigger}
                icon={View}
                variant="default"
                aria-label="View controls"
                title="View controls"
                aria-expanded={open}
                aria-controls={id}
                aria-haspopup="dialog"
                onClick={() => setOpen(!open)}
            />
            {open && (
                <div
                    ref={panel}
                    id={id}
                    role="dialog"
                    aria-label="Roster view"
                    className="roster-view-menu"
                >
                    <h2>Roster view</h2>
                    <fieldset className="roster-size-control">
                        <legend>Resize cards</legend>
                        <div className="roster-size-options">
                            {["small", "standard", "large"].map((size) => (
                                <label key={size}>
                                    <input
                                        type="radio"
                                        name="card-size"
                                        value={size}
                                        checked={view.size === size}
                                        onChange={() =>
                                            onChange({ ...view, size })
                                        }
                                    />
                                    <span>
                                        {size[0].toUpperCase() + size.slice(1)}
                                    </span>
                                </label>
                            ))}
                        </div>
                        <p>Change card width. Text stays the same size.</p>
                    </fieldset>
                    <p className="roster-size-mobile">
                        Cards fit the screen on mobile.
                    </p>
                    <label className="roster-view-choice">
                        <input
                            type="checkbox"
                            checked={view.sideScroll}
                            onChange={(event) =>
                                onChange({
                                    ...view,
                                    sideScroll: event.target.checked,
                                })
                            }
                        />
                        <span>Side-scroll mode</span>
                    </label>
                    <label className="roster-view-choice">
                        <input
                            type="checkbox"
                            disabled={!view.sideScroll}
                            checked={view.separateGroups}
                            onChange={(event) =>
                                onChange({
                                    ...view,
                                    separateGroups: event.target.checked,
                                })
                            }
                        />
                        <span>Separate rows by group</span>
                    </label>
                </div>
            )}
        </div>
    );
}

export function CarouselRow({ row, children, onEditGroup, saved }) {
    const [mounted, setMounted] = useState(false);
    useLayoutEffect(() => setMounted(true), []);
    const track = useRef(null),
        regionId = useId();
    const [position, setPosition] = useState({ index: 0, total: 0, end: true });
    const [dragging, setDragging] = useState(false);
    function cards() {
        return [...track.current.children].filter(
            (card) => card.matches(".gang-card") && !card.hidden,
        );
    }
    function measure() {
        const el = track.current,
            visible = cards();
        const left = el.getBoundingClientRect().left;
        let index = 0,
            distance = Infinity;
        visible.forEach((card, i) => {
            const next = Math.abs(card.getBoundingClientRect().left - left - 8);
            if (next < distance) {
                index = i;
                distance = next;
            }
        });
        const next = {
            index,
            total: visible.length,
            end: el.scrollLeft >= el.scrollWidth - el.clientWidth - 2,
        };
        setPosition((previous) =>
            previous.index === next.index &&
            previous.total === next.total &&
            previous.end === next.end
                ? previous
                : next,
        );
    }
    useLayoutEffect(() => {
        measure();
        const observer = new ResizeObserver(measure);
        observer.observe(track.current);
        [...track.current.children].forEach((card) => observer.observe(card));
        return () => observer.disconnect();
    }, [children]);
    function go(index) {
        const el = track.current,
            card = cards()[index];
        if (card)
            el.scrollTo({
                left:
                    card.getBoundingClientRect().left -
                    el.getBoundingClientRect().left +
                    el.scrollLeft -
                    8,
                behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
                    ? "instant"
                    : "smooth",
            });
    }
    useEffect(() => {
        const el = track.current;
        let pointer = null,
            suppress = false,
            timer;
        function down(event) {
            if (
                event.pointerType === "touch" ||
                event.button !== 0 ||
                el.scrollWidth <= el.clientWidth + 1 ||
                event.target.closest(
                    "button, a, input, label, textarea, select, [role=tab]",
                )
            )
                return;
            pointer = {
                id: event.pointerId,
                x: event.clientX,
                left: el.scrollLeft,
                moved: false,
            };
        }
        function move(event) {
            if (!pointer || pointer.id !== event.pointerId) return;
            const delta = event.clientX - pointer.x;
            if (!pointer.moved && Math.abs(delta) < 5) return;
            pointer.moved = true;
            setDragging(true);
            el.setPointerCapture(event.pointerId);
            event.preventDefault();
            el.scrollLeft = pointer.left - delta;
        }
        function up(event) {
            if (!pointer || event.pointerId !== pointer.id) return;
            suppress = pointer.moved;
            pointer = null;
            setDragging(false);
            if (el.hasPointerCapture(event.pointerId))
                el.releasePointerCapture(event.pointerId);
            clearTimeout(timer);
            timer = setTimeout(() => {
                suppress = false;
            }, 0);
        }
        function click(event) {
            if (suppress) {
                event.preventDefault();
                event.stopPropagation();
            }
        }
        el.addEventListener("pointerdown", down);
        el.addEventListener("pointermove", move);
        el.addEventListener("pointerup", up);
        el.addEventListener("pointercancel", up);
        window.addEventListener("pointerup", up);
        window.addEventListener("pointercancel", up);
        el.addEventListener("click", click, true);
        return () => {
            clearTimeout(timer);
            el.removeEventListener("pointerdown", down);
            el.removeEventListener("pointermove", move);
            el.removeEventListener("pointerup", up);
            el.removeEventListener("pointercancel", up);
            window.removeEventListener("pointerup", up);
            window.removeEventListener("pointercancel", up);
            el.removeEventListener("click", click, true);
        };
    }, []);
    return (
        <section
            className="roster-carousel"
            style={{ "--group-colour": M.groupColour(row.colour || "none") }}
            aria-label={row.name}
            aria-roledescription="carousel"
            data-carousel-row={row.id}
        >
            <header>
                {row.children ? (
                    <button
                        className="roster-carousel-title"
                        onClick={() => onEditGroup(row.id)}
                        aria-label={`Edit group ${row.name}`}
                    >
                        {row.name}
                    </button>
                ) : (
                    <h2>{row.name}</h2>
                )}
                <span className="roster-carousel-position" aria-live="polite">
                    {position.total ? position.index + 1 : 0} / {position.total}
                </span>
                <Button
                    icon={ChevronLeft}
                    aria-label={`Previous card in ${row.name}`}
                    aria-controls={regionId}
                    disabled={position.index === 0}
                    onClick={() => go(position.index - 1)}
                />
                <Button
                    icon={ChevronRight}
                    aria-label={`Next card in ${row.name}`}
                    aria-controls={regionId}
                    disabled={position.end}
                    onClick={() => go(position.index + 1)}
                />
            </header>
            <div
                id={regionId}
                ref={track}
                className="roster-carousel-track"
                data-dragging={dragging || undefined}
                tabIndex={0}
                role="group"
                aria-label={`${row.name} cards`}
                onScroll={measure}
                onKeyDown={(event) => {
                    if (event.target !== event.currentTarget) return;
                    const target = {
                        ArrowRight: position.index + 1,
                        ArrowLeft: position.index - 1,
                        Home: 0,
                        End: position.total - 1,
                    }[event.key];
                    if (target !== undefined) {
                        event.preventDefault();
                        go(Math.max(0, Math.min(position.total - 1, target)));
                    }
                }}
            >
                {children}
                {mounted &&
                    saved?.some((group) => group.showBox && !group.hidden) && (
                        <GroupBoxes
                            saved={
                                row.id === "all"
                                    ? saved
                                    : saved.filter(
                                          (group) => group.id === row.id,
                                      )
                            }
                            showLabels={row.id === "all"}
                            fitMembers
                            grid={track}
                            onEditGroup={onEditGroup}
                        />
                    )}
            </div>
        </section>
    );
}
