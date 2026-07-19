// Phiếu LỆNH SẢN XUẤT (nội bộ giao xưởng) — TUYỆT ĐỐI KHÔNG có bất kỳ số tiền nào.
// Có ĐVT + khổ thành phẩm (thông từ Đơn vị tính). Data từ LenhSXDetailOut + ngữ cảnh đơn.
import { PrintSheet } from "../components/PrintSheet";
import type { LenhSXDetailOut, OrderDetail, PrintFormDetailOut } from "../api/client";

const maLenh = (id: number): string => `LSX-${String(id).padStart(4, "0")}`;

const TRANG_THAI_LABEL: Record<string, string> = {
  nhap: "Nháp",
  dang_chay: "Đang chạy",
  xong: "Xong",
  huy: "Hủy",
};

const fmtNum = (v: number | null | undefined): string =>
  typeof v === "number" ? Math.round(v).toLocaleString("vi-VN") : "—";

function fmtDate(v: string | null | undefined): string {
  if (!v) return "—";
  const d = new Date(v);
  return isNaN(d.getTime()) ? "—" : d.toLocaleDateString("vi-VN");
}

export function LenhSanXuatPrint({
  detail,
  order,
  mayName,
  cdName,
  toName,
  formDetails,
  khoTP,
  onClose,
  canPrint,
}: {
  detail: LenhSXDetailOut;
  order: OrderDetail | null;
  mayName: (id: number | null) => string | null;
  cdName: (id: number | null) => string;
  toName: (id: number | null) => string | null;
  formDetails: Map<number, PrintFormDetailOut>;
  khoTP: Map<number, string>;
  onClose: () => void;
  canPrint?: boolean;
}) {
  const ma = maLenh(detail.id);
  const firstForm = detail.forms[0] ?? null;

  return (
    <PrintSheet
      title="LỆNH SẢN XUẤT"
      docNo={ma}
      docDate={fmtDate(new Date().toISOString())}
      onClose={onClose}
      canPrint={canPrint}
    >
      {/* Thông tin lệnh */}
      <div className="ps-info">
        <div className="ps-info-grid">
          <div>
            <span className="ps-lbl">Đơn nguồn: </span>
            <b>{order?.order_no ?? `#${detail.order_id}`}</b>
          </div>
          <div>
            <span className="ps-lbl">Khách hàng: </span>
            <b>{order?.customer_name ?? "—"}</b>
          </div>
          <div>
            <span className="ps-lbl">Hạn giao: </span>
            {fmtDate(order?.delivery_committed_date)}
          </div>
          <div>
            <span className="ps-lbl">Trạng thái: </span>
            {TRANG_THAI_LABEL[detail.trang_thai] ?? detail.trang_thai}
          </div>
          <div>
            <span className="ps-lbl">Duyệt mẫu: </span>
            {detail.mau_approved_at
              ? `Đã duyệt — ${detail.mau_approved_snapshot?.ten ?? "—"}`
              : "Chưa duyệt"}
          </div>
        </div>
      </div>

      {/* Ấn phẩm */}
      <div className="ps-sec">Ấn phẩm</div>
      <table className="ps-tbl">
        <colgroup>
          <col style={{ width: "7%" }} />
          <col style={{ width: "45%" }} />
          <col style={{ width: "12%" }} />
          <col style={{ width: "16%" }} />
          <col style={{ width: "20%" }} />
        </colgroup>
        <thead>
          <tr>
            <th>STT</th>
            <th>Tên ấn phẩm</th>
            <th>ĐVT</th>
            <th>Số lượng đích</th>
            <th>Khổ thành phẩm</th>
          </tr>
        </thead>
        <tbody>
          {detail.items.map((it, i) => (
            <tr key={it.id ?? `x${i}`}>
              <td className="c">{i + 1}</td>
              <td>{it.ten}</td>
              <td className="c">{it.don_vi_tinh}</td>
              <td className="c">{fmtNum(it.qty)}</td>
              <td className="c">{(it.id != null ? khoTP.get(it.id) : undefined) ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Quy cách in */}
      <div className="ps-sec">Quy cách in</div>
      {firstForm ? (
        <div className="ps-specs">
          <div>
            <span className="ps-lbl">Khổ in</span>
            <b>
              {firstForm.kho_in_dai || firstForm.kho_in_rong
                ? `${fmtNum(firstForm.kho_in_dai)}×${fmtNum(firstForm.kho_in_rong)} mm`
                : "—"}
            </b>
          </div>
          <div>
            <span className="ps-lbl">Số màu</span>
            <b>{firstForm.so_mau > 0 ? String(firstForm.so_mau) : "—"}</b>
          </div>
          <div>
            <span className="ps-lbl">Số kẽm</span>
            <b>{firstForm.so_kem > 0 ? String(firstForm.so_kem) : "—"}</b>
          </div>
          <div>
            <span className="ps-lbl">Máy</span>
            <b>{mayName(firstForm.may_id) ?? "—"}</b>
          </div>
          <div>
            <span className="ps-lbl">Giấy</span>
            <b>{firstForm.giay_label ?? "—"}</b>
          </div>
          <div>
            <span className="ps-lbl">Tờ chạy</span>
            <b>{firstForm.so_to_chay > 0 ? fmtNum(firstForm.so_to_chay) : "—"}</b>
          </div>
        </div>
      ) : (
        <p style={{ fontSize: 10.5, color: "var(--ps-muted)", margin: "4px 0 0" }}>Chưa xếp tờ in</p>
      )}

      {/* Công đoạn (routing) */}
      <div className="ps-sec">Công đoạn (routing)</div>
      <table className="ps-tbl">
        <colgroup>
          <col style={{ width: "12%" }} />
          <col style={{ width: "53%" }} />
          <col style={{ width: "35%" }} />
        </colgroup>
        <thead>
          <tr>
            <th>Bước</th>
            <th>Công đoạn</th>
            <th>Tổ phụ trách</th>
          </tr>
        </thead>
        <tbody>
          {detail.routing.length === 0 ? (
            <tr>
              <td className="c" colSpan={3}>
                Chưa có routing — theo phân công xưởng
              </td>
            </tr>
          ) : (
            detail.routing.map((s, i) => (
              <tr key={s.id}>
                <td className="c">{i + 1}</td>
                <td>{s.ten || cdName(s.cong_doan_id)}</td>
                <td>{s.to_id != null ? toName(s.to_id) : "Theo công đoạn"}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>

      {/* Tờ in & xếp bài */}
      <div className="ps-sec">Tờ in &amp; xếp bài</div>
      {detail.forms.length === 0 ? (
        <p style={{ fontSize: 10.5, color: "var(--ps-muted)", margin: "4px 0 0" }}>Chưa ghép tờ in</p>
      ) : (
        detail.forms.map((f) => {
          const fd = formDetails.get(f.id);
          return (
            <div key={f.id} className="ps-form">
              <div className="ps-form__hd">Tờ in #{f.id}</div>
              <div className="ps-form__meta">
                Giấy: {f.giay_label ?? "—"} · Khổ in:{" "}
                {f.kho_in_dai || f.kho_in_rong
                  ? `${fmtNum(f.kho_in_dai)}×${fmtNum(f.kho_in_rong)} mm`
                  : "—"}{" "}
                · Tờ chạy: {f.so_to_chay > 0 ? fmtNum(f.so_to_chay) : "—"}
              </div>
              {fd && fd.placements.length > 0 ? (
                <div className="ps-form__gang">
                  <span className="ps-lbl">Xếp bài: </span>
                  {fd.placements.map((p) => `${maLenh(p.lenh_sx_id)}: ${fmtNum(p.so_con)} con/tờ`).join(" · ")}
                </div>
              ) : null}
            </div>
          );
        })
      )}

      {/* Chữ ký */}
      <div className="ps-signs">
        <div>
          <div className="ps-role">Quản đốc</div>
          <div className="ps-hint">(Ký, ghi rõ họ tên)</div>
          <div className="ps-sp" />
        </div>
        <div>
          <div className="ps-role">Tổ trưởng</div>
          <div className="ps-hint">(Ký, ghi rõ họ tên)</div>
          <div className="ps-sp" />
        </div>
      </div>
    </PrintSheet>
  );
}
