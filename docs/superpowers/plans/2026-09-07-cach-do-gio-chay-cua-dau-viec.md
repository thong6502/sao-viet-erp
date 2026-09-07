# Cách đo giờ chạy của đầu việc — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: dùng superpowers:executing-plans để làm theo từng
> task. Các bước dùng cú pháp checkbox (`- [ ]`) để đánh dấu tiến độ.

**Goal:** Tách cách đo GIỜ của bước Tổ ra khỏi công thức tính TIỀN CÔNG — thêm ô "Cách đo giờ
chạy" cho từng đầu việc trong bảng định mức của công đoạn, và mở lại ô "Đơn vị" của Năng suất
khoán cho người khai chọn.

**Architecture:** Bảng `cong_doan_dau_viec` nhận thêm MỘT cột `cong_thuc_gio` (TEXT), đối xứng
hoàn toàn với `cong_doan_may` (`cong_thuc_gio` + `cong_thuc_gia`). Cột `don_vi_nang_suat` đã có
sẵn trong DB từ trước nhưng đang DORMANT (UI khoá cứng theo đơn vị đơn giá khoán) — nay bật lại
thành ô chọn. `khoan_snapshot` ghim thêm `cong_thuc_gio` vào `khoan_json` của bước; chính SỰ CÓ
MẶT của khoá đó là dấu phân biệt ảnh chụp mới với ảnh chụp cũ, nên lệnh đã phát không xê dịch một
đồng nào. Bước Máy không đụng tới: giờ của nó vẫn lấy từ cặp (công đoạn × máy).

**Tech Stack:** FastAPI + SQLAlchemy 2 (không Alembic — migration tay trong
`backend/app/db_migrations.py`), Pydantic v2, React 19 + TypeScript + Vite, pytest, vitest.

**Spec:** không có file spec riêng. Thiết kế chốt trong hội thoại 07/09/2026, tóm tắt ở phần
"Bối cảnh" ngay dưới; plan này là bản ghi đầy đủ của thiết kế đó.

## Bối cảnh — vì sao làm

Bước Tổ hiện chỉ có MỘT công thức (`cong_doan_dau_viec.cong_thuc_khoan`, nhãn "Công thức tính
tiền công") và engine dùng chính nó cho CẢ tiền lẫn giờ (`LsxService._sl_theo_don_vi` —
"MỘT bộ quy đổi cho CẢ tiền lẫn giờ"). Hệ quả đo được trên LSX26-0028, bước **In offset**:

| số lượt | lượng quy đổi | tiền công | thời lượng |
|---|---|---|---|
| 1 | 241.000 kg | 144.600.000 đ | 483h15 |
| 2 | 482.000 kg | 289.200.000 đ | 965h15 |

Câu hint dưới ô số lượt hứa *"giờ của bước KHÔNG đổi theo"* — sai. Nguyên nhân gốc không phải
`so_luot_chay`: bước Tổ **không có chỗ nào khai cách đo giờ riêng**, trong khi bước Máy có
(`cong_doan_may.cong_thuc_gio`, đích là `may.don_vi_toc_do` — độc lập hoàn toàn với giá).

## Global Constraints

- **Ngôn ngữ:** mọi comment, docstring, nhãn UI, thông báo lỗi, commit message đều **tiếng Việt**
  (thuật ngữ kỹ thuật giữ tiếng Anh). Comment nói **VÌ SAO**, không kể lại code làm gì.
- **KHÔNG chạy `./init.ps1`.** Verify bằng `python -m pytest <file cụ thể> -q` chạy từ trong
  `backend/`, và `npx tsc --noEmit` chạy từ trong `frontend/`.
- **KHÔNG chạy `python -c` trần trong `backend/`** — nó trỏ vào Postgres dev thật.
- Không có Alembic; `create_all` **không** ALTER. Thêm cột ⇒ migration idempotent trong
  `backend/app/db_migrations.py` **và** cập nhật `docs/DB_SCHEMA.md` (có guard test, thiếu là FAIL).
- **Migration cấm ORM full-select** — raw SQL đích danh cột. Soi cột XONG HẾT rồi mới ghi (bẫy
  Inspector mượn/trả connection của pool SQLite `:memory:`).
- Migration mới nhất đang là `0275_moi_buoc_deu_bat_buoc` ⇒ migration của plan này là **`0276`**.
- Sửa route/schema/service backend ⇒ **RESTART uvicorn** (ở đây không hot-reload đáng tin).
- **Commit sau mỗi task. KHÔNG push.** Không thêm `Co-Authored-By`.
- Dự án đang dev, prod DB trắng, chưa có user thật ⇒ ưu tiên ĐÚNG, không cần giữ tương thích ngược
  con số cũ. **Trừ một chỗ:** ảnh chụp `khoan_json` của lệnh ĐÃ PHÁT phải giữ nguyên hành vi — đó
  là luật nghiệp vụ (tiền đã trả cho thợ), không phải tương thích ngược kỹ thuật.
- Xong luồng có UI ⇒ **BẮT BUỘC** thao tác lại đúng luồng đó bằng chuột/bàn phím thật trên
  dev-browser trước khi báo xong; không dùng API/curl thay bất kỳ bước nào.

## File Structure

**Backend — sửa:**
- `backend/app/models/cong_doan.py` — thêm cột `cong_thuc_gio` vào `CongDoanDauViec`, viết lại
  comment của `don_vi_nang_suat` (hết dormant).
- `backend/app/db_migrations.py` — thêm `_migrate_cong_thuc_gio_dau_viec` + đăng ký `0276`.
- `backend/app/schemas/cong_doan.py` — `CongDoanDauViecIn.cong_thuc_gio`.
- `backend/app/services/cong_doan_service.py` — `_validate`: chuẩn hoá + kiểm ô mới.
- `backend/app/services/piece_work_service.py` — `khoan_snapshot` ghim `cong_thuc_gio`.
- `backend/app/services/lsx_service.py` — hàm mới `dich_gio_cua_khoan`; `sl_tinh_cua_buoc` nhánh
  `LB_TO` đọc nó; `_dinh_muc_snapshot` bỏ nhãn DORMANT; `_dau_viec_option_dicts` thôi đóng cứng
  `rate.unit`; hai chỗ gán `row.don_vi_nang_suat` trong `_ke_thua`.
- `backend/app/services/bai_ghep_service.py` — `chung.don_vi_nang_suat` dùng chung một hàm.
- `backend/app/services/nhat_ky_danh_muc.py` — `_con_cua_cong_doan` ghi thêm ô mới.
- `backend/app/services/catalog_excel_specs.py` — cột Excel mới + `_doc_dau_viec_hien_co`.
- `docs/DB_SCHEMA.md` — mục `cong_doan_dau_viec` (danh sách cột + mô tả) và bảng tổng hợp công thức.

**Backend — test:**
- `backend/tests/test_lsx_service.py` — viết lại `test_don_vi_nang_suat_KHOA_theo_don_gia_khoan`
  (đang KHOÁ đúng hành vi ta đảo), thêm test giờ-tách-khỏi-tiền và test ảnh-chụp-cũ.
- `backend/tests/test_cong_doan.py` — test validate ô mới.
- `backend/tests/test_migrations.py` (nếu có) hoặc `test_cong_doan.py` — test backfill 0276.

**Frontend — sửa:**
- `frontend/src/pages/danh-muc/fields/DinhMucDauViec.tsx` — cột "Cách đo giờ chạy" + panel công
  thức thứ hai + ô Đơn vị đổi từ chữ chỉ-đọc sang `<select>`; `colSpan` 9 → 10.
- `frontend/src/pages/danh-muc/types.ts` — `DinhMucRow.cong_thuc_gio`.
- `frontend/src/pages/LsxBuocDrawer.tsx` + `frontend/src/pages/BaiGhepBuocChungForm.tsx` — viết
  lại câu hint dưới ô "Số lượt chạy" của bước Tổ.

---

### Task 1: Cột `cong_thuc_gio` — model, migration, DB_SCHEMA

**Files:**
- Modify: `backend/app/models/cong_doan.py:198-219`
- Modify: `backend/app/db_migrations.py` (cuối file)
- Modify: `docs/DB_SCHEMA.md:3283` và `docs/DB_SCHEMA.md:3285`
- Test: `backend/tests/test_cong_doan.py`

**Interfaces:**
- Produces: `CongDoanDauViec.cong_thuc_gio: Mapped[str | None]` — mọi task sau đọc/ghi cột này.
- Produces: migration `0276_cong_thuc_gio_dau_viec` chép `cong_thuc_khoan → cong_thuc_gio` cho
  dòng đang có (chỉ khi đích còn trống).

- [x] **Bước 1: Viết test thất bại**

Thêm vào cuối `backend/tests/test_cong_doan.py`:

```python
def test_migration_0276_chep_cong_thuc_khoan_sang_o_gio(db):
    """Chép XUỐNG, không đoán: số của lệnh không được nhảy ngay sau khi chạy migration.

    Hệ quả CÓ CHỦ ĐÍCH: chip `so_luot_chay` đang nằm trong công thức tiền công sẽ theo sang ô giờ,
    nên lỗi "giờ nhân theo số lượt" CHƯA tự hết — xưởng phải vào từng đầu việc bỏ chip đó ra khỏi ô
    giờ. Đó là lựa chọn: tự bỏ hộ là tự ý đổi giờ của mọi công đoạn đang chạy.
    """
    from sqlalchemy import text

    from app.db_migrations import _migrate_cong_thuc_gio_dau_viec

    cd = CongDoan(ma="CD-MG276", ten="Bế nổi", nhom="finishing")
    db.add(cd)
    db.flush()
    db.add(CongDoanDauViec(
        cong_doan_id=cd.id, piece_rate_id=1, nang_suat_nguoi_gio=500, so_nguoi_tieu_chuan=1,
        cong_thuc_khoan="sl_vao * 1000 * so_luot_chay",
    ))
    db.commit()

    _migrate_cong_thuc_gio_dau_viec(db)
    [ct] = db.execute(text(
        "SELECT cong_thuc_gio FROM cong_doan_dau_viec WHERE cong_doan_id = :i"
    ), {"i": cd.id}).scalars().all()
    assert ct == "sl_vao * 1000 * so_luot_chay"

    # Chạy lại KHÔNG đè cấu hình đã sửa tay — migration phải idempotent.
    db.execute(text("UPDATE cong_doan_dau_viec SET cong_thuc_gio = 'sl_vao * 1000'"))
    db.commit()
    _migrate_cong_thuc_gio_dau_viec(db)
    [ct2] = db.execute(text(
        "SELECT cong_thuc_gio FROM cong_doan_dau_viec WHERE cong_doan_id = :i"
    ), {"i": cd.id}).scalars().all()
    assert ct2 == "sl_vao * 1000"
```

Nếu `CongDoanDauViec` chưa được import ở đầu file test thì thêm vào import sẵn có:
`from app.models.cong_doan import CongDoan, CongDoanDauViec`.

- [x] **Bước 2: Chạy test cho chắc là ĐỎ**

Từ trong `backend/`:

```bash
python -m pytest tests/test_cong_doan.py::test_migration_0276_chep_cong_thuc_khoan_sang_o_gio -q
```

Kỳ vọng: FAIL — `ImportError: cannot import name '_migrate_cong_thuc_gio_dau_viec'`.

- [x] **Bước 3: Thêm cột vào model**

Trong `backend/app/models/cong_doan.py`, ngay SAU khối `cong_thuc_khoan` (kết thúc ở dòng
`cong_thuc_khoan: Mapped[str | None] = mapped_column(Text, nullable=True)`), chèn:

```python
    # CÁCH ĐO GIỜ CHẠY của đầu việc này TRONG công đoạn này (07/09/2026).
    #
    # Ra LƯỢNG theo đơn vị của NĂNG SUẤT khoán (`don_vi_nang_suat` ngay trên), rồi engine mới chia
    # cho năng suất — đối xứng đúng cặp `cong_doan_may.cong_thuc_gio` + `may.don_vi_toc_do` của
    # bước Máy.
    #
    # Vì sao phải tách khỏi `cong_thuc_khoan`: trước đây bước Tổ chỉ có MỘT công thức và engine
    # dùng nó cho cả tiền lẫn giờ, nên "in trở 2 lượt" (`sl_vao * so_luot_chay`) vừa nhân đôi tiền
    # công — ĐÚNG — vừa nhân đôi thời lượng — SAI: hai lượt in chồng lên nhau trên cùng một tờ,
    # tổ vẫn chỉ sờ tay vào từng ấy tờ. Máy không mắc lỗi này vì đơn vị tốc độ của máy độc lập
    # hoàn toàn với đơn vị đơn giá.
    #
    # ⚠️ GHIM vào bước lệnh qua `khoan_snapshot` — sửa ở đây KHÔNG xê dịch giờ của lệnh đã phát.
    cong_thuc_gio: Mapped[str | None] = mapped_column(Text, nullable=True)
```

Và thay khối comment của `don_vi_nang_suat` (dòng 198-200) bằng:

```python
    # ĐƠN VỊ của NĂNG SUẤT khoán, do người khai CHỌN (mã `<đơn vị>_gio`, cùng bảng mã với ô "Đơn vị
    # tốc độ" của máy). Trống = lùi về đơn vị của ĐƠN GIÁ khoán.
    #
    # DORMANT 10/08/2026 → BẬT LẠI 07/09/2026: hồi đó nhãn bị khoá cứng theo đơn giá vì tiền và
    # giờ dùng CHUNG một công thức, nên hai đơn vị buộc phải là một. Nay giờ có ô đo riêng
    # (`cong_thuc_gio`) nên hai thứ tách được: khoán "600 đ/kg mực" mà năng suất đếm "500 tờ/h".
```

- [x] **Bước 4: Viết migration `0276`**

Thêm vào CUỐI `backend/app/db_migrations.py`:

```python
def _migrate_cong_thuc_gio_dau_viec(db) -> None:
    """Đầu việc có ô đo GIỜ riêng, tách khỏi ô tính TIỀN CÔNG (07/09/2026).

    Nghiệp vụ: bước Tổ trước đây chỉ khai MỘT công thức và engine dùng nó cho cả tiền lẫn giờ. Ai
    khai "in trở 2 lượt" (`sl_vao * so_luot_chay`) thì tiền công nhân đôi — đúng — nhưng thời
    lượng cũng nhân đôi — sai, vì hai lượt in chồng lên nhau trên cùng một tờ. Bước Máy không dính
    vì đơn vị tốc độ của máy độc lập với đơn vị đơn giá; đầu việc thì không có ô tương đương.

    Chép `cong_thuc_khoan` sang là CHÉP XUỐNG, không đoán: sau migration mọi con số giữ nguyên,
    không lệnh nào tự nhảy. Đổi lại lỗi "giờ nhân theo số lượt" CHƯA tự hết — xưởng phải vào từng
    đầu việc bỏ chip `so_luot_chay` ra khỏi ô giờ. Tự bỏ hộ là tự ý đổi giờ của mọi công đoạn đang
    chạy mà không dòng nhật ký nào giải thích.

    Chỉ chép khi ô đích còn TRỐNG — chạy lại migration không đè cấu hình đã sửa tay.

    Raw SQL đích danh cột (không ORM): ORM full-select kéo cả cột do migration SAU thêm, vỡ deploy
    trên DB trung gian. Không đụng `piece_rates` — nguồn đã gỡ ở mg `0274`.
    """
    insp = inspect(db.get_bind())
    bang_co = set(insp.get_table_names())
    if "cong_doan_dau_viec" not in bang_co:
        return
    # Soi cột XONG rồi mới ghi: Inspector mượn/trả connection riêng, mà pool SQLite `:memory:` chỉ
    # có MỘT connection dùng chung — trả về là ROLLBACK, nuốt luôn lệnh ghi của đoạn trước.
    cot = _existing_columns(insp, "cong_doan_dau_viec")
    if "cong_thuc_gio" not in cot:
        db.execute(text("ALTER TABLE cong_doan_dau_viec ADD COLUMN cong_thuc_gio TEXT"))
    if "cong_thuc_khoan" in cot or "cong_thuc_gio" not in cot:
        db.execute(text(
            "UPDATE cong_doan_dau_viec SET cong_thuc_gio = cong_thuc_khoan "
            "WHERE (cong_thuc_gio IS NULL OR cong_thuc_gio = '') "
            "  AND cong_thuc_khoan IS NOT NULL AND cong_thuc_khoan <> ''"
        ))
    db.commit()


MIGRATIONS.append(("0276_cong_thuc_gio_dau_viec", _migrate_cong_thuc_gio_dau_viec))
```

- [x] **Bước 5: Cập nhật `docs/DB_SCHEMA.md`**

Ở mục `### cong_doan_dau_viec`, dòng **Tất cả cột** — thêm `cong_thuc_gio` ngay sau
`cong_thuc_khoan`:

```
**Tất cả cột:** `id`, `cong_doan_id`, `piece_rate_id`, `nang_suat_nguoi_gio`, `nang_suat_nguoi_gio_min`, `nang_suat_nguoi_gio_max`, `don_vi_nang_suat`, `so_nguoi_tieu_chuan`, `cong_thuc_khoan`, `cong_thuc_gio`, `cho_ky_thuat_gio`.
```

Chèn đoạn mô tả ngay SAU đoạn `**cong_thuc_khoan**`:

```
**`cong_thuc_gio`** (TEXT nullable, mg `0276`, 07/09/2026): **CÁCH ĐO GIỜ CHẠY** của đầu việc này TRONG công đoạn này — ra **LƯỢNG** theo đơn vị của `don_vi_nang_suat`, engine chia cho năng suất sau. Đối xứng đúng cặp `cong_doan_may.cong_thuc_gio` + `may_thiet_bi.don_vi_toc_do` của bước Máy. Trước đó bước Tổ chỉ có `cong_thuc_khoan` và engine dùng nó cho CẢ tiền lẫn giờ, nên `sl_vao * so_luot_chay` (in trở 2 lượt) vừa nhân đôi tiền công — đúng — vừa nhân đôi thời lượng — sai, hai lượt in chồng lên nhau trên cùng một tờ. Ghim vào bước lệnh cùng lúc với `cong_thuc_khoan` (`khoan_snapshot`); **sự CÓ MẶT của khoá `cong_thuc_gio` trong `khoan_json` là dấu phân biệt ảnh chụp mới với ảnh chụp cũ** — ảnh chụp cũ vắng khoá thì giờ vẫn đọc `cong_thuc`, nên lệnh đã phát không xê dịch. Migration `0276` chép `cong_thuc_khoan` sang khi ô đích còn trống ⇒ số không nhảy, nhưng chip `so_luot_chay` cũng theo sang: muốn hết lỗi phải vào từng đầu việc bỏ nó ra khỏi ô giờ.
```

Sửa đoạn `don_vi_nang_suat` (dòng bắt đầu bằng `` `don_vi_nang_suat` (VARCHAR(32), nullable) ``)
thành:

```
`don_vi_nang_suat` (VARCHAR(32), nullable): đơn vị người khai **CHỌN**, cùng bảng mã với ô "Đơn vị tốc độ" của máy (`<đơn vị>_gio`). Trống = lùi về đơn vị của **ĐƠN GIÁ khoán**. 🟢 **DORMANT 10/08/2026 → BẬT LẠI 07/09/2026 (cùng đợt `cong_thuc_gio`):** hồi đó nhãn bị khoá cứng theo đơn giá vì tiền và giờ dùng chung MỘT công thức nên hai đơn vị buộc phải là một; nay giờ có ô đo riêng nên tách được — khoán `600 đ/kg` mực mà năng suất đếm `500 tờ/h`. `LsxService.dich_gio_cua_khoan` cắt hậu tố `_gio` (`may_thiet_bi.ma_don_vi_goc`) để ra mã đơn vị đích, và **chỉ đọc khoá này khi ảnh chụp có khoá `cong_thuc_gio`** — dữ liệu cũ khai `to_gio` từ thời dormant không được phép đổi giờ của lệnh đã phát.
```

Trong bảng tổng hợp công thức (quanh dòng có `cong_doan_dau_viec.cong_thuc_khoan` (mg `0272`)),
thêm hàng ngay dưới:

```
| `cong_doan_dau_viec.cong_thuc_gio` (mg `0276`) | **LƯỢNG** | ĐẦU VIỆC này trong CÔNG ĐOẠN này đo giờ theo lượng nào (÷ năng suất ⇒ phút) |
```

- [x] **Bước 6: Chạy test cho chắc là XANH**

Từ trong `backend/`:

```bash
python -m pytest tests/test_cong_doan.py -q
```

Kỳ vọng: PASS toàn bộ file.

- [x] **Bước 7: Chạy guard DB_SCHEMA**

Từ trong `backend/`:

```bash
python -m pytest tests/test_db_schema_doc.py -q
```

(Nếu tên file khác thì tìm bằng `grep -rl "DB_SCHEMA" backend/tests`.) Kỳ vọng: PASS.

- [x] **Bước 8: Commit**

```bash
git add backend/app/models/cong_doan.py backend/app/db_migrations.py docs/DB_SCHEMA.md backend/tests/test_cong_doan.py && git commit -m "Them cot cong_thuc_gio cho dau viec cua cong doan (mg 0276)"
```

---

### Task 2: Nhận và kiểm ô mới ở tầng schema + service

**Files:**
- Modify: `backend/app/schemas/cong_doan.py:16-32`
- Modify: `backend/app/services/cong_doan_service.py:110-131`
- Test: `backend/tests/test_cong_doan.py`

**Interfaces:**
- Consumes: `CongDoanDauViec.cong_thuc_gio` (Task 1).
- Produces: `CongDoanDauViecIn.cong_thuc_gio: str | None` — FE (Task 5) và Excel (Task 4) gửi qua
  khoá này. `_validate` chuẩn hoá khoảng trắng thừa về `None` và chặn công thức sai cú pháp bằng
  `CongDoanValidationError` (HTTP 422).

- [x] **Bước 1: Viết test thất bại**

Thêm vào `backend/tests/test_cong_doan.py`:

```python
def test_cong_thuc_gio_dau_viec_duoc_luu_va_don_khoang_trang(client, admin_headers, db):
    """Ô giờ đi trọn đường schema → service → DB, và khoảng trắng thừa về None.

    Chuẩn hoá TẠI service để mọi đường vào (form, Excel, API) cùng một dạng: chuỗi toàn khoảng
    trắng làm `if cong_thuc:` ở engine tưởng có khai rồi `safe_eval("  ")` nổ.
    """
    to = _to_san_xuat(db)
    rate = _piece_rate(db, to, ma="XEN-G", ten="Xén giấy", don_vi="to", don_gia=100)
    r = client.post("/api/cong-doan", headers=admin_headers, json={
        **_cong_doan_toi_thieu(ma="CD-CTG", ten="Xén"),
        "department_id": to.id,
        "dau_viec_dinh_muc": [{
            "piece_rate_id": rate.id, "nang_suat_nguoi_gio": 500, "so_nguoi_tieu_chuan": 1,
            "cong_thuc_khoan": "sl_vao * so_luot_chay",
            "cong_thuc_gio": "sl_vao",
            "don_vi_nang_suat": "to_gio",
        }],
    })
    assert r.status_code == 201, r.text
    cd_id = r.json()["id"]
    [dv] = db.get(CongDoan, cd_id).dau_viec_dinh_muc
    assert dv.cong_thuc_gio == "sl_vao" and dv.don_vi_nang_suat == "to_gio"

    r2 = client.put(f"/api/cong-doan/{cd_id}", headers=admin_headers, json={
        **_cong_doan_toi_thieu(ma="CD-CTG", ten="Xén"),
        "department_id": to.id,
        "dau_viec_dinh_muc": [{
            "piece_rate_id": rate.id, "nang_suat_nguoi_gio": 500, "so_nguoi_tieu_chuan": 1,
            "cong_thuc_gio": "   ",
        }],
    })
    assert r2.status_code == 200, r2.text
    db.expire_all()
    [dv2] = db.get(CongDoan, cd_id).dau_viec_dinh_muc
    assert dv2.cong_thuc_gio is None


def test_cong_thuc_gio_dau_viec_sai_cu_phap_bi_chan(client, admin_headers, db):
    """Câu lỗi phải GỌI TÊN đầu việc — bảng nhiều dòng, không nói tên thì người khai phải mở từng
    panel để dò xem mình gõ hỏng ở đâu."""
    to = _to_san_xuat(db)
    rate = _piece_rate(db, to, ma="XEN-G2", ten="Xén giấy 2", don_vi="to", don_gia=100)
    r = client.post("/api/cong-doan", headers=admin_headers, json={
        **_cong_doan_toi_thieu(ma="CD-CTG2", ten="Xén 2"),
        "department_id": to.id,
        "dau_viec_dinh_muc": [{
            "piece_rate_id": rate.id, "nang_suat_nguoi_gio": 500, "so_nguoi_tieu_chuan": 1,
            "cong_thuc_gio": "sl_vao * *",
        }],
    })
    assert r.status_code == 422
    assert "Xén giấy 2" in r.text and "Cách đo giờ chạy" in r.text
```

⚠️ Tên helper (`_to_san_xuat`, `_piece_rate`, `_cong_doan_toi_thieu`, fixture `client` /
`admin_headers`) phải khớp helper đang có SẴN trong `backend/tests/test_cong_doan.py`. Mở file, đọc
một test POST/PUT công đoạn có `dau_viec_dinh_muc` đang chạy được, rồi dùng đúng helper và đúng bộ
trường tối thiểu của nó thay cho tên giả định ở trên.

- [x] **Bước 2: Chạy test cho chắc là ĐỎ**

```bash
python -m pytest tests/test_cong_doan.py -k cong_thuc_gio_dau_viec -q
```

Kỳ vọng: FAIL — `cong_thuc_gio` bị Pydantic bỏ im lặng nên `dv.cong_thuc_gio is None`, và test
thứ hai trả 201 thay vì 422.

- [x] **Bước 3: Thêm field vào schema**

Trong `backend/app/schemas/cong_doan.py`, ngay SAU dòng `cong_thuc_khoan: str | None = None` của
`CongDoanDauViecIn`, chèn:

```python
    # CÁCH ĐO GIỜ CHẠY của đầu việc này trong công đoạn này (07/09/2026) — ra LƯỢNG theo đơn vị
    # NĂNG SUẤT khoán, engine chia cho năng suất sau. Tách khỏi `cong_thuc_khoan` ngay trên vì
    # tiền và giờ không cùng một cách đếm: in trở 2 lượt thì tiền nhân đôi mà giờ thì không.
    cong_thuc_gio: str | None = None
```

Và sửa comment của `don_vi_nang_suat` (dòng 18-19) — bỏ chữ "là nhãn khai báo", thay bằng:

```python
    # `nang_suat_nguoi_gio` = mức TRUNG BÌNH (số chảy vào công thức thời lượng); min/max chỉ để ra
    # khoảng nhanh–chậm, để trống thì ba mức bằng nhau. `don_vi_nang_suat` là ĐƠN VỊ ĐÍCH mà
    # `cong_thuc_gio` phải quy về (mã `<đơn vị>_gio`); trống = lùi về đơn vị của đơn giá khoán.
```

- [x] **Bước 4: Chuẩn hoá + kiểm ở `_validate`**

Trong `backend/app/services/cong_doan_service.py`, trong vòng `for r in dinh_muc:`, THAY dòng
`self._kiem_o(r.get("cong_thuc_khoan"), ...)` (và ba dòng của nó) bằng:

```python
                # Chuẩn hoá TẠI ĐÂY để mọi đường vào (form, Excel, API) cùng một dạng: khoảng
                # trắng thừa làm `if cong_thuc:` ở engine tưởng có khai rồi `safe_eval("  ")` nổ.
                # Cùng luật đang áp cho hai ô của bảng máy ngay trên.
                for k in ("cong_thuc_khoan", "cong_thuc_gio", "don_vi_nang_suat"):
                    r[k] = ((r.get(k) or "").strip()) or None
                # Gọi tên ĐẦU VIỆC trong câu lỗi — bảng nhiều dòng, không nói tên thì người khai
                # phải mở từng panel để dò xem mình gõ hỏng ở đâu.
                self._kiem_o(r.get("cong_thuc_khoan"),
                             nhan=f"Công thức tính tiền công (đầu việc {rate.ten})",
                             loai=LOAI_QUY_DOI)
                self._kiem_o(r.get("cong_thuc_gio"),
                             nhan=f"Cách đo giờ chạy (đầu việc {rate.ten})",
                             loai=LOAI_QUY_DOI)
```

- [x] **Bước 5: Chạy test cho chắc là XANH**

```bash
python -m pytest tests/test_cong_doan.py -q
```

Kỳ vọng: PASS toàn bộ file.

- [x] **Bước 6: Commit**

```bash
git add backend/app/schemas/cong_doan.py backend/app/services/cong_doan_service.py backend/tests/test_cong_doan.py && git commit -m "Nhan va kiem o Cach do gio chay cua dau viec o tang schema + service"
```

---

### Task 3: Engine — bước Tổ đo giờ bằng ô mới, đơn vị năng suất hết khoá

**Files:**
- Modify: `backend/app/services/piece_work_service.py:62-88` (`khoan_snapshot`)
- Modify: `backend/app/services/lsx_service.py:127-142` (`_dinh_muc_snapshot`), `:731-772`
  (`_dau_viec_option_dicts`), `:845-871` (`sl_tinh_cua_buoc`), `:2960-2985` (`_ke_thua`)
- Modify: `backend/app/services/bai_ghep_service.py:900-907`
- Test: `backend/tests/test_lsx_service.py`

**Interfaces:**
- Consumes: `CongDoanDauViec.cong_thuc_gio` + `don_vi_nang_suat` (Task 1, 2).
- Produces: `lsx_service.dich_gio_cua_khoan(kh: dict) -> tuple[str | None, str]` — trả
  `(mã đơn vị đích, công thức)` để đo GIỜ của bước Tổ từ ảnh chụp `khoan_json`. Task sau và mọi
  service ngoài dùng chung hàm này, không tự suy.
- Produces: `khoan_json` của bước Tổ có thêm khoá `cong_thuc_gio` (chuỗi, **có mặt kể cả khi
  rỗng**) mỗi khi ảnh chụp lấy từ một dòng định mức.

- [x] **Bước 1: Viết test thất bại**

Trong `backend/tests/test_lsx_service.py`, **THAY TRỌN** hàm
`test_don_vi_nang_suat_KHOA_theo_don_gia_khoan` (dòng ~744) bằng:

```python
def test_don_vi_nang_suat_NGUOI_KHAI_CHON(db, lsx_svc):
    """Đơn vị năng suất do người khai CHỌN, không còn khoá theo đơn giá khoán (07/09/2026).

    🔴 ĐẢO LẠI chốt 10/08/2026. Hồi đó nhãn bị khoá cứng vì tiền và giờ dùng CHUNG một công thức
    nên hai đơn vị buộc phải là một. Nay đầu việc có ô đo giờ riêng (`cong_thuc_gio`) nên tách
    được: khoán 120 đ/cuốn mà năng suất đếm 500 tờ/h.

    Trống thì vẫn lùi về đơn vị đơn giá khoán — đó là mặc định hợp lý, không phải hành vi khoá.
    """
    from app.models.don_vi_do import DonViDo
    from app.models.piece_work import PieceRate

    to = _to_san_xuat(db)
    for ma, ten, ho in (("to", "tờ", "to"), ("cuon", "cuốn", "thanh_pham")):
        if db.query(DonViDo).filter(DonViDo.ma == ma).first() is None:
            db.add(DonViDo(ma=ma, ten=ten, ho=ho, he_so_goc=1, active=True))
    rate = PieceRate(group_name="to_be", department_id=to.id, ma="XEN-K",
                     ten="Xén 3 mặt thành phẩm", unit="cuốn", unit_price=120)
    db.add(rate)
    cd = CongDoan(ma="CD-BE-KHOA", ten="Bế nổi", nhom="finishing", department_id=to.id,
                  don_vi_vao="to", don_vi_ra="cai", cong_thuc_gia="so_luong * don_gia")
    db.add(cd)
    db.flush()
    dm = CongDoanDauViec(
        cong_doan_id=cd.id, piece_rate_id=rate.id, nang_suat_nguoi_gio=500,
        so_nguoi_tieu_chuan=1, don_vi_nang_suat="to_gio",
    )
    db.add(dm)
    db.commit()

    # Khai "to_gio" ⇒ năng suất đếm TỜ, trong khi đơn giá vẫn đếm CUỐN. Hai số, hai đơn vị.
    [dv] = [x for x in lsx_svc._dau_viec_option_dicts(cd, to.id) if x["id"] == rate.id]
    assert dv["don_vi"] == "cuốn" and dv["don_vi_nang_suat"] == "to"

    # Bỏ khai ⇒ lùi về đơn vị đơn giá khoán.
    dm.don_vi_nang_suat = None
    db.commit()
    [dv2] = [x for x in lsx_svc._dau_viec_option_dicts(cd, to.id) if x["id"] == rate.id]
    assert dv2["don_vi_nang_suat"] == "cuốn"


def test_dich_gio_cua_khoan_ANH_CHUP_CU_van_doc_cong_thuc_tien_cong():
    """Lệnh ĐÃ PHÁT trước 07/09/2026 không được xê dịch một phút nào.

    Ảnh chụp cũ chỉ có `cong_thuc` (chung cho tiền lẫn giờ) và có thể mang `don_vi_nang_suat` rác
    từ thời cột đó dormant. Dấu phân biệt là SỰ CÓ MẶT của khoá `cong_thuc_gio` — vắng khoá thì
    đọc y như trước, kể cả khi `don_vi_nang_suat` có giá trị.
    """
    from app.services.lsx_service import dich_gio_cua_khoan

    cu = {"don_vi": "cuốn", "cong_thuc": "sl_vao * so_luot_chay", "don_vi_nang_suat": "to_gio"}
    assert dich_gio_cua_khoan(cu) == ("cuốn", "sl_vao * so_luot_chay")

    # Ảnh chụp MỚI: đọc ô giờ + đơn vị năng suất đã cắt hậu tố `_gio`.
    moi = {"don_vi": "cuốn", "cong_thuc": "sl_vao * so_luot_chay",
           "cong_thuc_gio": "sl_vao", "don_vi_nang_suat": "to_gio"}
    assert dich_gio_cua_khoan(moi) == ("to", "sl_vao")

    # Ảnh chụp MỚI mà người khai CỐ Ý để trống ô giờ ⇒ KHÔNG được lùi về `cong_thuc`: rơi về
    # trống nghĩa là để cầu quy đổi trả lời, đúng thứ người khai chọn.
    trong = {"don_vi": "cuốn", "cong_thuc": "sl_vao * so_luot_chay", "cong_thuc_gio": ""}
    assert dich_gio_cua_khoan(trong) == ("cuốn", "")
```

Thêm ngay dưới đó test số thật — đây là ca chủ báo lỗi:

```python
def test_buoc_TO_so_luot_chi_nhan_TIEN_khong_nhan_GIO(db, lsx_svc):
    """⭐ Ca chủ bắt lỗi 07/09/2026: in trở 2 lượt thì TIỀN nhân đôi, GIỜ giữ nguyên.

    Khai tiền công `sl_vao * so_luot_chay` (2 lượt ⇒ 2× tiền) và giờ `sl_vao` (1 lượt tờ, vì hai
    lượt in chồng lên nhau trên cùng một tờ nên tổ vẫn chỉ sờ tay vào từng ấy tờ).
    """
    from app.models.don_vi_do import DonViDo
    from app.models.piece_work import PieceRate
    from app.services.lsx_service import thoi_luong_buoc

    to = _to_san_xuat(db)
    if db.query(DonViDo).filter(DonViDo.ma == "to").first() is None:
        db.add(DonViDo(ma="to", ten="tờ", ho="to", he_so_goc=1, active=True))
    rate = PieceRate(group_name="to_in", department_id=to.id, ma="IN-LUOT",
                     ten="In offset khoán", unit="to", unit_price=600)
    db.add(rate)
    cd = CongDoan(ma="CD-IN-LUOT", ten="In offset", nhom="print", department_id=to.id,
                  don_vi_vao="to", don_vi_ra="to")
    db.add(cd)
    db.flush()
    db.add(CongDoanDauViec(
        cong_doan_id=cd.id, piece_rate_id=rate.id, nang_suat_nguoi_gio=500,
        so_nguoi_tieu_chuan=1, don_vi_nang_suat="to_gio",
        cong_thuc_khoan="sl_vao * so_luot_chay", cong_thuc_gio="sl_vao",
    ))
    db.commit()

    buoc = _BuocGia(loai_buoc="to", cong_doan_id=cd.id, so_luong_vao=1000, so_luong_ra=1000,
                    don_vi_vao="to", so_luot_chay=2, so_nhan_cong_tieu_chuan=1,
                    nang_suat=500, phat_sinh_phut=0,
                    khoan_json=lsx_svc._khoan_mac_dinh(to.id, cd))

    # TIỀN: 1.000 tờ × 2 lượt × 600 đ = 1.200.000 đ.
    assert lsx_svc._khoan_derived(buoc, {})["khoan_tien"] == 1_200_000
    # GIỜ: 1.000 tờ ÷ (500 tờ/h × 1 người) × 60 = 120 phút — KHÔNG nhân 2.
    sl = lsx_svc.sl_tinh_cua_buoc(buoc, None, {})
    assert thoi_luong_buoc(buoc, None, sl)["chiem_may_phut"] == pytest.approx(120.0)
```

⚠️ `_BuocGia` là tên giả định. Mở `backend/tests/test_lsx_service.py`, tìm cách các test bước-Tổ
hiện có dựng đối tượng bước (thường là một `LsxCongDoan` thật thêm vào `db`, hoặc một
`SimpleNamespace`). Dùng đúng lối đang có ở file đó; nếu file dựng bước qua lệnh thật thì viết
test này theo lối lệnh thật thay vì bịa helper mới.

- [x] **Bước 2: Chạy test cho chắc là ĐỎ**

```bash
python -m pytest tests/test_lsx_service.py -k "don_vi_nang_suat or dich_gio_cua_khoan or so_luot_chi_nhan" -q
```

Kỳ vọng: FAIL — `ImportError: cannot import name 'dich_gio_cua_khoan'`, và
`dv["don_vi_nang_suat"] == "cuốn"` thay vì `"to"`.

- [x] **Bước 3: `khoan_snapshot` ghim thêm ô giờ**

Trong `backend/app/services/piece_work_service.py`, THAY khối cuối của `khoan_snapshot`:

```python
    if (ct := (getattr(dm, "cong_thuc_khoan", None) or "").strip()):
        snap["cong_thuc"] = ct
    return snap
```

bằng:

```python
    if (ct := (getattr(dm, "cong_thuc_khoan", None) or "").strip()):
        snap["cong_thuc"] = ct
    if dm is not None:
        # Khoá này CÓ MẶT kể cả khi rỗng — khác luật "vắng khi rỗng" của `cong_thuc` ngay trên, và
        # cố ý: chính SỰ CÓ MẶT của nó là dấu "ảnh chụp biết đầu việc có ô đo giờ riêng". Ảnh chụp
        # trước 07/09/2026 vắng khoá ⇒ `dich_gio_cua_khoan` lùi về `cong_thuc` như cũ, nên lệnh đã
        # phát không xê dịch một phút nào. Không có dấu này thì ô giờ để trống có chủ đích lại bị
        # hiểu nhầm là ảnh chụp cũ, và chip `so_luot_chay` của tiền công lại chảy vào giờ.
        snap["cong_thuc_gio"] = (getattr(dm, "cong_thuc_gio", None) or "").strip()
    return snap
```

Và bổ sung vào docstring của hàm, ngay trước đoạn "Khoá VẮNG khi công thức rỗng":

```
    Từ 07/09/2026 chụp THÊM `cong_thuc_gio` — cách đo GIỜ, tách khỏi cách đo tiền. Hai ô ghim cùng
    lúc vì cùng một lý do: chúng quyết định LƯỢNG, mà lượng thì một bên nhân đơn giá ra tiền, một
    bên chia năng suất ra phút.
```

- [x] **Bước 4: Hàm `dich_gio_cua_khoan` + `sl_tinh_cua_buoc` đọc nó**

Trong `backend/app/services/lsx_service.py`, thêm hàm module-level ngay SAU `ma_don_vi_toc_do`
(dòng ~152):

```python
def dich_gio_cua_khoan(kh: dict) -> tuple[str | None, str]:
    """Từ ảnh chụp đầu việc ra `(mã đơn vị đích, công thức)` để đo GIỜ của bước Tổ.

    Đối xứng với `ma_don_vi_toc_do` + `cong_doan_may.cong_thuc_gio` của bước Máy: một cặp
    "đếm bằng gì" + "quy về đó thế nào", tách hẳn khỏi cặp tính tiền (`don_vi` + `cong_thuc`).

    **Dấu phân biệt là SỰ CÓ MẶT của khoá `cong_thuc_gio`**, không phải giá trị của nó. Ảnh chụp
    trước 07/09/2026 chỉ có `cong_thuc` (dùng chung cho tiền lẫn giờ) và có thể còn mang
    `don_vi_nang_suat` rác từ thời cột đó dormant — đọc hai khoá ấy ra là tự ý đổi giờ của lệnh đã
    phát. Ngược lại, ảnh chụp MỚI mà người khai cố ý để trống ô giờ thì phải giữ trống (để cầu quy
    đổi trả lời), chứ lùi về `cong_thuc` là kéo nguyên chip `so_luot_chay` của tiền công vào giờ —
    đúng cái lỗi ô này sinh ra để chữa.

    ĐÚNG MỘT chỗ đọc: bốn service ngoài (bài ghép · xếp lịch · kế hoạch vật tư · phiếu công nghệ)
    phải dựng cùng một số, mỗi nơi tự suy là mở đường cho Gantt và drawer lệch nhau.
    """
    if "cong_thuc_gio" not in kh:
        return kh.get("don_vi"), (kh.get("cong_thuc") or "").strip()
    return (ma_don_vi_goc(kh.get("don_vi_nang_suat")) or kh.get("don_vi"),
            (kh.get("cong_thuc_gio") or "").strip())
```

Trong `sl_tinh_cua_buoc`, THAY nhánh `elif loai == LB_TO:` (4 dòng, từ `kh = getattr(...)` tới
`ct_rieng = (kh.get("cong_thuc") or "").strip()`) bằng:

```python
        elif loai == LB_TO:
            # Cặp GHIM trong ảnh chụp đầu việc, KHÔNG đọc lại danh mục: xưởng sửa cách đo về sau
            # không được xê dịch lệnh đã phát (xem `khoan_snapshot`). Từ 07/09/2026 cặp này là ô
            # ĐO GIỜ riêng, không còn dùng chung với ô tính tiền công.
            dich, ct_rieng = dich_gio_cua_khoan(getattr(cd, "khoan_json", None) or {})
```

Và sửa dòng đích trong docstring của `sl_tinh_cua_buoc`:

```
        Đích: bước MÁY → đơn vị tốc độ của máy đang gán · bước TỔ → đơn vị NĂNG SUẤT của đầu việc
        (`don_vi_nang_suat`, lùi về đơn vị đơn giá khoán khi chưa khai). THUÊ NGOÀI đi chung đường
        bước máy — nhà thầu là một máy khai trong danh mục, có tốc độ và đơn vị tốc độ như máy nhà.
```

- [x] **Bước 5: Bỏ nhãn DORMANT + thôi đóng cứng `rate.unit`**

Trong `_dinh_muc_snapshot` (dòng ~127), thay đoạn docstring nói `don_vi_nang_suat` DORMANT bằng:

```
    `don_vi_nang_suat` BẬT LẠI 07/09/2026 (dormant từ 10/08/2026): nay nó là ĐƠN VỊ ĐÍCH mà
    `cong_thuc_gio` quy về, đọc qua `dich_gio_cua_khoan` chứ đừng đọc thẳng — hàm đó gác luật
    "ảnh chụp cũ không được đổi giờ".
```

Trong `_dau_viec_option_dicts` (dòng ~768-771), THAY:

```python
                item.update({
                    **_dinh_muc_snapshot(dm),
                    # Đơn vị của năng suất = đơn vị của ĐƠN GIÁ KHOÁN, không còn nhãn riêng: thời
                    # lượng nay quy SL vào về chính đơn vị đó rồi mới chia (`_sl_theo_don_vi`).
                    "don_vi_nang_suat": rate.unit,
                    "vat_tus": vt,
                    "canh_bao_vat_tu": cb,
                })
```

bằng:

```python
                item.update({
                    **_dinh_muc_snapshot(dm),
                    # Đọc THẲNG danh mục (không qua `dich_gio_cua_khoan`) vì đây là danh sách CHỌN
                    # ĐƯỢC — nó phải bày thứ đang khai ở danh mục, không phải thứ bước cũ đã ghim.
                    # Cắt hậu tố `_gio` để ra mã đơn vị; chưa khai thì lùi về đơn vị đơn giá khoán.
                    "don_vi_nang_suat": ma_don_vi_goc(dm.don_vi_nang_suat) or rate.unit,
                    "vat_tus": vt,
                    "canh_bao_vat_tu": cb,
                })
```

- [x] **Bước 6: Hai chỗ gán `row.don_vi_nang_suat` trong `_ke_thua`**

Trong `backend/app/services/lsx_service.py`, THAY:

```python
                        if row.loai_buoc == LB_TO:
                            row.nang_suat = _f(dm.nang_suat_nguoi_gio)
                            row.don_vi_nang_suat = row.khoan_json.get("don_vi")
```

bằng:

```python
                        if row.loai_buoc == LB_TO:
                            row.nang_suat = _f(dm.nang_suat_nguoi_gio)
                            # Nhãn năng suất ĐI THEO đơn vị mà giờ quy về — hai thứ lệch nhau thì
                            # drawer hiện "500 cuốn/h" trong khi máy chia số TỜ, đúng lỗi 15/08.
                            row.don_vi_nang_suat = dich_gio_cua_khoan(row.khoan_json)[0]
```

và THAY:

```python
                if row.loai_buoc == LB_TO:
                    row.nang_suat = _f(snap.get("nang_suat_nguoi_gio")) or None
                    row.don_vi_nang_suat = snap.get("don_vi")
```

bằng:

```python
                if row.loai_buoc == LB_TO:
                    row.nang_suat = _f(snap.get("nang_suat_nguoi_gio")) or None
                    row.don_vi_nang_suat = dich_gio_cua_khoan(snap)[0]
```

Trong `backend/app/services/bai_ghep_service.py`, THAY:

```python
        # Đơn vị năng suất = đơn vị ĐƠN GIÁ KHOÁN. Bảng ánh xạ `_DV_VAO_SANG_NS` đã gỡ 15/08/2026
        # cùng hai cơ chế đơn vị cũ — thời lượng nay quy SL vào về chính đơn vị này.
        chung.don_vi_nang_suat = rate.unit
```

bằng:

```python
        # Nhãn năng suất ĐI THEO đơn vị mà giờ quy về (07/09/2026) — cùng một hàm bước lệnh dùng,
        # để bàn bài ghép và drawer lệnh không nói hai đơn vị khác nhau cho cùng một con số.
        chung.don_vi_nang_suat = dich_gio_cua_khoan(chung.khoan_json)[0]
```

và thêm `dich_gio_cua_khoan` vào import sẵn có từ `lsx_service` ở đầu file (`_dinh_muc_snapshot`
đang được import từ đó — thêm vào cùng dòng).

- [x] **Bước 7: Chạy test cho chắc là XANH**

```bash
python -m pytest tests/test_lsx_service.py tests/test_bai_ghep_2_service.py -q
```

Kỳ vọng: PASS. Test nào đỏ vì đang khoá hành vi cũ ("đơn vị năng suất = đơn vị đơn giá") thì sửa
kỳ vọng của nó cho khớp thiết kế mới, KHÔNG sửa engine để chiều test.

- [x] **Bước 8: Chạy rộng hơn các file đụng `khoan_json`**

```bash
python -m pytest tests/test_khsx_ui_contract.py tests/test_xep_lich_dot2.py tests/test_lenh_sx_pdf.py -q
```

Kỳ vọng: PASS.

- [x] **Bước 9: Commit**

```bash
git add backend/app/services/piece_work_service.py backend/app/services/lsx_service.py backend/app/services/bai_ghep_service.py backend/tests && git commit -m "Buoc To do gio bang o rieng cua dau viec, don vi nang suat het khoa theo don gia"
```

---

### Task 4: Nhật ký danh mục + bảng Excel

**Files:**
- Modify: `backend/app/services/nhat_ky_danh_muc.py:441-445`
- Modify: `backend/app/services/catalog_excel_specs.py:476-490` và `:606-618`
- Test: `backend/tests/test_import_excel.py`, `backend/tests/test_danh_muc_bug_fixes.py`

**Interfaces:**
- Consumes: `CongDoanDauViec.cong_thuc_gio` (Task 1), `CongDoanDauViecIn.cong_thuc_gio` (Task 2).
- Produces: cột Excel `"Cách đo giờ chạy"` trong sheet con "Đầu việc định mức"; dòng nhật ký
  `Đầu việc #<id> · Công thức giờ chạy`.

- [x] **Bước 1: Viết test thất bại**

Thêm vào `backend/tests/test_import_excel.py`:

```python
def test_excel_cong_doan_co_cot_cach_do_gio_chay():
    """Xuất/nhập Excel phải chở ô giờ, không thì nhập một file cũ là xoá sạch cách đo giờ."""
    from app.services.catalog_excel_specs import SPECS

    [con] = [s for s in SPECS["cong_doan"].sheet_con if s.field == "dau_viec_dinh_muc"]
    khoa = [c.field for c in con.cot]
    assert "cong_thuc_gio" in khoa and "cong_thuc_khoan" in khoa
```

⚠️ `SPECS`, `.sheet_con`, `.cot`, `.field` là tên giả định. Mở
`backend/app/services/catalog_excel_specs.py`, đọc tên biến/thuộc tính thật (spec công đoạn được
gán vào biến nào, `SheetCon` có thuộc tính gì) rồi viết test bằng đúng tên đó.

- [x] **Bước 2: Chạy test cho chắc là ĐỎ**

```bash
python -m pytest tests/test_import_excel.py -k cach_do_gio_chay -q
```

Kỳ vọng: FAIL — `"cong_thuc_gio" not in khoa`.

- [x] **Bước 3: Thêm cột Excel**

Trong `backend/app/services/catalog_excel_specs.py`, thêm vào `_doc_dau_viec_hien_co` ngay SAU
dòng `"cong_thuc_khoan": dv.cong_thuc_khoan,`:

```python
            "cong_thuc_gio": dv.cong_thuc_gio,
```

và trong `SheetCon("Đầu việc định mức", ...)`, thêm ngay SAU dòng
`Cot("Công thức tính tiền công", "cong_thuc_khoan", rong=36),`:

```python
                Cot("Cách đo giờ chạy", "cong_thuc_gio", rong=36),
```

- [x] **Bước 4: Ghi ô mới vào nhật ký**

Trong `backend/app/services/nhat_ky_danh_muc.py`, THAY:

```python
        dv[f"{dau} · {NHAN['cong_thuc_khoan']}"] = getattr(r, "cong_thuc_khoan", None)
```

bằng:

```python
        for truong in ("cong_thuc_khoan", "cong_thuc_gio"):
            dv[f"{dau} · {NHAN[truong]}"] = getattr(r, truong, None)
```

`NHAN["cong_thuc_gio"] = "Công thức giờ chạy"` đã có sẵn (dùng chung với bảng máy) — không thêm gì.

- [x] **Bước 5: Chạy test cho chắc là XANH**

```bash
python -m pytest tests/test_import_excel.py tests/test_import_danh_muc_prod.py tests/test_danh_muc_bug_fixes.py -q
```

Kỳ vọng: PASS.

- [x] **Bước 6: Commit**

```bash
git add backend/app/services/catalog_excel_specs.py backend/app/services/nhat_ky_danh_muc.py backend/tests/test_import_excel.py && git commit -m "O Cach do gio chay len bang Excel danh muc va nhat ky cong doan"
```

---

### Task 5: Màn Công đoạn — cột "Cách đo giờ chạy" + ô Đơn vị chọn được

**Files:**
- Modify: `frontend/src/pages/danh-muc/fields/DinhMucDauViec.tsx`
- Modify: `frontend/src/pages/danh-muc/types.ts:202-217`
- Modify: `frontend/src/pages/LsxBuocDrawer.tsx:1359`
- Modify: `frontend/src/pages/BaiGhepBuocChungForm.tsx:975`

**Interfaces:**
- Consumes: `CongDoanDauViecIn.cong_thuc_gio` (Task 2) — body PUT/POST `/api/cong-doan`.
- Produces: `DinhMucRow.cong_thuc_gio?: string | null`.

- [x] **Bước 1: Thêm trường vào type**

Trong `frontend/src/pages/danh-muc/types.ts`, chèn vào `DinhMucRow` ngay SAU khối
`cong_thuc_khoan`:

```ts
  /** CÁCH ĐO GIỜ CHẠY của đầu việc này trong CÔNG ĐOẠN này (07/09/2026). Ra LƯỢNG theo đơn vị
   *  NĂNG SUẤT (`don_vi_nang_suat`), server chia cho năng suất sau. Tách khỏi `cong_thuc_khoan`
   *  vì tiền và giờ không cùng cách đếm: in trở 2 lượt thì tiền nhân đôi mà giờ thì không. */
  cong_thuc_gio?: string | null;
```

- [x] **Bước 2: Nạp danh mục Đơn vị trong `DinhMucDauViec.tsx`**

Ngay SAU khối `useEffect` nạp `vatTu`, thêm:

```tsx
  // Danh mục Đơn vị & quy đổi cho ô chọn "Đơn vị" của năng suất khoán. Nạp TẠI ĐÂY chứ không qua
  // `refData` chung: bộ nạp chung khoá theo MỘT `refPrefix` mỗi field, mà field này đã dùng
  // `refPrefix` cho danh sách đầu việc.
  const [donVi, setDonVi] = useState<Row[]>([]);
  useEffect(() => {
    if (!token) return;
    let alive = true;
    crud("/api/don-vi").list(token, { active: true, size: 200 })
      .then((r) => { if (alive) setDonVi(r.items); })
      .catch(() => { if (alive) setDonVi([]); });
    return () => { alive = false; };
  }, [token]);
```

và thêm `import { DonViTocDoField } from "./DonViTocDo";` vào khối import (kiểm lại đường dẫn
tương đối thật của file `DonViTocDo.tsx` trong cùng thư mục `fields/`).

- [x] **Bước 3: Ô Đơn vị từ chữ chỉ-đọc thành ô chọn**

THAY nguyên ô đơn vị (dòng bắt đầu bằng `<td className="rc-col--unit rc-dinh-muc-unit">{opt?.don_vi_ten ...`)
bằng:

```tsx
            {/* CHỌN ĐƯỢC lại từ 07/09/2026 (khoá cứng theo đơn giá khoán 10/08/2026 → mở).
                Hồi đó khoá vì tiền và giờ dùng CHUNG một công thức nên hai đơn vị buộc phải là
                một; nay ô "Cách đo giờ chạy" bên phải tách hai thứ ra, nên khai được "tiền tính
                theo kg mực, giờ tính theo tờ". Bỏ trống = lùi về đơn vị của đơn giá khoán. */}
            <td className="rc-col--unit rc-dinh-muc-unit">
              <DonViTocDoField value={r.don_vi_nang_suat ?? ""} donViList={donVi}
                onChange={(v) => patch(i, { don_vi_nang_suat: v || null })} />
            </td>
```

Nếu ô chọn tràn cột, thêm `title` cho biết mặc định: bọc `<td>` bằng
`title={opt?.don_vi_ten ? `Bỏ trống = ${opt.don_vi_ten}` : undefined}`.

- [x] **Bước 4: Cột "Cách đo giờ chạy"**

Trong `<thead>`, thêm NGAY SAU `<th>` của "Công thức tiền công":

```tsx
              {/* Đối xứng bảng "Máy chạy được công đoạn này": máy có cặp (Cách đo giờ chạy · Cách
                  tính giá), đầu việc có cặp (Công thức tiền công · Cách đo giờ chạy). */}
              <th rowSpan={2} className="rc-col--left"
                title="Ra LƯỢNG theo đơn vị năng suất khoán — hệ chia cho năng suất sau.">Cách đo giờ chạy</th>
```

Trong `<tbody>`, thêm NGAY SAU `<td>` của ô công thức tiền công:

```tsx
            <td className="rc-col--left rc-dinh-muc-unit">
              <button type="button" title="Sửa cách đo giờ chạy của đầu việc này"
                className={`rc-ct-cell ${moCtGio?.id === r.piece_rate_id ? "is-open" : ""} ${r.cong_thuc_gio ? "" : "is-empty"}`}
                onClick={(e) => batCtGio(r.piece_rate_id, e.currentTarget)}>
                {r.cong_thuc_gio || "—"}
              </button>
            </td>
```

Đổi CẢ HAI `colSpan={9}` trong file thành `colSpan={10}` (một ở dòng "chưa chọn đầu việc", một ở
hàng phụ vật tư).

- [x] **Bước 5: State + panel công thức giờ**

Thêm ngay SAU khai báo `moCt`:

```tsx
  // Panel CÁCH ĐO GIỜ — tách hẳn panel tiền công: hai ô trả lời hai câu khác nhau (bao nhiêu
  // tiền / bao nhiêu phút) nên mở lẫn nhau là chỗ gõ nhầm ô.
  const [moCtGio, setMoCtGio] = useState<{ id: number; neo: HTMLElement } | null>(null);
  const batCtGio = (id: number, neo: HTMLElement) =>
    setMoCtGio(moCtGio?.id === id ? null : { id, neo });
  const iCtGio = moCtGio ? value.findIndex((r) => r.piece_rate_id === moCtGio.id) : -1;
```

Thêm panel ngay SAU khối `{moCt && iCt >= 0 && <FormulaPopover ...>}`:

```tsx
      {moCtGio && iCtGio >= 0 && <FormulaPopover neo={moCtGio.neo} nhan="Cách đo giờ chạy"
        onClose={() => setMoCtGio(null)}>
        <FormulaField
          id={`ct-gio-${moCtGio.id}`} configPrefix="/api/cong-doan" loaiO="quy_doi"
          nhanO="Cách đo giờ chạy"
          goY="Ra LƯỢNG theo đơn vị Năng suất khoán, hệ chia cho năng suất sau. Bỏ trống = hệ tự quy đổi. Ở bước tổ hệ KHÔNG tự nhân số lượt — in trở 2 lượt chồng trên cùng một tờ thì để nguyên sl_vao. Lệnh ĐÃ phát giữ cách đo cũ."
          value={value[iCtGio].cong_thuc_gio ?? ""}
          onChange={(v) => patch(iCtGio, { cong_thuc_gio: v })} />
      </FormulaPopover>}
```

Và trong `<select>` "＋ Chọn đầu việc của tổ", thêm `cong_thuc_gio: null` vào object dòng mới, ngay
sau `don_vi_nang_suat: null`.

Sửa luôn comment đầu file (`donViVao` … "đơn vị năng suất giờ do người khai chọn") — nay câu đó
đúng trở lại, bỏ chữ "KHÔNG dùng nữa" nếu prop thật sự vẫn không dùng thì giữ nguyên phần đó.

- [x] **Bước 6: Viết lại câu hint dưới ô số lượt**

Ở CẢ HAI file `frontend/src/pages/LsxBuocDrawer.tsx` và
`frontend/src/pages/BaiGhepBuocChungForm.tsx`, thay chuỗi:

```
"Số lần hàng đi qua bước này — mặc định 1. Ở bước tổ, số này chỉ vào công thức tính tiền công; giờ của bước KHÔNG đổi theo."
```

bằng:

```
"Số lần hàng đi qua bước này — mặc định 1. Ở bước tổ, số này chỉ chảy vào công thức nào có gõ chip so_luot_chay: tiền công và giờ chạy khai ở hai ô riêng tại danh mục Công đoạn."
```

- [x] **Bước 7: Kiểm kiểu**

Từ trong `frontend/`:

```bash
npx tsc --noEmit
```

Kỳ vọng: exit 0, không lỗi.

- [x] **Bước 8: Commit**

```bash
git add frontend/src && git commit -m "Bang dau viec cua cong doan them o Cach do gio chay, o Don vi nang suat chon duoc"
```

---

### Task 6: Nghiệm thu bằng UI thật

**Files:** không sửa file nào — task này chỉ chạy và quan sát. Phát hiện lỗi thì sửa rồi commit
riêng.

**Interfaces:**
- Consumes: toàn bộ Task 1-5.

- [x] **Bước 1: Restart uvicorn**

Sửa model/schema/service backend ⇒ **BẮT BUỘC** restart (ở đây không hot-reload đáng tin). Dùng
đúng lối `Win32_Process.Create` mà dự án này vẫn dùng để đẻ tiến trình sống qua phiên; BE
`127.0.0.1:8000`, FE `localhost:5173`. Chờ `/api/health` trả 200 rồi mới sang bước sau.

- [x] **Bước 2: Xác nhận migration 0276 đã chạy trên DB dev**

Đọc log khởi động uvicorn, tìm dòng ghi `0276_cong_thuc_gio_dau_viec`. **KHÔNG** chạy `python -c`
trần trong `backend/` để soi DB.

- [ ] **Bước 3: Danh mục Công đoạn — khai hai ô**

Trên dev-browser, đăng nhập bằng phiên user đã mở sẵn (KHÔNG tự gõ mật khẩu vào bất kỳ ô nào).
Vào **Cấu hình danh mục → Công đoạn → sửa công đoạn In offset**, cuộn tới bảng **Đầu việc và định
mức của tổ**. Kiểm và ghi lại từng thứ thấy được:

  1. Bảng có **hai** ô công thức cạnh nhau: *Công thức tiền công* và *Cách đo giờ chạy* — đúng lối
     bảng *Máy chạy được công đoạn này* ngay dưới.
  2. Ô **Đơn vị** của Năng suất khoán nay là **ô chọn** (không còn chữ `cuốn/h` chỉ-đọc).
  3. Bấm vào ô *Cách đo giờ chạy* → panel công thức nổi ra, câu gợi ý nói "hệ KHÔNG tự nhân số
     lượt".
  4. Ô *Cách đo giờ chạy* đã có sẵn nội dung y hệt ô tiền công (do migration `0276` chép sang).

- [ ] **Bước 4: Sửa ô giờ, bỏ chip lượt**

Trong ô *Cách đo giờ chạy* của đầu việc đang khai `sl_vao * 1000 * so_luot_chay`, xoá phần
`* so_luot_chay` để còn `sl_vao * 1000`. Chọn **Đơn vị** năng suất cho khớp thứ năng suất đang
đếm. Bấm **Lưu**, chờ toast thành công.

- [ ] **Bước 5: Đối chiếu số ở Lệnh sản xuất**

Mở **LSX26-0028 → bước In offset**, đổi Loại bước sang **Tổ**, chọn đúng đầu việc vừa sửa, đặt
**Số lượt = 1**, bấm Lưu. Ghi lại tiền công và thời lượng hiện ra. Đổi **Số lượt = 2**, Lưu, ghi
lại lần nữa.

Kỳ vọng: **tiền công nhân đôi, thời lượng GIỮ NGUYÊN**. Đây chính là ca chủ báo lỗi
(483h15 → 965h15 trước khi sửa).

- [ ] **Bước 6: Trả bước In offset về nguyên trạng**

Bước này trong DB đang là `loai_buoc='may'`, `may_id=2`, `so_luot_chay=2` (bị để dở ở phiên trước
với banner "Sửa ở đây chưa ghi vào DB"). Đặt lại đúng ba giá trị đó rồi Lưu, và xác nhận drawer
hiện `BƯỚC · Máy`.

- [ ] **Bước 7: Nhật ký danh mục**

Vào **Công đoạn In offset → tab Nhật ký**, xác nhận có dòng ghi lần sửa ở Bước 4 với nhãn
`Đầu việc #<id> · Công thức giờ chạy`, kèm giá trị trước/sau.

- [ ] **Bước 8: Excel danh mục**

Vào **Cấu hình danh mục → Công đoạn → Xuất Excel**, mở file, xác nhận sheet *Đầu việc định mức* có
cột **Cách đo giờ chạy** với giá trị vừa khai. Sửa một ô trong file rồi **Nhập Excel** lại, xác
nhận màn hình nhận đúng giá trị mới.

- [ ] **Bước 9: Tick lại checkbox của plan này**

Đánh dấu `- [x]` cho mọi bước đã làm trong file plan, rồi commit:

```bash
git add docs/superpowers/plans/2026-09-07-cach-do-gio-chay-cua-dau-viec.md && git commit -m "Plan cach do gio chay cua dau viec: tick sau khi nghiem thu bang UI that"
```

- [ ] **Bước 10: Báo cáo**

Báo cáo phải liệt kê **cụ thể** đã bấm gì, gõ gì, thấy gì ở từng bước — không nói chung chung "đã
test UI". Nếu vì lý do nào đó buộc phải tắt qua API ở một đoạn, **nói rõ ngay lúc báo cáo**.

---

## Ngoài phạm vi (cố ý không làm)

- **Lỗi "số lượt" chưa tự hết sau migration.** `0276` chép nguyên văn `cong_thuc_khoan` sang ô giờ
  để số của mọi lệnh giữ nguyên, nên đầu việc nào đang gõ `so_luot_chay` trong ô tiền công thì ô
  giờ cũng có. Xưởng phải vào từng đầu việc bỏ chip đó ra — tự bỏ hộ là tự ý đổi giờ của mọi công
  đoạn đang chạy mà không dòng nhật ký nào giải thích.
- **Bước Máy không đụng gì.** Giờ vẫn lấy từ cặp (công đoạn × máy) qua `cong_doan_may.cong_thuc_gio`
  + `may.don_vi_toc_do`, đọc SỐNG (không ghim).
- **Lỗi BOM bị xoá khi đổi tổ** (`dau_viec_options` trả `vat_tus: []` vì thiếu `buoc`, rồi
  `LsxRoutingTable.napDauViec` đè `khoan_chon_duoc`) — đã chẩn đoán, **chưa sửa**, chờ user yêu cầu.
- **Logic tiền lúc phát hành lệnh** — user đã nói *"tạm thời logic về tiền khi phát hành lệnh thì
  chưa bàn"*.
