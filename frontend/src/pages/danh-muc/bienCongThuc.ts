// Từ điển BIẾN dùng trong ô công thức — nạp MỘT lần cho cả app.
//
// ⚠️ `_bienCache` / `_bienChoDoi` là cache CẤP MODULE, dùng chung mọi màn (danh mục · phiếu tính
// giá · quy đổi của đơn vị). Tách file này làm đôi là ra HAI cache: màn nào nạp trước thì màn kia
// vẫn bắn thêm một request, và hai bên có thể cầm hai bản từ điển khác nhau. Muốn thêm chỗ dùng
// thì IMPORT từ đây, đừng chép hai dòng `let _cache` sang chỗ mới.
import { useEffect, useState } from "react";

import { useAuth } from "../../auth/useAuth";
import { authed } from "../../api/client";

export type BienCongThuc = {
  ma: string;
  nhan: string;
  mo_ta: string;
  don_vi: string;
  nguon: string;
  loai: string[];
};

let _bienCache: BienCongThuc[] | null = null;
let _bienChoDoi: Promise<BienCongThuc[]> | null = null;

export function useBienCongThuc(): BienCongThuc[] {
  const { token } = useAuth();
  const [bien, setBien] = useState<BienCongThuc[]>(_bienCache ?? []);
  useEffect(() => {
    if (!token || _bienCache) return;
    const cho = (_bienChoDoi ??= authed<{ items: BienCongThuc[] }>("/api/bien-cong-thuc", token)
      .then((r) => (_bienCache = r.items))
      .catch((): BienCongThuc[] => []));
    let song = true;
    cho.then((ds) => { if (song) setBien(ds); });
    return () => { song = false; };
  }, [token]);
  return bien;
}

export type TraBien = (ma: string) => BienCongThuc | undefined;

export function traBien(ds: BienCongThuc[]): TraBien {
  const theoMa = new Map(ds.map((b) => [b.ma, b]));
  return (ma) => theoMa.get(ma);
}
