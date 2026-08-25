// Ô nhập dùng chung của màn Hồ sơ nhân sự (tách từ pages/NhanSuPage.tsx).
import { useEffect, useRef, useState, type ReactNode } from "react";
import type { JobGrade } from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { UploadCloud } from "lucide-react";
import { DOC_KIND_LABEL } from "../shared/constants";
import { errMsg } from "../shared/helpers";

/** Ô chọn bậc + thêm bậc TẠI CHỖ.
 *  KHÔNG bọc bằng `Field`: `Field` render `<label>`, mà `<label>` nuốt click của nút bên trong
 *  (bấm "+ Thêm bậc" sẽ nhảy focus vào select thay vì mở ô nhập).
 *  ⚠ Nơi gọi TUYỆT ĐỐI không preselect `emp.job_grade_id`: danh sách chỉ có bậc đang BẬT, người
 *  đang mang bậc đã tắt sẽ bị select nhảy về option đầu rồi ÂM THẦM đổi bậc lúc Lưu. */
export function JobGradeField({
  grades,
  err,
  reload,
  addGrade,
  value,
  onChange,
  label,
  hint,
  allowKeep,
  canCreate,
}: {
  grades: JobGrade[] | null;
  err: string | null;
  reload: () => void;
  addGrade: (name: string) => Promise<JobGrade>;
  value: number | null;
  onChange: (id: number | null) => void;
  label: string;
  hint?: string;
  allowKeep?: boolean;
  canCreate: boolean;
}) {
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [addErr, setAddErr] = useState<string | null>(null);
  const [added, setAdded] = useState<string | null>(null);
  const loading = grades === null && err == null;

  function cancelAdd() {
    setAdding(false);
    setName("");
    setAddErr(null);
  }

  async function saveGrade() {
    const n = name.trim();
    if (!n) return;
    setBusy(true);
    setAddErr(null);
    try {
      const g = await addGrade(n);
      onChange(g.id);
      setAdded(g.name);
      setAdding(false);
      setName("");
    } catch (e) {
      // Trùng tên là lỗi hay gặp nhất → GIỮ NGUYÊN ô nhập để sửa vài ký tự, đừng bắt gõ lại.
      setAddErr(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ns-field">
      <span className="ns-field__label">{label}</span>
      <div className="ns-inline-add">
        <select
          value={value ?? ""}
          disabled={loading || err != null}
          onChange={(e) => {
            setAdded(null);
            onChange(e.target.value === "" ? null : Number(e.target.value));
          }}
        >
          <option value="">
            {loading
              ? "Đang tải danh mục bậc…"
              : err != null
                ? "Không tải được danh mục bậc"
                : allowKeep
                  ? "— giữ nguyên —"
                  : "— chưa khai —"}
          </option>
          {(grades ?? []).map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </select>
        {/* {canCreate && !adding && (
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={() => {
              setAdding(true);
              setAddErr(null);
              setAdded(null);
            }}
          >
            + Thêm bậc
          </button>
        )} */}
      </div>

      {adding && (
        <div className="ns-inline-add">
          <input
            autoFocus
            value={name}
            placeholder="Tên bậc, vd: Thợ vững"
            onChange={(e) => setName(e.target.value)}
            // Ô này nằm TRONG modal: không chặn nổi bọt thì Esc đóng luôn cả wizard, mất sạch
            // những gì đang gõ dở ở các bước trước.
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                e.stopPropagation();
                void saveGrade();
              }
              if (e.key === "Escape") {
                e.stopPropagation();
                cancelAdd();
              }
            }}
          />
          <button
            type="button"
            className="btn btn--primary btn--sm"
            disabled={busy || !name.trim()}
            onClick={() => void saveGrade()}
          >
            {busy ? "Đang lưu…" : "Lưu bậc"}
          </button>
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            disabled={busy}
            onClick={cancelAdd}
          >
            Hủy
          </button>
        </div>
      )}

      {addErr && (
        <span className="ns-field__hint ns-field__hint--err">{addErr}</span>
      )}
      {err != null && (
        <span className="ns-field__hint ns-field__hint--err">
          Không tải được danh mục bậc ({err}).{" "}
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={reload}
          >
            Thử lại
          </button>
        </span>
      )}
      {added && (
        <span className="ns-field__hint">Đã thêm “{added}” vào danh mục.</span>
      )}
      {err == null && !loading && grades?.length === 0 && !adding && (
        <span className="ns-field__hint">
          {canCreate
            ? "Danh mục bậc đang trống — bấm “+ Thêm bậc” để khai."
            : "Danh mục bậc đang trống — nhờ HCNS khai bậc trước."}
        </span>
      )}
      {hint && <span className="ns-field__hint">{hint}</span>}
    </div>
  );
}

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
