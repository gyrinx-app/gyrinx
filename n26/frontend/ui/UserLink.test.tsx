import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import cotton from "../generated/cotton.json";
import { Toggle, UserLink, type BadgeMark } from ".";

const guilder: BadgeMark = {
    label: "Guilder supporter",
    svg: {
        tag: "svg",
        props: { viewBox: "0 0 24 24", shapeRendering: "crispEdges" },
        children: [
            { tag: "rect", props: { x: "1", y: "2", width: "3", height: "4" } },
            { tag: "title", props: {}, children: ["Guilder"] },
        ],
    },
};

describe("UserLink", () => {
    it("links the name and names the badge as an image", () => {
        render(<UserLink name="vex" href="/n26/users/@vex/" badge={guilder} />);
        const link = screen.getByRole("link", { name: /vex/ });
        expect(link.getAttribute("href")).toBe("/n26/users/@vex/");
        expect(link.className).toBe(cotton.userLink.link);
        const mark = screen.getByRole("img", { name: "Guilder supporter" });
        expect(mark.getAttribute("title")).toBe("Guilder supporter");
        const svg = mark.querySelector("svg")!;
        expect(svg.getAttribute("viewBox")).toBe("0 0 24 24");
        expect(svg.getAttribute("shape-rendering")).toBe("crispEdges");
        expect(svg.getAttribute("aria-hidden")).toBe("true");
        expect(svg.querySelector("rect")?.getAttribute("width")).toBe("3");
    });

    it("draws the name alone when there is no badge", () => {
        render(<UserLink name="kesh" href="/n26/users/@kesh/" />);
        expect(screen.getByRole("link").textContent).toBe("kesh");
        expect(screen.queryByRole("img")).toBeNull();
    });

    it("draws nothing from the tree that the allowlist would refuse", () => {
        const hostile: BadgeMark = {
            label: "Odd",
            svg: {
                tag: "svg",
                props: { viewBox: "0 0 1 1", onLoad: "x()", style: "fill:red" },
                children: [
                    { tag: "script", props: {}, children: ["alert(1)"] },
                    { tag: "foreignObject", props: {} },
                    { tag: "use", props: { href: "https://example.com/a" } },
                    { tag: "use", props: { href: "#a" } },
                ],
            },
        };
        const { container } = render(
            <UserLink name="odd" href="/u/" badge={hostile} />,
        );
        const svg = container.querySelector("svg")!;
        expect(svg.getAttribute("style")).toBeNull();
        expect(svg.getAttribute("onload")).toBeNull();
        expect(container.querySelector("script")).toBeNull();
        expect(container.querySelector("foreignObject")).toBeNull();
        const uses = container.querySelectorAll("use");
        expect([...uses].map((use) => use.getAttribute("href"))).toEqual([
            null,
            "#a",
        ]);
    });
});

describe("Toggle", () => {
    function Harness() {
        const [on, setOn] = useState(true);
        return (
            <>
                <Toggle
                    label="Hide gangs"
                    checked={on}
                    onCheckedChange={setOn}
                />
                <output>{on ? "on" : "off"}</output>
            </>
        );
    }

    it("flips from its switch and from its words, once each", async () => {
        const user = userEvent.setup();
        render(<Harness />);
        const control = screen.getByRole("switch", { name: "Hide gangs" });
        expect(control.getAttribute("aria-checked")).toBe("true");
        await user.click(control);
        expect(screen.getByRole("status").textContent).toBe("off");
        await user.click(screen.getByText("Hide gangs"));
        expect(screen.getByRole("status").textContent).toBe("on");
    });
});
