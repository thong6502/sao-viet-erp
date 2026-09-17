// Ô nhập dùng chung của màn Hồ sơ nhân sự (tách từ pages/NhanSuPage.tsx).
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "../../../../components/Button";
import { UploadCloud } from "lucide-react";
import { DOC_KIND_LABEL } from "../shared/constants";

export function FilePicker({
  onAdd,
  disabled = false,
  compact = false,
  defaultKind = "hop_dong",
}: {
  onAdd: (file: File, kind: string) => void;
  disabled?: boolean;
  compact?: boolean;
  defaultKind?: string;
}) {
  const [kind, setKind] = useState(defaultKind || "hop_dong");
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (defaultKind && defaultKind !== "all") {
      setKind(defaultKind);
    }
  }, [defaultKind]);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!disabled && !isDragging) setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (disabled) return;
    const f = e.dataTransfer.files?.[0];
    if (f) onAdd(f, kind);
  };

  if (compact) {
    return (
      <div
        className={`ns-upload-bar ${isDragging ? "ns-upload-bar--dragging" : ""}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <input
          ref={inputRef}
          type="file"
          style={{ display: "none" }}
          disabled={disabled}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onAdd(f, kind);
            e.target.value = "";
          }}
        />
        <div className="ns-upload-bar__left">
          <Button
            variant="accent"
            className="btn--sm"
            disabled={disabled}
            onClick={() => inputRef.current?.click()}
          >
            <UploadCloud size={15} style={{ marginRight: 4 }} />
            Tải tệp đính kèm
          </Button>
          <select
            className="ns-dropzone__select"
            value={kind}
            onChange={(e) => setKind(e.target.value)}
            disabled={disabled}
          >
            {Object.entries(DOC_KIND_LABEL).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
          <span className="ns-upload-bar__drop-text">
            hoặc kéo & thả tệp trực tiếp vào đây
          </span>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`ns-dropzone--empty ${isDragging ? "ns-dropzone--dragging" : ""}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <input
        ref={inputRef}
        type="file"
        style={{ display: "none" }}
        disabled={disabled}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onAdd(f, kind);
          e.target.value = "";
        }}
      />
      <div
        className="ns-dropzone__body"
        onClick={() => !disabled && inputRef.current?.click()}
      >
        <div className="ns-dropzone__icon-wrap">
          <UploadCloud size={20} />
        </div>
        <p className="ns-dropzone__prompt">
          Kéo & thả tệp vào đây hoặc{" "}
          <button type="button" className="ns-dropzone__btn" disabled={disabled}>
            chọn tệp từ máy tính
          </button>
        </p>
        <p className="ns-dropzone__hint">
          Hợp đồng, CCCD, bằng cấp (PDF, Word, Ảnh)... tải lên để lưu hồ sơ
        </p>
        <div
          style={{ marginTop: 6 }}
          onClick={(e) => e.stopPropagation()}
        >
          <select
            className="ns-dropzone__select"
            value={kind}
            onChange={(e) => setKind(e.target.value)}
            disabled={disabled}
          >
            {Object.entries(DOC_KIND_LABEL).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}

export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  const required = label.trimEnd().endsWith("*");
  const text = required ? label.trimEnd().slice(0, -1).trimEnd() : label;
  return (
    <label className="ns-field">
      <span className="ns-field__label">
        {text}
        {required && (
          <span className="ns-field__required" aria-hidden="true">
            {" "}
            *
          </span>
        )}
      </span>
      {children}
      {hint && <span className="ns-field__hint">{hint}</span>}
    </label>
  );
}
