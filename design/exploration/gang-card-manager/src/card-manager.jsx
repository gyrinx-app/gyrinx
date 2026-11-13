import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
    LayoutFreeform,
    GripVertical,
    ArrowUp,
    ArrowDown,
    ArrowUpToLine,
    ArrowDownToLine,
    X,
    Pin,
    PinOff,
    Group,
    Unlink,
    SquareDashed,
    RotateCcw,
    Skull,
    Wrench,
    Cat,
    Archive,
    Trash2,
    Undo2,
    Coins,
    CirclePile,
    Package,
    Zap,
    Flag,
    Check,
    Ellipsis,
    Move,
    Crown,
    Car,
    Palette,
    Pencil,
} from "lucide-react";
import { Button, Icon, TextInput, useModal } from "./controls.jsx";
import cotton from "./cotton.json";
import * as M from "./card-manager-model.js";
import { GangSheet } from "./gang-sheet.jsx";
import { GroupEditor } from "./group-editor.jsx";
import { GroupColourPalette } from "./group-colour-palette.jsx";

function IconButton({ icon, label, ...props }) {
    return <Button icon={icon} aria-label={label} title={label} {...props} />;
}
function useReorderAnimation(ref, dependency) {
    const snapshot = useRef(null);
    function measure() {
        const host = ref.current;
        if (!host) return new Map();
        const origin = host.getBoundingClientRect();
        return new Map(
            [...host.querySelectorAll("[data-flip]")].map((el) => {
                const rect = el.getBoundingClientRect();
                return [
                    el.dataset.flip,
                    {
                        el,
                        x: rect.left - origin.left + host.scrollLeft,
                        y: rect.top - origin.top + host.scrollTop,
                    },
                ];
            }),
        );
    }
    function capture() {
        const visual = measure();
        visual.forEach(({ el }) =>
            el.getAnimations().forEach((animation) => animation.cancel()),
        );
        snapshot.current = visual;
    }
    useLayoutEffect(() => {
        const old = snapshot.current;
        snapshot.current = null;
        if (!old || matchMedia("(prefers-reduced-motion: reduce)").matches)
            return;
        const next = measure();
        // Measure all final positions before starting any transform animations.
        next.forEach(({ el, x, y }, id) => {
            const visual = old.get(id);
            if (!visual) return;
            const dx = visual.x - x,
                dy = visual.y - y;
            if (Math.abs(dx) + Math.abs(dy) < 0.75) return;
            el.animate(
                [
                    { transform: `translate(${dx}px,${dy}px)` },
                    { transform: "translate(0,0)" },
                ],
                { duration: 220, easing: "cubic-bezier(.2,.8,.2,1)" },
            );
        });
    }, [dependency]);
    return capture;
}
function Confirm({ title, text, details, proceed, onConfirm, onClose }) {
    const ref = useModal();
    return (
        <dialog
            ref={ref}
            className={`${cotton.dialog.root} cm-confirm`}
            aria-labelledby="confirm-title"
            onCancel={(e) => {
                e.preventDefault();
                onClose();
            }}
        >
            <h2 id="confirm-title">{title}</h2>
            <p>{text}</p>
            {details && (
                <ul className="cm-confirm-details">
                    {details.map((detail, i) => (
                        <li key={i}>
                            {typeof detail === "string" ? (
                                detail
                            ) : (
                                <>
                                    <strong>{detail.heading}</strong>
                                    {detail.text && <p>{detail.text}</p>}
                                    <ul>
                                        {detail.names.map((name) => (
                                            <li key={name}>{name}</li>
                                        ))}
                                    </ul>
                                </>
                            )}
                        </li>
                    ))}
                </ul>
            )}
            <div className="cm-confirm-buttons">
                <Button autoFocus variant="default" onClick={onClose}>
                    Cancel
                </Button>
                <Button variant="primary" onClick={onConfirm}>
                    {proceed}
                </Button>
            </div>
        </dialog>
    );
}
function RenameGroup({ group, onSave, onClose }) {
    const ref = useModal(),
        [name, setName] = useState(group.name);
    return (
        <dialog
            ref={ref}
            className={`${cotton.dialog.root} cm-confirm`}
            aria-labelledby="rename-title"
            onCancel={(e) => {
                e.preventDefault();
                onClose();
            }}
        >
            <form
                onSubmit={(e) => {
                    e.preventDefault();
                    if (name.trim()) onSave(name.trim());
                }}
            >
                <h2 id="rename-title">Group name</h2>
                <label className="cm-rename-label">
                    Group name
                    <TextInput
                        value={name}
                        onChange={setName}
                        autoFocus
                        required
                        maxLength={120}
                        aria-label="Group name"
                    />
                </label>
                <div className="cm-confirm-buttons">
                    <Button variant="default" onClick={onClose}>
                        Cancel
                    </Button>
                    <button
                        className={cotton.button.success}
                        type="submit"
                        disabled={!name.trim()}
                    >
                        Set name
                    </button>
                </div>
            </form>
        </dialog>
    );
}
const pendingLabels = {
    Delete: "To be deleted",
    Archive: "To be archived",
    Refund: "To be refunded",
};
const pendingIcons = { Delete: Trash2, Archive, Refund: Coins };
function CardManager({ saved, onSave, onClose }) {
    const [draft, setDraft] = useState(() => M.copy(saved)),
        [selection, setSelection] = useState([]),
        [sort, setSort] = useState("default");
    const [menu, setMenu] = useState(false),
        [palette, setPalette] = useState(false),
        [paletteTargets, setPaletteTargets] = useState(null),
        [pending, setPending] = useState([]),
        [confirm, setConfirm] = useState(null),
        [renaming, setRenaming] = useState(null);
    const [announcement, announce] = useState(""),
        [drag, setDrag] = useState(null),
        [target, setTarget] = useState(null);
    const dialog = useModal(),
        list = useRef(),
        dragState = useRef(null),
        hover = useRef(null),
        hoverTimer = useRef(null),
        menuRef = useRef(),
        paletteRef = useRef(),
        paletteTrigger = useRef();
    const capture = useReorderAnimation(list, draft);
    const changed =
        JSON.stringify(draft) !== JSON.stringify(saved) || pending.length > 0;
    const ids = M.selectedIds(draft, selection),
        selectedModels = M.selectedModels(draft, selection),
        selectedGroups = draft.filter((n) => n.children && ids.includes(n.id));
    const pinCompatible =
        ids.length > 0 &&
        new Set(ids.map((id) => M.effectivePin(draft, id))).size === 1;
    const colourGroups = paletteTargets
        ? draft.filter((n) => n.children && paletteTargets.includes(n.id))
        : selectedGroups;
    const allIds = draft.map((n) => n.id);
    const pendingById = new Map(
        pending.flatMap((p) => p.ids.map((id) => [id, p.kind])),
    );
    useEffect(() => {
        if (!changed) return;
        const before = (e) => {
            e.preventDefault();
            e.returnValue = "";
        };
        window.addEventListener("beforeunload", before);
        return () => window.removeEventListener("beforeunload", before);
    }, [changed]);
    useEffect(() => {
        if (!menu && !palette) return;
        const close = (e) => {
            const path = e.composedPath();
            if (!path.includes(menuRef.current)) setMenu(false);
            if (
                !path.includes(paletteRef.current) &&
                !path.some((el) => el.dataset?.colourTrigger)
            )
                setPalette(false);
        };
        document.addEventListener("pointerdown", close);
        return () => document.removeEventListener("pointerdown", close);
    }, [menu, palette]);
    useEffect(() => () => clearTimeout(hoverTimer.current), []);
    function update(next, message = "Card order changed.") {
        if (JSON.stringify(next) === JSON.stringify(draft)) return;
        capture();
        setDraft(next);
        announce(message);
    }
    function toggle(id) {
        const n = M.find(draft, id),
            parent = draft.find((g) => g.children?.some((c) => c.id === id));
        setSelection((current) => {
            if (n.children) {
                const remove = new Set([id, ...n.children.map((c) => c.id)]);
                return current.includes(id) ||
                    n.children.every((c) => current.includes(c.id))
                    ? current.filter((x) => !remove.has(x))
                    : [...current.filter((x) => !remove.has(x)), id];
            }
            const next =
                parent && current.includes(parent.id)
                    ? [
                          ...current.filter((x) => x !== parent.id),
                          ...parent.children.map((c) => c.id),
                      ]
                    : current;
            return next.includes(id)
                ? next.filter((x) => x !== id)
                : [...next, id];
        });
    }
    function exit() {
        if (changed)
            setConfirm({
                title: "Discard changes?",
                text: "Your card order, groups and pending model actions will be discarded.",
                proceed: "Discard changes",
                action: onClose,
            });
        else onClose();
    }
    function action(fn) {
        fn();
        setMenu(false);
        setPalette(false);
    }
    function group() {
        action(() => {
            update(M.groupSelection(draft, ids), "Cards grouped.");
            setSelection([]);
        });
    }
    function ungroup(groupIds = ids) {
        action(() => {
            update(M.ungroup(draft, groupIds), "Groups ungrouped.");
            setSelection([]);
        });
    }
    function byType() {
        const picked = ids.length ? ids : draft.map((n) => n.id);
        const affected = M.groupsAffectedByType(draft, picked);
        const apply = () => {
            update(
                M.groupByType(draft, picked),
                "Selected cards grouped by type.",
            );
            setSelection([]);
        };
        action(() =>
            affected.length
                ? setConfirm({
                      title: "Replace existing groups?",
                      text: "Group by type will ungroup the existing groups listed below and regroup the selected cards. Unselected cards in those groups will become individual cards. Gang panels will be pinned at the top, and dead/destroyed models at the bottom.",
                      details: affected.map((g) => g.name),
                      proceed: "Ungroup and group by type",
                      action: apply,
                  })
                : apply(),
        );
    }
    function rename(group) {
        setRenaming(group);
        setMenu(false);
        setPalette(false);
    }
    function stage(kind) {
        const picked = selectedModels.map((n) => n.id);
        action(() =>
            setConfirm({
                title: `${kind} ${picked.length} model${picked.length === 1 ? "" : "s"}?`,
                text: "This will only take effect when you save. You can undo this action before saving.",
                details: picked.map((id) => M.models[id].name),
                proceed: `Confirm ${kind.toLowerCase()}`,
                action: () => {
                    setPending((current) => [
                        ...current
                            .map((p) => ({
                                ...p,
                                ids: p.ids.filter((id) => !picked.includes(id)),
                            }))
                            .filter((p) => p.ids.length),
                        { kind, ids: picked },
                    ]);
                    setSelection([]);
                    announce(`${kind} pending until Save.`);
                },
            }),
        );
    }
    function undoPending(id) {
        setPending((current) =>
            current
                .map((p) => ({
                    ...p,
                    ids: p.ids.filter((value) => value !== id),
                }))
                .filter((p) => p.ids.length),
        );
        announce("Pending action undone.");
    }
    function save() {
        if (!pending.length) {
            onSave(draft, []);
            return;
        }
        setConfirm({
            title: "Save and apply model actions?",
            text: "Saving will apply the layout and these model actions. This prototype simulates the actions.",
            details: pending.map((p) => ({
                heading: `${p.kind} ${p.ids.length} model${p.ids.length === 1 ? "" : "s"}`,
                names: p.ids.map(
                    (id) =>
                        `${M.models[id].name}${M.models[id].pets?.length ? ` (with ${M.models[id].pets.length} attached pets)` : ""}`,
                ),
            })),
            proceed: "Save and apply",
            action: () =>
                onSave(
                    M.remove(
                        draft,
                        pending.flatMap((p) => p.ids),
                    ),
                    pending,
                ),
        });
    }
    function startDrag(e, id) {
        if (e.button !== 0 || !e.isPrimary) return;
        if (e.button !== 0) return;
        const parentSelected = draft.find(
            (n) =>
                selection.includes(n.id) &&
                n.children?.some((c) => c.id === id),
        );
        dragState.current = {
            ids: ids.includes(id) || parentSelected ? ids : [id],
            x: e.clientX,
            y: e.clientY,
            active: false,
            target: null,
        };
        e.currentTarget.setPointerCapture(e.pointerId);
    }
    function pointerMove(e) {
        const state = dragState.current;
        if (!state) return;
        if (
            !state.active &&
            Math.hypot(e.clientX - state.x, e.clientY - state.y) < 5
        )
            return;
        state.active = true;
        setDrag({ ids: state.ids, x: e.clientX, y: e.clientY });
        const el = dialog.current
            .getRootNode()
            .elementFromPoint(e.clientX, e.clientY)
            ?.closest("[data-drop]");
        if (!el) {
            clearTimeout(hoverTimer.current);
            hover.current = null;
            state.target = null;
            setTarget(null);
            return;
        }
        const id = el.dataset.drop,
            box = el.getBoundingClientRect(),
            inMiddle =
                e.clientY > box.top + box.height * 0.23 &&
                e.clientY < box.bottom - box.height * 0.23;
        const mode = e.clientY < box.top + box.height / 2 ? "before" : "after",
            valid = M.canRelocate(draft, state.ids, id),
            key = `${id}-${inMiddle}-${valid}`;
        if (hover.current !== key) {
            clearTimeout(hoverTimer.current);
            hover.current = key;
            state.target = valid ? { id, mode } : null;
            setTarget(valid ? { id, mode, waiting: inMiddle } : null);
            if (valid && inMiddle)
                hoverTimer.current = setTimeout(() => {
                    state.target = { id, mode: "merge" };
                    setTarget({ id, mode: "merge" });
                    announce("Release to group cards.");
                }, 650);
        } else if (state.target && state.target.mode !== "merge") {
            state.target = { id, mode };
            setTarget({ id, mode, waiting: inMiddle });
        }
        const bounds = list.current.getBoundingClientRect();
        if (e.clientY < bounds.top + 35) list.current.scrollTop -= 10;
        if (e.clientY > bounds.bottom - 35) list.current.scrollTop += 10;
    }
    function endDrag() {
        const state = dragState.current;
        if (state?.active && state.target)
            update(
                M.relocate(
                    draft,
                    state.ids,
                    state.target.id,
                    state.target.mode,
                ),
                state.target.mode === "merge"
                    ? "Cards grouped."
                    : "Cards moved.",
            );
        clearDrag();
    }
    function clearDrag() {
        clearTimeout(hoverTimer.current);
        hover.current = null;
        dragState.current = null;
        setDrag(null);
        setTarget(null);
    }
    const isChecked = (n) =>
        selection.includes(n.id) ||
        draft.some(
            (g) =>
                selection.includes(g.id) &&
                g.children?.some((c) => c.id === n.id),
        );
    function checkbox(n, parent) {
        const partial =
            n.children &&
            !selection.includes(n.id) &&
            n.children.some((c) => selection.includes(c.id));
        return (
            <input
                type="checkbox"
                aria-label={`Select ${n.children ? "group " : ""}${n.name || M.models[n.id].name}`}
                aria-describedby={
                    parent ? `group-label-${parent.id}` : undefined
                }
                checked={
                    isChecked(n) ||
                    !!(
                        n.children &&
                        n.children.every((c) => selection.includes(c.id))
                    )
                }
                ref={(el) => {
                    if (el)
                        el.indeterminate =
                            !!partial &&
                            !n.children.every((c) => selection.includes(c.id));
                }}
                onChange={() => toggle(n.id)}
            />
        );
    }
    function handle(n) {
        return (
            <button
                type="button"
                className="cm-grip"
                aria-label={`Drag ${n.name || M.models[n.id].name}`}
                title="Drag to move. Hold over a card to group. Use selection and arrows for keyboard movement."
                onPointerDown={(e) => startDrag(e, n.id)}
                onPointerMove={pointerMove}
                onPointerUp={endDrag}
                onPointerCancel={clearDrag}
            >
                <Icon icon={GripVertical} size={n.children ? 12 : 17} />
            </button>
        );
    }
    function dropClass(id) {
        return target?.id === id
            ? `cm-drop-${target.mode} ${target.waiting ? "cm-waiting" : ""}`
            : "";
    }
    function row(n, parent, last) {
        const model = M.models[n.id],
            kind = pendingById.get(n.id);
        return (
            <div
                key={n.id}
                data-flip={n.id}
                data-card-id={n.id}
                role="listitem"
                className={`cm-row-wrap ${parent ? "cm-group-child" : ""} ${last ? "cm-group-last" : ""} ${dropClass(n.id)}`}
                style={
                    parent
                        ? {
                              "--group-colour": M.groupColour(parent.colour),
                          }
                        : undefined
                }
            >
                <div
                    data-drop={n.id}
                    className={`cm-row ${model.status ? "cm-inactive" : ""} ${isChecked(n) ? "cm-selected" : ""} ${drag?.ids.includes(n.id) ? "cm-dragging" : ""} ${kind ? "cm-pending-row" : ""}`}
                >
                    {checkbox(n, parent)}
                    <div className="cm-name-block">
                        <div className="cm-name-line">
                            <span className="cm-model-name" title={model.name}>
                                {model.subtypes?.includes("Leader") && (
                                    <span
                                        role="img"
                                        aria-label="Leader"
                                        title="Leader"
                                    >
                                        <Icon icon={Crown} size={14} />
                                    </span>
                                )}
                                {model.subtypes?.includes("Vehicle") && (
                                    <span
                                        role="img"
                                        aria-label="Vehicle"
                                        title="Vehicle"
                                    >
                                        <Icon icon={Car} size={14} />
                                    </span>
                                )}
                                {model.special && (
                                    <Icon
                                        icon={
                                            model.icon === "stash"
                                                ? Package
                                                : model.icon === "actions"
                                                  ? Zap
                                                  : Flag
                                        }
                                        size={14}
                                    />
                                )}
                                <span className="cm-name-text">
                                    {model.name}
                                </span>
                            </span>
                            {model.status && (
                                <span className="cm-status">
                                    <Icon
                                        icon={
                                            model.status === "Dead"
                                                ? Skull
                                                : Wrench
                                        }
                                        size={12}
                                    />
                                    {model.status}
                                </span>
                            )}
                            {kind && (
                                <span className="cm-action-label">
                                    <Icon icon={pendingIcons[kind]} size={12} />
                                    {pendingLabels[kind]}
                                </span>
                            )}
                        </div>
                        {model.pets && (
                            <div
                                className="cm-pets"
                                aria-label={`${model.pets.length} attached pets: ${model.pets.join(", ")}`}
                            >
                                {model.pets.map((pet, i) => (
                                    <span key={i} title={pet}>
                                        <Icon icon={Cat} size={12} />
                                    </span>
                                ))}
                                <span>
                                    {model.pets.length === 1
                                        ? model.pets[0]
                                        : `${model.pets.length} ${model.pets[0].toLowerCase()}s`}{" "}
                                    · moves with model
                                </span>
                            </div>
                        )}
                    </div>
                    <span className="cm-type" title={model.type}>
                        {model.type}
                    </span>
                    {n.pin && (
                        <span className="cm-pin" title={`Pinned to ${n.pin}`}>
                            <Icon icon={Pin} size={12} />
                        </span>
                    )}
                    {kind && (
                        <IconButton
                            icon={Undo2}
                            label={`Undo pending ${kind.toLowerCase()} for ${model.name}`}
                            onClick={() => undoPending(n.id)}
                        />
                    )}
                    {handle(n)}
                </div>
            </div>
        );
    }
    function groupHeader(n) {
        return (
            <div
                key={`header-${n.id}`}
                data-flip={`header-${n.id}`}
                role="listitem"
                data-group-id={n.id}
                className={`cm-group-header cm-group-start ${isChecked(n) ? "cm-selected" : ""} ${drag?.ids.includes(n.id) ? "cm-dragging" : ""} ${dropClass(n.id)}`}
                data-drop={n.id}
                style={{ "--group-colour": M.groupColour(n.colour) }}
            >
                {checkbox(n)}
                <Button
                    className={`${cotton.button.ghost} cm-group-name`}
                    id={`group-label-${n.id}`}
                    title={`Rename ${n.name}`}
                    aria-label={`Rename group ${n.name}`}
                    onClick={() => rename(n)}
                >
                    {n.name}
                </Button>
                <span className="cm-count">{n.children.length}</span>
                <button
                    type="button"
                    className="cm-colour-dot"
                    data-colour-trigger="true"
                    aria-label={`Group colour for ${n.name}`}
                    title={`Group colour for ${n.name}`}
                    aria-expanded={
                        (palette && paletteTargets?.includes(n.id)) || false
                    }
                    onClick={(e) => {
                        paletteTrigger.current = e.currentTarget;
                        setPaletteTargets([n.id]);
                        setPalette(true);
                        setMenu(false);
                    }}
                />

                <IconButton
                    icon={SquareDashed}
                    label="Show group box"
                    aria-pressed={Boolean(n.showBox)}
                    iconSize={12}
                    className="cm-header-box"
                    onClick={() =>
                        update(
                            M.setGroupBox(
                                draft,
                                M.groupActionIds(draft, ids, n.id),
                                !n.showBox,
                            ),
                            n.showBox
                                ? "Group boxes hidden."
                                : "Group boxes shown.",
                        )
                    }
                />
                <IconButton
                    icon={Unlink}
                    label={`Ungroup ${n.name}`}
                    iconSize={12}
                    className="cm-header-ungroup"
                    onClick={() => ungroup(M.groupActionIds(draft, ids, n.id))}
                />

                {n.pin && (
                    <span className="cm-pin-label">
                        <Icon icon={Pin} size={12} />
                        {n.pin === "top" ? "Top" : "Bottom"}
                    </span>
                )}
                {handle(n)}
            </div>
        );
    }
    function groupControls() {
        return (
            <>
                <Button
                    icon={Group}
                    disabled={!pinCompatible}
                    title={
                        !pinCompatible
                            ? "Select cards with the same pin position."
                            : "Group selected cards"
                    }
                    onClick={group}
                >
                    Group
                </Button>
                <Button
                    icon={Unlink}
                    disabled={!selectedGroups.length}
                    onClick={() => ungroup()}
                >
                    Ungroup
                </Button>
                <Button icon={CirclePile} onClick={byType}>
                    Group by type
                </Button>
            </>
        );
    }
    function groupSettings(overflow = false) {
        return (
            <>
                <Button
                    icon={Pencil}
                    aria-label="Group name"
                    title="Group name"
                    disabled={selectedGroups.length !== 1 || ids.length !== 1}
                    onClick={() => rename(selectedGroups[0])}
                >
                    {overflow ? "Group name" : null}
                </Button>
                <Button
                    icon={Palette}
                    aria-label="Group colour"
                    title="Group colour"
                    data-colour-trigger="true"
                    aria-expanded={palette}
                    disabled={!selectedGroups.length}
                    onClick={(e) => {
                        paletteTrigger.current = e.currentTarget;
                        setPaletteTargets(null);
                        setPalette(!palette);
                        setMenu(false);
                    }}
                >
                    {overflow ? "Group colour" : null}
                </Button>
            </>
        );
    }
    function pinControls(overflow = false) {
        return (
            <>
                {[
                    ["top", "Pin to top"],
                    ["bottom", "Pin to bottom"],
                    [null, "Unpin"],
                ].map(([pin, label]) => (
                    <Button
                        key={label}
                        icon={
                            pin === null
                                ? PinOff
                                : pin === "top"
                                  ? ArrowUpToLine
                                  : ArrowDownToLine
                        }
                        aria-label={label}
                        title={label}
                        disabled={
                            pin === null
                                ? !ids.some((id) => M.find(draft, id)?.pin)
                                : !ids.length
                        }
                        onClick={() =>
                            action(() => update(M.setPin(draft, ids, pin)))
                        }
                    >
                        {overflow ? label : null}
                    </Button>
                ))}
            </>
        );
    }
    return (
        <dialog
            ref={dialog}
            className={`${cotton.dialog.root} cm-dialog`}
            aria-labelledby="cm-title"
            aria-describedby="cm-help"
            onCancel={(e) => {
                e.preventDefault();
                if (dragState.current) clearDrag();
                else if (palette) {
                    setPalette(false);
                    paletteTrigger.current?.focus();
                } else if (menu) setMenu(false);
                else exit();
            }}
        >
            <header className="cm-header">
                <div>
                    <span className="cm-eyebrow">The Nightshade Coven</span>
                    <h2 id="cm-title">
                        <Icon icon={LayoutFreeform} size={18} />
                        Card Manager
                    </h2>
                </div>
                <IconButton icon={X} label="Exit Card Manager" onClick={exit} />
            </header>
            <p id="cm-help" className="cm-help">
                Drag to reorder. Hold over a card to group.
            </p>
            <div className="cm-toolbar">
                <div className="cm-selection-buttons">
                    <button
                        type="button"
                        className="cm-text-control"
                        disabled={!allIds.length}
                        onClick={() => setSelection(allIds)}
                    >
                        All
                    </button>
                    <button
                        type="button"
                        className="cm-text-control"
                        disabled={!ids.length}
                        onClick={() => setSelection([])}
                    >
                        None
                    </button>
                </div>
                <span className="cm-divider" />
                <IconButton
                    icon={ArrowUp}
                    label="Move selected up"
                    disabled={
                        !ids.length ||
                        JSON.stringify(M.move(draft, ids, -1)) ===
                            JSON.stringify(draft)
                    }
                    onClick={() =>
                        update(
                            M.move(draft, ids, -1),
                            "Selected cards moved up.",
                        )
                    }
                />
                <IconButton
                    icon={ArrowDown}
                    label="Move selected down"
                    disabled={
                        !ids.length ||
                        JSON.stringify(M.move(draft, ids, 1)) ===
                            JSON.stringify(draft)
                    }
                    onClick={() =>
                        update(
                            M.move(draft, ids, 1),
                            "Selected cards moved down.",
                        )
                    }
                />
                <div className="cm-inline-groups">
                    <div className="cm-inline-primary">{groupControls()}</div>
                    <div className="cm-inline-pins">{pinControls()}</div>
                    <div className="cm-inline-settings">{groupSettings()}</div>
                </div>
                <div className="cm-menu-anchor" ref={menuRef}>
                    <IconButton
                        variant="default"
                        icon={Ellipsis}
                        label="More options"
                        aria-expanded={menu}
                        aria-controls="cm-actions"
                        onClick={() => {
                            setMenu(!menu);
                            setPalette(false);
                        }}
                    />
                    {menu && (
                        <div
                            id="cm-actions"
                            className="cm-actions"
                            onKeyDown={(e) => {
                                if (e.key === "Escape") {
                                    e.preventDefault();
                                    e.stopPropagation();
                                    setMenu(false);
                                    menuRef.current
                                        .querySelector("button")
                                        .focus();
                                }
                            }}
                        >
                            <div className="cm-overflow-groups">
                                <div className="cm-overflow-primary">
                                    {groupControls()}
                                </div>
                                <div className="cm-overflow-pins">
                                    {pinControls(true)}
                                </div>
                            </div>
                            <hr />
                            <div className="cm-group-settings">
                                {groupSettings(true)}
                            </div>
                            <hr />
                            <Button
                                icon={Coins}
                                disabled={!selectedModels.length}
                                onClick={() => stage("Refund")}
                            >
                                Refund models
                            </Button>
                            <Button
                                icon={Archive}
                                disabled={!selectedModels.length}
                                onClick={() => stage("Archive")}
                            >
                                Archive models
                            </Button>
                            <Button
                                icon={Trash2}
                                disabled={!selectedModels.length}
                                onClick={() => stage("Delete")}
                            >
                                Delete models
                            </Button>
                            <hr />
                            <Button
                                icon={RotateCcw}
                                disabled={ids.length > 0}
                                onClick={() =>
                                    action(() =>
                                        setConfirm({
                                            title: "Reset card order?",
                                            text: "Restore the default order, groups, colours and pins. Pending model actions will stay marked until you save.",
                                            proceed: "Reset order",
                                            action: () => {
                                                const survivors = new Set(
                                                    M.flatten(saved).map(
                                                        (n) => n.id,
                                                    ),
                                                );
                                                update(
                                                    M.clean(
                                                        M.defaults()
                                                            .map((n) =>
                                                                n.children
                                                                    ? {
                                                                          ...n,
                                                                          children:
                                                                              n.children.filter(
                                                                                  (
                                                                                      c,
                                                                                  ) =>
                                                                                      survivors.has(
                                                                                          c.id,
                                                                                      ),
                                                                              ),
                                                                      }
                                                                    : n,
                                                            )
                                                            .filter((n) =>
                                                                n.children
                                                                    ? n.children
                                                                          .length
                                                                    : survivors.has(
                                                                          n.id,
                                                                      ),
                                                            ),
                                                    ),
                                                );
                                                setSort("default");
                                            },
                                        }),
                                    )
                                }
                            >
                                Reset order
                            </Button>
                        </div>
                    )}
                </div>
                {palette && (
                    <div
                        ref={paletteRef}
                        className="cm-palette"
                        role="group"
                        aria-label="Group colour"
                        onKeyDown={(e) => {
                            if (e.key === "Escape") {
                                e.preventDefault();
                                e.stopPropagation();
                                setPalette(false);
                                paletteTrigger.current?.focus();
                            }
                        }}
                    >
                        <span>Group colour</span>
                        <GroupColourPalette
                            selected={colourGroups.map((group) => group.colour)}
                            onChange={(colour) =>
                                update(
                                    draft.map((node) =>
                                        colourGroups.some(
                                            (group) => group.id === node.id,
                                        )
                                            ? { ...node, colour }
                                            : node,
                                    ),
                                    "Group colour changed.",
                                )
                            }
                        />
                    </div>
                )}
            </div>
            <div className="cm-sortbar">
                <span>
                    {ids.length
                        ? `${selectedModels.length} models · ${ids.length} selected`
                        : `${M.flatten(draft).length} cards`}
                </span>
                <label>
                    Sort by
                    <select
                        className={cotton.select.className}
                        style={cotton.select.style}
                        aria-label="Sort by"
                        value={sort}
                        onChange={(e) => {
                            setSort(e.target.value);
                            update(
                                M.sortCards(draft, e.target.value),
                                "Cards sorted.",
                            );
                        }}
                    >
                        <option value="default">Default</option>
                        <option value="profile">Profile type</option>
                        <option value="name-asc">Name: A–Z</option>
                        <option value="name-desc">Name: Z–A</option>
                        <option value="rating-asc">Rating: low–high</option>
                        <option value="rating-desc">Rating: high–low</option>
                    </select>
                </label>
            </div>
            <div
                className="cm-list"
                ref={list}
                role="list"
                aria-label="Gang cards"
            >
                {draft.flatMap((n) =>
                    n.children
                        ? [
                              groupHeader(n),
                              ...n.children.map((child, i) =>
                                  row(child, n, i === n.children.length - 1),
                              ),
                          ]
                        : [row(n)],
                )}
            </div>
            <div className="cm-footnote">
                <Icon icon={Move} size={13} />
                <span>
                    {target?.mode === "merge"
                        ? "Release to group cards."
                        : drag
                          ? "Drag cards out of groups to move them freely. Pinned groups stay in their position."
                          : "Select cards to move together. Pets stay with their model."}
                </span>
            </div>
            {pending.length > 0 && (
                <div className="cm-pending">
                    <span>
                        {pending.reduce((n, p) => n + p.ids.length, 0)} model
                        actions pending until Save
                    </span>
                    <Button
                        icon={Undo2}
                        onClick={() => {
                            setPending([]);
                            setSort("default");
                            update(M.copy(saved), "All changes discarded.");
                            setSelection([]);
                        }}
                    >
                        Undo all changes
                    </Button>
                </div>
            )}
            <footer className="cm-footer">
                <span>{changed ? "Unsaved changes" : "No changes"}</span>
                <Button variant="default" onClick={exit}>
                    Cancel
                </Button>
                <Button
                    variant="success"
                    icon={Check}
                    disabled={!changed}
                    onClick={save}
                >
                    Save
                </Button>
            </footer>
            <div className="cm-sr" role="status" aria-live="polite">
                {announcement}
            </div>
            {drag && (
                <div
                    className="cm-drag-preview"
                    style={{ left: drag.x + 12, top: drag.y + 12 }}
                >
                    <Icon icon={GripVertical} size={15} />
                    {drag.ids.length === 1
                        ? M.find(draft, drag.ids[0]).name ||
                          M.models[drag.ids[0]].name
                        : `${drag.ids.length} selected cards`}
                </div>
            )}
            {confirm && (
                <Confirm
                    {...confirm}
                    onClose={() => setConfirm(null)}
                    onConfirm={() => {
                        const fn = confirm.action;
                        setConfirm(null);
                        fn();
                    }}
                />
            )}
            {renaming && (
                <RenameGroup
                    group={renaming}
                    onClose={() => setRenaming(null)}
                    onSave={(name) => {
                        update(
                            draft.map((n) =>
                                n.id === renaming.id ? { ...n, name } : n,
                            ),
                            "Group renamed.",
                        );
                        setRenaming(null);
                    }}
                />
            )}
        </dialog>
    );
}
function App() {
    const [stored] = useState(() =>
        M.loadLayout(
            () => localStorage,
            cotton.colours.map((c) => c.name.toLowerCase()),
        ),
    );
    const [saved, setSaved] = useState(stored.layout);
    const [editingGroup, setEditingGroup] = useState(null);
    const [open, setOpen] = useState(false),
        [dark, setDark] = useState(false),
        [notice, setNotice] = useState(stored.notice);
    const page = useRef(),
        trigger = useRef();
    const capturePage = useReorderAnimation(page, saved);
    useEffect(() => {
        document.querySelector("#gang-root").classList.toggle("dark", dark);
    }, [dark]);
    function close() {
        setOpen(false);
        requestAnimationFrame(() => trigger.current?.focus());
    }
    function updateGroup(id, changes) {
        const nodes = saved.map((node) =>
            node.id === id ? { ...node, ...changes } : node,
        );
        setSaved(nodes);
        const persisted = M.storeLayout(
            () => localStorage,
            nodes,
            stored.writable,
        );
        setNotice(
            persisted
                ? "Group saved."
                : "The group changed for this visit, but could not be saved in this browser.",
        );
    }
    function save(nodes, actions) {
        capturePage();
        setSaved(nodes);
        const persisted = M.storeLayout(
            () => localStorage,
            nodes,
            stored.writable,
        );
        close();
        setNotice(
            !persisted
                ? "The layout changed for this visit, but could not be saved in this browser."
                : actions.length
                  ? "Card layout saved. Pending model actions were simulated."
                  : "Card layout saved.",
        );
    }
    return (
        <div className={`gang-page ${dark ? "dark" : ""}`}>
            <GangSheet
                saved={saved}
                page={page}
                trigger={trigger}
                onOpen={() => setOpen(true)}
                onEditGroup={setEditingGroup}
                onToggleTheme={() => setDark(!dark)}
                notice={notice}
                onNotice={setNotice}
            />
            {editingGroup && (
                <GroupEditor
                    group={M.find(saved, editingGroup)}
                    onSave={(changes) => updateGroup(editingGroup, changes)}
                    onClose={() => setEditingGroup(null)}
                    onManager={() => setOpen(true)}
                />
            )}
            {open && (
                <CardManager saved={saved} onSave={save} onClose={close} />
            )}
        </div>
    );
}
if (new URLSearchParams(location.search).get("names") !== "short") {
    Object.assign(M.models.vesper, {
        name: "Lady Vesper Krail, the Unrelenting Sovereign of the Nightshade Coven and the Thirteen Ashen Spires",
    });
    Object.assign(M.models.nyx, {
        name: "Nyx the Unbroken, Keeper of a Thousand Poisoned Promises Beyond the Sump-Sea",
    });
    Object.assign(M.models.crawler, {
        name: "The Indefatigable Nightshade Express, Last Survivor of the Great Ash-Waste Convoy",
    });
}
const host = document.querySelector("#gang-root");
const shadow = host.attachShadow({ mode: "open" });
const style = document.createElement("link");
style.rel = "stylesheet";
style.href = host.dataset.themeUrl || "/static/theme.css";
shadow.append(style);
const root = document.createElement("div");
shadow.append(root);
createRoot(root).render(<App />);
