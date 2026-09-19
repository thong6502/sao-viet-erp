// Tổ trưởng ăn THƯỞNG hay ăn CHIA theo sản lượng tổ (chủ 19/09/2026) — CHỈ là chỗ khai báo.
// Chủ: "Ông A làm được 100k thì công ty sẽ thưởng 5% dựa trên 100k, còn Ông B ăn chia ấy làm được
// 100k, ông B lấy 5% rồi còn 95% lại chia đều cho cả tổ: giờ tôi cần chỗ nhập liệu trước còn đấu vào
// lương để làm sau" ⇒ engine tính lương KHÔNG đọc số này; bảng lương không đổi.
//
// Cùng khuôn với Chỉ tiêu ngày ngay trên (thẻ, hàng nhập, bảng mốc): mỗi lần đổi chế độ là một MỐC
// "áp dụng từ ngày", mốc cũ giữ nguyên để các tháng trước vẫn tra đúng chế độ của tháng đó. Thêm một
// dòng VÍ DỤ SỐNG theo đúng lời chủ (tổ làm 100.000 đ) để người khai thấy ngay hai chế độ khác nhau
// thế nào trước khi bấm lưu.
import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  api,
  type ToTruongCheDo,
  type ToTruongList,
  type ToTruongMoc,
} from "../../../../../api/client";
import { Button } from "../../../../../components/Button";
import { ConfirmDialog } from "../../../../../components/ConfirmDialog";
import { RowActionButton } from "../../../../../components/RowActionButton";
import { fmtYmd, money, todayYmd } from "../../shared/helpers";
import { NumInput } from "./fields";

const NHAN_CHE_DO: Record<ToTruongCheDo, string> = {
  khong: "Không áp dụng",
  thuong: "Ăn thưởng",
  chia: "Ăn chia",
};
const CHE_DO: ToTruongCheDo[] = ["khong", "thuong", "chia"];
/** Số sản lượng tổ dùng cho dòng ví dụ — đúng con số chủ đưa. */
const VI_DU = 100_000;

const pct = (v: number) => `${v.toLocaleString("vi-VN", { maximumFractionDigits: 2 })}%`;
const nhanMoc = (m: Pick<ToTruongMoc, "che_do" | "ty_le">) =>
  m.che_do === "khong" ? NHAN_CHE_DO.khong : `${NHAN_CHE_DO[m.che_do]} ${pct(m.ty_le)}`;

/** Lỗi tỷ lệ theo đúng luật máy chủ, hiện ngay dưới ô thay vì đợi bấm lưu mới biết. */
function loiTyLe(cheDo: ToTruongCheDo, tyLe: number | null): string | null {
  if (cheDo === "khong" || tyLe == null) return null;
  if (tyLe <= 0) return "Tỷ lệ phải lớn hơn 0%.";
  if (tyLe > 100) return "Tỷ lệ tối đa 100%.";
  if (cheDo === "chia" && tyLe >= 100) return "Ăn chia phải nhỏ hơn 100% — còn phần chia cho tổ.";
  return null;
}

function ViDu({ cheDo, tyLe, soNguoi }: { cheDo: ToTruongCheDo; tyLe: number | null; soNguoi: number }) {
  if (cheDo === "khong") {
    return <>Tổ trưởng ăn sản lượng như thợ, không thưởng hay chia gì thêm.</>;
  }
  if (tyLe == null) return <>Gõ tỷ lệ % để xem ví dụ với tổ làm ra {money(VI_DU)} đ.</>;
  if (loiTyLe(cheDo, tyLe)) return null;
  const phanToTruong = (VI_DU * tyLe) / 100;
  if (cheDo === "thuong") {
    return (
      <>
        Ví dụ tổ làm ra <b>{money(VI_DU)} đ</b> → công ty thưởng thêm tổ trưởng{" "}
        <b>{money(phanToTruong)} đ</b>; thợ vẫn ăn sản lượng của mình.
      </>
    );
  }
  const conLai = VI_DU - phanToTruong;
  return (
    <>
      Ví dụ tổ làm ra <b>{money(VI_DU)} đ</b> → tổ trưởng lấy <b>{money(phanToTruong)} đ</b>,{" "}
      <b>{money(conLai)} đ</b> còn lại chia đều cho cả tổ
      {soNguoi > 0 && (
        <>
          {" "}
          ({soNguoi} người ≈ <b>{money(conLai / soNguoi)} đ/người</b>)
        </>
      )}
      .
    </>
  );
}

export function ToTruongEditor({
  token,
  departmentId,
  deptName,
  headName,
  headTitle,
  soNguoi = 0,
  readOnly,
}: {
  token: string;
  departmentId: number;
  deptName: string;
  /** Người đứng đầu tổ ở màn Phòng ban — chính là tổ trưởng. */
  headName?: string | null;
  /** Nhãn chức danh theo cấp đơn vị ("Tổ trưởng"…); trống thì gọi là tổ trưởng. */
  headTitle?: string | null;
  /** Số người của tổ — chỉ để tính dòng ví dụ ăn chia. */
  soNguoi?: number;
  readOnly?: boolean;
}) {
  const [data, setData] = useState<ToTruongList | null>(null);
  const [loading, setLoading] = useState(true);
  // Lưu và xoá tách cờ: đang xoá mốc thì nút "Thêm mốc" không được quay vòng theo.
  const [dangLuu, setDangLuu] = useState(false);
  const [dangXoa, setDangXoa] = useState(false);
  const busy = dangLuu || dangXoa;
  const [err, setErr] = useState<string | null>(null);
  const [cheDo, setCheDo] = useState<ToTruongCheDo>("thuong");
  const [ngay, setNgay] = useState(todayYmd());
  const [tyLe, setTyLe] = useState<number | null>(null);
  const [ghiChu, setGhiChu] = useState("");
  const [xoa, setXoa] = useState<ToTruongMoc | null>(null);

  const nap = useCallback(() => {
    setLoading(true);
    setErr(null);
    api.luong
      .toTruong(token, departmentId)
      .then(setData)
      .catch(() => setErr("Không tải được chế độ tổ trưởng của tổ."))
      .finally(() => setLoading(false));
  }, [token, departmentId]);

  useEffect(() => {
    nap();
  }, [nap]);

  // Ngày gõ trùng mốc đã có ⇒ nút thành "Sửa mốc": người khai biết mình đang GHI ĐÈ, không đẻ mốc mới.
  const trungMoc = data?.items.find((m) => m.ap_dung_tu === ngay) ?? null;
  const loi = loiTyLe(cheDo, tyLe);
  const hopLe = !!ngay && (cheDo === "khong" || (tyLe != null && !loi));
  const homNay = todayYmd();
  const chucDanh = headTitle?.trim() || "Tổ trưởng";

  const luu = () => {
    if (!hopLe || busy) return;
    setDangLuu(true);
    setErr(null);
    api.luong
      .khaiToTruong(token, departmentId, {
        ap_dung_tu: ngay,
        che_do: cheDo,
        ty_le: cheDo === "khong" ? 0 : (tyLe as number),
        // Sửa mốc mà bỏ trống ô Ghi chú ⇒ GIỮ ghi chú cũ của mốc đó, không xoá mất nó một cách âm thầm.
        ghi_chu: ghiChu.trim() || trungMoc?.ghi_chu || null,
      })
      .then((r) => {
        setData(r);
        setTyLe(null);
        setGhiChu("");
      })
      .catch((e: unknown) =>
        setErr(
          e instanceof ApiError && (e.status === 400 || e.status === 422)
            ? e.message
            : "Lưu chế độ tổ trưởng thất bại. Vui lòng thử lại.",
        ),
      )
      .finally(() => setDangLuu(false));
  };

  const xacNhanXoa = () => {
    if (!xoa || busy) return;
    setDangXoa(true);
    setErr(null);
    api.luong
      .xoaToTruong(token, departmentId, xoa.id)
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
          <h3 className="cl-card__title">Tổ trưởng — {deptName}</h3>
          <p className="cl-card__desc">
            Tổ trưởng ăn thưởng hay ăn chia trên sản lượng của tổ. Chưa áp vào tính lương.
          </p>
        </div>
        {!loading && (
          <div className="cl-chitieu__now" aria-live="polite">
            {hienHanh ? (
              <>
                <div className="cl-chitieu__now-val">{nhanMoc(hienHanh)}</div>
                <div className="cl-chitieu__now-sub">
                  đang áp dụng từ {fmtYmd(hienHanh.ap_dung_tu)}
                </div>
              </>
            ) : (
              <div className="cl-chitieu__now-sub">Chưa khai — không áp dụng</div>
            )}
          </div>
        )}
      </div>

      <div className="cl-card__body">
        {err && <div className="banner banner--error">{err}</div>}

        <p className="cl-totruong__nguoi">
          {headName ? (
            <>
              {chucDanh}: <b>{headName}</b>
            </>
          ) : (
            <>
              Tổ chưa có người đứng đầu — gán ở màn <b>Phòng ban</b> (người đó là tổ trưởng). Vẫn
              khai chế độ trước được.
            </>
          )}
        </p>

        {loading ? (
          <p className="cl-hint-inline">Đang tải chế độ tổ trưởng…</p>
        ) : (
          <>
            {!readOnly && (
              <>
                <div className="cl-totruong__che-do">
                  <span className="rc-field__label" id={`to-truong-che-do-${departmentId}`}>
                    Chế độ
                  </span>
                  <div
                    className="lg-seg"
                    role="radiogroup"
                    aria-labelledby={`to-truong-che-do-${departmentId}`}
                  >
                    {CHE_DO.map((c) => (
                      <button
                        key={c}
                        type="button"
                        role="radio"
                        aria-checked={cheDo === c}
                        className={cheDo === c ? "is-active" : ""}
                        onClick={() => setCheDo(c)}
                      >
                        {NHAN_CHE_DO[c]}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="cl-totruong__form">
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
                    <span className="rc-field__label">Tỷ lệ trên sản lượng tổ</span>
                    <NumInput
                      value={cheDo === "khong" ? null : tyLe}
                      onChange={setTyLe}
                      suffix="%"
                      step={0.5}
                      min={0}
                      max={100}
                      placeholder={cheDo === "khong" ? "—" : "5"}
                      disabled={cheDo === "khong"}
                      invalid={!!loi}
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
                {loi ? (
                  <p className="rc-field__hint cl-totruong__loi">{loi}</p>
                ) : (
                  <p className="cl-totruong__vd">
                    <ViDu cheDo={cheDo} tyLe={tyLe} soNguoi={soNguoi} />
                  </p>
                )}
                {trungMoc && (cheDo === "khong" || tyLe != null) && (
                  <p className="rc-field__hint cl-chitieu__trung">
                    Ngày {fmtYmd(ngay)} đã có mốc {nhanMoc(trungMoc)} — lưu là ghi đè mốc đó.
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
                      <th style={{ width: 150 }}>Chế độ</th>
                      <th className="num" style={{ width: 90 }}>
                        Tỷ lệ
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
                        <td>{NHAN_CHE_DO[m.che_do]}</td>
                        <td className="num">
                          {m.che_do === "khong" ? (
                            <span className="cl-chitieu__rong">—</span>
                          ) : (
                            pct(m.ty_le)
                          )}
                        </td>
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
              Đổi chế độ thì thêm mốc mới — mốc cũ giữ nguyên để tra lại các tháng trước.
            </p>
          </>
        )}
      </div>

      <ConfirmDialog
        open={xoa != null}
        title="Xoá mốc chế độ tổ trưởng?"
        message={
          xoa
            ? `Xoá mốc "${nhanMoc(xoa)}" áp dụng từ ${fmtYmd(xoa.ap_dung_tu)} của ${deptName}.`
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
