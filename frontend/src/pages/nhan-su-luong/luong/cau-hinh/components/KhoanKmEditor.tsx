// Đơn giá khoán km giao hàng — bảng bậc + % chia kíp, theo TỪNG PHÒNG.
//
// Chuyển từ màn Phòng ban sang màn Cấu hình lương (chủ chốt 24/08/2026): đơn giá khoán là cấu hình
// LƯƠNG, để chung với "Đơn giá khoán" (sản xuất) và "Cơ chế lương theo bộ phận" thì HCNS/kế toán
// tìm một chỗ. Component TỰ CHỨA (tự tải + tự lưu), mirror `KhoanRatesEditor` — nút Lưu riêng, không
// dính save-bar của tab.
//
// Cách tính (nhắc lại để khỏi mở service): tiền chuyến = km × đơn giá của BẬC km rơi vào; chia kíp
// theo % (đi một mình tài xế ăn 100%). Đơn giá là số TÀI XẾ ĐƯỢC HƯỞNG, không phải cước cả xe.
import { useCallback, useEffect, useState } from "react";

import { ApiError, api, type KmBracket } from "../../../../../api/client";
import { Button } from "../../../../../components/Button";

export function KhoanKmEditor({
  token,
  departmentId,
  deptName,
  readOnly,
}: {
  token: string;
  departmentId: number;
  deptName: string;
  readOnly?: boolean;
}) {
  const [brackets, setBrackets] = useState<KmBracket[]>([]);
  const [pctTaiXe, setPctTaiXe] = useState("60");
  const [pctPhuXe, setPctPhuXe] = useState("40");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  // Ảnh chụp lúc tải/lưu — biết "có gì chưa lưu" để bật nút, và không hiện "đã lưu" khi chưa đổi.
  const [goc, setGoc] = useState("");

  const hienTai = JSON.stringify({ brackets, pctTaiXe, pctPhuXe });
  const dirty = hienTai !== goc && !loading;

  const nap = useCallback(() => {
    setLoading(true);
    setErr(null);
    api.giaoHang
      .kmBrackets(token, departmentId)
      .then((r) => {
        // Chưa khai bậc nào ⇒ seed một dòng ∞ (0 đ) để có chỗ gõ ngay.
        const bs = r.items.length ? r.items : [{ up_to_km: null, don_gia: 0 }];
        setBrackets(bs);
        setPctTaiXe(String(r.pct_tai_xe));
        setPctPhuXe(String(r.pct_phu_xe));
        setGoc(
          JSON.stringify({
            brackets: bs,
            pctTaiXe: String(r.pct_tai_xe),
            pctPhuXe: String(r.pct_phu_xe),
          }),
        );
      })
      .catch(() => setErr("Không tải được đơn giá khoán km."))
      .finally(() => setLoading(false));
  }, [token, departmentId]);

  useEffect(() => {
    nap();
  }, [nap]);

  const luu = () => {
    setSaving(true);
    setErr(null);
    setOk(null);
    api.giaoHang
      .saveKmBrackets(token, departmentId, brackets, {
        pct_tai_xe: Number(pctTaiXe) || 0,
        pct_phu_xe: Number(pctPhuXe) || 0,
      })
      .then((r) => {
        const bs = r.items.length ? r.items : [{ up_to_km: null, don_gia: 0 }];
        setBrackets(bs);
        setPctTaiXe(String(r.pct_tai_xe));
        setPctPhuXe(String(r.pct_phu_xe));
        setGoc(
          JSON.stringify({
            brackets: bs,
            pctTaiXe: String(r.pct_tai_xe),
            pctPhuXe: String(r.pct_phu_xe),
          }),
        );
        setOk("Đã lưu đơn giá khoán km.");
      })
      .catch((e: unknown) =>
        setErr(
          e instanceof ApiError && (e.status === 400 || e.isConflict)
            ? e.message
            : "Lưu thất bại. Vui lòng thử lại.",
        ),
      )
      .finally(() => setSaving(false));
  };

  const chuyen100 = (Number(brackets[0]?.don_gia) || 0) * 100;

  return (
    <div className="cl-card">
      <h3 className="cl-card__title">Đơn giá khoán km — {deptName}</h3>
      <p className="cl-card__desc">
        Tiền một chuyến = <b>km × đơn giá của bậc</b> km rơi vào (không cộng dồn từng đoạn). Đơn giá
        là số <b>tài xế được hưởng</b>. Chia cho kíp theo % dưới; đi một mình tài xế ăn trọn.
      </p>
      <div className="cl-card__body">
        {err && <div className="banner banner--error">{err}</div>}
        {ok && !dirty && <div className="banner banner--success">{ok}</div>}
        {loading ? (
          <p className="cc-note">Đang tải…</p>
        ) : (
          <>
            <div className="depts__bac">
              <div className="depts__bac-head">
                <span>Đến km</span>
                <span>Đơn giá (đ/km)</span>
                <span />
              </div>
              {brackets.map((b, i) => {
                const cuoi = i === brackets.length - 1;
                return (
                  <div className="depts__bac-row" key={i}>
                    <input
                      type="number"
                      min={1}
                      placeholder={cuoi ? "trở lên" : "vd 5"}
                      disabled={cuoi || readOnly}
                      value={b.up_to_km ?? ""}
                      onChange={(e) => {
                        const v = e.target.value ? Number(e.target.value) : null;
                        setBrackets((s) => s.map((x, j) => (j === i ? { ...x, up_to_km: v } : x)));
                      }}
                    />
                    <input
                      type="number"
                      min={0}
                      step={1000}
                      disabled={readOnly}
                      value={b.don_gia}
                      onChange={(e) => {
                        const v = Number(e.target.value) || 0;
                        setBrackets((s) => s.map((x, j) => (j === i ? { ...x, don_gia: v } : x)));
                      }}
                    />
                    <button
                      type="button"
                      className="depts__bac-x"
                      title="Xoá bậc này"
                      disabled={brackets.length === 1 || readOnly}
                      onClick={() => setBrackets((s) => s.filter((_, j) => j !== i))}
                    >
                      ×
                    </button>
                  </div>
                );
              })}
              {!readOnly && (
                <button
                  type="button"
                  className="depts__bac-add"
                  onClick={() =>
                    setBrackets((s) => {
                      const truoc = s.slice(0, -1);
                      const cuoi = s[s.length - 1] ?? { up_to_km: null, don_gia: 0 };
                      return [...truoc, { up_to_km: 0, don_gia: 0 }, cuoi];
                    })
                  }
                >
                  + Thêm bậc
                </button>
              )}
            </div>

            <div className="depts__khoankm">
              <label className="depts__khoankm-o">
                <span>% tài xế</span>
                <input
                  type="number"
                  min={0}
                  max={100}
                  disabled={readOnly}
                  value={pctTaiXe}
                  onChange={(e) => {
                    setPctTaiXe(e.target.value);
                    setPctPhuXe(String(100 - (Number(e.target.value) || 0)));
                  }}
                />
              </label>
              <label className="depts__khoankm-o">
                <span>% phụ xe</span>
                <input
                  type="number"
                  min={0}
                  max={100}
                  disabled={readOnly}
                  value={pctPhuXe}
                  onChange={(e) => {
                    setPctPhuXe(e.target.value);
                    setPctTaiXe(String(100 - (Number(e.target.value) || 0)));
                  }}
                />
              </label>
            </div>
            <span className="depts__khoankm-note">
              Chuyến 100 km = <b>{chuyen100.toLocaleString("vi-VN")} đ</b> — chia{" "}
              {Number(pctTaiXe) || 0}/{Number(pctPhuXe) || 0}.
            </span>

            {!readOnly && (
              <div style={{ marginTop: 12 }}>
                <Button variant="accent" loading={saving} disabled={!dirty} onClick={luu}>
                  Lưu đơn giá khoán km
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
