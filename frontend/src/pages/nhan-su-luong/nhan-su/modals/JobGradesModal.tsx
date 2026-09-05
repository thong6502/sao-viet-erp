// Danh mục BẬC TAY NGHỀ — khai HỆ SỐ SẢN LƯỢNG cho từng bậc.
//
// Vì sao nằm ở Hồ sơ nhân sự chứ không ở "Cấu hình danh mục": bậc thuộc module `nhan_su` (xem
// `routers/employees.py` — "HCNS quản hồ sơ mới là người cần thêm bậc, mà họ thường không có
// quyền lương"). Đặt ở nhóm danh mục sẽ phải đẻ thêm một ô quyền `dm_*` mà đúng người cần lại
// không có.
//
// Hệ số dùng ở ĐÂU: chia một mẻ khoán cho những người đã làm mẻ đó — phần mỗi người tỉ lệ với
// (phút chấm công hợp lệ × hệ số bậc). Nó KHÔNG cộng vào lương thời gian.
// ⚠ Bỏ trống KHÔNG phải "coi như 1.0": `services/san_xuat/phan_bo.py` chặn chốt phân bổ và báo
// "Có người chưa gán hệ số bậc (§8)" — tiền mẻ treo. Nên ô này không cho lưu trắng.
import { useCallback, useEffect, useState } from "react";
import { api, type JobGrade } from "../../../../api/client";
import { EmptyState } from "../../../../components/EmptyState";
import { Button } from "../../../../components/Button";
import { errMsg } from "../shared/helpers";

/** Số hiện trong ô nhập. Dùng dấu chấm thập phân cho khớp `<input type="number">`. */
function nhap(v: number | null): string {
  return v === null || v === undefined ? "" : String(v);
}

export function JobGradesModal({
  token,
  canEdit,
  onClose,
  onSaved,
}: {
  token: string;
  canEdit: boolean;
  onClose: () => void;
  onSaved?: () => void;
}) {
  const [items, setItems] = useState<JobGrade[] | null>(null);
  const [draft, setDraft] = useState<Record<number, string>>({});
  const [listError, setListError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    setListError(null);
    // `active_only: false` — bậc đã tắt vẫn còn người đang đeo, mẻ của họ vẫn cần hệ số.
    api.employees
      .jobGrades(token, { active_only: false })
      .then((r) => {
        setItems(r.items);
        setDraft(
          Object.fromEntries(r.items.map((g) => [g.id, nhap(g.output_coefficient)])),
        );
      })
      .catch((e) => {
        setItems([]);
        setListError(errMsg(e));
      });
  }, [token]);
  useEffect(() => {
    load();
  }, [load]);

  function set(id: number, v: string) {
    setSaved(false);
    setDraft((d) => ({ ...d, [id]: v }));
  }

  /** Câu lỗi của MỘT dòng, hoặc null nếu hợp lệ. Hiện ngay dưới ô, không đợi bấm Lưu. */
  function loiDong(v: string): string | null {
    const s = v.trim();
    if (s === "") return "Chưa khai — mẻ khoán có người bậc này sẽ không chốt phân bổ được.";
    const n = Number(s.replace(",", "."));
    if (!Number.isFinite(n)) return "Phải là một con số.";
    if (n <= 0) return "Phải lớn hơn 0 — hệ số 0 nghĩa là người bậc này không được chia đồng nào.";
    if (n > 999.999) return "Tối đa 999,999.";
    return null;
  }

  const coLoi = items?.some((g) => loiDong(draft[g.id] ?? "") !== null) ?? false;
  const doiGi =
    items?.filter((g) => {
      const n = Number((draft[g.id] ?? "").trim().replace(",", "."));
      return Number.isFinite(n) && n !== g.output_coefficient;
    }) ?? [];

  async function luu() {
    if (coLoi || doiGi.length === 0) return;
    setBusy(true);
    setSaveError(null);
    try {
      // Gửi TỪNG bậc đã đổi. Chỉ gửi `output_coefficient` — backend `exclude_unset` nên tên,
      // thứ tự, ghi chú của bậc không bị đụng tới.
      for (const g of doiGi) {
        const n = Number((draft[g.id] ?? "").trim().replace(",", "."));
        await api.employees.updateJobGrade(token, g.id, { output_coefficient: n });
      }
      setSaved(true);
      load();
      onSaved?.();
    } catch (e) {
      setSaveError(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ns-modal" role="dialog" aria-modal="true" aria-labelledby="nsbac-title">
      <div className="ns-modal__box ns-modal__box--wide">
        <header className="ns-modal__head">
          <h2 id="nsbac-title">Bậc tay nghề · hệ số chia sản lượng</h2>
          <button className="ns-modal__x" onClick={onClose} aria-label="Đóng">
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          <p className="nsbac__intro">
            Khi một mẻ khoán làm xong, tiền của mẻ chia cho những người đã làm mẻ đó theo{" "}
            <b>số phút chấm công hợp lệ × hệ số bậc</b>. Đây là chỗ duy nhất nói thợ cứng tay ăn
            hơn thợ mới bao nhiêu — khai một lần, cả xưởng theo. Hệ số <b>không</b> cộng vào lương
            theo thời gian.
          </p>

          {saveError && (
            <div className="banner banner--error" role="alert">
              {saveError}
            </div>
          )}
          {saved && !saveError && (
            <div className="banner banner--success" role="status">
              Đã lưu. Hệ số mới áp cho các mẻ mở TỪ ĐÂY — mẻ đang chạy dở đã chụp hệ số cũ lúc
              người thợ vào làm, không đổi theo.
            </div>
          )}

          {!items && !listError && <EmptyState trangThai="dang-tai" inline />}
          {listError && (
            <EmptyState trangThai="loi" loi={listError} onThuLai={load} inline />
          )}

          {!listError && !!items?.length && (
            <table className="ns-table-records nsbac__table">
              <thead>
                <tr>
                  <th>Bậc</th>
                  <th className="nsbac__th-num">Hệ số sản lượng</th>
                </tr>
              </thead>
              <tbody>
                {items.map((g) => {
                  const loi = loiDong(draft[g.id] ?? "");
                  return (
                    <tr key={g.id}>
                      <td>
                        <span className="nsbac__ten">{g.name}</span>
                        {!g.is_active && (
                          <span className="nsbac__tat">đã tắt</span>
                        )}
                      </td>
                      <td className="nsbac__th-num">
                        <input
                          type="number"
                          min={0.001}
                          max={999.999}
                          step={0.05}
                          className={`nsbac__o${loi ? " nsbac__o--loi" : ""}`}
                          value={draft[g.id] ?? ""}
                          disabled={!canEdit || busy}
                          onChange={(e) => set(g.id, e.target.value)}
                          aria-label={`Hệ số sản lượng của bậc ${g.name}`}
                        />
                        {loi && <p className="nsbac__loi">{loi}</p>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}

          <p className="nsbac__vd">
            Ví dụ: một mẻ khoán 1.500.000đ, 4 người cùng làm 8 tiếng. Thợ vững để 1,15 và ba Thợ
            thường để 1,0 ⇒ Thợ vững nhận 415.663đ, mỗi Thợ thường 361.446đ. Để cả bốn cùng 1,0
            thì bốn người bằng nhau 375.000đ.
          </p>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Đóng
          </button>
          {canEdit && (
            <Button
              type="button"
              variant="accent"
              disabled={busy || coLoi || doiGi.length === 0}
              onClick={luu}
            >
              {busy ? "Đang lưu…" : `Lưu hệ số${doiGi.length ? ` (${doiGi.length})` : ""}`}
            </Button>
          )}
        </footer>
      </div>
    </div>
  );
}
