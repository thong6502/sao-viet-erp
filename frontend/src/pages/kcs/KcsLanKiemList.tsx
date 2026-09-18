// Danh sách các LẦN KIỂM của một công đoạn (mới nhất trước) — dùng chung ở màn KCS (dưới mỗi công
// đoạn trong chuỗi) và mục "Kết quả KCS" trong ngăn chi tiết của bàn tổ. Chỉ hiển thị; nút "Đã xem"
// chỉ bày khi nơi gọi truyền `onDaXem` (bàn tổ, người Xác nhận sản lượng của tổ bị báo lỗi).
//
// Ảnh lỗi bày như "Tệp của lệnh" (mỗi ảnh một dòng, bấm là mở hộp xem trước ngay trên trang) — mở tab
// mới thì mất ngăn đang xem. Dòng phụ là giờ + người kiểm: ảnh chỉ tải lên cùng lúc ghi lần kiểm, máy
// chủ không lưu cỡ tệp.
import { useState } from "react";
import { createPortal } from "react-dom";
import { type SxKcsChiTietTieuChi, type SxKcsLanKiem } from "../../api/client";
import { XemTruoc } from "../../components/DinhKemTep";
import { Icon } from "../../components/Icons";
import type { TepXem } from "../../components/tepDinhKem";
import { ngayGio, num } from "../keHoachSxShared";
import { nhanDonVi } from "../lsxBuoc";
import { DongTep } from "../ThsxDongTep";
import { KCS_KET_LUAN } from "./kcsNhan";
import "../thuc-hien-sx.css";

export function KcsLanKiemList({
  lanKiem, checklist = [], busy = false, onDaXem,
}: {
  lanKiem: SxKcsLanKiem[];
  /** Snapshot tiêu chí của công đoạn — để đổi `thu_tu` trong kết quả ra tên tiêu chí. */
  checklist?: SxKcsChiTietTieuChi[];
  busy?: boolean;
  onDaXem?: (loiId: number) => void;
}) {
  const [xem, setXem] = useState<TepXem | null>(null);
  if (lanKiem.length === 0) return <p className="kcs-lk__trong">Chưa có lần kiểm nào.</p>;
  const tenTc = new Map(checklist.map((t) => [t.thu_tu, t.ten ?? t.ma ?? `Tiêu chí #${t.thu_tu}`]));
  return (
    <>
      <ul className="kcs-lk">
        {lanKiem.map((lk) => {
          const kl = KCS_KET_LUAN[lk.ket_luan] ?? { nhan: lk.ket_luan, cls: "badge-sem--muted" };
          const dv = nhanDonVi(lk.don_vi);
          const soDat = lk.checklist.filter((c) => c.dat).length;
          // Không đạt lên đầu, còn lại giữ thứ tự tiêu chí. Mỗi tiêu chí một dòng: tên tiêu chí có thể
          // tự chứa dấu phẩy nên không nối chung một câu được.
          const tieuChi = [...lk.checklist].sort((a, b) => Number(a.dat) - Number(b.dat) || a.thu_tu - b.thu_tu);
          return (
            <li key={lk.id} className="kcs-lk__it">
              <div className="kcs-lk__dau">
                <span className={`badge-sem ${kl.cls}`}>{kl.nhan}</span>
                <span className="kcs-lk__so">
                  đạt <b>{num(lk.so_dat)}</b> · lỗi <b>{num(lk.so_loi)}</b> {dv}
                </span>
                <span className="kcs-lk__ai">{lk.nguoi_kiem ?? "—"} · {ngayGio(lk.luc)}</span>
              </div>
              {lk.checklist.length > 0 && (
                <div className="kcs-lk__tc">
                  <p className="kcs-lk__phu">Tiêu chí: {soDat}/{lk.checklist.length} đạt</p>
                  <ul className="kcs-lk__tc-ds">
                    {tieuChi.map((c) => (
                      <li key={c.thu_tu} className={`kcs-lk__tc-it${c.dat ? "" : " is-khong"}`}>
                        <Icon name={c.dat ? "check" : "x"} size={12} className="kcs-lk__tc-ic" />
                        <span className="kcs-lk__tc-ten">{tenTc.get(c.thu_tu) ?? `Tiêu chí #${c.thu_tu}`}</span>
                        <span className="kcs-lk__tc-kq">{c.dat ? "Đạt" : "Không đạt"}</span>
                        {c.ghi_chu && <span className="kcs-lk__tc-gc">{c.ghi_chu}</span>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {lk.ghi_chu && <p className="kcs-lk__phu">Ghi chú: {lk.ghi_chu}</p>}
              {lk.loi.map((l) => (
                <div key={l.id} className="kcs-lk__loi">
                  <div className="kcs-lk__loi-dau">
                    <Icon name="alert" size={13} />
                    <span className="kcs-lk__loi-mota">{l.mo_ta || "Lỗi"}</span>
                    <span className="kcs-lk__loi-tt">
                      {l.da_xem_luc
                        ? `Tổ đã xem${l.nguoi_xem ? ` (${l.nguoi_xem})` : ""} · ${ngayGio(l.da_xem_luc)}`
                        : "Tổ chưa xem"}
                    </span>
                    {!l.da_xem_luc && onDaXem && (
                      <button type="button" className="btn btn--ghost btn--sm" disabled={busy}
                        onClick={() => onDaXem(l.id)}>
                        <Icon name="check" size={12} /> Đã xem
                      </button>
                    )}
                  </div>
                  {l.anh.length > 0 && (
                    <ul className="thsx-tep__ds">
                      {l.anh.map((a) => (
                        <DongTep key={a.id} onXem={setXem}
                          t={{ ten_tep: a.file_name, file_url: a.file_url, content_type: a.file_type ?? null }}
                          meta={`${ngayGio(lk.luc)}${lk.nguoi_kiem ? ` · ${lk.nguoi_kiem}` : ""}`} />
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </li>
          );
        })}
      </ul>
      {/* Ra thẳng body: ngăn chi tiết bàn tổ có transform trượt vào nên `position: fixed` bị nhốt trong ngăn. */}
      {xem && createPortal(<XemTruoc tep={xem} onDong={() => setXem(null)} />, document.body)}
    </>
  );
}
