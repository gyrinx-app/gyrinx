import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { CampaignGangs } from "../islands/campaign-gangs/CampaignGangs";
import { CampaignViewLink } from "../islands/campaign-view-link/entry";

test.each([false, true])(
    "an external asset dialog holds the table view until completion (failure=%s)",
    async (failure) => {
        window.history.replaceState(
            null,
            "",
            "/campaign/?sort=name&group=label%3Adivision",
        );
        const user = userEvent.setup();
        let finish: () => void = () => {};
        const open = vi.fn(
            () =>
                new Promise<void>((resolve, reject) => {
                    finish = () =>
                        failure ? reject(new Error("Offline")) : resolve();
                }),
        );
        render(
            <>
                <CampaignGangs
                    href="/campaign/"
                    sort="name"
                    group="label:division"
                    defaultGroup="label:division"
                    counters={[]}
                    labels={[
                        {
                            token: "label:division",
                            label: "Division",
                            colours: {},
                        },
                    ]}
                    gangs={[
                        {
                            id: "gang",
                            name: "Rust Kings",
                            type: "Goliath",
                            artwork: "",
                            owner: null,
                            colour: "",
                            href: "/gang/",
                            rating: 100,
                            credits: 0,
                            wealth: 100,
                            creditsHref: "",
                            removeHref: "",
                            overBudget: false,
                            sortValues: {
                                name: "rust kings",
                                rating: 100,
                                "label:division": "upper",
                            },
                            labels: ["Upper"],
                            assets: [],
                            rolls: [],
                            counters: [],
                        },
                    ]}
                    badges={{}}
                    artwork={{}}
                    onOpenDialog={vi.fn()}
                />
                <CampaignViewLink
                    href="/assets/transfer/"
                    label="Transfer"
                    variant="ghost"
                    className=""
                    dialog
                    onOpenDialog={open}
                />
            </>,
        );
        await user.click(screen.getByRole("link", { name: "Transfer" }));
        expect(
            (screen.getByLabelText("Sort by") as HTMLSelectElement).disabled,
        ).toBe(true);
        expect(
            (screen.getByLabelText("View groups by") as HTMLSelectElement)
                .disabled,
        ).toBe(true);
        fireEvent.click(screen.getByRole("link", { name: "Rating" }));
        fireEvent.change(screen.getByLabelText("View groups by"), {
            target: { value: "" },
        });
        expect(window.location.search).toBe(
            "?sort=name&group=label%3Adivision",
        );
        await act(async () => finish());
        expect(
            (screen.getByLabelText("Sort by") as HTMLSelectElement).disabled,
        ).toBe(false);
        await user.selectOptions(screen.getByLabelText("View groups by"), "");
        await user.click(screen.getByRole("link", { name: "Rating" }));
        expect(window.location.search).toBe("?sort=rating&group=");
        expect(
            screen.getByRole("link", { name: "Transfer" }).getAttribute("href"),
        ).toBe("/assets/transfer/?sort=rating&group=");
    },
);
