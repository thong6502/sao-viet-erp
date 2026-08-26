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
import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type DeNghiMuaXemTruoc } from "../api/client";
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
  // `null` = CHƯA BIẾT (chưa hỏi xong, hoặc hỏi mà hỏng). KHÔNG gộp với `false`: gộp thì đúng một
  // lỗi mạng cũng làm mọi nút "Mua" biến mất vĩnh viễn cho tới khi F5 — người dùng đọc thành
  // "phần mềm hỏng", đúng câu hỏi nhận ngày 20/08/2026.
  const [canDeNghiMua, setCanDeNghiMua] = useState<boolean | null>(null);
  const [gom, setGom] = useState<Gom>(focusLsxMa ? "lenh" : "hang");
  const [soDo, setSoDo] = useState(0);
  const [soGiuLau, setSoGiuLau] = useState(0);

  // Bấm chấm lần thứ hai (mã khác) trong cùng phiên phải kéo được về đây, nên theo dõi cả sau lần
  // khởi tạo — chỉ đặt giá trị đầu là lần sau đứng nguyên chỗ cũ.
  useEffect(() => {
    if (focusLsxMa) setGom("lenh");
  }, [focusLsxMa]);

  // "Đề nghị mua ngay" KHÔNG tự đẻ phiếu nữa (20/08/2026, theo yêu cầu chủ): nó mở form "Tạo yêu
  // cầu mua hàng" ở màn Yêu cầu mua hàng, ĐÃ điền sẵn ngày cần · nội dung · từng dòng vật tư.
  //
  // Đi bằng đường seed có sẵn (`purchaseSeed*`, thứ màn Kho đang dùng) chứ không dựng form mua thứ
  // hai ngay trên bảng cân đối: hai form cùng một việc thì đúng một tháng nữa chúng lệch nhau, mà
  // chỗ lệch luôn rơi vào ô ít ai bấm nhất.
  const moFormMua = useCallback(
    (nhap: DeNghiMuaXemTruoc) => {
      navigate?.("yeu-cau-mua-hang", {
        purchaseSeedLines: nhap.lines.map((d) => ({
          hang_loai: d.hang_loai,
          hang_id: d.hang_id,
          item_name: d.item_name,
          unit: d.unit,
          quantity: d.quantity,
        })),
        purchaseSeedPurpose: nhap.noi_dung,
        purchaseSeedHeader: {
          source_type: "san_xuat",
          needed_date: nhap.needed_date,
          related_document_type: nhap.related_document_type,
          related_document_code: nhap.related_document_code,
        },
      });
    },
    [navigate],
  );

  useEffect(() => {
    if (!token) return;
    let alive = true;
    let hen: number | undefined;
    let lan = 0;
    const hoi = () => {
      api.departmentPurchaseRequests
        .canCreate(token)
        .then((r: { can_create: boolean }) => alive && setCanDeNghiMua(r.can_create))
        .catch((e: unknown) => {
          if (!alive) return;
          // Server TRẢ LỜI là không có quyền ⇒ chốt `false`, ẩn nút cho đúng.
          if (e instanceof ApiError && (e.status === 401 || e.status === 403)) {
            setCanDeNghiMua(false);
            return;
          }
          // Mạng rớt / 5xx ⇒ vẫn CHƯA BIẾT. Thử lại vài nhịp; nút cứ hiện, ai bấm thì lỗi thật của
          // server nói ra — thà báo lỗi còn hơn nút mất tăm không một lời nào.
          if (lan < 3) {
            lan += 1;
            hen = window.setTimeout(hoi, 1_000 * lan);
          }
        });
    };
    hoi();
    return () => {
      alive = false;
      if (hen) window.clearTimeout(hen);
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
      <header className="khvt-header khvt-header--compact">
        <div className="khvt-header__left">
          <h1 className="khvt-header__title">Kế hoạch vật tư</h1>
          <span className="khvt-header__dot">•</span>
          <span className="khvt-header__desc">Bảng cân đối nhu cầu tồn kho &amp; giữ chỗ</span>
          <div className="khvt-header__sync" title="Dữ liệu tự động cập nhật qua kết nối thời gian thực">
            <Icon name="workflow" size={12} />
            <span>Live Sync</span>
          </div>
        </div>

        {/* Công tắc GOM THEO — Segmented Capsule Switch */}
        <div className="khvt-segmented-switch" role="group" aria-label="Chế độ xem bảng cân đối">
          <button
            type="button"
            className={`khvt-segmented-btn ${gom === "hang" ? "is-active" : ""}`}
            aria-pressed={gom === "hang"}
            onClick={() => setGom("hang")}
          >
            <span>Theo mặt hàng</span>
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
            <span>Theo lệnh sản xuất</span>
            {soGiuLau > 0 && (
              <span className="khvt-badge-count khvt-badge-count--warn" title="Lệnh giữ vật tư lâu chưa vào kế hoạch">
                {num(soGiuLau)}
              </span>
            )}
          </button>
        </div>
      </header>

      {gom === "hang" ? (
        <VatTuKeHoachView
          eventTick={eventTick}
          canDeNghiMua={canDeNghiMua !== false}
          onSoDo={setSoDo}
          onOpenLsx={navigate ? (id) => navigate("ke-hoach-sx", { openLsxId: id }) : undefined}
          onMoFormMua={navigate ? moFormMua : undefined}
        />
      ) : (
        <GiuChoTheoLenhView
          eventTick={eventTick}
          canDeNghiMua={canDeNghiMua !== false}
          onSoGiuLau={setSoGiuLau}
          focusLsxMa={focusLsxMa}
          onOpenLsx={navigate ? (id) => navigate("ke-hoach-sx", { openLsxId: id }) : undefined}
          onMoFormMua={navigate ? moFormMua : undefined}
        />
      )}
    </main>
  );
}
