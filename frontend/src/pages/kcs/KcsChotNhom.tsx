// CHỐT NHÓM ở màn KCS — cửa vào của "Đóng thiếu nhóm" (§13.3): nhóm làm xong mà KCS đạt hụt mục
// tiêu (960/1.000), hoặc còn việc dở không làm nữa, phải có người đóng lại, nếu không lệnh treo.
// CHỈ trưởng phòng ban "Tổ KCS" (máy chủ gác `gate_truong_kcs`). Nhóm đạt đủ mục tiêu thì tự đóng đủ.
//
// "Phân loại BTP dư" từng nằm ở đây — ĐÃ GỠ 17/09/2026 (lot chỉ ghi nhận, không nối tồn kho thật).
//
// KCS theo lệnh (mg 0306): khối này nằm dưới CHUỖI CÔNG ĐOẠN của một lệnh, nên nhận thẳng nhóm của
// lệnh đó — không còn tự gom nhóm từ danh sách bước KCS của một tổ.
//
// Component tự gọi API và chỉ mượn lại phần hiển thị `ThsxDongNhomPanel`.
import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type SxDongNhomDieuKien, type SxDongThieuIn } from "../../api/client";
import { useAuth } from "../../auth/useAuth";
import { ThsxDongNhomPanel } from "../ThsxG5";
import "../thuc-hien-sx.css";

export function KcsChotNhom({
  nhomId, nhan, canDong, eventTick, onDone,
}: {
  nhomId: number;
  nhan: string;
  /** Đóng thiếu nhóm — trưởng phòng ban "Tổ KCS". */
  canDong: boolean;
  /** Bump khi có sự kiện SX (SSE) — tải lại điều kiện của nhóm. */
  eventTick?: number;
  onDone: () => void;
}) {
  const { token } = useAuth();
  const [dieuKien, setDieuKien] = useState<SxDongNhomDieuKien | null>(null);
  const [loi, setLoi] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const tai = useCallback(() => {
    if (!token) return;
    api.sanXuat.dieuKienDongNhom(token, nhomId)
      .then((dk) => { setDieuKien(dk); setLoi(null); })
      .catch((e) => setLoi(e instanceof ApiError ? e.message : "Không đọc được điều kiện đóng nhóm."));
  }, [token, nhomId]);

  useEffect(() => { tai(); }, [tai, eventTick]);

  async function onDongThieu(id: number, body: SxDongThieuIn): Promise<boolean> {
    if (!token || busy) return false;
    setBusy(true);
    setLoi(null);
    try {
      await api.sanXuat.dongThieu(token, id, body);
      tai();
      onDone();
      return true;
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không thực hiện được.");
      return false;
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="kcs-section">
      <h2>Chốt nhóm <span className="kcs-chot__sl">{nhan}</span></h2>
      <p className="kcs-chot__hint">
        KCS đạt đủ mục tiêu thì nhóm tự đóng đủ. Nhóm giao hụt thì chốt đóng thiếu tại đây.
      </p>
      <div className="kcs-chot__than">
        {loi && <div className="banner banner--error" role="alert"><span>{loi}</span></div>}
        <ThsxDongNhomPanel dieuKien={dieuKien} canAssign={canDong} busy={busy}
          onDongThieu={onDongThieu} />
      </div>
    </section>
  );
}
