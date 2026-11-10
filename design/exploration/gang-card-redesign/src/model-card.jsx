import React, {
    useEffect,
    useId,
    useLayoutEffect,
    useMemo,
    useRef,
    useState,
} from "react";
import {
    ArrowRight,
    ChevronDown,
    X,
    Cog,
    Toolbox,
    EllipsisVertical,
    Image as ImageIcon,
    Layers,
    CircleFadingArrowUp,
} from "lucide-react";
import { Button, Icon, useModal } from "./controls.jsx";
import cotton from "./cotton.json";
import * as M from "./models.js";
import { nameplateEdge } from "./nameplate-edge.js";
import { ModelName } from "./model-name.jsx";
import { ModelPictureUpload } from "./model-picture-upload.jsx";
import {
    physical,
    mental,
    archetypes,
    profiles,
    cardExamples,
    weaponTraits,
} from "./gang-sheet-data.js";

function InfoDialog({ title, children, onClose }) {
    const ref = useModal();
    return (
        <dialog
            ref={ref}
            className={`${cotton.dialog.root} sheet-info-dialog`}
            aria-labelledby="sheet-info-title"
            onCancel={(e) => {
                e.preventDefault();
                onClose();
            }}
        >
            <header>
                <h2 id="sheet-info-title" className={cotton.dialog.title}>
                    {title}
                </h2>
                <Button
                    icon={X}
                    aria-label="Close"
                    title="Close"
                    onClick={onClose}
                />
            </header>
            <div className="sheet-info-content">{children}</div>
            <footer>
                <Button variant="default" onClick={onClose}>
                    Close
                </Button>
            </footer>
        </dialog>
    );
}
function ModelActions({ model, onAction }) {
    return (
        <details
            className="gang-model-menu"
            onKeyDown={(event) => {
                if (event.key === "Escape") {
                    event.currentTarget.open = false;
                    event.currentTarget.querySelector("summary").focus();
                }
            }}
            onBlur={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget))
                    event.currentTarget.open = false;
            }}
        >
            <summary
                className={cotton.button.ghost}
                aria-label={`More actions for ${model.name}`}
                title="More actions"
            >
                <Icon icon={EllipsisVertical} size={14} />
                <Icon icon={ChevronDown} size={11} />
            </summary>
            <div className="gang-model-menu-items">
                {["Mark as…", "Clone model", "Refund", "Delete"].map(
                    (action) => (
                        <button
                            type="button"
                            key={action}
                            className={action === "Delete" ? "gang-danger" : ""}
                            onClick={(event) => {
                                event.currentTarget.closest("details").open =
                                    false;
                                onAction(action);
                            }}
                        >
                            {action}
                        </button>
                    ),
                )}
            </div>
        </details>
    );
}
function Portrait({ model, onPicture }) {
    const [dismissed, setDismissed] = useState(false);
    const [hovered, setHovered] = useState(false);
    useEffect(() => {
        if (!hovered) return;
        const dismiss = (event) => {
            if (event.key === "Escape") setDismissed(true);
        };
        window.addEventListener("keydown", dismiss);
        return () => window.removeEventListener("keydown", dismiss);
    }, [hovered]);
    return (
        <span
            className="gang-portrait-wrap"
            data-dismissed={dismissed}
            onMouseEnter={() => {
                setHovered(true);
                setDismissed(false);
            }}
            onMouseLeave={() => {
                setHovered(false);
                setDismissed(false);
            }}
            onKeyDown={(event) => {
                if (event.key === "Escape") {
                    event.stopPropagation();
                    setDismissed(true);
                }
            }}
        >
            <button
                type="button"
                className="gang-portrait"
                aria-label={`Show portrait of ${model.name}`}
                onFocus={() => setDismissed(false)}
                onClick={onPicture}
            >
                <img src={model.image} alt="" />
            </button>
            <span className="gang-portrait-preview">
                <img
                    src={model.image}
                    alt={`Larger picture of ${model.name}`}
                />
            </span>
        </span>
    );
}
function CardTabs({ model, children, onAction, onPicture, onCards }) {
    const [tab, setTab] = useState(0),
        id = useId();
    const panelRef = useRef(null);
    const names = ["Card", "Lore", "Notes"];
    useLayoutEffect(() => {
        const panel = panelRef.current;
        const card = panel.closest("article");
        const buttons = [
            ...card.querySelectorAll('.gang-card-tabs > [role="tab"]'),
        ];
        const setPixels = (element, property, value) => {
            const next = `${Math.round(value * 1000) / 1000}px`;
            if (element.style.getPropertyValue(property) !== next)
                element.style.setProperty(property, next);
        };
        const alignPaper = () => {
            const width = parseFloat(getComputedStyle(card).width);
            if (!width) return;
            // Undo hover scaling so the image stays anchored to the card's layout.
            const scale = card.getBoundingClientRect().width / width;
            if (!scale) return;
            const body = panel.getBoundingClientRect();
            const bounds = buttons.map((button) =>
                button.getBoundingClientRect(),
            );
            const top = bounds[0].top;
            setPixels(card, "--card-paper-height", (body.bottom - top) / scale);
            buttons.forEach((button, index) =>
                setPixels(
                    button,
                    "--paper-x",
                    (body.left - bounds[index].left) / scale,
                ),
            );
            setPixels(panel, "--paper-y", (top - body.top) / scale);
        };
        const observer = new ResizeObserver(alignPaper);
        observer.observe(panel);
        buttons.forEach((button) => observer.observe(button));
        alignPaper();
        return () => observer.disconnect();
    }, []);
    return (
        <>
            <div className="gang-card-controls">
                <div
                    className="gang-card-tabs"
                    role="tablist"
                    aria-label={`${model.name} card sections`}
                    onKeyDown={(e) => {
                        const next =
                            e.key === "ArrowRight"
                                ? (tab + 1) % names.length
                                : e.key === "ArrowLeft"
                                  ? (tab + names.length - 1) % names.length
                                  : e.key === "Home"
                                    ? 0
                                    : e.key === "End"
                                      ? names.length - 1
                                      : null;
                        if (next !== null) {
                            e.preventDefault();
                            setTab(next);
                            e.currentTarget
                                .querySelectorAll("button")
                                [next].focus();
                        }
                    }}
                >
                    {names.map((name, i) => (
                        <button
                            key={name}
                            id={`${id}-tab-${i}`}
                            role="tab"
                            aria-selected={tab === i}
                            aria-controls={`${id}-panel`}
                            tabIndex={tab === i ? 0 : -1}
                            type="button"
                            onClick={() => setTab(i)}
                        >
                            {name}
                        </button>
                    ))}
                </div>
                <div
                    className="gang-model-actions"
                    aria-label={`${model.name} controls`}
                >
                    {model.image && (
                        <Button
                            icon={ImageIcon}
                            iconSize={14}
                            className={`${cotton.button.ghost} gang-picture-control`}
                            title="Show model picture"
                            aria-label={`Show picture of ${model.name}`}
                            onClick={onPicture}
                        />
                    )}
                    <Button
                        icon={Layers}
                        iconSize={14}
                        title="Model cards"
                        aria-label={`Model cards for ${model.name}`}
                        onClick={onCards}
                    />
                    <Button
                        icon={Cog}
                        iconSize={14}
                        title="Edit model"
                        aria-label={`Edit ${model.name}`}
                        onClick={() => onAction("Edit model")}
                    />
                    <Button
                        icon={Toolbox}
                        iconSize={14}
                        title="Equip model"
                        aria-label={`Equip ${model.name}`}
                        onClick={() => onAction("Equip model")}
                    />
                    <ModelActions model={model} onAction={onAction} />
                </div>
            </div>
            <div
                className="gang-card-panel"
                ref={panelRef}
                id={`${id}-panel`}
                role="tabpanel"
                aria-labelledby={`${id}-tab-${tab}`}
                tabIndex={0}
            >
                {tab === 0 ? (
                    children
                ) : (
                    <div className="gang-card-prose">
                        {tab === 1
                            ? model.lore || "Nothing written yet."
                            : model.notes || "No notes yet."}
                    </div>
                )}
            </div>
        </>
    );
}
function Statline({ model, pet }) {
    const profile = profiles[model.id];
    const stats =
        profile?.stats ||
        (pet
            ? ["6″", "4+", "6+", "3", "3", "1", "3+", "2", "6+"]
            : ["5″", "4+", "4+", "3", "3", "1", "3+", "1", "6+"]);
    const mind = profile?.mind || ["7+", "7+", "7+", "7+"];
    return (
        <div className="gang-statline">
            <table aria-label={`${model.name} characteristics`}>
                <tbody>
                    <tr>
                        {physical.map((name) => (
                            <th scope="col" key={name}>
                                {name}
                            </th>
                        ))}
                    </tr>
                    <tr>
                        {stats.map((value, i) => (
                            <td key={i}>{value}</td>
                        ))}
                    </tr>
                    <tr className="gang-book-header">
                        {mental.map((name) => (
                            <th scope="col" key={name}>
                                {name}
                            </th>
                        ))}
                        <th scope="col" colSpan={4}>
                            Type
                        </th>
                        <th scope="col">XP</th>
                    </tr>
                    <tr className="gang-book-values">
                        {mind.map((value, i) => (
                            <td key={i}>{value}</td>
                        ))}
                        <td colSpan={4}>
                            {pet
                                ? "Fighter (Beast, Pet)"
                                : model.subtypes?.includes("Vehicle")
                                  ? "Vehicle"
                                  : `Fighter (${archetypes[model.rank] || "Ganger"})`}
                        </td>
                        <td>{profile?.xp || "0/–"}</td>
                    </tr>
                </tbody>
            </table>
        </div>
    );
}
function ModelDetails({ model, pet }) {
    const rows = [
        ...(model.counters || []),
        ["Skills", profiles[model.id]?.skills || "—"],
        ...(model.rules ? [["Rules", model.rules]] : []),
        ...(model.powers ? [["Powers", model.powers]] : []),
        ["Gear", pet ? "—" : (model.pets || []).join(", ") || "Flak armour"],
        ...(model.gearGroups || []),
        ...(!pet
            ? [["Gang legacy", <span className="gang-slot">House Escher</span>]]
            : []),
    ];
    return (
        <dl className="gang-model-details">
            {rows.map(([label, value]) => (
                <React.Fragment key={label}>
                    <dt>{label}</dt>
                    <dd>{value}</dd>
                </React.Fragment>
            ))}
        </dl>
    );
}
export function ModelCard({ node, pet, owner, index }) {
    const [info, setInfo] = useState(null);
    const [status, setStatus] = useState(undefined);
    const [picture, setPicture] = useState(null);
    const cardRef = useRef(null);
    useEffect(() => {
        if (picture) cardRef.current?.querySelector(".gang-portrait")?.focus();
    }, [picture]);
    useEffect(
        () => () => {
            if (picture) URL.revokeObjectURL(picture);
        },
        [picture],
    );
    const model = pet
        ? {
              id: `${node.id}-pet-${index}`,
              name: pet,
              rating: 0,
              type: pet,
              rank: 5,
              gear: "—",
          }
        : { ...M.models[node.id], id: node.id };
    const example = pet ? {} : cardExamples[node.id] || {};
    Object.assign(model, example);
    if (picture) model.image = picture;
    if (status !== undefined) model.status = status;
    const gear = model.gear.split(" · ");
    const edge = useMemo(() => nameplateEdge(model.name, true), [model.name]);
    return (
        <article
            ref={cardRef}
            data-status={model.status || undefined}
            id={`model-${model.id}`}
            data-flip={`card-${model.id}`}
            data-striped=""
            className={`gang-card gang-material gang-new callout-frame ${pet ? "gang-pet" : ""}`}
        >
            <header
                className="gang-card-header"
                style={{ "--nameplate-edge": edge }}
            >
                <a
                    className="gang-header-link"
                    href="#"
                    onClick={(event) => {
                        event.preventDefault();
                        setInfo("Edit model");
                    }}
                    aria-label={`Edit ${model.name}`}
                    title={`${model.name}\n${model.type}`}
                />
                <div className="gang-card-title">
                    <ModelName model={model} pet={pet} owner={owner} />
                    <div className="gang-header-marks">
                        {model.image && (
                            <Portrait
                                model={model}
                                onPicture={() => setInfo("picture")}
                            />
                        )}
                        {!model.image && (
                            <ModelPictureUpload
                                name={model.name}
                                onSave={(blob) =>
                                    setPicture(URL.createObjectURL(blob))
                                }
                            />
                        )}
                        <span
                            className="gang-rating"
                            title="Rating, including weapons and wargear"
                        >
                            {model.rating}¢
                            <span className="cm-sr">
                                {" "}
                                rating, including weapons and wargear
                            </span>
                        </span>
                    </div>
                </div>
            </header>
            {model.actions?.length > 0 && (
                <button
                    className="gang-model-prompt"
                    onClick={() => setInfo("actions")}
                    aria-label={`Actions available for ${model.name}: ${model.actions.join(", ")}`}
                >
                    <Icon icon={CircleFadingArrowUp} size={16} />
                    <span>
                        {model.actions.length > 1
                            ? "Multiple actions available"
                            : model.actions[0]}
                    </span>
                    {model.actions.length === 1 && <small>Available</small>}
                    <Icon icon={ArrowRight} size={14} />
                </button>
            )}
            <CardTabs
                model={model}
                onAction={setInfo}
                onPicture={() => setInfo("picture")}
                onCards={() => setInfo("cards")}
            >
                <div className="gang-card-information">
                    <Statline model={model} pet={pet} />
                    <ModelDetails model={model} pet={pet} />
                </div>
                <div className="gang-weapons">
                    <table aria-label={`${model.name} weapons`}>
                        <thead>
                            <tr>
                                <th scope="col">Weapons</th>
                                {["SR", "LR", "Str", "AP", "L"].map((name) => (
                                    <th scope="col" key={name}>
                                        {name}
                                    </th>
                                ))}
                                <th
                                    scope="col"
                                    className="gang-weapon-trait-column"
                                >
                                    Traits
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            {(pet ? ["Claws and teeth"] : gear).map(
                                (weapon, i) => (
                                    <React.Fragment key={weapon}>
                                        <tr>
                                            <td>{weapon}</td>
                                            {(i === 0 && !pet
                                                ? ["6″", "12″", "3", "–", "1"]
                                                : ["E", "–", "S", "–", "1"]
                                            ).map((value, j) => (
                                                <td key={j}>{value}</td>
                                            ))}
                                            <td className="gang-weapon-trait-column">
                                                {weaponTraits[weapon] || "—"}
                                            </td>
                                        </tr>
                                        {model.accessories?.[weapon] && (
                                            <tr className="gang-weapon-accessory">
                                                <td colSpan={7}>
                                                    +{" "}
                                                    {model.accessories[weapon]}
                                                </td>
                                            </tr>
                                        )}
                                    </React.Fragment>
                                ),
                            )}
                        </tbody>
                    </table>
                </div>
            </CardTabs>
            {info && (
                <InfoDialog
                    title={
                        info === "picture"
                            ? `${model.name} · Picture`
                            : info === "actions"
                              ? `${model.name} · Available actions`
                              : info === "cards"
                                ? `${model.name} · Model cards`
                                : `${model.name} · ${info}`
                    }
                    onClose={() => setInfo(null)}
                >
                    {info === "picture" ? (
                        <img
                            className="gang-picture-preview"
                            src={model.image}
                            alt={`Picture of ${model.name}`}
                        />
                    ) : info === "actions" ? (
                        <>
                            <p>Sample actions for this design preview:</p>
                            <ul>
                                {model.actions.map((action) => (
                                    <li key={action}>{action}</li>
                                ))}
                            </ul>
                        </>
                    ) : info === "cards" ? (
                        <p>All equipment · {model.rating}¢</p>
                    ) : info === "Mark as…" ? (
                        <div className="gang-status-options">
                            {[
                                "Active",
                                "In recovery",
                                "Captured",
                                "Dead",
                                "Destroyed",
                            ].map((label) => (
                                <Button
                                    variant="default"
                                    key={label}
                                    onClick={() => {
                                        setStatus(
                                            label === "Active" ? "" : label,
                                        );
                                        setInfo(null);
                                    }}
                                >
                                    {label}
                                </Button>
                            ))}
                        </div>
                    ) : (
                        <p>
                            {info} for {model.name}. This action is simulated in
                            the design preview.
                        </p>
                    )}
                </InfoDialog>
            )}
        </article>
    );
}
