// Bằng chứng THẬT cho ô soạn công thức (`FormulaField`) — khoá lại vụ TRẮNG MÀN 14/08/2026.
//
// Ô này vừa đổi từ `textarea` sang "ô chip inline". Bản đổi bỏ ba hàm mà JSX vẫn gọi
// (`handleRemoveToken`, `handleInlineBlur`, `insertVar`) ⇒ ReferenceError NGAY LÚC RENDER ⇒ React
// gỡ cả cây ⇒ bấm "Công thức" ở drawer Đơn vị là trắng bong. Vite dev dùng esbuild, KHÔNG
// type-check, nên lỗi này lọt tới tận trình duyệt.
//
// Vì thế test ở đây phải RENDER và BẤM thật, không grep chuỗi: chỉ cần một identifier trong JSX
// mất chỗ dựa là cả bộ này đỏ.
import { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FormulaField } from "./RebuildCatalogPage";
import { AuthContext, type AuthState } from "../auth/AuthContext";

// Token null ⇒ `useBienCongThuc` không gọi API (từ điển rỗng, chip hiện MÃ thay nhãn). Whitelist
// đã truyền thẳng qua `bienGoiY` — đúng cách màn Đơn vị & quy đổi đang dùng.
const AUTH: AuthState = {
  status: "anonymous", user: null, token: null,
  login: async () => {}, logout: async () => {},
  updateUser: () => {}, notice: null, setNotice: () => {},
};

const BIEN = ["dinh_luong", "dai_in", "rong_in", "so_mau", "so_mau_pha"];

/** Cha giữ `value` — đúng như drawer thật, để thấy chuỗi công thức thay đổi ra sao. */
function Harness({
  dau = "", bien = BIEN, auth = AUTH, recordId = null, truocGiaTri = null, truocSuaLuc = null,
}: {
  dau?: string; bien?: string[]; auth?: AuthState;
  recordId?: number | null; truocGiaTri?: string | null; truocSuaLuc?: string | null;
}) {
  const [v, setV] = useState(dau);
  return (
    <AuthContext.Provider value={auth}>
      <FormulaField
        id="ct-test" value={v} onChange={setV} configPrefix="/api/don-vi" bienGoiY={bien}
        recordId={recordId} truocGiaTri={truocGiaTri} truocSuaLuc={truocSuaLuc}
      />
      <output data-testid="ct">{v}</output>
    </AuthContext.Provider>
  );
}

const ct = () => screen.getByTestId("ct").textContent;
const o = () => screen.getByRole("textbox") as HTMLInputElement;

// 25/08/2026 — chuỗi công thức nay được CHUẨN HOÁ: token nối lại bằng đúng một dấu cách, không
// còn khoảng trắng thừa ở đuôi ("dai_in " → "dai_in"). Đây là hệ quả bắt buộc của việc cho ô gõ
// chạy vào GIỮA dãy chip: chỉ số chip phải khớp một-một với chuỗi, mà chuỗi còn khoảng trắng lạc
// thì mỗi lần cắt token ra một kiểu. Backend `safe_eval` phân tích bằng Python nên khoảng trắng
// không đổi kết quả tính — công thức cũ đã lưu vẫn chạy y như trước.

describe("ô soạn công thức không được trắng màn", () => {
  it("render được với công thức có sẵn — chip + ô gõ đều có mặt", () => {
    render(<Harness dau="dinh_luong * dai_in" />);
    expect(o()).toBeInTheDocument();
    expect(screen.getByTitle("Xoá biến dinh_luong")).toBeInTheDocument();
  });

  it("render được khi công thức TRỐNG — đây chính là lúc bấm nút “Công thức” ở drawer Đơn vị", () => {
    render(<Harness />);
    expect(o()).toBeInTheDocument();
    expect(ct()).toBe("");
  });
});

describe("thao tác trên ô công thức", () => {
  it("bấm chip biến rồi bấm toán tử → công thức nối thêm (insertVar)", async () => {
    const user = userEvent.setup();
    render(<Harness dau="dinh_luong" />);
    await user.click(screen.getByTitle("Nhân"));
    expect(ct()).toBe("dinh_luong *");
  });

  it("bấm × trên chip → đúng token đó biến mất, phần còn lại giữ nguyên (handleRemoveToken)", async () => {
    const user = userEvent.setup();
    render(<Harness dau="dinh_luong * dai_in" />);
    await user.click(screen.getByTitle("Xoá biến dinh_luong"));
    expect(ct()).toBe("* dai_in");
  });

  it("gõ số rồi rời ô → số được chốt vào công thức chứ không bay mất (handleInlineBlur)", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.type(o(), "1000");
    expect(ct()).toBe("");        // còn nằm trong ô gõ, chưa vào công thức
    await user.tab();
    expect(ct()).toBe("1000");
  });

  it("gõ đúng tên biến → tự hoá chip ngay", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.type(o(), "dai_in");
    expect(ct()).toBe("dai_in");
    expect(o().value).toBe("");
  });

  it("KHÔNG chốt sớm khi còn mã dài hơn: gõ hết “so_mau_pha” phải ra so_mau_pha", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.type(o(), "so_mau");
    expect(ct()).toBe("");        // `so_mau_pha` còn đó ⇒ chưa được chốt
    await user.type(o(), "_pha");
    expect(ct()).toBe("so_mau_pha");
  });
});

// Chỗ khó chịu 25/08/2026: ô gõ đóng đinh ở CUỐI công thức. Gõ nhầm một dấu ở giữa thì không có
// cách nào lùi vào đó — nút "×" chỉ mọc trên chip BIẾN, còn Backspace chỉ ăn chip cuối cùng, nên
// muốn bỏ dấu "×" ở giữa là phải xoá sạch mọi thứ đứng sau nó rồi gõ lại. Nay ô gõ chạy được.
describe("con trỏ chạy được trong dãy chip", () => {
  it("← rồi Backspace → xoá đúng chip Ở GIỮA, hai đầu giữ nguyên", async () => {
    const user = userEvent.setup();
    render(<Harness dau="dinh_luong * dai_in" />);
    await user.click(o());
    await user.keyboard("{ArrowLeft}{Backspace}");   // lùi qua `dai_in`, xoá dấu `*`
    expect(ct()).toBe("dinh_luong dai_in");
  });

  it("Home rồi gõ → chèn vào ĐẦU công thức chứ không nối vào đuôi", async () => {
    const user = userEvent.setup();
    render(<Harness dau="dinh_luong * dai_in" />);
    await user.click(o());
    await user.keyboard("{Home}");
    await user.type(o(), "1000");
    await user.tab();                                 // blur = chốt chữ đang gõ
    expect(ct()).toBe("1000 dinh_luong * dai_in");
  });

  it("Home rồi Delete → xoá chip BÊN PHẢI con trỏ", async () => {
    const user = userEvent.setup();
    render(<Harness dau="dinh_luong * dai_in" />);
    await user.click(o());
    await user.keyboard("{Home}{Delete}");
    expect(ct()).toBe("* dai_in");
  });

  it("bấm vào chip → con trỏ nhảy tới đó, không bị nền ô kéo về cuối", async () => {
    const user = userEvent.setup();
    render(<Harness dau="dinh_luong * dai_in" />);
    await user.click(screen.getByTitle("Mã: dinh_luong"));
    await user.type(o(), "1000");
    await user.tab();
    // Bấm nửa trái chip thì đứng trước, nửa phải thì đứng sau — jsdom không có kích thước thật nên
    // không chốt được nửa nào. Điều PHẢI đúng: số mới nằm cạnh chip vừa bấm, không rơi xuống cuối.
    expect(["1000 dinh_luong * dai_in", "dinh_luong 1000 * dai_in"]).toContain(ct());
  });
});

// Chỗ khó chịu 03/09/2026: con trỏ CHỈ đặt được bằng cách bấm trúng một chip. Kẽ 6px giữa hai
// chip (`gap` của `.rc-formula__row`) và cả dải trắng bên phải mỗi dòng đều là NỀN ô, mà nền ô lúc
// ấy quăng thẳng con trỏ về CUỐI công thức — nhắm vào kẽ giữa hai chip để chen một dấu là bị đá về
// đuôi, nhìn như bấm chẳng ăn thua gì.
//
// jsdom không tự tính layout: mọi `getBoundingClientRect` đều là 0. Phải bịa hình học thì mới thử
// được phép dò khe — chip thứ i chiếm x [50i, 50i+40] (kẽ 10px sau mỗi chip), dòng thứ j chiếm
// y [30j, 30j+30] và rộng hết 600px.
const HCN = (left: number, right: number, top: number, bottom: number) =>
  ({ left, right, top, bottom, x: left, y: top, width: right - left, height: bottom - top,
     toJSON() {} }) as DOMRect;

function biaHinhHoc() {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (
    this: HTMLElement,
  ) {
    if (this.classList.contains("rc-formula__row")) {
      const j = Array.prototype.indexOf.call(this.parentElement?.children ?? [], this);
      return HCN(0, 600, j * 30, j * 30 + 30);
    }
    const idx = this.dataset?.idx;
    if (idx != null) {
      const i = Number(idx);
      return HCN(i * 50, i * 50 + 40, 0, 30);
    }
    return HCN(0, 0, 0, 0);
  });
}

/** Bấm vào NỀN của dòng thứ `j` tại hoành độ `x` — đúng thứ chuột người dùng làm khi nhắm vào kẽ
 *  giữa hai chip: `mousedown` rồi `click`, cả hai đều mang toạ độ. */
function bamNenDong(j: number, x: number) {
  const dong = document.querySelectorAll<HTMLElement>(".rc-formula__row")[j];
  const toaDo = { clientX: x, clientY: j * 30 + 15 };
  fireEvent.mouseDown(dong, toaDo);
  fireEvent.click(dong, toaDo);
}

describe("bấm vào khoảng trống giữa các chip", () => {
  afterEach(() => vi.restoreAllMocks());

  it("bấm đúng KẼ giữa hai chip → con trỏ vào giữa, không rơi về cuối công thức", async () => {
    const user = userEvent.setup();
    render(<Harness dau="dinh_luong * dai_in" />);
    biaHinhHoc();
    bamNenDong(0, 95);            // kẽ giữa chip `*` (50–90) và chip `dai_in` (100–140)
    await user.type(o(), "1000");
    await user.tab();
    expect(ct()).toBe("dinh_luong * 1000 dai_in");
  });

  it("bấm dải trắng bên phải một dòng → con trỏ về CUỐI DÒNG ĐÓ, không nhảy xuống cuối công thức", async () => {
    const user = userEvent.setup();
    render(<Harness dau="if ( dinh_luong , dai_in" />);
    biaHinhHoc();
    // `tinhDong` tách 3 dòng: [if · (] · [dinh_luong · ,] · [dai_in]. Bấm mãi bên phải dòng đầu.
    bamNenDong(0, 590);
    await user.type(o(), "1000");
    await user.tab();
    expect(ct()).toBe("if ( 1000 dinh_luong , dai_in");
  });
});

// "Lần trước" (mục 3+7): dòng nhắc đọc thẳng từ props (không tốn request) + link "Xem thêm lịch sử"
// mới gọi API, một cửa cho cả 4 ô công thức / 5 danh mục qua `catalog_base.py`.
describe("\"Lần trước\" — nhắc + lịch sử công thức (mục 3+7)", () => {
  it("có truocGiaTri → hiện dòng nhắc kèm giờ sửa", () => {
    render(<Harness dau="dinh_luong" truocGiaTri="LAN_TRUOC_HINT" truocSuaLuc="2026-08-20T08:00:00Z" />);
    expect(screen.getByText("Lần trước:")).toBeInTheDocument();
    expect(screen.getByText("LAN_TRUOC_HINT")).toBeInTheDocument();
  });

  it("dòng MỚI TẠO (chưa từng sửa) → KHÔNG hiện dòng nhắc", () => {
    render(<Harness dau="dinh_luong" />);
    expect(screen.queryByText("Lần trước:")).not.toBeInTheDocument();
  });

  it("bấm 'Xem thêm lịch sử' → gọi đúng route và hiện đủ danh sách mốc cũ", async () => {
    const user = userEvent.setup();
    const goi: string[] = [];
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      goi.push(String(url));
      // `useBienCongThuc` (mount tự gọi, vì auth có token) đọc từ điển ở URL này — phải trả đúng
      // phong bì `{items:[]}` của nó, khác hẳn phong bì mảng phẳng của lịch sử công thức.
      const data = String(url).includes("/api/bien-cong-thuc")
        ? { items: [] }
        : [
          { id: 2, gia_tri_cu: "CU_2", gia_tri_moi: "MOI_2", sua_boi: 1, sua_luc: "2026-08-20T08:00:00Z" },
          { id: 1, gia_tri_cu: "CU_1", gia_tri_moi: "MOI_1", sua_boi: 1, sua_luc: "2026-08-10T08:00:00Z" },
        ];
      return Promise.resolve(new Response(
        JSON.stringify(data),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ));
    }));
    render(
      <Harness
        dau="dinh_luong" recordId={7} truocGiaTri="LAN_TRUOC_HINT" truocSuaLuc="2026-08-20T08:00:00Z"
        auth={{ ...AUTH, status: "authenticated", token: "t" }}
      />,
    );
    await user.click(screen.getByText("Xem thêm lịch sử"));
    await waitFor(() => expect(screen.getByText("CU_2")).toBeInTheDocument());
    expect(screen.getByText("MOI_2")).toBeInTheDocument();
    expect(screen.getByText("CU_1")).toBeInTheDocument();
    expect(screen.getByText("MOI_1")).toBeInTheDocument();
    expect(goi.some((u) => u.includes("/api/don-vi/7/lich-su-cong-thuc"))).toBe(true);
  });
});
