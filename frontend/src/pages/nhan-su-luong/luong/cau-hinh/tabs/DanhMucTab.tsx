// Tab con Danh mục khoản thu nhập (tách từ pages/CauHinhLuongTab.tsx).
import { useCallback, useEffect, useState } from "react";
import {
  api,
  type ComponentHolders,
  type ComponentKind,
  type PayrollComponent,
} from "../../../../../api/client";
import { Button } from "../../../../../components/Button";
import { ConfirmDialog } from "../../../../../components/ConfirmDialog";
import { RowActionButton } from "../../../../../components/RowActionButton";
import { BulkAssignDialog } from "../modals/BulkAssignDialog";
import { NEW_COMPONENT } from "../shared/constants";
import { errText } from "../shared/helpers";
import type { CompDraft } from "../shared/types";

export function DanhMucTab({ token, readOnly }: { token: string; readOnly: boolean }) {
  // null = ĐANG TẢI. Khởi tạo [] sẽ hiện "chưa có khoản nào" ngay lúc còn đang fetch — báo SAI.
  const [items, setItems] = useState<PayrollComponent[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  // Form thêm/sửa dùng chung — `id: null` = thêm mới.
  const [form, setForm] = useState<{ id: number | null; draft: CompDraft } | null>(null);
  const [formBusy, setFormBusy] = useState(false);
  const [formErr, setFormErr] = useState<string | null>(null);
  const [del, setDel] = useState<PayrollComponent | null>(null);
  const [delBusy, setDelBusy] = useState(false);
  const [delErr, setDelErr] = useState<string | null>(null);
  // Danh sách NV còn giữ một khoản ĐÃ NGỪNG ÁP DỤNG. `null` = chưa mở modal; `items` rỗng =
  // mở rồi mà không còn ai. Lương vẫn trả đủ — modal này để HCNS biết còn ai phải gỡ.
  const [holders, setHolders] = useState<ComponentHolders | null>(null);
  const [holdersBusy, setHoldersBusy] = useState(false);
  const [holdersErr, setHoldersErr] = useState<string | null>(null);
  // Gán hàng loạt (chủ 28/07/2026). `bulk` = khoản đang gán; null = modal đóng.
  const [bulk, setBulk] = useState<PayrollComponent | null>(null);

  const load = useCallback(() => {
    api.luong.components
      .list(token)
      .then((r) => {
        setItems(r.items);
        setErr(null);
      })
      // GIỮ NGUYÊN `items`: gán [] khi lỗi sẽ hiện "chưa có khoản nào" — báo SAI (tải hỏng
      // chứ danh mục không rỗng). Lần đầu hỏng thì `items` vẫn null ⇒ render khối "thử lại".
      .catch((e) => setErr(errText(e)));
  }, [token]);
  useEffect(() => {
    load();
  }, [load]);

  /** Ai còn giữ khoản đã ngừng áp dụng. Gọi lúc BẤM (không tải sẵn cho cả bảng): danh sách
   *  này chỉ cần khi người dùng thật sự muốn xem, tải sẵn là N request thừa mỗi lần vào tab. */
  async function openHolders(c: PayrollComponent) {
    setHoldersBusy(true);
    setHoldersErr(null);
    setHolders({ component_id: c.id, component_name: c.name, items: [] });
    try {
      setHolders(await api.luong.components.holders(token, c.id));
    } catch (e) {
      setHoldersErr(errText(e));
    } finally {
      setHoldersBusy(false);
    }
  }

  function openBulk(c: PayrollComponent) {
    setErr(null);
    setBulk(c);
  }

  /** Báo việc VỪA làm. `sticky` cho câu quan trọng (ngừng áp dụng) — không tự tắt sau vài giây. */
  function say(msg: string, sticky = false) {
    setOk(msg);
    if (!sticky)
      window.setTimeout(() => setOk((cur) => (cur === msg ? null : cur)), 5000);
  }

  async function patch(c: PayrollComponent, body: Parameters<typeof api.luong.components.update>[2], msg: string) {
    setBusyId(c.id);
    setErr(null);
    try {
      const updated = await api.luong.components.update(token, c.id, body);
      setItems((list) => (list ?? []).map((x) => (x.id === c.id ? updated : x)));
      say(msg);
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusyId(null);
    }
  }

  async function saveForm() {
    if (!form) return;
    const name = form.draft.name.trim();
    if (!name) {
      setFormErr("Nhập tên khoản.");
      return;
    }
    setFormBusy(true);
    setFormErr(null);
    try {
      if (form.id == null) {
        // Khoản mới xuống CUỐI danh mục (không chen giữa các khoản kế toán đang quen thứ tự).
        const maxSort = (items ?? []).reduce((m, c) => Math.max(m, c.sort_order), 0);
        await api.luong.components.create(token, {
          name,
          kind: form.draft.kind,
          is_taxable: form.draft.is_taxable,
          sort_order: maxSort + 10,
        });
        say(`Đã thêm khoản “${name}”.`);
      } else {
        await api.luong.components.update(token, form.id, {
          name,
          kind: form.draft.kind,
          is_taxable: form.draft.is_taxable,
        });
        say(`Đã lưu khoản “${name}”.`);
      }
      setForm(null);
      load();
    } catch (e) {
      setFormErr(errText(e));
    } finally {
      setFormBusy(false);
    }
  }

  /** ĐỌC kết quả trả về rồi mới báo: backend có thể chỉ NGỪNG ÁP DỤNG chứ không xoá.
   *  Câu báo lấy NGUYÊN VĂN `message` của backend — tự chế lại là nói sai việc vừa làm
   *  (và làm lệch với thông điệp chủ đã duyệt). */
  async function confirmDelete() {
    if (!del) return;
    const name = del.name;
    setDelBusy(true);
    setDelErr(null);
    try {
      const res = await api.luong.components.remove(token, del.id);
      setDel(null);
      load();
      if (res.deleted) say(res.message || `Đã xoá khoản “${name}”.`);
      else if (res.deactivated)
        say(
          res.message ||
            `Khoản “${name}” đã có phát sinh dữ liệu nên chỉ chuyển sang NGỪNG SỬ DỤNG.`,
          true,
        );
      else
        say(
          res.message ||
            "Hệ thống không xoá và cũng không ngừng áp dụng khoản này. Tải lại danh mục để xem trạng thái thật.",
          true,
        );
    } catch (e) {
      setDelErr(errText(e));
    } finally {
      setDelBusy(false);
    }
  }

  /** Đã có số liệu (gán cho NV hoặc đã chạy qua kỳ lương) ⇒ backend KHÔNG xoá cứng. */
  const delUsed = del ? del.employee_count > 0 || del.period_count > 0 : false;

  const editing = form?.id != null;

  return (
    <>
      <div className="cl-card">
        <div className="cl-card__head">
          <div>
            <h3 className="cl-card__title">Danh mục khoản thu nhập</h3>
            <p className="cl-card__desc">
              <b>Bước 1</b> của quy trình 2 bước: khoản mới phải tạo ở đây
              trước. <b>Bước 2</b> — sang <b>Lương → Lương nhân viên → Sửa
              lương</b> chọn khoản này cho từng người và nhập số tiền. Ô tích
              “Chịu thuế” quyết định khoản có tính vào thu nhập chịu thuế TNCN
              hay không, và <b>chỉ khai ở đây</b>.
            </p>
          </div>
          {!readOnly && (
            <Button
              variant="ghost"
              onClick={() => {
                setFormErr(null);
                setForm({ id: null, draft: NEW_COMPONENT });
              }}
            >
              + Thêm khoản
            </Button>
          )}
        </div>

        <div className="cl-card__body">
          {err && <div className="banner banner--error">{err}</div>}
          {ok && <div className="banner banner--success">{ok}</div>}

          {items === null ? (
            err ? (
              <div className="cl-empty">
                <span className="cl-empty__title">
                  Không tải được danh mục khoản thu nhập
                </span>
                <span className="cl-empty__desc">
                  Danh mục có thể vẫn còn nguyên — chỉ là lần tải này hỏng.
                </span>
                <div className="cl-note">
                  <Button variant="ghost" onClick={load}>
                    Thử lại
                  </Button>
                </div>
              </div>
            ) : (
              <p className="cl-hint-inline">Đang tải danh mục…</p>
            )
          ) : items.length === 0 ? (
            <div className="cl-empty">
              <span className="cl-empty__title">
                Chưa có khoản nào trong danh mục
              </span>
              <span className="cl-empty__desc">
                Bấm “+ Thêm khoản” để khai khoản đầu tiên (vd Trang phục · Tiền
                ăn ca · Hỗ trợ đi lại). Chưa có khoản ở đây thì hồ sơ nhân viên
                cũng chưa chọn được gì.
              </span>
            </div>
          ) : (
            <div className="cl-table__wrap">
              <table className="cl-table">
                <thead>
                  <tr>
                    <th>Tên khoản</th>
                    <th style={{ width: 96 }}>Loại</th>
                    <th style={{ width: 132 }}>Chịu thuế</th>
                    <th className="num" style={{ width: 176 }}>
                      Đang dùng
                    </th>
                    {/* Cho CHỮ "Thao tác" thay vì ô trống chỉ có aria-label. Nút chữ đã thu về
                        icon dense (32px/nút) nên 150 → 132 vẫn đủ cho 3 nút, trả lại chỗ cho
                        cột "Tên khoản". */}
                    {!readOnly && (
                      <th className="act" style={{ width: 132 }}>
                        Thao tác
                      </th>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {items.map((c) => (
                    <tr key={c.id} className={c.is_active ? "" : "cl-dm--off"}>
                      <td>
                        <strong>{c.name}</strong>
                        {!c.is_active && (
                          <span className="rc-pill rc-pill--off cl-dm__tag">
                            Ngừng áp dụng
                          </span>
                        )}
                        {c.note && (
                          <span className="cl-cell__sub">{c.note}</span>
                        )}
                        {/* Ngừng áp dụng mà NV còn giữ ⇒ lương VẪN TRẢ khoản này. Không nói
                            ra thì tắt khoản xong không ai biết còn ai đang dính. */}
                        {!c.is_active && c.employee_count > 0 && (
                          <button
                            type="button"
                            className="cl-dm__holders"
                            onClick={() => openHolders(c)}
                          >
                            Xem {c.employee_count} người đang gán
                          </button>
                        )}
                      </td>
                      <td>
                        <span
                          className={`ns-badge ${c.kind === "tru" ? "ns-badge--danger" : "ns-badge--ok"}`}
                        >
                          {c.kind === "tru" ? "Trừ" : "Thu"}
                        </span>
                      </td>
                      <td>
                        <label className="cl-check">
                          <input
                            type="checkbox"
                            checked={c.is_taxable}
                            disabled={readOnly || busyId === c.id}
                            aria-label={`Chịu thuế — ${c.name}`}
                            onChange={(e) =>
                              patch(
                                c,
                                { is_taxable: e.target.checked },
                                e.target.checked
                                  ? `“${c.name}” giờ TÍNH vào thu nhập chịu thuế TNCN.`
                                  : `“${c.name}” giờ được MIỄN thuế TNCN.`,
                              )
                            }
                          />
                          <span>{c.is_taxable ? "Chịu thuế" : "Miễn thuế"}</span>
                        </label>
                      </td>
                      {/* "N nhân viên · M kỳ lương" — HR hình dung được mức độ ảnh hưởng;
                          "N dòng lương" của bản cũ nói 100 dòng cùng một tháng thành 100. */}
                      <td className="num">
                        {c.employee_count > 0 || c.period_count > 0 ? (
                          <>
                            {c.employee_count} nhân viên 
                            {/* · {c.period_count} kỳ
                            lương */}
                            <span className="cl-cell__sub">
                              không xoá cứng được
                            </span>
                          </>
                        ) : (
                          <span className="cl-muted">chưa dùng</span>
                        )}
                      </td>
                      {/* Nút chữ trên dòng → `RowActionButton` dense: icon + tooltip, nhãn cũ
                          thành aria-label nên không mất nghĩa cho người đọc màn hình. */}
                      {!readOnly && (
                        <td className="act">
                          <RowActionButton
                            dense
                            label="Sửa khoản"
                            icon="pencil"
                            disabled={busyId === c.id}
                            onClick={() => {
                              setFormErr(null);
                              setForm({
                                id: c.id,
                                draft: {
                                  name: c.name,
                                  kind: c.kind,
                                  is_taxable: c.is_taxable,
                                },
                              });
                            }}
                          />
                          {/* Gán hàng loạt (chủ 28/07/2026): tạo khoản xong mà phải mở hồ sơ
                              từng người thì nhà máy 40–100 người không dùng được. Khoản đã
                              ngừng áp dụng thì không gán mới (luật sẵn có ở backend). */}
                          {c.is_active && (
                            <RowActionButton
                              dense
                              label="Gán cho nhân viên"
                              icon="users"
                              disabled={busyId === c.id}
                              onClick={() => openBulk(c)}
                            />
                          )}
                          {c.is_active ? (
                            <RowActionButton
                              dense
                              danger
                              label={`Xoá khoản ${c.name}`}
                              icon="trash"
                              disabled={busyId === c.id}
                              onClick={() => {
                                setDelErr(null);
                                setDel(c);
                              }}
                            />
                          ) : (
                            <RowActionButton
                              dense
                              label={`Bật lại khoản ${c.name}`}
                              icon="rotateCcw"
                              disabled={busyId === c.id}
                              onClick={() =>
                                patch(
                                  c,
                                  { is_active: true },
                                  `Đã bật lại khoản “${c.name}”.`,
                                )
                              }
                            />
                          )}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <p className="cl-hint-inline">
            Bỏ tích “Chịu thuế” = khoản đó không tính vào thu nhập chịu thuế
            TNCN. Đổi cờ chỉ ảnh hưởng kỳ tính từ đó về sau; kỳ đã chốt giữ
            nguyên số cũ.
          </p>
          <p className="cl-hint-inline">
            Khoản đã có số liệu thì KHÔNG xoá cứng được — hệ thống chỉ chuyển
            sang <b>Ngừng áp dụng</b> để phiếu lương các kỳ cũ vẫn còn đủ dòng.
            Người đang được gán khoản đó <b>vẫn được trả tiền như cũ</b>: bấm
            “Xem N người đang gán” để gỡ từng người ở{" "}
            <b>Lương → Lương nhân viên</b>.
          </p>
          <p className="cl-hint-inline">
            Thưởng nóng / khoản chỉ có <b>một tháng</b> thì đừng tạo danh mục
            mới: dùng sẵn <b>“Thu nhập khác (chịu thuế)”</b> hoặc{" "}
            <b>“(miễn thuế)”</b>, khai thẳng ở <b>Bảng lương → Sửa dòng → Khoản
            phát sinh tháng này</b> kèm ghi chú.
          </p>
        </div>
      </div>

      <ConfirmDialog
        open={form !== null}
        title={editing ? "Sửa khoản thu nhập" : "Thêm khoản thu nhập"}
        confirmLabel={editing ? "Lưu khoản" : "Thêm khoản"}
        busy={formBusy}
        error={formErr}
        onCancel={() => {
          if (!formBusy) setForm(null);
        }}
        onConfirm={saveForm}
      >
        {form && (
          <div className="rc-grid">
            <label className="rc-field rc-field--full">
              <span className="rc-field__label">Tên khoản</span>
              <div className="rc-input-wrapper">
                <input
                  className="rc-input"
                  autoFocus
                  maxLength={120}
                  placeholder="vd Trang phục · Tiền ăn ca · Hỗ trợ đi lại"
                  value={form.draft.name}
                  onChange={(e) =>
                    setForm((f) =>
                      f ? { ...f, draft: { ...f.draft, name: e.target.value } } : f,
                    )
                  }
                />
              </div>
              <span className="rc-field__hint">
                Tên này hiện nguyên văn trên phiếu lương của nhân viên.
              </span>
            </label>
            <label className="rc-field">
              <span className="rc-field__label">Loại khoản</span>
              <div className="rc-input-wrapper">
                <select
                  className="rc-input"
                  value={form.draft.kind}
                  onChange={(e) =>
                    setForm((f) =>
                      f
                        ? {
                            ...f,
                            draft: {
                              ...f.draft,
                              kind: e.target.value as ComponentKind,
                            },
                          }
                        : f,
                    )
                  }
                >
                  <option value="thu">Thu — cộng vào tổng lương</option>
                  <option value="tru">Trừ — khấu trừ vào thực nhận</option>
                </select>
              </div>
            </label>
            <label className="rc-field rc-field--check">
              <span className="rc-field__label">Chịu thuế TNCN</span>
              <input
                type="checkbox"
                className="cl-check__box"
                checked={form.draft.is_taxable}
                onChange={(e) =>
                  setForm((f) =>
                    f
                      ? {
                          ...f,
                          draft: { ...f.draft, is_taxable: e.target.checked },
                        }
                      : f,
                  )
                }
              />
            </label>
            <p className="rc-field__hint rc-field--full">
              Bỏ tích nếu khoản này được MIỄN thuế (trang phục · tiền ăn ca ·
              trợ cấp tiền nhà · hỗ trợ đi lại…). Tích = cộng vào thu nhập chịu
              thuế TNCN.
            </p>
          </div>
        )}
      </ConfirmDialog>

      <ConfirmDialog
        open={del !== null}
        danger
        title={`Xoá khoản “${del?.name ?? ""}”?`}
        confirmLabel={delUsed ? "Ngừng áp dụng khoản này" : "Xoá khoản"}
        busy={delBusy}
        error={delErr}
        onCancel={() => {
          if (!delBusy) setDel(null);
        }}
        onConfirm={confirmDelete}
      >
        {del &&
          (delUsed ? (
            <p className="cdlg__msg">
              Khoản này đã có phát sinh dữ liệu (gán cho{" "}
              <b>{del.employee_count} nhân viên</b>, đã chốt{" "}
              <b>{del.period_count} kỳ lương</b>) nên KHÔNG xoá vĩnh viễn được.
              Hệ thống sẽ chuyển sang <b>Ngừng áp dụng</b>: khoản biến mất khỏi
              danh sách chọn khi gán mới, còn phiếu lương các kỳ cũ giữ nguyên
              số đã trả.
              {del.employee_count > 0 && (
                <>
                  {" "}
                  Người đang được gán <b>vẫn tiếp tục được trả</b> khoản này cho
                  tới khi bạn gỡ ở <b>Lương → Lương nhân viên</b>.
                </>
              )}
            </p>
          ) : (
            <p className="cdlg__msg">
              Khoản này chưa gán cho ai và chưa qua kỳ lương nào nên sẽ được xoá
              hẳn khỏi danh mục.
            </p>
          ))}
      </ConfirmDialog>

      {/* Ai còn giữ khoản đã ngừng áp dụng — chỉ để XEM rồi đi gỡ, không thao tác tại chỗ:
          gỡ khoản là sửa TIỀN LƯƠNG của người ta, phải làm ở đúng màn hồ sơ lương. */}
      <ConfirmDialog
        open={holders !== null}
        hideConfirm
        wide
        title={`Đang gán khoản “${holders?.component_name ?? ""}”`}
        cancelLabel="Đóng"
        error={holdersErr}
        onConfirm={() => setHolders(null)}
        onCancel={() => setHolders(null)}
      >
        {holdersBusy ? (
          <p className="cdlg__msg">Đang tải danh sách…</p>
        ) : holders && holders.items.length === 0 ? (
          <p className="cdlg__msg">
            Không còn ai được gán khoản này.
          </p>
        ) : (
          <>
            <p className="cdlg__msg">
              <b>{holders?.items.length ?? 0} người</b> vẫn đang được trả khoản
              này mỗi tháng dù khoản đã ngừng áp dụng. Gỡ từng người ở{" "}
              <b>Lương → Lương nhân viên → Sửa lương</b>.
            </p>
            <ul className="cl-holders">
              {holders?.items.map((h) => (
                <li key={h.employee_id}>
                  <span className="cl-holders__code">{h.code}</span>
                  {h.full_name}
                </li>
              ))}
            </ul>
          </>
        )}
      </ConfirmDialog>

      {bulk && (
        <BulkAssignDialog
          token={token}
          component={bulk}
          onClose={() => setBulk(null)}
          onDone={(msg) => {
            setBulk(null);
            load();          // đếm "N nhân viên" trên bảng phải nhảy theo
            say(msg, true);
          }}
        />
      )}
    </>
  );
}

// --- Gán hàng loạt một khoản cho nhiều NV (chủ 28/07/2026) ------------------
// Trước đây tạo khoản xong phải mở hồ sơ TỪNG người để thêm — nhà máy 40–100 người thì không
// dùng được. Chỗ nguy hiểm duy nhất ở màn này là ô "Ghi đè": bật lên là xoá mức riêng đã khai
// cho từng người và KHÔNG hoàn tác được, nên nó mặc định TẮT và khi bật phải cho xem trước
// đúng ai bị đổi từ bao nhiêu sang bao nhiêu.

/** Lấy HẾT nhân viên, phân trang cho tới khi đủ `total`.
 *
 * `GET /api/employees` chặn `size ≤ 200` (Query `le=200`) — gửi 500 là **422**, và vì gọi trong
 * `Promise.all` nên hỏng một cái là danh sách treo mãi ở "Đang tải…". Kẹp về 200 thì hết lỗi
 * nhưng ÂM THẦM SÓT người khi nhà máy vượt 200 — gán hàng loạt mà thiếu người thì tệ hơn là báo
 * lỗi. Nên lặp cho đủ. */
