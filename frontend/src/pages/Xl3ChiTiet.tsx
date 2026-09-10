// XẾP LỊCH 3 — PANEL chi tiết một LỆNH SẢN XUẤT.
//
// Panel trả lời ba câu, theo đúng thứ tự người dùng hỏi:
//   1. Lệnh này là gì (khách · đơn · PO · sale · sản lượng · quy cách · hạn);
//   2. Nó chạy từ lúc nào tới lúc nào, và vì sao dài như vậy (chạy + nghỉ ngoài ca);
//   3. Nó gồm những bước nào, ai làm, máy nào, mất bao lâu.
//
// Bảng công đoạn CỐ Ý không có cột bắt đầu/kết thúc từng bước: đây là màn cấp LỆNH. Bốn chỗ khác
// (giữ chỗ vật tư · bảng cân đối · màn Máy · bàn tổ) cần mốc bước thì lấy qua đường riêng ở backend.
import type { Xl3ChiTiet as Xl3ChiTietData } from "../api/client";
import { gio, ngayNgan, thoiLuong, treHan } from "./xl3Shared";

const TRANG_THAI_NHAN: Record<string, string> = {
  nhap: "Nháp",
  cho_bo_sung: "Chờ bổ sung",
  san_sang: "Sẵn sàng",
  da_lap_ke_hoach: "Đã lập kế hoạch",
  da_phat_hanh: "Đã phát hành",
};

function O({ nhan, children }: { nhan: string; children: React.ReactNode }) {
  return (
    <div className="xl3-o">
      <span className="xl3-o__nhan">{nhan}</span>
      <span className="xl3-o__gt">{children}</span>
    </div>
  );
}

export interface Xl3ChiTietProps {
  ct: Xl3ChiTietData | null;
  dangTai: boolean;
  suaDuoc: boolean;
  duyetDuoc: boolean;
  dangGhi: boolean;
  onDoiGio(gioMoi: string): void;
  onBoLich(): void;
  onPhatHanh(): void;
  onThuHoi(): void;
  onDong(): void;
}

export function Xl3ChiTiet({
  ct, dangTai, suaDuoc, duyetDuoc, dangGhi,
  onDoiGio, onBoLich, onPhatHanh, onThuHoi, onDong,
}: Xl3ChiTietProps) {
  if (dangTai && !ct) return <section className="xl3-panel xl3-panel--trong">Đang tải…</section>;
  if (!ct) {
    return (
      <section className="xl3-panel xl3-panel--trong">
        Chọn một lệnh trên lưới hoặc trong hàng chờ để xem chi tiết.
      </section>
    );
  }

  const daXep = !!ct.bat_dau_at;
  const daPhatHanh = ct.trang_thai === "da_phat_hanh";
  const tre = treHan(ct);
  // Ô giờ nhận `datetime-local`: server đã trả ISO naive giờ nhà máy nên cắt 16 ký tự là đúng ô.
  const gioInput = (ct.bat_dau_at ?? "").slice(0, 16);

  return (
    <section className="xl3-panel">
      <header className="xl3-panel__dau">
        <div>
          <div className="xl3-panel__ma">
            {ct.is_rush && <span className="xl3-gap">GẤP</span>}
            <strong>{ct.ma}</strong>
            <span className={`xl3-tt xl3-tt--${ct.trang_thai}`}>
              {TRANG_THAI_NHAN[ct.trang_thai] ?? ct.trang_thai}
            </span>
          </div>
          <div className="xl3-panel__ten">{ct.ten || "—"}</div>
        </div>
        <button type="button" className="xl3-panel__dong" onClick={onDong} aria-label="Đóng">
          ×
        </button>
      </header>

      <div className="xl3-panel__than">
        <div className="xl3-khoi-o">
          <O nhan="Khách hàng">{ct.customer_name ?? "—"}</O>
          <O nhan="Đơn hàng">{ct.order_no ?? "—"}</O>
          <O nhan="PO khách">{ct.customer_po_no ?? "—"}</O>
          <O nhan="Sale">{ct.sale_name ?? "—"}</O>
          <O nhan="Sản lượng">
            {ct.so_luong_dat.toLocaleString("vi-VN")} {ct.don_vi_tinh ?? ""}
          </O>
          <O nhan="Tờ kế hoạch">
            {ct.so_to_ke_hoach.toLocaleString("vi-VN")}
            {ct.so_con > 1 ? ` · ${ct.so_con} con/tờ` : ""}
          </O>
          {ct.giay && <O nhan="Giấy">{ct.giay}</O>}
          {ct.kho_in && <O nhan="Khổ in">{ct.kho_in}</O>}
          {ct.so_mau && <O nhan="Số màu">{ct.so_mau}</O>}
          {ct.so_kem && <O nhan="Số kẽm">{ct.so_kem}</O>}
          <O nhan="Hạn SX">{ngayNgan(ct.han_hoan_thanh_sx)}</O>
          <O nhan="Hạn giao khách">{ngayNgan(ct.han_giao_khach)}</O>
          <O nhan="Phụ trách">{ct.nguoi_phu_trach_ten ?? "—"}</O>
          <O nhan="Kíp chuẩn">{ct.kip_chuan || "—"}</O>
        </div>

        {ct.luu_y_gui_xuong && (
          <p className="xl3-luu-y">
            <span>Dặn xuống xưởng</span>
            {ct.luu_y_gui_xuong}
          </p>
        )}

        <div className={`xl3-lich${tre !== null && tre > 0 ? " xl3-lich--tre" : ""}`}>
          <label className="xl3-lich__o">
            <span>Bắt đầu</span>
            <input
              type="datetime-local"
              value={gioInput}
              min="2000-01-01T00:00"
              max="2099-12-31T23:59"
              disabled={!suaDuoc || dangGhi}
              onChange={(e) => e.target.value && onDoiGio(`${e.target.value}:00`)}
            />
          </label>
          <div className="xl3-lich__ra">
            <span>Kết thúc</span>
            <strong>{gio(ct.ket_thuc)}</strong>
          </div>
          <div className="xl3-lich__ra">
            <span>Chạy máy</span>
            <strong>{thoiLuong(ct.chay_phut)}</strong>
          </div>
          <div className="xl3-lich__ra" title="Nghỉ giữa ca + ngoài ca + ngày nghỉ">
            <span>Nghỉ / ngoài ca</span>
            <strong>{thoiLuong(ct.nghi_ngoai_ca_phut)}</strong>
          </div>
          {tre !== null && tre > 0 && (
            <p className="xl3-lich__canh">
              Kết thúc muộn hơn hạn SX {tre} ngày. Màn không chặn — cân nhắc dời lệnh khác hoặc báo
              lại hạn.
            </p>
          )}
        </div>

        {ct.ghi_chu.length > 0 && (
          <ul className="xl3-ghi-chu">
            {ct.ghi_chu.map((g, i) => (
              <li key={i}>{g}</li>
            ))}
          </ul>
        )}

        <table className="xl3-bang">
          {/* Chia cột CỨNG (`table-layout: fixed` ở CSS): panel hẹp mà để bảng tự chia thì tên máy
              dài bị bóp còn một chữ mỗi dòng. */}
          <colgroup>
            <col className="xl3-c-stt" />
            <col className="xl3-c-ten" />
            <col className="xl3-c-may" />
            <col className="xl3-c-sl" />
            <col className="xl3-c-kip" />
            <col className="xl3-c-tl" />
          </colgroup>
          <thead>
            <tr>
              <th>#</th>
              <th>Công đoạn</th>
              <th>Máy / Tổ</th>
              <th className="xl3-bang--so">SL vào</th>
              <th className="xl3-bang--so">Kíp</th>
              <th className="xl3-bang--so">Thời lượng</th>
            </tr>
          </thead>
          <tbody>
            {ct.cong_doans.map((c) => (
              <tr key={c.id}>
                <td>
                  <span className={`xl3-cham xl3-cham--${c.mau_index}`} />
                  {c.thu_tu}
                </td>
                <td>{c.ten}</td>
                <td>{c.may_ten ?? c.to_ten ?? "—"}</td>
                <td className="xl3-bang--so">
                  {c.so_luong_vao ? c.so_luong_vao.toLocaleString("vi-VN") : "—"}
                  {c.don_vi_vao ? ` ${c.don_vi_vao}` : ""}
                </td>
                <td className="xl3-bang--so">{c.kip_chuan || "—"}</td>
                <td className="xl3-bang--so">
                  {c.thue_ngoai_ngay != null ? `${c.thue_ngoai_ngay} ngày (ngoài)` : thoiLuong(c.chay_phut)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <footer className="xl3-panel__chan">
        {suaDuoc && daXep && !daPhatHanh && (
          <button type="button" className="xl3-nut xl3-nut--phu" disabled={dangGhi} onClick={onBoLich}>
            Bỏ lịch
          </button>
        )}
        {duyetDuoc && daXep && !daPhatHanh && (
          <button type="button" className="xl3-nut xl3-nut--chinh" disabled={dangGhi} onClick={onPhatHanh}>
            Phát hành xuống xưởng
          </button>
        )}
        {duyetDuoc && daPhatHanh && (
          <button type="button" className="xl3-nut xl3-nut--phu" disabled={dangGhi} onClick={onThuHoi}>
            Thu hồi phát hành
          </button>
        )}
      </footer>
    </section>
  );
}
