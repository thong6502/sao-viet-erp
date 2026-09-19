// Nội dung tab "KCS" trong ngăn chi tiết của Bàn tổ (KCS theo lệnh, mg 0306) — CHỈ LỖI tổ chịu ở công
// đoạn này: mô tả, số, ảnh, ai bắt lúc nào (19/09/2026: *"chỉ hiển thị lỗi thôi, không hiển thị đạt"*).
// KCS ở công đoạn giữa chỉ ghi lỗi nên không bày lần kiểm đạt, số đạt hay tiêu chí. Riêng công đoạn
// CUỐI (KCS kiểm đạt để nhập kho) có thêm một dòng: KCS đạt / số tốt tổ ghi · đã đề nghị nhập kho.
// Không có lỗi thì nói một câu, không để tab trắng.
//
// Tự gọi API (`GET /work-items/{id}/kcs`) và nạp lại theo `kcsTick` (SSE + sau mỗi lần ghi của bàn).
//
// MỞ TAB LÀ TỔ ĐÃ XEM (chủ xưởng 18/09/2026: *"mở tab là tính đã xem"*) — không còn nút "Đã xem".
// Nút đó sinh ra khi lỗi nằm thành dòng trong hộp "Chờ tổ bạn xác nhận" (chỉ thấy tiêu đề); hộp gỡ
// 17/09 thì người mở tab đã thấy đủ mô tả + ảnh, bắt bấm thêm là thừa. Chỉ lỗi trong `loiChoXem` mới
// được ghi — danh sách máy chủ đã lọc theo quyền Xác nhận sản lượng của tổ, nên thợ mở tab xem không
// làm "tổ đã xem"; FE không tự suy quyền lần hai.
//
// Lỗi KCS bắt ở công đoạn SAU nhưng quy về công đoạn này (19/09/2026) nằm chung danh sách, gắn "Bắt ở
// …" — số của công đoạn này không đổi, tổ xem để biết trách nhiệm; mở tab cũng tính là đã xem.
import { useEffect, useRef, useState } from "react";
import { ApiError, api, type SxKcsCongViec } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Icon } from "../components/Icons";
import { KcsLoiCuaTo, loiCuaTo } from "./kcs/KcsLanKiemList";
import { num } from "./keHoachSxShared";
import { nhanDonVi } from "./lsxBuoc";
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
      .catch((e) => { if (alive) setLoi(e instanceof ApiError ? e.message : "Không tải được lỗi KCS."); });
    return () => { alive = false; };
  }, [token, congViecId, kcsTick]);

  useEffect(() => {
    // `data` còn của công đoạn trước khi vừa đổi công đoạn — chờ bản của công đoạn đang mở.
    if (!data || data.cong_viec_id !== congViecId || !loiChoXem || !onXem) return;
    const ids = [...data.lan_kiem, ...(data.lan_kiem_buoc_sau ?? [])].flatMap((lk) => lk.loi)
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
          <Icon name="alert" size={14} />
          <span className="thsx-psec__title">Lỗi KCS</span>
        </div>
        <p className="thsx-note">{loi}</p>
      </section>
    );
  }
  const dong = data && data.cong_viec_id === congViecId ? loiCuaTo(congViecId, data.lan_kiem, data.lan_kiem_buoc_sau) : [];
  const cuoi = data && data.cong_viec_id === congViecId ? data.cuoi : null;
  const tong = dong.reduce((t, d) => t + d.l.so_luong, 0);
  // Cùng một đơn vị thì kèm đơn vị vào tổng; lẫn đơn vị (lỗi bắt ở nhiều bước) thì chỉ đếm số lỗi.
  const dv = new Set(dong.map((d) => d.l.don_vi ?? d.lk.don_vi));
  const nhanTong = dv.size === 1
    ? `${tong.toLocaleString("vi-VN")} ${nhanDonVi([...dv][0])}`
    : `${dong.length} lỗi`;

  return (
    <section className="thsx-psec">
      <div className="thsx-psec__h">
        <Icon name="alert" size={14} />
        <span className="thsx-psec__title">Lỗi KCS</span>
        {dong.length > 0 && <span className="kcs-bs__tong">{nhanTong}</span>}
      </div>
      {cuoi && (
        <p className="kcs-bs__cuoi">
          KCS đạt <b>{num(cuoi.dat)}</b> / tổ ghi tốt <b>{num(cuoi.tot)}</b> {nhanDonVi(cuoi.don_vi)}
          {" · "}đã đề nghị nhập kho <b>{num(cuoi.da_de_nghi_kho)}</b>
        </p>
      )}
      {dong.length > 0
        ? <KcsLoiCuaTo congViecId={congViecId} dong={dong} />
        : <p className="thsx-note">{data ? "KCS chưa ghi lỗi nào cho công đoạn này." : "Đang tải lỗi KCS…"}</p>}
    </section>
  );
}
