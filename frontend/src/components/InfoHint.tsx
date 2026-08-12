// Small info affordance: a circled "i" that reveals a short tooltip on hover/focus.
// Reusable across screens to explain a field or section without cluttering the layout.
import { useId } from "react";
import "./info-hint.css";

interface InfoHintProps {
  /** The tooltip text. Keep it one short sentence. */
  label: string;
  /** Hướng mở bubble: "left" (mặc định, neo trái) hoặc "right" (neo phải, mở sang trái — dùng khi
   *  icon nằm sát mép phải drawer/dialog để bubble không bị cắt). */
  align?: "left" | "right";
}

export function InfoHint({ label, align = "left" }: InfoHintProps) {
  const id = useId();
  return (
    <span className="hint-tip">
      <button
        type="button"
        className="hint-tip__btn"
        aria-describedby={id}
        aria-label="Giải thích"
      >
        i
      </button>
      <span
        role="tooltip"
        id={id}
        className={`hint-tip__bubble${align === "right" ? " hint-tip__bubble--right" : ""}`}
      >
        {label}
      </span>
    </span>
  );
}
