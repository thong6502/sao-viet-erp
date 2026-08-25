// Gán khoản thu nhập hàng loạt cho nhân viên (tách từ pages/CauHinhLuongTab.tsx).
import { useEffect, useState } from "react";
import {
  api,
  type Department,
  type EmployeeRow,
  type PayrollComponent,
} from "../../../../../api/client";
import { ConfirmDialog } from "../../../../../components/ConfirmDialog";
import { money } from "../../../../../utils/format";
import { errText, fetchAllEmployees } from "../shared/helpers";

export function BulkAssignDialog({
  token,
  component,
  onClose,
  onDone,
}: {
  token: string;
  component: PayrollComponent;
  onClose: () => void;
  onDone: (msg: string) => void;
}) {
  const [emps, setEmps] = useState<EmployeeRow[] | null>(null);
  const [held, setHeld] = useState<Map<number, number> | null>(null);
  const [mode, setMode] = useState<"all" | "pick">("all");
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [q, setQ] = useState("");
  const [dept, setDept] = useState("");   // "" = mọi phòng ban/tổ; khác rỗng = department_id
  const [depts, setDepts] = useState<Department[]>([]);
  const [amount, setAmount] = useState(0);
  const [note, setNote] = useState("");
  const [overwrite, setOverwrite] = useState(false);   // ⚠️ mặc định TẮT — xem ghi chú khối trên
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    Promise.all([
      fetchAllEmployees(token),
      api.luong.components.employeeAmounts(token, component.id),
      // Lấy TỪ DANH MỤC phòng ban, KHÔNG suy từ nhân viên đã tải: suy từ nhân viên thì phòng
      // nào chưa có ai sẽ biến mất khỏi bộ lọc — người dùng biết phòng đó tồn tại mà không
      // thấy đâu, tưởng hệ thống mất dữ liệu.
      api.rbac.departments(token),
    ])
      .then(([all, amounts, dsPhong]) => {
        if (!alive) return;
        // Chỉ NV ĐANG LÀM VIỆC — rải phụ cấp cho người đã nghỉ là đẻ tiền cho hồ sơ chết.
        // "Hết thử việc chờ xác nhận" vẫn đang đi làm ⇒ vẫn phải chọn được ở đây.
        setEmps(all.filter(
          (e) => e.status === "active" || e.status === "probation"
            || e.status === "probation_ended"));
        setHeld(new Map(amounts.items.map((x) => [x.employee_id, x.amount])));
        setDepts(dsPhong);
        setErr(null);
      })
      .catch((e) => alive && setErr(errText(e)));
    return () => {
      alive = false;
    };
  }, [token, component.id]);

  // Xổ theo CÂY: phòng cha rồi tới tổ con, tổ con thụt vào. Danh sách phẳng theo bảng chữ cái
  // làm mất quan hệ "tổ này thuộc phòng nào" — nhà máy có nhiều tổ cùng tên kiểu "Tổ 1".
  const deptOptions: { id: number; label: string }[] = [];
  const soNguoi = new Map<number, number>();
  for (const e of emps ?? []) {
    if (e.department_id != null) soNguoi.set(e.department_id, (soNguoi.get(e.department_id) ?? 0) + 1);
  }
  const duyet = (parentId: number | null, sau: number) => {
    for (const d of depts.filter((x) => (x.parent_id ?? null) === parentId)) {
      const n = soNguoi.get(d.id) ?? 0;
      deptOptions.push({
        id: d.id,
        // Số người hiện ngay trên nhãn: phòng "(0)" thì biết trước là lọc vào sẽ trống, khỏi
        // bấm rồi mới ngơ ngác.
        label: `${"  ".repeat(sau)}${sau ? "└ " : ""}${d.name} (${n})`,
      });
      duyet(d.id, sau + 1);
    }
  };
  duyet(null, 0);

  const shown = (emps ?? []).filter((e) => {
    const s = q.trim().toLowerCase();
    const hopTen =
      !s || e.full_name.toLowerCase().includes(s) || (e.code ?? "").toLowerCase().includes(s);
    return hopTen && (!dept || e.department_id === Number(dept));
  });
  // Người đã có mức riêng mà chưa xin ghi đè thì KHOÁ ⇒ "Chọn tất cả" cũng phải bỏ qua họ,
  // nếu không nút này lại đẩy vào những id mà backend sẽ bỏ qua — số trên màn nói dối.
  const chonDuoc = shown.filter((e) => overwrite || !held?.has(e.id));
  const targets = mode === "all" ? (emps ?? []) : (emps ?? []).filter((e) => picked.has(e.id));
  const willOverwrite = targets.filter((e) => held?.has(e.id)).length;
  const willAdd = targets.length - willOverwrite;

  async function save() {
    setBusy(true);
    setErr(null);
    try {
      const res = await api.luong.components.bulkAssign(token, component.id, {
        amount,
        note: note.trim() || null,
        all_active: mode === "all",
        employee_ids: mode === "all" ? [] : [...picked],
        overwrite,
      });
      // Câu báo nói ĐÚNG việc vừa xảy ra: thêm mới và ghi đè là hai chuyện khác nhau.
      const parts = [`Đã thêm mới ${res.assigned} người`];
      if (res.overwritten) parts.push(`ghi đè ${res.overwritten} người`);
      if (res.skipped_existing) parts.push(`bỏ qua ${res.skipped_existing} người đã có mức riêng`);
      onDone(`“${component.name}”: ${parts.join(" · ")}.`);
    } catch (e) {
      setErr(errText(e));
      setBusy(false);
    }
  }

  return (
    <ConfirmDialog
      open
      wide
      title={`Gán “${component.name}” cho nhân viên`}
      confirmLabel={busy ? "Đang lưu…" : "Lưu"}
      cancelLabel="Hủy"
      error={err}
      confirmDisabled={busy || targets.length === 0 || amount < 0}
      onConfirm={() => void save()}
      onCancel={onClose}
    >
      <div className="cl-bulk">
        <div className="cl-bulk__modes">
          <label className="cl-check">
            <input type="radio" checked={mode === "all"} onChange={() => setMode("all")} />
            <span>Tất cả nhân viên đang làm việc{emps ? ` (${emps.length})` : ""}</span>
          </label>
          <label className="cl-check">
            <input type="radio" checked={mode === "pick"} onChange={() => setMode("pick")} />
            <span>Chọn cụ thể{mode === "pick" ? ` (${picked.size})` : ""}</span>
          </label>
        </div>

        {mode === "pick" && (
          <>
            {/* Lọc + chọn cả nhóm: "lọc tổ Bế → Chọn tất cả" là 2 cú bấm cho cả tổ, thay vì
                tick từng người. Cố ý KHÔNG phân trang — danh sách tick chọn mà chia trang thì
                tick xong sang trang khác là không còn nhìn thấy mình đã chọn ai. */}
            <div className="cl-bulk__tools">
              <input
                className="cc-input-text"
                placeholder="Tìm theo tên hoặc mã nhân viên…"
                value={q}
                onChange={(e) => setQ(e.target.value)}
              />
              <select
                value={dept}
                onChange={(e) => setDept(e.target.value)}
                aria-label="Lọc theo phòng ban / tổ"
              >
                <option value="">Tất cả phòng ban / tổ</option>
                {deptOptions.map((d) => (
                  <option key={d.id} value={String(d.id)}>
                    {d.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="cl-bulk__bar">
              <span>
                Đang hiện <b>{shown.length}</b> · đã chọn <b>{picked.size}</b>
              </span>
              <button
                type="button"
                className="btn btn--ghost"
                disabled={chonDuoc.length === 0}
                onClick={() => setPicked((s) => new Set([...s, ...chonDuoc.map((e) => e.id)]))}
              >
                Chọn tất cả đang hiện ({chonDuoc.length})
              </button>
              <button
                type="button"
                className="btn btn--ghost"
                disabled={picked.size === 0}
                onClick={() => setPicked(new Set())}
              >
                Bỏ chọn hết
              </button>
            </div>
            <div className="cl-bulk__list">
              {emps === null ? (
                <p className="cl-hint-inline">Đang tải danh sách nhân viên…</p>
              ) : shown.length === 0 ? (
                <p className="cl-hint-inline">Không tìm thấy ai khớp.</p>
              ) : (
                shown.map((e) => {
                  const cu = held?.get(e.id);
                  // Đã có mức riêng: KHOÁ khi chưa xin ghi đè — nhìn là biết ngay sẽ bị bỏ qua.
                  const locked = cu != null && !overwrite;
                  return (
                    <label
                      key={e.id}
                      className={`cl-bulk__row${locked ? " cl-bulk__row--locked" : ""}`}
                    >
                      <input
                        type="checkbox"
                        checked={picked.has(e.id)}
                        disabled={locked}
                        onChange={(ev) =>
                          setPicked((s) => {
                            const n = new Set(s);
                            if (ev.target.checked) n.add(e.id);
                            else n.delete(e.id);
                            return n;
                          })
                        }
                      />
                      <span className="cl-bulk__name">
                        <b>{e.code}</b> {e.full_name}
                      </span>
                      {cu != null && (
                        <span className={overwrite ? "cl-bulk__over" : "cl-bulk__has"}>
                          {overwrite
                            /* `money()` đã kèm " đ" — đừng nối thêm `đ`. */
                            ? `${money(cu)} → ${money(amount)}`
                            : `đã có ${money(cu)} — bỏ qua`}
                        </span>
                      )}
                    </label>
                  );
                })
              )}
            </div>
          </>
        )}

        <div className="ns-grid">
          <label className="ns-field">
            <span className="ns-field__label">Mức tiền chung *</span>
            <input
              type="number"
              min={0}
              step={50000}
              value={amount}
              onChange={(e) => setAmount(Number(e.target.value))}
            />
          </label>
          <label className="ns-field">
            <span className="ns-field__label">Ghi chú (dùng chung cả lô)</span>
            <input
              type="text"
              maxLength={255}
              placeholder="vd: Áp dụng từ tháng 8"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
        </div>

        <label className="cl-check cl-bulk__ow">
          <input
            type="checkbox"
            checked={overwrite}
            onChange={(e) => setOverwrite(e.target.checked)}
          />
          <span>
            Ghi đè mức riêng đã có
            <span className="cl-cell__sub">
              Tắt: giữ nguyên mức riêng của người đã có. Bật: đổi hết về mức chung ở trên.
            </span>
          </span>
        </label>

        {overwrite && willOverwrite > 0 && (
          <div className="banner banner--warn">
            ⚠ Sẽ ghi đè mức riêng của <b>{willOverwrite} người</b>. Thao tác này{" "}
            <b>không hoàn tác được</b>.
          </div>
        )}
        <p className="cl-hint-inline">
          Sẽ thêm mới cho <b>{willAdd}</b> người
          {willOverwrite > 0 && !overwrite && <> · bỏ qua <b>{willOverwrite}</b> người đã có mức riêng</>}
          {willOverwrite > 0 && overwrite && <> · ghi đè <b>{willOverwrite}</b> người</>}.
        </p>
      </div>
    </ConfirmDialog>
  );
}
