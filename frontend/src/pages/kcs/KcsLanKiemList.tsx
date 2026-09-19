// Danh sách các LẦN KIỂM của một công đoạn (mới nhất trước) — dùng chung ở màn KCS (dưới mỗi công
// đoạn trong chuỗi) và mục "Kết quả KCS" trong ngăn chi tiết của bàn tổ. Chỉ hiển thị — không có nút
// "Đã xem": mở tab KCS của ngăn chi tiết là tổ đã xem (18/09/2026, xem `ThsxKetQuaKcs`).
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
  lanKiem, checklist = [],
}: {
  lanKiem: SxKcsLanKiem[];
  /** Snapshot tiêu chí của công đoạn — để đổi `thu_tu` trong kết quả ra tên tiêu chí. */
  checklist?: SxKcsChiTietTieuChi[];
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
            <li key={lk.id} className={`kcs-lk__it ${lk.so_loi > 0 ? "kcs-lk__it--loi" : "kcs-lk__it--dat"}`}>
              <div className="kcs-lk__dau">
                <div className="kcs-lk__dau-main">
                  <span className={`badge-sem ${kl.cls}`}>{kl.nhan}</span>
                  <div className="kcs-lk__so">
                    <span className="kcs-lk__chip kcs-lk__chip--dat">đạt <b>{num(lk.so_dat)}</b></span>
                    <span className="kcs-lk__chip kcs-lk__chip--loi">lỗi <b>{num(lk.so_loi)}</b> {dv}</span>
                  </div>
                </div>
                <span className="kcs-lk__ai">
                  <Icon name="users" size={12} className="kcs-lk__ai-ic" />
                  <span>{lk.nguoi_kiem ?? "—"} · {ngayGio(lk.luc)}</span>
                </span>
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
              {lk.ghi_chu && (
                <div className="kcs-lk__note-box">
                  <Icon name="help" size={13} className="kcs-lk__note-ic" />
                  <p className="kcs-lk__phu">Ghi chú: {lk.ghi_chu}</p>
                </div>
              )}
              {lk.loi.map((l) => (
                <div key={l.id} className="kcs-lk__loi">
                  <div className="kcs-lk__loi-dau">
                    <div className="kcs-lk__loi-info">
                      <Icon name="alert" size={14} className="kcs-lk__loi-ic" />
                      <span className="kcs-lk__loi-mota">{l.mo_ta || "Lỗi"}</span>
                    </div>
                    <div className="kcs-lk__loi-act">
                      <span className={`kcs-lk__loi-tt ${l.da_xem_luc ? "is-daxem" : "is-chua"}`}>
                        {l.da_xem_luc
                          ? `Tổ đã xem${l.nguoi_xem ? ` (${l.nguoi_xem})` : ""} · ${ngayGio(l.da_xem_luc)}`
                          : "Tổ chưa xem"}
                      </span>
                    </div>
                  </div>
                  {l.anh.length > 0 && (
                    <div className="kcs-lk__loi-anh">
                      <ul className="thsx-tep__ds">
                        {l.anh.map((a) => (
                          <DongTep key={a.id} onXem={setXem}
                            t={{ ten_tep: a.file_name, file_url: a.file_url, content_type: a.file_type ?? null }}
                            meta={`${ngayGio(lk.luc)}${lk.nguoi_kiem ? ` · ${lk.nguoi_kiem}` : ""}`} />
                        ))}
                      </ul>
                    </div>
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
