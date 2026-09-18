// GIAI ĐOẠN 5 của bàn THỰC HIỆN SẢN XUẤT — phần còn sống sau khi gỡ tab "KCS & Kho" khỏi bàn tổ.
//
// Hai panel KcsPanel/KhoPanel cũ nằm trong drawer bàn tổ đã XOÁ 16/09/2026. Luồng KCS nay là màn
// KCS theo lệnh (`pages/kcs/`, mg 0306); lỗi KCS về tổ hiện thành chấm đỏ trên dòng công đoạn + tab
// KCS của ngăn chi tiết (§11.5) — không còn Nhận/Từ chối trách nhiệm ở hộp thư này.
//
// Còn lại ở đây: ThsxDongNhomPanel — `pages/kcs/KcsChotNhom.tsx` dựng lại ở màn KCS.
// Phân loại BTP dư (form + dòng "Nhận BTP") ĐÃ GỠ 17/09/2026. Hộp thư "Kho chờ xác nhận" nhập thành
// phẩm cũng GỠ 17/09/2026 — thành phẩm nay vào kho qua yêu cầu NHẬP thật, kho nhận ở module Kho.
import { useState } from "react";
import type { SxDongNhomDieuKien, SxDongThieuIn } from "../api/client";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";

// ============================ bảng nhãn trạng thái ==========================
const NHOM_TT: Record<string, { txt: string; cls: string }> = {
  in_production: { txt: "đang sản xuất", cls: "thsx-x-pill--adj" },
  cho_dieu_kien: { txt: "chờ điều kiện", cls: "thsx-x-pill--wait" },
  closed_full: { txt: "đã đóng đủ", cls: "thsx-x-pill--ok" },
  closed_short: { txt: "đóng thiếu", cls: "thsx-x-pill--bad" },
};

function Pill({ map, k }: { map: Record<string, { txt: string; cls: string }>; k: string }) {
  const m = map[k] ?? { txt: k, cls: "thsx-x-pill--off" };
  return <span className={`thsx-x-pill ${m.cls}`}>{m.txt}</span>;
}

// ══════════════════ THƯỞNG/PHẠT TỔ TRƯỞNG §8 (panel drawer) ══════════════════
/* `ThsxThuongToTruongPanel` GỠ 11/09/2026 (mg `0297`): bảng thưởng/phạt tổ trưởng và
   chuỗi ghi thưởng lúc đóng nhóm đã xoá — thưởng/phạt là TIỀN, mà sản xuất thôi giữ tiền. */

// ══════════════════════ ĐÓNG NHÓM §16 / §13.3 (panel drawer) ═════════════════
export function ThsxDongNhomPanel({
  dieuKien, canAssign, busy, onDongThieu,
}: {
  dieuKien: SxDongNhomDieuKien | null;
  canAssign: boolean;
  busy: boolean;
  /** Chỉ nhận ĐÚNG mặt ghi nó cần, không ôm cả `exec` — panel này còn được dùng ở màn KCS
   *  (`pages/kcs`), nơi không có controller bàn tổ để dựng đủ 30 hàm của `ThsxExec`. */
  onDongThieu: (nhomId: number, body: SxDongThieuIn) => Promise<boolean>;
}) {
  const [dongOpen, setDongOpen] = useState(false);

  if (dieuKien == null) {
    return (
      <section className="thsx-psec thsx-x">
        <div className="thsx-psec__h"><span className="thsx-psec__title"><Icon name="packageCheck" size={13} /> Đóng nhóm thành phẩm</span></div>
        <p className="thsx-note">Đang tải điều kiện đóng…</p>
      </section>
    );
  }

  const daDong = dieuKien.trang_thai === "closed_full" || dieuKien.trang_thai === "closed_short";

  async function dong() {
    if (await onDongThieu(dieuKien!.nhom_id, { expected_version: dieuKien!.version })) {
      setDongOpen(false);
    }
  }

  return (
    <section className="thsx-psec thsx-x thsx-x-dong">
      <div className="thsx-psec__h">
        <span className="thsx-psec__title"><Icon name="packageCheck" size={13} /> Đóng nhóm thành phẩm</span>
        <Pill map={NHOM_TT} k={dieuKien.trang_thai} />
      </div>

      <ul className="thsx-x-check">
        {dieuKien.dieu_kien.map((d) => (
          <li key={d.ma} className={`thsx-x-check__it${d.dat ? " is-ok" : ""}`}>
            <Icon name={d.dat ? "check" : "clock"} size={14} />
            <span className="thsx-x-check__ten">{d.ten}</span>
            {!d.dat && d.chi_tiet && <span className="thsx-x-check__ct">{d.chi_tiet}</span>}
          </li>
        ))}
      </ul>

      {daDong ? (
        <p className="thsx-note thsx-note--ok">
          <Icon name="check" size={13} /> Nhóm đã {dieuKien.trang_thai === "closed_full" ? "đóng đủ" : "đóng thiếu"}.
        </p>
      ) : dieuKien.du_dong_du ? (
        <p className="thsx-note thsx-note--ok">
          <Icon name="check" size={13} /> Đủ điều kiện — nhóm tự đóng đủ.
        </p>
      ) : (
        <>
          <p className="thsx-note">
            {dieuKien.du_dong_thieu
              ? "Chưa đủ mục tiêu hoặc còn việc dở, nhưng các điều kiện toàn vẹn đã sạch — có thể đóng thiếu."
              : "Chưa đủ điều kiện đóng. Xử lý các mục còn thiếu ở trên."}
          </p>
          {canAssign && dieuKien.du_dong_thieu && (
            !dongOpen ? (
              <div className="thsx-x-act thsx-x-act--row">
                <Button variant="secondary" onClick={() => setDongOpen(true)} disabled={busy}>
                  <Icon name="packageCheck" size={13} /> Đóng thiếu nhóm
                </Button>
              </div>
            ) : (
              <div className="thsx-x-form thsx-x-form--sub">
                <p className="thsx-x-hint">Đóng thiếu sẽ báo ngay cho Sale và Kế hoạch SX.</p>
                <div className="thsx-x-act">
                  <Button variant="ghost" onClick={() => setDongOpen(false)} disabled={busy}>Huỷ</Button>
                  <Button variant="accent" onClick={dong} disabled={busy}>
                    <Icon name="check" size={13} /> Xác nhận đóng thiếu
                  </Button>
                </div>
              </div>
            )
          )}
        </>
      )}
    </section>
  );
}
