// Cảnh báo TRÊN TỪNG DÒNG routing (`loiDong`) — đóng đinh vụ "đứt đơn vị" giả 16/08/2026.
//
// Bối cảnh: bước ghi kẽm khai `m² → bài in` (hợp lệ từ 11/08/2026, khi công đoạn được khai đơn vị
// tự do từ danh mục). Luật cũ lấy "bước trước gần nhất CÓ khai đơn vị" nên vớ đúng bước chế bản
// rồi so `bài in` với `tờ` — mọi lệnh có chế bản đều đeo cảnh báo, cả 3 lệnh trên DB dev.
//
// Vì sao đáng một file test riêng: cảnh báo giả không làm gãy gì cả, nó chỉ dạy người dùng bỏ qua
// cột "Cần xem lại". Không có test thì lần sau ai đó "dọn" cái cờ `tren_dong_giay` là nó lặng lẽ
// quay lại.
import { describe, expect, it } from "vitest";
import { emptyRow, loiDong, type EditRow } from "./lsxBuoc";

/** Dòng routing tối thiểu. `may_id` đặt sẵn để khỏi dính cảnh báo "chưa gán tổ / máy" — thứ đang
 *  không phải chủ đề của phần lớn test dưới đây. */
function dong(p: Partial<EditRow>): EditRow {
  return { ...emptyRow(), may_id: 1, ...p };
}

/** Đúng chuỗi 6 bước của LSX26-0004 trên DB dev (sách 160 trang, 5 tay/cuốn). */
function chuoiSach(): EditRow[] {
  return [
    dong({ ten: "Ghi kẽm CTP", nhom: "prepress", don_vi_vao: "m2", don_vi_ra: "bai",
           tren_dong_giay: false, so_luong_vao: "1801", so_luong_ra: "7200" }),
    dong({ ten: "In offset", nhom: "print", don_vi_vao: "to", don_vi_ra: "to",
           so_luong_vao: "5200", so_luong_ra: "5000" }),
    dong({ ten: "Gấp tay sách", don_vi_vao: "to", don_vi_ra: "tay",
           so_luong_vao: "5000", so_luong_ra: "5000" }),
    dong({ ten: "Bắt tay + vào keo", don_vi_vao: "tay", don_vi_ra: "cai",
           so_luong_vao: "5000", so_luong_ra: "1000" }),
    dong({ ten: "Xén 3 mặt thành phẩm", don_vi_vao: "cai", don_vi_ra: "cai",
           so_luong_vao: "1000", so_luong_ra: "1000" }),
    dong({ ten: "Đóng gói + nhập kho", don_vi_vao: "cai", don_vi_ra: "cai",
           so_luong_vao: "1000", so_luong_ra: "1000" }),
  ];
}

const loiCua = (rows: EditRow[]) => rows.map((_r, i) => loiDong(rows, i));

describe("loiDong — đứt đơn vị", () => {
  it("bước NGOÀI dòng giấy không kéo cảnh báo giả xuống bước in ngay sau", () => {
    const rows = chuoiSach();
    // Bản cũ: bước In offset (#1) so `bài in` (ra của chế bản) với `tờ` ⇒ "đứt đơn vị".
    expect(loiDong(rows, 1)).not.toContain("đứt đơn vị");
    // Và cả chuỗi phải sạch — đây là routing ĐÚNG, không có gì để kêu.
    expect(loiCua(rows).flat()).toEqual([]);
  });

  it("bước ngoài dòng giấy KHÔNG bị soi đơn vị, kể cả khi nó đứng giữa chuỗi", () => {
    const rows = [
      dong({ ten: "In offset", don_vi_vao: "to", don_vi_ra: "to" }),
      dong({ ten: "Ghi kẽm CTP", don_vi_vao: "m2", don_vi_ra: "bai", tren_dong_giay: false }),
      dong({ ten: "Gấp tay sách", don_vi_vao: "to", don_vi_ra: "tay" }),
    ];
    // Bước #2 phải nối với bước IN (#0), nhảy qua chế bản — không phải nối với `bài in`.
    expect(loiDong(rows, 2)).not.toContain("đứt đơn vị");
    expect(loiDong(rows, 1)).not.toContain("đứt đơn vị");
  });

  it("đứt THẬT vẫn bắt được — bỏ khâu gấp/bắt tay thì tờ không ra thẳng cái", () => {
    const rows = [
      dong({ ten: "In offset", don_vi_vao: "to", don_vi_ra: "to" }),
      dong({ ten: "Đóng gói + nhập kho", don_vi_vao: "cai", don_vi_ra: "cai" }),
    ];
    expect(loiDong(rows, 1)).toContain("đứt đơn vị");
  });

  it("bước ĐẦU chuỗi không có gì phía trước để đứt", () => {
    expect(loiDong([dong({ don_vi_vao: "to", don_vi_ra: "to" })], 0)).toEqual([]);
  });
});

describe("loiDong — các kiểm còn lại giữ nguyên", () => {
  it("ra nhiều hơn vào khi KHÔNG đổi đơn vị", () => {
    const r = dong({ don_vi_vao: "to", don_vi_ra: "to", so_luong_vao: "100", so_luong_ra: "120" });
    expect(loiDong([r], 0)).toContain("ra nhiều hơn vào");
  });

  it("đổi đơn vị thì ra > vào là chuyện thường (1 tờ bế ra 8 con)", () => {
    const r = dong({ don_vi_vao: "to", don_vi_ra: "con", so_luong_vao: "100", so_luong_ra: "800" });
    expect(loiDong([r], 0)).not.toContain("ra nhiều hơn vào");
  });

  it("chưa gán tổ / máy", () => {
    const r = { ...emptyRow(), department_id: null, may_id: null };
    expect(loiDong([r], 0)).toContain("chưa gán tổ / máy");
  });

  it("thuê ngoài thiếu nhà gia công + thiếu ngày", () => {
    const r = dong({ loai_buoc: "thue_ngoai", nha_cung_cap: "  " });
    const loi = loiDong([r], 0);
    expect(loi).toContain("chưa có nhà gia công");
    expect(loi).toContain("chưa có ngày gửi / nhận");
    // Bước thuê ngoài KHÔNG bị đòi tổ/máy — nó đâu chạy trong xưởng.
    expect(loi).not.toContain("chưa gán tổ / máy");
  });

  it("trùng bước trước", () => {
    const rows = [dong({ ten: "Cán màng mờ" }), dong({ ten: "Cán màng mờ" })];
    expect(loiDong(rows, 1)).toContain("trùng bước trước");
  });
});
