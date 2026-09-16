import { describe, expect, it } from "vitest";
import {
  chonViecKeTiep,
  duoiTep,
  dungLuong,
  kiemTruocKhiTai,
  kieuXemTruoc,
  nenThuLai,
  type ViecTai,
} from "./tepDinhKem";

const viec = (id: number, trangThai: ViecTai["trangThai"]): ViecTai => ({
  id,
  file: new File(["x"], `t${id}.pdf`),
  trangThai,
  loi: null,
});

describe("chonViecKeTiep — tối đa N tệp chạy song song", () => {
  it("hàng mới: lấy đúng N việc đầu đang chờ", () => {
    const hang = [1, 2, 3, 4, 5].map((i) => viec(i, "cho"));
    expect(chonViecKeTiep(hang, 3)).toEqual([1, 2, 3]);
  });

  it("đang chạy 2 thì chỉ bù thêm 1", () => {
    const hang = [viec(1, "dang"), viec(2, "dang"), viec(3, "cho"), viec(4, "cho")];
    expect(chonViecKeTiep(hang, 3)).toEqual([3]);
  });

  it("việc lỗi không chiếm chỗ và không tự chạy lại", () => {
    const hang = [viec(1, "loi"), viec(2, "loi"), viec(3, "cho")];
    expect(chonViecKeTiep(hang, 3)).toEqual([3]);
  });

  it("đủ N việc đang chạy thì không lấy thêm", () => {
    const hang = [viec(1, "dang"), viec(2, "dang"), viec(3, "dang"), viec(4, "cho")];
    expect(chonViecKeTiep(hang, 3)).toEqual([]);
  });
});

describe("kiemTruocKhiTai — báo ngay, khỏi tốn một lượt gửi", () => {
  const MB = 1024 * 1024;
  it("tệp rỗng", () => {
    expect(kiemTruocKhiTai({ name: "a.pdf", size: 0 }, 50 * MB)).toBe("Tệp rỗng");
  });
  it("vượt cỡ nói rõ giới hạn", () => {
    expect(kiemTruocKhiTai({ name: "a.pdf", size: 50 * MB + 1 }, 50 * MB)).toBe("Tệp vượt quá 50MB");
  });
  it("đúng giới hạn vẫn nhận", () => {
    expect(kiemTruocKhiTai({ name: "a.pdf", size: 50 * MB }, 50 * MB)).toBeNull();
  });
});

describe("kieuXemTruoc", () => {
  it("ảnh theo kiểu hoặc theo đuôi", () => {
    expect(kieuXemTruoc({ ten_tep: "x.bin", content_type: "image/png" })).toBe("anh");
    expect(kieuXemTruoc({ ten_tep: "Mau.JPG", content_type: null })).toBe("anh");
  });
  it("pdf theo kiểu hoặc theo đuôi", () => {
    expect(kieuXemTruoc({ ten_tep: "maket.pdf", content_type: null })).toBe("pdf");
    expect(kieuXemTruoc({ ten_tep: "x", content_type: "application/pdf" })).toBe("pdf");
  });
  it("tệp thiết kế thì chỉ tải về", () => {
    expect(kieuXemTruoc({ ten_tep: "hop.ai", content_type: "application/postscript" })).toBe("khac");
    expect(kieuXemTruoc({ ten_tep: "hop.cdr", content_type: null })).toBe("khac");
  });
});

describe("dungLuong", () => {
  it("đổi đơn vị theo độ lớn, dấu phẩy thập phân kiểu Việt", () => {
    expect(dungLuong(820)).toBe("820 B");
    expect(dungLuong(1536)).toBe("1,5 KB");
    expect(dungLuong(12.34 * 1024 * 1024)).toBe("12,3 MB");
  });
});

describe("duoiTep — nhãn trên ô thu nhỏ của tệp không xem trước được", () => {
  it("lấy đuôi viết hoa", () => {
    expect(duoiTep("Maket hop.ai")).toBe("AI");
    expect(duoiTep("ban-ve.v2.cdr")).toBe("CDR");
  });
  it("không đuôi hoặc đuôi dài quá thì ghi chung là TỆP", () => {
    expect(duoiTep("README")).toBe("TỆP");
    expect(duoiTep("a.photoshop")).toBe("TỆP");
    expect(duoiTep(".env")).toBe("TỆP");
  });
});

describe("nenThuLai — chỉ mời thử lại khi lần sau có thể khác", () => {
  it("mất mạng hoặc máy chủ trục trặc thì thử lại được", () => {
    expect(nenThuLai(0)).toBe(true);
    expect(nenThuLai(500)).toBe(true);
    expect(nenThuLai(502)).toBe(true);
    expect(nenThuLai(408)).toBe(true);
    expect(nenThuLai(429)).toBe(true);
  });
  it("máy chủ đã từ chối nội dung/quyền thì gửi lại vẫn vậy", () => {
    for (const s of [400, 403, 404, 409, 413, 415]) expect(nenThuLai(s)).toBe(false);
  });
});
