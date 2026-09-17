// MỨC khoán km — mỗi mức một bảng bậc giá, nhiều xe dùng chung một mức.
// Giao diện tinh gọn, đơn giản, chuẩn phong cách ERP.
// Cấu hình CHUNG toàn công ty (chủ chốt 14/09/2026): sống ở sub-tab riêng "Khoán km giao hàng",
// KHÔNG nhận phòng ban nào — trước đó nằm trong "Cơ chế lương theo bộ phận", tắt cờ Giao hàng của
// phòng đang chọn là cả thẻ biến mất dù xe vẫn đang ăn các mức này.
import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Pencil,
  Plus,
  Save,
  SlidersHorizontal,
  Trash2,
  X,
} from "lucide-react";

import { ApiError, api, type KmBracket, type MucKm } from "../../../../../api/client";
import { Button } from "../../../../../components/Button";

const MOI: KmBracket[] = [{ up_to_km: null, don_gia: 0 }];
const tien = (n: number) => Number(n || 0).toLocaleString("vi-VN");

export function MucKhoanKmEditor({
  token,
  readOnly,
}: {
  token: string;
  readOnly?: boolean;
}) {
  const [ds, setDs] = useState<MucKm[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [tenMoi, setTenMoi] = useState("");

  // Popup modal sửa bậc giá
  const [mo, setMo] = useState<number | null>(null);
  const [nhap, setNhap] = useState<KmBracket[]>(MOI);
  const [goc, setGoc] = useState("");
  const [modalErr, setModalErr] = useState<string | null>(null);

  // Dialog sửa tên mức
  const [doiTenTarget, setDoiTenTarget] = useState<MucKm | null>(null);
  const [doiTenInput, setDoiTenInput] = useState("");

  // Dialog xác nhận xóa mức
  const [xoaConfirm, setXoaConfirm] = useState<MucKm | null>(null);

  const dirty = JSON.stringify(nhap) !== goc;

  const nap = useCallback(() => {
    setLoading(true);
    setErr(null);
    api.giaoHang
      .mucKhoanKm(token)
      .then((r) => setDs(r.items))
      .catch(() => setErr("Không tải được danh sách mức khoán km."))
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    nap();
  }, [nap]);

  // Phím Escape đóng modal
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (doiTenTarget) setDoiTenTarget(null);
        else if (xoaConfirm) setXoaConfirm(null);
        else if (mo != null && !busy) setMo(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mo, busy, doiTenTarget, xoaConfirm]);

  const loi = (e: unknown, inModal = false) => {
    const msg =
      e instanceof ApiError && (e.status === 400 || e.status === 422 || e.isConflict)
        ? e.message
        : "Thao tác thất bại. Vui lòng thử lại.";
    if (inModal) {
      setModalErr(msg);
    } else {
      setErr(msg);
    }
  };

  const taoMuc = () => {
    if (!tenMoi.trim()) return;
    setBusy(true);
    setErr(null);
    setOk(null);
    api.giaoHang
      .taoMucKhoanKm(token, { ten: tenMoi.trim() })
      .then((r) => {
        setDs(r.items);
        const vua = r.items.find((m) => m.ten === tenMoi.trim());
        setTenMoi("");
        setOk(`Đã tạo mức “${vua?.ten ?? tenMoi.trim()}”.`);
        if (vua) moBang(vua);
      })
      .catch((e) => loi(e, false))
      .finally(() => setBusy(false));
  };

  const moDoiTen = (m: MucKm) => {
    setDoiTenTarget(m);
    setDoiTenInput(m.ten);
    setErr(null);
  };

  const luuTenMoi = () => {
    if (!doiTenTarget || !doiTenInput.trim()) return;
    setBusy(true);
    setErr(null);
    setOk(null);
    api.giaoHang
      .suaMucKhoanKm(token, doiTenTarget.id, { ten: doiTenInput.trim() })
      .then((r) => {
        setDs(r.items);
        setOk(`Đã đổi tên thành “${doiTenInput.trim()}”.`);
        setDoiTenTarget(null);
      })
      .catch((e) => loi(e, false))
      .finally(() => setBusy(false));
  };

  const xoaMuc = (m: MucKm) => {
    setBusy(true);
    setErr(null);
    setOk(null);
    api.giaoHang
      .xoaMucKhoanKm(token, m.id)
      .then((r) => {
        setDs(r.items);
        setOk(`Đã xoá mức “${m.ten}”.`);
        setXoaConfirm(null);
        if (mo === m.id) setMo(null);
      })
      .catch((e) => loi(e, false))
      .finally(() => setBusy(false));
  };

  const moBang = (m: MucKm) => {
    const kh = m.items.length ? m.items.map((b) => ({ ...b })) : MOI.map((b) => ({ ...b }));
    setMo(m.id);
    setNhap(kh);
    setGoc(JSON.stringify(m.items.length ? kh : []));
    setModalErr(null);
    setErr(null);
    setOk(null);
  };

  const themBac = () => {
    setNhap((s) => {
      const truoc = s.slice(0, -1);
      const cuoi = s[s.length - 1] ?? { up_to_km: null, don_gia: 0 };
      const prevTran = truoc.length > 0 ? (truoc[truoc.length - 1].up_to_km ?? 0) : 0;
      const nextKm = prevTran + 20;
      return [...truoc, { up_to_km: nextKm, don_gia: cuoi.don_gia || 0 }, cuoi];
    });
  };

  const xoaBac = (i: number) => {
    setNhap((s) => s.filter((_, j) => j !== i));
  };

  const luuBac = () => {
    if (mo == null) return;

    for (let i = 0; i < nhap.length - 1; i++) {
      const km = nhap[i].up_to_km;
      if (km == null || km <= 0) {
        setModalErr(`Vui lòng nhập số km trần (> 0) cho Bậc ${i + 1}.`);
        return;
      }
      if (i > 0) {
        const prevKm = nhap[i - 1].up_to_km ?? 0;
        if (km <= prevKm) {
          setModalErr(`Mốc km của Bậc ${i + 1} (${km} km) phải lớn hơn Bậc ${i} (${prevKm} km).`);
          return;
        }
      }
    }
    for (let i = 0; i < nhap.length; i++) {
      if (nhap[i].don_gia < 0) {
        setModalErr(`Đơn giá của Bậc ${i + 1} không được là số âm.`);
        return;
      }
    }

    setBusy(true);
    setModalErr(null);
    setErr(null);
    setOk(null);
    api.giaoHang
      .saveKmBracketsMuc(token, mo, nhap)
      .then((r) => {
        setDs(r.items);
        setOk("Đã lưu bảng bậc giá khoán km thành công.");
        setMo(null);
      })
      .catch((e) => loi(e, true))
      .finally(() => setBusy(false));
  };

  const dangMo = ds.find((m) => m.id === mo);

  return (
    <div className="cl-card">
      <div className="cl-card__head">
        <div>
          <h3 className="cl-card__title">Mức khoán km</h3>
          <p className="cl-card__desc">
            Bảng giá khoán km áp dụng cho xe giao hàng (gán tại <b>Cấu hình danh mục → Xe giao hàng</b>).
            Mỗi mức thiết lập các nấc km và đơn giá tương ứng.
          </p>
        </div>
      </div>

      <div className="cl-card__body">
        {err && (
          <div className="banner banner--error" style={{ marginBottom: 12 }}>
            <AlertCircle size={15} />
            <span>{err}</span>
          </div>
        )}
        {ok && (
          <div className="banner banner--success" style={{ marginBottom: 12 }}>
            <CheckCircle2 size={15} />
            <span>{ok}</span>
          </div>
        )}

        {/* Thêm mức mới */}
        {!readOnly && (
          <div className="muc-km-add-row">
            <input
              className="input"
              style={{ maxWidth: 360 }}
              placeholder="Tên mức mới (vd: Xe 2 tấn, Xe 5 tấn)..."
              value={tenMoi}
              disabled={busy}
              onChange={(e) => setTenMoi(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && tenMoi.trim() && !busy) taoMuc();
              }}
            />
            <Button
              variant="secondary"
              className="btn--sm"
              loading={busy}
              disabled={!tenMoi.trim()}
              onClick={taoMuc}
            >
              <Plus size={14} style={{ marginRight: 4 }} />
              Tạo mức mới
            </Button>
          </div>
        )}

        {/* Danh sách bảng mức */}
        {loading ? (
          <p className="cl-hint-inline">Đang tải danh sách mức khoán…</p>
        ) : ds.length === 0 ? (
          <p className="cl-hint-inline">
            Chưa có mức khoán km nào. Vui lòng nhập tên ở trên (ví dụ “Xe 2 tấn”) để tạo mức.
          </p>
        ) : (
          <div className="cl-table__wrap">
            <table className="cl-table">
              <thead>
                <tr>
                  <th style={{ width: "22%" }}>Tên mức</th>
                  <th style={{ width: "48%" }}>Bậc giá cước</th>
                  <th style={{ width: "15%" }}>Xe áp dụng</th>
                  <th style={{ width: "15%", textAlign: "right" }}>Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {ds.map((m) => (
                  <tr key={m.id}>
                    <td>
                      <span style={{ fontWeight: 600 }}>{m.ten}</span>
                    </td>
                    <td>
                      {m.items.length === 0 ? (
                        <span className="cl-hint-inline" style={{ color: "var(--amber-deep, #b45309)" }}>
                          {/* Từ 14/09/2026 lên đơn bằng xe có mức rỗng bị CHẶN — nói luôn hệ quả,
                              kẻo người ta tưởng mức rỗng vẫn chạy như trước. */}
                          Chưa cài bậc giá — xe gán mức này chưa lên đơn được
                        </span>
                      ) : (
                        <div className="muc-km-brackets-clean">
                          {m.items.map((b, idx) => (
                            <span key={idx} className="muc-km-bracket-item">
                              {b.up_to_km == null ? (
                                <>
                                  &gt;{m.items[idx - 1]?.up_to_km ?? 0} km: <b>{tien(b.don_gia)} đ</b>
                                </>
                              ) : (
                                <>
                                  ≤{b.up_to_km} km: <b>{tien(b.don_gia)} đ</b>
                                </>
                              )}
                              {idx < m.items.length - 1 && <span className="muc-km-bracket-dot">·</span>}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td>
                      {m.so_xe > 0 ? (
                        <span>{m.so_xe} xe</span>
                      ) : (
                        <span className="cl-hint-inline">Chưa gán</span>
                      )}
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <div style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                        <Button
                          variant="ghost"
                          className="btn--sm"
                          title="Xem & sửa bậc giá"
                          onClick={() => moBang(m)}
                        >
                          <SlidersHorizontal size={13} style={{ marginRight: 4 }} />
                          Sửa bậc
                        </Button>
                        {!readOnly && (
                          <>
                            <button
                              type="button"
                              className="btn-icon"
                              title="Đổi tên mức"
                              disabled={busy}
                              onClick={() => moDoiTen(m)}
                            >
                              <Pencil size={13} />
                            </button>
                            <button
                              type="button"
                              className="btn-icon text-danger"
                              title="Xóa mức"
                              disabled={busy}
                              onClick={() => setXoaConfirm(m)}
                            >
                              <Trash2 size={13} />
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* POPUP MODAL: CHI TIẾT BẬC GIÁ KHOÁN KM */}
      {dangMo && (
        <div
          className="ns-modal"
          role="dialog"
          aria-modal="true"
          onClick={() => {
            if (!busy) setMo(null);
          }}
        >
          <div
            className="ns-modal__box"
            style={{ maxWidth: 620, width: "95%" }}
            onClick={(e) => e.stopPropagation()}
          >
            <header className="ns-modal__head">
              <div>
                <h2>Bậc giá khoán km · {dangMo.ten}</h2>
                <p className="cl-hint-inline" style={{ marginTop: 2, margin: 0 }}>
                  {dangMo.so_xe > 0
                    ? `Đang áp dụng cho ${dangMo.so_xe} xe giao hàng.`
                    : "Mức này chưa gán cho xe nào."}
                </p>
              </div>

              <button
                type="button"
                className="ns-modal__x"
                aria-label="Đóng popup"
                onClick={() => setMo(null)}
              >
                <X size={16} />
              </button>
            </header>

            <div className="ns-modal__body" style={{ padding: "16px 20px" }}>
              {modalErr && (
                <div className="banner banner--error" style={{ marginBottom: 12 }}>
                  <AlertCircle size={15} />
                  <span>{modalErr}</span>
                </div>
              )}

              {/* Bảng bậc giá */}
              <div className="cl-table__wrap">
                <table className="cl-table">
                  <thead>
                    <tr>
                      <th style={{ width: "15%" }}>Bậc</th>
                      <th style={{ width: "45%" }}>Cự ly chuyến áp dụng</th>
                      <th style={{ width: "30%" }}>Đơn giá (đ/km)</th>
                      <th style={{ width: "10%", textAlign: "center" }}>Xóa</th>
                    </tr>
                  </thead>
                  <tbody>
                    {nhap.map((b, i) => {
                      const cuoi = i === nhap.length - 1;
                      const prevKm = i > 0 ? (nhap[i - 1]?.up_to_km ?? 0) : 0;
                      return (
                        <tr key={i}>
                          <td style={{ fontWeight: 600 }}>Bậc {i + 1}</td>
                          <td>
                            {cuoi ? (
                              <span className="cl-hint-inline">
                                Từ <b>{prevKm} km</b> trở lên (không giới hạn)
                              </span>
                            ) : (
                              <div style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                                <span style={{ fontSize: 13, color: "var(--ash, #64748b)" }}>
                                  Từ {prevKm} đến
                                </span>
                                <input
                                  type="number"
                                  className="input input--sm"
                                  style={{ width: 75, textAlign: "right" }}
                                  min={(prevKm || 0) + 1}
                                  placeholder="vd 10"
                                  disabled={readOnly}
                                  value={b.up_to_km ?? ""}
                                  onChange={(e) => {
                                    const v = e.target.value ? Number(e.target.value) : null;
                                    setNhap((s) =>
                                      s.map((x, j) => (j === i ? { ...x, up_to_km: v } : x)),
                                    );
                                  }}
                                />
                                <span style={{ fontSize: 13, color: "var(--ash, #64748b)" }}>km</span>
                              </div>
                            )}
                          </td>
                          <td>
                            <div style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                              <input
                                type="number"
                                className="input input--sm"
                                style={{ width: 110, textAlign: "right" }}
                                min={0}
                                step={500}
                                disabled={readOnly}
                                value={b.don_gia}
                                onChange={(e) => {
                                  const v = Number(e.target.value) || 0;
                                  setNhap((s) =>
                                    s.map((x, j) => (j === i ? { ...x, don_gia: v } : x)),
                                  );
                                }}
                              />
                              <span style={{ fontSize: 13, color: "var(--ash, #64748b)" }}>đ/km</span>
                            </div>
                          </td>
                          <td style={{ textAlign: "center" }}>
                            {!readOnly && (
                              <button
                                type="button"
                                className="btn-icon text-danger"
                                title="Xóa bậc này"
                                disabled={nhap.length === 1}
                                onClick={() => xoaBac(i)}
                              >
                                <Trash2 size={13} />
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {!readOnly && (
                <div style={{ marginTop: 10 }}>
                  <Button
                    variant="secondary"
                    className="btn--sm"
                    onClick={themBac}
                  >
                    <Plus size={14} style={{ marginRight: 4 }} />
                    Thêm bậc cự ly
                  </Button>
                </div>
              )}
            </div>

            <footer className="ns-modal__foot">
              <Button
                variant="ghost"
                onClick={() => setMo(null)}
              >
                Đóng
              </Button>
              {!readOnly && (
                <Button
                  variant="accent"
                  loading={busy}
                  disabled={!dirty || busy}
                  onClick={luuBac}
                >
                  <Save size={15} style={{ marginRight: 6 }} />
                  Lưu bậc giá
                </Button>
              )}
            </footer>
          </div>
        </div>
      )}

      {/* POPUP MODAL: ĐỔI TÊN MỨC */}
      {doiTenTarget && (
        <div
          className="ns-modal"
          role="dialog"
          aria-modal="true"
          onClick={() => setDoiTenTarget(null)}
        >
          <div
            className="ns-modal__box"
            style={{ maxWidth: 420, width: "90%" }}
            onClick={(e) => e.stopPropagation()}
          >
            <header className="ns-modal__head">
              <h2>Đổi tên mức khoán km</h2>
              <button
                type="button"
                className="ns-modal__x"
                onClick={() => setDoiTenTarget(null)}
              >
                <X size={16} />
              </button>
            </header>
            <div className="ns-modal__body" style={{ padding: "16px 20px" }}>
              <label className="ns-field" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <span className="ns-field__label" style={{ fontWeight: 600, fontSize: "13px" }}>
                  Tên mức khoán *
                </span>
                <input
                  className="input"
                  value={doiTenInput}
                  autoFocus
                  placeholder="vd: Xe 2 tấn"
                  onChange={(e) => setDoiTenInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && doiTenInput.trim() && !busy) luuTenMoi();
                  }}
                />
              </label>
            </div>
            <footer className="ns-modal__foot">
              <Button variant="ghost" disabled={busy} onClick={() => setDoiTenTarget(null)}>
                Hủy
              </Button>
              <Button
                variant="accent"
                loading={busy}
                disabled={!doiTenInput.trim() || doiTenInput.trim() === doiTenTarget.ten}
                onClick={luuTenMoi}
              >
                Lưu tên mới
              </Button>
            </footer>
          </div>
        </div>
      )}

      {/* POPUP MODAL: XÁC NHẬN XÓA MỨC */}
      {xoaConfirm && (
        <div
          className="ns-modal"
          role="dialog"
          aria-modal="true"
          onClick={() => setXoaConfirm(null)}
        >
          <div
            className="ns-modal__box"
            style={{ maxWidth: 440, width: "90%" }}
            onClick={(e) => e.stopPropagation()}
          >
            <header className="ns-modal__head">
              <h2>Xác nhận xóa mức khoán</h2>
              <button
                type="button"
                className="ns-modal__x"
                onClick={() => setXoaConfirm(null)}
              >
                <X size={16} />
              </button>
            </header>
            <div className="ns-modal__body" style={{ padding: "16px 20px" }}>
              <p style={{ margin: 0, fontSize: "13.5px", color: "var(--ink, #0f172a)", lineHeight: 1.5 }}>
                Bạn có chắc chắn muốn xóa mức khoán <b>“{xoaConfirm.ten}”</b>?
              </p>
              {xoaConfirm.so_xe > 0 && (
                <div className="banner banner--warn" style={{ marginTop: 12 }}>
                  <AlertCircle size={15} style={{ flexShrink: 0 }} />
                  <span>
                    Đang có <b>{xoaConfirm.so_xe} xe</b> được gán mức này. Máy chủ sẽ từ chối xóa nếu
                    chưa chuyển các xe này sang mức khác.
                  </span>
                </div>
              )}
            </div>
            <footer className="ns-modal__foot">
              <Button variant="ghost" disabled={busy} onClick={() => setXoaConfirm(null)}>
                Hủy
              </Button>
              <Button
                variant="danger"
                loading={busy}
                onClick={() => xoaMuc(xoaConfirm)}
              >
                Xóa mức
              </Button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}
