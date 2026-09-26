// Thanh "chọn nhiều" của tab Tạm ứng (25/09/2026): duyệt / từ chối nhiều phiếu, lập phiếu chi và
// xuất Excel cho nhiều phiếu đã duyệt một lượt — chủ: lập phiếu cho cả xưởng một cú mà bắt duyệt,
// lập phiếu chi từng người là bất tiện.
//
// Thanh đi theo TAB trạng thái (xem `tamUngLoc.ts`): tab Chờ duyệt chỉ có Duyệt / Từ chối (ô
// `luong:approve`), tab Chờ chi chỉ có Lập phiếu chi (`phieu_chi:create`) / Xuất Excel (`luong:export`).
// Lựa chọn GIỮ qua trang / loại / tổ / ô tìm ⇒ thanh phải nói rõ bao nhiêu phiếu đã chọn đang bị
// bộ lọc che, và cho "Chỉ xem phiếu đã chọn" để soát trước khi bấm.
import { useEffect, type Dispatch, type SetStateAction } from "react";
import { api, type SalaryAdvance } from "../../../../api/client";
import { money } from "../shared/helpers";
import type { TabTrangThai } from "./tamUngLoc";

/** Danh sách tải lại (đổi kỳ, người khác vừa duyệt…) ⇒ bỏ khỏi lựa chọn những phiếu không còn
 *  thao tác được, để nút "Duyệt N phiếu" không đếm phiếu đã rời trạng thái. `phuThuoc` = dữ liệu
 *  khác mà `thaoTacDuoc` đọc (tab đang đứng). */
export function useTiaLuaChon(
  items: SalaryAdvance[],
  setChon: Dispatch<SetStateAction<Set<number>>>,
  thaoTacDuoc: (a: SalaryAdvance) => boolean,
  phuThuoc: unknown,
) {
  useEffect(() => {
    setChon((cu) => {
      const con = new Set(items.filter((a) => cu.has(a.id) && thaoTacDuoc(a)).map((a) => a.id));
      return con.size === cu.size ? cu : con;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, phuThuoc]);
}

/** Tải file chuyển khoản (khuôn lô lương BIZ MBBank) — cả kỳ, hoặc chỉ `ids` đang tick. */
export async function taiFileChuyenKhoan(
  token: string,
  year: number,
  month: number,
  ids?: number[],
): Promise<void> {
  const url = await api.luong.advancesXlsxBlobUrl(token, year, month, ids);
  const a = document.createElement("a");
  a.href = url;
  a.download = `ck-luong-ung-${year}-${String(month).padStart(2, "0")}.xlsx`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function TamUngChonNhieu({
  tab,
  tabRows,
  dangLoc,
  chon,
  setChon,
  chiXemChon,
  setChiXemChon,
  busy,
  canDuyet,
  canLapPhieuChi,
  canXuat,
  onDuyet,
  onTuChoi,
  onLapPhieuChi,
  onXuatExcel,
}: {
  tab: TabTrangThai;
  /** Mọi phiếu của tab (bỏ qua bộ lọc) — tính phiếu đã chọn, kể cả phiếu bộ lọc đang che. */
  tabRows: SalaryAdvance[];
  /** Phiếu của tab KHỚP bộ lọc, mọi trang — nguồn "Chọn tất cả N phiếu đang lọc". */
  dangLoc: SalaryAdvance[];
  chon: Set<number>;
  setChon: Dispatch<SetStateAction<Set<number>>>;
  chiXemChon: boolean;
  setChiXemChon: (v: boolean) => void;
  busy: boolean;
  canDuyet: boolean;
  canLapPhieuChi: boolean;
  canXuat: boolean;
  onDuyet: (advs: SalaryAdvance[]) => void;
  onTuChoi: (advs: SalaryAdvance[]) => void;
  onLapPhieuChi: (advs: SalaryAdvance[]) => void;
  onXuatExcel: (advs: SalaryAdvance[]) => void;
}) {
  const choDuyet = tab === "cho_duyet" && canDuyet;
  const choChi = tab === "cho_chi" && (canLapPhieuChi || canXuat);
  if ((!choDuyet && !choChi) || tabRows.length === 0) return null;

  const daChon = tabRows.filter((a) => chon.has(a.id));
  const idLoc = new Set(dangLoc.map((a) => a.id));
  const biChe = daChon.filter((a) => !idLoc.has(a.id)).length;
  const chuaChonHet = dangLoc.some((a) => !chon.has(a.id));
  const tong = daChon.reduce((s, a) => s + a.amount, 0);

  return (
    <div className="lg-tu-chon" role="toolbar" aria-label="Thao tác nhiều phiếu">
      {chuaChonHet && dangLoc.length > 0 && (
        <button
          type="button"
          className="btn btn--ghost"
          onClick={() => setChon((cu) => new Set([...cu, ...dangLoc.map((a) => a.id)]))}
          title="Chọn mọi phiếu khớp bộ lọc, ở mọi trang — phiếu đã chọn trước đó vẫn giữ"
        >
          Chọn tất cả {dangLoc.length} phiếu đang lọc
        </button>
      )}
      {daChon.length > 0 && (
        <>
          <span className="lg-tu-chon__dem">
            Đã chọn <b>{daChon.length}</b> phiếu · {money(tong)}đ
            {biChe > 0 && (
              <span className="lg-tu-chon__che">
                {" "}
                — {biChe} phiếu đang không hiện vì bộ lọc
              </span>
            )}
          </span>
          {(biChe > 0 || chiXemChon) && (
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => setChiXemChon(!chiXemChon)}
            >
              {chiXemChon ? "Xem lại theo bộ lọc" : "Chỉ xem phiếu đã chọn"}
            </button>
          )}
          {choDuyet && (
            <>
              <button
                type="button"
                className="btn btn--primary"
                disabled={busy}
                onClick={() => onDuyet(daChon)}
              >
                Duyệt {daChon.length} phiếu
              </button>
              <button
                type="button"
                className="btn btn--danger"
                disabled={busy}
                onClick={() => onTuChoi(daChon)}
              >
                Từ chối {daChon.length} phiếu
              </button>
            </>
          )}
          {choChi && canLapPhieuChi && (
            <button
              type="button"
              className="btn btn--primary"
              disabled={busy}
              onClick={() => onLapPhieuChi(daChon)}
            >
              Lập phiếu chi cho {daChon.length} phiếu
            </button>
          )}
          {choChi && canXuat && (
            <button
              type="button"
              className="btn btn--ghost"
              disabled={busy}
              onClick={() => onXuatExcel(daChon)}
              title="File chuyển khoản theo mẫu lô lương BIZ MBBank — chỉ những phiếu đang chọn"
            >
              Xuất Excel {daChon.length} phiếu
            </button>
          )}
          <button
            type="button"
            className="btn btn--ghost"
            onClick={() => {
              setChon(new Set());
              setChiXemChon(false);
            }}
          >
            Bỏ chọn
          </button>
        </>
      )}
    </div>
  );
}
