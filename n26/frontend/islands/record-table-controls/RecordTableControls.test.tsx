import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mount } from "./entry";

let disposers: (() => void)[] = [];
afterEach(() => {
    act(() => disposers.forEach((dispose) => dispose()));
    disposers = [];
    document.body.innerHTML = "";
});

async function listings() {
    document.body.innerHTML = `
        <section data-record-table id="gangs">
          <div id="gang-controls"></div><span data-record-count></span>
          <span data-record-noun></span>
          <div data-record-row data-record-type="Goliath" data-record-search="rust kings goliath">Rust Kings</div>
          <div data-record-row data-record-type="Escher" data-record-search="ashen choir escher">Ashen Choir</div>
          <p data-record-empty hidden>No gangs match.</p>
        </section>
        <section data-record-table id="campaigns">
          <div id="campaign-controls"></div><span data-record-count></span>
          <span data-record-noun></span>
          <div data-record-row data-record-type="" data-record-search="dust falls">Dust Falls</div>
          <p data-record-empty hidden>No campaigns match.</p>
        </section>
        <p id="invitation">Invitation to Sump City</p>`;
    await act(async () => {
        disposers.push(
            mount(document.getElementById("gang-controls")!, {
                action: "/n26/gangs/",
                query: "",
                noun: "gangs",
                singular: "gang",
                typeOptions: [
                    { value: "Goliath", label: "Goliath" },
                    { value: "Escher", label: "Escher" },
                ],
            }),
        );
        disposers.push(
            mount(document.getElementById("campaign-controls")!, {
                action: "/n26/campaigns/",
                query: "",
                noun: "campaigns",
                singular: "campaign",
                typeOptions: [],
            }),
        );
    });
    return userEvent.setup();
}

function visibleRows(id: string) {
    return [
        ...document.querySelectorAll<HTMLElement>(`#${id} [data-record-row]`),
    ]
        .filter((row) => !row.hidden)
        .map((row) => row.textContent);
}

describe("Independent listing filters", () => {
    it("filters and resets gangs without hiding campaigns or invitations", async () => {
        const user = await listings();
        await user.click(screen.getByRole("button", { name: "Type" }));
        await user.click(screen.getByRole("checkbox", { name: "Escher" }));
        await user.click(screen.getByRole("button", { name: "OK" }));
        expect(visibleRows("gangs")).toEqual(["Rust Kings"]);
        expect(visibleRows("campaigns")).toEqual(["Dust Falls"]);
        expect(
            document.querySelector("#gangs [data-record-count]")?.textContent,
        ).toBe("1");
        expect(
            document.querySelector("#campaigns [data-record-count]")
                ?.textContent,
        ).toBe("1");
        expect(screen.getByText("Invitation to Sump City").hidden).toBe(false);
        await user.click(screen.getByRole("button", { name: /Type/ }));
        await user.click(screen.getByRole("button", { name: "None" }));
        await user.click(screen.getByRole("button", { name: "OK" }));
        expect(visibleRows("gangs")).toEqual([]);
        expect(screen.getByText("No gangs match.").hidden).toBe(false);
        expect(visibleRows("campaigns")).toEqual(["Dust Falls"]);
        await user.click(screen.getByRole("button", { name: /Type/ }));
        await user.click(screen.getByRole("button", { name: "All" }));
        await user.click(screen.getByRole("button", { name: "OK" }));
        expect(visibleRows("gangs")).toEqual(["Rust Kings", "Ashen Choir"]);
        expect(visibleRows("campaigns")).toEqual(["Dust Falls"]);
    });

    it("keeps search and clearing local to each listing", async () => {
        const user = await listings();
        await user.type(
            screen.getByRole("searchbox", { name: "Search gangs" }),
            "ashen",
        );
        expect(visibleRows("gangs")).toEqual(["Ashen Choir"]);
        expect(visibleRows("campaigns")).toEqual(["Dust Falls"]);
        await user.type(
            screen.getByRole("searchbox", { name: "Search campaigns" }),
            "missing",
        );
        expect(visibleRows("campaigns")).toEqual([]);
        expect(visibleRows("gangs")).toEqual(["Ashen Choir"]);
        await user.click(
            within(document.getElementById("campaign-controls")!).getByRole(
                "button",
                { name: "Clear search" },
            ),
        );
        expect(visibleRows("campaigns")).toEqual(["Dust Falls"]);
        expect(visibleRows("gangs")).toEqual(["Ashen Choir"]);
    });

    it("submits the live query to the existing search URL with Enter", async () => {
        const user = await listings();
        const field = screen.getByRole("searchbox", { name: "Search gangs" });
        const form = field.closest("form")!;
        const submit = vi
            .spyOn(form, "requestSubmit")
            .mockImplementation(() => {});
        await user.type(field, "rust{Enter}");
        expect(submit).toHaveBeenCalledOnce();
        expect(form.getAttribute("action")).toBe("/n26/gangs/");
        expect(form.getAttribute("method")).toBe("get");
        expect(
            form.querySelector<HTMLInputElement>('input[name="q"]')?.value,
        ).toBe("rust");
    });
});
