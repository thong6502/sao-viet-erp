// TỔ LÀM VIỆC — chọn NHIỀU tổ cho một công việc khoán (17/09/2026). Cùng một việc ("Bế nổi") do tổ
// Bế lẫn tổ Thành phẩm làm, chung một đơn giá: khai hai dòng là hai đơn giá phải sửa song song.
//
// Chip bật/tắt dùng lại primitive `.seg` + khối `.rc-nhom-may` của ô nhóm máy — danh sách tổ sản
// xuất ngắn (vài chục), bày hết ra bấm một nhát nhanh hơn mở menu từng lần. Lưu ID (khác ô nhóm máy
// lưu tên).
//
// Tổ đang chọn mà KHÔNG còn trong danh sách (bị xoá khỏi cây tổ chức) vẫn hiện thành chip đã bật,
// đánh dấu "đã xoá" — bỏ nó đi ngầm thì bấm Lưu là mất dấu việc từng thuộc tổ nào mà không ai hay.
import type { Row } from "../types";

export function ToMultiField({ value, options, nhanDau, onChange }: {
  value: number[]; options: Row[]; nhanDau?: string; onChange: (v: number[]) => void;
}) {
  const chon = (Array.isArray(value) ? value : []).map(Number);
  const toggle = (id: number) =>
    onChange(chon.includes(id) ? chon.filter((x) => x !== id) : [...chon, id]);
  const coThat = new Set(options.map((o) => Number(o.id)));
  const daXoa = chon.filter((id) => !coThat.has(id));
  // Tổ ĐẦU danh sách đang chọn (thứ tự bấm, không phải thứ tự chip) — công đoạn dùng làm tổ mặc định.
  const dau = nhanDau && chon.length > 1 ? chon[0] : null;

  return (
    <div className="rc-nhom-may">
      {options.length === 0 && daXoa.length === 0 && (
        <div className="rc-timeline__empty">Chưa có tổ sản xuất nào trong cây tổ chức.</div>
      )}
      {options.map((o) => {
        const id = Number(o.id);
        const on = chon.includes(id);
        return (
          <label key={id} className={`seg${on ? " is-active" : ""}`} title={o.ma ? String(o.ma) : undefined}>
            <input type="checkbox" checked={on} onChange={() => toggle(id)} />
            {String(o.ten)}
            {id === dau && <span className="rc-to-multi__dau"> · {nhanDau}</span>}
          </label>
        );
      })}
      {daXoa.map((id) => (
        <label key={id} className="seg is-active" title="Tổ này không còn trong cây tổ chức — bỏ chọn để gỡ">
          <input type="checkbox" checked onChange={() => toggle(id)} />
          Tổ #{id} (đã xoá)
          {id === dau && <span className="rc-to-multi__dau"> · {nhanDau}</span>}
        </label>
      ))}
    </div>
  );
}
