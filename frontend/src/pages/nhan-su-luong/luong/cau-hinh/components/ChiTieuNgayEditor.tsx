// Chỉ tiêu ngày của tổ lương khoán / sản lượng (chủ 16/09/2026) — CHỈ là chỗ khai báo.
// Chủ dặn: "chưa cần phải đâu vào đâu cả, chỉ cần tạo ra đã" ⇒ engine tính lương KHÔNG đọc số
// này; bảng lương / phiếu lương không đổi. Mỗi lần đổi chỉ tiêu là một MỐC "áp dụng từ ngày", mốc
// cũ giữ nguyên để sau này đem so sản lượng các tháng trước vẫn đúng chỉ tiêu của tháng đó.
//
// Dáng thẻ theo đúng khuôn Cấu hình lương (chủ chê bản đầu "xấu quá", 16/09/2026): số ĐANG ÁP DỤNG
// đặt gọn ở góc phải tiêu đề thay cho banner; một hàng nhập `rc-field` thẳng hàng; không banner
// "đã lưu" — số ở góc phải và bảng mốc đổi ngay là phản hồi rồi, lỗi mới hiện banner.
import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type ChiTieuNgay, type ChiTieuNgayList } from "../../../../../api/client";
import { Button } from "../../../../../components/Button";
import { ConfirmDialog } from "../../../../../components/ConfirmDialog";
import { RowActionButton } from "../../../../../components/RowActionButton";
import { fmtYmd, money, todayYmd } from "../../shared/helpers";
import { NumInput } from "./fields";

export function ChiTieuNgayEditor({
  token,
  departmentId,
  deptName,
  readOnly,
}: {
  token: string;
  departmentId: number;
  deptName: string;
  readOnly?: boolean;
}) {
  const [data, setData] = useState<ChiTieuNgayList | null>(null);
  const [loading, setLoading] = useState(true);
  // Lưu và xoá tách cờ: đang xoá mốc thì nút "Thêm mốc" không được quay vòng theo.
  const [dangLuu, setDangLuu] = useState(false);
  const [dangXoa, setDangXoa] = useState(false);
  const busy = dangLuu || dangXoa;
  const [err, setErr] = useState<string | null>(null);
  const [ngay, setNgay] = useState(todayYmd());
  const [soTien, setSoTien] = useState<number | null>(null);
  const [ghiChu, setGhiChu] = useState("");
  const [xoa, setXoa] = useState<ChiTieuNgay | null>(null);

  const nap = useCallback(() => {
    setLoading(true);
    setErr(null);
    api.luong
      .chiTieuNgay(token, departmentId)
      .then(setData)
      .catch(() => setErr("Không tải được chỉ tiêu ngày của tổ."))
      .finally(() => setLoading(false));
  }, [token, departmentId]);

  useEffect(() => {
    nap();
  }, [nap]);

  // Ngày gõ trùng mốc đã có ⇒ nút thành "Sửa mốc": người khai biết mình đang GHI ĐÈ, không đẻ mốc mới.
  const trungMoc = data?.items.find((m) => m.ap_dung_tu === ngay) ?? null;
  const hopLe = !!ngay && soTien != null && soTien > 0;
  const homNay = todayYmd();

  const luu = () => {
    if (!hopLe || busy) return;
    setDangLuu(true);
    setErr(null);
    api.luong
      .khaiChiTieuNgay(token, departmentId, {
        ap_dung_tu: ngay,
        so_tien: soTien as number,
        // Sửa mốc mà bỏ trống ô Ghi chú ⇒ GIỮ ghi chú cũ của mốc đó, không xoá mất nó một cách âm thầm.
        ghi_chu: ghiChu.trim() || trungMoc?.ghi_chu || null,
      })
      .then((r) => {
        setData(r);
        setSoTien(null);
        setGhiChu("");
      })
      .catch((e: unknown) =>
        setErr(
          e instanceof ApiError && (e.status === 400 || e.status === 422)
            ? e.message
            : "Lưu chỉ tiêu ngày thất bại. Vui lòng thử lại.",
        ),
      )
      .finally(() => setDangLuu(false));
  };

  const xacNhanXoa = () => {
    if (!xoa || busy) return;
    setDangXoa(true);
    setErr(null);
    api.luong
      .xoaChiTieuNgay(token, departmentId, xoa.id)
      .then((r) => {
        setData(r);
        setXoa(null);
      })
      .catch(() => setErr("Xoá mốc thất bại. Vui lòng thử lại."))
      .finally(() => setDangXoa(false));
  };

  const hienHanh = data?.hien_hanh ?? null;

  return (
    <div className="cl-card">
      <div className="cl-card__head">
        <div>
          <h3 className="cl-card__title">Chỉ tiêu ngày — {deptName}</h3>
          <p className="cl-card__desc">
            Tiền sản lượng một thợ phải làm ra trong một công. Chưa áp vào tính lương.
          </p>
        </div>
        {!loading && (
          <div className="cl-chitieu__now" aria-live="polite">
            {hienHanh ? (
              <>
                <div className="cl-chitieu__now-val">
                  {money(hienHanh.so_tien)}
                  <small>đ/công</small>
                </div>
                <div className="cl-chitieu__now-sub">
                  đang áp dụng từ {fmtYmd(hienHanh.ap_dung_tu)}
                </div>
              </>
            ) : (
              <div className="cl-chitieu__now-sub">Chưa có chỉ tiêu đang áp dụng</div>
            )}
          </div>
        )}
      </div>

      <div className="cl-card__body">
        {err && <div className="banner banner--error">{err}</div>}

        {loading ? (
          <p className="cl-hint-inline">Đang tải chỉ tiêu ngày…</p>
        ) : (
          <>
            {!readOnly && (
              <>
                <div className="cl-chitieu__form">
                  <label className="rc-field">
                    <span className="rc-field__label">Áp dụng từ ngày</span>
                    <input
                      className="rc-input"
                      type="date"
                      value={ngay}
                      onChange={(e) => setNgay(e.target.value)}
                    />
                  </label>
                  <label className="rc-field">
                    <span className="rc-field__label">Chỉ tiêu</span>
                    <NumInput
                      value={soTien}
                      onChange={setSoTien}
                      suffix="đ/công"
                      step={1000}
                      min={0}
                      placeholder="350000"
                    />
                  </label>
                  <label className="rc-field">
                    <span className="rc-field__label">Ghi chú</span>
                    <input
                      className="rc-input"
                      maxLength={255}
                      value={ghiChu}
                      placeholder="Không bắt buộc"
                      onChange={(e) => setGhiChu(e.target.value)}
                    />
                  </label>
                  <Button
                    variant="accent"
                    loading={dangLuu}
                    disabled={!hopLe || dangXoa}
                    onClick={luu}
                  >
                    {trungMoc ? "Sửa mốc" : "Thêm mốc"}
                  </Button>
                </div>
                {/* Chỉ nhắc khi đã gõ số — vừa thêm mốc xong thì bảng ngay dưới đã có dòng đó, nhắc thêm là lặp. */}
                {trungMoc && soTien != null && (
                  <p className="rc-field__hint cl-chitieu__trung">
                    Ngày {fmtYmd(ngay)} đã có mốc {money(trungMoc.so_tien)} đ/công — lưu là ghi đè
                    số của mốc đó.
                  </p>
                )}
              </>
            )}

            {data && data.items.length > 0 && (
              <div className="cl-table__wrap cl-chitieu__table">
                <table className="cl-table">
                  <thead>
                    <tr>
                      <th style={{ width: 210 }}>Áp dụng từ</th>
                      <th className="num" style={{ width: 170 }}>
                        Chỉ tiêu (đ/công)
                      </th>
                      <th>Ghi chú</th>
                      {!readOnly && <th className="act" style={{ width: 56 }} aria-label="Thao tác" />}
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((m) => (
                      <tr key={m.id}>
                        <td>
                          <span className="cl-chitieu__ngay">{fmtYmd(m.ap_dung_tu)}</span>
                          {hienHanh?.id === m.id && (
                            <span className="ns-badge ns-badge--ok">đang áp dụng</span>
                          )}
                          {m.ap_dung_tu > homNay && (
                            <span className="ns-badge ns-badge--muted">sắp áp dụng</span>
                          )}
                        </td>
                        <td className="num">{money(m.so_tien)}</td>
                        <td>{m.ghi_chu || <span className="cl-chitieu__rong">—</span>}</td>
                        {!readOnly && (
                          <td className="act">
                            <RowActionButton
                              dense
                              danger
                              label={`Xoá mốc ${fmtYmd(m.ap_dung_tu)}`}
                              icon="trash"
                              disabled={busy}
                              onClick={() => setXoa(m)}
                            />
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="cl-hint-inline">
              Đổi chỉ tiêu thì thêm mốc mới — mốc cũ giữ nguyên để tra lại các tháng trước.
            </p>
          </>
        )}
      </div>

      <ConfirmDialog
        open={xoa != null}
        title="Xoá mốc chỉ tiêu ngày?"
        message={
          xoa
            ? `Xoá mốc ${money(xoa.so_tien)} đ/công áp dụng từ ${fmtYmd(xoa.ap_dung_tu)} của ${deptName}.`
            : undefined
        }
        confirmLabel="Xoá mốc"
        danger
        busy={dangXoa}
        onConfirm={xacNhanXoa}
        onCancel={() => setXoa(null)}
      />
    </div>
  );
}
