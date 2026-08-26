// Tab Đính kèm của hồ sơ nhân sự (tách từ pages/NhanSuPage.tsx).
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, assetUrl, type EmployeeAttachment } from "../../../../api/client";
import { EmptyState } from "../../../../components/EmptyState";
import { fmtDate } from "../../../../utils/format";
import { Eye, Trash2 } from "lucide-react";
import { DOC_KIND_LABEL } from "../shared/constants";
import { errMsg, getFileTypeInfo } from "../shared/helpers";
import { FilePicker } from "../components/form-fields";

export function FilesTab({
  token,
  employeeId,
  canUpdate,
}: {
  token: string;
  employeeId: number;
  canUpdate: boolean;
}) {
  const [items, setItems] = useState<EmployeeAttachment[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);
  const [activeKind, setActiveKind] = useState<string>("all");

  const load = useCallback(() => {
    setLoi(null);
    api.employees
      .attachments(token, employeeId)
      .then((r) => setItems(r.items))
      .catch((e) => {
        setItems([]);
        setLoi(errMsg(e));
      });
  }, [token, employeeId]);

  useEffect(() => {
    load();
  }, [load]);

  const counts = useMemo(() => {
    if (!items) return {};
    const res: Record<string, number> = { all: items.length };
    for (const item of items) {
      res[item.doc_kind] = (res[item.doc_kind] || 0) + 1;
    }
    return res;
  }, [items]);

  const filteredItems = useMemo(() => {
    if (!items) return [];
    if (activeKind === "all") return items;
    return items.filter((a) => a.doc_kind === activeKind);
  }, [items, activeKind]);

  const hasFiles = !!(items && items.length > 0);

  return (
    <div>
      {canUpdate && (
        <FilePicker
          disabled={busy}
          compact={hasFiles}
          defaultKind={activeKind !== "all" ? activeKind : "hop_dong"}
          onAdd={async (file, kind) => {
            setBusy(true);
            try {
              await api.employees.upload(token, employeeId, file, kind);
              load();
            } finally {
              setBusy(false);
            }
          }}
        />
      )}

      {busy && <p className="ns__empty">Đang tải tệp lên…</p>}
      {loi && <EmptyState trangThai="loi" loi={loi} onThuLai={load} />}
      {!loi && items === null && <EmptyState trangThai="dang-tai" />}

      {!loi && items !== null && (
        <>
          {/* Category Filter Chips Bar */}
          <div className="ns-file-filters">
            <button
              type="button"
              className={`ns-file-filter-chip ${activeKind === "all" ? "ns-file-filter-chip--active" : ""}`}
              onClick={() => setActiveKind("all")}
            >
              Tất cả
              <span className="ns-file-filter-chip__count">
                {counts["all"] || 0}
              </span>
            </button>
            {Object.entries(DOC_KIND_LABEL).map(([k, label]) => (
              <button
                key={k}
                type="button"
                className={`ns-file-filter-chip ${activeKind === k ? "ns-file-filter-chip--active" : ""}`}
                onClick={() => setActiveKind(k)}
              >
                {label}
                <span className="ns-file-filter-chip__count">
                  {counts[k] || 0}
                </span>
              </button>
            ))}
          </div>

          {/* Full-width List Rows */}
          {filteredItems.length === 0 ? (
            <p className="ns__empty" style={{ padding: "20px 0" }}>
              {activeKind === "all"
                ? "Chưa có tệp đính kèm nào."
                : `Chưa có tệp nào thuộc danh mục "${DOC_KIND_LABEL[activeKind]}".`}
            </p>
          ) : (
            <ul className="ns-filelist-v2">
              {filteredItems.map((a) => {
                const typeInfo = getFileTypeInfo(a.file_name);
                const IconComponent = typeInfo.icon;
                return (
                  <li key={a.id} className="ns-fileitem">
                    <div className={`ns-fileitem__icon ${typeInfo.className}`}>
                      <IconComponent size={18} />
                    </div>
                    <div className="ns-fileitem__main">
                      <div className="ns-fileitem__name-group">
                        <span className="ns-fileitem__name" title={a.file_name}>
                          {a.file_name}
                        </span>
                        <div className="ns-fileitem__sub">
                          <span>{fmtDate(a.uploaded_at)}</span>
                        </div>
                      </div>
                      <span className="ns-fileitem__badge">
                        {DOC_KIND_LABEL[a.doc_kind] ?? a.doc_kind}
                      </span>
                    </div>
                    <div className="ns-fileitem__actions">
                      <a
                        href={assetUrl(a.file_url) ?? "#"}
                        target="_blank"
                        rel="noreferrer"
                        className="btn btn--secondary btn--sm"
                        style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
                        title="Xem / Tải tệp"
                      >
                        <Eye size={13} /> Xem / Tải
                      </a>
                      {canUpdate && (
                        <button
                          type="button"
                          className="btn btn--ghost ns-danger btn--sm"
                          style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
                          title="Xóa tệp"
                          aria-label={`Xóa tệp ${a.file_name}`}
                          onClick={async () => {
                            if (
                              window.confirm(
                                `Bạn có chắc chắn muốn xóa tệp "${a.file_name}"?`,
                              )
                            ) {
                              await api.employees.deleteAttachment(
                                token,
                                employeeId,
                                a.id,
                              );
                              load();
                            }
                          }}
                        >
                          <Trash2 size={13} /> Xóa
                        </button>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
