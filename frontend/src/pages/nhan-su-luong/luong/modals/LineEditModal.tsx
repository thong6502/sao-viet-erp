// Modal sửa một dòng lương + khoản phát sinh (tách từ pages/LuongPage.tsx).
import { useCallback, useEffect, useState } from "react";
import {
  api,
  type LineComponent,
  type PayrollComponent,
  type PayrollLine,
} from "../../../../api/client";
import { OPEN_COMPONENT_CODES } from "../shared/constants";
import { errText, legacyBonusRows, money } from "../shared/helpers";

export function LineEditModal({
  token,
  line,
  readOnly,
  onClose,
  onSaved,
}: {
  token: string;
  line: PayrollLine;
  /** Kỳ đã chốt / đã chi ⇒ khối "Khoản phát sinh" chỉ đọc (backend cũng chặn — 409). */
  readOnly: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [viPham, setViPham] = useState(line.vi_pham);
  const [note, setNote] = useState(line.note ?? "");
  // ⚠️ KHÔNG còn ô thưởng ở đây (chủ 28/07/2026: "khoản 5s hay thưởng gì thì cho nó select từ
  // quy tắc, để coi nó chịu thuế hay không"). 5 ô thưởng + "Thưởng khác" đã bị gỡ; thưởng khai ở
  // khối "Khoản phát sinh tháng này" bên dưới. Backend cũng đã bỏ chúng khỏi `LineUpdateIn`.
  const [detail, setDetail] = useState({
    di_tre: line.di_tre,
    dt_vuot_troi: line.dt_vuot_troi,
    phat_bien_ban: line.phat_bien_ban,
    phat_5s_dong_phuc: line.phat_5s_dong_phuc,
  });
  // Cột thưởng CŨ còn số (kỳ chốt trước 28/07/2026, hoặc dòng migration cố ý không đụng vì HCNS
  // đã tự thêm khoản trùng) → hiện CHỈ ĐỌC để tổng trên màn khớp phiếu, không cho sửa.
  const legacyBonus = legacyBonusRows(line);
  const setD = (k: keyof typeof detail, v: number) =>
    setDetail((d) => ({ ...d, [k]: v }));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // Ô "Đi trễ": mặc định TỰ ĐỘNG từ chấm công. `di_tre_manual` = HCNS đã ghi đè tay.
  const [diTreManual, setDiTreManual] = useState(line.di_tre_manual);

  // --- TẦNG 3: khoản PHÁT SINH của riêng kỳ này (thưởng nóng) ---------------
  // Mỗi thao tác gọi API NGAY (backend tính lại dòng lương ngay lúc đó), KHÔNG gom vào nút
  // "Lưu" chung — gom lại thì số tổng trên màn và số thật trong DB lệch nhau giữa chừng.
  // null = ĐANG TẢI (khởi tạo [] sẽ báo "chưa có khoản nào" lúc còn fetch — sai).
  const [lcRows, setLcRows] = useState<LineComponent[] | null>(null);
  const [lcErr, setLcErr] = useState<string | null>(null);
  const [lcOk, setLcOk] = useState<string | null>(null);
  const [lcBusyId, setLcBusyId] = useState<number | null>(null);
  const [lcDraft, setLcDraft] = useState<
    Record<number, { amount: number; note: string }>
  >({});
  const [lcCatalog, setLcCatalog] = useState<PayrollComponent[] | null>(null);
  const [lcCatalogErr, setLcCatalogErr] = useState<string | null>(null);
  const [lcAdd, setLcAdd] = useState<{
    component_id: number;
    amount: number;
    note: string;
  } | null>(null);
  const [lcAddBusy, setLcAddBusy] = useState(false);
  // Sửa khoản ⇒ backend tính lại dòng ⇒ các số tổng ở đầu modal (`line`) thành CŨ. Nói ra chứ
  // đừng để người dùng đọc số cũ tưởng là số mới.
  const [lcTouched, setLcTouched] = useState(false);

  const loadLineComps = useCallback(async () => {
    try {
      const r = await api.luong.lineComponents(token, line.id);
      setLcRows(r.items);
      // GIỮ nháp của dòng còn tồn tại: tải lại sau khi xoá/sửa một dòng khác mà xoá trắng số
      // đang gõ dở ở dòng bên cạnh là mất công gõ lại (và dễ gõ nhầm số tiền lần hai).
      setLcDraft((prev) =>
        Object.fromEntries(
          r.items.map((x) => [
            x.id,
            prev[x.id] ?? { amount: x.amount, note: x.note ?? "" },
          ]),
        ),
      );
      setLcErr(null);
    } catch (e) {
      setLcErr(errText(e));
    }
  }, [token, line.id]);
  useEffect(() => {
    void loadLineComps();
  }, [loadLineComps]);
  useEffect(() => {
    if (readOnly) return; // chỉ đọc thì không cần danh mục để thêm
    let alive = true;
    api.luong.components
      .list(token)
      .then((r) => {
        if (!alive) return;
        setLcCatalog(r.items);
        setLcCatalogErr(null);
      })
      .catch((e) => {
        if (!alive) return;
        setLcCatalogErr(errText(e));
      });
    return () => {
      alive = false;
    };
  }, [token, readOnly]);

  /** Khoản chọn được khi thêm phát sinh: đang bật, 2 khoản "Thu nhập khác" lên đầu. KHÔNG lọc
   *  khoản đã có trên dòng — cùng một khoản có thể phát sinh 2 lần với 2 lý do khác nhau. */
  const lcAddable = (lcCatalog ?? [])
    .filter((c) => c.is_active)
    .slice()
    .sort((a, b) => {
      const ia = OPEN_COMPONENT_CODES.indexOf(a.code);
      const ib = OPEN_COMPONENT_CODES.indexOf(b.code);
      if (ia !== ib) return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
      return a.sort_order - b.sort_order;
    });

  async function lcRun(id: number, fn: () => Promise<unknown>, okMsg: string) {
    setLcBusyId(id);
    setLcErr(null);
    setLcOk(null);
    try {
      await fn();
      await loadLineComps();
      setLcTouched(true);
      setLcOk(okMsg);
    } catch (e) {
      setLcErr(errText(e));
    } finally {
      setLcBusyId(null);
    }
  }

  async function addLineComp() {
    if (!lcAdd) return;
    if (!lcAdd.component_id) {
      setLcErr("Chọn khoản trong danh mục trước.");
      return;
    }
    if (lcAdd.amount <= 0) {
      setLcErr("Nhập số tiền của khoản phát sinh.");
      return;
    }
    setLcAddBusy(true);
    setLcErr(null);
    setLcOk(null);
    try {
      await api.luong.addLineComponent(token, line.id, {
        component_id: lcAdd.component_id,
        amount: lcAdd.amount,
        note: lcAdd.note.trim() || null,
      });
      setLcAdd(null);
      await loadLineComps();
      setLcTouched(true);
      setLcOk("Đã thêm khoản phát sinh cho kỳ này.");
    } catch (e) {
      setLcErr(errText(e));
    } finally {
      setLcAddBusy(false);
    }
  }

  async function save() {
    setBusy(true);
    setErr(null);
    try {
      // TNCN LUÔN tự tính theo Biểu thuế lũy tiến — KHÔNG gửi `pit`; ép `pit_manual:false`
      // để backend tính lại TNCN theo thu nhập chịu thuế mới (không cho sửa tay).
      const { di_tre, ...restDetail } = detail;
      const input = {
        vi_pham: viPham,
        pit_manual: false,
        note: note || null,
        ...restDetail,
        // Đi trễ: chỉ gửi số TAY khi HCNS chủ động sửa (khóa auto); bỏ về tự động → gửi cờ false
        // (backend tính lại từ chấm công). Auto không đổi → không gửi gì, giữ nguyên số auto.
        ...(diTreManual
          ? { di_tre }
          : line.di_tre_manual
            ? { di_tre_manual: false }
            : {}),
      };
      await api.luong.updateLine(token, line.id, input);
      onSaved();
    } catch (e) {
      setErr(errText(e));
      setBusy(false);
    }
  }
  // "Đi trễ" render RIÊNG (auto/sửa tay); các ô phạt còn lại nhập tay bình thường.
  const penaltyFields: [keyof typeof detail, string][] = [
    ["dt_vuot_troi", "Điện thoại vượt trội"],
    ["phat_bien_ban", "Phạt biên bản"],
    ["phat_5s_dong_phuc", "Đồng phục / phạt 5S"],
  ];
  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box ns-modal__box--wide">
        <header className="ns-modal__head">
          <h2>Sửa lương — {line.employee_name}</h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}
          <p className="cc-note">
            Lương công {money(line.luong_cong)} · chuyên cần{" "}
            {money(line.chuyen_can)} · phụ cấp {money(line.allowance)} · thu
            nhập tính thuế {money(line.pit_taxable)} → Thuế TNCN{" "}
            <b>{money(line.pit)}đ</b> (tự tính theo biểu thuế lũy tiến, không
            sửa).
          </p>
          <div className="ns-grid" style={{ marginTop: 12 }}>
            <label className="ns-field">
              <span className="ns-field__label">Giảm trừ khác (trừ)</span>
              <input
                type="number"
                min={0}
                value={viPham}
                onChange={(e) => setViPham(Number(e.target.value))}
              />
            </label>
          </div>
          {legacyBonus.length > 0 && (
            <>
              <h4 className="ns-section__title" style={{ marginTop: 14 }}>
                Khoản kỳ cũ{" "}
                <span className="ns-badge ns-badge--muted">chỉ đọc</span>
              </h4>
              <p className="cc-note">
                Các ô thưởng nhập tay đã ngừng dùng từ 28/07/2026 — nay khai ở{" "}
                <b>Khoản phát sinh tháng này</b> để chọn được chịu thuế hay miễn
                thuế. Số dưới đây là của kỳ cũ, <b>vẫn được trả</b> và giữ
                nguyên để phiếu lương đã ký không đổi.
              </p>
              <div className="lg-legacy">
                {legacyBonus.map(([lbl, v]) => (
                  <div className="lg-legacy__row" key={lbl}>
                    <span>{lbl}</span>
                    <b>{money(v)}đ</b>
                  </div>
                ))}
              </div>
            </>
          )}
          <h4 className="ns-section__title" style={{ marginTop: 12 }}>
            Các khoản giảm trừ (phạt)
          </h4>
          <div className="ns-grid">
            <label className="ns-field">
              <span className="ns-field__label">
                Đi trễ / nghỉ KP{" "}
                <span
                  className={`ns-badge ${diTreManual ? "ns-badge--muted" : "ns-badge--ok"}`}
                >
                  {diTreManual ? "đã sửa tay" : "tự động"}
                </span>
              </span>
              <input
                type="number"
                min={0}
                value={detail.di_tre}
                readOnly={!diTreManual}
                onChange={(e) => setD("di_tre", Number(e.target.value))}
              />
              <span className="cc-card__hint">
                {diTreManual ? (
                  <>
                    Đang dùng số nhập tay.{" "}
                    <button
                      type="button"
                      className="lg-linkbtn"
                      onClick={() => setDiTreManual(false)}
                    >
                      ↩ Về tự động từ chấm công
                    </button>
                  </>
                ) : (
                  <>
                    Tự tính từ chấm công (bảng phạt × số phút trễ/về sớm KHÔNG
                    phép mỗi ngày).{" "}
                    <button
                      type="button"
                      className="lg-linkbtn"
                      onClick={() => setDiTreManual(true)}
                    >
                      ✎ Sửa tay
                    </button>
                  </>
                )}
              </span>
            </label>
            {penaltyFields.map(([k, lbl]) => (
              <label className="ns-field" key={k}>
                <span className="ns-field__label">{lbl}</span>
                <input
                  type="number"
                  min={0}
                  value={detail[k]}
                  onChange={(e) => setD(k, Number(e.target.value))}
                />
              </label>
            ))}
          </div>
          {/* TẦNG 3 — khoản chỉ có ở KỲ NÀY. Khoản gán ở hồ sơ được trả LẶP LẠI mọi tháng
              (quên gỡ là trả mãi); khoản ở đây không lặp. Mỗi thao tác lưu NGAY. */}
          <h4 className="ns-section__title" style={{ marginTop: 14 }}>
            Khoản phát sinh tháng này
          </h4>
          <p className="cc-note">
            Khoản ở đây <b>chỉ có ở kỳ này, không lặp sang tháng sau</b> — đúng
            chỗ để khai thưởng nóng. Khoản trả đều hằng tháng thì gán ở{" "}
            <b>Lương → Lương nhân viên → Sửa lương</b>. Thao tác ở khối này{" "}
            <b>lưu ngay</b>, không chờ nút “Lưu” bên dưới.
          </p>
          {lcErr && <div className="banner banner--error">{lcErr}</div>}
          {lcOk && <div className="banner banner--success">{lcOk}</div>}
          <div className="lg-lc">
            <div className="lg-lc__head">
              <span>Khoản</span>
              <span>Thuế TNCN</span>
              <span>Số tiền</span>
              <span>Ghi chú</span>
              <span />
            </div>
            {lcRows === null ? (
              <div className="lg-lc__empty">
                {lcErr ? (
                  <button
                    type="button"
                    className="lg-linkbtn"
                    onClick={() => void loadLineComps()}
                  >
                    Thử tải lại
                  </button>
                ) : (
                  "Đang tải khoản của dòng lương…"
                )}
              </div>
            ) : lcRows.length === 0 ? (
              <div className="lg-lc__empty">
                Kỳ này chưa có khoản nào ngoài các ô lương ở trên.
              </div>
            ) : (
              lcRows.map((r) => {
                const fromEmp = r.source === "employee";
                // HỆ TỰ TÍNH (hoa hồng KD): CHỈ ĐỌC. Backend chặn sửa/gỡ, nên để ô nhập ở đây là
                // mời người ta bấm vào một cái báo lỗi; mà có sửa được thì "Tính lại" cũng ghi đè.
                const tuDong = r.source === "auto";
                // Dòng chép từ hồ sơ nhưng HCNS đã sửa số CHO RIÊNG KỲ NÀY (12/08/2026).
                // "Tính lại" chừa nó ra, và hồ sơ nhân viên không đổi.
                const daDe = Boolean(r.da_de_tay);
                const d = lcDraft[r.id] ?? {
                  amount: r.amount,
                  note: r.note ?? "",
                };
                const dirty =
                  d.amount !== r.amount || (d.note.trim() || null) !== r.note;
                const rowBusy = lcBusyId === r.id;
                return (
                  <div
                    key={r.id}
                    className={`lg-lc__row${fromEmp ? " lg-lc__row--emp" : ""}`}
                  >
                    <div className="lg-lc__name">
                      {r.name}
                      {fromEmp && (
                        <span
                          className={`ns-badge ${daDe ? "ns-badge--info" : "ns-badge--muted"}`}
                          style={{ marginLeft: 6 }}
                        >
                          {daDe ? "Đã sửa cho kỳ này" : "Từ hồ sơ"}
                        </span>
                      )}
                      {tuDong && (
                        <span className="ns-badge ns-badge--muted" style={{ marginLeft: 6 }}>
                          Hệ tự tính
                        </span>
                      )}
                      {tuDong && (
                        <span className="lg-lc__src">
                          theo hoá đơn bán trong kỳ · % lấy từ hồ sơ lương lúc chốt đơn
                        </span>
                      )}
                      {fromEmp && (
                        <span className="lg-lc__src">
                          {daDe
                            ? "hồ sơ giữ nguyên — tháng sau tự về mức cũ"
                            : "mức theo hồ sơ; sửa ở đây chỉ đổi riêng kỳ này"}
                        </span>
                      )}
                    </div>
                    <div>
                      <span
                        className={`ns-badge ${r.is_taxable ? "ns-badge--info" : "ns-badge--ok"}`}
                      >
                        {r.is_taxable ? "Chịu thuế" : "Miễn thuế"}
                      </span>
                    </div>
                    <div className="lg-lc__money">
                      {/* Dòng "Từ hồ sơ" NAY SỬA ĐƯỢC (chủ chốt 12/08/2026): "tháng này nó đi
                          nhiều hơn thì sửa thế nào". Sửa ở hồ sơ là đổi cho MỌI tháng sau và phải
                          nhớ sửa ngược — quên một lần là trả sai mãi.
                          Dòng "Hệ tự tính" (hoa hồng) thì KHÔNG: chủ chốt 24/08/2026 "kệ nó ăn
                          theo đơn hàng cho chắc". Đè tay là kỳ đó thôi chạy theo hoá đơn, kế toán
                          xuất thêm hoá đơn sau cũng không cộng — mà không ai nhớ ra để sửa lại. */}
                      {readOnly || tuDong ? (
                        <span className="lg-lc__ro">{money(r.amount)}</span>
                      ) : (
                        <input
                          type="number"
                          min={0}
                          step={50000}
                          aria-label={`Số tiền khoản ${r.name}`}
                          value={d.amount}
                          disabled={rowBusy}
                          onChange={(e) =>
                            setLcDraft((s) => ({
                              ...s,
                              [r.id]: { ...d, amount: Number(e.target.value) },
                            }))
                          }
                        />
                      )}
                    </div>
                    <div className="lg-lc__note">
                      {fromEmp || readOnly || tuDong ? (
                        <span className="lg-lc__ro">{r.note || "—"}</span>
                      ) : (
                        <input
                          type="text"
                          maxLength={255}
                          placeholder="vd: Thưởng nóng của Sếp"
                          aria-label={`Ghi chú khoản ${r.name}`}
                          value={d.note}
                          disabled={rowBusy}
                          onChange={(e) =>
                            setLcDraft((s) => ({
                              ...s,
                              [r.id]: { ...d, note: e.target.value },
                            }))
                          }
                        />
                      )}
                    </div>
                    <div className="lg-lc__act">
                      {fromEmp && !readOnly && (
                        <>
                          {d.amount !== r.amount && (
                            <button
                              type="button"
                              className="btn btn--ghost"
                              disabled={rowBusy}
                              onClick={() =>
                                void lcRun(
                                  r.id,
                                  () =>
                                    api.luong.updateLineComponent(token, r.id, {
                                      amount: d.amount,
                                    }),
                                  `Đã sửa “${r.name}” cho riêng kỳ này.`,
                                )
                              }
                            >
                              Lưu
                            </button>
                          )}
                          {daDe && d.amount === r.amount && (
                            <button
                              type="button"
                              className="btn btn--ghost"
                              disabled={rowBusy}
                              onClick={() =>
                                void lcRun(
                                  r.id,
                                  () => api.luong.boDeComponent(token, r.id),
                                  `Đã trả “${r.name}” về mức hồ sơ.`,
                                )
                              }
                            >
                              Trả về theo hồ sơ
                            </button>
                          )}
                        </>
                      )}
                      {/* Hệ tự tính: KHÔNG nút nào. Sửa thì máy chủ chặn, xoá thì "Tính lại" mọc
                          lại — bày nút ra chỉ để mời người ta bấm vào một cái báo lỗi. */}
                      {!fromEmp && !readOnly && !tuDong && (
                        <>
                          {dirty && (
                            <button
                              type="button"
                              className="btn btn--ghost"
                              disabled={rowBusy}
                              onClick={() =>
                                void lcRun(
                                  r.id,
                                  () =>
                                    api.luong.updateLineComponent(token, r.id, {
                                      amount: d.amount,
                                      note: d.note.trim() || null,
                                    }),
                                  `Đã lưu khoản “${r.name}”.`,
                                )
                              }
                            >
                              Lưu
                            </button>
                          )}
                          <button
                            type="button"
                            className="btn btn--ghost"
                            disabled={rowBusy}
                            onClick={() =>
                              void lcRun(
                                r.id,
                                () =>
                                  api.luong.deleteLineComponent(token, r.id),
                                `Đã xoá khoản “${r.name}” khỏi kỳ này.`,
                              )
                            }
                          >
                            Xoá
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {readOnly ? (
            <p className="cc-card__hint">
              Kỳ lương đã chốt / đã chi — khối này chỉ để xem.
            </p>
          ) : lcAdd ? (
            <div className="lg-lc__add">
              <select
                className="lg-lc__pick"
                autoFocus
                aria-label="Chọn khoản phát sinh"
                value={lcAdd.component_id || ""}
                onChange={(e) =>
                  setLcAdd({ ...lcAdd, component_id: Number(e.target.value) })
                }
              >
                <option value="">— chọn khoản trong danh mục —</option>
                {lcAddable.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} · {c.is_taxable ? "chịu thuế" : "miễn thuế"}
                    {c.kind === "tru" ? " · khấu trừ" : ""}
                  </option>
                ))}
                <option value="" disabled>
                  Không thấy khoản cần dùng? Tạo ở Cấu hình lương → Danh mục
                  khoản thu nhập.
                </option>
              </select>
              <input
                type="number"
                min={0}
                step={50000}
                placeholder="Số tiền"
                aria-label="Số tiền khoản phát sinh"
                value={lcAdd.amount || ""}
                onChange={(e) =>
                  setLcAdd({ ...lcAdd, amount: Number(e.target.value) })
                }
              />
              <input
                type="text"
                maxLength={255}
                placeholder="vd: Thưởng nóng của Sếp"
                aria-label="Ghi chú khoản phát sinh"
                value={lcAdd.note}
                onChange={(e) => setLcAdd({ ...lcAdd, note: e.target.value })}
              />
              <button
                type="button"
                className="btn btn--primary"
                disabled={lcAddBusy}
                onClick={() => void addLineComp()}
              >
                {lcAddBusy ? "Đang thêm…" : "Thêm"}
              </button>
              <button
                type="button"
                className="btn btn--ghost"
                disabled={lcAddBusy}
                onClick={() => setLcAdd(null)}
              >
                Hủy
              </button>
            </div>
          ) : (
            <div className="lg-lc__add">
              <button
                type="button"
                className="btn btn--ghost"
                disabled={lcCatalog === null}
                onClick={() => {
                  setLcErr(null);
                  setLcAdd({ component_id: 0, amount: 0, note: "" });
                }}
              >
                + Thêm khoản phát sinh
              </button>
              {lcCatalog === null && (
                <span className="cc-card__hint">
                  {lcCatalogErr
                    ? `Không đọc được danh mục khoản thu nhập (${lcCatalogErr}) — chưa thêm khoản phát sinh được.`
                    : "Đang tải danh mục khoản thu nhập…"}
                </span>
              )}
            </div>
          )}
          {lcTouched && (
            <p className="cc-card__hint">
              Đã tính lại dòng lương này. Các số tổng ở đầu màn (phụ cấp · thu
              nhập tính thuế · TNCN) cập nhật sau khi đóng màn.
            </p>
          )}

          <label className="ns-field" style={{ marginTop: 12 }}>
            <span className="ns-field__label">Ghi chú</span>
            <input value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Hủy
          </button>
          <button className="btn btn--primary" onClick={save} disabled={busy}>
            {busy ? "Đang lưu…" : "Lưu"}
          </button>
        </footer>
      </div>
    </div>
  );
}
