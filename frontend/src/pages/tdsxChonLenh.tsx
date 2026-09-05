// Popover "khối/việc này phục vụ ≥2 lệnh — chọn một lệnh" (C123), dùng CHUNG cho tab Theo máy và
// tab Theo ca của màn "Theo dõi sản xuất".
//
// Vì sao tách ra một file: một công việc GHÉP phục vụ nhiều lệnh là sự thật của DỮ LIỆU, không
// phải của riêng tab Theo máy — Theo ca bày đúng những công việc đó nên gặp y hệt tình huống. Hai
// bản sao của cùng một popover (kèm hai bản sao của effect bắt click-ngoài/Escape) là hai chỗ để
// lệch nhau về sau, nên nó ở đây và cả hai tab gọi vào.
//
// Class CSS đổi tiền tố `tdsx-tm__picker*` → `tdsx-picker*` cho khớp: nó không còn là đồ riêng của
// tab Theo máy nữa.
import { useEffect, useRef, useState } from "react";

import type { TdsxLsxThamChieu } from "../api/client";
import { Icon } from "../components/Icons";

export interface ChonLenhState {
  ds: TdsxLsxThamChieu[];
  x: number;
  y: number;
}

/** Trả về `[state, mo, dong]`. `mo(ds, x, y)` neo popover vào toạ độ MÀN HÌNH (`getBoundingClientRect`
 *  của chính phần tử vừa bấm) — popover `position: fixed`. Bấm ra ngoài hoặc Escape thì tự đóng. */
export function useChonLenh(): [ChonLenhState | null, (ds: TdsxLsxThamChieu[], x: number, y: number) => void, () => void] {
  const [state, setState] = useState<ChonLenhState | null>(null);
  return [state, (ds, x, y) => setState({ ds, x, y }), () => setState(null)];
}

export function ChonLenhPopover({
  state,
  onDong,
  onChon,
  /** Câu đầu popover — Theo máy gọi đối tượng là "Khối", Theo ca gọi là "Việc". */
  nhan,
}: {
  state: ChonLenhState;
  onDong: () => void;
  onChon: (lsxId: number) => void;
  nhan: string;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    function ngoai(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onDong();
    }
    function phimEsc(e: KeyboardEvent) {
      if (e.key === "Escape") onDong();
    }
    document.addEventListener("mousedown", ngoai);
    document.addEventListener("keydown", phimEsc);
    return () => {
      document.removeEventListener("mousedown", ngoai);
      document.removeEventListener("keydown", phimEsc);
    };
  }, [onDong]);

  return (
    <div
      ref={ref}
      className="tdsx-picker"
      style={{ left: state.x, top: state.y }}
      role="dialog"
      aria-label="Chọn lệnh để mở hồ sơ"
    >
      <div className="tdsx-picker__head">
        <span>
          {nhan} này phục vụ {state.ds.length} lệnh — chọn một lệnh
        </span>
        <button type="button" aria-label="Đóng" onClick={onDong}>
          <Icon name="x" size={14} />
        </button>
      </div>
      {state.ds.map((lsx) => (
        <button
          key={lsx.lsx_id}
          type="button"
          className="tdsx-picker__row"
          onClick={() => {
            onDong();
            onChon(lsx.lsx_id);
          }}
        >
          <span className="tdsx-picker__ma">{lsx.ma}</span>
          <Icon name="chevron" size={14} />
        </button>
      ))}
    </div>
  );
}
