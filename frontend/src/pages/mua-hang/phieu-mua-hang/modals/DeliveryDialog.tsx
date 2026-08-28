// GHI / SỬA MỘT ĐỢT GIAO (tách từ pages/PurchaseRequestsPage.tsx).
// ⚠️ KHỐI CẤM XÉ: `tienDot` / `conLai` / `daGiaoKhac` sinh thẳng ra công nợ, và vòng đời `blob:`
// của ảnh hoá đơn (tạo → xem trước → thu hồi) phải nằm nguyên một chỗ. Dài quá trần 400 dòng là
// CỐ Ý — xé nhỏ là tách con số ra khỏi luật sinh ra nó.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  api,
  assetUrl,
  type PurchaseDeliveryInput,
  type PurchaseDeliveryRow,
  type PurchaseRequestRow,
} from "../../../../api/client";
import { useAuth } from "../../../../auth/useAuth";
import { ConfirmDialog } from "../../../../components/ConfirmDialog";
import { Icon } from "../../../../components/Icons";
import { money } from "../../../../utils/format";
// Đơn vị lưu bằng MÃ (`cai`), tên hiển thị ("cái") nằm ở danh mục Đơn vị — xem pages/tenDonVi.ts.
import { tenDonVi } from "../../../tenDonVi";
import { ATTACHMENT_IMAGE_TYPES } from "../shared/constants";
import { daGiaoKhac, tienTheoSoLuong, todayInputValue } from "../shared/helpers";
import type { AnhCho } from "../shared/types";

/**
 * GHI / SỬA MỘT ĐỢT GIAO — khai theo TỪNG DÒNG HÀNG (Đ4).
 *
 * Không có ô nhập tiền: thành tiền hiện ra là số CHỈ-ĐỌC, suy từ đơn giá đã chốt trên phiếu. NCC
 * tính khác đơn giá đặt thì sửa đơn giá trên phiếu rồi duyệt lại, đừng mở ô tiền ở đây.
 *
 * Trần mỗi dòng = số đặt − những gì các đợt KHÁC đã nhận. Khai vống là bơm thẳng vào công nợ một
 * món nợ chưa từng phát sinh; server chặn, đây chặn sớm và nói rõ còn bao nhiêu.
 */
export function DeliveryDialog({
  row,
  delivery,
  onClose,
  onDone,
  onChanged,
}: {
  row: PurchaseRequestRow;
  delivery: PurchaseDeliveryRow | null;
  onClose: () => void;
  /** Lưu XONG đợt — cập nhật rồi ĐÓNG hộp. */
  onDone: (next: PurchaseRequestRow) => void;
  /** Đổi thứ gì đó mà hộp phải MỞ TIẾP (xoá một ảnh hoá đơn). Đóng hộp ở đây là người dùng mất
   *  hết những gì đang gõ dở chỉ vì bấm nhầm một cái ×. */
  onChanged: (next: PurchaseRequestRow) => void;
}) {
  const { token } = useAuth();
  const suaDot = delivery != null;

  const conLai = useCallback(
    (lineId: number) =>
      Math.max(
        0,
        row.lines.find((l) => l.id === lineId)!.quantity -
          daGiaoKhac(row, lineId, delivery?.id ?? null),
      ),
    [row, delivery],
  );

  const [ngayGiao, setNgayGiao] = useState(
    delivery?.delivery_date ?? todayInputValue(),
  );
  // Ô "Hạn trả" đang TẮT trên form (khối JSX bên dưới bị comment): hạn trả ưu tiên suy từ
  // `ngày hóa đơn + số ngày cho nợ của NCC`; chưa có hóa đơn mới lùi về ngày giao.
  //
  // Vẫn giữ biến này và vẫn GỬI LÊN: sửa một đợt đã có hạn khai tay trước đó mà gửi `null` là âm
  // thầm xoá mất hạn đó, và món nợ tụt khỏi cột Quá hạn không ai hay. Bật lại ô thì đổi dòng này
  // về `useState` là xong.
  const hanTra = delivery?.due_date ?? "";
  const [soHoaDon, setSoHoaDon] = useState(delivery?.invoice_number ?? "");
  const [ngayHoaDon, setNgayHoaDon] = useState(delivery?.invoice_date ?? "");
  const [ghiChu, setGhiChu] = useState(delivery?.note ?? "");
  // Ghi chú là ô HIẾM dùng ⇒ mặc định thu về một nút chữ. Nhưng đợt đang sửa mà ĐÃ có ghi chú thì
  // phải mở sẵn: giấu nó đi là người sửa không thấy câu cũ, và tưởng đợt này chưa ghi gì.
  const [moGhiChu, setMoGhiChu] = useState(() => (delivery?.note ?? "") !== "");
  // Chỉ tự đặt con trỏ khi NGƯỜI DÙNG bấm mở, không giật focus lúc hộp vừa hiện.
  const ghiChuMoSan = useRef(moGhiChu);
  // Ô số của TỪNG dòng đặt. Ghi đợt mới: điền sẵn phần CÒN LẠI ⇒ hàng về đủ thì chỉ bấm Lưu.
  // Không nhận món nào thì xoá trắng ô đó — dòng trống bị loại khỏi đợt.
  const [soNhan, setSoNhan] = useState<Record<number, string>>(() => {
    const out: Record<number, string> = {};
    for (const line of row.lines) {
      const cu = delivery?.lines.find(
        (dl) => dl.purchase_request_line_id === line.id,
      );
      if (suaDot) {
        out[line.id] = cu ? String(cu.quantity) : "";
      } else {
        // Đợt MỚI: không có đợt nào để bỏ qua, nên trừ hết những gì các đợt hiện có đã lấy.
        const con = line.quantity - daGiaoKhac(row, line.id, null);
        out[line.id] = con > 0 ? String(con) : "";
      }
    }
    return out;
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Ảnh/PDF hoá đơn chụp ngay lúc ghi đợt. Phải GIỮ TRONG BỘ NHỚ rồi tải sau khi lưu: đợt chưa
  // tồn tại thì chưa có `delivery_id` để gắn file vào. Ghi đợt xong mới quay ra tìm nút đính kèm
  // là kiểu người ta quên — hoá đơn đang cầm trên tay lúc nhận hàng, không phải lúc mở lại phiếu.
  //
  // Mỗi file mang theo một `blob:` URL để hiện ẢNH THẬT ngay khi chọn: người nhận hàng phải soát
  // được con số trên tờ hoá đơn có đọc nổi không TRƯỚC khi lưu, chứ không phải sau khi tải xong.
  const [anhMoi, setAnhMoi] = useState<AnhCho[]>([]);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [dangKeo, setDangKeo] = useState(false);
  // URL do `createObjectURL` cấp KHÔNG tự mất khi component chết — phải thu hồi tay, nếu không mỗi
  // lần mở/đóng hộp là rò một tấm ảnh. Ref chỉ để bản dọn lúc unmount thấy được danh sách mới nhất.
  const anhMoiRef = useRef<AnhCho[]>([]);
  useEffect(() => {
    anhMoiRef.current = anhMoi;
  }, [anhMoi]);
  useEffect(
    () => () => {
      for (const a of anhMoiRef.current) if (a.url) URL.revokeObjectURL(a.url);
    },
    [],
  );
  const anhDaCo = (delivery?.id ?? null) === null
    ? []
    : row.attachments.filter(
        (a) => a.delivery_id === delivery!.id && a.kind === "hoa_don",
      );

  // CHIA SỐ NHẬN thành phần TÍNH TIỀN và phần DƯ (28/08/2026). NCC giao thêm mà giá giữ nguyên
  // là chuyện có thật ("đơn 500 cái, họ giao 1000, tiền vẫn 5tr"), nên số nhận được phép vượt số
  // đặt — nhưng phần vượt giá 0đ. Phần tính tiền luôn được lấp TRƯỚC, nên tổng nợ của đơn dừng
  // đúng ở giá trị đã duyệt dù hàng về gấp đôi.
  //
  // ⚠️ Đây là bản XEM TRƯỚC. Con số THẬT do server chia (`phan_bo_du_dot`) theo thứ tự
  // (`delivery_date`, `seq_no`) của TOÀN BỘ các đợt. Bản này lấy `daGiaoKhac` = mọi đợt KHÁC làm
  // phần đã lấp — đúng tuyệt đối khi ghi đợt MỚI (mọi đợt khác đều nằm trước), có thể lệch khi
  // sửa một đợt CŨ nằm giữa. Nó chỉ để người khai thấy ngay hậu quả của số vừa gõ.
  const chiaDong = useMemo(() => {
    const out: Record<number, { tinhTien: number; du: number }> = {};
    for (const line of row.lines) {
      const qty = Number(soNhan[line.id]) || 0;
      const daKhac = daGiaoKhac(row, line.id, delivery?.id ?? null);
      const dat = Number(line.quantity) || 0;
      const tinhTien = Math.max(
        0,
        Math.min(daKhac + qty, dat) - Math.min(daKhac, dat),
      );
      out[line.id] = { tinhTien, du: Math.max(0, qty - tinhTien) };
    }
    return out;
  }, [row, soNhan, delivery]);

  // THÀNH TIỀN của đợt = Σ phần TÍNH TIỀN × đơn giá/CK/VAT đã chốt trên phiếu.
  //
  // KHÔNG có ô nhập tiền (chủ chốt 07/08/2026, đảo lại quyết định 06/08): *"không cho sửa nữa,
  // dựa vào số lượng thực tế tính ra tiền luôn"*. Ô gõ tay đẻ ra đúng cái lệch mà chính chủ bắt
  // được — chi tiết PMH hiện một số, ngoài bảng hiện số khác cho cùng một đợt.
  const tienDot = useMemo(
    () =>
      row.lines.reduce((sum, line) => {
        const t = chiaDong[line.id]?.tinhTien ?? 0;
        return sum + (t > 0 ? tienTheoSoLuong(line, t) : 0);
      }, 0),
    [row.lines, chiaDong],
  );

  /** Nhận file vào hàng chờ. Chặn ngay tại đây thay vì để server từ chối sau khi đợt đã lưu —
   *  lúc đó đợt đã tạo rồi mà người dùng chỉ thấy một câu báo lỗi, dễ ghi lại lần nữa. */
  function themAnh(list: FileList | null) {
    if (!list?.length) return;
    const nhan: AnhCho[] = [];
    for (const file of Array.from(list)) {
      const laAnh = file.type.startsWith("image/");
      if (!(laAnh || file.type === "application/pdf")) {
        setError(`"${file.name}": chỉ nhận ảnh hoặc PDF.`);
        continue;
      }
      if (file.size > 10 * 1024 * 1024) {
        setError(`"${file.name}": vượt quá 10 MB.`);
        continue;
      }
      nhan.push({ file, url: laAnh ? URL.createObjectURL(file) : "" });
    }
    if (nhan.length) setAnhMoi((cur) => [...cur, ...nhan]);
  }

  /** Bỏ một file khỏi hàng chờ — THU HỒI URL ngay tại đây, đừng đợi unmount: bỏ 10 tấm rồi mới
   *  đóng hộp là 10 tấm nằm lại trong bộ nhớ suốt phiên làm việc. */
  function boAnhCho(index: number) {
    setAnhMoi((cur) => {
      const bo = cur[index];
      if (bo?.url) URL.revokeObjectURL(bo.url);
      return cur.filter((_, j) => j !== index);
    });
  }

  async function xoaAnh(attachmentId: number) {
    if (!token || busy) return;
    setBusy(true);
    setError(null);
    try {
      onChanged(await api.purchaseRequests.deleteAttachment(token, row.id, attachmentId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không xóa được ảnh.");
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    if (!token || busy) return;
    const lines = row.lines
      .map((line) => {
        const existing = delivery?.lines.find(
          (item) => item.purchase_request_line_id === line.id,
        );
        return {
          purchase_request_line_id: line.id,
          quantity: Number(soNhan[line.id]),
          note: existing?.note ?? null,
        };
      })
      .filter((l) => Number.isFinite(l.quantity) && l.quantity > 0);
    if (lines.length === 0) {
      setError(
        "Đợt giao phải có ít nhất một dòng hàng. Không nhận món nào thì đừng ghi đợt.",
      );
      return;
    }
    // BỎ 28/08/2026 khối chặn "nhận vượt số còn lại". Nó là bản sao ở giao diện của luật cũ bên
    // `_clean_dot_lines`; luật đó đã gỡ vì NCC giao thêm mà giá giữ nguyên là chuyện có thật.
    // Gỡ server mà quên gỡ đây thì hộp thoại vẫn từ chối, chỉ khác là bằng một câu tự bịa —
    // đúng cái bẫy đã sập một lần: ba nơi cùng canh một luật (`max` của ô nhập, khối này, và
    // service) mà chỉ sửa hai. Nay số nhận vượt KHÔNG đẻ nợ nữa, phần vượt hiện ngay dưới ô gõ.
    if (!ngayGiao) {
      setError("Đợt giao phải có ngày giao.");
      return;
    }
    if (hanTra && hanTra < ngayGiao) {
      setError("Hạn trả không được trước ngày giao.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const existingLines = new Map(
        (delivery?.lines ?? []).map((line) => [line.purchase_request_line_id, line]),
      );
      const linesChanged =
        !suaDot ||
        lines.length !== existingLines.size ||
        lines.some((line) => {
          const existing = existingLines.get(line.purchase_request_line_id);
          return (
            existing == null ||
            Math.abs(existing.quantity - line.quantity) > 1e-9 ||
            (existing.note ?? null) !== (line.note ?? null)
          );
        });
      const payload: PurchaseDeliveryInput = {
        delivery_date: ngayGiao,
        due_date: hanTra || null,
        invoice_number: soHoaDon.trim() || null,
        invoice_date: ngayHoaDon || null,
        note: ghiChu.trim() || null,
        lines: linesChanged ? lines : null,
      };
      let sau = suaDot
        ? await api.purchaseRequests.updateDelivery(
            token,
            row.id,
            delivery!.id,
            payload,
          )
        : await api.purchaseRequests.createDelivery(token, row.id, payload);

      if (anhMoi.length > 0) {
        // Đợt VỪA tạo là đợt có `seq_no` lớn nhất trong kết quả trả về — server đánh số tăng dần
        // trong phạm vi phiếu. Không dò theo id vì id do DB cấp, giao diện không đoán được.
        const dotId = suaDot
          ? delivery!.id
          : sau.deliveries.reduce(
              (max, d) => (d.seq_no > max.seq_no ? d : max),
              sau.deliveries[0],
            )?.id;
        if (dotId != null) {
          for (const { file } of anhMoi) {
            sau = await api.purchaseRequests.uploadAttachment(
              token,
              row.id,
              file,
              "hoa_don",
              dotId,
            );
          }
        }
      }
      onDone(sau);
    } catch (err) {
      // ĐỢT ĐÃ LƯU rồi mới hỏng ở khâu tải ảnh thì KHÔNG được nói "không lưu được đợt giao" —
      // người dùng sẽ ghi lại lần nữa và đẻ đợt trùng.
      setError(
        err instanceof ApiError ? err.message : "Không lưu được đợt giao.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <ConfirmDialog
      open
      wide
      // Mã phiếu vào THẲNG tiêu đề. Đoạn văn dẫn nhập cũ đã bị bỏ: ba câu trong đó lặp lại đúng
      // những gì nhãn vùng, dòng gợi ý và dải "Ghi vào công nợ" bên dưới đã nói.
      title={
        suaDot
          ? `Sửa đợt ${delivery!.seq_no} · ${row.code}`
          : `Ghi đợt giao · ${row.code}`
      }
      confirmLabel={suaDot ? "Lưu đợt giao" : "Ghi đợt giao"}
      busy={busy}
      // Lỗi tự render ở ĐẦU children (ngay dưới đây). ConfirmDialog đặt `error` SAU children, mà
      // hộp này dài hơn một màn ⇒ báo lỗi rơi xuống đáy vùng cuộn, ngoài tầm mắt người vừa bấm Lưu.
      error={null}
      onConfirm={submit}
      onCancel={onClose}
    >
      {error && (
        <div className="banner banner--error" role="alert">
          {error}
        </div>
      )}

      {/* VÙNG 1 — HÀNG NHẬN. Ngày giao nằm ngay trên bảng vì nó là ngày của CHÍNH những dòng
          hàng này, không phải một ô hành chính rời rạc. */}
      <section className="pdot__sec">
        <div className="pdot__sechead">
          <span className="pdot__sectitle">Hàng nhận đợt này</span>
          <label className="pdot__inline">
            <span>
              Ngày giao <span className="purchase__required-star">*</span>
            </span>
            {/* Chặn TƯƠNG LAI: chưa có hóa đơn thì ngày giao là mốc dự phòng tính hạn trả. Quá khứ
                vẫn cho — hàng về hôm qua mới ghi hôm nay là chuyện thường. */}
            <input
              className="input"
              type="date"
              max={todayInputValue()}
              value={ngayGiao}
              onChange={(e) => setNgayGiao(e.target.value)}
            />
          </label>
        </div>
        {/* Ô "Hạn trả" TẮT có chủ ý (ưu tiên ngày hóa đơn, chưa có mới dùng ngày giao + số ngày nợ).
            Biến `hanTra` vẫn được gửi lên — xem khai báo state ở đầu component. Giữ nguyên khối
            dưới đây để bật lại được, đừng xoá: */}
        {/* <label className="purchase__field">
          <span>Hạn trả</span>
          <input
            className="input"
            type="date"
            min={ngayGiao || undefined}
            value={hanTra}
            onChange={(e) => setHanTra(e.target.value)}
          />
          <small className="pdot__hint">
            Bỏ trống = lấy ngày giao + số ngày cho nợ của nhà cung cấp. NCC chưa
            khai số ngày thì đợt này <strong>không vào cột Quá hạn</strong>.
          </small>
        </label> */}
        <div className="pdot__tablecard">
          <table className="pdot__linetable">
            <colgroup>
              <col />
              <col className="pdot__c2" />
              <col className="pdot__c3" />
              <col className="pdot__c4" />
            </colgroup>
            <thead>
              <tr>
                <th>Vật tư</th>
                <th className="pdot__num">Đặt</th>
                <th className="pdot__num">Chưa giao</th>
                {/* KHÔNG có cột tiền theo dòng. Tiền của đợt là MỘT số ở ô "Số tiền theo hóa
                    đơn" bên dưới — hoá đơn ghi một số tổng, không tách theo mặt hàng. Cột tiền ở đây
                    chỉ lặp lại con số đã nằm trong dòng gợi ý dưới ô đó, và tệ hơn: nó trông như số
                    chính thức trong khi không phải. */}
                <th className="pdot__num">Thực nhận</th>
              </tr>
            </thead>
            <tbody>
              {row.lines.map((line) => {
                const con = conLai(line.id);
                // KHÔNG CÒN KHOÁ Ô NHẬP (28/08/2026). Trước đây dòng đã nhận đủ ở các đợt khác
                // thì ô bị khoá cứng, vì gõ vượt sẽ bơm một món nợ ma vào phiếu. Nay gõ vượt KHÔNG
                // đẻ nợ nữa — phần vượt giá 0đ — nên khoá lại chỉ còn là chặn đúng ca hợp lệ: NCC
                // tặng thêm sau khi đã giao đủ số đặt.
                const dvt = tenDonVi(line.unit) ?? line.unit;
                const chia = chiaDong[line.id] ?? { tinhTien: 0, du: 0 };
                return (
                  <tr key={line.id}>
                    <td>
                      {line.item_name}
                      <small>{money(line.expected_unit_price)}/{dvt}</small>
                    </td>
                    <td className="pdot__num">
                      {line.quantity.toLocaleString("vi-VN")} {dvt}
                    </td>
                    <td className="pdot__num">
                      {con > 0 ? (
                        `${con.toLocaleString("vi-VN")} ${dvt}`
                      ) : (
                        <small className="pdot__muted">đã giao đủ</small>
                      )}
                    </td>
                    <td className="pdot__num">
                      <span className="pdot__qtywrap">
                        {/* KHÔNG còn `max`: số nhận được phép vượt số đặt. */}
                        <input
                          className="input pdot__qty"
                          type="number"
                          min={0}
                          step="any"
                          value={soNhan[line.id] ?? ""}
                          onChange={(e) =>
                            setSoNhan((cur) => ({
                              ...cur,
                              [line.id]: e.target.value,
                            }))
                          }
                        />
                        <span className="pdot__unit">{dvt}</span>
                      </span>
                      {/* PHÉP CHIA HIỆN NGAY DƯỚI Ô GÕ, không đợi bấm Lưu. Đây là chỗ DUY NHẤT
                          người khai còn kịp nhận ra "NCC có tính tiền 500 cái này đấy" trước khi
                          con số chạy vào công nợ. */}
                      {chia.du > 0 && (
                        <small className="pdot__split">
                          {chia.tinhTien.toLocaleString("vi-VN")} tính tiền
                          {" · "}
                          <em className="pdot__du">
                            {chia.du.toLocaleString("vi-VN")} dư (0đ)
                          </em>
                        </small>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* VÙNG 2 — TIỀN. CHỈ ĐỌC: tiền của đợt do máy tính từ số lượng × đơn giá đã chốt trên
          phiếu, không ai gõ tay. Vẫn để nó thành một dải riêng cỡ lớn vì đây là con số ĐI VÀO
          CÔNG NỢ — người khai phải thấy ngay hậu quả của số lượng mình vừa gõ. */}
      <div className="pdot__moneybar pdot__moneybar--auto">
        <span className="pdot__moneynote">
          Tính theo số lượng thực nhận × đơn giá đã chốt trên phiếu mua. Phần nhận
          vượt số đặt tính 0đ.
        </span>
        <div className="pdot__result">
          <span className="pdot__resultlabel">Ghi vào công nợ</span>
          <span className="pdot__resultrow">
            <span className="pdot__resultnum">{money(tienDot)}</span>
          </span>
        </div>
      </div>

      {/* VÙNG 3 — HÓA ĐƠN: số, ngày và ẢNH là MỘT nhóm. Ảnh chụp ngay lúc nhận hàng — đó là lúc
          tờ hoá đơn đang cầm trên tay. Bắt quay lại phiếu tìm nút đính kèm là kiểu người ta quên. */}
      <section className="pdot__sec">
        <div className="pdot__sechead">
          <span className="pdot__sectitle">Hóa đơn</span>
          <span className="pdot__secnote">có thể bổ sung sau</span>
        </div>
        <div className="pdot__invgrid">
          <label className="purchase__field">
            <span>Số hóa đơn</span>
            <input
              className="input"
              maxLength={64}
              value={soHoaDon}
              onChange={(e) => setSoHoaDon(e.target.value)}
              placeholder="Chưa có thì để trống"
            />
          </label>
          <label className="purchase__field">
            <span>Ngày hóa đơn</span>
            <input
              className="input"
              type="date"
              max={todayInputValue()}
              value={ngayHoaDon}
              onChange={(e) => setNgayHoaDon(e.target.value)}
            />
          </label>
          {/* Ô chọn file dựng theo mẫu `.nqr-picker` của màn Nội quy: input thật ẩn đi, cái người
              dùng thấy là một nút — và nút đó CŨNG là vùng thả. Kéo thả gọi lại đúng `themAnh` nên
              luật ảnh/PDF + 10 MB chỉ tồn tại ở một chỗ. */}
          <input
            type="file"
            hidden
            multiple
            accept="image/*,application/pdf"
            ref={fileRef}
            onChange={(e) => {
              themAnh(e.target.files);
              e.target.value = "";
            }}
          />
          <button
            type="button"
            className={`pdot__pick${dangKeo ? " is-drop" : ""}`}
            disabled={busy}
            onClick={() => fileRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              if (!busy) setDangKeo(true);
            }}
            onDragLeave={(e) => {
              if (e.target === e.currentTarget) setDangKeo(false);
            }}
            onDrop={(e) => {
              e.preventDefault();
              setDangKeo(false);
              if (!busy) themAnh(e.dataTransfer.files);
            }}
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.75}
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
              focusable="false"
            >
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <path d="M17 8l-5-5-5 5" />
              <path d="M12 3v12" />
            </svg>
            {anhDaCo.length + anhMoi.length > 0
              ? "Thêm ảnh"
              : "Chọn ảnh hóa đơn / kéo vào đây"}
          </button>
        </div>
        <small className="pdot__hint">Ảnh hoặc PDF, tối đa 10 MB mỗi file.</small>
        {(anhDaCo.length > 0 || anhMoi.length > 0) && (
          <div className="pdot__filegrid">
            {anhDaCo.map((a) => (
              <div className="pdot__file" key={a.id}>
                <a
                  href={assetUrl(a.file_url) ?? "#"}
                  target="_blank"
                  rel="noreferrer"
                  title={a.file_name}
                >
                  {ATTACHMENT_IMAGE_TYPES.includes(a.file_type ?? "") ? (
                    <img
                      className="pdot__thumb"
                      src={assetUrl(a.file_url) ?? ""}
                      alt={a.file_name}
                    />
                  ) : (
                    <span className="pdot__thumb pdot__thumb--pdf">
                      <Icon name="fileText" size={22} />
                    </span>
                  )}
                </a>
                <button
                  type="button"
                  className="pdot__filex"
                  aria-label={`Xóa ${a.file_name}`}
                  disabled={busy}
                  onClick={() => xoaAnh(a.id)}
                >
                  ×
                </button>
              </div>
            ))}
            {anhMoi.map((a, i) => (
              <div className="pdot__file" key={`${a.file.name}-${i}`}>
                {/* Xem trước ẢNH THẬT, không phải tên file: người nhận hàng cần soát con số trên
                    tờ hoá đơn có đọc nổi không TRƯỚC khi lưu. Viền đứt + pill để không ai nhầm
                    tấm chờ tải với tấm đã nằm trên máy chủ. */}
                {a.url ? (
                  <img
                    className="pdot__thumb pdot__thumb--cho"
                    src={a.url}
                    alt={a.file.name}
                    title={a.file.name}
                  />
                ) : (
                  <span
                    className="pdot__thumb pdot__thumb--pdf pdot__thumb--cho"
                    title={a.file.name}
                  >
                    <Icon name="fileText" size={22} />
                  </span>
                )}
                <span className="pdot__tilebadge">chờ tải lên</span>
                <button
                  type="button"
                  className="pdot__filex"
                  aria-label={`Bỏ ${a.file.name}`}
                  disabled={busy}
                  onClick={() => boAnhCho(i)}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* VÙNG 4 — GHI CHÚ: ô hiếm dùng nên mặc định thu về một nút chữ, đừng chiếm chỗ của thứ
          ngày nào cũng phải gõ. */}
      {moGhiChu ? (
        <label className="pdot__notewrap">
          <span>Ghi chú đợt</span>
          <input
            className="input"
            autoFocus={!ghiChuMoSan.current}
            value={ghiChu}
            onChange={(e) => setGhiChu(e.target.value)}
            placeholder="Ví dụ: giao tại kho 2, thiếu 3 ram bù sau."
          />
        </label>
      ) : (
        <button
          type="button"
          className="pdot__notebtn"
          onClick={() => setMoGhiChu(true)}
        >
          + Ghi chú đợt
        </button>
      )}
    </ConfirmDialog>
  );
}
