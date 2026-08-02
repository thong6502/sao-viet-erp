// Sơ đồ BÀI GHÉP — N nhánh vào → MỘT node IN → N nhánh ra (xem `docs/spec-bai-ghep-dag.md` §2).
import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  LSX_LOAI_BUOC_META,
  BAI_GHEP_MUC_META,
  api,
  type BaiGhepDetail,
  type BaiGhepSoDo as SoDo,
  type BaiGhepSoDoNhanh,
  type BaiGhepSoDoNode,
  type HangChoGhepItem,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import { BaiGhepDagCanvas } from "../components/BaiGhepDagCanvas";
import { BangLoi, ChipGap, Skeleton, classHan, ngay, num } from "./keHoachSxShared";
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
  onSuaThongSoTo?: () => void;
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

  const bg = sd.bai_ghep;
  const nhanhChon = typeof chon === "number" ? sd.nhanh.find((n) => n.lsx_id === chon) : null;

  return (
    <section className="khsx-panel bgsd bgsd-split-container">
      <div className="bgsd-split-main">
        <p className="bghep-hint" style={{ margin: "0 0 8px" }}>
          Mỗi lệnh giữ chuỗi riêng cả trước lẫn sau in — chỉ <strong>tờ giấy trên máy in</strong> là
          chung. Bấm node để xem/sửa chi tiết bên phải.
        </p>

        {sd.nhanh.length === 0 ? (
          <div className="khsx-empty khsx-empty--inline">
            <Icon name="layers" size={28} />
            <p className="khsx-empty__title">Bài chưa có lệnh nào.</p>
            <p className="khsx-empty__sub">
              Thêm lệnh ở bảng bên phải để sơ đồ có nhánh biểu diễn.
            </p>
          </div>
        ) : (
          <div className="bgsd-canvas-wrapper">
            <BaiGhepDagCanvas
              sd={sd}
              chon={chon}
              onChon={(val) => setChon(val)}
              onMoLenh={onMoLenh}
            />
            {chon === null && (
              <button
                type="button"
                className="bgsd-reopen-inspector"
                onClick={() => setChon("in")}
                title="Mở thông số tờ chạy chung & nhập liệu"
              >
                <Icon name="layers" size={14} />
                <span>Thông số & Nhập liệu</span>
              </button>
            )}
          </div>
        )}
      </div>

      {/* Side Inspector Panel (Trọn gói Nhập liệu & Quản lý Bài ghép) */}
      {(chon === "in" || nhanhChon) && (
        <aside className="bgsd-inspector-aside">
          <div className="bgsd-inspector-head">
            <span className="bgsd-inspector-title">
              <Icon name={chon === "in" ? "layers" : "file-text"} size={14} />
              {chon === "in" ? "Thông số tờ & Nhập liệu Bài ghép" : `Chi tiết ${nhanhChon?.lsx_ma}`}
            </span>
            <button
              type="button"
              className="bgsd-inspector-close"
              onClick={() => setChon(null)}
              title="Đóng panel"
            >
              <Icon name="x" size={14} />
            </button>
          </div>

          <div className="bgsd-inspector-body">
            {chon === "in" ? (
              <div className="bgsd-inspector-sections">
                {/* 1. Cấu hình Giấy, Khổ in & Hao hụt */}
                <div className="bgsd-sec">
                  <div className="bgsd-sec__head">
                    <Icon name="settings" size={14} />
                    <span>Cấu hình Giấy, Khổ in & Hao hụt</span>
                  </div>
                  <div className="khsx-form" style={{ gap: "8px" }}>
                    <label className="khsx-field" style={{ marginBottom: "6px" }}>
                      <span>Giấy chạy chung</span>
                      <select
                        value={form.giay_id ?? ""}
                        disabled={!canUpdate}
                        onChange={(e) =>
                          setForm({ ...form, giay_id: e.target.value ? Number(e.target.value) : null })
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
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
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
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
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
                </div>

                {/* 2. Quản lý Thành viên & Số con/tờ */}
                <div className="bgsd-sec">
                  <div className="bgsd-sec__head">
                    <Icon name="users" size={14} />
                    <span>Thành viên & Phân bổ con/tờ ({detail.thanh_vien.length})</span>
                  </div>

                  <div className="khsx__tablewrap" style={{ marginBottom: "8px" }}>
                    <table className="khsx__table">
                      <thead>
                        <tr>
                          <th>Lệnh</th>
                          <th className="khsx-num">Con/tờ</th>
                          <th className="khsx-num">Nhu cầu</th>
                          <th>Lượt in</th>
                          <th className="khsx-num">Dư</th>
                          <th aria-label="Bỏ" />
                        </tr>
                      </thead>
                      <tbody>
                        {detail.thanh_vien.map((t) => (
                          <tr key={t.thanh_vien_id} className="khsx__row">
                            <td>
                              <div className="khsx__code">{t.lsx_ma}</div>
                              {t.is_rush && <ChipGap />}
                            </td>
                            <td className="khsx-num">
                              <input
                                type="number"
                                min={0}
                                className="bghep-ups"
                                defaultValue={t.so_con_tren_to}
                                disabled={!canUpdate}
                                onBlur={(e) => {
                                  const v = Number(e.target.value);
                                  if (v !== t.so_con_tren_to) onSuaThanhVien(t.thanh_vien_id, v);
                                }}
                                aria-label={`Số con trên tờ của ${t.lsx_ma}`}
                              />
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
                                <span className="khsx-muted" style={{ fontSize: "11px" }}>
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
                    <ThemPicker
                      exclude={new Set(detail.thanh_vien.map((t) => t.lsx_id))}
                      onThem={onThemThanhVien}
                    />
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
                      <Icon name="check" size={14} />
                      <span>
                        Kiểm tương thích (
                        {detail.tuong_thich.rows.filter((r) => r.muc === "ok").length}/
                        {detail.tuong_thich.rows.length} đạt)
                      </span>
                    </span>
                    <Icon name={showTuongThich ? "chevron-up" : "chevron-down"} size={14} />
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
                    <Icon name="edit-3" size={14} />
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
              <div>
                <div className="bgsd-panel__head" style={{ marginBottom: "12px" }}>
                  <span className="bgsd__cham" style={{ background: mau(nhanhChon.mau) }} />
                  <span className="khsx__code">{nhanhChon.lsx_ma}</span>
                  <span style={{ fontSize: "13px", fontWeight: 600 }}>{nhanhChon.lsx_ten}</span>
                </div>
                <div style={{ marginBottom: "14px" }}>
                  <button
                    type="button"
                    className="khsx-xlink"
                    onClick={() => onMoLenh(nhanhChon.lsx_id)}
                  >
                    Mở chi tiết lệnh →
                  </button>
                </div>
                <div className="khsx-kvgrid" style={{ gap: "10px" }}>
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
        </aside>
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

function NodeChip({
  node,
  ngoai,
  onClick,
}: {
  node: BaiGhepSoDoNode;
  ngoai: { step_key: string; ten: string; lsx_ma: string | null }[];
  onClick: () => void;
}) {
  const meta = LSX_LOAI_BUOC_META[node.loai_buoc] ?? { label: node.loai_buoc, tone: "" };
  return (
    <>
      {ngoai.map((o) => (
        <span className="bgsd-node bgsd-node--ngoai" key={o.step_key} title="Bước của lệnh khác">
          <span className="bgsd-node__ten">{o.ten}</span>
          <span className="bgsd-node__phu">{o.lsx_ma ?? "LSX khác"}</span>
        </span>
      ))}
      <button type="button" className="bgsd-node" onClick={onClick} title={`Mở lệnh · ${node.ten}`}>
        <span className="bgsd-node__ten">{node.ten}</span>
        <span className="bgsd-node__phu">
          {node.loai_buoc === "thue_ngoai"
            ? node.nha_cung_cap || "chưa có nhà gia công"
            : node.may_ten || node.to_ten || meta.label}
          {node.tong_phut > 0 ? ` · ${phut(node.tong_phut)}` : ""}
        </span>
      </button>
    </>
  );
}
