// Hộp thoại NHÂN BẢN VAI TRÒ (tab "Vai trò & Quyền" của màn Phòng ban).
//
// Đẻ một vai MỚI mang y nguyên ma trận quyền của vai đang chọn. Dựng vai giống vai cũ bằng tay
// là tick lại hơn trăm ô — sai một ô thì tới lúc có người bị chặn nhầm mới lộ.
//
// Nhân bản sang PHÒNG KHÁC được: dòng quyền theo tổ tự đổi sang tổ đích (phòng ngoài khối sản
// xuất thì bỏ), phần còn lại giữ nguyên — máy chủ lo, xem `RoleRepository.copy_permissions`.
//
// Tách file riêng vì DepartmentsPage.tsx đã hơn 3.000 dòng; dùng lại bộ class `ndc-modal__*`
// trong departments.css để không đẻ thêm một khuôn hộp thoại thứ hai cho cùng một màn.
import { useMemo, useState } from "react";

import { api, ApiError, type Department, type Role } from "../../../api/client";
import { Button } from "../../../components/Button";
import { Select } from "../../../components/Select";

export function NhanBanVaiTroModal({
  token,
  vai,
  phongs,
  onClose,
  onDone,
}: {
  token: string;
  /** Vai đang chọn — bản gốc để nhân bản. */
  vai: Role;
  /** Mọi phòng ban, để chọn phòng đích. */
  phongs: Department[];
  onClose: () => void;
  /** Nhân bản xong: `cungPhong` = bản sao nằm ngay trong phòng đang mở (màn cần nạp lại chip). */
  onDone: (vaiMoi: Role, cungPhong: boolean) => void;
}) {
  const [ten, setTen] = useState(`${vai.name} (bản sao)`);
  const [phongDich, setPhongDich] = useState<number>(vai.department_id);
  const [ban, setBan] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);

  const tuyChon = useMemo(
    () =>
      [...phongs]
        .sort((a, b) => a.name.localeCompare(b.name, "vi"))
        .map((p) => ({ value: p.id, label: p.name, hint: p.code })),
    [phongs],
  );
  const doiPhong = phongDich !== vai.department_id;

  const nhanBan = async () => {
    const ten_ = ten.trim();
    if (!ten_ || ban) return;
    setBan(true);
    setLoi(null);
    try {
      const moi = await api.rbac.duplicateRole(token, vai.id, {
        name: ten_,
        departmentId: phongDich,
      });
      onDone(moi, !doiPhong);
      onClose();
    } catch (e) {
      if (e instanceof ApiError && e.isConflict) setLoi(e.message);
      else if (e instanceof ApiError && e.isForbidden)
        setLoi("Bạn không có quyền nhân bản vai trò.");
      else setLoi("Không nhân bản được vai trò. Vui lòng thử lại.");
    } finally {
      setBan(false);
    }
  };

  return (
    <div className="ndc-modal__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="ndc-modal" onClick={(e) => e.stopPropagation()}>
        <div className="ndc-modal__hd">
          <h3>Nhân bản vai trò</h3>
          <button type="button" className="ndc-modal__x" onClick={onClose} aria-label="Đóng">
            ×
          </button>
        </div>

        <p className="ndc-modal__note">
          Vai mới nhận y nguyên bộ quyền của “{vai.name}”. Sửa gì trên bản sao cũng không động
          tới bản gốc, và người đang giữ vai gốc vẫn nguyên vai của họ.
        </p>

        <div className="ndc-modal__block">
          <div className="ndc-modal__label">Tên vai mới</div>
          <input
            className="ndc-modal__input"
            value={ten}
            maxLength={255}
            onChange={(e) => {
              setTen(e.target.value);
              if (loi) setLoi(null);
            }}
          />
        </div>

        <div className="ndc-modal__block">
          <div className="ndc-modal__label">Phòng của vai mới</div>
          <Select
            ariaLabel="Phòng của vai mới"
            value={phongDich}
            onChange={(v) => setPhongDich((v as number) ?? vai.department_id)}
            options={tuyChon}
          />
          {doiPhong && (
            <span className="ndc-modal__dim">
              Khác phòng vai gốc: quyền theo tổ sẽ đổi sang tổ của phòng này; phòng ngoài khối
              sản xuất thì bỏ phần đó. Các ô còn lại giữ nguyên.
            </span>
          )}
        </div>

        {loi && <div className="ndc-modal__loi">{loi}</div>}

        <div className="ndc-modal__ft">
          <span className="ndc-modal__spacer" />
          <Button type="button" variant="secondary" onClick={onClose}>
            Đóng
          </Button>
          <Button
            type="button"
            variant="primary"
            loading={ban}
            disabled={!ten.trim() || ban}
            onClick={() => void nhanBan()}
          >
            Nhân bản
          </Button>
        </div>
      </div>
    </div>
  );
}
