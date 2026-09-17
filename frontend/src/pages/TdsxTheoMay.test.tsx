import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import type { TdsxMayLaneBlock, TdsxTheoMayOut } from "../api/client";
import { api } from "../api/client";
import { TdsxTheoMay } from "./TdsxTheoMay";

/** jsdom không dàn trang: mọi hộp đều 0×0. Dựng lại đúng hình học tab này dùng — thanh lấy
 *  `left`/`width` inline, nhãn đứng ngoài bắt đầu sau mép phải thanh 4px, mỗi ký tự ~7px. */
function gaiHinhHoc() {
  return vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    const hop = (left: number, width: number) =>
      ({ left, right: left + width, width, top: 0, bottom: 38, height: 38, x: left, y: 0, toJSON: () => ({}) }) as DOMRect;
    if (this.classList.contains("tdsx-tm__block")) {
      return hop(parseFloat(this.style.left), parseFloat(this.style.width));
    }
    if (this.classList.contains("tdsx-tm__nhan--ngoai")) {
      const thanh = this.closest<HTMLElement>(".tdsx-tm__block")!;
      return hop(parseFloat(thanh.style.left) + parseFloat(thanh.style.width) + 4, (this.textContent ?? "").length * 7);
    }
    return hop(0, 0);
  });
}

function khoi(id: number, ma: string, bd: string, kt: string): TdsxMayLaneBlock {
  return {
    cong_viec_id: id, ten: "In", trang_thai: "released", lsx: [{ lsx_id: id, ma } as TdsxMayLaneBlock["lsx"][number]],
    du_kien_bat_dau: bd, du_kien_ket_thuc: kt, nguoi: [], nhan: null,
  };
}

describe("TdsxTheoMay — nhãn đứng ngoài thanh hẹp", () => {
  let gai: ReturnType<typeof gaiHinhHoc>;
  beforeEach(() => {
    gai = gaiHinhHoc();
  });
  afterEach(() => {
    gai.mockRestore();
    vi.restoreAllMocks();
  });

  it("ẩn nhãn sẽ lấn lên thanh kế bên, giữ nhãn còn chỗ", async () => {
    // Dải > 30 giờ ⇒ 14px/giờ: việc 2 giờ = 28px, hẹp ⇒ nhãn ra ngoài. Ba việc nối đuôi nhau (máy
    // chạy liền tay), một việc đứng riêng hai ngày sau.
    const du: TdsxTheoMayOut = {
      lanes: [
        {
          may_id: 1, ten: "Máy in 4 màu", ngung_dung: false,
          blocks: [
            khoi(11, "LSX26-0011", "2026-09-17T06:00:00Z", "2026-09-17T08:00:00Z"),
            khoi(12, "LSX26-0012", "2026-09-17T08:00:00Z", "2026-09-17T10:00:00Z"),
            khoi(13, "LSX26-0013", "2026-09-17T10:00:00Z", "2026-09-17T12:00:00Z"),
            khoi(14, "LSX26-0014", "2026-09-19T06:00:00Z", "2026-09-19T08:00:00Z"),
          ],
        },
      ],
    };
    vi.spyOn(api.theoDoiSanXuat, "theoMay").mockResolvedValue(du);

    render(
      <TdsxTheoMay active token="t" params={{}} refreshTick={0} onOpenHoSo={() => {}} onXoaLoc={() => {}} khay={null} />,
    );

    const nhan = async (ma: string) => (await screen.findByText(ma, { selector: ".tdsx-tm__nhan--ngoai" })).classList;
    expect(await nhan("LSX26-0011")).toContain("is-che");
    expect(await nhan("LSX26-0012")).toContain("is-che");
    expect(await nhan("LSX26-0013")).not.toContain("is-che");
    expect(await nhan("LSX26-0014")).not.toContain("is-che");
  });
});
