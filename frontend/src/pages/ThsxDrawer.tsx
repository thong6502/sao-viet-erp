// DRAWER một công việc của bàn THỰC HIỆN SẢN XUẤT (`/work-items/{id}` detail).
//
// Các khối (§3):
//  1) THANH KẾ HOẠCH — dự kiến bắt đầu→kết thúc · máy · SL vào/ra + đơn vị (chỉ ĐỌC, số kế hoạch).
//  2) TỔ THỰC HIỆN (roster) — người `active`; ô "Giao người" (combobox từ `nhanVienChon`, loại người
//     đã trong roster; bước nội bộ `loai_buoc="to"` chỉ nhận thợ LƯƠNG KHOÁN) + nút Rút.
//  3) PHIÊN CHẠY — Bắt đầu / Tạm dừng / Kết thúc (điều kiện bật ở §8) + danh sách phiên + khoảng
//     tham gia (bảng phụ gấp/mở).
//  4) PHA SAU (Giai đoạn 3+4) — sản lượng · bàn giao · vật tư · hỗ trợ chéo · phân bổ lương, dựng ở
//     `ThsxExecPanels`; mọi mặt GHI đi qua `exec.*` (controller lo khoá lạc quan + refetch + toast).
//
// Component KHÔNG tự gọi API ghi: phát ý định qua callback; controller lo dialog lý do + version lạc quan.
import { useMemo, useState } from "react";
import type {
  SxNhanVienChon, SxWorkItemChiTiet, SxHoTroUngVien, SxLyDo,
  SxKcsChiTiet, SxKhoChiTiet, SxDongNhomDieuKien,
} from "../api/client";
import { NHAN_MUC_DO, type MayChon } from "../api/kyThuatMay";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import { num, ngayGio } from "./keHoachSxShared";
import { nhanDonVi } from "./lsxBuoc";
import { sxSerial, ThsxTrangThaiPill } from "./thsxShared";
import { ThsxExecPanels, type ThsxExec } from "./ThsxExecPanels";
import { ThsxKcsPanel, ThsxKhoPanel, ThsxDongNhomPanel, type Opt } from "./ThsxG5";

interface Props {
  chiTiet: SxWorkItemChiTiet | null;
  loading: boolean;
  canAssign: boolean;
  /** Người chọn được cho ô "Giao người" (endpoint riêng của module, gác `san_xuat:read`). */
  candidates: SxNhanVienChon[];
  /** Ứng viên HỖ TRỢ CHÉO (§9) — thợ tổ SX khác đang làm (endpoint riêng module). */
  hoTroUngVien: SxHoTroUngVien[];
  /** Máy chọn được cho ô "Đổi máy" (`may-chon` — không đòi quyền `dm_thiet_bi` như thợ đứng máy). */
  mayOptions: MayChon[];
  /** Nạp danh mục lý do/lỗi (§15) theo nhóm — có cache ở controller. */
  loadLyDo: (nhom: string) => Promise<SxLyDo[]>;
  /** Hợp đồng các mặt GHI của Giai đoạn 3+4+5. */
  exec: ThsxExec;
  /** Giai đoạn 5 — KCS §13: mẻ kiểm tra + lỗi + ảnh (chỉ nạp khi bước `la_kcs`). */
  kcsCt: SxKcsChiTiet | null;
  /** Giai đoạn 5 — Kho §14: yêu cầu nhập + BTP dư (chỉ nạp khi `la_kcs` + có `nhom_id`). */
  khoCt: SxKhoChiTiet | null;
  /** Giai đoạn 5 — §16/§13.3: checklist cổng đóng nhóm (chỉ nạp khi `la_kcs_cuoi` + có `nhom_id`). */
  dieuKien: SxDongNhomDieuKien | null;
  /** Danh sách tổ có thể chỉ định "chịu trách nhiệm lỗi" (dẫn xuất từ ứng viên hỗ trợ). */
  toChiuOpts: Opt[];
  /** Công đoạn thượng nguồn có thể gán "liên đới lỗi" (dẫn xuất từ bàn giao đến). */
  congDoanRefOpts: Opt[];
  /** Có một lệnh ghi đang bay (khoá nút để tránh double-submit). */
  busy: boolean;
  onGiao: (employeeId: number) => void;
  onRut: (phanCongId: number) => void;
  onBatDau: () => void;
  onTamDung: () => void;
  onKetThuc: () => void;
  onClose: () => void;
}

const DONG_LABEL: Record<string, string> = {
  tam_dung: "tạm dừng",
  ket_thuc: "kết thúc",
  // Đổi máy giữa chừng KHÔNG phải tạm dừng thật (§7.2 mở rộng 31/08/2026, review vòng 1) — nhãn
  // riêng để người xem lịch sử phiên không hiểu lầm công việc đã dừng.
  doi_may: "đổi máy",
};

// Mức độ sự cố: KHÔNG khai lại chuỗi mới ở màn này — đọc thẳng `NHAN_MUC_DO` của module Sửa chữa
// máy (nguồn là `models.ky_thuat_may.MUC_DO`), để thêm/đổi mức là hai màn tự đúng theo nhau.
const MUC_DO_OPTS = Object.entries(NHAN_MUC_DO);
// Mặc định trùng `MUC_DO_TRUNG_BINH` bên BE; nếu ai đổi danh mục thì lùi về mức đầu tiên còn lại
// thay vì gửi lên một chuỗi không còn hợp lệ.
const MUC_DO_MAC_DINH =
  "trung_binh" in NHAN_MUC_DO ? "trung_binh" : (MUC_DO_OPTS[0]?.[0] ?? "trung_binh");

export function ThsxDrawer({
  chiTiet, loading, canAssign, candidates, hoTroUngVien, mayOptions, loadLyDo, exec, busy,
  kcsCt, khoCt, dieuKien, toChiuOpts, congDoanRefOpts,
  onGiao, onRut, onBatDau, onTamDung, onKetThuc, onClose,
}: Props) {
  const [giaoOpen, setGiaoOpen] = useState(false);
  const [q, setQ] = useState("");
  const [moKhoang, setMoKhoang] = useState(false);
  const [doiMayOpen, setDoiMayOpen] = useState(false);
  const [mayChonId, setMayChonId] = useState<number | "">("");
  const [lyDoMay, setLyDoMay] = useState("");
  // Báo sự cố (§7.2 mở rộng 31/08/2026). Mức độ mặc định "trung_binh" — cùng mặc định với BE
  // (`models.ky_thuat_may.MUC_DO_TRUNG_BINH`), để tổ trưởng không phải chọn khi không chắc.
  const [suCoOpen, setSuCoOpen] = useState(false);
  const [scChoHong, setScChoHong] = useState("");
  const [scMoTa, setScMoTa] = useState("");
  const [scMucDo, setScMucDo] = useState(MUC_DO_MAC_DINH);
  const [scDung, setScDung] = useState(true);

  const cv = chiTiet?.cong_viec ?? null;
  const tt = chiTiet?.trang_thai ?? cv?.trang_thai ?? "released";
  const isTo = cv?.loai_buoc === "to";
  // Đổi máy §7.2: chỉ bước gắn MÁY mới có khái niệm này (bước "to"/"thue_ngoai" không có).
  const isMay = cv?.loai_buoc === "may";
  const canDoiMay = canAssign && !busy && (tt === "running" || tt === "paused") && isMay;
  // Báo sự cố: cùng điều kiện với Đổi máy (bước có MÁY, việc đang chạy hoặc tạm dừng) — không có
  // máy thì không có gì để báo hỏng, BE cũng chặn đúng như vậy.
  const canBaoSuCo = canDoiMay;
  // Cửa gửi, khớp luật BE: phải nêu chỗ hỏng; chọn "Dừng sản xuất" thì mô tả BẮT BUỘC (đây là
  // mốc mất giờ máy của lệnh). BE vẫn là trọng tài — chỗ này chỉ để không bấm rồi mới ăn lỗi.
  const scSanSang = !busy && scChoHong.trim() !== "" && (!scDung || scMoTa.trim() !== "");

  // Roster đang làm + điều kiện bật nút (khớp tiền điều kiện service; BE vẫn là trọng tài).
  const rosterActive = useMemo(
    () => (chiTiet?.phan_cong ?? []).filter((p) => p.trang_thai === "active"),
    [chiTiet],
  );
  // Loại máy ĐANG CHẠY khỏi danh sách chọn — "đổi máy" nghĩa là đổi SANG máy khác, không phải
  // chọn lại chính nó (review vòng 1, Minor 6). BE đã tự chặn same-machine (Important 2/4 cũ),
  // đây chỉ đỡ người dùng khỏi bấm nhầm rồi bị BE trả lỗi.
  const mayOptionsKhaDung = useMemo(
    () => mayOptions.filter((m) => m.id !== cv?.may_id),
    [mayOptions, cv?.may_id],
  );
  const hasKhoan = rosterActive.some((p) => p.la_luong_khoan);
  const done = tt === "completed";
  const canBatDau = canAssign && !busy && (tt === "released" || tt === "paused") && hasKhoan;
  const canTamDung = canAssign && !busy && tt === "running";
  const canKetThuc = canAssign && !busy && (tt === "running" || tt === "paused");
  const canGiao = canAssign && !done;

  // Ứng viên cho combobox: loại người đã trong roster active; lọc theo ô tìm (tên/mã).
  const activeIds = useMemo(() => new Set(rosterActive.map((p) => p.employee_id)), [rosterActive]);
  const dsChon = useMemo(() => {
    const kw = q.trim().toLowerCase();
    return candidates
      .filter((c) => !activeIds.has(c.id))
      .filter((c) => !kw || c.full_name.toLowerCase().includes(kw) || (c.code ?? "").toLowerCase().includes(kw));
  }, [candidates, activeIds, q]);

  function chon(c: SxNhanVienChon) {
    if (isTo && !c.la_luong_khoan) return; // bước nội bộ chỉ nhận thợ khoán (BE cũng chặn)
    onGiao(c.id);
    setGiaoOpen(false);
    setQ("");
  }

  async function xacNhanDoiMay() {
    if (mayChonId === "") return;
    const ok = await exec.doiMay(mayChonId, lyDoMay.trim() || null);
    if (ok) {
      setDoiMayOpen(false);
      setMayChonId("");
      setLyDoMay("");
    }
  }

  async function xacNhanSuCo() {
    if (!scSanSang) return;
    const ok = await exec.baoSuCo({
      bo_phan_hong: scChoHong.trim(),
      mo_ta: scMoTa.trim() || null,
      muc_do: scMucDo,
      dung_san_xuat: scDung,
    });
    if (ok) {
      setSuCoOpen(false);
      setScChoHong("");
      setScMoTa("");
      setScMucDo(MUC_DO_MAC_DINH);
      setScDung(true);
    }
  }

  const serial = cv ? sxSerial(cv.nguon_ma) : "";

  return (
    <div className="thsx-panel__inner">
      <div className="thsx-panel__head">
        <div className="thsx-panel__title">
          {cv ? (
            <>
              <span className="thsx-panel__serial">{serial}</span>
              <span className="thsx-panel__cd">{cv.ten_cong_doan}</span>
            </>
          ) : (
            <span className="thsx-panel__cd">Chi tiết công việc</span>
          )}
        </div>
        {chiTiet && <ThsxTrangThaiPill tt={tt} />}
        <button type="button" className="thsx-panel__close" onClick={onClose} aria-label="Đóng">
          <Icon name="x" size={16} />
        </button>
      </div>

      <div className="thsx-panel__body">
        {loading && !chiTiet ? (
          <div className="thsx-panel__loading">Đang tải…</div>
        ) : !cv || !chiTiet ? (
          <div className="thsx-panel__empty">Không tải được chi tiết công việc.</div>
        ) : (
          <>
            {/* 1 · THANH KẾ HOẠCH */}
            <section className="thsx-psec">
              <div className="thsx-psec__h"><span className="thsx-psec__title">Kế hoạch</span></div>
              <div className="thsx-kv"><span className="thsx-kv__k">Dự kiến</span>
                <span className="thsx-kv__v thsx-kv__v--num">
                  {cv.du_kien_bat_dau ? ngayGio(cv.du_kien_bat_dau) : "—"}
                  {" → "}
                  {cv.du_kien_ket_thuc ? ngayGio(cv.du_kien_ket_thuc) : "—"}
                </span>
              </div>
              {cv.may && (
                <div className="thsx-kv"><span className="thsx-kv__k">Máy</span>
                  <span className="thsx-kv__v">{cv.may}</span></div>
              )}
              <div className="thsx-kv"><span className="thsx-kv__k">SL vào</span>
                <span className="thsx-kv__v thsx-kv__v--num">
                  {cv.so_luong_vao != null ? `${num(cv.so_luong_vao)}${cv.don_vi_vao ? ` ${nhanDonVi(cv.don_vi_vao)}` : ""}` : "—"}
                </span>
              </div>
              <div className="thsx-kv"><span className="thsx-kv__k">SL ra</span>
                <span className="thsx-kv__v thsx-kv__v--num">
                  {cv.so_luong_ra != null ? `${num(cv.so_luong_ra)}${cv.don_vi_ra ? ` ${nhanDonVi(cv.don_vi_ra)}` : ""}` : "—"}
                </span>
              </div>
              <div className="thsx-kv"><span className="thsx-kv__k">Nguồn</span>
                <span className="thsx-kv__v">{cv.nguon_ma}{cv.nguon_ten ? ` · ${cv.nguon_ten}` : ""}</span></div>
            </section>

            {/* 1b · THỰC TẾ — ba số của CHÍNH tổ này. Hai dòng SL vào/SL ra ở trên vẫn là kế
                hoạch nguyên vẹn; "Còn thiếu" chấm theo lượng THỰC NHẬN, nên tổ trước giao thiếu
                thì tổ này không bị đổ oan. */}
            <section className="thsx-psec">
              <div className="thsx-psec__h"><span className="thsx-psec__title">Thực tế</span></div>
              <div className="thsx-kv"><span className="thsx-kv__k">Thực nhận</span>
                <span className="thsx-kv__v thsx-kv__v--num">
                  {cv.thuc_nhan != null
                    ? `${num(cv.thuc_nhan)}${cv.don_vi_vao ? ` ${nhanDonVi(cv.don_vi_vao)}` : ""}`
                    : "— chưa ai giao tới"}
                </span>
              </div>
              <div className="thsx-kv"><span className="thsx-kv__k">Đã làm</span>
                <span className="thsx-kv__v thsx-kv__v--num">
                  {cv.da_lam != null ? `${num(cv.da_lam)}${cv.don_vi_ra ? ` ${nhanDonVi(cv.don_vi_ra)}` : ""}` : "—"}
                </span>
              </div>
              <div className="thsx-kv"><span className="thsx-kv__k">Còn thiếu</span>
                <span className={`thsx-kv__v thsx-kv__v--num${(cv.con_thieu ?? 0) > 0 ? " thsx-kv__v--thieu" : ""}`}>
                  {cv.con_thieu == null
                    ? "—"
                    : cv.con_thieu > 0
                      ? `${num(cv.con_thieu)}${cv.don_vi_ra ? ` ${nhanDonVi(cv.don_vi_ra)}` : ""}`
                      : "đủ"}
                </span>
              </div>
              {cv.thuc_nhan != null && cv.muc_tieu != null && cv.so_luong_ra != null
                && cv.muc_tieu < cv.so_luong_ra && (
                <p className="thsx-note">
                  Nhận thiếu so với kế hoạch — mốc của tổ rút còn {num(cv.muc_tieu)}
                  {cv.don_vi_ra ? ` ${nhanDonVi(cv.don_vi_ra)}` : ""}.
                </p>
              )}
            </section>

            {/* 2 · TỔ THỰC HIỆN (roster) */}
            <section className="thsx-psec">
              <div className="thsx-psec__h">
                <span className="thsx-psec__title">Tổ thực hiện</span>
                {canGiao && (
                  <div className="thsx-giao">
                    <Button variant="ghost" onClick={() => setGiaoOpen((o) => !o)} disabled={busy}
                      aria-expanded={giaoOpen}>
                      <Icon name="plus" size={14} /> Giao người
                    </Button>
                    {giaoOpen && (
                      <div className="thsx-giao__pop" role="dialog" aria-label="Chọn người để giao">
                        <div className="thsx-giao__search">
                          <Icon name="search" size={14} />
                          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)}
                            placeholder="Tìm tên / mã…" />
                        </div>
                        {isTo && (
                          <p className="thsx-giao__note">
                            Bước nội bộ chỉ nhận thợ <b>lương khoán</b>.
                          </p>
                        )}
                        <div className="thsx-giao__list">
                          {dsChon.length === 0 ? (
                            <div className="thsx-giao__empty">Không còn ai để giao.</div>
                          ) : dsChon.map((c) => {
                            const chan = isTo && !c.la_luong_khoan;
                            return (
                              <button key={c.id} type="button" className="thsx-giao__opt"
                                disabled={chan} onClick={() => chon(c)}
                                title={chan ? "Công nhật — không giao vào bước nội bộ" : undefined}>
                                <span className="thsx-giao__nm">{c.full_name}</span>
                                {c.code && <span className="thsx-giao__code">{c.code}</span>}
                                <span className={`thsx-tag ${c.la_luong_khoan ? "thsx-tag--khoan" : "thsx-tag--nhat"}`}>
                                  {c.la_luong_khoan ? "khoán" : "công nhật"}
                                </span>
                                {!c.co_tai_khoan && <span className="thsx-tag thsx-tag--noacc">không TK</span>}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
              {rosterActive.length === 0 ? (
                <p className="thsx-note">Chưa giao ai. Cần ≥1 thợ lương khoán để bắt đầu.</p>
              ) : (
                <ul className="thsx-roster">
                  {rosterActive.map((p) => (
                    <li key={p.id} className="thsx-roster__row">
                      <Icon name="users" size={13} />
                      <span className="thsx-roster__nm">{p.ho_ten}</span>
                      <span className={`thsx-tag ${p.la_luong_khoan ? "thsx-tag--khoan" : "thsx-tag--nhat"}`}>
                        {p.la_luong_khoan ? "khoán" : "công nhật"}
                      </span>
                      {!p.co_tai_khoan && <span className="thsx-tag thsx-tag--noacc">không TK</span>}
                      {canAssign && !done && (
                        <button type="button" className="thsx-roster__rut" onClick={() => onRut(p.id)}
                          disabled={busy} title="Rút khỏi công việc">
                          <Icon name="minus" size={13} /> Rút
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {/* 3 · PHIÊN CHẠY */}
            <section className="thsx-psec">
              <div className="thsx-psec__h"><span className="thsx-psec__title">Phiên chạy</span></div>
              <div className="thsx-run">
                {tt === "running" ? (
                  <>
                    <Button variant="secondary" onClick={onTamDung} disabled={!canTamDung}>
                      <Icon name="pause" size={14} /> Tạm dừng
                    </Button>
                    <Button variant="accent" onClick={onKetThuc} disabled={!canKetThuc}>
                      <Icon name="square" size={13} /> Kết thúc
                    </Button>
                  </>
                ) : (
                  <>
                    <Button variant="accent" onClick={onBatDau} disabled={!canBatDau}>
                      <Icon name="play" size={14} /> {tt === "paused" ? "Tiếp tục" : "Bắt đầu"}
                    </Button>
                    {(tt === "paused") && (
                      <Button variant="secondary" onClick={onKetThuc} disabled={!canKetThuc}>
                        <Icon name="square" size={13} /> Kết thúc
                      </Button>
                    )}
                  </>
                )}
                {isMay && (
                  <Button variant="ghost" onClick={() => setDoiMayOpen((o) => !o)} disabled={!canDoiMay}
                    aria-expanded={doiMayOpen}>
                    <Icon name="cpu" size={14} /> Đổi máy
                  </Button>
                )}
                {isMay && (
                  <Button variant="ghost" onClick={() => setSuCoOpen((o) => !o)} disabled={!canBaoSuCo}
                    aria-expanded={suCoOpen}>
                    <Icon name="alert" size={14} /> Báo sự cố
                  </Button>
                )}
              </div>
              {!hasKhoan && !done && tt !== "running" && (
                <p className="thsx-note thsx-note--warn">
                  <Icon name="alert" size={13} /> Cần ≥1 thợ lương khoán mới bắt đầu được.
                </p>
              )}

              {doiMayOpen && (
                <div className="thsx-x-form thsx-x-form--sub">
                  <div className="thsx-x-grid2">
                    <label className="thsx-x-fld">
                      <span className="thsx-x-fld__l">Máy mới</span>
                      <select className="thsx-x-sel" value={mayChonId} disabled={mayOptionsKhaDung.length === 0}
                        onChange={(e) => setMayChonId(e.target.value ? Number(e.target.value) : "")}>
                        <option value="">— Chọn máy —</option>
                        {mayOptionsKhaDung.map((m) => (
                          <option key={m.id} value={m.id}>{m.ma}{m.ten ? ` — ${m.ten}` : ""}</option>
                        ))}
                      </select>
                    </label>
                    <label className="thsx-x-fld">
                      <span className="thsx-x-fld__l">Lý do (không bắt buộc)</span>
                      <input className="thsx-x-in" value={lyDoMay} onChange={(e) => setLyDoMay(e.target.value)}
                        placeholder="Máy hỏng, đổi ca…" />
                    </label>
                  </div>
                  {/* Review vòng 1, Minor 7: trước đây nút chỉ im lặng bị khoá khi rỗng, không
                      giải thích vì sao — hai nguyên nhân khác hẳn nhau nên tách hai thông báo:
                      danh mục KHÔNG tải được (thường do thiếu quyền đọc `ky_thuat_may`/`bao_tri`)
                      so với danh mục tải được nhưng chỉ có đúng máy đang chạy, không còn máy khác. */}
                  {mayOptions.length === 0 ? (
                    <p className="thsx-note thsx-note--warn">
                      <Icon name="alert" size={13} /> Không tải được danh mục Máy — kiểm tra lại
                      quyền xem Máy, hoặc thử tải lại trang.
                    </p>
                  ) : mayOptionsKhaDung.length === 0 && (
                    <p className="thsx-note thsx-note--warn">
                      <Icon name="alert" size={13} /> Không còn máy nào khác ngoài máy đang chạy để đổi sang.
                    </p>
                  )}
                  {tt === "running" ? (
                    <p className="thsx-note">
                      Đang CHẠY: đóng phiên máy cũ + mở phiên mới cùng mốc — giờ máy cũ không mất.
                    </p>
                  ) : (
                    <p className="thsx-note">Đang TẠM DỪNG: chỉ đổi máy phân công, không mở phiên mới.</p>
                  )}
                  <div className="thsx-run">
                    <Button variant="ghost" onClick={() => { setDoiMayOpen(false); setMayChonId(""); setLyDoMay(""); }}>
                      Huỷ
                    </Button>
                    <Button variant="accent" onClick={xacNhanDoiMay} disabled={busy || mayChonId === ""}>
                      Xác nhận đổi máy
                    </Button>
                  </div>
                </div>
              )}

              {suCoOpen && (
                <div className="thsx-x-form thsx-x-form--sub">
                  <div className="thsx-x-grid2">
                    <label className="thsx-x-fld">
                      <span className="thsx-x-fld__l">Chỗ hỏng</span>
                      <input className="thsx-x-in" value={scChoHong} maxLength={150}
                        onChange={(e) => setScChoHong(e.target.value)}
                        placeholder="Đầu cắn giấy, motor…" />
                    </label>
                    <label className="thsx-x-fld">
                      <span className="thsx-x-fld__l">Mức độ</span>
                      <select className="thsx-x-sel" value={scMucDo} onChange={(e) => setScMucDo(e.target.value)}>
                        {MUC_DO_OPTS.map(([ma, nhan]) => (
                          <option key={ma} value={ma}>{nhan}</option>
                        ))}
                      </select>
                    </label>
                  </div>
                  <div className="thsx-x-grid2">
                    <label className="thsx-x-fld">
                      <span className="thsx-x-fld__l">Máy còn chạy được không</span>
                      <select className="thsx-x-sel" value={scDung ? "dung" : "chay"}
                        onChange={(e) => setScDung(e.target.value === "dung")}>
                        <option value="dung">Dừng sản xuất</option>
                        <option value="chay">Vẫn chạy</option>
                      </select>
                    </label>
                    <label className="thsx-x-fld">
                      <span className="thsx-x-fld__l">Mô tả {scDung ? "(bắt buộc)" : "(không bắt buộc)"}</span>
                      <input className="thsx-x-in" value={scMoTa} onChange={(e) => setScMoTa(e.target.value)}
                        placeholder="Kể rõ hiện tượng cho thợ sửa…" />
                    </label>
                  </div>
                  {/* Hai lựa chọn khác nhau ở HỆ QUẢ chứ không chỉ ở chữ, nên nói thẳng ra: chọn
                      "Dừng sản xuất" là mốc mất giờ máy của lệnh (đóng phiên + tạm dừng công việc),
                      chọn "Vẫn chạy" thì chỉ là một yêu cầu gửi sang tổ sửa chữa. */}
                  {scDung ? (
                    <p className="thsx-note thsx-note--warn">
                      <Icon name="alert" size={13} />{" "}
                      {tt === "running"
                        ? "Công việc sẽ TẠM DỪNG và phiên máy đóng lại — giờ máy ngừng tính từ lúc gửi."
                        : "Công việc đang tạm dừng nên chỉ gửi yêu cầu sửa chữa, không đóng thêm phiên nào."}
                    </p>
                  ) : (
                    <p className="thsx-note">
                      Máy vẫn chạy: chỉ gửi yêu cầu sang tổ sửa chữa, công việc và phiên máy giữ nguyên.
                    </p>
                  )}
                  <div className="thsx-run">
                    <Button variant="ghost" onClick={() => {
                      setSuCoOpen(false); setScChoHong(""); setScMoTa("");
                      setScMucDo(MUC_DO_MAC_DINH); setScDung(true);
                    }}>
                      Huỷ
                    </Button>
                    <Button variant="accent" onClick={xacNhanSuCo} disabled={!scSanSang}>
                      Gửi tổ sửa chữa
                    </Button>
                  </div>
                </div>
              )}

              {chiTiet.phien_chay.length === 0 ? (
                <p className="thsx-note">Chưa có phiên chạy nào.</p>
              ) : (
                <ul className="thsx-phien">
                  {chiTiet.phien_chay.map((ph) => {
                    const dang = ph.ket_thuc == null;
                    return (
                      <li key={ph.id} className={`thsx-phien__row${dang ? " is-run" : ""}`}>
                        <span className="thsx-phien__no">#{ph.so_thu_tu}</span>
                        <span className="thsx-phien__time thsx-kv__v--num">
                          {ngayGio(ph.bat_dau)} → {dang ? "đang chạy" : ngayGio(ph.ket_thuc)}
                        </span>
                        {ph.may_ten && <span className="thsx-tag">{ph.may_ten}</span>}
                        {ph.loai_dong && (
                          <span className="thsx-phien__dong">{DONG_LABEL[ph.loai_dong] ?? ph.loai_dong}</span>
                        )}
                        {(ph.ly_do || ph.ly_do_bat_dau_tre) && (
                          <span className="thsx-phien__ly" title={ph.ly_do ?? ph.ly_do_bat_dau_tre ?? ""}>
                            “{ph.ly_do ?? ph.ly_do_bat_dau_tre}”
                          </span>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}

              {chiTiet.khoang_tham_gia.length > 0 && (
                <>
                  <button type="button" className="thsx-fold" onClick={() => setMoKhoang((o) => !o)}
                    aria-expanded={moKhoang}>
                    <Icon name={moKhoang ? "chevron" : "chevron"} size={13} />
                    Khoảng tham gia ({chiTiet.khoang_tham_gia.length})
                  </button>
                  {moKhoang && (
                    <ul className="thsx-kthamgia">
                      {chiTiet.khoang_tham_gia.map((k) => (
                        <li key={k.id} className="thsx-kthamgia__row">
                          <span className="thsx-kthamgia__nm">{k.ho_ten}</span>
                          <span className="thsx-kthamgia__ph">#{
                            chiTiet.phien_chay.find((p) => p.id === k.phien_chay_id)?.so_thu_tu ?? "?"
                          }</span>
                          <span className="thsx-kthamgia__time thsx-kv__v--num">
                            {ngayGio(k.bat_dau)} → {k.ket_thuc == null ? "…" : ngayGio(k.ket_thuc)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </>
              )}
            </section>

            {/* 4 · PHA SAU (Giai đoạn 3+4) — sản lượng · bàn giao · vật tư · hỗ trợ · phân bổ */}
            <ThsxExecPanels
              chiTiet={chiTiet}
              canAssign={canAssign}
              busy={busy}
              hoTroUngVien={hoTroUngVien}
              loadLyDo={loadLyDo}
              exec={exec}
            />

            {/* 5 · KCS §13 — bước kiểm tra: ghi mẻ + lỗi + ảnh + phản hồi trách nhiệm */}
            {cv.la_kcs && (
              <ThsxKcsPanel
                chiTiet={chiTiet}
                ct={kcsCt}
                canAssign={canAssign}
                busy={busy}
                loadLyDo={loadLyDo}
                toChiuOpts={toChiuOpts}
                congDoanRefOpts={congDoanRefOpts}
                exec={exec}
              />
            )}

            {/* 5 · KHO §14 — nhập thành phẩm + phân loại BTP dư (bước KCS thuộc một nhóm) */}
            {cv.la_kcs && cv.nhom_id != null && (
              <ThsxKhoPanel
                chiTiet={chiTiet}
                kho={khoCt}
                kcsBatches={kcsCt?.batch ?? []}
                canAssign={canAssign}
                busy={busy}
                exec={exec}
              />
            )}

            {/* 5 · ĐÓNG NHÓM §16/§13.3 — checklist cổng + đóng thiếu (chỉ ở KCS CUỐI của nhóm) */}
            {cv.la_kcs_cuoi && cv.nhom_id != null && (
              <ThsxDongNhomPanel
                dieuKien={dieuKien}
                canAssign={canAssign}
                busy={busy}
                loadLyDo={loadLyDo}
                onDongThieu={exec.dongThieu}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}
