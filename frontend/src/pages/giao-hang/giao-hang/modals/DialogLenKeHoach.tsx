// Hộp thoại LÊN ĐƠN GIAO HÀNG — chọn tài xế/phụ xe, giờ lấy hàng, giờ dự kiến giao
// (tách từ pages/GiaoHangPage.tsx). ⚠️ Payload `plan` là logic nghiệp vụ — giữ nguyên văn.
//
// HAI chế độ, MỘT form (chủ chốt 18/09/2026 — "gom nhiều phiếu lại chạy 1 lượt"):
//   một yêu cầu   — nút "Lên đơn giao hàng" ở từng dòng ⇒ `plan` như cũ.
//   `theoLuot`    — tick nhiều yêu cầu rồi "Lên lượt xe" ⇒ `lenLuot`: MỖI yêu cầu một chuyến, một
//                   phiếu kho, chung MỘT lượt xe; một yêu cầu hỏng là cả lô không lưu.
import { useEffect, useState } from "react";
import type { DeliveryDriverPick, DeliveryRequest, LuotXeMo } from "../../../../api/client";
import { api } from "../../../../api/client";
import { crud, type Row } from "../../../../api/rebuildCatalog";
import { Button } from "../../../../components/Button";
import { Icon } from "../../../../components/Icons";
import { fmtDate } from "../../../../utils/format";
import {
  GIO_NHAP_MAX, GIO_NHAP_MIN, gioNhapHopLe, gioNhapSai,
} from "../../../../lib/gioNhap";

// =============================================================================
// Dialog · Lên đơn giao hàng
// =============================================================================
export function DialogLenKeHoach({
  requests,
  theoLuot = false,
  token,
  onClose,
  onXong,
}: {
  requests: DeliveryRequest[];
  theoLuot?: boolean;
  token: string;
  onClose: () => void;
  /** `luotId` có khi lên theo lượt — màn ngoài mở luôn ngăn Lượt xe cho bước kế tiếp. */
  onXong: (luotId?: number) => void;
}) {
  const request = requests[0];
  const [employeeId, setEmployeeId] = useState("");
  // Phụ xe — TUỲ CHỌN, tối đa một người (mg 0231). Cùng danh sách với tài xế: vai trò do Ô THẢ
  // NGƯỜI VÀO quyết định, không phải thuộc tính của người. Hôm nay lái, mai đi phụ.
  const [phuXeId, setPhuXeId] = useState("");
  // XE — BẮT BUỘC (chủ chốt 12/09/2026). Đơn giá khoán km tra theo MỨC mà xe đang ăn, nên bỏ
  // trống là đẩy việc sang người đóng chuyến, lúc đó hàng đã đi rồi mới biết chuyến nào thiếu.
  const [xeId, setXeId] = useState("");
  const [xeDs, setXeDs] = useState<Row[]>([]);
  // LƯỢT XE (PRD khoán km §14, chủ chốt 18/09/2026): người lên đơn quyết đơn nào đi chung một vòng
  // xe. Tiền km tính theo TỪNG CHẶNG giữa hai lần ghi số đồng hồ, nên gom đúng lượt là gom đúng
  // tiền.
  const [luot, setLuot] = useState<string>("moi");
  const [luotDs, setLuotDs] = useState<LuotXeMo[]>([]);
  const [taiXe, setTaiXe] = useState<DeliveryDriverPick[]>([]);
  const [lay, setLay] = useState("");
  const [giao, setGiao] = useState("");
  const [ghiChu, setGhiChu] = useState("");
  const [loi, setLoi] = useState<string | null>(null);
  const [canhBao, setCanhBao] = useState<string[]>([]);
  const [dangGui, setDangGui] = useState(false);
  const gioSai = gioNhapSai(lay) || gioNhapSai(giao);
  const thieuXe = (theoLuot || xeDs.length > 0) && !xeId;

  useEffect(() => {
    api.giaoHang.taiXeChon(token).then((r) => setTaiXe(r.items)).catch(() => setTaiXe([]));
    crud("/api/xe").list(token, { active: true })
      .then((r) => setXeDs(r.items)).catch(() => setXeDs([]));
  }, [token]);

  useEffect(() => {
    setLuot("moi");
    if (!xeId) {
      setLuotDs([]);
      return;
    }
    let bo = false;
    api.giaoHang.luotXeMo(token, Number(xeId))
      .then((r) => { if (!bo) setLuotDs(r.items); })
      .catch(() => { if (!bo) setLuotDs([]); });
    return () => { bo = true; };
  }, [token, xeId]);

  const xongVoiCanhBao = (canh: string[], luotId?: number) => {
    if (canh.length) {
      setCanhBao(canh);
      window.setTimeout(() => onXong(luotId), 1500);
    } else {
      onXong(luotId);
    }
  };

  const gui = () => {
    setLoi(null);
    setDangGui(true);
    if (theoLuot) {
      api.giaoHang
        .lenLuot(token, {
          request_ids: requests.map((r) => r.id),
          employee_id: Number(employeeId),
          ...(phuXeId ? { phu_xe_employee_id: Number(phuXeId) } : {}),
          vehicle_id: Number(xeId),
          luot_xe_id: luot === "moi" ? "moi" : Number(luot),
          gio_lay_hang: new Date(lay).toISOString(),
          gio_du_kien_giao: new Date(giao).toISOString(),
          ghi_chu_phan_cong: ghiChu || null,
        })
        .then((r) => xongVoiCanhBao(r.canh_bao, r.luot_id))
        .catch((e: unknown) => setLoi(e instanceof Error ? e.message : "Không lưu được lượt xe"))
        .finally(() => setDangGui(false));
      return;
    }
    api.giaoHang
      .plan(token, {
        request_id: request.id,
        employee_id: Number(employeeId),
        ...(phuXeId ? { phu_xe_employee_id: Number(phuXeId) } : {}),
        ...(xeId
          ? { vehicle_id: Number(xeId), luot_xe_id: luot === "moi" ? "moi" as const : Number(luot) }
          : {}),
        gio_lay_hang: new Date(lay).toISOString(),
        gio_du_kien_giao: new Date(giao).toISOString(),
        ghi_chu_phan_cong: ghiChu || null,
      })
      .then((r) => xongVoiCanhBao(r.canh_bao))
      .catch((e: unknown) => setLoi(e instanceof Error ? e.message : "Không lưu được kế hoạch"))
      .finally(() => setDangGui(false));
  };

  return (
    <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="rc-drawer" onClick={(e) => e.stopPropagation()}>
        <header className="rc-drawer__head">
          <h2 className="rc-drawer__title">
            {theoLuot ? `Lên lượt xe · ${requests.length} yêu cầu` : `Lên đơn giao hàng · ${request.code}`}
          </h2>
          <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={16} />
          </button>
        </header>
        <div className="rc-drawer__body gh-form">
          {theoLuot ? (
            <div className="gh-card" style={{ background: "#f8fafc", marginBottom: 0 }}>
              <p style={{ margin: "0 0 8px", fontSize: "13px", color: "#334155" }}>
                Mỗi yêu cầu thành <strong>một đơn giao hàng riêng</strong> (một phiếu xuất kho riêng,
                một kết quả riêng), cùng chạy <strong>một lượt xe</strong>. Lưu xong, lượt hiện thành
                một khối ở tab Đơn giao hàng — gửi yêu cầu xuất kho cả lượt ngay trên khối đó.
              </p>
              <ul className="gh-ds-yc">
                {requests.map((r) => (
                  <li key={r.id}>
                    <b>{r.code}</b> · {r.customer_name} · cần giao {fmtDate(r.ngay_can_giao)}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="rc__sub" style={{ margin: 0 }}>
              Lưu xong, đơn giao hàng vào tab <strong>Đơn giao hàng</strong>. Bấm{" "}
              <strong>Gửi đề nghị xuất hàng</strong> ở đó thì kho mới thấy để duyệt.
            </p>
          )}

          <div className="gh-card" style={{ marginBottom: 0 }}>
            <h3 className="gh-card__title">Phương tiện &amp; Nhân sự</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              <label>
                Xe {(theoLuot || xeDs.length > 0) && <span className="gh-bat-buoc">*</span>}
                <select className="input" value={xeId} onChange={(e) => setXeId(e.target.value)}>
                  <option value="">— Chọn xe —</option>
                  {xeDs.map((x) => (
                    <option key={x.id} value={x.id}>
                      {String(x.ma ?? "")}
                      {x.ten ? ` · ${String(x.ten)}` : ""}
                      {x.tai_trong != null ? ` · ${Number(x.tai_trong).toLocaleString("vi-VN")} tấn` : ""}
                    </option>
                  ))}
                </select>
              </label>
              <p className="rc__sub" style={{ margin: "-6px 0 0" }}>
                {xeDs.length === 0
                  ? theoLuot
                    ? "Chưa khai chiếc xe nào — lượt là vòng chạy của một chiếc xe, khai xe ở Cấu hình danh mục → Xe giao hàng trước."
                    : "Chưa khai chiếc xe nào ở Cấu hình danh mục → Xe giao hàng."
                  : "Đơn giá khoán km tra theo MỨC mà xe này đang ăn."}
              </p>

              {xeId && (
                <>
                  <label>
                    Lượt xe
                    <select className="input" value={luot} onChange={(e) => setLuot(e.target.value)}>
                      <option value="moi">Lượt mới — xe xuất phát từ kho</option>
                      {luotDs.map((l) => (
                        <option key={l.id} value={l.id}>
                          Ghép vào {l.code} · {fmtDate(l.ngay)} · {l.so_diem} điểm
                          {l.tai_xe ? ` · ${l.tai_xe}` : ""}
                          {l.da_xuat_phat ? " · xe đã xuất phát" : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                  <p className="rc__sub" style={{ margin: "-6px 0 0" }}>
                    Chở nhiều đơn trong một vòng xe thì ghép chung một lượt. Tài xế ghi số đồng hồ lúc
                    đi, lúc tới từng khách và lúc về kho — tiền km tính theo từng chặng.
                  </p>
                </>
              )}

              <label>
                Nhân viên giao
                <select className="input" value={employeeId}
                  onChange={(e) => {
                    setEmployeeId(e.target.value);
                    if (e.target.value === phuXeId) setPhuXeId("");
                  }}>
                  <option value="">— Chọn tài xế —</option>
                  {taiXe.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.full_name}
                      {t.code ? ` · ${t.code}` : ""}
                      {t.department ? ` · ${t.department}` : ""}
                      {t.co_thao_tac
                        ? ""
                        : t.co_tai_khoan === false
                          ? " — chưa có tài khoản"
                          : " — chưa bấm nút được"}
                    </option>
                  ))}
                </select>
              </label>
              {taiXe.length === 0 && (
                <p className="rc__sub" style={{ margin: "-6px 0 0" }}>
                  Chưa ai được cấp ô <b>Giao hàng</b> ngoài bạn. Tài xế phải có tài khoản đăng nhập và
                  vai của họ phải bật ô Giao hàng, nếu không họ không bấm được “Đã lấy hàng”.
                </p>
              )}
              {(() => {
                const nv = taiXe.find((t) => String(t.id) === employeeId);
                if (!nv || nv.co_thao_tac) return null;
                return (
                  <div className="banner banner--warn" role="status" style={{ margin: 0 }}>
                    <b>{nv.full_name}</b>{" "}
                    {nv.co_tai_khoan === false ? "chưa có tài khoản" : "chưa được cấp quyền thao tác"}
                    {" "}— vẫn phân chuyến được, nhưng bạn phải bấm hộ.
                  </div>
                );
              })()}

              <label>
                Phụ xe <span className="gh-opt">(không bắt buộc)</span>
                <select
                  className="input"
                  value={phuXeId}
                  onChange={(e) => setPhuXeId(e.target.value)}
                >
                  <option value="">— Đi một mình —</option>
                  {taiXe
                    .filter((t) => String(t.id) !== employeeId)
                    .map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.full_name}
                        {t.code ? ` · ${t.code}` : ""}
                      </option>
                    ))}
                </select>
              </label>
              <p className="rc__sub" style={{ margin: "-6px 0 0" }}>
                Có phụ xe thì tiền chuyến chia theo tỷ lệ khai ở <b>Phòng ban</b>; đi một mình thì tài
                xế ăn trọn.
              </p>
            </div>
          </div>

          <div className="gh-card" style={{ marginBottom: 0 }}>
            <h3 className="gh-card__title">Thời gian giao nhận</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              <label>
                Giờ lấy hàng
                <input className="input" type="datetime-local" min={GIO_NHAP_MIN} max={GIO_NHAP_MAX}
                  value={lay} onChange={(e) => setLay(e.target.value)} />
              </label>
              <label>
                Giờ dự kiến giao
                <input className="input" type="datetime-local" min={GIO_NHAP_MIN} max={GIO_NHAP_MAX}
                  value={giao} onChange={(e) => setGiao(e.target.value)} />
              </label>
              {gioSai && (
                <div className="banner banner--warn" role="status" style={{ margin: 0 }}>
                  {gioNhapSai(lay) && gioNhapSai(giao)
                    ? "Giờ lấy hàng và giờ dự kiến giao"
                    : gioNhapSai(lay) ? "Giờ lấy hàng" : "Giờ dự kiến giao"}{" "}
                  không đọc được — năm phải 4 chữ số, trong khoảng 2000–2099.
                </div>
              )}
            </div>
          </div>

          <div className="gh-card" style={{ marginBottom: 0 }}>
            <h3 className="gh-card__title">Ghi chú phân công</h3>
            <label>
              Ghi chú phân công
              <input className="input" value={ghiChu} placeholder="Nhập ghi chú cho kíp xe..."
                onChange={(e) => setGhiChu(e.target.value)} />
            </label>
          </div>

          {canhBao.map((c) => (
            <div key={c} className="banner banner--warn" role="status" style={{ margin: 0 }}>
              {c}
            </div>
          ))}
          {loi && (
            <div className="banner banner--error" role="alert" style={{ margin: 0 }}>
              {loi}
            </div>
          )}

          <Button
            variant="accent"
            disabled={!employeeId || !gioNhapHopLe(lay) || !gioNhapHopLe(giao) || dangGui || thieuXe}
            onClick={gui}
          >
            {theoLuot ? `Lưu lượt xe (${requests.length} đơn)` : "Lưu kế hoạch"}
          </Button>
        </div>
      </aside>
    </div>
  );
}
