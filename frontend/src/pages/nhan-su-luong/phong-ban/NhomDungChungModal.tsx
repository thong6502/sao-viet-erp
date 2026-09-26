// Hộp thoại GỘP NHÓM DÙNG CHUNG (khối Kinh doanh).
//
// Hai người cùng một nhóm thì, ở bốn màn Tính giá · Báo giá · Đơn hàng · Khách hàng, phạm vi
// "Của tôi" của họ được hiểu là "của tôi + của người cùng nhóm". Nhóm MỞ RỘNG DỮ LIỆU, KHÔNG
// nâng quyền — người kia thiếu ô Duyệt thì vào phiếu của bạn vẫn không duyệt được.
//
// Tách file riêng vì DepartmentsPage.tsx đã hơn 3.000 dòng; nhét thêm một hộp thoại nữa vào đó
// là mỗi lần sửa một thứ phải đọc lại cả màn.
import { useCallback, useEffect, useMemo, useState } from "react";

import { api, type NhomDungChung } from "../../../api/client";
import { Button } from "../../../components/Button";
import { ConfirmDialog } from "../../../components/ConfirmDialog";
import { Select } from "../../../components/Select";

/** Người đang được tick ở tab Nhân sự và ĐÃ có tài khoản (nhóm gắn theo tài khoản, không theo hồ sơ). */
export interface NguoiChon {
  userId: number;
  hoTen: string;
}

export function NhomDungChungModal({
  token,
  nguoiChon,
  nhomMo,
  onClose,
  onSaved,
}: {
  token: string;
  /** Người đang tick — rỗng khi mở từ chip tên nhóm (chỉ xem/sửa nhóm có sẵn). */
  nguoiChon: NguoiChon[];
  /** Mở thẳng vào một nhóm có sẵn (bấm chip); null = mở để gộp người đang tick. */
  nhomMo?: NhomDungChung | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [nhoms, setNhoms] = useState<NhomDungChung[]>([]);
  const [dangTai, setDangTai] = useState(true);
  const [loi, setLoi] = useState<string | null>(null);
  const [ban, setBan] = useState(false);
  // "moi" = tạo nhóm mới · số = thêm vào nhóm đã có.
  const [dich, setDich] = useState<number | "moi">(nhomMo ? nhomMo.id : "moi");
  const [ten, setTen] = useState("");
  const [hoiXoa, setHoiXoa] = useState(false);

  const nap = useCallback(async () => {
    setDangTai(true);
    try {
      setNhoms(await api.nhomDungChung.list(token));
      setLoi(null);
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không tải được danh sách nhóm");
    } finally {
      setDangTai(false);
    }
  }, [token]);

  useEffect(() => {
    void nap();
  }, [nap]);

  const nhomDangChon = useMemo(
    () => (dich === "moi" ? null : nhoms.find((n) => n.id === dich) ?? null),
    [dich, nhoms],
  );

  // Thành viên sau khi gộp = người đang có trong nhóm + người đang tick (không trùng).
  const sauKhiGop = useMemo(() => {
    const ra = new Map<number, string>();
    for (const tv of nhomDangChon?.thanh_viens ?? []) ra.set(tv.user_id, tv.ho_ten);
    for (const n of nguoiChon) ra.set(n.userId, n.hoTen);
    return [...ra].map(([userId, hoTen]) => ({ userId, hoTen }));
  }, [nhomDangChon, nguoiChon]);

  const luu = async () => {
    setBan(true);
    setLoi(null);
    try {
      if (dich === "moi") {
        await api.nhomDungChung.create(
          token,
          ten.trim(),
          nguoiChon.map((n) => n.userId),
        );
      } else {
        await api.nhomDungChung.update(token, dich, {
          ...(ten.trim() ? { ten: ten.trim() } : {}),
          userIds: sauKhiGop.map((n) => n.userId),
        });
      }
      onSaved();
      onClose();
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không lưu được nhóm");
    } finally {
      setBan(false);
    }
  };

  const boNguoi = async (userId: number) => {
    if (!nhomDangChon) return;
    setBan(true);
    setLoi(null);
    try {
      await api.nhomDungChung.update(token, nhomDangChon.id, {
        userIds: nhomDangChon.thanh_viens
          .filter((tv) => tv.user_id !== userId)
          .map((tv) => tv.user_id),
      });
      await nap();
      onSaved();
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không gỡ được người khỏi nhóm");
    } finally {
      setBan(false);
    }
  };

  const xoaNhom = async () => {
    if (!nhomDangChon) return;
    setBan(true);
    try {
      await api.nhomDungChung.remove(token, nhomDangChon.id);
      onSaved();
      onClose();
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không xoá được nhóm");
      setBan(false);
    }
  };

  const luuDuoc =
    dich === "moi" ? ten.trim().length > 0 && nguoiChon.length > 0 : sauKhiGop.length > 0;

  return (
    <div className="ndc-modal__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="ndc-modal" onClick={(e) => e.stopPropagation()}>
        <div className="ndc-modal__hd">
          <h3>Gộp nhóm dùng chung — Kinh doanh</h3>
          <button type="button" className="ndc-modal__x" onClick={onClose} aria-label="Đóng">
            ×
          </button>
        </div>

        <p className="ndc-modal__note">
          Người cùng một nhóm xem và sửa được dữ liệu của nhau ở Tính giá, Báo giá, Đơn hàng và
          Khách hàng — kể cả khi phạm vi của họ là “Của tôi”. Nhóm không cấp thêm quyền nào khác.
        </p>

        {nguoiChon.length > 0 && (
          <div className="ndc-modal__block">
            <div className="ndc-modal__label">Đang chọn ({nguoiChon.length})</div>
            <div className="ndc-modal__chips">
              {nguoiChon.map((n) => (
                <span key={n.userId} className="ndc-modal__chip">
                  {n.hoTen}
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="ndc-modal__block">
          <div className="ndc-modal__label">Gộp vào</div>
          <Select
            ariaLabel="Nhóm đích"
            value={dich}
            onChange={(v) => setDich((v as number | "moi") ?? "moi")}
            options={[
              { value: "moi", label: "— Tạo nhóm mới —" },
              ...nhoms.map((n) => ({
                value: n.id,
                label: n.ten,
                hint: `${n.thanh_viens.length} người`,
              })),
            ]}
          />
        </div>

        <div className="ndc-modal__block">
          <div className="ndc-modal__label">
            {dich === "moi" ? "Tên nhóm mới" : "Đổi tên nhóm (bỏ trống = giữ nguyên)"}
          </div>
          <input
            className="ndc-modal__input"
            value={ten}
            maxLength={255}
            placeholder={dich === "moi" ? "vd: Cặp KD 1" : nhomDangChon?.ten ?? ""}
            onChange={(e) => setTen(e.target.value)}
          />
        </div>

        {nhomDangChon && (
          <div className="ndc-modal__block">
            <div className="ndc-modal__label">
              Đang trong nhóm ({nhomDangChon.thanh_viens.length})
            </div>
            {nhomDangChon.thanh_viens.length === 0 ? (
              <div className="ndc-modal__empty">Chưa có ai.</div>
            ) : (
              <ul className="ndc-modal__list">
                {nhomDangChon.thanh_viens.map((tv) => (
                  <li key={tv.user_id}>
                    <span>
                      {tv.ho_ten} <span className="ndc-modal__dim">@{tv.username}</span>
                    </span>
                    <button
                      type="button"
                      className="ndc-modal__bo"
                      disabled={ban}
                      onClick={() => void boNguoi(tv.user_id)}
                    >
                      Gỡ
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {loi && <div className="ndc-modal__loi">{loi}</div>}
        {dangTai && <div className="ndc-modal__empty">Đang tải danh sách nhóm…</div>}

        <div className="ndc-modal__ft">
          {nhomDangChon && (
            <Button type="button" variant="ghost" disabled={ban} onClick={() => setHoiXoa(true)}>
              Xoá nhóm
            </Button>
          )}
          <span className="ndc-modal__spacer" />
          <Button type="button" variant="secondary" onClick={onClose}>
            Đóng
          </Button>
          <Button
            type="button"
            variant="primary"
            loading={ban}
            disabled={!luuDuoc || ban}
            onClick={() => void luu()}
          >
            {dich === "moi" ? "Gộp nhóm" : "Lưu"}
          </Button>
        </div>
      </div>

      <ConfirmDialog
        open={hoiXoa}
        title="Xoá nhóm dùng chung"
        message={
          `Xoá nhóm “${nhomDangChon?.ten ?? ""}” thì ${nhomDangChon?.thanh_viens.length ?? 0} người ` +
          "trong nhóm sẽ trở lại chỉ thấy dữ liệu của chính mình. Dữ liệu không mất, chỉ là hết dùng chung."
        }
        confirmLabel="Xoá nhóm"
        danger
        onConfirm={() => {
          setHoiXoa(false);
          void xoaNhom();
        }}
        onCancel={() => setHoiXoa(false)}
      />
    </div>
  );
}
