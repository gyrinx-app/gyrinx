import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { RadioCard, RadioCards } from "./index";

test("selection captions and errors describe the group while card details stay in its native label", () => {
    const { container } = render(
        <form>
            <RadioCards
                legend="Primary"
                description="Select one skill."
                errors={["Select a skill before saving."]}
            >
                <RadioCard
                    name="thing"
                    value="catfall"
                    label="Catfall"
                    description="Already known"
                    wrap={false}
                    checked
                    onChange={() => {}}
                    details={
                        <>
                            <span>Choose a landing position.</span>
                            <span>Rating 10¢</span>
                        </>
                    }
                />
            </RadioCards>
        </form>,
    );
    const group = screen.getByRole("group", { name: "Primary" });
    const descriptions = group
        .getAttribute("aria-describedby")!
        .split(" ")
        .map((id) => document.getElementById(id)?.textContent);
    expect(descriptions).toEqual([
        "Select one skill.",
        "Select a skill before saving.",
    ]);
    const radio = screen.getByRole("radio") as HTMLInputElement;
    const label = radio.closest("label")!;
    expect(label.textContent).toContain("Rating 10¢");
    expect(label.querySelector(".truncate")).not.toBeNull();
    expect(
        screen.getByText("Choose a landing position.").parentElement?.className,
    ).toContain("border-t");
    expect(new FormData(container.querySelector("form")!).get("thing")).toBe(
        "catfall",
    );
});
