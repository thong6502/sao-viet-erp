// Hộp thoại LÊN ĐƠN GIAO HÀNG — chọn tài xế/phụ xe, giờ lấy hàng, giờ dự kiến giao
// (tách từ pages/GiaoHangPage.tsx). ⚠️ Payload `plan` là logic nghiệp vụ — giữ nguyên văn.
import { useEffect, useState } from "react";
import type { DeliveryDriverPick, DeliveryRequest } from "../../../../api/client";
import { api } from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { Icon } from "../../../../components/Icons";

// =============================================================================
// Dialog · Lên đơn giao hàng
// =============================================================================
export function DialogLenKeHoach({
  request,
  token,
  onClose,
  onXong,
}: {
  request: DeliveryRequest;
  token: string;
  onClose: () => void;
  onXong: () => void;
}) {
  const [employeeId, setEmployeeId] = useState("");
  // Phụ xe — TUỲ CHỌN, tối đa một người (mg 0231). Cùng danh sách với tài xế: vai trò do Ô THẢ
  // NGƯỜI VÀO quyết định, không phải thuộc tính của người. Hôm nay lái, mai đi phụ.
  const [phuXeId, setPhuXeId] = useState("");
  const [taiXe, setTaiXe] = useState<DeliveryDriverPick[]>([]);
  const [lay, setLay] = useState("");
  const [giao, setGiao] = useState("");
  const [ghiChu, setGhiChu] = useState("");
  const [loi, setLoi] = useState<string | null>(null);
  const [canhBao, setCanhBao] = useState<string[]>([]);
  const [dangGui, setDangGui] = useState(false);

  // Bắt quản lý GÕ MÃ nhân viên là bắt họ nhớ số — sai một chữ số là phân công nhầm người mà
  // không có gì báo. Chọn trong danh sách thì không sai được.
  useEffect(() => {
    api.giaoHang.taiXeChon(token).then((r) => setTaiXe(r.items)).catch(() => setTaiXe([]));
  }, [token]);

  const gui = () => {
    setLoi(null);
    setDangGui(true);
    api.giaoHang
      .plan(token, {
        request_id: request.id,
        employee_id: Number(employeeId),
        // KHÔNG gửi khi để trống (đừng gửi `null`): ở đường ĐỔI kế hoạch `null` nghĩa là GỠ phụ
        // xe, nên giữ hai nghĩa tách bạch ngay từ màn tạo cho khỏi lẫn về sau.
        ...(phuXeId ? { phu_xe_employee_id: Number(phuXeId) } : {}),
        gio_lay_hang: new Date(lay).toISOString(),
        gio_du_kien_giao: new Date(giao).toISOString(),
        ghi_chu_phan_cong: ghiChu || null,
      })
      .then((r) => {
        // Cảnh báo "sát giờ" KHÔNG chặn — hiện ra rồi vẫn lưu (PRD §6).
        if (r.canh_bao.length) {
          setCanhBao(r.canh_bao);
          window.setTimeout(onXong, 1500);
        } else {
          onXong();
        }
      })
      .catch((e: unknown) => setLoi(e instanceof Error ? e.message : "Không lưu được kế hoạch"))
      .finally(() => setDangGui(false));
  };

  return (
    <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="rc-drawer" onClick={(e) => e.stopPropagation()}>
        <header className="rc-drawer__head">
          <h2 className="rc-drawer__title">Lên đơn giao hàng · {request.code}</h2>
          <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={16} />
          </button>
        </header>
        <div className="rc-drawer__body">
          <p>
            Lưu xong, đơn giao hàng vào tab <strong>Đơn giao hàng</strong>. Bấm{" "}
            <strong>Gửi đề nghị xuất hàng</strong> ở đó thì kho mới thấy để duyệt.
          </p>
          <label>
            Nhân viên giao
            <select className="input" value={employeeId}
              onChange={(e) => {
                setEmployeeId(e.target.value);
                // Đổi tài xế thành đúng người đang làm phụ xe ⇒ GỠ ô phụ xe. Chỉ lọc danh sách
                // là chưa đủ: giá trị cũ còn trong state, gửi lên máy chủ mới báo lỗi.
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
          {/* Danh sách CHỈ gồm người vào được màn Giao hàng — tài xế còn phải bấm "Đã lấy hàng"
              rồi nhập kết quả, ai không mở được màn thì nhận chuyến xong là chuyến tắc. */}
          {taiXe.length === 0 && (
            <p className="rc__sub">
              Chưa ai được cấp ô <b>Giao hàng</b> ngoài bạn. Tài xế phải có tài khoản đăng nhập và
              vai của họ phải bật ô Giao hàng, nếu không họ không bấm được “Đã lấy hàng”.
            </p>
          )}
          {/* HAI tình huống, HAI câu — gộp một câu thì người đọc không biết đi đâu sửa. */}
          {(() => {
            const nv = taiXe.find((t) => String(t.id) === employeeId);
            if (!nv || nv.co_thao_tac) return null;
            return (
              // MỘT DÒNG. Bản đầu viết cả đoạn hướng dẫn đường đi nước bước — chủ chốt bảo
              // "dài quá" (20/08/2026): cảnh báo trong form là để người ta BIẾT rồi bấm tiếp,
              // không phải để đọc tài liệu. Việc phải làm nói gọn, ai cần chi tiết thì hỏi.
              <div className="banner banner--warn" role="status">
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
                // Bỏ chính tài xế khỏi danh sách: máy chủ chặn trùng người, nhưng bày ra rồi báo
                // lỗi là mời người ta bấm vào một cái sai.
                .filter((t) => String(t.id) !== employeeId)
                .map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.full_name}
                    {t.code ? ` · ${t.code}` : ""}
                  </option>
                ))}
            </select>
          </label>
          <p className="rc__sub">
            Có phụ xe thì tiền chuyến chia theo tỷ lệ khai ở <b>Phòng ban</b>; đi một mình thì tài
            xế ăn trọn.
          </p>
          <label>
            Giờ lấy hàng
            <input className="input" type="datetime-local" value={lay}
              onChange={(e) => setLay(e.target.value)} />
          </label>
          <label>
            Giờ dự kiến giao
            <input className="input" type="datetime-local" value={giao}
              onChange={(e) => setGiao(e.target.value)} />
          </label>
          <label>
            Ghi chú phân công
            <input className="input" value={ghiChu}
              onChange={(e) => setGhiChu(e.target.value)} />
          </label>

          {canhBao.map((c) => (
            <div key={c} className="banner banner--warn" role="status">
              {c}
            </div>
          ))}
          {loi && (
            <div className="banner banner--error" role="alert">
              {loi}
            </div>
          )}

          <Button variant="accent" disabled={!employeeId || !lay || !giao || dangGui} onClick={gui}>
            Lưu kế hoạch
          </Button>
        </div>
      </aside>
    </div>
  );
}
