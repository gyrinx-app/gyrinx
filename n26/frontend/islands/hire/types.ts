import type { ComponentProps } from "react";
import type { GangFiguresData, UserLink } from "../../ui";

import type { CatalogueData } from "../../ui";
export type {
    CatalogueData,
    HireEntry,
    HireSection,
    HireOption,
    HireGroup,
} from "../../ui";

export type HireValues = {
    list: string;
    section: string;
    profile: string;
    selection: string;
    name: string;
    paid: string;
    rate: string;
    request_key: string;
    profile_name: string;
    choice_names: string;
    quoted: string;
};
export type HireProps = CatalogueData & {
    gangName: string;
    gangHref: string;
    owner: ComponentProps<typeof UserLink>;
    figures: GangFiguresData;
    values: HireValues;
    errors: Record<string, string[]>;
    confirmation: boolean;
    notice: string;
    messages: Array<{
        text: string;
        tone: "success" | "error" | "warning" | "info";
    }>;
    csrfToken: string;
    action: string;
    commandHref: string;
    recoveryKey: string;
    back: string;
    signInHref: string;
};
