// KCS theo LỆNH (mg 0306) — màn thứ hai: CHUỖI CÔNG ĐOẠN của một lệnh, theo thứ tự routing.
//
// Mỗi công đoạn: tổ làm, trạng thái chạy, tốt/hỏng tổ đã ghi, tình trạng kiểm (chưa kiểm · đạt · có
// lỗi, số lần). Bấm "Kiểm" → ngăn `KcsKiemForm`. Công đoạn cuối của nhóm (`la_kcs_cuoi`) có thêm dải
// nhập kho: phần đạt luỹ kế (trần = số tốt) chưa gửi kho → nút "Tạo yêu cầu nhập kho". Yêu cầu tạo ra
// là yêu cầu NHẬP thật ở màn Yêu cầu nhập xuất (mã DNN…) — dải liệt kê từng mã, bấm mã mở màn Kho.
import { useCallback, useEffect, useState } from "react";
import {
  ApiError, api,
  type SxKcsChuoiCongDoan, type SxKcsCongDoan,
} from "../../api/client";
import { useAuth } from "../../auth/useAuth";
import { useKcs } from "../../auth/permissions";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { Icon } from "../../components/Icons";
import { ngayGio, num } from "../keHoachSxShared";
import { nhanDonVi } from "../lsxBuoc";
import { KcsChotNhom } from "./KcsChotNhom";
import { KcsKiemForm } from "./KcsKiemForm";
import { KcsLanKiemList } from "./KcsLanKiemList";
import {
  KCS_CD_TRANG_THAI, KCS_NHOM_TRANG_THAI, KCS_YC_KHO_TRANG_THAI, kiemDuoc, tinhTrangKiem,
} from "./kcsNhan";

export function KcsChuoiCongDoan({
  lsxId, eventTick, onBack, onChanged, onMoYeuCauKho,
}: {
  lsxId: number;
  eventTick?: number;
  onBack: () => void;
  /** Vừa ghi gì đó (lần kiểm, yêu cầu kho, chốt nhóm) — trang cha làm mới danh sách + báo cáo. */
  onChanged: () => void;
  /** Mở một yêu cầu nhập kho ở màn Kho. Không truyền (thiếu quyền xem kho) ⇒ mã chỉ là chữ. */
  onMoYeuCauKho?: (requestId: number) => void;
}) {
  const { token } = useAuth();
  const { kcs, truongKcs } = useKcs();
  const [data, setData] = useState<SxKcsChuoiCongDoan | null>(null);
  const [loi, setLoi] = useState<string | null>(null);
  const [mo, setMo] = useState<Set<number>>(new Set());
  const [kiem, setKiem] = useState<SxKcsCongDoan | null>(null);
  const [nhapKho, setNhapKho] = useState<SxKcsCongDoan | null>(null);
  const [nhapKhoBusy, setNhapKhoBusy] = useState(false);
  const [nhapKhoLoi, setNhapKhoLoi] = useState<string | null>(null);
  const [thongBao, setThongBao] = useState<string | null>(null);

  const tai = useCallback(() => {
    if (!token) return;
    api.sanXuat.kcsChuoiCongDoan(token, lsxId)
      .then((r) => { setData(r); setLoi(null); })
      .catch((e) => setLoi(e instanceof ApiError ? e.message : "Không tải được chuỗi công đoạn."));
  }, [token, lsxId]);
  useEffect(() => { tai(); }, [tai, eventTick]);

  function batTat(id: number) {
    setMo((cu) => {
      const s = new Set(cu);
      if (s.has(id)) s.delete(id); else s.add(id);
      return s;
    });
  }

  async function taoNhapKho() {
    if (!token || !nhapKho || nhapKhoBusy) return;
    setNhapKhoBusy(true);
    setNhapKhoLoi(null);
    try {
      const r = await api.sanXuat.taoYeuCauNhapKhoCongDoan(token, nhapKho.cong_viec_id);
      setThongBao(`Đã tạo yêu cầu nhập kho ${r.ma}: ${num(r.so_luong)} ${nhanDonVi(nhapKho.don_vi)} — chờ kho nhận.`);
      setNhapKho(null);
      tai();
      onChanged();
    } catch (e) {
      setNhapKhoLoi(e instanceof ApiError ? e.message : "Không tạo được yêu cầu nhập kho.");
    } finally {
      setNhapKhoBusy(false);
    }
  }

  const lsx = data?.lsx ?? null;
  const congDoan = data?.cong_doan ?? [];
  const nhomTt = lsx?.nhom_trang_thai ? KCS_NHOM_TRANG_THAI[lsx.nhom_trang_thai] : null;

  return (
    <>
      <div className="kcs-lenh-dau">
        <button type="button" className="btn btn--ghost btn--sm" onClick={onBack}>
          <Icon name="chevron" size={13} style={{ transform: "rotate(90deg)" }} /> Danh sách lệnh
        </button>
        {lsx && (
          <>
            <span className="kcs-lenh-dau__ma">{lsx.ma}</span>
            <span className="kcs-lenh-dau__phu">
              {[lsx.ten, lsx.khach].filter(Boolean).join(" · ")}
            </span>
            {nhomTt && <span className={`badge-sem ${nhomTt.cls}`}>{nhomTt.nhan}</span>}
          </>
        )}
      </div>

      {thongBao && (
        <div className="banner banner--success" role="status">
          <span>{thongBao}</span>
          <button type="button" className="btn btn--ghost btn--sm" onClick={() => setThongBao(null)}>Đóng</button>
        </div>
      )}
      {loi && (
        <div className="banner banner--error" role="alert">
          <span>{loi}</span>
          <button type="button" className="btn btn--ghost btn--sm" onClick={tai}>Tải lại</button>
        </div>
      )}

      <section className="kcs-section">
        <h2>Chuỗi công đoạn <span className="rc__count">{congDoan.length}</span></h2>
        {data == null && !loi ? (
          <p className="rc__empty-text">Đang tải…</p>
        ) : congDoan.length === 0 ? (
          <div className="rc__empty-state">
            <p className="rc__empty-text">Lệnh này chưa có công đoạn nào.</p>
          </div>
        ) : (
          <ol className="kcs-chuoi">
            {congDoan.map((cd, i) => {
              const tt = tinhTrangKiem(cd.so_lan_kiem, cd.tong_loi);
              const dv = nhanDonVi(cd.don_vi);
              const dangMo = mo.has(cd.cong_viec_id);
              const choKiem = kiemDuoc(cd.trang_thai);
              return (
                <li key={cd.cong_viec_id}
                  className={`kcs-chuoi__it${tt.loai === "chua" ? "" : ` kcs-chuoi__it--${tt.loai}`}`}>
                  <div className="kcs-chuoi__hd">
                    <span className="kcs-chuoi__stt">{i + 1}</span>
                    <span className="kcs-chuoi__ten">
                      {cd.ten}{cd.phan_doan_tong > 1 ? ` (${cd.phan_doan_so}/${cd.phan_doan_tong})` : ""}
                    </span>
                    {cd.la_kcs_cuoi && <span className="kcs-chuoi__cuoi-tag">Công đoạn cuối</span>}
                    <span className={`badge-sem ${tt.cls}`}>{tt.nhan}</span>
                  </div>
                  <div className="kcs-chuoi__meta">
                    <span>Tổ: <b>{cd.to_ten || "—"}</b></span>
                    <span>{KCS_CD_TRANG_THAI[cd.trang_thai] ?? cd.trang_thai}</span>
                    <span>Tốt <b>{num(cd.tot)}</b> · Hỏng <b>{num(cd.hong)}</b> {dv}</span>
                    {cd.so_lan_kiem > 0 && (
                      <span>KCS: đạt <b>{num(cd.tong_dat)}</b> · lỗi <b>{num(cd.tong_loi)}</b></span>
                    )}
                  </div>
                  {cd.la_kcs_cuoi && (
                    <div className="kcs-chuoi__kho">
                      <Icon name="warehouse" size={14} />
                      <span>
                        Đã đề nghị nhập kho <b>{num(cd.da_yeu_cau_kho)}</b> · còn chờ gửi kho <b>{num(cd.con_gui_kho)}</b> {dv}
                      </span>
                      {kcs && cd.con_gui_kho > 0 && (
                        <button type="button" className="btn btn--accent btn--sm"
                          onClick={() => { setNhapKhoLoi(null); setNhapKho(cd); }}>
                          Tạo yêu cầu nhập kho ({num(cd.con_gui_kho)})
                        </button>
                      )}
                      {cd.yeu_cau_kho.length > 0 && (
                        <ul className="kcs-chuoi__kho-ds">
                          {cd.yeu_cau_kho.map((y) => {
                            const ytt = KCS_YC_KHO_TRANG_THAI[y.trang_thai]
                              ?? { nhan: y.trang_thai, cls: "badge-sem--muted" };
                            return (
                              <li key={y.request_id}>
                                {onMoYeuCauKho ? (
                                  <button type="button" className="kcs-chuoi__kho-ma"
                                    title="Mở yêu cầu này ở màn Kho"
                                    onClick={() => onMoYeuCauKho(y.request_id)}>
                                    {y.ma}
                                  </button>
                                ) : (
                                  <span className="kcs-chuoi__kho-ma">{y.ma}</span>
                                )}
                                <span>
                                  Đề nghị <b>{num(y.sl_de_nghi)}</b> · kho đã nhận <b>{num(y.sl_da_nhan)}</b> {nhanDonVi(y.don_vi)}
                                </span>
                                <span className={`badge-sem ${ytt.cls}`}>{ytt.nhan}</span>
                                {y.tao_luc && <span className="kcs-chuoi__kho-luc">{ngayGio(y.tao_luc)}</span>}
                              </li>
                            );
                          })}
                        </ul>
                      )}
                    </div>
                  )}
                  <div className="kcs-chuoi__nut">
                    {kcs && (
                      <button type="button" className="btn btn--accent btn--sm" disabled={!choKiem}
                        title={choKiem ? undefined : "Công đoạn chưa bắt đầu — chưa kiểm được."}
                        onClick={() => setKiem(cd)}>
                        <Icon name="shield" size={12} /> Kiểm
                      </button>
                    )}
                    {cd.so_lan_kiem > 0 && (
                      <button type="button" className="btn btn--ghost btn--sm" aria-expanded={dangMo}
                        onClick={() => batTat(cd.cong_viec_id)}>
                        {dangMo ? "Ẩn lần kiểm" : `Xem ${cd.so_lan_kiem} lần kiểm`}
                      </button>
                    )}
                  </div>
                  {dangMo && (
                    <div className="kcs-chuoi__than">
                      <KcsLanKiemList lanKiem={cd.lan_kiem} checklist={cd.checklist} />
                    </div>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </section>

      {lsx?.nhom_id != null && (
        <KcsChotNhom nhomId={lsx.nhom_id} nhan={lsx.nhom_ma ?? `Nhóm #${lsx.nhom_id}`}
          canDong={truongKcs} eventTick={eventTick}
          onDone={() => { tai(); onChanged(); }} />
      )}

      {kiem && lsx && (
        <KcsKiemForm lenh={lsx} cd={kiem} onClose={() => setKiem(null)}
          onSaved={(r) => {
            setKiem(null);
            setThongBao(
              `Đã ghi lần kiểm ${r.ten_cong_doan}: đạt ${num(r.so_dat)} · lỗi ${num(r.so_loi)}`
              + (r.so_loi > 0 ? " — đã báo tổ làm công đoạn." : "."),
            );
            setMo((cu) => new Set(cu).add(r.cong_viec_id));
            tai();
            onChanged();
          }} />
      )}

      <ConfirmDialog
        open={nhapKho != null}
        title="Tạo yêu cầu nhập kho"
        message={nhapKho
          ? `Đề nghị kho nhập ${num(nhapKho.con_gui_kho)} ${nhanDonVi(nhapKho.don_vi)} thành phẩm đã kiểm đạt của ${lsx?.ma ?? "lệnh"} (${nhapKho.ten}).`
          : undefined}
        confirmLabel="Gửi yêu cầu"
        busy={nhapKhoBusy}
        error={nhapKhoLoi}
        onConfirm={taoNhapKho}
        onCancel={() => { if (!nhapKhoBusy) setNhapKho(null); }}
      />
    </>
  );
}
