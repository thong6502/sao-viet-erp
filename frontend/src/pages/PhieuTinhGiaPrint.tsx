// Phiếu tính giá ấn phẩm — component in tái dùng (bản CHỐT chủ xưởng đã duyệt).
// Giao diện đen-trắng thuần, bảng chi tiết theo 4 nhóm A/B/C/D, khối Tổng giá vốn, 3 ô ký.
// Toàn bộ dữ liệu vào qua props `data`. Component KHÔNG tự format số — số đã là chuỗi format sẵn.
import svnLogoUrl from "../assets/sao-viet-nhat-logo-mark.png";
import "./phieu-tinh-gia.css";

// ------------------------------- Types -------------------------------
export interface PhieuTinhGiaHeader {
  soPhieu: string;
  ngayLap: string;
  ngayIn: string;
  tenAnPham: string;
  soLuong: number;
  khoThanhPham: string;
  dvt: string;
}

export interface PhieuTinhGiaNoiDung {
  label: string;
  text: string;
}

export interface PhieuTinhGiaColumn {
  key: string;
  label: string;
  align?: "left" | "right" | "center";
  kind?: "text" | "num" | "formula";
  /** Bề rộng cột (vd "23%"). Tùy chọn — có thì render <colgroup> giữ đúng tỉ lệ bản duyệt. */
  width?: string;
}

export interface PhieuTinhGiaGroup {
  idx: string;
  name: string;
  columns: PhieuTinhGiaColumn[];
  rows: Array<Record<string, string | number>>;
  subtotalLabel: string;
  subtotal: string;
}

export interface PhieuTinhGiaChuKy {
  role: string;
  who?: string;
}

export interface PhieuTinhGia {
  header: PhieuTinhGiaHeader;
  noiDung: PhieuTinhGiaNoiDung[];
  groups: PhieuTinhGiaGroup[];
  grandTotal: string;
  grandNote?: string;
  chuKy: PhieuTinhGiaChuKy[];
}

// ------------------------------- Helpers -------------------------------
// Class căn lề cho ô dữ liệu theo kind + align (khớp bản duyệt: num→phải, formula→chữ nhỏ xám).
function cellClass(col: PhieuTinhGiaColumn): string {
  const cls: string[] = [];
  if (col.kind === "num") cls.push("ptg-num");
  else if (col.kind === "formula") cls.push("ptg-formula");
  else if (col.align === "right") cls.push("ptg-num");
  if (col.align === "center") cls.push("ptg-center");
  return cls.join(" ");
}

// Class căn lề cho ô tiêu đề (num/align right→phải, center→giữa).
function headClass(col: PhieuTinhGiaColumn): string {
  const cls: string[] = [];
  if (col.kind === "num" || col.align === "right") cls.push("ptg-num");
  if (col.align === "center") cls.push("ptg-center");
  return cls.join(" ");
}

// Vị trí cột hiển thị "Số tiền" cộng nhóm = cột num cuối cùng (fallback: cột cuối).
function subtotalColIndex(columns: PhieuTinhGiaColumn[]): number {
  let idx = columns.length - 1;
  for (let i = 0; i < columns.length; i++) {
    if (columns[i].kind === "num") idx = i;
  }
  return idx;
}

function GroupTable({ group }: { group: PhieuTinhGiaGroup }) {
  const { columns, rows } = group;
  const hasWidths = columns.some((c) => c.width);
  const valueIdx = subtotalColIndex(columns);
  const trailing = columns.length - valueIdx - 1;

  return (
    <table className="ptg-tbl">
      {hasWidths && (
        <colgroup>
          {columns.map((c) => (
            <col key={c.key} style={c.width ? { width: c.width } : undefined} />
          ))}
        </colgroup>
      )}
      <thead>
        <tr>
          {columns.map((c) => (
            <th key={c.key} className={headClass(c) || undefined}>
              {c.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, ri) => (
          <tr key={ri}>
            {columns.map((c) => {
              const cls = cellClass(c);
              return (
                <td key={c.key} className={cls || undefined}>
                  {row[c.key] ?? ""}
                </td>
              );
            })}
          </tr>
        ))}
        <tr className="ptg-sub">
          <td colSpan={valueIdx} className="ptg-num ptg-sl">
            {group.subtotalLabel}
          </td>
          <td className="ptg-num">{group.subtotal}</td>
          {Array.from({ length: trailing }, (_, i) => (
            <td key={i} />
          ))}
        </tr>
      </tbody>
    </table>
  );
}

// ------------------------------- Component -------------------------------
export function PhieuTinhGiaPrint({
  data,
  onPrint,
}: {
  data: PhieuTinhGia;
  onPrint?: () => void;
}) {
  const { header, noiDung, groups, grandTotal, grandNote, chuKy } = data;
  const doPrint = onPrint ?? (() => window.print());

  return (
    <div className="ptg-wrap">
      <div className="ptg-toolbar ptg-noprint">
        <button type="button" className="ptg-print-btn" onClick={doPrint}>
          In phiếu
        </button>
      </div>

      <div className="ptg-sheet">
        <div className="ptg-printed">Ngày in: {header.ngayIn}</div>

        <header className="ptg-mh">
          <div className="ptg-logo">
            <img src={svnLogoUrl} alt="Sao Việt Nhật" />
          </div>
          <div className="ptg-th">
            <h1>PHIẾU TÍNH GIÁ ẤN PHẨM</h1>
            <div className="ptg-cty">CÔNG TY SAO VIỆT NHẬT</div>
          </div>
          <div className="ptg-meta">
            <div>
              Số phiếu: <b>{header.soPhieu}</b>
            </div>
            <div>
              Ngày: <b>{header.ngayLap}</b>
            </div>
          </div>
        </header>

        <div className="ptg-info">
          <div className="ptg-r">
            <span className="ptg-lbl">Tên ấn phẩm:</span>{" "}
            <span className="ptg-val-b">{header.tenAnPham}</span>
          </div>
          <div className="ptg-g3">
            <div>
              <span className="ptg-lbl">Số lượng:</span>{" "}
              <span className="ptg-val">{header.soLuong}</span>
            </div>
            <div>
              <span className="ptg-lbl">Khổ thành phẩm:</span>{" "}
              <span className="ptg-val">{header.khoThanhPham}</span>
            </div>
            <div>
              <span className="ptg-lbl">Đơn vị tính:</span>{" "}
              <span className="ptg-val">{header.dvt}</span>
            </div>
          </div>
        </div>

        <div className="ptg-sec">Nội dung thực hiện</div>
        <ol className="ptg-scope">
          {noiDung.map((n, i) => (
            <li key={i}>
              <span className="ptg-k">{n.label}:</span> {n.text}
            </li>
          ))}
        </ol>

        <div className="ptg-sec">Kết quả tính giá</div>

        {groups.map((g) => (
          <div className="ptg-grp" key={g.idx}>
            <div className="ptg-grpt">
              <span className="ptg-idx">{g.idx}.</span> {g.name}
            </div>
            <GroupTable group={g} />
          </div>
        ))}

        <div className="ptg-grand">
          <div>
            <div className="ptg-gt">Tổng giá vốn</div>
            {grandNote && <div className="ptg-gs">{grandNote}</div>}
          </div>
          <div className="ptg-ga">
            {grandTotal}
            <span className="ptg-u">đ</span>
          </div>
        </div>

        <div className="ptg-signs">
          {chuKy.map((c, i) => (
            <div key={i}>
              <div className="ptg-role">{c.role}</div>
              <div className="ptg-hint">(Ký, ghi rõ họ tên)</div>
              <div className="ptg-sp" />
              {c.who && <div className="ptg-who">{c.who}</div>}
            </div>
          ))}
        </div>

        <div className="ptg-foot">
          <span>
            Công ty Sao Việt Nhật · Phiếu tính giá nội bộ — không có giá trị thanh toán.
          </span>
          <span>{header.soPhieu}</span>
        </div>
      </div>
    </div>
  );
}

// ------------------------------- Dữ liệu mẫu -------------------------------
// Bê đúng số liệu trong bản duyệt (TG-2026-0001, F80021846…) để test nhanh.
const AN_PHAM = "F80021846- HỘP CB LBF405RS12N-LL USA-278*198*280MM";

export const SAMPLE_PHIEU: PhieuTinhGia = {
  header: {
    soPhieu: "TG-2026-0001",
    ngayLap: "10/07/2026",
    ngayIn: "11/07/2026 09:42",
    tenAnPham: AN_PHAM,
    soLuong: 510,
    khoThanhPham: "— cm",
    dvt: "TỜ",
  },
  noiDung: [
    {
      label: "Quy cách in",
      text: "Khổ mở rộng ( )cm, 1 tờ, In 5 màu, 1 mặt » In (98.50x64.50) in 1 mặt x 1 tay; CANH THEO MẪU KHÁCH - CHẠY HÀNG MẪU DUYỆT TRƯỚC KHI SX",
    },
    {
      label: "Quy cách thành phẩm",
      text: "CM-CÁN MÀNG MỜ 1 mặt; TBOI-BỒI SẢN PHẨM; TB-BẾ CẤN HỘP, THÙNG; TD-DÁN HỘP CARTON; TD-DÁN MÓC ĐÁY; TP-KIỂM PHẨM.",
    },
    {
      label: "Quy cách chế bản",
      text: `${AN_PHAM} : KT-CTP GHI KẼM`,
    },
    { label: "Giao hàng", text: "chưa ghi" },
    {
      label: "Ghi chú",
      text: "CANH THEO MẪU KHÁCH - CHẠY HÀNG MẪU DUYỆT TRƯỚC KHI SX",
    },
  ],
  groups: [
    {
      idx: "A",
      name: "Giấy",
      columns: [
        { key: "anpham", label: "Tên ấn phẩm", width: "23%" },
        { key: "giay", label: "Giấy", width: "15%" },
        { key: "buhao", label: "TL bù hao", align: "center", width: "9%" },
        { key: "slnguyen", label: "SL giấy nguyên", kind: "num", width: "12%" },
        { key: "dgban", label: "ĐG bán", kind: "num", width: "11%" },
        { key: "tien", label: "Số tiền", kind: "num", width: "15%" },
        { key: "ghichu", label: "Ghi chú", width: "15%" },
      ],
      rows: [
        {
          anpham: AN_PHAM,
          giay: "D250-98.50x64.50",
          buhao: "0%",
          slnguyen: "760",
          dgban: "2.700",
          tien: "2.052.000",
          ghichu: "",
        },
      ],
      subtotalLabel: "Cộng nhóm A",
      subtotal: "2.052.000",
    },
    {
      idx: "B",
      name: "Công in",
      columns: [
        { key: "anpham", label: "Tên ấn phẩm", width: "23%" },
        { key: "congin", label: "Công in", width: "24%" },
        { key: "dg", label: "Đơn giá", kind: "num", width: "11%" },
        { key: "tien", label: "Số tiền", kind: "num", width: "13%" },
        { key: "ct", label: "Công thức", kind: "formula", width: "29%" },
      ],
      rows: [
        {
          anpham: AN_PHAM,
          congin: "(98.50x64.50) in 1 mặt - 1 tờ x 1 tay",
          dg: "0đ/T",
          tien: "0",
          ct: "0 × 1,00000 (5/0) × 1 × 1000/510",
        },
      ],
      subtotalLabel: "Cộng nhóm B",
      subtotal: "0",
    },
    {
      idx: "C",
      name: "Chế bản",
      columns: [
        { key: "anpham", label: "Tên ấn phẩm", width: "23%" },
        { key: "cheban", label: "Chế bản", width: "24%" },
        { key: "dg", label: "Đơn giá", kind: "num", width: "12%" },
        { key: "tien", label: "Số tiền", kind: "num", width: "13%" },
        { key: "ct", label: "Công thức", kind: "formula", width: "28%" },
      ],
      rows: [
        {
          anpham: AN_PHAM,
          cheban: "KT-CTP GHI KẼM",
          dg: "980,39đ/T",
          tien: "500.000",
          ct: "5 × 100.000 × 1 × 1,00000/510",
        },
      ],
      subtotalLabel: "Cộng nhóm C",
      subtotal: "500.000",
    },
    {
      idx: "D",
      name: "Gia công sau in",
      columns: [
        { key: "gc", label: "Gia công sau in", width: "22%" },
        { key: "dg", label: "Đơn giá", kind: "num", width: "13%" },
        { key: "tien", label: "Số tiền", kind: "num", width: "14%" },
        { key: "ct", label: "Công thức", kind: "formula", width: "29%" },
        { key: "ghichu", label: "Ghi chú", width: "22%" },
      ],
      rows: [
        { gc: "CM-CÁN MÀNG MỜ", dg: "1.238,86đ/T", tien: "631.830", ct: "0,20 × 3.240.157,50 ×1,00000/510", ghichu: "" },
        { gc: "TBOI-BỒI SẢN PHẨM", dg: "8.894.550đ/T", tien: "4.536.220.500", ct: "1.400 × 3.240.157,50 ×1,00000/510", ghichu: "SÓNG E NÂU 140/120" },
        { gc: "TB-BẾ CẤN HỘP, THÙNG", dg: "250đ/T", tien: "127.500", ct: "250 × 510 ×1,00000/510", ghichu: "KHUÔN MỚI N-0763" },
        { gc: "TD-DÁN HỘP CARTON", dg: "200đ/T", tien: "102.000", ct: "200 × 510 ×1,00000/510", ghichu: "" },
        { gc: "TD-DÁN MÓC ĐÁY", dg: "0đ/T", tien: "0", ct: "0 × 510 ×1,00000/510", ghichu: "" },
        { gc: "TP-KIỂM PHẨM", dg: "0đ/T", tien: "0", ct: "0 × 510 ×1,00000/510", ghichu: "" },
      ],
      subtotalLabel: "Cộng nhóm D",
      subtotal: "4.537.081.831",
    },
  ],
  grandTotal: "4.539.633.831",
  grandNote: "Cộng A+B+C+D · giá vốn cho 510 tờ · chưa gồm lợi nhuận & VAT",
  chuKy: [
    { role: "Người lập", who: "Bộ phận định giá" },
    { role: "Người duyệt", who: "Trưởng phòng KD" },
    { role: "Giám đốc", who: "Ban giám đốc" },
  ],
};
