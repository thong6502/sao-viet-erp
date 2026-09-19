// KCS theo LỆNH (mg 0306) — màn thứ hai: CHUỖI CÔNG ĐOẠN của một lệnh, theo thứ tự routing.
//
// Mỗi công đoạn: tổ làm, trạng thái chạy, số lượng tổ đã ghi, tình trạng kiểm (chưa kiểm · đạt · có
// lỗi, số lần). Bấm "Kiểm" → ngăn `KcsKiemForm`. Chỉ công đoạn cuối mới KIỂM ĐẠT (để nhập kho);
// công đoạn giữa KCS chỉ "Ghi lỗi" khi thấy, không bắt buộc — không bày đạt/tỉ lệ ở đó (19/09/2026). Công đoạn cuối của nhóm (`la_kcs_cuoi`) có thêm dải
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
import { Drawer } from "../danh-muc/components/Drawer";
import { ngayGio, num } from "../keHoachSxShared";
import { nhanChang, nhanDonVi } from "../lsxBuoc";
import { useNapTenDonVi } from "../tenDonVi";
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
  // Nhãn chặng + tên đơn vị nạp từ danh mục — không gọi thì bảng hiện mã trần ("to", "ma-0002").
  useNapTenDonVi();
  const [data, setData] = useState<SxKcsChuoiCongDoan | null>(null);
  const [loi, setLoi] = useState<string | null>(null);
  const [kiem, setKiem] = useState<SxKcsCongDoan | null>(null);
  const [lanKiemCd, setLanKiemCd] = useState<SxKcsCongDoan | null>(null);
  const [khoCd, setKhoCd] = useState<SxKcsCongDoan | null>(null);
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

  useEffect(() => {
    if (data) {
      if (lanKiemCd) {
        const found = data.cong_doan.find((c) => c.cong_viec_id === lanKiemCd.cong_viec_id);
        if (found) setLanKiemCd(found);
      }
      if (khoCd) {
        const found = data.cong_doan.find((c) => c.cong_viec_id === khoCd.cong_viec_id);
        if (found) setKhoCd(found);
      }
    }
  }, [data]);

  async function taoNhapKho() {
    if (!token || !nhapKho || nhapKhoBusy) return;
    setNhapKhoBusy(true);
    setNhapKhoLoi(null);
    try {
      const r = await api.sanXuat.taoYeuCauNhapKhoCongDoan(token, nhapKho.cong_viec_id);
      setThongBao(`Đã tạo yêu cầu nhập kho ${r.ma}: ${num(r.so_luong)} ${nhanChang(nhapKho.don_vi)} — chờ kho nhận.`);
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

  // Tính toán chỉ số tổng quan cho Hero Card
  const tongCd = congDoan.length;
  // Đạt chỉ có nghĩa ở công đoạn cuối — số đó mới là hàng vào kho.
  const cdCuoi = congDoan.filter((cd) => cd.la_kcs_cuoi);
  const tongDat = cdCuoi.reduce((acc, cd) => acc + cd.tong_dat, 0);
  const totCuoi = cdCuoi.reduce((acc, cd) => acc + cd.tot, 0);
  const dvCuoi = cdCuoi.length > 0 ? nhanChang(cdCuoi[0].don_vi) : "";
  const tongLoi = congDoan.reduce((acc, cd) => acc + cd.tong_loi, 0);

  return (
    <>
      {/* Nút quay lại danh sách lệnh */}
      <div className="kcs-lenh-dau">
        <button type="button" className="btn btn--ghost btn--sm" onClick={onBack}>
          <Icon name="chevron" size={13} style={{ transform: "rotate(90deg)" }} /> Danh sách lệnh
        </button>
      </div>

      {/* Hero Header Card - Tổng quan Lệnh sản xuất & KCS (Siêu gọn gàng) */}
      {lsx && (
        <div className="kcs-hero">
          <div className="kcs-hero__top">
            <div className="kcs-hero__ma-row">
              <span className="kcs-hero__ma">{lsx.ma}</span>
              {nhomTt && <span className={`badge-sem ${nhomTt.cls}`}>{nhomTt.nhan}</span>}
              <span className="kcs-hero__ten">{lsx.ten}</span>
            </div>
            <div className="kcs-hero__meta">
              {lsx.khach && <span>Khách hàng: <b>{lsx.khach}</b></span>}
              {lsx.nhom_ma && <span>Nhóm: <b>{lsx.nhom_ma}</b></span>}
            </div>
          </div>

          <div className="kcs-hero__inline-stats">
            <span className="kcs-hero__inline-item">
              Chuỗi công đoạn: <b>{tongCd} bước</b>
            </span>
            {cdCuoi.length > 0 && (
              <>
                <span style={{ color: "#cbd5e1" }}>·</span>
                <span className="kcs-hero__inline-item" style={{ color: "#047857" }}>
                  KCS đạt ở công đoạn cuối: <b>{num(tongDat)} / {num(totCuoi)} {dvCuoi}</b>
                </span>
              </>
            )}
            <span style={{ color: "#cbd5e1" }}>·</span>
            <span className="kcs-hero__inline-item" style={{ color: tongLoi > 0 ? "#b91c1c" : "#64748b" }}>
              Lỗi đã ghi: <b>{num(tongLoi)}</b>
            </span>
          </div>
        </div>
      )}

      {/* Pipeline Visual Stepper (Gọn gàng & ẩn scrollbar) */}
      {congDoan.length > 0 && (
        <div className="kcs-pipeline">
          <div className="kcs-pipeline__track">
            {congDoan.map((cd, i) => {
              const tt = tinhTrangKiem(cd.so_lan_kiem, cd.tong_loi, cd.la_kcs_cuoi);
              const isLast = i === congDoan.length - 1;
              return (
                <div key={cd.cong_viec_id} className="kcs-pipeline__node">
                  <div
                    className={`kcs-pipeline__step-box${tt.loai === "chua" ? "" : ` kcs-pipeline__step-box--${tt.loai}`}`}
                    onClick={() => {
                      if (cd.so_lan_kiem > 0) {
                        setLanKiemCd(cd);
                      } else {
                        const el = document.getElementById(`cd-card-${cd.cong_viec_id}`);
                        el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
                      }
                    }}
                    title={cd.so_lan_kiem > 0 ? `Mở popup lần kiểm công đoạn ${cd.ten}` : `Chuyển tới công đoạn ${cd.ten}`}
                  >
                    <span className="kcs-pipeline__num">{i + 1}</span>
                    <span className="kcs-pipeline__name">{cd.ten}</span>
                    <span className={`badge-sem ${tt.cls}`}>{tt.nhan}</span>
                  </div>
                  {!isLast && (
                    <div className="kcs-pipeline__arrow">
                      <Icon name="chevron" size={13} style={{ transform: "rotate(-90deg)" }} />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

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
          <div className="rc__tablewrap kcs-tablewrap">
            <table className="rc__table kcs-matrix-table">
              <thead>
                <tr>
                  <th style={{ width: "36px", textAlign: "center" }}>#</th>
                  <th>Công đoạn</th>
                  <th>Tổ đảm nhận</th>
                  <th>Sản xuất (tổ ghi)</th>
                  <th>KCS kiểm định</th>
                  <th>Tình trạng KCS</th>
                  <th style={{ textAlign: "right" }}>Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {congDoan.map((cd, i) => {
                  const tt = tinhTrangKiem(cd.so_lan_kiem, cd.tong_loi, cd.la_kcs_cuoi);
                  const dv = nhanChang(cd.don_vi);
                  const choKiem = kiemDuoc(cd.trang_thai);

                  const tongKcs = cd.tong_dat + cd.tong_loi;
                  const rateDat = tongKcs > 0 ? Math.round((cd.tong_dat / tongKcs) * 100) : null;

                  return (
                    <tr key={cd.cong_viec_id} id={`cd-card-${cd.cong_viec_id}`} className="kcs-matrix-row">
                      <td style={{ textAlign: "center", fontWeight: 700, color: "var(--ink)" }}>{i + 1}</td>
                      <td>
                        <div className="kcs-matrix__name-cell">
                          <span className="kcs-matrix__ten">
                            {cd.ten}{cd.phan_doan_tong > 1 ? ` (${cd.phan_doan_so}/${cd.phan_doan_tong})` : ""}
                          </span>
                          {cd.la_kcs_cuoi && <span className="kcs-chuoi__cuoi-tag">Cuối</span>}
                        </div>
                      </td>
                      <td>
                        <div className="kcs-matrix__to-cell">
                          <b style={{ color: "var(--ink)" }}>{cd.to_ten || "—"}</b>
                          <span className="kcs-matrix__sub-tt">{KCS_CD_TRANG_THAI[cd.trang_thai] ?? cd.trang_thai}</span>
                        </div>
                      </td>
                      <td>
                        <span className="kcs-matrix__stat">
                          Đã làm <b style={{ color: "#047857" }}>{num(cd.tot)}</b> {dv}
                        </span>
                      </td>
                      <td>
                        {!cd.la_kcs_cuoi ? (
                          cd.tong_loi > 0 ? (
                            <span className="kcs-matrix__stat">
                              Lỗi <b style={{ color: "#b91c1c" }}>{num(cd.tong_loi)}</b> {dv}
                            </span>
                          ) : (
                            <span style={{ color: "#94a3b8", fontSize: "12px" }}>Chưa ghi lỗi</span>
                          )
                        ) : cd.so_lan_kiem > 0 ? (
                          <span className="kcs-matrix__stat">
                            Đạt <b style={{ color: "#047857" }}>{num(cd.tong_dat)}</b> · Lỗi <b style={{ color: cd.tong_loi > 0 ? "#b91c1c" : "#64748b" }}>{num(cd.tong_loi)}</b> {dv}
                            {rateDat !== null && (
                              <span className="kcs-rate-pill" style={{ marginLeft: "6px" }}>
                                {rateDat}%
                              </span>
                            )}
                          </span>
                        ) : (
                          <span style={{ color: "#94a3b8", fontStyle: "italic", fontSize: "12px" }}>Chưa kiểm</span>
                        )}
                        {(cd.loi_buoc_sau ?? []).map((l) => (
                          <span key={`${l.phat_hien_o}-${l.don_vi}`} className="kcs-matrix__loi-sau"
                            title="Lỗi KCS bắt ở công đoạn sau, quy trách nhiệm về công đoạn này — không trừ số của công đoạn này">
                            +{num(l.so_luong)} {nhanChang(l.don_vi)} lỗi bắt ở {l.phat_hien_o}
                          </span>
                        ))}
                      </td>
                      <td>
                        <span className={`badge-sem ${tt.cls}`}>{tt.nhan}</span>
                      </td>
                      <td style={{ textAlign: "right" }}>
                        <div className="kcs-matrix__actions">
                          {cd.la_kcs_cuoi && cd.yeu_cau_kho.length > 0 && (
                            <button
                              type="button"
                              className="btn btn--ghost btn--sm"
                              style={{ padding: "3px 8px", fontSize: "12px", color: "#047857", border: "1px solid #a7f3d0", background: "#f0fdf4" }}
                              onClick={() => setKhoCd(cd)}
                              title="Xem lịch sử yêu cầu kho"
                            >
                              <Icon name="warehouse" size={12} /> Kho ({cd.yeu_cau_kho.length})
                            </button>
                          )}
                          {cd.la_kcs_cuoi && cd.con_gui_kho > 0 && kcs && (
                            <button
                              type="button"
                              className="btn btn--accent btn--sm"
                              style={{ background: "#059669", color: "#fff", border: "none", padding: "3px 8px", fontSize: "12px" }}
                              onClick={() => { setNhapKhoLoi(null); setNhapKho(cd); }}
                              title={`Tạo yêu cầu kho ${num(cd.con_gui_kho)} ${dv}`}
                            >
                              <Icon name="plus" size={12} /> YC Kho ({num(cd.con_gui_kho)})
                            </button>
                          )}
                          {kcs && (
                            <button
                              type="button"
                              className="btn btn--accent btn--sm"
                              style={choKiem ? { background: "linear-gradient(135deg, #ea580c 0%, #c2410c 100%)", color: "#fff", border: "none", padding: "3px 10px", fontSize: "12px" } : { padding: "3px 10px", fontSize: "12px" }}
                              disabled={!choKiem}
                              title={choKiem ? undefined : "Công đoạn chưa bắt đầu — chưa kiểm được."}
                              onClick={() => setKiem(cd)}
                            >
                              <Icon name="shield" size={12} /> {cd.la_kcs_cuoi ? "Kiểm" : "Ghi lỗi"}
                            </button>
                          )}
                          {cd.so_lan_kiem > 0 && (
                            <button
                              type="button"
                              className="btn btn--ghost btn--sm"
                              style={{ padding: "3px 8px", fontSize: "12px" }}
                              onClick={() => setLanKiemCd(cd)}
                              title={`Xem ${cd.so_lan_kiem} lần ${cd.la_kcs_cuoi ? "kiểm" : "ghi lỗi"} trong popup`}
                            >
                              {cd.la_kcs_cuoi ? "Lần kiểm" : "Lỗi đã ghi"} ({cd.so_lan_kiem})
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {lsx?.nhom_id != null && (
        <KcsChotNhom nhomId={lsx.nhom_id} nhan={lsx.nhom_ma ?? `Nhóm #${lsx.nhom_id}`}
          canDong={truongKcs} eventTick={eventTick}
          onDone={() => { tai(); onChanged(); }} />
      )}

      {/* Popup Drawer xem danh sách các lần kiểm */}
      {lanKiemCd && (
        <Drawer
          title={lanKiemCd.la_kcs_cuoi
            ? `Lịch sử ${lanKiemCd.so_lan_kiem} lần kiểm: ${lanKiemCd.ten}`
            : `Lỗi đã ghi: ${lanKiemCd.ten}`}
          kicker={lsx ? `Lệnh ${lsx.ma} · ${lsx.ten}` : "KCS Công đoạn"}
          onClose={() => setLanKiemCd(null)}
        >
          <div className="rc-drawer__body" style={{ padding: "16px 20px" }}>
            <KcsLanKiemList lanKiem={lanKiemCd.lan_kiem} checklist={lanKiemCd.checklist}
              chiLoi={!lanKiemCd.la_kcs_cuoi} />
          </div>
        </Drawer>
      )}

      {/* Popup Drawer xem lịch sử yêu cầu kho */}
      {khoCd && (
        <Drawer
          title={`Lịch sử yêu cầu nhập kho (${khoCd.yeu_cau_kho.length}): ${khoCd.ten}`}
          kicker={lsx ? `Lệnh ${lsx.ma} · ${lsx.ten}` : "Công đoạn thành phẩm"}
          onClose={() => setKhoCd(null)}
        >
          <div className="rc-drawer__body" style={{ padding: "16px 20px" }}>
            <ul className="kcs-chuoi__kho-ds">
              {khoCd.yeu_cau_kho.map((y) => {
                const ytt = KCS_YC_KHO_TRANG_THAI[y.trang_thai]
                  ?? { nhan: y.trang_thai, cls: "badge-sem--muted" };
                return (
                  <li key={y.request_id} style={{ padding: "10px 14px", border: "1px solid #d1fae5", borderRadius: "8px", background: "#fff", marginBottom: "8px", display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "8px" }}>
                    <div>
                      {onMoYeuCauKho ? (
                        <button type="button" className="kcs-chuoi__kho-ma"
                          style={{ fontSize: "14px", marginRight: "8px" }}
                          title="Mở yêu cầu này ở màn Kho"
                          onClick={() => { setKhoCd(null); onMoYeuCauKho(y.request_id); }}>
                          {y.ma}
                        </button>
                      ) : (
                        <span className="kcs-chuoi__kho-ma" style={{ fontSize: "14px", marginRight: "8px" }}>{y.ma}</span>
                      )}
                      <span className={`badge-sem ${ytt.cls}`}>{ytt.nhan}</span>
                    </div>
                    <div style={{ fontSize: "13px", color: "var(--ink)" }}>
                      Đề nghị <b>{num(y.sl_de_nghi)}</b> · kho đã nhận <b style={{ color: "#047857" }}>{num(y.sl_da_nhan)}</b> {nhanDonVi(y.don_vi)}
                    </div>
                    {y.tao_luc && <div className="kcs-chuoi__kho-luc" style={{ width: "100%", fontSize: "12px" }}>Tạo lúc: {ngayGio(y.tao_luc)}</div>}
                  </li>
                );
              })}
            </ul>
          </div>
        </Drawer>
      )}

      {kiem && lsx && (
        <KcsKiemForm lenh={lsx} cd={kiem} chuoi={congDoan} onClose={() => setKiem(null)}
          onSaved={(r) => {
            setKiem(null);
            const nguon = r.bao_loi_nguon ?? [];
            const soNguon = nguon.reduce((s, n) => s + n.so_loi, 0);
            const baoNguon = nguon.map((n) => `${n.ten_cong_doan} (${num(n.so_loi)})`).join(", ");
            // Công đoạn giữa chỉ ghi lỗi — không nói "đạt 0".
            const laCuoi = kiem.la_kcs_cuoi;
            setThongBao(
              (laCuoi
                ? `Đã ghi lần kiểm ${r.ten_cong_doan}: đạt ${num(r.so_dat)} · lỗi ${num(r.so_loi)}`
                : `Đã ghi lỗi ${r.ten_cong_doan}: ${num(r.so_loi)} ${nhanChang(kiem.don_vi)}`)
              + (r.so_loi - soNguon > 1e-9 ? " — đã báo tổ làm công đoạn" : "")
              + (baoNguon ? `${r.so_loi - soNguon > 1e-9 ? ";" : " —"} lỗi quy về ${baoNguon}, đã báo tổ đó` : "")
              + ".",
            );
            tai();
            onChanged();
          }} />
      )}

      <ConfirmDialog
        open={nhapKho != null}
        title="Tạo yêu cầu nhập kho"
        message={nhapKho
          ? `Đề nghị kho nhập ${num(nhapKho.con_gui_kho)} ${nhanChang(nhapKho.don_vi)} thành phẩm đã kiểm đạt của ${lsx?.ma ?? "lệnh"} (${nhapKho.ten}).`
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
