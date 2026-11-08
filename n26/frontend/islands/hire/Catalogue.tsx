import { useCallback, useState } from "react";
import { HireCatalogue, type CatalogueData } from "../../ui";
import { Preview, type PreviewCache } from "./Preview";

export function Catalogue(props: CatalogueData) {
    const [cache] = useState<PreviewCache>(() => new Map());
    const preview = useCallback(
        (href: string, selection: string[]) => (
            <Preview href={href} selection={selection} cache={cache} />
        ),
        [cache],
    );
    return <HireCatalogue {...props} renderPreview={preview} />;
}
