import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
    ArrowRight,
    ChevronLeft,
    ChevronRight,
    Menu,
    Moon,
    Sun,
    X,
} from "lucide-react";
import cotton from "./homepage.json";

const live = "https://gyrinx.app";
const features = [
    {
        label: "Gangs",
        title: "Build and manage your gangs",
        body: "Gyrinx is a powerful set of tools for building and running your Necromunda gangs — making the game simpler whatever your level of experience.",
    },
    {
        label: "Content",
        title: "All the latest content as it lands",
        body: "Gyrinx is kept up to date with the latest Necromunda rules as they drop. We offer full support for both Necromunda Skirmish (N26) and N23.",
    },
    {
        label: "Campaigns",
        title: "Take the hassle out of arbitration",
        body: "Running a campaign can get complicated. Gyrinx helps you manage all the key parts of campaigns, and supports custom content and rules.",
    },
];
function Glyph({ icon: Component, ...props }) {
    return (
        <Component size={18} strokeWidth={1.7} aria-hidden="true" {...props} />
    );
}
function LinkButton({ href, variant = "default", children }) {
    return (
        <a href={href} className={cotton.linkButton[variant]}>
            {children}
        </a>
    );
}
function FeatureCards() {
    const track = useRef(null);
    const [active, setActive] = useState(0);
    function show(index) {
        const el = track.current;
        const card = el.children[index];
        el.scrollTo({
            left: card.offsetLeft - el.children[0].offsetLeft,
            behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
                ? "instant"
                : "smooth",
        });
    }
    useEffect(() => {
        const el = track.current;
        const resize = new ResizeObserver(() => {
            el.scrollLeft = 0;
            setActive(0);
        });
        resize.observe(el);
        return () => resize.disconnect();
    }, []);
    return (
        <section className="home-features" aria-label="Gyrinx features">
            <div
                ref={track}
                className="home-feature-track"
                id="feature-cards"
                onScroll={() => {
                    const el = track.current;
                    const step =
                        el.children[1].offsetLeft - el.children[0].offsetLeft;
                    setActive(
                        Math.max(
                            0,
                            Math.min(
                                features.length - 1,
                                Math.round(el.scrollLeft / step),
                            ),
                        ),
                    );
                }}
                onKeyDown={(event) => {
                    if (
                        !["ArrowLeft", "ArrowRight", "Home", "End"].includes(
                            event.key,
                        )
                    )
                        return;
                    event.preventDefault();
                    show(
                        event.key === "Home"
                            ? 0
                            : event.key === "End"
                              ? features.length - 1
                              : Math.max(
                                    0,
                                    Math.min(
                                        features.length - 1,
                                        active +
                                            (event.key === "ArrowRight"
                                                ? 1
                                                : -1),
                                    ),
                                ),
                    );
                }}
                tabIndex={0}
                aria-label="Features: use the arrow keys or swipe on mobile"
            >
                {features.map(({ label, title, body }, index) => (
                    <article
                        className="callout-card home-feature"
                        data-colour="default"
                        data-striped=""
                        key={label}
                        aria-labelledby={`feature-title-${index}`}
                    >
                        <div className="callout-card__body">
                            <h2 id={`feature-title-${index}`}>{title}</h2>
                            <p>{body}</p>
                        </div>
                    </article>
                ))}
            </div>
            <nav
                className="home-carousel-controls"
                aria-label="Feature carousel"
            >
                <button
                    type="button"
                    aria-label="Previous card"
                    title="Previous card"
                    aria-controls="feature-cards"
                    disabled={active === 0}
                    onClick={() => show(active - 1)}
                >
                    <Glyph icon={ChevronLeft} />
                </button>
                <div className="home-carousel-dots">
                    {features.map(({ label }, index) => (
                        <button
                            type="button"
                            key={label}
                            aria-label={`Show ${label.toLowerCase()} card`}
                            title={`Show ${label.toLowerCase()} card`}
                            aria-controls="feature-cards"
                            aria-current={active === index ? "true" : undefined}
                            onClick={() => show(index)}
                        >
                            <span />
                        </button>
                    ))}
                </div>
                <span className="home-sr-only" role="status" aria-live="polite">
                    Card {active + 1} of {features.length}:{" "}
                    {features[active].label}
                </span>
                <button
                    type="button"
                    aria-label="Next card"
                    title="Next card"
                    aria-controls="feature-cards"
                    disabled={active === features.length - 1}
                    onClick={() => show(active + 1)}
                >
                    <Glyph icon={ChevronRight} />
                </button>
            </nav>
        </section>
    );
}
function LoginPreview() {
    const [username, setUsername] = useState("");
    const [submitted, setSubmitted] = useState(false);
    const usernameIsEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(username.trim());
    return (
        <section className="home-invitation" aria-label="Sign in">
            <div className="home-login">
                <form
                    onSubmit={(event) => {
                        event.preventDefault();
                        event.currentTarget.reset();
                        setUsername("");
                        setSubmitted(true);
                    }}
                >
                    <div className="home-login-field">
                        <label className={cotton.label} htmlFor="home-username">
                            Username
                        </label>
                        <div className={cotton.input.root}>
                            <input
                                className={cotton.input.control}
                                id="home-username"
                                name="login"
                                placeholder="Username"
                                autoComplete="username"
                                required
                                value={username}
                                onChange={(event) =>
                                    setUsername(event.target.value)
                                }
                                aria-describedby={
                                    usernameIsEmail
                                        ? "home-username-hint"
                                        : undefined
                                }
                            />
                        </div>
                        {usernameIsEmail && (
                            <p id="home-username-hint" role="status">
                                Use your username to sign in.
                            </p>
                        )}
                    </div>
                    <div className="home-login-field">
                        <label className={cotton.label} htmlFor="home-password">
                            Password
                        </label>
                        <div className={cotton.input.root}>
                            <input
                                className={cotton.input.control}
                                id="home-password"
                                name="password"
                                type="password"
                                placeholder="Password"
                                autoComplete="current-password"
                                required
                            />
                        </div>
                        <a
                            className="home-forgot-password"
                            href={`${live}/accounts/password/reset/`}
                        >
                            Forgot your password?
                        </a>
                    </div>
                    <label className="home-remember">
                        <input type="checkbox" name="remember" />
                        Remember me
                    </label>
                    <button type="submit" className={cotton.button.primary}>
                        Sign in <Glyph icon={ArrowRight} size={16} />
                    </button>
                    {submitted && (
                        <p className="home-login-status" role="status">
                            This is a design preview.{" "}
                            <a href={`${live}/accounts/login/`}>
                                Sign in on Gyrinx
                            </a>
                            .
                        </p>
                    )}
                </form>
                <nav
                    className="home-register-options"
                    aria-label="More about Gyrinx"
                >
                    <a href={`${live}/accounts/signup/`}>Create an account</a>
                    <span aria-hidden="true">·</span>
                    <a href={`${live}/about/`} className="home-about-link">
                        About Gyrinx
                    </a>
                </nav>
            </div>
        </section>
    );
}
function Homepage({ host }) {
    const [dark, setDark] = useState(() => {
        try {
            const value = localStorage.getItem("gyrinx-homepage-theme");
            return value
                ? value === "dark"
                : matchMedia("(prefers-color-scheme: dark)").matches;
        } catch {
            return false;
        }
    });
    const drawer = useRef(null);
    useEffect(() => {
        host.classList.toggle("dark", dark);
        try {
            localStorage.setItem(
                "gyrinx-homepage-theme",
                dark ? "dark" : "light",
            );
        } catch {
            /* Theme still works when storage is unavailable. */
        }
    }, [dark, host]);
    return (
        <div className={`home-page ${dark ? "dark" : ""}`}>
            <a
                className="home-skip"
                href="#main"
                onClick={(event) => {
                    event.preventDefault();
                    host.shadowRoot.getElementById("main").focus();
                }}
            >
                Skip to content
            </a>
            <header className="n26-site-nav home-header dark">
                <div className="home-nav-inner">
                    <a
                        className="n26-site-brand"
                        href="/homepage/"
                        aria-label="Gyrinx home"
                    >
                        <img
                            src="/static/homepage/logo.svg"
                            alt=""
                            width="24"
                            height="24"
                        />
                        <span>Gyrinx</span>
                    </a>
                    <div className="home-nav-actions">
                        <button
                            className={cotton.button.ghost}
                            type="button"
                            aria-label={
                                dark ? "Use light theme" : "Use dark theme"
                            }
                            title={dark ? "Use light theme" : "Use dark theme"}
                            onClick={() => setDark(!dark)}
                        >
                            <Glyph icon={dark ? Sun : Moon} />
                        </button>
                        <LinkButton href={`${live}/accounts/login/`}>
                            Sign in
                        </LinkButton>
                        <LinkButton
                            href={`${live}/accounts/signup/`}
                            variant="primary"
                        >
                            Sign up
                        </LinkButton>
                        <span className="home-nav-divider" />
                        <button
                            className={cotton.button.ghost}
                            type="button"
                            aria-label="Open navigation menu"
                            title="Open navigation menu"
                            onClick={() => drawer.current.showModal()}
                        >
                            <Glyph icon={Menu} size={20} />
                        </button>
                    </div>
                </div>
            </header>
            <main id="main" tabIndex={-1}>
                <section className="home-hero" aria-labelledby="home-title">
                    <img
                        className="home-hero-image"
                        src="/static/homepage/hero.webp"
                        width="1440"
                        height="554"
                        decoding="async"
                        alt=""
                        fetchPriority="high"
                    />
                    <div className="home-hero-shade" />
                    <div className="n26-site-container home-hero-content">
                        <h1 id="home-title">
                            <strong>Gyrinx:</strong>{" "}
                            <span className="home-keep-word">open-source</span>{" "}
                            tools for the Necromunda community.
                        </h1>
                    </div>
                </section>
                <div className="n26-site-container home-content-grid">
                    <LoginPreview />
                    <FeatureCards />
                    <aside className="home-updates" aria-label="Latest updates">
                        <div
                            dangerouslySetInnerHTML={{
                                __html: cotton.changelog,
                            }}
                        />
                    </aside>
                </div>
            </main>
            <div
                className="home-footer-slot"
                dangerouslySetInnerHTML={{ __html: cotton.footer }}
            />
            <dialog
                ref={drawer}
                className="home-drawer"
                aria-labelledby="home-navigation-title"
                onClick={(event) => {
                    if (event.target === drawer.current) drawer.current.close();
                }}
            >
                <div className="home-drawer-inner">
                    <div className="home-drawer-heading">
                        <span id="home-navigation-title">Gyrinx</span>
                        <button
                            className={cotton.button.ghost}
                            type="button"
                            title="Close navigation menu"
                            aria-label="Close navigation menu"
                            onClick={() => drawer.current.close()}
                        >
                            <Glyph icon={X} />
                        </button>
                    </div>
                    <nav aria-label="Main navigation">
                        <a href="/homepage/">Home</a>
                        <a href={`${live}/dice/`}>Dice roller</a>
                        <a href={`${live}/help/`}>Help</a>
                        <a href={`${live}/about/`}>About Gyrinx</a>
                    </nav>
                </div>
            </dialog>
        </div>
    );
}
const host = document.querySelector("[data-homepage-host]");
const shadow = host.attachShadow({ mode: "open" });
const stylesheet = document.createElement("link");
stylesheet.rel = "stylesheet";
stylesheet.href = "/static/homepage.css" + new URL(import.meta.url).search;
shadow.append(stylesheet);
const root = document.createElement("div");
shadow.append(root);
createRoot(root).render(<Homepage host={host} />);
