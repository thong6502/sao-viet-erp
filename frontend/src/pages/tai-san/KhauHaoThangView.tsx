// Tab BẢNG KHẤU HAO THÁNG — chọn tháng, nhìn bảng, xuất Excel. Hết.
//
// Từ 08/09/2026 KHÔNG còn kỳ (chủ: "nó chỉ theo dõi khấu hao thôi"): không nút Tính, không Chốt,
// không Mở lại. Máy chủ dựng bảng tại chỗ từ lịch của từng tài sản, hỏi lại tháng nào cũng ra
// đúng một số; hao mòn lũy kế ở tab Danh sách là cộng dồn chính lịch ấy tới hết tháng trước.
// Cầu nối sang phần mềm kế toán vẫn là file Excel — kế toán đọc rồi tự gõ định khoản.
//
// Hai tab phải NỐI với nhau (chủ 08/09: "bớt 1 tấm mà bảng tháng vẫn điền 26.400.000, khó hiểu"):
// tháng nào có chuyện thì dưới tên có câu "trước → sau" máy chủ viết sẵn, và bấm vào dòng là mở
// đúng ngăn xem chi tiết như bên Danh sách (bảng dự kiến + lịch sử chứng từ).
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import { taiSanApi, type BangThang, type HangBangThang, type TaiSanChiTiet } from "../../api/taiSan";
import { useAuth } from "../../auth/useAuth";
import { useCan } from "../../auth/permissions";
import { Button } from "../../components/Button";
import { Icon } from "../../components/Icons";
import { MonthPicker } from "../../components/MonthPicker";
import { ChiTietDialog } from "./ChiTietDialog";
import { tien } from "./chung";

function thangHienTai(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function KhauHaoThangView() {
  const { token } = useAuth();
  const can = useCan();
  const xuatDuoc = can("tai_san", "export");

  const [thangChon, setThangChon] = useState(thangHienTai);
  const [bang, setBang] = useState<BangThang | null>(null);
  const [dangTai, setDangTai] = useState(true);
  const [ban, setBan] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);
  const [xem, setXem] = useState<TaiSanChiTiet | null>(null);

  const [nam, thang] = thangChon.split("-").map(Number);

  /** Đánh số từng lượt nạp, lượt cũ về sau thì VỨT.
   *
   *  Ô tháng là `input[type=month]`: gõ "03/2026" là bốn năm lần `onChange`, mỗi lần một lượt
   *  GET. Các lượt ấy về không theo thứ tự gửi — bảng tháng 09 về sau bảng tháng 03 là màn hình
   *  ghi "Tháng 3 / 2026" mà số bên dưới của tháng 9. Không lỗi, không quay vòng, kế toán chép
   *  nhầm số vào phần mềm kế toán mà không có gì gợn. */
  const lanNap = useRef(0);

  const nap = useCallback(() => {
    if (!token || !nam || !thang) return;
    const lan = ++lanNap.current;
    const conDung = () => lan === lanNap.current;
    setDangTai(true);
    setLoi(null);
    taiSanApi
      .bangThang(token, nam, thang)
      .then((kq) => { if (conDung()) setBang(kq); })
      .catch((e) => {
        if (conDung()) setLoi(e instanceof ApiError ? e.message : "Không tải được bảng tháng.");
      })
      .finally(() => { if (conDung()) setDangTai(false); });
  }, [token, nam, thang]);

  useEffect(() => { nap(); }, [nap]);

  async function moXem(r: HangBangThang) {
    if (!token) return;
    try {
      setXem(await taiSanApi.chiTiet(token, r.tai_san_id));
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không mở được tài sản này.");
    }
  }

  async function xuatExcel() {
    if (!token) return;
    setBan(true);
    setLoi(null);
    try {
      const url = await taiSanApi.excelThang(token, nam, thang);
      const a = document.createElement("a");
      a.href = url;
      a.download = `Bang khau hao ${String(thang).padStart(2, "0")}-${nam}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không xuất được Excel.");
    } finally {
      setBan(false);
    }
  }

  const dong = bang?.items ?? [];
  const rong = dong.length === 0;
  const nhanThang = `${String(thang).padStart(2, "0")}/${nam}`;

  return (
    <>
      <div className="ts-kybar">
        <MonthPicker value={thangChon} onChange={setThangChon} ariaLabel="Chọn tháng" disabled={ban} />
        <span className="ts-kybar__chu">
          Tính tại chỗ từ sổ — không cần bấm tính, không có gì để chốt. Bấm vào dòng để xem chi tiết.
        </span>
        <div className="ts-kybar__phai">
          {xuatDuoc && (
            <Button variant="ghost" disabled={ban || rong} onClick={xuatExcel}>
              <Icon name="fileText" size={15} /> Xuất Excel
            </Button>
          )}
        </div>
      </div>

      {loi && (
        <div className="banner banner--error" role="alert" style={{ marginBottom: "var(--sp-4)" }}>
          {loi}
        </div>
      )}

      <div className="rc__tablewrap">
        <table className="rc__table">
          <thead>
            <tr>
              <th style={{ width: "9%" }}>Mã</th>
              <th className="ts-col-ten">Tên</th>
              <th style={{ width: "12%" }}>Bộ phận</th>
              <th style={{ width: "12%" }} className="ts-num">Nguyên giá</th>
              <th style={{ width: "12%" }} className="ts-num">Trích tháng này</th>
              <th style={{ width: "12%" }} className="ts-num">Lũy kế</th>
              <th style={{ width: "12%" }} className="ts-num">Còn lại</th>
            </tr>
          </thead>
          <tbody>
            {dangTai ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={`sk-${i}`} className="rc-skel__row">
                  {Array.from({ length: 7 }).map((__, j) => (
                    <td key={j}><span className="rc-skel" style={{ width: "70%" }} /></td>
                  ))}
                </tr>
              ))
            ) : rong ? (
              <tr>
                <td colSpan={7} className="rc__empty-state-td">
                  <div className="rc__empty-state">
                    <p className="rc__empty-text">
                      Tháng {nhanThang} không có tài sản nào trích khấu hao — chưa tới ngày đưa
                      vào sử dụng, đã trích hết, hoặc đã ghi giảm từ trước.
                    </p>
                  </div>
                </td>
              </tr>
            ) : (
              <>
                {dong.map((r) => (
                  <tr key={r.tai_san_id} className="ts-row--xem" onClick={() => moXem(r)}
                    title="Bấm để xem chi tiết và bảng khấu hao dự kiến">
                    <td><span className="rc__code-badge">{r.ma}</span></td>
                    <td className="ts-col-ten">
                      <div>
                        {r.ten}
                        {r.so_luong > 1 && <span className="ts-ten__sl"> · {r.so_luong} cái</span>}
                      </div>
                      {/* Tháng có chuyện: chip ngắn, câu đầy đủ ở tooltip và ngăn chi tiết —
                          không chèn cả câu vào bảng kẻo dòng cao gấp ba (chủ 08/09: "xấu"). */}
                      {r.su_kien.length > 0 && (
                        <div className="ts-chips">
                          {r.su_kien.map((s, i) => (
                            <span key={i} className={`ts-chip ts-chip--${s.loai}`} title={s.chi_tiet}>
                              {s.nhan}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="rc__clip" title={r.bo_phan_ten ?? ""}>{r.bo_phan_ten ?? "—"}</td>
                    <td className="ts-num">{tien(r.nguyen_gia)}</td>
                    <td className="ts-num ts-num--manh">{tien(r.muc_trich)}</td>
                    <td className="ts-num">{tien(r.luy_ke)}</td>
                    <td className={`ts-num${r.con_lai <= 0 ? " ts-num--het" : ""}`}>
                      {tien(r.con_lai)}
                    </td>
                  </tr>
                ))}
                {/* Dòng TỔNG: đây là con số kế toán chép sang phần mềm kế toán. */}
                <tr className="ts-table__tong">
                  <td colSpan={4}>TỔNG {dong.length} món · tháng {nhanThang}</td>
                  <td className="ts-num">{tien(bang?.tong_muc_trich)}</td>
                  <td colSpan={2} />
                </tr>
              </>
            )}
          </tbody>
        </table>
      </div>

      {token && xem && (
        <ChiTietDialog token={token} taiSan={xem} onClose={() => setXem(null)} />
      )}
    </>
  );
}
