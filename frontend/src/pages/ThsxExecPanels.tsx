// PHA SAU của DRAWER Thực hiện sản xuất — Giai đoạn 3 (sản lượng · bàn giao · vật tư) + Giai đoạn 4
// (hỗ trợ chéo · phân bổ sản lượng → lương khoán). Gộp thẳng vào drawer `ThsxDrawer` (KHÔNG đẻ màn
// mới): mỗi mặt là một khối; biểu mẫu mở từ nút đầu khối hiện thành hộp thoại nổi (`ThsxModal`),
// còn thao tác trên từng dòng (sửa số, điều chỉnh, huỷ…) vẫn mở tại chỗ ngay dưới dòng đó.
//
// Component KHÔNG tự gọi API: mọi mặt GHI đi qua `exec.*` (controller lo khoá lạc quan + refetch +
// toast). Danh mục "Lý do & lỗi SX" ĐÃ GỠ (mg 0288): không khâu nào bắt nêu lý do nữa, chỗ nào cần
// nói thêm thì có ô mô tả TỰ DO tuỳ chọn.
import { Fragment, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { ReactNode } from "react";
import type {
  SxWorkItemChiTiet, SxBatch, SxBanGiao, SxBanGiaoChangSau, SxPhanBo, SxHoTro, SxHoTroUngVien,
  SxBatchIn, SxBanGiaoDeXuatIn, SxBanGiaoSuaIn, SxBanGiaoDieuChinhIn,
  SxHoTroDeXuatIn, SxBuTruIn, SxLoaiTruIn, SxGoLoaiTruIn,
  SxKcsBatchIn, SxNhapKhoYeuCauIn, SxHuyPhanChuaNhanIn, SxPhanLoaiBtpIn, SxDongThieuIn,
  SxKetQuaNhanh, SxSuCoIn, SxVatTuCap, SxVatTuCapLan, SxVatTuCapDoiChieu,
  SxVatTuDeNghiIn, SxVatTuDeNghiDongIn,
} from "../api/client";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import type { IconName } from "../components/Icons";
import { MaterialCombobox } from "../components/MaterialCombobox";
import { Select, type SelectOption } from "../components/Select";
import { useAuth } from "../auth/useAuth";
import { GIO_NHAP_MAX, GIO_NHAP_MIN, gioNhapHopLe } from "../lib/gioNhap";
import { num, ngayGio, ngay, gioNgan } from "./keHoachSxShared";
import { VoucherDrawer } from "./KhoYeuCauPage";
import { nhanDonVi } from "./lsxBuoc";

// ============================ hợp đồng hành động (controller cấp) ============================
export interface ThsxExec {
  // Đổi máy giữa chừng (§7.2 mở rộng 31/08/2026) — CHẠY thì đóng phiên máy cũ + mở phiên mới
  // CÙNG mốc (giờ máy cũ không mất); TẠM DỪNG thì chỉ đổi máy phân công, không mở phiên.
  doiMay: (mayId: number, lyDo?: string | null) => Promise<boolean>;
  // Báo sự cố tại tổ (31/08/2026) — KHÔNG có bảng sự cố riêng: ghi thẳng vào hộp thư "Báo máy
  // hỏng" của tổ sửa chữa, kèm neo về công việc/lệnh. Nhánh "Dừng sản xuất" gộp luôn cú tạm dừng.
  baoSuCo: (body: SxSuCoIn) => Promise<boolean>;
  taoBatch: (body: SxBatchIn) => Promise<SxKetQuaNhanh[] | null>;
  deXuatBanGiao: (body: SxBanGiaoDeXuatIn) => Promise<boolean>;
  suaBanGiao: (banGiaoId: number, body: SxBanGiaoSuaIn) => Promise<boolean>;
  xacNhanBanGiao: (banGiaoId: number, version: number) => Promise<boolean>;
  dieuChinhBanGiao: (banGiaoId: number, body: SxBanGiaoDieuChinhIn) => Promise<boolean>;
  xacNhanVatTu: (voucherId: number) => Promise<boolean>;
  // Đề nghị cấp vật tư theo công đoạn — `deNghiId` là id ĐỀ NGHỊ SẢN XUẤT, không phải id yêu cầu kho.
  deNghiVatTu: (congViecId: number, body: SxVatTuDeNghiIn) => Promise<boolean>;
  suaDeNghiVatTu: (congViecId: number, deNghiId: number, body: SxVatTuDeNghiIn) => Promise<boolean>;
  deXuatHoTro: (body: SxHoTroDeXuatIn) => Promise<boolean>;
  xacNhanHoTro: (hoTroId: number, version: number) => Promise<boolean>;
  huyHoTro: (hoTroId: number, lyDo: string, version: number) => Promise<boolean>;
  tinhPhanBo: (batchId: number) => Promise<boolean>;
  chotPhanBo: (phanBoId: number, version: number) => Promise<boolean>;
  moLaiPhanBo: (phanBoId: number, version: number) => Promise<boolean>;
  buTru: (batchId: number, body: SxBuTruIn) => Promise<boolean>;
  loaiTru: (batchId: number, body: SxLoaiTruIn) => Promise<boolean>;
  goLoaiTru: (batchId: number, body: SxGoLoaiTruIn) => Promise<boolean>;
  // Giai đoạn 5 — KCS §13 · Kho §14 · Đóng nhóm §16/§13.3 (mọi mặt qua `mutate` ở controller).
  taoBatchKcs: (congViecId: number, body: SxKcsBatchIn) => Promise<boolean>;
  ghiLoiKcs: (
    kcsBatchId: number,
    body: {
      to_chiu_id?: number | null; cong_doan_ref_id?: number | null;
      so_luong?: number; mo_ta?: string | null; don_vi?: string | null; files: File[];
    },
  ) => Promise<boolean>;
  themAnhLoiKcs: (loiId: number, files: File[]) => Promise<boolean>;
  xoaAnhKcs: (anhId: number) => Promise<boolean>;
  taoYeuCauNhap: (body: SxNhapKhoYeuCauIn) => Promise<boolean>;
  huyPhanChuaNhan: (ycId: number, body: SxHuyPhanChuaNhanIn) => Promise<boolean>;
  phanLoaiBtp: (body: SxPhanLoaiBtpIn) => Promise<boolean>;
  dongThieu: (nhomId: number, body: SxDongThieuIn) => Promise<boolean>;
}

interface Props {
  chiTiet: SxWorkItemChiTiet;
  busy: boolean;
  hoTroUngVien: SxHoTroUngVien[];
  exec: ThsxExec;
}

// ============================ helper thuần ==================================
export function toNum(s: string): number { const n = Number(s.replace(/,/g, "")); return Number.isFinite(n) ? n : 0; }
export function toDtLocal(s: string | null | undefined): string {
  if (!s) return "";
  return s.replace(" ", "T").slice(0, 16); // "YYYY-MM-DDTHH:mm"
}
export function todayYmd(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
/** "Bây giờ" theo khuôn `datetime-local` — chỗ dựa khi công việc chưa có mốc dự kiến. */
function nowDtLocal(): string {
  const d = new Date();
  return `${todayYmd()}T${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

const BG_TT: Record<string, { txt: string; cls: string }> = {
  proposed: { txt: "chờ xác nhận", cls: "thsx-x-pill--wait" },
  confirmed: { txt: "đã xác nhận", cls: "thsx-x-pill--ok" },
  adjusted: { txt: "đã điều chỉnh", cls: "thsx-x-pill--adj" },
};
const HT_TT: Record<string, { txt: string; cls: string }> = {
  pending_both: { txt: "chờ hai bên", cls: "thsx-x-pill--wait" },
  confirmed: { txt: "đã chốt", cls: "thsx-x-pill--ok" },
  cancelled: { txt: "đã huỷ", cls: "thsx-x-pill--off" },
};
const PB_TT: Record<string, { txt: string; cls: string }> = {
  draft: { txt: "nháp", cls: "thsx-x-pill--wait" },
  finalized: { txt: "đã chốt", cls: "thsx-x-pill--ok" },
  reopened: { txt: "mở lại", cls: "thsx-x-pill--adj" },
};
// Trạng thái YÊU CẦU KHO của một lần đề nghị — nhãn giữ Y HỆT `REQUEST_STATUS` (khoShared.tsx),
// chỉ đổi sang chữ thường cho khớp văn phong pill của file này. Đừng bịa nhãn khác cho cùng trạng thái.
const VT_TT: Record<string, { txt: string; cls: string }> = {
  approved: { txt: "chờ xử lý", cls: "thsx-x-pill--adj" },
  received: { txt: "kho tiếp nhận", cls: "thsx-x-pill--adj" },
  preparing: { txt: "đang chuẩn bị", cls: "thsx-x-pill--adj" },
  partial: { txt: "đã cấp một phần", cls: "thsx-x-pill--bad" },
  done: { txt: "hoàn tất", cls: "thsx-x-pill--ok" },
  rejected: { txt: "từ chối", cls: "thsx-x-pill--bad" },
  cancelled: { txt: "đã hủy", cls: "thsx-x-pill--off" },
};
/** Ngưỡng "coi như bằng nhau" — khớp `_EPS` phía BE, để hàng khớp không hiện chênh lệch rác.
 *  Dùng cho số CÙNG THANG TỔ KHAI (kế hoạch ↔ đã yêu cầu, "số này có > 0 không"). */
const VT_EPS = 0.0005;
/** Ngưỡng riêng cho phép so ĐÃ QUA KHO. Hai bên lưu hai thang khác nhau: SX giữ 3 chữ số
 *  (`sl_yeu_cau_goc` là `Numeric(18,3)`), kho giữ 2 (`sl_de_nghi` là `Numeric(14,2)`), nên chỉ
 *  riêng làm tròn đã đẻ ra sai khác tới 0,005 — gấp 10 lần `VT_EPS`. Đo thật lúc nghiệm thu: tổ
 *  xin 554 tờ = 166,967 kg, kho cấp đúng 166,97 kg, `lech_thuc_te` ra +0,003 và dòng đeo badge
 *  vàng VĨNH VIỄN dù không ai làm gì sai. Giấy gần như không bao giờ ra số tròn 2 chữ số nên mọi
 *  dòng giấy đều dính, mà cờ lệch lại là tín hiệu DUY NHẤT của cả tính năng đối chiếu.
 *  0,005 = nửa bước lượng tử của `Numeric(_, 2)`: đúng phần sai khác mà cấu trúc bắt buộc phải có.
 *  KHÔNG nới `VT_EPS` lên bằng nó — hằng kia còn gác luật "có xin món này không" (`vtCanLyDo`,
 *  `vtCanTro`, `vtPayloadLines`), nới là đổi luôn luật bắt buộc ghi lý do. */
const VT_EPS_KHO = 0.005;

/** Số LẦN đề nghị CÓ XIN món này — nhân tử của dung sai `VT_EPS_KHO` (xem `vtCoLechThucTe`).
 *  Khớp theo cặp `hang_loai` + `hang_id`, đúng khoá mà `board.py::_vat_tu_cap` dùng để gom.
 *
 *  Dòng số 0 KHÔNG tính, dù nó vẫn nằm trong lần đề nghị đó: bản đối chiếu của sản xuất giữ cả
 *  dòng xin 0 (tổ đã sửa món đó về 0), nhưng `_lines_kho` không đẻ dòng kho cho chúng nên chúng
 *  không đi qua bước làm tròn về `Numeric(14,2)` nào — đếm vào là nới dung sai thêm 0,005 cho một
 *  lần không đóng góp sai số nào, tức bịt bớt cờ lệch THẬT. Xét ở thang GỐC (`sl_yeu_cau_goc`),
 *  đúng thang mà `board.py` cộng dồn để ra `lech_thuc_te`. */
export function vtSoLanCoMon(
  cacDeNghi: { dongs: { hang_loai: string; hang_id: number; sl_yeu_cau_goc: number }[] }[],
  d: { hang_loai: string; hang_id: number },
): number {
  return cacDeNghi.filter(
    (l) => l.dongs.some(
      (x) => x.hang_loai === d.hang_loai && x.hang_id === d.hang_id && x.sl_yeu_cau_goc > 0,
    ),
  ).length;
}

/** Kho thực xuất có LỆCH so với số tổ đã xin không — so ở thang KHO (`VT_EPS_KHO`).
 *  Tách khỏi JSX để test được: đây là vị ngữ quyết định badge vàng của cả bảng đối chiếu.
 *
 *  `soLan` = số lần đề nghị có chứa món này. `VT_EPS_KHO` là dung sai của MỘT lần làm tròn, nhưng
 *  `board.py` CỘNG DỒN `sl_yeu_cau_goc` qua mọi lần đề nghị của cùng một món, nên sai khác do làm
 *  tròn cũng cộng dồn: ba lần bổ sung mỗi lần lệch 0,004 là tổng 0,012 > 0,005 và badge vàng giả
 *  quay lại y như trước bản vá. Nhân dung sai theo số lần cộng vào là đúng chiều tích lũy đó.
 *  Sàn 1: món chưa có lần đề nghị nào (dòng kế hoạch thuần) vẫn phải giữ dung sai một lần. */
export function vtCoLechThucTe(
  d: Pick<SxVatTuCapDoiChieu, "lech_thuc_te">,
  soLan = 1,
): boolean {
  return Math.abs(d.lech_thuc_te) > VT_EPS_KHO * Math.max(1, soLan);
}

// ============================ khối chính ====================================
export function ThsxExecPanels({ chiTiet, busy, hoTroUngVien, exec }: Props) {
  // Nút ghi theo QUYỀN TRÊN CHÍNH công việc này (máy chủ tính theo dòng quyền của tổ): ghi mẻ là
  // Thực hiện lệnh; chia sản lượng · bàn giao · hỗ trợ chéo là Xác nhận sản lượng; vật tư là Kho.
  const quyen = chiTiet.quyen ?? {};
  const canThucHien = !!quyen.run_order;
  const canXacNhan = !!quyen.confirm_output;
  const canKho = !!quyen.warehouse;
  const sl = chiTiet.san_luong;
  const conLai = Math.max(0, sl.tong_tot - sl.da_giao);
  const pbTheoBatch = new Map<number, SxPhanBo>();
  for (const pb of chiTiet.phan_bo) pbTheoBatch.set(pb.batch_id, pb);
  // Tên người tham gia/được phân công — để gọi tên các id 'thiếu chấm công' (họ không có dòng phân bổ).
  const tenNguoi = new Map<number, string>();
  for (const k of chiTiet.khoang_tham_gia) tenNguoi.set(k.employee_id, k.ho_ten);
  for (const p of chiTiet.phan_cong) tenNguoi.set(p.employee_id, p.ho_ten);

  return (
    <>
      <SanLuongSection
        chiTiet={chiTiet} canAssign={canThucHien} canChia={canXacNhan} busy={busy}
        exec={exec} pbTheoBatch={pbTheoBatch}
        tenNguoi={tenNguoi} hoTroUngVien={hoTroUngVien} />
      <BanGiaoSection
        chiTiet={chiTiet} canAssign={canXacNhan} busy={busy}
        conLai={conLai} exec={exec} />
      <VatTuSection chiTiet={chiTiet} canAssign={canKho} busy={busy} exec={exec} tenNguoi={tenNguoi} />
      <HoTroSection
        chiTiet={chiTiet} canAssign={canXacNhan} busy={busy}
        hoTroUngVien={hoTroUngVien} exec={exec} />
    </>
  );
}

// ─────────────────────────── SẢN LƯỢNG (§10-11) ───────────────────────────
function SanLuongSection({
  chiTiet, canAssign, canChia, busy, exec, pbTheoBatch, tenNguoi, hoTroUngVien,
}: {
  /** `canAssign` = ghi mẻ (Thực hiện lệnh); `canChia` = chia/chốt sản lượng từng mẻ (Xác nhận). */
  chiTiet: SxWorkItemChiTiet; canAssign: boolean; canChia: boolean; busy: boolean;
  exec: ThsxExec;
  pbTheoBatch: Map<number, SxPhanBo>; tenNguoi: Map<number, string>; hoTroUngVien: SxHoTroUngVien[];
}) {
  const sl = chiTiet.san_luong;
  const cv = chiTiet.cong_viec;
  const [formOpen, setFormOpen] = useState(false);
  const [ketQuaToa, setKetQuaToa] = useState<SxKetQuaNhanh[] | null>(null);

  return (
    <section className="thsx-psec thsx-x">
      <div className="thsx-psec__h">
        <span className="thsx-psec__title"><Icon name="layers" size={13} /> Sản lượng</span>
        {canAssign && (
          <Button variant="ghost" onClick={() => setFormOpen(true)} disabled={busy} aria-haspopup="dialog">
            <Icon name="plus" size={13} /> Ghi mẻ
          </Button>
        )}
      </div>

      <div className="thsx-batch-metric-strip">
        <div className="thsx-batch-metric-tile">
          <span className="thsx-metric-lbl">Tổng tốt</span>
          <span className="thsx-metric-val thsx-metric-val--done">{num(sl.tong_tot)}</span>
        </div>
        <div className="thsx-batch-metric-tile">
          <span className="thsx-metric-lbl">Đã giao</span>
          <span className="thsx-metric-val">{num(sl.da_giao)}</span>
        </div>
        <div className="thsx-batch-metric-tile">
          <span className="thsx-metric-lbl">Còn lại</span>
          <span className="thsx-metric-val">{num(Math.max(0, sl.tong_tot - sl.da_giao))}</span>
        </div>
        {sl.muc_tieu != null && (
          <div className="thsx-batch-metric-tile">
            <span className="thsx-metric-lbl">Còn thiếu</span>
            <span className={`thsx-metric-val${sl.con_thieu ? " thsx-metric-val--thieu" : ""}`}>
              {sl.con_thieu ? `${num(sl.con_thieu)}${sl.don_vi ? ` ${nhanDonVi(sl.don_vi)}` : ""}` : "Đủ"}
            </span>
          </div>
        )}
      </div>

      {ketQuaToa && ketQuaToa.length > 0 && (
        <div className="thsx-x-toa-banner">
          <span className="thsx-x-toa-banner__title">Đã tự toả sang các lệnh sản xuất:</span>
          <ul className="thsx-x-toa-list">
            {ketQuaToa.map((k) => (
              <li key={k.lsx_id}>
                LSX #{k.lsx_id}: <b>{num(k.so_luong)}</b> {nhanDonVi(k.don_vi)}
                {k.ban_giao_id != null ? " · đã tự bàn giao" : ""}
              </li>
            ))}
          </ul>
          <button
            type="button" className="thsx-x-toa-close" aria-label="Đóng"
            onClick={() => setKetQuaToa(null)}
          >
            ×
          </button>
        </div>
      )}

      {formOpen && (
        <BatchForm cv={cv} busy={busy}
          onXong={(kq) => { setFormOpen(false); setKetQuaToa(kq.length ? kq : null); }}
          exec={exec} />
      )}

      {sl.batches.length === 0 ? (
        <p className="thsx-note">Chưa ghi mẻ sản lượng nào.</p>
      ) : (
        <ul className="thsx-x-list">
          {sl.batches.map((b) => (
            <BatchRow key={b.id} b={b} canAssign={canChia} busy={busy}
              pb={pbTheoBatch.get(b.id) ?? null}
              tenNguoi={tenNguoi} hoTroUngVien={hoTroUngVien} exec={exec} />
          ))}
        </ul>
      )}
    </section>
  );
}

function BatchForm({
  cv, busy, onXong, exec,
}: {
  cv: SxWorkItemChiTiet["cong_viec"]; busy: boolean;
  onXong: (ketQua: SxKetQuaNhanh[]) => void; exec: ThsxExec;
}) {
  const [batDau, setBatDau] = useState(toDtLocal(cv.du_kien_bat_dau));
  const [ketThuc, setKetThuc] = useState(toDtLocal(cv.du_kien_ket_thuc));
  const [tong, setTong] = useState("");
  const [tot, setTot] = useState("");
  const [moTaLoi, setMoTaLoi] = useState("");
  const [ghiChu, setGhiChu] = useState("");
  const nTong = toNum(tong);
  const nTot = toNum(tot);
  const hong = Math.max(0, nTong - nTot);
  const donVi = cv.don_vi_ra ?? cv.don_vi_vao ?? null;

  // `gioNhapHopLe` chứ không phải `!!`: ô ngày-giờ của trình duyệt nhận cả năm 6 chữ số, gửi lên
  // là backend trả 422 mà tổ chỉ thấy "không ghi được".
  const hopLe = gioNhapHopLe(batDau) && gioNhapHopLe(ketThuc) && ketThuc > batDau
    && nTong > 0 && nTot >= 0 && nTot <= nTong;

  async function luu() {
    const body: SxBatchIn = {
      bat_dau: batDau, ket_thuc: ketThuc, tong: nTong, tot: nTot, hong,
      don_vi: donVi,
      mo_ta_loi: hong > 0 && moTaLoi.trim() ? moTaLoi.trim() : null,
      ghi_chu: ghiChu.trim() || null,
    };
    const ketQua = await exec.taoBatch(body);
    if (ketQua) onXong(ketQua);
  }

  return (
    <ThsxModal
      title="Ghi mẻ sản lượng mới" icon="activity" busy={busy} onClose={() => onXong([])}
      badge={donVi ? nhanDonVi(donVi) : null}
      footer={<>
        <Button variant="ghost" onClick={() => onXong([])} disabled={busy}>Huỷ</Button>
        <Button variant="accent" onClick={luu} disabled={busy || !hopLe} className="thsx-glass-btn-save">
          <Icon name="check" size={13} /> Ghi mẻ sản lượng
        </Button>
      </>}
    >
      <div className="thsx-glass-time-grid thsx-x-grid2">
        <Field label="Bắt đầu">
          <input type="datetime-local" className="thsx-x-in thsx-glass-in" min={GIO_NHAP_MIN} max={GIO_NHAP_MAX}
            value={batDau} onChange={(e) => setBatDau(e.target.value)} />
        </Field>
        <Field label="Kết thúc">
          <input type="datetime-local" className="thsx-x-in thsx-glass-in" min={GIO_NHAP_MIN} max={GIO_NHAP_MAX}
            value={ketThuc} onChange={(e) => setKetThuc(e.target.value)} />
        </Field>
      </div>

      <div className="thsx-glass-metric-grid thsx-x-grid2">
        <Field label={`Tổng${donVi ? ` (${nhanDonVi(donVi)})` : ""}`}>
          <input type="number" min={0} className="thsx-x-in thsx-glass-in thsx-glass-in--num"
            placeholder="0" value={tong}
            onChange={(e) => {
              const val = e.target.value;
              setTong(val);
              if (!tot) setTot(val);
            }}
            inputMode="numeric" />
        </Field>
        <Field label="Tốt">
          <input type="number" min={0} className="thsx-x-in thsx-glass-in thsx-glass-in--num thsx-glass-in--tot"
            placeholder="0" value={tot} onChange={(e) => setTot(e.target.value)} inputMode="numeric" />
        </Field>
      </div>

      <div className={`thsx-glass-hong-tile thsx-x-hong${hong > 0 ? " is-bad" : ""}`}>
        <div className="thsx-glass-hong-left">
          <Icon name={hong > 0 ? "alert" : "check"} size={13} />
          <span>Hỏng: <b className="thsx-num">{num(hong)}</b>{donVi ? ` ${nhanDonVi(donVi)}` : ""}</span>
        </div>
        {nTot > nTong && <span className="thsx-x-err thsx-glass-err">Tốt không được vượt Tổng</span>}
      </div>

      {hong > 0 && (
        <Field label="Mô tả nguyên nhân lỗi">
          <input type="text" className="thsx-x-in thsx-glass-in" value={moTaLoi} onChange={(e) => setMoTaLoi(e.target.value)}
            placeholder="Ví dụ: Bẩn nước ca đầu, nhè màu mực..." />
        </Field>
      )}

      <Field label="Ghi chú">
        <input type="text" className="thsx-x-in thsx-glass-in" value={ghiChu} onChange={(e) => setGhiChu(e.target.value)}
          placeholder="Tuỳ chọn" />
      </Field>
    </ThsxModal>
  );
}

function formatBatchTime(batDau: string | null | undefined, ketThuc: string | null | undefined): string {
  if (!batDau) return "—";
  const d1 = new Date(batDau);
  if (Number.isNaN(d1.getTime())) return "—";
  const m1 = String(d1.getMonth() + 1).padStart(2, "0");
  const dt1 = String(d1.getDate()).padStart(2, "0");
  const hh1 = String(d1.getHours()).padStart(2, "0");
  const mm1 = String(d1.getMinutes()).padStart(2, "0");
  const str1 = `${dt1}/${m1} ${hh1}:${mm1}`;

  if (!ketThuc) return `${str1} → Đang chạy`;
  const d2 = new Date(ketThuc);
  if (Number.isNaN(d2.getTime())) return `${str1} → —`;

  const hh2 = String(d2.getHours()).padStart(2, "0");
  const mm2 = String(d2.getMinutes()).padStart(2, "0");

  if (d1.toDateString() === d2.toDateString()) {
    return `${str1} → ${hh2}:${mm2}`;
  }

  const m2 = String(d2.getMonth() + 1).padStart(2, "0");
  const dt2 = String(d2.getDate()).padStart(2, "0");
  return `${str1} → ${dt2}/${m2} ${hh2}:${mm2}`;
}

/** MỘT MẺ trong danh sách sản lượng. Gấp lại chỉ hiện giờ + số tốt; mở ra là ĐỌC TRỌN mẻ (§5.2):
 *  máy đã chạy, ca, đầu việc, kíp mấy người, các lần dừng máy, rồi tới bảng chia sản lượng. */
export function BatchRow({
  b, canAssign, busy, pb, tenNguoi, hoTroUngVien, exec,
}: {
  b: SxBatch; canAssign: boolean; busy: boolean; pb: SxPhanBo | null;
  tenNguoi: Map<number, string>;
  hoTroUngVien: SxHoTroUngVien[]; exec: ThsxExec;
}) {
  const [mo, setMo] = useState(false);
  return (
    <li className="thsx-x-item">
      <button type="button" className="thsx-x-item__h" onClick={() => setMo((o) => !o)} aria-expanded={mo}>
        <Icon name="chevron" size={12} className={mo ? "" : "thsx-rot-90"} />
        <span className="thsx-x-item__time thsx-num">{formatBatchTime(b.bat_dau, b.ket_thuc)}</span>
        {b.so_nguoi > 0 && <span className="thsx-x-item__kip thsx-num">{b.so_nguoi} thợ</span>}
        <span className="thsx-x-item__spacer" />
        <span className="thsx-batch-pill thsx-batch-pill--tot">{num(b.tot)} tốt</span>
        {b.hong > 0 && <span className="thsx-batch-pill thsx-batch-pill--hong">−{num(b.hong)} hỏng</span>}
      </button>
      {mo && (
        <div className="thsx-x-item__body">
          <div className="thsx-batch-spec-grid">
            <div className="thsx-batch-spec-cell">
              <span className="thsx-batch-spec-label">Tổng / tốt / hỏng</span>
              <span className="thsx-batch-spec-val thsx-num">
                <b>{num(b.tong)}</b> / <b className="thsx-text-emerald">{num(b.tot)}</b> / <b className={b.hong > 0 ? "thsx-text-rose" : ""}>{num(b.hong)}</b>{b.don_vi ? ` ${nhanDonVi(b.don_vi)}` : ""}
              </span>
            </div>
            {b.may_ten && (
              <div className="thsx-batch-spec-cell">
                <span className="thsx-batch-spec-label">Máy</span>
                <span className="thsx-batch-spec-val"><b>{b.may_ten}</b></span>
              </div>
            )}
            {(b.ca_ten || b.dau_viec_ten) && (
              <div className="thsx-batch-spec-cell">
                <span className="thsx-batch-spec-label">Ca / Đầu việc</span>
                <span className="thsx-batch-spec-val">
                  <b>{b.ca_ten ? `${b.ca_ten} • ` : ""}{b.dau_viec_ten ?? ""}</b>
                </span>
              </div>
            )}
            {b.nguoi_tham_gia.length > 0 && (
              <div className="thsx-batch-spec-cell">
                <span className="thsx-batch-spec-label">Người tham gia</span>
                <span className="thsx-batch-spec-val">{b.nguoi_tham_gia.map((p) => p.ho_ten).join(", ")}</span>
              </div>
            )}
            {b.su_co.length > 0 && (
              <div className="thsx-batch-spec-cell thsx-batch-spec-cell--full thsx-batch-spec-cell--bad">
                <span className="thsx-batch-spec-label">Dừng máy</span>
                <span className="thsx-batch-spec-val">{b.su_co.map((s) => `${gioNgan(s.bat_dau)}–${gioNgan(s.ket_thuc)}: ${s.ly_do ?? ""}`).join(" • ")}</span>
              </div>
            )}
            {b.mo_ta_loi && (
              <div className="thsx-batch-spec-cell thsx-batch-spec-cell--full thsx-batch-spec-cell--bad">
                <span className="thsx-batch-spec-label">Lỗi</span>
                <span className="thsx-batch-spec-val"><b>{b.mo_ta_loi}</b></span>
              </div>
            )}
            {b.lot_vao.length > 0 && (
              <div className="thsx-batch-spec-cell thsx-batch-spec-cell--full">
                <span className="thsx-batch-spec-label">Lô vào</span>
                <span className="thsx-batch-spec-val">{b.lot_vao.map((l) => `${num(l.so_luong)}${l.don_vi ? ` ${nhanDonVi(l.don_vi)}` : ""}`).join(" • ")}</span>
              </div>
            )}
            {b.ghi_chu && (
              <div className="thsx-batch-spec-cell thsx-batch-spec-cell--full">
                <span className="thsx-batch-spec-label">Ghi chú</span>
                <span className="thsx-batch-spec-val">{b.ghi_chu}</span>
              </div>
            )}
          </div>

          {/* Chia sản lượng của chính mẻ này (§12) */}
          <PhanBoBlock b={b} pb={pb} chiaNhap={b.chia_du_kien} canAssign={canAssign} busy={busy}
            tenNguoi={tenNguoi} hoTroUngVien={hoTroUngVien} exec={exec} />
        </div>
      )}
    </li>
  );
}

// ─────────────────────────── CHIA SẢN LƯỢNG theo mẻ (§12) ─────────────────
// Khối này CHỈ chia SỐ LƯỢNG cho từng người theo trọng số (phút chấm công hợp lệ × hệ số bậc).
// Không có ô tiền nào: quy sản lượng ra tiền là việc của kế toán lương ở màn "Khoán theo kỳ".
/** Bảng 4 cột của bản chia — dùng CHUNG cho bản nháp (tính lúc đọc) và bản đã lưu, để hai nhánh
 *  không chép nhau rồi lệch nhau. Không có cột tiền nào: sản xuất ghi số lượng. */
function BangChia({ dong }: {
  dong: { employee_id: number; ho_ten: string; so_luong: number;
          he_so_bac: number | null; phut_thuc_te: number | null; la_ho_tro: boolean;
          ngay?: string }[];
}) {
  if (dong.length === 0) return null;
  return (
    <table className="thsx-batch-share-tbl thsx-x-tbl">
      <thead>
        <tr><th>Người</th><th className="r">Sản lượng</th><th className="r">Bậc</th><th className="r">Phút</th></tr>
      </thead>
      <tbody>
        {dong.map((d) => (
          <tr key={`${d.employee_id}-${d.ngay ?? ""}`}>
            <td>{d.ho_ten}{d.la_ho_tro && <span className="thsx-x-tag-ht">hỗ trợ</span>}</td>
            <td className="r thsx-num">{num(d.so_luong)}</td>
            <td className="r thsx-num">{d.he_so_bac != null ? num(d.he_so_bac) : "—"}</td>
            <td className="r thsx-num">{d.phut_thuc_te != null ? num(d.phut_thuc_te) : "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function PhanBoBlock({
  b, pb, chiaNhap, canAssign, busy, tenNguoi, hoTroUngVien, exec,
}: {
  b: SxBatch; pb: SxPhanBo | null; canAssign: boolean; busy: boolean;
  /** Bản chia NHÁP server tính lúc đọc, chỉ có khi mẻ CHƯA có bản chia nào. Có nó thì bảng hiện
   *  NGAY sau khi ghi mẻ — chủ xưởng 11/09/2026: *"hình như thiếu sản lượng"*. */
  chiaNhap?: SxBatch["chia_du_kien"];
  tenNguoi: Map<number, string>;
  hoTroUngVien: SxHoTroUngVien[]; exec: ThsxExec;
}) {
  const [moLaiOpen, setMoLaiOpen] = useState(false);
  const [buTruOpen, setBuTruOpen] = useState(false);
  const [loaiTruFor, setLoaiTruFor] = useState<number | null>(null);  // id đang mở form loại khỏi mẻ
  const [loaiTruLyDo, setLoaiTruLyDo] = useState("");

  if (!pb) {
    // Chưa lưu bản chia nào. Có bản NHÁP từ server ⇒ bày ra luôn: số nháp vẫn là số, còn hơn để
    // tổ trưởng ghi mẻ xong nhìn vào một ô trống không biết ai được bao nhiêu.
    if (chiaNhap) {
      return (
        <div className="thsx-batch-share-card thsx-x-pb">
          <div className="thsx-batch-share-h thsx-x-pb__h">
            <div className="thsx-batch-share-h-title">
              <Icon name="table" size={13} />
              <span className="thsx-x-pb__ttl">Chia sản lượng</span>
              <span className="thsx-x-pill thsx-x-pill--wait">nháp</span>
            </div>
          </div>
          <div className="thsx-batch-share-sum thsx-x-pb__sum">
            <span>Sản lượng chia <b className="thsx-num">{num(chiaNhap.q)}</b>{chiaNhap.don_vi ? ` ${nhanDonVi(chiaNhap.don_vi)}` : ""}</span>
          </div>
          <BangChia dong={chiaNhap.dong} />
          {chiaNhap.canh_bao.length > 0 && (
            <div className="thsx-x-pbwarn" role="status">
              <Icon name="alert" size={14} />
              <div className="thsx-x-pbwarn__body">
                <b>Số nháp — chưa chốt được</b>
                <ul>{chiaNhap.canh_bao.map((c, i) => <li key={i}>{c}</li>)}</ul>
              </div>
            </div>
          )}
          {canAssign && (
            <div className="thsx-batch-share-actions thsx-x-act thsx-x-act--wrap">
              {/* Số đã hiện sẵn ở trên rồi, nên nút ở đây LƯU bản chia (tạo bản nháp thật trong
                  DB) chứ không phải "tính ra số" — tên nút nói đúng việc nó làm. */}
              <Button variant="secondary" onClick={() => void exec.tinhPhanBo(b.id)} disabled={busy}
                title="Lưu bản chia này lại để chốt được">
                <Icon name="calculator" size={13} /> Lưu bản chia
              </Button>
              <Button variant="accent" disabled
                title="Bấm Lưu bản chia rồi mới chốt được">
                <Icon name="lock" size={13} /> Chốt
              </Button>
            </div>
          )}
        </div>
      );
    }
    return (
      <div className="thsx-batch-share-card thsx-x-pb thsx-x-pb--empty">
        <span className="thsx-x-pb__none">Chưa chia sản lượng cho mẻ này.</span>
        {canAssign && (
          <Button variant="secondary" onClick={() => void exec.tinhPhanBo(b.id)} disabled={busy}>
            <Icon name="calculator" size={13} /> Chia sản lượng
          </Button>
        )}
      </div>
    );
  }
  const st = PB_TT[pb.trang_thai] ?? { txt: pb.trang_thai, cls: "thsx-x-pill--wait" };
  const isFinal = pb.trang_thai === "finalized";
  const canGhi = canAssign && !isFinal;

  return (
    <div className="thsx-batch-share-card thsx-x-pb">
      <div className="thsx-batch-share-h thsx-x-pb__h">
        <div className="thsx-batch-share-h-title">
          <Icon name="table" size={13} />
          <span className="thsx-x-pb__ttl">Chia sản lượng</span>
          <span className={`thsx-x-pill ${st.cls}`}>{st.txt}</span>
        </div>
        <span className="thsx-batch-share-ky thsx-num">kỳ {pb.ky_thang}/{pb.ky_nam}</span>
      </div>
      <div className="thsx-batch-share-sum thsx-x-pb__sum">
        <span>Sản lượng chia <b className="thsx-num">{num(pb.q_tra_luong)}</b>{pb.don_vi_tra_luong ? ` ${nhanDonVi(pb.don_vi_tra_luong)}` : ""}</span>
        {pb.tong_ty_le_ho_tro > 0 && <span className="thsx-batch-share-ht">Hỗ trợ <b className="thsx-num">{num(pb.tong_ty_le_ho_tro)}%</b></span>}
      </div>

      <BangChia dong={pb.dong.map((d) => ({ ...d, so_luong: d.so_luong_tra_luong }))} />

      {!pb.can_chot && pb.canh_bao.length > 0 && (
        <div className="thsx-x-pbwarn" role="status">
          <Icon name="alert" size={14} />
          <div className="thsx-x-pbwarn__body">
            <b>Giữ ở nháp — chưa chốt được</b>
            <ul>{pb.canh_bao.map((c, i) => <li key={i}>{c}</li>)}</ul>
          </div>
        </div>
      )}

      {pb.thieu_cham_cong.length > 0 && (
        <div className="thsx-x-pbcc">
          <div className="thsx-x-pbcc__h"><Icon name="alert" size={12} /> Thiếu chấm công hợp lệ</div>
          {pb.thieu_cham_cong.map((eid) => (
            <div key={eid} className="thsx-x-pbcc__row">
              <span className="thsx-x-pbcc__ten">{tenNguoi.get(eid) ?? `NV #${eid}`}</span>
              {canGhi && loaiTruFor !== eid && (
                <Button variant="ghost" onClick={() => { setLoaiTruFor(eid); setLoaiTruLyDo(""); }} disabled={busy}>
                  <Icon name="ban" size={12} /> Loại khỏi mẻ
                </Button>
              )}
              {loaiTruFor === eid && (
                <div className="thsx-x-pbcc__form">
                  <input type="text" className="thsx-x-in" autoFocus value={loaiTruLyDo}
                    onChange={(e) => setLoaiTruLyDo(e.target.value)}
                    placeholder="Lý do (bắt buộc): nghỉ, quên chấm công…" />
                  <Button variant="ghost" onClick={() => setLoaiTruFor(null)} disabled={busy}>Huỷ</Button>
                  <Button variant="accent" disabled={busy || !loaiTruLyDo.trim()}
                    onClick={async () => {
                      if (await exec.loaiTru(b.id, { employee_id: eid, ly_do: loaiTruLyDo.trim() })) setLoaiTruFor(null);
                    }}>
                    <Icon name="check" size={12} /> Xác nhận loại
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {pb.loai_tru.length > 0 && (
        <div className="thsx-x-pblt">
          <div className="thsx-x-pblt__h"><Icon name="ban" size={12} /> Đã loại khỏi mẻ</div>
          {pb.loai_tru.map((lt) => (
            <div key={lt.employee_id} className="thsx-x-pblt__row">
              <span className="thsx-x-pblt__ten">{lt.ho_ten}</span>
              <span className="thsx-x-pblt__ly">{lt.ly_do}</span>
              {canGhi && (
                <Button variant="ghost" onClick={() => void exec.goLoaiTru(b.id, { employee_id: lt.employee_id })} disabled={busy}>
                  <Icon name="rotateCcw" size={12} /> Gỡ
                </Button>
              )}
            </div>
          ))}
        </div>
      )}

      {pb.bu_tru.length > 0 && (
        <div className="thsx-x-butru">
          <div className="thsx-x-butru__h"><Icon name="rotateCcw" size={12} /> Bù trừ kỳ khác</div>
          {pb.bu_tru.map((x) => (
            <div key={x.id} className="thsx-x-butru__row">
              <span>{x.ho_ten}</span>
              <span className="thsx-num">{num(x.so_luong_tra_luong)}</span>
              <span className="thsx-num">→ {x.ky_bu_thang}/{x.ky_bu_nam}</span>
              {x.mo_ta && <span className="thsx-x-butru__mo">{x.mo_ta}</span>}
            </div>
          ))}
        </div>
      )}

      {canAssign && (
        <div className="thsx-batch-share-actions thsx-x-act thsx-x-act--wrap">
          {!isFinal ? (
            <Button variant="accent" onClick={() => void exec.chotPhanBo(pb.phan_bo_id, pb.version)}
              disabled={busy || pb.dong.length === 0 || !pb.can_chot}
              title={pb.dong.length === 0 ? "Chưa có dòng chia sản lượng"
                : !pb.can_chot ? "Chưa chốt được — xử lý cảnh báo bên trên" : undefined}>
              <Icon name="lock" size={13} /> Chốt
            </Button>
          ) : (
            <Button variant="secondary" onClick={() => setMoLaiOpen((o) => !o)} disabled={busy}>
              <Icon name="lockOpen" size={13} /> Mở lại
            </Button>
          )}
          <Button variant="ghost" onClick={() => void exec.tinhPhanBo(b.id)} disabled={busy || isFinal}
            title={isFinal ? "Đã chốt — mở lại trước khi tính lại" : "Tính lại theo roster/sản lượng mới"}>
            <Icon name="refresh" size={13} /> Tính lại
          </Button>
          {canGhi && (
            <Button variant="ghost" onClick={() => setBuTruOpen((o) => !o)} disabled={busy}>
              <Icon name="rotateCcw" size={13} /> Bù trừ
            </Button>
          )}
        </div>
      )}

      {moLaiOpen && (
        <XacNhanForm busy={busy} hoi="Mở lại bản chia sản lượng đã chốt? Kỳ lương gốc phải chưa khoá."
          confirm="Mở lại" onHuy={() => setMoLaiOpen(false)}
          onXac={async () => { if (await exec.moLaiPhanBo(pb.phan_bo_id, pb.version)) setMoLaiOpen(false); }} />
      )}
      {buTruOpen && (
        <BuTruForm batchId={b.id} dong={pb.dong} hoTroUngVien={hoTroUngVien} busy={busy}
          onHuy={() => setBuTruOpen(false)}
          onXong={() => setBuTruOpen(false)} exec={exec} />
      )}
    </div>
  );
}

function BuTruForm({
  batchId, dong, hoTroUngVien, busy, onHuy, onXong, exec,
}: {
  batchId: number; dong: SxPhanBo["dong"]; hoTroUngVien: SxHoTroUngVien[];
  busy: boolean; onHuy: () => void; onXong: () => void; exec: ThsxExec;
}) {
  const now = new Date();
  const [empId, setEmpId] = useState<number | null>(dong[0]?.employee_id ?? null);
  const [sl, setSl] = useState("");
  const [nam, setNam] = useState(String(now.getFullYear()));
  const [thang, setThang] = useState(String(now.getMonth() + 1));
  const [moTa, setMoTa] = useState("");

  // Ứng viên = người đã được chia + ứng viên hỗ trợ (phòng trường hợp ghi cho người ngoài roster).
  const ds = new Map<number, string>();
  for (const d of dong) ds.set(d.employee_id, d.ho_ten);
  for (const h of hoTroUngVien) if (!ds.has(h.id)) ds.set(h.id, `${h.full_name}${h.to_ten ? ` · ${h.to_ten}` : ""}`);

  const nSl = toNum(sl);
  const hopLe = empId != null && nSl > 0 && toNum(nam) > 0 && toNum(thang) >= 1 && toNum(thang) <= 12;

  async function luu() {
    const body: SxBuTruIn = {
      employee_id: empId!, so_luong_tra_luong: nSl,
      ky_bu_nam: toNum(nam), ky_bu_thang: toNum(thang),
      mo_ta: moTa.trim() || null,
    };
    if (await exec.buTru(batchId, body)) onXong();
  }

  return (
    <div className="thsx-x-form thsx-x-form--sub">
      <Field label="Người">
        <select className="thsx-x-sel" value={empId ?? ""} onChange={(e) => setEmpId(e.target.value ? Number(e.target.value) : null)}>
          <option value="">— Chọn người —</option>
          {[...ds].map(([id, nm]) => <option key={id} value={id}>{nm}</option>)}
        </select>
      </Field>
      <div className="thsx-x-grid2">
        <Field label="Sản lượng bù">
          <input type="number" min={0} className="thsx-x-in" value={sl} onChange={(e) => setSl(e.target.value)} inputMode="numeric" />
        </Field>
        <Field label="Kỳ bù (tháng/năm)">
          <div className="thsx-x-ky">
            <input type="number" min={1} max={12} className="thsx-x-in" value={thang} onChange={(e) => setThang(e.target.value)} aria-label="Tháng" />
            <span>/</span>
            <input type="number" className="thsx-x-in" value={nam} onChange={(e) => setNam(e.target.value)} aria-label="Năm" />
          </div>
        </Field>
      </div>
      <Field label="Mô tả">
        <input type="text" className="thsx-x-in" value={moTa} onChange={(e) => setMoTa(e.target.value)}
          placeholder="Bù trừ vì sao? (tuỳ chọn)" />
      </Field>
      <div className="thsx-x-act">
        <Button variant="ghost" onClick={onHuy} disabled={busy}>Huỷ</Button>
        <Button variant="accent" onClick={luu} disabled={busy || !hopLe}>
          <Icon name="check" size={13} /> Ghi bù trừ
        </Button>
      </div>
    </div>
  );
}

// ─────────────────────────── BÀN GIAO (§11.2) ─────────────────────────────
function BanGiaoSection({
  chiTiet, canAssign, busy, conLai, exec,
}: {
  chiTiet: SxWorkItemChiTiet; canAssign: boolean; busy: boolean; conLai: number;
  exec: ThsxExec;
}) {
  const [formOpen, setFormOpen] = useState(false);
  const di = chiTiet.ban_giao_di;
  const den = chiTiet.ban_giao_den;

  return (
    <section className="thsx-psec thsx-x">
      <div className="thsx-psec__h">
        <span className="thsx-psec__title"><Icon name="truck" size={13} /> Bàn giao</span>
        {canAssign && (
          <Button variant="ghost" onClick={() => setFormOpen(true)} disabled={busy} aria-haspopup="dialog">
            <Icon name="send" size={13} /> Đề xuất giao
          </Button>
        )}
      </div>

      {formOpen && (
        <BanGiaoForm chiTiet={chiTiet} conLai={conLai}
          busy={busy} onXong={() => setFormOpen(false)} exec={exec} />
      )}

      {di.length > 0 && (
        <>
          <div className="thsx-x-sub">Giao đi</div>
          <ul className="thsx-x-list">
            {di.map((g) => (
              <BanGiaoRow key={g.id} g={g} phia="di" canAssign={canAssign} busy={busy} exec={exec}
                batches={chiTiet.san_luong.batches} conLai={conLai} />
            ))}
          </ul>
        </>
      )}
      {den.length > 0 && (
        <>
          <div className="thsx-x-sub">Nhận về</div>
          <ul className="thsx-x-list">
            {den.map((g) => (
              <BanGiaoRow key={g.id} g={g} phia="den" canAssign={canAssign} busy={busy} exec={exec} />
            ))}
          </ul>
        </>
      )}
      {di.length === 0 && den.length === 0 && (
        <p className="thsx-note">Chưa có bàn giao nào.</p>
      )}
    </section>
  );
}

/** Nhãn một chặng sau: tên bước (đã kèm "lần k/N" nếu tách) · nơi làm. Bước thuê ngoài nói rõ
 *  nhà gia công — "giao ra ngoài" chung chung thì tổ không biết hàng đi đâu. */
function nhanChangSau(c: SxBanGiaoChangSau): string {
  const noi = c.loai_buoc === "thue_ngoai"
    ? `Gia công ngoài${c.nha_cung_cap ? ` · ${c.nha_cung_cap}` : ""}`
    : c.to_ten;
  return `${c.ten_cong_doan}${noi ? ` · ${noi}` : ""}`;
}

/** Số giao theo mẻ: tổng TỐT của mẻ đã tick, không vượt phần còn chưa giao (bàn giao tạo trước khi
 *  có giao-theo-mẻ không gắn mẻ nào, nên mẻ cũ vẫn hiện "chưa giao" dù số đã đi rồi). Không còn mẻ
 *  nào để chọn ⇒ giao nốt phần lẻ. Máy chủ tính lại đúng công thức này — ô số không còn trên form. */
function soTheoMe(me: SxBatch[], chon: Set<number>, conLai: number): number {
  if (me.length === 0) return conLai;
  return Math.min(me.filter((b) => chon.has(b.id)).reduce((t, b) => t + b.tot, 0), conLai);
}

/** Danh sách mẻ tick chọn — dùng chung cho đề xuất mới và sửa mẻ của đề xuất còn chờ xác nhận. */
function MeChon({
  me, chon, onDoi, tong, dv,
}: {
  me: SxBatch[]; chon: Set<number>; onDoi: (next: Set<number>) => void; tong: number; dv: string;
}) {
  function bat(id: number) {
    const next = new Set(chon);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onDoi(next);
  }
  return (
    <div className="thsx-x-fld">
      <span className="thsx-x-fld__l">
        Mẻ giao ({chon.size}/{me.length}) · <b className="thsx-num">{num(tong)}</b>{dv}
      </span>
      <div className="thsx-x-chon">
        {me.map((b) => (
          <label key={b.id} className={`thsx-x-chon__o${chon.has(b.id) ? " is-on" : ""}`}>
            <input type="checkbox" checked={chon.has(b.id)} onChange={() => bat(b.id)} />
            <span className="thsx-x-chon__ten thsx-num">{formatBatchTime(b.bat_dau, b.ket_thuc)}</span>
            <span className="thsx-x-chon__phu thsx-num"><b>{num(b.tot)}</b> tốt</span>
          </label>
        ))}
      </div>
    </div>
  );
}

/** Đề xuất bàn giao (§11.2, sửa 14/09/2026).
 *
 *  ĐÍCH không phải thứ để chọn: lệnh đã khai routing, backend trả đúng chặng sau. Chỉ khi bước sau
 *  tách lần chạy hoặc routing rẽ nhánh (nhiều chặng sau) tổ mới chọn một trong số đó. Bước cuối
 *  lệnh thì giao ra kho.
 *
 *  GIAO THEO MẺ: liệt kê các mẻ chưa giao, tick sẵn hết; số lượng = tổng tốt của mẻ đã tick, KHÔNG
 *  gõ tay. Đếm thực tế lệch thì bên nhận xác nhận rồi điều chỉnh (§11.3). */
function BanGiaoForm({
  chiTiet, conLai, busy, onXong, exec,
}: {
  chiTiet: SxWorkItemChiTiet; conLai: number;
  busy: boolean; onXong: () => void; exec: ThsxExec;
}) {
  const donVi = chiTiet.cong_viec.don_vi_ra ?? null;
  const dv = donVi ? ` ${nhanDonVi(donVi)}` : "";
  const changSau = chiTiet.ban_giao_chang_sau;
  const meChuaGiao = chiTiet.san_luong.batches.filter((b) => !b.da_ban_giao && b.tot > 0);
  const macDinh = changSau.find((c) => c.trang_thai !== "completed") ?? changSau[0];

  const [dich, setDich] = useState<number | null>(macDinh?.cong_viec_id ?? null);
  const [chon, setChon] = useState<Set<number>>(() => new Set(meChuaGiao.map((b) => b.id)));
  const tong = soTheoMe(meChuaGiao, chon, conLai);
  const hopLe = tong > 0
    && (meChuaGiao.length === 0 || chon.size > 0)
    && (changSau.length === 0 || dich != null);

  async function luu() {
    const body: SxBanGiaoDeXuatIn = {
      dich_cong_viec_id: changSau.length ? dich : null,
      don_vi: donVi,
      batch_ids: meChuaGiao.filter((b) => chon.has(b.id)).map((b) => b.id),
    };
    if (await exec.deXuatBanGiao(body)) onXong();
  }

  return (
    <ThsxModal
      title="Đề xuất bàn giao" icon="truck" busy={busy} onClose={onXong}
      badge={donVi ? nhanDonVi(donVi) : null}
      footer={<>
        <Button variant="ghost" onClick={onXong} disabled={busy}>Huỷ</Button>
        <Button variant="accent" onClick={luu} disabled={busy || !hopLe}>
          <Icon name="send" size={13} /> Đề xuất
        </Button>
      </>}
    >
      <div className="thsx-x-fld">
        <span className="thsx-x-fld__l">Giao cho chặng sau</span>
        {changSau.length === 0 ? (
          <div className="thsx-x-dich">
            <Icon name="packageCheck" size={14} />
            <span className="thsx-x-dich__ten">Kho — bước cuối của lệnh</span>
          </div>
        ) : changSau.length === 1 ? (
          <div className="thsx-x-dich">
            <Icon name="arrowRight" size={14} />
            <span className="thsx-x-dich__ten">{nhanChangSau(changSau[0])}</span>
            {changSau[0].du_kien_bat_dau && (
              <span className="thsx-x-dich__gio thsx-num">{ngayGio(changSau[0].du_kien_bat_dau)}</span>
            )}
          </div>
        ) : (
          <div className="thsx-x-chon" role="radiogroup" aria-label="Chặng sau">
            {changSau.map((c) => (
              <label key={c.cong_viec_id} className={`thsx-x-chon__o${dich === c.cong_viec_id ? " is-on" : ""}`}>
                <input type="radio" name="bg-dich" checked={dich === c.cong_viec_id}
                  onChange={() => setDich(c.cong_viec_id)} />
                <span className="thsx-x-chon__ten">{nhanChangSau(c)}</span>
                {c.trang_thai === "completed"
                  ? <span className="thsx-x-chon__phu">đã xong</span>
                  : c.du_kien_bat_dau && <span className="thsx-x-chon__phu thsx-num">{ngayGio(c.du_kien_bat_dau)}</span>}
              </label>
            ))}
          </div>
        )}
      </div>

      {meChuaGiao.length > 0 ? (
        <MeChon me={meChuaGiao} chon={chon} onDoi={setChon} tong={tong} dv={dv} />
      ) : conLai > 0 ? (
        <p className="thsx-x-hint">Mọi mẻ đã giao — giao nốt phần lẻ <b className="thsx-num">{num(conLai)}</b>{dv}.</p>
      ) : (
        <p className="thsx-x-hint">Không còn sản lượng tốt để giao.</p>
      )}
    </ThsxModal>
  );
}

function BanGiaoRow({
  g, phia, canAssign, busy, exec, batches = [], conLai = 0,
}: {
  g: SxBanGiao; phia: "di" | "den"; canAssign: boolean; busy: boolean;
  exec: ThsxExec;
  /** Chỉ dòng "Giao đi": mẻ của công đoạn nguồn + phần còn chưa giao — để sửa mẻ. */
  batches?: SxBatch[]; conLai?: number;
}) {
  const [suaOpen, setSuaOpen] = useState(false);
  const [dcOpen, setDcOpen] = useState(false);
  const st = BG_TT[g.trang_thai] ?? { txt: g.trang_thai, cls: "thsx-x-pill--wait" };
  const daXacNhan = g.trang_thai === "confirmed" || g.trang_thai === "adjusted";
  // Mẻ sửa được = mẻ chưa đi theo lần giao nào + mẻ của chính lần giao này.
  const meSua = batches.filter((b) => b.tot > 0 && (!b.da_ban_giao || g.batch_ids.includes(b.id)));
  // Nguồn (đi) sửa mẻ khi còn 'proposed'; đích (đến) xác nhận khi 'proposed'; điều chỉnh khi đã xác nhận.
  const canSua = canAssign && phia === "di" && g.trang_thai === "proposed" && meSua.length > 0;
  const canXac = canAssign && phia === "den" && g.trang_thai === "proposed";
  const canDc = canAssign && daXacNhan;

  return (
    <li className="thsx-x-bg">
      <div className="thsx-x-bg__main">
        <Icon name={phia === "di" ? "send" : "packageCheck"} size={13} className="thsx-x-bg__ic" />
        <span className="thsx-x-bg__to">{g.doi_tac_ten || (phia === "di" && g.doi_tac_cong_viec_id == null ? "Kho" : "")}{g.cung_to && <span className="thsx-x-tag-ht">cùng tổ</span>}</span>
        {g.batch_ids.length > 0 && <span className="thsx-x-bg__me thsx-num">{g.batch_ids.length} mẻ</span>}
        <span className="thsx-x-item__spacer" />
        <span className="thsx-x-bg__q thsx-num">{num(g.so_luong)}{g.don_vi ? ` ${nhanDonVi(g.don_vi)}` : ""}</span>
        <span className={`thsx-x-pill ${st.cls}`}>{st.txt}</span>
      </div>
      {g.khong_nhat_quan && (
        <p className="thsx-note thsx-note--warn"><Icon name="alert" size={12} /> Số nhận không khớp số giao.</p>
      )}
      {canAssign && (canSua || canXac || canDc) && (
        <div className="thsx-x-act thsx-x-act--row">
          {canXac && (
            <Button variant="accent" onClick={() => void exec.xacNhanBanGiao(g.id, g.version)} disabled={busy}>
              <Icon name="check" size={13} /> Xác nhận
            </Button>
          )}
          {canSua && (
            <Button variant="ghost" onClick={() => { setSuaOpen((o) => !o); setDcOpen(false); }} disabled={busy}>
              <Icon name="pencil" size={12} /> Sửa mẻ
            </Button>
          )}
          {canDc && (
            <Button variant="ghost" onClick={() => { setDcOpen((o) => !o); setSuaOpen(false); }} disabled={busy}>
              <Icon name="edit" size={12} /> Điều chỉnh
            </Button>
          )}
        </div>
      )}
      {suaOpen && (
        <SuaMeForm g={g} me={meSua} conLai={conLai} busy={busy}
          onXong={() => setSuaOpen(false)} exec={exec} />
      )}
      {dcOpen && (
        <DieuChinhForm g={g} busy={busy}
          onHuy={() => setDcOpen(false)} onXong={() => setDcOpen(false)} exec={exec} />
      )}
    </li>
  );
}

/** Sửa MẺ của lần giao còn chờ xác nhận — tick nhầm thì gỡ, sót thì thêm; số tính lại theo mẻ. */
function SuaMeForm({
  g, me, conLai, busy, onXong, exec,
}: {
  g: SxBanGiao; me: SxBatch[]; conLai: number; busy: boolean;
  onXong: () => void; exec: ThsxExec;
}) {
  const [chon, setChon] = useState<Set<number>>(() => new Set(g.batch_ids));
  // Phần còn lại tính cả số của chính lần giao này (nó sắp được thay bằng số mới).
  const tong = soTheoMe(me, chon, conLai + g.so_luong);
  const doi = chon.size !== g.batch_ids.length || g.batch_ids.some((id) => !chon.has(id));
  const dv = g.don_vi ? ` ${nhanDonVi(g.don_vi)}` : "";

  async function luu() {
    const body: SxBanGiaoSuaIn = {
      batch_ids: me.filter((b) => chon.has(b.id)).map((b) => b.id), expected_version: g.version,
    };
    if (await exec.suaBanGiao(g.id, body)) onXong();
  }

  return (
    <div className="thsx-x-form thsx-x-form--sub">
      <MeChon me={me} chon={chon} onDoi={setChon} tong={tong} dv={dv} />
      <div className="thsx-x-act">
        <Button variant="ghost" onClick={onXong} disabled={busy}>Huỷ</Button>
        <Button variant="accent" onClick={luu} disabled={busy || !doi || chon.size === 0 || tong <= 0}>
          <Icon name="check" size={13} /> Lưu
        </Button>
      </div>
    </div>
  );
}

function DieuChinhForm({
  g, busy, onHuy, onXong, exec,
}: {
  g: SxBanGiao; busy: boolean;
  onHuy: () => void; onXong: () => void; exec: ThsxExec;
}) {
  const [slSau, setSlSau] = useState(String(g.so_luong));
  const [moTa, setMoTa] = useState("");
  const nSl = toNum(slSau);
  const hopLe = nSl > 0;

  async function luu() {
    const body: SxBanGiaoDieuChinhIn = {
      so_luong_sau: nSl, mo_ta: moTa.trim() || null, expected_version: g.version,
    };
    if (await exec.dieuChinhBanGiao(g.id, body)) onXong();
  }

  return (
    <div className="thsx-x-form thsx-x-form--sub">
      <Field label={`Số lượng sau${g.don_vi ? ` (${nhanDonVi(g.don_vi)})` : ""}`}>
        <input type="number" min={0} className="thsx-x-in" value={slSau} onChange={(e) => setSlSau(e.target.value)} inputMode="numeric" />
      </Field>
      <Field label="Mô tả">
        <input type="text" className="thsx-x-in" value={moTa} onChange={(e) => setMoTa(e.target.value)}
          placeholder="Điều chỉnh vì sao? (tuỳ chọn)" />
      </Field>
      <div className="thsx-x-act">
        <Button variant="ghost" onClick={onHuy} disabled={busy}>Huỷ</Button>
        <Button variant="accent" onClick={luu} disabled={busy || !hopLe}>
          <Icon name="check" size={13} /> Điều chỉnh
        </Button>
      </div>
    </div>
  );
}

// ────────────── VẬT TƯ: đề nghị cấp theo công đoạn + phiếu nhận về tổ ──────────────
// Khối này LUÔN hiện, kể cả chưa có phiếu nào: bản cũ `if (vt.length === 0) return null;` khiến tổ
// trưởng không có cửa nào để bắt đầu xin vật tư (spec §7).
//
// Hai luồng dữ liệu KHÁC NHAU cùng nằm một section:
//   · `chiTiet.vat_tu_cap` — các LẦN tổ ĐỀ NGHỊ + bản đối chiếu kế hoạch/yêu cầu/thực xuất.
//   · `chiTiet.vat_tu`     — phiếu kho ĐÃ ghi sổ, chờ tổ xác nhận NHẬN (giữ nguyên như cũ).
//
// Vật tư KHÔNG BAO GIỜ chặn bắt đầu/kết thúc công đoạn (spec §8) — không có gì ở đây gài vào
// `disabled` của hai nút đó.
type VtFormMode = "moi" | "sua" | "bo_sung";

/** Đúng MỘT nút CTA hiện ở header. Thứ tự kiểm là CỐ ĐỊNH: `de_nghi_co_the_sua_id` trước, rồi
 *  "chưa từng đề nghị", cuối cùng mới tới bổ sung — `co_the_tao_bo_sung` có thể `true` ngay cả khi
 *  chưa có lần nào, đảo thứ tự là mời tổ trưởng "bổ sung" cho công đoạn chưa xin gì. */
function ctaMode(vt: SxVatTuCap): VtFormMode | null {
  if (vt.de_nghi_co_the_sua_id != null) return "sua";
  if (vt.cac_de_nghi.length === 0) return "moi";
  if (vt.co_the_tao_bo_sung) return "bo_sung";
  return null;
}

const VT_CTA: Record<VtFormMode, { txt: string; icon: "send" | "pencil" | "plus" }> = {
  moi: { txt: "Yêu cầu cấp vật tư", icon: "send" },
  sua: { txt: "Sửa đề nghị", icon: "pencil" },
  bo_sung: { txt: "Yêu cầu bổ sung", icon: "plus" },
};

function VatTuSection({
  chiTiet, canAssign, busy, exec, tenNguoi,
}: {
  chiTiet: SxWorkItemChiTiet; canAssign: boolean; busy: boolean; exec: ThsxExec;
  tenNguoi: Map<number, string>;
}) {
  const { token } = useAuth();
  const [formMode, setFormMode] = useState<VtFormMode | null>(null);
  const [phieuMo, setPhieuMo] = useState<number | null>(null);
  const vt = chiTiet.vat_tu;
  const cap = chiTiet.vat_tu_cap;
  const cta = ctaMode(cap);
  const cvId = chiTiet.cong_viec.id;
  const lanSua = cap.cac_de_nghi.find((d) => d.id === cap.de_nghi_co_the_sua_id) ?? null;

  // Drawer KHÔNG remount khi bấm sang việc khác (`ThsxDrawer` render không có `key`, `loadChiTiet`
  // không đặt `chiTiet = null` giữa chừng) nên khối này sống xuyên suốt: form đang mở dở của việc A
  // vẫn còn nguyên khi màn đã là việc B ⇒ bấm Gửi là B nhận vật tư của A. Đóng form khi đổi việc.
  useEffect(() => { setFormMode(null); setPhieuMo(null); }, [cvId]);

  const tongMatHang = cap.doi_chieu.length;
  const daXinCount = cap.doi_chieu.filter((d) => d.sl_yeu_cau > VT_EPS).length;
  const coKcsDaXuat = chiTiet.vat_tu.some((v) => v.da_nhan);
  const trangThaiKho = chiTiet.vat_tu.length === 0 ? "Chưa xuất" : coKcsDaXuat ? "Đã xuất kho" : "Chờ nhận";

  return (
    <section className="thsx-psec thsx-x">
      <div className="thsx-psec__h">
        <span className="thsx-psec__title"><Icon name="warehouse" size={13} /> Vật tư</span>
        {canAssign && cta != null && (
          <Button variant="accent" onClick={() => setFormMode(cta)} disabled={busy} aria-haspopup="dialog">
            <Icon name={VT_CTA[cta].icon} size={13} /> {VT_CTA[cta].txt}
          </Button>
        )}
      </div>

      {tongMatHang > 0 && (
        <div className="thsx-vattu-kpi-strip">
          <div className="thsx-vattu-kpi-tile">
            <span className="thsx-metric-lbl">Tổng mặt hàng</span>
            <span className="thsx-metric-val thsx-num">{tongMatHang} <span className="thsx-metric-unit">món</span></span>
          </div>
          <div className="thsx-vattu-kpi-tile">
            <span className="thsx-metric-lbl">Tiến độ yêu cầu</span>
            <span className={`thsx-metric-val thsx-num ${daXinCount === tongMatHang ? "thsx-metric-val--done" : "thsx-metric-val--thieu"}`}>
              {daXinCount} / {tongMatHang} <span className="thsx-metric-unit">đã xin</span>
            </span>
          </div>
          <div className="thsx-vattu-kpi-tile">
            <span className="thsx-metric-lbl">Trạng thái kho</span>
            <span className="thsx-metric-val">{trangThaiKho}</span>
          </div>
        </div>
      )}

      {cap.du_lieu_cu && (
        <div className="thsx-vattu-alert-banner" role="status">
          <Icon name="alert" size={14} />
          <span>
            <b>Dữ liệu lịch sử (trước 31/08/2026):</b> Công đoạn chưa từng gửi đề nghị nên phiếu đang lấy theo lệnh sản xuất cũ.
          </span>
        </div>
      )}

      {cap.doi_chieu.length === 0 ? (
        <p className="thsx-note">
          Công đoạn này không có nhu cầu vật tư theo kế hoạch. Vẫn gửi đề nghị được nếu tổ cần xin thêm.
        </p>
      ) : (
        <table className="thsx-vattu-matrix-tbl thsx-x-tbl">
          <thead>
            <tr>
              <th>Vật tư</th>
              <th className="r">Kế hoạch</th>
              <th className="r">Đã yêu cầu</th>
              <th className="r">Kho thực xuất</th>
              <th className="r">Chênh lệch</th>
              <th>Lý do</th>
            </tr>
          </thead>
          <tbody>
            {cap.doi_chieu.map((d) => {
              // Dung sai làm tròn cộng dồn theo số LẦN đề nghị có món này — xem `vtCoLechThucTe`.
              const soLan = vtSoLanCoMon(cap.cac_de_nghi, d);
              return (
              // Tô nền hàng kho xuất KHÁC số đã xin: đó là chỗ tổ trưởng KHÔNG chủ động được,
              // đáng chú ý hơn lệch kế-hoạch↔yêu-cầu (vốn là quyết định của chính tổ).
              <tr key={`${d.hang_loai}:${d.hang_id}`}
                className={vtCoLechThucTe(d, soLan) ? "is-lech" : undefined}>
                <td className="thsx-vattu-name-cell"><b>{d.ten}</b></td>
                <td className="r thsx-num">{num(d.sl_ke_hoach)}<span className="thsx-x-unit"> {nhanDonVi(d.dvt)}</span></td>
                <td className="r thsx-num">{num(d.sl_yeu_cau)}<span className="thsx-x-unit"> {nhanDonVi(d.dvt)}</span></td>
                {/* `sl_thuc_xuat` đọc thẳng từ dòng chứng từ nên LUÔN ở thang GỐC (board.py:
                    `_vat_tu_cap`) — dán nhãn `dvt` (thang tổ khai) vào đây là in sai đơn vị. */}
                <td className="r thsx-num">{num(d.sl_thuc_xuat)}<span className="thsx-x-unit"> {nhanDonVi(d.dvt_goc)}</span></td>
                <td className="r"><VtDeltaCell d={d} soLan={soLan} /></td>
                <td><VtLyDoCacLanCell ds={d.cac_ly_do} /></td>
              </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {formMode != null && (
        <VatTuDeNghiForm
          // `cvId` nằm trong key để dựng lại state form khi đổi việc — hai việc cùng chưa có đề
          // nghị thì `"moi-0"` giống hệt nhau, một mình `setFormMode(null)` ở trên vẫn hở nếu về
          // sau có đường nào mở form mà không đi qua nút CTA.
          key={`${cvId}-${formMode}-${lanSua?.id ?? 0}`}
          cv={chiTiet.cong_viec} cap={cap} mode={formMode} lanSua={lanSua} busy={busy}
          onHuy={() => setFormMode(null)} onXong={() => setFormMode(null)} exec={exec} />
      )}

      <div className="thsx-x-sub">Lịch sử đề nghị</div>
      {cap.cac_de_nghi.length === 0 ? (
        <div className="thsx-vattu-history-empty">
          <Icon name="history" size={14} />
          <span>Chưa có lịch sử đề nghị vật tư nào cho công đoạn này.</span>
        </div>
      ) : (
        <ul className="thsx-x-list">
          {/* Mới nhất lên đầu (BE trả theo `lan_so` tăng dần) — khớp quy ước màn Kho. */}
          {[...cap.cac_de_nghi].reverse().map((d) => (
            <VtDeNghiLanRow key={d.id} d={d} tenNguoi={tenNguoi} />
          ))}
        </ul>
      )}

      {vt.length > 0 && (
        <>
          <div className="thsx-x-sub">Phiếu kho đã xuất</div>
          <ul className="thsx-x-list">
            {vt.map((v) => (
              <li key={v.voucher_id} className="thsx-x-vt">
                <button type="button" className="thsx-x-vt__open" aria-haspopup="dialog"
                  title="Xem phiếu xuất kho" onClick={() => setPhieuMo(v.voucher_id)}>
                  <Icon name={v.da_nhan ? "packageCheck" : "box"} size={13}
                    className={v.da_nhan ? "thsx-x-vt__ic is-ok" : "thsx-x-vt__ic"} />
                  <span className="thsx-x-vt__ma">{v.ma}</span>
                </button>
                {v.da_nhan ? (
                  <span className="thsx-x-vt__at thsx-num">{v.xac_nhan_luc ? ngayGio(v.xac_nhan_luc) : "đã nhận"}</span>
                ) : canAssign ? (
                  <Button variant="secondary" onClick={() => void exec.xacNhanVatTu(v.voucher_id)} disabled={busy}>
                    <Icon name="packageCheck" size={13} /> Xác nhận nhận
                  </Button>
                ) : (
                  <span className="thsx-x-pill thsx-x-pill--wait">chờ nhận</span>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      {phieuMo != null && <PhieuKhoNoi voucherId={phieuMo} token={token ?? ""} onClose={() => setPhieuMo(null)} />}
    </section>
  );
}

/** Phiếu kho mở từ ngăn SX — CÙNG drawer phiếu của màn Kho, chỉ đọc (thao tác trên phiếu làm ở màn
 *  Kho). Hai việc phải lo vì drawer này nằm TRONG ngăn `.thsx-panel`:
 *  - Ngăn có `transform` nên `position: fixed` bên trong bị nhốt theo khung ngăn ⇒ đẩy ra `body`,
 *    lớp bọc đặt z-index trên ngăn (61).
 *  - Esc ở trang đóng cả ngăn ⇒ dời focus vào lớp này, tự bắt Esc rồi `preventDefault` để trang nhường.
 *  `canViewCost` để true như màn Đề nghị của Kho: backend tự ẩn giá với người không được xem. */
function PhieuKhoNoi({ voucherId, token, onClose }: { voucherId: number; token: string; onClose: () => void }) {
  const lopRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const truoc = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    lopRef.current?.focus({ preventScroll: true });
    return () => { if (truoc?.isConnected) truoc.focus({ preventScroll: true }); };
  }, []);
  return createPortal(
    <div ref={lopRef} className="thsx-phieu-kho-lop" tabIndex={-1}
      onKeyDown={(e) => { if (e.key !== "Escape" || e.defaultPrevented) return; e.preventDefault(); onClose(); }}>
      <VoucherDrawer token={token} voucherId={voucherId} canCreate={false} canPost={false}
        canViewCost onClose={onClose} onChanged={() => {}} />
    </div>,
    document.body,
  );
}

/** Ô "Chênh lệch": Đã được trực quan hoá thành các Pill Badge tiếng Việt thân thiện, dễ nhận biết ngay. */
function VtDeltaCell({ d, soLan }: { d: SxVatTuCapDoiChieu; soLan: number }) {
  const soKh = d.sl_yeu_cau - d.sl_ke_hoach;
  const soYc = d.lech_thuc_te;
  const lechYc = vtCoLechThucTe(d, soLan);

  // 1. Tổ chưa xin cấp (đã yêu cầu = 0 & kế hoạch > 0)
  if (d.sl_yeu_cau <= VT_EPS && d.sl_ke_hoach > VT_EPS) {
    return <span className="thsx-vattu-badge thsx-vattu-badge--wait">⚠️ Chưa xin cấp</span>;
  }

  // 2. Cả 2 đều khớp 100%
  if (Math.abs(soKh) <= VT_EPS && !lechYc) {
    return <span className="thsx-vattu-badge thsx-vattu-badge--ok">✓ Đủ & Khớp</span>;
  }

  return (
    <div className="thsx-vattu-delta-col">
      {/* So với Kế Hoạch */}
      {Math.abs(soKh) > VT_EPS && (
        <span className={`thsx-vattu-badge ${soKh > 0 ? "thsx-vattu-badge--up" : "thsx-vattu-badge--down"}`}>
          {soKh > 0 ? `+${num(soKh)}` : `−${num(Math.abs(soKh))}`} {nhanDonVi(d.dvt)} {soKh > 0 ? "(Vượt KH)" : "(Thiếu)"}
        </span>
      )}
      {/* So với Kho (Thực xuất ↔ Yêu cầu) */}
      {lechYc && (
        <span className={`thsx-vattu-badge ${soYc > 0 ? "thsx-vattu-badge--up" : "thsx-vattu-badge--down"}`}>
          Kho {soYc > 0 ? `xuất dư +${num(soYc)}` : `thiếu −${num(Math.abs(soYc))}`} {nhanDonVi(d.dvt_goc)}
        </span>
      )}
    </div>
  );
}

function VtLyDoCacLanCell({ ds }: { ds: { lan_so: number; ly_do: string }[] }) {
  if (ds.length === 0) return <span className="thsx-x-unit">—</span>;
  return (
    <div className="thsx-x-vt-delta thsx-x-vt-delta--left">
      {ds.map((d, i) => (
        <span key={i} className="thsx-x-butru__mo">Lần {d.lan_so}: {d.ly_do}</span>
      ))}
    </div>
  );
}

function VtDeNghiLanRow({ d, tenNguoi }: { d: SxVatTuCapLan; tenNguoi: Map<number, string> }) {
  const [mo, setMo] = useState(false);
  const st = d.stock_request_trang_thai ? VT_TT[d.stock_request_trang_thai] : null;
  const ten = (id: number | null) => (id == null ? "—" : tenNguoi.get(id) ?? `NV #${id}`);
  return (
    <li className="thsx-x-item">
      <button type="button" className="thsx-x-item__h" onClick={() => setMo((o) => !o)} aria-expanded={mo}>
        <Icon name="chevron" size={12} className={mo ? "" : "thsx-rot-90"} />
        <span className="thsx-x-item__q">Lần {d.lan_so}</span>
        {d.loai === "bo_sung" && <span className="thsx-x-tag-ht">bổ sung</span>}
        <span className="thsx-x-item__spacer" />
        <span className="thsx-x-item__time thsx-num">{ngayGio(d.can_luc)}</span>
        {d.stock_request_ma ? (
          <span className={`thsx-x-pill ${st?.cls ?? "thsx-x-pill--wait"}`}>
            {st?.txt ?? d.stock_request_trang_thai}
          </span>
        ) : (
          <span className="thsx-x-pill thsx-x-pill--off">không cần cấp</span>
        )}
      </button>
      {mo && (
        <div className="thsx-x-item__body">
          <div className="thsx-x-kv"><span>Mã yêu cầu kho</span><span>{d.stock_request_ma ?? "—"}</span></div>
          <div className="thsx-x-kv"><span>Người tạo</span>
            <span>{ten(d.created_by_id)} · {ngayGio(d.created_at)}</span></div>
          {d.updated_by_id != null && d.updated_by_id !== d.created_by_id && (
            <div className="thsx-x-kv"><span>Người sửa cuối</span>
              <span>{ten(d.updated_by_id)} · {ngayGio(d.updated_at)}</span></div>
          )}
          {d.dongs.length > 0 && (
            <table className="thsx-x-tbl" style={{ marginTop: 8 }}>
              <thead><tr><th>Vật tư</th><th className="r">Xin cấp</th><th>Lý do</th></tr></thead>
              <tbody>
                {d.dongs.map((x) => (
                  <tr key={`${x.hang_loai}:${x.hang_id}`}>
                    <td>{x.ten}</td>
                    <td className="r thsx-num">{num(x.sl_yeu_cau)}<span className="thsx-x-unit"> {nhanDonVi(x.dvt)}</span></td>
                    <td><span className="thsx-x-butru__mo">{x.ly_do_chenh_lech || "—"}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </li>
  );
}

// ---- Form đề nghị (dùng chung cho 3 mode) ---------------------------------------------------
interface VtDongForm {
  key: string;
  hang_loai: string;
  hang_id: number;          // 0 = dòng vừa thêm, chưa chọn mặt hàng
  ten: string;
  dvt: string;
  /** Đơn vị của dòng KẾ HOẠCH cùng mặt hàng — để biết tổ có đang khai bằng đơn vị khác không. */
  dvtKeHoach: string;
  sl_ke_hoach: number;
  sl_yeu_cau: number;
  /** Chuỗi THÔ đang gõ trong ô số. Giữ riêng vì `<input type="number">` điều khiển bằng SỐ sẽ nuốt
   *  dấu chấm đang gõ dở ("0." → trình duyệt trả "" → về 0), tức là không gõ nổi số lẻ — mà vật tư
   *  cân theo kg thì số lẻ là chuyện thường. */
  slText: string;
  ly_do_chenh_lech: string;
  /** Dòng đến TỪ kế hoạch: lần đầu phải lưu đủ kể cả khi = 0, nên không cho xoá (dùng "Về 0"). */
  tuKeHoach: boolean;
}

/** Hiện/bắt buộc ô Lý do — CHỈ để ra mắt sớm ô nhập, KHÔNG bao giờ dùng làm `disabled` nút gửi.
 *  Quy đổi đơn vị thật nằm ở BE (spec §3: BE không tin số client), nên so bằng số thô ở đây sai
 *  một chút cũng không sao: người dùng vẫn gõ tay được, còn thiếu lý do thật thì BE trả 400 kèm
 *  câu tiếng Việt cụ thể. */
function vtCanLyDo(d: VtDongForm, loai: "lan_dau" | "bo_sung"): { hien: boolean; batBuoc: boolean } {
  if (loai === "bo_sung") {
    const batBuoc = d.sl_yeu_cau > VT_EPS;
    return { hien: batBuoc, batBuoc };
  }
  // Đơn vị HIỆU LỰC — phải gộp ĐÚNG như BE gộp (`vat_tu_de_nghi.py:_chuan_hoa`:
  // `dvt = ln.dvt or k_row.dvt or ""`). Từ vòng vá gốc, `vtDongKhoiTao` mode `sua` đã tự gộp
  // `d.dvt` với đơn vị kế hoạch ngay lúc dựng dòng, nên tới đây `d.dvt` thường ĐÃ mang đơn vị
  // hiệu lực và dòng dưới thành lớp THỪA cho ca đó. GIỮ NGUYÊN, đừng xoá vì tưởng dead code —
  // đây là lớp phòng thủ CÓ CHỦ ĐÍCH, khoá hợp đồng "FE xét đúng thứ BE xét" bất kể dòng được
  // dựng bằng đường nào (kể cả đường dựng khác sau này không đi qua `vtDongKhoiTao`).
  const dvtHieuLuc = d.dvt || d.dvtKeHoach;
  // Món kế hoạch mà KẾ HOẠCH cũng không có đơn vị, và tổ để 0: không có mốc nào để nói lệch ⇒ BE
  // miễn luật lý do cho đúng ca này ⇒ đừng gắn dấu `*` đòi bắt buộc. Vẫn MỞ ô để ai muốn ghi chú
  // thì ghi — chữ đó nay đi được tới BE (xem `vtPayloadLines`).
  // BE tự TÍNH LẠI vị ngữ này (biến `khong_doi_chieu`), nó KHÔNG đọc cờ `CB_KHONG_DOI_CHIEU` —
  // cờ đó chỉ sống trong bảng cân đối (`ke_hoach_vat_tu_service.py:1139`, đọc lại ở `:1210`). Sửa
  // cờ mà tưởng đang sửa luật lý do là sửa nhầm file.
  if (d.tuKeHoach && !dvtHieuLuc && d.sl_yeu_cau <= VT_EPS) return { hien: true, batBuoc: false };
  if (!d.tuKeHoach) {
    const co = d.sl_yeu_cau > VT_EPS;
    return { hien: co, batBuoc: co };
  }
  // Đổi đơn vị thật (tổ khai bằng đơn vị khác kế hoạch) — FE không quy đổi được nên KHÔNG đoán,
  // để BE phán. Dùng đơn vị HIỆU LỰC: `dvt` rỗng không phải "đổi đơn vị", nó chỉ là "dòng đã lưu
  // chưa mang đơn vị" — BE khi đó so thẳng theo đơn vị kế hoạch, và FE phải so y hệt.
  if (dvtHieuLuc !== d.dvtKeHoach) return { hien: true, batBuoc: false };
  const lech = Math.abs(d.sl_yeu_cau - d.sl_ke_hoach) > VT_EPS;
  return { hien: lech, batBuoc: lech };
}

/** Dòng đã chọn được mặt hàng nhưng Ô ĐƠN VỊ CỦA CHÍNH DÒNG ĐÓ đang trống. BE không nhận nổi một
 *  dòng như vậy khi tổ xin số dương (nó không biết quy ra đơn vị kho), và im lặng vứt ở FE thì tổ
 *  trưởng thấy toast xanh "Đã gửi" trong khi kho không bao giờ thấy món đó.
 *
 *  CỐ Ý chỉ xét `d.dvt`, KHÔNG gộp `d.dvtKeHoach` như `vtCanLyDo` — hai hàm trả lời hai câu hỏi
 *  khác nhau. `vtCanLyDo` hỏi "BE có đòi lý do không" nên phải gộp y hệt BE gộp. Hàm này hỏi "ô
 *  đơn vị trên màn có chữ gì không" — và màn đang hiện đúng `{d.dvt ? nhanDonVi(d.dvt) : "—"}`. Gộp vào đây là cho
 *  tổ gõ một số dương vào ô đơn vị hiện "—" rồi để BE âm thầm đọc nó theo đơn vị KẾ HOẠCH: đổi
 *  một lần chặn thừa lấy một lần lệch thang im lặng, tệ hơn. Lần chặn thừa cũng không phải ngõ
 *  cụt — câu của `vtCanTro` chỉ ngay đường thoát ("đưa dòng đó về 0 rồi gửi phần còn lại").
 *
 *  Từ vòng vá gốc, ca "dòng đã lưu `dvt=""`, kế hoạch nay có đơn vị" không còn rơi vào hàm này
 *  nữa: `vtDongKhoiTao` mode `sua` đã gộp đơn vị kế hoạch vào `d.dvt` ngay lúc dựng dòng, nên
 *  `d.dvt` ở đây tự nhiên có chữ và hàm trả `false` — KHÔNG cần sửa thân hàm. Hàm chỉ còn trả
 *  `true` cho ca thật sự không có mốc nào để gộp (dòng ngoài kế hoạch hiện tại, hoặc chính kế
 *  hoạch cũng chưa có đơn vị). */
function vtThieuDonVi(d: VtDongForm): boolean {
  return d.hang_id > 0 && !d.dvt;
}

/** Câu giải thích vì sao nút Gửi đang tắt — `null` nghĩa là gửi được. KHÔNG bao giờ để nút disabled
 *  câm: người dùng không đoán được mình thiếu gì. */
function vtCanTro(
  dongs: VtDongForm[], lines: SxVatTuDeNghiDongIn[],
  mode: VtFormMode, loai: "lan_dau" | "bo_sung",
): string | null {
  // CHỈ chặn khi tổ đang THẬT SỰ xin món đó. Dòng kế hoạch cũng có thể trống đơn vị — chặn cả khi
  // nó đang để 0 là để một món hỏng khoá chết cả công đoạn, mà dòng kế hoạch lại không xoá được nên
  // tổ trưởng hết đường. Đường thoát thật: đưa món đó về 0, gửi phần còn lại.
  // Cùng cách nói với băng cảnh báo trên thẻ dòng và với câu lỗi BE (`vat_tu_de_nghi.py`): KHÔNG
  // đóng đinh nguyên nhân vào "danh mục chưa khai" — ô đơn vị còn trống được vì snapshot của bước,
  // vì routing của dòng giấy, chứ không riêng danh mục.
  if (dongs.some((d) => vtThieuDonVi(d) && d.sl_yeu_cau > VT_EPS)) {
    return "Còn mặt hàng chưa có đơn vị tính nên chưa xin được — đưa dòng đó về 0 rồi gửi phần còn "
      + "lại, hoặc nhờ kỹ thuật kiểm lại đơn vị rồi xin lại.";
  }
  // Gõ số rồi quên chọn mặt hàng: cũng là một dòng sẽ bị loại trước khi rời trình duyệt.
  if (dongs.some((d) => d.hang_id <= 0 && d.sl_yeu_cau > VT_EPS)) {
    return "Còn dòng đã điền số nhưng chưa chọn mặt hàng.";
  }
  // Trùng mặt hàng: dùng ĐÚNG câu BE trả, để hai bên không nói hai kiểu về cùng một lỗi.
  const dem = new Map<string, number>();
  for (const d of dongs) {
    if (d.hang_id <= 0) continue;
    const k = `${d.hang_loai}:${d.hang_id}`;
    dem.set(k, (dem.get(k) ?? 0) + 1);
  }
  if ([...dem.values()].some((n) => n > 1)) {
    return "Một mặt hàng chỉ được khai một dòng — gộp số lượng lại.";
  }
  // Sửa được phép đưa HẾT về 0 (đó là đường tự huỷ yêu cầu, spec §5.3) nên không đòi số dương.
  // Tạo mới thì phải có cái gì đó để gửi: một lần đề nghị RỖNG vẫn thành `de_nghi_co_the_sua_id`
  // và khoá luôn đường "Yêu cầu bổ sung" cho tới khi sửa.
  if (mode !== "sua" && lines.length === 0) {
    return loai === "bo_sung"
      ? "Đề nghị bổ sung phải có ít nhất một mặt hàng với số lớn hơn 0."
      : "Chưa có dòng nào để gửi — thêm mặt hàng và điền số trước khi gửi.";
  }
  return null;
}

export function vtPayloadLines(dongs: VtDongForm[], loai: "lan_dau" | "bo_sung"): SxVatTuDeNghiDongIn[] {
  // Dòng KẾ HOẠCH giữ lại kể cả khi `dvt` rỗng (danh mục, snapshot của bước, hay routing của dòng
  // giấy — nguyên nhân nào cũng vậy): BE nhận được
  // `dvt=""` với số 0 và miễn luật lý do cho đúng ca đó. Lọc thẳng `!!d.dvt` như trước là vứt HẲN
  // dòng — kéo theo cả chữ người dùng vừa gõ vào ô Lý do (mà giao diện lại đang gắn dấu `*` đòi
  // bắt buộc), và bản đối chiếu thì ghi thiếu thứ họ khai.
  // Dòng NGOÀI kế hoạch vẫn phải có đơn vị, và chính bộ lọc NÀY vứt nó ở MỌI số lượng: nó có
  // `tuKeHoach === false` nên vế `(!!d.dvt || d.tuKeHoach)` rút về đúng `!!d.dvt` — nó không bao
  // giờ đi tới bộ lọc thứ hai. Bộ lọc thứ hai chỉ lo chuyện số 0. Thêm một lớp nữa: `vtCanTro`
  // tắt nút Gửi khi dòng như vậy đang xin số dương. Không có ngách nào lọt xuống BE.
  // KHÔNG gộp `d.dvtKeHoach` vào đây như `vtCanLyDo`: câu hỏi ở đây khác ("dòng này có được gửi
  // xuống BE không", không phải "có phải ghi lý do không"), và gộp cũng là no-op — dòng kế hoạch
  // đã được `d.tuKeHoach` giữ rồi, còn dòng ngoài kế hoạch thì `dvtKeHoach` luôn BẰNG `dvt`
  // (`themDong` và `MaterialCombobox.onPick` đặt cả hai cùng lúc; `vtDongKhoiTao` mode `sua` rơi
  // về `?? d.dvt` khi mặt hàng không có trong kế hoạch).
  const giu = dongs.filter((d) => d.hang_id > 0 && (!!d.dvt || d.tuKeHoach))
    // lần đầu: giữ MỌI dòng gốc kế hoạch kể cả 0 ("kế hoạch có, tổ không lấy"); dòng ngoài kế
    // hoạch mà = 0 thì bỏ. Bổ sung: chỉ dòng dương.
    .filter((d) => (loai === "lan_dau" ? d.tuKeHoach || d.sl_yeu_cau > VT_EPS : d.sl_yeu_cau > VT_EPS));
  return giu.map((d) => ({
    hang_loai: d.hang_loai, hang_id: d.hang_id, dvt: d.dvt,
    sl_yeu_cau: d.sl_yeu_cau,
    // Ô Lý do ĐÓNG lại thì chữ cũ trong state phải thôi đi theo. Kéo một dòng đang lệch về đúng
    // kế hoạch (hoặc về 0 rồi xin lại đủ) làm ô biến mất, nhưng `d.ly_do_chenh_lech` vẫn giữ câu
    // gõ lần trước — gửi lên thì bảng đối chiếu ghi "554/554, không lệch" mà vẫn kèm lý do giải
    // thích một chỗ lệch KHÔNG CÒN TỒN TẠI (thấy khi nghiệm thu Task 10: hủy về 0 kèm lý do rồi
    // xin lại đủ 554, dòng vẫn đeo "tổ chưa cần cấp giấy"). Dùng ĐÚNG vị ngữ mà ô dùng để hiện.
    ly_do_chenh_lech: vtCanLyDo(d, loai).hien ? d.ly_do_chenh_lech.trim() || null : null,
  }));
}

/** Đơn vị mà lần đề nghị GẦN NHẤT đã dùng cho ĐÚNG mặt hàng này — `null` khi chưa lần nào xin nó.
 *
 *  Dùng làm đơn vị mặc định lúc tổ chọn mặt hàng ở form bổ sung. Trước đây dòng mới luôn nhận
 *  `don_vi_goc`, mà bảng đối chiếu lại gộp theo `(hang_loai, hang_id)` KHÔNG kèm đơn vị: một mặt
 *  hàng ôm hai `dvt` khác nhau thì `board.py` buộc phải hạ CẢ HÀNG về thang gốc (đúng — cộng 554
 *  tờ với 12 kg rồi in ra mới là nói dối). Hậu quả: tổ gõ lần 1 "554 tờ", xin bổ sung chút giấy
 *  mà form chỉ cho gõ kg, thế là cả dòng lật từ "554 to" sang "166,967 kg" rồi "178,967 kg" — tổ
 *  trưởng vốn nghĩ bằng tờ mở lại thấy đề nghị của chính mình ghi bằng kg. Bám theo đơn vị lần
 *  trước thì hàng vẫn một thang và không có gì phải lật.
 *
 *  Nhiều lần trước dùng nhiều đơn vị khác nhau ⇒ lấy của lần `lan_so` LỚN NHẤT (thói quen mới
 *  nhất của tổ). Dòng lưu với `dvt` rỗng KHÔNG tính là một câu trả lời — nó chỉ nghĩa là lúc đó
 *  routing/danh mục chưa nói được đơn vị, chép lại là chép cái trống. */
export function vtDvtLanTruoc(
  cacDeNghi: { lan_so: number; dongs: { hang_loai: string; hang_id: number; dvt: string }[] }[],
  hangLoai: string, hangId: number,
): string | null {
  let tot: { lanSo: number; dvt: string } | null = null;
  for (const lan of cacDeNghi) {
    for (const d of lan.dongs) {
      if (d.hang_loai !== hangLoai || d.hang_id !== hangId || !d.dvt) continue;
      if (tot == null || lan.lan_so > tot.lanSo) tot = { lanSo: lan.lan_so, dvt: d.dvt };
    }
  }
  return tot?.dvt ?? null;
}

function vtDongKhoiTao(cap: SxVatTuCap, mode: VtFormMode, lanSua: SxVatTuCapLan | null): VtDongForm[] {
  const kh = new Map(cap.ke_hoach.map((k) => [`${k.hang_loai}:${k.hang_id}`, k]));
  // Bổ sung: RỖNG — chỉ thêm đúng mặt hàng đang thiếu; liệt kê lại cả kế hoạch rồi bắt gõ lý do
  // cho từng dòng 0 là phiền vô ích (chỉ lần ĐẦU mới cần lưu đủ kế hoạch).
  if (mode === "bo_sung") return [];
  if (mode === "moi") {
    return cap.ke_hoach.map((k) => ({
      key: `${k.hang_loai}:${k.hang_id}`,
      hang_loai: k.hang_loai, hang_id: k.hang_id, ten: k.ten,
      dvt: k.dvt, dvtKeHoach: k.dvt,
      sl_ke_hoach: k.sl, sl_yeu_cau: k.sl, slText: String(k.sl),
      ly_do_chenh_lech: "", tuKeHoach: true,
    }));
  }
  // Sửa: điền số CỦA RIÊNG lần đang sửa (`dongs`), KHÔNG phải số cộng dồn của `doi_chieu` —
  // dùng nhầm là thổi phồng lần đang sửa bằng số của các lần trước.
  const ds: VtDongForm[] = (lanSua?.dongs ?? []).map((d) => {
    const k = `${d.hang_loai}:${d.hang_id}`;
    return {
      key: k,
      hang_loai: d.hang_loai, hang_id: d.hang_id, ten: d.ten,
      // Vá GỐC (không phải triệu chứng): dòng đã lưu có thể mang `dvt=""` (routing mập mờ lúc
      // gửi lần đầu) trong khi kế hoạch nay đã có đơn vị. BE gộp `ln.dvt or k_row.dvt` nên FE
      // phải hiện ĐÚNG thứ BE sẽ dùng — không được hiện "—" trên màn rồi tính theo "to" ở BE.
      dvt: d.dvt || (kh.get(k)?.dvt ?? d.dvt), dvtKeHoach: kh.get(k)?.dvt ?? d.dvt,
      sl_ke_hoach: d.sl_ke_hoach, sl_yeu_cau: d.sl_yeu_cau, slText: String(d.sl_yeu_cau),
      ly_do_chenh_lech: d.ly_do_chenh_lech ?? "", tuKeHoach: kh.has(k),
    };
  });
  // Sửa LẦN ĐẦU: kế hoạch có thể đã thêm mặt hàng sau lúc gửi — bù nốt vào (số xin = 0) để lần
  // đầu vẫn lưu đủ mọi vật tư kế hoạch.
  if (lanSua?.loai === "lan_dau") {
    const co = new Set(ds.map((d) => d.key));
    for (const k of cap.ke_hoach) {
      const key = `${k.hang_loai}:${k.hang_id}`;
      if (co.has(key)) continue;
      ds.push({
        key, hang_loai: k.hang_loai, hang_id: k.hang_id, ten: k.ten,
        dvt: k.dvt, dvtKeHoach: k.dvt, sl_ke_hoach: k.sl, sl_yeu_cau: 0, slText: "0",
        ly_do_chenh_lech: "", tuKeHoach: true,
      });
    }
  }
  return ds;
}

function VatTuDeNghiForm({
  cv, cap, mode, lanSua, busy, onHuy, onXong, exec,
}: {
  cv: SxWorkItemChiTiet["cong_viec"]; cap: SxVatTuCap; mode: VtFormMode;
  lanSua: SxVatTuCapLan | null; busy: boolean;
  onHuy: () => void; onXong: () => void; exec: ThsxExec;
}) {
  const { token } = useAuth();
  // Loại HIỆU LỰC quyết luật lý do + luật lọc dòng: sửa thì theo `loai` của chính lần đang sửa.
  const loaiHieuLuc: "lan_dau" | "bo_sung" =
    mode === "bo_sung" ? "bo_sung" : mode === "sua" ? (lanSua?.loai === "bo_sung" ? "bo_sung" : "lan_dau") : "lan_dau";
  // Giờ cần: sửa = giờ CỦA CHÍNH lần đó (chỉnh lại cái tổ đã chọn, không quay về mốc gốc).
  const [canLuc, setCanLuc] = useState(
    (mode === "sua" ? toDtLocal(lanSua?.can_luc) : toDtLocal(cv.du_kien_bat_dau)) || nowDtLocal(),
  );
  const [dongs, setDongs] = useState<VtDongForm[]>(() => vtDongKhoiTao(cap, mode, lanSua));
  const seq = useRef(0);
  const nganKeoRef = useRef<HTMLElement>(null);
  const nhanTrenNen = useRef(false);
  // Đưa focus vào ngăn kéo để Esc tới được `onKeyDown` của nó ngay cả khi chưa bấm ô nào.
  useEffect(() => { nganKeoRef.current?.focus({ preventScroll: true }); }, []);

  // "Đã yêu cầu luỹ kế" cho dòng bổ sung — nền để tổ trưởng biết mình đang xin thêm trên cái gì.
  const luyKe = new Map(cap.doi_chieu.map((d) => [`${d.hang_loai}:${d.hang_id}`, d]));

  function sua(key: string, patch: Partial<VtDongForm>) {
    setDongs((ds) => ds.map((d) => (d.key === key ? { ...d, ...patch } : d)));
  }
  /** Đặt số lượng bằng NÚT (±1 / Về 0): số và chuỗi hiển thị đi cùng nhau. */
  function datSl(key: string, sl: number) {
    const v = Math.max(0, sl);
    sua(key, { sl_yeu_cau: v, slText: String(v) });
  }
  function themDong() {
    seq.current += 1;
    setDongs((ds) => [...ds, {
      key: `moi-${seq.current}`, hang_loai: "", hang_id: 0, ten: "", dvt: "", dvtKeHoach: "",
      sl_ke_hoach: 0, sl_yeu_cau: 0, slText: "", ly_do_chenh_lech: "", tuKeHoach: false,
    }]);
  }

  const lines = vtPayloadLines(dongs, loaiHieuLuc);
  // Chỉ chặn khi có thứ NÓI RA ĐƯỢC là thiếu — không bao giờ chặn vì "đoán là thiếu lý do"
  // (luật lý do thật nằm ở BE, và BE trả câu tiếng Việt cụ thể).
  // `moi`/`sua` (lần đầu) vẫn cho gửi TOÀN 0 khi công đoạn CÓ kế hoạch: đó chính là "tổ xác nhận
  // không cần cấp" (spec §5.3) — dòng kế hoạch vẫn nằm trong `lines` nên không bị chặn.
  const canTro = vtCanTro(dongs, lines, mode, loaiHieuLuc);
  const hopLe = gioNhapHopLe(canLuc) && canTro == null;

  async function luu() {
    const body: SxVatTuDeNghiIn = { can_luc: canLuc, lines };
    // Sửa mà không tra ra lần nào ⇒ THOÁT, tuyệt đối không rơi sang nhánh tạo mới: đó là đẻ thêm
    // một lần đề nghị nữa (cộng dồn vào bản đối chiếu) thay vì sửa lần đang mở.
    if (mode === "sua" && lanSua == null) return;
    const ok = mode === "sua" && lanSua != null
      ? await exec.suaDeNghiVatTu(cv.id, lanSua.id, body)
      : await exec.deNghiVatTu(cv.id, body);
    if (ok) onXong();
  }

  const tieuDe = mode === "sua"
    ? `Sửa đề nghị${lanSua ? ` · Lần ${lanSua.lan_so}` : ""}`
    : mode === "bo_sung" ? "Yêu cầu bổ sung" : "Yêu cầu mới";
  const soMatHang = lines.filter((l) => l.sl_yeu_cau > VT_EPS).length;

  // Cùng khuôn ngăn kéo "Yêu cầu mới" của màn Yêu cầu nhập xuất (`KhoDeNghiPage`): tổ trưởng xin
  // vật tư ở đây hay ở màn Kho cũng gặp một kiểu. PORTAL ra `body` vì `.thsx-panel--open` có
  // `transform` — render tại chỗ thì ngăn kéo bị nhốt trong khung drawer bàn tổ, không trượt từ mép
  // màn được. `zIndex` inline: `.rc-drawer__scrim` khai 60, thấp hơn chính drawer bàn tổ (61).
  return createPortal(
    <div className="rc-drawer__scrim" style={{ zIndex: 70 }}
      // Chỉ đóng khi nhấn VÀ thả đều trên nền: kéo bôi chữ trong ô rồi thả lệch ra ngoài không được
      // vứt mất những gì vừa gõ. `stopPropagation` vì sự kiện React đi xuyên portal, nổi về cây bàn tổ.
      onMouseDown={(e) => { nhanTrenNen.current = e.target === e.currentTarget; }}
      onClick={(e) => {
        e.stopPropagation();
        if (nhanTrenNen.current && e.target === e.currentTarget && !busy) onHuy();
      }}>
      <aside ref={nganKeoRef} className="rc-drawer rc-drawer--wide" role="dialog" aria-modal="true"
        aria-label={`Yêu cầu cấp vật tư — ${tieuDe}`} tabIndex={-1}
        // Esc nuốt tại đây: trang nghe Esc ở `document` để đóng cả drawer bàn tổ, chỉ nhường phím
        // đã `defaultPrevented` (ô gợi ý mặt hàng đang xổ cũng tự nuốt Esc của nó).
        onKeyDown={(e) => {
          if (e.key !== "Escape" || e.defaultPrevented) return;
          e.preventDefault();
          if (!busy) onHuy();
        }}>
        <header className="rc-drawer__head">
          <div>
            <div className="rc-drawer__kicker">Yêu cầu cấp vật tư</div>
            <h2 className="rc-drawer__title">{tieuDe}</h2>
          </div>
          <button type="button" className="rc-drawer__x" onClick={onHuy} disabled={busy} aria-label="Đóng">
            <Icon name="x" size={16} />
          </button>
        </header>

        <div className="rc-drawer__body">
          <section className="rc-sec">
            <h3 className="rc-sec__title">Thông tin chung</h3>
            <div className="kho-info-grid">
              <label className="kho-info-item">
                <span className="kho-info-item__label">Giờ cần</span>
                <input type="datetime-local" className="rc-input" min={GIO_NHAP_MIN} max={GIO_NHAP_MAX}
                  value={canLuc} disabled={busy} onChange={(e) => setCanLuc(e.target.value)} />
              </label>
              {cv.nguon_ma && (
                <div className="kho-info-item">
                  <span className="kho-info-item__label">Cho lệnh</span>
                  <div className="kho-info-item__val">{cv.nguon_ma}</div>
                </div>
              )}
              <div className="kho-info-item">
                <span className="kho-info-item__label">Công đoạn</span>
                <div className="kho-info-item__val">{cv.ten_cong_doan}</div>
              </div>
            </div>
          </section>

          <section className="rc-sec">
            <h3 className="rc-sec__title">Vật tư yêu cầu</h3>
            <div className="kho-lines__wrap kho-lines-card">
              <table className="kho-lines thsx-vtdn">
                <thead className="kho-lines__head">
                  <tr>
                    <th style={{ width: 40, textAlign: "center" }}>STT</th>
                    <th style={{ minWidth: 180 }}>Vật tư</th>
                    {/* Bổ sung không có "kế hoạch" để so — nền của nó là số ĐÃ xin qua các lần trước. */}
                    <th className="kho-num" style={{ width: 120 }}>
                      {loaiHieuLuc === "bo_sung" ? "Đã yêu cầu" : "Kế hoạch"}
                    </th>
                    <th style={{ width: 70, textAlign: "center" }}>ĐVT</th>
                    <th className="kho-num" style={{ width: 110 }}>SL yêu cầu</th>
                    <th style={{ width: 56 }} aria-label="Thao tác" />
                  </tr>
                </thead>
                <tbody>
                  {dongs.length === 0 && (
                    <tr>
                      <td colSpan={6} className="kho-lines__empty">
                        {loaiHieuLuc === "bo_sung"
                          ? "Thêm đúng mặt hàng đang thiếu — đề nghị bổ sung là xin THÊM trên nền đã yêu cầu."
                          : "Công đoạn chưa có nhu cầu vật tư theo kế hoạch — thêm mặt hàng nếu tổ cần xin."}
                      </td>
                    </tr>
                  )}
                  {dongs.map((d, i) => {
                    const ly = vtCanLyDo(d, loaiHieuLuc);
                    const lk = luyKe.get(`${d.hang_loai}:${d.hang_id}`);
                    return (
                      <Fragment key={d.key}>
                        <tr>
                          <td className="kho-lines__code" style={{ textAlign: "center" }}>{i + 1}</td>
                          <td>
                            {d.tuKeHoach ? (
                              <div className="kho-lines__name">{d.ten}</div>
                            ) : (
                              <MaterialCombobox
                                token={token ?? ""} hangTen={d.ten || null} disabled={busy}
                                onPick={(m) => {
                                  // Ưu tiên đơn vị lần trước của CHÍNH mặt hàng này, chỉ rơi về đơn vị gốc
                                  // khi nó chưa từng được xin (xem `vtDvtLanTruoc`). KHÔNG gác thêm theo
                                  // `mode`: lần "moi" chưa có đề nghị nào nên hàm trả `null` và mọi thứ y
                                  // như cũ, còn lần "sua"/"bo_sung" thì bám lần trước mới là thứ đúng —
                                  // thêm điều kiện mode chỉ có thể làm dòng lật đơn vị trở lại.
                                  const dv = vtDvtLanTruoc(cap.cac_de_nghi, m.hang_loai, m.hang_id)
                                    ?? m.don_vi_goc ?? "";
                                  sua(d.key, {
                                    hang_loai: m.hang_loai, hang_id: m.hang_id, ten: m.ten,
                                    dvt: dv, dvtKeHoach: dv,
                                  });
                                }} />
                            )}
                            {/* Giọng đi theo SỐ ĐANG XIN, không theo "có đơn vị hay không". Ở 0 thì dòng
                             *  này hợp lệ — BE nhận và miễn cả luật lý do, ô Lý do ngay dưới ghi "Tuỳ
                             *  chọn" — chữ ĐỎ ở đó là hai câu đọc ngược nhau. Có số dương mới là chặn
                             *  thật: `vtCanTro` đang tắt nút Gửi vì đúng dòng này, nên phải nói ra.
                             *  Không đóng đinh nguyên nhân vào "danh mục chưa khai": ô đơn vị còn trống
                             *  được vì snapshot của bước chốt trước lúc kỹ thuật khai, hoặc vì routing
                             *  chưa đủ để suy ra đơn vị đếm giấy — cùng lý do câu lỗi BE đã bỏ cách nói đó. */}
                            {vtThieuDonVi(d) && (d.sl_yeu_cau > VT_EPS ? (
                              <div className="kho-hint kho-hint--rust">
                                Chưa có đơn vị tính nên chưa xin được — nhờ kỹ thuật kiểm lại đơn vị, hoặc
                                để dòng này ở 0 rồi gửi những món còn lại.
                              </div>
                            ) : (
                              <div className="kho-hint">
                                Chưa có đơn vị tính — để ở 0 thì vẫn gửi được. Muốn xin món này thì nhờ
                                kỹ thuật kiểm lại đơn vị.
                              </div>
                            ))}
                          </td>
                          {/* Số nền mang ĐƠN VỊ CỦA NÓ ngay trong ô: tổ có thể khai bằng đơn vị khác kế
                              hoạch, cột ĐVT bên cạnh là đơn vị của số ĐANG XIN. */}
                          <td className="kho-num">
                            {loaiHieuLuc === "bo_sung"
                              ? (lk ? `${num(lk.sl_yeu_cau)} ${nhanDonVi(lk.dvt)}` : "—")
                              : (d.tuKeHoach ? `${num(d.sl_ke_hoach)} ${nhanDonVi(d.dvtKeHoach)}` : "—")}
                          </td>
                          <td style={{ textAlign: "center" }}>
                            <span className="badge-sem badge-sem--muted" style={{ fontSize: 12 }}>
                              {d.dvt ? nhanDonVi(d.dvt) : "—"}
                            </span>
                          </td>
                          <td className="kho-num">
                            <input type="number" min={0} className="rc-input kho-num" inputMode="decimal"
                              value={d.slText} disabled={busy} aria-label={`Số lượng yêu cầu${d.ten ? ` — ${d.ten}` : ""}`}
                              onChange={(e) => sua(d.key, {
                                slText: e.target.value, sl_yeu_cau: Math.max(0, toNum(e.target.value)),
                              })}
                              // Rời ô thì chữ trong ô phải bằng ĐÚNG số sắp gửi. Gõ "-5" là ô hiện −5 mà
                              // payload gửi 0 — mà 0 có nghĩa nghiệp vụ hẳn hoi ("tổ xác nhận không cần
                              // cấp"), tức một dấu trừ gõ nhầm âm thầm đưa dòng kế hoạch về 0. Cùng lý do
                              // cho "1." bỏ dở, "1,5" dán kiểu Việt, hay ô xoá trắng: `<input type="number">`
                              // trả "" cho mọi giá trị chưa hợp lệ, nên số thật đã là 0 rồi.
                              onBlur={() => sua(d.key, { slText: String(d.sl_yeu_cau) })} />
                          </td>
                          <td style={{ textAlign: "center" }}>
                            {/* Dòng KẾ HOẠCH không xoá được (lần đầu phải lưu đủ kế hoạch) — đường của nó
                                là "Về 0", một hành động có CHỦ Ý: "tổ xác nhận không cần cấp". */}
                            {d.tuKeHoach ? (
                              <button type="button" className="thsx-x-linkbtn" disabled={busy || d.sl_yeu_cau <= 0}
                                onClick={() => datSl(d.key, 0)}>Về 0</button>
                            ) : (
                              <button type="button" className="rc-bands__del" aria-label="Bỏ dòng" disabled={busy}
                                onClick={() => setDongs((ds) => ds.filter((x) => x.key !== d.key))}>
                                <Icon name="x" size={13} />
                              </button>
                            )}
                          </td>
                        </tr>
                        {ly.hien && (
                          <tr className="thsx-vtdn__lydo">
                            <td />
                            <td colSpan={5}>
                              <label className="thsx-vtdn__lydo-f">
                                <span className="kho-info-item__label">
                                  Lý do{ly.batBuoc && <span className="thsx-x-vt-req">*</span>}
                                </span>
                                <input type="text" className="rc-input" value={d.ly_do_chenh_lech} disabled={busy}
                                  onChange={(e) => sua(d.key, { ly_do_chenh_lech: e.target.value })}
                                  placeholder={ly.batBuoc ? "Bắt buộc — vì sao khác kế hoạch" : "Tuỳ chọn"} />
                              </label>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
              {/* Không cộng "Tổng SL" như màn Kho: các dòng ở đây khác đơn vị (kg mực, tờ giấy…),
                  cộng lại ra một con số vô nghĩa. */}
              <div className="kho-live-summary-bar">
                <span>Đang xin <strong>{soMatHang}</strong> mặt hàng</span>
              </div>
            </div>
            <button type="button" className="rc-bands__add" onClick={themDong} disabled={busy}>
              + Thêm dòng
            </button>
          </section>
        </div>

        <footer className="rc-drawer__foot">
          {/* Nút Gửi tắt thì câu lý do đứng NGAY cạnh nó, không nằm cuối bảng dài đã cuộn khuất. */}
          {canTro && <span className="kho-hint kho-hint--rust thsx-vtdn__cantro">{canTro}</span>}
          <Button variant="accent" onClick={luu} disabled={busy || !hopLe}>
            <Icon name={mode === "sua" ? "check" : "send"} size={13} />
            {mode === "sua" ? " Lưu thay đổi" : " Gửi đề nghị"}
          </Button>
        </footer>
      </aside>
    </div>,
    document.body,
  );
}

// ─────────────────────────── HỖ TRỢ CHÉO (§9) ─────────────────────────────
function HoTroSection({
  chiTiet, canAssign, busy, hoTroUngVien, exec,
}: {
  chiTiet: SxWorkItemChiTiet; canAssign: boolean; busy: boolean;
  hoTroUngVien: SxHoTroUngVien[]; exec: ThsxExec;
}) {
  const [formOpen, setFormOpen] = useState(false);
  const ht = chiTiet.ho_tro;

  return (
    <section className="thsx-psec thsx-x">
      <div className="thsx-psec__h">
        <span className="thsx-psec__title"><Icon name="users" size={13} /> Hỗ trợ chéo</span>
        {canAssign && (
          <Button variant="ghost" onClick={() => setFormOpen(true)} disabled={busy} aria-haspopup="dialog">
            <Icon name="plus" size={13} /> Đề xuất hỗ trợ
          </Button>
        )}
      </div>

      {formOpen && (
        <HoTroForm hoTroUngVien={hoTroUngVien} busy={busy}
          onXong={() => setFormOpen(false)} exec={exec} />
      )}

      {ht.length === 0 ? (
        <p className="thsx-note">Chưa có thoả thuận hỗ trợ nào.</p>
      ) : (
        <ul className="thsx-x-list">
          {ht.map((h) => (
            <HoTroRow key={h.id} h={h} busy={busy} exec={exec} />
          ))}
        </ul>
      )}
    </section>
  );
}

function HoTroForm({
  hoTroUngVien, busy, onXong, exec,
}: {
  hoTroUngVien: SxHoTroUngVien[]; busy: boolean; onXong: () => void; exec: ThsxExec;
}) {
  const [toLoc, setToLoc] = useState<number | null>(null);
  const [empId, setEmpId] = useState<number | null>(null);
  const [ngayLv, setNgayLv] = useState(todayYmd());
  const [tyLe, setTyLe] = useState("");
  const [moTa, setMoTa] = useState("");
  const nTyLe = toNum(tyLe);
  const hopLe = empId != null && !!ngayLv && nTyLe > 0 && nTyLe <= 100;

  // Ứng viên là thợ của MỌI tổ SX khác — hàng chục người, nên ô chọn phải tìm được (gõ không dấu,
  // mảnh tên, mã NV hoặc tên tổ) và lọc theo tổ. Nhóm theo tổ để mắt biết đang ở khúc nào.
  const theoTo = new Map<number | null, { ten: string; n: number }>();
  for (const h of hoTroUngVien) {
    const cur = theoTo.get(h.to_id);
    if (cur) cur.n += 1;
    else theoTo.set(h.to_id, { ten: h.to_ten ?? "Chưa có tổ", n: 1 });
  }
  const toOpts: SelectOption<number | null>[] = [
    { value: null, label: "Tất cả tổ", hint: String(hoTroUngVien.length) },
    ...[...theoTo.entries()]
      .sort((a, b) => a[1].ten.localeCompare(b[1].ten, "vi"))
      .map(([id, t]) => ({ value: id, label: t.ten, hint: String(t.n) })),
  ];
  const thoOpts: SelectOption<number | null>[] = hoTroUngVien
    .filter((h) => toLoc == null || h.to_id === toLoc)
    .map((h) => ({ h, to: h.to_ten ?? "Chưa có tổ" }))
    .sort((a, b) => a.to.localeCompare(b.to, "vi") || a.h.full_name.localeCompare(b.h.full_name, "vi"))
    .map(({ h, to }) => ({
      value: h.id, label: h.full_name, hint: h.code ?? undefined,
      group: toLoc == null ? to : undefined, search: to,
    }));

  function chonTo(id: number | null) {
    setToLoc(id);
    // Thợ đang chọn không thuộc tổ vừa lọc ⇒ bỏ chọn, khỏi gửi nhầm người đã khuất khỏi danh sách.
    if (id != null && empId != null && hoTroUngVien.find((h) => h.id === empId)?.to_id !== id) setEmpId(null);
  }

  async function luu() {
    const body: SxHoTroDeXuatIn = {
      employee_id: empId!, ngay_lam_viec: ngayLv, ty_le_phan_tram: nTyLe,
      mo_ta: moTa.trim() || null,
    };
    if (await exec.deXuatHoTro(body)) onXong();
  }

  return (
    <ThsxModal
      title="Đề xuất hỗ trợ chéo" icon="users" busy={busy} onClose={onXong}
      footer={<>
        <Button variant="ghost" onClick={onXong} disabled={busy}>Huỷ</Button>
        <Button variant="accent" onClick={luu} disabled={busy || !hopLe}>
          <Icon name="check" size={13} /> Đề xuất
        </Button>
      </>}
    >
      {/* KHÔNG bọc bằng <Field> (thẻ <label>): nhãn bọc nút mở danh sách thì bấm chữ nhãn cũng
          bật danh sách, và ô tìm trong popover không gắn được với nhãn. */}
      <div className="thsx-x-grid-to">
        <div className="thsx-x-fld">
          <span className="thsx-x-fld__l">Tổ</span>
          <Select portal searchable value={toLoc} options={toOpts} onChange={chonTo} ariaLabel="Lọc theo tổ"
            searchPlaceholder="Gõ tên tổ…" className="thsx-x-seltrig" />
        </div>
        <div className="thsx-x-fld">
          <span className="thsx-x-fld__l">Thợ hỗ trợ (từ tổ khác)</span>
          <Select portal searchable value={empId} options={thoOpts} onChange={setEmpId}
            placeholder="— Chọn thợ —" searchPlaceholder="Gõ tên, mã NV hoặc tổ…" ariaLabel="Thợ hỗ trợ"
            className="thsx-x-seltrig" />
        </div>
      </div>
      <div className="thsx-x-grid2">
        <Field label="Ngày làm">
          <input type="date" className="thsx-x-in" value={ngayLv} onChange={(e) => setNgayLv(e.target.value)} />
        </Field>
        <Field label="Tỷ lệ (%)">
          <input type="number" min={0} max={100} className="thsx-x-in" value={tyLe} onChange={(e) => setTyLe(e.target.value)} inputMode="numeric" />
        </Field>
      </div>
      <Field label="Mô tả">
        <input type="text" className="thsx-x-in" value={moTa} onChange={(e) => setMoTa(e.target.value)} placeholder="Nội dung hỗ trợ (tuỳ chọn)" />
      </Field>
      {hoTroUngVien.length === 0 && <p className="thsx-x-hint">Không có thợ tổ khác đang làm để đề xuất.</p>}
    </ThsxModal>
  );
}

function HoTroRow({
  h, busy, exec,
}: {
  h: SxHoTro; busy: boolean; exec: ThsxExec;
}) {
  const [huyOpen, setHuyOpen] = useState(false);
  const [lyDo, setLyDo] = useState("");
  const st = HT_TT[h.trang_thai] ?? { txt: h.trang_thai, cls: "thsx-x-pill--wait" };
  const chuaChot = h.trang_thai === "pending_both";

  return (
    <li className="thsx-x-ht">
      <div className="thsx-x-ht__main">
        <span className="thsx-x-ht__nm">{h.ho_ten}</span>
        <span className="thsx-x-ht__flow">{h.to_goc_ten ?? "?"} → {h.to_thuc_hien_ten ?? "?"}</span>
        <span className="thsx-x-item__spacer" />
        <span className="thsx-x-ht__pc thsx-num">{num(h.ty_le_phan_tram)}%</span>
        <span className={`thsx-x-pill ${st.cls}`}>{st.txt}</span>
      </div>
      <div className="thsx-x-ht__meta">
        <span className="thsx-num">{ngay(h.ngay_lam_viec)}</span>
        {chuaChot && (
          <span className="thsx-x-ht__flags">
            <span className={h.da_xac_nhan_goc ? "is-ok" : ""}>tổ gốc {h.da_xac_nhan_goc ? "✓" : "…"}</span>
            <span className={h.da_xac_nhan_thuc_hien ? "is-ok" : ""}>tổ làm {h.da_xac_nhan_thuc_hien ? "✓" : "…"}</span>
          </span>
        )}
        {h.mo_ta && <span className="thsx-x-ht__mo">{h.mo_ta}</span>}
      </div>
      {/* Nút theo cờ máy chủ tính cho CHÍNH người xem: bên mình đã đứng tên thì thôi hiện Xác nhận
          (bấm lại không đổi gì); huỷ khi đứng được cho một trong hai tổ. */}
      {(h.co_the_xac_nhan || h.co_the_huy) && (
        <div className="thsx-x-act thsx-x-act--row">
          {h.co_the_xac_nhan && (
            <Button variant="accent" onClick={() => void exec.xacNhanHoTro(h.id, h.version)} disabled={busy}>
              <Icon name="check" size={13} /> Xác nhận
            </Button>
          )}
          {h.co_the_huy && (
            <Button variant="ghost" onClick={() => setHuyOpen((o) => !o)} disabled={busy}>
              <Icon name="ban" size={12} /> Huỷ
            </Button>
          )}
        </div>
      )}
      {huyOpen && (
        <div className="thsx-x-form thsx-x-form--sub">
          <Field label="Lý do huỷ">
            <input type="text" className="thsx-x-in" value={lyDo} onChange={(e) => setLyDo(e.target.value)} placeholder="Tuỳ chọn" autoFocus />
          </Field>
          <div className="thsx-x-act">
            <Button variant="ghost" onClick={() => setHuyOpen(false)} disabled={busy}>Đóng</Button>
            <Button variant="secondary" disabled={busy}
              onClick={async () => { if (await exec.huyHoTro(h.id, lyDo.trim(), h.version)) setHuyOpen(false); }}>
              <Icon name="ban" size={13} /> Huỷ hỗ trợ
            </Button>
          </div>
        </div>
      )}
    </li>
  );
}

// ============================ nguyên liệu dùng chung ========================
/** Hộp thoại NỔI cho biểu mẫu mở từ nút ở đầu khối (Ghi mẻ · Đề xuất giao · Đề xuất hỗ trợ) — một
 *  khung chung để các khối nói cùng một kiểu. Yêu cầu cấp vật tư KHÔNG dùng khung này: nó mở thành
 *  ngăn kéo cùng khuôn màn Kho (xem `VatTuDeNghiForm`). Render TẠI CHỖ, không portal: lớp phủ
 *  `position: fixed` bám khung drawer bàn tổ (drawer có `transform`), biểu mẫu giữ nguyên các lớp
 *  `.thsx-x-*` của nó. Thân cuộn riêng, chân nút đứng yên.
 *
 *  Esc bắt ở CHÍNH hộp thoại rồi `preventDefault`: trang (`ThucHienSxPage`) nghe Esc ở `document`
 *  để đóng cả drawer và chỉ nhường phím đã bị nuốt. Nghe ở `window` như bản đầu thì drawer đóng
 *  TRƯỚC (document nổi bọt trước window), mất luôn việc đang mở. Ô gợi ý mặt hàng đang xổ danh
 *  sách tự nuốt Esc của nó, nên Esc đầu chỉ gập danh sách.
 *
 *  Bấm ra ngoài thì đóng, nhưng chỉ khi cả nhấn lẫn thả đều trên lớp phủ — kéo bôi chữ trong ô rồi
 *  thả chuột lệch ra ngoài không được xoá mất những gì vừa gõ. */
function ThsxModal({
  title, icon, badge, busy, onClose, footer, children,
}: {
  title: string; icon: IconName; badge?: ReactNode; busy: boolean;
  onClose: () => void; footer: ReactNode; children: ReactNode;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const nhanTrenLopPhu = useRef(false);
  // Đưa focus vào hộp thoại để Esc tới được `onKeyDown` bên dưới ngay cả khi chưa bấm ô nào.
  useEffect(() => { dialogRef.current?.focus({ preventScroll: true }); }, []);

  return (
    <div className="thsx-batch-modal-overlay"
      onMouseDown={(e) => { nhanTrenLopPhu.current = e.target === e.currentTarget; }}
      onClick={(e) => {
        if (nhanTrenLopPhu.current && e.target === e.currentTarget && !busy) onClose();
      }}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1}
        className="thsx-batch-modal-dialog thsx-glass-batch-card thsx-x-form"
        onKeyDown={(e) => {
          if (e.key !== "Escape" || e.defaultPrevented) return;
          e.preventDefault();
          if (!busy) onClose();
        }}>
        <div className="thsx-glass-batch-h">
          <div className="thsx-glass-batch-h-title">
            <Icon name={icon} size={14} className="thsx-pulse-icon" />
            <span>{title}</span>
          </div>
          <div className="thsx-batch-modal-h-right">
            {badge && <span className="thsx-glass-unit-badge">{badge}</span>}
            <button type="button" className="thsx-batch-modal-close" aria-label="Đóng" disabled={busy} onClick={onClose}>
              ×
            </button>
          </div>
        </div>
        <div className="thsx-batch-modal-body">{children}</div>
        <div className="thsx-glass-form-ftr thsx-x-act">{footer}</div>
      </div>
    </div>
  );
}

export function Field({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <label className="thsx-x-fld">
      <span className="thsx-x-fld__l">{label}</span>
      {children}
    </label>
  );
}

/** Dải hỏi-lại một nhịp cho việc nghịch chiều (mở lại phân bổ đã chốt…). Trước đây chỗ này là
 *  form chọn lý do từ danh mục; danh mục ĐÃ GỠ (mg 0288) nên chỉ còn một nhịp xác nhận — vẫn giữ
 *  để không bấm nhầm một cú không tự hoàn lại. */
function XacNhanForm({
  busy, hoi, confirm, onHuy, onXac,
}: {
  busy: boolean; hoi: string; confirm: string; onHuy: () => void; onXac: () => void;
}) {
  return (
    <div className="thsx-x-form thsx-x-form--sub">
      <p className="thsx-note">{hoi}</p>
      <div className="thsx-x-act">
        <Button variant="ghost" onClick={onHuy} disabled={busy}>Huỷ</Button>
        <Button variant="accent" onClick={onXac} disabled={busy}>
          <Icon name="check" size={13} /> {confirm}
        </Button>
      </div>
    </div>
  );
}
