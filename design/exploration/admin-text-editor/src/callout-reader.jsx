import React, { useEffect, useRef, useState } from "react";
import {
    Info,
    Scan,
    ArrowDown,
    ArrowUp,
    ChevronLeft,
    ChevronRight,
    icons as libraryIcons,
} from "lucide-react";
import iconNames from "./lucide-icons.json";
import { RichBody } from "./rich-body";
const iconComponent = (name) => libraryIcons[iconNames[name]] || Info;
function safeHref(value) {
    if (!value?.trim()) return undefined;
    try {
        const url = new URL(value, location.origin);
        return ["http:", "https:"].includes(url.protocol)
            ? url.href
            : undefined;
    } catch {
        return undefined;
    }
}
function Paragraphs({ text, rich, budget }) {
    if (rich) return <RichBody document={rich} budget={budget} />;
    if (!text) return null;
    return text
        .split(/\n\n+/)
        .map((paragraph, index) => <p key={index}>{paragraph}</p>);
}
function Chrome({ config, eyebrow = config.eyebrow }) {
    const Icon = iconComponent(config.icon);
    return (
        <div className="callout-card__chrome">
            <div className="callout-card__meta">
                <span className="callout-card__icon">
                    <Icon className="lucide" strokeWidth={1.7} />
                </span>
                <span className="callout-card__label">{config.label}</span>
            </div>
            {eyebrow && (
                <span className="callout-card__eyebrow">
                    {eyebrow}
                    <Scan className="lucide" strokeWidth={1.7} />
                </span>
            )}
        </div>
    );
}
function calloutStyle(config) {
    return {
        "--theme":
            config.colour === "default"
                ? "var(--color-box-border)"
                : `var(--color-${config.colour}-500)`,
    };
}
function CardBody({ config, open, typed, detail }) {
    const body = <Paragraphs text={config.body} rich={config.bodyRich} />;
    const revealed = (rich) => (
        <Paragraphs text={typed} rich={rich} budget={typed.length} />
    );
    switch (config.type) {
        case "link-cluster":
            return (
                <>
                    {body}
                    <ul className="callout-card__links">
                        {config.links.map((link, index) => (
                            <li key={link.id || index}>
                                <a href={safeHref(link.href)}>{link.label}</a>
                            </li>
                        ))}
                    </ul>
                </>
            );
        case "mail-link": {
            const valid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(config.recipient);
            const href = valid
                ? `mailto:${config.recipient}?subject=${encodeURIComponent(config.eyebrow || "Hello")}`
                : undefined;
            return (
                <>
                    {body}
                    <p>
                        <a className="callout-card__mail-link" href={href}>
                            {config.recipient || "Email the team"}
                        </a>
                    </p>
                </>
            );
        }
        case "example":
            return open && revealed(config.bodyRich);
        case "expanding-info":
            return (
                <>
                    {body}
                    {open ? (
                        <div className="disclosure__detail">
                            {revealed(config.detailRich)}
                            {typed.length < detail.length && (
                                <span
                                    className="typewriter-cursor"
                                    aria-hidden="true"
                                >
                                    _
                                </span>
                            )}
                        </div>
                    ) : (
                        <span className="typewriter-cursor" aria-hidden="true">
                            _
                        </span>
                    )}
                </>
            );
        default:
            return body;
    }
}

function ReaderCard({ config }) {
    const [open, setOpen] = useState(false);
    const [typed, setTyped] = useState("");
    const expandable = ["expanding-info", "example"].includes(config.type);
    const detail = config.type === "example" ? config.body : config.detail;
    useEffect(() => {
        if (!open) {
            setTyped("");
            return;
        }
        if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
            setTyped(detail);
            return;
        }
        let length = 0;
        setTyped("");
        const timer = setInterval(() => {
            length += Math.max(1, Math.ceil(detail.length / 200));
            setTyped(detail.slice(0, length));
            if (length >= detail.length) clearInterval(timer);
        }, 5);
        return () => clearInterval(timer);
    }, [open, detail]);
    const content = (
        <>
            <Chrome config={config} />
            <div
                className="callout-card__body"
                onClick={() => {
                    if (expandable && !open) setOpen(true);
                }}
            >
                <CardBody
                    config={config}
                    open={open}
                    typed={typed}
                    detail={detail}
                />
            </div>
            {expandable && (
                <button
                    type="button"
                    className="disclosure__toggle"
                    aria-expanded={open}
                    onClick={() => setOpen(!open)}
                >
                    {open ? (
                        <ArrowUp className="lucide" />
                    ) : (
                        <ArrowDown className="lucide" />
                    )}
                    {config.type === "example"
                        ? open
                            ? "Collapse example"
                            : "Show me an example"
                        : open
                          ? "Collapse"
                          : "Expand"}
                </button>
            )}
        </>
    );
    const props = {
        className: `callout-card ${open ? "is-open" : ""}`,
        style: calloutStyle(config),
        "data-card-type": config.type,
        "data-colour": config.colour,
        "data-glow": config.glow ? "" : undefined,
        "data-striped": config.striped ? "" : undefined,
    };
    return config.type === "download" ? (
        <a
            {...props}
            className="callout-card callout-card--download"
            href={safeHref(config.href)}
            download
        >
            {content}
        </a>
    ) : (
        <aside {...props}>{content}</aside>
    );
}
function Carousel({ config }) {
    const [active, setActive] = useState(0);
    const track = useRef(null);
    const trackWidth = useRef(0);
    const activeIndex = useRef(0);
    const resizing = useRef(false);
    const show = (index) => {
        const el = track.current;
        index = Math.max(0, Math.min(config.slides.length - 1, index));
        if (!el?.children[index]) return;
        activeIndex.current = index;
        setActive(index);
        el.scrollTo({
            left: el.children[index].offsetLeft - el.children[0].offsetLeft,
            behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
                ? "auto"
                : "smooth",
        });
    };
    useEffect(() => {
        const el = track.current;
        let frame = 0,
            settledFrame = 0;
        const resize = new ResizeObserver(() => {
            const card = el.children[active];
            if (card) el.style.height = getComputedStyle(card).height;
            if (el.clientWidth !== trackWidth.current) {
                trackWidth.current = el.clientWidth;
                resizing.current = true;
                const align = () => {
                    const index = Math.min(
                        activeIndex.current,
                        el.children.length - 1,
                    );
                    if (!el.children[index]) return;
                    el.scrollLeft =
                        el.children[index].offsetLeft -
                        el.children[0].offsetLeft;
                };
                align();
                cancelAnimationFrame(frame);
                cancelAnimationFrame(settledFrame);
                frame = requestAnimationFrame(() => {
                    align();
                    settledFrame = requestAnimationFrame(() => {
                        resizing.current = false;
                    });
                });
            }
        });
        resize.observe(el);
        [...el.children].forEach((child) => resize.observe(child));
        return () => {
            resize.disconnect();
            cancelAnimationFrame(frame);
            cancelAnimationFrame(settledFrame);
            resizing.current = false;
        };
    }, [active, config]);
    return (
        <section
            className="callout-carousel"
            data-colour={config.colour}
            data-glow={config.glow ? "" : undefined}
            style={calloutStyle(config)}
            aria-label={config.label || "Frequently asked questions"}
        >
            <nav
                className="callout-carousel__indicators"
                aria-label="Choose a card"
            >
                {config.slides.map((_, index) => (
                    <button
                        key={index}
                        type="button"
                        className="callout-carousel__indicator"
                        aria-label={`Show card ${index + 1}`}
                        aria-current={index === active ? "true" : undefined}
                        onClick={() => show(index)}
                    />
                ))}
            </nav>
            <div className="callout-carousel__frame">
                <button
                    type="button"
                    className="callout-carousel__arrow callout-carousel__arrow--previous"
                    aria-label="Previous card"
                    disabled={active === 0}
                    onClick={() => show(active - 1)}
                >
                    <ChevronLeft className="lucide" />
                </button>
                <div
                    className="callout-carousel__track"
                    tabIndex={0}
                    ref={track}
                    onScroll={() => {
                        const el = track.current;
                        if (
                            resizing.current ||
                            el.clientWidth !== trackWidth.current
                        )
                            return;
                        const index = Math.max(
                            0,
                            Math.min(
                                config.slides.length - 1,
                                Math.round(
                                    el.scrollLeft /
                                        (el.children[0].offsetWidth +
                                            parseFloat(
                                                getComputedStyle(el).gap,
                                            )),
                                ),
                            ),
                        );
                        activeIndex.current = index;
                        setActive(index);
                    }}
                >
                    {config.slides.map((slide, index) => (
                        <article
                            key={index}
                            className="callout-card"
                            data-card-type="carousel"
                            data-colour={config.colour}
                            data-glow={config.glow ? "" : undefined}
                            data-striped={config.striped ? "" : undefined}
                            style={calloutStyle(config)}
                        >
                            <Chrome config={config} eyebrow={slide.eyebrow} />
                            <div className="callout-card__body">
                                <Paragraphs
                                    text={slide.body}
                                    rich={slide.bodyRich}
                                />
                            </div>
                        </article>
                    ))}
                </div>
                <button
                    type="button"
                    className="callout-carousel__arrow callout-carousel__arrow--next"
                    aria-label="Next card"
                    disabled={active === config.slides.length - 1}
                    onClick={() => show(active + 1)}
                >
                    <ChevronRight className="lucide" />
                </button>
            </div>
        </section>
    );
}
export function CalloutReader({ config }) {
    return config.type === "carousel" ? (
        <Carousel config={config} />
    ) : (
        <ReaderCard config={config} />
    );
}
