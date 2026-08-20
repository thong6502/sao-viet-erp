// KẾ HOẠCH VẬT TƯ — bảng cân đối *cần bao nhiêu · có bao nhiêu · thiếu bao nhiêu · bao giờ đặt*,
// gom NHIỀU LỆNH lại. Tách khỏi tab của màn Kế hoạch sản xuất 17/08/2026 theo yêu cầu chủ.
//
// Vì sao đứng riêng chứ không ké tab như trước: nó trả lời câu của một VAI KHÁC. Màn Kế hoạch sản
// xuất hỏi "lệnh này đã đủ thông tin để chạy chưa" — phạm vi MỘT lệnh. Màn này hỏi "cả xưởng còn
// thiếu gì, hôm nào phải đặt" — phạm vi CẢ KHO, và đầu ra của nó đi thẳng sang Thu mua. Ké tab thì
// người lo vật tư phải đi qua màn lệnh mới tới được việc của mình.
//
// Ranh giới với tab "Vật tư" của MỘT lệnh (`LsxVatTuPanel`): bên đó chỉ nói CẦN, không biết tồn.
// Bên này mới trừ tồn + hàng đang về + phần kho đã cấp. Một bên hỏi, một bên trả lời.
//
// HAI CÁCH NHÌN, MỘT MÀN (17/08/2026). Cùng một bảng cân đối, xoay 90°:
//   · theo MẶT HÀNG — "còn thiếu gì, mua bao nhiêu": gộp mọi lệnh vào một đơn mua.
//   · theo LỆNH     — "lệnh này chạy được chưa": nơi bật/tắt GIỮ CHỖ, thứ mở khoá xếp lịch.
// Cố ý là một CÔNG TẮC GOM-THEO chứ không phải hai tab (và càng không phải hai màn): dữ liệu y
// hệt, chỉ khác trục gom. Tách thành hai mục menu thì người dùng phải nhớ "việc này nằm ở màn
// nào", trong khi đây là cùng một việc nhìn từ hai phía.
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Icon } from "../components/Icons";
import { GiuChoTheoLenhView } from "./GiuChoTheoLenhView";
import { VatTuKeHoachView } from "./VatTuKeHoachView";
import { useNapTenDonVi } from "./tenDonVi";
import { num } from "./keHoachSxShared";
import "./ke-hoach-sx.css";

type Gom = "hang" | "lenh";

export function KeHoachVatTuPage({
  navigate,
  eventTick,
  focusLsxMa,
}: {
  navigate?: (id: string, params?: Record<string, unknown>) => void;
  /** Tăng mỗi lần có event SSE → bảng tự tính lại, không bắt người dùng F5. */
  eventTick?: number;
  /** Đèn "Vật tư" ở Kế hoạch SX bấm sang đây: mở thẳng cách nhìn THEO LỆNH + tìm sẵn mã lệnh đó.
   *  Cách nhìn mặc định gom theo mặt hàng, đứng ở đó thì mã lệnh không có chỗ nào để tìm. */
  focusLsxMa?: string | null;
}) {
  const { token } = useAuth();
  // Nhãn đơn vị đọc từ DANH MỤC — bảng cân đối hiện "2.961 tờ ≈ 116 kg", cả hai đầu đều cần tên.
  useNapTenDonVi();
  // Bit "tạo yêu cầu mua cho bộ phận" — KHÔNG lách bằng quyền `san_xuat`. Thiếu bit thì nút "Đề
  // nghị mua" tự ẩn, bảng cân đối vẫn xem được bình thường.
  const [canDeNghiMua, setCanDeNghiMua] = useState(false);
  const [gom, setGom] = useState<Gom>(focusLsxMa ? "lenh" : "hang");
  const [soDo, setSoDo] = useState(0);
  const [soGiuLau, setSoGiuLau] = useState(0);

  // Bấm chấm lần thứ hai (mã khác) trong cùng phiên phải kéo được về đây, nên theo dõi cả sau lần
  // khởi tạo — chỉ đặt giá trị đầu là lần sau đứng nguyên chỗ cũ.
  useEffect(() => {
    if (focusLsxMa) setGom("lenh");
  }, [focusLsxMa]);

  useEffect(() => {
    if (!token) return;
    let alive = true;
    api.departmentPurchaseRequests
      .canCreate(token)
      .then((r: { can_create: boolean }) => alive && setCanDeNghiMua(r.can_create))
      .catch(() => alive && setCanDeNghiMua(false));
    return () => {
      alive = false;
    };
  }, [token]);

  // Chip "giữ lâu chưa chạy" phải hiện NGAY trên nút, kể cả khi đang đứng ở cách nhìn theo mặt
  // hàng — nếu chỉ đếm lúc mở cách nhìn theo lệnh thì muốn thấy cảnh báo phải đoán trước là có
  // cảnh báo, tức là nó vô dụng. Gọi bản LỌC SẴN (`chi_giu_lau`) nên payload chỉ vài dòng; khi
  // người dùng sang tab kia thì chính view đó báo lại con số và ghi đè.
  useEffect(() => {
    if (!token) return;
    let alive = true;
    api.keHoachVatTu
      .theoLenh(token, { chi_giu_lau: true })
      .then((r) => alive && setSoGiuLau(r.so_giu_lau))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [token, eventTick]);

  return (
    <main className="khsx khvt-page">
      <header className="khvt-header">
        <div className="khvt-header__top">
          <div className="khvt-header__badge">
            <span className="khvt-header__pulse" aria-hidden="true" />
            <span>Sản xuất &amp; Cung ứng</span>
          </div>
          <div className="khvt-header__sync" title="Dữ liệu tự động cập nhật qua kết nối thời gian thực">
            <Icon name="workflow" size={12} />
            <span>Live Sync</span>
          </div>
        </div>

        <div className="khvt-header__title-row">
          <div>
            <h1 className="khvt-header__title">Kế hoạch vật tư</h1>
            <p className="khvt-header__desc">
              Bảng cân đối nhu cầu tồn kho, cảnh báo thiếu hụt và điều phối giữ chỗ toàn xưởng.
            </p>
          </div>

          {/* Công tắc GOM THEO — Segmented Capsule Tabs */}
          <div className="khvt-segmented-switch" role="group" aria-label="Chế độ xem bảng cân đối">
            <button
              type="button"
              className={`khvt-segmented-btn ${gom === "hang" ? "is-active" : ""}`}
              aria-pressed={gom === "hang"}
              onClick={() => setGom("hang")}
            >
              <Icon name="packageCheck" size={15} />
              <div className="khvt-segmented-btn__content">
                <span className="khvt-segmented-btn__label">Theo mặt hàng</span>
                <span className="khvt-segmented-btn__sub">còn thiếu gì · mua bao nhiêu</span>
              </div>
              {soDo > 0 && (
                <span className="khvt-badge-count khvt-badge-count--alert" title={`${num(soDo)} dòng cần xử lý`}>
                  {num(soDo)}
                </span>
              )}
            </button>
            <button
              type="button"
              className={`khvt-segmented-btn ${gom === "lenh" ? "is-active" : ""}`}
              aria-pressed={gom === "lenh"}
              onClick={() => setGom("lenh")}
            >
              <Icon name="fileText" size={15} />
              <div className="khvt-segmented-btn__content">
                <span className="khvt-segmented-btn__label">Theo lệnh sản xuất</span>
                <span className="khvt-segmented-btn__sub">giữ chỗ · lệnh nào chạy được</span>
              </div>
              {soGiuLau > 0 && (
                <span className="khvt-badge-count khvt-badge-count--warn" title="Lệnh giữ vật tư lâu chưa vào kế hoạch">
                  {num(soGiuLau)}
                </span>
              )}
            </button>
          </div>
        </div>
      </header>

      {gom === "hang" ? (
        <VatTuKeHoachView
          eventTick={eventTick}
          canDeNghiMua={canDeNghiMua}
          onSoDo={setSoDo}
          onOpenLsx={navigate ? (id) => navigate("ke-hoach-sx", { openLsxId: id }) : undefined}
        />
      ) : (
        <GiuChoTheoLenhView
          eventTick={eventTick}
          canDeNghiMua={canDeNghiMua}
          onSoGiuLau={setSoGiuLau}
          focusLsxMa={focusLsxMa}
          onOpenLsx={navigate ? (id) => navigate("ke-hoach-sx", { openLsxId: id }) : undefined}
        />
      )}
    </main>
  );
}
