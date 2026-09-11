// Băng "Sản lượng của tôi" — chỉ hiện cho THỢ (spec 2026-09-11 §6, mục 3).
//
// Thợ cần một con số trả lời được "tháng này tôi làm được bao nhiêu" mà không phải chờ bảng lương.
// KHÔNG có ô tiền ở đây: sản xuất chỉ ghi SỐ LƯỢNG, quy ra tiền là việc của kế toán lương.
//
// Gộp theo ĐƠN VỊ chứ không cộng thành một số: một tháng thợ có thể vừa chạy bước đếm bằng tờ vừa
// chạy bước đếm bằng cái — cộng chung hai thứ đó ra một con số vô nghĩa.
import type { SxSanLuongCuaToi } from "../api/client";
import { num } from "./keHoachSxShared";
import { nhanDonVi } from "./lsxBuoc";

export function ThsxSanLuongCuaToi({ data }: { data: SxSanLuongCuaToi | null }) {
  // Chưa nạp xong thì KHÔNG vẽ băng rỗng: một khung xám nhấp nháy rồi mới có số đọc thành lỗi.
  if (!data) return null;
  const co = data.theo_don_vi.length > 0;
  return (
    <section className="thsx-slt" aria-label="Sản lượng của tôi">
      <span className="thsx-slt__nhan">
        Sản lượng của tôi · tháng {data.thang}/{data.nam}
      </span>
      {co ? (
        <>
          <span className="thsx-slt__so">
            {data.theo_don_vi.map((d) => (
              <span key={d.don_vi ?? "—"} className="thsx-slt__dv">
                <b className="thsx-num">{num(d.tong)}</b>
                {d.don_vi ? ` ${nhanDonVi(d.don_vi)}` : ""}
              </span>
            ))}
          </span>
          <span className="thsx-slt__me thsx-num">{data.so_me} mẻ</span>
        </>
      ) : (
        // Nói rõ vì sao trống: mẻ đã ghi nhưng tổ trưởng chưa CHỐT bản chia thì chưa vào luỹ kế —
        // hiện "0" trống trơn thì thợ tưởng mình chưa làm gì.
        <span className="thsx-slt__trong">
          Tháng này chưa có mẻ nào được chốt phân chia.
        </span>
      )}
    </section>
  );
}
