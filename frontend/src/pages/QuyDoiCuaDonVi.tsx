// Khối "QUY ĐỔI CỦA <đơn vị>" nằm cuối drawer Đơn vị — CHỖ DUY NHẤT khai quy đổi.
//
// HAI KHỐI TÁCH BẠCH BỐ CỤC CHUẨN ERP:
//   · Khối 1: BẢNG TỔNG QUAN QUY ĐỔI 2 CHIỀU (Quy đổi khai tại đây & Quy đổi từ nơi khác về).
//   · Khối 2: KHU VỰC THÊM MỚI & SOẠN THẢO CÔNG THỨC (Thêm mới + Tra cứu biến).
//
// Cơ chế Tự động lưu (Auto-save): Khi chỉnh sửa số cố định, tự động lưu khi Blur hoặc gõ Enter,
// không cần bấm nút "Lưu" gây rườm rà.
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "../auth/useAuth";
import { ApiError } from "../api/client";
import { crud, type Row } from "../api/rebuildCatalog";

const apiCap = crud("/api/don-vi/quy-doi");
const apiDonVi = crud("/api/don-vi");

interface Cap extends Row {
  tu_id: number;
  den_id: number;
  tu_ten: string;
  den_ten: string;
  // Dòng CẶP chỉ mang SỐ. Field `cong_thuc` của cặp đã gỡ 14/08/2026 (mg 0198) — công thức nay khai
  // ở chính đơn vị (`don_vi_do.cong_thuc`, xem `ctCuaDonVi` bên dưới) và trả LƯỢNG, không có đích.
  he_so: number;
  cau: string | null;
}

/** Số cho người đọc: bỏ đuôi 0 thừa, tối đa 6 chữ số thập phân (1/1000 → "0,001"). */
function soGon(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return "?";
  return n.toLocaleString("vi-VN", { maximumFractionDigits: 6 });
}


export function QuyDoiCuaDonVi({ donVi }: { donVi: Row | null }) {
  const { token } = useAuth();
  const [caps, setCaps] = useState<Cap[]>([]);
  const [dvs, setDvs] = useState<Row[]>([]);
  const [err, setErr] = useState<string | null>(null);

  const [ban, setBan] = useState(false);
  // Dòng đang thêm. Chỉ còn MỘT dạng: "1 <đơn vị này> = <số> <đơn vị kia>".
  const [them, setThem] = useState({ gia: "", den_id: "" });
  const [sua, setSua] = useState<Record<number, string>>({});

  const nap = useCallback(() => {
    if (!token || !donVi) return;
    apiCap.list(token).then((r) => setCaps(r.items as Cap[])).catch(() => setCaps([]));
  }, [token, donVi]);

  useEffect(() => { nap(); }, [nap]);

  useEffect(() => {
    if (!token) return;
    apiDonVi.list(token, { active: true }).then((r) => setDvs(r.items)).catch(() => setDvs([]));
  }, [token]);

  const khaiODay = useMemo(() => caps.filter((c) => c.tu_id === donVi?.id), [caps, donVi]);
  const doiVe = useMemo(() => caps.filter((c) => c.den_id === donVi?.id), [caps, donVi]);

  if (!donVi) {
    return (
      <section className="dvqd">
        <div className="dvqd__head">Quy đổi đơn vị</div>
        <p className="dvqd__hint">Vui lòng lưu thông tin đơn vị trước khi khai báo quy đổi.</p>
      </section>
    );
  }

  async function chay<T>(viec: () => Promise<T>) {
    if (!token) return;
    setBan(true); setErr(null);
    try { await viec(); nap(); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Không thể lưu dữ liệu."); }
    finally { setBan(false); }
  }

  // MỘT DẠNG DUY NHẤT: dòng CẶP "1 tấn = 1.000 kg" — có đích, hệ số không đổi.
  //
  // Chế độ "Theo quy cách" (ghi `don_vi_do.cong_thuc`) GỠ 17/08/2026: câu "một lệnh cần bao nhiêu"
  // không thuộc về ĐƠN VỊ mà thuộc về một MÓN / MÁY / ĐẦU VIỆC / BƯỚC cụ thể, và cả bốn nay đều có
  // ô công thức riêng. Module này còn đúng hai việc: khai đơn vị, và quy đổi giữa các đơn vị.
  const themDong = () => chay(async () => {
    await apiCap.create(token!, {
      tu_id: donVi.id, den_id: Number(them.den_id),
      he_so: Number(them.gia.replace(",", ".")),
    });
    setThem({ gia: "", den_id: "" });
  });

  const luuDong = (c: Cap, forceVal?: string) => chay(async () => {
    const v = forceVal ?? sua[c.id] ?? String(c.he_so);
    await apiCap.update(token!, c.id, {
      tu_id: c.tu_id, den_id: c.den_id, he_so: Number(v.replace(",", ".")),
    });
    setSua((p) => { const n = { ...p }; delete n[c.id]; return n; });
  });

  const xoaDong = (c: Cap) => {
    if (!window.confirm(`Xoá dòng quy đổi "${c.cau}"?`)) return;
    chay(() => apiCap.remove(token!, c.id));
  };

  const dsDich = dvs.filter((d) => d.id !== donVi.id);

  return (
    <section className="dvqd">
      {err && <div className="dvqd__err" role="alert">{err}</div>}

      {/* =========================================================================
          KHỐI 1: BẢNG TỔNG QUAN QUY ĐỔI ĐƠN VỊ (2 CHIỀU)
          ========================================================================= */}
      <div className="dvqd__block">
        <div className="dvqd__block-header">
          <span className="dvqd__block-title">DANH SÁCH QUY ĐỔI CỦA {String(donVi.ten).toUpperCase()}</span>
          <span className="dvqd__count-badge">{khaiODay.length + doiVe.length} quy đổi</span>
        </div>

        {/* --- Sub-section 1: Quy đổi khai tại đây (Tờ ➔ ...) ----------------------- */}
        <div className="dvqd__sub-section">
          <div className="dvqd__sub-title">
            <span>Quy đổi khai tại đây</span>
            <span className="dvqd__sub-badge">{khaiODay.length}</span>
          </div>

          {khaiODay.length === 0 ? (
            <p className="dvqd__hint">Chưa có quy đổi nào được khai báo cho đơn vị này.</p>
          ) : khaiODay.length === 0 ? null : (
            <div className="dvqd__card-list">
              {khaiODay.map((c) => {
                const goc = String(c.he_so);
                const v = sua[c.id] ?? goc;
                const isDirty = v !== goc;

                return (
                  <div className="dvqd__card" key={c.id}>
                    <div className="dvqd__card-main">
                      <div className="dvqd__card-eq">
                        <span className="dvqd__unit-tag">1 {String(donVi.ten)}</span>
                        <span className="dvqd__eq-sign">=</span>

                        <input
                          className={`dvqd__val-input ${isDirty ? "dvqd__val-input--dirty" : ""}`}
                          value={v}
                          disabled={ban}
                          placeholder="Hệ số..."
                          onChange={(e) => setSua((p) => ({ ...p, [c.id]: e.target.value }))}
                          onBlur={() => { if (isDirty) luuDong(c); }}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" && isDirty) {
                              e.preventDefault();
                              luuDong(c);
                            }
                          }}
                        />

                        <span className="dvqd__unit-name">{c.den_ten}</span>

                        <span className="dvqd__badge dvqd__badge--static">
                          {isDirty ? "Đã sửa (Tự lưu)" : "Số cố định"}
                        </span>
                      </div>

                      <div className="dvqd__card-actions">
                        <button
                          type="button"
                          className="dvqd__btn dvqd__btn--danger"
                          disabled={ban}
                          onClick={() => xoaDong(c)}
                          title="Xoá dòng quy đổi này"
                        >
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <polyline points="3 6 5 6 21 6"/>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                          </svg>
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* --- Sub-section 2: Quy đổi từ đơn vị khác về (... ➔ Tờ) ------------------ */}
        {doiVe.length > 0 && (
          <div className="dvqd__sub-section dvqd__sub-section--inbound">
            <div className="dvqd__sub-title">
              <span>Quy đổi từ đơn vị khác về {String(donVi.ten)}</span>
              <span className="dvqd__sub-badge">{doiVe.length}</span>
            </div>

            <div className="dvqd__card-list">
              {doiVe.map((c) => (
                <div className="dvqd__inbound-card" key={c.id}>
                  <div className="dvqd__inbound-flow">
                    <span className="dvqd__unit-tag">{c.tu_ten}</span>
                    <svg className="dvqd__arrow-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <line x1="5" y1="12" x2="19" y2="12" />
                      <polyline points="12 5 19 12 12 19" />
                    </svg>
                    <span className="dvqd__inbound-expr">
                      {/* LẬT về chiều của đơn vị ĐANG MỞ (14/08/2026). Mở `kg` mà đọc
                          "1 tấn = 1.000 kg" thì phải tự lật trong đầu mới biết 1 kg là bao nhiêu
                          tấn. Cặp đi HAI CHIỀU nên lật là hợp lệ. */}
                      {`1 ${donVi.ten} = ${soGon(1 / Number(c.he_so || 1))} ${c.tu_ten}`}
                    </span>
                    <span className="dvqd__unit-tag">{String(donVi.ten)}</span>
                  </div>

                  <div className="dvqd__inbound-meta">
                    <span className="dvqd__nguon">Khai tại đơn vị {c.tu_ten}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* =========================================================================
          KHỐI 2: KHU VỰC THÊM MỚI & SOẠN THẢO CÔNG THỨC
          ========================================================================= */}
      <div className="dvqd__block dvqd__block--action">
        <div className="dvqd__create-card">
          <div className="dvqd__create-header">
            <div className="dvqd__create-title">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19"/>
                <line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
              <span>THÊM QUY ĐỔI MỚI</span>
            </div>

            {/* Dải chọn "Số cố định / Theo quy cách" GỠ 17/08/2026 — chỉ còn một dạng nên không
                còn gì để chọn. Công thức tính lượng khai ở món hàng · máy · công việc khoán · công
                đoạn, tuỳ số đó thuộc về ai. */}
          </div>

          <div className="dvqd__create-body">
            {(
              <div className="dvqd__create-row">
                <span className="dvqd__create-prefix">{String(donVi.ten)} =</span>
                <input
                  className="rc-input dvqd__val"
                  style={{ width: "120px" }}
                  value={them.gia}
                  disabled={ban}
                  placeholder="Vd: 1.000"
                  onChange={(e) => setThem((p) => ({ ...p, gia: e.target.value }))}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && them.gia && them.den_id) {
                      e.preventDefault();
                      themDong();
                    }
                  }}
                />
                <select
                  className="rc-input dvqd__den"
                  value={them.den_id}
                  disabled={ban}
                  onChange={(e) => setThem((p) => ({ ...p, den_id: e.target.value }))}
                >
                  <option value="">— Đơn vị quy đổi về —</option>
                  {dsDich.map((d) => (
                    <option key={d.id} value={d.id}>
                      {String(d.ten)}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>

          <div className="dvqd__create-footer">
            {!ban && (!them.gia || !them.den_id) && (
              <p className="dvqd__hint">
                {!them.gia ? "Nhập số quy đổi đã" : "Còn thiếu: chọn đơn vị quy đổi về"}
              </p>
            )}

            <div className="dvqd__footer-actions">
              <button
                type="button"
                className="dvqd__btn dvqd__btn--primary"
                disabled={ban || !them.gia || !them.den_id}
                onClick={themDong}
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <line x1="12" y1="5" x2="12" y2="19"/>
                  <line x1="5" y1="12" x2="19" y2="12"/>
                </svg>
                Thêm quy đổi
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
