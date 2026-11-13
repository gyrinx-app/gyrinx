import React, { useLayoutEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { SunMoon } from "lucide-react";
import { Button } from "./controls.jsx";
import { ModelCard } from "./model-card.jsx";
import { models } from "./models.js";
import cotton from "./cotton.json";

const host = document.querySelector("#gang-root");
const shadow = host.attachShadow({ mode: "open" });
const stylesheet = document.createElement("link");
stylesheet.rel = "stylesheet";
stylesheet.href = host.dataset.themeUrl;
shadow.append(stylesheet);
const root = document.createElement("div");
shadow.append(root);
const colours = cotton.colours.map((option) => option.name.toLowerCase());
const requested = new URLSearchParams(location.search).get("colour");

function Gallery() {
    const [colour, setColour] = useState(
        colours.includes(requested) ? requested : "sky",
    );
    const [dark, setDark] = useState(false);
    const [ratingInk, setRatingInk] = useState("black");
    const ref = useRef(null);
    const option = cotton.colours[colours.indexOf(colour)];
    useLayoutEffect(() => {
        host.classList.toggle("dark", dark);
    }, [dark]);
    useLayoutEffect(() => {
        function updateContrast() {
            // Resolve N26's CSS colour space through the browser before measuring luminance.
            const canvas = document.createElement("canvas");
            canvas.width = canvas.height = 1;
            const context = canvas.getContext("2d");
            if (!context) return;
            context.fillStyle = getComputedStyle(ref.current)
                .getPropertyValue("--gang-theme")
                .trim();
            context.fillRect(0, 0, 1, 1);
            const channels = [...context.getImageData(0, 0, 1, 1).data]
                .slice(0, 3)
                .map((value) => {
                    const channel = value / 255;
                    return channel <= 0.04045
                        ? channel / 12.92
                        : ((channel + 0.055) / 1.055) ** 2.4;
                });
            const luminance =
                channels[0] * 0.2126 +
                channels[1] * 0.7152 +
                channels[2] * 0.0722;
            setRatingInk(
                (luminance + 0.05) / 0.05 >= 1.05 / (luminance + 0.05)
                    ? "black"
                    : "white",
            );
        }
        if (stylesheet.sheet) updateContrast();
        else
            stylesheet.addEventListener("load", updateContrast, { once: true });
        return () => stylesheet.removeEventListener("load", updateContrast);
    }, [colour]);
    return (
        <main
            ref={ref}
            className="gang-page"
            style={{
                "--gang-theme": `var(${option.token})`,
                "--gang-rating-ink": ratingInk,
            }}
        >
            <header className="gallery-heading">
                <div>
                    <h1>Gang card redesign</h1>
                    <p>
                        Model-card design preview. Pictures and status changes
                        last until reload. Actions are simulated.
                    </p>
                </div>
                <label className="gang-theme-picker">
                    <span className={cotton.label}>Gang colour</span>
                    <select
                        aria-label="Gang colour"
                        className={cotton.select.className}
                        style={cotton.select.style}
                        value={colour}
                        onChange={(event) => {
                            setColour(event.target.value);
                            const url = new URL(location.href);
                            url.searchParams.set("colour", event.target.value);
                            history.replaceState(history.state, "", url);
                        }}
                    >
                        {cotton.colours.map((option) => (
                            <option
                                key={option.name}
                                value={option.name.toLowerCase()}
                            >
                                {option.name}
                            </option>
                        ))}
                    </select>
                </label>
                <Button
                    variant="default"
                    icon={SunMoon}
                    aria-label="Toggle dark mode"
                    aria-pressed={dark}
                    onClick={() => setDark(!dark)}
                >
                    Theme
                </Button>
            </header>
            <div className="gallery-cards">
                {Object.entries(models).flatMap(([id, model]) => [
                    <ModelCard key={id} node={{ id }} />,
                    ...(model.pets || []).map((pet, index) => (
                        <ModelCard
                            key={`${id}-pet-${index}`}
                            node={{ id }}
                            pet={pet}
                            owner={model.name}
                            index={index}
                        />
                    )),
                ])}
            </div>
        </main>
    );
}
createRoot(root).render(<Gallery />);
