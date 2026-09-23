// DẢI ROUTING của lệnh trên bàn tổ (docs/design-dai-routing-tren-ban-to.md).
//
// Tổ chỉ thao tác với bước của mình nhưng phải ĐỌC được cả chuỗi: bước trước xong chưa, ra bao
// nhiêu, đã giao sang chưa; làm xong thì hàng đi đâu. Trước đây thẻ lệnh chỉ hiện đúng bước của
// tổ nên câu đó phải hỏi miệng ngoài xưởng.
//
// CHỈ ĐỌC — không `<button>`, không `onClick`, không mở drawer. Bước của tổ khác không mang
// `cong_viec_id` nên cũng không có gì để mở.
import { Icon } from "../components/Icons";
import type { SxRoutingBuoc } from "../api/client";
import { ttMeta } from "./thsxShared";

/** Số kiểu Việt: 10.200 · 2,5 — cùng cách đọc với phần còn lại của bàn tổ. */
function so(n: number): string {
  return n.toLocaleString("vi-VN", { maximumFractionDigits: 3 });
}

/** Cửa sổ 5 ô quanh bước của mình; thừa hai đầu gom thành ô "+N".
 *  Không cuộn ngang: màn xưởng thao tác bằng tay, cuộn ngang là bẫy. */
function cuaSo(dai: SxRoutingBuoc[]): { truoc: number; hien: SxRoutingBuoc[]; sau: number } {
  if (dai.length <= 5) return { truoc: 0, hien: dai, sau: 0 };
  const i = Math.max(0, dai.findIndex((b) => b.la_cua_toi));
  let dau = Math.max(0, i - 2);
  if (dau + 5 > dai.length) dau = dai.length - 5;
  return { truoc: dau, hien: dai.slice(dau, dau + 5), sau: dai.length - dau - 5 };
}

export function ThsxDaiRouting({ dai }: { dai: SxRoutingBuoc[] }) {
  // Lệnh một bước: vẽ một ô lẻ là nhiễu, không phải thông tin.
  if (!dai || dai.length < 2) return null;
  const { truoc, hien, sau } = cuaSo(dai);
  const toi = dai.find((b) => b.la_cua_toi);
  // Bước kề SAU bước của mình = nơi hàng sẽ đi tiếp. Tổ biết đích trước khi mở form bàn giao.
  const iToi = dai.findIndex((b) => b.la_cua_toi);
  const keSau = iToi >= 0 && iToi + 1 < dai.length ? dai[iToi + 1].step_key : null;

  return (
    <div className="thsx-dai">
      <ol className="thsx-dai__list" aria-label="Chuỗi công đoạn của lệnh">
        {truoc > 0 && (
          <li className="thsx-dai__o thsx-dai__o--gom">
            <span className="thsx-dai__gom" aria-label={`còn ${truoc} công đoạn phía trước`}>
              +{truoc}
            </span>
          </li>
        )}
        {hien.map((b) => {
          const m = ttMeta(b.trang_thai);
          return (
            <li key={b.step_key ?? b.thu_tu}
                className={`thsx-dai__o${b.la_cua_toi ? " thsx-dai__o--toi" : ""}`}>
              <span className="thsx-dai__ten">
                {b.ten_cong_doan}
                {b.phan_doan_tong > 1 && (
                  <em className="thsx-dai__phu"> · {b.phan_doan_tong} lần chạy</em>
                )}
              </span>
              <span className="thsx-dai__to">
                {b.la_cua_toi ? "Tổ của bạn" : (b.to_ten ?? "— chưa rõ tổ —")}
                {b.chay_chung && <em className="thsx-dai__phu"> · chạy chung</em>}
              </span>
              <span className={`thsx-tt ${m.cls} thsx-tt--xs`}>
                <Icon name={m.icon} size={11} /><span>{m.label}</span>
              </span>
              <span className="thsx-dai__so thsx-num">
                {b.thuc_te > 0 ? so(b.thuc_te) : (b.ke_hoach != null ? so(b.ke_hoach) : "—")}
                {b.don_vi ? ` ${b.don_vi}` : ""}
              </span>
              {b.da_giao_sang_toi != null && (
                <span className="thsx-dai__giao">
                  Đã giao sang <b className="thsx-num">{so(b.da_giao_sang_toi)}</b>
                </span>
              )}
              {b.step_key != null && b.step_key === keSau && (
                <span className="thsx-dai__cho">chờ bạn giao</span>
              )}
              {b.la_kcs_cuoi && <span className="thsx-dai__cuoi">KCS cuối</span>}
            </li>
          );
        })}
        {sau > 0 && (
          <li className="thsx-dai__o thsx-dai__o--gom">
            <span className="thsx-dai__gom" aria-label={`còn ${sau} công đoạn phía sau`}>
              +{sau}
            </span>
          </li>
        )}
      </ol>
      {toi?.da_nhan != null && (
        <p className="thsx-dai__nhan">
          <Icon name="download" size={13} />
          {/* Không kèm đơn vị: số này theo đơn vị ĐẦU VÀO của bước, còn `don_vi` trên ô là đơn
              vị ĐẦU RA. Dán nhầm nhãn là tổ đọc ra con số khác hẳn. */}
          <span>Đã nhận <b className="thsx-num">{so(toi.da_nhan)}</b> từ công đoạn trước</span>
        </p>
      )}
    </div>
  );
}
