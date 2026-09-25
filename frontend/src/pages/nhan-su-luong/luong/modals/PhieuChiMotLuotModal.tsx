// Chi MỘT LƯỢT cho nhiều phiếu tạm ứng / lương đợt 1 đã duyệt ⇒ MỘT phiếu chi cho cả lô (chủ chốt
// 25/09/2026: "cho dù một nhân viên hay 1000 nhân viên cùng lúc, cũng chỉ 1 phiếu chi"). Số tiền =
// tổng lô, người nhận "Theo bảng kê đính kèm (N người)" — máy chủ tự điền; bảng kê in ở Kế toán →
// Phiếu chi (chủ: tab Tạm ứng không cần nút in bảng kê).
// Chuyển khoản: lập SAU khi ngân hàng báo kết quả, chỉ để lại người đã chuyển THÀNH CÔNG (ai lỗi
// bấm × bỏ khỏi lượt, chi sau). Sai thì huỷ cả phiếu chi rồi lập lại — không gỡ lẻ từng người.
import { useEffect, useMemo, useState } from "react";
import {
  api,
  type CompanyBankAccountRow,
  type PaymentVoucherType,
  type SalaryAdvance,
  type VoucherBatchResult,
} from "../../../../api/client";
import { errText, money, todayYmd, vuongIds } from "../shared/helpers";

const coTaiKhoan = (a: SalaryAdvance) => !!a.bank_account?.trim() && !!a.bank_name?.trim();

export function PhieuChiMotLuotModal({
  token,
  advs,
  onClose,
  onDone,
}: {
  token: string;
  advs: SalaryAdvance[];
  onClose: () => void;
  onDone: (r: VoucherBatchResult) => void;
}) {
  const homNay = todayYmd();
  const [ds, setDs] = useState<SalaryAdvance[]>(advs);
  const [vtype, setVtype] = useState<PaymentVoucherType>("cash");
  const [ngay, setNgay] = useState(homNay);
  const [ghiChu, setGhiChu] = useState("");
  const [tkCty, setTkCty] = useState<number | "">("");
  // `null` = đang tải — không bày cảnh báo "chưa có tài khoản" trong lúc chờ.
  const [tkList, setTkList] = useState<CompanyBankAccountRow[] | null>(null);
  const [tkLoi, setTkLoi] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // Phiếu tạm ứng máy chủ báo VƯỚNG (lượt bị chặn cả) — nút bỏ đúng chúng khỏi lượt rồi lập lại.
  const [vuong, setVuong] = useState<number[]>([]);
  const chuyenKhoan = vtype === "bank_transfer";
  const thieuTk = useMemo(() => ds.filter((a) => !coTaiKhoan(a)), [ds]);
  const tong = ds.reduce((s, a) => s + a.amount, 0);
  const soNguoi = new Set(ds.map((a) => a.employee_id)).size;

  // Cùng lối hộp lập từng phiếu: chỉ nạp tài khoản công ty khi chọn chuyển khoản — API đòi ô quyền
  // Tài khoản ngân hàng, gọi bừa là 403 cho cả người chỉ chi tiền mặt.
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

  async function luu() {
    if (ds.length === 0) {
      setErr("Không còn phiếu nào trong lượt.");
      return;
    }
    if (ngay > homNay) {
      setErr("Ngày chứng từ không được ở tương lai.");
      return;
    }
    if (chuyenKhoan && tkCty === "") {
      setErr("Chọn tài khoản công ty trích nợ.");
      return;
    }
    if (chuyenKhoan && thieuTk.length > 0) {
      setErr(
        `${thieuTk.length} người chưa khai số tài khoản trong hồ sơ — bỏ họ khỏi lượt này hoặc chọn Tiền mặt.`,
      );
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const r = await api.accounting.createVouchersFromAdvances(token, {
        salary_advance_ids: ds.map((a) => a.id),
        voucher_type: vtype,
        voucher_date: ngay,
        company_bank_account_id: chuyenKhoan ? Number(tkCty) : null,
        note: ghiChu.trim() || null,
      });
      onDone(r);
    } catch (e) {
      setErr(errText(e));
      setVuong(vuongIds(e));
      setBusy(false);
    }
  }

  return (
    <div className="ns-modal" role="dialog" aria-modal="true" aria-label="Lập phiếu chi một lượt">
      <div className="ns-modal__box ns-modal__box--wide lg-pcl">
        <header className="ns-modal__head">
          <h2>Lập 1 phiếu chi cho {ds.length} phiếu đã duyệt</h2>
          <button className="ns-modal__x" onClick={onClose} aria-label="Đóng">
            ×
          </button>
        </header>
        <div className="ns-modal__body lg-pc-body">
          {err && (
            <div className="banner banner--error lg-pcl__thieu">
              <span>{err}</span>
              {vuong.length > 0 && (
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => {
                    setDs((cu) => cu.filter((a) => !vuong.includes(a.id)));
                    setVuong([]);
                    setErr(null);
                  }}
                >
                  Bỏ {vuong.length} phiếu vướng khỏi lượt
                </button>
              )}
            </div>
          )}
          <div className="ns-grid">
            <label className="ns-field">
              <span className="ns-field__label">Hình thức chi *</span>
              <select
                value={vtype}
                onChange={(e) => {
                  setVtype(e.target.value as PaymentVoucherType);
                  setErr(null); // lỗi của hình thức cũ không còn đúng
                }}
              >
                <option value="cash">Tiền mặt</option>
                <option value="bank_transfer">Chuyển khoản</option>
              </select>
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Ngày chứng từ *</span>
              <input type="date" max={homNay} value={ngay} onChange={(e) => setNgay(e.target.value)} />
            </label>
          </div>

          {chuyenKhoan && (
            <>
              {tkLoi && (
                <div className="banner banner--warn">
                  Không đọc được danh sách tài khoản công ty (thiếu quyền Tài khoản ngân hàng). Chọn
                  “Tiền mặt”, hoặc nhờ kế toán có quyền lập giúp.
                </div>
              )}
              {!tkLoi && tkList !== null && tkList.length === 0 && (
                <div className="banner banner--warn">
                  Chưa có tài khoản công ty bật “dùng để chi”. Khai báo ở mục Tài khoản ngân hàng
                  trước khi lập UNC.
                </div>
              )}
              <label className="ns-field">
                <span className="ns-field__label">Tài khoản trích nợ *</span>
                <select
                  value={tkCty}
                  onChange={(e) => setTkCty(e.target.value ? Number(e.target.value) : "")}
                >
                  <option value="">— chọn tài khoản công ty —</option>
                  {(tkList ?? []).map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.bank_name} · {t.account_number} · {t.currency}
                    </option>
                  ))}
                </select>
              </label>
              {thieuTk.length > 0 && (
                <div className="banner banner--warn lg-pcl__thieu">
                  <span>
                    {thieuTk.length} người chưa khai số tài khoản / ngân hàng trong hồ sơ nhân sự —
                    không chuyển khoản được.
                  </span>
                  <button
                    type="button"
                    className="btn btn--ghost"
                    onClick={() => setDs((cu) => cu.filter(coTaiKhoan))}
                  >
                    Bỏ {thieuTk.length} người này khỏi lượt
                  </button>
                </div>
              )}
            </>
          )}

          <label className="ns-field">
            <span className="ns-field__label">Ghi chú (chung cho cả lượt)</span>
            <input value={ghiChu} onChange={(e) => setGhiChu(e.target.value)} />
          </label>
          <p className="lg-pc-hint">
            Cả lô ra <b>MỘT phiếu chi</b>, số tiền bằng tổng lô;{" "}
            {soNguoi > 1
              ? `người nhận ghi “Theo bảng kê đính kèm (${soNguoi} người)” — bảng kê in ở Kế toán → Phiếu chi.`
              : "lô một người thì phiếu chi ghi tên người đó."}
          </p>
          {chuyenKhoan && (
            <div className="banner banner--warn">
              Chỉ để lại những người <b>ngân hàng đã chuyển THÀNH CÔNG</b>. Ai bị trả lỗi thì bấm ×
              bỏ khỏi lượt này, chi sau — lập xong mà sai thì phải huỷ cả phiếu chi rồi lập lại.
            </div>
          )}

          <div className="lg-pcl__bang">
            <table className="ns__table">
              <thead>
                <tr>
                  <th>Nhân viên</th>
                  <th>Loại</th>
                  <th className="lg-num">Số tiền</th>
                  {chuyenKhoan && <th>Tài khoản nhận</th>}
                  <th aria-label="Bỏ khỏi lượt" />
                </tr>
              </thead>
              <tbody>
                {ds.length === 0 ? (
                  <tr>
                    <td colSpan={chuyenKhoan ? 5 : 4} className="lg-pcl__trong">
                      Không còn phiếu nào trong lượt.
                    </td>
                  </tr>
                ) : (
                  ds.map((a) => (
                    <tr key={a.id}>
                      <td>
                        <div className="lg-pcl__ten">{a.employee_name ?? `NV#${a.employee_id}`}</div>
                        <div className="lg-pcl__ma">{a.code ?? `#${a.id}`}</div>
                      </td>
                      <td>{a.kind === "luong_dot_1" ? "Lương đợt 1" : "Tạm ứng"}</td>
                      <td className="lg-num">{money(a.amount)}đ</td>
                      {chuyenKhoan && (
                        <td>
                          {coTaiKhoan(a) ? (
                            <>
                              {a.bank_account} · {a.bank_name}
                            </>
                          ) : (
                            <span className="lg-pcl__loi">Chưa khai tài khoản</span>
                          )}
                        </td>
                      )}
                      <td className="lg-pcl__bo">
                        <button
                          type="button"
                          className="ns-modal__x"
                          aria-label={`Bỏ ${a.employee_name ?? a.id} khỏi lượt`}
                          title="Bỏ khỏi lượt này"
                          onClick={() => setDs((cu) => cu.filter((x) => x.id !== a.id))}
                        >
                          ×
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
        <footer className="ns-modal__foot">
          <span className="lg-pcl__tong">
            1 phiếu chi · {soNguoi} người · {ds.length} phiếu · tổng <b>{money(tong)}đ</b>
          </span>
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Hủy
          </button>
          <button
            className="btn btn--primary"
            onClick={() => void luu()}
            disabled={busy || ds.length === 0}
          >
            {busy ? "Đang lập…" : "Lập 1 phiếu chi"}
          </button>
        </footer>
      </div>
    </div>
  );
}
