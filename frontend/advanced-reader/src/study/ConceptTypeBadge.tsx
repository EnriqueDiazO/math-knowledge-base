import { conceptKind, conceptType } from "../knowledge-map/concept-types";

export function ConceptTypeBadge({ type }: { type: string }) {
  const definition = conceptType(type);
  return (
    <span className="concept-type-badge" data-concept-type={conceptKind(type)}>
      {definition && <b aria-hidden="true">{definition.symbol}</b>}
      {definition?.label ?? type}
    </span>
  );
}
