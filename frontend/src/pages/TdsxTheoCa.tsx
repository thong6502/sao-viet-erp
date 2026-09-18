// Tab THEO CA của màn "Theo dõi sản xuất" (Task 18b, Bước W1) — công việc rơi vào từng ca của MỘT
// ngày xưởng đang xem.
//
// BỐN hành vi của `ca_id` PHẢI render KHÁC NHAU (task-18b-brief.md bảng W1) — không cần state đặc
// biệt cho từng ca, vì hình dạng `TdsxTheoCaOut.ca` mà máy chủ trả đã tự phân biệt:
//   · không chọn ca      → `ca` gồm MỌI ca thật + rổ "Ngoài ca" (id=null) đứng CUỐI.
//   · id một ca thật     → `ca` có ĐÚNG 1 phần tử (ca đó); phần tử ấy có thể `viec: []`, render ra
//                          y hệt một ca-rỗng bình thường (mỗi CA tự nói "Không có việc nào trong ca
//                          này." — không phải một khối lỗi).
//   · `"ngoai_ca"`       → `ca` có ĐÚNG 1 phần tử (rổ Ngoài ca, tên "Ngoài ca"); rỗng thì HIỆN
//                          header "Ngoài ca" + thân "Không có việc nào trong ca này." — câu này
//                          KHÁC hẳn câu bên dưới vì nó có TÊN CA đi kèm.
//   · id lạ / ca đã xoá  → `ca: []` (mảng RỖNG) → tab hiện MỘT EmptyState cấp toàn tab "Không tìm
//                          thấy ca này." — không phải "không có ca nào", và không có phần tử ca nào
//                          để vẽ header, nên tự nhiên KHÁC câu ở trên.
// Bốn nhánh này không cần if/else riêng ở FE — cứ vẽ đúng những gì `ca` mang là đủ tách bạch.
//
// Giới hạn API cũ ĐÃ GỠ (vòng rà UI 2026-09-04): `CaViecOut.lsx` nay mang danh sách lệnh của công
// việc, nên dòng việc bấm-mở-hồ-sơ được y như Kanban/Theo máy — 1 lệnh mở thẳng, ≥2 lệnh bày
// popover chọn (C123, dùng chung `tdsxChonLenh.tsx` với tab Theo máy).
//
// Ca đêm nhận diện bằng CỜ `qua_nua_dem` — CẤM dò theo `ten` (Ruling C116: xưởng khác gọi ca đêm
// là "Ca tối"/"Ca C").
import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";

import { ApiError, api } from "../api/client";
import type { TdsxBoLocMuc, TdsxCa, TdsxCaViec, TdsxLsxThamChieu, TdsxThanhLocParams } from "../api/client";
import { Button } from "../components/Button";
import { ChipKhuon, ChipLoaiBuoc, nhanKhuon } from "../components/ChipBuoc";
import { Icon } from "../components/Icons";
import { EmptyState, num } from "./keHoachSxShared";
import { ChonLenhPopover, useChonLenh } from "./tdsxChonLenh";
import { tdsxTtMeta } from "./TdsxKanban";

/** Sentinel `ca_id` cho rổ "Ngoài ca" — ĐÚNG chuỗi `bang_theo_doi.CA_ID_NGOAI_CA` phía máy chủ. */
const CA_ID_NGOAI_CA = "ngoai_ca";

function padNum(n: number): string {
  return String(n).padStart(2, "0");
}

function toDateStr(d: Date): string {
  return `${d.getFullYear()}-${padNum(d.getMonth() + 1)}-${padNum(d.getDate())}`;
}

function homNay(): string {
  return toDateStr(new Date());
}

/** Ô `<input type="date">` có thể đẻ năm > 4 chữ số khi gõ dở (bẫy đã dính ở `LenhSanXuatPage`) —
 *  máy chủ trả 422 CÂM cho giá trị đó. Chặn Ở FE: ngày sai thì KHÔNG gọi API, viền cảnh báo. */
function ngayHopLe(v: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(v)) return false;
  const nam = Number(v.slice(0, 4));
  if (nam < 2000 || nam > 2999) return false;
  return !Number.isNaN(new Date(v).getTime());
}

function doiNgay(v: string, delta: number): string {
  const d = new Date(`${v}T00:00:00`);
  d.setDate(d.getDate() + delta);
  return toDateStr(d);
}

function phutToHhmm(p: number): string {
  const h = Math.floor(p / 60) % 24;
  const m = p % 60;
  return `${padNum(h)}:${padNum(m)}`;
}

function khungGio(ca: TdsxCa): string | null {
  if (ca.bat_dau_phut == null || ca.ket_thuc_phut == null) return null;
  return `${phutToHhmm(ca.bat_dau_phut)}–${phutToHhmm(ca.ket_thuc_phut)}${ca.qua_nua_dem ? " (qua đêm)" : ""}`;
}

function gioTrongNgay(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

/** Mốc ngắn cho dòng việc: cùng ngày đang xem thì chỉ giờ, khác ngày thì kèm `dd/MM` — việc chạy
 *  sớm/trễ so với kế hoạch mà chỉ ghi giờ thì người xem không biết mốc đó thuộc hôm nào. Máy chủ trả
 *  ISO giờ xưởng KHÔNG offset nên 10 ký tự đầu chính là ngày xưởng. */
function mocNgan(iso: string, ngayStr: string): string {
  const gio = gioTrongNgay(iso);
  if (iso.slice(0, 10) === ngayStr) return gio;
  return `${iso.slice(8, 10)}/${iso.slice(5, 7)} ${gio}`;
}

const NHAN_LECH_LICH = { som: "sớm lịch", tre: "trễ lịch" } as const;

function nguoiText(nguoi: string[]): { text: string; full: string | undefined } {
  if (nguoi.length === 0) return { text: "Chưa gán người", full: undefined };
  if (nguoi.length <= 2) return { text: nguoi.join(", "), full: undefined };
  return { text: `${nguoi.length} người`, full: nguoi.join(", ") };
}

export function TdsxTheoCa({
  active,
  token,
  params,
  refreshTick,
  caFacet,
  onOpenHoSo,
  onXoaLoc,
  khay,
}: {
  active: boolean;
  token: string | null;
  params: TdsxThanhLocParams;
  refreshTick: number;
  /** Nguồn ô chọn Ca — `BoLocOut.ca` do trang cha tải (nạp cùng nhịp với 8 tham số lọc chung). */
  caFacet: TdsxBoLocMuc[];
  /** Mở lớp phủ hồ sơ đúng lệnh — bấm một dòng việc. Cùng chữ ký với Kanban/Theo máy. */
  onOpenHoSo: (lsxId: number) => void;
  onXoaLoc: () => void;
  /** Khay điều khiển trên dải tab — xem ghi chú cùng tên ở `TdsxKanban`. */
  khay: HTMLElement | null;
}) {
  const [ngay, setNgay] = useState(homNay);
  const [caIdRaw, setCaIdRaw] = useState("");
  // Chuỗi THÔ người dùng đang gõ ở ô "Mã ca khác" — tách khỏi `caIdRaw` (giá trị đã ÁP DỤNG, dùng
  // để gọi API + đồng bộ select). Áp mỗi phím bấm từng cắn nhánh: gõ "2" trùng Ca 1 khiến ô tự rỗng
  // lại (Ca 1 giờ hiện qua select, không qua ô này) rồi gõ tiếp "3" thành "3" (không phải "23") và
  // trúng ngay Ca 2 — một ca THẬT khác hẳn, im lặng không báo (vòng sửa 1, mục B1). Giờ chỉ áp vào
  // `caIdRaw` lúc rời ô/bấm Enter, đang gõ dở không đụng gì tới select hay API.
  const [maCaKhacDraft, setMaCaKhacDraft] = useState("");
  const [caList, setCaList] = useState<TdsxCa[]>([]);
  const [loading, setLoading] = useState(true);
  const [daTai, setDaTai] = useState(false);
  const [loi, setLoi] = useState<{ text: string; cam: boolean } | null>(null);
  const [picker, moPicker, dongPicker] = useChonLenh();

  // Trống (chưa gõ gì) khác SAI (gõ nhưng sai định dạng/ngoài khoảng `min`/`max`) — hai thông báo
  // khác nhau (vòng sửa 1, mục D#1: trước đây dùng chung câu "Ngày không hợp lệ" cho cả ô trống,
  // gọi sai tình huống, đúng khuôn lỗi "phân biệt trống vs sai" repo đã dính ở LenhSanXuatPage).
  const ngayRong = ngay.trim() === "";
  const ngaySai = !ngayRong && !ngayHopLe(ngay);
  const ngayKhongXemDuoc = ngayRong || ngaySai;

  const load = useCallback(() => {
    if (!token || ngayKhongXemDuoc) return;
    setLoading(true);
    api.theoDoiSanXuat
      .theoCa(token, { ...params, ngay, ca_id: caIdRaw || undefined })
      .then((r) => {
        setCaList(r.ca);
        setLoi(null);
        setDaTai(true);
      })
      .catch((e) => {
        const cam = e instanceof ApiError && e.isForbidden;
        setLoi({
          text: cam
            ? "Bạn không có quyền xem Theo dõi sản xuất."
            : "Không tải được bảng Theo dõi sản xuất. Kiểm tra mạng rồi thử lại.",
          cam,
        });
      })
      .finally(() => setLoading(false));
  }, [token, params, ngay, caIdRaw, ngayKhongXemDuoc]);

  useEffect(() => {
    if (!active) return;
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, load, refreshTick]);

  // Giá trị "biết" của ca select — id thật (chuỗi) hoặc sentinel "ngoai_ca". `caIdRaw` mang một mã
  // KHÔNG nằm trong tập này (gõ tay ở ô "Mã ca khác") thì select tự lùi về "Tất cả ca".
  const biet = useMemo(() => new Set([...caFacet.map((c) => c.id), CA_ID_NGOAI_CA]), [caFacet]);
  const caSelectValue = caIdRaw !== "" && biet.has(caIdRaw) ? caIdRaw : "";

  /** Chốt chuỗi đang gõ ở ô "Mã ca khác" vào `caIdRaw` (bấm Enter hoặc rời ô). Khớp một ca THẬT thì
   *  dọn ô về rỗng để nhường chỗ cho select hiển thị đúng ca đó — KHÔNG dọn khi mã lạ, để còn đọc lại
   *  được cái vừa gõ và ra đúng nhánh "Không tìm thấy ca này". */
  function apMaCaKhac() {
    const ma = maCaKhacDraft.trim();
    setCaIdRaw(ma);
    if (ma !== "" && biet.has(ma)) setMaCaKhacDraft("");
  }

  const dangLoc = Object.values(params).some((v) => v !== undefined);
  const khongTimThayCa = daTai && !loi && caList.length === 0;
  /** Có ca nhưng CẢ NGÀY không việc nào. Khác hẳn "không tìm thấy ca" và khác hẳn lỗi tải — mà
   *  màn cũ bày ba dòng "Không có công việc nào được xếp trong ca này" giống hệt nhau trên một
   *  mặt bàn cao bằng màn hình, nên người xem không biết là ngày rỗng thật hay bảng hỏng. */
  const khongCoViecNao = daTai && !loi && caList.length > 0 && caList.every((c) => c.viec.length === 0);

  return (
    <div className="tdsx-tc" aria-label="Bảng theo ca" role="group">
      {/* Ngày + ca lên dải tab. Dòng "Đang áp bộ lọc chung của cả màn · Xóa bộ lọc" đã bỏ: viên lọc
          ở hàng trên tự sẫm lại khi có giá trị, và nút "Xóa bộ lọc" đứng ngay cạnh chúng. */}
      {active &&
        khay &&
        createPortal(
          <>
            <span className="hslsx__field">
              <span className="hslsx__field-lb">Ngày</span>
              <span className="hslsx__daterow">
                <button
                  type="button"
                  className="tdsx-tc__daybtn"
                  onClick={() => setNgay((v) => (ngayHopLe(v) ? doiNgay(v, -1) : homNay()))}
                  aria-label="Lùi một ngày"
                  title="Lùi một ngày"
                >
                  <Icon name="chevron" size={14} />
                </button>
                <input
                  type="date"
                  value={ngay}
                  min="2000-01-01"
                  max="2999-12-31"
                  className={ngaySai ? "is-sai" : ""}
                  onChange={(e) => setNgay(e.target.value)}
                  aria-label="Ngày xem"
                />
                <button
                  type="button"
                  className="tdsx-tc__daybtn tdsx-tc__daybtn--sau"
                  onClick={() => setNgay((v) => (ngayHopLe(v) ? doiNgay(v, 1) : homNay()))}
                  aria-label="Tới một ngày"
                  title="Tới một ngày"
                >
                  <Icon name="chevron" size={14} />
                </button>
              </span>
            </span>

            {ngay !== homNay() && (
              <button type="button" className="hslsx__linkbtn" onClick={() => setNgay(homNay())}>
                Hôm nay
              </button>
            )}

            <label className="hslsx__field">
              <span className="hslsx__field-lb">Ca</span>
              <select
                value={caSelectValue}
                onChange={(e) => {
                  setCaIdRaw(e.target.value);
                  setMaCaKhacDraft("");
                }}
              >
                <option value="">Tất cả ca</option>
                {caFacet.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.ten}
                  </option>
                ))}
                <option value={CA_ID_NGOAI_CA}>Ngoài ca</option>
              </select>
            </label>

            <label className="hslsx__field tdsx-tc__macakhac">
              <span className="hslsx__field-lb">Mã ca khác</span>
              <input
                type="number"
                min={1}
                placeholder="Nhập mã ca"
                value={maCaKhacDraft}
                onChange={(e) => setMaCaKhacDraft(e.target.value)}
                onBlur={apMaCaKhac}
                onKeyDown={(e) => {
                  if (e.key !== "Enter") return;
                  apMaCaKhac();
                  (e.target as HTMLInputElement).blur();
                }}
              />
            </label>

            {ngayRong && <span className="tdsx__ctlwarn">Chưa nhập ngày — gõ ngày để xem việc trong ca.</span>}
            {ngaySai && <span className="tdsx__ctlwarn">Ngày không hợp lệ — sửa lại rồi thử tiếp.</span>}
          </>,
          khay,
        )}

      {loi && (
        <EmptyState
          icon="alert"
          title={loi.text}
          action={
            loi.cam ? undefined : (
              <Button variant="ghost" onClick={load}>
                Tải lại
              </Button>
            )
          }
        />
      )}

      {!loi && khongTimThayCa && (
        <EmptyState
          icon="search"
          title="Không tìm thấy ca này."
          sub="Mã ca không còn trong danh mục, hoặc đã gõ nhầm — chọn lại ở ô Ca phía trên."
        />
      )}

      {!loi && !daTai && (
        <div className="tdsx-tc__list">
          {Array.from({ length: 2 }).map((_, i) => (
            <div className="tdsx-tc__ca" key={i}>
              <span className="khsx-skel__bar" style={{ width: 140 }} />
              <span className="khsx-skel__bar" style={{ width: 240, marginTop: 8 }} />
            </div>
          ))}
        </div>
      )}

      {!loi && daTai && !khongTimThayCa && (
        // `ngayKhongXemDuoc` cũng làm mờ danh sách: ô Ngày trống/sai thì `load()` thoát sớm, danh
        // sách hiện đang bày vẫn là của lần xem HỢP LỆ gần nhất — mờ nó đi để khỏi trông như còn
        // đúng (vòng sửa 1, mục D#1: trước đây xoá ô Ngày thì 6 việc cũ vẫn sáng rõ như thường).
        <div className={`tdsx-tc__list${loading || ngayKhongXemDuoc ? " is-mo" : ""}`}>
          {khongCoViecNao && (
            <p className="tdsx-tc__trongngay">
              Ngày này không có việc nào — không việc nào xếp kế hoạch, cũng không việc nào chạy thật.
              Bảng vẫn tải bình thường.
              {dangLoc ? (
                <>
                  {" "}
                  Bộ lọc chung của màn đang áp.{" "}
                  <button type="button" className="hslsx__linkbtn" onClick={onXoaLoc}>
                    Xóa bộ lọc
                  </button>
                </>
              ) : (
                " Bấm mũi tên cạnh ô Ngày để xem ngày khác."
              )}
            </p>
          )}
          {caList.map((ca) => (
            <CaSection
              key={ca.id ?? "ngoai"}
              ca={ca}
              ngayStr={ngay}
              dangLoc={dangLoc}
              onXoaLoc={onXoaLoc}
              onOpenHoSo={onOpenHoSo}
              onChon={moPicker}
            />
          ))}
        </div>
      )}

      {picker && <ChonLenhPopover state={picker} onDong={dongPicker} onChon={onOpenHoSo} nhan="Việc" />}
    </div>
  );
}

function checkShiftActive(ca: TdsxCa, ngayStr: string): boolean {
  if (ngayStr !== homNay()) return false;
  if (ca.bat_dau_phut == null || ca.ket_thuc_phut == null) return false;
  const now = new Date();
  const nowPhut = now.getHours() * 60 + now.getMinutes();

  if (ca.qua_nua_dem) {
    if (ca.bat_dau_phut <= ca.ket_thuc_phut) {
      return nowPhut >= ca.bat_dau_phut && nowPhut <= ca.ket_thuc_phut;
    }
    return nowPhut >= ca.bat_dau_phut || nowPhut <= ca.ket_thuc_phut;
  }
  return nowPhut >= ca.bat_dau_phut && nowPhut <= ca.ket_thuc_phut;
}

function getShiftProgress(ca: TdsxCa): number | null {
  if (ca.bat_dau_phut == null || ca.ket_thuc_phut == null) return null;
  const now = new Date();
  const nowPhut = now.getHours() * 60 + now.getMinutes();

  let start = ca.bat_dau_phut;
  let end = ca.ket_thuc_phut;
  if (ca.qua_nua_dem && end < start) {
    end += 1440;
  }
  let current = nowPhut;
  if (ca.qua_nua_dem && current < start) {
    current += 1440;
  }

  const duration = end - start;
  if (duration <= 0) return null;
  const elapsed = current - start;
  const pct = Math.max(0, Math.min(100, Math.round((elapsed / duration) * 100)));
  return pct;
}

function CaSection({
  ca,
  ngayStr,
  dangLoc,
  onXoaLoc,
  onOpenHoSo,
  onChon,
}: {
  ca: TdsxCa;
  ngayStr: string;
  dangLoc: boolean;
  onXoaLoc: () => void;
  onOpenHoSo: (lsxId: number) => void;
  onChon: (ds: TdsxLsxThamChieu[], x: number, y: number) => void;
}) {
  const [expanded, setExpanded] = useState(ca.viec.length > 0);
  const khung = khungGio(ca);
  const isActive = checkShiftActive(ca, ngayStr);
  const hasViec = ca.viec.length > 0;
  const progressPct = isActive ? getShiftProgress(ca) : null;

  return (
    <section
      className={`tdsx-tc__ca${isActive ? " is-active-shift" : ""}${!hasViec && !expanded ? " is-compact-empty" : ""}`}
      aria-label={`Ca ${ca.ten}`}
    >
      <header
        className="tdsx-tc__cahead"
        onClick={() => {
          if (!hasViec) setExpanded((v) => !v);
        }}
        style={{ cursor: !hasViec ? "pointer" : "default" }}
      >
        <div className="tdsx-tc__cahead-left">
          <span className="tdsx-tc__caten">{ca.ten}</span>
          {khung && <span className="tdsx-tc__cakhung">{khung}</span>}
          {isActive && (
            <span className="tdsx-tc__live-badge">
              <span className="tdsx-live-dot" />
              đang diễn ra{progressPct != null ? ` ${progressPct}%` : ""}
            </span>
          )}
        </div>
        <div className="tdsx-tc__cahead-right">
          <span className={`tdsx-tc__can${hasViec ? " is-has-viec" : ""}`}>
            {num(ca.viec.length)} việc
          </span>
          {!hasViec && (
            <span className="tdsx-tc__toggle-icon">
              <Icon name="chevron" size={14} />
            </span>
          )}
        </div>
      </header>
      {isActive && progressPct != null && (
        <div className="tdsx-tc__progress-track" title={`Tiến độ ca: ${progressPct}%`}>
          <div className="tdsx-tc__progress-fill" style={{ width: `${progressPct}%` }} />
        </div>
      )}
      {(hasViec || expanded) && (
        <div className="tdsx-tc__body">
          {ca.viec.length === 0 ? (
            <p className="tdsx-tc__empty-slot">
              Ca này không có việc nào theo kế hoạch hay chạy thật.
              {dangLoc && (
                <>
                  {" "}
                  Bộ lọc chung của màn đang áp.{" "}
                  <button type="button" className="hslsx__linkbtn" onClick={onXoaLoc}>
                    Xóa bộ lọc
                  </button>
                </>
              )}
            </p>
          ) : (
            ca.viec.map((v) => (
              <ViecRow key={v.cong_viec_id} viec={v} ngayStr={ngayStr} onOpenHoSo={onOpenHoSo} onChon={onChon} />
            ))
          )}
        </div>
      )}
    </section>
  );
}

function ViecRow({
  viec,
  ngayStr,
  onOpenHoSo,
  onChon,
}: {
  viec: TdsxCaViec;
  ngayStr: string;
  onOpenHoSo: (lsxId: number) => void;
  onChon: (ds: TdsxLsxThamChieu[], x: number, y: number) => void;
}) {
  const meta = tdsxTtMeta(viec.trang_thai);
  const nguoi = nguoiText(viec.nguoi);
  const nhieuLenh = viec.lsx.length >= 2;
  const maChinh = viec.lsx[0]?.ma ?? null;
  const keHoach = viec.du_kien_bat_dau ? mocNgan(viec.du_kien_bat_dau, ngayStr) : null;
  const giaiThichLech =
    viec.lech_lich === "som"
      ? `Chạy trước ngày kế hoạch${keHoach ? ` (dự kiến ${keHoach})` : ""}`
      : viec.lech_lich === "tre"
        ? viec.bat_dau_thuc_te
          ? `Chạy sau ngày kế hoạch${keHoach ? ` (dự kiến ${keHoach})` : ""}`
          : "Đã quá giờ bắt đầu dự kiến mà chưa chạy"
        : undefined;

  function bam(e: React.MouseEvent<HTMLButtonElement>) {
    if (viec.lsx.length === 0) return;
    if (viec.lsx.length === 1) {
      onOpenHoSo(viec.lsx[0].lsx_id);
      return;
    }
    const r = e.currentTarget.getBoundingClientRect();
    onChon(viec.lsx, r.left, r.bottom + 4);
  }

  return (
    <button
      type="button"
      className={`tdsx-tc__viec tdsx-tc__viec--${viec.trang_thai ?? "released"}`}
      onClick={bam}
      disabled={viec.lsx.length === 0}
      title={
        nhieuLenh
          ? `${viec.lsx.map((l) => l.ma).join(", ")} — bấm để chọn lệnh`
          : maChinh
            ? `${maChinh} — bấm để mở hồ sơ lệnh`
            : "Việc này chưa gắn lệnh nào"
      }
    >
      <div className="tdsx-tc__viecrow1">
        <span className="tdsx-tc__vma">{nhieuLenh ? `${maChinh} +${viec.lsx.length - 1}` : (maChinh ?? "—")}</span>
        <span className="tdsx-tc__vten">{viec.ten ?? "—"}</span>
        <span className={`tdsx-tt ${meta.cls}`}>
          <i aria-hidden="true" />
          {meta.label}
        </span>
        {viec.lech_lich && (
          <span className={`tdsx-tc__lech tdsx-tc__lech--${viec.lech_lich}`} title={giaiThichLech}>
            {NHAN_LECH_LICH[viec.lech_lich]}
          </span>
        )}
      </div>
      {/* Máy · người · giờ gộp thành MỘT dòng chữ nhỏ. Trước đây mỗi mẩu là một viên có viền + nền +
          icon riêng: ba khung cho ba mẩu chữ ngắn, trong khi hai chip thật sự mang nhãn nghiệp vụ
          (thuê ngoài / khuôn) lại chìm nghỉm giữa chúng. Việc đã chạy ghi thêm giờ chạy thật, vì
          máy chủ xếp nó vào ca theo giờ đó chứ không theo giờ dự kiến. */}
      <div className="tdsx-tc__viecrow2">
        <span className="tdsx-tc__vphu" title={nguoi.full ?? viec.may ?? undefined}>
          {[
            viec.may,
            nguoi.text,
            viec.bat_dau_thuc_te ? `chạy từ ${mocNgan(viec.bat_dau_thuc_te, ngayStr)}` : null,
            keHoach ? `dự kiến ${keHoach}` : null,
          ]
            .filter(Boolean)
            .join(" · ")}
        </span>
        <ChipLoaiBuoc loai_buoc={viec.nhan?.loai_buoc} nha_cung_cap={viec.nhan?.nha_cung_cap} />
        <ChipKhuon can_khuon={!!viec.nhan?.khuon_ma} khuon={nhanKhuon(viec.nhan)} />
      </div>
    </button>
  );
}
