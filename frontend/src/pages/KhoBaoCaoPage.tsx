// Báo cáo kho (kế toán) — sổ nhập-xuất (phiếu ĐÃ GHI SỔ) + khóa kỳ THEO KHOẢNG (chốt/mở) +
// tab Lịch sử thao tác + export MISA. docs/spec-bao-cao-kho.md. Chỉ quyền `close_book` vào.
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  ApiError,
  type BaoCaoChuyenKhoRow,
  type BaoCaoKhoRow,
  type KhoaSoKyRow,
  type KhoKhoaSoRow,
} from "../api/client";
import { crud } from "../api/rebuildCatalog";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Icon } from "../components/Icons";
import { Select } from "../components/Select";
import { DateFilterHead, NumFilterHead, fmtQty, inDateRange, inNumRange, todayISO, useHeaderTitles } from "./khoShared";
import "./rebuild-catalog.css";
import "./kho-request.css";

type KhoOpt = { id: number; ma: string; ten: string };
type Tab = "tong-quan" | "so" | "lichsu" | "ky";

const PAGE_SIZE = 20;

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return d && m && y ? `${d}/${m}/${y}` : iso;
}
function fmtDateTime(iso: string | null): string {
  if (!iso) return "—";
  // Backend lưu UTC nhưng serialize KHÔNG kèm offset (naive) → thêm 'Z' để đổi về giờ máy cho đúng.
  const s = /[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`;
  const dt = new Date(s);
  if (Number.isNaN(dt.getTime())) return fmtDate(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(dt.getDate())}/${p(dt.getMonth() + 1)}/${dt.getFullYear()} ${p(dt.getHours())}:${p(dt.getMinutes())}`;
}
function fmtMoney(n: number | null): string {
  return n == null ? "" : n.toLocaleString("vi-VN");
}

// Bảng màu lát biểu đồ tròn — dùng đúng biến màu app (moss·rust·plum·amber·signal), ash cho "Khác".
const DONUT_COLORS = [
  "var(--moss)",
  "var(--rust)",
  "var(--plum)",
  "var(--amber)",
  "var(--signal)",
  "var(--ash)",
];

type DonutSeg = { label: string; color: string; from: number; to: number; pct: number };

// Donut tỉ trọng giá trị theo mặt hàng: TOP 5 + gộp phần còn lại thành "Khác" (khỏi loạn quá nhiều
// lát). Trả các lát kèm mốc % để dựng conic-gradient.
function buildDonut(
  items: { ten: string | null; ma: string | null; tien: number }[],
  total: number,
): DonutSeg[] {
  const base = total > 0 ? total : items.reduce((s, x) => s + x.tien, 0) || 1;
  // BỎ mặt hàng chiếm < 0.5% giá trị (làm tròn ra "0%" — nhìn rối vô nghĩa): gộp hết vào "Khác".
  const big = items.filter((x) => x.tien > 0 && x.tien / base >= 0.005).slice(0, 5);
  const shown = big.reduce((s, x) => s + x.tien, 0);
  const khac = Math.max(0, base - shown);
  const segs = [
    ...big.map((t) => ({ label: t.ten ?? t.ma ?? "?", val: t.tien })),
    ...(khac / base >= 0.005 ? [{ label: "Khác", val: khac }] : []),
  ].filter((s) => s.val > 0);
  const denom = segs.reduce((s, x) => s + x.val, 0) || 1;
  let acc = 0;
  return segs.map((s, i) => {
    const from = (acc / denom) * 100;
    acc += s.val;
    return {
      label: s.label,
      color: DONUT_COLORS[i % DONUT_COLORS.length],
      from,
      to: (acc / denom) * 100,
      pct: (s.val / denom) * 100,
    };
  });
}

// Icon khóa/mở theo bộ icon dự án (SVG line, thừa kế currentColor) — thay cho emoji.
function LockIcon({ open = false, size = 13 }: { open?: boolean; size?: number }) {
  return <Icon name={open ? "lockOpen" : "lock"} size={size} style={{ verticalAlign: "-2px" }} />;
}

export function KhoBaoCaoPage({ token }: { token: string }) {
  // Hover tiêu đề cột → hiện tên cột đầy đủ (kể cả khi bị cắt) — 1 ref bọc cả trang, phủ mọi bảng.
  const pageRef = useHeaderTitles<HTMLElement>();
  const [tab, setTab] = useState<Tab>("tong-quan");
  // Chiều của tab "Sổ kho": Nhập · Xuất · Chuyển kho (Chuyển kho = điều chuyển nội bộ, bảng riêng).
  const [soChieu, setSoChieu] = useState<"NHAP" | "XUAT" | "CHUYEN">("NHAP");
  const [khoId, setKhoId] = useState<number | null>(null);
  const [tu, setTu] = useState("");
  const [den, setDen] = useState("");
  // Sổ · Ngày CT + các cột SỐ (funnel cột) — khai sớm vì `filteredRows` dùng ngay.
  const [ctFrom, setCtFrom] = useState("");
  const [ctTo, setCtTo] = useState("");
  const [slFrom, setSlFrom] = useState(""); // Số lượng
  const [slTo, setSlTo] = useState("");
  const [dgFrom, setDgFrom] = useState(""); // Đơn giá
  const [dgTo, setDgTo] = useState("");
  const [ttFrom, setTtFrom] = useState(""); // Thành tiền
  const [ttTo, setTtTo] = useState("");

  const [rows, setRows] = useState<BaoCaoKhoRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [khoList, setKhoList] = useState<KhoOpt[]>([]);
  const [exporting, setExporting] = useState(false);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  // Khóa/mở kỳ + lịch sử + các kỳ CÒN đang khóa (tab "Kỳ đã khóa")
  const [locks, setLocks] = useState<KhoKhoaSoRow[]>([]);
  const [kyList, setKyList] = useState<KhoaSoKyRow[]>([]);
  const [khoaOpen, setKhoaOpen] = useState(false);
  const [khoaScope, setKhoaScope] = useState<"all" | number>("all");
  const [khoaHanhDong, setKhoaHanhDong] = useState<"khoa" | "mo">("khoa");
  const [khoaTu, setKhoaTu] = useState("");
  const [khoaDen, setKhoaDen] = useState(todayISO());
  const [khoaTen, setKhoaTen] = useState("");   // tên kỳ khi KHÓA (tuỳ chọn, chặn trùng)
  const [khoaBusy, setKhoaBusy] = useState(false);
  const [khoaError, setKhoaError] = useState<string | null>(null);

  useEffect(() => {
    crud("/api/kho")
      .list(token, { active: true })
      .then((r) =>
        setKhoList(
          r.items.map((w) => ({ id: Number(w.id), ma: String(w.ma), ten: String(w.ten) })),
        ),
      )
      .catch(() => {});
  }, [token]);

  const loadLocks = useCallback(() => {
    api.kho.baoCao.khoaSo(token).then(setLocks).catch(() => {});
    api.kho.baoCao.ky(token).then(setKyList).catch(() => {});
  }, [token]);
  useEffect(() => {
    loadLocks();
  }, [loadLocks]);

  const load = useCallback(() => {
    if (soChieu === "CHUYEN") return; // chiều Chuyển kho nạp qua loadChuyen (bên dưới)
    setLoading(true);
    setError(null);
    api.kho.baoCao
      .dong(token, { tu: tu || null, den: den || null, kho_id: khoId, loai: soChieu })
      .then((p) => setRows(p.items))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Không tải được báo cáo."))
      .finally(() => setLoading(false));
  }, [token, tu, den, khoId, soChieu]);
  useEffect(() => {
    if (tab === "so" && soChieu !== "CHUYEN") load();
  }, [load, tab, soChieu]);

  // Tab "Tổng quan": cần CẢ hai chiều → nạp Nhập + Xuất theo cùng bộ lọc kho/ngày rồi gộp.
  const [dashRows, setDashRows] = useState<BaoCaoKhoRow[]>([]);
  const loadDash = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      api.kho.baoCao.dong(token, { tu: tu || null, den: den || null, kho_id: khoId, loai: "NHAP" }),
      api.kho.baoCao.dong(token, { tu: tu || null, den: den || null, kho_id: khoId, loai: "XUAT" }),
    ])
      .then(([n, x]) => setDashRows([...n.items, ...x.items]))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Không tải được tổng quan."))
      .finally(() => setLoading(false));
  }, [token, tu, den, khoId]);
  useEffect(() => {
    if (tab === "tong-quan") loadDash();
  }, [loadDash, tab]);

  // Chiều "Chuyển kho" của tab Sổ: dòng điều chuyển đã ghi sổ (Xuất tại kho → Nhập tại kho).
  const [chuyenRows, setChuyenRows] = useState<BaoCaoChuyenKhoRow[]>([]);
  const loadChuyen = useCallback(() => {
    setLoading(true);
    setError(null);
    api.kho.baoCao
      .chuyenKho(token, { tu: tu || null, den: den || null, kho_id: khoId })
      .then((p) => setChuyenRows(p.items))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Không tải được báo cáo điều chuyển."))
      .finally(() => setLoading(false));
  }, [token, tu, den, khoId]);
  useEffect(() => {
    if (tab === "so" && soChieu === "CHUYEN") loadChuyen();
  }, [loadChuyen, tab, soChieu]);
  // Lọc client-side theo ô tìm (số CT / mã / tên hàng) — khớp cách tab Sổ dùng.
  const chuyenFiltered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return chuyenRows;
    return chuyenRows.filter((r) =>
      (r.so_ct ?? "").toLowerCase().includes(q) ||
      (r.ma_hang ?? "").toLowerCase().includes(q) ||
      (r.ten_hang ?? "").toLowerCase().includes(q),
    );
  }, [chuyenRows, search]);
  const chuyenTongTien = useMemo(
    () => chuyenFiltered.reduce((s, r) => s + (r.tien_von ?? 0), 0),
    [chuyenFiltered],
  );

  // Tổng hợp dashboard — tính client-side từ ĐÚNG data sổ (khớp con số tab Sổ nhập-xuất).
  const dash = useMemo(() => {
    // LOẠI ĐIỀU CHUYỂN nội bộ khỏi mọi con số mua/bán: điều chuyển là hàng dịch kho A→B, nét
    // toàn công ty bằng 0. Cộng vào là thổi phồng "mua/bán trong kỳ" (spec-dieu-chuyen-kho §11).
    const bizRows = dashRows.filter((r) => !r.dieu_chuyen);
    const soDieuChuyen = dashRows.length - bizRows.length;
    const nhap = bizRows.filter((r) => r.loai === "NHAP");
    const xuat = bizRows.filter((r) => r.loai === "XUAT");
    // Chuyển kho: dùng vế NHẬP đích của điều chuyển = 1 dòng/mặt hàng (không double-count 2 vế).
    const dcNhap = dashRows.filter((r) => r.dieu_chuyen && r.loai === "NHAP");
    const sumTien = (rs: BaoCaoKhoRow[]) => rs.reduce((s, r) => s + (r.thanh_tien ?? 0), 0);
    const soPhieu = (rs: BaoCaoKhoRow[]) => new Set(rs.map((r) => r.so_ct)).size;
    const tongNhap = sumTien(nhap);
    const tongXuat = sumTien(xuat);

    const khoAgg = new Map<number, { ten: string; nhap: number; xuat: number; phieu: Set<string> }>();
    for (const r of bizRows) {
      const key = r.kho_id ?? -1;
      let cur = khoAgg.get(key);
      if (!cur) {
        cur = { ten: r.kho_ten ?? "—", nhap: 0, xuat: 0, phieu: new Set() };
        khoAgg.set(key, cur);
      }
      if (r.loai === "NHAP") cur.nhap += r.thanh_tien ?? 0;
      else cur.xuat += r.thanh_tien ?? 0;
      cur.phieu.add(r.so_ct);
    }
    const theoKho = [...khoAgg.values()]
      .map((k) => ({ ten: k.ten, nhap: k.nhap, xuat: k.xuat, phieu: k.phieu.size }))
      .sort((a, b) => b.nhap + b.xuat - (a.nhap + a.xuat));

    const topBy = (rs: BaoCaoKhoRow[]) => {
      const m = new Map<
        string,
        { ma: string | null; ten: string | null; dvt: string | null; sl: number; tien: number }
      >();
      for (const r of rs) {
        const key = r.ma_hang ?? r.ten_hang ?? "?";
        let cur = m.get(key);
        if (!cur) {
          cur = { ma: r.ma_hang, ten: r.ten_hang, dvt: r.dvt, sl: 0, tien: 0 };
          m.set(key, cur);
        }
        cur.sl += r.so_luong ?? 0;
        cur.tien += r.thanh_tien ?? 0;
      }
      return [...m.values()].sort((a, b) => b.tien - a.tien).slice(0, 8);
    };

    // Chuỗi thời gian Nhập/Xuất — mặc định theo NGÀY; tự gộp theo THÁNG nếu quá nhiều ngày (>45)
    // để biểu đồ khỏi tràn/rối.
    const ngayCo = new Set(
      bizRows.map((r) => (r.ngay_ghi_so ?? "").slice(0, 10)).filter(Boolean),
    );
    const theoThang = ngayCo.size > 45;
    const tsMap = new Map<string, { nhap: number; xuat: number; chuyen: number }>();
    const bump = (raw: string, field: "nhap" | "xuat" | "chuyen", val: number) => {
      if (!raw) return;
      const k = theoThang ? raw.slice(0, 7) : raw.slice(0, 10);
      let cur = tsMap.get(k);
      if (!cur) {
        cur = { nhap: 0, xuat: 0, chuyen: 0 };
        tsMap.set(k, cur);
      }
      cur[field] += val;
    };
    for (const r of bizRows) bump(r.ngay_ghi_so ?? "", r.loai === "NHAP" ? "nhap" : "xuat", r.thanh_tien ?? 0);
    // Chuyển kho: dùng vế NHẬP đích (1 dòng/mặt hàng) → cột thứ 3 trên biểu đồ theo ngày.
    for (const r of dcNhap) bump(r.ngay_ghi_so ?? "", "chuyen", r.thanh_tien ?? 0);
    const chuoi = [...tsMap.entries()]
      .sort((a, b) => (a[0] < b[0] ? -1 : 1))
      .map(([k, v]) => ({
        key: k,
        label: theoThang ? `${k.slice(5)}/${k.slice(0, 4)}` : `${k.slice(8)}/${k.slice(5, 7)}`,
        nhap: v.nhap,
        xuat: v.xuat,
        chuyen: v.chuyen,
      }));
    const chuoiMax = Math.max(1, ...chuoi.map((c) => Math.max(c.nhap, c.xuat, c.chuyen)));

    return {
      tongNhap,
      tongXuat,
      chenhLech: tongNhap - tongXuat,
      phieuNhap: soPhieu(nhap),
      phieuXuat: soPhieu(xuat),
      soMatHang: new Set(bizRows.map((r) => r.ma_hang ?? r.ten_hang ?? "?")).size,
      soDong: bizRows.length,
      soDieuChuyen,
      chuyenGiaTri: sumTien(dcNhap),
      chuyenSoPhieu: soPhieu(dcNhap),
      chuyenSoDong: dcNhap.length,
      theoKho,
      topNhap: topBy(nhap),
      topXuat: topBy(xuat),
      theoThang,
      chuoi,
      chuoiMax,
    };
  }, [dashRows]);

  const khoOptions = useMemo(
    () => [
      { value: "", label: "Tất cả kho" },
      ...khoList.map((k) => ({ value: String(k.id), label: `${k.ma} · ${k.ten}` })),
    ],
    [khoList],
  );

  // Bản ghi 'khoa' phủ (kho, NGÀY GHI SỔ) — null nếu không khóa. Mới-nhất-trước (id desc) → bản ghi
  // đầu tiên phủ ngày quyết định (giống backend is_locked). Dùng cả để TÔ MÀU theo kỳ.
  const lockRecordFor = useCallback(
    (khoId: number | null, ngay: string | null): KhoKhoaSoRow | null => {
      const d = ngay?.slice(0, 10);
      if (!d) return null;
      for (const l of locks) {
        if (l.tu_ngay <= d && d <= l.den_ngay && (l.kho_id == null || l.kho_id === khoId)) {
          return l.hanh_dong === "khoa" ? l : null;
        }
      }
      return null;
    },
    [locks],
  );

  // Tìm kiếm (số CT / mã / tên hàng) + phân trang — client-side trên dữ liệu đã tải.
  const filteredRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((r) => {
      if (!inDateRange((r.ngay_ct ?? "").slice(0, 10), { from: ctFrom, to: ctTo })) return false;
      if (!inNumRange(r.so_luong, { from: slFrom, to: slTo })) return false;
      if (!inNumRange(r.don_gia, { from: dgFrom, to: dgTo })) return false;
      if (!inNumRange(r.thanh_tien, { from: ttFrom, to: ttTo })) return false;
      if (!q) return true;
      return (
        (r.so_ct ?? "").toLowerCase().includes(q) ||
        (r.ma_hang ?? "").toLowerCase().includes(q) ||
        (r.ten_hang ?? "").toLowerCase().includes(q)
      );
    });
  }, [rows, search, ctFrom, ctTo, slFrom, slTo, dgFrom, dgTo, ttFrom, ttTo]);

  const total = useMemo(
    () => filteredRows.reduce((s, r) => s + (r.thanh_tien ?? 0), 0),
    [filteredRows],
  );
  const pageCount = Math.max(1, Math.ceil(filteredRows.length / PAGE_SIZE));
  const pagedRows = useMemo(
    () => filteredRows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [filteredRows, page],
  );

  // Lọc cho "Lịch sử thao tác" (tìm phạm vi/người/tên kỳ/ngày + lọc hành động Khóa/Mở).
  const [histQuery, setHistQuery] = useState("");
  const [histAction, setHistAction] = useState<"all" | "khoa" | "mo">("all");
  // Lọc cho "Kỳ đã khóa" (tìm tên kỳ/phạm vi/ngày).
  const [kyQuery, setKyQuery] = useState("");
  // Lọc theo TỪNG CỘT ngày (funnel ở tiêu đề cột). KHOẢNG NGÀY dùng chung Lịch sử + Kỳ (chồng lấn).
  const [lockTu, setLockTu] = useState("");
  const [lockDen, setLockDen] = useState("");
  const [tdFrom, setTdFrom] = useState(""); // Lịch sử · Thời điểm (khoa_luc)
  const [tdTo, setTdTo] = useState("");
  const [klFrom, setKlFrom] = useState(""); // Kỳ · Khóa lúc (khoa_luc)
  const [klTo, setKlTo] = useState("");
  useEffect(() => {
    setPage(1);
  }, [search, soChieu, khoId, tu, den, tab, histQuery, histAction, kyQuery, lockTu, lockDen,
      ctFrom, ctTo, tdFrom, tdTo, klFrom, klTo, slFrom, slTo, dgFrom, dgTo, ttFrom, ttTo]);

  // Kỳ [tu,den] có chồng lấn khoảng lọc [lockTu,lockDen]? (đầu nào rỗng = không chặn phía đó).
  const lockInRange = (tuNgay: string, denNgay: string) => {
    if (lockTu && denNgay.slice(0, 10) < lockTu) return false;
    if (lockDen && tuNgay.slice(0, 10) > lockDen) return false;
    return true;
  };

  // --- Lịch sử thao tác: lọc rồi phân trang (dùng chung `page`; reset ở effect trên) ---
  const filteredLocks = useMemo(() => {
    const q = histQuery.trim().toLowerCase();
    return locks.filter((l) => {
      if (histAction !== "all" && l.hanh_dong !== histAction) return false;
      if (!lockInRange(l.tu_ngay, l.den_ngay)) return false;
      if (!inDateRange((l.khoa_luc ?? "").slice(0, 10), { from: tdFrom, to: tdTo })) return false;
      if (!q) return true;
      const pv = l.kho_id == null ? "toàn kho" : l.kho_ten ?? "";
      return (
        pv.toLowerCase().includes(q) ||
        (l.nguoi_khoa_ten ?? "").toLowerCase().includes(q) ||
        (l.ten ?? "").toLowerCase().includes(q) ||
        `${fmtDate(l.tu_ngay)} – ${fmtDate(l.den_ngay)}`.toLowerCase().includes(q)
      );
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locks, histQuery, histAction, lockTu, lockDen, tdFrom, tdTo]);
  const histPageCount = Math.max(1, Math.ceil(filteredLocks.length / PAGE_SIZE));
  const pagedLocks = useMemo(
    () => filteredLocks.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [filteredLocks, page],
  );

  // --- Kỳ đã khóa: lọc rồi phân trang ---
  const filteredKy = useMemo(() => {
    const q = kyQuery.trim().toLowerCase();
    return kyList.filter((k) => {
      if (!lockInRange(k.tu_ngay, k.den_ngay)) return false;
      if (!inDateRange((k.khoa_luc ?? "").slice(0, 10), { from: klFrom, to: klTo })) return false;
      if (!q) return true;
      const pv = k.kho_id == null ? "toàn kho" : k.kho_ten ?? "";
      return (
        (k.ten ?? "").toLowerCase().includes(q) ||
        pv.toLowerCase().includes(q) ||
        `${fmtDate(k.tu_ngay)} – ${fmtDate(k.den_ngay)}`.toLowerCase().includes(q)
      );
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kyList, kyQuery, lockTu, lockDen, klFrom, klTo]);
  const kyPageCount = Math.max(1, Math.ceil(filteredKy.length / PAGE_SIZE));
  const pagedKy = useMemo(
    () => filteredKy.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [filteredKy, page],
  );

  // Mỗi kỳ khóa (bản ghi 'khoa' phủ dòng) một MÀU riêng — index theo thứ tự thời gian (tu_ngay).
  const periodIndex = useMemo(() => {
    const ids: number[] = [];
    for (const r of rows) {
      const rec = lockRecordFor(r.kho_id, r.ngay_ghi_so);
      if (rec && !ids.includes(rec.id)) ids.push(rec.id);
    }
    ids.sort((a, b) => {
      const la = locks.find((l) => l.id === a);
      const lb = locks.find((l) => l.id === b);
      return (la?.tu_ngay ?? "").localeCompare(lb?.tu_ngay ?? "");
    });
    const m = new Map<number, number>();
    ids.forEach((id, i) => m.set(id, i));
    return m;
  }, [rows, lockRecordFor, locks]);

  async function doExport() {
    if (soChieu === "CHUYEN") return; // chiều Chuyển kho export qua doExportChuyen
    setExporting(true);
    setError(null);
    try {
      const url = await api.kho.baoCao.exportXlsxBlobUrl(token, soChieu, {
        tu: tu || null,
        den: den || null,
        kho_id: khoId,
        q: search || null,
      });
      const a = document.createElement("a");
      a.href = url;
      // Tên file DỄ HIỂU thay UUID của blob: "Báo cáo nhập/xuất kho [khoảng ngày].xlsx".
      // Bắt buộc gán a.download tên thật — để rỗng thì trình duyệt lấy id blob làm tên (khó nhìn).
      const chieu = soChieu === "NHAP" ? "nhập" : "xuất";
      const khoang = tu || den ? ` ${tu || "…"} đến ${den || "…"}` : "";
      a.download = `Báo cáo ${chieu} kho${khoang}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Không xuất được Excel.");
    } finally {
      setExporting(false);
    }
  }

  async function doExportChuyen() {
    setExporting(true);
    setError(null);
    try {
      const url = await api.kho.baoCao.chuyenKhoExportXlsxBlobUrl(token, {
        tu: tu || null,
        den: den || null,
        kho_id: khoId,
        q: search || null,
      });
      const a = document.createElement("a");
      a.href = url;
      const khoang = tu || den ? ` ${tu || "…"} đến ${den || "…"}` : "";
      a.download = `Báo cáo chuyển kho${khoang}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Không xuất được Excel.");
    } finally {
      setExporting(false);
    }
  }

  // Bấm "Xem sổ kỳ này" ở tab Kỳ đã khóa → nhảy về tab Sổ, set sẵn khoảng ngày (+kho) của kỳ.
  function viewKy(k: KhoaSoKyRow) {
    setTu(k.tu_ngay);
    setDen(k.den_ngay);
    setKhoId(k.kho_id ?? null);
    setSearch("");
    setTab("so");
  }

  // Điền sẵn dialog theo hành động: MỞ → lấy kỳ đang khóa MỚI NHẤT (kyList[0]) để khỏi gõ ngày;
  // KHÓA → về mặc định trống (Đến = hôm nay), phạm vi theo kho đang lọc.
  function fillKhoa(action: "khoa" | "mo") {
    setKhoaHanhDong(action);
    setKhoaError(null);
    setKhoaTen("");
    if (action === "mo" && kyList.length > 0) {
      const k = kyList[0];
      setKhoaScope(k.kho_id ?? "all");
      setKhoaTu(k.tu_ngay.slice(0, 10));
      setKhoaDen(k.den_ngay.slice(0, 10));
    } else if (action === "khoa") {
      setKhoaScope(khoId != null ? khoId : "all");
      setKhoaTu("");
      setKhoaDen(todayISO());
    }
  }
  function openKhoa() {
    loadLocks();
    // Có kỳ đang khóa → mở dialog ở luồng MỞ + điền sẵn kỳ MỚI NHẤT; không có kỳ nào → luồng KHÓA.
    fillKhoa(kyList.length > 0 ? "mo" : "khoa");
    setKhoaOpen(true);
  }
  async function saveKhoa() {
    if (!khoaTu || !khoaDen) {
      setKhoaError("Chọn cả ngày từ và ngày đến.");
      return;
    }
    if (khoaDen < khoaTu) {
      setKhoaError("Ngày đến phải ≥ ngày từ.");
      return;
    }
    setKhoaBusy(true);
    setKhoaError(null);
    try {
      await api.kho.baoCao.setKhoaSo(token, {
        kho_id: khoaScope === "all" ? null : khoaScope,
        tu_ngay: khoaTu,
        den_ngay: khoaDen,
        hanh_dong: khoaHanhDong,
        ten: khoaHanhDong === "khoa" ? khoaTen.trim() || null : null,
      });
      loadLocks();
      setKhoaOpen(false);
    } catch (e) {
      setKhoaError(e instanceof ApiError ? e.message : "Không thực hiện được.");
    } finally {
      setKhoaBusy(false);
    }
  }

  return (
    <main className="rc kho-list" ref={pageRef}>
      <header className="rc__head">
        <div className="rc__headrow">
          <h1 className="rc__title">Báo cáo kho</h1>
          <span className="rc__count">
            {tab === "tong-quan"
              ? `${dashRows.length} dòng sổ`
              : tab === "so"
                ? `${soChieu === "CHUYEN" ? chuyenRows.length : rows.length} dòng`
                : tab === "lichsu"
                  ? `${locks.length} thao tác`
                  : `${kyList.length} kỳ`}
          </span>
          <button
            type="button"
            className="btn btn--secondary kho-export-btn"
            onClick={openKhoa}
            title="Khóa / mở sổ kỳ kế toán theo khoảng ngày — toàn kho hoặc từng kho"
          >
            <LockIcon size={15} /> Khóa / mở kỳ
          </button>
          {tab === "so" && (
            <button
              type="button"
              className="btn btn--secondary kho-export-btn"
              disabled={exporting || (soChieu === "CHUYEN" ? chuyenRows.length === 0 : rows.length === 0)}
              onClick={soChieu === "CHUYEN" ? doExportChuyen : doExport}
              title="Xuất Excel đúng mẫu MISA (theo chiều đang chọn)"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
              {exporting ? "Đang xuất…" : "Xuất Excel"}
            </button>
          )}
        </div>
        <p className="rc__sub">
          Sổ kho từ phiếu ĐÃ GHI SỔ (Nhập · Xuất · Chuyển kho) + khóa/mở kỳ + lịch sử thao tác — cho
          kế toán kho. Loại nhập/xuất MISA do kế toán tự điền trên Excel dựa theo chiều + kho.
        </p>
      </header>

      <div className="kho-shell">
        <div className="kho-shell__fns">
          {(
            [
              ["tong-quan", "Tổng quan"],
              ["so", "Sổ kho"],
              ["lichsu", "Lịch sử thao tác"],
              ["ky", "Kỳ đã khóa"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              className={`kho-shell__fn${tab === id ? " is-active" : ""}`}
              onClick={() => setTab(id)}
            >
              {label}
              {id === "lichsu" && locks.length > 0 ? ` (${locks.length})` : ""}
              {id === "ky" && kyList.length > 0 ? ` (${kyList.length})` : ""}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="rc__empty-state" style={{ color: "var(--rust, #b4531f)" }}>{error}</div>
      )}

      {tab === "tong-quan" && (
        <>
          <div className="rc__toolbar">
            <div className="kho-picker">
              <Select
                ariaLabel="Kho"
                value={khoId == null ? "" : String(khoId)}
                onChange={(v) => setKhoId(v ? Number(v) : null)}
                options={khoOptions}
              />
            </div>
            <label className="kho-baocao__daterow">
              <span>Ngày ghi sổ từ</span>
              <input type="date" className="rc-input" value={tu} max={den || undefined} onChange={(e) => setTu(e.target.value)} />
            </label>
            <label className="kho-baocao__daterow">
              <span>đến</span>
              <input type="date" className="rc-input" value={den} min={tu || undefined} onChange={(e) => setDen(e.target.value)} />
            </label>
            {(tu || den) && (
              <button type="button" className="rc__link-btn" onClick={() => { setTu(""); setDen(""); }}>
                Xóa lọc ngày
              </button>
            )}
          </div>

          {loading ? (
            <div className="rc__empty-state">Đang tải…</div>
          ) : dashRows.length === 0 ? (
            <div className="rc__empty-state">Chưa có phiếu ghi sổ nào trong phạm vi lọc.</div>
          ) : (
            <div className="kho-dash">
              {/* Thẻ KPI — Nhập / Xuất / Chênh lệch / Mặt hàng, theo bộ lọc kho + ngày. */}
              <div className="kho-dash__kpis">
                <div className="kho-dash__card kho-dash__card--in">
                  <span className="kho-dash__label">Tổng nhập</span>
                  <span className="kho-dash__val">{fmtMoney(dash.tongNhap)} đ</span>
                  <span className="kho-dash__sub">{dash.phieuNhap} phiếu nhập</span>
                </div>
                <div className="kho-dash__card kho-dash__card--out">
                  <span className="kho-dash__label">Tổng xuất</span>
                  <span className="kho-dash__val">{fmtMoney(dash.tongXuat)} đ</span>
                  <span className="kho-dash__sub">{dash.phieuXuat} phiếu xuất</span>
                </div>
                <div className="kho-dash__card">
                  <span className="kho-dash__label">Chênh lệch Nhập − Xuất</span>
                  <span className="kho-dash__val">{fmtMoney(dash.chenhLech)} đ</span>
                  <span className="kho-dash__sub">= Tổng nhập − Tổng xuất (theo giá trị)</span>
                </div>
                <div className="kho-dash__card">
                  <span className="kho-dash__label">Mặt hàng luân chuyển</span>
                  <span className="kho-dash__val">{dash.soMatHang}</span>
                  <span className="kho-dash__sub">{dash.soDong} dòng sổ</span>
                </div>
                {dash.chuyenSoDong > 0 && (
                  <div className="kho-dash__card">
                    <span className="kho-dash__label">Chuyển kho nội bộ</span>
                    <span className="kho-dash__val">{fmtMoney(dash.chuyenGiaTri)} đ</span>
                    <span className="kho-dash__sub">
                      {dash.chuyenSoPhieu} phiếu · {dash.chuyenSoDong} dòng
                    </span>
                  </div>
                )}
              </div>

              {dash.soDieuChuyen > 0 && (
                // Chuyển kho là luân chuyển NỘI BỘ — tách khỏi tổng nhập/xuất (mua/bán), có thẻ riêng.
                <p className="kho-hint" style={{ marginTop: "calc(-1 * var(--sp-2))" }}>
                  Chuyển kho nội bộ KHÔNG tính vào Tổng nhập/Tổng xuất (tránh thổi phồng mua/bán). Xem
                  chi tiết + xuất Excel ở tab Sổ kho → chọn chiều "Chuyển kho".
                </p>
              )}

              {/* Biểu đồ cột Nhập/Xuất theo thời gian — CSS thuần, màu khớp app (nhập xanh/xuất cam). */}
              {dash.chuoi.length > 0 && (
                <section className="rc-sec">
                  <h3 className="rc-sec__title">
                    Nhập / Xuất / Chuyển kho theo {dash.theoThang ? "tháng" : "ngày"}
                  </h3>
                  <div className="kho-chart">
                    <div className="kho-chart__legend">
                      <span className="kho-chart__leg kho-chart__leg--in">Nhập</span>
                      <span className="kho-chart__leg kho-chart__leg--out">Xuất</span>
                      <span className="kho-chart__leg kho-chart__leg--move">Chuyển kho</span>
                    </div>
                    <div className="kho-chart__plot">
                      {dash.chuoi.map((c) => (
                        <div
                          className="kho-chart__grp"
                          key={c.key}
                          title={`${c.label} — Nhập ${fmtMoney(c.nhap)} đ · Xuất ${fmtMoney(c.xuat)} đ · Chuyển kho ${fmtMoney(c.chuyen)} đ`}
                        >
                          <div className="kho-chart__bars">
                            <div
                              className="kho-chart__bar kho-chart__bar--in"
                              style={{ height: `${(c.nhap / dash.chuoiMax) * 100}%` }}
                            />
                            <div
                              className="kho-chart__bar kho-chart__bar--out"
                              style={{ height: `${(c.xuat / dash.chuoiMax) * 100}%` }}
                            />
                            <div
                              className="kho-chart__bar kho-chart__bar--move"
                              style={{ height: `${(c.chuyen / dash.chuoiMax) * 100}%` }}
                            />
                          </div>
                          <div className="kho-chart__xlab">{c.label}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                </section>
              )}

              {/* Nhập / Xuất theo kho */}
              <section className="rc-sec">
                <h3 className="rc-sec__title">Nhập / Xuất theo kho</h3>
                <div className="kho-lines__wrap">
                  <table className="kho-lines">
                    <thead>
                      <tr>
                        <th>Kho</th>
                        <th className="kho-num">Giá trị nhập</th>
                        <th className="kho-num">Giá trị xuất</th>
                        <th className="kho-num">Số phiếu</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dash.theoKho.map((k, i) => (
                        <tr key={i}>
                          <td>{k.ten}</td>
                          <td className="kho-num">{fmtMoney(k.nhap)}</td>
                          <td className="kho-num">{fmtMoney(k.xuat)}</td>
                          <td className="kho-num">{k.phieu}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              {/* Tỉ trọng giá trị theo mặt hàng — biểu đồ TRÒN (donut): top 5 + "Khác", cho Nhập & Xuất. */}
              <div className="kho-dash__cols">
                {([
                  ["Tỉ trọng nhập", buildDonut(dash.topNhap, dash.tongNhap)],
                  ["Tỉ trọng xuất", buildDonut(dash.topXuat, dash.tongXuat)],
                ] as const).map(([ten, segs]) => (
                  <section className="rc-sec" key={ten}>
                    <h3 className="rc-sec__title">{ten}</h3>
                    {segs.length === 0 ? (
                      <p className="kho-hint">Không có dòng nào.</p>
                    ) : (
                      <div className="kho-donut">
                        <div
                          className="kho-donut__ring"
                          role="img"
                          aria-label={segs.map((s) => `${s.label} ${Math.round(s.pct)}%`).join(", ")}
                          style={{
                            background: `conic-gradient(${segs
                              .map((s) => `${s.color} ${s.from}% ${s.to}%`)
                              .join(", ")})`,
                          }}
                        />
                        <ul className="kho-donut__legend">
                          {segs.map((s, i) => (
                            <li className="kho-donut__leg" key={i} title={s.label}>
                              <span className="kho-donut__dot" style={{ background: s.color }} />
                              <span className="kho-donut__legname">{s.label}</span>
                              <span className="kho-donut__legpct">{Math.round(s.pct)}%</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </section>
                ))}
              </div>

              {/* Top mặt hàng — BẢNG THUẦN (Mặt hàng · SL · Giá trị). */}
              <div className="kho-dash__cols">
                {([
                  ["Top mặt hàng nhập", dash.topNhap],
                  ["Top mặt hàng xuất", dash.topXuat],
                ] as const).map(([tenBang, top]) => (
                  <section className="rc-sec" key={tenBang}>
                    <h3 className="rc-sec__title">{tenBang}</h3>
                    {top.length === 0 ? (
                      <p className="kho-hint">Không có dòng nào.</p>
                    ) : (
                      <div className="kho-lines__wrap">
                        <table className="kho-lines">
                          <thead>
                            <tr>
                              <th>Mặt hàng</th>
                              <th className="kho-num">SL</th>
                              <th className="kho-num">Giá trị</th>
                            </tr>
                          </thead>
                          <tbody>
                            {top.map((t, i) => (
                              <tr key={i}>
                                <td>
                                  <div className="kho-lines__name">{t.ten ?? "—"}</div>
                                  <div className="kho-lines__code">{t.ma ?? ""}</div>
                                </td>
                                <td className="kho-num">
                                  {fmtQty(t.sl)} {t.dvt ?? ""}
                                </td>
                                <td className="kho-num">{fmtMoney(t.tien)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </section>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {tab === "so" && (
        <>
          <div className="rc__toolbar">
            <div className="kho-picker">
              <Select
                ariaLabel="Chiều"
                value={soChieu}
                onChange={(v) => setSoChieu((v as "NHAP" | "XUAT" | "CHUYEN") || "NHAP")}
                options={[
                  { value: "NHAP", label: "Nhập kho" },
                  { value: "XUAT", label: "Xuất kho" },
                  { value: "CHUYEN", label: "Chuyển kho" },
                ]}
              />
            </div>
            <div className="kho-picker">
              <Select
                ariaLabel="Kho"
                value={khoId == null ? "" : String(khoId)}
                onChange={(v) => setKhoId(v ? Number(v) : null)}
                options={khoOptions}
              />
            </div>
            <input
              className="rc-input"
              style={{ marginLeft: "auto", maxWidth: 260 }}
              placeholder="Tìm số CT / mã / tên hàng…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          {soChieu === "CHUYEN" ? (
            <>
              <p className="rc-field__hint" style={{ margin: "0 0 var(--sp-1)" }}>
                Mỗi dòng = 1 mặt hàng điều chuyển ĐÃ GHI SỔ (Xuất tại kho → Nhập tại kho); giá vốn đi
                theo hàng. "Xuất Excel" theo mẫu MISA "Chuyển kho" — chỉ fill cột có sẵn.
              </p>
              <div className="kho-bc-wrap">
                <table className="rc__table kho-bc">
                  <thead>
                    <tr>
                      <th>Ngày ghi sổ</th>
                      <th>Số CT</th>
                      <th>Từ kho (xuất)</th>
                      <th>Đến kho (nhập)</th>
                      <th>Mã hàng</th>
                      <th>Tên hàng</th>
                      <th>ĐVT</th>
                      <th className="kho-bc__num">Số lượng</th>
                      <th className="kho-bc__num">Đơn giá vốn</th>
                      <th className="kho-bc__num">Tiền vốn</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading ? (
                      <tr><td colSpan={10} className="rc__empty-state">Đang tải…</td></tr>
                    ) : chuyenFiltered.length === 0 ? (
                      <tr><td colSpan={10} className="rc__empty-state">Chưa có điều chuyển nào đã ghi sổ trong kỳ / bộ lọc.</td></tr>
                    ) : (
                      chuyenFiltered.map((r, i) => (
                        <tr key={`${r.voucher_id}-${i}`}>
                          <td>{fmtDate(r.ngay_ghi_so)}</td>
                          <td><span className="rc__code-badge">{r.so_ct}</span></td>
                          <td>{r.kho_xuat_ten ?? "—"}</td>
                          <td>{r.kho_nhap_ten ?? "—"}</td>
                          <td>{r.ma_hang ?? "—"}</td>
                          <td><span className="kho-bc__name" title={r.ten_hang ?? ""}>{r.ten_hang ?? "—"}</span></td>
                          <td>{r.dvt ?? ""}</td>
                          <td className="kho-bc__num">{fmtQty(r.so_luong)}</td>
                          <td className="kho-bc__num">{fmtMoney(r.don_gia_von)}</td>
                          <td className="kho-bc__num">{fmtMoney(r.tien_von)}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                  {chuyenFiltered.length > 0 && (
                    <tfoot>
                      <tr>
                        <td colSpan={9} className="kho-bc__num" style={{ fontWeight: 600 }}>
                          Tổng tiền vốn ({chuyenFiltered.length} dòng)
                        </td>
                        <td className="kho-bc__num" style={{ fontWeight: 600 }}>{fmtMoney(chuyenTongTien)}</td>
                      </tr>
                    </tfoot>
                  )}
                </table>
              </div>
            </>
          ) : (
          <>
          {locks.some((l) => l.hanh_dong === "khoa") && (
            <p className="rc-field__hint" style={{ margin: "0 0 var(--sp-1)" }}>
              <LockIcon /> = phiếu thuộc kỳ đã khóa sổ (không ghi sổ vào kỳ này); mỗi MÀU vạch trái là một kỳ khóa khác nhau.
            </p>
          )}

          <div className="kho-bc-wrap">
            <table className="rc__table kho-bc">
              <thead>
                <tr>
                  <DateFilterHead label="Ngày ghi sổ" from={tu} to={den} onChange={(f, t) => { setTu(f); setDen(t); }} />
                  <DateFilterHead label="Ngày CT" from={ctFrom} to={ctTo} onChange={(f, t) => { setCtFrom(f); setCtTo(t); }} />
                  <th title="Số chứng từ — mã phiếu PNK/PXK">Số CT</th>
                  <th title="Kho của phiếu — kế toán dựa vào chiều + kho để điền mã 0/1/2/3 trên Excel">Kho</th>
                  <th title="Mã vật tư">Mã hàng</th>
                  <th title="Tên vật tư — di chuột xem đầy đủ nếu dài">Tên hàng</th>
                  <th title="Đơn vị tính">ĐVT</th>
                  <NumFilterHead className="kho-bc__num" label="Số lượng" from={slFrom} to={slTo} onChange={(f, t) => { setSlFrom(f); setSlTo(t); }} />
                  <NumFilterHead className="kho-bc__num" label="Đơn giá" from={dgFrom} to={dgTo} onChange={(f, t) => { setDgFrom(f); setDgTo(t); }} />
                  <NumFilterHead className="kho-bc__num" label="Thành tiền" from={ttFrom} to={ttTo} onChange={(f, t) => { setTtFrom(f); setTtTo(t); }} />
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={10} className="rc__empty-state">Đang tải…</td></tr>
                ) : filteredRows.length === 0 ? (
                  <tr><td colSpan={10} className="rc__empty-state">Không có dòng nào (phiếu đã ghi sổ) trong kỳ / bộ lọc.</td></tr>
                ) : (
                  pagedRows.map((r, i) => {
                    const rec = lockRecordFor(r.kho_id, r.ngay_ghi_so);
                    const pIdx = rec ? (periodIndex.get(rec.id) ?? 0) % 3 : -1;
                    return (
                    <tr key={`${r.voucher_id}-${i}`} className={rec ? `kho-bc__lock kho-bc__lock-${pIdx}` : undefined}>
                      <td>
                        {rec && (
                          <span title={`Kỳ đã khóa: ${fmtDate(rec.tu_ngay)} – ${fmtDate(rec.den_ngay)}`} style={{ marginRight: 3 }}>
                            <LockIcon />
                          </span>
                        )}
                        {fmtDate(r.ngay_ghi_so)}
                      </td>
                      <td>{fmtDate(r.ngay_ct)}</td>
                      <td>
                        <span className="rc__code-badge">{r.so_ct}</span>
                        {r.dieu_chuyen && (
                          <span
                            className="badge-sem badge-sem--steel"
                            style={{ marginLeft: 4 }}
                            title="Điều chuyển nội bộ — không tính vào tổng mua/bán"
                          >
                            ⇄ ĐC
                          </span>
                        )}
                      </td>
                      <td>{r.kho_ten ?? "—"}</td>
                      <td>{r.ma_hang ?? "—"}</td>
                      <td>
                        <span className="kho-bc__name" title={r.ten_hang ?? ""}>{r.ten_hang ?? "—"}</span>
                      </td>
                      <td>{r.dvt ?? ""}</td>
                      <td className="kho-bc__num">{fmtQty(r.so_luong)}</td>
                      <td className="kho-bc__num">{fmtMoney(r.don_gia)}</td>
                      <td className="kho-bc__num">{fmtMoney(r.thanh_tien)}</td>
                    </tr>
                    );
                  })
                )}
                {/* Dòng đệm giữ bảng CAO ĐỀU 1 trang dù ít dòng — popover funnel không bị container che. */}
                {filteredRows.length > 0 &&
                  Array.from({ length: Math.max(0, PAGE_SIZE - pagedRows.length) }).map((_, i) => (
                    <tr key={`filler-${i}`} className="rc__filler" aria-hidden="true"><td colSpan={10}>&nbsp;</td></tr>
                  ))}
              </tbody>
              {filteredRows.length > 0 && (
                <tfoot>
                  <tr>
                    <td colSpan={9} className="kho-bc__num" style={{ fontWeight: 600 }}>
                      Tổng thành tiền ({filteredRows.length} dòng)
                    </td>
                    <td className="kho-bc__num" style={{ fontWeight: 600 }}>{fmtMoney(total)}</td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>

          {filteredRows.length > 0 && (
            <div className="kho-bc-pager">
              <button
                type="button"
                className="rc__link-btn"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                ‹ Trước
              </button>
              <span>
                Trang {page}/{pageCount} · {filteredRows.length} dòng
              </span>
              <button
                type="button"
                className="rc__link-btn"
                disabled={page >= pageCount}
                onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
              >
                Sau ›
              </button>
            </div>
          )}
        </>
          )}
        </>
      )}

      {tab === "lichsu" && (
        <>
        <div className="rc__toolbar">
          <div className="kho-picker">
            <Select
              ariaLabel="Hành động"
              value={histAction}
              onChange={(v) => setHistAction((v as "all" | "khoa" | "mo") || "all")}
              options={[
                { value: "all", label: "Tất cả thao tác" },
                { value: "khoa", label: "Khóa kỳ" },
                { value: "mo", label: "Mở kỳ" },
              ]}
            />
          </div>
          <input
            className="rc-input"
            style={{ marginLeft: "auto", maxWidth: 280 }}
            placeholder="Tìm phạm vi / người / tên kỳ / ngày…"
            value={histQuery}
            onChange={(e) => setHistQuery(e.target.value)}
          />
        </div>
        <div className="kho-bc-wrap">
          <table className="rc__table kho-bc">
            <thead>
              <tr>
                <DateFilterHead label="Thời điểm" from={tdFrom} to={tdTo} onChange={(f, t) => { setTdFrom(f); setTdTo(t); }} />
                <th title="Khóa kỳ hoặc Mở lại kỳ đã khóa">Hành động</th>
                <th title="Áp dụng cho toàn bộ kho hay một kho cụ thể">Phạm vi</th>
                <DateFilterHead label="Khoảng ngày" from={lockTu} to={lockDen} onChange={(f, t) => { setLockTu(f); setLockDen(t); }} />
                <th title="Tên kỳ đặt khi khóa (Mở kỳ để trống)">Tên kỳ</th>
                <th title="Kế toán thực hiện thao tác">Người thực hiện</th>
              </tr>
            </thead>
            <tbody>
              {filteredLocks.length === 0 ? (
                <tr><td colSpan={6} className="rc__empty-state">
                  {locks.length === 0 ? "Chưa có thao tác khóa/mở kỳ nào." : "Không có thao tác nào khớp bộ lọc."}
                </td></tr>
              ) : (
                pagedLocks.map((l) => (
                  <tr key={l.id}>
                    <td>{fmtDateTime(l.khoa_luc)}</td>
                    <td>
                      <span
                        className={`badge-sem badge-sem--${l.hanh_dong === "khoa" ? "rust" : "moss"}`}
                        style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
                      >
                        <LockIcon open={l.hanh_dong === "mo"} />
                        {l.hanh_dong === "khoa" ? "Khóa" : "Mở"}
                      </span>
                    </td>
                    <td>{l.kho_id == null ? "Toàn kho" : l.kho_ten ?? `Kho #${l.kho_id}`}</td>
                    <td>{fmtDate(l.tu_ngay)} – {fmtDate(l.den_ngay)}</td>
                    <td>{l.ten ?? "—"}</td>
                    <td>{l.nguoi_khoa_ten ?? "—"}</td>
                  </tr>
                ))
              )}
              {filteredLocks.length > 0 &&
                Array.from({ length: Math.max(0, PAGE_SIZE - pagedLocks.length) }).map((_, i) => (
                  <tr key={`filler-${i}`} className="rc__filler" aria-hidden="true"><td colSpan={6}>&nbsp;</td></tr>
                ))}
            </tbody>
          </table>
        </div>
        {filteredLocks.length > 0 && (
          <div className="kho-bc-pager">
            <button
              type="button"
              className="rc__link-btn"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              ‹ Trước
            </button>
            <span>
              Trang {page}/{histPageCount} · {filteredLocks.length} thao tác
            </span>
            <button
              type="button"
              className="rc__link-btn"
              disabled={page >= histPageCount}
              onClick={() => setPage((p) => Math.min(histPageCount, p + 1))}
            >
              Sau ›
            </button>
          </div>
        )}
        </>
      )}

      {tab === "ky" && (
        <>
        <div className="rc__toolbar">
          <input
            className="rc-input"
            style={{ marginLeft: "auto", maxWidth: 280 }}
            placeholder="Tìm tên kỳ / phạm vi / ngày…"
            value={kyQuery}
            onChange={(e) => setKyQuery(e.target.value)}
          />
        </div>
        <div className="kho-bc-wrap">
          <table className="rc__table kho-bc">
            <thead>
              <tr>
                <DateFilterHead label="Khoảng ngày" from={lockTu} to={lockDen} onChange={(f, t) => { setLockTu(f); setLockDen(t); }} />
                <th title="Tên kỳ đặt khi khóa (tuỳ chọn)">Tên kỳ</th>
                <th title="Toàn kho hay một kho cụ thể">Phạm vi</th>
                <DateFilterHead label="Khóa lúc" from={klFrom} to={klTo} onChange={(f, t) => { setKlFrom(f); setKlTo(t); }} />
                <th aria-hidden="true" />
              </tr>
            </thead>
            <tbody>
              {filteredKy.length === 0 ? (
                <tr>
                  <td colSpan={5} className="rc__empty-state">
                    {kyList.length === 0
                      ? "Chưa có kỳ nào đang khóa. Bấm “Khóa / mở kỳ” để chốt sổ."
                      : "Không có kỳ nào khớp bộ lọc."}
                  </td>
                </tr>
              ) : (
                pagedKy.map((k, i) => (
                  <tr key={`${k.kho_id ?? "all"}-${k.tu_ngay}-${i}`}>
                    <td>{fmtDate(k.tu_ngay)} – {fmtDate(k.den_ngay)}</td>
                    <td>{k.ten ?? "—"}</td>
                    <td>{k.kho_id == null ? "Toàn kho" : k.kho_ten ?? `Kho #${k.kho_id}`}</td>
                    <td>{fmtDateTime(k.khoa_luc)}</td>
                    <td>
                      <button type="button" className="rc__link-btn" onClick={() => viewKy(k)}>
                        Xem sổ kỳ này
                      </button>
                    </td>
                  </tr>
                ))
              )}
              {filteredKy.length > 0 &&
                Array.from({ length: Math.max(0, PAGE_SIZE - pagedKy.length) }).map((_, i) => (
                  <tr key={`filler-${i}`} className="rc__filler" aria-hidden="true"><td colSpan={5}>&nbsp;</td></tr>
                ))}
            </tbody>
          </table>
        </div>
        {filteredKy.length > 0 && (
          <div className="kho-bc-pager">
            <button
              type="button"
              className="rc__link-btn"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              ‹ Trước
            </button>
            <span>
              Trang {page}/{kyPageCount} · {filteredKy.length} kỳ
            </span>
            <button
              type="button"
              className="rc__link-btn"
              disabled={page >= kyPageCount}
              onClick={() => setPage((p) => Math.min(kyPageCount, p + 1))}
            >
              Sau ›
            </button>
          </div>
        )}
        </>
      )}

      <ConfirmDialog
        open={khoaOpen}
        title={khoaHanhDong === "khoa" ? "Khóa kỳ kế toán kho" : "Mở lại kỳ kế toán kho"}
        confirmLabel={khoaHanhDong === "khoa" ? "Khóa sổ" : "Mở sổ"}
        cancelLabel="Hủy"
        busy={khoaBusy}
        error={khoaError}
        confirmDisabled={!khoaTu || !khoaDen}
        onConfirm={saveKhoa}
        onCancel={() => setKhoaOpen(false)}
      >
        <div className="kho-khoa">
          <div className="kho-khoa__field">
            <span className="kho-khoa__label">Hành động</span>
            <div className="kho-khoa__seg">
              {(
                [
                  ["khoa", "Khóa kỳ"],
                  ["mo", "Mở kỳ"],
                ] as const
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  className={`kho-khoa__seg-btn${
                    khoaHanhDong === id ? (id === "khoa" ? " is-khoa" : " is-mo") : ""
                  }`}
                  onClick={() => fillKhoa(id)}
                >
                  <LockIcon open={id === "mo"} size={15} />
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="kho-khoa__field">
            <span className="kho-khoa__label">Phạm vi</span>
            <Select
              portal
              ariaLabel="Phạm vi"
              value={khoaScope === "all" ? "" : String(khoaScope)}
              onChange={(v) => setKhoaScope(v ? Number(v) : "all")}
              options={[
                { value: "", label: "Toàn kho" },
                ...khoList.map((k) => ({ value: String(k.id), label: `${k.ma} · ${k.ten}` })),
              ]}
            />
          </div>

          <div className="kho-khoa__row">
            <div className="kho-khoa__field">
              <label className="kho-khoa__label" htmlFor="khoa-tu">Từ ngày</label>
              <input id="khoa-tu" type="date" className="rc-input" value={khoaTu} max={khoaDen || undefined} onChange={(e) => setKhoaTu(e.target.value)} />
            </div>
            <div className="kho-khoa__field">
              <label className="kho-khoa__label" htmlFor="khoa-den">Đến ngày</label>
              <input id="khoa-den" type="date" className="rc-input" value={khoaDen} min={khoaTu || undefined} onChange={(e) => setKhoaDen(e.target.value)} />
            </div>
          </div>

          {/* KHÓA: đặt TÊN kỳ (tuỳ chọn) — trùng tên kỳ đang khóa khác thì backend chặn. */}
          {khoaHanhDong === "khoa" && (
            <div className="kho-khoa__field">
              <label className="kho-khoa__label" htmlFor="khoa-ten">Tên kỳ (tuỳ chọn)</label>
              <input
                id="khoa-ten"
                className="rc-input"
                value={khoaTen}
                maxLength={120}
                onChange={(e) => setKhoaTen(e.target.value)}
                placeholder="vd Kỳ tháng 7/2026"
              />
            </div>
          )}

          <p className={`kho-khoa__note kho-khoa__note--${khoaHanhDong}`}>
            <LockIcon open={khoaHanhDong === "mo"} size={14} />
            <span>
              {khoaHanhDong === "khoa"
                ? "Phiếu có NGÀY GHI SỔ (ngày hạch toán) trong khoảng này thuộc kỳ đã chốt — không ghi sổ vào kỳ này được."
                : "Mở lại kỳ để ghi sổ tiếp. Đặt “Đến ngày” = ngày cuối đang khóa. Thao tác nào cũng lưu vào Lịch sử."}
            </span>
          </p>

          {/* KHÓA: hiện KỲ KHÓA GẦN NHẤT theo phạm vi (kyList sắp mới nhất trước) để biết đã chốt tới
              đâu → đặt "Từ ngày" cho khớp, tránh giẫm kỳ cũ. */}
          {khoaHanhDong === "khoa" &&
            (() => {
              const k = kyList.find((x) => (x.kho_id ?? "all") === khoaScope);
              return k ? (
                <p className="kho-khoa__kyten">
                  Kỳ khóa gần nhất: <b>{fmtDate(k.tu_ngay)} – {fmtDate(k.den_ngay)}</b>
                  {k.ten ? ` · ${k.ten}` : ""}
                </p>
              ) : null;
            })()}

          {/* MỞ: hiện TÊN kỳ ĐANG KHÓA sắp được mở (nếu kỳ có đặt tên) để biết rõ đang mở kỳ nào. */}
          {khoaHanhDong === "mo" &&
            (() => {
              const k = kyList.find(
                (x) => (x.kho_id ?? "all") === khoaScope && x.den_ngay.slice(0, 10) === khoaDen,
              );
              return k?.ten ? (
                <p className="kho-khoa__kyten">
                  Kỳ đang khóa: <b>{k.ten}</b>
                </p>
              ) : null;
            })()}
        </div>
      </ConfirmDialog>
    </main>
  );
}
