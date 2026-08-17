// Form lập kế hoạch cho MỘT lượt chạy chung của bài ghép.
//
// Nằm riêng file vì CẢ HAI màn bài ghép đều dựng nó (Bài ghép cũ `BaiGhepSoDo` và Bài ghép 2).
// Trước đây nó `export` từ `BaiGhepSoDo.tsx`, nên màn mới phụ thuộc ngược vào màn cũ — xoá màn cũ
// là gãy màn mới. Form tự nạp `bai-ghep.css` (khuôn `.bgsd-*`) và `ke-hoach-sx.css` (khuôn
// `.khsx-*`) để style đi theo component chứ không đi theo trang nào.
import { useEffect, useState } from "react";
import type { BaiGhepBuocChungBody, BaiGhepSoDo } from "../api/client";
import { crud } from "../api/rebuildCatalog";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Kv, num } from "./keHoachSxShared";
import { nhanDonVi, phut } from "./lsxBuoc";
import "./ke-hoach-sx.css";
import "./bai-ghep.css";

/** Lập kế hoạch cho MỘT lượt chạy chung.
 *
 * Chỉ mở những ô NGƯỜI nhập: tổ · máy · số người · năng suất · vật tư · ghi chú · (thuê ngoài).
 * Số lượng / hao / thời lượng KHÔNG có ở đây — chúng là dẫn xuất, engine tính lúc đọc; cho sửa
 * là đẻ nguồn sự thật thứ hai. Ghi chú kỹ thuật của từng lệnh hiện ở dưới, GOM chứ không đè: thợ
 * chạy chung một lượt phải đọc được yêu cầu của mọi khách trên tờ đó.
 */
export function BuocChungForm({
  g,
  canUpdate,
  onLuu,
  onTach,
}: {
  g: BaiGhepSoDo["gop"][number];
  canUpdate: boolean;
  onLuu: (body: BaiGhepBuocChungBody) => Promise<unknown>;
  onTach: () => Promise<unknown>;
}) {
  const { token } = useAuth();
  const [toRefs, setToRefs] = useState<{ id: number; ten: string }[] | null>(null);
  const [mayRefs, setMayRefs] = useState<{ id: number; ten: string; loaiMay: string | null }[] | null>(null);
  const [vtRefs, setVtRefs] = useState<{ id: number; ma: string; ten: string; donVi: string }[] | null>(null);
  const [f, setF] = useState<BaiGhepBuocChungBody>({});
  const [dangLuu, setDangLuu] = useState(false);
  const [confirmTach, setConfirmTach] = useState(false);

  useEffect(() => {
    if (!token) return;
    crud("/api/cong-doan/phong-ban").list(token)
      .then((r) => setToRefs(r.items.map((t) => ({ id: t.id, ten: String(t.ten) }))))
      .catch(() => setToRefs(null));
    crud("/api/may-thiet-bi").list(token)
      .then((r) => setMayRefs(r.items.map((m) => ({
        id: m.id, ten: String(m.ten),
        loaiMay: (m as { loai_may?: string | null }).loai_may ?? null,
      }))))
      .catch(() => setMayRefs(null));
    crud("/api/vat-lieu-kho/vat-tu-in-an").list(token, { active: true })
      .then((r) => setVtRefs(r.items.map((v) => ({
        id: v.id, ma: String(v.ma), ten: String(v.ten), donVi: String(v.don_vi_gia ?? ""),
      }))))
      .catch(() => setVtRefs(null));
  }, [token]);

  // Đổi form về `{}` khi chuyển sang bước chung khác — không thì số vừa gõ cho bước này rơi sang
  // bước kia lúc bấm Lưu.
  useEffect(() => setF({}), [g.step_key]);

  /** Giá trị đang hiển thị: ưu tiên thứ người vừa gõ, chưa gõ thì lấy thứ server đang giữ. */
  const val = <K extends keyof BaiGhepBuocChungBody>(k: K, hienCo: BaiGhepBuocChungBody[K]) =>
    (f[k] !== undefined ? f[k] : hienCo);

  /** Đầu việc đang GHIM có thể không còn trong bảng khoán của tổ (đổi tổ, hoặc dòng bị ngừng) —
   *  vẫn phải bày ra, không thì `<select>` rơi về "— chọn —" và người dùng tưởng chưa ai chọn. */
  const dsKhoan = (() => {
    const ds = [...g.khoan_chon_duoc];
    if (g.khoan_rate_id != null && !ds.some((k) => k.id === g.khoan_rate_id)) {
      ds.unshift({
        id: g.khoan_rate_id,
        ten: g.khoan_ten ?? `(đang ghim) đầu việc #${g.khoan_rate_id}`,
        don_vi: g.khoan_don_vi ?? "",
        don_gia: g.khoan_don_gia ?? 0,
      });
    }
    return ds;
  })();

  // Vật tư sửa theo LÔ: giữ nguyên danh sách hiện có rồi thay cả cụm khi lưu (API là replace-all).
  const vtHienTai = (f.vat_tus ?? g.vat_tus.map((v) => ({ vat_tu_id: v.vat_tu_id, so_luong: v.so_luong })));
  const datVatTu = (rows: { vat_tu_id: number; so_luong: number }[]) => setF({ ...f, vat_tus: rows });

  const dirty = Object.keys(f).length > 0;
  const luu = async () => {
    setDangLuu(true);
    try {
      const saved = await onLuu(f);
      // BG2 trả `false` khi API validation/guard từ chối nhưng đã đưa lỗi lên banner của page.
      // Giữ draft để người lập kế hoạch sửa tiếp; legacy trả detail/undefined nên vẫn tương thích.
      if (saved !== false) setF({});
    } finally {
      setDangLuu(false);
    }
  };

  return (
    <div className="bgsd-modal-content-grid">
      <div className="bgsd-sec bgsd-sec--featured">
        <div className="bgsd-sec__head">
          <Icon name="link" size={16} style={{ color: "#0284c7" }} />
          <span>{g.ten} — một lượt chạy cho {g.thanh_vien.length} lệnh</span>
        </div>
        <div className="bgsd-form-grid-4">
          <label className="khsx-field bgsd-field-wide">
            <span>Tổ thực hiện</span>
            {/* `value` phải là ID. Trước đây fallback bằng `g.to_ten` (chuỗi) nên không khớp
                `option value` nào → tổ đã gán vẫn hiện "— chọn tổ —". */}
            <select
              value={val("department_id", g.department_id) ?? ""}
              disabled={!canUpdate || !toRefs}
              onChange={(e) => setF({ ...f, department_id: e.target.value ? Number(e.target.value) : null })}
            >
              <option value="">— chọn tổ —</option>
              {(toRefs ?? []).map((t) => (
                <option key={t.id} value={t.id}>{t.ten}</option>
              ))}
            </select>
          </label>
          <label className="khsx-field bgsd-field-wide">
            <span>Máy chạy</span>
            <select
              value={val("may_id", g.may_id) ?? ""}
              disabled={!canUpdate || !mayRefs}
              onChange={(e) => setF({ ...f, may_id: e.target.value ? Number(e.target.value) : null })}
            >
              <option value="">— chọn máy —</option>
              {(mayRefs ?? [])
                .filter((m) => {
                  // T3: lọc máy theo NHÓM công đoạn (bước Bế chỉ thấy máy Bế). Chưa khai ràng buộc
                  // → hiện tất cả. Giữ máy ĐANG CHỌN dù sai loại, để select không rơi về trống.
                  const allow = g.nhom_may_cho_phep ?? [];
                  if (allow.length === 0) return true;
                  if (m.id === val("may_id", g.may_id)) return true;
                  return m.loaiMay != null && allow.includes(m.loaiMay);
                })
                .map((m) => (
                  <option key={m.id} value={m.id}>{m.ten}</option>
                ))}
            </select>
            {(g.nhom_may_cho_phep?.length ?? 0) > 0 && (
              <span className="bgsd-field-hint">Chỉ máy nhóm: {g.nhom_may_cho_phep.join(", ")}</span>
            )}
            {g.may_khong_hop.length > 0 && (
              <span className="bgsd-field-warn">⚠ {g.may_khong_hop.join("; ")}</span>
            )}
          </label>
          <label className="khsx-field">
            <span>Số người</span>
            <input
              type="number" min={1} disabled={!canUpdate}
              value={val("so_nhan_cong", g.so_nhan_cong) ?? ""}
              onChange={(e) => setF({ ...f, so_nhan_cong: Number(e.target.value) || 1 })}
            />
          </label>
          <label className="khsx-field">
            <span>Số lượt chạy</span>
            <input
              type="number" min={1} disabled={!canUpdate}
              title="Vd in 2 mặt trở tự = 2 lượt qua máy"
              value={val("so_luot_chay", g.so_luot_chay) ?? ""}
              onChange={(e) => setF({ ...f, so_luot_chay: Number(e.target.value) || 1 })}
            />
          </label>
        </div>

        {/* Thời lượng: NĂNG SUẤT là đường chính (máy khai tốc độ thì suy ra phút chạy); `chay_phut`
            là cửa GÕ ĐÈ và nó THẮNG công thức. Thiếu ô năng suất thì cách duy nhất tắt chip
            "Chưa có năng suất" là bấm máy tính rồi gõ tay số phút — máy đã khai tốc độ tờ/giờ rồi. */}
        <div className="bgsd-form-grid-4">
          <label className="khsx-field">
            <span>Năng suất</span>
            <input
              type="number" min={0} disabled={!canUpdate}
              placeholder={g.don_vi_nang_suat ?? "theo máy"}
              value={val("nang_suat", g.nang_suat) ?? ""}
              onChange={(e) => setF({ ...f, nang_suat: e.target.value ? Number(e.target.value) : null })}
            />
          </label>
          {/* Chạy · Canh máy · Chờ · Di chuyển ĐÃ BỎ (2026-08-04): thời lượng lượt chung nay
              suy từ MÁY đang gán bằng đúng công thức của bước lệnh —
                thời gian khác + chuẩn bị (từ máy) + SL vào × 60 ÷ tốc độ × số lượt.
              Ô duy nhất còn gõ được là "Thời gian khác". */}
          <label className="khsx-field">
            <span>Thời gian khác (phút)</span>
            <input
              type="number" min={0} disabled={!canUpdate}
              title="Phát sinh ngoài định mức — cộng thẳng vào thời gian chiếm máy"
              value={val("phat_sinh_phut", g.phat_sinh_phut) ?? ""}
              onChange={(e) => setF({ ...f, phat_sinh_phut: e.target.value ? Number(e.target.value) : 0 })}
            />
          </label>
        </div>

        <div className="khsx-tinh-gio">
          <div className="khsx-tinh-gio__row">
            <span>Chuẩn bị (từ máy) + chạy + thời gian khác</span>
            <b>{phut(g.chiem_may_phut)}</b>
          </div>
          {g.chiem_may_phut_max - g.chiem_may_phut_min > 0.5 && (
            <div className="khsx-tinh-gio__dai">
              <span>Nhanh nhất <b>{phut(g.chiem_may_phut_min)}</b></span>
              <span>Chậm nhất <b>{phut(g.chiem_may_phut_max)}</b></span>
            </div>
          )}
        </div>

        {/* Công việc khoán của LƯỢT CHUNG — cùng bảng khoán, cùng cách chọn với bước lệnh ở màn
            KHSX. Ghim theo ID; ảnh chụp đơn giá do server chụp. Đổi tổ thì danh sách đổi theo, nên
            phải LƯU rồi mở lại mới thấy danh sách mới — báo rõ thay vì để người dùng tưởng tổ mới
            không có đầu việc nào. */}
        {(g.khoan_chon_duoc.length > 0 || g.khoan_rate_id != null) && (
          <div className="khsx-field khsx-field--wide khsx-khoan-card">
            <div className="khsx-khoan-card__head">
              <span className="khsx-field__label">Công việc khoán</span>
              <span className="khsx-tag-subtle">bảng khoán của tổ</span>
            </div>
            <select
              value={val("piece_rate_id", g.khoan_rate_id) ?? ""}
              disabled={!canUpdate}
              onChange={(e) =>
                setF({ ...f, piece_rate_id: e.target.value ? Number(e.target.value) : null })
              }
            >
              <option value="">— chọn đầu việc khoán —</option>
              {dsKhoan.map((k) => (
                <option key={k.id} value={k.id}>
                  {k.don_vi ? `${k.ten} — ${num(k.don_gia)} đ/${k.don_vi}` : k.ten}
                </option>
              ))}
            </select>
            <div className="khsx-khoan-card__status">
              {f.piece_rate_id !== undefined || f.department_id !== undefined ? (
                <span className="khsx-pill-status khsx-pill-status--warn">
                  Lưu lượt chung để tính lại tiền công
                </span>
              ) : g.khoan_dien_giai ? (
                <span className="khsx-pill-status khsx-pill-status--ok">{g.khoan_dien_giai}</span>
              ) : g.khoan_ly_do ? (
                <span className="khsx-pill-status khsx-pill-status--error">{g.khoan_ly_do}</span>
              ) : g.khoan_chon_duoc.length > 1 ? (
                <span className="khsx-field__hint">
                  Tổ có {g.khoan_chon_duoc.length} đầu việc khoán — chọn đúng việc thợ làm để tự
                  động ra tiền công.
                </span>
              ) : null}
            </div>
          </div>
        )}

        {/* Số của cả lượt — CHỈ ĐỌC. Đây là chỗ hay bị hiểu nhầm nhất: hao đếm MỘT LẦN cho lượt
            chung, không phải mỗi lệnh một bộ cho cùng một lần lên máy. */}
        <div className="khsx-kvgrid" style={{ gap: "12px", gridTemplateColumns: "1fr 1fr 1fr" }}>
          {/* Đơn vị lấy theo KHAI BÁO của công đoạn — bước bế nhả `cai` thì "ra" đếm con, đóng
              đinh chữ "tờ" là nói sai ngay trên ô người dùng soi kỹ nhất. */}
          <Kv k="Vào (cả lượt)" v={`${num(g.so_luong_vao)} ${nhanDonVi(g.don_vi_vao)}`} />
          <Kv k="Ra (cả lượt)" v={`${num(g.so_luong_ra)} ${nhanDonVi(g.don_vi_ra)}`} />
          <Kv k="Hao (một lần)" v={`${num(g.hao_hut)} ${nhanDonVi(g.don_vi_vao)}`} />
        </div>
      </div>

      {/* Vật tư của CẢ LƯỢT — mực, kẽm, màng dùng chung, không của riêng lệnh nào. API là
          replace-all nên form giữ nguyên danh sách rồi gửi lại cả cụm. */}
      <div className="bgsd-sec">
        <div className="bgsd-sec__head">
          <Icon name="box" size={16} style={{ color: "#0284c7" }} />
          <span>Vật tư cho cả lượt chung</span>
        </div>
        {vtHienTai.length === 0 && <p className="khsx-nhom__sub">Chưa khai vật tư nào cho lượt này.</p>}
        {vtHienTai.map((row, i) => {
          const dm = (vtRefs ?? []).find((v) => v.id === row.vat_tu_id);
          const snap = g.vat_tus.find((v) => v.vat_tu_id === row.vat_tu_id);
          return (
            <div className="bgsd-form-grid-4" key={`${row.vat_tu_id}_${i}`}>
              <label className="khsx-field bgsd-field-wide">
                <span>Vật tư</span>
                <select
                  value={row.vat_tu_id || ""}
                  disabled={!canUpdate || !vtRefs}
                  onChange={(e) => {
                    const next = [...vtHienTai];
                    next[i] = { ...row, vat_tu_id: Number(e.target.value) };
                    datVatTu(next);
                  }}
                >
                  <option value="">— chọn vật tư —</option>
                  {(vtRefs ?? []).map((v) => (
                    <option key={v.id} value={v.id}>{v.ma} · {v.ten}</option>
                  ))}
                </select>
              </label>
              <label className="khsx-field">
                <span>Định mức{dm?.donVi || snap?.don_vi ? ` (${dm?.donVi || snap?.don_vi})` : ""}</span>
                <input
                  type="number" min={0} step="0.001" disabled={!canUpdate}
                  value={row.so_luong ?? ""}
                  onChange={(e) => {
                    const next = [...vtHienTai];
                    next[i] = { ...row, so_luong: Number(e.target.value) || 0 };
                    datVatTu(next);
                  }}
                />
              </label>
              {canUpdate && (
                <button
                  type="button" className="khsx-xlink" style={{ color: "var(--signal)", alignSelf: "end" }}
                  onClick={() => datVatTu(vtHienTai.filter((_, j) => j !== i))}
                >
                  Bỏ
                </button>
              )}
            </div>
          );
        })}
        {canUpdate && (
          <button
            type="button" className="khsx-xlink" style={{ marginTop: "6px" }}
            onClick={() => datVatTu([...vtHienTai, { vat_tu_id: 0, so_luong: 0 }])}
          >
            + Thêm vật tư
          </button>
        )}
      </div>

      {g.loai_buoc === "thue_ngoai" && (
        <div className="bgsd-sec">
          <div className="bgsd-sec__head">
            <Icon name="truck" size={16} style={{ color: "#0284c7" }} />
            {/* Bước chung nằm TRƯỚC điểm toả nên cả giao lẫn nhận đều ở tầng bài — một phiếu. */}
            <span>Gia công ngoài — cả bài đi một phiếu, một nhà cung cấp</span>
          </div>
          <div className="bgsd-form-grid-4">
            <label className="khsx-field bgsd-field-wide">
              <span>Nhà cung cấp</span>
              <input
                type="text" disabled={!canUpdate}
                value={val("nha_cung_cap", g.nha_cung_cap) ?? ""}
                placeholder="tên nhà gia công"
                onChange={(e) => setF({ ...f, nha_cung_cap: e.target.value })}
              />
            </label>
            <label className="khsx-field">
              <span>Đơn giá gia công</span>
              <input
                type="number" min={0} disabled={!canUpdate}
                value={val("don_gia_gia_cong", g.don_gia_gia_cong) ?? ""}
                onChange={(e) => setF({ ...f, don_gia_gia_cong: e.target.value ? Number(e.target.value) : null })}
              />
            </label>
            <label className="khsx-field">
              <span>Số lượng gửi</span>
              <input
                type="number" min={0} disabled={!canUpdate}
                value={val("sl_gui", g.sl_gui) ?? ""}
                onChange={(e) => setF({ ...f, sl_gui: e.target.value ? Number(e.target.value) : null })}
              />
            </label>
            <label className="khsx-field">
              <span>Hao hụt cho phép</span>
              <input
                type="number" min={0} disabled={!canUpdate}
                title="Thoả thuận với nhà gia công"
                value={val("hao_hut_cho_phep", g.hao_hut_cho_phep) ?? ""}
                onChange={(e) => setF({ ...f, hao_hut_cho_phep: e.target.value ? Number(e.target.value) : null })}
              />
            </label>
            <label className="khsx-field">
              <span>Ngày gửi (DK)</span>
              <input
                type="date" disabled={!canUpdate}
                value={val("ngay_gui_dk", g.ngay_gui_dk) ?? ""}
                onChange={(e) => setF({ ...f, ngay_gui_dk: e.target.value || null })}
              />
            </label>
            <label className="khsx-field">
              <span>Ngày nhận (DK)</span>
              <input
                type="date" disabled={!canUpdate}
                value={val("ngay_nhan_dk", g.ngay_nhan_dk) ?? ""}
                onChange={(e) => setF({ ...f, ngay_nhan_dk: e.target.value || null })}
              />
            </label>
            <label className="khsx-field">
              <span>Vận chuyển (ngày)</span>
              <input
                type="number" min={0} step="0.5" disabled={!canUpdate}
                title="Tính cả hai chiều"
                value={val("van_chuyen_ngay", g.van_chuyen_ngay) ?? ""}
                onChange={(e) => setF({ ...f, van_chuyen_ngay: e.target.value ? Number(e.target.value) : null })}
              />
            </label>
            <label className="khsx-field">
              <span>Gia công (ngày)</span>
              <input
                type="number" min={0} step="0.5" disabled={!canUpdate}
                value={val("gia_cong_ngay", g.gia_cong_ngay) ?? ""}
                onChange={(e) => setF({ ...f, gia_cong_ngay: e.target.value ? Number(e.target.value) : null })}
              />
            </label>
          </div>
          <label className="khsx-field" style={{ marginTop: "8px" }}>
            <span>Yêu cầu kỹ thuật gửi nhà gia công</span>
            <textarea
              rows={2} className="khsx-textarea" disabled={!canUpdate}
              value={val("yeu_cau_ky_thuat", g.yeu_cau_ky_thuat) ?? ""}
              onChange={(e) => setF({ ...f, yeu_cau_ky_thuat: e.target.value })}
            />
          </label>
        </div>
      )}

      <div className="bgsd-sec">
        <div className="bgsd-sec__head">
          <Icon name="fileText" size={16} style={{ color: "#0284c7" }} />
          <span>Yêu cầu kỹ thuật của từng lệnh trên tờ này</span>
        </div>
        <ul className="bgsd-gang-notes">
          {g.thanh_vien.map((tv) => (
            <li key={tv.lsx_step_key}>
              <span className="khsx__code">{tv.lsx_ma}</span>
              <span className={tv.ghi_chu_ky_thuat ? "" : "khsx-muted"}>
                {tv.ghi_chu_ky_thuat || "không có ghi chú riêng"}
              </span>
            </li>
          ))}
        </ul>
        <label className="khsx-field" style={{ marginTop: "10px" }}>
          <span>Ghi chú của bài cho lượt chạy này</span>
          <textarea
            rows={2} className="khsx-textarea" disabled={!canUpdate}
            value={f.ghi_chu ?? g.ghi_chu ?? ""}
            onChange={(e) => setF({ ...f, ghi_chu: e.target.value })}
          />
        </label>
      </div>
      {canUpdate && (
        <div className="bgsd-gang-actions">
          <Button variant="primary" disabled={!dirty} loading={dangLuu} onClick={() => void luu()}>
            Lưu kế hoạch lượt chung
          </Button>
          <button
            type="button" className="khsx-xlink" style={{ color: "var(--signal)" }}
            onClick={() => setConfirmTach(true)}
          >
            Tách lượt chung
          </button>
          <ConfirmDialog
            open={confirmTach}
            title={`Tách "${g.ten}"?`}
            message="Kế hoạch của lượt chung sẽ mất, số riêng của từng lệnh quay lại."
            confirmLabel="Tách lượt chung"
            cancelLabel="Hủy"
            danger
            onConfirm={() => {
              setConfirmTach(false);
              void onTach();
            }}
            onCancel={() => setConfirmTach(false)}
          />
        </div>
      )}
    </div>
  );
}
