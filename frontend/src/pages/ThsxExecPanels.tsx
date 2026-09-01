// PHA SAU của DRAWER Thực hiện sản xuất — Giai đoạn 3 (sản lượng · bàn giao · vật tư) + Giai đoạn 4
// (hỗ trợ chéo · phân bổ sản lượng → lương khoán). Gộp thẳng vào drawer `ThsxDrawer` (KHÔNG đẻ màn
// mới): mỗi mặt là một khối gấp/mở với form ghi tại chỗ (panel hẹp, tránh modal chồng).
//
// Component KHÔNG tự gọi API: mọi mặt GHI đi qua `exec.*` (controller lo khoá lạc quan + refetch +
// toast). Lý do/lỗi (§15) nạp từ danh mục `san_xuat_ly_do` qua `loadLyDo(nhom)` — KHÔNG hardcode.
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import type {
  SxWorkItemChiTiet, SxBatch, SxBanGiao, SxPhanBo, SxHoTro, SxHoTroUngVien, SxLyDo,
  SxBatchIn, SxBanGiaoDeXuatIn, SxBanGiaoSuaIn, SxBanGiaoDieuChinhIn,
  SxHoTroDeXuatIn, SxBuTruIn, SxLoaiTruIn, SxGoLoaiTruIn,
  SxKcsBatchIn, SxNhapKhoYeuCauIn, SxHuyPhanChuaNhanIn, SxPhanLoaiBtpIn, SxDongThieuIn,
  SxKetQuaNhanh, SxSuCoIn,
} from "../api/client";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import { num, ngayGio, ngay } from "./keHoachSxShared";

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
      <VatTuSection chiTiet={chiTiet} canAssign={canAssign} busy={busy} exec={exec} />
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

// ─────────────────────────── VẬT TƯ (nhận về tổ) ──────────────────────────
function VatTuSection({
  chiTiet, canAssign, busy, exec,
}: {
  chiTiet: SxWorkItemChiTiet; canAssign: boolean; busy: boolean; exec: ThsxExec;
}) {
  const vt = chiTiet.vat_tu;
  if (vt.length === 0) return null;
  return (
    <section className="thsx-psec thsx-x">
      <div className="thsx-psec__h">
        <span className="thsx-psec__title"><Icon name="warehouse" size={13} /> Vật tư nhận</span>
      </div>
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
    </section>
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
export function Field({ label, children }: { label: string; children: ReactNode }) {
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
