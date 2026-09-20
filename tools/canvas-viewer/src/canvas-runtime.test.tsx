import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Callout, Grid, H1, Stack, Table, Text } from "./canvas-runtime";

describe("Canvas runtime", () => {
    it("renders the core layout and table primitives used by repository Canvases", () => {
        const html = renderToStaticMarkup(
            <Stack gap={16}>
                <H1>Audit</H1>
                <Grid columns={2}>
                    <Text>Summary</Text>
                    <Callout tone="warning">Check this.</Callout>
                </Grid>
                <Table
                    headers={["Name", "Status"]}
                    rows={[["Counter", "Open"]]}
                />
            </Stack>,
        );

        expect(html).toContain("Audit");
        expect(html).toContain("Check this.");
        expect(html).toContain("Counter");
        expect(html).toContain("cv-table");
    });
});
