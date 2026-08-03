// Sơ đồ BÀI GHÉP — N nhánh vào → MỘT node IN → N nhánh ra (xem `docs/spec-bai-ghep-dag.md` §2).
import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  BAI_GHEP_MUC_META,
  api,
  type BaiGhepDetail,
  type BaiGhepSoDo as SoDo,
  type HangChoGhepItem,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import { BaiGhepDagCanvas } from "../components/BaiGhepDagCanvas";
import { BangLoi, ChipGap, Skeleton, ngay, num } from "./keHoachSxShared";
import { phut } from "./lsxBuoc";

export interface Form {
  giay_id: number | null;
  kho_in_dai: number | null;
  kho_in_rong: number | null;
  hao_hut_setup: number;
  hao_hut_chay: number;
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
}: {
  baiGhepId: number;
  tick: number;
  canUpdate: boolean;
  detail: BaiGhepDetail;
  form: Form;
  setForm: (f: Form) => void;
  giayOptions: [number, string | null][];
  onMoLenh: (lsxId: number) => void;
  onSuaThanhVien: (tvId: number, soCon: number, buocInStepKey?: string) => void;
  onBoThanhVien: (tvId: number) => void;
  onThemThanhVien: (lsxIds: number[]) => void;
  /** CỬA GHI DUY NHẤT của thông số tờ: sơ đồ không tự gọi API, đẩy lên cha (xem
   *  `test_so_do_bai_ghep_nhanh_chi_doc_va_mot_cua_ghi_thong_so_to`). */
  onSuaThongSoTo?: () => void;
  dirtyThongSoTo?: boolean;
  dangLuuThongSoTo?: boolean;
}) {
  const { token } = useAuth();
  const [sd, setSd] = useState<SoDo | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [chon, setChon] = useState<"in" | number | null>("in");
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

  const nhanhChon = typeof chon === "number" ? sd.nhanh.find((n) => n.lsx_id === chon) : null;

  return (
    <section className="khsx-panel bgsd bgsd-canvas-container">
      <div className="bgsd-canvas-wrapper">
        <p className="bghep-hint" style={{ margin: "0 0 8px" }}>
          Mỗi lệnh giữ chuỗi riêng cả trước lẫn sau in — chỉ <strong>tờ giấy trên máy in</strong> là
          chung. Bấm node hoặc nút bên trên để xem/sửa chi tiết.
        </p>

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
            chon={chon}
            onChon={(val) => setChon(val)}
            onMoLenh={onMoLenh}
          />
        )}

        {/* Floating Bar trên góc Canvas */}
        <div className="bgsd-floating-bar">
          <button
            type="button"
            className="bgsd-btn-floating-inspector"
            onClick={() => setChon("in")}
            title="Mở bảng Thông số tờ chạy chung & Nhập liệu Bài ghép"
          >
            <Icon name="layers" size={16} />
            <span>Thông số tờ & Nhập liệu Bài ghép</span>
            {detail.thanh_vien.length > 0 && (
              <span className="bgsd-floating-badge">{detail.thanh_vien.length} lệnh</span>
            )}
          </button>
        </div>
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
                <Icon name={chon === "in" ? "layers" : "fileText"} size={16} />
                {chon === "in"
                  ? "Thông số tờ & Nhập liệu Bài ghép"
                  : `Chi tiết Lệnh ${nhanhChon?.lsx_ma}`}
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
              {chon === "in" ? (
                <div className="bgsd-modal-content-grid">
                  {/* 1. Cấu hình Giấy, Khổ in & Hao hụt (Grid 4 cột) */}
                  <div className="bgsd-sec bgsd-sec--featured">
                    <div className="bgsd-sec__head">
                      <Icon name="settings" size={15} />
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
                          onChange={(e) =>
                            setForm({
                              ...form,
                              kho_in_rong: e.target.value ? Number(e.target.value) : null,
                            })
                          }
                        />
                      </label>

                      <label className="khsx-field">
                        <span>Hao setup (tờ)</span>
                        <input
                          type="number"
                          min={0}
                          disabled={!canUpdate}
                          value={form.hao_hut_setup}
                          onChange={(e) =>
                            setForm({ ...form, hao_hut_setup: Number(e.target.value) })
                          }
                        />
                      </label>

                      <label className="khsx-field">
                        <span>Hao chạy (tờ)</span>
                        <input
                          type="number"
                          min={0}
                          disabled={!canUpdate}
                          value={form.hao_hut_chay}
                          onChange={(e) =>
                            setForm({ ...form, hao_hut_chay: Number(e.target.value) })
                          }
                        />
                      </label>
                    </div>
                  </div>

                  {/* 2. Quản lý Thành viên & Số con/tờ */}
                  <div className="bgsd-sec">
                    <div className="bgsd-sec__head" style={{ justifyContent: "space-between" }}>
                      <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                        <Icon name="users" size={15} />
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
                            <th>Lượt in</th>
                            <th className="khsx-num">Số tờ dư</th>
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
                              </td>
                              <td className="khsx-num">{num(t.nhu_cau_to)}</td>
                              <td>
                                {t.buoc_in_chon_duoc.length > 1 ? (
                                  <select
                                    className="khsx-select-sm"
                                    value={t.buoc_in_step_key ?? ""}
                                    disabled={!canUpdate}
                                    onChange={(e) =>
                                      onSuaThanhVien(t.thanh_vien_id, t.so_con_tren_to, e.target.value)
                                    }
                                  >
                                    {t.buoc_in_chon_duoc.map((b) => (
                                      <option key={b.step_key} value={b.step_key}>
                                        {b.ten}
                                      </option>
                                    ))}
                                  </select>
                                ) : (
                                  <span className="khsx-muted" style={{ fontSize: "12px" }}>
                                    {t.buoc_in_chon_duoc[0]?.ten ?? "—"}
                                  </span>
                                )}
                              </td>
                              <td className={`khsx-num ${t.du > 0 ? "bghep-du" : ""}`}>
                                {t.du > 0 ? `+${num(t.du)}` : num(t.du)}
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
                        <Icon name="check" size={15} />
                        <span>
                          Kiểm tương thích sản xuất (
                          {detail.tuong_thich.rows.filter((r) => r.muc === "ok").length}/
                          {detail.tuong_thich.rows.length} đạt)
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
                      <Icon name="edit" size={15} />
                      <span>Ghi chú kế hoạch</span>
                    </div>
                    <textarea
                      rows={2}
                      className="khsx-textarea"
                      value={form.ghi_chu}
                      disabled={!canUpdate}
                      onChange={(e) => setForm({ ...form, ghi_chu: e.target.value })}
                      placeholder="Ghi chú thêm cho bài ghép…"
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
                      k="Các bước sau in"
                      v={`${nhanhChon.sau_in.length} bước · ${phut(
                        nhanhChon.sau_in.reduce((s, c) => s + c.tong_phut, 0),
                      )}`}
                    />
                  </div>
                </div>
              ) : null}
            </div>

            <div className="bgsd-modal-footer">
              <Button variant="secondary" onClick={() => setChon(null)}>
                Đóng
              </Button>
              {/* Form thông số tờ nằm trong popup che cả trang, nên nút Lưu ở header không với tới
                  được — lặp lại lối ghi ở đây. Vẫn gọi cùng một hàm luu() của cha, không đẻ cửa ghi thứ hai. */}
              {chon === "in" && dirtyThongSoTo && (
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
  const [sel, setSel] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (!open || !token) return;
    api.baiGhep.hangCho(token).then((r) => setPool(r.items.filter((i) => !exclude.has(i.lsx_id))));
  }, [open, token, exclude]);

  if (!open) {
    return (
      <Button variant="secondary" onClick={() => setOpen(true)} style={{ width: "100%", justifyContent: "center" }}>
        <Icon name="plus" size={14} /> Thêm lệnh vào bài
      </Button>
    );
  }
  return (
    <div className="bghep-pick">
      <p className="bghep-pick__title">Chọn lệnh sẵn sàng để thêm</p>
      {pool == null ? (
        <p className="khsx-muted">Đang tải…</p>
      ) : pool.length === 0 ? (
        <p className="khsx-muted">Không còn lệnh nào chờ ghép.</p>
      ) : (
        <ul className="bghep-pick__list">
          {pool.map((i) => (
            <li key={i.lsx_id}>
              <label>
                <input
                  type="checkbox"
                  checked={sel.has(i.lsx_id)}
                  onChange={() =>
                    setSel((s) => {
                      const n = new Set(s);
                      n.has(i.lsx_id) ? n.delete(i.lsx_id) : n.add(i.lsx_id);
                      return n;
                    })
                  }
                />
                <strong>{i.ma}</strong> · {i.ten} · {i.giay_ten || "—"} · {num(i.so_luong_dat)}
              </label>
            </li>
          ))}
        </ul>
      )}
      <div className="bghep-pick__foot">
        <Button variant="ghost" onClick={() => (setOpen(false), setSel(new Set()))}>
          Đóng
        </Button>
        <Button
          variant="accent"
          disabled={sel.size < 1}
          onClick={() => (onThem([...sel]), setOpen(false), setSel(new Set()))}
        >
          Thêm {sel.size > 0 ? `(${sel.size})` : ""}
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
