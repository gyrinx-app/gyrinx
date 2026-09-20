import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
    BarChart,
    Button,
    Card,
    CardBody,
    CardHeader,
    Callout,
    Grid,
    H1,
    LineChart,
    PieChart,
    Stack,
    Table,
    Text,
    Toggle,
    canvasPaletteDark,
    canvasPaletteLight,
    canvasTokens,
    canvasTokensLight,
    computeDAGLayout,
} from "./canvas-runtime";

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

    it("matches the documented theme token and palette shapes", () => {
        for (const palette of [canvasPaletteDark, canvasPaletteLight]) {
            expect(palette.foreground).toBeTruthy();
            expect(palette.editor).toBeTruthy();
            expect(palette.strokeFocused).toBeTruthy();
            expect(palette.diffStripAdded).toBeTruthy();
        }
        for (const tokens of [canvasTokens, canvasTokensLight]) {
            expect(tokens.stroke.focused).toBeTruthy();
            expect(tokens.accent.controlHover).toBeTruthy();
            expect(tokens.diff.insertedLine).toBeTruthy();
            expect(tokens.diff.stripRemoved).toBeTruthy();
            expect(() => JSON.stringify(tokens)).not.toThrow();
        }
    });

    it("lays out documented DAG options and marks cycle back-edges", () => {
        const layout = computeDAGLayout({
            nodes: [{ id: "a" }, { id: "b" }, { id: "c" }],
            edges: [
                { from: "a", to: "b" },
                { from: "b", to: "c" },
                { from: "c", to: "a" },
            ],
            direction: "horizontal",
            nodeWidth: 100,
            nodeHeight: 30,
        });

        expect(layout.direction).toBe("horizontal");
        expect(layout.nodes.map((node) => node.rank)).toEqual([0, 1, 2]);
        expect(layout.edges.filter((edge) => edge.isBackEdge)).toEqual([
            expect.objectContaining({ from: "c", to: "a" }),
        ]);
        expect(layout.ranks).toHaveLength(3);
        expect(layout.edges[0]?.sourceX).toBeGreaterThan(
            layout.nodes[0]?.x ?? 0,
        );
    });

    it("renders stacked chart data, reference lines, and filled series", () => {
        const html = renderToStaticMarkup(
            <Stack>
                <BarChart
                    categories={["Mon", "Tue"]}
                    series={[
                        { name: "Used", data: [30, 60] },
                        { name: "Free", data: [70, 40] },
                    ]}
                    normalized
                    referenceLines={[{ value: 50, label: "Half" }]}
                />
                <LineChart
                    categories={["Mon", "Tue"]}
                    series={[{ name: "Latency", data: [90, 110] }]}
                    fill
                    beginAtZero={false}
                    yMin={80}
                    yMax={120}
                    referenceLines={[{ value: 100, label: "Budget" }]}
                />
            </Stack>,
        );

        expect(html).toContain('data-chart-mode="normalized"');
        expect(html).toContain('data-reference-value="50"');
        expect(html).toContain('data-reference-value="100"');
        expect(html).toContain("<polygon");
    });

    it("keeps grouped bars, sub-unit ranges, and zero pies numerically honest", () => {
        const html = renderToStaticMarkup(
            <Stack>
                <BarChart
                    categories={["p95"]}
                    series={[{ name: "Latency", data: [90] }]}
                    beginAtZero={false}
                    yMin={80}
                    yMax={120}
                />
                <LineChart
                    categories={["Low", "High"]}
                    series={[{ name: "Ratio", data: [0.1, 0.2] }]}
                    beginAtZero={false}
                    yMin={0.1}
                    yMax={0.2}
                />
                <PieChart
                    data={[
                        { label: "One", value: 0 },
                        { label: "Two", value: -1 },
                    ]}
                    donut
                />
                <Toggle label="Notifications" />
            </Stack>,
        );

        expect(html).toContain('data-start="80"');
        expect(html).toContain('data-end="90"');
        expect(html).toContain('cy="230"');
        expect(html).toContain('cy="30"');
        expect(html).toContain('class="cv-pie-total">0</text>');
        expect(html).toContain('aria-label="Notifications"');
    });

    it("keeps pie strokes in bounds and card actions outside disclosure buttons", () => {
        const pie = renderToStaticMarkup(
            <PieChart data={[{ label: "Whole", value: 1 }]} />,
        );
        const card = renderToStaticMarkup(
            <Card collapsible>
                <CardHeader trailing={<Button>Action</Button>}>
                    Details
                </CardHeader>
                <CardBody>Body</CardBody>
            </Card>,
        );

        expect(pie).toContain('r="25"');
        expect(pie).toContain('stroke-width="50"');
        expect(card).toContain("cv-card-collapsible-header");
        expect(card.indexOf(">Action</button>")).toBeGreaterThan(
            card.indexOf("</button>"),
        );
    });
});
