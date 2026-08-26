// Tab Phiếu lương của tôi (tách từ pages/LuongPage.tsx).
import { useEffect, useState } from "react";
import { AlertTriangle, FileText } from "lucide-react";
import { api, type ChoPhat } from "../../../../api/client";
import { fmtDateTime } from "../../../../utils/format";
import { PayslipCard } from "../components/PayslipCard";

// --- Tab: Phiếu lương của tôi -----------------------------------------------

/** Câu giải thích vì sao chưa xem được phiếu — CHỈ tháng + lý do, không bao giờ kèm tiền.
 *  Bốn tình huống trước đây gộp thành một câu "Chưa có phiếu lương", nên thợ tưởng bị sót
 *  lương rồi đi hỏi HCNS (`docs/prd-phieu-luong-tu-phuc-vu.md` §1.2). */
function lyDoChuaCoPhieu(cp: ChoPhat | null): { tieu_de: string; mo_ta: string } {
  if (!cp)
    return {
      tieu_de: "Chưa có phiếu lương",
      mo_ta: "Bạn chưa có kỳ lương nào trong hệ thống. Liên hệ HCNS nếu bạn nghĩ đây là nhầm lẫn.",
    };
  const ky = `tháng ${String(cp.month).padStart(2, "0")}/${cp.year}`;
  if (cp.tinh_trang === "hen_gio")
    return {
      tieu_de: `Phiếu lương ${ky} sắp được phát`,
      mo_ta: `Phiếu sẽ mở lúc ${cp.mo_luc ? fmtDateTime(cp.mo_luc) : "giờ đã hẹn"}. Quay lại sau thời điểm đó.`,
    };
  if (cp.tinh_trang === "da_dong")
    return {
      tieu_de: `Phiếu lương ${ky} đã đóng`,
      mo_ta: "Thời hạn xem phiếu của kỳ này đã hết. Cần xem lại thì liên hệ HCNS.",
    };
  if (cp.tinh_trang === "chua_phat")
    return {
      tieu_de: `Phiếu lương ${ky} đang được lập`,
      mo_ta: "Bảng lương kỳ này chưa được phát. Phiếu sẽ hiện ngay khi HCNS công bố.",
    };
  // Máy chủ thêm trạng thái mới mà màn chưa biết: nói chung chung còn hơn nói SAI. Đừng gộp ca
  // này vào "đang được lập" — một ngày nào đó nó sẽ là câu sai với một tình huống thật.
  return {
    tieu_de: `Chưa xem được phiếu lương ${ky}`,
    mo_ta: "Liên hệ HCNS để biết thời điểm phát phiếu.",
  };
}

export function PhieuLuongTab({ token }: { token: string }) {
  const [data, setData] = useState<Awaited<
    ReturnType<typeof api.luong.myPayslip>
  > | null>(null);
  // Kỳ đang xem. `null` = để máy chủ chọn kỳ mới nhất đang mở — mở màn luôn về phiếu mới nhất,
  // KHÔNG nhớ lựa chọn cũ: người ta vào đây để xem lương tháng này, tra lại là việc phụ.
  const [ky, setKy] = useState<{ year: number; month: number } | null>(null);
  useEffect(() => {
    // Không gọi `getParams` nữa: 3 dòng BHXH/BHYT/BHTN do backend trả kèm phiếu, nên nhân viên
    // KHÔNG cần quyền cấu hình lương (trước đây gọi rồi ăn 403 → phiếu rơi về dòng gộp).
    api.luong
      .myPayslip(token, ky ?? undefined)
      .then(setData)
      .catch(() => setData(null));
  }, [token, ky]);

  if (!data)
    return (
      <div className="lg-payslip-empty-container">
        <div className="lg-payslip-empty-card">
          <p className="lg-payslip-empty-desc">Đang tải dữ liệu...</p>
        </div>
      </div>
    );
  if (!data.has_employee) {
    return (
      <div className="lg-payslip-empty-container">
        <div className="lg-payslip-empty-card">
          <div className="lg-payslip-empty-icon lg-payslip-empty-icon--warn">
            <AlertTriangle size={24} />
          </div>
          <h3 className="lg-payslip-empty-title">Tài khoản chưa gắn hồ sơ</h3>
          <p className="lg-payslip-empty-desc">
            Tài khoản của bạn chưa được liên kết với bất kỳ hồ sơ nhân viên nào.
            Vui lòng liên hệ bộ phận HCNS để được thiết lập.
          </p>
        </div>
      </div>
    );
  }
  const dsKy = data.ky_xem_duoc ?? [];
  const l = data.line;
  if (!l || !data.period) {
    const { tieu_de, mo_ta } = lyDoChuaCoPhieu(data.cho_phat);
    return (
      <div className="lg-payslip-empty-container">
        <div className="lg-payslip-empty-card">
          <div className="lg-payslip-empty-icon">
            <FileText size={24} />
          </div>
          <h3 className="lg-payslip-empty-title">{tieu_de}</h3>
          <p className="lg-payslip-empty-desc">{mo_ta}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="lg-payslip">
      <div
        className="lg-payslip-noprint"
        style={{ textAlign: "center", marginBottom: 8 }}
      >
        {/* Ô chọn kỳ CHỈ hiện khi có từ 2 kỳ trở lên — một kỳ mà bày dropdown là thêm khối UI
            vô nghĩa. Kỳ nào vào được danh sách này là máy chủ đã duyệt cửa sổ công bố rồi. */}
        {dsKy.length > 1 && (
          <select
            className="input"
            style={{ width: "auto", marginRight: 8 }}
            value={`${data.period.year}-${data.period.month}`}
            onChange={(e) => {
              const [y, m] = e.target.value.split("-").map(Number);
              setKy({ year: y, month: m });
            }}
            title="Chọn kỳ lương muốn xem lại"
          >
            {dsKy.map((k) => (
              <option key={`${k.year}-${k.month}`} value={`${k.year}-${k.month}`}>
                {`Tháng ${String(k.month).padStart(2, "0")}/${k.year}`}
                {k.dong_phieu_luc ? ` — xem tới ${fmtDateTime(k.dong_phieu_luc)}` : ""}
              </option>
            ))}
          </select>
        )}
        <button className="btn btn--ghost" onClick={() => window.print()}>
          🖨 In phiếu
        </button>
        {/* Đang xem được kỳ cũ mà kỳ mới chưa phát: nói ra, đừng để họ tưởng bị sót lương. */}
        {data.cho_phat && (
          <div className="lg-payslip-noprint" style={{ marginTop: 6, fontSize: 13, opacity: 0.75 }}>
            {lyDoChuaCoPhieu(data.cho_phat).tieu_de}.
          </div>
        )}
      </div>
      <PayslipCard line={l} period={data.period} />
    </div>
  );
}
