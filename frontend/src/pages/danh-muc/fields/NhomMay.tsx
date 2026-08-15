// NHÓM MÁY: ô chọn một nhóm (kèm thêm/xoá NGAY TẠI CHỖ) và ô chọn NHIỀU nhóm.
//
// Danh mục THẬT (`/api/nhom-may`) chứ không còn là chữ tự do khai cứng trong code. Giá trị lưu
// trên máy vẫn là CHỮ (`may_thiet_bi.loai_may`) — bảng chỉ quản danh sách tên được bày ra.
// Quyền `dm_thiet_bi` = đúng module của màn này, nên không có cảnh thấy nút rồi ăn 403.
// 🔴 Xoá nhóm còn máy dùng bị backend CHẶN kèm số máy — hiện nguyên câu đó cho người ta biết
// phải đi sửa mấy máy, đừng nuốt thành "không xoá được".
import { useState } from "react";

import { useAuth } from "../../../auth/useAuth";
import { useCan } from "../../../auth/permissions";
import { ApiError } from "../../../api/client";
import { crud } from "../../../api/rebuildCatalog";
import type { Row } from "../types";

// ⚠️ HẰNG CẤP MODULE, cố ý. Nhét vào `useMemo` trong component thì mỗi lần render ra một object
// mới, effect nào phụ thuộc nó sẽ nạp lại vô hạn.
const nhomMayApi = crud("/api/nhom-may");

export function NhomMayField({
  value, onChange, options, onCatalogChanged,
}: {
  value: string;
  onChange: (v: string) => void;
  options: Row[];
  onCatalogChanged: () => void;
}) {
  const { token } = useAuth();
  const can = useCan();
  const coQuyen = can("dm_thiet_bi", "create") && can("dm_thiet_bi", "delete");
  const [moQuanLy, setMoQuanLy] = useState(false);
  const [tenMoi, setTenMoi] = useState("");
  const [ban, setBan] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);

  async function xoa(row: Row) {
    if (!token) return;
    setBan(true); setLoi(null);
    try {
      await nhomMayApi.remove(token, row.id);
      if (value === row.ten) onChange("");
      onCatalogChanged();
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không xoá được nhóm máy.");
    } finally { setBan(false); }
  }

  async function them() {
    const ten = tenMoi.trim();
    if (!token || !ten) return;
    setBan(true); setLoi(null);
    try {
      await nhomMayApi.create(token, { ten });
      setTenMoi("");
      onChange(ten);            // vừa tạo là chọn luôn — không bắt bấm thêm một nhát
      onCatalogChanged();
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không tạo được nhóm máy.");
    } finally { setBan(false); }
  }

  return (
    <div className="rc-dvtd">
      <div className="rc-dvtd__row">
        <select className="rc-input" value={value} onChange={(e) => onChange(e.target.value)}>
          <option value="">— chọn nhóm máy —</option>
          {options.map((o) => (
            <option key={o.id} value={String(o.ten)}>{String(o.ten)}</option>
          ))}
        </select>
        {coQuyen && (
          <button type="button" className="rc-dvtd__manage" onClick={() => setMoQuanLy((v) => !v)}>
            {moQuanLy ? "Xong" : "＋ Thêm / xoá"}
          </button>
        )}
      </div>
      {moQuanLy && coQuyen && (
        <div className="rc-dvtd__panel">
          {loi && <div className="rc-dvtd__err">{loi}</div>}
          <div className="rc-dvtd__chips">
            {options.length === 0 && <span className="badge-sem badge-sem--muted">Chưa có nhóm máy nào.</span>}
            {options.map((o) => (
              <span key={o.id} className="rc-dvtd__chip">
                {String(o.ten)}
                <button type="button" disabled={ban} title="Xoá nhóm (chỉ được khi không còn máy nào dùng)"
                  onClick={() => xoa(o)}>×</button>
              </span>
            ))}
          </div>
          <div className="rc-dvtd__row">
            <input className="rc-input" value={tenMoi} disabled={ban}
              placeholder="Tên nhóm mới, vd: Ép kim"
              onChange={(e) => setTenMoi(e.target.value)} />
            <button type="button" className="rc-dvtd__manage" disabled={ban || !tenMoi.trim()}
              onClick={them}>Thêm</button>
          </div>
          <p className="rc-field__hint">
            Nhóm đang có máy dùng thì không xoá được — đổi nhóm cho những máy đó trước đã.
          </p>
        </div>
      )}
    </div>
  );
}

// `CaLamField` (ô "Ca làm việc của máy này") ĐÃ XOÁ 2026-08-10 — máy chạy liên tục, ca chỉ khai ở
// Nhân sự → Ca kíp. Nếu cần lại một ô chọn nhiều mục dạng chip thì viết mới, đừng dựng lại ô ca.

/** Multi-select nhóm máy → lưu mảng TÊN (khớp `may_thiet_bi.loai_may`). Khác `RefMultiField` (lưu
 *  id) và `NhomMayField` (single). Dùng cho `cong_doan.nhom_may_cho_phep` — chặn gán máy sai loại. */
export function NhomMayMultiField({ value, options, onChange }: {
  value: string[]; options: Row[]; onChange: (v: string[]) => void;
}) {
  const chon = Array.isArray(value) ? value : [];
  const toggle = (ten: string) =>
    onChange(chon.includes(ten) ? chon.filter((t) => t !== ten) : [...chon, ten]);
  // Chip chọn nhóm dùng primitive `.seg` của hệ (nền charcoal khi chọn) — bản trước tô tay
  // #2563eb/#eff6ff/#1d4ed8 ngay trong `style`, tức một accent XANH THỨ HAI nằm ngoài mọi token,
  // đổi theme là nó đứng im một mình.
  return (
    <div className="rc-nhom-may">
      {options.length === 0 ? (
        <div className="rc-timeline__empty">Chưa có nhóm máy nào trong danh mục.</div>
      ) : (
        options.map((o) => {
          const ten = String(o.ten);
          const on = chon.includes(ten);
          return (
            <label key={o.id} className={`seg${on ? " is-active" : ""}`}>
              <input type="checkbox" checked={on} onChange={() => toggle(ten)} />
              {ten}
            </label>
          );
        })
      )}
      <p className="rc-field__hint rc-nhom-may__hint">
        Bỏ trống = mọi máy (không ràng buộc). Chọn nhóm nào thì chỉ máy nhóm đó được gán cho công đoạn này ở bài ghép.
      </p>
    </div>
  );
}
