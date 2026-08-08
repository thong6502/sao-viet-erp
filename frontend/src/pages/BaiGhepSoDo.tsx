// Sơ đồ BÀI GHÉP — routing ĐẦY ĐỦ của từng lệnh + các bước NGƯỜI khai là chạy chung.
// Không có node "in chung tờ" nào tự mọc ra: ghép bài chung cả CTP/cán/bế chứ không riêng bước in,
// nên chọn bước nào là việc của người lập kế hoạch.
import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  BAI_GHEP_MUC_META,
  api,
  type BaiGhepBuocChungBody,
  type BaiGhepDetail,
  type BaiGhepSoDo as SoDo,
  type HangChoGhepItem,
} from "../api/client";
import { crud } from "../api/rebuildCatalog";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { BaiGhepDagCanvas } from "../components/BaiGhepDagCanvas";
import { BangLoi, ChipGap, Skeleton, ngay, num } from "./keHoachSxShared";
import { nhanDonVi, phut } from "./lsxBuoc";

export interface Form {
  giay_id: number | null;
  kho_in_dai: number | null;
  kho_in_rong: number | null;
  // `null` = CHƯA KHAI → bài lấy số máy đề xuất. `0` = khai "chạy đúng số, không bù".
  // Hai ý này từng chung một giá trị 0 nên không có cách nào bảo bài đừng cộng hao.
  hao_hut_setup: number | null;
  hao_hut_chay: number | null;
  ghi_chu: string;
}

const QUY_CACH_IN_LABEL: Record<string, string> = {
  mot_mat: "1 mặt",
  "hai_mat(AB)": "2 mặt (AB)",
  tu_tro: "trở tự",
  tro_nhip: "trở nhíp",
};
const nhanCompat = (v: string | null) => (v == null ? "—" : QUY_CACH_IN_LABEL[v] ?? v);

/** Màu nhánh — mỗi lệnh một màu để ba đơn hàng nằm cạnh nhau không lẫn. */
const MAU_NHANH = ["#c25e38", "#2563eb", "#059669", "#7c5cbf", "#b7791f", "#be185d"];

export function BaiGhepSoDo({
  baiGhepId,
  tick,
  canUpdate,
  detail,
  form,
  setForm,
  giayOptions,
  onMoLenh,
  onSuaThanhVien,
  onBoThanhVien,
  onThemThanhVien,
  onSuaThongSoTo,
  dirtyThongSoTo,
  dangLuuThongSoTo,
  onGop,
  onTach,
  onLuuBuocChung,
  onHoiUngVien,
}: {
  baiGhepId: number;
  tick: number;
  canUpdate: boolean;
  detail: BaiGhepDetail;
  form: Form;
  setForm: (f: Form) => void;
  giayOptions: [number, string | null][];
  onMoLenh: (lsxId: number) => void;
  onSuaThanhVien: (tvId: number, soCon: number) => void;
  onBoThanhVien: (tvId: number) => void;
  onThemThanhVien: (lsxIds: number[]) => void;
  /** CỬA GHI DUY NHẤT của thông số tờ: sơ đồ không tự gọi API, đẩy lên cha (xem
   *  `test_so_do_bai_ghep_nhanh_chi_doc_va_mot_cua_ghi_thong_so_to`). */
  onSuaThongSoTo?: () => void;
  dirtyThongSoTo?: boolean;
  dangLuuThongSoTo?: boolean;
  /** Gộp / tách / lập kế hoạch lượt chung — cũng đẩy lên cha, không tự gọi API ghi. */
  onGop?: (stepKeys: string[]) => Promise<unknown>;
  onTach?: (gangStepKey: string) => Promise<unknown>;
  onLuuBuocChung?: (gangStepKey: string, body: BaiGhepBuocChungBody) => Promise<unknown>;
  onHoiUngVien?: (
    stepKeys: string[],
  ) => Promise<Record<string, { gop_duoc: boolean; ly_do: string | null }>>;
}) {
  const { token } = useAuth();
  const [sd, setSd] = useState<SoDo | null>(null);
  const [err, setErr] = useState<string | null>(null);
  /** Đang mở gì trong popup: cấu hình bài · một lệnh · một lượt chạy chung. */
  const [chon, setChon] = useState<
    { loai: "bai" } | { loai: "lsx"; id: number } | { loai: "gop"; key: string } | null
  >({ loai: "bai" });
  const [showTuongThich, setShowTuongThich] = useState(false);

  const load = useCallback(() => {
    if (!token) return;
    setErr(null);
    api.baiGhep
      .soDo(token, baiGhepId)
      .then(setSd)
      .catch((e: unknown) => setErr(e instanceof ApiError ? e.message : String(e)));
  }, [token, baiGhepId]);

  useEffect(() => load(), [load, tick]);

  if (err) return <BangLoi text={err} onRetry={load} />;
  if (!sd) return <Skeleton />;

  const nhanhChon = chon?.loai === "lsx" ? sd.nhanh.find((n) => n.lsx_id === chon.id) : null;
  const gopChon = chon?.loai === "gop" ? sd.gop.find((g) => g.step_key === chon.key) : null;

  // Chip tương thích lấy mức XẤU NHẤT từ chính dữ liệu. Trước đây icon/màu tô cứng xanh nên bài
  // ghép có dòng "không phù hợp" vẫn hiện dấu tích xanh — báo an toàn cho một bài đang lỗi.
  // Lưu ý `muc` (phu_hop/can_xac_nhan/khong_phu_hop) KHÁC `tone` trong BAI_GHEP_MUC_META.
  // Hao của bài: chưa khai ô nào (cả hai `null`) thì bài đang chạy bằng số MÁY ĐỀ XUẤT. Phải nói
  // ra, không thì hai ô trống trông như "không bù hao" trong khi số tờ cấp vẫn đang cộng hao.
  const hao = {
    deXuat: form.hao_hut_setup == null && form.hao_hut_chay == null,
    setup: detail.so_to.hao_setup_de_xuat,
    chay: detail.so_to.hao_chay_de_xuat,
  };

  const compatRows = detail.tuong_thich.rows;
  const compatDat = compatRows.filter((r) => r.muc === "phu_hop").length;
  const compatTone = compatRows.some((r) => r.muc === "khong_phu_hop")
    ? "bad"
    : compatRows.some((r) => r.muc === "can_xac_nhan")
      ? "warn"
      : "ok";

  return (
    <section className="khsx-panel bgsd bgsd-canvas-container">
      <div className="bgsd-canvas-wrapper">
        <div className="bgsd-canvas-top-bar">
          <p className="bghep-hint" style={{ margin: 0 }}>
            {sd.bai_ghep.so_buoc_chung > 0 ? (
              <>
                <strong>{sd.bai_ghep.so_buoc_chung} bước</strong> đang chạy chung. Bấm một bước để
                gộp thêm, nháy đúp thẻ chung để lập kế hoạch cho lượt đó.
              </>
            ) : (
              <>
                Đây là routing đầy đủ của từng lệnh — chưa có gì chạy chung.{" "}
                <strong>Bấm một bước</strong> rồi bấm bước cùng công đoạn ở lệnh khác để gộp.
              </>
            )}
          </p>

          <button
            type="button"
            className="bgsd-btn-floating-inspector"
            onClick={() => setChon({ loai: "bai" })}
            title="Mở bảng Thông số tờ chạy chung & Nhập liệu Bài ghép"
          >
            <Icon name="layers" size={15} />
            <span>Thông số tờ & Nhập liệu</span>
            {detail.thanh_vien.length > 0 && (
              <span className="bgsd-floating-badge">{detail.thanh_vien.length} lệnh</span>
            )}
          </button>
        </div>

        {sd.nhanh.length === 0 ? (
          <div className="khsx-empty khsx-empty--inline">
            <Icon name="layers" size={28} />
            <p className="khsx-empty__title">Bài chưa có lệnh nào.</p>
            <p className="khsx-empty__sub">
              Bấm nút "Thông số tờ & Nhập liệu" ở góc trên để thêm lệnh vào bài ghép.
            </p>
          </div>
        ) : (
          <BaiGhepDagCanvas
            sd={sd}
            chon={chon?.loai === "lsx" ? chon.id : chon?.loai === "gop" ? chon.key : null}
            onChon={(val) =>
              setChon(typeof val === "number" ? { loai: "lsx", id: val } : { loai: "gop", key: val })
            }
            onMoLenh={onMoLenh}
            canUpdate={canUpdate}
            onGop={onGop}
            onTach={onTach}
            onHoiUngVien={onHoiUngVien}
            onMoBuocChung={(key) => setChon({ loai: "gop", key })}
            // `con/tờ` sửa TẠI CHỖ trên thẻ lệnh — nó là số người dùng chỉnh nhiều nhất khi cân
            // bài; bắt mở modal mỗi lần đổi một con số là thừa một vòng thao tác. Vẫn ĐẨY LÊN CHA
            // chứ sơ đồ không tự gọi API ghi.
            onSuaCon={onSuaThanhVien}
          />
        )}
      </div>

      {/* Modal Popup (Trọn gói Nhập liệu & Quản lý Bài ghép) */}
      {chon !== null && (
        <div className="bgsd-modal-overlay" onClick={() => setChon(null)}>
          <div
            className="bgsd-modal-dialog"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
          >
            <div className="bgsd-modal-head">
              <span className="bgsd-modal-title">
                <span className="bgsd-modal-icon-badge">
                  <Icon
                    name={chon.loai === "bai" ? "layers" : chon.loai === "gop" ? "link" : "fileText"}
                    size={16}
                  />
                </span>
                {chon.loai === "bai"
                  ? "Thông số tờ & Nhập liệu Bài ghép"
                  : chon.loai === "gop"
                    ? `Bước chung của bài ${sd.bai_ghep.ma} · áp cho ${gopChon?.thanh_vien.length ?? 0} lệnh`
                    : `Chi tiết Lệnh ${nhanhChon?.lsx_ma}`}
                {chon.loai === "bai" && dirtyThongSoTo && (
                  <span className="khsx-pill khsx-pill--warn" style={{ fontSize: "11px", marginLeft: "4px" }}>
                    Chưa lưu
                  </span>
                )}
              </span>
              <button
                type="button"
                className="bgsd-modal-close"
                onClick={() => setChon(null)}
                title="Đóng popup (Esc)"
              >
                <Icon name="x" size={16} />
              </button>
            </div>

            <div className="bgsd-modal-body">
              {chon.loai === "bai" ? (
                <div className="bgsd-modal-content-grid">
                  {/* 1. Cấu hình Giấy, Khổ in & Hao hụt (Grid 4 cột) */}
                  <div className="bgsd-sec bgsd-sec--featured">
                    <div className="bgsd-sec__head">
                      <Icon name="settings" size={16} style={{ color: "#0284c7" }} />
                      <span>Cấu hình Giấy, Khổ in & Hao hụt</span>
                    </div>
                    <div className="bgsd-form-grid-4">
                      <label className="khsx-field bgsd-field-wide">
                        <span>Giấy chạy chung</span>
                        <select
                          value={form.giay_id ?? ""}
                          disabled={!canUpdate}
                          onChange={(e) =>
                            setForm({
                              ...form,
                              giay_id: e.target.value ? Number(e.target.value) : null,
                            })
                          }
                        >
                          <option value="">— chọn giấy —</option>
                          {giayOptions.map(([id, ten]) => (
                            <option key={id} value={id}>
                              {ten || `Giấy #${id}`}
                            </option>
                          ))}
                        </select>
                      </label>

                      <label className="khsx-field">
                        <span>Khổ dài (mm)</span>
                        <input
                          type="number"
                          min={0}
                          disabled={!canUpdate}
                          value={form.kho_in_dai ?? ""}
                          placeholder="860"
                          onChange={(e) =>
                            setForm({
                              ...form,
                              kho_in_dai: e.target.value ? Number(e.target.value) : null,
                            })
                          }
                        />
                      </label>

                      <label className="khsx-field">
                        <span>Khổ rộng (mm)</span>
                        <input
                          type="number"
                          min={0}
                          disabled={!canUpdate}
                          value={form.kho_in_rong ?? ""}
                          placeholder="650"
                          onChange={(e) =>
                            setForm({
                              ...form,
                              kho_in_rong: e.target.value ? Number(e.target.value) : null,
                            })
                          }
                        />
                      </label>

                      {/* ĐỂ TRỐNG ≠ GÕ 0. Trống = chưa khai, bài tự lấy hao máy đề xuất. Gõ 0 =
                          "chạy đúng số, không bù" và bài tôn trọng đúng số đó. */}
                      <label className="khsx-field bgsd-field-half">
                        <span>Hao setup (tờ)</span>
                        <input
                          type="number"
                          min={0}
                          disabled={!canUpdate}
                          value={form.hao_hut_setup ?? ""}
                          placeholder={hao.deXuat ? `${hao.setup}` : "theo máy"}
                          title="Để trống = dùng hao máy đề xuất. Gõ 0 = chạy đúng số, không bù."
                          onChange={(e) =>
                            setForm({
                              ...form,
                              hao_hut_setup: e.target.value === "" ? null : Number(e.target.value),
                            })
                          }
                        />
                      </label>

                      <label className="khsx-field bgsd-field-half">
                        <span>Hao chạy (tờ)</span>
                        <input
                          type="number"
                          min={0}
                          disabled={!canUpdate}
                          value={form.hao_hut_chay ?? ""}
                          placeholder={hao.deXuat ? `${hao.chay}` : "theo máy"}
                          title="Để trống = dùng hao máy đề xuất. Gõ 0 = chạy đúng số, không bù."
                          onChange={(e) =>
                            setForm({
                              ...form,
                              hao_hut_chay: e.target.value === "" ? null : Number(e.target.value),
                            })
                          }
                        />
                      </label>
                    </div>
                    {hao.deXuat && (
                      <p className="bgsd-hint">
                        Đang dùng hao máy đề xuất <b>{num(hao.setup + hao.chay)} tờ</b> (canh máy{" "}
                        {num(hao.setup)} · chạy {num(hao.chay)}). Gõ số để đè, gõ <b>0</b> để chạy
                        đúng số không bù.
                      </p>
                    )}
                  </div>

                  {/* 2. Quản lý Thành viên & Số con/tờ */}
                  <div className="bgsd-sec">
                    <div className="bgsd-sec__head" style={{ justifyContent: "space-between" }}>
                      <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                        <Icon name="users" size={16} style={{ color: "#0284c7" }} />
                        <span>Thành viên & Phân bổ con/tờ ({detail.thanh_vien.length})</span>
                      </span>
                    </div>

                    <div className="khsx__tablewrap bgsd-modal-tablewrap">
                      <table className="khsx__table bgsd-modal-table">
                        <thead>
                          <tr>
                            <th>Mã LSX & Đơn hàng</th>
                            <th className="khsx-num" style={{ width: "120px" }}>Con / tờ</th>
                            <th className="khsx-num">Nhu cầu tờ</th>
                            {/* Hai loại dư KHÁC NHAU: dư TỜ sinh ngay tại điểm toả, dư THÀNH PHẨM
                                là cuối chuỗi (đã trừ hao mọi bước riêng). Gộp một cột là nói sai. */}
                            <th className="khsx-num">Dư tờ (tại điểm toả)</th>
                            <th className="khsx-num">Dư thành phẩm</th>
                            <th aria-label="Hành động" style={{ width: "60px" }} />
                          </tr>
                        </thead>
                        <tbody>
                          {detail.thanh_vien.map((t) => (
                            <tr key={t.thanh_vien_id} className="khsx__row">
                              <td>
                                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                                  <span className="khsx__code">{t.lsx_ma}</span>
                                  {t.is_rush && <ChipGap />}
                                </div>
                              </td>
                              <td className="khsx-num">
                                <div className="bgsd-ups-stepper">
                                  <button
                                    type="button"
                                    className="bgsd-ups-btn"
                                    disabled={!canUpdate || t.so_con_tren_to <= 0}
                                    onClick={() =>
                                      onSuaThanhVien(t.thanh_vien_id, Math.max(0, t.so_con_tren_to - 1))
                                    }
                                    title="Giảm số con"
                                  >
                                    -
                                  </button>
                                  <input
                                    type="number"
                                    min={0}
                                    className="bghep-ups bgsd-ups-input"
                                    value={t.so_con_tren_to}
                                    disabled={!canUpdate}
                                    onChange={(e) => {
                                      const v = Number(e.target.value);
                                      onSuaThanhVien(t.thanh_vien_id, v);
                                    }}
                                    aria-label={`Số con trên tờ của ${t.lsx_ma}`}
                                  />
                                  <button
                                    type="button"
                                    className="bgsd-ups-btn"
                                    disabled={!canUpdate}
                                    onClick={() =>
                                      onSuaThanhVien(t.thanh_vien_id, t.so_con_tren_to + 1)
                                    }
                                    title="Tăng số con"
                                  >
                                    +
                                  </button>
                                </div>
                                {/* D3: gợi ý con/tờ — tối đa theo khổ (ước lượng) + gợi ý cân sản
                                    lượng (bấm để áp). Con/tờ vẫn do người bình bài quyết. */}
                                {(t.con_toi_da > 0 || t.con_goi_y > 0) && (
                                  <div className="bgsd-ups-hint">
                                    {t.con_toi_da > 0 && <span>tối đa ~{num(t.con_toi_da)}</span>}
                                    {t.con_goi_y > 0 && t.con_goi_y !== t.so_con_tren_to && (
                                      <>
                                        {t.con_toi_da > 0 && " · "}
                                        {canUpdate ? (
                                          <button
                                            type="button"
                                            className="bgsd-ups-goiy"
                                            onClick={() => onSuaThanhVien(t.thanh_vien_id, t.con_goi_y)}
                                            title="Áp số gợi ý để cân sản lượng giữa các lệnh"
                                          >
                                            gợi ý {num(t.con_goi_y)}
                                          </button>
                                        ) : (
                                          <span>gợi ý {num(t.con_goi_y)}</span>
                                        )}
                                      </>
                                    )}
                                  </div>
                                )}
                              </td>
                              <td className="khsx-num">{num(t.nhu_cau_to)}</td>
                              <td className="khsx-num">
                                {!t.toa_step_key ? (
                                  <span className="khsx-muted" title="Lệnh chưa gộp bước nào — chưa chung tờ với bài">
                                    chạy riêng
                                  </span>
                                ) : t.du_to > 0 ? (
                                  <span className="bgsd-chip-surplus">+{num(t.du_to)} tờ</span>
                                ) : (
                                  <span className="khsx-muted">đủ tờ</span>
                                )}
                              </td>
                              <td className="khsx-num">
                                {/* D3: cờ DƯ LỚN — ghép lệch sản lượng (dư > 30% so với SL đặt). */}
                                {t.du > 0 ? (
                                  t.so_luong_dat > 0 && t.du / t.so_luong_dat > 0.3 ? (
                                    <span
                                      className="bgsd-chip-surplus bgsd-chip-surplus--warn"
                                      title="Ghép lệch sản lượng — lệnh này dư nhiều; cân lại con/tờ để giảm dư"
                                    >
                                      +{num(t.du)} ⚠
                                    </span>
                                  ) : (
                                    <span className="bgsd-chip-surplus">+{num(t.du)}</span>
                                  )
                                ) : (
                                  num(t.du)
                                )}
                              </td>
                              <td>
                                {canUpdate && (
                                  <button
                                    type="button"
                                    className="khsx-xlink"
                                    style={{ color: "var(--signal)" }}
                                    onClick={() => onBoThanhVien(t.thanh_vien_id)}
                                    title="Bỏ khỏi bài ghép"
                                  >
                                    Bỏ
                                  </button>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    {canUpdate && (
                      <div style={{ marginTop: "12px" }}>
                        <ThemPicker
                          exclude={new Set(detail.thanh_vien.map((t) => t.lsx_id))}
                          onThem={onThemThanhVien}
                        />
                      </div>
                    )}
                  </div>

                  {/* 3. Kiểm tương thích sản xuất (Accordion) */}
                  <div className="bgsd-sec">
                    <button
                      type="button"
                      className="bgsd-accordion-btn"
                      onClick={() => setShowTuongThich(!showTuongThich)}
                    >
                      <span className="bgsd-sec__head" style={{ margin: 0 }}>
                        <Icon
                          name={compatTone === "ok" ? "check" : "alert"}
                          size={16}
                          className={`bgsd-compat-icon is-${compatTone}`}
                        />
                        <span>Kiểm tương thích sản xuất</span>
                        <span className={`bgsd-chip-compat-count is-${compatTone}`}>
                          {compatDat}/{compatRows.length} ĐẠT
                        </span>
                      </span>
                      <Icon
                        name="chevron"
                        size={15}
                        className={`bgsd-accordion-caret ${showTuongThich ? "is-open" : ""}`}
                      />
                    </button>

                    {showTuongThich && (
                      <div className="bgsd-accordion-body">
                        <table className="khsx__table bghep-compat">
                          <thead>
                            <tr>
                              <th>Thuộc tính</th>
                              {detail.thanh_vien.map((m) => (
                                <th key={m.thanh_vien_id}>{m.lsx_ma}</th>
                              ))}
                              <th>Kết quả</th>
                            </tr>
                          </thead>
                          <tbody>
                            {detail.tuong_thich.rows.map((row) => {
                              const meta = BAI_GHEP_MUC_META[row.muc] ?? {
                                label: row.muc,
                                tone: "warn",
                              };
                              return (
                                <tr key={row.thuoc_tinh} className="khsx__row">
                                  <td className="bghep-compat__attr">{row.thuoc_tinh}</td>
                                  {row.gia_tri.map((v, i) => (
                                    <td key={i}>{nhanCompat(v)}</td>
                                  ))}
                                  <td>
                                    <span className={`bghep-muc bghep-muc--${meta.tone}`}>
                                      {meta.label}
                                    </span>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>

                  {/* 4. Ghi chú Kế hoạch */}
                  <div className="bgsd-sec">
                    <div className="bgsd-sec__head">
                      <Icon name="edit" size={16} style={{ color: "#0284c7" }} />
                      <span>Ghi chú kế hoạch</span>
                    </div>
                    <textarea
                      rows={3}
                      className="khsx-textarea bgsd-notes-textarea"
                      value={form.ghi_chu}
                      disabled={!canUpdate}
                      onChange={(e) => setForm({ ...form, ghi_chu: e.target.value })}
                      placeholder="Ghi chú thêm thông tin hoặc lưu ý sản xuất cho bài ghép…"
                    />
                  </div>
                </div>
              ) : nhanhChon ? (
                <div style={{ padding: "8px 4px" }}>
                  <div className="bgsd-panel__head" style={{ marginBottom: "16px" }}>
                    <span className="bgsd__cham" style={{ background: mau(nhanhChon.mau) }} />
                    <span className="khsx__code">{nhanhChon.lsx_ma}</span>
                    <span style={{ fontSize: "14px", fontWeight: 600 }}>{nhanhChon.lsx_ten}</span>
                  </div>
                  <div style={{ marginBottom: "16px" }}>
                    <button
                      type="button"
                      className="khsx-xlink"
                      style={{ fontSize: "14px", fontWeight: 600 }}
                      onClick={() => onMoLenh(nhanhChon.lsx_id)}
                    >
                      Mở chi tiết lệnh sản xuất →
                    </button>
                  </div>
                  <div className="khsx-kvgrid" style={{ gap: "12px", gridTemplateColumns: "1fr 1fr" }}>
                    <Kv k="Khách hàng" v={nhanhChon.customer_name ?? "—"} />
                    <Kv k="Hạn hoàn thành" v={ngay(nhanhChon.han_hoan_thanh_sx) || "—"} />
                    <Kv k="Con / tờ" v={String(nhanhChon.so_con_tren_to)} />
                    <Kv k="Nhu cầu tờ" v={num(nhanhChon.nhu_cau_to)} />
                    <Kv
                      k="Routing"
                      v={`${nhanhChon.buoc.length} bước · ${phut(
                        nhanhChon.buoc.reduce((s, c) => s + c.tong_phut, 0),
                      )}`}
                    />
                    <Kv
                      k="Chạy chung"
                      v={
                        nhanhChon.toa_step_key
                          ? `${nhanhChon.buoc.filter((b) => b.gop_step_key).length} bước`
                          : "chưa gộp bước nào"
                      }
                    />
                  </div>
                </div>
              ) : gopChon ? (
                <BuocChungForm
                  key={gopChon.step_key}
                  g={gopChon}
                  canUpdate={canUpdate}
                  onLuu={(body) => onLuuBuocChung?.(gopChon.step_key, body) ?? Promise.resolve()}
                  onTach={() => onTach?.(gopChon.step_key) ?? Promise.resolve()}
                />
              ) : null}
            </div>

            <div className="bgsd-modal-footer">
              <Button variant="secondary" onClick={() => setChon(null)}>
                Đóng
              </Button>
              {/* Form thông số tờ nằm trong popup che cả trang, nên nút Lưu ở header không với tới
                  được — lặp lại lối ghi ở đây. Vẫn gọi cùng một hàm luu() của cha, không đẻ cửa ghi thứ hai. */}
              {chon.loai === "bai" && dirtyThongSoTo && (
                <Button variant="primary" loading={dangLuuThongSoTo} onClick={() => onSuaThongSoTo?.()}>
                  Lưu thông số tờ
                </Button>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

/** Lập kế hoạch cho MỘT lượt chạy chung.
 *
 * Chỉ mở những ô NGƯỜI nhập: tổ · máy · số người · năng suất · vật tư · ghi chú · (thuê ngoài).
 * Số lượng / hao / thời lượng KHÔNG có ở đây — chúng là dẫn xuất, engine tính lúc đọc; cho sửa
 * là đẻ nguồn sự thật thứ hai. Ghi chú kỹ thuật của từng lệnh hiện ở dưới, GOM chứ không đè: thợ
 * chạy chung một lượt phải đọc được yêu cầu của mọi khách trên tờ đó.
 */
function BuocChungForm({
  g,
  canUpdate,
  onLuu,
  onTach,
}: {
  g: SoDo["gop"][number];
  canUpdate: boolean;
  onLuu: (body: BaiGhepBuocChungBody) => Promise<unknown>;
  onTach: () => Promise<unknown>;
}) {
  const { token } = useAuth();
  const [toRefs, setToRefs] = useState<{ id: number; ten: string }[] | null>(null);
  const [mayRefs, setMayRefs] = useState<{ id: number; ten: string; loaiMay: string | null }[] | null>(null);
  const [vtRefs, setVtRefs] = useState<{ id: number; ma: string; ten: string; donVi: string }[] | null>(null);
  const [f, setF] = useState<BaiGhepBuocChungBody>({});
  const [dangLuu, setDangLuu] = useState(false);
  const [confirmTach, setConfirmTach] = useState(false);

  useEffect(() => {
    if (!token) return;
    crud("/api/cong-doan/phong-ban").list(token)
      .then((r) => setToRefs(r.items.map((t) => ({ id: t.id, ten: String(t.ten) }))))
      .catch(() => setToRefs(null));
    crud("/api/may-thiet-bi").list(token)
      .then((r) => setMayRefs(r.items.map((m) => ({
        id: m.id, ten: String(m.ten),
        loaiMay: (m as { loai_may?: string | null }).loai_may ?? null,
      }))))
      .catch(() => setMayRefs(null));
    crud("/api/vat-lieu-kho/vat-tu-in-an").list(token, { active: true })
      .then((r) => setVtRefs(r.items.map((v) => ({
        id: v.id, ma: String(v.ma), ten: String(v.ten), donVi: String(v.don_vi_gia ?? ""),
      }))))
      .catch(() => setVtRefs(null));
  }, [token]);

  // Đổi form về `{}` khi chuyển sang bước chung khác — không thì số vừa gõ cho bước này rơi sang
  // bước kia lúc bấm Lưu.
  useEffect(() => setF({}), [g.step_key]);

  /** Giá trị đang hiển thị: ưu tiên thứ người vừa gõ, chưa gõ thì lấy thứ server đang giữ. */
  const val = <K extends keyof BaiGhepBuocChungBody>(k: K, hienCo: BaiGhepBuocChungBody[K]) =>
    (f[k] !== undefined ? f[k] : hienCo);

  /** Đầu việc đang GHIM có thể không còn trong bảng khoán của tổ (đổi tổ, hoặc dòng bị ngừng) —
   *  vẫn phải bày ra, không thì `<select>` rơi về "— chọn —" và người dùng tưởng chưa ai chọn. */
  const dsKhoan = (() => {
    const ds = [...g.khoan_chon_duoc];
    if (g.khoan_rate_id != null && !ds.some((k) => k.id === g.khoan_rate_id)) {
      ds.unshift({
        id: g.khoan_rate_id,
        ten: g.khoan_ten ?? `(đang ghim) đầu việc #${g.khoan_rate_id}`,
        don_vi: g.khoan_don_vi ?? "",
        don_gia: g.khoan_don_gia ?? 0,
      });
    }
    return ds;
  })();

  // Vật tư sửa theo LÔ: giữ nguyên danh sách hiện có rồi thay cả cụm khi lưu (API là replace-all).
  const vtHienTai = (f.vat_tus ?? g.vat_tus.map((v) => ({ vat_tu_id: v.vat_tu_id, so_luong: v.so_luong })));
  const datVatTu = (rows: { vat_tu_id: number; so_luong: number }[]) => setF({ ...f, vat_tus: rows });

  const dirty = Object.keys(f).length > 0;
  const luu = async () => {
    setDangLuu(true);
    try {
      await onLuu(f);
      setF({});
    } finally {
      setDangLuu(false);
    }
  };

  return (
    <div className="bgsd-modal-content-grid">
      <div className="bgsd-sec bgsd-sec--featured">
        <div className="bgsd-sec__head">
          <Icon name="link" size={16} style={{ color: "#0284c7" }} />
          <span>{g.ten} — một lượt chạy cho {g.thanh_vien.length} lệnh</span>
        </div>
        <div className="bgsd-form-grid-4">
          <label className="khsx-field bgsd-field-wide">
            <span>Tổ thực hiện</span>
            {/* `value` phải là ID. Trước đây fallback bằng `g.to_ten` (chuỗi) nên không khớp
                `option value` nào → tổ đã gán vẫn hiện "— chọn tổ —". */}
            <select
              value={val("department_id", g.department_id) ?? ""}
              disabled={!canUpdate || !toRefs}
              onChange={(e) => setF({ ...f, department_id: e.target.value ? Number(e.target.value) : null })}
            >
              <option value="">— chọn tổ —</option>
              {(toRefs ?? []).map((t) => (
                <option key={t.id} value={t.id}>{t.ten}</option>
              ))}
            </select>
          </label>
          <label className="khsx-field bgsd-field-wide">
            <span>Máy chạy</span>
            <select
              value={val("may_id", g.may_id) ?? ""}
              disabled={!canUpdate || !mayRefs}
              onChange={(e) => setF({ ...f, may_id: e.target.value ? Number(e.target.value) : null })}
            >
              <option value="">— chọn máy —</option>
              {(mayRefs ?? [])
                .filter((m) => {
                  // T3: lọc máy theo NHÓM công đoạn (bước Bế chỉ thấy máy Bế). Chưa khai ràng buộc
                  // → hiện tất cả. Giữ máy ĐANG CHỌN dù sai loại, để select không rơi về trống.
                  const allow = g.nhom_may_cho_phep ?? [];
                  if (allow.length === 0) return true;
                  if (m.id === val("may_id", g.may_id)) return true;
                  return m.loaiMay != null && allow.includes(m.loaiMay);
                })
                .map((m) => (
                  <option key={m.id} value={m.id}>{m.ten}</option>
                ))}
            </select>
            {(g.nhom_may_cho_phep?.length ?? 0) > 0 && (
              <span className="bgsd-field-hint">Chỉ máy nhóm: {g.nhom_may_cho_phep.join(", ")}</span>
            )}
            {g.may_khong_hop.length > 0 && (
              <span className="bgsd-field-warn">⚠ {g.may_khong_hop.join("; ")}</span>
            )}
          </label>
          <label className="khsx-field">
            <span>Số người</span>
            <input
              type="number" min={1} disabled={!canUpdate}
              value={val("so_nhan_cong", g.so_nhan_cong) ?? ""}
              onChange={(e) => setF({ ...f, so_nhan_cong: Number(e.target.value) || 1 })}
            />
          </label>
          <label className="khsx-field">
            <span>Số lượt chạy</span>
            <input
              type="number" min={1} disabled={!canUpdate}
              title="Vd in 2 mặt trở tự = 2 lượt qua máy"
              value={val("so_luot_chay", g.so_luot_chay) ?? ""}
              onChange={(e) => setF({ ...f, so_luot_chay: Number(e.target.value) || 1 })}
            />
          </label>
        </div>

        {/* Thời lượng: NĂNG SUẤT là đường chính (máy khai tốc độ thì suy ra phút chạy); `chay_phut`
            là cửa GÕ ĐÈ và nó THẮNG công thức. Thiếu ô năng suất thì cách duy nhất tắt chip
            "Chưa có năng suất" là bấm máy tính rồi gõ tay số phút — máy đã khai tốc độ tờ/giờ rồi. */}
        <div className="bgsd-form-grid-4">
          <label className="khsx-field">
            <span>Năng suất</span>
            <input
              type="number" min={0} disabled={!canUpdate}
              placeholder={g.don_vi_nang_suat ?? "theo máy"}
              value={val("nang_suat", g.nang_suat) ?? ""}
              onChange={(e) => setF({ ...f, nang_suat: e.target.value ? Number(e.target.value) : null })}
            />
          </label>
          {/* Chạy · Canh máy · Chờ · Di chuyển ĐÃ BỎ (2026-08-04): thời lượng lượt chung nay
              suy từ MÁY đang gán bằng đúng công thức của bước lệnh —
                thời gian khác + chuẩn bị (từ máy) + SL vào × 60 ÷ tốc độ × số lượt.
              Ô duy nhất còn gõ được là "Thời gian khác". */}
          <label className="khsx-field">
            <span>Thời gian khác (phút)</span>
            <input
              type="number" min={0} disabled={!canUpdate}
              title="Phát sinh ngoài định mức — cộng thẳng vào thời gian chiếm máy"
              value={val("phat_sinh_phut", g.phat_sinh_phut) ?? ""}
              onChange={(e) => setF({ ...f, phat_sinh_phut: e.target.value ? Number(e.target.value) : 0 })}
            />
          </label>
        </div>

        <div className="khsx-tinh-gio">
          <div className="khsx-tinh-gio__row">
            <span>Chuẩn bị (từ máy) + chạy + thời gian khác</span>
            <b>{phut(g.chiem_may_phut)}</b>
          </div>
          {g.chiem_may_phut_max - g.chiem_may_phut_min > 0.5 && (
            <div className="khsx-tinh-gio__dai">
              <span>Nhanh nhất <b>{phut(g.chiem_may_phut_min)}</b></span>
              <span>Chậm nhất <b>{phut(g.chiem_may_phut_max)}</b></span>
            </div>
          )}
        </div>

        {/* Công việc khoán của LƯỢT CHUNG — cùng bảng khoán, cùng cách chọn với bước lệnh ở màn
            KHSX. Ghim theo ID; ảnh chụp đơn giá do server chụp. Đổi tổ thì danh sách đổi theo, nên
            phải LƯU rồi mở lại mới thấy danh sách mới — báo rõ thay vì để người dùng tưởng tổ mới
            không có đầu việc nào. */}
        {(g.khoan_chon_duoc.length > 0 || g.khoan_rate_id != null) && (
          <div className="khsx-field khsx-field--wide khsx-khoan-card">
            <div className="khsx-khoan-card__head">
              <span className="khsx-field__label">Công việc khoán</span>
              <span className="khsx-tag-subtle">bảng khoán của tổ</span>
            </div>
            <select
              value={val("piece_rate_id", g.khoan_rate_id) ?? ""}
              disabled={!canUpdate}
              onChange={(e) =>
                setF({ ...f, piece_rate_id: e.target.value ? Number(e.target.value) : null })
              }
            >
              <option value="">— chọn đầu việc khoán —</option>
              {dsKhoan.map((k) => (
                <option key={k.id} value={k.id}>
                  {k.don_vi ? `${k.ten} — ${num(k.don_gia)} đ/${k.don_vi}` : k.ten}
                </option>
              ))}
            </select>
            <div className="khsx-khoan-card__status">
              {f.piece_rate_id !== undefined || f.department_id !== undefined ? (
                <span className="khsx-pill-status khsx-pill-status--warn">
                  Lưu lượt chung để tính lại tiền công
                </span>
              ) : g.khoan_dien_giai ? (
                <span className="khsx-pill-status khsx-pill-status--ok">{g.khoan_dien_giai}</span>
              ) : g.khoan_ly_do ? (
                <span className="khsx-pill-status khsx-pill-status--error">{g.khoan_ly_do}</span>
              ) : g.khoan_chon_duoc.length > 1 ? (
                <span className="khsx-field__hint">
                  Tổ có {g.khoan_chon_duoc.length} đầu việc khoán — chọn đúng việc thợ làm để tự
                  động ra tiền công.
                </span>
              ) : null}
            </div>
          </div>
        )}

        {/* Số của cả lượt — CHỈ ĐỌC. Đây là chỗ hay bị hiểu nhầm nhất: hao đếm MỘT LẦN cho lượt
            chung, không phải mỗi lệnh một bộ cho cùng một lần lên máy. */}
        <div className="khsx-kvgrid" style={{ gap: "12px", gridTemplateColumns: "1fr 1fr 1fr" }}>
          {/* Đơn vị lấy theo KHAI BÁO của công đoạn — bước bế nhả `cai` thì "ra" đếm con, đóng
              đinh chữ "tờ" là nói sai ngay trên ô người dùng soi kỹ nhất. */}
          <Kv k="Vào (cả lượt)" v={`${num(g.so_luong_vao)} ${nhanDonVi(g.don_vi_vao)}`} />
          <Kv k="Ra (cả lượt)" v={`${num(g.so_luong_ra)} ${nhanDonVi(g.don_vi_ra)}`} />
          <Kv k="Hao (một lần)" v={`${num(g.hao_hut)} ${nhanDonVi(g.don_vi_vao)}`} />
        </div>
      </div>

      {/* Vật tư của CẢ LƯỢT — mực, kẽm, màng dùng chung, không của riêng lệnh nào. API là
          replace-all nên form giữ nguyên danh sách rồi gửi lại cả cụm. */}
      <div className="bgsd-sec">
        <div className="bgsd-sec__head">
          <Icon name="box" size={16} style={{ color: "#0284c7" }} />
          <span>Vật tư cho cả lượt chung</span>
        </div>
        {vtHienTai.length === 0 && <p className="khsx-nhom__sub">Chưa khai vật tư nào cho lượt này.</p>}
        {vtHienTai.map((row, i) => {
          const dm = (vtRefs ?? []).find((v) => v.id === row.vat_tu_id);
          const snap = g.vat_tus.find((v) => v.vat_tu_id === row.vat_tu_id);
          return (
            <div className="bgsd-form-grid-4" key={`${row.vat_tu_id}_${i}`}>
              <label className="khsx-field bgsd-field-wide">
                <span>Vật tư</span>
                <select
                  value={row.vat_tu_id || ""}
                  disabled={!canUpdate || !vtRefs}
                  onChange={(e) => {
                    const next = [...vtHienTai];
                    next[i] = { ...row, vat_tu_id: Number(e.target.value) };
                    datVatTu(next);
                  }}
                >
                  <option value="">— chọn vật tư —</option>
                  {(vtRefs ?? []).map((v) => (
                    <option key={v.id} value={v.id}>{v.ma} · {v.ten}</option>
                  ))}
                </select>
              </label>
              <label className="khsx-field">
                <span>Định mức{dm?.donVi || snap?.don_vi ? ` (${dm?.donVi || snap?.don_vi})` : ""}</span>
                <input
                  type="number" min={0} step="0.001" disabled={!canUpdate}
                  value={row.so_luong ?? ""}
                  onChange={(e) => {
                    const next = [...vtHienTai];
                    next[i] = { ...row, so_luong: Number(e.target.value) || 0 };
                    datVatTu(next);
                  }}
                />
              </label>
              {canUpdate && (
                <button
                  type="button" className="khsx-xlink" style={{ color: "var(--signal)", alignSelf: "end" }}
                  onClick={() => datVatTu(vtHienTai.filter((_, j) => j !== i))}
                >
                  Bỏ
                </button>
              )}
            </div>
          );
        })}
        {canUpdate && (
          <button
            type="button" className="khsx-xlink" style={{ marginTop: "6px" }}
            onClick={() => datVatTu([...vtHienTai, { vat_tu_id: 0, so_luong: 0 }])}
          >
            + Thêm vật tư
          </button>
        )}
      </div>

      {g.loai_buoc === "thue_ngoai" && (
        <div className="bgsd-sec">
          <div className="bgsd-sec__head">
            <Icon name="truck" size={16} style={{ color: "#0284c7" }} />
            {/* Bước chung nằm TRƯỚC điểm toả nên cả giao lẫn nhận đều ở tầng bài — một phiếu. */}
            <span>Gia công ngoài — cả bài đi một phiếu, một nhà cung cấp</span>
          </div>
          <div className="bgsd-form-grid-4">
            <label className="khsx-field bgsd-field-wide">
              <span>Nhà cung cấp</span>
              <input
                type="text" disabled={!canUpdate}
                value={val("nha_cung_cap", g.nha_cung_cap) ?? ""}
                placeholder="tên nhà gia công"
                onChange={(e) => setF({ ...f, nha_cung_cap: e.target.value })}
              />
            </label>
            <label className="khsx-field">
              <span>Đơn giá gia công</span>
              <input
                type="number" min={0} disabled={!canUpdate}
                value={val("don_gia_gia_cong", g.don_gia_gia_cong) ?? ""}
                onChange={(e) => setF({ ...f, don_gia_gia_cong: e.target.value ? Number(e.target.value) : null })}
              />
            </label>
            <label className="khsx-field">
              <span>Số lượng gửi</span>
              <input
                type="number" min={0} disabled={!canUpdate}
                value={val("sl_gui", g.sl_gui) ?? ""}
                onChange={(e) => setF({ ...f, sl_gui: e.target.value ? Number(e.target.value) : null })}
              />
            </label>
            <label className="khsx-field">
              <span>Hao hụt cho phép</span>
              <input
                type="number" min={0} disabled={!canUpdate}
                title="Thoả thuận với nhà gia công"
                value={val("hao_hut_cho_phep", g.hao_hut_cho_phep) ?? ""}
                onChange={(e) => setF({ ...f, hao_hut_cho_phep: e.target.value ? Number(e.target.value) : null })}
              />
            </label>
            <label className="khsx-field">
              <span>Ngày gửi (DK)</span>
              <input
                type="date" disabled={!canUpdate}
                value={val("ngay_gui_dk", g.ngay_gui_dk) ?? ""}
                onChange={(e) => setF({ ...f, ngay_gui_dk: e.target.value || null })}
              />
            </label>
            <label className="khsx-field">
              <span>Ngày nhận (DK)</span>
              <input
                type="date" disabled={!canUpdate}
                value={val("ngay_nhan_dk", g.ngay_nhan_dk) ?? ""}
                onChange={(e) => setF({ ...f, ngay_nhan_dk: e.target.value || null })}
              />
            </label>
            <label className="khsx-field">
              <span>Vận chuyển (ngày)</span>
              <input
                type="number" min={0} step="0.5" disabled={!canUpdate}
                title="Tính cả hai chiều"
                value={val("van_chuyen_ngay", g.van_chuyen_ngay) ?? ""}
                onChange={(e) => setF({ ...f, van_chuyen_ngay: e.target.value ? Number(e.target.value) : null })}
              />
            </label>
            <label className="khsx-field">
              <span>Gia công (ngày)</span>
              <input
                type="number" min={0} step="0.5" disabled={!canUpdate}
                value={val("gia_cong_ngay", g.gia_cong_ngay) ?? ""}
                onChange={(e) => setF({ ...f, gia_cong_ngay: e.target.value ? Number(e.target.value) : null })}
              />
            </label>
          </div>
          <label className="khsx-field" style={{ marginTop: "8px" }}>
            <span>Yêu cầu kỹ thuật gửi nhà gia công</span>
            <textarea
              rows={2} className="khsx-textarea" disabled={!canUpdate}
              value={val("yeu_cau_ky_thuat", g.yeu_cau_ky_thuat) ?? ""}
              onChange={(e) => setF({ ...f, yeu_cau_ky_thuat: e.target.value })}
            />
          </label>
        </div>
      )}

      <div className="bgsd-sec">
        <div className="bgsd-sec__head">
          <Icon name="fileText" size={16} style={{ color: "#0284c7" }} />
          <span>Yêu cầu kỹ thuật của từng lệnh trên tờ này</span>
        </div>
        <ul className="bgsd-gang-notes">
          {g.thanh_vien.map((tv) => (
            <li key={tv.lsx_step_key}>
              <span className="khsx__code">{tv.lsx_ma}</span>
              <span className={tv.ghi_chu_ky_thuat ? "" : "khsx-muted"}>
                {tv.ghi_chu_ky_thuat || "không có ghi chú riêng"}
              </span>
            </li>
          ))}
        </ul>
        <label className="khsx-field" style={{ marginTop: "10px" }}>
          <span>Ghi chú của bài cho lượt chạy này</span>
          <textarea
            rows={2} className="khsx-textarea" disabled={!canUpdate}
            value={f.ghi_chu ?? g.ghi_chu ?? ""}
            onChange={(e) => setF({ ...f, ghi_chu: e.target.value })}
          />
        </label>
      </div>
      {canUpdate && (
        <div className="bgsd-gang-actions">
          <Button variant="primary" disabled={!dirty} loading={dangLuu} onClick={() => void luu()}>
            Lưu kế hoạch lượt chung
          </Button>
          <button
            type="button" className="khsx-xlink" style={{ color: "var(--signal)" }}
            onClick={() => setConfirmTach(true)}
          >
            Tách lượt chung
          </button>
          <ConfirmDialog
            open={confirmTach}
            title={`Tách "${g.ten}"?`}
            message="Kế hoạch của lượt chung sẽ mất, số riêng của từng lệnh quay lại."
            confirmLabel="Tách lượt chung"
            cancelLabel="Hủy"
            danger
            onConfirm={() => {
              setConfirmTach(false);
              void onTach();
            }}
            onCancel={() => setConfirmTach(false)}
          />
        </div>
      )}
    </div>
  );
}

function ThemPicker({ exclude, onThem }: { exclude: Set<number>; onThem: (ids: number[]) => void }) {
  const { token } = useAuth();
  const [open, setOpen] = useState(false);
  const [pool, setPool] = useState<HangChoGhepItem[] | null>(null);
  const [sel, setSel] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (!open || !token) return;
    api.baiGhep.hangCho(token).then((r) => setPool(r.items.filter((i) => !exclude.has(i.lsx_id))));
  }, [open, token, exclude]);

  if (!open) {
    return (
      <button
        type="button"
        className="bgsd-btn-add-picker"
        onClick={() => setOpen(true)}
      >
        <Icon name="plus" size={15} />
        <span>Thêm lệnh vào bài ghép</span>
      </button>
    );
  }
  return (
    <div className="bghep-pick bgsd-pick-container">
      <div className="bghep-pick__head">
        <Icon name="plus" size={16} style={{ color: "#0284c7" }} />
        <span className="bghep-pick__title">Chọn lệnh sẵn sàng để thêm vào bài</span>
      </div>

      {pool == null ? (
        <p className="khsx-muted" style={{ padding: "8px 0" }}>Đang tải danh sách lệnh chờ…</p>
      ) : pool.length === 0 ? (
        <p className="khsx-muted" style={{ padding: "8px 0" }}>Không còn lệnh nào sẵn sàng chờ ghép.</p>
      ) : (
        <ul className="bghep-pick__list">
          {pool.map((i) => {
            const isChecked = sel.has(i.lsx_id);
            return (
              <li key={i.lsx_id}>
                <label className={`bgsd-pick-item ${isChecked ? "is-checked" : ""}`}>
                  <input
                    type="checkbox"
                    checked={isChecked}
                    className="bgsd-pick-checkbox"
                    onChange={() =>
                      setSel((s) => {
                        const n = new Set(s);
                        n.has(i.lsx_id) ? n.delete(i.lsx_id) : n.add(i.lsx_id);
                        return n;
                      })
                    }
                  />
                  <span className="khsx__code bgsd-pick-code">{i.ma}</span>
                  <span className="bgsd-pick-name">{i.ten}</span>
                  {i.giay_ten && <span className="bgsd-pick-giay">{i.giay_ten}</span>}
                  <span className="bgsd-pick-qty">{num(i.so_luong_dat)} con</span>
                </label>
              </li>
            );
          })}
        </ul>
      )}
      <div className="bghep-pick__foot">
        <Button variant="ghost" onClick={() => (setOpen(false), setSel(new Set()))}>
          Hủy
        </Button>
        <Button
          variant="primary"
          disabled={sel.size < 1}
          onClick={() => (onThem([...sel]), setOpen(false), setSel(new Set()))}
        >
          Xác nhận thêm {sel.size > 0 ? `(${sel.size})` : ""}
        </Button>
      </div>
    </div>
  );
}

function mau(i: number): string {
  return MAU_NHANH[i % MAU_NHANH.length];
}

function Kv({ k, v }: { k: string; v: string | number }) {
  return (
    <div className="khsx-kv">
      <span className="khsx-kv__k">{k}</span>
      <span className="khsx-kv__v">{v}</span>
    </div>
  );
}
