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
import { boBuoc, chenBuoc, emptyRow, loiDong, mayChonDuoc, toBody, type EditRow } from "./lsxBuoc";

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

  it("thuê ngoài đòi tổ / máy Y HỆT bước máy", () => {
    // Nhà thầu được khai như một MÁY trong danh mục (hậu tố "thuê ngoài – …"), nên bước thuê
    // ngoài không có luật riêng nào ở đây nữa.
    const r = { ...emptyRow(), loai_buoc: "thue_ngoai" as const, department_id: null, may_id: null };
    expect(loiDong([r], 0)).toContain("chưa gán tổ / máy");
  });

  it("trùng bước trước", () => {
    const rows = [dong({ ten: "Cán màng mờ" }), dong({ ten: "Cán màng mờ" })];
    expect(loiDong(rows, 1)).toContain("trùng bước trước");
  });
});

// Máy chọn được trong drawer bước — phải khớp ĐÚNG luật `BaiGhepService.may_ngoai_cong_doan` của
// backend. Không khớp thì kế hoạch gán được một máy mà xếp lịch / bài ghép sẽ từ chối, và người
// dùng chỉ biết ở khâu sau cùng.
describe("mayChonDuoc — máy nào được mời cho một bước", () => {
  // Đúng dữ liệu DB dev: nhóm "Máy in" có 6 máy, "In ngoài" 4 máy, còn công đoạn In offset chỉ
  // khai 4 máy cụ thể (IN-01, IN-02, IN-03, IN-06).
  const MAY = [
    { id: 1, ten: "IN-01", nhom: "Máy in" },
    { id: 2, ten: "IN-02", nhom: "Máy in" },
    { id: 3, ten: "IN-03", nhom: "Máy in" },
    { id: 4, ten: "IN-04", nhom: "Máy in" },
    { id: 5, ten: "IN-05", nhom: "Máy in" },
    { id: 6, ten: "IN-06", nhom: "Máy in" },
    { id: 7, ten: "IN-07", nhom: "In ngoài" },
    { id: 27, ten: "TB-0001", nhom: "CTP" },
  ];
  const ten = (ds: { ten: string }[]) => ds.map((m) => m.ten);
  const IN_OFFSET = { nhomMayChoPhep: ["In ngoài", "Máy in"], mayChoPhep: [1, 2, 3, 6] };

  it("① bảng máy của công đoạn THẮNG hàng tick nhóm máy", () => {
    expect(ten(mayChonDuoc(MAY, IN_OFFSET, null)))
      .toEqual(["IN-01", "IN-02", "IN-03", "IN-06"]);
  });

  it("② chưa khai máy nào thì lùi về nhóm máy", () => {
    const cd = { nhomMayChoPhep: ["CTP"], mayChoPhep: [] };
    expect(ten(mayChonDuoc(MAY, cd, null))).toEqual(["TB-0001"]);
  });

  it("chưa khai cả hai ⇒ mọi máy", () => {
    expect(mayChonDuoc(MAY, { nhomMayChoPhep: null, mayChoPhep: null }, null)).toHaveLength(MAY.length);
    expect(mayChonDuoc(MAY, null, null)).toHaveLength(MAY.length);
  });

  it("máy ĐANG gán luôn còn trong danh sách dù rớt cả hai tầng", () => {
    // Lệnh cũ gán IN-07 rồi công đoạn mới siết bảng máy lại. Loại nó đi là ô máy về trống trơn.
    expect(ten(mayChonDuoc(MAY, IN_OFFSET, 7)))
      .toEqual(["IN-01", "IN-02", "IN-03", "IN-06", "IN-07"]);
  });

  it("máy chưa khai nhóm KHÔNG lọt bộ lọc nhóm", () => {
    const cd = { nhomMayChoPhep: ["Máy in"], mayChoPhep: null };
    const ds = [...MAY, { id: 99, ten: "MAY-LA", nhom: null }];
    expect(ten(mayChonDuoc(ds, cd, null))).not.toContain("MAY-LA");
  });
});

// --- Chèn / bỏ bước phải NỐI LẠI DÂY (09/09/2026) ------------------------------------------
//
// Bối cảnh: sơ đồ DAG vẽ theo `phu_thuoc_step_keys`, còn số lượng bám `thu_tu`. Nút "Chèn
// trước/sau" trước đây chỉ `splice` một dòng rỗng vào mảng nên số vẫn chảy đúng mà bước mới đứng
// trơ không dây trên sơ đồ — nhìn thì tưởng chuỗi liền, lưu xuống mới lộ.

/** Chuỗi thẳng A → B → C, dây khai đúng như server tự nối lúc tạo lệnh. */
function chuoiThang(): EditRow[] {
  const a = dong({ ten: "A", key: "ka" });
  const b = dong({ ten: "B", key: "kb", phu_thuoc_step_keys: ["ka"] });
  const c = dong({ ten: "C", key: "kc", phu_thuoc_step_keys: ["kb"] });
  return [a, b, c];
}

/** `[tên, tiền nhiệm...]` cho dễ đọc kỳ vọng — key sinh ra là UUID nên không so thẳng được. */
function day(rows: EditRow[]): string[][] {
  const ten = new Map(rows.map((r) => [r.key, r.ten || "MỚI"]));
  return rows.map((r) => [r.ten || "MỚI", ...r.phu_thuoc_step_keys.map((k) => ten.get(k) ?? k)]);
}

describe("chenBuoc", () => {
  it("chèn vào GIỮA thì cắt cạnh cũ và nối A → MỚI → B", () => {
    expect(day(chenBuoc(chuoiThang(), 1, emptyRow()))).toEqual([
      ["A"], ["MỚI", "A"], ["B", "MỚI"], ["C", "B"],
    ]);
  });

  it("chèn lên ĐẦU chuỗi thì bước cũ đứng đầu nhận bước mới làm tiền nhiệm", () => {
    expect(day(chenBuoc(chuoiThang(), 0, emptyRow()))).toEqual([
      ["MỚI"], ["A", "MỚI"], ["B", "A"], ["C", "B"],
    ]);
  });

  it("chèn ở CUỐI thì treo vào bước cuối, không còn đứng mồ côi", () => {
    expect(day(chenBuoc(chuoiThang(), 3, emptyRow()))).toEqual([
      ["A"], ["B", "A"], ["C", "B"], ["MỚI", "C"],
    ]);
  });

  it("bước sau KHÔNG phụ thuộc bước trước thì KHÔNG bịa cạnh mới cho nó", () => {
    // Hai nhánh rời (B tự đứng đầu một nhánh). Chèn vào giữa chỉ được treo bước mới vào A —
    // tự nối A → MỚI → B là sửa DAG sau lưng người dùng.
    const roi = [dong({ ten: "A", key: "ka" }), dong({ ten: "B", key: "kb" })];
    expect(day(chenBuoc(roi, 1, emptyRow()))).toEqual([["A"], ["MỚI", "A"], ["B"]]);
  });

  it("giữ nguyên các tiền nhiệm KHÁC của bước sau (nhánh song song / cạnh xuyên LSX)", () => {
    const rows = [
      dong({ ten: "A", key: "ka" }),
      dong({ ten: "B", key: "kb", phu_thuoc_step_keys: ["ka", "ngoai"] }),
    ];
    expect(day(chenBuoc(rows, 1, emptyRow()))).toEqual([
      ["A"], ["MỚI", "A"], ["B", "MỚI", "ngoai"],
    ]);
  });

  it("chuỗi RỖNG thì bước đầu tiên không có tiền nhiệm", () => {
    expect(day(chenBuoc([], 0, emptyRow()))).toEqual([["MỚI"]]);
  });
});

describe("boBuoc", () => {
  it("bỏ bước GIỮA thì bắc cầu A → C, không để lại key mồ côi", () => {
    expect(day(boBuoc(chuoiThang(), 1))).toEqual([["A"], ["C", "A"]]);
  });

  it("bỏ bước ĐẦU thì bước kế tiếp thành đầu chuỗi", () => {
    expect(day(boBuoc(chuoiThang(), 0))).toEqual([["B"], ["C", "B"]]);
  });

  it("bắc cầu KHÔNG đẻ tiền nhiệm trùng khi bước sau đã phụ thuộc sẵn", () => {
    // C phụ thuộc cả B lẫn A; bỏ B thì cầu A của B trùng với A sẵn có.
    const rows = [
      dong({ ten: "A", key: "ka" }),
      dong({ ten: "B", key: "kb", phu_thuoc_step_keys: ["ka"] }),
      dong({ ten: "C", key: "kc", phu_thuoc_step_keys: ["kb", "ka"] }),
    ];
    expect(day(boBuoc(rows, 1))).toEqual([["A"], ["C", "A"]]);
  });

  it("bắc cầu KHÔNG biến bước thành tự phụ thuộc chính nó", () => {
    // Ca vòng do người dùng nối tay: B phụ thuộc C, C phụ thuộc B. Bỏ B thì cầu trả về chính C.
    const rows = [
      dong({ ten: "B", key: "kb", phu_thuoc_step_keys: ["kc"] }),
      dong({ ten: "C", key: "kc", phu_thuoc_step_keys: ["kb"] }),
    ];
    expect(day(boBuoc(rows, 0))).toEqual([["C"]]);
  });
});

describe("toBody — số lượt qua máy", () => {
  // 08/09/2026, chủ chốt: "loại bước là tổ thì ẩn cái này đi và cho mặc định là 1". Ô đã gỡ khỏi
  // drawer ở bước tổ, nên số 2 lượt còn sót của bước máy cũ KHÔNG được nằm lại vô hình trong DB —
  // chip `so_luot_chay` của công thức tiền công đọc thẳng cột này.
  it("bước TỔ luôn gửi 1 lượt dù dòng còn giữ số cũ", () => {
    const [body] = toBody([dong({ ten: "Dán hộp", loai_buoc: "to", so_luot_chay: "2" })]);
    expect(body.so_luot_chay).toBe(1);
  });

  it("bước MÁY vẫn gửi đúng số đã khai", () => {
    const [body] = toBody([dong({ ten: "In offset", loai_buoc: "may", so_luot_chay: "2" })]);
    expect(body.so_luot_chay).toBe(2);
  });
});
