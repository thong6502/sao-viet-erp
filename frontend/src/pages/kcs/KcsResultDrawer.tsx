// KCS kiêm nhiệm (mg 0250) — drawer ghi kết quả / kiểm đột xuất / xem lịch sử.
//
// Ruling 3 (docs/design-kcs-kiem-nhiem-ui.md mục 3): BỐN KHỐI xếp DỌC cuộn liên tục trong MỘT
// drawer (KHÔNG phải wizard nhiều trang) — khối 2 (checklist) chỉ hiện ở mode="ghi" (Ruling 6:
// đột xuất không có snapshot tiêu chí cố định để bám); khối 4 (lỗi) chỉ hiện khi Lỗi > 0.
//
// Khác biệt quan trọng giữa hai luồng LƯU (đọc kỹ trước khi sửa):
//   - mode="ghi" (routing): backend TÁCH hai lệnh — `taoBatchKcs` (JSON) tạo mẻ, rồi NẾU lỗi>0
//     mới gọi tiếp `ghiLoiKcs` (multipart) để ghi lỗi + ảnh vào batch vừa tạo.
//   - mode="dot_xuat" | "diem_kiem": backend GỘP một lệnh multipart `taoKiemDotXuat` — mẻ + lỗi +
//     ảnh cùng lúc; khác nhau ở `loai` gửi lên và ở chỗ điểm kiểm ĐÃ BIẾT việc cần kiểm (mở từ bàn
//     điểm kiểm) nên không có bước chọn tổ/việc. Xem `docs/design-kcs-theo-cong-doan.md` mục 4.
import { useEffect, useRef, useState } from "react";
import {
  ApiError, api,
  type SxDiemKiemItem, type SxKcsBatchChiTiet, type SxKcsChiTiet, type SxHoTroUngVien,
  type SxTeam, type SxWorkItem,
} from "../../api/client";
import { ChipKhuon, ChipLoaiBuoc } from "../../components/ChipBuoc";
import { useAuth } from "../../auth/useAuth";
import { Drawer } from "../danh-muc/components/Drawer";
import { Select, type SelectOption } from "../../components/Select";
import { num } from "../keHoachSxShared";
import { nhanChang, nhanDonVi } from "../lsxBuoc";
import { useNapTenDonVi } from "../tenDonVi";

export const KCS_TRANG_THAI_GUI_KHO_LABEL: Record<string, string> = {
  chua_gui: "Chưa gửi kho",
  dang_cho: "Đang chờ kho xác nhận",
  da_nhap: "Đã nhập kho",
  khong_ap_dung: "Không áp dụng",
};

type SavedInfo = { kcsBatchId: number; version: number; ctaEligible: boolean; soDat: number; donVi: string };

/** Tóm tắt một lượt vừa lưu — trả lên `ThucHienKcsPage` để cập nhật "Kết quả đã ghi" ngay, không
 * đợi vòng refetch. Cần cho `loai="dot_xuat"` vì KHÔNG có endpoint liệt kê lịch sử đột xuất theo tổ
 * KCS (việc bị kiểm thuộc tổ KHÁC) — trang cha giữ những dòng này ở state phiên (mất khi tải lại). */
export interface KcsSavedRow {
  kcsBatchId: number;
  congViecId: number;
  luc: string;
  soDat: number;
  soLoi: number;
  loai: "routing" | "dot_xuat" | "diem_kiem";
  donVi: string;
  maNguon: string;
  tenNguon: string;
  tenCongDoan: string;
}

type Props =
  | {
      mode: "ghi";
      teamId: number;
      tenTo: string;
      item: SxWorkItem;
      conCho: number;
      onClose: () => void;
      onSaved: (row: KcsSavedRow) => void;
    }
  | {
      mode: "dot_xuat";
      teamId: number;
      tenTo: string;
      onClose: () => void;
      onSaved: (row: KcsSavedRow) => void;
    }
  | {
      /** Điểm kiểm theo công đoạn: mở từ bàn KCS, việc thuộc tổ KHÁC và đã mang sẵn checklist —
       *  không gọi lại `kcsChiTiet`, không có bước chọn tổ/việc. */
      mode: "diem_kiem";
      /** Tổ KCS ĐI KIỂM (ghi vào `kcs_department_id`) — KHÁC `item.to_id` là tổ bị kiểm. */
      teamId: number;
      tenTo: string;
      item: SxDiemKiemItem;
      onClose: () => void;
      onSaved: (row: KcsSavedRow) => void;
    }
  | {
      mode: "xem";
      teamId: number;
      tenTo: string;
      item: SxWorkItem;
      batch: SxKcsBatchChiTiet;
      onClose: () => void;
    };

export function KcsResultDrawer(props: Props) {
  const { token } = useAuth();
  // `don_vi*` của tầng sản xuất là MÃ danh mục (`to`, `kem`) — nạp bảng tên rồi bọc `nhanDonVi`
  // ở từng chỗ bày ra. Drawer mở được từ nhiều màn nên nạp NGAY TẠI ĐÂY, đừng trông vào màn cha.
  useNapTenDonVi();

  // ---- Bước chọn việc (chỉ mode="dot_xuat", trước khi có công việc) ----
  const [teams, setTeams] = useState<SxTeam[] | null>(null);
  const [pickedTeam, setPickedTeam] = useState<SxTeam | null>(null);
  const [pickerItems, setPickerItems] = useState<SxWorkItem[] | null>(null);
  const [pickerQ, setPickerQ] = useState("");
  const [pickedItem, setPickedItem] = useState<SxWorkItem | null>(null);

  useEffect(() => {
    if (props.mode !== "dot_xuat" || !token) return;
    api.sanXuat.teams(token).then((r) => setTeams(r.teams)).catch(() => setTeams([]));
  }, [props.mode, token]);

  useEffect(() => {
    if (!pickedTeam || !token) { setPickerItems(null); return; }
    let alive = true;
    api.sanXuat.workItems(token, pickedTeam.id, "production")
      .then((r) => { if (alive) setPickerItems(r.cong_viec.filter((c) => c.trang_thai === "running" || c.trang_thai === "paused")); })
      .catch(() => { if (alive) setPickerItems([]); });
    return () => { alive = false; };
  }, [pickedTeam, token]);

  const item: SxWorkItem | null = props.mode === "dot_xuat" ? pickedItem : props.item;

  // ---- Ngữ cảnh (checklist §Ruling 6, chỉ mode="ghi") ----
  const [chiTiet, setChiTiet] = useState<SxKcsChiTiet | null>(null);
  useEffect(() => {
    if (props.mode !== "ghi" || !token) return;
    let alive = true;
    api.sanXuat.kcsChiTiet(token, props.item.id).then((r) => { if (alive) setChiTiet(r); }).catch(() => { if (alive) setChiTiet(null); });
    return () => { alive = false; };
  }, [props.mode, props.mode === "ghi" ? props.item.id : null, token]);
  // Điểm kiểm nhận checklist THEO THẺ VIỆC từ bàn KCS (đã gói sẵn trong một lượt tải); chỉ
  // mode="ghi" mới phải gọi `kcsChiTiet`. Đột xuất không có snapshot tiêu chí nào để bám.
  const checklist =
    props.mode === "diem_kiem" ? props.item.checklist : chiTiet?.checklist ?? [];

  // ---- Khối 3: Đạt / Lỗi ----
  // Điểm kiểm không có "còn chờ" theo bàn giao (không gác theo số bàn giao) — mốc gợi ý là mục
  // tiêu RA của chính bước đó.
  const conChoBanDau =
    props.mode === "ghi" ? props.conCho
      : props.mode === "diem_kiem" ? props.item.so_luong_ra ?? props.item.so_luong_vao ?? 0
        : item?.so_luong_vao ?? 0;
  const [soDat, setSoDat] = useState<string>("");
  const [soLoi, setSoLoi] = useState<string>("0");
  const daKhoiTaoSoDat = useRef(false);
  useEffect(() => {
    // Nạp mặc định soDat = còn chờ MỘT LẦN khi việc/mode xác định (không ghi đè lúc người dùng đang gõ).
    if (daKhoiTaoSoDat.current) return;
    if (props.mode === "dot_xuat" && !item) return;
    setSoDat(String(conChoBanDau || 0));
    daKhoiTaoSoDat.current = true;
  }, [props.mode, item, conChoBanDau]);
  const nSoDat = Number(soDat) || 0;
  const nSoLoi = Number(soLoi) || 0;

  // ---- Khối 2: checklist trả lời ----
  const [dat, setDat] = useState<Record<number, boolean>>({});
  const [ghiChuTc, setGhiChuTc] = useState<Record<number, string>>({});

  // ---- Khối 4: lỗi (chỉ hiện khi soLoi > 0) ----
  const [moTaLoi, setMoTaLoi] = useState("");
  // `to_chiu_id` là ID PHÒNG BAN (không phải người) — gom từ ứng viên hỗ trợ chéo, dedupe theo
  // `to_id`, ĐÚNG cách `toChiuOpts` của ThucHienSxPage.tsx đang làm (đọc lại làm tham khảo).
  const [hoTroUngVien, setHoTroUngVien] = useState<SxHoTroUngVien[]>([]);
  const [toChiuId, setToChiuId] = useState<number | null>(null);
  const [files, setFiles] = useState<File[]>([]);

  useEffect(() => {
    if (nSoLoi <= 0 || !token) return;
    api.sanXuat.hoTroUngVien(token, props.teamId).then((r) => setHoTroUngVien(r.nhan_vien)).catch(() => setHoTroUngVien([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nSoLoi > 0, token, props.teamId]);

  const toChiuOpts: SelectOption<number | null>[] = (() => {
    const seen = new Map<number, string>();
    for (const c of hoTroUngVien) {
      if (c.to_id != null && c.to_id !== props.teamId && !seen.has(c.to_id)) seen.set(c.to_id, c.to_ten ?? `Tổ #${c.to_id}`);
    }
    return [...seen.entries()].map(([id, ten]) => ({ value: id, label: ten }));
  })();

  // ---- Lưu ----
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<SavedInfo | null>(null);
  const [ctaSaving, setCtaSaving] = useState(false);
  const [ctaDone, setCtaDone] = useState<string | null>(null);

  async function luuKetQua() {
    if (!token || saving) return;
    setSaving(true);
    setError(null);
    try {
      const now = new Date().toISOString();
      const donVi = item?.don_vi_ra ?? item?.don_vi_vao ?? undefined;
      const checklistKetQua = checklist
        .filter((tc) => dat[tc.thu_tu] !== undefined)
        .map((tc) => ({ thu_tu: tc.thu_tu, dat: !!dat[tc.thu_tu], ghi_chu: ghiChuTc[tc.thu_tu] || null }));

      if (props.mode === "dot_xuat" || props.mode === "diem_kiem") {
        if (!item) throw new Error("Chưa chọn việc cần kiểm.");
        const loai = props.mode === "diem_kiem" ? "diem_kiem" : "dot_xuat";
        const r = await api.sanXuat.taoKiemDotXuat(token, {
          cong_viec_id: item.id,
          kcs_department_id: props.teamId,
          loai,
          bat_dau: now, ket_thuc: now,
          so_luong_nhan: nSoDat + nSoLoi, so_luong_dat: nSoDat, so_luong_khong_dat: nSoLoi,
          don_vi: donVi,
          checklist_ket_qua: checklistKetQua.length ? checklistKetQua : null,
          loi_mo_ta: nSoLoi > 0 ? moTaLoi.trim() || null : null,
          to_chiu_id: nSoLoi > 0 ? toChiuId : null,
          files: nSoLoi > 0 ? files : [],
        });
        setSaved({ kcsBatchId: r.kcs_batch_id, version: r.version, ctaEligible: false, soDat: nSoDat, donVi: donVi ?? "" });
        props.onSaved({
          kcsBatchId: r.kcs_batch_id, congViecId: item.id, luc: now,
          soDat: nSoDat, soLoi: nSoLoi, loai, donVi: donVi ?? "",
          maNguon: item.nguon_ma, tenNguon: item.nguon_ten, tenCongDoan: item.ten_cong_doan,
        });
      } else if (props.mode === "ghi") {
        const cv = props.item;
        const r = await api.sanXuat.taoBatchKcs(token, cv.id, {
          bat_dau: now, ket_thuc: now,
          so_luong_nhan: nSoDat + nSoLoi, so_luong_dat: nSoDat, so_luong_khong_dat: nSoLoi,
          don_vi: donVi,
          checklist_ket_qua: checklistKetQua.length ? checklistKetQua : null,
        });
        if (nSoLoi > 0) {
          await api.sanXuat.ghiLoiKcs(token, r.kcs_batch_id, {
            to_chiu_id: toChiuId,
            so_luong: nSoLoi,
            mo_ta: moTaLoi.trim() || null,
            don_vi: donVi ?? null,
            files,
          });
        }
        const ctaEligible = !!cv.la_kcs_cuoi && nSoDat > 0;
        setSaved({ kcsBatchId: r.kcs_batch_id, version: r.version, ctaEligible, soDat: nSoDat, donVi: donVi ?? "" });
        props.onSaved({
          kcsBatchId: r.kcs_batch_id, congViecId: cv.id, luc: now,
          soDat: nSoDat, soLoi: nSoLoi, loai: "routing", donVi: donVi ?? "",
          maNguon: cv.nguon_ma, tenNguon: cv.nguon_ten, tenCongDoan: cv.ten_cong_doan,
        });
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Không lưu được kết quả KCS.");
    } finally {
      setSaving(false);
    }
  }

  async function guiKho() {
    if (!token || !saved || ctaSaving) return;
    setCtaSaving(true);
    try {
      await api.sanXuat.taoYeuCauKhoMotNut(token, saved.kcsBatchId);
      setCtaDone("Đã gửi yêu cầu nhập kho.");
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setCtaDone("Không còn số đạt chưa gửi (có thể đã gửi ở lượt trước).");
      } else {
        setCtaDone(e instanceof ApiError ? e.message : "Không gửi được yêu cầu nhập kho.");
      }
    } finally {
      setCtaSaving(false);
    }
  }

  const title =
    props.mode === "xem" ? "Chi tiết kết quả KCS"
      : props.mode === "dot_xuat" ? "Kiểm đột xuất"
        : props.mode === "diem_kiem" ? "Ghi điểm kiểm công đoạn"
          : "Ghi kết quả KCS";

  // ================= mode="xem": chỉ đọc =================
  if (props.mode === "xem") {
    const b = props.batch;
    return (
      <Drawer title={title} onClose={props.onClose}>
        <div className="rc-drawer__body">
          <KhoiNguCanh item={props.item} tenTo={props.tenTo} conCho={null} />
          <div className="kcs-drawer__block">
            <h3>Kết quả</h3>
            <div className="kcs-drawer__soluong">
              <label>Số đạt<input type="number" value={b.so_luong_dat} disabled /></label>
              <label>Số lỗi<input type="number" value={b.so_luong_khong_dat} disabled /></label>
            </div>
            <div className="kcs-drawer__ctx-row">
              Người ghi: {b.nguoi_ghi ?? "—"} · Trạng thái gửi kho:{" "}
              {KCS_TRANG_THAI_GUI_KHO_LABEL[b.trang_thai_gui_kho] ?? b.trang_thai_gui_kho}
            </div>
          </div>
          {b.loi.length > 0 && (
            <div className="kcs-drawer__block">
              <h3>Lỗi đã ghi</h3>
              {b.loi.map((l) => (
                <div key={l.id} className="kcs-drawer__loi" style={{ marginBottom: 8 }}>
                  <strong>{l.mo_ta || "Lỗi"}</strong>
                  {l.so_luong > 0 && <span> — {num(l.so_luong)} {nhanDonVi(l.don_vi)}</span>}
                  {l.anh.length > 0 && (
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
                      {l.anh.map((a) => (
                        <a key={a.id} href={a.file_url} target="_blank" rel="noreferrer">
                          <img src={a.file_url} alt={a.file_name} style={{ width: 64, height: 64, objectFit: "cover", borderRadius: 4, border: "1px solid var(--rule)" }} />
                        </a>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </Drawer>
    );
  }

  // ================= mode="dot_xuat": bước chọn việc trước =================
  if (props.mode === "dot_xuat" && !item) {
    return (
      <Drawer title={title} onClose={props.onClose}>
        <div className="rc-drawer__body">
          <div className="kcs-picker">
            {!pickedTeam ? (
              <>
                <p className="kcs-picker__hint">Chọn tổ đang có việc cần kiểm:</p>
                <div className="kcs-picker__list">
                  {(teams ?? []).map((t) => (
                    <button key={t.id} type="button" className="kcs-picker__row" onClick={() => setPickedTeam(t)}>
                      <span className="kcs-picker__row-title">{t.ten}</span>
                      <span className="kcs-picker__row-sub">Mã {t.ma}</span>
                    </button>
                  ))}
                  {teams != null && teams.length === 0 && <p className="rc__empty-text">Không có tổ nào.</p>}
                  {teams == null && <p className="rc__empty-text">Đang tải…</p>}
                </div>
              </>
            ) : (
              <>
                <p className="kcs-picker__hint">
                  Tổ <strong>{pickedTeam.ten}</strong> — chọn việc đang chạy/tạm dừng:{" "}
                  <button type="button" className="btn btn--ghost" onClick={() => { setPickedTeam(null); setPickerItems(null); }}>Đổi tổ</button>
                </p>
                <input
                  type="text" placeholder="Tìm theo mã LSX/đơn/công đoạn" value={pickerQ}
                  onChange={(e) => setPickerQ(e.target.value)}
                  style={{ height: 34, border: "1px solid var(--rule)", borderRadius: 4, padding: "0 10px" }}
                />
                <div className="kcs-picker__list">
                  {(pickerItems ?? [])
                    .filter((c) => !pickerQ.trim() || `${c.nguon_ma} ${c.nguon_ten} ${c.ten_cong_doan}`.toLowerCase().includes(pickerQ.trim().toLowerCase()))
                    .map((c) => (
                      <button key={c.id} type="button" className="kcs-picker__row" onClick={() => setPickedItem(c)}>
                        <span className="kcs-picker__row-title">{c.nguon_ma} · {c.ten_cong_doan}</span>
                        <span className="kcs-picker__row-sub">{c.nguon_ten} — {c.trang_thai === "running" ? "Đang chạy" : "Tạm dừng"}</span>
                      </button>
                    ))}
                  {pickerItems != null && pickerItems.length === 0 && <p className="rc__empty-text">Tổ này không có việc đang chạy/tạm dừng.</p>}
                  {pickerItems == null && <p className="rc__empty-text">Đang tải…</p>}
                </div>
              </>
            )}
          </div>
        </div>
      </Drawer>
    );
  }

  if (!item) return null; // vệ tinh cho TS — không xảy ra thực tế (đã lọc ở trên)

  // ================= 4 khối ghi kết quả (mode="ghi" | "dot_xuat" đã chọn việc) =================
  return (
    <Drawer
      title={title}
      onClose={props.onClose}
      foot={!saved ? (
        <button type="button" className="btn btn--accent" onClick={luuKetQua} disabled={saving}>
          {saving ? "Đang lưu…" : "Lưu kết quả"}
        </button>
      ) : undefined}
    >
      <div className="rc-drawer__body">
        <KhoiNguCanh
          item={item}
          tenTo={
            props.mode === "dot_xuat" ? pickedTeam?.ten ?? ""
              : props.mode === "diem_kiem" ? props.item.to_ten
                : props.tenTo
          }
          nguoi={props.mode === "diem_kiem" ? props.item.nguoi : []}
          conCho={saved ? null : conChoBanDau}
        />

        {saved ? (
          <div className="kcs-drawer__block">
            <p>Đã lưu kết quả: <b>{num(saved.soDat)}</b> đạt · <b>{num(nSoLoi)}</b> lỗi.</p>
            {saved.ctaEligible && (
              <div className="kcs-drawer__cta">
                <span className="kcs-drawer__cta-text">
                  {ctaDone ?? `Đây là bước KCS cuối — có ${num(saved.soDat)} ${nhanDonVi(saved.donVi)} đạt sẵn sàng nhập kho.`}
                </span>
                {!ctaDone && (
                  <button type="button" className="btn btn--accent" onClick={guiKho} disabled={ctaSaving}>
                    {ctaSaving ? "Đang gửi…" : `Tạo yêu cầu nhập kho (${num(saved.soDat)})`}
                  </button>
                )}
              </div>
            )}
          </div>
        ) : (
          <>
            {props.mode !== "dot_xuat" && checklist.length > 0 && (
              <div className="kcs-drawer__block">
                <h3>Checklist</h3>
                {checklist.map((tc) => (
                  <div className="kcs-check-row" key={tc.thu_tu}>
                    <label className="kcs-check-row__label">
                      <input
                        type="checkbox"
                        checked={dat[tc.thu_tu] === true}
                        ref={(el) => { if (el) el.indeterminate = dat[tc.thu_tu] === undefined; }}
                        onChange={(e) => setDat((d) => ({ ...d, [tc.thu_tu]: e.target.checked }))}
                      />
                      {tc.ten ?? tc.ma ?? `Tiêu chí #${tc.thu_tu}`}
                      {tc.bat_buoc && <span className="kcs-check-row__req">*</span>}
                    </label>
                    <input
                      type="text" className="kcs-check-row__note" placeholder="Ghi chú (nếu có)"
                      value={ghiChuTc[tc.thu_tu] ?? ""}
                      onChange={(e) => setGhiChuTc((g) => ({ ...g, [tc.thu_tu]: e.target.value }))}
                    />
                  </div>
                ))}
              </div>
            )}

            <div className="kcs-drawer__block">
              <h3>Số lượng</h3>
              <div className="kcs-drawer__soluong">
                <label>Số đạt
                  <input type="number" min={0} value={soDat} onChange={(e) => setSoDat(e.target.value)} />
                </label>
                <label>Số lỗi
                  <input type="number" min={0} value={soLoi} onChange={(e) => setSoLoi(e.target.value)} />
                </label>
                {conChoBanDau > 0 && nSoDat + nSoLoi !== conChoBanDau && (
                  <span className="kcs-drawer__hint">
                    Đạt + Lỗi ({num(nSoDat + nSoLoi)}) khác số còn chờ ({num(conChoBanDau)}) — vẫn lưu được, backend sẽ kiểm lại.
                  </span>
                )}
              </div>
            </div>

            {nSoLoi > 0 && (
              <div className="kcs-drawer__block kcs-drawer__loi">
                <div className="kcs-drawer__field">
                  <label>Mô tả lỗi</label>
                  <textarea value={moTaLoi} onChange={(e) => setMoTaLoi(e.target.value)} placeholder="Mô tả ngắn (tuỳ chọn)" />
                </div>
                <div className="kcs-drawer__field">
                  <label>Tổ liên đới (tuỳ chọn)</label>
                  <Select
                    value={toChiuId}
                    options={toChiuOpts}
                    onChange={setToChiuId}
                    placeholder="— Chưa xác định —"
                  />
                </div>
                <div className="kcs-drawer__field">
                  <label>Ảnh bằng chứng (bắt buộc ≥1)</label>
                  <input
                    type="file" accept="image/*" multiple className="kcs-drawer__anh-input"
                    onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
                  />
                  {files.length > 0 && <p className="kcs-drawer__anh-hint">Đã chọn {files.length} ảnh.</p>}
                  {files.length === 0 && <p className="kcs-drawer__anh-hint">Cần ít nhất 1 ảnh khi có lỗi.</p>}
                </div>
              </div>
            )}

            {error && (
              <div className="banner banner--error" role="alert">
                <span>{error}</span>
              </div>
            )}
          </>
        )}
      </div>
    </Drawer>
  );
}

function KhoiNguCanh(
  { item, tenTo, conCho, nguoi = [] }:
  { item: SxWorkItem; tenTo: string; conCho: number | null; nguoi?: string[] },
) {
  return (
    <div className="kcs-drawer__ctx">
      <div className="kcs-drawer__ctx-row"><strong>{item.nguon_ma}</strong> — {item.nguon_ten}</div>
      <div className="kcs-drawer__ctx-row">
        Công đoạn: {item.ten_cong_doan} · Tổ: {tenTo} · Máy: {item.may || "—"}
        <ChipLoaiBuoc loai_buoc={item.loai_buoc} nha_cung_cap={item.nha_cung_cap} />
        <ChipKhuon can_khuon={!!item.khuon} khuon={{ ...(item.khuon ?? {}), da_nhan: item.khuon_da_nhan }} />
      </div>
      {/* Cột "TÊN THỢ LÀM" của tờ ISO — đọc từ thẻ việc, KCS không phải gõ lại. */}
      {nguoi.length > 0 && (
        <div className="kcs-drawer__ctx-row">Thợ làm: {nguoi.join(", ")}</div>
      )}
      {conCho != null && (
        <div className="kcs-drawer__ctx-row">Còn chờ: <strong>{num(conCho)} {nhanChang(item.don_vi_vao)}</strong></div>
      )}
    </div>
  );
}
