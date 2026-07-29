// Drawer CHI TIẾT 1 BƯỚC routing — chỗ khai đủ thứ mà bảng không chứa nổi.
//
// Vì sao tách khỏi bảng: routing lát này cần ~20 ô mỗi bước (đơn vị vào/ra + hệ số, 5 loại thời
// gian, số nhân công, điều kiện bắt đầu, 10 ô gia công ngoài). Nhồi hết vào bảng thì mỗi ô còn
// ~60px và phải cuộn ngang liên tục. Bảng giữ phần QUYẾT ĐỊNH (bước nào, ai làm, bao lâu), drawer
// giữ phần KHAI BÁO.
//
// Sửa ở đây ghi THẲNG vào state của bảng (không có nút "Áp dụng" riêng) — vẫn chỉ một nút "Lưu
// công đoạn" duy nhất ở bảng, nên người dùng không phải nhớ mình đang ở tầng lưu nào.
//
// Máy CHỈ ĐỀ XUẤT: số kế thừa nằm ở placeholder + nút 1-click, KHÔNG tự ghi vào ô.
import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { LSX_DON_VI_LABELS, LSX_LOAI_BUOC_META, type LsxLoaiBuoc } from "../api/client";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import type { RefRow } from "./LsxRoutingTable";
import { num } from "./keHoachSxShared";
import {
  DIEU_KIEN,
  DON_VI,
  DON_VI_NANG_SUAT,
  type EditRow,
  n,
  phut,
  thoiLuong,
} from "./lsxBuoc";

const LOAI_BUOC_ORDER: LsxLoaiBuoc[] = ["may", "to", "thue_ngoai", "cho", "kcs", "xa_to"];

/** Gom máy theo `loai_may`, máy mặc định của công đoạn tách riêng lên đầu.
 *  Xưởng có ~24 máy đủ loại (bế, bồi, UV, cán, in) — đổ phẳng thì gán máy bế cho bước ghi kẽm
 *  cũng trôi. Nhóm KHÔNG chặn: vẫn chọn được máy bất kỳ, chỉ là mắt phải đi qua nhãn loại. */
function nhomMayTheoLoai(mayRefs: RefRow[], mayGoiYId: number | null): { ten: string; items: RefRow[] }[] {
  const groups = new Map<string, RefRow[]>();
  for (const m of mayRefs) {
    if (m.id === mayGoiYId) continue;
    const k = (m.nhom || "").trim() || "Chưa phân loại";
    const arr = groups.get(k);
    if (arr) arr.push(m);
    else groups.set(k, [m]);
  }
  const out = [...groups.entries()]
    .sort((a, b) => a[0].localeCompare(b[0], "vi"))
    .map(([ten, items]) => ({ ten, items }));
  const goiY = mayRefs.find((m) => m.id === mayGoiYId);
  return goiY ? [{ ten: "Máy mặc định của công đoạn", items: [goiY] }, ...out] : out;
}

export function LsxBuocDrawer({
  row,
  index,
  tong,
  soCon,
  soToKeHoach,
  soLuongDat,
  congDoanRefs,
  toRefs,
  mayRefs,
  canUpdate,
  onPatch,
  onDoiCongDoan,
  onClose,
  onPrev,
  onNext,
}: {
  row: EditRow;
  index: number;
  tong: number;
  soCon: number;
  soToKeHoach: number;
  soLuongDat: number;
  congDoanRefs: RefRow[] | null;
  toRefs: RefRow[] | null;
  mayRefs: RefRow[] | null;
  canUpdate: boolean;
  onPatch: (p: Partial<EditRow>) => void;
  /** Đổi công đoạn: kéo lại toàn bộ mặc định của công đoạn mới (giữ SL vào/ra). */
  onDoiCongDoan: (congDoanId: number | null) => void;
  onClose: () => void;
  onPrev: () => void;
  onNext: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const ngoai = row.loai_buoc === "thue_ngoai";
  const doiDonVi = row.don_vi_vao !== row.don_vi_ra;
  const t = useMemo(() => thoiLuong(row), [row]);
  const [hienTatCaMay, setHienTatCaMay] = useState(false);

  const mayGoiYId = congDoanRefs?.find((c) => c.id === row.cong_doan_id)?.mayId ?? null;
  const nhomMay = useMemo(
    () => (mayRefs ? nhomMayTheoLoai(mayRefs, mayGoiYId) : []),
    [mayRefs, mayGoiYId],
  );
  // Máy thay thế chỉ có nghĩa trong CÙNG loại máy (bế thay bế, không thay bằng máy cán). Mặc định
  // lọc theo loại của máy chính + giữ máy đã chọn; cần khác loại thì bấm "Hiện tất cả".
  const mayChinh = mayRefs?.find((m) => m.id === row.may_id) ?? null;
  const dsMayThayThe = useMemo(() => {
    if (!mayRefs) return [];
    const base = hienTatCaMay
      ? mayRefs
      : mayRefs.filter(
          (m) => (mayChinh != null && m.nhom === mayChinh.nhom) || row.may_thay_the_ids.includes(m.id),
        );
    return base.filter((m) => m.id !== row.may_id);
  }, [mayRefs, hienTatCaMay, mayChinh, row.may_id, row.may_thay_the_ids]);

  useEffect(() => titleRef.current?.focus(), [row.key]);

  // Esc đóng + BẪY TAB trong drawer (nợ của lát trước: tab lọt ra sau nền, người dùng bàn phím lạc).
  function onKeyDown(e: KeyboardEvent) {
    if (e.key === "Escape") {
      e.stopPropagation();
      onClose();
      return;
    }
    if (e.key !== "Tab") return;
    const focusables = panelRef.current?.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    );
    if (!focusables || focusables.length === 0) return;
    const dau = focusables[0];
    const cuoi = focusables[focusables.length - 1];
    if (!e.shiftKey && document.activeElement === cuoi) {
      e.preventDefault();
      dau.focus();
    } else if (e.shiftKey && document.activeElement === dau) {
      e.preventDefault();
      cuoi.focus();
    }
  }

  function set<K extends keyof EditRow>(k: K, v: EditRow[K]) {
    onPatch({ [k]: v } as Partial<EditRow>);
  }

  function toggleDieuKien(key: string) {
    const co = row.dieu_kien_json.includes(key);
    set("dieu_kien_json", co
      ? row.dieu_kien_json.filter((x) => x !== key)
      : [...row.dieu_kien_json, key]);
  }

  /** Ngày nhận lại gợi ý = gửi + vận chuyển đi + gia công + vận chuyển về.
   *
   *  Ghép chuỗi ngày bằng tay chứ KHÔNG dùng `toISOString()`: hàm đó quy về UTC, mà giờ VN là
   *  UTC+7 nên nửa đêm giờ ta rơi về hôm trước — gợi ý sẽ lệch đúng 1 ngày. */
  const ngayNhanGoiY = useMemo(() => {
    if (!row.ngay_gui_dk) return "";
    const ngay = n(row.van_chuyen_ngay) * 2 + n(row.gia_cong_ngay);
    if (ngay <= 0) return "";
    const d = new Date(`${row.ngay_gui_dk}T00:00:00`);
    d.setDate(d.getDate() + Math.ceil(ngay));
    const hai = (v: number) => String(v).padStart(2, "0");
    return `${d.getFullYear()}-${hai(d.getMonth() + 1)}-${hai(d.getDate())}`;
  }, [row.ngay_gui_dk, row.van_chuyen_ngay, row.gia_cong_ngay]);

  const meta = LSX_LOAI_BUOC_META[row.loai_buoc];

  return (
    <div className="khsx-scrim" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        ref={panelRef}
        className="khsx-drawer khsx-drawer--buoc"
        role="dialog"
        aria-modal="true"
        aria-labelledby="khsx-buoc-title"
        onKeyDown={onKeyDown}
      >
        <header className="khsx-drawer__head">
          <div className="khsx-drawer__headmain">
            <p className="khsx-drawer__kicker">Bước {index + 1} / {tong}</p>
            <h2
              className="khsx-drawer__title"
              id="khsx-buoc-title"
              tabIndex={-1}
              ref={titleRef}
            >
              {row.ten || "Công đoạn chưa đặt tên"}
            </h2>
            <p className="khsx-drawer__meta">
              <span className={`khsx-lb khsx-lb--${meta.tone}`}>{meta.label}</span>
              <span> {meta.hint}</span>
            </p>
          </div>
          <div className="khsx-buoc__nav">
            <button type="button" onClick={onPrev} disabled={index === 0} aria-label="Bước trước">
              <Icon name="chevron" size={15} />
            </button>
            <button
              type="button"
              onClick={onNext}
              disabled={index >= tong - 1}
              aria-label="Bước sau"
            >
              <Icon name="chevron" size={15} />
            </button>
          </div>
          <button type="button" className="khsx-drawer__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={18} />
          </button>
        </header>

        <div className="khsx-drawer__body">
          {/* --- 1. Nhận diện --- */}
          <Nhom title="Nhận diện">
            <div className="khsx-form">
              <label className="khsx-field">
                <span className="khsx-field__label">Công đoạn</span>
                {congDoanRefs ? (
                  <select
                    value={row.cong_doan_id ?? (row.ten ? "__keep__" : "")}
                    disabled={!canUpdate}
                    onChange={(e) => {
                      if (e.target.value === "__keep__") return;
                      // Đổi công đoạn = đổi hẳn bản chất bước → kéo lại mặc định của công đoạn mới
                      // (loại bước, tổ, máy, đơn vị, chuẩn bị, năng suất). Backend quyết, không tự
                      // tính ở đây. SL vào/ra giữ nguyên vì thuộc chuỗi, không thuộc công đoạn.
                      onDoiCongDoan(e.target.value ? Number(e.target.value) : null);
                    }}
                  >
                    <option value="">— chọn công đoạn —</option>
                    {/* Bước lấy từ bài tính giá có thể là TÊN TỰ DO (không gắn danh mục) —
                        giữ nguyên option đó, đừng để select rơi về rỗng làm mất dữ liệu. */}
                    {row.cong_doan_id == null && row.ten && (
                      <option value="__keep__">{row.ten} (tên tự do)</option>
                    )}
                    {row.cong_doan_id != null
                      && !congDoanRefs.some((c) => c.id === row.cong_doan_id) && (
                        <option value={row.cong_doan_id}>{row.ten}</option>
                      )}
                    {congDoanRefs.map((c) => (
                      <option key={c.id} value={c.id}>{c.ten}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    value={row.ten}
                    disabled={!canUpdate}
                    onChange={(e) => set("ten", e.target.value)}
                  />
                )}
              </label>

              <div className="khsx-field khsx-field--wide">
                <span className="khsx-field__label">Loại bước — quyết định bước chiếm gì khi xếp lịch</span>
                <div className="khsx-seg khsx-seg--wrap" role="group" aria-label="Loại bước">
                  {LOAI_BUOC_ORDER.map((k) => {
                    const m = LSX_LOAI_BUOC_META[k];
                    return (
                      <button
                        key={k}
                        type="button"
                        className={row.loai_buoc === k ? "is-active" : ""}
                        disabled={!canUpdate}
                        aria-pressed={row.loai_buoc === k}
                        title={m.hint}
                        onClick={() => set("loai_buoc", k)}
                      >
                        {m.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              <label className="khsx-field khsx-field--check">
                <input
                  type="checkbox"
                  checked={row.bat_buoc}
                  disabled={!canUpdate}
                  onChange={(e) => set("bat_buoc", e.target.checked)}
                />
                <span>Bước bắt buộc (bỏ tick = tùy chọn, có thể cắt khi gấp)</span>
              </label>

              <label className="khsx-field khsx-field--wide">
                <span className="khsx-field__label">Ghi chú kỹ thuật cho thợ</span>
                <input
                  value={row.ghi_chu}
                  disabled={!canUpdate}
                  placeholder="vd: canh màu theo mẫu đã ký"
                  onChange={(e) => set("ghi_chu", e.target.value)}
                />
              </label>
            </div>
          </Nhom>

          {/* --- 2. Số lượng --- */}
          <Nhom title="Số lượng &amp; hao hụt">
            <div className="khsx-form">
              <label className="khsx-field">
                <span className="khsx-field__label">Số lượng vào</span>
                <div className="khsx-inline">
                  <input
                    type="number"
                    value={row.so_luong_vao}
                    placeholder={String(row.don_vi_vao === "cai" ? soLuongDat : soToKeHoach)}
                    disabled={!canUpdate}
                    onChange={(e) => set("so_luong_vao", e.target.value)}
                  />
                  <DonViChon
                    value={row.don_vi_vao}
                    disabled={!canUpdate}
                    label="Đơn vị vào"
                    onChange={(v) => set("don_vi_vao", v)}
                  />
                </div>
              </label>
              <label className="khsx-field">
                <span className="khsx-field__label">Số lượng ra</span>
                <div className="khsx-inline">
                  <input
                    type="number"
                    value={row.so_luong_ra}
                    placeholder={String(row.don_vi_ra === "cai" ? soLuongDat : soToKeHoach)}
                    disabled={!canUpdate}
                    onChange={(e) => set("so_luong_ra", e.target.value)}
                  />
                  <DonViChon
                    value={row.don_vi_ra}
                    disabled={!canUpdate}
                    label="Đơn vị ra"
                    onChange={(v) => set("don_vi_ra", v)}
                  />
                </div>
              </label>

              {doiDonVi && (
                <label className="khsx-field">
                  <span className="khsx-field__label">
                    Hệ số quy đổi
                    <span className="khsx-field__origin">bắt buộc khi đổi đơn vị</span>
                  </span>
                  <div className="khsx-inline">
                    <input
                      type="number"
                      value={row.he_so_quy_doi}
                      placeholder={soCon > 1 ? String(soCon) : "1"}
                      disabled={!canUpdate}
                      onChange={(e) => set("he_so_quy_doi", e.target.value)}
                    />
                    {canUpdate && soCon > 1 && (
                      <button
                        type="button"
                        className="khsx-xlink"
                        onClick={() => set("he_so_quy_doi", String(soCon))}
                      >
                        dùng {num(soCon)} con/tờ
                      </button>
                    )}
                  </div>
                  <span className="khsx-field__hint">
                    1 {LSX_DON_VI_LABELS[row.don_vi_vao] ?? row.don_vi_vao} ra{" "}
                    {row.he_so_quy_doi || "?"} {LSX_DON_VI_LABELS[row.don_vi_ra] ?? row.don_vi_ra}
                  </span>
                </label>
              )}

              <label className="khsx-field">
                <span className="khsx-field__label">Hao hụt cố định (canh máy)</span>
                <div className="khsx-inline">
                  <input
                    type="number"
                    value={row.hao_hut}
                    placeholder="0"
                    disabled={!canUpdate}
                    onChange={(e) => set("hao_hut", e.target.value)}
                  />
                  {/* Ô số trần không nói 50 là 50 tờ hay 50 kẽm — dán đơn vị VÀO của bước vào cạnh. */}
                  <span className="khsx-unit-tag">{LSX_DON_VI_LABELS[row.don_vi_vao] ?? row.don_vi_vao}</span>
                </div>
              </label>
              <label className="khsx-field">
                <span className="khsx-field__label">Hao hụt theo tỷ lệ (%)</span>
                <input
                  type="number"
                  step="0.1"
                  value={row.hao_hut_pct}
                  placeholder="0"
                  disabled={!canUpdate}
                  onChange={(e) => set("hao_hut_pct", e.target.value)}
                />
              </label>
              <label className="khsx-field">
                <span className="khsx-field__label">Số lượt chạy</span>
                <input
                  type="number"
                  value={row.so_luot_chay}
                  placeholder="1"
                  disabled={!canUpdate}
                  onChange={(e) => set("so_luot_chay", e.target.value)}
                />
                <span className="khsx-field__hint">In trở 2 mặt = 2 lượt → thời gian chạy gấp đôi.</span>
              </label>
            </div>
          </Nhom>

          {/* --- 3. Thực hiện --- */}
          <Nhom title="Ai làm">
            <div className="khsx-form">
              {!ngoai && (
                <>
                  <label className="khsx-field">
                    <span className="khsx-field__label">Tổ phụ trách</span>
                    {toRefs ? (
                      <select
                        value={row.department_id ?? ""}
                        disabled={!canUpdate}
                        onChange={(e) =>
                          set("department_id", e.target.value ? Number(e.target.value) : null)}
                      >
                        <option value="">— tổ mặc định của công đoạn —</option>
                        {toRefs.map((t2) => (
                          <option key={t2.id} value={t2.id}>{t2.ten}</option>
                        ))}
                      </select>
                    ) : (
                      <span className="khsx-kv__val">tổ mặc định</span>
                    )}
                  </label>
                  <label className="khsx-field">
                    <span className="khsx-field__label">Máy</span>
                    {mayRefs ? (
                      <select
                        value={row.may_id ?? ""}
                        disabled={!canUpdate}
                        onChange={(e) => set("may_id", e.target.value ? Number(e.target.value) : null)}
                      >
                        <option value="">— chưa gán —</option>
                        {nhomMay.map((g) => (
                          <optgroup key={g.ten} label={g.ten}>
                            {g.items.map((m) => (
                              <option key={m.id} value={m.id}>{m.ten}</option>
                            ))}
                          </optgroup>
                        ))}
                      </select>
                    ) : (
                      <span className="khsx-kv__val">—</span>
                    )}
                  </label>
                  {(row.loai_buoc === "to" || row.loai_buoc === "kcs") && (
                    <label className="khsx-field">
                      <span className="khsx-field__label">Số người làm cùng lúc</span>
                      <input
                        type="number"
                        value={row.so_nhan_cong}
                        placeholder="1"
                        disabled={!canUpdate}
                        onChange={(e) => set("so_nhan_cong", e.target.value)}
                      />
                      <span className="khsx-field__hint">
                        5 người dán thì thời gian chạy chia 5 — chuẩn bị vẫn làm một lần.
                      </span>
                    </label>
                  )}
                  {mayRefs && (
                    <div className="khsx-field khsx-field--wide">
                      <span className="khsx-field__label">
                        Máy thay thế
                        <span className="khsx-field__origin">tham khảo — không tự xếp lịch</span>
                      </span>
                      {dsMayThayThe.length === 0 ? (
                        <span className="khsx-field__hint">
                          {mayChinh
                            ? "Không có máy nào cùng loại."
                            : "Chọn Máy ở trên trước — rồi bấm chọn máy cùng loại để dự phòng."}
                        </span>
                      ) : (
                        <div className="khsx-maychip">
                          {dsMayThayThe.map((m) => {
                            const on = row.may_thay_the_ids.includes(m.id);
                            return (
                              <button
                                key={m.id}
                                type="button"
                                className={`khsx-maychip__item${on ? " is-on" : ""}`}
                                aria-pressed={on}
                                disabled={!canUpdate}
                                onClick={() =>
                                  set(
                                    "may_thay_the_ids",
                                    on
                                      ? row.may_thay_the_ids.filter((x) => x !== m.id)
                                      : [...row.may_thay_the_ids, m.id],
                                  )}
                              >
                                {/* Đã chọn không chỉ đổi màu — có dấu tick, để không phải phân
                                    biệt bằng riêng màu nền. */}
                                {on && <Icon name="check" size={11} />}
                                {m.ten}
                              </button>
                            );
                          })}
                        </div>
                      )}
                      {canUpdate && mayRefs.length > 1 && (
                        <button
                          type="button"
                          className="khsx-xlink"
                          onClick={() => setHienTatCaMay((v) => !v)}
                        >
                          {hienTatCaMay ? "Chỉ máy cùng loại" : `Hiện tất cả ${mayRefs.length} máy`}
                        </button>
                      )}
                    </div>
                  )}
                </>
              )}

              {ngoai && (
                <>
                  <label className="khsx-field khsx-field--wide">
                    <span className="khsx-field__label">Nhà gia công</span>
                    <input
                      className={!row.nha_cung_cap ? "khsx-input--bad" : ""}
                      value={row.nha_cung_cap}
                      disabled={!canUpdate}
                      placeholder="Tên cơ sở nhận gia công"
                      onChange={(e) => set("nha_cung_cap", e.target.value)}
                    />
                  </label>
                  <label className="khsx-field">
                    <span className="khsx-field__label">Số lượng gửi</span>
                    <input
                      type="number"
                      value={row.sl_gui}
                      placeholder={row.so_luong_vao || "—"}
                      disabled={!canUpdate}
                      onChange={(e) => set("sl_gui", e.target.value)}
                    />
                  </label>
                  <label className="khsx-field">
                    <span className="khsx-field__label">Hao hụt cho phép</span>
                    <input
                      type="number"
                      value={row.hao_hut_cho_phep}
                      placeholder="0"
                      disabled={!canUpdate}
                      onChange={(e) => set("hao_hut_cho_phep", e.target.value)}
                    />
                  </label>
                  <label className="khsx-field">
                    <span className="khsx-field__label">Ngày dự kiến gửi</span>
                    <input
                      type="date"
                      className={!row.ngay_gui_dk ? "khsx-input--bad" : ""}
                      value={row.ngay_gui_dk}
                      disabled={!canUpdate}
                      onChange={(e) => set("ngay_gui_dk", e.target.value)}
                    />
                  </label>
                  <label className="khsx-field">
                    <span className="khsx-field__label">Vận chuyển 1 chiều (ngày)</span>
                    <input
                      type="number"
                      step="0.5"
                      value={row.van_chuyen_ngay}
                      placeholder="0"
                      disabled={!canUpdate}
                      onChange={(e) => set("van_chuyen_ngay", e.target.value)}
                    />
                  </label>
                  <label className="khsx-field">
                    <span className="khsx-field__label">Thời gian gia công (ngày)</span>
                    <input
                      type="number"
                      step="0.5"
                      value={row.gia_cong_ngay}
                      placeholder="0"
                      disabled={!canUpdate}
                      onChange={(e) => set("gia_cong_ngay", e.target.value)}
                    />
                  </label>
                  <label className="khsx-field">
                    <span className="khsx-field__label">Ngày dự kiến nhận lại</span>
                    <input
                      type="date"
                      className={!row.ngay_nhan_dk ? "khsx-input--bad" : ""}
                      value={row.ngay_nhan_dk}
                      disabled={!canUpdate}
                      onChange={(e) => set("ngay_nhan_dk", e.target.value)}
                    />
                    {canUpdate && ngayNhanGoiY && ngayNhanGoiY !== row.ngay_nhan_dk && (
                      <button
                        type="button"
                        className="khsx-xlink"
                        onClick={() => set("ngay_nhan_dk", ngayNhanGoiY)}
                      >
                        dùng {ngayNhanGoiY} (gửi + đi + gia công + về)
                      </button>
                    )}
                  </label>
                  <label className="khsx-field">
                    <span className="khsx-field__label">Đơn giá gia công</span>
                    <input
                      type="number"
                      value={row.don_gia_gia_cong}
                      placeholder="0"
                      disabled={!canUpdate}
                      onChange={(e) => set("don_gia_gia_cong", e.target.value)}
                    />
                  </label>
                  <label className="khsx-field khsx-field--wide">
                    <span className="khsx-field__label">Yêu cầu kỹ thuật gửi nhà gia công</span>
                    <textarea
                      rows={2}
                      value={row.yeu_cau_ky_thuat}
                      disabled={!canUpdate}
                      placeholder="vd: màng mờ, không bong mép, giao đủ 2 đợt"
                      onChange={(e) => set("yeu_cau_ky_thuat", e.target.value)}
                    />
                  </label>
                </>
              )}
            </div>
          </Nhom>

          {/* --- 4. Năng suất & thời gian --- */}
          <Nhom title="Mất bao lâu">
            <div className="khsx-form">
              <label className="khsx-field">
                <span className="khsx-field__label">Chuẩn bị máy (phút)</span>
                <input
                  type="number"
                  value={row.setup_phut}
                  placeholder="0"
                  disabled={!canUpdate}
                  onChange={(e) => set("setup_phut", e.target.value)}
                />
              </label>
              <label className="khsx-field">
                <span className="khsx-field__label">Năng suất</span>
                <div className="khsx-inline">
                  <input
                    type="number"
                    value={row.nang_suat}
                    placeholder="—"
                    disabled={!canUpdate}
                    onChange={(e) => set("nang_suat", e.target.value)}
                  />
                  <select
                    className="khsx-inline__unit"
                    value={row.don_vi_nang_suat}
                    disabled={!canUpdate}
                    aria-label="Đơn vị năng suất"
                    onChange={(e) => set("don_vi_nang_suat", e.target.value)}
                  >
                    <option value="">— đơn vị —</option>
                    {DON_VI_NANG_SUAT.map((u) => (
                      <option key={u.key} value={u.key}>{u.label}</option>
                    ))}
                  </select>
                </div>
              </label>
              <label className="khsx-field">
                <span className="khsx-field__label">Thời gian chạy (phút)</span>
                <input
                  type="number"
                  value={row.chay_phut}
                  placeholder={t.chay > 0 ? String(Math.round(t.chay)) : "—"}
                  disabled={!canUpdate}
                  onChange={(e) => set("chay_phut", e.target.value)}
                />
                <span className="khsx-field__hint">
                  Bỏ trống = máy tính từ năng suất. Gõ số vào đây là ghi đè.
                </span>
              </label>
              <label className="khsx-field">
                <span className="khsx-field__label">Vệ sinh / chuyển đổi (phút)</span>
                <input
                  type="number"
                  value={row.ve_sinh_phut}
                  placeholder="0"
                  disabled={!canUpdate}
                  onChange={(e) => set("ve_sinh_phut", e.target.value)}
                />
              </label>
              <label className="khsx-field">
                <span className="khsx-field__label">Chờ kỹ thuật (phút)</span>
                <input
                  type="number"
                  value={row.cho_phut}
                  placeholder="0"
                  disabled={!canUpdate}
                  onChange={(e) => set("cho_phut", e.target.value)}
                />
                <span className="khsx-field__hint">Khô mực / khô keo — không chiếm máy.</span>
              </label>
              <label className="khsx-field">
                <span className="khsx-field__label">Di chuyển sang bước sau (phút)</span>
                <input
                  type="number"
                  value={row.di_chuyen_phut}
                  placeholder="0"
                  disabled={!canUpdate}
                  onChange={(e) => set("di_chuyen_phut", e.target.value)}
                />
              </label>
            </div>

            <div className="khsx-tinh">
              <div className="khsx-tinh__row">
                <span className="khsx-tinh__label">Chiếm máy / tổ</span>
                <span className="khsx-tinh__val khsx-dur">{phut(t.chiemMay)}</span>
                <span className="khsx-tinh__note">
                  {num(Math.round(n(row.setup_phut)))} chuẩn bị + {num(Math.round(t.chay))} chạy +{" "}
                  {num(Math.round(n(row.ve_sinh_phut)))} vệ sinh
                </span>
              </div>
              <div className="khsx-tinh__row khsx-tinh__row--total">
                <span className="khsx-tinh__label">Tổng thời gian dẫn</span>
                <span className="khsx-tinh__val khsx-dur">{phut(t.tong)}</span>
                <span className="khsx-tinh__note">
                  {n(row.cho_phut) > 0 || n(row.di_chuyen_phut) > 0
                    ? `thêm ${num(Math.round(n(row.cho_phut)))} chờ + ${num(Math.round(n(row.di_chuyen_phut)))} di chuyển — hai khoản này KHÔNG chiếm máy`
                    : "không có chờ / di chuyển"}
                </span>
              </div>
            </div>
          </Nhom>

          {/* --- 5. Điều kiện bắt đầu --- */}
          <Nhom title="Chỉ được bắt đầu khi">
            <p className="khsx-nhom__sub">
              Công đoạn trước xong là điều kiện mặc định — dưới đây là những thứ cần thêm.
            </p>
            <div className="khsx-cond">
              {DIEU_KIEN.map((d) => (
                <label key={d.key} className="khsx-cond__item">
                  <input
                    type="checkbox"
                    checked={row.dieu_kien_json.includes(d.key)}
                    disabled={!canUpdate}
                    onChange={() => toggleDieuKien(d.key)}
                  />
                  <span>{d.label}</span>
                </label>
              ))}
            </div>
          </Nhom>
        </div>

        <footer className="khsx-drawer__foot">
          <p className="khsx-drawer__tally">
            Sửa ở đây chưa ghi vào hệ thống — bấm <strong>Lưu công đoạn</strong> ở bảng.
          </p>
          <div className="khsx-drawer__footbtns">
            <Button variant="secondary" onClick={onClose}>Xong</Button>
          </div>
        </footer>
      </div>
    </div>
  );
}

function Nhom({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="khsx-nhom">
      <h3 className="khsx-nhom__title">{title}</h3>
      {children}
    </section>
  );
}

function DonViChon({
  value,
  disabled,
  label,
  onChange,
}: {
  value: string;
  disabled: boolean;
  label: string;
  onChange: (v: string) => void;
}) {
  return (
    <select
      className="khsx-inline__unit"
      value={value}
      disabled={disabled}
      aria-label={label}
      onChange={(e) => onChange(e.target.value)}
    >
      {DON_VI.map((u) => (
        <option key={u.key} value={u.key}>{u.label}</option>
      ))}
    </select>
  );
}
