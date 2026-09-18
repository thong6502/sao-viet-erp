import { afterEach, describe, expect, it } from "vitest";
import { fireEvent } from "@testing-library/react";
import { chanLanChuotDoiSo } from "./chanLanChuotDoiSo";

describe("chanLanChuotDoiSo", () => {
  let go: (() => void) | null = null;
  afterEach(() => {
    go?.();
    go = null;
    document.body.innerHTML = "";
  });

  function o(type: string) {
    const el = document.createElement("input");
    el.type = type;
    document.body.appendChild(el);
    el.focus();
    return el;
  }

  it("lăn chuột trên ô số đang gõ thì nhả focus — trình duyệt thôi tăng/giảm số, trang vẫn cuộn", () => {
    go = chanLanChuotDoiSo();
    const so = o("number");
    expect(document.activeElement).toBe(so);
    fireEvent.wheel(so, { deltaY: 100 });
    expect(document.activeElement).not.toBe(so);
  });

  it("không đụng ô chữ, và ô số KHÔNG đang focus thì để yên", () => {
    go = chanLanChuotDoiSo();
    const chu = o("text");
    fireEvent.wheel(chu, { deltaY: 100 });
    expect(document.activeElement).toBe(chu);

    const soKhac = document.createElement("input");
    soKhac.type = "number";
    document.body.appendChild(soKhac);
    fireEvent.wheel(soKhac, { deltaY: 100 });
    expect(document.activeElement).toBe(chu);
  });

  it("gỡ ra thì hết chặn", () => {
    chanLanChuotDoiSo()();
    const so = o("number");
    fireEvent.wheel(so, { deltaY: 100 });
    expect(document.activeElement).toBe(so);
  });
});
