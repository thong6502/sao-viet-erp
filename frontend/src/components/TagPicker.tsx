// Gắn nhãn cho MỘT BƯỚC công đoạn (LSX / Bài ghép) — LOGIC y hệt gán thẻ ở module Khách hàng
// (TagModal trong KhachHangPage): kho nhãn dùng chung, thêm/gỡ khác hoa-thường không đẻ đúp, nhãn
// gõ tay tại chỗ tự vào kho, xoá nhãn khỏi kho hỏi kèm SỐ BƯỚC thật.
//
// Khác trình bày: ở đây KHÔNG mở modal toàn màn (bước được sửa trong drawer, modal chồng drawer là
// tệ) — dùng khối inline: hàng chip đang gán + nút "＋ Nhãn" mở bảng chọn ngay dưới. Mỗi cú bấm ăn
// NGAY (thêm/gỡ tức thì), không có nút "Lưu" riêng — hợp thói quen "ít thao tác".
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Check, Plus, Search, Tag, X } from "lucide-react";
import { api, ApiError, type CongDoanTagRow, type KhoNhanBuocRow } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { ConfirmDialog } from "./ConfirmDialog";
import { tagTone } from "../lib/tagTone";
import "./tag-picker.css";

export function TagPicker({
  buocLoai,
  buocId,
  canUpdate,
}: {
  /** "lsx" | "bai_ghep" — bước sống ở hai bảng khác nhau, phân biệt bằng loại. */
  buocLoai: string;
  buocId: number;
  canUpdate: boolean;
}) {
  const { token } = useAuth();
  const [tags, setTags] = useState<CongDoanTagRow[]>([]);
  const [kho, setKho] = useState<KhoNhanBuocRow[]>([]);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [xoaNhan, setXoaNhan] = useState<KhoNhanBuocRow | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const nap = useCallback(() => {
    if (!token) return;
    api.congDoanTag.list(token, buocLoai, buocId).then((r) => setTags(r.items)).catch(() => {});
    api.congDoanTag.kho(token).then((r) => setKho(r.items)).catch(() => setKho([]));
  }, [token, buocLoai, buocId]);
  useEffect(() => nap(), [nap]);

  // Nhãn đang gán (hạ chữ) — để biết pill nào đang bật.
  const onLabels = useMemo(
    () => new Set(tags.map((t) => t.label.toLowerCase())),
    [tags],
  );

  // Mọi nhãn có thể chọn: kho + nhãn đang gán (case-insensitive dedup). `tags` phải góp mặt phòng
  // khi kho chưa nạp kịp — thiếu nó thì chip đang bật biến khỏi lưới.
  const allLabels = useMemo(() => {
    const seen = new Set<string>();
    const out: string[] = [];
    for (const l of [...kho.map((r) => r.label), ...tags.map((t) => t.label)]) {
      const k = l.toLowerCase();
      if (!seen.has(k)) {
        seen.add(k);
        out.push(l);
      }
    }
    return out;
  }, [kho, tags]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? allLabels.filter((l) => l.toLowerCase().includes(q)) : allLabels;
  }, [allLabels, query]);

  const exactExists = useMemo(() => {
    const q = query.trim().toLowerCase();
    return !q || allLabels.some((l) => l.toLowerCase() === q);
  }, [allLabels, query]);

  // Số bước đang mang từng nhãn — để nút xoá-khỏi-kho hỏi bằng số thật.
  const dongKhoTheoNhan = useMemo(() => {
    const m = new Map<string, KhoNhanBuocRow>();
    for (const r of kho) m.set(r.label.toLowerCase(), r);
    return m;
  }, [kho]);

  async function themNhan(label: string) {
    if (!token || busy) return;
    const clean = label.trim().replace(/\s+/g, " ");
    if (!clean) return;
    if (clean.length > 50) {
      setError("Nhãn tối đa 50 ký tự.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.congDoanTag.add(token, buocLoai, buocId, clean);
      setQuery("");
      nap();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Không gắn được nhãn.");
    } finally {
      setBusy(false);
    }
  }

  async function goNhanKhoiBuoc(label: string) {
    if (!token || busy) return;
    const tag = tags.find((t) => t.label.toLowerCase() === label.toLowerCase());
    if (!tag) return;
    setBusy(true);
    setError(null);
    try {
      await api.congDoanTag.remove(token, buocLoai, buocId, tag.id);
      nap();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Không gỡ được nhãn.");
    } finally {
      setBusy(false);
    }
  }

  function toggle(label: string) {
    if (onLabels.has(label.toLowerCase())) goNhanKhoiBuoc(label);
    else themNhan(label);
  }

  return (
    <div className="tagpick">
      {/* Hàng chip đang gán + nút mở bảng chọn */}
      <div className="tagpick__chips">
        {tags.length === 0 && !open && (
          <span className="tagpick__empty">Chưa gắn nhãn</span>
        )}
        {tags.map((t) => (
          <span key={t.id} className={`tagpick__chip tagpick__tone--${tagTone(t.label)}`}>
            {t.label}
            {canUpdate && (
              <button
                type="button"
                className="tagpick__chip-del"
                title={`Gỡ nhãn "${t.label}" khỏi bước`}
                aria-label={`Gỡ nhãn ${t.label}`}
                onClick={() => goNhanKhoiBuoc(t.label)}
                disabled={busy}
              >
                <X size={11} strokeWidth={2.5} />
              </button>
            )}
          </span>
        ))}
        {canUpdate && (
          <button
            type="button"
            className={`tagpick__add${open ? " is-open" : ""}`}
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
          >
            <Tag size={13} strokeWidth={2.2} />
            <span>Nhãn</span>
          </button>
        )}
      </div>

      {/* Bảng chọn inline */}
      {open && canUpdate && (
        <div className="tagpick__panel" ref={panelRef}>
          <div className="tagpick__searchbar">
            <Search size={14} className="tagpick__search-ic" />
            <input
              className="tagpick__search-input"
              placeholder="Tìm nhãn hoặc gõ tên để tạo mới (Enter)…"
              value={query}
              autoFocus
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  themNhan(query);
                } else if (e.key === "Escape") {
                  e.preventDefault();
                  setOpen(false);
                }
              }}
            />
            {query && (
              <button
                type="button"
                className="tagpick__search-clear"
                onClick={() => setQuery("")}
                title="Xoá tìm kiếm"
              >
                <X size={12} />
              </button>
            )}
          </div>

          <div className="tagpick__cloud">
            {filtered.map((label) => {
              const on = onLabels.has(label.toLowerCase());
              const tone = tagTone(label);
              const dongKho = dongKhoTheoNhan.get(label.toLowerCase());
              return (
                <span key={label} className="tagpick__pill-wrap">
                  <button
                    type="button"
                    className={`tagpick__pill tagpick__tone--${tone}${on ? " is-on" : ""}`}
                    aria-pressed={on}
                    onClick={() => toggle(label)}
                    disabled={busy}
                  >
                    {on ? (
                      <Check size={12} strokeWidth={2.6} />
                    ) : (
                      <span className="tagpick__pill-dot" />
                    )}
                    <span>{label}</span>
                  </button>
                  {/* Nút xoá NẰM NGOÀI pill: button lồng button là HTML không hợp lệ. Chỉ nhãn ĐÃ
                      Ở TRONG KHO mới xoá được. */}
                  {dongKho && (
                    <button
                      type="button"
                      className="tagpick__pill-del"
                      title={`Xoá nhãn "${label}" khỏi kho`}
                      aria-label={`Xoá nhãn ${label} khỏi kho`}
                      onClick={() => setXoaNhan(dongKho)}
                      disabled={busy}
                    >
                      <X size={10} strokeWidth={2.6} />
                    </button>
                  )}
                </span>
              );
            })}

            {!exactExists && query.trim() && (
              <button
                type="button"
                className="tagpick__pill tagpick__pill--create"
                onClick={() => themNhan(query)}
                disabled={busy}
              >
                <Plus size={12} strokeWidth={2.6} />
                <span>Tạo mới "<strong>{query.trim()}</strong>"</span>
              </button>
            )}

            {filtered.length === 0 && !query.trim() && (
              <span className="tagpick__cloud-empty">Kho nhãn trống — gõ tên để tạo nhãn đầu tiên.</span>
            )}
          </div>

          {error && <div className="tagpick__error" role="alert">{error}</div>}
        </div>
      )}

      {/* Xoá nhãn khỏi KHO — khác gỡ khỏi bước (gỡ chỉ bỏ nhãn ở riêng bước này). Hỏi kèm SỐ BƯỚC
          thật: con số là thứ duy nhất cho người bấm biết mình sắp làm rơi nhãn khỏi bao nhiêu bước. */}
      <ConfirmDialog
        open={xoaNhan !== null}
        danger
        title={`Xoá nhãn "${xoaNhan?.label ?? ""}" khỏi kho?`}
        message={
          xoaNhan && xoaNhan.so_buoc > 0
            ? `${xoaNhan.so_buoc} bước đang mang nhãn này — xoá thì nhãn rơi khỏi cả ${xoaNhan.so_buoc} bước đó. `
              + "Không khôi phục được."
            : "Chưa bước nào mang nhãn này, xoá là an toàn."
        }
        confirmLabel="Xoá nhãn"
        busy={busy}
        onCancel={() => setXoaNhan(null)}
        onConfirm={async () => {
          if (!token || !xoaNhan) return;
          setBusy(true);
          setError(null);
          try {
            await api.congDoanTag.xoaNhanKho(token, xoaNhan.id);
            setXoaNhan(null);
            nap();
          } catch (e) {
            setError(e instanceof ApiError ? e.message : "Xoá nhãn không thành công.");
          } finally {
            setBusy(false);
          }
        }}
      />
    </div>
  );
}
