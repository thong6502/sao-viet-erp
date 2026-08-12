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
import { ApiError, authed } from "../api/client";
import { crud, type Row } from "../api/rebuildCatalog";
import { FormulaField } from "./RebuildCatalogPage";

const apiCap = crud("/api/don-vi/quy-doi");
const apiDonVi = crud("/api/don-vi");

interface Cap extends Row {
  tu_id: number;
  den_id: number;
  tu_ten: string;
  den_ten: string;
  he_so: number;
  cong_thuc: string | null;
  cau: string | null;
}
interface Bien { ma: string; nhan: string }

export function QuyDoiCuaDonVi({ donVi }: { donVi: Row | null }) {
  const { token } = useAuth();
  const [caps, setCaps] = useState<Cap[]>([]);
  const [dvs, setDvs] = useState<Row[]>([]);
  const [bien, setBien] = useState<Bien[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [ban, setBan] = useState(false);
  // Dòng đang thêm. `dong` = khai bằng công thức (quy đổi động) thay vì con số.
  const [them, setThem] = useState({ gia: "", den_id: "", dong: false });
  const [moBien, setMoBien] = useState(true);
  const [sua, setSua] = useState<Record<number, string>>({});
  // Chỉ MỘT trình soạn công thức mở một lúc.
  const [suaCt, setSuaCt] = useState<number | null>(null);

  const nap = useCallback(() => {
    if (!token || !donVi) return;
    apiCap.list(token).then((r) => setCaps(r.items as Cap[])).catch(() => setCaps([]));
  }, [token, donVi]);

  useEffect(() => { nap(); }, [nap]);

  useEffect(() => {
    if (!token) return;
    apiDonVi.list(token, { active: true }).then((r) => setDvs(r.items)).catch(() => setDvs([]));
    authed<{ items: Bien[] }>("/api/don-vi/bien", token)
      .then((r) => setBien(r.items)).catch(() => setBien([]));
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

  const themDong = () => chay(async () => {
    const body: Record<string, unknown> = { tu_id: donVi.id, den_id: Number(them.den_id) };
    if (them.dong) body.cong_thuc = them.gia.trim();
    else body.he_so = Number(them.gia.replace(",", "."));
    await apiCap.create(token!, body);
    setThem({ gia: "", den_id: "", dong: false });
  });

  const luuDong = (c: Cap, forceVal?: string) => chay(async () => {
    const v = forceVal ?? (sua[c.id] ?? (c.cong_thuc ?? String(c.he_so)));
    await apiCap.update(token!, c.id, {
      tu_id: c.tu_id, den_id: c.den_id,
      ...(c.cong_thuc ? { cong_thuc: v } : { he_so: Number(v.replace(",", ".")) }),
    });
    setSua((p) => { const n = { ...p }; delete n[c.id]; return n; });
    setSuaCt(null);
  });

  const xoaDong = (c: Cap) => {
    if (!window.confirm(`Xoá dòng quy đổi "${c.cau}"?`)) return;
    chay(() => apiCap.remove(token!, c.id));
  };

  // MỖI ĐƠN VỊ CHỈ TÍNH RA BẰNG MỘT CÔNG THỨC (12/08/2026) — luật cho BOM: vật tư khai ĐVT là kg thì
  // lúc bung ở bước lệnh phải có đúng một cách ra kg, hai cái là máy không biết chọn. Chặn theo đơn
  // vị ĐÍCH: `tờ` vẫn đi ra được nhiều đường (→ cái · → kg · → m²) vì ba đích khác nhau.
  // Lọc ngay ở dropdown thay vì để 422 bật ra sau khi bấm — server vẫn chặn, đây chỉ là cửa sớm.
  const dichDaCoCongThuc = useMemo(
    () => new Set(caps.filter((c) => (c.cong_thuc ?? "").trim()).map((c) => c.den_id)),
    [caps],
  );
  const conLai = dvs.filter((d) => d.id !== donVi.id);
  const conLaiChoDong = conLai.filter((d) => !dichDaCoCongThuc.has(Number(d.id)));
  const dsDich = them.dong ? conLaiChoDong : conLai;
  const hetChoDong = conLaiChoDong.length === 0;
  const bienQuyDoi = bien.map((b) => b.ma);

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
          ) : (
            <div className="dvqd__card-list">
              {khaiODay.map((c) => {
                const goc = c.cong_thuc ?? String(c.he_so);
                const v = sua[c.id] ?? goc;
                const dangSoan = suaCt === c.id;
                const isDirty = v !== goc;

                return (
                  <div className={`dvqd__card ${dangSoan ? "dvqd__card--editing" : ""}`} key={c.id}>
                    <div className="dvqd__card-main">
                      <div className="dvqd__card-eq">
                        <span className="dvqd__unit-tag">1 {String(donVi.ten)}</span>
                        <span className="dvqd__eq-sign">=</span>

                        {c.cong_thuc && !dangSoan ? (
                          <span className="dvqd__expr" title={c.cong_thuc}>
                            {cauChu(c.cau, c.den_ten)}
                          </span>
                        ) : c.cong_thuc ? (
                          <span className="dvqd__ve dvqd__ve--soan">Đang soạn công thức...</span>
                        ) : (
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
                        )}

                        <span className="dvqd__unit-name">{c.den_ten}</span>

                        {c.cong_thuc ? (
                          <span className="dvqd__badge dvqd__badge--dynamic" title="Hệ số tự động tính theo công thức">
                            Công thức
                          </span>
                        ) : (
                          <span className="dvqd__badge dvqd__badge--static">
                            {isDirty ? "Đã sửa (Tự lưu)" : "Số cố định"}
                          </span>
                        )}
                      </div>

                      <div className="dvqd__card-actions">
                        {c.cong_thuc && (
                          <button
                            type="button"
                            className="dvqd__btn"
                            disabled={ban}
                            onClick={() => {
                              if (dangSoan && isDirty) luuDong(c);
                              setSuaCt(dangSoan ? null : c.id);
                            }}
                          >
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <path d="M12 20h9"/>
                              <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
                            </svg>
                            {dangSoan ? "Đóng & Lưu" : "Sửa công thức"}
                          </button>
                        )}

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

                    {dangSoan && (
                      <div className="dvqd__editor-subpanel">
                        <FormulaField
                          id={`ct-cap-${c.id}`}
                          value={v}
                          onChange={(x) => setSua((p) => ({ ...p, [c.id]: x }))}
                          configPrefix="/api/don-vi"
                          bienGoiY={bienQuyDoi}
                          nhanO={`Công thức quy đổi: 1 ${String(donVi.ten)} = … ${c.den_ten}`}
                          goY="vd: dinh_luong * dai * rong"
                        />
                      </div>
                    )}
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
                      {c.cau ? cauChu(c.cau, String(donVi.ten)) : `1 ${c.tu_ten} = ${c.he_so} ${donVi.ten}`}
                    </span>
                    <span className="dvqd__unit-tag">{String(donVi.ten)}</span>
                  </div>

                  <div className="dvqd__inbound-meta">
                    {c.cong_thuc && <span className="dvqd__badge dvqd__badge--dynamic">Công thức</span>}
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
            <span>THÊM QUY ĐỔI MỚI</span>

            <div className="dvqd__type-toggle">
              <button
                type="button"
                className={`dvqd__type-btn ${!them.dong ? "is-active" : ""}`}
                onClick={() => setThem((p) => ({ ...p, dong: false, gia: "" }))}
              >
                Số cố định
              </button>
              <button
                type="button"
                className={`dvqd__type-btn ${them.dong ? "is-active" : ""}`}
                disabled={hetChoDong && !them.dong}
                title={hetChoDong
                  ? "Mọi đơn vị còn lại đều đã có công thức động — mỗi đơn vị chỉ tính ra bằng một công thức."
                  : undefined}
                // Đổi sang chế độ động thì bỏ luôn đích đã chọn nếu đích đó không còn hợp lệ —
                // không thì select giữ value cũ mà danh sách không có, trông như chưa chọn gì.
                onClick={() => setThem((p) => ({
                  ...p, dong: true, gia: "",
                  den_id: dichDaCoCongThuc.has(Number(p.den_id)) ? "" : p.den_id,
                }))}
              >
                Công thức động
              </button>
            </div>
          </div>

          <div className="dvqd__create-row">
            <span className="dvqd__create-prefix">1 {String(donVi.ten)} =</span>

            {!them.dong ? (
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
            ) : (
              <input
                className="rc-input dvqd__val"
                style={{ flex: "1 1 200px" }}
                value={them.gia}
                disabled={ban}
                placeholder="Gõ công thức... vd: dinh_luong * dai * rong"
                onChange={(e) => setThem((p) => ({ ...p, gia: e.target.value }))}
              />
            )}

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

            {/* Nút khoá thì phải NÓI THIẾU GÌ. Không có dòng này người dùng bấm mãi không ăn rồi
                tưởng hỏng — đúng cái vừa dính 12/08/2026. */}
            {!ban && (!them.gia || !them.den_id) && (
              <p className="dvqd__hint">
                {!them.gia
                  ? (them.dong ? "Gõ công thức đã" : "Nhập số quy đổi đã")
                  : "Còn thiếu: chọn đơn vị quy đổi về"}
              </p>
            )}

            {them.dong && (
              <button
                type="button"
                className={`dvqd__btn ${moBien ? "dvqd__btn--primary" : ""}`}
                onClick={() => setMoBien((v) => !v)}
                title="Tra cứu danh sách mã biến khả dụng và hướng dẫn cú pháp"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="11" cy="11" r="8"/>
                  <line x1="21" y1="21" x2="16.65" y2="16.65"/>
                </svg>
                {moBien ? "Thu gọn biến" : "Tra cứu biến"}
              </button>
            )}
          </div>

          {them.dong && moBien && (
            <div className="dvqd__editor-subpanel">
              <FormulaField
                id="ct-them"
                value={them.gia}
                onChange={(x) => setThem((p) => ({ ...p, gia: x }))}
                configPrefix="/api/don-vi"
                bienGoiY={bienQuyDoi}
                nhanO="Tra cứu biến & Cú pháp công thức quy đổi"
                goY="vd: dinh_luong * dai * rong"
              />
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

/** Vế phải của câu server dựng ("1 tờ = định lượng × dài × rộng kg" → "định lượng × dài × rộng"). */
function cauChu(cau: string | null, denTen: string): string {
  if (!cau) return "";
  const sau = cau.split("=").slice(1).join("=").trim();
  return sau.endsWith(denTen) ? sau.slice(0, -denTen.length).trim() : sau;
}
