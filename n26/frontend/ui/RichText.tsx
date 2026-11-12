import { createElement, type CSSProperties, type ReactNode } from "react";

/** Only server-sanitised element data crosses this boundary. */
export type RichNode =
    | string
    | {
          tag: string;
          attrs: Record<string, string | CSSProperties>;
          children: RichNode[];
      };

function elements(nodes: RichNode[]): ReactNode[] {
    return nodes.map((node, key) =>
        typeof node === "string"
            ? node
            : createElement(
                  node.tag,
                  { ...node.attrs, key },
                  ...elements(node.children),
              ),
    );
}

export function RichText({
    nodes,
    className = "",
}: {
    nodes: RichNode[];
    className?: string;
}) {
    return (
        <div className={`rich-text break-words ${className}`}>
            {elements(nodes)}
        </div>
    );
}
