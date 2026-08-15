// Hiển thị một dòng nhật ký danh mục.
//
// **Nhãn trường KHÔNG còn dịch ở đây.** Bảng `NK_FIELD_LABELS` cũ khai theo TÊN CỘT TIẾNG ANH
// (`machine_group`, `max_width_cm`) của mấy bảng đời cũ, trong khi cột thật của màn là `loai_may`,
// `kho_max_rong` — đo ngày 15/08/2026: khớp **0/8**, tức nó chưa từng dịch được gì. Đã xoá.
//
// Nhãn giờ do BACKEND gắn, ngay tại chỗ dựng câu (`services/nhat_ky_danh_muc.NHAN`, đã bổ sung
// đủ 59 cột còn thiếu, có test gác `test_nhat_ky_nhan_du.py`). Đó là đúng tầng: một nguồn, và
// thêm cột mới mà quên nhãn thì đỏ ở backend chứ không âm thầm lọt ra màn hình.
//
// 🔴 Phần CÒN LẠI (`formatNkVal` + `NK_SUB_LABELS`) chỉ phục vụ DÒNG CŨ: audit ghi trước khi
// backend biết định dạng `dict` còn để nguyên repr Python (`{'khoan_lo': True}`). Dòng MỚI không
// bao giờ có dấu `{` nên hàm thoát ngay ở câu đầu. Đừng thêm nhãn mới vào đây.

/** Nhãn cho từng loại hành động. */
export const NK_NHAN: Record<string, string> = {
  dm_tao: "Tạo mới",
  dm_sua: "Cập nhật",
  dm_xoa: "Xoá",
};

/** "13:44 05/08/2026", riêng trong 48h gần nhất thì thay ngày bằng hôm nay/hôm qua — ba tháng
 *  sau mở lại "3 ngày trước" thì vô nghĩa, nên tuyệt đối vẫn là mặc định. */
export function nhanThoiGian(iso: string): string {
  const d = new Date(iso);
  const gio = d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", hour12: false });
  const ngay0 = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const homNay = new Date();
  const moc = new Date(homNay.getFullYear(), homNay.getMonth(), homNay.getDate()).getTime();
  const lech = Math.round((moc - ngay0) / 86400000);
  if (lech === 0) return `${gio} hôm nay`;
  if (lech === 1) return `${gio} hôm qua`;
  return `${gio} ${d.toLocaleDateString("vi-VN")}`;
}

const NK_SUB_LABELS: Record<string, string> = {
  chuan_bi_khoan: "Chuẩn bị khoan",
  so_luong_dao: "Số lượng dao",
  duong_kinh: "Đường kính",
  khoan_lo: "Khoan lỗ",
  can_mang: "Cán màng",
  be_noi: "Bế nổi",
  ep_kim: "Ép kim",
};

export function formatNkVal(valStr: string): string {
  let s = valStr.trim();
  if (s === "{}" || s === "dict()") return "Trống";

  if (s.includes("{") && s.includes("}")) {
    try {
      const jsonStr = s
        .replace(/'/g, '"')
        .replace(/True/g, 'true')
        .replace(/False/g, 'false')
        .replace(/None/g, 'null');
      const parsed = JSON.parse(jsonStr);
      if (typeof parsed === "object" && parsed !== null) {
        const keys = Object.keys(parsed);
        if (keys.length === 0) return "Trống";
        const items: string[] = [];
        for (const [k, v] of Object.entries(parsed)) {
          const kLbl = NK_SUB_LABELS[k] || k.replace(/_/g, " ");
          let vLbl = "";
          if (Array.isArray(v)) {
            vLbl = v.length > 0 ? v.join(", ") : "Chưa thiết lập";
          } else if (v === null || v === "") {
            vLbl = "Trống";
          } else if (typeof v === "boolean") {
            vLbl = v ? "Có" : "Không";
          } else {
            vLbl = String(v);
          }
          items.push(`${kLbl}: ${vLbl}`);
        }
        return items.join("; ");
      }
    } catch {
      s = s.replace(/'([^']+)':\s*\[\]/g, (_, k) => `${NK_SUB_LABELS[k] || k}: Chưa thiết lập`);
      s = s.replace(/'([^']+)':\s*'([^']*)'/g, (_, k, v) => `${NK_SUB_LABELS[k] || k}: ${v || "Trống"}`);
      s = s.replace(/'([^']+)':\s*(\d+)/g, (_, k, v) => `${NK_SUB_LABELS[k] || k}: ${v}`);
      s = s.replace(/'([^']+)':\s*(True|False)/g, (_, k, v) => `${NK_SUB_LABELS[k] || k}: ${v === "True" ? "Có" : "Không"}`);
      s = s.replace(/[{}]/g, "");
    }
  }
  return s;
}

/** Cắt "Nhãn giá-cũ → giá-mới" thành hai vế để vẽ hai cột có mũi tên ở giữa.
 *
 *  Backend đã ghép sẵn nhãn tiếng Việt vào vế trái, nên ở đây chỉ còn việc CẮT — không dịch. */
export function formatNkLine(item: string): { left: string; right?: string } {
  const parts = item.split(" → ");
  if (parts.length === 2) {
    return { left: formatNkVal(parts[0]), right: formatNkVal(parts[1]) };
  }
  return { left: formatNkVal(item) };
}
