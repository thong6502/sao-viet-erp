/** Hai luật ĐƠN VỊ của khối Vật tư trên drawer Thực hiện SX — cả hai đều là chuyện "hai thang số
 *  gặp nhau", nên để chung một file.
 *
 *  · `vtCoLechThucTe` — SX lưu 3 chữ số, kho lưu 2: cờ lệch phải chịu được sai khác do làm tròn,
 *    và chịu được cả phần sai khác đó CỘNG DỒN qua nhiều lần đề nghị (`vtSoLanCoMon`).
 *  · `vtDvtLanTruoc`  — lần bổ sung phải nói cùng đơn vị với lần trước của chính mặt hàng đó.
 */
import { describe, expect, it } from "vitest";

import { vtCoLechThucTe, vtDvtLanTruoc, vtSoLanCoMon } from "./ThsxExecPanels";

describe("vtCoLechThucTe — lệch thật, không phải lệch do làm tròn", () => {
  it("0,003 kg: KHÔNG lệch (kho ghi 2 chữ số, SX ghi 3 — sai khác cấu trúc)", () => {
    // Ca đo thật lúc nghiệm thu: tổ xin 554 tờ = 166,967 kg, kho cấp 166,97 kg. Kho cấp ĐÚNG thứ
    // được xin mà dòng vẫn đeo badge vàng "so YC +0,003 kg" vĩnh viễn — và giấy gần như không bao
    // giờ ra số tròn 2 chữ số nên MỌI dòng giấy đều dính, tổ trưởng học cách bỏ qua cờ lệch.
    expect(vtCoLechThucTe({ lech_thuc_te: 0.003 })).toBe(false);
    expect(vtCoLechThucTe({ lech_thuc_te: -0.003 })).toBe(false);
  });

  it("0,01 kg: CÓ lệch — vượt nửa bước lượng tử của kho, không đổ cho làm tròn được", () => {
    expect(vtCoLechThucTe({ lech_thuc_te: 0.01 })).toBe(true);
    expect(vtCoLechThucTe({ lech_thuc_te: -0.01 })).toBe(true);
  });

  it("khớp tuyệt đối vẫn là khớp", () => {
    expect(vtCoLechThucTe({ lech_thuc_te: 0 })).toBe(false);
  });

  it("lệch to (kho cấp thiếu hẳn) vẫn phải kêu", () => {
    expect(vtCoLechThucTe({ lech_thuc_te: -46.97 })).toBe(true);
  });

  it("3 lần đề nghị × 0,004 mỗi lần: KHÔNG lệch — sai khác làm tròn CỘNG DỒN theo số lần", () => {
    // `board.py::_vat_tu_cap` cộng dồn `sl_yeu_cau_goc` qua MỌI lần của cùng một món, nên sai khác
    // do làm tròn cũng cộng dồn. Dung sai một-lần (0,005) chỉ đúng cho lần đầu; từ lần bổ sung thứ
    // hai trở đi badge vàng giả quay lại đúng như trước bản vá.
    expect(vtCoLechThucTe({ lech_thuc_te: 0.012 }, 3)).toBe(false);
    expect(vtCoLechThucTe({ lech_thuc_te: -0.012 }, 3)).toBe(false);
  });

  it("1 lần mà lệch 0,012: CÓ lệch — nới dung sai chỉ theo SỐ LẦN, không nới vô tội vạ", () => {
    expect(vtCoLechThucTe({ lech_thuc_te: 0.012 }, 1)).toBe(true);
    expect(vtCoLechThucTe({ lech_thuc_te: 0.012 })).toBe(true);
  });

  it("0 lần (dòng kế hoạch chưa từng gửi) vẫn giữ dung sai một lần — sàn 1", () => {
    expect(vtCoLechThucTe({ lech_thuc_te: 0.003 }, 0)).toBe(false);
    expect(vtCoLechThucTe({ lech_thuc_te: 0.012 }, 0)).toBe(true);
  });
});

describe("vtSoLanCoMon — đếm số lần đề nghị CÓ XIN đúng món đó", () => {
  const lan = (hangLoai: string, hangId: number, slGoc = 12.5) => ({
    dongs: [{ hang_loai: hangLoai, hang_id: hangId, sl_yeu_cau_goc: slGoc }],
  });

  it("đếm đúng số lần có món, bỏ qua lần không có", () => {
    const ds = [lan("vat_tu", 7), lan("vat_tu", 7), lan("vat_tu", 9)];
    expect(vtSoLanCoMon(ds, { hang_loai: "vat_tu", hang_id: 7 })).toBe(2);
    expect(vtSoLanCoMon(ds, { hang_loai: "vat_tu", hang_id: 9 })).toBe(1);
  });

  it("khác `hang_loai` là khác mặt hàng, dù trùng id", () => {
    expect(vtSoLanCoMon([lan("vat_tu", 7)], { hang_loai: "giay", hang_id: 7 })).toBe(0);
  });

  it("chưa gửi đề nghị nào → 0 (chỗ gọi rơi về sàn 1)", () => {
    expect(vtSoLanCoMon([], { hang_loai: "vat_tu", hang_id: 7 })).toBe(0);
  });

  it("lần đã sửa món đó về 0 KHÔNG tính — nó không đẻ dòng kho nên không làm tròn gì", () => {
    // Bản đối chiếu của sản xuất giữ cả dòng xin 0, nhưng `_lines_kho` bỏ chúng: lần đó không đi
    // qua bước làm tròn về `Numeric(14,2)` nào. Đếm vào là nới dung sai thêm 0,005 cho một lần
    // không đóng góp sai số — tức bịt bớt cờ lệch THẬT.
    const ds = [lan("vat_tu", 7), lan("vat_tu", 7, 0)];
    expect(vtSoLanCoMon(ds, { hang_loai: "vat_tu", hang_id: 7 })).toBe(1);
    // Mọi lần đều 0 ⇒ 0 lần, chỗ gọi rơi về sàn 1 (dung sai một lần) chứ không phải 2.
    expect(vtSoLanCoMon([lan("vat_tu", 7, 0), lan("vat_tu", 7, 0)],
                        { hang_loai: "vat_tu", hang_id: 7 })).toBe(0);
  });
});

describe("vtDvtLanTruoc — đơn vị mặc định của form bổ sung", () => {
  const lan = (lanSo: number, dvt: string, hangId = 7) => ({
    lan_so: lanSo,
    dongs: [{ hang_loai: "vat_tu", hang_id: hangId, dvt }],
  });

  it("mặt hàng đã xin lần trước bằng 'to' → lấy 'to' (không lật sang đơn vị gốc)", () => {
    expect(vtDvtLanTruoc([lan(1, "to")], "vat_tu", 7)).toBe("to");
  });

  it("mặt hàng chưa lần nào xin → null, để chỗ gọi rơi về `don_vi_goc`", () => {
    expect(vtDvtLanTruoc([lan(1, "to")], "vat_tu", 99)).toBeNull();
    expect(vtDvtLanTruoc([], "vat_tu", 7)).toBeNull();
    // Khác `hang_loai` là khác mặt hàng, dù trùng id.
    expect(vtDvtLanTruoc([lan(1, "to")], "giay", 7)).toBeNull();
  });

  it("hai lần trước dùng 'to' rồi 'kg' → lấy của lần GẦN NHẤT ('kg')", () => {
    expect(vtDvtLanTruoc([lan(1, "to"), lan(2, "kg")], "vat_tu", 7)).toBe("kg");
    // Thứ tự trong mảng không phải nguồn sự thật — `lan_so` mới là.
    expect(vtDvtLanTruoc([lan(2, "kg"), lan(1, "to")], "vat_tu", 7)).toBe("kg");
  });

  it("lần gần nhất lưu `dvt` rỗng → bỏ qua, lấy lần trước đó có đơn vị thật", () => {
    // Dòng `dvt=""` chỉ nghĩa là lúc đó routing/danh mục chưa nói được đơn vị (BE cho phép gửi
    // dòng như vậy với số 0). Chép lại là chép cái trống rồi bắt tổ đối mặt với băng "chưa có đơn
    // vị tính" cho một mặt hàng họ vừa xin bằng "to" ở lần trước.
    expect(vtDvtLanTruoc([lan(1, "to"), lan(2, "")], "vat_tu", 7)).toBe("to");
  });
});
