// SỐ ĐỒNG HỒ của lượt xe — hai đầu mút của một vòng xe (PRD khoán km §14, 18/09/2026):
//   xuat_phat — xe rời kho (nút "Bắt đầu giao" của khối lượt).
//   ve_kho    — mọi điểm đã có kết quả: số lúc xe về tới kho ⇒ đóng lượt, tính chặng về kho.
// Số lúc tới từng khách ghi ở hộp Nhập kết quả. Máy trừ số liền trước ra km từng chặng rồi tra
// đơn giá theo bậc của chặng — tài xế không gõ km nữa.
//
// Form nằm THẲNG trong khối lượt (không mở hộp riêng): người bấm vẫn thấy lượt mình đang ghi số.
// Việc GỬI do nơi gọi truyền vào — cùng một ô số, khác nhau ở đường API.
import { useState, type ReactNode } from "react";
import { Button } from "../../../../components/Button";

export type CheDoSoDongHo = "xuat_phat" | "ve_kho";

/** Phần lượt mà ô số đồng hồ cần biết. */
export interface LuotChoSoDongHo {
  code: string;
  goi_y_xuat_phat: number | null;
  so_dong_ho_gan_nhat: number | null;
}

const KM_CANH_BAO = 500;

export function FormSoDongHo({
  cheDo,
  luot,
  moTa,
  nhanNut,
  gui,
  onXong,
  onHuy,
}: {
  cheDo: CheDoSoDongHo;
  luot: LuotChoSoDongHo;
  /** Câu dẫn — nói người bấm đang ghi số cho cái gì. */
  moTa: ReactNode;
  nhanNut: string;
  /** Gửi số lên máy chủ; trả về cảnh báo KHÔNG chặn (vd "xe chạy ngoài sổ N km"). */
  gui: (so: number, xacNhanKmLon: boolean) => Promise<string[]>;
  onXong: () => void;
  onHuy?: () => void;
}) {
  // Xuất phát: TỰ ĐIỀN số cuối đã ghi của xe ở lượt trước (PRD §14.4). Đồng hồ trên xe khác số
  // này thì tài xế sửa, máy chủ báo "xe chạy ngoài sổ N km" cho người lên đơn kiểm.
  const [so, setSo] = useState(
    cheDo === "xuat_phat" && luot.goi_y_xuat_phat != null ? String(luot.goi_y_xuat_phat) : "",
  );
  const [xacNhan, setXacNhan] = useState(false);
  const [hoiXacNhan, setHoiXacNhan] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);
  const [canhBao, setCanhBao] = useState<string[]>([]);
  const [dangGui, setDangGui] = useState(false);

  const soGo = so === "" ? null : Number(so);
  const ganNhat = luot.so_dong_ho_gan_nhat;
  const changVe = cheDo === "ve_kho" && soGo != null && ganNhat != null && soGo >= ganNhat
    ? soGo - ganNhat : null;
  const phaiXacNhan = (changVe ?? 0) > KM_CANH_BAO || hoiXacNhan;

  const bam = () => {
    if (soGo == null) return;
    setLoi(null);
    setDangGui(true);
    gui(soGo, xacNhan)
      .then((cb) => {
        // Cảnh báo KHÔNG chặn (số đã lưu) — nhưng không để nó vụt qua: giữ khung mở cho người bấm
        // đọc, bấm "Đã hiểu" mới đóng. "Xe chạy ngoài sổ 30 km" là chuyện phải có người hỏi lại.
        if (cb.length) setCanhBao(cb);
        else onXong();
      })
      .catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : "Không lưu được số đồng hồ";
        setLoi(msg);
        if (msg.includes("bất thường")) {
          setXacNhan(false);
          setHoiXacNhan(true);
        }
      })
      .finally(() => setDangGui(false));
  };

  return (
    <div className="gh-form">
      <p className="rc__sub">{moTa}</p>
      <label>
        {cheDo === "xuat_phat" ? "Số đồng hồ lúc xuất phát" : "Số đồng hồ lúc về kho"}
        <input className="input" type="number" min="0" step="1" value={so}
          disabled={canhBao.length > 0}
          onChange={(e) => setSo(e.target.value)} />
      </label>
      <p className="rc__sub">
        {cheDo === "xuat_phat"
          ? luot.goi_y_xuat_phat != null
            ? `Tự điền số cuối đã ghi của xe (${luot.goi_y_xuat_phat.toLocaleString("vi-VN")}). Đồng hồ trên xe khác số này thì sửa lại cho đúng.`
            : "Xe chưa có số nào trong sổ — đọc số trên đồng hồ xe."
          : ganNhat != null
            ? `Số ở điểm giao cuối: ${ganNhat.toLocaleString("vi-VN")}` +
              (changVe != null ? ` ⇒ chặng về kho ${changVe.toLocaleString("vi-VN")} km` : "")
            : ""}
      </p>

      {/* Bọc <div>: `.gh-form > label` ép nhãn thành cột — ô tích sẽ nhảy lên một dòng riêng. */}
      {phaiXacNhan && canhBao.length === 0 && (
        <div>
          <label className="gh-line">
            <input type="checkbox" checked={xacNhan}
              onChange={(e) => setXacNhan(e.target.checked)} />
            {" "}Xác nhận {changVe != null ? `chặng về kho ${changVe} km` : `số ${so}`} là đúng
          </label>
        </div>
      )}

      {canhBao.map((c) => (
        <div key={c} className="banner banner--warn" role="status">
          {c}
        </div>
      ))}
      {loi && (
        <div className="banner banner--error" role="alert">
          {loi}
        </div>
      )}

      <div className="gh-actions">
        {canhBao.length > 0 ? (
          <Button variant="accent" onClick={onXong}>
            Đã hiểu
          </Button>
        ) : (
          <>
            <Button variant="accent" disabled={soGo == null || dangGui} onClick={bam}>
              {nhanNut}
            </Button>
            {onHuy && (
              <Button variant="ghost" onClick={onHuy}>
                Thôi
              </Button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
