// Khối "VỊ TRÍ CẤT TRONG KHO" nằm cuối drawer Khai báo kho (qua `config.renderExtra`).
//
// Khai danh sách kệ/ô của MỘT kho để khi lập lô/phiếu chọn từ dropdown thay vì gõ tay. Danh sách
// KHÔNG ràng buộc cứng lô cũ (`stock_lots.vi_tri` vẫn là chuỗi tự do) — chỉ là gợi ý/chọn.
//
// Dùng lại class `rc-*` của nền danh mục + inline nhẹ → KHÔNG thêm CSS mới (khỏi đụng guard CSS).
import { useCallback, useEffect, useState } from "react";

import { ApiError, api } from "../api/client";
import type { KhoViTriRow } from "../api/client";
import type { Row } from "../api/rebuildCatalog";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { ConfirmDialog } from "../components/ConfirmDialog";

export function KhoViTriPanel({ kho }: { kho: Row | null }) {
  const { token } = useAuth();
  const can = useCan();
  const coThem = can("dm_kho_hang", "create");
  const coXoa = can("dm_kho_hang", "delete");

  const [items, setItems] = useState<KhoViTriRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [ban, setBan] = useState(false);
  const [ma, setMa] = useState("");
  const [xoaTarget, setXoaTarget] = useState<KhoViTriRow | null>(null);

  const khoId = kho ? Number(kho.id) : null;

  const nap = useCallback(() => {
    if (!token || khoId == null) return;
    api.kho.viTri.list(token, khoId)
      .then((r) => setItems(r.items))
      .catch(() => setItems([]));
  }, [token, khoId]);

  useEffect(() => { nap(); }, [nap]);

  if (khoId == null) {
    return (
      <section className="kvt-panel">
        <div className="kvt-card">
          <div className="kvt-header">
            <div className="kvt-header__title">
              <span className="kvt-header__icon">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                  <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
                  <line x1="12" y1="22.08" x2="12" y2="12"/>
                </svg>
              </span>
              <span>Vị trí cất trong kho</span>
            </div>
          </div>
          <div className="kvt-empty-state">
            <div className="kvt-empty-state__icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="8" x2="12" y2="12"/>
                <line x1="12" y1="16" x2="12.01" y2="16"/>
              </svg>
            </div>
            <p className="kvt-empty-state__text">Lưu kho (bấm “Tạo mới”) rồi mới khai được danh sách vị trí.</p>
          </div>
        </div>
      </section>
    );
  }

  async function themViTri(tenCustom?: string) {
    const t = (tenCustom ?? ma).trim();
    if (!token || khoId == null || !t) return;
    setBan(true); setErr(null);
    try {
      await api.kho.viTri.create(token, khoId, { ma: t });
      setMa("");
      nap();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Không thêm được vị trí.");
    } finally {
      setBan(false);
    }
  }

  async function xoaViTri(vt: KhoViTriRow) {
    if (!token) return;
    setBan(true); setErr(null);
    try {
      await api.kho.viTri.remove(token, vt.id);
      setXoaTarget(null);
      nap();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Không xóa được vị trí.");
    } finally {
      setBan(false);
    }
  }

  // Danh sách các gợi ý điền nhanh vị trí kho phổ biến
  const existingNames = new Set(items.map((i) => i.ma.trim().toLowerCase()));
  const presetSuggestions = ["Ô 1", "Ô 2", "Ô 3", "Kệ A1", "Kệ A2", "Kệ B1"]
    .filter((p) => !existingNames.has(p.toLowerCase()))
    .slice(0, 4);

  return (
    <section className="kvt-panel">
      {err && <div className="banner banner--error">{err}</div>}

      <div className="kvt-card">
        {/* Header với Subtitle & Stats Badge */}
        <div className="kvt-header">
          <div className="kvt-header__title-group">
            <div className="kvt-header__title">
              <span className="kvt-header__icon">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                  <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
                  <line x1="12" y1="22.08" x2="12" y2="12"/>
                </svg>
              </span>
              <span>Vị trí cất trong kho</span>
            </div>
            <span className="kvt-header__subtitle">Gợi ý vị trí chọn nhanh khi lập lô hoặc phiếu xuất nhập kho</span>
          </div>
          <span className="kvt-count-badge">
            <span className="kvt-count-badge__dot" />
            {items.length} vị trí đã tạo
          </span>
        </div>

        {/* Chips danh sách vị trí đã khai */}
        <div className="kvt-chips-section">
          {items.length === 0 ? (
            <div className="kvt-empty-state">
              <div className="kvt-empty-state__icon">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
                  <circle cx="12" cy="10" r="3"/>
                </svg>
              </div>
              <p className="kvt-empty-state__text">Kho này chưa khai vị trí nào. Nhập tên vị trí ở khung bên dưới để tạo mới.</p>
            </div>
          ) : (
            <div className="kvt-chips-grid">
              {items.map((vt) => (
                <span key={vt.id} className="kvt-chip" title={vt.ghi_chu ?? undefined}>
                  <span className="kvt-chip__pin">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
                      <circle cx="12" cy="10" r="3"/>
                    </svg>
                  </span>
                  {vt.ma}
                  {coXoa && (
                    <button
                      type="button"
                      className="kvt-chip__del-btn"
                      aria-label={`Xóa vị trí ${vt.ma}`}
                      disabled={ban}
                      onClick={() => setXoaTarget(vt)}
                    >
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round">
                        <line x1="18" y1="6" x2="6" y2="18" />
                        <line x1="6" y1="6" x2="18" y2="18" />
                      </svg>
                    </button>
                  )}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Section thêm vị trí mới liền khối */}
        {coThem && (
          <>
            <div className="kvt-divider" />
            <div className="kvt-add-section">
              <span className="kvt-add-section__header">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
                  <line x1="12" y1="5" x2="12" y2="19"/>
                  <line x1="5" y1="12" x2="19" y2="12"/>
                </svg>
                Thêm vị trí mới
              </span>

              <div className="kvt-input-bar">
                <span className="kvt-input-bar__prefix">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
                    <circle cx="12" cy="10" r="3"/>
                  </svg>
                </span>
                <input
                  className="kvt-input-bar__field"
                  value={ma}
                  disabled={ban}
                  placeholder="Nhập tên vị trí (Vd: Ô 1, Kệ A1...)"
                  onChange={(e) => setMa(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); themViTri(); } }}
                />
                <button
                  type="button"
                  className="kvt-input-bar__btn"
                  disabled={ban || !ma.trim()}
                  onClick={() => themViTri()}
                >
                  + Thêm vị trí
                </button>
              </div>

              {presetSuggestions.length > 0 && (
                <div className="kvt-presets">
                  <span>Gợi ý nhanh:</span>
                  {presetSuggestions.map((ps) => (
                    <button
                      key={ps}
                      type="button"
                      className="kvt-preset-btn"
                      disabled={ban}
                      onClick={() => themViTri(ps)}
                    >
                      + {ps}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>

      <ConfirmDialog
        open={xoaTarget !== null}
        title="Xóa vị trí?"
        message={xoaTarget ? `Bỏ vị trí “${xoaTarget.ma}” khỏi danh sách của kho. Lô đã ghi vị trí này (dạng chữ) không đổi.` : ""}
        confirmLabel="Xóa"
        cancelLabel="Giữ lại"
        danger
        busy={ban}
        onConfirm={() => xoaTarget && xoaViTri(xoaTarget)}
        onCancel={() => setXoaTarget(null)}
      />
    </section>
  );
}
