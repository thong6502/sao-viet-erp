// Drawer CHI TIẾT 1 BƯỚC routing — chỗ khai đủ thứ mà bảng không chứa nổi.
//
// Vì sao tách khỏi bảng: routing lát này cần nhiều dữ liệu mỗi bước (đơn vị, thời gian, nhân công,
// vật tư, phụ thuộc và gia công ngoài). Nhồi hết vào bảng thì mỗi ô còn
// ~60px và phải cuộn ngang liên tục. Bảng giữ phần QUYẾT ĐỊNH (bước nào, ai làm, bao lâu), drawer
// giữ phần KHAI BÁO.
//
// Sửa ở đây ghi THẲNG vào state của bảng (không có nút "Áp dụng" riêng) — vẫn chỉ một nút "Lưu
// công đoạn" duy nhất ở bảng, nên người dùng không phải nhớ mình đang ở tầng lưu nào.
//
// Năng suất là snapshot chỉ đọc từ máy hoặc định mức đầu việc; người dùng chỉ nhập đè thời gian.
import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { LSX_LOAI_BUOC_META, type LsxLoaiBuoc } from "../api/client";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import { dvNhan as dvNhanChung, type RefRow } from "./LsxRoutingTable";
import { num } from "./keHoachSxShared";
import {
  DON_VI_NANG_SUAT,
  type EditRow,
  n,
  phut,
  thoiLuong,
} from "./lsxBuoc";

const LOAI_BUOC_ORDER: LsxLoaiBuoc[] = ["may", "to", "thue_ngoai"];

/** Gom máy theo `loai_may`.
 *  Xưởng có ~24 máy đủ loại (bế, bồi, UV, cán, in) — đổ phẳng thì gán máy bế cho bước ghi kẽm
 *  cũng trôi. Nhóm KHÔNG chặn: vẫn chọn được máy bất kỳ, chỉ là mắt phải đi qua nhãn loại. */
function nhomMayTheoLoai(mayRefs: RefRow[]): { ten: string; items: RefRow[] }[] {
  const groups = new Map<string, RefRow[]>();
  for (const m of mayRefs) {
    const k = (m.nhom || "").trim() || "Chưa phân loại";
    const arr = groups.get(k);
    if (arr) arr.push(m);
    else groups.set(k, [m]);
  }
  return [...groups.entries()]
    .sort((a, b) => a[0].localeCompare(b[0], "vi"))
    .map(([ten, items]) => ({ ten, items }));
}

export function LsxBuocDrawer({
  row,
  index,
  tong,
  soLuongDat,
  buHaoThem,
  congDoanRefs,
  toRefs,
  mayRefs,
  vatTuRefs,
  phuThuocRefs,
  canUpdate,
  onPatch,
  onPatchLsx,
  onDoiCongDoan,
  onDoiTo,
  onClose,
  onPrev,
  onNext,
}: {
  row: EditRow;
  index: number;
  tong: number;
  soLuongDat: number;
  /** `lsx.bu_hao_to` — hao thêm của kế hoạch, cộng vào bước CUỐI (đơn vị theo bước đó). */
  buHaoThem: number;
  congDoanRefs: RefRow[] | null;
  toRefs: RefRow[] | null;
  mayRefs: RefRow[] | null;
  vatTuRefs: RefRow[] | null;
  phuThuocRefs: import("../api/client").LsxPhuThuocOption[];
  canUpdate: boolean;
  onPatch: (p: Partial<EditRow>) => void;
  /** Sửa thẳng CẤP LỆNH — chỉ bước CUỐI dùng: SL thành phẩm cần giao (`so_luong_dat`) và hao
   *  thêm của kế hoạch (`bu_hao_to`). Cả chuỗi phía trên tính ngược lại từ hai số này. */
  onPatchLsx?: (p: { so_luong_dat?: number; bu_hao_to?: number }) => void;
  /** Đổi công đoạn: kéo lại toàn bộ mặc định của công đoạn mới (giữ SL vào/ra). */
  onDoiCongDoan: (congDoanId: number | null) => void;
  onDoiTo: (departmentId: number | null) => void;
  onClose: () => void;
  onPrev: () => void;
  onNext: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const ngoai = row.loai_buoc === "thue_ngoai";
  const doiDonVi = !!row.don_vi_vao && !!row.don_vi_ra && row.don_vi_vao !== row.don_vi_ra;
  // Bước CUỐI là chỗ DUY NHẤT còn gõ số: SL thành phẩm cần giao + hao thêm. Bước không chạm giấy
  // (chế bản, đơn vị trống) không tính là bước cuối của dòng giấy.
  const laBuocCuoi = index === tong - 1 && !!row.don_vi_ra;
  const [slRaCuoi, setSlRaCuoi] = useState(String(soLuongDat ?? 0));
  const [haoThem, setHaoThem] = useState(String(buHaoThem ?? 0));
  useEffect(() => setSlRaCuoi(String(soLuongDat ?? 0)), [soLuongDat]);
  useEffect(() => setHaoThem(String(buHaoThem ?? 0)), [buHaoThem]);
  // Nhãn đơn vị dùng CHUNG với bảng routing — hai nơi tự viết là sớm muộn lệch chữ.
  const dvNhan = (dv: string | null | undefined) => dvNhanChung(dv, row.nhom);
  const t = useMemo(() => thoiLuong(row), [row]);
  const tg = row.thoi_luong_dien_giai;
  const nhomMay = useMemo(
    () => (mayRefs ? nhomMayTheoLoai(mayRefs) : []),
    [mayRefs],
  );
  // Khối "Máy thay thế" đã BỎ (mig 0142): nó là ghi chú tay không ai đọc — xếp lịch/Gantt không tra
  // tới. Việc "máy này kham nổi bài không" do `_may_fit.kiem_kha_nang` tự kiểm từ spec máy × quy
  // cách mỗi lần gán/kéo máy, không cần ai nhớ tick trước.

  // Đầu việc khoán chọn được: danh sách server gửi + giữ cả đầu việc ĐANG ghim dù nó không còn khớp
  // (đổi tổ ở bước, hoặc bảng khoán đã sửa) — mất khỏi dropdown là người dùng tưởng dữ liệu bay.
  const dsKhoan = useMemo(() => {
    const ds = [...row.khoan_chon_duoc];
    if (row.khoan_rate_id && !ds.some((k) => k.id === row.khoan_rate_id)) {
      ds.unshift({
        id: row.khoan_rate_id,
        ten: `(đang ghim) đầu việc #${row.khoan_rate_id}`,
        don_vi: "",
        don_gia: 0,
      });
    }
    return ds;
  }, [row.khoan_chon_duoc, row.khoan_rate_id]);
  const nhomPhuThuoc = useMemo(() => {
    const currentLsxId = phuThuocRefs.find((o) => o.step_key === row.key)?.lsx_id;
    const groups = new Map<number, typeof phuThuocRefs>();
    for (const option of phuThuocRefs.filter((o) => o.step_key !== row.key)) {
      groups.set(option.lsx_id, [...(groups.get(option.lsx_id) ?? []), option]);
    }
    return [...groups.entries()]
      .sort(([a], [b]) => a === currentLsxId ? -1 : b === currentLsxId ? 1 : a - b)
      .map(([lsxId, options]) => ({
        lsxId,
        label: `${options[0]?.lsx_ma ?? `LSX #${lsxId}`}${lsxId === currentLsxId ? " · hiện tại" : ""}`,
        options,
      }));
  }, [phuThuocRefs, row.key]);
  // Diễn giải tiền do SERVER tính cho lựa chọn lúc tải. Vừa đổi lựa chọn thì nó hết đúng → không
  // hiện số cũ (số cũ nhìn như số của việc mới), chỉ nhắc lưu để tính lại.
  const khoanConKhop = row.khoan_rate_id === row.khoan_rate_id_luc_tai;

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
              {/* Số lượng của MỌI bước là dẫn xuất của chuỗi ngược — server tính từ SL thành
                  phẩm của bước CUỐI đi ngược lên. Ô duy nhất gõ được nằm ở bước cuối. */}
              <div className="khsx-field">
                <span className="khsx-field__label">Số lượng vào</span>
                <p className="khsx-readonly">
                  {num(Number(row.so_luong_vao || 0))}{" "}
                  <span className="khsx-unit-tag">{dvNhan(row.don_vi_vao)}</span>
                </p>
              </div>
              <div className="khsx-field">
                <span className="khsx-field__label">
                  Số lượng ra
                  {laBuocCuoi && <span className="khsx-field__origin">gõ được</span>}
                </span>
                {laBuocCuoi ? (
                  <div className="khsx-inline">
                    <input
                      type="number"
                      min={1}
                      value={slRaCuoi}
                      disabled={!canUpdate}
                      onChange={(e) => setSlRaCuoi(e.target.value)}
                      onBlur={() => onPatchLsx?.({ so_luong_dat: Math.max(0, Number(slRaCuoi) || 0) })}
                    />
                    <span className="khsx-unit-tag">{dvNhan(row.don_vi_ra)}</span>
                  </div>
                ) : (
                  <p className="khsx-readonly">
                    {num(Number(row.so_luong_ra || 0))}{" "}
                    <span className="khsx-unit-tag">{dvNhan(row.don_vi_ra)}</span>
                  </p>
                )}
                <span className="khsx-field__hint">
                  {laBuocCuoi
                    ? "Số thành phẩm cần giao — cả chuỗi phía trên tính ngược từ đây."
                    : "Máy tính ngược từ SL thành phẩm của bước cuối."}
                </span>
              </div>

              {doiDonVi && (
                <div className="khsx-field">
                  <span className="khsx-field__label">Quy đổi đơn vị</span>
                  <p className="khsx-readonly">
                    1 {dvNhan(row.don_vi_vao)} = {num(Number(row.he_so_quy_doi || 1))}{" "}
                    {dvNhan(row.don_vi_ra)}
                  </p>
                  <span className="khsx-field__hint">
                    Hệ số lấy từ quy cách của lệnh (con/tờ · số mảnh xả) — không khai ở đây.
                  </span>
                </div>
              )}

              <div className="khsx-field">
                <span className="khsx-field__label">Hao hụt</span>
                <p className="khsx-readonly">
                  {Number(row.hao_hut || 0) > 0 || Number(row.hao_hut_pct || 0) > 0 ? (
                    <>
                      {Number(row.hao_hut || 0) > 0 && (
                        <>
                          {num(Number(row.hao_hut))}{" "}
                          <span className="khsx-unit-tag">{dvNhan(row.don_vi_vao)}</span>
                        </>
                      )}
                      {Number(row.hao_hut_pct || 0) > 0 && <> + {row.hao_hut_pct}%</>}
                    </>
                  ) : (
                    "—"
                  )}
                </p>
                <span className="khsx-field__hint">
                  Theo định mức bù hao khai ở danh mục công đoạn. Muốn đổi thì sửa ở đó
                  {laBuocCuoi ? "; riêng bước cuối có ô Hao thêm dưới đây." : "."}
                </span>
              </div>

              {laBuocCuoi && (
                <label className="khsx-field">
                  <span className="khsx-field__label">Hao thêm</span>
                  <div className="khsx-inline">
                    <input
                      type="number"
                      min={0}
                      value={haoThem}
                      disabled={!canUpdate}
                      onChange={(e) => setHaoThem(e.target.value)}
                      onBlur={() => onPatchLsx?.({ bu_hao_to: Math.max(0, Number(haoThem) || 0) })}
                    />
                    <span className="khsx-unit-tag">{dvNhan(row.don_vi_ra)}</span>
                  </div>
                  <span className="khsx-field__hint">
                    Kế hoạch cộng thêm khi biết ca này khó — cộng vào bước cuối rồi chảy ngược
                    lên thành số giấy.
                  </span>
                </label>
              )}
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
                          onDoiTo(e.target.value ? Number(e.target.value) : null)}
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
                  {row.loai_buoc === "to" && (
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
                        Chuẩn {row.so_nhan_cong_tieu_chuan}; hiệu quả tối đa {row.so_nhan_cong_toi_da ?? "—"} người.
                      </span>
                    </label>
                  )}
                  {/* CÔNG VIỆC KHOÁN của bước — nằm ở "Ai làm" vì nó đi liền tổ nhận việc. Ý nghĩa
                      lớn nhất không phải tiền mà là CHỈ VIỆC: lệnh nói rõ bước cán này làm *cán mờ*
                      hay *ghép metalize*, xưởng khỏi đoán. Danh sách do server lọc theo tổ + công
                      đoạn (đã áp luật "ưu tiên dòng khai riêng") nên đây chỉ render. */}
                  {(row.khoan_chon_duoc.length > 0 || row.khoan_rate_id != null) && (
                    <label className="khsx-field khsx-field--wide">
                      <span className="khsx-field__label">
                        Công việc khoán
                        <span className="khsx-field__origin">bảng khoán của tổ</span>
                      </span>
                      <select
                        value={row.khoan_rate_id ?? ""}
                        disabled={!canUpdate}
                        onChange={(e) =>
                          set("khoan_rate_id", e.target.value ? Number(e.target.value) : null)}
                      >
                        <option value="">— chưa chọn —</option>
                        {dsKhoan.map((k) => (
                          <option key={k.id} value={k.id}>
                            {k.don_vi ? `${k.ten} — ${num(k.don_gia)} đ/${k.don_vi}` : k.ten}
                          </option>
                        ))}
                      </select>
                      {/* Ba số một dòng: SL bước → SL đã quy đổi → tiền. Không quy đổi được thì nói
                          THIẾU GÌ, tuyệt đối không hiện số đoán (số đoán chảy thẳng vào tiền công). */}
                      {!khoanConKhop ? (
                        <span className="khsx-field__hint">
                          Lưu công đoạn để tính lại tiền công theo đầu việc vừa chọn.
                        </span>
                      ) : row.khoan_dien_giai ? (
                        <span className="khsx-khoan__ok">{row.khoan_dien_giai}</span>
                      ) : row.khoan_ly_do ? (
                        <span className="khsx-khoan__thieu">{row.khoan_ly_do}</span>
                      ) : row.khoan_chon_duoc.length > 1 ? (
                        <span className="khsx-field__hint">
                          Tổ này có {row.khoan_chon_duoc.length} đầu việc cho công đoạn — chọn đúng
                          việc thợ sẽ làm để ra tiền công.
                        </span>
                      ) : null}
                    </label>
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

          <Nhom title="Vật tư cần dùng">
            <p className="khsx-nhom__sub">Khai nhu cầu của riêng bước này từ Danh mục vật tư in ấn.</p>
            <div className="khsx-form">
              {row.vat_tus.map((v, i) => (
                <div className="khsx-field khsx-field--wide" key={v.vat_tu_id}>
                  <span className="khsx-field__label">{v.vat_tu_ma} · {v.vat_tu_ten}</span>
                  <div className="khsx-inline">
                    <input type="number" min="0.001" step="any" value={v.so_luong} disabled={!canUpdate}
                      onChange={(e) => set("vat_tus", row.vat_tus.map((x, j) => j === i ? { ...x, so_luong: e.target.value } : x))} />
                    <span className="khsx-kv__val">{v.don_vi}</span>
                    {canUpdate && <button type="button" className="khsx-xlink"
                      onClick={() => set("vat_tus", row.vat_tus.filter((_, j) => j !== i))}>Bỏ</button>}
                  </div>
                </div>
              ))}
              {canUpdate && vatTuRefs && (
                <label className="khsx-field khsx-field--wide">
                  <span className="khsx-field__label">Thêm vật tư</span>
                  <select value="" onChange={(e) => {
                    const item = vatTuRefs.find((v) => v.id === Number(e.target.value));
                    if (item && !row.vat_tus.some((v) => v.vat_tu_id === item.id)) {
                      set("vat_tus", [...row.vat_tus, { vat_tu_id: item.id, vat_tu_ma: item.ma ?? "", vat_tu_ten: item.ten, don_vi: item.donVi ?? "", so_luong: "" }]);
                    }
                  }}>
                    <option value="">— chọn từ danh mục —</option>
                    {vatTuRefs.filter((x) => !row.vat_tus.some((v) => v.vat_tu_id === x.id)).map((x) =>
                      <option key={x.id} value={x.id}>{x.ma} · {x.ten} ({x.donVi})</option>)}
                  </select>
                </label>
              )}
            </div>
          </Nhom>

          <Nhom title="Phụ thuộc để xếp lịch">
            <p className="khsx-nhom__sub">Bước này chỉ bắt đầu sau khi tất cả tiền nhiệm đã hoàn thành.</p>
            <div className="khsx-cond">
              {nhomPhuThuoc.map((group) => (
                <fieldset className="khsx-dep-group" key={group.lsxId}>
                  <legend>{group.label}</legend>
                  {group.options.map((o) => (
                    <label key={o.step_key} className="khsx-cond__item">
                      <input type="checkbox" disabled={!canUpdate}
                        checked={row.phu_thuoc_step_keys.includes(o.step_key)}
                        onChange={(e) => set("phu_thuoc_step_keys", e.target.checked
                          ? [...row.phu_thuoc_step_keys, o.step_key]
                          : row.phu_thuoc_step_keys.filter((k) => k !== o.step_key))} />
                      <span>{o.ten_buoc}</span>
                    </label>
                  ))}
                </fieldset>
              ))}
              {nhomPhuThuoc.length === 0 && <span className="khsx-field__hint">Chưa có bước khác trong đơn hàng.</span>}
            </div>
          </Nhom>

          {/* --- Năng suất & thời gian --- */}
          <Nhom title="Mất bao lâu">
            <div className="khsx-form">
              <label className="khsx-field">
                <span className="khsx-field__label">Chuẩn bị (phút)</span>
                <input
                  type="number"
                  value={row.setup_phut}
                  placeholder="0"
                  disabled={!canUpdate}
                  onChange={(e) => set("setup_phut", e.target.value)}
                />
              </label>
              {row.loai_buoc === "may" && (
                <label className="khsx-field">
                  <span className="khsx-field__label">Số lượt chạy qua máy</span>
                  <input type="number" min="1" value={row.so_luot_chay} placeholder="1"
                    disabled={!canUpdate} onChange={(e) => set("so_luot_chay", e.target.value)} />
                </label>
              )}
              <label className="khsx-field">
                <span className="khsx-field__label">Năng suất kế hoạch</span>
                <div className="khsx-inline">
                  <input
                    type="number"
                    value={row.nang_suat}
                    placeholder="—"
                    disabled
                  />
                  <select
                    className="khsx-inline__unit"
                    value={row.don_vi_nang_suat}
                    disabled
                    aria-label="Đơn vị năng suất"
                  >
                    <option value="">— đơn vị —</option>
                    {DON_VI_NANG_SUAT.map((u) => (
                      <option key={u.key} value={u.key}>{u.label}</option>
                    ))}
                  </select>
                </div>
                <span className="khsx-field__hint">
                  {row.loai_buoc === "may"
                    ? "Kế thừa từ máy được chọn."
                    : row.loai_buoc === "to"
                      ? "Kế thừa từ định mức của đầu việc."
                      : "Không áp dụng cho bước thuê ngoài."}
                </span>
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
              {Array.isArray(tg.canh_bao) && tg.canh_bao.map((warning) => (
                <div className="khsx-alert" key={String(warning)}>{String(warning)}</div>
              ))}
              {Number(tg.nang_suat_hieu_dung ?? 0) > 0 && (
                <div className="khsx-tinh__row">
                  <span className="khsx-tinh__label">Công thức chạy</span>
                  <span className="khsx-tinh__note">
                    {num(Number(tg.so_luong_vao ?? 0))} {String(tg.don_vi_vao ?? "")}
                    {row.loai_buoc === "may" ? ` × ${Number(tg.so_luot_chay ?? 1)} lượt` : ""}
                    {row.loai_buoc === "to" ? ` ÷ ${num(Number(tg.nang_suat_co_so ?? 0))}/người/giờ × ${Number(tg.so_nhan_cong_tinh ?? 1)} người` : ` ÷ ${num(Number(tg.nang_suat_hieu_dung ?? 0))}/giờ`}
                    {` × 60 = ${num(Number(tg.chay_phut ?? 0))} phút`}
                  </span>
                </div>
              )}
              <div className="khsx-tinh__row">
                <span className="khsx-tinh__label">Chiếm máy / tổ</span>
                <span className="khsx-tinh__val khsx-dur">{phut(t.chiemMay)}</span>
                <span className="khsx-tinh__note">
                  {num(Number(tg.setup_phut ?? 0))} chuẩn bị + {num(Number(tg.chay_phut ?? 0))} chạy +{" "}
                  {num(Number(tg.ve_sinh_phut ?? 0))} vệ sinh
                </span>
              </div>
              <div className="khsx-tinh__row khsx-tinh__row--total">
                <span className="khsx-tinh__label">Tổng thời gian dẫn</span>
                <span className="khsx-tinh__val khsx-dur">{phut(t.tong)}</span>
                <span className="khsx-tinh__note">
                  {Number(tg.cho_phut ?? 0) > 0 || Number(tg.di_chuyen_phut ?? 0) > 0
                    ? `thêm ${num(Number(tg.cho_phut ?? 0))} chờ + ${num(Number(tg.di_chuyen_phut ?? 0))} di chuyển — hai khoản này KHÔNG chiếm máy`
                    : "không có chờ / di chuyển"}
                </span>
              </div>
              {canUpdate && <p className="khsx-field__hint">Sửa số rồi lưu công đoạn để backend tính và cập nhật diễn giải.</p>}
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

// `DonViChon` đã BỎ: đơn vị vào/ra khai MỘT CHỖ ở danh mục công đoạn, lệnh chỉ kế thừa và hiển
// thị. Cho chọn lại ở đây là đẻ nguồn sự thật thứ hai, và cũng vô nghĩa — đơn vị là bản chất
// của công đoạn (bế luôn là tờ in → con), không đổi theo từng đơn hàng.
