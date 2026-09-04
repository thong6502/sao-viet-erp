// Phiếu lương 2 cột (Thu | Trừ) — tách từ pages/LuongPage.tsx.
import { Fragment } from "react";
import type {
  LineComponent,
  PayrollLine,
  PayrollPeriod,
} from "../../../../api/client";
import { legacyBonusRows, money } from "../shared/helpers";

// --- Phiếu lương 2 cột (Thu | Trừ) — dùng chung cho self-service + In của HCNS ---------------

export function PayslipCard({
  line: l,
  period,
}: {
  line: PayrollLine;
  period: PayrollPeriod;
}) {
  // 3 khoản phụ cấp KHAI TAY — mỗi khoản một dòng. BẪY CỘNG ĐÔI: `l.allowance` là TỔNG của
  // đúng 2 số (thâm niên + khác) → KHÔNG cộng `allowance` vào tổng thu nữa. Phụ cấp CA
  // (`ca_pay`, chính là `night_pay`) là khoản RIÊNG, nằm NGOÀI `allowance`.
  // Dòng lương cũ: khác = allowance, thâm niên = 0 → vẫn hiện đúng, không mất tiền.
  const pcCa = l.ca_pay ?? l.night_pay;
  const pcThamNien = l.phu_cap_tham_nien ?? 0;

  // Khoản DANH MỤC của dòng (Tầng 3). HAI NGUỒN, HAI CÁCH CỘNG — nhầm là sai tiền:
  //   `employee` = chép từ hồ sơ, ĐÃ NẰM TRONG `l.allowance` ⇒ tách thành dòng riêng thì phải
  //                TRỪ khỏi "Phụ cấp khác", không thì cộng đôi.
  //   `line`     = phát sinh riêng kỳ này, nằm NGOÀI `allowance` ⇒ cộng thẳng thành dòng mới.
  const comps = l.components ?? [];
  const compThuHoSo = comps.filter(
    (c) => c.kind !== "tru" && c.source === "employee",
  );
  const compThuKy = comps.filter(
    (c) => c.kind !== "tru" && c.source === "line",
  );
  const compTru = comps.filter((c) => c.kind === "tru");
  const pcKhacGoc = l.phu_cap_khac ?? l.allowance - pcThamNien;
  const pcKhac = Math.max(
    0,
    pcKhacGoc - compThuHoSo.reduce((s, c) => s + c.amount, 0),
  );
  const compLabel = (c: LineComponent) =>
    c.note ? `${c.name} (${c.note})` : c.name;

  // Dòng phụ "TRONG ĐÓ" — chỉ để NV đối chiếu, TUYỆT ĐỐI KHÔNG cộng vào TỔNG THU: số này đã
  // nằm sẵn trong `luong_cong` (ngày nghỉ phép chỉ trả LƯƠNG VỊ TRÍ, không có lương trách
  // nhiệm). Cùng idiom `phu_cap_tham_nien ⊂ allowance`; cộng nhầm là SAI TIỀN LƯƠNG.
  // Key = nhãn dòng cha → dòng phụ render ngay dưới dòng đó và nằm NGOÀI `incomeTotal`.
  const luongNgayPhep = l.luong_ngay_phep ?? 0;
  const incomeSub: Record<string, [string, number]> =
    luongNgayPhep > 0
      ? {
          "Lương theo công": [
            "Trong đó: lương ngày phép",
            luongNgayPhep,
          ],
        }
      : {};

  const income = [
    ["Lương theo công", l.luong_cong],
    // Hai khoản theo CA THỰC LÀM (từ 03/08/2026) — mỗi khoản MỘT DÒNG, không gộp: phiếu lương
    // phải nói rõ ăn bao nhiêu cơm, bao nhiêu phụ cấp.
    ["Cơm ca", l.meal_allowance_pay ?? 0],
    // Dòng RIÊNG, không gộp vào "Cơm ca": hai khoản khác luật (một theo ca thực làm, một theo
    // giờ tăng ca) và một ngày có thể ăn CẢ HAI. Gộp là hết đường giải thích khi NLĐ hỏi.
    ["Cơm tăng ca", l.com_tang_ca_pay ?? 0],
    ["Phụ cấp ca (theo ca làm)", l.shift_allowance_pay ?? 0],
    // Ô cũ per-người đã ngưng ⇒ chỉ còn hiện ở kỳ CŨ đã chốt (còn số thì mới in dòng), để phiếu
    // lương tháng trước in lại vẫn đúng y nguyên.
    ...(pcCa ? ([["Phụ cấp ca (khai tay — đã ngưng)", pcCa]] as [string, number][]) : []),
    ["Phụ cấp ca đêm (giờ × hệ số)", l.night_premium_pay ?? 0],
    ["Phụ cấp thâm niên", pcThamNien],
    ["Phụ cấp khác", pcKhac],
    ["Chuyên cần", l.chuyen_can],
    ["Lương khoán / sản lượng", l.khoan],
    // Khoán km CÓ trong `gross` của engine nhưng TRƯỚC 04/09/2026 thiếu dòng ở đây ⇒ phiếu lương
    // của tài xế cộng lại thiếu đúng phần km (thu nhập CHÍNH của họ). Chỉ in khi còn số, để phiếu
    // của người không chạy xe không mọc thêm dòng 0đ.
    ...((l.khoan_km ?? 0) !== 0
      ? ([["Khoán km giao hàng", l.khoan_km ?? 0]] as [string, number][])
      : []),
    // Thưởng/PHẠT tổ trưởng — cộng ĐẠI SỐ vào `gross`, in như `Điều chỉnh lương`: có số mới có
    // dòng, và dòng âm là tiền BỊ TRỪ ngay trong khối thu nhập (không phải khấu trừ kỷ luật).
    ...((l.thuong_to_truong ?? 0) !== 0
      ? ([["Thưởng/phạt tổ trưởng (chất lượng)", l.thuong_to_truong ?? 0]] as [string, number][])
      : []),
    ["Tăng ca", l.ot_pay],
    // Khoản danh mục — mỗi khoản MỘT DÒNG, đúng tên chủ đặt (chữa "phụ cấp một cục").
    ...compThuHoSo.map((c) => [compLabel(c), c.amount]),
    ...compThuKy.map((c) => [compLabel(c), c.amount]),
    // Điều chỉnh lương (±) — cộng vào `gross` ở engine nên PHẢI có dòng, không thì tổng lệch.
    ...((l.dieu_chinh_luong ?? 0) !== 0
      ? [["Điều chỉnh lương", l.dieu_chinh_luong ?? 0]]
      : []),
    // 6 cột thưởng CŨ (ngừng ghi 28/07/2026) — chỉ hiện khi còn số, để kỳ đã chốt in y nguyên.
    ...legacyBonusRows(l),
  ] as [string, number][];
  const incomeTotal = income.reduce((s, [, v]) => s + v, 0);

  // BHXH/BHYT/BHTN: backend trả sẵn 3 dòng (nhãn đã kèm tỷ lệ) — AI XEM CŨNG THẤY, không phải đi xin
  // `GET /params` vốn đòi quyền cấu hình lương. Tổng 3 dòng luôn đúng bằng `l.bhxh` đã đóng băng.
  const deduct = [
    ...((l.insurance_lines ?? []).map((r) => [r.label, r.amount]) as [
      string,
      number,
    ][]),
    ["Công đoàn", l.cong_doan],
    ["Thuế TNCN", l.pit],
    ["Đi trễ / nghỉ KP", l.di_tre],
    ["Điện thoại vượt trội", l.dt_vuot_troi],
    ["Phạt biên bản", l.phat_bien_ban],
    ["Đồng phục / phạt 5S", l.phat_5s_dong_phuc],
    ["Giảm trừ khác", l.vi_pham],
    // Khoản danh mục loại TRỪ (mua đồng phục, ứng tiền…) — trừ thẳng vào thực nhận, KHÔNG thuộc
    // trần 30% Điều 102 (trần đó dành cho bồi thường/kỷ luật).
    ...compTru.map((c) => [compLabel(c), c.amount]),
    // 2 dòng RIÊNG: đợt 1 (đã trả giữa tháng qua phiếu) và tạm ứng ad-hoc. Thực nhận = đợt 2.
    ["Thanh toán lương đợt 1", l.luong_dot_1_total ?? 0],
    ["Tạm ứng đã nhận", l.advance_total],
  ] as [string, number][];
  const deductTotal = deduct.reduce((s, [, v]) => s + v, 0);

  return (
    <div className="lg-payslip2 lg-payslip-print">
      <div className="lg-payslip2__head">
        <div>
          <div className="lg-payslip2__title">PHIẾU LƯƠNG</div>
          <div className="lg-payslip2__who">
            {l.employee_name}{" "}
            <span className="ns__code">{l.employee_code}</span>
          </div>
          <div className="cc-card__hint">
            {l.department_name ?? "—"} · Tháng{" "}
            {String(period.month).padStart(2, "0")}/{period.year}
          </div>
        </div>
        <div className="lg-payslip2__meta">
          <div>
            NC chuẩn: <b>{l.standard_cong}</b> · Ngày công:{" "}
            <b>{l.actual_cong}</b>
          </div>
          <div>
            Giờ tăng ca: <b>{(l.ot_minutes / 60).toFixed(1)}h</b> · Mức đóng BH:{" "}
            <b>{money(l.insurance_base)}</b>
          </div>
          <span
            className={`ns-badge ${period.status !== "draft" ? "ns-badge--ok" : "ns-badge--muted"}`}
          >
            {period.status === "paid"
              ? "Đã chi"
              : period.status === "locked"
                ? "Đã chốt"
                : "Tạm tính"}
          </span>
        </div>
      </div>
      <div className="lg-payslip2__cols">
        <table className="lg-payslip2__tbl">
          <thead>
            <tr>
              <th>Các khoản THU</th>
              <th className="lg-num">Số tiền</th>
            </tr>
          </thead>
          <tbody>
            {income.map(([lbl, v]) => {
              const sub = incomeSub[lbl];
              return (
                <Fragment key={lbl}>
                  <tr>
                    <td>{lbl}</td>
                    <td className="lg-num">{v ? money(v) : "—"}</td>
                  </tr>
                  {sub && (
                    <tr className="lg-payslip2__in">
                      <td>{sub[0]}</td>
                      <td className="lg-num">{money(sub[1])}</td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
            <tr className="lg-payslip2__sub">
              <td>TỔNG THU</td>
              <td className="lg-num">{money(incomeTotal)}</td>
            </tr>
          </tbody>
        </table>
        <table className="lg-payslip2__tbl">
          <thead>
            <tr>
              <th>Các khoản TRỪ</th>
              <th className="lg-num">Số tiền</th>
            </tr>
          </thead>
          <tbody>
            {deduct.map(([lbl, v]) => (
              <tr key={lbl}>
                <td>{lbl}</td>
                <td className="lg-num">{v ? money(v) : "—"}</td>
              </tr>
            ))}
            <tr className="lg-payslip2__sub">
              <td>TỔNG TRỪ</td>
              <td className="lg-num">{money(deductTotal)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      {/* 2 dòng thuế (chủ 27/07/2026). `pit_taxable` là thu nhập TÍNH thuế — đã trừ bảo hiểm
          + giảm trừ gia cảnh, KHÔNG phải "tổng thu nhập chịu thuế"; backend không snapshot số
          đó nên gọi đúng tên, đừng dán nhãn "chịu thuế" lên số đã trừ giảm trừ. */}
      {/* <div className="lg-payslip2__tax">
        <span className="lg-payslip2__taxcell">
          <span>Thu nhập tính thuế TNCN</span>
          <b>{money(l.pit_taxable)}đ</b>
        </span>
        <span className="lg-payslip2__taxcell">
          <span>Thu nhập miễn thuế</span>
          <b>{money(l.thu_nhap_mien_thue)}đ</b>
        </span>
        <span className="lg-payslip2__taxnote">
          Thu nhập tính thuế = phần chịu thuế sau khi trừ bảo hiểm bắt buộc và
          giảm trừ gia cảnh — thuế TNCN bấm trên số này. Thu nhập miễn thuế gồm
          tăng ca, ca đêm và các khoản không tích “Chịu thuế” trong danh mục.
        </span>
      </div> */}
      <div className="lg-payslip2__net">
        <span>THỰC NHẬN</span>
        <span>{money(l.net_pay)}đ</span>
      </div>
      <div className="lg-payslip2__sign">
        <div>Người lập phiếu</div>
        <div>
          Người nhận tiền
          <br />
          <span className="cc-card__hint">(ký, ghi rõ họ tên)</span>
        </div>
      </div>
    </div>
  );
}
