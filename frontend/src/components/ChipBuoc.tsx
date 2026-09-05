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
    // NƠI LÀM của bước thuê ngoài nay là MÁY của nhà thầu (khai trong danh mục Máy, tên kèm hậu
    // tố "thuê ngoài – <nhà in>") — cột "Thực hiện" của bảng/thẻ đã bày tên máy đó. Nên chip chỉ
    // còn nói LOẠI bước, y như "Máy"/"Tổ", và KHÔNG kêu "chưa chọn nơi làm" nữa: ô nhập nhà cung
    // cấp đã gỡ khỏi màn kế hoạch, giữ lời kêu đó thì mọi bước đều đỏ vĩnh viễn.
    const cu = (nha_cung_cap ?? "").trim();   // dữ liệu CŨ còn sót thì vẫn bày ra
    return (
      <span className="chip-buoc chip-buoc--ngoai">
        {cu ? `Ngoài · ${cu}` : "Thuê ngoài"}
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

/** Khối `nhan` mà backend gắn lên mỗi bước (Kanban · Theo máy · Theo ca · KCS · Kho). */
export interface NhanBuoc {
  loai_buoc?: string | null;
  nha_cung_cap?: string | null;
  khuon_ma?: string | null;
  khuon_so_ke?: string | null;
  khuon_tinh_trang?: string | null;
  khuon_ngay_ve?: string | null;
  khuon_da_nhan?: boolean;
}

/** `nhan` → props của `<ChipKhuon>`. Một chỗ đổi tên field là mọi màn theo — bốn màn tự trải
 *  `nhan.khuon_*` ra là bốn chỗ để quên một field, đúng lối hỏng mà hai chip này sinh ra để chặn. */
export function nhanKhuon(n?: NhanBuoc | null): KhuonChip {
  return {
    ma: n?.khuon_ma ?? null,
    so_ke: n?.khuon_so_ke ?? null,
    tinh_trang: n?.khuon_tinh_trang ?? null,
    ngay_ve_du_kien: n?.khuon_ngay_ve ?? null,
    da_nhan: n?.khuon_da_nhan ?? false,
  };
}

/** Một chữ NGẮN cho `title` của thanh Gantt hẹp (Theo máy) — chỗ không đủ bề ngang cho chip thật,
 *  nhưng vẫn phải nói ra được nhãn khi rê chuột. Rỗng nếu bước không có gì để nói. */
export function nhanTomTat(n?: NhanBuoc | null): string {
  const ra: string[] = [];
  if (n?.loai_buoc === "thue_ngoai") {
    const cu = (n.nha_cung_cap ?? "").trim();
    ra.push(cu ? `Ngoài · ${cu}` : "Thuê ngoài");
  }
  if (n?.khuon_ma) {
    const ng = ngayNgan(n.khuon_ngay_ve);
    ra.push(
      n.khuon_da_nhan
        ? `${n.khuon_ma} · đã nhận`
        : n.khuon_tinh_trang === "dang_dat_lam"
          ? `${n.khuon_ma} · ${ng ? `dự kiến ${ng}` : "chưa có ngày"}`
          : `${n.khuon_ma}${(n.khuon_so_ke ?? "").trim() ? ` · ${n.khuon_so_ke}` : ""}`,
    );
  }
  return ra.join(" · ");
}
