// BÁO CÁO KINH DOANH theo khách hàng (24/09/2026).
//
// Trả lời: trong kỳ, mỗi khách đặt những đơn nào, đơn gồm sản phẩm gì, đơn giá bao nhiêu, cọc phải
// thu / đã nhận bao nhiêu. Chủ chốt: chỉ ĐƠN ĐÃ CHỐT, vào kỳ theo NGÀY CHỐT, phạm vi theo ô quyền
// riêng `bao_cao_kinh_doanh` (sale chỉ thấy đơn mình bán — server lọc, màn này không lọc thêm).
//
// Tải CẢ KỲ một lần rồi lọc khách ở trình duyệt: ô chọn khách cần danh sách khách có đơn trong kỳ,
// mà danh sách đó chính là kết quả. Nút Xuất Excel thì gửi `customer_id` lên để file chỉ có khách đó.
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, api, type BaoCaoKinhDoanh, type BaoCaoKinhDoanhKhach } from "../../api/client";
import { useAuth } from "../../auth/useAuth";
import { Button } from "../../components/Button";
import { Icon } from "../../components/Icons";
import { fmtDate, money } from "../../utils/format";
import "./bao-cao-kinh-doanh.css";

function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function dauThang(d = new Date()): string {
  return ymd(new Date(d.getFullYear(), d.getMonth(), 1));
}

function Tien({ v, nhat = false }: { v: number | null | undefined; nhat?: boolean }) {
  if (!v) return <span className="bckd__khong">—</span>;
  return <span className={nhat ? "bckd__tien bckd__tien--nhat" : "bckd__tien"}>{money(v)}</span>;
}

function KhoiKhach({ k }: { k: BaoCaoKinhDoanhKhach }) {
  const [mo, setMo] = useState(false);
  return (
    <>
      <tr className="bckd__khach" onClick={() => setMo((x) => !x)} aria-expanded={mo}>
        <td>
          <button type="button" className="bckd__mo" aria-label={mo ? "Thu gọn" : "Xem các đơn"}>
            <Icon name="chevron" size={14} className={mo ? "bckd__caret is-open" : "bckd__caret"} />
          </button>
        </td>
        <td>
          <div className="bckd__ten">{k.ten}</div>
          {k.ma && <div className="bckd__phu">{k.ma}</div>}
        </td>
        <td className="bckd__so">{k.so_don}</td>
        <td className="bckd__so"><Tien v={k.tong_vat} /></td>
        <td className="bckd__so"><Tien v={k.coc_phai_thu} /></td>
        <td className="bckd__so"><Tien v={k.coc_da_nhan} /></td>
        <td className="bckd__so"><Tien v={k.coc_con_thieu} nhat /></td>
      </tr>
      {mo &&
        k.don.map((d) => (
          <tr key={d.order_id} className="bckd__don-hang">
            <td />
            <td colSpan={6}>
              <div className="bckd__don">
                <div className="bckd__don-dau">
                  <strong>{d.order_no}</strong>
                  <span>Chốt {fmtDate(d.ngay_chot)}</span>
                  {d.sale && <span>Sale: {d.sale}</span>}
                  {d.po_khach && <span>PO: {d.po_khach}</span>}
                  <span className="bckd__don-coc">
                    {!d.coc_pct && !d.coc_da_nhan ? (
                      "Không cọc"
                    ) : (
                      <>
                        Cọc {d.coc_pct ? `${d.coc_pct}%` : ""}: phải thu <Tien v={d.coc_phai_thu} /> · đã
                        nhận <Tien v={d.coc_da_nhan} />
                        {d.coc_con_thieu > 0 && (
                          <> · <span className="bckd__thieu">còn thiếu {money(d.coc_con_thieu)}</span></>
                        )}
                      </>
                    )}
                  </span>
                </div>
                <table className="bckd__dong">
                  <thead>
                    <tr>
                      <th>Sản phẩm</th>
                      <th className="bckd__so">SL</th>
                      <th>ĐVT</th>
                      <th className="bckd__so">Đơn giá</th>
                      <th className="bckd__so">VAT</th>
                      <th className="bckd__so">Thành tiền</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.dong.map((ln, i) => (
                      <tr key={i}>
                        <td>{ln.ten || "—"}</td>
                        <td className="bckd__so">{ln.so_luong.toLocaleString("vi-VN")}</td>
                        <td>{ln.dvt ?? ""}</td>
                        <td className="bckd__so"><Tien v={ln.don_gia} /></td>
                        <td className="bckd__so">{ln.vat_pct ? `${ln.vat_pct}%` : "—"}</td>
                        <td className="bckd__so"><Tien v={ln.thanh_tien} /></td>
                      </tr>
                    ))}
                    <tr className="bckd__dong-cong">
                      <td colSpan={5}>Tổng đơn (chưa VAT · có VAT)</td>
                      <td className="bckd__so">
                        <Tien v={d.tong} /> · <Tien v={d.tong_vat} nhat />
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </td>
          </tr>
        ))}
    </>
  );
}

export function BaoCaoKinhDoanhPage() {
  const { token } = useAuth();
  const [tuNgay, setTuNgay] = useState(dauThang());
  const [denNgay, setDenNgay] = useState(ymd(new Date()));
  const [khachId, setKhachId] = useState<number | "">("");
  const [data, setData] = useState<BaoCaoKinhDoanh | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dangXuat, setDangXuat] = useState(false);

  const tai = useCallback(async () => {
    if (!token) return;
    // Ô ngày đang gõ dở (năm "0008", ô trống) thì CHỜ, đừng gọi server — gọi là ăn câu lỗi kiểm
    // dữ liệu tiếng Anh của máy chủ hiện thẳng lên màn (bắt được khi bấm thử 24/09/2026).
    const hopLe = (s: string) => /^\d{4}-\d{2}-\d{2}$/.test(s) && Number(s.slice(0, 4)) >= 2000;
    if (!hopLe(tuNgay) || !hopLe(denNgay)) return;
    if (tuNgay > denNgay) {
      setError("Từ ngày phải trước hoặc bằng đến ngày.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setData(await api.baoCaoKinhDoanh.xem(token, { tuNgay, denNgay }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Không tải được báo cáo.");
    } finally {
      setLoading(false);
    }
  }, [token, tuNgay, denNgay]);

  useEffect(() => {
    void tai();
  }, [tai]);

  // Khách vừa chọn không còn trong kỳ mới ⇒ về "Tất cả", đừng giữ một bộ lọc ra bảng trống.
  useEffect(() => {
    if (khachId !== "" && data && !data.khach.some((k) => k.customer_id === khachId)) setKhachId("");
  }, [data, khachId]);

  const khachHien = useMemo(
    () => (data?.khach ?? []).filter((k) => khachId === "" || k.customer_id === khachId),
    [data, khachId],
  );
  const tong = useMemo(() => {
    const t = { so_don: 0, tong_vat: 0, coc_phai_thu: 0, coc_da_nhan: 0, coc_con_thieu: 0 };
    for (const k of khachHien) {
      t.so_don += k.so_don;
      t.tong_vat += k.tong_vat;
      t.coc_phai_thu += k.coc_phai_thu;
      t.coc_da_nhan += k.coc_da_nhan;
      t.coc_con_thieu += k.coc_con_thieu;
    }
    return t;
  }, [khachHien]);

  async function xuatExcel() {
    if (!token) return;
    setDangXuat(true);
    try {
      const { url, ten } = await api.baoCaoKinhDoanh.xuatExcel(token, {
        tuNgay,
        denNgay,
        customerId: khachId === "" ? null : khachId,
      });
      const a = document.createElement("a");
      a.href = url;
      a.download = ten;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Không xuất được file.");
    } finally {
      setDangXuat(false);
    }
  }

  return (
    <main className="bckd">
      <header className="bckd__head">
        <div>
          <h1 className="bckd__title">Báo cáo kinh doanh</h1>
          <p className="bckd__sub">Đơn đã chốt trong kỳ, theo khách hàng · sản phẩm · đơn giá · cọc</p>
        </div>
        <Button variant="ghost" onClick={() => void xuatExcel()} disabled={dangXuat || !data || khachHien.length === 0}>
          <Icon name="table" size={14} />{" "}
          {dangXuat ? "Đang xuất…" : khachId === "" ? "Xuất Excel" : "Xuất Excel khách này"}
        </Button>
      </header>

      <section className="bckd__loc" aria-label="Bộ lọc">
        <label className="bckd__o">
          <span>Từ ngày chốt</span>
          <input type="date" value={tuNgay} onChange={(e) => setTuNgay(e.target.value)} />
        </label>
        <label className="bckd__o">
          <span>Đến ngày</span>
          <input type="date" value={denNgay} onChange={(e) => setDenNgay(e.target.value)} />
        </label>
        <label className="bckd__o bckd__o--rong">
          <span>Khách hàng</span>
          <select
            value={khachId === "" ? "" : String(khachId)}
            onChange={(e) => setKhachId(e.target.value === "" ? "" : Number(e.target.value))}
          >
            <option value="">Tất cả khách hàng ({data?.khach.length ?? 0})</option>
            {(data?.khach ?? [])
              .filter((k) => k.customer_id != null)
              .map((k) => (
                <option key={k.customer_id} value={k.customer_id!}>
                  {k.ma ? `${k.ma} — ${k.ten}` : k.ten} ({k.so_don} đơn)
                </option>
              ))}
          </select>
        </label>
      </section>

      {error && <div className="banner banner--error" role="alert">{error}</div>}

      <section className="bckd__kpi" aria-label="Tổng hợp">
        <div><span>Số đơn</span><strong>{tong.so_don}</strong></div>
        <div><span>Doanh số (có VAT)</span><strong>{money(tong.tong_vat)}</strong></div>
        <div><span>Cọc phải thu</span><strong>{money(tong.coc_phai_thu)}</strong></div>
        <div><span>Cọc đã nhận</span><strong>{money(tong.coc_da_nhan)}</strong></div>
        <div className={tong.coc_con_thieu ? "is-thieu" : ""}>
          <span>Cọc còn thiếu</span><strong>{money(tong.coc_con_thieu)}</strong>
        </div>
      </section>

      <div className="bckd__bang-khung">
        <table className="bckd__bang">
          <thead>
            <tr>
              <th aria-label="Mở" />
              <th>Khách hàng</th>
              <th className="bckd__so">Số đơn</th>
              <th className="bckd__so">Doanh số (có VAT)</th>
              <th className="bckd__so">Cọc phải thu</th>
              <th className="bckd__so">Cọc đã nhận</th>
              <th className="bckd__so">Còn thiếu</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} className="bckd__trong">Đang tải…</td></tr>
            ) : khachHien.length === 0 ? (
              <tr><td colSpan={7} className="bckd__trong">Không có đơn đã chốt nào trong kỳ này.</td></tr>
            ) : (
              khachHien.map((k) => <KhoiKhach key={k.customer_id ?? "khong-gan"} k={k} />)
            )}
          </tbody>
        </table>
      </div>
    </main>
  );
}
