// THẺ QUY CÁCH CHẠY MÁY — dùng chung ngăn chi tiết của bàn tổ (`ThsxDrawer`) và form kiểm của KCS
// (`KcsKiemForm`): cùng ảnh chụp `quy_cach_json` lúc phát hành, vẽ cùng MỘT hình để thợ làm và KCS
// đối chiếu nhìn đúng một thứ.
import type { SxQuyCachThe } from "../api/client";
import { Icon } from "../components/Icons";
import { MucInHang } from "../components/MucIn";
import { nhanCachIn } from "./keHoachSxShared";
// Khung `.khsx-kv` của khối Mực in mượn từ màn lệnh — nạp tường minh, đừng trông vào AppShell.
import "./ke-hoach-sx.css";
import "./thuc-hien-sx.css";

// Thứ tự đọc của người đứng máy: giấy → khổ → cách in/màu/kẽm → con/tờ → SL đặt (§6). Server BỎ
// HẲN khoá không có số, nên bảng này chỉ là NHÃN + đuôi đơn vị; hàng nào thiếu thì không vẽ. Khoá
// `ghi_chu_ky_thuat` là chữ nên tách ra khỏi bảng (vẽ thành đoạn riêng bên dưới); mực từng mặt là
// tập mã nên vẽ bằng khối chip của màn lệnh, cũng nằm ngoài bảng.
const QUY_CACH_DONG: [keyof SxQuyCachThe, string, string][] = [
  ["giay", "Giấy", ""],
  ["dinh_luong", "Định lượng", " gsm"],
  ["kho_nguyen", "Khổ giấy nguyên", " mm"],
  ["kho_in", "Khổ tờ in", " mm"],
  ["kho_tp", "Khổ thành phẩm", " mm"],
  ["cach_in", "Cách in", ""],
  ["so_mat", "Số mặt", ""],
  ["so_mau", "Số màu", ""],
  ["so_kem", "Số kẽm", " bản"],
  ["so_con", "Con / tờ", ""],
  ["so_luong", "SL đặt của đơn", ""],
];

/** Các dòng của thẻ quy cách thành cặp nhãn–chữ. Khổ tờ in LUÔN có dòng: server bỏ khoá khi
 *  khổ 0 × 0, và 0 × 0 nghĩa là in thẳng khổ giấy nguyên (cùng câu với màn lệnh) — mất dòng thì
 *  đọc như lệnh thiếu khổ. "Số mặt" nhường cho "Cách in" khi có: "2 mặt (AB)" đã nói số mặt. */
export function dongQuyCach(qc: SxQuyCachThe): [string, string, string][] {
  const out: [string, string, string][] = [];
  for (const [k, nhan, duoi] of QUY_CACH_DONG) {
    if (k === "so_mat" && qc.cach_in) continue;
    const v = qc[k];
    if (k === "kho_in" && v == null) {
      out.push([k, nhan, "In thẳng khổ giấy nguyên"]);
    } else if (k === "cach_in" && typeof v === "string") {
      out.push([k, nhan, nhanCachIn(v) ?? v]);
    } else if (v != null) {
      out.push([k, nhan, `${v}${duoi}`]);
    }
  }
  return out;
}

export function ThsxQuyCachThe({ qc }: { qc: SxQuyCachThe }) {
  return (
    <div className="thsx-card">
      <div className="thsx-psec__h">
        <Icon name="layers" size={14} />
        <span className="thsx-psec__title" style={{ color: "var(--rust-deep)" }}>
          Quy cách chạy máy
        </span>
      </div>
      <div className="thsx-flat-spec-grid">
        {dongQuyCach(qc).map(([k, nhan, chu]) => (
          <div className="thsx-flat-spec-item" key={k}>
            <span className="thsx-flat-spec-lbl">{nhan}:</span>
            <span className="thsx-flat-spec-val">{chu}</span>
          </div>
        ))}
      </div>
      {/* Mực từng mặt — ĐÚNG khối chip của màn lệnh (khung `.khsx-kv` + `MucInHang` khoá sửa), để
          thợ in và kế hoạch nhìn cùng một hình. */}
      {(qc.muc_a?.length || qc.muc_b?.length) ? (
        <div className="khsx-kv khsx-kv--span thsx-muc">
          <span className="khsx-kv__key">Mực in</span>
          <MucInHang
            mucA={qc.muc_a ?? []}
            mucB={qc.muc_b ?? []}
            quyCachIn={qc.cach_in ?? (qc.muc_b?.length ? "hai_mat" : "mot_mat")}
            disabled
            onChange={() => {}}
          />
        </div>
      ) : null}
      {qc.ghi_chu_ky_thuat && (
        <div style={{ marginTop: "8px", paddingTop: "6px", borderTop: "1px solid #f1f5f9" }}>
          <p className="thsx-dando" style={{ fontSize: "12px", color: "#475569" }}>
            {qc.ghi_chu_ky_thuat}
          </p>
        </div>
      )}
    </div>
  );
}
