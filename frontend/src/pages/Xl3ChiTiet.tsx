// XẾP LỊCH 3 — POPUP MODAL COMPACT STUDIO (TINH GỌN CAO CẤP)
import { useEffect, useRef, useState } from "react";
import {
  AlertCircle, Box, Calendar, CalendarCheck, Check, Copy,
  FoldVertical, Gauge, History, Layers, PackageCheck, PauseCircle,
  PlayCircle, Printer, RotateCcw, Scissors, Send, Sparkles, Tag, Target, Trash2, Truck, UserCheck, X,
} from "lucide-react";
import type {
  Xl3ChiTiet as Xl3ChiTietData,
  Xl3CongDoan as Xl3CongDoanData,
  Xl3GoiPhatHanh,
  Xl3SoSanh,
} from "../api/client";
import { gio, ngayNgan, thoiLuong, treHan } from "./xl3Shared";

const TRANG_THAI_NHAN: Record<string, string> = {
  nhap: "Nháp",
  cho_bo_sung: "Chờ bổ sung",
  san_sang: "Sẵn sàng",
  da_lap_ke_hoach: "Đã lập kế hoạch",
  da_phat_hanh: "Đã phát hành",
};

export interface Xl3ChiTietProps {
  ct: Xl3ChiTietData | null;
  dangTai: boolean;
  suaDuoc: boolean;
  duyetDuoc: boolean;
  dangGhi: boolean;
  /** Trạng thái gói đã thả xuống xưởng. `null` = chưa hỏi xong; `co_goi:false` = chưa phát hành. */
  goi: Xl3GoiPhatHanh | null;
  onDoiGio(gioMoi: string): void;
  onBoLich(): void;
  onPhatHanh(): void;
  onThuHoi(): void;
  onCapNhat(): void;
  onDong(): void;
  /** Nạp bảng so sánh hai phiên bản. Trang cha giữ token nên panel không tự gọi API. */
  onSoSanh(a: number, b: number): Promise<Xl3SoSanh>;
}

function getCongDoanTheme(ten: string): { icon: JSX.Element; colorClass: string } {
  const t = ten.toLowerCase();
  if (t.includes("ctp") || t.includes("bản") || t.includes("kẽm")) {
    return { icon: <Layers size={13} />, colorClass: "xl3-c-icon--ctp" };
  }
  if (t.includes("cắt") || t.includes("xả")) {
    return { icon: <Scissors size={13} />, colorClass: "xl3-c-icon--cat" };
  }
  if (t.includes("in")) {
    return { icon: <Printer size={13} />, colorClass: "xl3-c-icon--in" };
  }
  if (t.includes("cán") || t.includes("màng") || t.includes("phủ") || t.includes("uv") || t.includes("ép kim")) {
    return { icon: <Sparkles size={13} />, colorClass: "xl3-c-icon--can" };
  }
  if (t.includes("bế") || t.includes("dập")) {
    return { icon: <Box size={13} />, colorClass: "xl3-c-icon--be" };
  }
  if (t.includes("dán") || t.includes("gấp") || t.includes("đóng cuốn")) {
    return { icon: <FoldVertical size={13} />, colorClass: "xl3-c-icon--dan" };
  }
  if (t.includes("kcs") || t.includes("đóng gói") || t.includes("giao")) {
    return { icon: <PackageCheck size={13} />, colorClass: "xl3-c-icon--kcs" };
  }
  return { icon: <Box size={13} />, colorClass: "xl3-c-icon--default" };
}

function tinhDemNguocHan(isoHan: string | null | undefined): { nhan: string; loai: "tre" | "sat" | "an_toan" | "khong" } {
  if (!isoHan) return { nhan: "Chưa gán", loai: "khong" };
  const m = isoHan.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return { nhan: "—", loai: "khong" };
  const target = new Date(+m[1], +m[2] - 1, +m[3], 23, 59, 59).getTime();
  const now = new Date().getTime();
  const diffNgay = Math.ceil((target - now) / (1000 * 60 * 60 * 24));
  if (diffNgay < 0) {
    return { nhan: `Quá hạn ${Math.abs(diffNgay)} ngày`, loai: "tre" };
  } else if (diffNgay === 0) {
    return { nhan: "Hạn hôm nay", loai: "sat" };
  } else if (diffNgay <= 2) {
    return { nhan: `Còn ${diffNgay} ngày`, loai: "sat" };
  } else {
    return { nhan: `Còn ${diffNgay} ngày`, loai: "an_toan" };
  }
}

/** Đối chiếu NGÀY XONG THEO LỊCH với MỤC TIÊU hoàn thành SX. Hai thứ này hay bị đọc lẫn: mục tiêu
 *  là mốc kinh doanh cam kết, còn ngày xong là kết quả xếp lịch tính ra — chênh nhau bao nhiêu mới
 *  là câu người điều độ cần. `tre` lấy từ `treHan()`: dương = trễ, âm = xong sớm. */
function doiChieuMucTieu(tre: number | null): { nhan: string; loai: "tre" | "khit" | "som" | "khong" } {
  if (tre === null) return { nhan: "", loai: "khong" };
  if (tre > 0) return { nhan: `Trễ mục tiêu ${tre} ngày`, loai: "tre" };
  if (tre >= -1) return { nhan: "Vừa khít mục tiêu", loai: "khit" };
  return { nhan: `Sớm hơn mục tiêu ${Math.abs(tre)} ngày`, loai: "som" };
}

/** Nhãn MÁY của một bước. Lệnh đã phát hành thì máy thật nằm ở công việc dưới xưởng, không phải ô
 *  máy kế hoạch — khi hai cái lệch nhau phải nói ra cả hai, vì số giờ ở cột bên tính theo máy đang
 *  chạy chứ không theo máy kế hoạch. */
function nhanMay(c: Xl3CongDoanData): JSX.Element {
  if (!c.may_ten) return <span title="Bước chưa gán máy nên chưa tính được giờ chạy">{c.to_ten ?? "Chưa gán máy"}</span>;
  return (
    <>
      <span title={c.may_nguon === "thuc_thi" ? "Máy đang giao chạy dưới xưởng" : "Máy kế hoạch (lệnh chưa phát hành)"}>
        {c.may_ten}
      </span>
      {c.may_ke_hoach_ten && (
        <span className="xl3-c-may-kh" title={`Kế hoạch ban đầu: ${c.may_ke_hoach_ten} — xưởng đã đổi máy`}>
          {" ≠ KH "}{c.may_ke_hoach_ten}
        </span>
      )}
    </>
  );
}

/** Trạng thái thẻ việc dưới xưởng → nhãn + hậu tố class. `null` ⇔ lệnh chưa phát hành: bước
 *  không có lớp thực tế nào, và cả khối KH/TT bên dưới cũng vắng theo. */
const TT_BUOC: Record<string, { chu: string; cls: string }> = {
  released: { chu: "Chờ chạy", cls: "cho" },
  running: { chu: "Đang chạy", cls: "chay" },
  paused: { chu: "Tạm dừng", cls: "dung" },
  completed: { chu: "Xong", cls: "xong" },
};

/** Chênh mốc kết thúc của MỘT bước → chữ + hậu tố class. Server đã tính sẵn `lech_phut` trên mốc
 *  gốc; ở đây chỉ đọc dấu. Ngưỡng ±15 phút gọi là "đúng giờ": xưởng ghi mốc bằng tay, chênh trong
 *  một phần tư giờ là nhiễu ghi chép chứ không phải tín hiệu điều độ cần thấy. */
function nhanLech(phut: number | null): { chu: string; cls: string } | null {
  if (phut === null) return null;
  if (Math.abs(phut) <= 15) return { chu: "đúng giờ", cls: "khit" };
  const d = thoiLuong(Math.abs(phut));
  return phut > 0 ? { chu: `muộn ${d}`, cls: "tre" } : { chu: `sớm ${d}`, cls: "som" };
}

/** Nhãn SỐ LƯỢNG VÀO. Chưa khai thì nói "chưa khai SL vào" chứ đừng in "0 tờ": số 0 đọc như bước
 *  không nhận gì, và đơn vị "tờ" trước đây là mặc định bịa ra khi bước không khai đơn vị. */
function nhanSl(c: Xl3CongDoanData): string {
  if (c.so_luong_vao == null || c.so_luong_vao <= 0) return " · chưa khai SL vào";
  const dv = c.don_vi_vao_ten ?? c.don_vi_vao;
  return ` · ${c.so_luong_vao.toLocaleString("vi-VN")}${dv ? ` ${dv}` : ""}`;
}

export function Xl3ChiTiet({
  ct, dangTai, suaDuoc, duyetDuoc, dangGhi, goi,
  onDoiGio, onBoLich, onPhatHanh, onThuHoi, onCapNhat, onDong, onSoSanh,
}: Xl3ChiTietProps) {
  const [copied, setCopied] = useState(false);
  // Khối lịch sử phiên bản: đóng mặc định — panel đã dày, và câu hỏi "lịch đã đổi thế nào" là
  // câu hỏi thỉnh thoảng, không phải thứ đọc mỗi lần mở lệnh.
  const [moLichSu, setMoLichSu] = useState(false);
  const [chon, setChon] = useState<number[]>([]);
  const [soSanh, setSoSanh] = useState<Xl3SoSanh | null>(null);
  const [loiSoSanh, setLoiSoSanh] = useState<string | null>(null);
  const capA = chon.length === 2 ? Math.min(chon[0], chon[1]) : null;
  const capB = chon.length === 2 ? Math.max(chon[0], chon[1]) : null;
  // Trang cha truyền hàm nội tuyến ⇒ mỗi lần render là một hàm MỚI. Đưa thẳng vào deps của
  // useEffect thì nó gọi lại API sau mỗi render, không dừng. Giữ qua ref, deps chỉ là cặp số.
  const refSoSanh = useRef(onSoSanh);
  refSoSanh.current = onSoSanh;

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onDong();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onDong]);

  const lsxId = ct?.lsx_id;
  // Đổi lệnh thì mọi thứ của khối lịch sử phải về 0 — không thì bảng so sánh của lệnh trước còn
  // nằm đó dưới mã lệnh mới, và nó trông hoàn toàn hợp lý.
  useEffect(() => {
    setMoLichSu(false);
    setChon([]);
    setSoSanh(null);
    setLoiSoSanh(null);
  }, [lsxId]);

  useEffect(() => {
    if (capA == null || capB == null) {
      setSoSanh(null);
      return;
    }
    let huy = false;
    // Xoá bảng cũ TRƯỚC khi gọi: nếu để nguyên, tiêu đề đã nhảy sang "So v8 → v9" mà bên dưới vẫn
    // là các dòng của v7 → v8 — người đọc không có cách nào biết mình đang nhìn cặp nào.
    setSoSanh(null);
    setLoiSoSanh(null);
    refSoSanh.current(capA, capB)
      .then((r) => { if (!huy) setSoSanh(r); })
      .catch((e) => { if (!huy) { setSoSanh(null); setLoiSoSanh(e?.message ?? "Không so được."); } });
    return () => { huy = true; };
  }, [capA, capB]);

  if (!ct && !dangTai) return null;

  const daXep = !!ct?.bat_dau_at;
  const daPhatHanh = ct?.trang_thai === "da_phat_hanh";
  // Gói đã có việc chạy ⇒ thu hồi CẢ gói là xoá việc thợ đã làm, server chặn (§4.3). Bày nút xám
  // kèm câu nói rõ ngay cạnh — tooltip thôi thì người dùng gõ xong lý do mới biết mình đâm tường.
  const soDaBatDau = goi?.co_goi ? (goi.so_da_bat_dau ?? 0) : 0;
  const khoaThuHoi = !!goi?.co_goi && goi.cho_phep_thu_hoi === false;
  const capNhatDuoc = !!goi?.co_goi && goi.cho_phep_cap_nhat === true && soDaBatDau > 0;
  const tre = ct ? treHan(ct) : null;
  const gioInput = (ct?.bat_dau_at ?? "").slice(0, 16);
  const demNguocSx = tinhDemNguocHan(ct?.han_hoan_thanh_sx);
  const demNguocGiao = tinhDemNguocHan(ct?.han_giao_khach);
  const soVoiMucTieu = doiChieuMucTieu(tre);
  // Chênh giữa "xong theo thực tế" và "xong theo lịch". `null` khi lệnh chưa phát hành.
  const lechThucTe = ct?.co_thuc_te ? nhanLech(ct.lech_ket_thuc_phut) : null;
  // Lệnh đã có việc chạy dưới xưởng ⇒ ô giờ đổi nghĩa thành "bắt đầu phần còn lại".
  const daChayDo = !!ct?.co_thuc_te && !!ct.thuc_bat_dau_lenh;

  const phienBans = goi?.co_goi ? (goi.phien_bans ?? []) : [];
  // Bấm phiên bản thứ nhất là chọn, thứ hai là so; bấm lại cái đang chọn thì bỏ nó ra. Không dựng
  // hai ô select: người dùng đang NHÌN danh sách, bắt họ rời mắt xuống hai dropdown là thừa.
  const chonPhienBan = (so: number) => {
    setChon((cu) => {
      if (cu.includes(so)) return cu.filter((x) => x !== so);
      if (cu.length < 2) return [...cu, so];
      return [cu[1], so];
    });
  };

  const handleCopy = () => {
    if (ct?.ma) {
      navigator.clipboard.writeText(ct.ma);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  };

  return (
    <div className="xl3-modal-overlay" onClick={(e) => e.target === e.currentTarget && onDong()}>
      <div className="xl3-modal xl3-modal--compact" role="dialog" aria-modal="true">
        {dangTai && !ct ? (
          <div style={{ padding: "40px", textAlign: "center", color: "var(--ash-2)" }}>
            Đang tải dữ liệu lệnh sản xuất…
          </div>
        ) : ct ? (
          <>
            {/* Header Tinh gọn 2 dòng sắc nét */}
            <header className="xl3-modal__dau xl3-modal__dau--compact">
              <div className="xl3-modal__dau-trai">
                <div className="xl3-modal__ma-cum">
                  <span className="xl3-modal__ma">{ct.ma}</span>
                  <button
                    type="button"
                    onClick={handleCopy}
                    className="xl3-copy-btn"
                    title="Sao chép mã lệnh"
                  >
                    {copied ? <Check size={12} color="var(--moss-deep)" /> : <Copy size={12} />}
                    <span>{copied ? "Đã chép" : "Mã LSX"}</span>
                  </button>
                  {ct.is_rush && <span className="xl3-gap">GẤP</span>}
                  <span className={`xl3-tt xl3-tt--pulse xl3-tt--${ct.trang_thai}`}>
                    {TRANG_THAI_NHAN[ct.trang_thai] ?? ct.trang_thai}
                  </span>
                </div>
                <div className="xl3-modal__sub-line">
                  <span className="xl3-modal__ten-sp">{ct.ten || "—"}</span>
                  <span className="xl3-modal__sub-sep">·</span>
                  <span className="xl3-modal__sub-kh">{ct.customer_name ?? "Khách lẻ"}</span>
                  {ct.customer_po_no && <span className="xl3-modal__sub-po">PO: {ct.customer_po_no}</span>}
                </div>
              </div>
              <button type="button" className="xl3-modal__dong" onClick={onDong} aria-label="Đóng popup">
                <X size={16} />
              </button>
            </header>

            {/* Thân Modal 2 Cột Studio */}
            <div className="xl3-modal__than">
              {/* CỘT TRÁI: ĐIỀU ĐỘ, DEADLINE & THÔNG SỐ */}
              <div className="xl3-modal__col-trai">
                {/* Khối Kế hoạch chạy */}
                <div className={`xl3-modal__card${tre !== null && tre > 0 ? " xl3-modal__card--tre" : ""}`}>
                  {/* Lệnh đã chạy dở thì ô này KHÔNG còn là "bắt đầu cả lệnh" — lệnh bắt đầu
                      lúc nào là chuyện đã rồi. Nó là mốc bắt đầu PHẦN CÒN LẠI, và nhãn phải nói
                      thẳng ra: người dùng gõ 11/09 rồi đọc lại chính con số đó sẽ tưởng cả lệnh
                      dời sang 11/09, trong khi bước đã xong vẫn nằm ở 9/9. */}
                  <div className="xl3-modal__card-tieu">
                    <Calendar size={13} /> {daChayDo ? "Bắt đầu phần còn lại" : "Bắt đầu chạy máy"}
                  </div>
                  <div className="xl3-modal__input-wrap">
                    <input
                      type="datetime-local"
                      className="xl3-modal__input"
                      value={gioInput}
                      min="2000-01-01T00:00"
                      max="2099-12-31T23:59"
                      disabled={!suaDuoc || dangGhi}
                      onChange={(e) => e.target.value && onDoiGio(`${e.target.value}:00`)}
                    />
                  </div>
                  {daChayDo && (
                    <div
                      className="xl3-modal__da-chay"
                      title="Không lùi được mốc xuống dưới bước đã xong — máy sẽ tự trượt lên và báo lại."
                    >
                      <PlayCircle size={10} />
                      Lệnh đã bắt đầu {gio(ct.thuc_bat_dau_lenh)} · {ct.so_buoc_xong}/{ct.so_buoc} việc đã xong
                    </div>
                  )}

                  <div className="xl3-modal__stats">
                    <div className="xl3-modal__stat xl3-modal__stat--chay">
                      <span className="xl3-modal__stat-k"><PlayCircle size={10} /> Chạy</span>
                      <span className="xl3-modal__stat-v">{thoiLuong(ct.chay_phut)}</span>
                    </div>
                    <div className="xl3-modal__stat xl3-modal__stat--nghi">
                      <span className="xl3-modal__stat-k"><PauseCircle size={10} /> Nghỉ ca</span>
                      <span className="xl3-modal__stat-v">{thoiLuong(ct.nghi_ngoai_ca_phut)}</span>
                    </div>
                  </div>

                  {/* Ngày xong THEO LỊCH ĐÃ XẾP — khác hẳn MỤC TIÊU ở thẻ dưới, nên tách riêng và
                      nói thẳng chênh nhau mấy ngày, đừng bắt người điều độ tự trừ hai con số. */}
                  <div className={`xl3-modal__ketqua xl3-modal__ketqua--${daXep ? soVoiMucTieu.loai : "chua"}`}>
                    <span className="xl3-modal__ketqua-k">
                      <CalendarCheck size={11} /> Dự kiến xong (theo lịch đã xếp)
                    </span>
                    <div className="xl3-modal__ketqua-body">
                      <span className="xl3-modal__ketqua-v">
                        {daXep ? gio(ct.ket_thuc) : "Chưa xếp lịch"}
                      </span>
                      {daXep && soVoiMucTieu.loai !== "khong" && (
                        <span
                          className={`xl3-modal__ketqua-badge xl3-modal__ketqua-badge--${soVoiMucTieu.loai}`}
                          title={`Mục tiêu hoàn thành SX: ${ngayNgan(ct.han_hoan_thanh_sx)}`}
                        >
                          {soVoiMucTieu.loai === "tre" && <AlertCircle size={11} />}
                          {soVoiMucTieu.nhan}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* SỐ THỨ HAI — tính lại theo việc đã xảy ra. Kế hoạch không bao giờ đúng
                      tuyệt đối: bước xong sớm kéo mốc xong lùi lại, xong muộn đẩy nó ra. Bày
                      CẠNH số kế hoạch chứ không thay nó: đây là màn xếp lịch, người điều độ cần
                      thấy cả cái mình đã hứa lẫn cái đang thành sự thật.
                      CHỈ ĐỌC — máy không tự dời mốc (`docs/spec-thuc-te-vs-ke-hoach.md` §3). */}
                  {ct.co_thuc_te && (
                    <div className={`xl3-modal__ketqua xl3-modal__ketqua--tt xl3-modal__ketqua--${lechThucTe?.cls ?? "khit"}`}>
                      <span className="xl3-modal__ketqua-k">
                        <Gauge size={11} /> Dự kiến xong (theo thực tế)
                      </span>
                      <div className="xl3-modal__ketqua-body">
                        <span className="xl3-modal__ketqua-v">{gio(ct.ket_thuc_thuc_te)}</span>
                        {lechThucTe && (
                          <span
                            className={`xl3-modal__ketqua-badge xl3-modal__ketqua-badge--${lechThucTe.cls}`}
                            title="So với ngày xong theo lịch đã xếp ở trên — dương là thực tế đang kéo lệnh muộn hơn kế hoạch"
                          >
                            {lechThucTe.cls === "tre" && <AlertCircle size={11} />}
                            {lechThucTe.chu} so với kế hoạch
                          </span>
                        )}
                      </div>
                    </div>
                  )}
                </div>

                {/* Vì sao ngày dự kiến có thể SAI: bước chưa gán máy / chưa quy đổi được đơn vị
                    chiếm 0 phút, gia công ngoài chưa khai ngày gửi-nhận. Không có băng này thì
                    lệnh vẫn hiện một ngày trông rất chắc chắn mà bên dưới thiếu cả một bước. */}
                {daXep && ct.ghi_chu.length > 0 && (
                  <div className="xl3-modal__thieu">
                    <AlertCircle size={13} />
                    <div>
                      <strong>Ngày dự kiến còn thiếu dữ kiện:</strong>
                      <ul>
                        {ct.ghi_chu.map((g) => <li key={g}>{g}</li>)}
                      </ul>
                    </div>
                  </div>
                )}

                {/* Khối Deadline Cards: Hạn SX & Hạn Giao Hàng */}
                <div className="xl3-deadline-grid">
                  <div
                    className={`xl3-deadline-card xl3-deadline-card--sx xl3-deadline-card--${demNguocSx.loai}`}
                    title="Mốc kinh doanh yêu cầu xưởng phải xong — KHÔNG phải ngày xong theo lịch đã xếp"
                  >
                    <div className="xl3-deadline-head">
                      <Target size={13} className="xl3-deadline-icon" />
                      <span className="xl3-deadline-label">Mục tiêu hoàn thành SX</span>
                    </div>
                    <div className="xl3-deadline-body">
                      <span className="xl3-deadline-val">{ngayNgan(ct.han_hoan_thanh_sx)}</span>
                      {ct.han_hoan_thanh_sx && (
                        <span
                          className={`xl3-deadline-badge xl3-deadline-badge--${demNguocSx.loai}`}
                          title="Đếm ngược từ hôm nay tới mục tiêu"
                        >
                          {demNguocSx.nhan}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className={`xl3-deadline-card xl3-deadline-card--giao xl3-deadline-card--${demNguocGiao.loai}`}>
                    <div className="xl3-deadline-head">
                      <Truck size={13} className="xl3-deadline-icon" />
                      <span className="xl3-deadline-label">Hạn Giao Khách</span>
                    </div>
                    <div className="xl3-deadline-body">
                      <span className="xl3-deadline-val">{ngayNgan(ct.han_giao_khach)}</span>
                      {ct.han_giao_khach && (
                        <span className={`xl3-deadline-badge xl3-deadline-badge--${demNguocGiao.loai}`}>
                          {demNguocGiao.nhan}
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Bảng Quy cách kỹ thuật & Vật tư */}
                <div className="xl3-modal__card">
                  <div className="xl3-modal__card-tieu">
                    <Tag size={13} /> Quy cách & Vật tư
                  </div>
                  <div className="xl3-spec-table">
                    <div className="xl3-spec-row">
                      <span className="xl3-spec-k">Sản lượng đặt</span>
                      <span className="xl3-spec-v">{ct.so_luong_dat.toLocaleString("vi-VN")} {ct.don_vi_tinh ?? "sp"}</span>
                    </div>
                    <div className="xl3-spec-row">
                      <span className="xl3-spec-k">Tờ kế hoạch</span>
                      <span className="xl3-spec-v">
                        {ct.so_to_ke_hoach.toLocaleString("vi-VN")} tờ
                        {ct.so_con > 1 ? <span className="xl3-spec-sub"> ({ct.so_con} con)</span> : ""}
                      </span>
                    </div>
                    {ct.giay && (
                      <div className="xl3-spec-row">
                        <span className="xl3-spec-k">Loại giấy</span>
                        <span className="xl3-spec-v">
                          <span className="xl3-paper-pill">{ct.giay}</span>
                        </span>
                      </div>
                    )}
                    {ct.kho_in && (
                      <div className="xl3-spec-row">
                        <span className="xl3-spec-k">Khổ & Màu</span>
                        <span className="xl3-spec-v">
                          <span className="xl3-spec-pill">{ct.kho_in}{ct.so_mau ? ` · ${ct.so_mau}m` : ""}</span>
                        </span>
                      </div>
                    )}
                    {ct.sale_name && (
                      <div className="xl3-spec-row">
                        <span className="xl3-spec-k"><UserCheck size={11} style={{ display: "inline", marginRight: 4 }} />Kinh doanh</span>
                        <span className="xl3-spec-v">{ct.sale_name}</span>
                      </div>
                    )}
                  </div>
                </div>

                {ct.luu_y_gui_xuong && (
                  <div className="xl3-luu-y">
                    <AlertCircle size={14} />
                    <div><strong>Dặn xưởng:</strong> {ct.luu_y_gui_xuong}</div>
                  </div>
                )}

                {/* LỊCH SỬ PHIÊN BẢN. Mỗi lần "Phát hành cập nhật" là một lời hứa mới với tổ;
                    không bày ra thì người điều độ đổi lịch xong không có gì đối chiếu ngoài trí
                    nhớ. Bấm hai phiên bản để so từng bước. */}
                {phienBans.length > 0 && (
                  <div className="xl3-modal__card xl3-ls">
                    <button
                      type="button"
                      className="xl3-ls-dau"
                      onClick={() => setMoLichSu((v) => !v)}
                      aria-expanded={moLichSu}
                    >
                      <span className="xl3-modal__card-tieu" style={{ margin: 0 }}>
                        <History size={13} /> Lịch sử phát hành
                      </span>
                      <span className="xl3-ls-dem">{phienBans.length} phiên bản</span>
                    </button>

                    {moLichSu && (
                      <>
                        <div className="xl3-ls-list">
                          {phienBans.map((p) => {
                            const dangChon = chon.includes(p.so);
                            return (
                              <button
                                key={p.so}
                                type="button"
                                className={`xl3-ls-item${dangChon ? " xl3-ls-item--chon" : ""}`}
                                onClick={() => chonPhienBan(p.so)}
                                title="Bấm hai phiên bản để so lịch từng bước"
                              >
                                <span className="xl3-ls-v">v{p.so}</span>
                                <span className="xl3-ls-loai">
                                  {p.loai === "cap_nhat" ? "cập nhật" : "phát hành"}
                                </span>
                                <span className="xl3-ls-ly-do">{p.ly_do || "—"}</span>
                                <span className="xl3-ls-luc">{gio(p.luc)}</span>
                              </button>
                            );
                          })}
                        </div>

                        {capA != null && capB != null && (
                          <div className="xl3-ls-so">
                            <div className="xl3-ls-so-dau">
                              So v{capA} → v{capB}
                              <button type="button" className="xl3-ls-bo" onClick={() => setChon([])}>
                                bỏ chọn
                              </button>
                            </div>
                            {loiSoSanh && <div className="xl3-ls-loi">{loiSoSanh}</div>}
                            {!soSanh && !loiSoSanh && <div className="xl3-ls-trong">Đang so…</div>}
                            {soSanh && (
                              soSanh.dong.some((d) => d.doi_gio || d.doi_may) ? (
                                <table className="xl3-ls-bang">
                                  <tbody>
                                    {soSanh.dong.filter((d) => d.doi_gio || d.doi_may).map((d) => (
                                      <tr key={d.cong_viec_id}>
                                        <td className="xl3-ls-b-ten">{d.ten}</td>
                                        <td className="xl3-ls-b-doi">
                                          {d.doi_gio && (
                                            <span className="xl3-ls-b-gio">
                                              {gio(d.a.bat_dau)} → {gio(d.b.bat_dau)}
                                            </span>
                                          )}
                                          {d.doi_may && (
                                            <span className="xl3-ls-b-may">
                                              máy {d.a.may_ten ?? "—"} → {d.b.may_ten ?? "—"}
                                            </span>
                                          )}
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              ) : (
                                /* KHÔNG nói "không đổi gì" chắc nịch: bản ghi lịch sử chỉ có từ
                                   10/09/2026, phiên bản cũ hơn đã bị đè mất và đọc ra y hệt bản
                                   hiện tại. Hai chuyện đó phải phân biệt được. */
                                <div className="xl3-ls-trong">
                                  Không thấy bước nào đổi giữa hai phiên bản này. Lưu ý: bản ghi lịch sử
                                  chỉ có từ 10/09/2026 — các lần cập nhật trước đó đã bị ghi đè, không dựng lại được.
                                </div>
                              )
                            )}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                )}
              </div>

              {/* CỘT PHẢI: QUY TRÌNH SẢN XUẤT VERTICAL PIPELINE TIMELINE */}
              <div className="xl3-modal__col-phai">
                <div className="xl3-pipe-head">
                  <div className="xl3-pipe-title-wrap">
                    <span className="xl3-modal__card-tieu" style={{ margin: 0 }}>
                      <Layers size={13} color="var(--rust)" /> Quy trình sản xuất
                    </span>
                  </div>
                  <span
                    className="xl3-pipe-count"
                    title="Routing RIÊNG của lệnh này (sửa ở Kế hoạch SX), không phải quy trình mẫu. Bàn cấp lệnh trải các bước NỐI ĐUÔI theo thứ tự — bước gắn nhãn 'song song được' là bước không chặn bước cùng lớp, nhưng ở đây vẫn xếp lần lượt."
                  >
                    {ct.cong_doans.length} bước · thứ tự chạy
                    {ct.so_nguoi_tong > 0 ? ` · ${ct.so_nguoi_tong} người` : ""}
                  </span>
                </div>

                <div className="xl3-pipe-card-container">
                  <div className="xl3-pipe-line" />
                  <div className="xl3-pipe-list">
                    {ct.cong_doans.map((c, idx) => {
                      const { icon, colorClass } = getCongDoanTheme(c.ten);
                      const coThoiGian = c.chay_phut > 0 || c.thue_ngoai_ngay != null;
                      const tt = c.trang_thai ? TT_BUOC[c.trang_thai] : null;
                      const lech = nhanLech(c.lech_phut);
                      // Có gì THẬT để bày không: mốc kế hoạch một mình là số thừa ở bàn cấp lệnh
                      // (spec §4) — nó chỉ có nghĩa khi đứng cạnh mốc đã xảy ra.
                      const coMoc = !!(c.ke_hoach_bat_dau || c.thuc_bat_dau);
                      return (
                        <div key={c.id} className={`xl3-pipe-step${coThoiGian ? " xl3-pipe-step--active" : ""}`}>
                          {/* Circle Node trên đường pipeline */}
                          <div className={`xl3-pipe-node ${colorClass}`}>
                            <span className="xl3-pipe-node-num">{idx + 1}</span>
                          </div>

                          {/* Thẻ nội dung công đoạn */}
                          <div className="xl3-pipe-content">
                            <div className={`xl3-c-icon ${colorClass}`}>{icon}</div>
                            <div className="xl3-pipe-info">
                              <span className="xl3-pipe-name">
                                {c.ten}
                                {c.song_song && (
                                  <span
                                    className="xl3-c-song-song"
                                    /* +1 để khớp Hồ sơ LSX: server đếm lớp từ 0, màn đếm từ 1. */
                                    title={`Cùng lớp ${c.lop + 1} với bước khác nên hai bước không chặn nhau. Bàn cấp lệnh vẫn xếp lần lượt — ngày kết thúc đang tính theo kịch bản chạy nối đuôi.`}
                                  >
                                    song song được
                                  </span>
                                )}
                                {tt && (
                                  <span className={`xl3-c-tt xl3-c-tt--${tt.cls}`} title="Trạng thái thẻ việc dưới xưởng">
                                    {tt.chu}
                                  </span>
                                )}
                              </span>
                              <span className="xl3-pipe-sub">
                                {nhanMay(c)}
                                {nhanSl(c)}
                              </span>
                              {/* KẾ HOẠCH ↔ THỰC TẾ của bước. Chỉ hiện khi lệnh đã phát hành —
                                  trước đó không có thẻ việc nào để so, và bày mốc bước một mình
                                  là quay lại đúng thứ spec §4 đã bỏ. */}
                              {coMoc && (
                                <span className="xl3-pipe-moc">
                                  <span className="xl3-pipe-moc-hang">
                                    <span className="xl3-pipe-moc-k">KH</span>
                                    <span className="xl3-pipe-moc-v">
                                      {gio(c.ke_hoach_bat_dau)} → {gio(c.ke_hoach_ket_thuc)}
                                    </span>
                                  </span>
                                  <span className="xl3-pipe-moc-hang xl3-pipe-moc-hang--tt">
                                    <span className="xl3-pipe-moc-k">TT</span>
                                    <span className="xl3-pipe-moc-v">
                                      {c.thuc_bat_dau
                                        ? `${gio(c.thuc_bat_dau)} → ${c.thuc_ket_thuc ? gio(c.thuc_ket_thuc) : "đang chạy"}`
                                        : "chưa vào việc"}
                                    </span>
                                    {lech && (
                                      <span className={`xl3-pipe-lech xl3-pipe-lech--${lech.cls}`}>
                                        {lech.chu}
                                      </span>
                                    )}
                                  </span>
                                </span>
                              )}
                            </div>
                            <div className="xl3-pipe-meta">
                              {c.so_nguoi_chuan > 0 && (
                                <span className="xl3-c-nguoi" title="Số người tiêu chuẩn của bước">
                                  {c.so_nguoi_chuan} người
                                </span>
                              )}
                              <span
                                className={`xl3-pipe-dur${
                                  coThoiGian
                                    ? " xl3-pipe-dur--active"
                                    : c.canh_bao ? " xl3-pipe-dur--thieu" : " xl3-pipe-dur--wait"
                                }`}
                                title={c.canh_bao ?? undefined}
                              >
                                {c.thue_ngoai_ngay != null
                                  ? `Thuê ngoài ${c.thue_ngoai_ngay}d`
                                  : c.chay_phut > 0
                                    ? thoiLuong(c.chay_phut)
                                    : c.canh_bao
                                      ? "Chưa tính được giờ"
                                      : "—"}
                              </span>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>

            {/* Footer Modal Tinh gọn cao cấp */}
            <footer className="xl3-modal__chan xl3-modal__chan--compact">
              <button type="button" className="xl3-nut xl3-nut--phu" onClick={onDong}>
                Đóng
              </button>
              <div className="xl3-modal__actions">
                {duyetDuoc && daPhatHanh && khoaThuHoi && (
                  <span className="xl3-modal__chan-nhac">
                    <AlertCircle size={12} />
                    Đã có {soDaBatDau}/{goi?.so_cong_viec ?? 0} việc bắt đầu — không rút cả gói về được.
                  </span>
                )}
                {suaDuoc && daXep && !daPhatHanh && (
                  <button type="button" className="xl3-nut xl3-nut--nguy-hiem" disabled={dangGhi} onClick={onBoLich}>
                    <Trash2 size={13} /> Bỏ lịch
                  </button>
                )}
                {duyetDuoc && daPhatHanh && (
                  <button
                    type="button"
                    className="xl3-nut xl3-nut--thu-hoi"
                    disabled={dangGhi || khoaThuHoi}
                    title={khoaThuHoi
                      ? "Thu hồi cả gói sẽ xoá luôn việc thợ đã làm — dùng Phát hành cập nhật để đẩy lịch mới cho phần chưa bắt đầu."
                      : undefined}
                    /* `title` một mình thành TÊN của nút với trình đọc màn hình, nuốt mất nhãn
                       nhìn thấy. Ghép nhãn vào đầu `aria-label` để tên đọc lên vẫn là tên nút. */
                    aria-label={khoaThuHoi
                      ? "Thu hồi phát hành — không dùng được: thu hồi cả gói sẽ xoá luôn việc thợ đã làm."
                      : undefined}
                    onClick={onThuHoi}
                  >
                    <RotateCcw size={13} /> Thu hồi phát hành
                  </button>
                )}
                {duyetDuoc && daPhatHanh && capNhatDuoc && (
                  <button
                    type="button"
                    className="xl3-nut xl3-nut--chinh"
                    disabled={dangGhi}
                    title={`Đẩy lịch mới xuống xưởng cho ${goi?.so_chua_bat_dau ?? 0} việc chưa bắt đầu; ${soDaBatDau} việc đã chạy giữ nguyên.`}
                    aria-label={`Phát hành cập nhật — đẩy lịch mới xuống xưởng cho ${goi?.so_chua_bat_dau ?? 0} việc chưa bắt đầu; ${soDaBatDau} việc đã chạy giữ nguyên.`}
                    onClick={onCapNhat}
                  >
                    <Send size={13} /> Phát hành cập nhật
                  </button>
                )}
                {duyetDuoc && daXep && !daPhatHanh && (
                  <button type="button" className="xl3-nut xl3-nut--chinh" disabled={dangGhi} onClick={onPhatHanh}>
                    <Send size={13} /> Phát hành ngay
                  </button>
                )}
              </div>
            </footer>
          </>
        ) : null}
      </div>
    </div>
  );
}

