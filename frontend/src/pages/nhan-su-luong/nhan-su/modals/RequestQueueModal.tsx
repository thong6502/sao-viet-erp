// Hàng đợi duyệt "yêu cầu cập nhật hồ sơ" (tách từ pages/NhanSuPage.tsx).
import { useCallback, useEffect, useState } from "react";
import { api, type UpdateRequest } from "../../../../api/client";
import { EmptyState } from "../../../../components/EmptyState";
import { RowActionButton } from "../../../../components/RowActionButton";
import { fmtDateTime } from "../../../../utils/format";
import { AlertTriangle, ArrowRight, Clock, User } from "lucide-react";
import { REQ_FIELD_LABEL } from "../shared/constants";
import { errMsg, reqQuaDai, reqValue } from "../shared/helpers";

export function RequestQueueModal({
  token,
  onClose,
  onDecided,
}: {
  token: string;
  onClose: () => void;
  onDecided: () => void;
}) {
  const [items, setItems] = useState<UpdateRequest[] | null>(null);
  const [busy, setBusy] = useState(false);
  /** Lỗi TẢI hàng đợi. Trước đây `.catch` nuốt lỗi rồi `setItems([])` ⇒ máy chủ chết mà bảng
   *  vẫn in "không có yêu cầu": HCNS tưởng sạch việc và đóng màn. */
  const [listError, setListError] = useState<string | null>(null);
  /** Lỗi khi DUYỆT/TỪ CHỐI (khác lỗi tải danh sách) — vd nội dung dài hơn ô hồ sơ. */
  const [actionError, setActionError] = useState<string | null>(null);
  const load = useCallback(() => {
    setListError(null);
    api.employees
      .updateRequests(token, "pending")
      .then((r) => setItems(r.items))
      .catch((e) => {
        setItems([]);
        setListError(errMsg(e));
      });
  }, [token]);
  useEffect(() => {
    load();
  }, [load]);

  async function decide(id: number, approve: boolean) {
    setBusy(true);
    setActionError(null);
    try {
      if (approve) await api.employees.approveRequest(token, id);
      else await api.employees.rejectRequest(token, id, "Từ chối");
      load();
      onDecided();
    } catch (e) {
      // Trước đây lỗi duyệt rơi vào hư không: người duyệt bấm, không thấy gì đổi, tưởng máy
      // đơ. Hay gặp nhất là ô dài hơn cột (BE trả câu "… tối đa N ký tự").
      setActionError(errMsg(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="ns-modal" role="dialog" aria-modal="true" aria-labelledby="nsq-title">
      <div className="ns-modal__box ns-modal__box--wide">
        <header className="ns-modal__head">
          <h2 id="nsq-title">Yêu cầu cập nhật hồ sơ (chờ duyệt)</h2>
          <button className="ns-modal__x" onClick={onClose} aria-label="Đóng">
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {actionError && (
            <div className="banner banner--error" role="alert">
              {actionError}
            </div>
          )}
          {!items && !listError && <EmptyState trangThai="dang-tai" inline />}
          {listError && (
            <EmptyState trangThai="loi" loi={listError} onThuLai={load} inline />
          )}
          {!listError && items?.length === 0 && (
            <EmptyState
              icon="clipboard"
              title="Chưa có yêu cầu chờ duyệt"
              sub="Nhân viên gửi đề nghị sửa hồ sơ thì việc sẽ hiện ở đây."
              inline
            />
          )}
          {/* MỖI ĐỀ NGHỊ MỘT THẺ, không nhồi vào một ô bảng nữa: chuỗi nối bằng dấu "·" không
              xuống dòng nên hộ khẩu / nơi cấp CCCD dài là đẩy luôn cột Lý do và hai nút
              Duyệt–Từ chối ra khỏi màn. Thẻ cũng là chỗ đặt được cột "Hiện tại" — người duyệt
              phải thấy đang đổi TỪ GÌ sang gì mới quyết được. */}
          {!listError && !!items?.length && (
            <ul className="nsq__list">
              {items.map((r) => {
                const entries = Object.entries(r.changes);
                const quaDai = reqQuaDai(r.changes);
                return (
                  <li className="nsq__item" key={r.id}>
                    <div className="nsq__head">
                      <span className="nsq__who">
                        <User size={13} />
                        {r.employee_name ?? `NV#${r.employee_id}`}
                      </span>
                      <span className="nsq__sent">
                        <Clock size={12} />
                        Gửi {fmtDateTime(r.created_at)}
                      </span>
                    </div>

                    <div className="nsq__diff">
                      <div className="nsq__diff-head">
                        <span>Mục thông tin</span>
                        <span>Hiện tại</span>
                        <span aria-hidden="true" />
                        <span>Đề nghị mới</span>
                      </div>
                      {entries.map(([k, v]) => (
                        <div className="nsq__diff-row" key={k}>
                          <span className="nsq__diff-name">
                            {REQ_FIELD_LABEL[k] ?? k}
                          </span>
                          <span className="nsq__chip nsq__chip--old">
                            {reqValue(k, r.current?.[k], "(chưa có)")}
                          </span>
                          <ArrowRight
                            size={13}
                            className="nsq__arrow"
                            aria-hidden="true"
                          />
                          <span className="nsq__chip nsq__chip--new">
                            {reqValue(k, v, "(bỏ trống)")}
                          </span>
                        </div>
                      ))}
                    </div>

                    {r.reason && (
                      <p className="nsq__reason">
                        <span className="nsq__reason-label">Lý do đề nghị:</span>{" "}
                        {r.reason}
                      </p>
                    )}

                    {quaDai.length > 0 && (
                      <p className="nsq__warn" role="alert">
                        <AlertTriangle size={13} />
                        <span>
                          Nội dung dài hơn ô hồ sơ cho phép ({quaDai.join(" · ")}) — duyệt
                          sẽ bị chặn. Đề nghị nhân viên gửi lại bản ngắn gọn.
                        </span>
                      </p>
                    )}

                    <div className="nsq__foot">
                      <div className="cc-rowact ns-rowact">
                        <RowActionButton
                          dense
                          label="Duyệt"
                          icon="check"
                          disabled={busy || quaDai.length > 0}
                          onClick={() => decide(r.id, true)}
                        />
                        {/* GIỮ tín hiệu nguy hiểm: từ chối là quyết định NV nhận được ngay,
                            mất màu đỏ là bấm nhầm ô bên cạnh. */}
                        <RowActionButton
                          dense
                          danger
                          label="Từ chối"
                          icon="ban"
                          disabled={busy}
                          onClick={() => decide(r.id, false)}
                        />
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose}>
            Đóng
          </button>
        </footer>
      </div>
    </div>
  );
}
