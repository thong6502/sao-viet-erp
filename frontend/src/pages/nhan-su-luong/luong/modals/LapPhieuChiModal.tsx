// Modal lập phiếu chi từ phiếu tạm ứng đã duyệt (tách từ pages/LuongPage.tsx).
import { useEffect, useState } from "react";
import {
  api,
  type CompanyBankAccountRow,
  type PaymentVoucherRow,
  type PaymentVoucherType,
  type SalaryAdvance,
} from "../../../../api/client";
import { errText, money, todayYmd } from "../shared/helpers";

/** Lập PHIẾU CHI từ một phiếu tạm ứng ĐÃ DUYỆT (chủ chốt 18/08/2026).
 *
 *  Ba ô nhận diện (nhân viên · mã tạm ứng · số tiền) để CHỈ ĐỌC — backend lấy số tiền từ phiếu
 *  tạm ứng và tên người nhận từ hồ sơ NV, mọi giá trị gửi lên đều bị bỏ qua. Bày ô cho gõ rồi
 *  âm thầm vứt đi là cách nhanh nhất để kế toán tin phiếu chi ghi số họ vừa sửa. */
export function LapPhieuChiModal({
  token,
  adv,
  onClose,
  onDone,
}: {
  token: string;
  adv: SalaryAdvance;
  onClose: () => void;
  onDone: (pc: PaymentVoucherRow) => void;
}) {
  const tenNv = adv.employee_name ?? `NV#${adv.employee_id}`;
  const kyLuong = `${String(adv.period_month).padStart(2, "0")}/${adv.period_year}`;
  const homNay = todayYmd();
  const [vtype, setVtype] = useState<PaymentVoucherType>("cash");
  const [ngay, setNgay] = useState(homNay);
  // Phiếu đợt 1 KHÔNG phải "tạm ứng" — gọi đúng tên khoản để nội dung in trên chứng từ không nói
  // sai bản chất. Sửa được, đây chỉ là chữ điền sẵn.
  const [noiDung, setNoiDung] = useState(
    `${adv.kind === "luong_dot_1" ? "Thanh toán lương đợt 1" : "Tạm ứng lương"} tháng ${kyLuong} — ${tenNv}`,
  );
  const [ghiChu, setGhiChu] = useState("");
  // Địa chỉ + giấy tờ CHỈ in trên mẫu 02-TT tiền mặt (ký nhận tại quỹ), nên bày đúng nhánh tiền
  // mặt như modal phiếu chi bên Kế toán. Chuyển khoản đã có tài khoản thụ hưởng làm bằng chứng.
  const [diaChi, setDiaChi] = useState("");
  const [giayTo, setGiayTo] = useState("");
  const [tkCty, setTkCty] = useState<number | "">("");
  const [tkList, setTkList] = useState<CompanyBankAccountRow[]>([]);
  const [tkLoi, setTkLoi] = useState(false);
  const [thHolder, setThHolder] = useState(adv.employee_name ?? "");
  const [thSo, setThSo] = useState(adv.bank_account ?? "");
  const [thNganHang, setThNganHang] = useState(adv.bank_name ?? "");
  const [thChiNhanh, setThChiNhanh] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const chuyenKhoan = vtype === "bank_transfer";

  // Chỉ nạp tài khoản công ty khi thật sự chọn chuyển khoản — phiếu tiền mặt không cần, mà API
  // này còn đòi ô quyền KHÁC (Tài khoản ngân hàng), gọi bừa là 403 cho cả người chi tiền mặt.
  useEffect(() => {
    if (!chuyenKhoan) return;
    let alive = true;
    api.accounting
      .companyAccounts(token, true, "pay")
      .then((rows) => {
        if (!alive) return;
        setTkList(rows);
        setTkLoi(false);
        if (rows.length === 1) setTkCty(rows[0].id);
      })
      .catch(() => {
        if (!alive) return;
        setTkList([]);
        setTkLoi(true);
      });
    return () => {
      alive = false;
    };
  }, [chuyenKhoan, token]);

  async function save() {
    const nd = noiDung.trim();
    if (!nd) {
      setErr("Nhập nội dung chi.");
      return;
    }
    if (ngay > homNay) {
      setErr("Ngày chứng từ không được ở tương lai.");
      return;
    }
    if (
      chuyenKhoan &&
      (tkCty === "" ||
        !thHolder.trim() ||
        !thSo.trim() ||
        !thNganHang.trim())
    ) {
      setErr(
        "Chuyển khoản phải có tài khoản trích nợ và đủ tên · số tài khoản · ngân hàng thụ hưởng.",
      );
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const pc = await api.accounting.createVoucherFromAdvance(token, {
        salary_advance_id: adv.id,
        amount: adv.amount,
        voucher_type: vtype,
        voucher_date: ngay,
        content: nd,
        note: ghiChu.trim() || null,
        cash_recipient_address: chuyenKhoan ? null : diaChi.trim() || null,
        cash_recipient_identity: chuyenKhoan ? null : giayTo.trim() || null,
        // `bank_fee_bearer` cố ý KHÔNG bày thành ô: lương chuyển đi thì công ty chịu phí, nếu
        // không nhân viên nhận hụt so với số đã duyệt. Backend mặc định đúng "payer".
        company_bank_account_id: chuyenKhoan ? Number(tkCty) : null,
        beneficiary_account_holder: chuyenKhoan ? thHolder.trim() : null,
        beneficiary_account_number: chuyenKhoan ? thSo.trim() : null,
        beneficiary_bank_name: chuyenKhoan ? thNganHang.trim() : null,
        beneficiary_bank_branch: chuyenKhoan ? thChiNhanh.trim() || null : null,
      });
      onDone(pc);
    } catch (e) {
      // 409 (đã có phiếu chi) · 422 (chưa duyệt) — backend trả câu tiếng Việt đủ ý, giữ nguyên.
      setErr(errText(e));
      setBusy(false);
    }
  }

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box">
        <header className="ns-modal__head">
          <h2>Lập phiếu chi — {adv.code ?? `tạm ứng #${adv.id}`}</h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        {/* `lg-pc-body` = flex column + gap: mọi khối con tự giãn cách đều nhau, không phải rắc
            `margin-top` số cứng lên từng ô (khối chuyển khoản ẩn/hiện làm lệch nhịp ngay). */}
        <div className="ns-modal__body lg-pc-body">
          {err && <div className="banner banner--error">{err}</div>}

          <div className="lg-pc-ro">
            <div className="lg-pc-ro__cell">
              <span className="lg-pc-ro__lbl">Nhân viên nhận tiền</span>
              <b className="lg-pc-ro__val">{tenNv}</b>
            </div>
            <div className="lg-pc-ro__cell">
              <span className="lg-pc-ro__lbl">Mã phiếu tạm ứng</span>
              <b className="lg-pc-ro__val lg-pc-ro__val--code">
                {adv.code ?? "—"}
              </b>
            </div>
            <div className="lg-pc-ro__cell">
              <span className="lg-pc-ro__lbl">Số tiền</span>
              <b className="lg-pc-ro__val lg-pc-ro__val--money">
                {money(adv.amount)}đ
              </b>
            </div>
          </div>
          <p className="lg-pc-hint">
            Ba ô trên lấy thẳng từ phiếu tạm ứng đã duyệt, không sửa được — phiếu
            chi luôn đúng bằng số đã duyệt.
          </p>

          <div className="ns-grid">
            <label className="ns-field">
              <span className="ns-field__label">Hình thức chi *</span>
              <select
                value={vtype}
                onChange={(e) =>
                  setVtype(e.target.value as PaymentVoucherType)
                }
              >
                <option value="cash">Tiền mặt</option>
                <option value="bank_transfer">Chuyển khoản</option>
              </select>
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Ngày chứng từ *</span>
              {/* `max` chặn ngay ở ô chọn — backend cũng từ chối ngày tương lai (422). */}
              <input
                type="date"
                max={homNay}
                value={ngay}
                onChange={(e) => setNgay(e.target.value)}
              />
            </label>
          </div>

          {chuyenKhoan && (
            <>
              {tkLoi && (
                <div className="banner banner--warn">
                  Không đọc được danh sách tài khoản công ty (thiếu quyền Tài
                  khoản ngân hàng). Chọn “Tiền mặt”, hoặc nhờ kế toán có quyền
                  lập giúp.
                </div>
              )}
              {!tkLoi && tkList.length === 0 && (
                <div className="banner banner--warn">
                  Chưa có tài khoản công ty bật “dùng để chi”. Khai báo ở mục Tài
                  khoản ngân hàng trước khi lập UNC.
                </div>
              )}
              <label className="ns-field">
                <span className="ns-field__label">Tài khoản trích nợ *</span>
                <select
                  value={tkCty}
                  onChange={(e) =>
                    setTkCty(e.target.value ? Number(e.target.value) : "")
                  }
                >
                  <option value="">— chọn tài khoản công ty —</option>
                  {tkList.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.bank_name} · {t.account_number} · {t.currency}
                    </option>
                  ))}
                </select>
              </label>
              <div className="ns-grid">
                <label className="ns-field">
                  <span className="ns-field__label">Chủ tài khoản nhận *</span>
                  <input
                    value={thHolder}
                    onChange={(e) => setThHolder(e.target.value)}
                  />
                </label>
                <label className="ns-field">
                  <span className="ns-field__label">Số tài khoản nhận *</span>
                  <input
                    inputMode="numeric"
                    value={thSo}
                    onChange={(e) => setThSo(e.target.value)}
                  />
                </label>
                <label className="ns-field">
                  <span className="ns-field__label">Ngân hàng nhận *</span>
                  <input
                    value={thNganHang}
                    onChange={(e) => setThNganHang(e.target.value)}
                  />
                </label>
                <label className="ns-field">
                  <span className="ns-field__label">Chi nhánh</span>
                  <input
                    value={thChiNhanh}
                    onChange={(e) => setThChiNhanh(e.target.value)}
                  />
                </label>
              </div>
              <p className="lg-pc-hint">
                Điền sẵn theo tài khoản ngân hàng khai trong hồ sơ nhân viên —
                soát lại trước khi chuyển.
              </p>
            </>
          )}

          {/* Nhánh TIỀN MẶT: hai ô của mẫu 02-TT người nhận ký tại quỹ. Bỏ trống được — hồ sơ
              nhân viên thường đã có, đây là chỗ ghi khi giấy tờ xuất trình khác hồ sơ. */}
          {!chuyenKhoan && (
            <div className="ns-grid">
              <label className="ns-field">
                <span className="ns-field__label">Địa chỉ người nhận</span>
                <input
                  value={diaChi}
                  onChange={(e) => setDiaChi(e.target.value)}
                />
              </label>
              <label className="ns-field">
                <span className="ns-field__label">CCCD/Giấy tờ</span>
                <input
                  value={giayTo}
                  onChange={(e) => setGiayTo(e.target.value)}
                />
              </label>
            </div>
          )}

          <label className="ns-field">
            <span className="ns-field__label">Nội dung chi *</span>
            <input
              value={noiDung}
              onChange={(e) => setNoiDung(e.target.value)}
            />
          </label>
          <label className="ns-field">
            <span className="ns-field__label">Ghi chú</span>
            <input value={ghiChu} onChange={(e) => setGhiChu(e.target.value)} />
          </label>
        </div>
        <footer className="ns-modal__foot">
          <span className="lg-pc-warn">
            Lập phiếu chi là tiền đã ra khỏi két. Lập xong không sửa được, chỉ
            huỷ được.
          </span>
          <div className="ns-modal__footright">
            <button
              className="btn btn--ghost"
              onClick={onClose}
              disabled={busy}
            >
              Hủy
            </button>
            <button className="btn btn--primary" onClick={save} disabled={busy}>
              {busy ? "Đang lập…" : "Lập phiếu chi"}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
