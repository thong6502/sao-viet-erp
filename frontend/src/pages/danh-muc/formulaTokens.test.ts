import { describe, expect, it } from "vitest";

import { catToken, laSo, laToanTu } from "./formulaTokens";

describe("catToken", () => {
  it("giữ dấu phẩy của hàm nhiều tham số", () => {
    // Bản chép tay ở hàm kiểm tra công thức từng QUÊN `,` trong lớp ký tự — regex chỉ lặng lẽ bỏ
    // qua nó, nên dấu phẩy đi lọt mà không chỗ nào soi. Gộp về một bản thì phải chắc nó có mặt.
    expect(catToken("max(a, b)").filter((t) => t.trim())).toEqual(
      ["max", "(", "a", ",", "b", ")"],
    );
  });

  it("cắt được số thập phân và biến có gạch dưới", () => {
    expect(catToken("dinh_luong * 1.5").filter((t) => t.trim())).toEqual(
      ["dinh_luong", "*", "1.5"],
    );
  });

  it("giữ khoảng trắng để chỗ vẽ chip dựng lại đúng hình", () => {
    expect(catToken("a + b").join("")).toBe("a + b");
  });

  it("không giữ trạng thái giữa hai lần gọi", () => {
    // Regex cờ `g` dùng chung sẽ nhớ `lastIndex` và lần gọi sau cắt hụt từ giữa chuỗi.
    const mot = catToken("a + b");
    const hai = catToken("a + b");
    expect(hai).toEqual(mot);
  });
});

describe("phân loại token", () => {
  it("dấu phẩy là toán tử/dấu ngăn, không phải biến lạ", () => {
    expect(laToanTu(",")).toBe(true);
    expect(laToanTu("dinh_luong")).toBe(false);
  });

  it("nhận số nguyên và số thập phân", () => {
    expect(laSo("12")).toBe(true);
    expect(laSo("1.5")).toBe(true);
    expect(laSo("1.5.2")).toBe(false);
  });
});
