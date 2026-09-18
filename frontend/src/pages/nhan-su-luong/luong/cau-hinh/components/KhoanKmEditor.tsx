// Chia tiền một chuyến cho KÍP XE — hai ô % tài xế / % phụ xe.
// Đơn giản, dùng chung ParamField & rc-grid chuẩn phong cách Lương.
import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../../../../../api/client";
import { Button } from "../../../../../components/Button";
import { ParamField } from "./fields";

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
  const [pctTaiXe, setPctTaiXe] = useState("60");
  const [pctPhuXe, setPctPhuXe] = useState("40");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [goc, setGoc] = useState("");

  const numTx = Number(pctTaiXe) || 0;
  const numPx = Number(pctPhuXe) || 0;
  const total = numTx + numPx;
  const isValidTotal = Math.abs(total - 100) < 0.001;

  const dirty = JSON.stringify({ pctTaiXe, pctPhuXe }) !== goc && !loading;

  const nap = useCallback(() => {
    setLoading(true);
    setErr(null);
    api.giaoHang
      .khoanKmPct(token, departmentId)
      .then((r) => {
        setPctTaiXe(String(r.pct_tai_xe));
        setPctPhuXe(String(r.pct_phu_xe));
        setGoc(JSON.stringify({ pctTaiXe: String(r.pct_tai_xe), pctPhuXe: String(r.pct_phu_xe) }));
      })
      .catch(() => setErr("Không tải được tỷ lệ chia kíp xe."))
      .finally(() => setLoading(false));
  }, [token, departmentId]);

  useEffect(() => {
    nap();
  }, [nap]);

  const luu = () => {
    if (!isValidTotal) {
      setErr("Tổng tỷ lệ % của tài xế và phụ xe phải bằng đúng 100%.");
      return;
    }
    setSaving(true);
    setErr(null);
    setOk(null);
    api.giaoHang
      .saveKhoanKmPct(token, departmentId, {
        pct_tai_xe: numTx,
        pct_phu_xe: numPx,
      })
      .then((r) => {
        setPctTaiXe(String(r.pct_tai_xe));
        setPctPhuXe(String(r.pct_phu_xe));
        setGoc(JSON.stringify({ pctTaiXe: String(r.pct_tai_xe), pctPhuXe: String(r.pct_phu_xe) }));
        setOk("Đã lưu tỷ lệ chia kíp xe thành công.");
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

  const handleTxChange = (valStr: string) => {
    setPctTaiXe(valStr);
    if (valStr === "") {
      setPctPhuXe("100");
    } else {
      const v = Math.max(0, Math.min(100, Number(valStr) || 0));
      setPctPhuXe(String(100 - v));
    }
  };

  const handlePxChange = (valStr: string) => {
    setPctPhuXe(valStr);
    if (valStr === "") {
      setPctTaiXe("100");
    } else {
      const v = Math.max(0, Math.min(100, Number(valStr) || 0));
      setPctTaiXe(String(100 - v));
    }
  };

  return (
    <div className="cl-card">
      <div className="cl-card__head">
        <div>
          <h3 className="cl-card__title">Chia tiền chuyến cho kíp xe — {deptName}</h3>
          <p className="cl-card__desc">
            Tiền một chuyến (km × đơn giá bậc) chia cho tài xế và phụ xe theo tỷ lệ bên dưới (tổng bằng 100%).
            Khi tài xế chạy một mình, hệ thống tự động tính 100% cho tài xế.
          </p>
        </div>
      </div>

      <div className="cl-card__body">
        {err && <div className="banner banner--error">{err}</div>}
        {ok && !dirty && <div className="banner banner--success">{ok}</div>}

        {loading ? (
          <p className="cl-hint-inline">Đang tải tỷ lệ chia kíp…</p>
        ) : (
          <>
            <div className="rc-grid" style={{ maxWidth: 560 }}>
              <ParamField
                label="Tài xế (Lái xe chính)"
                suffix="%"
                min={0}
                max={100}
                readOnly={readOnly}
                value={numTx}
                onChange={(v) => handleTxChange(String(v))}
              />
              <ParamField
                label="Phụ xe / Bốc xếp"
                suffix="%"
                min={0}
                max={100}
                readOnly={readOnly}
                value={numPx}
                onChange={(v) => handlePxChange(String(v))}
              />
            </div>

            {!isValidTotal && (
              <div className="banner banner--warn" style={{ marginTop: 12 }}>
                <span>
                  Tổng hiện tại là <b>{total}%</b> — tổng tỷ lệ tài xế và phụ xe phải bằng đúng <b>100%</b>.
                </span>
              </div>
            )}

            {!readOnly && (
              <div style={{ marginTop: 14 }}>
                <Button
                  variant="accent"
                  loading={saving}
                  disabled={!dirty || !isValidTotal}
                  onClick={luu}
                >
                  Lưu tỷ lệ
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
