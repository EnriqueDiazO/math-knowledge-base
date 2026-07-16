import { useCallback, useEffect, useRef, useState } from "react";
import type { RefObject } from "react";

import { isPersistableSelection } from "../annotations/ui";
import type { TextSelectionEvent } from "../selection/types";
import type { VisualAnnotationKind } from "../types/api";

interface SelectionActionToolbarProps {
  selection: TextSelectionEvent | null;
  enabled: boolean;
  stageRef: RefObject<HTMLElement | null>;
  viewerRef: RefObject<HTMLElement | null>;
  onChoose(kind: VisualAnnotationKind): void;
  onCancel(): void;
}

interface ToolbarPosition {
  left: number;
  top: number;
}

export function SelectionActionToolbar({
  selection,
  enabled,
  stageRef,
  viewerRef,
  onChoose,
  onCancel,
}: SelectionActionToolbarProps) {
  const toolbarRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState<ToolbarPosition | null>(null);

  const updatePosition = useCallback(() => {
    if (!enabled || !isPersistableSelection(selection)) {
      setPosition(null);
      return;
    }
    const stage = stageRef.current;
    const viewer = viewerRef.current;
    const page = viewer?.querySelector<HTMLElement>(
      `.page[data-page-number="${selection.pdf_page}"]`,
    );
    if (stage === null || viewer === null || page == null) {
      setPosition(null);
      return;
    }
    const first = selection.rects_normalized[0];
    const stageBounds = stage.getBoundingClientRect();
    const pageBounds = page.getBoundingClientRect();
    const toolbarBounds = toolbarRef.current?.getBoundingClientRect();
    const width = toolbarBounds?.width ?? 330;
    const height = toolbarBounds?.height ?? 44;
    const desiredLeft = pageBounds.left - stageBounds.left +
      (first.x + first.width / 2) * pageBounds.width - width / 2;
    const desiredTop = pageBounds.top - stageBounds.top + first.y * pageBounds.height - height - 8;
    const maxLeft = Math.max(8, stageBounds.width - width - 8);
    const maxTop = Math.max(8, stageBounds.height - height - 8);
    setPosition({
      left: Math.min(maxLeft, Math.max(8, desiredLeft)),
      top: Math.min(maxTop, Math.max(8, desiredTop)),
    });
  }, [enabled, selection, stageRef, viewerRef]);

  useEffect(() => {
    updatePosition();
    const stage = stageRef.current;
    const viewerContainer = viewerRef.current?.closest("#viewerContainer");
    const resizeObserver = typeof ResizeObserver === "undefined"
      ? null
      : new ResizeObserver(updatePosition);
    if (stage !== null) resizeObserver?.observe(stage);
    const selectionPage = isPersistableSelection(selection)
      ? viewerRef.current?.querySelector<HTMLElement>(
          `.page[data-page-number="${selection.pdf_page}"]`,
        ) ?? null
      : null;
    if (selectionPage !== null) resizeObserver?.observe(selectionPage);
    if (toolbarRef.current !== null) resizeObserver?.observe(toolbarRef.current);
    viewerContainer?.addEventListener("scroll", updatePosition, { passive: true });
    window.addEventListener("resize", updatePosition);
    return () => {
      resizeObserver?.disconnect();
      viewerContainer?.removeEventListener("scroll", updatePosition);
      window.removeEventListener("resize", updatePosition);
    };
  }, [selection, stageRef, updatePosition, viewerRef]);

  if (!enabled || !isPersistableSelection(selection)) return null;

  return (
    <div
      ref={toolbarRef}
      className="selection-action-toolbar"
      role="toolbar"
      aria-label="Guardar selección como marca visual"
      style={position === null ? { visibility: "hidden" } : position}
    >
      <button type="button" onClick={() => onChoose("highlight")}>Highlight</button>
      <button type="button" onClick={() => onChoose("underline")}>Underline</button>
      <button type="button" onClick={onCancel}>Cancelar</button>
    </div>
  );
}
