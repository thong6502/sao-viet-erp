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
//
// Và vì chốt/mở là hai thao tác DUY NHẤT làm lũy kế nhúc nhích, mỗi lần bấm để lại một dòng vết
// (`lich_su`) hiện ngay dưới bảng — mở lại kỳ xoá sạch người/ngày chốt trên `tai_san_ky`, không
// có vết thì không ai trả lời được "tháng này ai chốt, chốt bao nhiêu, sao giờ số khác".
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import { NHAN_TRANG_THAI_KY, taiSanApi, type BangKy } from "../../api/taiSan";
import { useAuth } from "../../auth/useAuth";
import { useCan } from "../../auth/permissions";
import { Button } from "../../components/Button";
import { Icon } from "../../components/Icons";
import { MonthPicker } from "../../components/MonthPicker";
import { fmtDateTime } from "../../utils/format";
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
                    <td className="ts-col-ten">{r.ten}</td>
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

      {/* Chỉ hiện khi kỳ ĐÃ từng được chốt: kỳ chưa ai đụng tới thì một ô "chưa có vết" rỗng
          chỉ tổ choán chỗ. Câu chú thích đứng một lần ở tiêu đề, thay vì mỗi dòng một dấu +/−
          bắt người đọc tự giải nghĩa. */}
      {bang && bang.lich_su.length > 0 && (
        <section className="ts-vet">
          {/* `{" "}` là bắt buộc: xuống dòng ngay trước một thẻ thì JSX nuốt luôn khoảng trắng,
              ra "Vết chốt / mở kỳ— số tiền…" dính liền. */}
          <h3 className="ts-vet__de">
            Vết chốt / mở kỳ{" "}
            <span className="ts-vet__chu">
              — số tiền là phần đã cộng vào (chốt) hoặc trừ ra (mở) khỏi hao mòn lũy kế
            </span>
          </h3>
          <ul className="ts-vet__ds">
            {bang.lich_su.map((v) => (
              <li key={v.id} className="ts-vet__dong">
                <Badge he={v.hanh_dong === "chot" ? "da_chot" : "mo"}>
                  {v.hanh_dong === "chot" ? "Chốt kỳ" : "Mở lại kỳ"}
                </Badge>
                <span className="ts-vet__tien">{tien(v.so_tien)} đ</span>
                <span className="ts-vet__phu">{v.so_mon} món</span>
                <span className="ts-vet__phu ts-vet__nguoi">{v.nguoi_ten ?? "—"}</span>
                <time className="ts-vet__phu" dateTime={v.thoi_diem}>
                  {fmtDateTime(v.thoi_diem)}
                </time>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
