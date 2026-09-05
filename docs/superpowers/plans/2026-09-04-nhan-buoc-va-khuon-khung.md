# Nhãn loại bước xuyên suốt + Khuôn & khung — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nhãn loại bước và khuôn/khung của một công đoạn đi theo bước đó qua mọi màn từ phiếu tính giá tới lúc lệnh sản xuất hoàn thành, và luật "bế phải có khuôn mới làm được" được chặn tại đúng một điểm — nút Bắt đầu của tổ.

**Architecture:** Dữ liệu (`loai_buoc`, `nha_cung_cap`, khối khuôn) được bơm vào MỌI API trả bước/công việc; frontend dùng đúng hai component chip dùng chung (`ChipLoaiBuoc`, `ChipKhuon`). Khuôn được chụp vào công việc lúc phát hành như `vat_tu_json`; tổ tích "đã nhận" trước khi bắt đầu.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 (Postgres dev/prod, SQLite in-memory cho test) · React 18 + TypeScript + Vite.

**Spec:** `docs/superpowers/specs/2026-09-04-nhan-buoc-va-khuon-khung-design.md`

## Global Constraints

- **KHÔNG có Alembic.** `create_all` chỉ TẠO bảng, không ALTER. Mọi cột mới phải viết migration vào `backend/app/db_migrations.py` và `MIGRATIONS.append(...)` ở cuối file. Migration mới nhất hiện tại là `0256_cong_viec_hoan_thanh_luc` ⇒ cột mới bắt đầu từ `0257`.
- **Migration cấm ORM full-select** — dùng raw SQL đích danh cột. `select(Model)` kéo cả cột do migration SAU thêm → vỡ deploy trên DB trung gian.
- **Boolean mới:** `server_default` là `false`/`true` (Python bool), KHÔNG phải `"0"`/`"1"`.
- **`docs/DB_SCHEMA.md` có guard test:** mọi bảng/cột trong model phải được ghi vào đó. Thêm cột → cập nhật DB_SCHEMA.md **cùng task**.
- **Chuỗi `khuon_be` là BẤT KHẢ XÂM PHẠM:** tên bảng, `moduleQuyen`, `prefix /api/khuon-be`, `nhatKyLoai`. Chỉ đổi nhãn hiển thị thành `Khuôn & khung`.
- **Bộ mã loại dụng cụ dùng chung:** `("khuon_be", "khuon_ep", "khung_lua")` — `cong_doan.TOOLING_TYPE` và `khuon_be.LOAI_KHUON` phải khớp khít.
- **Verify:** `python -m pytest tests/<file> -q` (nhắm đúng file, không chạy cả bộ) + `npx tsc --noEmit` trong `frontend/`. KHÔNG chạy `./init.ps1`.
- **KHÔNG chạy `python -c` trần trong `backend/`** — nó trỏ vào Postgres DEV thật. Thăm dò thì viết test tạm rồi chạy pytest.
- Commit message tiếng Việt, thuật ngữ kỹ thuật giữ tiếng Anh.

---

### Task 1: Danh mục "Khuôn & khung" — nhận thêm loại `khung_lua`

**Files:**
- Modify: `backend/app/models/khuon_be.py:29` (`LOAI_KHUON`)
- Modify: `frontend/src/pages/rebuildCatalogConfigs.tsx:884-887` (`LOAI_KHUON`), `:908` (`title`)
- Modify: `frontend/src/components/Sidebar.tsx:251` (label)
- Modify: `docs/DB_SCHEMA.md:3508-3527` (mục `khuon_be`), `:1163` (`cong_doan.tooling_type`)
- Test: `backend/tests/test_khuon_be.py`

**Interfaces:**
- Produces: `LOAI_KHUON = ("khuon_be", "khuon_ep", "khung_lua")` — Task 5 và Task 7 lọc theo bộ mã này.

- [ ] **Step 1: Viết test đỏ**

Thêm vào `backend/tests/test_khuon_be.py`:

```python
def test_accept_loai_khung_lua():
    """Khung lụa cũng lưu kho dùng lại như khuôn bế (chốt 04/09/2026) — kho phải nhận loại này,
    không thì bước lụa ở lệnh mở ô chọn ra rỗng và bấm 'làm mới' thì service ném 400."""
    db, svc = _svc()
    k = svc.create(dict(ten="Khung lụa hộp bánh A", loai="khung_lua", so_ke="Kệ C1"))
    assert k.loai == "khung_lua"
```

- [ ] **Step 2: Chạy test cho chắc nó đỏ**

```bash
cd backend && python -m pytest tests/test_khuon_be.py::test_accept_loai_khung_lua -q
```

Kỳ vọng: FAIL — `KhuonBeValidationError`.

- [ ] **Step 3: Nới bộ mã ở backend**

`backend/app/models/khuon_be.py` — sửa hằng và chú thích:

```python
# Loại dụng cụ lưu kho (mg 0205; thêm `khung_lua` 04/09/2026). DÙNG CHUNG bộ mã với
# `cong_doan.TOOLING_TYPE` — ô chọn ở bước lệnh lọc bằng cách so thẳng
# `cong_doan.tooling_type == khuon_be.loai`, hai bộ mã lệch nhau là lọc ra rỗng.
LOAI_KHUON = ("khuon_be", "khuon_ep", "khung_lua")
```

Sửa luôn docstring đầu file: `"""Danh mục KHUÔN & KHUNG — kho dụng cụ dùng chung của xưởng..."""`.

- [ ] **Step 4: Chạy lại test**

```bash
cd backend && python -m pytest tests/test_khuon_be.py -q
```

Kỳ vọng: PASS toàn bộ file.

- [ ] **Step 5: Đổi nhãn ở frontend**

`frontend/src/pages/rebuildCatalogConfigs.tsx`:

```tsx
export const LOAI_KHUON: Lbls = {
  khuon_be: "Khuôn bế",
  khuon_ep: "Khuôn ép nhũ / dập nổi",
  khung_lua: "Khung lụa",
};
```

Trong `CFG_KHUON_BE` đổi `title: "Khuôn"` → `title: "Khuôn & khung"`, và nhãn field `loai` từ
`"Loại khuôn"` → `"Loại"`, hint đổi thành:
`"Bước “Ép nhũ” chỉ thấy dao ép, bước “Bế” chỉ thấy dao bế, bước lụa chỉ thấy khung lụa."`

`frontend/src/components/Sidebar.tsx:251`:

```tsx
{ id: "khuon-be", label: "Khuôn & khung", icon: "clipboard", module: "khuon_be" },
```

- [ ] **Step 6: Cập nhật DB_SCHEMA.md**

Mục `### khuon_be`: đổi Purpose thành *"KHO DỤNG CỤ của xưởng — khuôn bế, khuôn ép nhũ và khung lụa (nhan đề màn là **"Khuôn & khung"** từ 04/09/2026; tên bảng + module quyền vẫn `khuon_be`…)"*, và dòng `loai` thành `khuon_be | khuon_ep | khung_lua`.
Dòng 1163 (`cong_doan.tooling_type`) sửa mô tả sai cũ thành `khuon_be / khuon_ep / khung_lua`.

- [ ] **Step 7: Kiểm TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/khuon_be.py backend/tests/test_khuon_be.py frontend/src/pages/rebuildCatalogConfigs.tsx frontend/src/components/Sidebar.tsx docs/DB_SCHEMA.md
git commit -m "Danh muc Khuon & khung: nhan them loai khung lua, doi nhan man"
```

---

### Task 2: Hai component chip dùng chung

**Files:**
- Create: `frontend/src/components/ChipBuoc.tsx`
- Create: `frontend/src/components/chip-buoc.css`
- Test: `frontend/src/components/ChipBuoc.test.tsx`

**Interfaces:**
- Produces:
  ```ts
  export interface KhuonChip {
    ma?: string | null; ten?: string | null; so_ke?: string | null;
    tinh_trang?: string | null; ngay_ve_du_kien?: string | null; da_nhan?: boolean;
  }
  export function ChipLoaiBuoc(p: { loai_buoc?: string | null; nha_cung_cap?: string | null }): JSX.Element | null;
  export function ChipKhuon(p: { can_khuon?: boolean; khuon?: KhuonChip | null }): JSX.Element | null;
  ```
  Task 6, 8, 9, 10, 11, 12, 13 import đúng hai hàm này — không màn nào tự vẽ lại chip.

- [ ] **Step 1: Viết test đỏ**

`frontend/src/components/ChipBuoc.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ChipKhuon, ChipLoaiBuoc } from "./ChipBuoc";

describe("ChipLoaiBuoc", () => {
  it("thuê ngoài CÓ nhà gia công → hiện tên nơi làm", () => {
    render(<ChipLoaiBuoc loai_buoc="thue_ngoai" nha_cung_cap="Cơ sở Minh Phát" />);
    expect(screen.getByText("Ngoài · Cơ sở Minh Phát")).toBeTruthy();
  });

  it("thuê ngoài CHƯA có nhà gia công → vẫn hiện nhãn, đổi sang tone cảnh báo", () => {
    const { container } = render(<ChipLoaiBuoc loai_buoc="thue_ngoai" />);
    expect(screen.getByText("Ngoài · chưa chọn nơi làm")).toBeTruthy();
    expect(container.querySelector(".chip-buoc--canhbao")).toBeTruthy();
  });

  it("máy và tổ vẫn có nhãn riêng", () => {
    render(<ChipLoaiBuoc loai_buoc="may" />);
    expect(screen.getByText("Máy")).toBeTruthy();
  });

  it("không biết loại → không vẽ gì", () => {
    const { container } = render(<ChipLoaiBuoc />);
    expect(container.firstChild).toBeNull();
  });
});

describe("ChipKhuon", () => {
  it("bước cần dụng cụ mà chưa chốt dao → chip đỏ", () => {
    const { container } = render(<ChipKhuon can_khuon />);
    expect(screen.getByText("chưa chốt khuôn")).toBeTruthy();
    expect(container.querySelector(".chip-khuon--thieu")).toBeTruthy();
  });

  it("dao đang dùng → mã + số kệ", () => {
    render(<ChipKhuon can_khuon khuon={{ ma: "KB-0123", so_ke: "Kệ A3", tinh_trang: "dang_dung" }} />);
    expect(screen.getByText("KB-0123 · Kệ A3")).toBeTruthy();
  });

  it("dao đang đặt làm → mã + ngày dự kiến, tone vàng", () => {
    const { container } = render(
      <ChipKhuon can_khuon khuon={{ ma: "KB-0130", tinh_trang: "dang_dat_lam", ngay_ve_du_kien: "2026-09-12" }} />,
    );
    expect(screen.getByText("KB-0130 · dự kiến 12/09")).toBeTruthy();
    expect(container.querySelector(".chip-khuon--cho")).toBeTruthy();
  });

  it("tổ đã tích nhận → nói 'đã nhận'", () => {
    render(<ChipKhuon can_khuon khuon={{ ma: "KB-0123", so_ke: "Kệ A3", da_nhan: true }} />);
    expect(screen.getByText("KB-0123 · đã nhận")).toBeTruthy();
  });

  it("bước không cần dụng cụ → không vẽ gì", () => {
    const { container } = render(<ChipKhuon />);
    expect(container.firstChild).toBeNull();
  });
});
```

- [ ] **Step 2: Chạy test cho chắc nó đỏ**

```bash
cd frontend && npx vitest run src/components/ChipBuoc.test.tsx
```

Kỳ vọng: FAIL — không tìm thấy module `./ChipBuoc`.

- [ ] **Step 3: Viết component**

`frontend/src/components/ChipBuoc.tsx`:

```tsx
// HAI CHIP DÙNG CHUNG cho mọi màn có mặt một bước sản xuất — từ phiếu tính giá tới lúc lệnh xong.
//
// Vì sao phải là MỘT component: trước đây mỗi màn tự quyết định lại nhãn từ một dữ liệu khác nhau
// (Kế hoạch đọc `loai_buoc`, Gantt đọc tên nhà cung cấp, Theo dõi SX không đọc gì) — ba cách suy
// ba kết quả, nên nhãn đứt quãng giữa đường. Nhãn là DỮ LIỆU đi theo bước, không phải thứ mỗi màn
// tự đoán lấy.
import "./chip-buoc.css";

const NHAN_LOAI: Record<string, string> = { may: "Máy", to: "Tổ" };

export function ChipLoaiBuoc({
  loai_buoc,
  nha_cung_cap,
}: {
  loai_buoc?: string | null;
  nha_cung_cap?: string | null;
}) {
  if (!loai_buoc) return null;
  if (loai_buoc === "thue_ngoai") {
    const noi = (nha_cung_cap ?? "").trim();
    // Điều kiện hiện chip CHỈ là loại bước. Chưa điền nơi làm thì đổi tone chứ KHÔNG giấu chip —
    // giấu đi là đúng cái làm nhãn biến mất giữa đường ở bản trước.
    return (
      <span className={`chip-buoc chip-buoc--${noi ? "ngoai" : "canhbao"}`}>
        {noi ? `Ngoài · ${noi}` : "Ngoài · chưa chọn nơi làm"}
      </span>
    );
  }
  const nhan = NHAN_LOAI[loai_buoc];
  if (!nhan) return null;
  return <span className={`chip-buoc chip-buoc--${loai_buoc}`}>{nhan}</span>;
}

export interface KhuonChip {
  ma?: string | null;
  ten?: string | null;
  so_ke?: string | null;
  tinh_trang?: string | null;
  ngay_ve_du_kien?: string | null;
  da_nhan?: boolean;
}

/** yyyy-mm-dd → dd/mm. Rỗng/sai định dạng → "". */
function ngayNgan(v?: string | null): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(v ?? ""));
  return m ? `${m[3]}/${m[2]}` : "";
}

export function ChipKhuon({ can_khuon, khuon }: { can_khuon?: boolean; khuon?: KhuonChip | null }) {
  if (!can_khuon) return null;
  if (!khuon || !khuon.ma) {
    return <span className="chip-khuon chip-khuon--thieu">🔧 chưa chốt khuôn</span>;
  }
  if (khuon.da_nhan) {
    return <span className="chip-khuon chip-khuon--nhan">🔧 {khuon.ma} · đã nhận</span>;
  }
  if (khuon.tinh_trang === "dang_dat_lam") {
    const ng = ngayNgan(khuon.ngay_ve_du_kien);
    return (
      <span className="chip-khuon chip-khuon--cho">
        🔧 {khuon.ma}{ng ? ` · dự kiến ${ng}` : " · chưa có ngày"}
      </span>
    );
  }
  const ke = (khuon.so_ke ?? "").trim();
  return (
    <span className="chip-khuon chip-khuon--co">
      🔧 {khuon.ma}{ke ? ` · ${ke}` : ""}
    </span>
  );
}
```

- [ ] **Step 4: Viết CSS**

`frontend/src/components/chip-buoc.css`:

```css
/* Chip dùng chung — bám đúng bảng màu của `khsx-lb` ở ke-hoach-sx.css để hai màn không lệch nhau. */
.chip-buoc,
.chip-khuon {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
  line-height: 16px;
  white-space: nowrap;
}
.chip-buoc--may { background: var(--steel-soft); color: var(--steel); }
.chip-buoc--to { background: var(--rule-hair); color: var(--ash); }
.chip-buoc--ngoai { background: var(--rust-soft); color: var(--rust-deep); }
.chip-buoc--canhbao { background: var(--amber-soft); color: var(--amber-deep); }

.chip-khuon--thieu { background: var(--danger-soft, #fde8e8); color: var(--danger-deep, #9b1c1c); }
.chip-khuon--cho { background: var(--amber-soft); color: var(--amber-deep); }
.chip-khuon--co { background: var(--moss-soft, #e6f4ea); color: var(--moss-deep, #1e6b3a); }
.chip-khuon--nhan { background: var(--moss-deep, #1e6b3a); color: #fff; }
```

- [ ] **Step 5: Chạy test cho xanh**

```bash
cd frontend && npx vitest run src/components/ChipBuoc.test.tsx && npx tsc --noEmit
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ChipBuoc.tsx frontend/src/components/ChipBuoc.test.tsx frontend/src/components/chip-buoc.css
git commit -m "Them hai chip dung chung ChipLoaiBuoc + ChipKhuon"
```

---

### Task 3: Phiếu tính giá — hỏi "khuôn có sẵn hay làm mới"

**Files:**
- Modify: `backend/app/models/phieu_tinh_gia.py:229` (thêm 2 cột sau `phi_khuon`)
- Modify: `backend/app/db_migrations.py` (mg `0257`)
- Modify: `backend/app/schemas/phieu_tinh_gia.py:29-33`, `:52-55`
- Modify: `backend/app/services/thanh_phan_engine.py:1024-1060` (cảnh báo)
- Modify: `frontend/src/pages/PhieuTinhGiaDetailView.tsx` (khối khuôn của bước)
- Modify: `frontend/src/api/client.ts` (type dòng thành phẩm)
- Modify: `docs/DB_SCHEMA.md` (mục `phieu_thanh_pham`)
- Test: `backend/tests/test_phieu_tinh_gia.py`

**Interfaces:**
- Consumes: bộ mã dụng cụ từ Task 1.
- Produces: `phieu_thanh_pham.khuon_nguon: "co_san" | "lam_moi" | None`, `phieu_thanh_pham.khuon_ngay_du_kien: date | None`. Task 4 chép hai giá trị này sang bước của lệnh.

- [ ] **Step 1: Viết test đỏ**

Thêm vào `backend/tests/test_phieu_tinh_gia.py`:

```python
def test_khuon_nguon_co_san_khong_canh_bao(db):
    """Chọn 'dùng khuôn có sẵn' là một câu trả lời ĐÚNG, không phải chỗ trống bị bỏ quên —
    engine không được nhắc nữa. Trước đây mọi bước để trống phí đều bị nhắc, nên lời nhắc thành
    tiếng ồn và người lập phiếu tắt mắt với nó."""
    from app.services import thanh_phan_engine as eng
    row = {"cong_doan": {"requires_tooling": True, "tooling_type": "khuon_be", "ten": "Bế"},
           "ten": "Bế", "phi_khuon": 0, "khuon_nguon": "co_san"}
    canh_bao = eng._canh_bao_khuon([row])
    assert canh_bao == []


def test_khuon_nguon_lam_moi_ma_khong_tien_thi_nhac(db):
    from app.services import thanh_phan_engine as eng
    row = {"cong_doan": {"requires_tooling": True, "tooling_type": "khuon_be", "ten": "Bế"},
           "ten": "Bế", "phi_khuon": 0, "khuon_nguon": "lam_moi"}
    canh_bao = eng._canh_bao_khuon([row])
    assert len(canh_bao) == 1 and "làm khuôn mới" in canh_bao[0]
```

- [ ] **Step 2: Chạy test cho chắc nó đỏ**

```bash
cd backend && python -m pytest tests/test_phieu_tinh_gia.py -q -k khuon_nguon
```

Kỳ vọng: FAIL — `_canh_bao_khuon` chưa tồn tại.

- [ ] **Step 3: Thêm cột vào model**

`backend/app/models/phieu_tinh_gia.py`, ngay sau `phi_khuon`:

```python
    # NGUỒN KHUÔN — sale trả lời ĐÚNG MỘT CÂU: dao này có sẵn hay phải làm mới (chốt 04/09/2026).
    #
    # Trước đây chỉ có ô tiền ở trên, với quy ước NGẦM "để trống = dùng dao cũ" — nên hệ thống
    # không phân biệt được "đã cân nhắc và dùng dao cũ" với "quên nhập". Kế hoạch đọc phiếu không
    # biết sale định thế nào, tới lúc lập lệnh mới lòi ra phải đặt dao mới: mất tiền và mất luôn
    # thời gian chờ dao.
    #
    # NULL = chưa chọn (phiếu cũ, hoặc người lập bỏ qua) → engine giữ nguyên lời nhắc như trước.
    khuon_nguon: Mapped[str | None] = mapped_column(String(10), nullable=True)  # co_san|lam_moi
    # Ngày sale dự kiến có khuôn — chỉ có nghĩa với `khuon_nguon='lam_moi'`. Đây là DỰ TRÙ để kế
    # hoạch liệu cơm gắp mắm, KHÔNG phải mốc ràng buộc lịch: mốc thật nằm ở `khuon_be`.
    khuon_ngay_du_kien: Mapped[date | None] = mapped_column(Date, nullable=True)
```

Thêm `Date` vào import `sqlalchemy` và `date` vào import `datetime` của file nếu chưa có.

- [ ] **Step 4: Viết migration 0257**

Cuối `backend/app/db_migrations.py`:

```python
def _migrate_phieu_thanh_pham_khuon_nguon(db) -> None:
    """mg 0257 — `phieu_thanh_pham.khuon_nguon` + `khuon_ngay_du_kien` (chốt 04/09/2026).

    Raw SQL đích danh cột, KHÔNG ORM full-select. KHÔNG backfill: `phi_khuon=0` ở phiếu cũ là một
    chỗ TRỐNG mơ hồ (dùng dao cũ, hay quên nhập?) — đoán hộ là ghi một câu trả lời mà không ai
    từng nói. Để NULL, engine giữ nguyên lời nhắc như trước cho phiếu cũ.
    """
    insp = inspect(db.get_bind())
    if "phieu_thanh_pham" not in set(insp.get_table_names()):
        return
    cols = _existing_columns(insp, "phieu_thanh_pham")
    if "khuon_nguon" not in cols:
        db.execute(text("ALTER TABLE phieu_thanh_pham ADD COLUMN khuon_nguon VARCHAR(10)"))
    if "khuon_ngay_du_kien" not in cols:
        db.execute(text("ALTER TABLE phieu_thanh_pham ADD COLUMN khuon_ngay_du_kien DATE"))
    db.commit()


MIGRATIONS.append(("0257_phieu_thanh_pham_khuon_nguon", _migrate_phieu_thanh_pham_khuon_nguon))
```

- [ ] **Step 5: Mở schema**

`backend/app/schemas/phieu_tinh_gia.py` — thêm vào cả class In và class Out của dòng thành phẩm:

```python
    khuon_nguon: str | None = None
    khuon_ngay_du_kien: date | None = None
```

(class In: `= None`; class Out: `= None`. Thêm `from datetime import date` nếu thiếu.)

⚠️ Pydantic nuốt field im lặng: field không khai ở schema Out thì service trả dict có nó vẫn bị bỏ, FE nhận `undefined`. Phải đi hết dict → hàm trung gian → schema → type TS.

- [ ] **Step 6: Tách lời nhắc của engine thành hàm riêng**

`backend/app/services/thanh_phan_engine.py` — thêm hàm cạnh `TOOLING_CO_PHI`:

```python
def _canh_bao_khuon(chain: list[dict]) -> list[str]:
    """Lời nhắc về phí khuôn, đọc theo NGUỒN KHUÔN sale đã chọn (chốt 04/09/2026).

    · `co_san` → im lặng: đó là một câu trả lời đúng, không phải chỗ trống bị bỏ quên.
    · `lam_moi` mà 0đ → nhắc: đã chọn làm dao mới thì phải có tiền, không thì báo giá thiếu.
    · chưa chọn (NULL, phiếu cũ) → giữ nguyên lời nhắc cũ.
    """
    thieu_cu: list[str] = []
    thieu_moi: list[str] = []
    for row in chain:
        cd = row.get("cong_doan") or {}
        if not cd.get("requires_tooling") or cd.get("tooling_type") not in TOOLING_CO_PHI:
            continue
        if _f(row.get("phi_khuon")) > 0:
            continue
        ten_b = row.get("ten") or cd.get("ten") or "Công đoạn"
        nguon = row.get("khuon_nguon")
        if nguon == "co_san":
            continue
        (thieu_moi if nguon == "lam_moi" else thieu_cu).append(ten_b)
    ra: list[str] = []
    if thieu_moi:
        ra.append(
            "Đã chọn làm khuôn mới nhưng chưa nhập tiền khuôn: "
            + ", ".join(thieu_moi) + " — báo giá đang thiếu khoản này."
        )
    if thieu_cu:
        ra.append(
            "Chưa cho biết khuôn có sẵn hay làm mới: " + ", ".join(thieu_cu)
            + " — để trống thì hiểu là dùng khuôn cũ, không tính tiền."
        )
    return ra
```

Ở khối `PHÍ KHUÔN` (khoảng dòng 1024-1060), thay đoạn gom `thieu_phi` + phát cảnh báo cũ bằng
`warnings.extend(_canh_bao_khuon(chain))`, giữ nguyên phần đẻ dòng tiền.

- [ ] **Step 7: Chạy test cho xanh**

```bash
cd backend && python -m pytest tests/test_phieu_tinh_gia.py -q
```

- [ ] **Step 8: UI phiếu tính giá**

`frontend/src/pages/PhieuTinhGiaDetailView.tsx` — ở khối khuôn của bước (chỗ đang render ô
`phi_khuon`), thêm bộ chọn hai nhánh phía TRƯỚC ô tiền:

```tsx
{/* NGUỒN KHUÔN — một câu hỏi, hai nhánh. Ô tiền chỉ mở khi chọn "làm mới": hỏi tiền cho một
    con dao đã có trong kho là mời người ta gõ nhầm. */}
<div className="rdx-cost__khuon-nguon">
  <label>
    <input type="radio" name={`kn-${row.key}`} checked={row.khuon_nguon === "co_san"}
           onChange={() => set("khuon_nguon", "co_san")} />
    Dùng khuôn có sẵn
  </label>
  <label>
    <input type="radio" name={`kn-${row.key}`} checked={row.khuon_nguon === "lam_moi"}
           onChange={() => set("khuon_nguon", "lam_moi")} />
    Làm khuôn mới
  </label>
</div>
```

Ô `phi_khuon` và ô `khuon_ngay_du_kien` (type `date`, nhãn "Dự kiến có khuôn") chỉ render khi
`row.khuon_nguon === "lam_moi"`. Chọn `co_san` thì `set("phi_khuon", 0)` cùng lúc.

Thêm hai field vào type dòng thành phẩm ở `frontend/src/api/client.ts`.

- [ ] **Step 9: Cập nhật DB_SCHEMA.md**

Mục `phieu_thanh_pham` — thêm hai dòng cột mới, ghi rõ `NULL = chưa chọn (phiếu cũ)` và vì sao
không backfill.

- [ ] **Step 10: Kiểm + commit**

```bash
cd frontend && npx tsc --noEmit
```

```bash
git add backend/app/models/phieu_tinh_gia.py backend/app/db_migrations.py backend/app/schemas/phieu_tinh_gia.py backend/app/services/thanh_phan_engine.py backend/tests/test_phieu_tinh_gia.py frontend/src/pages/PhieuTinhGiaDetailView.tsx frontend/src/api/client.ts docs/DB_SCHEMA.md
git commit -m "Phieu tinh gia: hoi khuon co san hay lam moi (mg 0257)"
```

---

### Task 4: Chép ý định của sale sang bước của lệnh + cảnh báo lệch

**Files:**
- Modify: `backend/app/models/lsx.py:209` (thêm 2 cột cạnh `khuon_be_id`)
- Modify: `backend/app/db_migrations.py` (mg `0258`)
- Modify: `backend/app/services/lsx_service.py` (`_tinh_dong`/dựng routing — chép field; `_buoc_dict` — trả field + cảnh báo lệch)
- Modify: `backend/app/schemas/lsx.py:230-234`
- Modify: `frontend/src/pages/lsxBuoc.ts`, `frontend/src/pages/LsxBuocDrawer.tsx`
- Modify: `docs/DB_SCHEMA.md` (mục `lsx_cong_doan`)
- Test: `backend/tests/test_lsx_service.py`

**Interfaces:**
- Consumes: `phieu_thanh_pham.khuon_nguon` / `khuon_ngay_du_kien` (Task 3).
- Produces: `lsx_cong_doan.khuon_nguon`, `lsx_cong_doan.khuon_phi`; và trong dict bước:
  `khuon_lech: str | None` — câu nhắc tiếng Việt hoặc `None`.

- [ ] **Step 1: Viết test đỏ**

Thêm vào `backend/tests/test_lsx_service.py`:

```python
def test_khuon_lech_sale_bao_co_san_ma_dao_dang_dat_lam(db, lsx_svc, ...):
    """Máy chỉ NHẮC, không chặn: tiền đã trót báo cho khách nên người phải biết mà quyết."""
    from app.services.lsx_service import canh_bao_lech_khuon
    assert canh_bao_lech_khuon("co_san", 0, "dang_dat_lam") is not None
    assert "có sẵn" in canh_bao_lech_khuon("co_san", 0, "dang_dat_lam")


def test_khuon_lech_sale_tinh_tien_ma_dung_dao_cu():
    from app.services.lsx_service import canh_bao_lech_khuon
    msg = canh_bao_lech_khuon("lam_moi", 1_200_000, "dang_dung")
    assert msg is not None and "1.200.000" in msg


def test_khuon_khong_lech_thi_im_lang():
    from app.services.lsx_service import canh_bao_lech_khuon
    assert canh_bao_lech_khuon("lam_moi", 1_200_000, "dang_dat_lam") is None
    assert canh_bao_lech_khuon("co_san", 0, "dang_dung") is None
    assert canh_bao_lech_khuon(None, 0, "dang_dung") is None
```

- [ ] **Step 2: Chạy test cho chắc nó đỏ**

```bash
cd backend && python -m pytest tests/test_lsx_service.py -q -k khuon_lech
```

- [ ] **Step 3: Thêm cột vào model**

`backend/app/models/lsx.py`, cạnh `khuon_be_id`:

```python
    # Ý ĐỊNH CỦA SALE về khuôn, chép từ phiếu tính giá lúc dựng lệnh (04/09/2026). KHÔNG phải
    # quyết định cuối: quyết định cuối là `khuon_be_id` ở trên, do kế hoạch chốt. Hai thứ này tồn
    # tại cạnh nhau để so được — lệch nhau nghĩa là tiền đã báo cho khách không khớp việc sẽ làm.
    khuon_nguon: Mapped[str | None] = mapped_column(String(10), nullable=True)  # co_san|lam_moi
    khuon_phi: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, server_default="0", default=0)
```

- [ ] **Step 4: Viết migration 0258**

```python
def _migrate_lsx_cong_doan_khuon_nguon(db) -> None:
    """mg 0258 — `lsx_cong_doan.khuon_nguon` + `khuon_phi` (chốt 04/09/2026).

    Không backfill từ `phieu_thanh_pham`: lệnh đã dựng xong là ảnh chụp của thời điểm dựng, tra
    ngược phiếu bây giờ có thể lấy nhầm phiên bản phiếu đã sửa sau đó.
    """
    insp = inspect(db.get_bind())
    if "lsx_cong_doan" not in set(insp.get_table_names()):
        return
    cols = _existing_columns(insp, "lsx_cong_doan")
    if "khuon_nguon" not in cols:
        db.execute(text("ALTER TABLE lsx_cong_doan ADD COLUMN khuon_nguon VARCHAR(10)"))
    if "khuon_phi" not in cols:
        db.execute(text(
            "ALTER TABLE lsx_cong_doan ADD COLUMN khuon_phi NUMERIC(18,2) NOT NULL DEFAULT 0"
        ))
    db.commit()


MIGRATIONS.append(("0258_lsx_cong_doan_khuon_nguon", _migrate_lsx_cong_doan_khuon_nguon))
```

- [ ] **Step 5: Viết hàm cảnh báo lệch**

`backend/app/services/lsx_service.py`, cấp module (trước class):

```python
def canh_bao_lech_khuon(nguon: str | None, phi: float | None, tinh_trang: str | None) -> str | None:
    """Sale định một đằng, kế hoạch chốt một nẻo → một câu nhắc. KHÔNG chặn.

    Máy chỉ ghi nhận: nó không biết xưởng sẽ báo lại khách hay tự nuốt chi phí, nên nó nói ra chỗ
    lệch rồi để người quyết. Chưa chọn nguồn (phiếu cũ) hoặc chưa trỏ dao → không có gì để so.
    """
    if not nguon or not tinh_trang:
        return None
    if nguon == "co_san" and tinh_trang == "dang_dat_lam":
        return "Sale báo dùng khuôn có sẵn, nhưng khuôn này đang đặt làm."
    if nguon == "lam_moi" and tinh_trang == "dang_dung" and float(phi or 0) > 0:
        return (
            f"Sale đã tính {float(phi or 0):,.0f}".replace(",", ".")
            + " đồng tiền làm khuôn, nhưng bước này dùng khuôn có sẵn."
        )
    return None
```

- [ ] **Step 6: Chép field lúc dựng lệnh + trả ra dict bước**

Trong `lsx_service.py`:
- Chỗ dựng routing từ `PhieuThanhPham` (hàm `_tinh_dong` / nơi map dòng phiếu → dict bước): chép
  `khuon_nguon` và `phi_khuon` → `khuon_phi`.
- Thêm hai tên cột vào danh sách kế thừa ở `_KE_THUA`/tuple cột dòng ~2720 và ~2734 để lưu/đọc
  không rơi field.
- Trong `_buoc_dict` (~2239), sau khối `khuon_map`, thêm:

```python
            "khuon_nguon": cd.khuon_nguon,
            "khuon_phi": float(cd.khuon_phi or 0),
            "khuon_lech": canh_bao_lech_khuon(
                cd.khuon_nguon, cd.khuon_phi,
                (khuon_map or {}).get(cd.khuon_be_id, {}).get("khuon_be_tinh_trang"),
            ),
```

- [ ] **Step 7: Mở schema + FE**

`backend/app/schemas/lsx.py` (cạnh `requires_tooling`):

```python
    khuon_nguon: str | None = None
    khuon_phi: float = 0
    khuon_lech: str | None = None
```

`frontend/src/pages/lsxBuoc.ts`: thêm 3 field vào type bước.
`frontend/src/pages/LsxBuocDrawer.tsx`: trong khối khuôn, phía trên ô chọn dao, hiện dòng ý định
sale và (nếu có) băng nhắc:

```tsx
{row.khuon_nguon && (
  <p className="khsx-khuon__y-dinh">
    Sale báo: {row.khuon_nguon === "lam_moi"
      ? `làm khuôn mới${row.khuon_phi ? `, ${row.khuon_phi.toLocaleString("vi-VN")}đ` : ""}`
      : "dùng khuôn có sẵn"}
  </p>
)}
{row.khuon_lech && <p className="khsx-khuon__lech">{row.khuon_lech}</p>}
```

Thêm CSS `.khsx-khuon__lech` (tone amber) vào `ke-hoach-sx.css`.

- [ ] **Step 8: Chạy test + tsc**

```bash
cd backend && python -m pytest tests/test_lsx_service.py -q
```

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 9: Cập nhật DB_SCHEMA.md + commit**

```bash
git add backend/app/models/lsx.py backend/app/db_migrations.py backend/app/services/lsx_service.py backend/app/schemas/lsx.py backend/tests/test_lsx_service.py frontend/src/pages/lsxBuoc.ts frontend/src/pages/LsxBuocDrawer.tsx frontend/src/pages/ke-hoach-sx.css docs/DB_SCHEMA.md
git commit -m "Lenh SX: chep y dinh khuon cua sale + nhac khi lech (mg 0258)"
```

---

### Task 5: Cửa "Sẵn sàng lập kế hoạch" đòi đủ khuôn

**Files:**
- Modify: `backend/app/services/lsx_service.py:1565-1640` (`thieu_cua`), `:1248-1266` (`_thieu` — sửa chú thích lỗi thời)
- Modify: `frontend/src/pages/keHoachSxShared.tsx` hoặc nơi map mã thiếu → nhãn tiếng Việt
- Test: `backend/tests/test_lsx_service.py`

**Interfaces:**
- Consumes: `requires_tooling` / `tooling_type` đã nạp theo lô trong `thieu_cua` (dòng 1575).
- Produces: mã thiếu `"thieu_khuon"`.

- [ ] **Step 1: Viết test đỏ**

```python
def test_thieu_khuon_chan_san_sang(db, lsx_svc, lsx_co_buoc_be):
    """Bước bế chưa trỏ dao → không qua cửa. Đứng ngang hàng với thiếu nhà gia công: cùng một
    danh sách, người dùng không phải học luật mới."""
    thieu = lsx_svc.thieu_cua(lsx_co_buoc_be)
    assert "thieu_khuon" in thieu


def test_tro_dao_roi_thi_het_thieu_khuon(db, lsx_svc, lsx_co_buoc_be, khuon):
    buoc = [cd for cd in lsx_co_buoc_be.cong_doans if cd.ten == "Bế"][0]
    buoc.khuon_be_id = khuon.id
    db.flush()
    assert "thieu_khuon" not in lsx_svc.thieu_cua(lsx_co_buoc_be)
```

(Fixture `lsx_co_buoc_be` dựng lệnh có một bước trỏ công đoạn `requires_tooling=True,
tooling_type="khuon_be"`; `khuon` là một dòng `KhuonBe` `tinh_trang="dang_dung"`.)

- [ ] **Step 2: Chạy test cho chắc nó đỏ**

```bash
cd backend && python -m pytest tests/test_lsx_service.py -q -k thieu_khuon
```

- [ ] **Step 3: Thêm điều kiện**

Trong `thieu_cua`, ở vòng lặp `for cd in lsx.cong_doans` (chỗ đang kiểm `thieu_to_may` /
`thieu_ncc`), thêm:

```python
            # Bước cần dụng cụ lưu kho mà chưa trỏ con dao nào → chưa chạy được, chặn y như
            # thiếu nhà gia công. Danh sách dụng cụ đọc từ CỜ của công đoạn (`co_dung_cu` nạp
            # theo lô ở trên), không ghi cứng tên bước.
            can, loai_dc = co_dung_cu.get(cd.cong_doan_id, (False, None))
            if can and loai_dc in TOOLING_CO_KHO and cd.khuon_be_id is None:
                if "thieu_khuon" not in thieu:
                    thieu.append("thieu_khuon")
```

Khai cạnh các hằng đầu file:

```python
# Dụng cụ LƯU KHO — bước dùng chúng phải trỏ vào một dòng `khuon_be`. Bám đúng bộ mã của
# `cong_doan.TOOLING_TYPE`; `kem` KHÔNG có mặt (bản kẽm là vật tư tiêu hao, mỗi bài phơi mới).
TOOLING_CO_KHO = frozenset({"khuon_be", "khuon_ep", "khung_lua"})
```

- [ ] **Step 4: Sửa chú thích lỗi thời ở `_thieu`**

Thay ba dòng chú thích ở `_thieu` (nói *"từ 16/08 khuôn ra khỏi lệnh hẳn (mg 0203)"*) bằng:

```python
        # Khuôn KHÔNG kiểm ở đây: `_thieu` chấm "job readiness" của một dòng ĐƠN trước khi lệnh ra
        # đời, lúc đó chưa có bước nào để trỏ dao. Điều kiện khuôn nằm ở `thieu_cua` (checklist của
        # LỆNH đã có routing) — xem mã `thieu_khuon` ở đó.
        # ⚠️ Chú thích cũ ở đây ghi "khuôn ra khỏi lệnh hẳn (mg 0203)" — SAI từ mg `0205`, khuôn đã
        # được nối lại qua `lsx_cong_doan.khuon_be_id`.
```

- [ ] **Step 5: Chạy test cho xanh**

```bash
cd backend && python -m pytest tests/test_lsx_service.py -q
```

- [ ] **Step 6: Nhãn tiếng Việt ở FE**

Tìm map mã thiếu → nhãn (`thieu_ncc`, `thieu_to_may`…) và thêm:

```ts
  thieu_khuon: "Thiếu khuôn / khung",
```

- [ ] **Step 7: Kiểm + commit**

```bash
cd frontend && npx tsc --noEmit
```

```bash
git add backend/app/services/lsx_service.py backend/tests/test_lsx_service.py frontend/src/pages/keHoachSxShared.tsx
git commit -m "Cua San sang lap ke hoach doi du khuon cho buoc can dung cu"
```

---

### Task 6: Chip khuôn + chip loại bước ra khỏi drawer, lên bảng công đoạn

**Files:**
- Modify: `frontend/src/pages/LsxRoutingTable.tsx` (cột tên bước)
- Modify: `frontend/src/components/DagNodeCard.tsx` (thay chip tự vẽ bằng component chung)
- Test: thủ công qua dev-browser ở Task 13 (không có test đơn vị cho lớp render bảng này)

**Interfaces:**
- Consumes: `ChipLoaiBuoc`, `ChipKhuon` (Task 2); `khuon_be_ma` / `khuon_be_so_ke` /
  `khuon_be_tinh_trang` / `khuon_be_ngay_ve` / `requires_tooling` đã có sẵn trong dict bước.

- [ ] **Step 1: Thay chip tự vẽ bằng component chung**

`LsxRoutingTable.tsx` — trong ô tên bước, thay
`<span className={`khsx-lb khsx-lb--${meta.tone}`}>{meta.label}</span>` bằng:

```tsx
<ChipLoaiBuoc loai_buoc={r.loai_buoc} nha_cung_cap={r.nha_cung_cap} />
<ChipKhuon
  can_khuon={r.requires_tooling}
  khuon={{ ma: r.khuon_be_ma, so_ke: r.khuon_be_so_ke,
           tinh_trang: r.khuon_be_tinh_trang, ngay_ve_du_kien: r.khuon_be_ngay_ve }}
/>
```

Import từ `../components/ChipBuoc`. Giữ nguyên chip `tùy chọn` bên cạnh.

- [ ] **Step 2: Cùng việc đó ở thẻ DAG**

`DagNodeCard.tsx:74` — thay chip đọc `LSX_LOAI_BUOC_META` bằng `<ChipLoaiBuoc …/>` và thêm
`<ChipKhuon …/>` bên dưới tên bước.

- [ ] **Step 3: Kiểm**

```bash
cd frontend && npx vitest run src/components && npx tsc --noEmit
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/LsxRoutingTable.tsx frontend/src/components/DagNodeCard.tsx
git commit -m "Ke hoach SX: chip khuon ra khoi drawer, hien tren bang cong doan va the DAG"
```

---

### Task 7: Chụp khuôn + nhà gia công vào công việc lúc phát hành

**Files:**
- Modify: `backend/app/models/san_xuat.py:224-258` (5 cột mới trên `SanXuatCongViec`)
- Modify: `backend/app/db_migrations.py` (mg `0259`)
- Modify: `backend/app/services/san_xuat/snapshot.py:160-185`
- Modify: `docs/DB_SCHEMA.md` (mục `san_xuat_cong_viec`)
- Test: `backend/tests/test_san_xuat_release.py`

**Interfaces:**
- Consumes: `lsx_cong_doan.khuon_be_id`, `nha_cung_cap`.
- Produces: `SanXuatCongViec.nha_cung_cap`, `.khuon_json`, `.khuon_nhan_luc`, `.khuon_nhan_by_id`,
  `.khuon_tra_luc`. Task 8 đọc `khuon_json` + ghi `khuon_nhan_luc`.
  `khuon_json` shape: `{"id", "ma", "ten", "loai", "so_ke", "tinh_trang", "ngay_ve_du_kien"}`.

- [ ] **Step 1: Viết test đỏ**

Thêm vào `backend/tests/test_san_xuat_release.py`:

```python
def test_phat_hanh_chup_khuon_va_nha_gia_cong(db, ...):
    """Khuôn được CHỤP chứ không tra sống: bàn tổ phải thấy đúng con dao đã chốt lúc phát hành,
    kể cả khi kế hoạch đổi dao sau đó."""
    # ... dựng lệnh có 1 bước bế trỏ dao KB-0001 (so_ke="Kệ A3") + 1 bước thuê ngoài
    cvs = {cv.ten_cong_doan: cv for cv in db.query(SanXuatCongViec).all()}
    be = cvs["Bế"]
    assert be.khuon_json["ma"] == "KB-0001"
    assert be.khuon_json["so_ke"] == "Kệ A3"
    assert be.khuon_nhan_luc is None
    assert cvs["Cán màng"].nha_cung_cap == "Cơ sở Minh Phát"
```

- [ ] **Step 2: Chạy test cho chắc nó đỏ**

```bash
cd backend && python -m pytest tests/test_san_xuat_release.py -q -k chup_khuon
```

- [ ] **Step 3: Thêm cột vào model**

`backend/app/models/san_xuat.py`, cạnh `vat_tu_json`:

```python
    # Nhà gia công — ẢNH CHỤP lúc phát hành, để chip "Ngoài · <nơi làm>" hiện được ở bàn tổ và
    # các màn theo dõi mà không phải tra ngược lệnh.
    nha_cung_cap: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # KHUÔN/KHUNG của bước — ảnh chụp cùng kiểu với `vat_tu_json`. Chụp chứ không tra sống: tổ
    # phải thấy đúng con dao đã chốt lúc phát hành, kể cả khi kế hoạch đổi dao sau đó.
    # {"id","ma","ten","loai","so_ke","tinh_trang","ngay_ve_du_kien"} · NULL = bước không cần dụng cụ.
    khuon_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Tổ tích "đã nhận khuôn" — ĐIỂM CHẶN DUY NHẤT của luật "bế phải có khuôn mới làm được".
    # Không chặn ở xếp lịch: ngày dự kiến có khuôn không đủ tin để chặn ai (chốt 04/09/2026).
    khuon_nhan_luc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    khuon_nhan_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Trả dao về kệ — KHÔNG chặn gì, chỉ để hệ thống không mất dấu con dao sau khi nó rời kệ.
    khuon_tra_luc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 4: Viết migration 0259**

```python
def _migrate_cong_viec_khuon(db) -> None:
    """mg 0259 — `san_xuat_cong_viec`: `nha_cung_cap` + khối khuôn (chốt 04/09/2026).

    Raw SQL đích danh cột. Không backfill: công việc đã phát hành trước hôm nay không có ảnh chụp
    khuôn, và dựng lại ảnh chụp từ lệnh HIỆN TẠI là ghi một sự thật của hôm nay vào một mốc quá khứ.
    """
    insp = inspect(db.get_bind())
    if "san_xuat_cong_viec" not in set(insp.get_table_names()):
        return
    cols = _existing_columns(insp, "san_xuat_cong_viec")
    them = {
        "nha_cung_cap": "VARCHAR(255)",
        "khuon_json": "JSON",
        "khuon_nhan_luc": "TIMESTAMP WITH TIME ZONE",
        "khuon_nhan_by_id": "INTEGER",
        "khuon_tra_luc": "TIMESTAMP WITH TIME ZONE",
    }
    for ten, kieu in them.items():
        if ten not in cols:
            db.execute(text(f"ALTER TABLE san_xuat_cong_viec ADD COLUMN {ten} {kieu}"))
    db.commit()


MIGRATIONS.append(("0259_cong_viec_khuon", _migrate_cong_viec_khuon))
```

- [ ] **Step 5: Chụp lúc phát hành**

`backend/app/services/san_xuat/snapshot.py` — thêm helper cạnh `_vat_tu`:

```python
def _khuon(db, cd) -> dict | None:
    """Ảnh chụp con dao của bước. `None` khi bước không trỏ dao nào (kể cả bước không cần dụng cụ).

    Đọc đích danh cột thay vì trả cả object: ảnh chụp phải là dữ liệu chết, không phải một hàng ORM
    còn sống mà lần đọc sau lại ra giá trị khác.
    """
    kid = getattr(cd, "khuon_be_id", None)
    if not kid:
        return None
    from ...models.khuon_be import KhuonBe
    k = db.get(KhuonBe, kid)
    if k is None:
        return None
    return {
        "id": k.id, "ma": k.ma, "ten": k.ten, "loai": k.loai, "so_ke": k.so_ke,
        "tinh_trang": k.tinh_trang,
        "ngay_ve_du_kien": k.ngay_ve_du_kien.isoformat() if k.ngay_ve_du_kien else None,
    }
```

Trong `SanXuatCongViec(...)` (dòng ~177) thêm:

```python
            nha_cung_cap=getattr(cd, "nha_cung_cap", None),
            khuon_json=_khuon(repo.db, cd),
```

(Nếu `repo` không phơi `db`, truyền `Session` xuống hàm dựng — xem chữ ký `dung_cong_viec`.)

- [ ] **Step 6: Chạy test cho xanh**

```bash
cd backend && python -m pytest tests/test_san_xuat_release.py tests/test_san_xuat_release_phan_doan.py -q
```

- [ ] **Step 7: Cập nhật DB_SCHEMA.md + commit**

```bash
git add backend/app/models/san_xuat.py backend/app/db_migrations.py backend/app/services/san_xuat/snapshot.py backend/tests/test_san_xuat_release.py docs/DB_SCHEMA.md
git commit -m "Phat hanh SX: chup khuon va nha gia cong vao cong viec (mg 0259)"
```

---

### Task 8: Bàn tổ — tích "đã nhận khuôn", chặn Bắt đầu, tích "đã trả"

**Files:**
- Modify: `backend/app/services/san_xuat/thuc_thi.py:221` (`bat_dau` — cổng), thêm `nhan_khuon` / `tra_khuon`
- Modify: `backend/app/services/san_xuat/board.py:245` (bơm khuôn ra thẻ việc)
- Modify: `backend/app/schemas/san_xuat.py:46-78` (`WorkItemOut`)
- Modify: `backend/app/routers/` — router thực hiện SX (2 endpoint mới)
- Modify: `frontend/src/pages/ThsxDrawer.tsx`, `frontend/src/pages/thsxShared.tsx`, `frontend/src/api/client.ts`
- Test: `backend/tests/test_san_xuat_thuc_thi.py`

**Interfaces:**
- Consumes: `SanXuatCongViec.khuon_json` / `.khuon_nhan_luc` (Task 7); `ChipKhuon` (Task 2).
- Produces:
  ```python
  def nhan_khuon(db, *, user, cong_viec_id: int) -> dict   # {"khuon_nhan_luc": iso}
  def tra_khuon(db, *, user, cong_viec_id: int) -> dict    # {"khuon_tra_luc": iso}
  ```
  `WorkItemOut.khuon: KhuonChipOut | None`, `WorkItemOut.khuon_da_nhan: bool`,
  `WorkItemOut.nha_cung_cap: str | None`.

- [ ] **Step 1: Viết test đỏ**

Thêm vào `backend/tests/test_san_xuat_thuc_thi.py`:

```python
def test_chua_nhan_khuon_thi_khong_bat_dau_duoc(db, ...):
    """Điểm chặn DUY NHẤT của luật 'bế phải có khuôn mới làm được'. Trước điểm này — xếp lịch,
    kéo thả, phát hành — máy không cản gì cả."""
    cv = ...  # công việc bế đã phát hành, khuon_json có, khuon_nhan_luc None, roster đủ thợ khoán
    with pytest.raises(ValueError, match="Chưa nhận khuôn"):
        thuc_thi.bat_dau(db, user=to_truong, cong_viec_id=cv.id)


def test_tich_nhan_khuon_roi_thi_bat_dau_duoc(db, ...):
    cv = ...
    thuc_thi.nhan_khuon(db, user=to_truong, cong_viec_id=cv.id)
    assert cv.khuon_nhan_luc is not None and cv.khuon_nhan_by_id == to_truong.id
    thuc_thi.bat_dau(db, user=to_truong, cong_viec_id=cv.id)
    assert cv.trang_thai == CV_DANG_CHAY


def test_buoc_khong_can_khuon_khong_bi_chan(db, ...):
    cv = ...  # khuon_json None
    thuc_thi.bat_dau(db, user=to_truong, cong_viec_id=cv.id)
    assert cv.trang_thai == CV_DANG_CHAY


def test_tra_khuon_khong_chan_gi(db, ...):
    cv = ...
    thuc_thi.nhan_khuon(db, user=to_truong, cong_viec_id=cv.id)
    thuc_thi.tra_khuon(db, user=to_truong, cong_viec_id=cv.id)
    assert cv.khuon_tra_luc is not None
```

- [ ] **Step 2: Chạy test cho chắc nó đỏ**

```bash
cd backend && python -m pytest tests/test_san_xuat_thuc_thi.py -q -k khuon
```

- [ ] **Step 3: Thêm cổng vào `bat_dau`**

Trong `thuc_thi.bat_dau`, ngay sau cổng "bước ghép" (§10.2) và TRƯỚC cổng trễ giờ:

```python
    # Cổng KHUÔN/KHUNG: bước có dụng cụ lưu kho thì phải có người xác nhận dao đang nằm trên bàn.
    # Đây là điểm chặn DUY NHẤT của luật — ngày dự kiến có khuôn không chặn xếp lịch (chốt
    # 04/09/2026), vì ngày đó không đủ tin để chặn ai.
    if cv.khuon_json and cv.khuon_nhan_luc is None:
        ma = (cv.khuon_json or {}).get("ma") or "khuôn"
        raise ValueError(
            f"Chưa nhận khuôn/khung ({ma}) — tích “Đã nhận” trước khi bắt đầu."
        )
```

- [ ] **Step 4: Viết hai hàm ghi**

Cuối `thuc_thi.py`:

```python
def nhan_khuon(db: Session, *, user, cong_viec_id: int) -> dict:
    """Tổ xác nhận đã cầm con dao trong tay. Tích một lần, không gỡ được — gỡ ra thì cái mốc
    "ai nói dao đã ở đây, lúc mấy giờ" mất nghĩa."""
    repo = SanXuatThucThiRepository(db)
    cv = _lay_cong_viec(repo, cong_viec_id)
    _gate(db, user, cv)
    if not cv.khuon_json:
        raise ValueError("Bước này không dùng khuôn/khung.")
    if cv.khuon_nhan_luc is not None:
        raise ValueError("Khuôn của bước này đã được xác nhận nhận.")
    cv.khuon_nhan_luc = _moc()
    cv.khuon_nhan_by_id = getattr(user, "id", None)
    db.flush()
    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_nhan_khuon",
        target=f"san_xuat_cong_viec:{cv.id}",
        detail=(cv.khuon_json or {}).get("ma"),
    )
    return {"khuon_nhan_luc": cv.khuon_nhan_luc.isoformat()}


def tra_khuon(db: Session, *, user, cong_viec_id: int) -> dict:
    """Trả dao về kệ. KHÔNG chặn gì — chỉ để hệ thống khỏi mất dấu con dao sau khi nó rời kệ,
    đúng việc kho dao sinh ra để khỏi phải đi hỏi từng tổ."""
    repo = SanXuatThucThiRepository(db)
    cv = _lay_cong_viec(repo, cong_viec_id)
    _gate(db, user, cv)
    if not cv.khuon_json:
        raise ValueError("Bước này không dùng khuôn/khung.")
    cv.khuon_tra_luc = _moc()
    db.flush()
    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_tra_khuon",
        target=f"san_xuat_cong_viec:{cv.id}",
        detail=(cv.khuon_json or {}).get("ma"),
    )
    return {"khuon_tra_luc": cv.khuon_tra_luc.isoformat()}
```

Bổ sung import `AuditLogRepository` nếu file chưa có.

- [ ] **Step 5: Chạy test cho xanh**

```bash
cd backend && python -m pytest tests/test_san_xuat_thuc_thi.py -q
```

- [ ] **Step 6: Bơm ra thẻ việc + schema**

`backend/app/schemas/san_xuat.py`:

```python
class KhuonChipOut(BaseModel):
    """Ảnh chụp khuôn của bước, đủ để vẽ chip — KHÔNG phải bản sao của danh mục."""
    ma: str | None = None
    ten: str | None = None
    so_ke: str | None = None
    tinh_trang: str | None = None
    ngay_ve_du_kien: str | None = None
```

Thêm vào `WorkItemOut`:

```python
    nha_cung_cap: str | None = None
    khuon: KhuonChipOut | None = None
    khuon_da_nhan: bool = False
    khuon_da_tra: bool = False
```

`board.py:245` — cạnh `"dinh_muc_vat_tu"`:

```python
        "nha_cung_cap": cv.nha_cung_cap,
        "khuon": cv.khuon_json or None,
        "khuon_da_nhan": cv.khuon_nhan_luc is not None,
        "khuon_da_tra": cv.khuon_tra_luc is not None,
```

- [ ] **Step 7: Hai endpoint**

Trong router Thực hiện SX, cạnh các action của công việc:

```python
@router.post("/cong-viec/{cong_viec_id}/nhan-khuon")
def nhan_khuon(cong_viec_id: int, db: Session = Depends(get_db), user=Depends(...)):
    try:
        return thuc_thi.nhan_khuon(db, user=user, cong_viec_id=cong_viec_id)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
```

Tương tự `tra-khuon`. Bám đúng mẫu try/except và `Depends` của các endpoint kề bên.

- [ ] **Step 8: UI bàn tổ**

`ThsxDrawer.tsx` — khối khuôn trên thẻ việc:

```tsx
{viec.khuon && (
  <div className="thsx-khuon">
    <ChipKhuon can_khuon khuon={{ ...viec.khuon, da_nhan: viec.khuon_da_nhan }} />
    {viec.khuon.so_ke && <span className="thsx-khuon__ke">Lấy ở {viec.khuon.so_ke}</span>}
    {!viec.khuon_da_nhan && (
      <Button variant="secondary" onClick={() => nhanKhuon(viec.id)}>Đã nhận khuôn</Button>
    )}
    {viec.khuon_da_nhan && !viec.khuon_da_tra && viec.trang_thai === "completed" && (
      <Button variant="ghost" onClick={() => traKhuon(viec.id)}>Đã trả khuôn về kệ</Button>
    )}
  </div>
)}
```

Thẻ việc cũng gắn `<ChipLoaiBuoc loai_buoc={viec.loai_buoc} nha_cung_cap={viec.nha_cung_cap} />`.
Thêm hai hàm gọi API vào `client.ts` + CSS `.thsx-khuon` vào `thuc-hien-sx.css`.

- [ ] **Step 9: Kiểm + commit**

```bash
cd backend && python -m pytest tests/test_san_xuat_thuc_thi.py tests/test_san_xuat_board.py -q
```

```bash
cd frontend && npx tsc --noEmit
```

```bash
git add backend/app/services/san_xuat/thuc_thi.py backend/app/services/san_xuat/board.py backend/app/schemas/san_xuat.py backend/app/routers backend/tests/test_san_xuat_thuc_thi.py frontend/src/pages/ThsxDrawer.tsx frontend/src/pages/thsxShared.tsx frontend/src/pages/thuc-hien-sx.css frontend/src/api/client.ts
git commit -m "Ban to: tich da nhan khuon moi bat dau duoc, them tich da tra"
```

---

### Task 9: Phiếu công nghệ in mã dao + số kệ

**Files:**
- Modify: `backend/app/services/lenh_sx/phieu_cong_nghe.py:355-370` (dòng bước)
- Test: `backend/tests/test_lsx_tong_quan.py` (hoặc test phiếu công nghệ hiện có)

**Interfaces:**
- Consumes: `khuon_be_ma` / `khuon_be_so_ke` / `khuon_be_tinh_trang` / `khuon_be_ngay_ve` trong
  dict bước (đã có từ `_khuon_map`).

- [ ] **Step 1: Viết test đỏ**

```python
def test_phieu_cong_nghe_in_ma_dao_va_so_ke(db, ...):
    """Thợ cầm tờ giấy đi lấy dao chứ không mở màn hình — thiếu số kệ ở đây là hỏng cả chuỗi dù
    phần mềm có đủ dữ liệu."""
    noi_dung = phieu_cong_nghe.dung(...)
    assert "KB-0001" in noi_dung and "Kệ A3" in noi_dung
```

(Bám đúng cách test hiện có soi nội dung phiếu — nếu phiếu trả cấu trúc dict/list thì assert trên
cấu trúc đó thay vì chuỗi.)

- [ ] **Step 2: Chạy test cho chắc nó đỏ**

```bash
cd backend && python -m pytest tests/test_lsx_tong_quan.py -q -k phieu_cong_nghe
```

- [ ] **Step 3: In khuôn vào dòng bước**

Ngay cạnh chỗ ghép nhà gia công vào ô "Loại bước" (dòng ~359-363):

```python
        # KHUÔN/KHUNG đi cùng ô đó: thợ đọc một chỗ là biết "bước này ai làm, lấy dao ở đâu".
        # Dao chưa về thì nói thẳng ngày dự kiến — im lặng là để thợ đi tìm một con dao không có.
        k_ma = (node.get("khuon_be_ma") or "").strip()
        if k_ma:
            if node.get("khuon_be_tinh_trang") == "dang_dat_lam":
                ng = node.get("khuon_be_ngay_ve")
                dong.append(f"{k_ma} — chưa về" + (f", dự kiến {_ngay(ng)}" if ng else ""))
            else:
                ke = (node.get("khuon_be_so_ke") or "").strip()
                dong.append(f"{k_ma}" + (f" — {ke}" if ke else ""))
```

Ghép vào đúng cấu trúc hàng của phiếu (cùng ô với `ncc`, theo mẫu đang có ở dòng 359-365).

- [ ] **Step 4: Chạy test cho xanh + commit**

```bash
cd backend && python -m pytest tests/test_lsx_tong_quan.py -q
```

```bash
git add backend/app/services/lenh_sx/phieu_cong_nghe.py backend/tests/test_lsx_tong_quan.py
git commit -m "Phieu cong nghe: in ma dao va so ke o dong buoc"
```

---

### Task 10: Xếp lịch 2 — chip thay cho suy đoán từ nhà cung cấp

**Files:**
- Modify: `backend/app/services/xep_lich_service.py:2200-2210` (dict dòng — thêm khối khuôn)
- Modify: `frontend/src/pages/Xl2Gantt.tsx`, `frontend/src/pages/xl2Shared.tsx`, `frontend/src/pages/XepLich2Page.tsx`
- Test: `backend/tests/test_xep_lich_2.py`

**Interfaces:**
- Consumes: `lsx_cong_doan.khuon_be_id` + danh mục `KhuonBe`.
- Produces: dòng xếp lịch mang thêm `khuon_ma`, `khuon_so_ke`, `khuon_tinh_trang`,
  `khuon_ngay_ve`, `requires_tooling`.

- [ ] **Step 1: Viết test đỏ**

```python
def test_dong_xep_lich_mang_theo_khuon(db, ...):
    """Xếp lịch KHÔNG chặn theo ngày dao về (chốt 04/09/2026) — nhưng phải HIỆN, để người điều độ
    biết trước thay vì phát hiện lúc tổ không bắt đầu được."""
    ds = svc.danh_sach(...)
    dong_be = [d for d in ds["dong"] if d["cong_doan_ten"] == "Bế"][0]
    assert dong_be["khuon_ma"] == "KB-0001"
    assert dong_be["khuon_so_ke"] == "Kệ A3"
    assert dong_be["requires_tooling"] is True
```

- [ ] **Step 2: Chạy test cho chắc nó đỏ**

```bash
cd backend && python -m pytest tests/test_xep_lich_2.py -q -k mang_theo_khuon
```

- [ ] **Step 3: Bơm khuôn vào dict dòng**

`xep_lich_service.py` (~2202) — nạp map khuôn theo LÔ (một query cho cả danh sách, không tra lẻ
từng dòng: đây là màn trả hàng trăm dòng), rồi thêm vào dict:

```python
                "requires_tooling": bool(cd_cua_dong.get("requires_tooling")),
                "khuon_ma": k.get("ma"), "khuon_so_ke": k.get("so_ke"),
                "khuon_tinh_trang": k.get("tinh_trang"), "khuon_ngay_ve": k.get("ngay_ve_du_kien"),
```

- [ ] **Step 4: Chạy test cho xanh**

```bash
cd backend && python -m pytest tests/test_xep_lich_2.py -q
```

- [ ] **Step 5: FE — chip trên thanh Gantt và bảng dòng**

`Xl2Gantt.tsx`: trong nhãn thanh, thêm `<ChipLoaiBuoc …/>` + `<ChipKhuon …/>`.
`xl2Shared.tsx`: giữ nguyên hàm phân nhóm màu, nhưng đổi nguồn từ `isNcc` (suy từ tên nhà cung cấp)
sang `loai_buoc === "thue_ngoai"` — chú thích lại lý do:

```ts
// Đổi 04/09/2026: nhóm màu đọc LOẠI BƯỚC, không suy từ tên nhà cung cấp nữa. Suy từ NCC thì bước
// đã gán Thuê ngoài mà chưa điền nơi làm rơi về nhóm thường — đúng chỗ nhãn biến mất giữa đường.
```

`XepLich2Page.tsx`: thêm hai chip vào ô tên bước của bảng dòng.

- [ ] **Step 6: Kiểm + commit**

```bash
cd frontend && npx tsc --noEmit
```

```bash
git add backend/app/services/xep_lich_service.py backend/tests/test_xep_lich_2.py frontend/src/pages/Xl2Gantt.tsx frontend/src/pages/xl2Shared.tsx frontend/src/pages/XepLich2Page.tsx
git commit -m "Xep lich 2: chip loai buoc + khuon, bo suy doan tu nha cung cap"
```

---

### Task 11: Theo dõi sản xuất — chip vào Kanban, Theo máy, Theo ca

**Files:**
- Modify: `backend/app/schemas/theo_doi_san_xuat.py` (`KanbanChipOut`, `MayLaneBlockOut`, `CaViecOut`)
- Modify: `backend/app/services/lenh_sx/bang_theo_doi.py` (3 chỗ dựng thẻ)
- Modify: `frontend/src/pages/TdsxKanban.tsx`, `TdsxTheoMay.tsx`, `TdsxTheoCa.tsx`, `frontend/src/api/client.ts`
- Test: `backend/tests/test_theo_doi_kanban.py`, `backend/tests/test_theo_doi_may_ca_gantt.py`

**Interfaces:**
- Consumes: `SanXuatCongViec.loai_buoc` / `.nha_cung_cap` / `.khuon_json` / `.khuon_nhan_luc` (Task 7).
- Produces: schema con dùng chung
  ```python
  class NhanBuocOut(BaseModel):
      loai_buoc: str | None = None
      nha_cung_cap: str | None = None
      khuon_ma: str | None = None
      khuon_so_ke: str | None = None
      khuon_tinh_trang: str | None = None
      khuon_ngay_ve: str | None = None
      khuon_da_nhan: bool = False
  ```
  nhúng vào cả ba schema dưới tên field `nhan`.

- [ ] **Step 1: Viết test đỏ**

```python
def test_kanban_chip_mang_nhan_buoc(db, ...):
    """Nhãn đi theo bước tới tận màn theo dõi — trước đây bốn tab Theo dõi SX không có một chữ nào
    về thuê ngoài hay khuôn."""
    board = bang_theo_doi.kanban(db, ...)
    chip = board["cards"][0]["chip_dang_chay"][0]
    assert chip["nhan"]["loai_buoc"] == "thue_ngoai"
    assert chip["nhan"]["nha_cung_cap"] == "Cơ sở Minh Phát"


def test_theo_may_block_mang_nhan_buoc(db, ...):
    lanes = bang_theo_doi.theo_may(db, ...)
    block = lanes["lanes"][0]["blocks"][0]
    assert block["nhan"]["khuon_ma"] == "KB-0001"
```

- [ ] **Step 2: Chạy test cho chắc nó đỏ**

```bash
cd backend && python -m pytest tests/test_theo_doi_kanban.py tests/test_theo_doi_may_ca_gantt.py -q -k nhan_buoc
```

- [ ] **Step 3: Viết schema con + helper dựng**

Thêm `NhanBuocOut` vào `schemas/theo_doi_san_xuat.py`, thêm `nhan: NhanBuocOut | None = None` vào
`KanbanChipOut`, `MayLaneBlockOut`, `CaViecOut`.

Trong `bang_theo_doi.py`, một helper duy nhất:

```python
def _nhan(cv) -> dict:
    """Khối nhãn của MỘT công việc — dùng chung cho Kanban / Theo máy / Theo ca.

    Một hàm chứ không ba: ba chỗ tự dựng lấy là ba cơ hội để một chỗ quên field, rồi nhãn lại đứt
    ở đúng một tab mà không ai để ý.
    """
    k = cv.khuon_json or {}
    return {
        "loai_buoc": cv.loai_buoc,
        "nha_cung_cap": cv.nha_cung_cap,
        "khuon_ma": k.get("ma"),
        "khuon_so_ke": k.get("so_ke"),
        "khuon_tinh_trang": k.get("tinh_trang"),
        "khuon_ngay_ve": k.get("ngay_ve_du_kien"),
        "khuon_da_nhan": cv.khuon_nhan_luc is not None,
    }
```

Gắn `"nhan": _nhan(cv)` vào ba chỗ dựng thẻ.

- [ ] **Step 4: Chạy test cho xanh**

```bash
cd backend && python -m pytest tests/test_theo_doi_kanban.py tests/test_theo_doi_may_ca_gantt.py -q
```

- [ ] **Step 5: FE — ba tab**

Thêm vào type ở `client.ts`, rồi ở mỗi tab render cạnh tên việc:

```tsx
<ChipLoaiBuoc loai_buoc={x.nhan?.loai_buoc} nha_cung_cap={x.nhan?.nha_cung_cap} />
<ChipKhuon
  can_khuon={!!x.nhan?.khuon_ma}
  khuon={{ ma: x.nhan?.khuon_ma, so_ke: x.nhan?.khuon_so_ke,
           tinh_trang: x.nhan?.khuon_tinh_trang, ngay_ve_du_kien: x.nhan?.khuon_ngay_ve,
           da_nhan: x.nhan?.khuon_da_nhan }}
/>
```

Tab Gantt KHÔNG đụng: một dòng ở đó là một LỆNH, không phải một bước.

- [ ] **Step 6: Kiểm + commit**

```bash
cd frontend && npx tsc --noEmit
```

```bash
git add backend/app/schemas/theo_doi_san_xuat.py backend/app/services/lenh_sx/bang_theo_doi.py backend/tests/test_theo_doi_kanban.py backend/tests/test_theo_doi_may_ca_gantt.py frontend/src/pages/TdsxKanban.tsx frontend/src/pages/TdsxTheoMay.tsx frontend/src/pages/TdsxTheoCa.tsx frontend/src/api/client.ts
git commit -m "Theo doi SX: chip loai buoc + khuon o Kanban, Theo may, Theo ca"
```

---

### Task 12: KCS và Yêu cầu kho — hai màn còn lại có mặt bước

**Files:**
- Modify: `backend/app/services/san_xuat/kcs.py` (dict thẻ KCS), `backend/app/services/san_xuat/kho.py` (dòng yêu cầu)
- Modify: `frontend/src/pages/kcs/ThucHienKcsPage.tsx`, `frontend/src/pages/kcs/KcsResultDrawer.tsx`, `frontend/src/pages/KhoYeuCauPage.tsx`
- Test: `backend/tests/test_san_xuat_kcs.py`, `backend/tests/test_san_xuat_kho.py`

**Interfaces:**
- Consumes: `_nhan(cv)` — **import lại** helper từ Task 11 (`from ..lenh_sx.bang_theo_doi import _nhan`)
  chứ không chép, để một chỗ sửa là mọi màn theo.

- [ ] **Step 1: Viết test đỏ**

```python
def test_the_kcs_mang_nhan_buoc(db, ...):
    the = kcs.danh_sach(db, ...)["items"][0]
    assert the["nhan"]["loai_buoc"] in ("may", "to", "thue_ngoai")


def test_dong_yeu_cau_kho_mang_nhan_buoc(db, ...):
    dong = kho.yeu_cau(db, ...)["items"][0]
    assert "nhan" in dong
```

- [ ] **Step 2: Chạy test cho chắc nó đỏ**

```bash
cd backend && python -m pytest tests/test_san_xuat_kcs.py tests/test_san_xuat_kho.py -q -k nhan_buoc
```

- [ ] **Step 3: Bơm `"nhan": _nhan(cv)` vào hai chỗ dựng dict**

- [ ] **Step 4: Chạy test cho xanh**

```bash
cd backend && python -m pytest tests/test_san_xuat_kcs.py tests/test_san_xuat_kho.py -q
```

- [ ] **Step 5: FE — hai chip vào ô tên bước của cả ba màn**

- [ ] **Step 6: Kiểm + commit**

```bash
cd frontend && npx tsc --noEmit
```

```bash
git add backend/app/services/san_xuat/kcs.py backend/app/services/san_xuat/kho.py backend/tests/test_san_xuat_kcs.py backend/tests/test_san_xuat_kho.py frontend/src/pages/kcs frontend/src/pages/KhoYeuCauPage.tsx
git commit -m "KCS va Yeu cau kho: chip loai buoc + khuon"
```

---

### Task 13: Nghiệm thu bằng luồng UI thật

**Files:** không sửa code trừ khi phát hiện lỗi.

**Interfaces:** Consumes: toàn bộ Task 1-12.

- [ ] **Step 1: Bật dev server**

BE `127.0.0.1:8000`, FE `localhost:5173`. Đẻ tiến trình qua `Win32_Process.Create` (Bash nền lẫn
`Start-Process` đều chết khi hết phiên). Đăng nhập `admin` / `admin123`.

- [ ] **Step 2: Danh mục**

Mở **Khuôn & khung**, kiểm nhan đề sidebar + tiêu đề màn đã đổi; tạo một dòng loại **Khung lụa**,
số kệ `Kệ C1`; tạo một dòng loại **Khuôn bế** `tinh_trang = Đang đặt làm`, ngày có khuôn `12/09`.

- [ ] **Step 3: Phiếu tính giá**

Mở một phiếu có bước bế. Chọn **Làm khuôn mới**, gõ tiền, gõ ngày dự kiến, Lưu, mở lại — số còn
nguyên. Đổi sang **Dùng khuôn có sẵn**, kiểm ô tiền đóng lại và lời nhắc engine biến mất.

- [ ] **Step 4: Kế hoạch**

Chuyển đơn xuống SX, mở lệnh. Bảng công đoạn phải hiện chip `🔧 chưa chốt khuôn` **ngoài bảng**
(không cần mở drawer). Bấm "Sẵn sàng lập kế hoạch" → phải bị chặn với mã **Thiếu khuôn / khung**.
Mở drawer, kiểm dòng "Sale báo: làm khuôn mới, …đ". Trỏ vào con dao **Đang dùng** → phải hiện băng
nhắc lệch ý định. Đổi sang dao đang đặt làm → băng nhắc mất, chip chuyển vàng `dự kiến 12/09`.
Bấm "Sẵn sàng lập kế hoạch" lần nữa → qua.

- [ ] **Step 5: Xếp lịch**

Kéo bước bế vào một ngày **trước** 12/09 → phải cho kéo, không báo chặn (đúng quyết định 04/09).
Thanh Gantt phải mang chip khuôn vàng. Gán một bước Thuê ngoài **chưa điền nơi làm** → chip
`Ngoài · chưa chọn nơi làm` vẫn hiện (đây là chỗ bản cũ mất nhãn).

- [ ] **Step 6: Phát hành + bàn tổ**

Phát hành. Mở **Thực hiện sản xuất** ở tổ có bước bế: thẻ việc mang chip khuôn + dòng
"Lấy ở Kệ …". Bấm **Bắt đầu** khi chưa tích → phải báo *"Chưa nhận khuôn/khung (KB-…)"*. Bấm
**Đã nhận khuôn** → chip đổi sang `đã nhận`, bấm Bắt đầu → chạy. Kết thúc việc → nút
**Đã trả khuôn về kệ** hiện ra, bấm được.

- [ ] **Step 7: Phiếu công nghệ + các màn theo dõi**

In phiếu công nghệ: dòng bước bế phải có mã dao + số kệ. Mở 4 tab **Theo dõi sản xuất**, màn
**KCS**, màn **Yêu cầu kho** — mọi thẻ có bước đều mang chip loại bước, bước bế mang chip khuôn.

- [ ] **Step 8: Báo cáo**

Liệt kê CỤ THỂ đã bấm gì / gõ gì / thấy gì ở từng bước. Nếu có bước nào phải tắt qua API thay vì
UI, nói rõ ngay trong báo cáo.

- [ ] **Step 9: Commit các sửa lỗi phát sinh (nếu có)**

```bash
git add -A
git commit -m "Va loi phat hien khi nghiem thu luong khuon & khung tren UI"
```

---

## Self-Review

**Spec coverage:**

| Mục spec | Task |
|---|---|
| §3 chip loại bước, 12 màn | 2 (component) · 6 (Kế hoạch) · 8 (bàn tổ) · 10 (xếp lịch) · 11 (theo dõi) · 12 (KCS/kho) |
| §4.1 đổi tên module | 1 |
| §4.2 phân loại `khung_lua` | 1 |
| §4.4 chip khuôn 3+1 trạng thái | 2 · 6 · 8 · 10 · 11 · 12 |
| §4.5 ý định sale + cảnh báo lệch | 3 · 4 |
| §4.6 cửa `thieu_khuon` | 5 |
| §4.7 nhận/trả khuôn + chặn Bắt đầu | 7 · 8 |
| §4.8 vết dùng dao | 7 (`khuon_json` giữ lại sau khi lệnh xong) |
| §5 bảng cột mới | 3 (mg 0257) · 4 (mg 0258) · 7 (mg 0259) |
| Phiếu công nghệ in mã dao + số kệ | 9 |

**Type consistency:** `khuon_nguon` là `"co_san" | "lam_moi" | None` xuyên suốt Task 3-4.
`khuon_json` shape khai ở Task 7 và được đọc y nguyên ở Task 8 (`board.py`), Task 11 (`_nhan`),
Task 12 (import lại `_nhan`). `ChipKhuon` nhận `KhuonChip` với `ngay_ve_du_kien` dạng chuỗi ISO ở
mọi nguồn — backend luôn `.isoformat()` trước khi trả.

**Placeholder scan:** không có TBD/TODO. Ba chỗ mô tả bằng lời thay vì code là có chủ ý:
Task 3 Step 8 và Task 8 Step 8 (vị trí chèn JSX phụ thuộc cấu trúc file đang có), Task 9 Step 3
(cấu trúc hàng của phiếu) — cả ba đều chỉ đích danh dòng và mẫu để bám theo.
