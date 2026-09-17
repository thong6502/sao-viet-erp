// Ô "Đổi máy" của ngăn kéo bàn tổ. Danh sách máy do máy chủ dựng (`/work-items/{id}/may-doi`):
// chỉ máy làm được công đoạn của việc (luật chung với Xếp lịch — `may_ngoai_cong_doan`), kèm TÌNH
// TRẠNG lúc này của từng máy, cùng nguồn cột Trạng thái màn Thiết bị & Máy móc.
//
// Tách khỏi `ThsxDrawer` vì tự gọi API: chỉ mount khi mở ô, nên danh sách luôn nạp lại mỗi lần mở
// (máy vừa hỏng/vừa nhận lệnh khác phải hiện đúng lúc chọn), và ngăn kéo vẫn không cần phiên đăng nhập.
import { useEffect, useMemo, useState } from "react";
import { api, ApiError, type SxMayDoiOut } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { Select, type SelectOption } from "../components/Select";

// Thứ tự nhóm: máy nhận việc được lên đầu; có phiếu sửa vẫn chạy được nên đứng ngay sau; máy hỏng
// cuối cùng. Mã lạ (máy chủ thêm trạng thái mới) xếp trước nhóm hỏng để không bị giấu.
const THU_TU_TT = ["ranh", "co_phieu_sua", "dang_chay", "bao_tri", "khoa", "may_dung"];
function thuTu(tt: string): number {
  const i = THU_TU_TT.indexOf(tt);
  return i < 0 ? THU_TU_TT.length - 1.5 : i;
}

interface Props {
  congViecId: number;
  mayHienTaiId: number | null;
  tenCongDoan: string;
  busy: boolean;
  onDoi: (mayId: number, lyDo?: string | null) => Promise<boolean>;
  onClose: () => void;
}

export function ThsxDoiMay({ congViecId, mayHienTaiId, tenCongDoan, busy, onDoi, onClose }: Props) {
  const { token } = useAuth();
  const [ds, setDs] = useState<SxMayDoiOut | null>(null);
  const [loi, setLoi] = useState<string | null>(null);
  const [mayId, setMayId] = useState<number | "">("");
  const [lyDo, setLyDo] = useState("");

  useEffect(() => {
    if (!token) return;
    let bo = false;
    setDs(null);
    setLoi(null);
    api.sanXuat
      .mayDoi(token, congViecId)
      .then((r) => { if (!bo) setDs(r); })
      .catch((e) => {
        if (bo) return;
        setLoi(e instanceof ApiError && e.isNetwork ? "Mất kết nối tới máy chủ" : "Không nạp được danh sách máy");
      });
    return () => { bo = true; };
  }, [token, congViecId, mayHienTaiId]);

  const opts = useMemo<SelectOption<number | "">[]>(
    () => [...(ds?.items ?? [])]
      .sort((a, b) => thuTu(a.trang_thai) - thuTu(b.trang_thai) || a.ma.localeCompare(b.ma, "vi"))
      .map((m) => ({
        value: m.id,
        label: m.ten ? `${m.ma} — ${m.ten}` : m.ma,
        group: m.nhan,
        sub: m.chi_tiet ?? undefined,
        search: `${m.nhan} ${m.loai_may ?? ""}`,
      })),
    [ds],
  );
  const chon = ds?.items.find((m) => m.id === mayId) ?? null;

  async function xacNhan() {
    if (mayId === "") return;
    if (await onDoi(mayId, lyDo.trim() || null)) onClose();
  }

  return (
    <div className="thsx-x-form thsx-x-form--sub" style={{ marginTop: "12px" }}>
      <div className="thsx-x-grid2">
        <div className="thsx-x-fld">
          <span className="thsx-x-fld__l">Máy mới</span>
          <Select portal searchable value={mayId} options={opts} onChange={setMayId}
            disabled={!ds || opts.length === 0} ariaLabel="Máy mới"
            placeholder={loi ? "—" : !ds ? "Đang nạp máy…" : opts.length === 0 ? "Không có máy đổi được" : "— Chọn máy —"}
            searchPlaceholder="Gõ mã, tên hoặc tình trạng máy…" className="thsx-x-seltrig" />
        </div>
        <label className="thsx-x-fld">
          <span className="thsx-x-fld__l">Lý do (không bắt buộc)</span>
          <input className="thsx-x-in" value={lyDo} onChange={(e) => setLyDo(e.target.value)} placeholder="Máy hỏng, đổi ca…" />
        </label>
      </div>
      {loi ? (
        <p className="thsx-x-hint thsx-x-hint--err" style={{ marginTop: "6px" }}>{loi}</p>
      ) : ds && (
        <p className="thsx-x-hint" style={{ marginTop: "6px" }}>
          {ds.theo_cong_doan
            ? <>Chỉ hiện máy khai cho công đoạn <b>{tenCongDoan}</b>.</>
            : <>Công đoạn <b>{tenCongDoan}</b> chưa khai máy — đang hiện mọi máy còn dùng.</>}
        </p>
      )}
      {/* Chỉ cảnh báo, không chặn: tổ có thể biết điều máy chủ chưa biết (máy đã sửa xong mà phiếu
          chưa đóng, lệnh kia đang tạm dừng…). */}
      {chon && chon.trang_thai !== "ranh" && (
        <p className="thsx-x-hint thsx-x-hint--err" style={{ marginTop: "4px" }}>
          <b>{chon.ma}</b> đang ở tình trạng: {chon.nhan}{chon.chi_tiet ? ` · ${chon.chi_tiet}` : ""}
        </p>
      )}
      <div className="thsx-run" style={{ marginTop: "8px" }}>
        <Button variant="ghost" onClick={onClose}>Huỷ</Button>
        <Button variant="accent" onClick={xacNhan} disabled={busy || mayId === ""}>Xác nhận đổi máy</Button>
      </div>
    </div>
  );
}
