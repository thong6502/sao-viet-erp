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
import { Button } from "../components/Button";
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
  const [ghiChu, setGhiChu] = useState("");
  const [xoaTarget, setXoaTarget] = useState<KhoViTriRow | null>(null);

  const khoId = kho ? Number(kho.id) : null;

  const nap = useCallback(() => {
    if (!token || khoId == null) return;
    api.kho.viTri.list(token, khoId)
      .then((r) => setItems(r.items))
      .catch(() => setItems([]));
  }, [token, khoId]);

  useEffect(() => { nap(); }, [nap]);

  // Đang TẠO kho mới (chưa có id) → chưa gắn vị trí được. `moLaiSauKhiTao` giữ drawer mở sau khi
  // lưu nên người dùng khai tên → Tạo mới → panel này có id ngay, không phải đi tìm lại dòng.
  if (khoId == null) {
    return (
      <section style={{ padding: "4px 2px" }}>
        <div style={{ fontWeight: "var(--fw-bold)", marginBottom: 6 }}>Vị trí cất trong kho</div>
        <p className="rc-field__hint">Lưu kho (bấm “Tạo mới”) rồi mới khai được danh sách vị trí.</p>
      </section>
    );
  }

  async function themViTri() {
    const t = ma.trim();
    if (!token || khoId == null || !t) return;
    setBan(true); setErr(null);
    try {
      await api.kho.viTri.create(token, khoId, { ma: t, ghi_chu: ghiChu.trim() || null });
      setMa(""); setGhiChu("");
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

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: 12, padding: "4px 2px" }}>
      <div>
        <div style={{ fontWeight: "var(--fw-bold)" }}>Vị trí cất trong kho</div>
        <p className="rc-field__hint" style={{ marginTop: 2 }}>
          Khai kệ/ô của kho này (vd “Kệ A - Ô 1”). Khi lập lô/phiếu, ô “Vị trí” sẽ gợi ý từ danh sách này.
        </p>
      </div>

      {err && <div className="banner banner--error">{err}</div>}

      {/* Danh sách vị trí đã khai */}
      {items.length === 0 ? (
        <p className="rc-field__hint" style={{ margin: 0 }}>Chưa khai vị trí nào cho kho này.</p>
      ) : (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {items.map((vt) => (
            <span
              key={vt.id}
              title={vt.ghi_chu ?? undefined}
              style={{
                display: "inline-flex", alignItems: "center", gap: 6,
                padding: "4px 8px 4px 12px", borderRadius: "var(--r-pill)",
                border: "1px solid var(--rule-soft)", background: "var(--paper)",
                fontSize: 13, fontWeight: "var(--fw-med)",
              }}
            >
              {vt.ma}
              {coXoa && (
                <button
                  type="button"
                  aria-label={`Xóa vị trí ${vt.ma}`}
                  disabled={ban}
                  onClick={() => setXoaTarget(vt)}
                  style={{
                    border: "none", background: "transparent", cursor: "pointer",
                    color: "var(--ash)", lineHeight: 0, padding: 2, borderRadius: "var(--r-pill)",
                  }}
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
                    <line x1="6" y1="6" x2="18" y2="18" />
                    <line x1="18" y1="6" x2="6" y2="18" />
                  </svg>
                </button>
              )}
            </span>
          ))}
        </div>
      )}

      {/* Khu thêm mới — chỉ hiện với vai có quyền thêm (dm_kho_hang.create) */}
      {coThem && (
        <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
          <label className="rc-field" style={{ flex: "1 1 180px", margin: 0 }}>
            <span className="rc-field__label">Tên vị trí</span>
            <div className="rc-input-wrapper">
              <input
                className="rc-input"
                value={ma}
                disabled={ban}
                placeholder="Vd: Kệ A - Ô 1"
                onChange={(e) => setMa(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); themViTri(); } }}
              />
            </div>
          </label>
          <label className="rc-field" style={{ flex: "1 1 180px", margin: 0 }}>
            <span className="rc-field__label">Ghi chú (tuỳ chọn)</span>
            <div className="rc-input-wrapper">
              <input
                className="rc-input"
                value={ghiChu}
                disabled={ban}
                placeholder="Vd: sát cửa ra vào"
                onChange={(e) => setGhiChu(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); themViTri(); } }}
              />
            </div>
          </label>
          <Button type="button" variant="primary" loading={ban} disabled={!ma.trim()} onClick={themViTri}>
            Thêm vị trí
          </Button>
        </div>
      )}

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
