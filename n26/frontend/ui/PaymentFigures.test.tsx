import { render } from "@testing-library/react";
import { expect, test } from "vitest";
import { PaymentFigures } from "./index";

test("payment shows the formatted Available and Price columns without a remainder", () => {
    const { container } = render(
        <PaymentFigures
            figures={{
                label: "",
                available: "0¢",
                price: "0¢",
                remaining: "18¢",
            }}
        />,
    );
    expect(
        Array.from(
            container.querySelectorAll("dt"),
            (term) => term.textContent,
        ),
    ).toEqual(["Available", "Price"]);
    expect(
        Array.from(
            container.querySelectorAll("dd"),
            (value) => value.textContent,
        ),
    ).toEqual(["0¢", "0¢"]);
    expect(container.textContent).not.toContain("18¢");
    expect(container.querySelectorAll("dd span").length).toBe(2);
});

test("payment keeps resource units beside zero prices and unlimited balances", () => {
    const { container } = render(
        <PaymentFigures
            figures={{
                label: "XP",
                available: "Unlimited",
                price: "0",
                remaining: "Unlimited",
            }}
        />,
    );
    expect(
        Array.from(container.querySelectorAll("dd"), (value) =>
            Array.from(value.children, (part) => part.textContent),
        ),
    ).toEqual([
        ["Unlimited", "XP"],
        ["0", "XP"],
    ]);
});

test("empty formatted figures remain empty", () => {
    const { container } = render(
        <PaymentFigures
            figures={{ label: "", available: "", price: "", remaining: "" }}
        />,
    );
    expect(
        Array.from(
            container.querySelectorAll("dd"),
            (value) => value.textContent,
        ),
    ).toEqual(["", ""]);
    expect(container.querySelectorAll("dd span").length).toBe(2);
});
