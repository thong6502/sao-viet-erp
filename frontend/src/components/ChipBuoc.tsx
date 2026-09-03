// HAI CHIP DÙNG CHUNG cho mọi màn có mặt một bước sản xuất — từ phiếu tính giá tới lúc lệnh xong.
//
// Vì sao phải là MỘT component chứ không phải mỗi màn tự vẽ: trước 04/09/2026 mỗi màn tự quyết
// định lại nhãn từ một dữ liệu KHÁC NHAU — màn Kế hoạch đọc `loai_buoc`, Gantt xếp lịch suy từ tên
// nhà cung cấp, bốn tab Theo dõi SX không đọc gì cả. Ba cách suy ba kết quả, nên nhãn đứt quãng
// giữa đường: bước đã gán Thuê ngoài mà chưa điền nơi làm thì tới Gantt là mất dấu.
//
// Nguyên tắc: nhãn là DỮ LIỆU đi theo bước, không phải thứ mỗi màn tự đoán lấy.
import "./chip-buoc.css";

const NHAN_LOAI: Record<string, string> = { may: "Máy", to: "Tổ" };

export function ChipLoaiBuoc({
  loai_buoc,
  nha_cung_cap,
}: {
  loai_buoc?: string | null;
  nha_cung_cap?: string | null;
}) {
  if (!loai_buoc) return null;
  if (loai_buoc === "thue_ngoai") {
    const noi = (nha_cung_cap ?? "").trim();
    // Điều kiện hiện chip CHỈ là loại bước. Chưa điền nơi làm thì đổi tone chứ KHÔNG giấu chip —
    // giấu đi là đúng cái làm nhãn biến mất giữa đường ở bản trước, mà chỗ thiếu dữ liệu lại là
    // chỗ cần nhìn thấy nhất.
    return (
      <span className={`chip-buoc chip-buoc--${noi ? "ngoai" : "canhbao"}`}>
        {noi ? `Ngoài · ${noi}` : "Ngoài · chưa chọn nơi làm"}
      </span>
    );
  }
  const nhan = NHAN_LOAI[loai_buoc];
  if (!nhan) return null;
  return <span className={`chip-buoc chip-buoc--${loai_buoc}`}>{nhan}</span>;
}

export interface KhuonChip {
  ma?: string | null;
  ten?: string | null;
  so_ke?: string | null;
  tinh_trang?: string | null;
  /** ISO `yyyy-mm-dd`. Mọi nguồn backend `.isoformat()` trước khi trả. */
  ngay_ve_du_kien?: string | null;
  /** Tổ đã tích "đã nhận khuôn" — chỉ có nghĩa ở các màn xưởng. */
  da_nhan?: boolean;
}

/** `yyyy-mm-dd` → `dd/mm`. Rỗng / sai định dạng → chuỗi rỗng, KHÔNG bịa ngày. */
function ngayNgan(v?: string | null): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(v ?? ""));
  return m ? `${m[3]}/${m[2]}` : "";
}

export function ChipKhuon({
  can_khuon,
  khuon,
}: {
  can_khuon?: boolean;
  khuon?: KhuonChip | null;
}) {
  if (!can_khuon) return null;
  // Nhãn dựng thành MỘT chuỗi rồi mới render: ghép `{ma}{" · "}{ke}` trong JSX đẻ ra nhiều text
  // node, chuỗi hiện đúng nhưng máy đọc màn hình (và cả test) thấy ba mảnh rời.
  let cls = "co";
  let chu: string;
  if (!khuon || !khuon.ma) {
    // Bước CÓ yêu cầu dụng cụ mà chưa trỏ dao nào là trạng thái phải NHÌN THẤY, không phải chỗ
    // trống để im lặng: đó chính là thứ chặn ở cửa "Sẵn sàng lập kế hoạch".
    cls = "thieu";
    chu = "chưa chốt khuôn";
  } else if (khuon.da_nhan) {
    cls = "nhan";
    chu = `${khuon.ma} · đã nhận`;
  } else if (khuon.tinh_trang === "dang_dat_lam") {
    const ng = ngayNgan(khuon.ngay_ve_du_kien);
    cls = "cho";
    chu = ng ? `${khuon.ma} · dự kiến ${ng}` : `${khuon.ma} · chưa có ngày`;
  } else {
    const ke = (khuon.so_ke ?? "").trim();
    chu = ke ? `${khuon.ma} · ${ke}` : String(khuon.ma);
  }
  return (
    <span className={`chip-khuon chip-khuon--${cls}`}>
      <span aria-hidden="true">🔧</span>
      {chu}
    </span>
  );
}
