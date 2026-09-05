// BÁO CÁO KẾ TOÁN — vỏ chứa các sổ, chia TAB (chủ chốt 03/09/2026).
//
// Bản đầu dựng hai mục menu riêng cho hai sổ công nợ; chủ gộp lại: *"gộp chung vào 1 menu báo cáo
// trong đó chia tab ra phải trả phải thu"*.
//
// 04/09/2026 từng có thêm ba tab đối chiếu với MISA (số dư đầu kỳ · so lệch) rồi BỎ HẲN cùng ngày
// — *"mình không cần làm cho họ đâu, kệ họ"*. Đừng dựng lại nếu chưa hỏi.
//
// Vỏ cố ý MỎNG: nó chỉ chọn tab và GIỮ KỲ. Mọi thứ về từng sổ nằm trong component của sổ đó.
//
// PHÂN QUYỀN: từ 04/09/2026 gác bằng MỘT ô quyền riêng `bao_cao_cong_no` (chủ chốt: "báo cáo đó
// là một module riêng mà") — không còn ăn ké quyền Xem của `cong_no_phai_tra`/`cong_no_phai_thu`
// nữa, nên KHÔNG còn ca "chỉ thấy một tab": có quyền là thấy đủ cả hai, không có thì `duocXem`
// rỗng, rơi vào nhánh báo lỗi dưới đây. `TAB[].module` giữ lại (thay vì bỏ hẳn bộ lọc) làm lớp
// phòng thủ thứ hai — phòng khi màn này bị vào thẳng mà không qua hàng rào route của AppShell.
import { useMemo, useState } from "react";
import type { NavigateFn } from "../../../components/AppShell";
import { useCan } from "../../../auth/permissions";
import { BaoCaoCongNoPage } from "../bao-cao-cong-no";
import { kyMacDinh, type Ky } from "../bao-cao-cong-no/shared/ky";
import "./bao-cao.css";

type TabId = "phai-tra" | "phai-thu";

const TAB: { id: TabId; label: string; module: string; ben: "payables" | "receivables" }[] = [
  { id: "phai-tra", label: "Công nợ phải trả", module: "bao_cao_cong_no", ben: "payables" },
  { id: "phai-thu", label: "Công nợ phải thu", module: "bao_cao_cong_no", ben: "receivables" },
];

export function BaoCaoKeToanPage({ navigate }: { navigate?: NavigateFn } = {}) {
  const can = useCan();
  const duocXem = useMemo(() => TAB.filter((t) => can(t.module, "read")), [can]);
  const [tab, setTab] = useState<TabId | null>(null);
  // KỲ ở VỎ, không ở từng sổ: đổi tab mà mất kỳ đang chọn là bắt gõ lại ngày mỗi lần muốn so hai
  // bên với nhau — mà so hai bên CÙNG MỘT KỲ mới là lý do gộp chúng vào một màn. Bảng so lệch
  // cũng ăn chính kỳ này, nên chọn kỳ ở tab sổ rồi nhảy sang so lệch là so đúng kỳ đó luôn.
  const [ky, setKy] = useState<Ky>(kyMacDinh);

  // Tab đang mở = tab người dùng chọn, hoặc tab ĐẦU TIÊN họ được xem. Tính ở đây chứ không đặt
  // giá trị đầu cứng trong `useState`: người chỉ có quyền phải thu mà mặc định là "phải trả" thì
  // mở màn ra thấy trống trơn.
  const dangMo = duocXem.find((t) => t.id === tab) ?? duocXem[0] ?? null;

  if (!dangMo) {
    return (
      <main className="md-page">
        <div className="alert alert--error">Bạn chưa được cấp quyền xem báo cáo công nợ nào.</div>
      </main>
    );
  }

  return (
    <div className="bckt">
      {/* Một tab thì KHÔNG vẽ thanh tab: một cái nút đứng lẻ trông như hỏng, mà bấm cũng không
          đi đâu được. */}
      {duocXem.length > 1 && (
        <nav className="bckt__tabs" aria-label="Chọn báo cáo">
          {duocXem.map((t) => (
            <button
              key={t.id}
              type="button"
              className={`bckt__tab${dangMo.id === t.id ? " is-on" : ""}`}
              aria-current={dangMo.id === t.id ? "page" : undefined}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </nav>
      )}
      {/* KHÔNG `key` để ép dựng lại: kỳ nằm ở vỏ nên phải sống qua lần đổi tab. Bảng cũng
          không nháy số của bên kia — `load()` bật cờ tải ngay khi `ben` đổi, nên khung xương
          hiện trước, số cũ không kịp lộ ra. */}
      <BaoCaoCongNoPage ben={dangMo.ben} ky={ky} onKy={setKy} navigate={navigate} />
    </div>
  );
}
