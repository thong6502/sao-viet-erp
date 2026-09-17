// Nội dung tab "KCS" trong ngăn chi tiết của Bàn tổ (KCS theo lệnh, mg 0306) — tổ xem KCS đã kiểm
// công đoạn này mấy lần, đạt/lỗi bao nhiêu, ảnh lỗi, ai kiểm lúc nào. Đứng thành tab riêng nên chưa
// kiểm lần nào vẫn phải nói ra, không được để tab trắng.
//
// Tự gọi API (`GET /work-items/{id}/kcs`) và nạp lại theo `kcsTick` (SSE + sau mỗi lần ghi của bàn).
// Nút "Đã xem" chỉ bày cho lỗi đang nằm trong hộp "Chờ tổ bạn xác nhận" của người xem — danh sách đó
// máy chủ đã lọc theo quyền Xác nhận sản lượng của tổ, nên FE không tự suy quyền lần hai.
import { useEffect, useState } from "react";
import { ApiError, api, type SxKcsCongViec } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Icon } from "../components/Icons";
import { KcsLanKiemList } from "./kcs/KcsLanKiemList";
import "./kcs/kcs.css";

export function ThsxKetQuaKcs({
  congViecId, kcsTick, loiChoXem, busy = false, onDaXem,
}: {
  congViecId: number;
  kcsTick?: number;
  /** Id các lỗi KCS đang chờ người xem bấm "Đã xem" (từ hộp "Chờ tổ bạn xác nhận"). */
  loiChoXem?: ReadonlySet<number>;
  busy?: boolean;
  onDaXem?: (loiId: number) => void;
}) {
  const { token } = useAuth();
  const [data, setData] = useState<SxKcsCongViec | null>(null);
  const [loi, setLoi] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let alive = true;
    api.sanXuat.kcsCongViec(token, congViecId)
      .then((r) => { if (alive) { setData(r); setLoi(null); } })
      .catch((e) => { if (alive) setLoi(e instanceof ApiError ? e.message : "Không tải được kết quả KCS."); });
    return () => { alive = false; };
  }, [token, congViecId, kcsTick]);

  if (loi) {
    return (
      <section className="thsx-psec">
        <div className="thsx-psec__h">
          <Icon name="shield" size={14} />
          <span className="thsx-psec__title">Kết quả KCS</span>
        </div>
        <p className="thsx-note">{loi}</p>
      </section>
    );
  }
  if (!data || data.lan_kiem.length === 0) {
    return (
      <section className="thsx-psec">
        <div className="thsx-psec__h">
          <Icon name="shield" size={14} />
          <span className="thsx-psec__title">Kết quả KCS</span>
        </div>
        <p className="thsx-note">{data ? "KCS chưa kiểm công đoạn này lần nào." : "Đang tải kết quả KCS…"}</p>
      </section>
    );
  }

  const coLoiChoXem = !!loiChoXem && data.lan_kiem.some((lk) => lk.loi.some((l) => loiChoXem.has(l.id)));
  const tongDat = data.lan_kiem.reduce((s, lk) => s + lk.so_dat, 0);
  const tongLoi = data.lan_kiem.reduce((s, lk) => s + lk.so_loi, 0);

  return (
    <section className="thsx-psec">
      <div className="thsx-psec__h">
        <Icon name="shield" size={14} />
        <span className="thsx-psec__title">
          Kết quả KCS ({data.lan_kiem.length} lần · đạt {tongDat.toLocaleString("vi-VN")} · lỗi {tongLoi.toLocaleString("vi-VN")})
        </span>
      </div>
      <KcsLanKiemList lanKiem={data.lan_kiem} checklist={data.checklist} busy={busy}
        onDaXem={coLoiChoXem ? onDaXem : undefined} />
    </section>
  );
}
