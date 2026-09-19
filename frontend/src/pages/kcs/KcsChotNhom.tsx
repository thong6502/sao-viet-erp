// CHỐT NHÓM ở màn KCS — cửa vào của "Đóng thiếu nhóm" (§13.3): nhóm làm xong mà KCS đạt hụt mục
// tiêu (960/1.000), hoặc còn việc dở không làm nữa, phải có người đóng lại, nếu không lệnh treo.
// CHỈ trưởng phòng ban "Tổ KCS" (máy chủ gác `gate_truong_kcs`). Nhóm đạt đủ mục tiêu thì tự đóng đủ.
//
// Hiển thị RÚT GỌN 18/09/2026: thôi bày checklist 4 điều kiện (người đọc không hiểu "toàn vẹn" là
// gì). Nay là một con số "KCS đạt X / mục tiêu" + MỘT câu nói nhóm đang ở đâu; hai điều kiện toàn
// vẹn (bàn giao khớp · KCS kiểm hết hàng tổ đã làm) chỉ hiện khi chúng CHẶN đóng thiếu. Logic cổng
// không đổi — vẫn đọc nguyên `dieu-kien-dong` của máy chủ.
//
// KCS theo lệnh (mg 0306): khối này nằm dưới CHUỖI CÔNG ĐOẠN của một lệnh, nên nhận thẳng nhóm của
// lệnh đó — không còn tự gom nhóm từ danh sách bước KCS của một tổ.
import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type SxDongNhomDieuKien } from "../../api/client";
import { useAuth } from "../../auth/useAuth";
import { Icon } from "../../components/Icons";
import { num } from "../keHoachSxShared";

export type ChotNhomTone = "ok" | "cho" | "dong";

/** Nhóm đang ở đâu, nói bằng MỘT câu. `lyDoChan` = vì sao chưa đóng thiếu được (rỗng khi được). */
export function tomTatChotNhom(dk: SxDongNhomDieuKien): {
  tone: ChotNhomTone;
  cau: string;
  goiY: string | null;
  lyDoChan: string[];
} {
  const theo = (ma: string) => dk.dieu_kien.find((d) => d.ma === ma);
  const daDat = num(dk.da_dat ?? 0);
  const chot = dk.muc_tieu != null ? `${daDat} / ${num(dk.muc_tieu)}` : daDat;

  if (dk.trang_thai === "closed_full") {
    return { tone: "ok", cau: "Đã đóng đủ — đủ hàng để giao.", goiY: null, lyDoChan: [] };
  }
  if (dk.trang_thai === "closed_short") {
    return { tone: "dong", cau: `Đã đóng thiếu — chốt giao ${chot}.`, goiY: null, lyDoChan: [] };
  }
  if (dk.du_dong_du) {
    return { tone: "ok", cau: "Đủ hàng, mọi công đoạn đã xong — nhóm tự đóng đủ.", goiY: null, lyDoChan: [] };
  }

  const viecDo = theo("moi_viec_xong");
  const conViec = viecDo && !viecDo.dat && viecDo.chi_tiet ? viecDo.chi_tiet : null;
  const duHang = theo("dat_muc_tieu")?.dat ?? false;
  const cau = dk.muc_tieu == null
    ? "Công đoạn cuối chưa có số mục tiêu nên nhóm không tự đóng được."
    : duHang
      ? `Đủ hàng rồi${conViec ? `, nhưng ${conViec}` : ""} — xong hết thì nhóm tự đóng đủ.`
      : `Chưa đủ hàng${conViec ? `, ${conViec}` : ""}.`;

  const lyDoChan: string[] = [];
  for (const d of dk.dieu_kien) {
    if (d.dat || d.ma === "moi_viec_xong" || d.ma === "dat_muc_tieu") continue;
    if (d.ma === "khong_lech_ban_giao") {
      lyDoChan.push("Có công đoạn bàn giao chưa khớp số — tổ phải xử lý ở bàn tổ trước.");
    } else if (d.ma === "kcs_cuoi_kiem_het") {
      lyDoChan.push(`KCS chưa kiểm hết hàng tổ đã làm ở công đoạn cuối${d.chi_tiet ? ` (${d.chi_tiet})` : ""}.`);
    } else {
      lyDoChan.push(`${d.ten}${d.chi_tiet ? ` (${d.chi_tiet})` : ""}.`);
    }
  }

  return {
    tone: "cho",
    cau,
    goiY: dk.du_dong_thieu
      ? `Nếu không làm tiếp nữa, trưởng tổ KCS bấm "Đóng thiếu" để chốt giao ${chot}.`
      : null,
    lyDoChan,
  };
}

export function KcsChotNhom({
  nhomId, nhan, canDong, eventTick, onDone,
}: {
  nhomId: number;
  nhan: string;
  /** Đóng thiếu nhóm — trưởng phòng ban "Tổ KCS". */
  canDong: boolean;
  /** Bump khi có sự kiện SX (SSE) — tải lại điều kiện của nhóm. */
  eventTick?: number;
  onDone: () => void;
}) {
  const { token } = useAuth();
  const [dk, setDk] = useState<SxDongNhomDieuKien | null>(null);
  const [loi, setLoi] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [xacNhan, setXacNhan] = useState(false);

  const tai = useCallback(() => {
    if (!token) return;
    api.sanXuat.dieuKienDongNhom(token, nhomId)
      .then((r) => { setDk(r); setLoi(null); })
      .catch((e) => setLoi(e instanceof ApiError ? e.message : "Không đọc được tình trạng nhóm."));
  }, [token, nhomId]);

  useEffect(() => { tai(); }, [tai, eventTick]);

  async function dongThieu() {
    if (!token || !dk || busy) return;
    setBusy(true);
    setLoi(null);
    try {
      await api.sanXuat.dongThieu(token, dk.nhom_id, { expected_version: dk.version });
      setXacNhan(false);
      tai();
      onDone();
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không đóng thiếu được.");
    } finally {
      setBusy(false);
    }
  }

  const tt = dk ? tomTatChotNhom(dk) : null;
  const pct = dk?.muc_tieu ? Math.min(100, ((dk.da_dat ?? 0) / dk.muc_tieu) * 100) : null;
  const moDong = dk != null && tt?.tone === "cho" && dk.du_dong_thieu && canDong;

  return (
    <section className="kcs-section">
      <h2>Chốt nhóm thành phẩm <span className="kcs-chot__sl">{nhan}</span></h2>
      <div className="kcs-chot">
        {loi && <div className="banner banner--error" role="alert"><span>{loi}</span></div>}
        {dk == null || tt == null ? (
          !loi && <p className="kcs-chot__phu">Đang tải…</p>
        ) : (
          <>
            <div className="kcs-chot__so">
              <span>KCS đạt <b>{num(dk.da_dat ?? 0)}</b>{dk.muc_tieu != null && <> / {num(dk.muc_tieu)}</>}</span>
              {dk.con_thieu != null && dk.con_thieu > 0 && (
                <span className="kcs-chot__thieu">Còn thiếu <b>{num(dk.con_thieu)}</b></span>
              )}
            </div>
            {pct != null && (
              <div className="kcs-chot__ray" aria-hidden="true">
                <span className={`kcs-chot__day kcs-chot__day--${tt.tone}`} style={{ width: `${pct}%` }} />
              </div>
            )}

            <p className={`kcs-chot__cau kcs-chot__cau--${tt.tone}`}>
              <Icon name={tt.tone === "ok" ? "check" : tt.tone === "dong" ? "packageCheck" : "clock"} size={14} />
              <span>{tt.cau}</span>
            </p>
            {tt.goiY && <p className="kcs-chot__phu">{tt.goiY}</p>}
            {tt.lyDoChan.length > 0 && (
              <div className="kcs-chot__chan">
                <span>Chưa đóng thiếu được vì:</span>
                <ul>{tt.lyDoChan.map((l) => <li key={l}>{l}</li>)}</ul>
              </div>
            )}

            {moDong && (!xacNhan ? (
              <div className="kcs-chot__nut">
                <button type="button" className="btn btn--ghost btn--sm" onClick={() => setXacNhan(true)} disabled={busy}>
                  <Icon name="packageCheck" size={13} /> Đóng thiếu
                </button>
              </div>
            ) : (
              <div className="kcs-chot__xn">
                <p>
                  Chốt giao <b>{num(dk.da_dat ?? 0)}</b>{dk.muc_tieu != null && <> / {num(dk.muc_tieu)}</>} và
                  đóng nhóm? Sale và Kế hoạch SX sẽ được báo ngay.
                </p>
                <div className="kcs-chot__nut">
                  <button type="button" className="btn btn--ghost btn--sm" onClick={() => setXacNhan(false)} disabled={busy}>Huỷ</button>
                  <button type="button" className="btn btn--accent btn--sm" onClick={dongThieu} disabled={busy}>
                    <Icon name="check" size={13} /> {busy ? "Đang đóng…" : "Xác nhận đóng thiếu"}
                  </button>
                </div>
              </div>
            ))}
          </>
        )}
      </div>
    </section>
  );
}
