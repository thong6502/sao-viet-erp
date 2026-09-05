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

  return (
    <div className="tdsx-tc" aria-label="Bảng theo ca" role="group">
      <div className="tdsx-tc__toolbar">
        <div className="hslsx__field">
          <span className="hslsx__field-lb">Ngày</span>
          <div className="hslsx__daterow">
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
            {ngay !== homNay() && (
              <button type="button" className="hslsx__linkbtn" onClick={() => setNgay(homNay())}>
                Hôm nay
              </button>
            )}
          </div>
          {ngayRong && <span className="hslsx__hint">Chưa nhập ngày — gõ ngày để xem việc trong ca.</span>}
          {ngaySai && <span className="hslsx__hint">Ngày không hợp lệ — sửa lại rồi thử tiếp.</span>}
        </div>

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
      </div>

      {dangLoc && (
        <p className="tdsx-tc__locbao">
          Đang áp bộ lọc chung của cả màn.{" "}
          <button type="button" className="hslsx__linkbtn" onClick={onXoaLoc}>
            Xóa bộ lọc
          </button>
        </p>
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
          {caList.map((ca) => (
            <CaSection key={ca.id ?? "ngoai"} ca={ca} onOpenHoSo={onOpenHoSo} onChon={moPicker} />
          ))}
        </div>
      )}

      {picker && <ChonLenhPopover state={picker} onDong={dongPicker} onChon={onOpenHoSo} nhan="Việc" />}
    </div>
  );
}

function CaSection({
  ca,
  onOpenHoSo,
  onChon,
}: {
  ca: TdsxCa;
  onOpenHoSo: (lsxId: number) => void;
  onChon: (ds: TdsxLsxThamChieu[], x: number, y: number) => void;
}) {
  const khung = khungGio(ca);
  return (
    <section className="tdsx-tc__ca" aria-label={`Ca ${ca.ten}`}>
      <header className="tdsx-tc__cahead">
        <span className="tdsx-tc__caten">{ca.ten}</span>
        {khung && <span className="tdsx-tc__cakhung">{khung}</span>}
        <span className="tdsx-tc__can">{num(ca.viec.length)} việc</span>
      </header>
      <div className="tdsx-tc__body">
        {ca.viec.length === 0 ? (
          <p className="tdsx-tc__rong">Không có việc nào trong ca này.</p>
        ) : (
          ca.viec.map((v) => (
            <ViecRow key={v.cong_viec_id} viec={v} onOpenHoSo={onOpenHoSo} onChon={onChon} />
          ))
        )}
      </div>
    </section>
  );
}

function ViecRow({
  viec,
  onOpenHoSo,
  onChon,
}: {
  viec: TdsxCaViec;
  onOpenHoSo: (lsxId: number) => void;
  onChon: (ds: TdsxLsxThamChieu[], x: number, y: number) => void;
}) {
  const meta = tdsxTtMeta(viec.trang_thai);
  const nguoi = nguoiText(viec.nguoi);
  const nhieuLenh = viec.lsx.length >= 2;
  const maChinh = viec.lsx[0]?.ma ?? null;

  // Cùng luật C123 với khối của tab Theo máy: 1 lệnh mở thẳng, ≥2 lệnh BẮT BUỘC hỏi. Việc không
  // gắn lệnh nào (dữ liệu lỗi) thì dòng vẫn hiện nhưng không bấm được — không bịa một đích đến.
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
      className="tdsx-tc__viec"
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
      </div>
      <div className="tdsx-tc__viecrow2">
        <span className="tdsx-tc__vmay" title={viec.may}>
          {viec.may}
        </span>
        <span aria-hidden="true">·</span>
        <span title={nguoi.full}>{nguoi.text}</span>
        <span aria-hidden="true">·</span>
        <span>Dự kiến {gioTrongNgay(viec.du_kien_bat_dau)}</span>
        <ChipLoaiBuoc loai_buoc={viec.nhan?.loai_buoc} nha_cung_cap={viec.nhan?.nha_cung_cap} />
        <ChipKhuon can_khuon={!!viec.nhan?.khuon_ma} khuon={nhanKhuon(viec.nhan)} />
      </div>
    </button>
  );
}
