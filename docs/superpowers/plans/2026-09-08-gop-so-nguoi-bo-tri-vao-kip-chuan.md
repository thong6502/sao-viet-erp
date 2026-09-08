# Gộp "Số người bố trí" vào "Kíp chuẩn" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Xoá hẳn ô/cột "Số người bố trí (kế hoạch)" (`so_nhan_cong`) khỏi bước lệnh SX và bước chung bài ghép; `so_nhan_cong_tieu_chuan` ("Kíp chuẩn") thành con số nhân lực DUY NHẤT — vừa chia thời lượng bước tổ, vừa là số bàn xếp lịch cân quân số tổ.

**Architecture:** `so_nhan_cong` chưa bao giờ là dữ liệu độc lập — mọi đường sinh nó đều chép từ `cong_doan_dau_viec.so_nguoi_tieu_chuan`, cùng nguồn với kíp chuẩn (bằng chứng: `lsx_service.py:1576`, `lsx_service.py:3249-3250`, `lsx_service.py:3269`, `bai_ghep_service.py:908-910`, `LsxBuocDrawer.tsx:302`, `LsxBuocDrawer.tsx:339`). Hộ tiêu thụ THẬT của nó chỉ có một: đỉnh quân số tổ ở xếp lịch (v1 core `_so_nguoi_dong` + v2 `TinhHuong._so_nguoi`). Đổi hộ đó sang đọc kíp chuẩn rồi gỡ cột.

Thứ tự 5 task giữ cây LUÔN XANH: backend thôi dùng cột (cột vẫn còn) → xếp lịch đổi nguồn đọc → frontend thôi gửi/hiện → mới gỡ cột khỏi model + migration → verify UI thật.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 (không Alembic — migration tay ở `backend/app/db_migrations.py`), PostgreSQL 16, pytest, React + TypeScript + Vite.

**Spec:** Chính tài liệu này (§ Bối cảnh & Quyết định bên dưới). Không có spec riêng — quyết định chốt trong hội thoại 08/09/2026.

## Bối cảnh & Quyết định

**Vì sao gỡ.** Hai ô cạnh nhau cùng trả lời một câu hỏi "việc này mấy người", cùng rót từ một nguồn, và ô "bố trí" không tham gia bất kỳ phép tính nào ngoài đỉnh quân số. Đây là đợt tiếp của migration `0270` (gộp 4 ô định mức nhân lực về 1) — cùng lý lẽ, cùng hình.

**Chốt 1 — kíp chuẩn THẮNG, không backfill.** Bước nào đang có `so_nhan_cong` ≠ `so_nhan_cong_tieu_chuan` (do gõ tay hoặc do drift ở `lsx_service.py:3016`/`:3260` — hai chỗ cập nhật kíp chuẩn mà cố ý không đụng bố trí) thì số bố trí **mất**, kíp chuẩn giữ nguyên. KHÔNG chép `so_nhan_cong` sang kíp chuẩn: gõ "6 người bố trí" trong khi kíp chuẩn 2 nghĩa là "tổ dồn 6 người vào", chép sang kíp chuẩn sẽ nhân 6 vào công thức và rút thời lượng bước tổ xuống 1/3 — bịa số. Prod đang DB trắng nên mất mát chỉ nằm ở DB demo dev.

**Chốt 2 — sau khi gộp, kíp chuẩn gánh HAI vai.** (a) chia thời lượng bước tổ (`thoi_luong_buoc`), (b) là số người bàn xếp lịch cộng dồn để dò đỉnh quân số tổ. Microcopy phải nói cả hai, không chỉ vai (a).

**Chốt 3 — payload API bỏ hẳn khoá `so_nhan_cong`**, không giữ lại như alias trỏ kíp chuẩn. Màn Xếp lịch 2 đã có sẵn `dinh_bien.tieu_chuan` cho đúng con số đó (`xep_lich_2/service.py:935-943`).

**Chốt 4 — cột DB DROP thật**, theo đúng mẫu `_migrate_gop_dinh_muc_nhan_luc` (mg `0270`, `db_migrations.py:12058`): chỉ DROP khi cột còn, để DB fresh (create_all theo model đã bỏ cột) và DB trung gian cho ra kết quả bằng nhau.

## Global Constraints

- Ngôn ngữ code/comment/commit: tiếng Việt (thuật ngữ kỹ thuật giữ tiếng Anh). Commit KHÔNG có `Co-Authored-By`.
- **KHÔNG chạy `./init.ps1`** và không chạy pytest toàn bộ. Verify bằng pytest NHẮM FILE (`cd backend && python -m pytest tests/<file> -q`) + `cd frontend && npx tsc --noEmit`.
- **KHÔNG chạy `python -c` trong `backend/`** — nó trỏ thẳng vào Postgres DEV thật. Muốn thăm dò thì viết test tạm rồi chạy pytest.
- Không có Alembic: `create_all` KHÔNG alter. Mọi thay đổi cột phải vào `backend/app/db_migrations.py`, và `docs/DB_SCHEMA.md` phải cập nhật CÙNG LÚC (có guard test — thiếu là fail).
- Migration mới nhất hiện tại: `0280_hang_loai_vat_tu_buoc` (`db_migrations.py:12559`). Migration của plan này là **`0281_go_so_nguoi_bo_tri`**.
- Backfill trong migration phải RAW SQL đích danh cột, KHÔNG dùng ORM full-select.
- Sửa route/schema backend ⇒ phải RESTART uvicorn (không hot-reload đáng tin).
- Task 5 (verify UI) BẮT BUỘC thao tác chuột/bàn phím thật trên dev-browser, KHÔNG dùng API/curl thay bất kỳ bước nào.

## File Structure

**Backend — thôi dùng cột (Task 1-2):**
- `backend/app/services/lsx_service.py` — engine thời lượng + bung routing + lưu routing + dict trả về bước
- `backend/app/schemas/lsx.py` — `LsxCongDoanIn` (input), `LsxCongDoanOut` (output)
- `backend/app/services/bai_ghep_service.py` — bước chung: tạo, danh sách sửa được, ghim khoán, dict trả về
- `backend/app/schemas/bai_ghep.py` — `BuocChungUpdateIn`, `BuocChungOut`
- `backend/app/services/xep_lich_service.py` — engine v1 (còn sống, v2 compose nó): `_so_nguoi_dong`, `khoang_tai_to`, cảnh báo, row `danh_sach`
- `backend/app/services/xep_lich_2/context.py` — `TinhHuong._so_nguoi`
- `backend/app/services/xep_lich_2/service.py` — payload `boi_canh` + panel

**Frontend — thôi gửi/hiện (Task 3):**
- `frontend/src/pages/lsxBuoc.ts` — model `EditRow`, map từ API, payload lưu, mirror engine thời lượng
- `frontend/src/pages/LsxBuocDrawer.tsx` — khối "Nhân sự tổ làm tay / vận hành máy"
- `frontend/src/pages/LsxRoutingTable.tsx` — dòng mới + chip dưới tên tổ
- `frontend/src/pages/BaiGhepBuocChungForm.tsx` — khối nhân lực bước chung
- `frontend/src/pages/XepLich2Page.tsx` — chip thẻ bước, tag dialog, dòng "Nhân lực" panel
- `frontend/src/api/client.ts` — 6 type
- `frontend/src/test/baiGhepSoDoFixture.ts` — fixture

**DB & docs (Task 4):**
- `backend/app/models/lsx.py`, `backend/app/models/bai_ghep_cong_doan.py`
- `backend/app/db_migrations.py` — migration `0281`
- `docs/DB_SCHEMA.md`, `docs/spec-xep-lich-2.md`

---

### Task 1: Backend lệnh SX + bài ghép thôi đọc/ghi `so_nhan_cong`

Cột vẫn còn trong model — chỉ cắt mọi đường đọc/ghi ở service + schema. Sau task này cây phải xanh.

**Files:**
- Modify: `backend/app/services/lsx_service.py` (dòng 276, 306, 391, 1576, 2477, 2921, 3012, 3096, 3250, 3269)
- Modify: `backend/app/schemas/lsx.py` (dòng 184, 271)
- Modify: `backend/app/services/bai_ghep_service.py` (dòng 764, 825, 854, 910, 1665)
- Modify: `backend/app/schemas/bai_ghep.py` (dòng 46, 374)
- Test: `backend/tests/test_lsx_service.py`, `backend/tests/test_bai_ghep_service.py`, `backend/tests/test_bai_ghep_2_service.py`, `backend/tests/test_cong_thuc_ve_cong_doan.py`

**Interfaces:**
- Consumes: `LsxCongDoan.so_nhan_cong_tieu_chuan` (int, NOT NULL, default 1) — cột duy nhất còn lại.
- Produces: dict bước của `LsxService` và `BaiGhepService` KHÔNG còn khoá `so_nhan_cong`; `thoi_luong_buoc(...)["dien_giai"]` KHÔNG còn khoá `so_nhan_cong_ke_hoach`. Khoá `so_nhan_cong_tieu_chuan` và `so_nhan_cong_tinh` giữ nguyên tên và ý nghĩa.

- [ ] **Step 1: Viết test đỏ — payload bước không còn `so_nhan_cong`, và sửa kíp chuẩn là đủ**

Thêm vào cuối `backend/tests/test_lsx_service.py`:

```python
def test_buoc_khong_con_o_so_nguoi_bo_tri(db, lsx_svc, admin, orders, customer):
    """Gộp 08/09/2026: nhân lực chỉ còn MỘT con số — kíp chuẩn.

    Trước đây `so_nhan_cong` (bố trí) và `so_nhan_cong_tieu_chuan` (kíp chuẩn) là hai cột nhưng
    mọi đường sinh đều chép từ cùng một nguồn `cong_doan_dau_viec.so_nguoi_tieu_chuan`.
    """
    lsx = _lsx_co_routing(db, lsx_svc, admin, orders, customer)
    buoc = lsx_svc.get(lsx.id)["cong_doans"][0]
    assert "so_nhan_cong" not in buoc
    assert "so_nhan_cong_tieu_chuan" in buoc
    assert "so_nhan_cong_ke_hoach" not in buoc["thoi_luong_dien_giai"]
```

`_lsx_co_routing` là helper — nếu file test chưa có helper cùng tên thì dùng đúng lối dựng lệnh mà các test lân cận trong file đang dùng (đọc `test_lsx_service.py` quanh dòng 2280 để chép cách dựng), đừng đẻ helper mới.

- [ ] **Step 2: Chạy để thấy nó ĐỎ**

```bash
cd backend && python -m pytest tests/test_lsx_service.py::test_buoc_khong_con_o_so_nguoi_bo_tri -q
```

Kỳ vọng: FAIL — `assert "so_nhan_cong" not in buoc`.

- [ ] **Step 3: Cắt `so_nhan_cong` khỏi `lsx_service.py`**

1. Dòng ~306: xoá `nguoi_ke_hoach = max(int(getattr(cd, "so_nhan_cong", 1) or 1), 1)`.
2. Dòng ~391 trong `dien_giai`: xoá khoá `"so_nhan_cong_ke_hoach": nguoi_ke_hoach,`.
3. Dòng ~276 (docstring `thoi_luong_buoc`): thay câu

   > `Dùng số người TIÊU CHUẨN (so_nhan_cong_tieu_chuan), KHÔNG dùng số người kế hoạch (so_nhan_cong) — số kế hoạch chỉ để bàn xếp lịch cân quân số + đối chiếu thực hiện.`

   bằng

   > `Nhân lực của bước nay chỉ còn MỘT con số — kíp chuẩn (so_nhan_cong_tieu_chuan). Ô "số người bố trí" (so_nhan_cong) GỠ 08/09/2026 (mg 0281): nó chưa bao giờ có nguồn riêng, mọi đường sinh đều chép từ cùng cong_doan_dau_viec.so_nguoi_tieu_chuan. Kíp chuẩn nay gánh cả hai vai: chia thời lượng ở đây, và là số bàn xếp lịch cộng dồn để dò đỉnh quân số tổ.`
4. Dòng ~1576 (`_buoc_tu_cong_doan`): xoá dòng `"so_nhan_cong": kip,` — giữ `"so_nhan_cong_tieu_chuan": kip,`.
5. Dòng ~2477: đổi `"so_luot_chay": cd.so_luot_chay, "so_nhan_cong": cd.so_nhan_cong,` thành `"so_luot_chay": cd.so_luot_chay,`.
6. Dòng ~2921 `_ROUTING_FIELD_THUAN`: đổi `"so_nhan_cong", "so_nhan_cong_tieu_chuan", "phat_sinh_phut",` thành `"so_nhan_cong_tieu_chuan", "phat_sinh_phut",`.
7. Dòng ~3012 comment: thay `Kíp CHUẨN đi theo công đoạn nên lấy số danh mục; \`so_nhan_cong\` (quân số thật kế hoạch bố trí) KHÔNG đụng — đó là con số của người, không của danh mục.` bằng `Kíp CHUẨN đi theo công đoạn nên lấy số danh mục. Số sửa tay tại bước vẫn thắng: \`_ap_soi_danh_muc\` chỉ ghi khi client không gửi trường đó.`
8. Dòng ~3096 docstring: bỏ cụm `(\`so_nhan_cong\`), ` khỏi câu liệt kê trường.
9. Dòng ~3250: xoá `_ke_thua("so_nhan_cong", int(dm.so_nguoi_tieu_chuan))`.
10. Dòng ~3269: xoá `_ke_thua("so_nhan_cong", row.so_nhan_cong_tieu_chuan)`.

- [ ] **Step 4: Cắt khỏi `schemas/lsx.py`**

Xoá dòng 184 `so_nhan_cong: int | None = Field(default=None, ge=1)` (giữ nguyên comment + dòng `so_nhan_cong_tieu_chuan` ngay dưới) và dòng 271 `so_nhan_cong: int = 1`.

Nhớ bẫy đã cắn một lần: Pydantic nuốt field IM LẶNG. Service trả dict mà schema `Out` không khai thì FE nhận `undefined` không lỗi — nên phải đi HẾT chuỗi `dict service → schema Out → type TS`, đừng dừng ở một tầng.

- [ ] **Step 5: Chạy test lệnh SX**

```bash
cd backend && python -m pytest tests/test_lsx_service.py tests/test_cong_thuc_ve_cong_doan.py -q
```

Kỳ vọng: test mới PASS. Các test cũ truyền `so_nhan_cong=` vào constructor `LsxCongDoan` (test_lsx_service.py:2165, 2179, 2186, 2205, 2216, 2226, 2284, 2292, 2714, 2726, 2897, 2904, 2946; test_cong_thuc_ve_cong_doan.py:164, 186) vẫn chạy được vì cột còn trong model — nhưng test nào ASSERT trên `so_nhan_cong` của payload thì phải sửa sang `so_nhan_cong_tieu_chuan`. Sửa từng cái theo đúng ý nghĩa gốc của test, đừng xoá test.

- [ ] **Step 6: Cắt khỏi `bai_ghep_service.py` + `schemas/bai_ghep.py`**

1. `bai_ghep_service.py:764`: xoá `so_nhan_cong=1,` (giữ `so_nhan_cong_tieu_chuan=1,`).
2. `:825` `_SUA_DUOC_BUOC_CHUNG`: đổi `"department_id", "may_id", "so_nhan_cong", "loai_buoc",` thành `"department_id", "may_id", "loai_buoc",`.
3. `:854`: xoá tham số `giu_kip="so_nhan_cong" in patch,` khỏi lời gọi `self._ghim_khoan_chung(...)`.
4. `_ghim_khoan_chung`: bỏ tham số `giu_kip` khỏi chữ ký và xoá hai dòng cuối thân hàm:

```python
        if not giu_kip:                       # người dùng vừa gõ tay kíp thì đừng đè lên
            chung.so_nhan_cong = int(dm.so_nguoi_tieu_chuan)
```

5. `:1665`: xoá `"so_nhan_cong": c.so_nhan_cong,` và sửa comment ngay trên cho khớp (nay chỉ còn kíp chuẩn).
6. `schemas/bai_ghep.py`: xoá dòng 46 `so_nhan_cong: int | None = None` và dòng 374 `so_nhan_cong: int = 1`.

- [ ] **Step 7: Chạy test bài ghép**

```bash
cd backend && python -m pytest tests/test_bai_ghep_service.py tests/test_bai_ghep_2_service.py -q
```

Kỳ vọng: PASS. Hai chỗ phải sửa: `test_bai_ghep_service.py:1241` (`sau["so_nhan_cong"] == 2` → `sau["so_nhan_cong_tieu_chuan"] == 2`) và `test_bai_ghep_2_service.py:164` (`chung.so_nhan_cong == 1` → `chung.so_nhan_cong_tieu_chuan == 1`).

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/lsx_service.py backend/app/schemas/lsx.py backend/app/services/bai_ghep_service.py backend/app/schemas/bai_ghep.py backend/tests/
git commit -m "Bo o so nguoi bo tri khoi lenh SX va bai ghep, nhan luc chi con kip chuan"
```

---

### Task 2: Xếp lịch cân quân số theo KÍP CHUẨN

Hộ tiêu thụ thật duy nhất của `so_nhan_cong`. Đổi nguồn đọc, và bỏ khoá `so_nhan_cong` khỏi payload API (màn v2 đã có `dinh_bien.tieu_chuan`).

**Files:**
- Modify: `backend/app/services/xep_lich_service.py:658`, `:851-855`, `:1800`, `:1808`, `:2283-2285`
- Modify: `backend/app/services/xep_lich_2/context.py:118-125`
- Modify: `backend/app/services/xep_lich_2/service.py:501`, `:928`
- Test: `backend/tests/test_xep_lich_dot3.py`, `backend/tests/test_xep_lich_service.py`, `backend/tests/test_xep_lich_2.py`, `backend/tests/test_xep_lich_phan_doan.py`

**Interfaces:**
- Consumes: `LsxCongDoan.so_nhan_cong_tieu_chuan`, `BaiGhepCongDoan.so_nhan_cong_tieu_chuan`.
- Produces: `XepLichService._so_nguoi_dong(r) -> int | None` đọc kíp chuẩn; khoá dict nội bộ của `khoang_tai_to` đổi tên `so_nhan_cong` → `so_nguoi`; payload `boi_canh`/panel của v2 KHÔNG còn khoá `so_nhan_cong` (dùng `dinh_bien.tieu_chuan`).

- [ ] **Step 1: Viết test đỏ — đỉnh quân số đếm theo kíp chuẩn**

Thêm vào `backend/tests/test_xep_lich_dot3.py` (file đã có helper `_dong_to`):

```python
def test_qua_tai_to_dem_theo_kip_chuan(db, vd_svc, to_dan):
    """08/09/2026: nhân lực chỉ còn kíp chuẩn — đỉnh quân số tổ đếm theo đúng số đó."""
    dong = _dong_to(to_dan.id, id=1, so_nhan_cong_tieu_chuan=3)
    assert vd_svc._qua_tai_to([dong]) != []
```

Nếu `_dong_to` chưa nhận `so_nhan_cong_tieu_chuan`, mở rộng helper cho nhận (đừng đẻ helper thứ hai) và đổi mọi lời gọi `so_nhan_cong=` hiện có trong file sang `so_nhan_cong_tieu_chuan=` — chúng đang mô tả đúng khái niệm đó.

- [ ] **Step 2: Chạy để thấy đỏ**

```bash
cd backend && python -m pytest tests/test_xep_lich_dot3.py -q
```

- [ ] **Step 3: Đổi nguồn đọc ở engine v1**

`xep_lich_service.py` dòng ~851:

```python
    def _so_nguoi_dong(self, r: XepLichCongDoan) -> int | None:
        """Kíp của một dòng — bước lệnh đọc `lsx_cong_doan`, bài ghép đọc bước chung.

        Đọc KÍP CHUẨN (`so_nhan_cong_tieu_chuan`): ô "số người bố trí" riêng đã gỡ 08/09/2026
        (mg `0281`) vì nó luôn là bản sao của kíp chuẩn, và không ai đồng bộ lại bản sao đó.
        """
        buoc = (
            self._lcd(r.lsx_cong_doan_id) if r.nguon == NGUON_LSX
            else self.db.get(BaiGhepCongDoan, r.bai_ghep_cong_doan_id)
            if r.bai_ghep_cong_doan_id else None
        )
        return int(getattr(buoc, "so_nhan_cong_tieu_chuan", 1) or 1) if buoc else None
```

Rồi đổi tên khoá dict NỘI BỘ (không phải cột, không phải API) cho khỏi gọi tên đã chết:
- `:658` `dung = sum(int(r.get("so_nhan_cong") or 1) for r in chay)` → `r.get("so_nguoi")`
- `:1800` và `:1808`: khoá `"so_nhan_cong": self._so_nguoi_dong(...)` → `"so_nguoi": ...`

Trước khi đổi, chạy `grep -rn '"so_nhan_cong"' backend/app/services/xep_lich_service.py backend/app/services/xep_lich_van_de_service.py` để chắc không sót nơi đọc khoá này (`khoang_tai_to` được `xep_lich_van_de_service` dùng lại).

- [ ] **Step 4: Bỏ khoá khỏi payload API (v1 row + v2)**

- `xep_lich_service.py:2283-2285`: **ĐỔI TÊN** khoá `"so_nhan_cong"` của row `danh_sach()` thành
  `"so_nguoi"` (đọc `_so_nguoi_dong`), sửa comment hai dòng trên nó. KHÔNG xoá như bản plan đầu:
  `xep_lich_van_de_service.py:161` rót thẳng `danh_sach()["items"]` vào `_qua_tai_to` → `khoang_tai_to`,
  xoá khoá là detector vượt quân số câm luôn.
- `xep_lich_2/service.py:501` và `:928`: xoá dòng `"so_nhan_cong": int(getattr(op, "so_nhan_cong", 1) or 1) if op is not None else None,` — `"dinh_bien": self._dinh_bien(op)` ngay dưới đã mang đúng con số.
- `xep_lich_2/context.py:118-125`: đổi thân `_so_nguoi` sang `so_nhan_cong_tieu_chuan`, sửa docstring:

```python
    def _so_nguoi(self, dong: XepLichCongDoan) -> int:
        """Kíp MỘT dòng tiêu thụ — kíp chuẩn của bước (§4).

        Ô "số người bố trí" riêng đã gỡ 08/09/2026 (mg `0281`): kíp chuẩn nay gánh cả hai vai —
        chia thời lượng bước tổ và là số cân quân số ở bàn này.
        """
        op = None
        if dong.nguon == NGUON_IN_GHEP and dong.bai_ghep_cong_doan_id:
            op = self.db.get(BaiGhepCongDoan, dong.bai_ghep_cong_doan_id)
        elif dong.lsx_cong_doan_id:
            op = self.db.get(LsxCongDoan, dong.lsx_cong_doan_id)
        return max(1, int(getattr(op, "so_nhan_cong_tieu_chuan", 1) or 1))
```

- [ ] **Step 5: Sửa test hợp đồng của v2**

`backend/tests/test_xep_lich_2.py:1481` — bỏ `"so_nhan_cong"` khỏi `_KHOA_BUOC`.

Đồng thời KIỂM `:1523` `assert set(b["dinh_bien"]) == {"toi_thieu", "tieu_chuan", "toi_da"}`: `_dinh_bien` hiện chỉ trả `{"tieu_chuan"}` (mg `0270` đã gỡ hai mốc kia), nên assert này khả năng đang ĐỎ SẴN từ trước plan này. Chạy file test trước khi sửa để biết chắc, rồi sửa thành `== {"tieu_chuan"}` và ghi rõ trong commit message là vá nợ cũ chứ không phải hệ quả của đợt gộp.

- [ ] **Step 6: Chạy test xếp lịch**

```bash
cd backend && python -m pytest tests/test_xep_lich_dot3.py tests/test_xep_lich_dot2.py tests/test_xep_lich_service.py tests/test_xep_lich_2.py tests/test_xep_lich_phan_doan.py tests/test_xep_lich_van_de.py -q
```

Kỳ vọng: PASS. Chỗ phải sửa: `test_xep_lich_service.py:1056` (`step.so_nhan_cong = 3` → `step.so_nhan_cong_tieu_chuan = 3`), `test_xep_lich_dot2.py:47`, `test_xep_lich_phan_doan.py:284` (bỏ `so_nhan_cong=1,`, giữ `so_nhan_cong_tieu_chuan=1`).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/xep_lich_service.py backend/app/services/xep_lich_2/ backend/tests/
git commit -m "Xep lich can quan so to theo kip chuan, bo khoa so_nhan_cong khoi payload"
```

---

### Task 3: Frontend thôi gửi và thôi bày "số bố trí"

**Files:**
- Modify: `frontend/src/pages/lsxBuoc.ts:86`, `:235`, `:340`, `:464`, `:560`, `:582`, `:668`
- Modify: `frontend/src/pages/LsxBuocDrawer.tsx:302`, `:339`, `:876-897` (khối ô bố trí), `:941-947`, hint kíp chuẩn `:933-960`
- Modify: `frontend/src/pages/LsxRoutingTable.tsx:301`, `:350`, `:775-780`
- Modify: `frontend/src/pages/BaiGhepBuocChungForm.tsx:196`, `:207`, `:223`, `:540-556`, `:578-584`
- Modify: `frontend/src/pages/XepLich2Page.tsx:1756-1762`, `:1914-1921`, `:2203-2208`
- Modify: `frontend/src/api/client.ts:675`, `:776`, `:1043`, `:1315`, `:2439`, `:2500`
- Modify: `frontend/src/test/baiGhepSoDoFixture.ts:87`
- Test: `frontend/src/pages/lsxBuoc.test.ts`, `backend/tests/test_khsx_ui_contract.py`

**Interfaces:**
- Consumes: payload bước KHÔNG còn `so_nhan_cong` (Task 1), payload xếp lịch KHÔNG còn `so_nhan_cong` (Task 2).
- Produces: `EditRow` không còn field `so_nhan_cong`; `thoiLuongLive(...)` trả `dien_giai` không còn `so_nhan_cong_ke_hoach`.

- [ ] **Step 1: Sửa test hợp đồng UI (đây là test ĐỎ của task này)**

`backend/tests/test_khsx_ui_contract.py`, hàm `test_drawer_hien_nhan_luc_ke_thua_va_ket_qua_thoi_gian_o_cuoi`:

```python
    # 08/09/2026 (mg `0281`): ô "số người bố trí" GỠ HẲN — nhân lực chỉ còn kíp chuẩn, và kíp
    # chuẩn nay gánh cả hai vai (chia thời lượng + cân quân số tổ ở bàn xếp lịch).
    assert "số người bố trí" not in source
    assert "kíp chuẩn (định mức công đoạn)" in source
    assert "cân quân số tổ" in source
```

(xoá dòng `assert "số người bố trí (kế hoạch)" in source` cũ và comment 21/08/2026 đi kèm.)

- [ ] **Step 2: Chạy để thấy đỏ**

```bash
cd backend && python -m pytest tests/test_khsx_ui_contract.py -q
```

- [ ] **Step 3: `lsxBuoc.ts` — gỡ field khỏi model + payload + mirror engine**

- `:86`: xoá `so_nhan_cong: string;`
- `:235`: xoá `so_nhan_cong: s(cd.so_nhan_cong),`
- `:340`: bỏ `so_nhan_cong: "",` khỏi row rỗng
- `:464`: xoá `so_nhan_cong: on(r.so_nhan_cong),` khỏi payload lưu
- `:560`: xoá `| "so_nhan_cong"` khỏi union
- `:582`: xoá `const nguoiKeHoach = ...`
- `:668`: xoá `so_nhan_cong_ke_hoach: nguoiKeHoach,`

- [ ] **Step 4: `LsxBuocDrawer.tsx` — gỡ ô, dồn microcopy vào kíp chuẩn**

- `tuDinhMuc` (`:302`): xoá `so_nhan_cong: String(chon?.so_nguoi_tieu_chuan ?? 1),`
- `doiLoaiBuoc` (`:339`): `onPatch({ loai_buoc: k, so_nhan_cong_tieu_chuan: kip });`
- Xoá nguyên `<label className="khsx-field">` của "SỐ NGƯỜI BỐ TRÍ (KẾ HOẠCH)" (input + hint).
- Ô kíp chuẩn `onChange`: bỏ nhánh kéo theo, còn `onPatch({ so_nhan_cong_tieu_chuan: std })` — xoá hai biến `cu`/`kh` nay không ai dùng.
- Hint kíp chuẩn phải nói ĐỦ HAI VAI. Bước tổ:

```tsx
  <>
    Kíp chuẩn <strong>rút ngắn thời gian</strong>: năng suất khoán khai theo đầu người nên kíp{" "}
    {Math.max(1, Number(row.so_nhan_cong_tieu_chuan) || 1)} người làm nhanh gấp{" "}
    {Math.max(1, Number(row.so_nhan_cong_tieu_chuan) || 1)}. Bàn xếp lịch cũng{" "}
    <strong>cân quân số tổ</strong> theo đúng số này.
  </>
```

  Bước máy/thuê ngoài: giữ câu "Điền sẵn từ định mức đầu việc của công đoạn — …" và nối thêm `Bàn xếp lịch cân quân số tổ theo đúng số này.` trước câu "Không ảnh hưởng tốc độ máy".
- Sửa comment khối `{/* Nhân lực của bước — … */}` cho khớp: nay một ô, không phải "số bố trí ở trên, ba mốc ở dưới".

- [ ] **Step 5: `LsxRoutingTable.tsx`**

- `:301`: xoá `so_nhan_cong: String(chosen?.so_nguoi_tieu_chuan ?? 1),`
- `:350`: `so_nhan_cong: "1", so_nhan_cong_tieu_chuan: 1,` → `so_nhan_cong_tieu_chuan: 1,`
- `:775-780`: chip đổi thành

```tsx
                    <span
                      className="khsx-rt__sub2"
                      title="Kíp chuẩn của bước — chia thời lượng bước tổ và là số bàn xếp lịch cân quân số tổ."
                    >
                      Kíp {Math.max(1, n(r.so_nhan_cong_tieu_chuan) || 1)} người
                    </span>
```

- [ ] **Step 6: `BaiGhepBuocChungForm.tsx`**

- `:196`: xoá `const boTri = ...`
- `:207`: xoá `so_nhan_cong: String(...)` khỏi object truyền vào `thoiLuongLive`
- `:223`: bỏ `f.so_nhan_cong` khỏi mảng deps
- `:540-556`: xoá nguyên `<label>` "SỐ NGƯỜI BỐ TRÍ (KẾ HOẠCH)"
- `:578-584`: `onChange` kíp chuẩn còn `setF({ ...f, so_nhan_cong_tieu_chuan: std })`; xoá biến `cu`
- Hint kíp chuẩn: nối thêm câu cân quân số y như drawer lệnh.

- [ ] **Step 7: `XepLich2Page.tsx` + `client.ts` + fixture**

- `:1756-1762`: xoá khối `{b.so_nhan_cong != null && (...)}`; khối `dbText` ngay dưới đổi nhãn từ `ĐB {dbText}` sang `{dbText}` với `nhanLucTom` trả `\`${db.tieu_chuan} người\`` thay `\`chuẩn ${db.tieu_chuan}\`` (dòng 136-138).
- `:1860-1861`: `nhanLucText` đổi thành `nl.text == null ? null : \`kíp ${nl.text}\`` → giữ, nhưng vì `nhanLucTom` đổi format thì rà lại chuỗi cho không thành "kíp 3 người người".
- `:1914-1921`: xoá khối `{xt.so_nhan_cong != null && (...)}`, thay bằng tag chỉ hiện `nhanLucText`.
- `:2203-2208`: dòng "Nhân lực" đổi sang đọc `nl` (kíp chuẩn), bỏ `xt.so_nhan_cong`.
- `client.ts`: xoá `so_nhan_cong` ở dòng 675, 776, 1043, 1315, 2439, 2500 (giữ mọi `so_nhan_cong_tieu_chuan`).
- `baiGhepSoDoFixture.ts:87`: xoá `so_nhan_cong: 1,`.

- [ ] **Step 8: Verify frontend**

```bash
cd frontend && npx tsc --noEmit
```

Kỳ vọng: 0 lỗi. Rồi:

```bash
cd frontend && npx vitest run src/pages/lsxBuoc.test.ts
```

Sửa test nào còn dựng `so_nhan_cong` trong row.

- [ ] **Step 9: Chạy lại test hợp đồng UI**

```bash
cd backend && python -m pytest tests/test_khsx_ui_contract.py -q
```

Kỳ vọng: PASS.

- [ ] **Step 10: Commit**

```bash
git add frontend/src backend/tests/test_khsx_ui_contract.py
git commit -m "Frontend bo o so nguoi bo tri, kip chuan gánh ca vai can quan so"
```

---

### Task 4: Gỡ cột khỏi model + migration `0281` + docs

**Files:**
- Modify: `backend/app/models/lsx.py:72`, `:277-281`
- Modify: `backend/app/models/bai_ghep_cong_doan.py:75`
- Modify: `backend/app/db_migrations.py` (thêm cuối file, sau `0280`)
- Modify: `docs/DB_SCHEMA.md:3976`, `:4136`, và mô tả `so_nhan_cong_tieu_chuan` ở cả hai bảng
- Modify: `docs/spec-xep-lich-2.md:38`, `:75`
- Test: `backend/tests/test_migration_0281_go_so_nguoi_bo_tri.py` (tạo mới)

**Interfaces:**
- Consumes: không còn code nào đọc `so_nhan_cong` (Task 1-3 đã cắt hết).
- Produces: `LsxCongDoan` và `BaiGhepCongDoan` không còn attribute `so_nhan_cong`; migration `0281_go_so_nguoi_bo_tri` idempotent.

- [ ] **Step 1: Viết test migration (đỏ)**

Tạo `backend/tests/test_migration_0281_go_so_nguoi_bo_tri.py`, lấy `backend/tests/test_migration_0270_gop_dinh_muc_nhan_luc.py` làm khuôn (đọc nó trước, chép đúng lối dựng engine tạm + gọi migration), nội dung kiểm:

```python
"""mg `0281`: gỡ cột `so_nhan_cong` (số người bố trí) ở bước lệnh và bước chung bài ghép.

Nhân lực của hệ nay chỉ còn MỘT con số: `so_nhan_cong_tieu_chuan` (kíp chuẩn). Cột bỏ đi chưa
bao giờ có nguồn riêng — mọi đường sinh đều chép từ `cong_doan_dau_viec.so_nguoi_tieu_chuan`.
"""

BANG_COT = {
    "lsx_cong_doan": ("so_nhan_cong", "so_nhan_cong_tieu_chuan"),
    "bai_ghep_cong_doan": ("so_nhan_cong", "so_nhan_cong_tieu_chuan"),
}
```

Hai assert bắt buộc: (a) sau khi chạy toàn bộ `MIGRATIONS` trên DB dựng từ model, cột `so_nhan_cong` KHÔNG còn ở cả hai bảng còn `so_nhan_cong_tieu_chuan` CÒN; (b) chạy migration `0281` lần hai không nổ (idempotent — DB fresh không có cột thì nhánh DROP bị bỏ qua).

- [ ] **Step 2: Chạy để thấy đỏ**

```bash
cd backend && python -m pytest tests/test_migration_0281_go_so_nguoi_bo_tri.py -q
```

- [ ] **Step 3: Gỡ cột khỏi model**

`backend/app/models/lsx.py` — xoá khối:

```python
    # Số người/máy chạy ĐỒNG THỜI (BC: Concurrent Capacities) — 5 người dán thì thời gian chạy ÷ 5.
    # Chỉ có nghĩa với bước chiếm tổ; bước chiếm máy để 1.
    so_nhan_cong: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1", default=1
    )
```

và sửa comment dòng 72 `# Bước chiếm tổ (nhiều người làm song song được → \`so_nhan_cong\` chia thời gian chạy).` thành `# Bước chiếm tổ (nhiều người làm song song được → \`so_nhan_cong_tieu_chuan\` chia thời gian chạy).`

Bổ sung vào comment của `so_nhan_cong_tieu_chuan` một câu mốc: `Ô "số người bố trí" (\`so_nhan_cong\`) GỠ 08/09/2026 (mg \`0281\`) — nó luôn là bản sao của cột này; kíp chuẩn nay gánh cả hai vai: chia thời lượng bước tổ và cân quân số tổ ở bàn xếp lịch.`

`backend/app/models/bai_ghep_cong_doan.py:75`: xoá dòng `so_nhan_cong: Mapped[int] = ...` và nối câu mốc tương tự vào comment của `so_nhan_cong_tieu_chuan`.

- [ ] **Step 4: Viết migration `0281`**

Thêm vào cuối `backend/app/db_migrations.py`:

```python
def _migrate_go_so_nguoi_bo_tri(db) -> None:
    """Gỡ ô "số người bố trí" — nhân lực của bước còn MỘT con số (08/09/2026).

    Nghiệp vụ: bước lệnh (và bước chung bài ghép) có hai ô người đứng cạnh nhau — "số người bố
    trí (kế hoạch)" và "kíp chuẩn". Chúng KHÔNG phải hai đại lượng: mọi đường sinh `so_nhan_cong`
    đều chép từ đúng cùng một nguồn `cong_doan_dau_viec.so_nguoi_tieu_chuan` như kíp chuẩn, nên
    hai ô luôn hiện cùng một số cho tới khi ai đó gõ tay đè lên một ô. Đây là đợt tiếp của `0270`
    (gộp 4 mốc định mức nhân lực về 1), cùng lý lẽ.

    Kíp chuẩn nay gánh cả hai vai: chia thời lượng bước tổ (`thoi_luong_buoc`) VÀ là số bàn xếp
    lịch cộng dồn để dò đỉnh quân số tổ (`XepLichService._so_nguoi_dong`, `TinhHuong._so_nguoi`).

    MẤT THEO — KHÔNG backfill: bước nào đang có `so_nhan_cong` khác kíp chuẩn thì số đó mất.
    Cố ý: gõ "6 người bố trí" trong khi kíp chuẩn 2 nghĩa là tổ dồn 6 người vào, chép 6 sang kíp
    chuẩn sẽ nhân 6 vào công thức và rút thời lượng còn 1/3 — bịa số tệ hơn là mất số.

    Chỉ DROP khi cột còn: DB fresh (create_all theo model đã bỏ cột) rơi vào nhánh bỏ qua, nên
    DB trung gian chạy tới đây cho kết quả bằng DB fresh.
    """
    insp = inspect(db.get_bind())
    bang_co = set(insp.get_table_names())
    for bang in ("lsx_cong_doan", "bai_ghep_cong_doan"):
        if bang not in bang_co:
            continue
        if "so_nhan_cong" in _existing_columns(insp, bang):
            db.execute(text(f"ALTER TABLE {bang} DROP COLUMN so_nhan_cong"))
    db.commit()


MIGRATIONS.append(("0281_go_so_nguoi_bo_tri", _migrate_go_so_nguoi_bo_tri))
```

- [ ] **Step 5: Cập nhật `docs/DB_SCHEMA.md` (guard test đòi khớp model)**

- Xoá dòng `| \`so_nhan_cong\` | \`Integer\` | — | no | \`1\` | Số người kế hoạch. …|` ở bảng `lsx_cong_doan` (dòng ~3976) và dòng tương ứng ở `bai_ghep_cong_doan` (~4136).
- Sửa mô tả `so_nhan_cong_tieu_chuan` ở CẢ HAI bảng thành: `Kíp chuẩn kế thừa từ \`cong_doan_dau_viec.so_nguoi_tieu_chuan\` — con số nhân lực DUY NHẤT của bước: chia thời lượng bước Tổ, và là số bàn xếp lịch cân quân số tổ. Ô "số người bố trí" (\`so_nhan_cong\`) GỠ ở mg \`0281\`; hai mốc \`_toi_thieu\`/\`_toi_da\` GỠ ở mg \`0270\`.`
- Nếu ba dòng dài bị công cụ tìm kiếm báo "Omitted" (`:3189`, `:4001`, `:4179`) có liệt kê tên cột thì rà và bỏ `so_nhan_cong` khỏi đó.

- [ ] **Step 6: Cập nhật `docs/spec-xep-lich-2.md`**

- Dòng 38: `| Số người của bước | \`lsx_cong_doan.so_nhan_cong_tieu_chuan\` (kíp chuẩn), mirror ở \`bai_ghep_cong_doan\` |`
- Dòng 75: đổi `chiếm **đúng \`so_nhan_cong\`**` thành `chiếm **đúng \`so_nhan_cong_tieu_chuan\`** (kíp chuẩn)`.

- [ ] **Step 7: Chạy test migration + guard schema + hồi quy vùng liên quan**

```bash
cd backend && python -m pytest tests/test_migration_0281_go_so_nguoi_bo_tri.py tests/test_db_schema_doc.py tests/test_khsx_migration.py -q
```

(Tên file guard schema: tìm bằng `grep -rln "DB_SCHEMA" backend/tests` nếu `test_db_schema_doc.py` không đúng tên.)

```bash
cd backend && python -m pytest tests/test_lsx_service.py tests/test_bai_ghep_service.py tests/test_xep_lich_2.py tests/test_xep_lich_dot3.py tests/test_san_xuat_thuc_thi.py -q
```

Kỳ vọng: PASS hết. `test_khsx_migration.py:13,33` dựng bảng cũ CÓ cột `so_nhan_cong` — migration `0281` phải DROP được nó, đó chính là đường mà test này đi.

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/ backend/app/db_migrations.py backend/tests/ docs/DB_SCHEMA.md docs/spec-xep-lich-2.md
git commit -m "mg 0281: go cot so_nhan_cong o buoc lenh va buoc chung bai ghep"
```

---

### Task 5: Nghiệm thu bằng luồng UI THẬT

CLAUDE.md bắt buộc: luồng nghiệp vụ có UI thì phải thao tác lại đúng luồng bằng chuột/bàn phím thật trên dev-browser, KHÔNG dùng API/curl thay bất kỳ bước nào (kể cả bước dựng dữ liệu). Báo cáo phải kể cụ thể bấm gì / gõ gì / thấy gì.

**Files:** không sửa code (trừ khi phát hiện lỗi).

- [ ] **Step 1: Dựng lại DB dev**

Cột bị DROP nên uvicorn phải chạy migration `0281`. Bật lại backend (đẻ tiến trình qua WMI `Win32_Process.Create`, không dùng Bash nền / Start-Process — chúng chết theo phiên), BE `127.0.0.1:8000`, FE `localhost:5173`. Sửa model/schema ⇒ RESTART uvicorn, không tin hot-reload.

- [ ] **Step 2: Đăng nhập + mở lệnh SX**

Đăng nhập `admin` / `admin123`. Input React phải set qua native setter khi lái bằng JS; ưu tiên gõ thật bằng `computer` action `type`. Bẫy đã biết: click theo `ref` bắn trật toạ độ (hệ số ≈2,65) — hover đo trước rồi mới click.

Mở màn Lệnh sản xuất → chọn một lệnh có bước TỔ → mở drawer bước.

- [ ] **Step 3: Kiểm khối nhân lực còn ĐÚNG MỘT ô**

Thấy: tiêu đề "NHÂN SỰ TỔ LÀM TAY", KHÔNG còn ô "SỐ NGƯỜI BỐ TRÍ (KẾ HOẠCH)", còn ô "KÍP CHUẨN (ĐỊNH MỨC CÔNG ĐOẠN)", hint nói cả hai vai (rút ngắn thời gian + cân quân số tổ).

- [ ] **Step 4: Gõ kíp chuẩn = 3, xem thời lượng nhảy NGAY**

Ghi lại số "Thời gian chiếm máy" trước và sau. Bước tổ có năng suất ⇒ thời lượng phải giảm còn ~1/3. Bấm **Lưu**, đóng drawer, mở lại — kíp chuẩn vẫn 3 (không bị server kéo về định mức).

- [ ] **Step 5: Bảng routing hiện chip "Kíp 3 người"**

Nhìn cột tổ ở bảng routing của chính lệnh đó: chip phải đọc "Kíp 3 người", không còn chữ "Kế hoạch".

- [ ] **Step 6: Xếp lịch cân quân số theo số vừa gõ**

Vào màn Xếp lịch (v2), xếp bước đó vào một tổ có quân số nhỏ hơn 3 → phải nổ cảnh báo `vuot_quan_so_to` / tải tổ cao với đúng con số 3. Panel bên phải: dòng "Nhân lực" hiện kíp chuẩn, KHÔNG còn dòng "Bố trí N người".

- [ ] **Step 7: Bài ghép — bước chung**

Mở màn Bài ghép → một bài có bước chung → drawer bước chung: cũng đúng một ô kíp chuẩn, gõ số, lưu, mở lại thấy giữ.

- [ ] **Step 8: Ghi báo cáo nghiệm thu**

Liệt kê từng bước: bấm gì, gõ gì, thấy gì (kèm số trước/sau ở Step 4). Nếu vì lý do nào đó buộc phải tắt qua API ở một đoạn thì PHẢI tự nói rõ ngay trong báo cáo.

- [ ] **Step 9: Commit (nếu Step 1-8 lộ lỗi phải vá)**

```bash
git add -A
git commit -m "Va loi phat hien khi nghiem thu luong nhan luc mot o"
```

## Ghi chú cho người thực thi

- **Bẫy Pydantic nuốt field im lặng:** bỏ field ở `schemas/*Out` mà quên bỏ ở dict service thì không ai báo lỗi — chỉ là FE không thấy. Ngược lại cũng vậy. Đi đủ chuỗi `dict service → schema Out → type TS` cho từng khoá.
- **`_ke_thua` chỉ ghi khi client KHÔNG gửi trường đó** (`lsx_service.py:3212`). Sau khi gỡ, số kíp chuẩn gõ tay vẫn phải thắng — chính là test `test_lsx_service.py:2897-2904` đang canh (nhớ chuyển assert của nó sang kíp chuẩn thay vì xoá).
- **Hai chỗ drift cũ** (`lsx_service.py:3016`, `:3260`) chỉ cập nhật kíp chuẩn và cố ý không đụng bố trí — sau khi gỡ cột thì chúng thành đúng, không cần sửa logic, chỉ sửa comment nếu comment còn nhắc `so_nhan_cong`.
- **Đừng chạy pytest toàn bộ** để "cho chắc" — chạy nhắm file như từng task đã ghi; CI GitHub gánh phần còn lại.
