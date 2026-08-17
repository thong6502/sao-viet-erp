// Sơ đồ BÀI GHÉP — routing ĐẦY ĐỦ của từng lệnh + các bước NGƯỜI khai là chạy chung.
// Không có node "in chung tờ" nào tự mọc ra: ghép bài chung cả CTP/cán/bế chứ không riêng bước in,
// nên chọn bước nào là việc của người lập kế hoạch.
import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  api,
  type BaiGhepBuocChungBody,
  type BaiGhepDetail,
  type BaiGhepSoDo as SoDo,
  type HangChoGhepItem,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import { BaiGhepDagCanvas } from "../components/BaiGhepDagCanvas";
import { BuocChungForm } from "./BaiGhepBuocChungForm";
import { BangLoi, ChipGap, Kv, Skeleton, ngay, num } from "./keHoachSxShared";
import { phut } from "./lsxBuoc";

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

  // Hao của bài: chưa khai ô nào (cả hai `null`) thì bài đang chạy bằng số MÁY ĐỀ XUẤT. Phải nói
  // ra, không thì hai ô trống trông như "không bù hao" trong khi số tờ cấp vẫn đang cộng hao.
  const hao = {
    deXuat: form.hao_hut_setup == null && form.hao_hut_chay == null,
    setup: detail.so_to.hao_setup_de_xuat,
    chay: detail.so_to.hao_chay_de_xuat,
  };

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

                  {/* 3. Ghi chú Kế hoạch */}
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


function ThemPicker({ exclude, onThem }: { exclude: Set<number>; onThem: (ids: number[]) => void }) {
  const { token } = useAuth();
  const [open, setOpen] = useState(false);
  const [pool, setPool] = useState<HangChoGhepItem[] | null>(null);
  // Lệnh đang giữ chỗ vật tư bị lọc khỏi hàng chờ. Picker này là chỗ người ta ĐI TÌM một mã cụ
  // thể, nên im lặng ở đây còn khó chịu hơn ở bảng hàng chờ — phải nói vì sao không thấy.
  const [soGiuCho, setSoGiuCho] = useState(0);
  const [sel, setSel] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (!open || !token) return;
    api.baiGhep.hangCho(token).then((r) => {
      setPool(r.items.filter((i) => !exclude.has(i.lsx_id)));
      setSoGiuCho(r.so_giu_cho ?? 0);
    });
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

      {soGiuCho > 0 && (
        <p className="bghep-anvi" role="status">
          <Icon name="lock" size={13} />
          <span>
            <b>{soGiuCho} lệnh</b> đang giữ chỗ vật tư nên không có trong danh sách — nhả chỗ bên
            {" "}<b>Kế hoạch vật tư</b> nếu muốn ghép.
          </span>
        </p>
      )}
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

