// KCS theo LỆNH (mg 0306, docs/design-kcs-theo-lenh.md) — ngăn kéo "Kiểm công đoạn".
//
// MỘT thao tác duy nhất: KCS đã mở lệnh, bấm một công đoạn trong chuỗi → tick checklist, ghi Số đạt
// / Số lỗi. Có lỗi thì bắt mô tả + ít nhất một ảnh. Tổ chịu lỗi = tổ của công đoạn, người kiểm = tài
// khoản đang đăng nhập — cả hai do máy chủ chốt, form KHÔNG có ô chọn. Ghi xong không trừ số, không
// đổi trạng thái công việc; kiểm lại bao nhiêu lần cũng được.
//
// Ảnh lỗi là DANH SÁCH cộng dồn: KCS đứng ở chồng hàng chụp từng tấm một (nút "Chụp ảnh" mở thẳng
// camera điện thoại) hoặc chọn nhiều tấm có sẵn; mỗi lần thêm là nối vào, không đè. Ảnh nằm chờ trong
// form (URL `blob:`), bấm Lưu mới gửi cùng lần kiểm — lần kiểm chưa có thì chưa có chỗ gắn ảnh.
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  ApiError, api,
  type SxKcsChecklistKetQuaIn, type SxKcsCongDoan, type SxKcsKiemKetQua, type SxKcsLenhDau,
} from "../../api/client";
import { useAuth } from "../../auth/useAuth";
import { XemTruoc } from "../../components/DinhKemTep";
import { Icon } from "../../components/Icons";
import type { TepXem } from "../../components/tepDinhKem";
import { coChu, nenAnh } from "../../lib/anhNen";
import { Drawer } from "../danh-muc/components/Drawer";
import { num } from "../keHoachSxShared";
import { nhanDonVi } from "../lsxBuoc";
import { DongTep } from "../ThsxDongTep";
import { KCS_CD_TRANG_THAI } from "./kcsNhan";
import "../thuc-hien-sx.css";

/** Một ảnh đang chờ gửi: file (đã nén nếu lợi) + URL xem ngay + cỡ gốc để nói đã nén bao nhiêu. */
interface AnhCho {
  id: number;
  file: File;
  url: string;
  goc: number;
}

export function KcsKiemForm({
  lenh, cd, onClose, onSaved,
}: {
  lenh: SxKcsLenhDau;
  cd: SxKcsCongDoan;
  onClose: () => void;
  onSaved: (r: SxKcsKiemKetQua) => void;
}) {
  const { token } = useAuth();
  const [dat, setDat] = useState<Record<number, boolean | undefined>>({});
  const [ghiChuTc, setGhiChuTc] = useState<Record<number, string>>({});
  const [soDat, setSoDat] = useState("");
  const [soLoi, setSoLoi] = useState("");
  const [moTaLoi, setMoTaLoi] = useState("");
  const [anh, setAnh] = useState<AnhCho[]>([]);
  const [dangNen, setDangNen] = useState(0);
  const [xem, setXem] = useState<TepXem | null>(null);
  const [ghiChu, setGhiChu] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Thông báo chặn nằm cuối thân ngăn — cuộn tới nó, không thì người bấm "Lưu" không thấy gì xảy ra.
  const errorRef = useRef<HTMLDivElement>(null);
  useEffect(() => { if (error) errorRef.current?.scrollIntoView({ block: "nearest" }); }, [error]);

  const chupRef = useRef<HTMLInputElement>(null);
  const chonRef = useRef<HTMLInputElement>(null);
  const idAnh = useRef(0);
  // URL `blob:` không tự mất khi ngăn đóng — dọn tay; ref để bản dọn lúc unmount thấy danh sách mới nhất.
  const anhRef = useRef<AnhCho[]>([]);
  useEffect(() => { anhRef.current = anh; }, [anh]);
  useEffect(() => () => { for (const a of anhRef.current) URL.revokeObjectURL(a.url); }, []);

  async function themAnh(input: HTMLInputElement) {
    const ds = Array.from(input.files ?? []);
    // Xoá giá trị ô chọn: không thì chọn lại đúng tấm vừa bỏ, trình duyệt không bắn `change`.
    input.value = "";
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
      setAnh((cu) => [...cu, moi]);
    }
  }

  function boAnh(id: number) {
    setAnh((cu) => {
      const bo = cu.find((a) => a.id === id);
      if (bo) URL.revokeObjectURL(bo.url);
      return cu.filter((a) => a.id !== id);
    });
  }

  const nSoDat = Number(soDat) || 0;
  const nSoLoi = Number(soLoi) || 0;
  const dv = nhanDonVi(cd.don_vi);
  // Công đoạn cuối: phần đạt đi kho nên không được vượt số tốt tổ đã ghi (máy chủ chặn cùng luật).
  const conDatDuoc = cd.la_kcs_cuoi ? Math.max(0, cd.tot - cd.tong_dat) : null;
  const thieuBatBuoc = cd.checklist.filter((tc) => tc.bat_buoc && dat[tc.thu_tu] === undefined);

  function kiemTra(): string | null {
    if (soDat.trim() !== "" && (!Number.isFinite(Number(soDat)) || Number(soDat) < 0)) return "Số đạt không hợp lệ.";
    if (soLoi.trim() !== "" && (!Number.isFinite(Number(soLoi)) || Number(soLoi) < 0)) return "Số lỗi không hợp lệ.";
    if (nSoDat + nSoLoi <= 0) return "Nhập số đạt hoặc số lỗi.";
    if (conDatDuoc != null && nSoDat > conDatDuoc) {
      return `Công đoạn cuối: số đạt vượt số tốt tổ đã ghi (còn kiểm đạt được ${num(conDatDuoc)} ${dv}).`;
    }
    if (thieuBatBuoc.length > 0) return "Còn tiêu chí bắt buộc chưa ghi kết quả.";
    if (nSoLoi > 0 && !moTaLoi.trim()) return "Có lỗi thì phải mô tả lỗi.";
    if (nSoLoi > 0 && anh.length === 0) return "Có lỗi thì phải kèm ít nhất một ảnh.";
    return null;
  }

  async function luu() {
    if (!token || saving || dangNen > 0) return;
    const loi = kiemTra();
    if (loi) { setError(loi); return; }
    setSaving(true);
    setError(null);
    const checklist: SxKcsChecklistKetQuaIn[] = cd.checklist
      .filter((tc) => dat[tc.thu_tu] !== undefined)
      .map((tc) => ({
        thu_tu: tc.thu_tu,
        dat: dat[tc.thu_tu] === true,
        ghi_chu: ghiChuTc[tc.thu_tu]?.trim() || null,
      }));
    try {
      const r = await api.sanXuat.kiemCongDoan(token, cd.cong_viec_id, {
        so_dat: nSoDat,
        so_loi: nSoLoi,
        checklist,
        ghi_chu: ghiChu.trim() || null,
        loi_mo_ta: nSoLoi > 0 ? moTaLoi.trim() : null,
        files: nSoLoi > 0 ? anh.map((a) => a.file) : [],
      });
      onSaved(r);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Không lưu được kết quả kiểm.");
      setSaving(false);
    }
  }

  const tenCd = cd.phan_doan_tong > 1 ? `${cd.ten} (${cd.phan_doan_so}/${cd.phan_doan_tong})` : cd.ten;

  return (
    <Drawer
      kicker="Kiểm công đoạn"
      title={tenCd}
      onClose={onClose}
      foot={(
        <>
          <button type="button" className="btn btn--ghost" onClick={onClose} disabled={saving}>Huỷ</button>
          <button type="button" className="btn btn--accent" onClick={luu} disabled={saving || dangNen > 0}>
            {saving ? "Đang lưu…" : dangNen > 0 ? "Đang xử lý ảnh…" : "Lưu kết quả kiểm"}
          </button>
        </>
      )}
    >
      <div className="rc-drawer__body">
        <div className="kcs-drawer__ctx">
          <div className="kcs-drawer__ctx-row"><strong>{lenh.ma}</strong>{lenh.ten ? ` — ${lenh.ten}` : ""}</div>
          <div className="kcs-drawer__ctx-row">
            Tổ làm: <strong>{cd.to_ten || "—"}</strong> · {KCS_CD_TRANG_THAI[cd.trang_thai] ?? cd.trang_thai}
          </div>
          <div className="kcs-drawer__ctx-row">
            Tổ đã ghi: tốt <strong>{num(cd.tot)}</strong> · hỏng <strong>{num(cd.hong)}</strong> {dv}
          </div>
          {cd.so_lan_kiem > 0 && (
            <div className="kcs-drawer__ctx-row">
              Đã kiểm {cd.so_lan_kiem} lần: đạt <strong>{num(cd.tong_dat)}</strong> · lỗi <strong>{num(cd.tong_loi)}</strong>
            </div>
          )}
          {cd.la_kcs_cuoi && (
            <div className="kcs-drawer__ctx-row">
              Công đoạn cuối của nhóm — số đạt được đề nghị nhập kho (còn kiểm đạt được <strong>{num(conDatDuoc ?? 0)}</strong> {dv}).
            </div>
          )}
        </div>

        {cd.checklist.length > 0 && (
          <div className="kcs-drawer__block">
            <h3>Tiêu chí kiểm</h3>
            {cd.checklist.map((tc) => (
              <div className="kcs-check-row" key={tc.thu_tu}>
                <label className="kcs-check-row__label">
                  <input
                    type="checkbox"
                    checked={dat[tc.thu_tu] === true}
                    ref={(el) => { if (el) el.indeterminate = dat[tc.thu_tu] === undefined; }}
                    onChange={(e) => setDat((d) => ({ ...d, [tc.thu_tu]: e.target.checked }))}
                  />
                  {tc.ten ?? tc.ma ?? `Tiêu chí #${tc.thu_tu}`}
                  {tc.bat_buoc && <span className="kcs-check-row__req" title="Bắt buộc">*</span>}
                </label>
                <input
                  type="text" className="kcs-check-row__note" placeholder="Ghi chú (nếu có)"
                  value={ghiChuTc[tc.thu_tu] ?? ""}
                  onChange={(e) => setGhiChuTc((g) => ({ ...g, [tc.thu_tu]: e.target.value }))}
                />
              </div>
            ))}
            <p className="kcs-drawer__anh-hint">Ô gạch ngang = chưa kiểm; tick = đạt; bỏ tick = không đạt.</p>
          </div>
        )}

        <div className="kcs-drawer__block">
          <h3>Số lượng ({dv || "đơn vị công đoạn"})</h3>
          <div className="kcs-drawer__soluong">
            <label>Số đạt
              <input type="number" min={0} inputMode="decimal" value={soDat}
                onChange={(e) => setSoDat(e.target.value)} aria-label="Số đạt" />
            </label>
            <label>Số lỗi
              <input type="number" min={0} inputMode="decimal" value={soLoi}
                onChange={(e) => setSoLoi(e.target.value)} aria-label="Số lỗi" />
            </label>
          </div>
        </div>

        {nSoLoi > 0 && (
          <div className="kcs-drawer__block kcs-drawer__loi">
            <p className="kcs-drawer__anh-hint">
              Lỗi sẽ báo về <b>{cd.to_ten || "tổ làm công đoạn này"}</b>.
            </p>
            <div className="kcs-drawer__field">
              <label htmlFor="kcs-mo-ta-loi">Mô tả lỗi</label>
              <textarea id="kcs-mo-ta-loi" value={moTaLoi} onChange={(e) => setMoTaLoi(e.target.value)}
                placeholder="VD: lem mực góc phải, lệch màu" />
            </div>
            <div className="kcs-drawer__field" role="group" aria-labelledby="kcs-anh-loi-nhan">
              <div className="kcs-drawer__anh-dau">
                <span id="kcs-anh-loi-nhan" className="kcs-drawer__anh-nhan">Ảnh lỗi (ít nhất 1)</span>
                <span className="kcs-drawer__anh-dem">
                  {anh.length > 0 ? `${anh.length} ảnh` : "Chưa có ảnh"}
                  {dangNen > 0 && " · đang xử lý…"}
                </span>
              </div>
              <div className="kcs-drawer__anh-nut">
                <button type="button" className="btn btn--ghost" onClick={() => chupRef.current?.click()}>
                  <Icon name="camera" size={14} /> Chụp ảnh
                </button>
                <button type="button" className="btn btn--ghost" onClick={() => chonRef.current?.click()}>
                  <Icon name="upload" size={14} /> Chọn ảnh có sẵn
                </button>
              </div>
              {/* `capture`: điện thoại mở thẳng camera sau; máy tính bỏ qua cờ này và mở hộp chọn tệp. */}
              <input ref={chupRef} type="file" accept="image/*" capture="environment" hidden
                aria-label="Chụp ảnh lỗi" onChange={(e) => void themAnh(e.currentTarget)} />
              <input ref={chonRef} type="file" accept="image/*" multiple hidden
                aria-label="Chọn ảnh lỗi" onChange={(e) => void themAnh(e.currentTarget)} />
              {anh.length > 0 && (
                <ul className="thsx-tep__ds">
                  {anh.map((a) => (
                    <DongTep key={a.id} onXem={setXem} onBo={() => boAnh(a.id)}
                      t={{ ten_tep: a.file.name, file_url: a.url, content_type: a.file.type }}
                      meta={a.goc > a.file.size ? `${coChu(a.file.size)} (đã nén từ ${coChu(a.goc)})` : coChu(a.file.size)} />
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}

        <div className="kcs-drawer__block">
          <div className="kcs-drawer__field">
            <label htmlFor="kcs-ghi-chu">Ghi chú (nếu có)</label>
            <input id="kcs-ghi-chu" type="text" className="kcs-check-row__note" value={ghiChu}
              onChange={(e) => setGhiChu(e.target.value)} />
          </div>
        </div>

        {error && (
          <div ref={errorRef} className="banner banner--error" role="alert">
            <span>{error}</span>
          </div>
        )}
      </div>
      {xem && createPortal(<XemTruoc tep={xem} onDong={() => setXem(null)} />, document.body)}
    </Drawer>
  );
}
