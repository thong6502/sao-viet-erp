// Popup chỉ-xem một đề nghị cập nhật hồ sơ (tách từ pages/HoSoCuaToiPage.tsx).
import { useEffect, useState } from "react";
import type { EmployeeDetail, UpdateRequest } from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { DetailModal } from "../../../../components/DetailModal";
import { Icon } from "../../../../components/Icons";
import { Timeline } from "../../../../components/Timeline";
import { REQ_FIELD_LABEL } from "../shared/constants";
import { cfgReq, fmtDate, fmtDateTime, giaTriCu, giaTriMoi } from "../shared/helpers";

/** Popup CHỈ-XEM một đề nghị. Nút thao tác nằm ở `footer` theo hợp đồng của `DetailModal`.
 *
 *  Mũi tên "cũ → mới" CHỈ vẽ khi còn `pending`: đơn đã duyệt thì hồ sơ đã mang giá trị mới, hai
 *  vế trùng nhau — vẽ mũi tên lúc đó là bịa dữ liệu. Ba trạng thái còn lại dùng bảng 2 cột. */
export function ReqDetailModal({ req, emp, onClose, onHuy }: {
  req: UpdateRequest; emp: EmployeeDetail; onClose: () => void; onHuy: () => void;
}) {
  const cho = req.status === "pending";
  const cfg = cfgReq(req.status);
  const entries = Object.entries(req.changes);
  // Lý do/ghi chú là chuỗi tự do: gấp lại 8 dòng để một đoạn dán 2000 ký tự không đẩy nút Hủy
  // ra khỏi tầm nhìn. Mở lại thì hiện đủ, không cắt mất chữ nào.
  const [moLyDo, setMoLyDo] = useState(false);
  const [moTuChoi, setMoTuChoi] = useState(false);
  useEffect(() => { setMoLyDo(false); setMoTuChoi(false); }, [req.id]);

  return (
    <DetailModal
      kicker="Đề nghị cập nhật hồ sơ"
      title={`Gửi ngày ${fmtDate(req.created_at)}`}
      subtitle={`${entries.length} mục thông tin · ${fmtDateTime(req.created_at)}`}
      badge={<span className={`badge-sem ${cfg.cls}`}><Icon name={cfg.icon} size={11} />{cfg.label}</span>}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Đóng</Button>
          {cho && (
            <button type="button" className="mine__reqhuy mine__reqhuy--lon" onClick={onHuy}>
              <Icon name="x" size={13} /> Hủy đề nghị
            </button>
          )}
        </>
      }
    >
      <div className={`mine__diff-table${cho ? "" : " mine__diff-table--2col"}`}>
        <div className="mine__diff-table__head">
          <span>Mục thông tin</span>
          {cho ? (
            <>
              <span>Hiện tại</span>
              <span />
              <span>Đề nghị mới</span>
            </>
          ) : (
            <span>Giá trị đã đề nghị</span>
          )}
        </div>
        <div className="mine__diff-table__body">
          {entries.map(([k, v]) => (
            <div className="mine__diff-table__row" key={k}>
              <span className="mine__diff-table__name">{REQ_FIELD_LABEL[k] ?? k}</span>
              {cho ? (
                <>
                  {/* Endpoint "của tôi" KHÔNG trả `current` (BE chỉ điền cho hàng đợi HCNS) —
                      cột này bắt buộc tính từ hồ sơ đang cầm sẵn. */}
                  <span className="mine__diff-chip mine__diff-chip--old">{giaTriCu(emp, k) || "(chưa có)"}</span>
                  <Icon name="arrowRight" size={12} className="mine__diff-arrow" />
                  <span className="mine__diff-chip mine__diff-chip--new">{giaTriMoi(k, v)}</span>
                </>
              ) : (
                <span className="mine__diff-chip mine__diff-chip--val">{giaTriMoi(k, v)}</span>
              )}
            </div>
          ))}
        </div>
      </div>

      {req.reason && (
        <div className="mine__reqreason">
          <Icon name="fileText" size={14} className="mine__reqreason-icon" />
          <div className="mine__reqreason-text">
            <div className={moLyDo ? undefined : "mine__reqreason--clamp"}>
              <span className="mine__reqreason-label">Lý do đề nghị:</span> {req.reason}
            </div>
            <button type="button" className="mine__reqreason-more" onClick={() => setMoLyDo((m) => !m)}>
              {moLyDo ? "Thu gọn" : "Xem đầy đủ"}
            </button>
          </div>
        </div>
      )}

      {req.status === "rejected" && (
        <div className="mine__reqreject">
          <Icon name="alert" size={14} />
          <div className="mine__reqreason-text">
            <div className={moTuChoi ? undefined : "mine__reqreason--clamp"}>
              <strong>HCNS từ chối:</strong>{" "}
              {req.decision_note || "HCNS không ghi lý do. Liên hệ HCNS để biết thêm."}
            </div>
            <button type="button" className="mine__reqreason-more" onClick={() => setMoTuChoi((m) => !m)}>
              {moTuChoi ? "Thu gọn" : "Xem đầy đủ"}
            </button>
          </div>
        </div>
      )}

      <div>
        <h5 className="mine__reqsec">Tiến trình xử lý</h5>
        <Timeline items={[
          { title: "Bạn gửi đề nghị", meta: fmtDateTime(req.created_at), accent: true, tone: "rust" },
          cho
            ? { title: "Đang chờ HCNS xem xét", meta: "—" }
            : {
                title: req.status === "approved" ? `HCNS phê duyệt · ${req.decided_by_name ?? "HCNS"}`
                  : req.status === "rejected" ? `HCNS từ chối · ${req.decided_by_name ?? "HCNS"}`
                  : "Bạn rút lại đề nghị",
                meta: fmtDateTime(req.decided_at),
                accent: true,
                tone: req.status === "approved" ? "moss" : req.status === "rejected" ? "signal" : undefined,
              },
        ]} />
      </div>
    </DetailModal>
  );
}
