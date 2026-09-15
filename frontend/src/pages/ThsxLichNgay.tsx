// LỊCH NGÀY của bàn THỰC HIỆN SẢN XUẤT — lưới CỘT NGÀY cùng khuôn với Xếp lịch 3 (15/09/2026),
// thay cho Gantt trục giờ cũ (`ThsxTimeline`, zoom Giờ/Ca/Ngày/Tuần — đã gỡ).
//
// Mỗi VIỆC một dòng: ô nhãn dính bên trái (mã · trạng thái / công đoạn / nguồn · máy / số lượng),
// bên phải là thanh KẾ HOẠCH `du_kien_bat_dau → du_kien_ket_thuc`.
//
// Thanh DÍNH THEO NGUYÊN NGÀY, không theo tỉ lệ giờ (15/09/2026, lượt 2): một bước của tổ dài vài
// phút tới vài giờ, vẽ theo giờ trên ô ngày 96px thì bước 4 phút ra vạch 6px — chữ phải đặt lơ lửng
// ngoài thanh và vạch "bây giờ" đè lên nó. Bàn tổ đọc "ngày nào làm việc gì, xong chưa", nên thanh
// chiếm trọn các ô ngày nó chạm và giờ cụ thể viết NGAY TRONG thanh (dòng 2). Phiên chạy thật
// (`thuc_te`) cũng dính theo ngày thành ruy-băng dưới thanh: nằm lệch sang ô khác = làm lệch ngày.
//
// CHỈ ĐỌC: tổ trưởng không dời lịch (§5.2/§10.1) — không kéo–thả, bấm dòng/thanh chỉ phát `onChon(w)`.
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { SxThucTeKhoang, SxWorkItem } from "../api/client";
import { Icon } from "../components/Icons";
import { ChipKhuon, ChipLoaiBuoc } from "../components/ChipBuoc";
import { khungLuoi, nhanNgay, ngayGio, soNgayGiua, themNgay } from "./xl3Shared";
import { slText, sxSerial, ttMeta } from "./thsxShared";

interface Props {
  /** Ngày đầu cửa sổ (YYYY-MM-DD). */
  tu: string;
  soNgay: number;
  /** Việc CÓ GIỜ chạm cửa sổ, đã lọc + sắp theo giờ bắt đầu ở controller. */
  viec: SxWorkItem[];
  selectedId: number | null;
  onChon: (w: SxWorkItem) => void;
  /** Đang lọc theo từ khoá? Lưới rỗng thì báo "không khớp" thay vì "khoảng ngày trống". */
  dangTim?: boolean;
}

/** "Bây giờ" dạng ISO naive theo đồng hồ máy người xem — cùng hệ với `du_kien_*` (giờ nhà máy,
 *  không múi). KHÔNG dùng `toISOString()`: chuỗi đó là giờ UTC, lệch 7 tiếng — qua nửa đêm là
 *  tô nhầm cột hôm nay. */
function bayGioIso(): string {
  const n = new Date();
  const p = (v: number) => String(v).padStart(2, "0");
  return `${n.getFullYear()}-${p(n.getMonth() + 1)}-${p(n.getDate())}T${p(n.getHours())}:${p(n.getMinutes())}`;
}

/** Mốc kết thúc THỰC của việc đã xong: phiên chạy khép sau cùng. Không có ⇒ null. */
function ketThucThucTe(w: SxWorkItem): string | null {
  let cuoi: string | null = null;
  for (const p of w.thuc_te ?? []) {
    if (p.ket_thuc && (cuoi === null || p.ket_thuc > cuoi)) cuoi = p.ket_thuc;
  }
  return cuoi;
}

/** Ngày (YYYY-MM-DD) của một mốc. Mốc KẾT THÚC đúng 00:00 thuộc về ngày TRƯỚC — việc xong lúc
 *  nửa đêm không chạm sang ngày hôm sau. */
function ngayCua(iso: string | null | undefined, laKetThuc = false): string | null {
  const m = iso?.match(/^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}):(\d{2}))?/);
  if (!m) return null;
  return laKetThuc && m[2] === "00" && m[3] === "00" ? themNgay(m[1], -1) : m[1];
}

const hm = (iso: string | null | undefined) => iso?.match(/[T ](\d{2}:\d{2})/)?.[1] ?? "";
/** "2026-09-15…" → "15/9" — cùng kiểu với đầu cột ngày. */
const dm = (iso: string | null | undefined) => {
  const d = ngayCua(iso);
  return d ? `${Number(d.slice(8, 10))}/${Number(d.slice(5, 7))}` : "";
};

export interface ONgay {
  /** Chỉ số ô ngày đầu / cuối (0-based) trong cửa sổ, đã kẹp. */
  dau: number;
  cuoi: number;
  tranTrai: boolean;
  tranPhai: boolean;
}

/** Các ô ngày mà quãng `tuIso → denIso` chạm, kẹp vào cửa sổ `[cuaSoTu, +soNgay)`. `null` = nằm
 *  hẳn ngoài cửa sổ hoặc thiếu mốc. Thiếu mốc cuối thì coi như việc gọn trong ngày bắt đầu. */
export function oNgay(
  tuIso: string | null | undefined,
  denIso: string | null | undefined,
  cuaSoTu: string,
  soNgay: number,
): ONgay | null {
  const a = ngayCua(tuIso);
  const b = ngayCua(denIso ?? tuIso, true);
  if (!a || !b) return null;
  const i = soNgayGiua(cuaSoTu, a) - 1;
  const j = Math.max(i, soNgayGiua(cuaSoTu, b) - 1);
  if (j < 0 || i > soNgay - 1) return null;
  return { dau: Math.max(0, i), cuoi: Math.min(soNgay - 1, j), tranTrai: i < 0, tranPhai: j > soNgay - 1 };
}

/** Các dải NGÀY có chạy thật, gộp liền nhau. `mo` = trong dải có phiên đang mở (chưa bấm Kết thúc). */
export function dayThucTe(
  phien: SxThucTeKhoang[] | null | undefined,
  cuaSoTu: string,
  soNgay: number,
  bayGio: string,
): { dau: number; cuoi: number; mo: boolean }[] {
  const co: (0 | 1 | 2)[] = Array.from({ length: soNgay }, () => 0);
  for (const p of phien ?? []) {
    const o = oNgay(p.bat_dau, p.ket_thuc ?? bayGio, cuaSoTu, soNgay);
    if (!o) continue;
    for (let k = o.dau; k <= o.cuoi; k++) co[k] = Math.max(co[k], p.ket_thuc ? 1 : 2) as 1 | 2;
  }
  const ra: { dau: number; cuoi: number; mo: boolean }[] = [];
  for (let k = 0; k < soNgay; k++) {
    if (!co[k]) continue;
    const last = ra[ra.length - 1];
    if (last && last.cuoi === k - 1) {
      last.cuoi = k;
      last.mo = last.mo || co[k] === 2;
    } else {
      ra.push({ dau: k, cuoi: k, mo: co[k] === 2 });
    }
  }
  return ra;
}

/** Cỡ chữ trong thanh theo bề rộng: `du` ≥120px, `gon` 84–119px (bỏ chữ dẫn — "08:17–08:21" rộng
 *  ~70px), `mini` <84px (một mốc giờ — icon ở dòng 1 đã nói trạng thái). */
export type CoThanh = "du" | "gon" | "mini";

export function coThanh(rong: number): CoThanh {
  return rong >= 120 ? "du" : rong >= 84 ? "gon" : "mini";
}

/** Dòng 2 trong thanh — thứ tổ cần biết ngay theo trạng thái. */
export function dongHaiThanh(w: SxWorkItem, co: CoThanh): string {
  switch (w.trang_thai) {
    case "running": {
      const mo = (w.thuc_te ?? []).filter((p) => !p.ket_thuc).map((p) => p.bat_dau).sort().pop();
      if (!mo) return co === "mini" ? "Chạy" : "Đang chạy";
      if (co === "mini") return hm(mo);
      const khacNgay = ngayCua(mo) !== ngayCua(w.du_kien_bat_dau);
      return `${co === "gon" ? "Từ" : "Chạy từ"} ${khacNgay ? `${dm(mo)} ` : ""}${hm(mo)}`;
    }
    case "paused":
      return co === "mini" ? "Dừng" : "Tạm dừng";
    case "completed": {
      const kt = ketThucThucTe(w);
      if (!kt) return co === "mini" ? "Xong" : "Đã xong";
      const khacNgay = ngayCua(kt, true) !== ngayCua(w.du_kien_ket_thuc, true);
      if (co === "mini") return khacNgay ? dm(kt) : hm(kt);
      return `Xong ${khacNgay ? `${dm(kt)} ` : ""}${hm(kt)}`;
    }
    default: {
      const a = w.du_kien_bat_dau;
      const b = w.du_kien_ket_thuc;
      const motNgay = ngayCua(a) === ngayCua(b, true);
      if (co === "mini") return motNgay ? hm(a) : `→ ${dm(b)}`;
      const truoc = co === "gon" ? "" : "KH ";
      if (!motNgay) return `${truoc}${dm(a)} → ${dm(b)}`;
      // Kế hoạch 0 phút (bắt đầu = kết thúc) ra "08:21–08:21" chỉ là nhiễu.
      return hm(a) === hm(b) ? `${truoc}${hm(a)}` : `${truoc}${hm(a)}–${hm(b)}`;
    }
  }
}

export function ThsxLichNgay({ tu, soNgay, viec, selectedId, onChon, dangTim = false }: Props) {
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Bề ngang KHUNG (không phải cửa sổ trình duyệt): bàn tổ còn cột Hàng chờ bên trái nên lưới hẹp
  // hơn cửa sổ. Cột ngày CO/GIÃN cho vừa đúng số ngày đã chọn — giãn khi khung thừa chỗ (khỏi mảng
  // trắng bên phải), co khi khung thiếu: ở 1280px mở Hàng chờ, cỡ gốc 168px của Xếp lịch 3 cho nút
  // "7 Ngày" thấy đúng 2,7 ngày (đo 15/09/2026). Co không dưới nấc nhỏ nhất của màn hẹp (96/64/36).
  const [khungW, setKhungW] = useState(0);
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const doLai = () => setKhungW(el.clientWidth);
    doLai();
    const ro = new ResizeObserver(doLai);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const coSo = khungLuoi(typeof window !== "undefined" ? window.innerWidth : 1440, soNgay);
  const nhanW = coSo.nhanW;
  const dongH = coSo.dongH;
  const san = Math.min(coSo.ngayW, khungLuoi(480, soNgay).ngayW);
  const ngayW = khungW > 0 ? Math.max(san, Math.floor((khungW - nhanW) / soNgay)) : coSo.ngayW;
  // Ô dưới 60px không chứa nổi "T3 15/9" + "2 việc" — đầu cột xuống kiểu gọn (số ngày + chấm).
  const oHep = ngayW < 60;
  // Khoảng hở hai bên thanh để hai việc liền ngày không dính thành một khối.
  const le = oHep ? 2 : 4;
  const rongLuoi = ngayW * soNgay;
  const tongW = nhanW + rongLuoi;
  const ngays = useMemo(() => Array.from({ length: soNgay }, (_, i) => themNgay(tu, i)), [tu, soNgay]);

  // "Bây giờ" chỉ còn dùng để tô cột HÔM NAY và kéo đuôi phiên đang mở — nhích mỗi phút cho
  // qua nửa đêm là cột hôm nay tự dời.
  const [bayGio, setBayGio] = useState(bayGioIso);
  useEffect(() => {
    const h = setInterval(() => setBayGio(bayGioIso()), 60_000);
    return () => clearInterval(h);
  }, []);
  const iNay = ngays.indexOf(bayGio.slice(0, 10));

  const oCuaViec = useMemo(() => {
    const m = new Map<number, ONgay | null>();
    for (const w of viec) m.set(w.id, oNgay(w.du_kien_bat_dau, w.du_kien_ket_thuc, tu, soNgay));
    return m;
  }, [viec, tu, soNgay]);

  // Số việc chạm từng ngày — dòng nhỏ "N việc" dưới ngày. Đếm theo ĐÚNG ô thanh đang chiếm.
  const demNgay = useMemo(() => {
    const dem = Array.from({ length: soNgay }, () => 0);
    for (const o of oCuaViec.values()) {
      if (!o) continue;
      for (let k = o.dau; k <= o.cuoi; k++) dem[k] += 1;
    }
    return dem;
  }, [oCuaViec, soNgay]);

  // Đổi khoảng ngày ⇒ đưa cột HÔM NAY vào tầm nhìn: 7 ngày ở 602px chỉ thấy T2–T5, hôm nay là CN
  // thì mở màn ra không thấy việc của hôm nay.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || khungW <= 0 || iNay < 0) return;
    const trai = iNay * ngayW;
    const hienDen = el.scrollLeft + el.clientWidth - nhanW;
    if (trai >= el.scrollLeft && trai + ngayW <= hienDen) return;
    el.scrollLeft = Math.max(0, trai - ngayW);
    // Chỉ chạy khi đổi khoảng / lần đo đầu — không giật về hôm nay mỗi lần người dùng tự cuộn.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tu, soNgay, khungW > 0]);

  // Chọn việc (từ Hàng chờ hay từ lưới) ⇒ cuộn tới thanh của nó nếu đang khuất.
  useEffect(() => {
    const el = scrollRef.current;
    if (selectedId == null || !el) return;
    const o = oCuaViec.get(selectedId);
    if (!o) return;
    const trai = o.dau * ngayW;
    const hienTu = el.scrollLeft;
    const hienDen = el.scrollLeft + el.clientWidth - nhanW;
    if (trai >= hienTu && trai < hienDen) return;
    el.scrollTo({ left: Math.max(0, trai - 8), behavior: "smooth" });
  }, [selectedId, oCuaViec, ngayW, nhanW]);

  return (
    <div className="thsx-ln" ref={scrollRef}>
      {/* Đầu cột ngày — dính đỉnh */}
      <div className="thsx-ln__head" style={{ width: tongW }}>
        <div className="thsx-ln__head-nhan" style={{ width: nhanW }}>
          <strong className="thsx-num">{viec.length}</strong> việc trong khoảng
        </div>
        {ngays.map((d, i) => {
          const n = nhanNgay(d);
          const dem = demNgay[i] ?? 0;
          const cls = `thsx-ln__ngay${oHep ? " thsx-ln__ngay--hep" : ""}${i === iNay ? " thsx-ln__ngay--nay" : ""}${n.thu === "CN" ? " thsx-ln__ngay--cn" : ""}`;
          return (
            <div key={d} className={cls} style={{ width: ngayW }}
              title={`${i === iNay ? "Hôm nay · " : ""}${n.thu} ${n.so}${dem ? ` · ${dem} việc` : ""}`}>
              {oHep ? (
                <>
                  <span className="thsx-ln__so thsx-num">{d.slice(8, 10)}</span>
                  <span className="thsx-ln__thu">{n.thu}</span>
                  {dem > 0 && <span className="thsx-ln__cham" />}
                </>
              ) : (
                <>
                  <span className="thsx-ln__ngay-dong1">
                    <span className="thsx-ln__thu">{n.thu}</span>
                    <span className="thsx-ln__so thsx-num">{n.so}</span>
                  </span>
                  <span className="thsx-ln__dem thsx-num">{dem > 0 ? `${dem} việc` : " "}</span>
                </>
              )}
            </div>
          );
        })}
      </div>

      <div className="thsx-ln__body" style={{ width: tongW }}>
        {/* Lớp NỀN kéo hết chiều cao khung: dải nhãn + vạch cột ngày + tô cột hôm nay/CN. Có ít việc
            thì phần dưới vẫn là lưới, không phải mảng trắng. */}
        <div className="thsx-ln__nen" aria-hidden="true">
          <div className="thsx-ln__nen-nhan" style={{ width: nhanW }} />
          {ngays.map((d, i) => (
            <span
              key={d}
              className={`thsx-ln__nen-cot${i === iNay ? " thsx-ln__nen-cot--nay" : ""}${nhanNgay(d).thu === "CN" ? " thsx-ln__nen-cot--cn" : ""}`}
              style={{ left: nhanW + i * ngayW, width: ngayW }}
            />
          ))}
        </div>

        {viec.length === 0 && (
          // Dính mép trái + rộng đúng khung nhìn: lưới 30 ngày rộng hơn khung nhiều lần, căn giữa theo
          // cả lưới là hộp rơi ra ngoài màn (đo ở 602px: hộp nằm ở left 584px).
          <div className="thsx-ln__trong" style={{ width: khungW || undefined }}>
            <div className="thsx-ln__trong-hop">
              <Icon name="calendar" size={24} />
              {dangTim ? (
                <>
                  <h3>Không có việc nào khớp từ khoá</h3>
                  <p>Trong khoảng ngày này không việc nào khớp. Xoá từ khoá ở ô tìm, hoặc dời khoảng ngày bằng ◀ ▶.</p>
                </>
              ) : (
                <>
                  <h3>Không có việc nào trong khoảng ngày này</h3>
                  <p>Dời khoảng ngày bằng ◀ ▶, hoặc xem việc chưa định giờ ở Hàng chờ.</p>
                </>
              )}
            </div>
          </div>
        )}

        {viec.map((w) => {
          const sel = w.id === selectedId;
          const meta = ttMeta(w.trang_thai);
          const ma = w.nguon_ma || sxSerial(w.nguon_ma);
          const cd = w.ten_cong_doan || "";
          const o = oCuaViec.get(w.id) ?? null;
          const phu = [w.nguon_ten, w.may].filter(Boolean).join(" · ");
          const sl = w.so_luong_ra != null || w.so_luong_vao != null ? slText(w) : "";
          const acts = dayThucTe(w.thuc_te, tu, soNgay, bayGio);
          const thucTeTitle = (w.thuc_te ?? [])
            .map((p) => `${ngayGio(p.bat_dau)} → ${p.ket_thuc ? ngayGio(p.ket_thuc) : "đang chạy"}`)
            .join("; ");

          let thanh = null;
          if (o) {
            const trai = o.dau * ngayW + (o.tranTrai ? 0 : le);
            const rong = (o.cuoi + 1) * ngayW - (o.tranPhai ? 0 : le) - trai;
            // Dưới 56px không chứa nổi hai dòng: chỉ còn icon trạng thái (+ serial nếu ≥40px); chi tiết
            // ở tooltip, ô nhãn bên trái đã có mã.
            const ratHep = rong < 56;
            const coSerial = rong >= 40;
            const co = coThanh(rong);
            // Tên công đoạn chỉ vào thanh khi còn chỗ cho vài chữ — dưới 150px nó chỉ ra "· …", mà ô
            // nhãn bên trái đã ghi đủ tên.
            const coCd = !!cd && rong >= 150;
            const d2 = dongHaiThanh(w, co);
            const d2Du = dongHaiThanh(w, "du");
            thanh = (
              <button
                type="button"
                className={`thsx-ln__thanh thsx-ln__thanh--${w.trang_thai} thsx-ln__thanh--${ratHep ? "hep" : co}${sel ? " thsx-ln__thanh--chon" : ""}${w.la_kcs ? " thsx-ln__thanh--kcs" : ""}${o.tranTrai ? " thsx-ln__thanh--tran-trai" : ""}${o.tranPhai ? " thsx-ln__thanh--tran-phai" : ""}`}
                style={{ left: trai, width: rong }}
                title={`${ma}${cd ? ` · ${cd}` : ""}${w.nguon_ten ? ` · ${w.nguon_ten}` : ""} · ${meta.label} · ${d2Du}\nKế hoạch: ${ngayGio(w.du_kien_bat_dau)} → ${ngayGio(w.du_kien_ket_thuc)}${thucTeTitle ? `\nThực tế: ${thucTeTitle}` : ""}`}
                aria-label={`${ma}${cd ? `, ${cd}` : ""}, ${meta.label}, ${d2Du}`}
                aria-pressed={sel}
                onClick={(e) => { e.stopPropagation(); onChon(w); }}
              >
                {o.tranTrai && !ratHep && <Icon name="chevron" size={12} className="thsx-ln__mui thsx-rot90" />}
                <span className="thsx-ln__thanh-chu">
                  <span className="thsx-ln__thanh-d1">
                    <Icon name={meta.icon} size={12} />
                    {coSerial && <strong className="thsx-num">{sxSerial(w.nguon_ma)}</strong>}
                    {coCd && <span className="thsx-ln__thanh-cd">· {cd}</span>}
                  </span>
                  {!ratHep && <span className="thsx-ln__thanh-d2 thsx-num">{d2}</span>}
                </span>
                {o.tranPhai && !ratHep && <Icon name="chevron" size={12} className="thsx-ln__mui thsx-rot270" />}
              </button>
            );
          }

          return (
            <div
              key={w.id}
              className={`thsx-ln__hang${sel ? " thsx-ln__hang--chon" : ""}`}
              style={{ height: dongH }}
              onClick={() => onChon(w)}
            >
              <div className={`thsx-ln__nhan thsx-ln__nhan--${w.trang_thai}`} style={{ width: nhanW }}>
                <div className="thsx-ln__ma">
                  <span className="thsx-ln__ma-text thsx-num">{ma}</span>
                  <span className={`thsx-ln__tt thsx-ln__tt--${w.trang_thai}`} role="img" aria-label={meta.label} title={meta.label}>
                    <Icon name={meta.icon} size={12} />
                  </span>
                  {w.la_kcs && <span className="thsx-ln__kcs">KCS</span>}
                </div>
                <div className="thsx-ln__cd" title={cd}>{cd || "—"}</div>
                {phu && <div className="thsx-ln__phu" title={phu}>{phu}</div>}
                <div className="thsx-ln__sl">
                  {sl && <span className="thsx-ln__sl-so thsx-num" title={sl}>{sl}</span>}
                  <ChipLoaiBuoc loai_buoc={w.loai_buoc === "may" ? null : w.loai_buoc} nha_cung_cap={w.nha_cung_cap} />
                  <ChipKhuon can_khuon={!!w.khuon} khuon={{ ...(w.khuon ?? {}), da_nhan: w.khuon_da_nhan }} />
                </div>
              </div>

              <div className="thsx-ln__luoi" style={{ width: rongLuoi }}>
                {thanh}
                {acts.map((p) => {
                  const trai = p.dau * ngayW + le;
                  return (
                    <span
                      key={`a${p.dau}`}
                      className={`thsx-ln__that${p.mo ? " thsx-ln__that--mo" : ""}`}
                      style={{ left: trai, width: (p.cuoi + 1) * ngayW - le - trai }}
                      title={`Thực tế: ${thucTeTitle}`}
                    />
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
