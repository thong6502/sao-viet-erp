// KCS theo LỆNH (mg 0306, docs/design-kcs-theo-lenh.md) — ngăn kéo "Kiểm công đoạn".
//
// MỘT thao tác duy nhất: KCS đã mở lệnh, bấm một công đoạn trong chuỗi → tick checklist, ghi Số lỗi.
// Có lỗi thì bắt mô tả + ít nhất một ảnh. Tổ chịu lỗi = tổ của công đoạn, người kiểm = tài khoản đang
// đăng nhập — cả hai do máy chủ chốt, form KHÔNG có ô chọn. Ghi xong không trừ số, không đổi trạng
// thái công việc; kiểm lại bao nhiêu lần cũng được.
//
// Chỉ gõ SỐ LỖI (18/09/2026): mỗi lần kiểm bao trọn phần tổ đã làm mà chưa kiểm, số đạt = phần đó −
// số lỗi — máy chủ tự tính, form chỉ bày ra cho KCS thấy trước.
//
// Bối cảnh đầy đủ (19/09/2026): KCS đứng ở chồng hàng cần biết đang kiểm CÁI GÌ mà không phải mở màn
// khác — đầu lệnh + tổ/máy, dải số kế hoạch → tổ làm → đã kiểm → chưa kiểm, các MẺ tổ đã ghi (mẻ nào
// chưa kiểm), thẻ quy cách chạy máy (cùng thẻ với ngăn bàn tổ) để đối chiếu, và các lần kiểm trước.
// Mẻ "chưa kiểm" suy ra ở đây: mỗi lần kiểm bao trọn phần chưa kiểm lúc đó, nên phần chưa kiểm luôn
// là các mẻ MỚI NHẤT — đi từ mẻ mới nhất trừ dần `chuaKiem`.
//
// Lỗi theo DÒNG (19/09/2026): mỗi dòng số lượng + mô tả + ảnh + "Lỗi do công đoạn" — mặc định chính
// công đoạn đang kiểm, chọn được công đoạn đứng TRƯỚC trong chuỗi của lệnh (lem mực bắt lúc đóng gói
// là lỗi của In). Số lượng vẫn đếm bằng đơn vị công đoạn đang kiểm (hàng hỏng ở đây); lỗi báo về tổ
// của công đoạn chịu để họ xem và tính trách nhiệm, số của công đoạn đó không đổi. Một lần kiểm chia
// được lỗi cho nhiều công đoạn — tách thành hai lần kiểm thì lần sau không còn hàng, vì lần đầu đã bao
// trọn phần chưa kiểm.
//
// Công đoạn GIỮA chỉ GHI LỖI (19/09/2026 — chỉ KCS cuối mới kiểm đạt để nhập kho): không tiêu chí,
// không "chờ kiểm"/số đạt, không dải tiến độ; trần Σ lỗi ≤ số tốt tổ đã ghi, ghi lúc nào thấy lỗi.
// Công đoạn cuối (`la_kcs_cuoi`) giữ nguyên lần kiểm đầy đủ ở trên.
//
// Ảnh lỗi là DANH SÁCH cộng dồn: KCS đứng ở chồng hàng chụp từng tấm một (nút "Chụp ảnh" mở thẳng
// camera điện thoại) hoặc chọn nhiều tấm có sẵn; mỗi lần thêm là nối vào, không đè. Ảnh nằm chờ trong
// form (URL `blob:`), bấm Lưu mới gửi cùng lần kiểm — lần kiểm chưa có thì chưa có chỗ gắn ảnh.
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  ApiError, api,
  type SxKcsChecklistKetQuaIn, type SxKcsCongDoan, type SxKcsKiemKetQua, type SxKcsLenhDau,
  type SxKcsMe,
} from "../../api/client";
import { useAuth } from "../../auth/useAuth";
import { XemTruoc } from "../../components/DinhKemTep";
import { Icon } from "../../components/Icons";
import type { TepXem } from "../../components/tepDinhKem";
import { coChu, nenAnh } from "../../lib/anhNen";
import { Drawer } from "../danh-muc/components/Drawer";
import { gioNgan, ngay, num } from "../keHoachSxShared";
import { nhanChang } from "../lsxBuoc";
import { useNapTenDonVi } from "../tenDonVi";
import { DongTep } from "../ThsxDongTep";
import { ThsxQuyCachThe } from "../ThsxQuyCach";
import { KcsLanKiemList } from "./KcsLanKiemList";
import { KCS_CD_TRANG_THAI } from "./kcsNhan";
import "../thuc-hien-sx.css";
import "./kcs-kiem-form.css";

/** Một ảnh đang chờ gửi: file (đã nén nếu lợi) + URL xem ngay + cỡ gốc để nói đã nén bao nhiêu. */
interface AnhCho {
  id: number;
  file: File;
  url: string;
  goc: number;
}

/** Một dòng lỗi đang soạn. `cvId` = công đoạn chịu lỗi. */
interface DongLoi {
  key: number;
  cvId: number;
  so: string;
  moTa: string;
  anh: AnhCho[];
}

/** Mẻ kèm phần CHƯA KIỂM của nó (xem đầu tệp). */
interface MeKiem extends SxKcsMe {
  chua: number;
  tt: "chua" | "mot_phan" | "da";
}

const ME_HIEN = 5;
const LAN_KIEM_HIEN = 3;
const EPS = 1e-9;

/** Gắn phần chưa kiểm cho từng mẻ — `me` đã xếp mới nhất trước. */
function meChuaKiem(me: SxKcsMe[], chuaKiem: number): MeKiem[] {
  let con = chuaKiem;
  return me.map((m) => {
    const chua = Math.max(0, Math.min(con, m.so_luong));
    con -= chua;
    const tt = chua <= EPS ? "da" : chua >= m.so_luong - EPS ? "chua" : "mot_phan";
    return { ...m, chua, tt };
  });
}

function khoangGio(m: SxKcsMe): string {
  const kt = gioNgan(m.ket_thuc);
  return m.bat_dau ? `${gioNgan(m.bat_dau)}–${kt}` : kt;
}

function chuaKiemCua(c: SxKcsCongDoan): number {
  return Math.max(0, c.tot - c.tong_dat - c.tong_loi);
}

function tenCongDoan(c: SxKcsCongDoan): string {
  return c.phan_doan_tong > 1 ? `${c.ten} (${c.phan_doan_so}/${c.phan_doan_tong})` : c.ten;
}

export function KcsKiemForm({
  lenh, cd, chuoi = [], onClose, onSaved,
}: {
  lenh: SxKcsLenhDau;
  cd: SxKcsCongDoan;
  /** Cả chuỗi công đoạn của lệnh theo thứ tự routing — nguồn ô "Lỗi do công đoạn". */
  chuoi?: SxKcsCongDoan[];
  onClose: () => void;
  onSaved: (r: SxKcsKiemKetQua) => void;
}) {
  const { token } = useAuth();
  // `don_vi` của công đoạn/mẻ là mã CHẶNG dòng giấy (`to` = tờ in) — màn KCS không tự nạp bảng nhãn.
  useNapTenDonVi();
  // Tiêu chí là ô tick: tick = đạt, để trống = không đạt.
  const [dat, setDat] = useState<Record<number, boolean>>({});
  const [ghiChuTc, setGhiChuTc] = useState<Record<number, string>>({});
  const [dongLoi, setDongLoi] = useState<DongLoi[]>(() => [
    { key: 1, cvId: cd.cong_viec_id, so: "", moTa: "", anh: [] },
  ]);
  const [dangNen, setDangNen] = useState(0);
  const [xem, setXem] = useState<TepXem | null>(null);
  const [ghiChu, setGhiChu] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [moHetMe, setMoHetMe] = useState(false);
  const [moHetLk, setMoHetLk] = useState(false);
  // Thông báo chặn nằm cuối thân ngăn — cuộn tới nó, không thì người bấm "Lưu" không thấy gì xảy ra.
  const errorRef = useRef<HTMLDivElement>(null);
  useEffect(() => { if (error) errorRef.current?.scrollIntoView({ block: "nearest" }); }, [error]);

  const chupRef = useRef<HTMLInputElement>(null);
  const chonRef = useRef<HTMLInputElement>(null);
  const idAnh = useRef(0);
  const idDong = useRef(1);
  // Dòng lỗi đang thêm ảnh — hai ô chọn tệp ẩn dùng chung cho mọi dòng.
  const dongAnh = useRef(1);
  // URL `blob:` không tự mất khi ngăn đóng — dọn tay; ref để bản dọn lúc unmount thấy danh sách mới nhất.
  const anhRef = useRef<AnhCho[]>([]);
  useEffect(() => { anhRef.current = dongLoi.flatMap((d) => d.anh); }, [dongLoi]);
  useEffect(() => () => { for (const a of anhRef.current) URL.revokeObjectURL(a.url); }, []);

  function suaDong(key: number, sua: (d: DongLoi) => DongLoi) {
    setDongLoi((ds) => ds.map((d) => (d.key === key ? sua(d) : d)));
    setError(null);
  }

  function moChonAnh(key: number, o: HTMLInputElement | null) {
    dongAnh.current = key;
    o?.click();
  }

  async function themAnh(input: HTMLInputElement) {
    const key = dongAnh.current;
    const ds = Array.from(input.files ?? []);
    // Xoá giá trị ô chọn: không thì chọn lại đúng tấm vừa bỏ, trình duyệt không bắn `change`.
    input.value = "";
    setError(null);
    for (const f of ds) {
      if (!f.type.startsWith("image/")) {
        setError(`"${f.name}" không phải ảnh.`);
        continue;
      }
      // Ảnh điện thoại 4–8 MB/tấm: nén ngay khi thêm để lúc Lưu không phải đẩy vài chục MB qua wifi xưởng.
      setDangNen((n) => n + 1);
      const kq = await nenAnh(f);
      setDangNen((n) => n - 1);
      const moi = { id: ++idAnh.current, file: kq.file, url: URL.createObjectURL(kq.file), goc: kq.goc };
      setDongLoi((ds) => ds.map((d) => (d.key === key ? { ...d, anh: [...d.anh, moi] } : d)));
    }
  }

  function boAnh(key: number, id: number) {
    const bo = dongLoi.find((d) => d.key === key)?.anh.find((a) => a.id === id);
    if (bo) URL.revokeObjectURL(bo.url);
    suaDong(key, (d) => ({ ...d, anh: d.anh.filter((a) => a.id !== id) }));
  }

  function themDong() {
    // Dòng thêm thường là lỗi của công đoạn KHÁC — gợi sẵn công đoạn ngay trước công đoạn đang kiểm.
    const goiY = nguonLoi.length > 1 ? nguonLoi[nguonLoi.length - 2].cong_viec_id : cd.cong_viec_id;
    setDongLoi((ds) => [...ds, { key: ++idDong.current, cvId: goiY, so: "", moTa: "", anh: [] }]);
    setError(null);
  }

  function boDong(key: number) {
    for (const a of dongLoi.find((d) => d.key === key)?.anh ?? []) URL.revokeObjectURL(a.url);
    setDongLoi((ds) => ds.filter((d) => d.key !== key));
    setError(null);
  }

  // Thông báo chặn là của lần bấm Lưu trước — người đã sửa ô thì nó hết đúng, đừng để treo.
  function doiTieuChi(thuTu: number, v: boolean) {
    setDat((d) => ({ ...d, [thuTu]: v }));
    setError(null);
  }

  const nSoLoi = dongLoi.reduce((s, d) => s + (Number(d.so) > 0 ? Number(d.so) : 0), 0);
  const dv = nhanChang(cd.don_vi);
  const cuoi = cd.la_kcs_cuoi;
  // Công đoạn giữa: còn ghi được bao nhiêu lỗi nữa (máy chủ chặn cùng trần).
  const conGhiLoi = Math.max(0, cd.tot - cd.tong_loi);
  const moGhi = cuoi ? chuaKiemCua(cd) > 0 : conGhiLoi > 0;
  // Công đoạn nhận được lỗi: từ đầu chuỗi tới chính công đoạn đang kiểm (máy chủ kiểm lại y hệt).
  const viTri = chuoi.findIndex((c) => c.cong_viec_id === cd.cong_viec_id);
  const nguonLoi = viTri >= 0 ? chuoi.slice(0, viTri + 1) : [cd];
  const congDoanCua = (id: number) => nguonLoi.find((c) => c.cong_viec_id === id) ?? cd;
  // Phần tổ đã làm mà chưa kiểm — lần kiểm này bao trọn phần đó (máy chủ tính lại cùng công thức).
  const chuaKiem = chuaKiemCua(cd);
  const datLanNay = Math.max(0, chuaKiem - nSoLoi);
  // Tiêu chí bắt buộc không đạt nghĩa là có hàng lỗi — để trống mà Số lỗi = 0 là quên tick.
  const batBuocChuaDat = cd.checklist.find((tc) => tc.bat_buoc && !dat[tc.thu_tu]);
  const keHoach = cd.so_luong_ra ?? null;
  const me = useMemo(() => meChuaKiem(cd.me ?? [], chuaKiem), [cd.me, chuaKiem]);
  const soMeChua = me.filter((m) => m.tt !== "da").length;
  // Công đoạn giữa chỉ bày lần có lỗi — lọc TRƯỚC khi cắt trang, không thì lần có lỗi bị gấp mất.
  const lanKiem = (cd.lan_kiem ?? []).filter((lk) => cd.la_kcs_cuoi || lk.loi.length > 0);
  const soLanHien = lanKiem.length;

  // Dải tiến độ: đạt · lỗi · chưa kiểm · chưa làm (so kế hoạch). Chia theo TỔNG các đoạn chứ không
  // theo kế hoạch — dữ liệu cũ kiểm lố (đạt + lỗi > tổ làm) hay tổ làm vượt kế hoạch vẫn vẽ đủ.
  const chuaLam = keHoach != null ? Math.max(0, keHoach - cd.tot) : 0;
  const doan = [
    { k: "dat", nhan: "Đạt", so: cd.tong_dat },
    { k: "loi", nhan: "Lỗi", so: cd.tong_loi },
    { k: "chua", nhan: "Chưa kiểm", so: chuaKiem },
    { k: "chualam", nhan: "Chưa làm", so: chuaLam },
  ];
  const tongDoan = doan.reduce((s, d) => s + d.so, 0);
  const pctLam = keHoach && keHoach > 0 ? Math.round((cd.tot / keHoach) * 100) : null;

  function kiemTra(): string | null {
    // Một dòng thì nói như cũ; nhiều dòng thì chỉ rõ dòng nào.
    const truoc = (i: number, cau: string) =>
      dongLoi.length > 1 ? `Dòng lỗi ${i + 1}: ${cau.charAt(0).toLowerCase()}${cau.slice(1)}` : cau;
    for (const [i, d] of dongLoi.entries()) {
      if (d.so.trim() !== "" && (!Number.isFinite(Number(d.so)) || Number(d.so) < 0)) return truoc(i, "Số lỗi không hợp lệ.");
    }
    if (!cuoi) {
      if (cd.tot <= 0) return "Tổ chưa ghi sản lượng nào — chưa có hàng để ghi lỗi.";
      if (nSoLoi <= 0) return "Nhập số lỗi.";
      if (nSoLoi > conGhiLoi) return `Tổng lỗi vượt số tốt tổ đã ghi (còn ghi được ${num(conGhiLoi)} ${dv}).`;
    }
    if (cuoi && chuaKiem <= 0) return "Tổ chưa ghi thêm sản lượng nào từ lần kiểm trước — chưa có gì để kiểm.";
    if (cuoi && nSoLoi > chuaKiem) return `Số lỗi vượt phần tổ đã làm mà chưa kiểm (${num(chuaKiem)} ${dv}).`;
    if (cuoi && batBuocChuaDat && nSoLoi === 0) {
      return `Tiêu chí bắt buộc "${batBuocChuaDat.ten ?? batBuocChuaDat.ma ?? `#${batBuocChuaDat.thu_tu}`}" chưa tick đạt — đạt thì tick, không đạt thì ghi Số lỗi.`;
    }
    for (const [i, d] of dongLoi.entries()) {
      if (!(Number(d.so) > 0)) continue;
      if (!d.moTa.trim()) return truoc(i, "Có lỗi thì phải mô tả lỗi.");
      if (d.anh.length === 0) return truoc(i, "Có lỗi thì phải kèm ít nhất một ảnh.");
    }
    return null;
  }

  async function luu() {
    if (!token || saving || dangNen > 0) return;
    const loi = kiemTra();
    if (loi) { setError(loi); return; }
    setSaving(true);
    setError(null);
    const checklist: SxKcsChecklistKetQuaIn[] = !cuoi ? [] : cd.checklist.map((tc) => ({
      thu_tu: tc.thu_tu,
      dat: dat[tc.thu_tu] === true,
      ghi_chu: ghiChuTc[tc.thu_tu]?.trim() || null,
    }));
    try {
      const r = await api.sanXuat.kiemCongDoan(token, cd.cong_viec_id, {
        so_loi: nSoLoi,
        checklist,
        ghi_chu: ghiChu.trim() || null,
        lsx_id: lenh.id,
        loi: dongLoi.filter((d) => Number(d.so) > 0).map((d) => ({
          cong_viec_id: d.cvId === cd.cong_viec_id ? null : d.cvId,
          so_luong: Number(d.so),
          mo_ta: d.moTa.trim(),
          files: d.anh.map((a) => a.file),
        })),
      });
      onSaved(r);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Không lưu được kết quả kiểm.");
      setSaving(false);
    }
  }

  const tenCd = tenCongDoan(cd);
  const meHien = moHetMe ? me : me.slice(0, ME_HIEN);
  const lkHien = moHetLk ? lanKiem : lanKiem.slice(0, LAN_KIEM_HIEN);
  const soTcDat = cd.checklist.filter((tc) => dat[tc.thu_tu]).length;
  const tatCaDat = cd.checklist.length > 0 && soTcDat === cd.checklist.length;

  return (
    <Drawer
      kicker={cuoi ? "Kiểm công đoạn" : "Ghi lỗi công đoạn"}
      title={tenCd}
      onClose={onClose}
      foot={(
        <>
          <button type="button" className="btn btn--ghost" onClick={onClose} disabled={saving}>Huỷ</button>
          <button type="button" className="btn btn--accent" onClick={luu}
            disabled={saving || dangNen > 0 || !moGhi}>
            {saving ? "Đang lưu…" : dangNen > 0 ? "Đang xử lý ảnh…" : cuoi ? "Lưu kết quả kiểm" : "Lưu lỗi"}
          </button>
        </>
      )}
    >
      <div className="rc-drawer__body kkf">
        {/* 1 · ĐẦU LỆNH — lệnh nào, của ai, tổ nào làm trên máy nào. */}
        <section className="kkf-dau">
          <div className="kkf-dau__lenh">
            <span className="kkf-dau__ma">{lenh.ma}</span>
            {lenh.ten && <span className="kkf-dau__ten">{lenh.ten}</span>}
          </div>
          {lenh.khach && <div className="kkf-dau__khach">Khách hàng: <b>{lenh.khach}</b></div>}
          <div className="kkf-chips">
            <span className="kkf-chip" title="Tổ làm công đoạn — lỗi báo về tổ này">
              <Icon name="users" size={12} /> {cd.to_ten || "Chưa có tổ"}
            </span>
            <span className={`kkf-chip kkf-chip--tt kkf-chip--${cd.trang_thai}`}>
              {KCS_CD_TRANG_THAI[cd.trang_thai] ?? cd.trang_thai}
            </span>
            {cd.may && (
              <span className="kkf-chip" title="Máy chạy công đoạn">
                <Icon name="cpu" size={12} /> {cd.may}
              </span>
            )}
            {cd.la_kcs_cuoi && (
              <span className="kkf-chip kkf-chip--cuoi" title="Số đạt ở công đoạn này được đề nghị nhập kho">
                <Icon name="packageCheck" size={12} /> Công đoạn cuối · đạt thì nhập kho
              </span>
            )}
          </div>
        </section>

        {/* 2 · DẢI SỐ — kế hoạch → tổ làm → KCS đã kiểm → còn chờ kiểm. */}
        <section className="thsx-card kkf-the">
          <div className="thsx-psec__h">
            <Icon name="activity" size={14} />
            <span className="thsx-psec__title">{cuoi ? <>Sản lượng &amp; kiểm</> : "Sản lượng"}</span>
            {pctLam != null && <span className="kkf-h__phu">Tổ làm {pctLam}% kế hoạch</span>}
          </div>
          <div className="kkf-so">
            <div className="kkf-so__o">
              <span className="kkf-so__nhan">Kế hoạch</span>
              <span className="kkf-so__so">{num(keHoach)}<small>{keHoach != null ? dv : ""}</small></span>
            </div>
            <div className="kkf-so__o">
              <span className="kkf-so__nhan">Tổ đã làm</span>
              <span className="kkf-so__so">{num(cd.tot)}<small>{dv}</small></span>
              <span className="kkf-so__phu">{me.length} mẻ</span>
            </div>
            {!cuoi && (
              <div className="kkf-so__o">
                <span className="kkf-so__nhan">Lỗi đã ghi</span>
                <span className="kkf-so__so">{num(cd.tong_loi)}<small>{dv}</small></span>
                <span className="kkf-so__phu">{cd.so_lan_kiem > 0 ? `${cd.so_lan_kiem} lần ghi` : "chưa ghi lỗi"}</span>
              </div>
            )}
            {cuoi && <div className="kkf-so__o">
              <span className="kkf-so__nhan">KCS đã kiểm</span>
              <span className="kkf-so__so">{num(cd.tong_dat + cd.tong_loi)}<small>{dv}</small></span>
              <span className="kkf-so__phu">
                {cd.so_lan_kiem > 0
                  ? <>đạt <b className="is-dat">{num(cd.tong_dat)}</b> · lỗi <b className="is-loi">{num(cd.tong_loi)}</b></>
                  : "chưa kiểm lần nào"}
              </span>
            </div>}
            {cuoi && <div className={`kkf-so__o kkf-so__o--chua${chuaKiem > 0 ? " is-co" : ""}`}>
              <span className="kkf-so__nhan">Chờ kiểm</span>
              <span className="kkf-so__so">{num(chuaKiem)}<small>{dv}</small></span>
              <span className="kkf-so__phu">{chuaKiem > 0 ? `${soMeChua} mẻ mới nhất` : "đã kiểm hết"}</span>
            </div>}
          </div>
          {cuoi && tongDoan > 0 && (
            <>
              <div className="kkf-bar" role="img"
                aria-label={doan.filter((d) => d.so > 0).map((d) => `${d.nhan} ${num(d.so)}`).join(", ")}>
                {doan.filter((d) => d.so > 0).map((d) => (
                  <span key={d.k} className={`kkf-bar__doan kkf-bar__doan--${d.k}`}
                    style={{ flexGrow: d.so }} title={`${d.nhan}: ${num(d.so)} ${dv}`} />
                ))}
              </div>
              <div className="kkf-chu-giai">
                {doan.filter((d) => d.so > 0).map((d) => (
                  <span key={d.k} className="kkf-chu-giai__it">
                    <i className={`kkf-bar__cham kkf-bar__doan--${d.k}`} />{d.nhan} <b>{num(d.so)}</b>
                  </span>
                ))}
              </div>
            </>
          )}
        </section>

        {/* 3 · MẺ TỔ ĐÃ GHI — mới nhất trước; mẻ nào còn chờ kiểm thì tô nổi. */}
        <section className="thsx-card kkf-the">
          <div className="thsx-psec__h">
            <Icon name="history" size={14} />
            <span className="thsx-psec__title">Mẻ tổ đã ghi</span>
            {me.length > 0 && <span className="kkf-h__phu">{me.length} mẻ · mới nhất trước</span>}
          </div>
          {me.length === 0 ? (
            <p className="kkf-trong">Tổ chưa ghi mẻ nào.</p>
          ) : (
            <ul className="kkf-me">
              {meHien.map((m) => {
                const dvMe = nhanChang(m.don_vi ?? cd.don_vi);
                return (
                  <li key={m.id} className={`kkf-me__it${cuoi ? ` kkf-me__it--${m.tt}` : ""}`}>
                    <div className="kkf-me__gio">
                      <b>{khoangGio(m)}</b>
                      <span>{ngay(m.ket_thuc ?? m.bat_dau)}</span>
                    </div>
                    <div className="kkf-me__giua">
                      <span className="kkf-me__viec">{m.viec || `Mẻ #${m.id}`}</span>
                      <span className="kkf-me__nguoi">
                        {m.nguoi.length > 0 ? m.nguoi.join(", ") : "Chưa ghi người làm"}
                        {m.nguoi_ghi && <span className="kkf-me__ghi"> · ghi: {m.nguoi_ghi}</span>}
                      </span>
                    </div>
                    <div className="kkf-me__phai">
                      <span className="kkf-me__sl">{num(m.so_luong)}<small>{dvMe}</small></span>
                      {cuoi && (
                        <span className={`kkf-me__tt kkf-me__tt--${m.tt}`}>
                          {m.tt === "da" ? "Đã kiểm" : m.tt === "chua" ? "Chờ kiểm" : `Còn ${num(m.chua)} chờ kiểm`}
                        </span>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
          {me.length > ME_HIEN && (
            <button type="button" className="kkf-them" onClick={() => setMoHetMe((v) => !v)}>
              {moHetMe ? "Thu gọn" : `Xem thêm ${me.length - ME_HIEN} mẻ cũ hơn`}
            </button>
          )}
        </section>

        {/* 4 · ĐỐI CHIẾU — dặn dò của kế hoạch + quy cách chạy máy (cùng thẻ với ngăn bàn tổ). */}
        {cd.ghi_chu_ky_thuat?.trim() && (
          <section className="thsx-card kkf-the kkf-dando">
            <div className="thsx-psec__h">
              <Icon name="alert" size={14} />
              <span className="thsx-psec__title">Dặn dò kỹ thuật</span>
            </div>
            <p className="thsx-dando">{cd.ghi_chu_ky_thuat}</p>
          </section>
        )}
        {cd.quy_cach && <ThsxQuyCachThe qc={cd.quy_cach} />}

        {/* 5 · KẾT QUẢ LẦN KIỂM NÀY — phần duy nhất KCS gõ. */}
        <section className="kkf-ghi">
          <div className="kkf-ghi__h">
            <Icon name="shield" size={15} />
            <span>{cuoi ? "Kết quả lần kiểm này" : "Ghi lỗi"}</span>
          </div>
          {!cuoi && (
            <p className="kcs-drawer__anh-hint">
              Công đoạn giữa: chỉ ghi khi thấy lỗi, không cần kiểm đạt — đạt chỉ kiểm ở công đoạn cuối để nhập kho.
            </p>
          )}

          {cuoi && cd.checklist.length > 0 && (
            <div className="kkf-ghi__khoi">
              <div className="kkf-ghi__nhan">
                Tiêu chí kiểm <span className="kkf-h__phu">{soTcDat}/{cd.checklist.length} đạt · để trống là không đạt</span>
                <button type="button" className="kkf-them kkf-them--phai"
                  onClick={() => {
                    setDat(Object.fromEntries(cd.checklist.map((tc) => [tc.thu_tu, !tatCaDat])));
                    setError(null);
                  }}>
                  {tatCaDat ? "Bỏ tick hết" : "Tất cả đạt"}
                </button>
              </div>
              <ul className="kkf-tc">
                {cd.checklist.map((tc) => {
                  const ten = tc.ten ?? tc.ma ?? `Tiêu chí #${tc.thu_tu}`;
                  const v = !!dat[tc.thu_tu];
                  return (
                    <li key={tc.thu_tu} className={`kkf-tc__it${v ? " is-dat" : ""}`}>
                      <label className="kkf-tc__chon">
                        <input type="checkbox" className="kkf-tc__o" checked={v}
                          onChange={(e) => doiTieuChi(tc.thu_tu, e.target.checked)} />
                        <span className="kkf-tc__ten">
                          {ten}
                          {tc.bat_buoc && <span className="kcs-check-row__req" title="Bắt buộc"> *</span>}
                        </span>
                      </label>
                      <input
                        type="text" className="kcs-check-row__note kkf-tc__gc" placeholder="Ghi chú (nếu có)"
                        aria-label={`Ghi chú ${ten}`}
                        value={ghiChuTc[tc.thu_tu] ?? ""}
                        onChange={(e) => setGhiChuTc((g) => ({ ...g, [tc.thu_tu]: e.target.value }))}
                      />
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          <div className="kkf-ghi__khoi">
            <div className="kkf-ghi__nhan">Số lỗi ({dv || "đơn vị công đoạn"})</div>
            {moGhi ? (
              <>
                {dongLoi.map((d, i) => {
                  const chiu = congDoanCua(d.cvId);
                  const khac = chiu.cong_viec_id !== cd.cong_viec_id;
                  const nhanSo = i === 0 ? "Số lỗi" : `Số lỗi dòng ${i + 1}`;
                  return (
                    <div key={d.key} className={`kkf-dl${dongLoi.length > 1 ? " kkf-dl--nhieu" : ""}`}>
                      <div className="kkf-loi">
                        <input type="number" min={0} inputMode="decimal" value={d.so} placeholder="0"
                          className="kkf-loi__o" aria-label={nhanSo}
                          onChange={(e) => suaDong(d.key, (x) => ({ ...x, so: e.target.value }))} />
                        {nguonLoi.length > 1 && (
                          <label className="kkf-dl__nguon">
                            <span>Lỗi do công đoạn</span>
                            <select value={d.cvId} aria-label={i === 0 ? "Lỗi do công đoạn" : `Lỗi do công đoạn dòng ${i + 1}`}
                              onChange={(e) => suaDong(d.key, (x) => ({ ...x, cvId: Number(e.target.value) }))}>
                              {nguonLoi.map((c) => (
                                <option key={c.cong_viec_id} value={c.cong_viec_id}>
                                  {tenCongDoan(c)}{c.to_ten ? ` · ${c.to_ten}` : ""}
                                  {c.cong_viec_id === cd.cong_viec_id ? " (đang kiểm)" : ""}
                                </option>
                              ))}
                            </select>
                          </label>
                        )}
                        {dongLoi.length > 1 && (
                          <button type="button" className="kkf-dl__bo" aria-label={`Bỏ dòng lỗi ${i + 1}`}
                            title="Bỏ dòng lỗi" onClick={() => boDong(d.key)}>
                            <Icon name="x" size={14} />
                          </button>
                        )}
                      </div>
                      {Number(d.so) > 0 && (
                        <div className="kcs-drawer__loi">
                          <p className="kcs-drawer__anh-hint">
                            {khac
                              ? <>Lỗi tính cho công đoạn <b>{tenCongDoan(chiu)}</b> — báo về <b>{chiu.to_ten || "tổ làm công đoạn đó"}</b>. Số của công đoạn đó không đổi.</>
                              : <>Lỗi sẽ báo về <b>{cd.to_ten || "tổ làm công đoạn này"}</b>.</>}
                          </p>
                          <div className="kcs-drawer__field">
                            <label htmlFor={`kcs-mo-ta-loi-${d.key}`}>
                              {dongLoi.length > 1 ? `Mô tả lỗi dòng ${i + 1}` : "Mô tả lỗi"}
                            </label>
                            <textarea id={`kcs-mo-ta-loi-${d.key}`} value={d.moTa}
                              onChange={(e) => suaDong(d.key, (x) => ({ ...x, moTa: e.target.value }))}
                              placeholder="VD: lem mực góc phải, lệch màu" />
                          </div>
                          <div className="kcs-drawer__field" role="group" aria-labelledby={`kcs-anh-loi-nhan-${d.key}`}>
                            <div className="kcs-drawer__anh-dau">
                              <span id={`kcs-anh-loi-nhan-${d.key}`} className="kcs-drawer__anh-nhan">Ảnh lỗi (ít nhất 1)</span>
                              <span className="kcs-drawer__anh-dem">
                                {d.anh.length > 0 ? `${d.anh.length} ảnh` : "Chưa có ảnh"}
                                {dangNen > 0 && dongAnh.current === d.key && " · đang xử lý…"}
                              </span>
                            </div>
                            <div className="kcs-drawer__anh-nut">
                              <button type="button" className="btn btn--ghost" onClick={() => moChonAnh(d.key, chupRef.current)}>
                                <Icon name="camera" size={14} /> Chụp ảnh
                              </button>
                              <button type="button" className="btn btn--ghost" onClick={() => moChonAnh(d.key, chonRef.current)}>
                                <Icon name="upload" size={14} /> Chọn ảnh có sẵn
                              </button>
                            </div>
                            {d.anh.length > 0 && (
                              <ul className="thsx-tep__ds">
                                {d.anh.map((a) => (
                                  <DongTep key={a.id} onXem={setXem} onBo={() => boAnh(d.key, a.id)}
                                    t={{ ten_tep: a.file.name, file_url: a.url, content_type: a.file.type }}
                                    meta={a.goc > a.file.size ? `${coChu(a.file.size)} (đã nén từ ${coChu(a.goc)})` : coChu(a.file.size)} />
                                ))}
                              </ul>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
                {/* `capture`: điện thoại mở thẳng camera sau; máy tính bỏ qua cờ này và mở hộp chọn tệp. */}
                <input ref={chupRef} type="file" accept="image/*" capture="environment" hidden
                  aria-label="Chụp ảnh lỗi" onChange={(e) => void themAnh(e.currentTarget)} />
                <input ref={chonRef} type="file" accept="image/*" multiple hidden
                  aria-label="Chọn ảnh lỗi" onChange={(e) => void themAnh(e.currentTarget)} />
                {nguonLoi.length > 1 && nSoLoi > 0 && (
                  <button type="button" className="kkf-them" onClick={themDong}>
                    + Thêm dòng lỗi do công đoạn khác
                  </button>
                )}
                {cuoi && (
                  <>
                    <div className="kkf-loi__kq">
                      <span>Kiểm <b>{num(chuaKiem)}</b></span>
                      <span className="is-dat">Đạt <b>{num(datLanNay)}</b></span>
                      <span className={nSoLoi > 0 ? "is-loi" : ""}>Lỗi <b>{num(nSoLoi)}</b></span>
                    </div>
                    <p className="kcs-drawer__anh-hint">
                      Lần này kiểm <b>{num(chuaKiem)}</b> {dv} tổ đã làm mà chưa kiểm → đạt <b>{num(datLanNay)}</b> {dv}.
                    </p>
                  </>
                )}
              </>
            ) : (
              <p className="kcs-drawer__anh-hint">
                {cuoi
                  ? "Tổ chưa ghi thêm sản lượng nào từ lần kiểm trước — chưa có gì để kiểm."
                  : cd.tot > 0
                    ? "Lỗi đã ghi bằng số tốt tổ đã làm — không ghi thêm được."
                    : "Tổ chưa ghi sản lượng nào — chưa có hàng để ghi lỗi."}
              </p>
            )}
          </div>

          <div className="kcs-drawer__field">
            <label htmlFor="kcs-ghi-chu">Ghi chú (nếu có)</label>
            <input id="kcs-ghi-chu" type="text" className="kcs-check-row__note" value={ghiChu}
              onChange={(e) => setGhiChu(e.target.value)} />
          </div>

          {error && (
            <div ref={errorRef} className="banner banner--error" role="alert">
              <span>{error}</span>
            </div>
          )}
        </section>

        {/* 6 · CÁC LẦN KIỂM TRƯỚC — mới nhất trước, dài thì gấp bớt. */}
        <section className="thsx-card kkf-the">
          <div className="thsx-psec__h">
            <Icon name="clipboard" size={14} />
            <span className="thsx-psec__title">{cuoi ? "Các lần kiểm trước" : "Lỗi đã ghi trước"}</span>
            {soLanHien > 0 && <span className="kkf-h__phu">{soLanHien} lần</span>}
          </div>
          <KcsLanKiemList lanKiem={lkHien} checklist={cd.checklist} chiLoi={!cuoi} />
          {lanKiem.length > LAN_KIEM_HIEN && (
            <button type="button" className="kkf-them" onClick={() => setMoHetLk((v) => !v)}>
              {moHetLk ? "Thu gọn" : `Xem thêm ${lanKiem.length - LAN_KIEM_HIEN} lần cũ hơn`}
            </button>
          )}
        </section>
      </div>
      {xem && createPortal(<XemTruoc tep={xem} onDong={() => setXem(null)} />, document.body)}
    </Drawer>
  );
}
