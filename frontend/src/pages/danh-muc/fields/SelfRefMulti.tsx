// NVL THAY THẾ (mục 5 "Bảng định mức", mg 0239) — chọn NHIỀU dòng CÙNG danh mục dùng thay được
// dòng đang sửa. MỘT CHIỀU (khai A→B không tự suy B→A). `options` do nơi gọi (CatalogDrawer) đã
// lọc bỏ chính dòng đang sửa — field này không tự biết "chính mình" là ai.
//
// Tái dùng nguyên khối `.rc-dm-vt*`/`.rc-dinh-muc-add*` đã chạy tốt ở `DinhMucDauViecField`
// (không viết CSS mới) — chỉ khác: đây là field ĐỘC LẬP (luôn hiện), không phải hàng phụ bung từ
// một pill trong bảng.
import { TrashIcon } from "../icons";
import type { Row } from "../types";

export function SelfRefMultiField({ value, options, onChange }: {
  value: number[]; options: Row[]; onChange: (v: number[]) => void;
}) {
  const byId = (id: number) => options.find((o) => Number(o.id) === id);
  const remaining = options.filter((o) => !value.includes(Number(o.id)));

  return (
    <div className="rc-dm-vt">
      {value.length === 0 && <div className="rc-dm-vt__empty">Chưa khai hàng thay thế.</div>}
      {value.map((id) => {
        const o = byId(id);
        return (
          <div className="rc-dm-vt__item" key={id}>
            <span className="rc-dm-vt__ma">{o ? String(o.ma) : `#${id}`}</span>
            <span className="rc-dm-vt__ten">{o ? String(o.ten) : "(đã gỡ khỏi danh mục)"}</span>
            <button type="button" className="rc-bands__del" title="Bỏ khỏi danh sách thay thế"
              onClick={() => onChange(value.filter((x) => x !== id))}>
              <TrashIcon />
            </button>
          </div>
        );
      })}
      <select className="rc-dinh-muc-add__select" value=""
        onChange={(e) => { const id = Number(e.target.value); if (id) onChange([...value, id]); }}>
        <option value="">＋ chọn từ danh mục</option>
        {remaining.map((o) => <option key={o.id} value={o.id}>{String(o.ma)} · {String(o.ten)}</option>)}
      </select>
    </div>
  );
}
