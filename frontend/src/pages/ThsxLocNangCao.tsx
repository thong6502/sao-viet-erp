// "Lọc nâng cao" của bàn tổ (view Bảng) — trạng thái · ngày tổ NHẬN lệnh · cách sắp.
//
// Lọc chạy ở MÁY CHỦ, trước khi cắt trang (`/work-items` nhận `trang_thai`, `nhan_tu`, `nhan_den`,
// `sap_xep`) — component này chỉ giữ ô. Cùng hình với "Lọc nâng cao" của màn danh mục:
//   · MỞ   — hàng ô chọn + "Xoá bộ lọc".
//   · GẬP mà vẫn lọc — hàng nhãn "Trạng thái: Đang chạy ✕", để không ai tưởng tổ chỉ có chừng đó lệnh.
import { useState } from "react";

import { Icon } from "../components/Icons";
import { FilterIcon } from "./danh-muc/icons";
import { ngay } from "./keHoachSxShared";

export type ThsxSapXep = "moi_nhan" | "cu_nhan" | "du_kien";
export type ThsxTrangThaiLoc = "released" | "running" | "paused" | "completed";

export interface ThsxLoc {
  trangThai: ThsxTrangThaiLoc[];
  nhanTu: string;   // "YYYY-MM-DD" hoặc "" — ngày XƯỞNG tổ nhận lệnh, gồm cả hai đầu
  nhanDen: string;
  sapXep: ThsxSapXep;
}

export const LOC_TRONG: ThsxLoc = { trangThai: [], nhanTu: "", nhanDen: "", sapXep: "moi_nhan" };

const TRANG_THAI: { v: ThsxTrangThaiLoc; nhan: string }[] = [
  { v: "released", nhan: "Chờ làm" },
  { v: "running", nhan: "Đang chạy" },
  { v: "paused", nhan: "Tạm dừng" },
  { v: "completed", nhan: "Hoàn thành" },
];

const SAP_XEP: { v: ThsxSapXep; nhan: string }[] = [
  { v: "moi_nhan", nhan: "Mới nhận trước" },
  { v: "cu_nhan", nhan: "Nhận lâu nhất trước" },
  { v: "du_kien", nhan: "Theo giờ dự kiến" },
];

/** Ô ngày của trình duyệt nhận được năm 6 chữ số — chỉ gửi máy chủ khi đúng "YYYY-MM-DD". */
const ngayHopLe = (s: string) => /^\d{4}-\d{2}-\d{2}$/.test(s);

/** Khoảng ngày sai (từ > đến) thì không lọc theo ngày, để ô báo lỗi thay vì bảng trắng câm. */
export function khoangNgaySai(loc: ThsxLoc): boolean {
  return ngayHopLe(loc.nhanTu) && ngayHopLe(loc.nhanDen) && loc.nhanTu > loc.nhanDen;
}

/** Tham số gửi `/work-items` từ bộ lọc — bỏ hết thứ đang ở mặc định. */
export function thamSoLoc(loc: ThsxLoc): {
  trangThai?: string[]; nhanTu?: string; nhanDen?: string; sapXep?: ThsxSapXep;
} {
  const sai = khoangNgaySai(loc);
  return {
    trangThai: loc.trangThai.length ? loc.trangThai : undefined,
    nhanTu: !sai && ngayHopLe(loc.nhanTu) ? loc.nhanTu : undefined,
    nhanDen: !sai && ngayHopLe(loc.nhanDen) ? loc.nhanDen : undefined,
    sapXep: loc.sapXep === "moi_nhan" ? undefined : loc.sapXep,
  };
}

/** Số tiêu chí đang áp — con số trên nút "Lọc nâng cao". */
export function soTieuChi(loc: ThsxLoc): number {
  return (loc.trangThai.length ? 1 : 0)
    + (loc.nhanTu || loc.nhanDen ? 1 : 0)
    + (loc.sapXep !== "moi_nhan" ? 1 : 0);
}

function isoNgay(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function luiNgay(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return isoNgay(d);
}

function nhanKhoang(loc: ThsxLoc): string {
  if (loc.nhanTu && loc.nhanDen) return loc.nhanTu === loc.nhanDen ? ngay(loc.nhanTu) : `${ngay(loc.nhanTu)} – ${ngay(loc.nhanDen)}`;
  if (loc.nhanTu) return `từ ${ngay(loc.nhanTu)}`;
  return `đến ${ngay(loc.nhanDen)}`;
}

export function ThsxNutLoc({ mo, so, onDoi }: { mo: boolean; so: number; onDoi: () => void }) {
  return (
    <button type="button" className={`thsx-locnc-btn${mo ? " is-open" : ""}${so > 0 ? " is-active" : ""}`}
      aria-expanded={mo} onClick={onDoi}>
      <FilterIcon size={13} /> Lọc nâng cao
      {so > 0 && <span className="thsx-locnc-btn__so thsx-num">{so}</span>}
    </button>
  );
}

export function ThsxLocNangCao({ mo, value, onChange }: {
  mo: boolean;
  value: ThsxLoc;
  onChange: (v: ThsxLoc) => void;
}) {
  const dat = (p: Partial<ThsxLoc>) => onChange({ ...value, ...p });
  const doiTrangThai = (v: ThsxTrangThaiLoc) => dat({
    trangThai: value.trangThai.includes(v) ? value.trangThai.filter((x) => x !== v) : [...value.trangThai, v],
  });
  const homNay = isoNgay(new Date());
  const nhanh: { nhan: string; tu: string; den: string }[] = [
    { nhan: "Tất cả", tu: "", den: "" },
    { nhan: "Hôm nay", tu: homNay, den: homNay },
    { nhan: "7 ngày", tu: luiNgay(6), den: homNay },
    { nhan: "30 ngày", tu: luiNgay(29), den: homNay },
  ];
  // "Khoảng ngày" đang mở: người dùng bấm vào nó, hoặc ngày đang lọc không khớp nút nhanh nào.
  const khopNhanh = nhanh.find((n) => n.tu === value.nhanTu && n.den === value.nhanDen);
  const [moKhoang, setMoKhoang] = useState(false);
  const khoang = moKhoang || !khopNhanh;
  const sai = khoangNgaySai(value);
  const coLoc = soTieuChi(value) > 0;

  if (!mo) {
    if (!coLoc) return null;
    return (
      <div className="thsx-locnc-tags" aria-label="Bộ lọc đang áp">
        {value.trangThai.length > 0 && (
          <span className="thsx-locnc-tag">
            <span className="thsx-locnc-tag__k">Trạng thái:</span>
            {" "}{TRANG_THAI.filter((t) => value.trangThai.includes(t.v)).map((t) => t.nhan).join(", ")}
            <button type="button" className="thsx-locnc-tag__x" aria-label="Bỏ lọc Trạng thái"
              onClick={() => dat({ trangThai: [] })}><Icon name="x" size={11} /></button>
          </span>
        )}
        {(value.nhanTu || value.nhanDen) && (
          <span className={`thsx-locnc-tag${sai ? " is-loi" : ""}`}>
            <span className="thsx-locnc-tag__k">Nhận:</span> {nhanKhoang(value)}
            <button type="button" className="thsx-locnc-tag__x" aria-label="Bỏ lọc ngày nhận"
              onClick={() => dat({ nhanTu: "", nhanDen: "" })}><Icon name="x" size={11} /></button>
          </span>
        )}
        {value.sapXep !== "moi_nhan" && (
          <span className="thsx-locnc-tag">
            <span className="thsx-locnc-tag__k">Sắp:</span> {SAP_XEP.find((s) => s.v === value.sapXep)?.nhan}
            <button type="button" className="thsx-locnc-tag__x" aria-label="Bỏ cách sắp"
              onClick={() => dat({ sapXep: "moi_nhan" })}><Icon name="x" size={11} /></button>
          </span>
        )}
        {soTieuChi(value) > 1 && (
          <button type="button" className="thsx-locnc-clear" onClick={() => onChange(LOC_TRONG)}>Xoá hết</button>
        )}
      </div>
    );
  }

  return (
    <div className="thsx-locnc" role="group" aria-label="Lọc nâng cao">
      <div className="thsx-locnc__row">
        <span className="thsx-locnc__label" id="locnc-tt">Trạng thái</span>
        <div className="thsx-locnc__seg" role="group" aria-labelledby="locnc-tt">
          {TRANG_THAI.map((t) => {
            const bat = value.trangThai.includes(t.v);
            return (
              <button key={t.v} type="button" className={`thsx-locnc__opt thsx-locnc__opt--${t.v}`}
                aria-pressed={bat} onClick={() => doiTrangThai(t.v)}>
                <i className="thsx-locnc__dot" aria-hidden="true" />
                {t.nhan}
              </button>
            );
          })}
        </div>
      </div>

      <div className="thsx-locnc__row">
        <span className="thsx-locnc__label" id="locnc-ngay">Ngày tổ nhận</span>
        <div className="thsx-locnc__seg" role="radiogroup" aria-labelledby="locnc-ngay">
          {nhanh.map((n) => (
            <button key={n.nhan} type="button" role="radio" className="thsx-locnc__opt"
              aria-checked={!khoang && khopNhanh === n}
              onClick={() => { setMoKhoang(false); dat({ nhanTu: n.tu, nhanDen: n.den }); }}>
              {n.nhan}
            </button>
          ))}
          <button type="button" role="radio" className="thsx-locnc__opt" aria-checked={khoang}
            onClick={() => setMoKhoang(true)}>
            <Icon name="calendar" size={12} /> Khoảng ngày
          </button>
        </div>
        {khoang && (
          <div className="thsx-locnc__ngay">
            <input type="date" className="thsx-locnc__in thsx-num" aria-label="Nhận từ ngày"
              min="2000-01-01" max="2200-12-31"
              value={value.nhanTu} onChange={(e) => dat({ nhanTu: e.target.value })} />
            <span aria-hidden="true">→</span>
            <input type="date" className="thsx-locnc__in thsx-num" aria-label="Nhận đến ngày"
              min="2000-01-01" max="2200-12-31"
              value={value.nhanDen} onChange={(e) => dat({ nhanDen: e.target.value })} />
            {sai && <span className="thsx-locnc__loi" role="alert">"Từ ngày" đang sau "Đến ngày" — chưa lọc theo ngày.</span>}
          </div>
        )}
      </div>

      <div className="thsx-locnc__row">
        <span className="thsx-locnc__label" id="locnc-sx">Sắp xếp</span>
        <div className="thsx-locnc__seg" role="radiogroup" aria-labelledby="locnc-sx">
          {SAP_XEP.map((o) => (
            <button key={o.v} type="button" role="radio" className="thsx-locnc__opt"
              aria-checked={value.sapXep === o.v} onClick={() => dat({ sapXep: o.v })}>
              {o.nhan}
            </button>
          ))}
        </div>
      </div>

      {coLoc && (
        <div className="thsx-locnc__foot">
          <button type="button" className="thsx-locnc-clear"
            onClick={() => { setMoKhoang(false); onChange(LOC_TRONG); }}>
            <Icon name="refresh" size={12} /> Xoá bộ lọc
          </button>
        </div>
      )}
    </div>
  );
}
