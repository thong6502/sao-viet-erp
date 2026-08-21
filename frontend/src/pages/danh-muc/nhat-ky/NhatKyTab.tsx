// TAB NHẬT KÝ — ai đổi gì, lúc nào, cho MỘT bản ghi danh mục.
//
// Mỗi lần bấm Lưu là MỘT mục; các trường đổi nằm bên trong mục đó (backend nối bằng " · ") chứ
// không tách thành nhiều mục rời.
import { useEffect, useState } from "react";

import { useAuth } from "../../../auth/useAuth";
import { ApiError } from "../../../api/client";
import { nhatKyDanhMuc, type NhatKyItem } from "../../../api/rebuildCatalog";
import { NK_NHAN, formatNkLine, nhanThoiGian } from "./nhatKyNhan";

function NhatKyChangeItem({ item }: { item: string }) {
  const isTien = /đ\/|Đơn giá/.test(item);
  const { left, right } = formatNkLine(item);
  if (right !== undefined) {
    return (
      <li className={`rc-nk__change-row${isTien ? " is-tien" : ""}`}>
        <span className="rc-nk__change-left">{left}</span>
        <span className="rc-nk__arrow" aria-hidden="true">→</span>
        <span className="rc-nk__change-right">{right}</span>
      </li>
    );
  }
  return <li className={`rc-nk__change-row${isTien ? " is-tien" : ""}`}>{left}</li>;
}

export function NhatKyTab({ loai, id }: { loai: string; id: number }) {
  const { token } = useAuth();
  const [rows, setRows] = useState<NhatKyItem[] | null>(null);
  const [loi, setLoi] = useState<string | null>(null);

  useEffect(() => {
    let huy = false;
    setRows(null);
    setLoi(null);
    nhatKyDanhMuc(token!, loai, id)
      .then((r) => { if (!huy) setRows(r.items); })
      .catch((e) => { if (!huy) setLoi(e instanceof ApiError ? e.message : "Không tải được nhật ký."); });
    return () => { huy = true; };
  }, [token, loai, id]);

  if (loi) return <div className="banner banner--error">{loi}</div>;
  if (rows === null) return <div className="rc-nk__empty">Đang tải nhật ký…</div>;
  if (rows.length === 0) {
    return (
      <div className="rc-nk__empty">
        Chưa có thay đổi nào được ghi. Nhật ký bắt đầu từ lần sửa tiếp theo.
      </div>
    );
  }

  return (
    <ol className="rc-nk">
      {rows.map((r, i) => {
        const dong = r.detail ? r.detail.split(" · ").filter(Boolean) : [];
        const laTao = r.action === "dm_tao";
        const laXoa = r.action === "dm_xoa";
        return (
          <li key={i} className={`rc-nk__item${laTao ? " is-tao" : laXoa ? " is-xoa" : " is-sua"}`}>
            <span className="rc-nk__dot" aria-hidden="true">
              {laTao ? "+" : laXoa ? "×" : "✎"}
            </span>
            <div className="rc-nk__body">
              <div className="rc-nk__head">
                <span className={`rc-nk__badge rc-nk__badge--${r.action}`}>{NK_NHAN[r.action] ?? r.action}</span>
                <span className="rc-nk__who">{r.actor_name ?? "—"}</span>
                <time className="rc-nk__at" dateTime={r.at}>{nhanThoiGian(r.at)}</time>
              </div>
              {/* Tạo mới / Xoá: detail chỉ là tên bản ghi → đã có ở tiêu đề drawer, không lặp lại. */}
              {r.action === "dm_sua" && dong.length > 0 && (
                <ul className="rc-nk__changes">
                  {dong.map((d, k) => (
                    <NhatKyChangeItem key={k} item={d} />
                  ))}
                </ul>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
