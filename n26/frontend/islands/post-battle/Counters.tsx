import { Button, Input } from "../../ui";
import type { Counter } from "./types";
import { value } from "./types";
import type { Draft } from "./useReportDraft";
function signed(value: number) {
    return value > 0 ? `+${value}` : String(value);
}
export function Counters({
    rows,
    effects,
    steps,
    form,
}: {
    rows: Counter[];
    effects: boolean;
    steps: boolean;
    form: Draft;
}) {
    return (
        <div className="overflow-x-auto">
            <table className="text-sm">
                <thead>
                    <tr className="border-b border-box-border text-left text-muted">
                        <th scope="col" className="py-2 pr-4 font-medium">
                            Counter
                        </th>
                        <th scope="col" className="py-2 pr-4 font-medium">
                            Change
                        </th>
                        <th
                            scope="col"
                            className="hidden py-2 pr-4 text-right font-medium sm:table-cell"
                        >
                            Before
                        </th>
                        {effects && (
                            <th
                                scope="col"
                                className="py-2 pr-4 text-right font-medium"
                            >
                                From results
                            </th>
                        )}
                        <th scope="col" className="py-2 text-right font-medium">
                            After
                        </th>
                    </tr>
                </thead>
                <tbody>
                    {rows.map((row, index) => {
                        const entered = value(form, row.prefix);
                        const number = Number(entered || 0);
                        const after = Number.isInteger(number)
                            ? Math.max(0, row.base + number)
                            : "—";
                        const step = (amount: number) => {
                            if (Number.isInteger(number))
                                form.change(
                                    row.prefix,
                                    String(
                                        Math.max(
                                            -row.limit,
                                            Math.min(
                                                row.limit,
                                                number + amount,
                                            ),
                                        ),
                                    ),
                                );
                        };
                        return (
                            <tr
                                key={row.id || `new-${index}`}
                                className="border-b border-box-border"
                            >
                                <th
                                    scope="row"
                                    className="py-2 pr-4 text-left font-medium"
                                >
                                    {row.editable ? (
                                        <label htmlFor={row.prefix}>
                                            {row.name}
                                        </label>
                                    ) : (
                                        row.name
                                    )}
                                    <span className="block text-xs font-normal text-muted tabular-nums sm:hidden">
                                        Before {row.before}
                                    </span>
                                </th>
                                <td className="py-2 pr-4">
                                    {row.editable ? (
                                        <div className="flex items-center gap-1">
                                            {steps && (
                                                <Button
                                                    size="sm"
                                                    aria-label={row.minusLabel}
                                                    disabled={
                                                        !Number.isInteger(
                                                            number,
                                                        ) ||
                                                        Number(after) <= 0 ||
                                                        number <= -row.limit
                                                    }
                                                    onClick={() => step(-1)}
                                                >
                                                    −1
                                                </Button>
                                            )}
                                            <div className="w-16 sm:w-20">
                                                <Input
                                                    id={row.prefix}
                                                    name={row.prefix}
                                                    type="number"
                                                    step="1"
                                                    value={entered}
                                                    placeholder="0"
                                                    aria-describedby={`${row.prefix}-after`}
                                                    onChange={(event) =>
                                                        form.change(
                                                            row.prefix,
                                                            event.currentTarget
                                                                .value,
                                                        )
                                                    }
                                                />
                                            </div>
                                            {steps && (
                                                <Button
                                                    size="sm"
                                                    aria-label={row.plusLabel}
                                                    disabled={
                                                        !Number.isInteger(
                                                            number,
                                                        ) || number >= row.limit
                                                    }
                                                    onClick={() => step(1)}
                                                >
                                                    +1
                                                </Button>
                                            )}
                                        </div>
                                    ) : (
                                        <span className="text-muted">New</span>
                                    )}
                                </td>
                                <td className="hidden py-2 pr-4 text-right tabular-nums sm:table-cell">
                                    {row.before}
                                </td>
                                {effects && (
                                    <td className="py-2 pr-4 text-right tabular-nums">
                                        {signed(row.fromResults)}
                                    </td>
                                )}
                                <td
                                    id={`${row.prefix}-after`}
                                    className="py-2 text-right font-semibold tabular-nums"
                                >
                                    {row.editable ? after : row.after}
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}
