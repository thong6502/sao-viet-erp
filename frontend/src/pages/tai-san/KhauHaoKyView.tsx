// Tab KHẤU HAO THEO KỲ — mỗi tháng một bảng, làm xong thì chốt.
//
// Hai việc TÁCH HẲN nhau, đừng gộp:
//
//   • TÍNH  — xoá dòng cũ của kỳ rồi ghi lại. Bấm mười lần ra một kết quả, và `hao_mon_luy_ke`
//             của tài sản KHÔNG nhúc nhích. Sửa sai thì sửa rồi bấm Tính lại.
//   • CHỐT  — cộng mức trích của kỳ vào `hao_mon_luy_ke`. Đây là thứ DUY NHẤT làm số lũy kế
//             chạy, nên mở lại kỳ là trừ ra đúng con số đó — không lệch một đồng.
//
// Vì thế nút Tính biến mất khi kỳ đã chốt: còn đó thì sớm muộn có người bấm và tự hỏi vì sao
// bảng không đổi.
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import { NHAN_TRANG_THAI_KY, taiSanApi, type BangKy } from "../../api/taiSan";
import { useAuth } from "../../auth/useAuth";
import { useCan } from "../../auth/permissions";
import { Button } from "../../components/Button";
import { Icon } from "../../components/Icons";
import { MonthPicker } from "../../components/MonthPicker";
import { Badge, tien } from "./chung";

function kyHienTai(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function KhauHaoKyView() {
  const { token } = useAuth();
  const can = useCan();
  // Chốt sổ dùng lại ô quyền `close_book` sẵn có của hệ — không đẻ thêm cột quyền cho một nút.
  const chotDuoc = can("tai_san", "close_book");
  const tinhDuoc = can("tai_san", "update");
  const xuatDuoc = can("tai_san", "export");

  const [ky, setKy] = useState(kyHienTai);
  const [bang, setBang] = useState<BangKy | null>(null);
  const [dangTai, setDangTai] = useState(true);
  const [ban, setBan] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);
  const [bao, setBao] = useState<string | null>(null);

  const [nam, thang] = ky.split("-").map(Number);

  /** Đánh số từng lượt nạp, lượt cũ về sau thì VỨT.
   *
   *  Ô tháng là `input[type=month]`: gõ "03/2026" là bốn năm lần `onChange`, mỗi lần một lượt
   *  GET. Các lượt ấy về không theo thứ tự gửi — bảng kỳ 09 về sau bảng kỳ 03 là màn hình ghi
   *  "Tháng 3 / 2026" mà số bên dưới của tháng 9. Không lỗi, không quay vòng, kế toán chép nhầm
   *  số vào phần mềm kế toán mà không có gì gợn. */
  const lanNap = useRef(0);

  const nap = useCallback(() => {
    if (!token || !nam || !thang) return;
    const lan = ++lanNap.current;
    const conDung = () => lan === lanNap.current;
    setDangTai(true);
    setLoi(null);
    taiSanApi
      .bangKy(token, nam, thang)
      .then((kq) => { if (conDung()) setBang(kq); })
      .catch((e) => {
        if (conDung()) setLoi(e instanceof ApiError ? e.message : "Không tải được bảng kỳ.");
      })
      .finally(() => { if (conDung()) setDangTai(false); });
  }, [token, nam, thang]);

  useEffect(() => { nap(); }, [nap]);
  useEffect(() => { setBao(null); }, [ky]);

  /** Mọi nút đều đi qua đây: câu lỗi 409 của máy chủ ("kỳ đã chốt" / "kỳ trước chưa chốt") phải
   *  hiện NGUYÊN VĂN. Gói thành "có lỗi xảy ra" là kế toán không biết phải làm gì tiếp. */
  async function chay(viec: (t: string) => Promise<unknown>, xong: string) {
    if (!token) return;
    setBan(true);
    setLoi(null);
    setBao(null);
    try {
      await viec(token);
      setBao(xong);
      nap();
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không thực hiện được.");
    } finally {
      setBan(false);
    }
  }

  async function xuatExcel() {
    if (!token) return;
    setBan(true);
    setLoi(null);
    try {
      const url = await taiSanApi.excelKy(token, nam, thang);
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

  const daChot = bang?.trang_thai === "da_chot";
  const dong = bang?.items ?? [];
  const rong = dong.length === 0;

  return (
    <>
      <div className="ts-kybar">
        <MonthPicker value={ky} onChange={setKy} ariaLabel="Chọn kỳ khấu hao" disabled={ban} />
        {bang && (
          <Badge he={bang.trang_thai}>
            {NHAN_TRANG_THAI_KY[bang.trang_thai] ?? bang.trang_thai}
          </Badge>
        )}
        <div className="ts-kybar__phai">
          {!daChot && tinhDuoc && (
            <Button variant="accent" loading={ban}
              onClick={() => chay(
                (t) => taiSanApi.tinhKy(t, nam, thang),
                "Đã tính lại bảng khấu hao của kỳ này.",
              )}>
              <Icon name="calculator" size={15} /> Tính khấu hao tháng này
            </Button>
          )}
          {xuatDuoc && (
            <Button variant="ghost" disabled={ban || rong} onClick={xuatExcel}>
              <Icon name="fileText" size={15} /> Xuất Excel
            </Button>
          )}
          {chotDuoc && !daChot && (
            <Button variant="primary" disabled={ban || rong}
              onClick={() => chay(
                (t) => taiSanApi.chotKy(t, nam, thang),
                "Đã chốt kỳ. Số lũy kế của từng tài sản đã cộng thêm mức trích của kỳ này.",
              )}>
              <Icon name="lock" size={15} /> Chốt kỳ
            </Button>
          )}
          {chotDuoc && daChot && (
            <Button variant="ghost" disabled={ban}
              onClick={() => chay(
                (t) => taiSanApi.moKy(t, nam, thang),
                "Đã mở lại kỳ. Số lũy kế đã trừ ra đúng mức trích của kỳ này.",
              )}>
              <Icon name="lockOpen" size={15} /> Mở lại kỳ
            </Button>
          )}
        </div>
      </div>

      {daChot && (
        <div className="ts-khoa">
          <Icon name="lock" size={15} />
          <span>
            Kỳ này đã chốt — số đã vào lũy kế, không tính lại được. Cần sửa thì bấm
            <strong> Mở lại kỳ</strong> (chỉ mở được khi chưa chốt kỳ nào sau nó).
          </span>
        </div>
      )}

      {loi && (
        <div className="banner banner--error" role="alert" style={{ marginBottom: "var(--sp-4)" }}>
          {loi}
        </div>
      )}
      {bao && (
        <div className="banner banner--success" role="status" style={{ marginBottom: "var(--sp-4)" }}>
          {bao}
        </div>
      )}

      <div className="rc__tablewrap">
        <table className="rc__table">
          <thead>
            <tr>
              <th style={{ width: "9%" }}>Mã</th>
              <th>Tên</th>
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
                      Kỳ {String(thang).padStart(2, "0")}/{nam} chưa có số.
                      {tinhDuoc && !daChot
                        ? " Bấm “Tính khấu hao tháng này” để máy dựng bảng."
                        : ""}
                    </p>
                  </div>
                </td>
              </tr>
            ) : (
              <>
                {dong.map((r) => (
                  <tr key={r.tai_san_id}>
                    <td><span className="rc__code-badge">{r.ma}</span></td>
                    <td>{r.ten}</td>
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
                  <td colSpan={4}>TỔNG {dong.length} món</td>
                  <td className="ts-num">{tien(bang?.tong_muc_trich)}</td>
                  <td colSpan={2} />
                </tr>
              </>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
