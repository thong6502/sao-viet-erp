// Tab Tài khoản & Quyền của hồ sơ nhân sự (tách từ pages/NhanSuPage.tsx).
import { useCallback, useEffect, useState } from "react";
import {
  api,
  type AuditRow,
  type EmployeeDetail,
  type EmployeeMeta,
  type Session,
  type UserRow,
} from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { useCan } from "../../../../auth/permissions";
import { fmtDate, fmtDateTime } from "../../../../utils/format";
import {
  Activity,
  ChevronDown,
  Hash,
  Key,
  Lock,
  Shield,
  User,
} from "lucide-react";
import { deviceLabel, errMsg, genPassword } from "../shared/helpers";
import { Field } from "../components/form-fields";
import { InfoCard, InfoField } from "../components/info-display";

const ACTIVITY_LIMIT = 8;

/** Tab "Tài khoản & Quyền" — gộp từ màn Người dùng cũ (đã bỏ). Mọi tài khoản đều thuộc một
 * hồ sơ, nên đây là nơi DUY NHẤT cấp/quản tài khoản đăng nhập của nhân viên. */
export function AccountTab({
  token,
  emp,
  meta,
  onChanged,
}: {
  token: string;
  emp: EmployeeDetail;
  meta: EmployeeMeta | null;
  onChanged: () => void;
}) {
  const can = useCan();
  const canCreate = can("nhan_su", "update");
  // Bốn ô quản trị tài khoản dời từ khoá `nguoi_dung` sang `nhan_su` 24/09/2026 (mg `0331`) —
  // tên thao tác giữ nguyên nên chỉ đổi khoá màn.
  const canAssignRole = can("nhan_su", "assign_role");
  const canReset = can("nhan_su", "reset_password");
  const canLock = can("nhan_su", "lock");
  const canRevoke = can("nhan_su", "revoke_sessions");

  const [row, setRow] = useState<UserRow | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activity, setActivity] = useState<AuditRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tempPw, setTempPw] = useState<string | null>(null);
  // form tạo tài khoản (khi hồ sơ chưa có)
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState(() => genPassword());
  const [roleId, setRoleId] = useState<number | "">("");

  const uid = emp.user_id;
  // Ba nguồn tải RIÊNG: mỗi thao tác chỉ tải lại phần nó đổi (đổi vai trò không đụng phiên).
  // Trước đây mỗi lần bấm là kéo lại cả danh sách tài khoản toàn hệ thống + phiên + nhật ký.
  const loadRow = useCallback(() => {
    if (uid == null) return;
    api.rbac
      .user(token, uid)
      .then(setRow)
      .catch(() => setRow(null));
  }, [token, uid]);
  const loadSessions = useCallback(() => {
    if (uid == null) return;
    api.rbac
      .userSessions(token, uid)
      .then(setSessions)
      .catch(() => setSessions([]));
  }, [token, uid]);
  const loadActivity = useCallback(() => {
    if (uid == null) return;
    api.rbac
      .userActivity(token, uid, ACTIVITY_LIMIT)
      .then(setActivity)
      .catch(() => setActivity([]));
  }, [token, uid]);
  useEffect(() => {
    if (uid == null) {
      setRow(null);
      setSessions([]);
      setActivity([]);
      return;
    }
    loadRow();
    loadSessions();
    loadActivity();
  }, [uid, loadRow, loadSessions, loadActivity]);

  const roleOpts = (meta?.roles ?? []).filter(
    (r) => r.department_id === emp.department_id,
  );

  /** `after`: tải lại đúng phần vừa đổi. `listChanged`: danh sách nhân sự có cột phản ánh thao
   * này (tài khoản, vai trò) thì mới báo trang cha tải lại. */
  async function run(
    fn: () => Promise<unknown>,
    {
      after = [],
      listChanged = false,
    }: { after?: (() => void)[]; listChanged?: boolean } = {},
  ) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      after.forEach((f) => f());
      if (listChanged) onChanged();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  // --- Chưa có tài khoản → cấp tài khoản ---
  if (uid == null) {
    return (
      <div>
        {error && <div className="banner banner--error">{error}</div>}
        <InfoCard title="Chưa có tài khoản đăng nhập" icon={Key}>
          <p className="ns-info-field__label" style={{ gridColumn: "1 / -1" }}>
            Nhân viên chưa đăng nhập được vào hệ thống. Công nhân xưởng có thể
            không cần tài khoản.
          </p>
        </InfoCard>
        {canCreate && (
          <div className="ns-grid">
            <Field label="Tên đăng nhập *">
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="vd nguyenvana"
              />
            </Field>
            <Field label="Mật khẩu ban đầu *">
              <input
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
            <Field label="Vai trò">
              <select
                value={roleId}
                onChange={(e) =>
                  setRoleId(e.target.value ? Number(e.target.value) : "")
                }
              >
                <option value="">
                  — chưa gán (đăng nhập nhưng chưa thấy gì) —
                </option>
                {roleOpts.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </select>
            </Field>
          </div>
        )}
        {canCreate && (
          <div className="ns2-editfoot">
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => setPassword(genPassword())}
              disabled={busy}
            >
              Tạo mật khẩu khác
            </button>
            <Button
              type="button"
              variant="accent"
              disabled={busy || !username.trim() || password.length < 6}
              onClick={() =>
                run(
                  async () => {
                    await api.employees.createAccount(token, emp.id, {
                      username: username.trim(),
                      password,
                      role_id: roleId === "" ? null : roleId,
                    });
                    setTempPw(password);
                  },
                  { listChanged: true },
                )
              }
            >
              {busy ? "Đang tạo…" : "Cấp tài khoản"}
            </Button>
          </div>
        )}
        {tempPw && (
          <div className="banner banner--ok">
            Đã cấp tài khoản. Mật khẩu ban đầu: <strong>{tempPw}</strong> — bàn
            giao cho nhân viên rồi đổi khi đăng nhập lần đầu.
          </div>
        )}
      </div>
    );
  }

  // --- Đã có tài khoản ---
  const locked = row !== null && !row.is_active;
  // Mỗi lần đăng nhập mà không bấm Đăng xuất để lại một phiên sống 7 ngày, nên một người có thể
  // có hàng trăm phiên chỉ từ vài trình duyệt. Gom theo thiết bị: phiên đã về mới-nhất-trước nên
  // nhóm đầu tiên là thiết bị vừa đăng nhập, mốc giữ lại là lần đăng nhập mới nhất của nhóm.
  const sessionGroups: { label: string; count: number; latest: string }[] = [];
  for (const s of sessions) {
    const label = deviceLabel(s.user_agent);
    const g = sessionGroups.find((x) => x.label === label);
    if (g) g.count += 1;
    else sessionGroups.push({ label, count: 1, latest: s.created_at });
  }
  return (
    <div>
      {error && <div className="banner banner--error">{error}</div>}
      {tempPw && (
        <div className="banner banner--ok">
          Mật khẩu tạm: <strong>{tempPw}</strong> — mọi phiên đã bị thu hồi, bàn
          giao cho nhân viên.
        </div>
      )}
      <div className="ns-info-sections">
        <InfoCard title="Tài khoản" icon={Key}>
          <InfoField
            label="Tên đăng nhập"
            value={row?.username ?? emp.account_username}
            icon={User}
          />
          <InfoField
            label="Mã tài khoản"
            value={row?.code ?? null}
            icon={Hash}
          />
          <InfoField
            label="Trạng thái"
            value={locked ? "Đã khóa" : "Hoạt động"}
            icon={Lock}
          />
        </InfoCard>
        <InfoCard title="Vai trò" icon={Shield}>
          {canAssignRole ? (
            <div className="ns-info-field" style={{ gridColumn: "1 / -1" }}>
              <div className="ns-info-field__content" style={{ width: "100%" }}>
                <span className="ns-info-field__label">
                  Vai trò (theo phòng của hồ sơ)
                </span>
                <div className="ns-info-select-wrapper">
                  <select
                    value={row?.role_id ?? ""}
                    disabled={busy}
                    onChange={(e) => {
                      const v = e.target.value ? Number(e.target.value) : null;
                      run(() => api.rbac.assignUserRole(token, uid, v), {
                        after: [loadRow, loadActivity],
                        listChanged: true,
                      });
                    }}
                  >
                    <option value="">— chưa gán —</option>
                    {roleOpts.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.name}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="ns-info-select-chevron" size={14} />
                </div>
              </div>
            </div>
          ) : (
            <InfoField label="Vai trò" value={row?.role_name} icon={Shield} />
          )}
        </InfoCard>
      </div>

      <InfoCard title="Bảo mật" icon={Lock}>
        <div className="ns-detail__shortcuts" style={{ gridColumn: "1 / -1" }}>
          {canReset && (
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              disabled={busy}
              onClick={() =>
                run(
                  async () => {
                    const r = await api.rbac.resetUserPassword(token, uid);
                    setTempPw(r.temporary_password);
                  },
                  { after: [loadSessions, loadActivity] },
                )
              }
            >
              <Key size={12} /> Đặt lại mật khẩu
            </button>
          )}
          {canRevoke && (
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              disabled={busy}
              onClick={() =>
                run(() => api.rbac.revokeUserSessions(token, uid), {
                  after: [loadSessions, loadActivity],
                })
              }
            >
              <Lock size={12} /> Thu hồi mọi phiên
            </button>
          )}
          {canLock && (
            <button
              type="button"
              className={`btn btn--sm ${locked ? "btn--primary" : "btn--ghost ns-btn--danger"}`}
              disabled={busy}
              onClick={() =>
                run(() => api.rbac.setUserActive(token, uid, locked), {
                  after: [loadRow, loadActivity],
                })
              }
            >
              <Lock size={12} />{" "}
              {locked ? "Mở khóa tài khoản" : "Khóa tài khoản"}
            </button>
          )}
        </div>
        <p className="ns-info-field__label" style={{ gridColumn: "1 / -1" }}>
          Nhân viên <strong>đã nghỉ việc</strong> tự động không đăng nhập được
          (theo trạng thái hồ sơ) — không cần khóa tay. Khóa dùng khi muốn chặn
          một người <strong>đang làm việc</strong>.
        </p>
      </InfoCard>

      <InfoCard
        title={`Phiên đang hoạt động (${sessions.length})`}
        icon={Activity}
      >
        {sessionGroups.length === 0 ? (
          <InfoField label="Phiên" value={null} icon={Activity} />
        ) : (
          sessionGroups.map((g) => (
            <InfoField
              key={g.label}
              label={g.label}
              value={
                g.count > 1
                  ? `${g.count} phiên · mới nhất ${fmtDateTime(g.latest)}`
                  : `Đăng nhập ${fmtDateTime(g.latest)}`
              }
              icon={Activity}
            />
          ))
        )}
      </InfoCard>

      <InfoCard title="Hoạt động tài khoản gần đây" icon={Activity}>
        {activity.length === 0 ? (
          <InfoField label="Hoạt động" value={null} icon={Activity} />
        ) : (
          activity.map((a) => (
            <InfoField
              key={a.id}
              label={`${a.action} · ${fmtDate(a.created_at)}`}
              value={a.actor_name ?? a.detail}
              icon={Activity}
            />
          ))
        )}
      </InfoCard>
    </div>
  );
}
