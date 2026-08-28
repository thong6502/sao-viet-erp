// Khối CÁC ĐỢT GIAO trong drawer chi tiết đơn (tách từ pages/PurchaseRequestsPage.tsx).
// ⚠️ KHỐI CẤM XÉ: bảng đợt + dòng tổng "Đã giao − Đã chi = Còn nợ" + khung xem ảnh hoá đơn là
// một khối công nợ, đọc rời từng mảnh là mất mạch.
import { useState } from "react";
import {
  assetUrl,
  type PurchaseAttachmentRow,
  type PurchaseDeliveryRow,
  type PurchaseRequestRow,
} from "../../../../api/client";
import { useCan } from "../../../../auth/permissions";
import { Button } from "../../../../components/Button";
import { Icon } from "../../../../components/Icons";
import { RowActionButton } from "../../../../components/RowActionButton";
import { fmtDate, money } from "../../../../utils/format";
// Đơn vị lưu bằng MÃ (`cai`), tên hiển thị ("cái") nằm ở danh mục Đơn vị — xem pages/tenDonVi.ts.
import { tenDonVi } from "../../../tenDonVi";
import { ATTACHMENT_IMAGE_TYPES, GHI_DOT_DUOC } from "../shared/constants";

/**
 * CÁC ĐỢT GIAO — nơi công nợ thật sự sinh ra.
 *
 * Hàng về tới đâu nợ tới đó: mỗi đợt là một khoản nợ có ngày giao, hạn trả và hoá đơn riêng. Dòng
 * tổng dưới bảng nói đủ ba số để không ai phải tự trừ trong đầu: **Đã giao − Đã chi = Còn nợ**.
 */
export function DeliveriesBlock({
  row,
  canUpdate,
  canApprove,
  onGhiDot,
  onGanHoaDon,
  onXoaDot,
  onDongDon,
  onNhapKho,
  onXemYeuCau,
}: {
  row: PurchaseRequestRow;
  canUpdate: boolean;
  canApprove: boolean;
  onGhiDot: (delivery: PurchaseDeliveryRow | null) => void;
  onGanHoaDon: () => void;
  onXoaDot: (delivery: PurchaseDeliveryRow) => void;
  onDongDon: () => void;
  onNhapKho: (delivery: PurchaseDeliveryRow) => void;
  onXemYeuCau: (delivery: PurchaseDeliveryRow) => void;
}) {
  const ghiDuoc = canUpdate && GHI_DOT_DUOC.includes(row.status);
  // "Nhập kho" nhảy sang màn Kho, tab ĐỀ NGHỊ · Nhập với form điền sẵn ⇒ hỏi đúng ô mở tab đó
  // (`kho:request`), KHÔNG phải `kho:create` — bộ phận mua hàng có `request` mà không có `create`,
  // gác nhầm là giấu nút của chính người cần dùng nó nhiều nhất.
  const coQuyenNhapKho = useCan()("kho", "request");
  const dots = row.deliveries;
  // Khung XEM ẢNH hoá đơn của một đợt. `i` = đang xem tấm thứ mấy (đợt có thể nhiều tấm).
  const [xemAnh, setXemAnh] = useState<null | {
    ds: PurchaseAttachmentRow[];
    i: number;
    dot: number;
  }>(null);

  return (
    <section className="pdot">
      <header className="pdot__head">
        <h3>Các đợt giao</h3>
        <div className="pdot__headbtns">
          {canUpdate && dots.length > 1 && (
            <Button type="button" variant="ghost" onClick={onGanHoaDon}>
              Gán hóa đơn
            </Button>
          )}
          {/* "Đóng đơn" chỉ có nghĩa khi còn hàng chưa về. Server đòi `thu_mua:approve` + lý do;
              nút vẫn hiện cho người thiếu quyền để họ nhận đúng câu báo thay vì không thấy lối. */}
          {canUpdate && canApprove && row.status === "partially_received" && (
            <Button type="button" variant="ghost" onClick={onDongDon}>
              Đóng đơn
            </Button>
          )}
          {ghiDuoc && (
            // Nút CAM DUY NHẤT của hộp thoại Chi tiết phiếu (xem chú thích ở ContractBlock):
            // ghi đợt giao là việc chính của màn và là đường duy nhất sinh công nợ.
            <Button
              type="button"
              variant="accent"
              onClick={() => onGhiDot(null)}
            >
              Ghi đợt giao
            </Button>
          )}
        </div>
      </header>

      {dots.length === 0 ? (
        <p className="pdot__empty">
          <strong>Chưa ghi đợt giao nào.</strong>{" "}
          {ghiDuoc
            ? "Hàng về đợt nào thì ghi đợt đó — công nợ chỉ phát sinh theo số đã ghi ở đây."
            : row.status === "received"
              ? "Đơn này đã chốt nhận hàng theo đường cũ (không theo dõi theo đợt)."
              : "Đơn phải ở trạng thái Đang mua thì mới ghi được đợt giao."}
        </p>
      ) : (
        // Cuộn ngang trong KHUNG RIÊNG của bảng: 10 cột trên drawer 960px là chật, nhưng để cả
        // trang cuộn ngang thì hỏng cả màn (laptop-first). Ba cột tiền cuối (Đã trả · Trừ cọc ·
        // Còn nợ) phải đi liền nhau — tách chúng ra là mất phép trừ.
        <div className="pdot__tablewrap">
        <table className="pay-table pdot__table">
          <thead>
            <tr>
              <th>Đợt</th>
              <th>Ngày giao</th>
              {/* TÁCH ĐÔI 28/08/2026 (chủ chốt: *"tách ra 2 cột, tên mặt hàng và số lượng nhận,
                  chứ đừng nhét chung nhau"*). Trước là một ô "Mini app: 100 cái · Loa: 200 cái" —
                  mắt phải tự dò dấu hai chấm để tách tên khỏi số. */}
              <th>Mặt hàng</th>
              <th className="pay-num">SL nhận</th>
              <th className="pay-num">Thành tiền</th>
              <th>Hóa đơn</th>
              <th>Hạn trả</th>
              <th className="pay-num">Đã trả</th>
              {/* TRỪ CỌC + CÒN NỢ (chủ chốt 27/08/2026). Trước đây bảng chỉ có "Thành tiền" và
                  "Đã trả": đợt được cọc bù thì hai số đó không trừ ra nổi số nợ thật, người đọc
                  chịu chết. Đây đúng bệnh vừa vá ở khối "Đợt giao còn nợ" bên Công nợ phải trả —
                  hai màn nói về CÙNG một đợt giao nên phải cùng một bộ cột. */}
              <th className="pay-num">Trừ cọc</th>
              <th className="pay-num">Còn nợ</th>
              {/* Cột nút không có nhãn nhìn thấy được, nhưng `<th>` rỗng thì trình đọc màn hình
                  đọc ra một ô câm — phải có `aria-label`. */}
              {canUpdate && <th aria-label="Thao tác" />}
            </tr>
          </thead>
          <tbody>
            {dots.map((dot) => {
              const khoa = dot.paid_amount > 0;
              return (
                <tr key={dot.id}>
                  <td>
                    {/* Ai khai đợt này nằm ở tooltip chứ không thành cột: đợt giao đẻ ra công nợ
                        nên phải truy được người khai, nhưng nó là câu hỏi hiếm — chiếm một cột
                        thường trực là đẩy cột TIỀN ra khỏi tầm mắt ở 1440px. */}
                    <strong
                      title={
                        dot.created_by_name
                          ? `${dot.created_by_name} ghi ngày ${fmtDate(dot.created_at)}`
                          : undefined
                      }
                    >
                      Đợt {dot.seq_no}
                    </strong>
                  </td>
                  <td>{fmtDate(dot.delivery_date)}</td>
                  {/* HAI Ô RIÊNG, mỗi ô xếp chồng CÙNG số dòng theo cùng thứ tự — nên dòng thứ n
                      bên trái luôn là món của dòng thứ n bên phải. Tên hàng bị cấm xuống dòng
                      (`.pdot__dl-name`): để nó tràn 2 dòng là lệch hàng ngay, đọc thành món này
                      với số lượng của món kia. Tên đầy đủ nằm ở `title`. */}
                  <td>
                    <div className="pdot__delivery-lines">
                      {dot.lines.map((line) => (
                        <span
                          key={line.id}
                          className="pdot__dl-name"
                          title={line.item_name}
                        >
                          <strong>{line.item_name}</strong>
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="pay-num">
                    <div className="pdot__delivery-lines">
                      {dot.lines.map((line) => (
                        <span key={line.id} className="pdot__dl-qty">
                          {line.quantity.toLocaleString("vi-VN")}{" "}
                          {tenDonVi(line.unit) ?? line.unit}
                          {/* PHẦN DƯ — hàng về nhiều hơn số đặt, tính 0đ. Hiện ngay cạnh số nhận
                              chứ không giấu vào tooltip: nếu NCC thực ra CÓ tính tiền phần này
                              thì đây là chỗ duy nhất bắt được trước lúc đối chiếu hoá đơn. */}
                          {line.quantity_du > 0 && (
                            <em
                              className="pdot__du"
                              title={`${line.quantity_tinh_tien.toLocaleString("vi-VN")} tính tiền · ${line.quantity_du.toLocaleString("vi-VN")} vượt số đặt, giá 0đ`}
                            >
                              {" · "}
                              {line.quantity_du.toLocaleString("vi-VN")} dư
                            </em>
                          )}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="pay-num">
                    <strong>{money(dot.amount)}</strong>
                  </td>
                  <td>
                    {dot.invoice_number ? (
                      <>
                        <strong>{dot.invoice_number}</strong>
                        {dot.invoice_date && (
                          <small>{fmtDate(dot.invoice_date)}</small>
                        )}
                      </>
                    ) : (
                      <small className="pdot__muted">chưa gán</small>
                    )}
                    {/* Có ảnh hoá đơn hay chưa — nhìn được ngay từ bảng, khỏi mở từng đợt ra dò.
                        Chỉ NHẮC, không chặn: hoá đơn về muộn là chuyện thường. */}
                    {(() => {
                      const n = row.attachments.filter(
                        (a) => a.delivery_id === dot.id && a.kind === "hoa_don",
                      ).length;
                      // BẤM VÀO LÀ XEM ẢNH, ngay tại chỗ (chủ chốt 15/08/2026).
                      //
                      // Bản 12/08 cho bấm nhưng mở ô SỬA ĐỢT — vì ảnh đã render sẵn trong đó, tôi
                      // tưởng khỏi dựng thêm màn. Sai: người ta bấm vào cái kẹp giấy là muốn NHÌN
                      // cái ảnh, mà cái mở ra lại là một form nhập liệu có nút "Lưu đợt giao" —
                      // vừa lạc, vừa mời người ta sửa nhầm một con số đang đẻ ra công nợ.
                      return n > 0 ? (
                        <button
                          type="button"
                          className="pdot__clip pdot__clip--btn"
                          onClick={() =>
                            setXemAnh({
                              ds: row.attachments.filter(
                                (a) => a.delivery_id === dot.id && a.kind === "hoa_don",
                              ),
                              i: 0,
                              dot: dot.seq_no,
                            })
                          }
                          title={`Xem ${n} ảnh hoá đơn của đợt ${dot.seq_no}`}
                        >
                          {/* Icon SVG chứ KHÔNG dùng emoji 📎: máy không có font emoji thì nó ra
                              ô vuông tofu, đúng cảnh chủ bắt 27/08/2026. Dùng `fileText` cho khớp
                              ô xem ảnh/PDF của chính đợt này. */}
                          <Icon name="fileText" size={13} />
                          {n}
                        </button>
                      ) : null;
                    })()}
                  </td>
                  <td>
                    {dot.chua_dat_han ? (
                      // Đợt không có hạn thì KHÔNG BAO GIỜ vào cột Quá hạn ở màn Công nợ — nói ra
                      // ngay đây để người thu mua đi khai "Số ngày cho nợ" cho NCC.
                      <span className="pay-badge pay-badge--warn">
                        Chưa đặt hạn
                      </span>
                    ) : (
                      fmtDate(dot.due_date)
                    )}
                  </td>
                  <td className="pay-num">
                    {dot.paid_amount > 0 ? (
                      money(dot.paid_amount)
                    ) : (
                      <small className="pdot__muted">—</small>
                    )}
                  </td>
                  <td className="pay-num">
                    {dot.coc_bu > 0 ? (
                      money(dot.coc_bu)
                    ) : (
                      <small className="pdot__muted">—</small>
                    )}
                  </td>
                  <td className="pay-num">
                    {dot.con_no > 0 ? (
                      <strong>{money(dot.con_no)}</strong>
                    ) : (
                      // Đợt trả xong rồi thì nói "xong", đừng bày một số 0 trơ ra giữa cột tiền.
                      <small className="pdot__muted">xong</small>
                    )}
                  </td>
                  {canUpdate && (
                    <td className="pay-num">
                      {/* Đợt ĐÃ CÓ PHIẾU CHI thì server cấm sửa/xoá — tiền đã ra thì không được
                          đổi số hàng dưới chân nó. Hiện KHOÁ ngay ở đây chứ không bày nút rồi để
                          người dùng gõ xong cả form mới ăn lỗi. */}
                      <div className="pdot__rowbtns">
                        {/* 🔌 NỐI SANG PHÂN HỆ KHO (chủ 07/08/2026: *"cho tôi cái nút Nhập kho…
                            để dev bên kho nó tự nối"*). HIỆN Ở MỌI ĐỢT, không riêng đợt đã chi
                            (*"cứ có đợt về là cho nhập kho"*): nhận hàng vào kho là sự kiện VẬT LÝ,
                            không phụ thuộc đã trả tiền. Bấm → nhảy sang màn Yêu cầu kho, mở sẵn form
                            NHẬP điền theo hàng đã nhận của đợt này. (Nối cứng qua `stock_voucher_id`
                            khi lập phiếu là bước sau — xem docs/prd-mua-hang-cong-no.md §11.) */}
                        {coQuyenNhapKho &&
                          (dot.da_nhap_kho ? (
                            // Đợt đã sinh yêu cầu nhập → không cho seed lại; bấm để XEM yêu cầu đó.
                            <RowActionButton
                              dense
                              label={dot.stock_request_ma ? `Đã nhập · ${dot.stock_request_ma}` : "Đã nhập kho"}
                              icon="check"
                              onClick={() => onXemYeuCau(dot)}
                            />
                          ) : (
                            <RowActionButton
                              dense
                              label="Nhập kho"
                              icon="warehouse"
                              onClick={() => onNhapKho(dot)}
                            />
                          ))}
                        {/* Đợt ĐÃ CÓ PHIẾU CHI thì server cấm sửa/xoá — tiền đã ra thì không được
                            đổi số hàng dưới chân nó. Hiện KHOÁ ngay ở đây chứ không bày nút rồi để
                            người dùng gõ xong cả form mới ăn lỗi. Nhưng NHẬP KHO thì vẫn cho. */}
                        {/* CHỈ hiện với người có quyền GHI (đợt 5). Trước đây mọi người xem đơn
                            đều thấy "Sửa/Xoá đợt giao", bấm mới ăn 403 — máy chủ chặn đúng, giao
                            diện thì bày ra. `ghiDuoc` = canUpdate + đơn đang ở trạng thái ghi được. */}
                        {!ghiDuoc ? null : khoa ? (
                          <span
                            className="pdot__locked"
                            title="Đợt này đã có phiếu chi — huỷ phiếu chi trước rồi mới sửa/xoá được."
                          >
                            Đã chi — khoá
                          </span>
                        ) : (
                          <>
                            <RowActionButton
                              dense
                              label="Sửa đợt giao"
                              icon="pencil"
                              onClick={() => onGhiDot(dot)}
                            />
                            <RowActionButton
                              dense
                              danger
                              label="Xóa đợt giao"
                              icon="trash"
                              onClick={() => onXoaDot(dot)}
                            />
                          </>
                        )}
                      </div>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
        </div>
      )}

      {/* Dòng tổng: ba số của công thức công nợ, đặt cạnh nhau để không ai phải tự trừ trong đầu. */}
      <div className="pdot__totals">
        <span>
          Đã giao <b>{money(row.gia_tri_da_giao)}</b>
        </span>
        <span>
          Đã chi <b>{money(row.net_paid)}</b>
          {row.receipt_received_amount > 0 && (
            <small> (đã trừ {money(row.receipt_received_amount)} thu về)</small>
          )}
        </span>
        <span className="pdot__totals-due">
          Còn nợ <b>{money(row.outstanding_amount)}</b>
        </span>
      </div>

      {/* KHUNG XEM ẢNH hoá đơn — chỉ để NHÌN: không ô nhập, không nút lưu, đóng là xong.
          Có nút mở tab mới cho ai cần phóng to / tải về, và mũi tên khi đợt có nhiều tấm. */}
      {xemAnh && xemAnh.ds.length > 0 && (
        <div
          className="pdot__lb"
          role="presentation"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setXemAnh(null);
          }}
        >
          <div
            className="pdot__lb-box"
            role="dialog"
            aria-modal="true"
            aria-label={`Ảnh hoá đơn đợt ${xemAnh.dot}`}
          >
            <header className="pdot__lb-head">
              <span className="pdot__lb-name">
                Hoá đơn · đợt {xemAnh.dot}
                {xemAnh.ds.length > 1 && (
                  <small>
                    {" "}
                    ({xemAnh.i + 1}/{xemAnh.ds.length})
                  </small>
                )}
              </span>
              <div className="pdot__lb-acts">
                <a
                  href={assetUrl(xemAnh.ds[xemAnh.i].file_url) ?? "#"}
                  target="_blank"
                  rel="noreferrer"
                  title="Mở tab mới / tải về"
                >
                  Mở tab mới
                </a>
                <button
                  type="button"
                  onClick={() => setXemAnh(null)}
                  aria-label="Đóng"
                >
                  ✕
                </button>
              </div>
            </header>
            <div className="pdot__lb-body">
              {ATTACHMENT_IMAGE_TYPES.includes(
                xemAnh.ds[xemAnh.i].file_type ?? "",
              ) ? (
                <img
                  src={assetUrl(xemAnh.ds[xemAnh.i].file_url) ?? ""}
                  alt={xemAnh.ds[xemAnh.i].file_name}
                />
              ) : (
                // PDF cũng đính kèm được ở đây — nhúng thẳng, khỏi bắt tải về mới xem được.
                <iframe
                  src={assetUrl(xemAnh.ds[xemAnh.i].file_url) ?? ""}
                  title={xemAnh.ds[xemAnh.i].file_name}
                />
              )}
            </div>
            {xemAnh.ds.length > 1 && (
              <footer className="pdot__lb-nav">
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() =>
                    setXemAnh((c) =>
                      c
                        ? { ...c, i: (c.i - 1 + c.ds.length) % c.ds.length }
                        : c,
                    )
                  }
                >
                  ← Trước
                </Button>
                <span className="pdot__lb-filename">
                  {xemAnh.ds[xemAnh.i].file_name}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() =>
                    setXemAnh((c) =>
                      c ? { ...c, i: (c.i + 1) % c.ds.length } : c,
                    )
                  }
                >
                  Sau →
                </Button>
              </footer>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
