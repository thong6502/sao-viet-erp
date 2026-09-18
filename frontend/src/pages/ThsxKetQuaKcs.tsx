// Nội dung tab "KCS" trong ngăn chi tiết của Bàn tổ (KCS theo lệnh, mg 0306) — tổ xem KCS đã kiểm
// công đoạn này mấy lần, đạt/lỗi bao nhiêu, ảnh lỗi, ai kiểm lúc nào. Đứng thành tab riêng nên chưa
// kiểm lần nào vẫn phải nói ra, không được để tab trắng.
//
// Tự gọi API (`GET /work-items/{id}/kcs`) và nạp lại theo `kcsTick` (SSE + sau mỗi lần ghi của bàn).
//
// MỞ TAB LÀ TỔ ĐÃ XEM (chủ xưởng 18/09/2026: *"mở tab là tính đã xem"*) — không còn nút "Đã xem".
// Nút đó sinh ra khi lỗi nằm thành dòng trong hộp "Chờ tổ bạn xác nhận" (chỉ thấy tiêu đề); hộp gỡ
// 17/09 thì người mở tab đã thấy đủ mô tả + ảnh, bắt bấm thêm là thừa. Chỉ lỗi trong `loiChoXem` mới
// được ghi — danh sách máy chủ đã lọc theo quyền Xác nhận sản lượng của tổ, nên thợ mở tab xem không
// làm "tổ đã xem"; FE không tự suy quyền lần hai.
import { useEffect, useRef, useState } from "react";
import { ApiError, api, type SxKcsCongViec } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Icon } from "../components/Icons";
import { KcsLanKiemList } from "./kcs/KcsLanKiemList";
import "./kcs/kcs.css";

export function ThsxKetQuaKcs({
  congViecId, kcsTick, loiChoXem, onXem,
}: {
  congViecId: number;
  kcsTick?: number;
  /** Id các lỗi KCS người đang mở còn phải xem (từ `GET /teams/{id}/cho-xac-nhan`). */
  loiChoXem?: ReadonlySet<number>;
  /** Ghi "tổ đã xem" cho các lỗi vừa bày ra trong tab. */
  onXem?: (loiIds: number[]) => void;
}) {
  const { token } = useAuth();
  const [data, setData] = useState<SxKcsCongViec | null>(null);
  const [loi, setLoi] = useState<string | null>(null);
  // Lỗi đã gửi "đã xem" trong lần mở tab này — dữ liệu có thể nạp lại (SSE) trước khi danh sách chờ
  // kịp cập nhật, đừng gửi lặp. Máy chủ bấm lại cũng không đổi gì, đây chỉ để khỏi tốn lượt gọi.
  const daGui = useRef(new Set<number>());

  useEffect(() => {
    if (!token) return;
    let alive = true;
    api.sanXuat.kcsCongViec(token, congViecId)
      .then((r) => { if (alive) { setData(r); setLoi(null); } })
      .catch((e) => { if (alive) setLoi(e instanceof ApiError ? e.message : "Không tải được kết quả KCS."); });
    return () => { alive = false; };
  }, [token, congViecId, kcsTick]);

  useEffect(() => {
    // `data` còn của công đoạn trước khi vừa đổi công đoạn — chờ bản của công đoạn đang mở.
    if (!data || data.cong_viec_id !== congViecId || !loiChoXem || !onXem) return;
    const ids = data.lan_kiem.flatMap((lk) => lk.loi)
      .filter((l) => !l.da_xem_luc && loiChoXem.has(l.id) && !daGui.current.has(l.id))
      .map((l) => l.id);
    if (ids.length === 0) return;
    ids.forEach((id) => daGui.current.add(id));
    onXem(ids);
  }, [data, congViecId, loiChoXem, onXem]);

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

  const tongDat = data.lan_kiem.reduce((s, lk) => s + lk.so_dat, 0);
  const tongLoi = data.lan_kiem.reduce((s, lk) => s + lk.so_loi, 0);

  return (
    <section className="thsx-psec">
      <div className="thsx-psec__h kcs-hdr">
        <div className="kcs-hdr__main">
          <Icon name="shield" size={15} className="kcs-hdr__icon" />
          <span className="thsx-psec__title">Kết quả KCS</span>
        </div>
        <div className="kcs-hdr__chips">
          <span className="kcs-hdr__chip kcs-hdr__chip--lan">{data.lan_kiem.length} lần</span>
          <span className="kcs-hdr__chip kcs-hdr__chip--dat">đạt {tongDat.toLocaleString("vi-VN")}</span>
          {tongLoi > 0 && (
            <span className="kcs-hdr__chip kcs-hdr__chip--loi">lỗi {tongLoi.toLocaleString("vi-VN")}</span>
          )}
        </div>
      </div>
      <KcsLanKiemList lanKiem={data.lan_kiem} checklist={data.checklist} />
    </section>
  );
}
