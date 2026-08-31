// PHA SAU của DRAWER Thực hiện sản xuất — Giai đoạn 3 (sản lượng · bàn giao · vật tư) + Giai đoạn 4
// (hỗ trợ chéo · phân bổ sản lượng → lương khoán). Gộp thẳng vào drawer `ThsxDrawer` (KHÔNG đẻ màn
// mới): mỗi mặt là một khối gấp/mở với form ghi tại chỗ (panel hẹp, tránh modal chồng).
//
// Component KHÔNG tự gọi API: mọi mặt GHI đi qua `exec.*` (controller lo khoá lạc quan + refetch +
// toast). Lý do/lỗi (§15) nạp từ danh mục `san_xuat_ly_do` qua `loadLyDo(nhom)` — KHÔNG hardcode.
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import type {
  SxWorkItemChiTiet, SxBatch, SxBanGiao, SxPhanBo, SxHoTro, SxHoTroUngVien, SxLyDo,
  SxBatchIn, SxBanGiaoDeXuatIn, SxBanGiaoSuaIn, SxBanGiaoDieuChinhIn,
  SxHoTroDeXuatIn, SxBuTruIn, SxLoaiTruIn, SxGoLoaiTruIn,
  SxKcsBatchIn, SxNhapKhoYeuCauIn, SxHuyPhanChuaNhanIn, SxPhanLoaiBtpIn, SxDongThieuIn,
  SxKetQuaNhanh, SxVatTuCap, SxVatTuCapLan, SxVatTuCapDoiChieu,
  SxVatTuDeNghiIn, SxVatTuDeNghiDongIn,
} from "../api/client";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import { MaterialCombobox } from "../components/MaterialCombobox";
import { useAuth } from "../auth/useAuth";
import { num, ngayGio, ngay } from "./keHoachSxShared";

// ============================ hợp đồng hành động (controller cấp) ============================
export interface ThsxExec {
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
  moLaiPhanBo: (phanBoId: number, lyDoId: number, version: number) => Promise<boolean>;
  buTru: (batchId: number, body: SxBuTruIn) => Promise<boolean>;
  loaiTru: (batchId: number, body: SxLoaiTruIn) => Promise<boolean>;
  goLoaiTru: (batchId: number, body: SxGoLoaiTruIn) => Promise<boolean>;
  // Giai đoạn 5 — KCS §13 · Kho §14 · Đóng nhóm §16/§13.3 (mọi mặt qua `mutate` ở controller).
  taoBatchKcs: (congViecId: number, body: SxKcsBatchIn) => Promise<boolean>;
  ghiLoiKcs: (
    kcsBatchId: number,
    body: {
      nhom_loi_id: number; to_chiu_id?: number | null; cong_doan_ref_id?: number | null;
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
  canAssign: boolean;
  busy: boolean;
  hoTroUngVien: SxHoTroUngVien[];
  loadLyDo: (nhom: string) => Promise<SxLyDo[]>;
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
export function ThsxExecPanels({ chiTiet, canAssign, busy, hoTroUngVien, loadLyDo, exec }: Props) {
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
        chiTiet={chiTiet} canAssign={canAssign} busy={busy}
        loadLyDo={loadLyDo} exec={exec} pbTheoBatch={pbTheoBatch}
        tenNguoi={tenNguoi} hoTroUngVien={hoTroUngVien} />
      <BanGiaoSection
        chiTiet={chiTiet} canAssign={canAssign} busy={busy}
        conLai={conLai} loadLyDo={loadLyDo} exec={exec} />
      <VatTuSection chiTiet={chiTiet} canAssign={canAssign} busy={busy} exec={exec} tenNguoi={tenNguoi} />
      <HoTroSection
        chiTiet={chiTiet} canAssign={canAssign} busy={busy}
        hoTroUngVien={hoTroUngVien} exec={exec} />
    </>
  );
}

// ─────────────────────────── SẢN LƯỢNG (§10-11) ───────────────────────────
function SanLuongSection({
  chiTiet, canAssign, busy, loadLyDo, exec, pbTheoBatch, tenNguoi, hoTroUngVien,
}: {
  chiTiet: SxWorkItemChiTiet; canAssign: boolean; busy: boolean;
  loadLyDo: Props["loadLyDo"]; exec: ThsxExec;
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
          <Button variant="ghost" onClick={() => setFormOpen((o) => !o)} disabled={busy} aria-expanded={formOpen}>
            <Icon name="plus" size={13} /> Ghi mẻ
          </Button>
        )}
      </div>

      <div className="thsx-x-stat">
        <span className="thsx-x-stat__it"><b className="thsx-num">{num(sl.tong_tot)}</b> tốt</span>
        <span className="thsx-x-stat__sep">·</span>
        <span className="thsx-x-stat__it">đã giao <b className="thsx-num">{num(sl.da_giao)}</b></span>
        <span className="thsx-x-stat__sep">·</span>
        <span className="thsx-x-stat__it">còn <b className="thsx-num">{num(Math.max(0, sl.tong_tot - sl.da_giao))}</b></span>
      </div>

      {ketQuaToa && ketQuaToa.length > 0 && (
        <div className="thsx-x-toa-banner">
          <span className="thsx-x-toa-banner__title">Đã tự toả sang các lệnh sản xuất:</span>
          <ul className="thsx-x-toa-list">
            {ketQuaToa.map((k) => (
              <li key={k.lsx_id}>
                LSX #{k.lsx_id}: <b>{num(k.so_luong)}</b> {k.don_vi}
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
        <BatchForm cv={cv} busy={busy} loadLyDo={loadLyDo}
          onXong={(kq) => { setFormOpen(false); setKetQuaToa(kq.length ? kq : null); }}
          exec={exec} />
      )}

      {sl.batches.length === 0 ? (
        <p className="thsx-note">Chưa ghi mẻ sản lượng nào.</p>
      ) : (
        <ul className="thsx-x-list">
          {sl.batches.map((b) => (
            <BatchRow key={b.id} b={b} canAssign={canAssign} busy={busy}
              pb={pbTheoBatch.get(b.id) ?? null} loadLyDo={loadLyDo}
              tenNguoi={tenNguoi} hoTroUngVien={hoTroUngVien} exec={exec} />
          ))}
        </ul>
      )}
    </section>
  );
}

function BatchForm({
  cv, busy, loadLyDo, onXong, exec,
}: {
  cv: SxWorkItemChiTiet["cong_viec"]; busy: boolean;
  loadLyDo: Props["loadLyDo"]; onXong: (ketQua: SxKetQuaNhanh[]) => void; exec: ThsxExec;
}) {
  const [batDau, setBatDau] = useState(toDtLocal(cv.du_kien_bat_dau));
  const [ketThuc, setKetThuc] = useState(toDtLocal(cv.du_kien_ket_thuc));
  const [tong, setTong] = useState("");
  const [tot, setTot] = useState("");
  const [nhomLoiId, setNhomLoiId] = useState<number | null>(null);
  const [moTaLoi, setMoTaLoi] = useState("");
  const [ghiChu, setGhiChu] = useState("");
  const nTong = toNum(tong);
  const nTot = toNum(tot);
  const hong = Math.max(0, nTong - nTot);
  const donVi = cv.don_vi_ra ?? cv.don_vi_vao ?? null;

  const hopLe = !!batDau && !!ketThuc && ketThuc > batDau
    && nTong > 0 && nTot >= 0 && nTot <= nTong
    && (hong === 0 || nhomLoiId != null);

  async function luu() {
    const body: SxBatchIn = {
      bat_dau: batDau, ket_thuc: ketThuc, tong: nTong, tot: nTot, hong,
      don_vi: donVi,
      nhom_loi_id: hong > 0 ? nhomLoiId : null,
      mo_ta_loi: hong > 0 && moTaLoi.trim() ? moTaLoi.trim() : null,
      ghi_chu: ghiChu.trim() || null,
    };
    const ketQua = await exec.taoBatch(body);
    if (ketQua) onXong(ketQua);
  }

  return (
    <div className="thsx-x-form">
      <div className="thsx-x-grid2">
        <Field label="Bắt đầu">
          <input type="datetime-local" className="thsx-x-in" value={batDau} onChange={(e) => setBatDau(e.target.value)} />
        </Field>
        <Field label="Kết thúc">
          <input type="datetime-local" className="thsx-x-in" value={ketThuc} onChange={(e) => setKetThuc(e.target.value)} />
        </Field>
      </div>
      <div className="thsx-x-grid2">
        <Field label={`Tổng${donVi ? ` (${donVi})` : ""}`}>
          <input type="number" min={0} className="thsx-x-in" value={tong} onChange={(e) => setTong(e.target.value)} inputMode="numeric" />
        </Field>
        <Field label="Tốt">
          <input type="number" min={0} className="thsx-x-in" value={tot} onChange={(e) => setTot(e.target.value)} inputMode="numeric" />
        </Field>
      </div>
      <div className={`thsx-x-hong${hong > 0 ? " is-bad" : ""}`}>
        <Icon name={hong > 0 ? "alert" : "check"} size={13} />
        Hỏng: <b className="thsx-num">{num(hong)}</b>{donVi ? ` ${donVi}` : ""}
        {nTot > nTong && <span className="thsx-x-err">Tốt không được vượt Tổng</span>}
      </div>
      {hong > 0 && (
        <>
          <Field label="Nhóm lỗi (bắt buộc)">
            <LyDoSelect nhom="loi" loadLyDo={loadLyDo} value={nhomLoiId} onChange={setNhomLoiId} />
          </Field>
          <Field label="Mô tả lỗi">
            <input type="text" className="thsx-x-in" value={moTaLoi} onChange={(e) => setMoTaLoi(e.target.value)}
              placeholder="Chi tiết (tuỳ chọn)" />
          </Field>
        </>
      )}
      <Field label="Ghi chú">
        <input type="text" className="thsx-x-in" value={ghiChu} onChange={(e) => setGhiChu(e.target.value)}
          placeholder="Tuỳ chọn" />
      </Field>
      <div className="thsx-x-act">
        <Button variant="ghost" onClick={() => onXong([])} disabled={busy}>Huỷ</Button>
        <Button variant="accent" onClick={luu} disabled={busy || !hopLe}>
          <Icon name="check" size={13} /> Ghi mẻ
        </Button>
      </div>
    </div>
  );
}

function BatchRow({
  b, canAssign, busy, pb, loadLyDo, tenNguoi, hoTroUngVien, exec,
}: {
  b: SxBatch; canAssign: boolean; busy: boolean; pb: SxPhanBo | null;
  loadLyDo: Props["loadLyDo"]; tenNguoi: Map<number, string>;
  hoTroUngVien: SxHoTroUngVien[]; exec: ThsxExec;
}) {
  const [mo, setMo] = useState(false);
  return (
    <li className="thsx-x-item">
      <button type="button" className="thsx-x-item__h" onClick={() => setMo((o) => !o)} aria-expanded={mo}>
        <Icon name="chevron" size={12} className={mo ? "" : "thsx-rot-90"} />
        <span className="thsx-x-item__time thsx-num">{ngayGio(b.bat_dau)}</span>
        <span className="thsx-x-item__spacer" />
        <span className="thsx-x-item__q thsx-num">{num(b.tot)}<span className="thsx-x-unit"> tốt</span></span>
        {b.hong > 0 && <span className="thsx-x-item__hong thsx-num">−{num(b.hong)}</span>}
      </button>
      {mo && (
        <div className="thsx-x-item__body">
          <div className="thsx-x-kv"><span>Tổng / tốt / hỏng</span>
            <b className="thsx-num">{num(b.tong)} / {num(b.tot)} / {num(b.hong)}{b.don_vi ? ` ${b.don_vi}` : ""}</b></div>
          {b.nhom_loi_ten && (
            <div className="thsx-x-kv"><span>Lỗi</span>
              <b>{b.nhom_loi_ten}{b.mo_ta_loi ? ` · ${b.mo_ta_loi}` : ""}</b></div>
          )}
          {b.nguoi_tham_gia.length > 0 && (
            <div className="thsx-x-kv"><span>Người tham gia</span>
              <span className="thsx-x-people">{b.nguoi_tham_gia.join(", ")}</span></div>
          )}
          {b.lot_vao.length > 0 && (
            <div className="thsx-x-kv"><span>Lô vào</span>
              <span>{b.lot_vao.map((l) => `${num(l.so_luong)}${l.don_vi ? ` ${l.don_vi}` : ""}`).join(" · ")}</span></div>
          )}
          {b.ghi_chu && <div className="thsx-x-kv"><span>Ghi chú</span><span>{b.ghi_chu}</span></div>}

          {/* Phân bổ lương của chính mẻ này (§12) */}
          <PhanBoBlock b={b} pb={pb} canAssign={canAssign} busy={busy}
            loadLyDo={loadLyDo} tenNguoi={tenNguoi} hoTroUngVien={hoTroUngVien} exec={exec} />
        </div>
      )}
    </li>
  );
}

// ─────────────────────────── PHÂN BỔ LƯƠNG theo mẻ (§12) ──────────────────
function PhanBoBlock({
  b, pb, canAssign, busy, loadLyDo, tenNguoi, hoTroUngVien, exec,
}: {
  b: SxBatch; pb: SxPhanBo | null; canAssign: boolean; busy: boolean;
  loadLyDo: Props["loadLyDo"]; tenNguoi: Map<number, string>;
  hoTroUngVien: SxHoTroUngVien[]; exec: ThsxExec;
}) {
  const [moLaiOpen, setMoLaiOpen] = useState(false);
  const [buTruOpen, setBuTruOpen] = useState(false);
  const [loaiTruFor, setLoaiTruFor] = useState<number | null>(null);  // id đang mở form loại khỏi lương
  const [loaiTruLyDo, setLoaiTruLyDo] = useState("");

  if (!pb) {
    return (
      <div className="thsx-x-pb thsx-x-pb--empty">
        <span className="thsx-x-pb__none">Chưa phân bổ lương cho mẻ này.</span>
        {canAssign && (
          <Button variant="secondary" onClick={() => void exec.tinhPhanBo(b.id)} disabled={busy}>
            <Icon name="calculator" size={13} /> Tính phân bổ
          </Button>
        )}
      </div>
    );
  }
  const st = PB_TT[pb.trang_thai] ?? { txt: pb.trang_thai, cls: "thsx-x-pill--wait" };
  const isFinal = pb.trang_thai === "finalized";
  const canGhi = canAssign && !isFinal;

  return (
    <div className="thsx-x-pb">
      <div className="thsx-x-pb__h">
        <Icon name="table" size={13} />
        <span className="thsx-x-pb__ttl">Phân bổ lương</span>
        <span className={`thsx-x-pill ${st.cls}`}>{st.txt}</span>
        <span className="thsx-x-item__spacer" />
        <span className="thsx-x-pb__ky thsx-num">kỳ {pb.ky_thang}/{pb.ky_nam}</span>
      </div>
      <div className="thsx-x-pb__sum">
        <span>Q trả lương <b className="thsx-num">{num(pb.q_tra_luong)}</b>{pb.don_vi_tra_luong ? ` ${pb.don_vi_tra_luong}` : ""}</span>
        <span>đơn giá <b className="thsx-num">{num(pb.don_gia)}</b></span>
        {pb.tong_ty_le_ho_tro > 0 && <span>hỗ trợ <b className="thsx-num">{num(pb.tong_ty_le_ho_tro)}%</b></span>}
      </div>

      {pb.dong.length > 0 && (
        <table className="thsx-x-tbl">
          <thead>
            <tr><th>Người</th><th className="r">SL trả lương</th><th className="r">Bậc</th><th className="r">Đơn giá</th></tr>
          </thead>
          <tbody>
            {pb.dong.map((d) => (
              <tr key={`${d.employee_id}-${d.ngay}`}>
                <td>{d.ho_ten}{d.la_ho_tro && <span className="thsx-x-tag-ht">hỗ trợ</span>}</td>
                <td className="r thsx-num">{num(d.so_luong_tra_luong)}</td>
                <td className="r thsx-num">{d.he_so_bac != null ? num(d.he_so_bac) : "—"}</td>
                <td className="r thsx-num">{num(d.don_gia)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

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
                  <Icon name="ban" size={12} /> Loại khỏi lương
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
          <div className="thsx-x-pblt__h"><Icon name="ban" size={12} /> Đã loại khỏi lương batch</div>
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
        <div className="thsx-x-act thsx-x-act--wrap">
          {!isFinal ? (
            <Button variant="accent" onClick={() => void exec.chotPhanBo(pb.phan_bo_id, pb.version)}
              disabled={busy || pb.dong.length === 0 || !pb.can_chot}
              title={pb.dong.length === 0 ? "Chưa có dòng phân bổ"
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
        <LyDoForm nhom="mo_lai_phan_bo" busy={busy} loadLyDo={loadLyDo} label="Lý do mở lại"
          confirm="Mở lại" onHuy={() => setMoLaiOpen(false)}
          onXac={async (id) => { if (await exec.moLaiPhanBo(pb.phan_bo_id, id, pb.version)) setMoLaiOpen(false); }} />
      )}
      {buTruOpen && (
        <BuTruForm batchId={b.id} dong={pb.dong} hoTroUngVien={hoTroUngVien} busy={busy}
          loadLyDo={loadLyDo} onHuy={() => setBuTruOpen(false)}
          onXong={() => setBuTruOpen(false)} exec={exec} />
      )}
    </div>
  );
}

function BuTruForm({
  batchId, dong, hoTroUngVien, busy, loadLyDo, onHuy, onXong, exec,
}: {
  batchId: number; dong: SxPhanBo["dong"]; hoTroUngVien: SxHoTroUngVien[];
  busy: boolean; loadLyDo: Props["loadLyDo"]; onHuy: () => void; onXong: () => void; exec: ThsxExec;
}) {
  const now = new Date();
  const [empId, setEmpId] = useState<number | null>(dong[0]?.employee_id ?? null);
  const [sl, setSl] = useState("");
  const [nam, setNam] = useState(String(now.getFullYear()));
  const [thang, setThang] = useState(String(now.getMonth() + 1));
  const [lyDoId, setLyDoId] = useState<number | null>(null);
  const [moTa, setMoTa] = useState("");

  // Ứng viên = người trong phân bổ + ứng viên hỗ trợ (phòng trường hợp trả lương người ngoài roster).
  const ds = new Map<number, string>();
  for (const d of dong) ds.set(d.employee_id, d.ho_ten);
  for (const h of hoTroUngVien) if (!ds.has(h.id)) ds.set(h.id, `${h.full_name}${h.to_ten ? ` · ${h.to_ten}` : ""}`);

  const nSl = toNum(sl);
  const hopLe = empId != null && nSl > 0 && toNum(nam) > 0 && toNum(thang) >= 1 && toNum(thang) <= 12 && lyDoId != null;

  async function luu() {
    const body: SxBuTruIn = {
      employee_id: empId!, so_luong_tra_luong: nSl,
      ky_bu_nam: toNum(nam), ky_bu_thang: toNum(thang),
      ly_do_id: lyDoId!, mo_ta: moTa.trim() || null,
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
        <Field label="SL trả lương">
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
      <Field label="Lý do">
        <LyDoSelect nhom="mo_lai_phan_bo" loadLyDo={loadLyDo} value={lyDoId} onChange={setLyDoId} />
      </Field>
      <Field label="Mô tả">
        <input type="text" className="thsx-x-in" value={moTa} onChange={(e) => setMoTa(e.target.value)} placeholder="Tuỳ chọn" />
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
  chiTiet, canAssign, busy, conLai, loadLyDo, exec,
}: {
  chiTiet: SxWorkItemChiTiet; canAssign: boolean; busy: boolean; conLai: number;
  loadLyDo: Props["loadLyDo"]; exec: ThsxExec;
}) {
  const [formOpen, setFormOpen] = useState(false);
  const cv = chiTiet.cong_viec;
  const di = chiTiet.ban_giao_di;
  const den = chiTiet.ban_giao_den;

  return (
    <section className="thsx-psec thsx-x">
      <div className="thsx-psec__h">
        <span className="thsx-psec__title"><Icon name="truck" size={13} /> Bàn giao</span>
        {canAssign && (
          <Button variant="ghost" onClick={() => setFormOpen((o) => !o)} disabled={busy} aria-expanded={formOpen}>
            <Icon name="send" size={13} /> Đề xuất giao
          </Button>
        )}
      </div>

      {formOpen && (
        <BanGiaoForm goiY={chiTiet.ban_giao_goi_y} donVi={cv.don_vi_ra ?? null} conLai={conLai}
          busy={busy} onXong={() => setFormOpen(false)} exec={exec} />
      )}

      {di.length > 0 && (
        <>
          <div className="thsx-x-sub">Giao đi</div>
          <ul className="thsx-x-list">
            {di.map((g) => (
              <BanGiaoRow key={g.id} g={g} phia="di" canAssign={canAssign} busy={busy} loadLyDo={loadLyDo} exec={exec} />
            ))}
          </ul>
        </>
      )}
      {den.length > 0 && (
        <>
          <div className="thsx-x-sub">Nhận về</div>
          <ul className="thsx-x-list">
            {den.map((g) => (
              <BanGiaoRow key={g.id} g={g} phia="den" canAssign={canAssign} busy={busy} loadLyDo={loadLyDo} exec={exec} />
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

function BanGiaoForm({
  goiY, donVi, conLai, busy, onXong, exec,
}: {
  goiY: SxWorkItemChiTiet["ban_giao_goi_y"]; donVi: string | null; conLai: number;
  busy: boolean; onXong: () => void; exec: ThsxExec;
}) {
  const [dich, setDich] = useState<string>(goiY[0] ? String(goiY[0].cong_viec_id) : "ngoai");
  const [sl, setSl] = useState(conLai > 0 ? String(conLai) : "");
  const nSl = toNum(sl);
  const hopLe = nSl > 0;

  async function luu() {
    const body: SxBanGiaoDeXuatIn = {
      dich_cong_viec_id: dich === "ngoai" ? null : Number(dich),
      so_luong: nSl, don_vi: donVi,
    };
    if (await exec.deXuatBanGiao(body)) onXong();
  }

  return (
    <div className="thsx-x-form">
      <Field label="Giao cho chặng">
        <select className="thsx-x-sel" value={dich} onChange={(e) => setDich(e.target.value)}>
          {goiY.map((g) => (
            <option key={g.cong_viec_id} value={g.cong_viec_id}>
              {g.ten_cong_doan}{g.to_ten ? ` · ${g.to_ten}` : ""}
            </option>
          ))}
          <option value="ngoai">Giao ra ngoài (không nối chặng)</option>
        </select>
      </Field>
      <Field label={`Số lượng${donVi ? ` (${donVi})` : ""}`}>
        <input type="number" min={0} className="thsx-x-in" value={sl} onChange={(e) => setSl(e.target.value)} inputMode="numeric" />
      </Field>
      {conLai > 0 && <p className="thsx-x-hint">Còn chưa giao: <b className="thsx-num">{num(conLai)}</b>{donVi ? ` ${donVi}` : ""}</p>}
      <div className="thsx-x-act">
        <Button variant="ghost" onClick={onXong} disabled={busy}>Huỷ</Button>
        <Button variant="accent" onClick={luu} disabled={busy || !hopLe}>
          <Icon name="send" size={13} /> Đề xuất
        </Button>
      </div>
    </div>
  );
}

function BanGiaoRow({
  g, phia, canAssign, busy, loadLyDo, exec,
}: {
  g: SxBanGiao; phia: "di" | "den"; canAssign: boolean; busy: boolean;
  loadLyDo: Props["loadLyDo"]; exec: ThsxExec;
}) {
  const [suaOpen, setSuaOpen] = useState(false);
  const [dcOpen, setDcOpen] = useState(false);
  const [slSua, setSlSua] = useState(String(g.so_luong));
  const st = BG_TT[g.trang_thai] ?? { txt: g.trang_thai, cls: "thsx-x-pill--wait" };
  const daXacNhan = g.trang_thai === "confirmed" || g.trang_thai === "adjusted";
  // Nguồn (đi) sửa khi còn 'proposed'; đích (đến) xác nhận khi 'proposed'; điều chỉnh khi đã xác nhận.
  const canSua = canAssign && phia === "di" && g.trang_thai === "proposed";
  const canXac = canAssign && phia === "den" && g.trang_thai === "proposed";
  const canDc = canAssign && daXacNhan;

  return (
    <li className="thsx-x-bg">
      <div className="thsx-x-bg__main">
        <Icon name={phia === "di" ? "send" : "packageCheck"} size={13} className="thsx-x-bg__ic" />
        <span className="thsx-x-bg__to">{g.doi_tac_ten}{g.cung_to && <span className="thsx-x-tag-ht">cùng tổ</span>}</span>
        <span className="thsx-x-item__spacer" />
        <span className="thsx-x-bg__q thsx-num">{num(g.so_luong)}{g.don_vi ? ` ${g.don_vi}` : ""}</span>
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
            <Button variant="ghost" onClick={() => { setSlSua(String(g.so_luong)); setSuaOpen((o) => !o); setDcOpen(false); }} disabled={busy}>
              <Icon name="pencil" size={12} /> Sửa số
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
        <div className="thsx-x-form thsx-x-form--sub">
          <Field label={`Số lượng${g.don_vi ? ` (${g.don_vi})` : ""}`}>
            <input type="number" min={0} className="thsx-x-in" value={slSua} onChange={(e) => setSlSua(e.target.value)} inputMode="numeric" />
          </Field>
          <div className="thsx-x-act">
            <Button variant="ghost" onClick={() => setSuaOpen(false)} disabled={busy}>Huỷ</Button>
            <Button variant="accent" disabled={busy || toNum(slSua) <= 0}
              onClick={async () => { if (await exec.suaBanGiao(g.id, { so_luong: toNum(slSua), expected_version: g.version })) setSuaOpen(false); }}>
              <Icon name="check" size={13} /> Lưu
            </Button>
          </div>
        </div>
      )}
      {dcOpen && (
        <DieuChinhForm g={g} busy={busy} loadLyDo={loadLyDo}
          onHuy={() => setDcOpen(false)} onXong={() => setDcOpen(false)} exec={exec} />
      )}
    </li>
  );
}

function DieuChinhForm({
  g, busy, loadLyDo, onHuy, onXong, exec,
}: {
  g: SxBanGiao; busy: boolean; loadLyDo: Props["loadLyDo"];
  onHuy: () => void; onXong: () => void; exec: ThsxExec;
}) {
  const [slSau, setSlSau] = useState(String(g.so_luong));
  const [lyDoId, setLyDoId] = useState<number | null>(null);
  const [moTa, setMoTa] = useState("");
  const nSl = toNum(slSau);
  const hopLe = nSl > 0 && lyDoId != null;

  async function luu() {
    const body: SxBanGiaoDieuChinhIn = {
      so_luong_sau: nSl, ly_do_id: lyDoId!, mo_ta: moTa.trim() || null, expected_version: g.version,
    };
    if (await exec.dieuChinhBanGiao(g.id, body)) onXong();
  }

  return (
    <div className="thsx-x-form thsx-x-form--sub">
      <Field label={`Số lượng sau${g.don_vi ? ` (${g.don_vi})` : ""}`}>
        <input type="number" min={0} className="thsx-x-in" value={slSau} onChange={(e) => setSlSau(e.target.value)} inputMode="numeric" />
      </Field>
      <Field label="Lý do điều chỉnh">
        <LyDoSelect nhom="dieu_chinh_ban_giao" loadLyDo={loadLyDo} value={lyDoId} onChange={setLyDoId} />
      </Field>
      <Field label="Mô tả">
        <input type="text" className="thsx-x-in" value={moTa} onChange={(e) => setMoTa(e.target.value)} placeholder="Tuỳ chọn" />
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
  const [formMode, setFormMode] = useState<VtFormMode | null>(null);
  const vt = chiTiet.vat_tu;
  const cap = chiTiet.vat_tu_cap;
  const cta = ctaMode(cap);
  const cvId = chiTiet.cong_viec.id;
  const lanSua = cap.cac_de_nghi.find((d) => d.id === cap.de_nghi_co_the_sua_id) ?? null;

  // Drawer KHÔNG remount khi bấm sang việc khác (`ThsxDrawer` render không có `key`, `loadChiTiet`
  // không đặt `chiTiet = null` giữa chừng) nên khối này sống xuyên suốt: form đang mở dở của việc A
  // vẫn còn nguyên khi màn đã là việc B ⇒ bấm Gửi là B nhận vật tư của A. Đóng form khi đổi việc.
  useEffect(() => { setFormMode(null); }, [cvId]);

  return (
    <section className="thsx-psec thsx-x">
      <div className="thsx-psec__h">
        <span className="thsx-psec__title"><Icon name="warehouse" size={13} /> Vật tư</span>
        {canAssign && cta != null && formMode == null && (
          <Button variant="accent" onClick={() => setFormMode(cta)} disabled={busy}>
            <Icon name={VT_CTA[cta].icon} size={13} /> {VT_CTA[cta].txt}
          </Button>
        )}
      </div>

      {cap.du_lieu_cu && (
        <p className="thsx-note thsx-note--warn">
          <Icon name="alert" size={12} />
          Dữ liệu trước 31/08/2026 — công đoạn này chưa từng gửi đề nghị nên phiếu đang lấy theo
          lệnh sản xuất cũ, có thể thiếu hoặc lẫn phiếu của công đoạn khác cùng lệnh.
        </p>
      )}

      {cap.doi_chieu.length === 0 ? (
        <p className="thsx-note">
          Công đoạn này không có nhu cầu vật tư theo kế hoạch. Vẫn gửi đề nghị được nếu tổ cần xin thêm.
        </p>
      ) : (
        <table className="thsx-x-tbl">
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
                <td>{d.ten}</td>
                <td className="r thsx-num">{num(d.sl_ke_hoach)}<span className="thsx-x-unit"> {d.dvt}</span></td>
                <td className="r thsx-num">{num(d.sl_yeu_cau)}<span className="thsx-x-unit"> {d.dvt}</span></td>
                {/* `sl_thuc_xuat` đọc thẳng từ dòng chứng từ nên LUÔN ở thang GỐC (board.py:
                    `_vat_tu_cap`) — dán nhãn `dvt` (thang tổ khai) vào đây là in sai đơn vị. */}
                <td className="r thsx-num">{num(d.sl_thuc_xuat)}<span className="thsx-x-unit"> {d.dvt_goc}</span></td>
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
        <p className="thsx-note">Chưa gửi đề nghị nào.</p>
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
                <Icon name={v.da_nhan ? "packageCheck" : "box"} size={13}
                  className={v.da_nhan ? "thsx-x-vt__ic is-ok" : "thsx-x-vt__ic"} />
                <span className="thsx-x-vt__ma">{v.ma}</span>
                <span className="thsx-x-item__spacer" />
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
    </section>
  );
}

/** Ô "Chênh lệch": HAI độ lệch có nghĩa khác nhau nên KHÔNG gộp thành một số — xếp chồng, ẩn dòng
 *  bằng 0. MỖI số in kèm đơn vị NGAY TRONG ô: hai số này không cùng thang, và tổ trưởng đứng ngoài
 *  xưởng dùng máy bảng thì không có chuột để hover xem `title`.
 *
 *  "so KH" tính lại ở thang TỔ KHAI (`sl_yeu_cau − sl_ke_hoach`, đơn vị `dvt`) để đứng cạnh hai cột
 *  "Kế hoạch"/"Đã yêu cầu" mà trừ nhẩm được: BE tính đúng hiệu số đó nhưng ở thang GỐC, nên giấy ra
 *  "+0,07" nằm cạnh hai cột "tờ". Không đổi cách BE tính — chỉ đổi thang HIỂN THỊ, và trong một
 *  hàng thì `sl_ke_hoach`/`sl_yeu_cau` chắc chắn cùng `dvt` (`board.py::_vat_tu_cap` hạ CẢ HAI về
 *  thang gốc khi hàng lẫn đơn vị).
 *  "so YC" là số MÁY so (kho thực xuất ↔ đã yêu cầu) — giữ nguyên số BE, thang gốc, nhãn `dvt_goc`. */
function VtDeltaCell({ d, soLan }: { d: SxVatTuCapDoiChieu; soLan: number }) {
  const soKh = d.sl_yeu_cau - d.sl_ke_hoach;
  const soYc = d.lech_thuc_te;
  // Hai số, HAI ngưỡng: "so KH" là hai con số tổ tự khai cùng một thang (dung sai `VT_EPS` như BE),
  // còn "so YC" bắc qua ranh giới SX↔kho nên phải dùng `VT_EPS_KHO` × số lần đề nghị — xem chú
  // giải của hằng đó và của `vtCoLechThucTe`. Ô này và badge vàng của hàng phải dùng CÙNG một vị
  // ngữ, nếu không sẽ có hàng tô vàng mà ô "Chênh lệch" ghi "khớp".
  const lechYc = vtCoLechThucTe(d, soLan);
  if (Math.abs(soKh) <= VT_EPS && !lechYc) {
    return <span className="thsx-x-unit">khớp</span>;
  }
  return (
    <div className="thsx-x-vt-delta">
      {Math.abs(soKh) > VT_EPS && (
        <span className={`thsx-x-vt-delta__row ${soKh > 0 ? "is-up" : "is-down"}`}>
          <span className="thsx-x-vt-delta__lbl">so KH</span>
          {soKh > 0 ? "+" : ""}{num(soKh)}<span className="thsx-x-unit"> {d.dvt}</span>
        </span>
      )}
      {lechYc && (
        <span className={`thsx-x-vt-delta__row ${soYc > 0 ? "is-up" : "is-down"}`}>
          <span className="thsx-x-vt-delta__lbl">so YC</span>
          {soYc > 0 ? "+" : ""}{num(soYc)}<span className="thsx-x-unit"> {d.dvt_goc}</span>
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
                    <td className="r thsx-num">{num(x.sl_yeu_cau)}<span className="thsx-x-unit"> {x.dvt}</span></td>
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
 *  đơn vị trên màn có chữ gì không" — và màn đang hiện đúng `{d.dvt || "—"}`. Gộp vào đây là cho
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
  const hopLe = !!canLuc && canTro == null;

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

  return (
    <div className="thsx-x-form">
      <Field label="Giờ cần">
        <input type="datetime-local" className="thsx-x-in" value={canLuc}
          onChange={(e) => setCanLuc(e.target.value)} />
      </Field>

      {dongs.length === 0 && (
        <p className="thsx-x-hint">
          {loaiHieuLuc === "bo_sung"
            ? "Thêm đúng mặt hàng đang thiếu — đề nghị bổ sung là xin THÊM trên nền đã yêu cầu."
            : "Công đoạn chưa có nhu cầu vật tư theo kế hoạch — thêm mặt hàng nếu tổ cần xin."}
        </p>
      )}

      {dongs.map((d) => {
        const ly = vtCanLyDo(d, loaiHieuLuc);
        const lk = luyKe.get(`${d.hang_loai}:${d.hang_id}`);
        return (
          <div key={d.key} className="thsx-x-vtline">
            <div className="thsx-x-vtline__h">
              {d.tuKeHoach ? (
                <span className="thsx-x-item__q">{d.ten}</span>
              ) : (
                <MaterialCombobox
                  token={token ?? ""} hangTen={d.ten || null} disabled={busy}
                  onPick={(m) => {
                    // Ưu tiên đơn vị lần trước của CHÍNH mặt hàng này, chỉ rơi về đơn vị gốc khi
                    // nó chưa từng được xin (xem `vtDvtLanTruoc`). KHÔNG gác thêm theo `mode`:
                    // lần "moi" chưa có đề nghị nào nên hàm trả `null` và mọi thứ y như cũ, còn
                    // lần "sua"/"bo_sung" thì bám lần trước mới là thứ đúng — thêm điều kiện mode
                    // chỉ có thể làm dòng lật đơn vị trở lại.
                    const dv = vtDvtLanTruoc(cap.cac_de_nghi, m.hang_loai, m.hang_id)
                      ?? m.don_vi_goc ?? "";
                    sua(d.key, {
                      hang_loai: m.hang_loai, hang_id: m.hang_id, ten: m.ten,
                      dvt: dv, dvtKeHoach: dv,
                    });
                  }} />
              )}
              <span className="thsx-x-item__spacer" />
              {!d.tuKeHoach && (
                <button type="button" className="thsx-x-vtline__del" aria-label="Bỏ dòng" disabled={busy}
                  onClick={() => setDongs((ds) => ds.filter((x) => x.key !== d.key))}>
                  <Icon name="x" size={13} />
                </button>
              )}
            </div>

            {/* Giọng đi theo SỐ ĐANG XIN, không theo "có đơn vị hay không". Ở 0 thì dòng này hợp
             *  lệ — BE nhận và miễn cả luật lý do, ô Lý do ngay dưới ghi "Tuỳ chọn" — băng ĐỎ ở
             *  đó là hai câu đọc ngược nhau. Có số dương mới là chặn thật: `vtCanTro` đang tắt
             *  nút Gửi vì đúng dòng này, nên phải nói ra.
             *  Không đóng đinh nguyên nhân vào "danh mục chưa khai": ô đơn vị còn trống được vì
             *  snapshot của bước chốt trước lúc kỹ thuật khai, hoặc vì routing chưa đủ để suy ra
             *  đơn vị đếm giấy — cùng lý do câu lỗi BE đã bỏ cách nói đó. */}
            {vtThieuDonVi(d) && (d.sl_yeu_cau > VT_EPS ? (
              <div className="thsx-x-vtline__err">
                <Icon name="alert" size={12} />
                Chưa có đơn vị tính nên chưa xin được — nhờ kỹ thuật kiểm lại đơn vị, hoặc để dòng
                này ở 0 rồi gửi những món còn lại.
              </div>
            ) : (
              <div className="thsx-x-vtline__ref">
                Chưa có đơn vị tính — để ở 0 thì vẫn gửi được. Muốn xin món này thì nhờ kỹ thuật
                kiểm lại đơn vị.
              </div>
            ))}

            {d.tuKeHoach && (
              <div className="thsx-x-vtline__ref">Kế hoạch: {num(d.sl_ke_hoach)} {d.dvtKeHoach}</div>
            )}
            {loaiHieuLuc === "bo_sung" && lk && (
              <div className="thsx-x-vtline__ref">Đã yêu cầu luỹ kế: {num(lk.sl_yeu_cau)} {lk.dvt}</div>
            )}

            <div className="thsx-x-vt-qty">
              {/* Bước ±1 ĐƠN VỊ ĐANG CHỌN — không đoán bước theo loại vật tư; số lẻ thì gõ tay. */}
              <button type="button" className="thsx-x-vt-qty__btn" aria-label="Giảm" disabled={busy || d.sl_yeu_cau <= 0}
                onClick={() => datSl(d.key, d.sl_yeu_cau - 1)}>
                <Icon name="minus" size={13} />
              </button>
              <input type="number" min={0} className="thsx-x-in" inputMode="decimal"
                value={d.slText} disabled={busy} aria-label={`Số lượng xin cấp${d.ten ? ` — ${d.ten}` : ""}`}
                onChange={(e) => sua(d.key, {
                  slText: e.target.value, sl_yeu_cau: Math.max(0, toNum(e.target.value)),
                })}
                // Rời ô thì chữ trong ô phải bằng ĐÚNG số sắp gửi. Gõ "-5" là ô hiện −5 mà payload
                // gửi 0 — mà 0 có nghĩa nghiệp vụ hẳn hoi ("tổ xác nhận không cần cấp"), tức một
                // dấu trừ gõ nhầm âm thầm đưa dòng kế hoạch về 0. Cùng lý do cho "1." bỏ dở, "1,5"
                // dán kiểu Việt, hay ô xoá trắng: `<input type="number">` trả "" cho mọi giá trị
                // chưa hợp lệ, nên số thật đã là 0 rồi.
                onBlur={() => sua(d.key, { slText: String(d.sl_yeu_cau) })} />
              <button type="button" className="thsx-x-vt-qty__btn" aria-label="Tăng" disabled={busy}
                onClick={() => datSl(d.key, d.sl_yeu_cau + 1)}>
                <Icon name="plus" size={13} />
              </button>
              <span className="thsx-x-unit">{d.dvt || "—"}</span>
              {/* "Về 0" là hành động có CHỦ Ý ("tổ xác nhận không cần cấp"), không gộp vào nút giảm. */}
              <button type="button" className="thsx-x-linkbtn" disabled={busy || d.sl_yeu_cau <= 0}
                onClick={() => datSl(d.key, 0)}>Về 0</button>
            </div>

            {ly.hien && (
              <Field label={<>Lý do{ly.batBuoc && <span className="thsx-x-vt-req">*</span>}</>}>
                <input type="text" className="thsx-x-in" value={d.ly_do_chenh_lech} disabled={busy}
                  onChange={(e) => sua(d.key, { ly_do_chenh_lech: e.target.value })}
                  placeholder={ly.batBuoc ? "Bắt buộc — vì sao khác kế hoạch" : "Tuỳ chọn"} />
              </Field>
            )}
          </div>
        );
      })}

      <div className="thsx-x-act thsx-x-act--row">
        <Button variant="ghost" onClick={themDong} disabled={busy}>
          <Icon name="plus" size={13} /> Thêm mặt hàng
        </Button>
      </div>

      {canTro && (
        <p className="thsx-note thsx-note--warn">
          <Icon name="alert" size={12} /> {canTro}
        </p>
      )}

      <div className="thsx-x-act">
        <Button variant="ghost" onClick={onHuy} disabled={busy}>Huỷ</Button>
        <Button variant="accent" onClick={luu} disabled={busy || !hopLe}>
          <Icon name={mode === "sua" ? "check" : "send"} size={13} />
          {mode === "sua" ? " Lưu thay đổi" : " Gửi đề nghị"}
        </Button>
      </div>
    </div>
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
          <Button variant="ghost" onClick={() => setFormOpen((o) => !o)} disabled={busy} aria-expanded={formOpen}>
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
            <HoTroRow key={h.id} h={h} canAssign={canAssign} busy={busy} exec={exec} />
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
  const [empId, setEmpId] = useState<number | null>(null);
  const [ngayLv, setNgayLv] = useState(todayYmd());
  const [tyLe, setTyLe] = useState("");
  const [moTa, setMoTa] = useState("");
  const nTyLe = toNum(tyLe);
  const hopLe = empId != null && !!ngayLv && nTyLe > 0 && nTyLe <= 100;

  async function luu() {
    const body: SxHoTroDeXuatIn = {
      employee_id: empId!, ngay_lam_viec: ngayLv, ty_le_phan_tram: nTyLe,
      mo_ta: moTa.trim() || null,
    };
    if (await exec.deXuatHoTro(body)) onXong();
  }

  return (
    <div className="thsx-x-form">
      <Field label="Thợ hỗ trợ (từ tổ khác)">
        <select className="thsx-x-sel" value={empId ?? ""} onChange={(e) => setEmpId(e.target.value ? Number(e.target.value) : null)}>
          <option value="">— Chọn thợ —</option>
          {hoTroUngVien.map((h) => (
            <option key={h.id} value={h.id}>{h.full_name}{h.to_ten ? ` · ${h.to_ten}` : ""}</option>
          ))}
        </select>
      </Field>
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
      <div className="thsx-x-act">
        <Button variant="ghost" onClick={onXong} disabled={busy}>Huỷ</Button>
        <Button variant="accent" onClick={luu} disabled={busy || !hopLe}>
          <Icon name="check" size={13} /> Đề xuất
        </Button>
      </div>
    </div>
  );
}

function HoTroRow({
  h, canAssign, busy, exec,
}: {
  h: SxHoTro; canAssign: boolean; busy: boolean; exec: ThsxExec;
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
      {canAssign && h.trang_thai !== "cancelled" && (
        <div className="thsx-x-act thsx-x-act--row">
          {chuaChot && (
            <Button variant="accent" onClick={() => void exec.xacNhanHoTro(h.id, h.version)} disabled={busy}>
              <Icon name="check" size={13} /> Xác nhận
            </Button>
          )}
          <Button variant="ghost" onClick={() => setHuyOpen((o) => !o)} disabled={busy}>
            <Icon name="ban" size={12} /> Huỷ
          </Button>
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
export function Field({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <label className="thsx-x-fld">
      <span className="thsx-x-fld__l">{label}</span>
      {children}
    </label>
  );
}

/** Dropdown lý do/lỗi nạp theo NHÓM từ danh mục `san_xuat_ly_do` (§15). */
export function LyDoSelect({
  nhom, loadLyDo, value, onChange,
}: {
  nhom: string; loadLyDo: Props["loadLyDo"];
  value: number | null; onChange: (v: number | null) => void;
}) {
  const [opts, setOpts] = useState<SxLyDo[] | null>(null);
  useEffect(() => {
    let alive = true;
    void loadLyDo(nhom).then((r) => { if (alive) setOpts(r); });
    return () => { alive = false; };
  }, [nhom, loadLyDo]);
  return (
    <select className="thsx-x-sel" value={value ?? ""}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}>
      <option value="">{opts == null ? "Đang tải…" : "— Chọn —"}</option>
      {(opts ?? []).map((o) => <option key={o.id} value={o.id}>{o.ten}</option>)}
    </select>
  );
}

/** Form 1-dropdown-lý-do dùng cho "mở lại phân bổ" (và các chỗ chỉ cần chọn lý do). */
function LyDoForm({
  nhom, busy, loadLyDo, label, confirm, onHuy, onXac,
}: {
  nhom: string; busy: boolean; loadLyDo: Props["loadLyDo"];
  label: string; confirm: string; onHuy: () => void; onXac: (lyDoId: number) => void;
}) {
  const [lyDoId, setLyDoId] = useState<number | null>(null);
  return (
    <div className="thsx-x-form thsx-x-form--sub">
      <Field label={label}>
        <LyDoSelect nhom={nhom} loadLyDo={loadLyDo} value={lyDoId} onChange={setLyDoId} />
      </Field>
      <div className="thsx-x-act">
        <Button variant="ghost" onClick={onHuy} disabled={busy}>Huỷ</Button>
        <Button variant="accent" onClick={() => lyDoId != null && onXac(lyDoId)} disabled={busy || lyDoId == null}>
          <Icon name="check" size={13} /> {confirm}
        </Button>
      </div>
    </div>
  );
}
