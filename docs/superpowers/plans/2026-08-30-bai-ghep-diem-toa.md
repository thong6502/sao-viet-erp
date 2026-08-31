# Bài ghép — Điểm toả (một khuôn – một chuỗi chung – một điểm toả) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hoàn thiện mô hình Bài ghép "một khuôn – một chuỗi chung – một điểm toả": thêm các gate CỨNG chặn "Sẵn sàng" khi bài ghép chưa đủ điều kiện vật lý/kỹ thuật, sửa bug chọn kiểu in khi tính kẽm gộp, cho phép mỗi dòng vật tư của bước chung chọn nguồn số lượng (định mức tự tính / nhập tay), và nối điểm toả (bước chung cuối cùng trên dòng giấy) thành cạnh phụ thuộc PERSISTED để pha Thực hiện sản xuất tự động tách sản lượng tốt của batch chung thành sản lượng riêng cho từng LSX thành viên, bàn giao thẳng, và chặn LSX này dùng nhầm phần đã tỏa cho LSX khác.

**Architecture:** Bài ghép đã có sẵn hai nửa của mô hình: (1) "một chuỗi chung" — `BaiGhepCongDoan` (bước dùng chung) + `BaiGhepCongDoanMap` (bước LSX nào bị phủ), lập kế hoạch xuôi/ngược qua `_ap_so_luong_chung`/`chuoi_nguoc_dv`; (2) "một điểm toả" ở dạng HÀM THUẦN trong bộ nhớ (`_toa_tai`/tính `so_con_tren_to` mỗi thành viên) nhưng CHƯA có cạnh DB nào ghi lại "điểm này là nơi chuỗi chung tách ra". Plan này:
- Thêm 4 gate cứng vào `BaiGhepService.thieu_cua()` (Task 1–2), tái dùng dữ liệu đã tính sẵn (`fill_pct`, `_con_toi_da`, `tren_dong_giay`) — không viết engine mới.
- Sửa `gop()` chặn gộp lệch đơn vị vào/ra hoặc lệch kiểu in ngay lúc bấm Gộp (Task 3), và trích một helper `_kieu_in_bai()` dùng chung để `muc_gop()` không còn "đoán" kiểu in theo thành viên đầu tiên tìm thấy (Task 4).
- Thêm cột `nguon_so_luong` (`dinh_muc`/`thu_cong`) trên `BaiGhepCongDoanVatTu` (Task 6) để dòng vật tư nào do người khai tay thì KHÔNG bị ghi đè khi bài ghép đổi số (Task 7), và phản ánh đúng lên UI (Task 8) — thay heuristic so khớp số hiện tại (không đáng tin) bằng cờ SERVER lưu thật.
- Ở lúc PHÁT HÀNH, suy ra điểm toả của từng LSX thành viên (bước dùng-chung cuối cùng TRÊN DÒNG GIẤY, dùng đúng `tren_dong_giay` đã có) và ghi PERSISTED thành một cạnh `SanXuatPhuThuoc` (bảng đã tồn tại cho phụ thuộc chéo LSX-LSX, tái dùng cho phụ thuộc điểm-toả) — Task 9.
- Ở lúc ghi batch sản lượng cho công việc điểm-toả, tự động nhân `tot` với `ty_le_ghep` (= số con/tờ) của mỗi cạnh toả để ra sản lượng riêng từng LSX, ghi vào bảng mới `SanXuatKetQuaNhanh` (Task 10) rồi bàn giao THẲNG dạng đã xác nhận (Task 11) — không qua vòng đề xuất/xác nhận hai bên vì số này suy một chiều, không thể vượt. Chặn LSX này tiêu thụ nhầm phần đã tỏa cho LSX khác qua một quota check mới trong `_chuan_hoa_lot()` (Task 12).
- Trả kết quả toả qua API (Task 13) và hiển thị trên màn Thực hiện sản xuất (Task 14).
- Cập nhật tài liệu để hai spec (`spec-bai-ghep-dag.md`, `spec-thuc-hien-san-xuat.md`) phản ánh đúng thiết kế mới (Task 15).

**Tech Stack:** FastAPI + SQLAlchemy 2.0 (Python), Postgres (dev/prod) / SQLite `:memory:` (test), React + TypeScript (frontend, không dùng framework state riêng — state cục bộ + `client.ts` làm lớp API).

**Spec:** Không có file spec riêng — thiết kế đầy đủ được người dùng cung cấp trực tiếp trong hội thoại (dạng văn bản "một khuôn – một chuỗi chung – một điểm toả") và đã được đối chiếu kỹ với CODE hiện tại (không phải với `docs/spec-bai-ghep-dag.md`/`docs/spec-thuc-hien-san-xuat.md`, hai file này ĐANG CŨ trên đúng điểm này). Phần **Architecture** ở trên là nguồn sự thật tạm thời cho tới khi Task 15 cập nhật lại hai spec đó.

## Global Constraints

- KHÔNG có Alembic. Mọi cột/bảng thêm vào model ĐÃ TỒN TẠI phải có ALTER tương ứng trong `backend/app/db_migrations.py` (bảng MỚI thì `create_all` tự lo, không cần migration). Số hiệu migration tiếp theo là **`0243`** — đã xác minh lại từ đuôi file thật (`0242_doi_ten_cot_markup` là migration cuối cùng đã có trên nhánh hiện tại; ĐỪNG dùng số `0240` dù tài liệu/bộ nhớ cũ có nhắc tới số đó — số đó đã bị việc khác chiếm).
- Cột Boolean thêm mới (nếu có) phải `server_default=false()`/`true()` (import từ `sqlalchemy`), KHÔNG phải chuỗi `"0"`/`"1"`.
- `docs/DB_SCHEMA.md` có guard test: mọi bảng/cột trong model phải được liệt kê ở đó, thiếu là `pytest` đỏ.
- Sửa route/schema backend xong phải RESTART uvicorn thủ công — dev server ở máy này không hot-reload đáng tin.
- KHÔNG động vào `BaiGhepService.canh_bao_cua()` (cảnh báo MỀM: khác giấy/khác số màu/khác số mặt/bài thưa…) — quyết định 17/08/2026 gỡ các cảnh báo đó khỏi `canh_bao_cua()` giữ nguyên. Plan này chỉ thêm gate CỨNG mới vào `thieu_cua()` (chặn "Sẵn sàng"), một khối hoàn toàn khác, không phải khôi phục lại cảnh báo mềm đã gỡ.
- KHÔNG chạy `python -c` chạm DB dev thật để thăm dò dữ liệu — mọi kiểm chứng hành vi đi qua pytest (fixture `db` ép SQLite `:memory:`, xem `backend/tests/conftest.py`).
- KHÔNG tự ý chạy `./init.ps1` hay bộ pytest đầy đủ — verify từng Task bằng lệnh pytest NHẮM ĐÚNG FILE/hàm test của Task đó (`pytest backend/tests/<file>.py::<test> -v`) và `npx tsc --noEmit` (từ `frontend/`) cho các Task sửa `.ts`/`.tsx`. Chỉ chạy bộ rộng hơn khi được yêu cầu.
- Mọi công việc GHI ở tầng `services/san_xuat/*` giữ nguyên khuôn "không tự `db.commit()` bên trong hàm phụ trợ dùng chung một giao dịch" — chỉ hàm ở tầng ngoài cùng (được router gọi trực tiếp) mới `commit()`.

---

### Task 1: Gate cứng — khác giấy · bước chung phải phủ hết thành viên · bước chung phải có mặt trên dòng giấy

**Files:**
- Modify: `backend/app/services/bai_ghep_service.py:1825-1861` (hàm `thieu_cua`)
- Test: `backend/tests/test_bai_ghep_service.py`

**Interfaces:**
- Consumes: `self._buoc_chungs(bg)` (có sẵn), `self._tram()` (có sẵn, memoized `ban_do_tram`), `tren_dong_giay(don_vi_vao, don_vi_ra, ban_do, *, nhom=None) -> bool` (đã import sẵn ở đầu file từ `.dong_giay`), `BaiGhepCongDoan.thanh_phans` (list `BaiGhepCongDoanMap`, có `.lsx_id`).
- Produces: `thieu_cua(bg, lsx_map=None) -> list[str]` thêm 3 mã mới vào danh sách trả về: `"khac_giay"`, `"buoc_chung_thieu_thanh_vien"`, `"thieu_buoc_chung_tren_giay"`. Task 5 (FE) tiêu thụ đúng 3 chuỗi này.

Hiện trạng hàm `thieu_cua` (đọc để biết chỗ chèn — KHÔNG xoá gì trong đoạn này):

```python
    def thieu_cua(self, bg: BaiGhep, lsx_map: dict[int, Lsx] | None = None) -> list[str]:
        lsx_map = lsx_map or self._lsx_map(bg)
        thieu: list[str] = []
        if len(bg.thanh_viens) < 2:
            thieu.append("thieu_thanh_vien")
        if not bg.giay_id:
            thieu.append("thieu_giay")
        if not (bg.kho_in_dai and bg.kho_in_rong):
            thieu.append("thieu_kho_in")
        if any(int(tv.so_con_tren_to or 0) <= 0 for tv in bg.thanh_viens):
            thieu.append("thieu_ups")
        if not self._buoc_chungs(bg):
            thieu.append("thieu_buoc_chung")
        so_to = self.tinh_so_to(bg, lsx_map)
        if so_to["so_to_tot"] <= 0:
            thieu.append("thieu_so_to")
        return thieu
```

- [ ] **Step 1: Viết test thất bại cho cả 3 gate**

```python
def test_thieu_cua_khac_giay(db, orders, lsx_svc, bg_svc, admin, customer):
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg = bg_svc.tao(lsx_ids=[a.id, b.id], actor=admin)
    lsx_map = bg_svc._lsx_map(bg)
    qc_b = dict(lsx_map[b.id].quy_cach_json or {})
    qc_b["giay_id"] = (qc_b.get("giay_id") or 0) + 9999
    lsx_map[b.id].quy_cach_json = qc_b
    db.commit()
    bg = bg_svc._get(bg.id)
    assert "khac_giay" in bg_svc.thieu_cua(bg)


def test_thieu_cua_buoc_chung_thieu_thanh_vien(db, orders, lsx_svc, bg_svc, admin, customer):
    a, b, c = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer, so_luong=3)
    bg = bg_svc.tao(lsx_ids=[a.id, b.id, c.id], actor=admin)
    created = bg_svc._get(bg.id)
    lsx_map = bg_svc._lsx_map(created)
    keys = [
        cd.step_key for l in (lsx_map[a.id], lsx_map[b.id])
        for cd in l.cong_doans if cd.loai_buoc == "may"
    ][:2]
    bg_svc.gop(bai_ghep_id=bg.id, step_keys=keys, actor=admin)
    bg = bg_svc._get(bg.id)
    assert "buoc_chung_thieu_thanh_vien" in bg_svc.thieu_cua(bg)


def test_thieu_cua_buoc_chung_tren_giay(db, orders, lsx_svc, bg_svc, admin, customer):
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg = bg_svc.tao(lsx_ids=[a.id, b.id], actor=admin)
    created = bg_svc._get(bg.id)
    lsx_map = bg_svc._lsx_map(created)
    ctp_keys = []
    for l in (lsx_map[a.id], lsx_map[b.id]):
        cd = l.cong_doans[0]
        cd.don_vi_vao = "bo_ban"
        cd.don_vi_ra = "bo_ban"
        ctp_keys.append(cd.step_key)
    db.commit()
    bg_svc.gop(bai_ghep_id=bg.id, step_keys=ctp_keys, actor=admin)
    bg = bg_svc._get(bg.id)
    assert "thieu_buoc_chung_tren_giay" in bg_svc.thieu_cua(bg)
```

Ghi chú test: `_hai_lsx_san_sang` (import từ `tests.test_bai_ghep_service`, đã có sẵn 2 LSX Sẵn sàng lập kế hoạch cùng đơn); test thứ 2 giả định fixture nhận `so_luong=3` trả về 3 LSX — nếu chữ ký thật không nhận tham số này, thay bằng gọi `_hai_lsx_san_sang` hai lần lấy đủ 3 LSX rồi `bg_svc.tao(lsx_ids=[a.id, b.id, c.id], ...)`. Test 3 gán đơn vị `"bo_ban"` (không có cờ trạm trong `TRAM_MAC_DINH`/`don_vi_do.tram_dong_giay`) cho MỌI bước chung của bài để đảm bảo `tren_dong_giay` trả `False` ở mọi bước — mô phỏng đúng "bài chỉ có bước CTP dùng chung, chưa gộp bước in".

- [ ] **Step 2: Chạy test, xác nhận FAIL**

```bash
cd backend && python -m pytest tests/test_bai_ghep_service.py -k "thieu_cua_khac_giay or thieu_cua_buoc_chung_thieu_thanh_vien or thieu_cua_buoc_chung_tren_giay" -v
```
Expected: FAIL (assertion `"khac_giay" in [...]` sai vì `thieu_cua` chưa sinh mã này).

- [ ] **Step 3: Thêm 3 gate vào `thieu_cua`**

```python
    def thieu_cua(self, bg: BaiGhep, lsx_map: dict[int, Lsx] | None = None) -> list[str]:
        lsx_map = lsx_map or self._lsx_map(bg)
        thieu: list[str] = []
        if len(bg.thanh_viens) < 2:
            thieu.append("thieu_thanh_vien")
        if not bg.giay_id:
            thieu.append("thieu_giay")
        if not (bg.kho_in_dai and bg.kho_in_rong):
            thieu.append("thieu_kho_in")
        if any(int(tv.so_con_tren_to or 0) <= 0 for tv in bg.thanh_viens):
            thieu.append("thieu_ups")
        # Giấy của bài PHẢI khớp giấy đang khai ở mỗi thành viên — bài ghép in CHUNG một tờ nên
        # giấy lệch là dữ liệu cũ/nhập nhầm, không phải "chọn giấy khác cho vui".
        giay_khac_tv = {
            gid for tv in bg.thanh_viens if tv.lsx_id in lsx_map
            and (gid := (lsx_map[tv.lsx_id].quy_cach_json or {}).get("giay_id")) is not None
        }
        if bg.giay_id and giay_khac_tv and any(gid != bg.giay_id for gid in giay_khac_tv):
            thieu.append("khac_giay")
        chungs = self._buoc_chungs(bg)
        if not chungs:
            thieu.append("thieu_buoc_chung")
        else:
            # Mỗi bước dùng chung phải phủ ĐỦ mọi thành viên đang có trong bài — thêm thành viên
            # sau khi đã gộp mà quên gộp bước của người mới thì lượt chung tính hao/kẽm THIẾU một
            # lệnh trong im lặng.
            lsx_ids_all = {tv.lsx_id for tv in bg.thanh_viens}
            if any({m.lsx_id for m in c.thanh_phans} != lsx_ids_all for c in chungs):
                thieu.append("buoc_chung_thieu_thanh_vien")
            # ÍT NHẤT một bước dùng chung phải nằm TRÊN DÒNG GIẤY (đếm được số tờ) — bài chỉ gộp
            # bước CTP/ghi kẽm (không đụng dòng giấy) thì chưa có "điểm toả" nào để tính, và số tờ
            # cả bài vẫn = 0 (xem gate `thieu_so_to` dưới).
            tram = self._tram()
            if not any(tren_dong_giay(c.don_vi_vao, c.don_vi_ra, tram, nhom=c.nhom) for c in chungs):
                thieu.append("thieu_buoc_chung_tren_giay")
        so_to = self.tinh_so_to(bg, lsx_map)
        if so_to["so_to_tot"] <= 0:
            thieu.append("thieu_so_to")
        return thieu
```

- [ ] **Step 4: Chạy lại test, xác nhận PASS**

```bash
cd backend && python -m pytest tests/test_bai_ghep_service.py -k "thieu_cua" -v
```
Expected: PASS toàn bộ (kể cả các test `thieu_cua` cũ đã có từ trước — không được vỡ).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/bai_ghep_service.py backend/tests/test_bai_ghep_service.py
git commit -m "Bài ghép: thêm gate khác giấy, bước chung thiếu thành viên, bước chung phải trên dòng giấy"
```

---

### Task 2: Gate cứng — vượt số con/tờ tối đa · vượt diện tích tờ

**Files:**
- Modify: `backend/app/services/bai_ghep_service.py` (tiếp `thieu_cua`, ngay sau khối `so_to` từ Task 1)
- Test: `backend/tests/test_bai_ghep_service.py`

**Interfaces:**
- Consumes: `self._con_toi_da(lsx, bg) -> int` (có sẵn, L1090+), `self.tinh_so_to(bg, lsx_map) -> dict` với key `"fill_pct": float | None` (có sẵn, ĐÃ tính, chỉ chưa được gate dùng tới).
- Produces: 2 mã mới trong `thieu_cua()`: `"vuot_con_toi_da"`, `"vuot_dien_tich"`.

- [ ] **Step 1: Viết test thất bại**

```python
def test_thieu_cua_vuot_con_toi_da(db, orders, lsx_svc, bg_svc, admin, customer):
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg = bg_svc.tao(lsx_ids=[a.id, b.id], actor=admin)
    tv = next(t for t in bg.thanh_viens if t.lsx_id == a.id)
    tv.so_con_tren_to = 9999  # vượt xa khả năng khổ tờ ghép thật
    db.commit()
    bg = bg_svc._get(bg.id)
    assert "vuot_con_toi_da" in bg_svc.thieu_cua(bg)


def test_thieu_cua_vuot_dien_tich(db, orders, lsx_svc, bg_svc, admin, customer):
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg = bg_svc.tao(lsx_ids=[a.id, b.id], actor=admin)
    bg.kho_in_dai = 1
    bg.kho_in_rong = 1  # tờ bé tí — tổng diện tích thành phẩm chắc chắn vượt 100%
    db.commit()
    bg = bg_svc._get(bg.id)
    assert "vuot_dien_tich" in bg_svc.thieu_cua(bg)
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

```bash
cd backend && python -m pytest tests/test_bai_ghep_service.py -k "vuot_con_toi_da or vuot_dien_tich" -v
```
Expected: FAIL.

- [ ] **Step 3: Thêm 2 gate, nối tiếp `so_to` đã tính ở Task 1 (không gọi `tinh_so_to` lần hai)**

```python
        so_to = self.tinh_so_to(bg, lsx_map)
        if so_to["so_to_tot"] <= 0:
            thieu.append("thieu_so_to")
        if any(
            (con := int(tv.so_con_tren_to or 0)) > 0
            and (cap := self._con_toi_da(lsx_map.get(tv.lsx_id), bg)) > 0
            and con > cap
            for tv in bg.thanh_viens
        ):
            thieu.append("vuot_con_toi_da")
        fill_pct = so_to.get("fill_pct")
        if fill_pct is not None and fill_pct > 100:
            thieu.append("vuot_dien_tich")
        return thieu
```

- [ ] **Step 4: Chạy lại test, xác nhận PASS**

```bash
cd backend && python -m pytest tests/test_bai_ghep_service.py -k "thieu_cua" -v
```
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/bai_ghep_service.py backend/tests/test_bai_ghep_service.py
git commit -m "Bài ghép: thêm gate vượt số con tối đa và vượt diện tích tờ"
```

---

### Task 3: `gop()` — chặn gộp khác đơn vị vào/ra hoặc khác kiểu in

**Files:**
- Modify: `backend/app/services/bai_ghep_service.py:731-736` (hàm `gop`)
- Test: `backend/tests/test_bai_ghep_2_service.py`

**Interfaces:**
- Consumes: `theo_key[k] -> tuple[LsxCongDoan, Lsx]` (có sẵn trong `gop()`), `Lsx.quy_cach_json: dict | None` (có `"quy_cach_in"`).
- Produces: `gop()` raise `BaiGhepValidationError` sớm hơn khi bước chọn gộp lệch `(don_vi_vao, don_vi_ra)` hoặc lệch `quy_cach_in` — không đổi chữ ký, không đổi hành vi khi dữ liệu hợp lệ.

Hiện trạng đoạn cần sửa:

```python
        cds = [theo_key[k][0] for k in keys]
        if len({cd.cong_doan_id for cd in cds}) != 1 or cds[0].cong_doan_id is None:
            raise BaiGhepValidationError("Chỉ gộp được các bước CÙNG một công đoạn")
        lsx_ids = [theo_key[k][1].id for k in keys]
        if len(set(lsx_ids)) != len(lsx_ids):
            raise BaiGhepValidationError("Mỗi lệnh chỉ góp một bước vào một lượt chạy chung")
```

- [ ] **Step 1: Viết test thất bại**

```python
def test_gop_chan_khac_don_vi_vao_ra(db, orders, lsx_svc, admin, customer):
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg_svc = _bg2_svc(db)
    bg = bg_svc.tao(lsx_ids=[a.id, b.id], actor=admin)
    created = bg_svc._get(bg.id)
    lsx_map = bg_svc._lsx_map(created)
    cd_a = next(cd for cd in lsx_map[a.id].cong_doans if cd.loai_buoc == "may")
    cd_b = next(cd for cd in lsx_map[b.id].cong_doans if cd.cong_doan_id == cd_a.cong_doan_id)
    cd_b.don_vi_ra = (cd_a.don_vi_ra or "to") + "_khac"
    db.commit()
    with pytest.raises(BaiGhepValidationError, match="CÙNG đơn vị vào/ra"):
        bg_svc.gop(bai_ghep_id=bg.id, step_keys=[cd_a.step_key, cd_b.step_key], actor=admin)


def test_gop_chan_khac_kieu_in(db, orders, lsx_svc, admin, customer):
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg_svc = _bg2_svc(db)
    bg = bg_svc.tao(lsx_ids=[a.id, b.id], actor=admin)
    created = bg_svc._get(bg.id)
    lsx_map = bg_svc._lsx_map(created)
    cd_a = next(cd for cd in lsx_map[a.id].cong_doans if cd.loai_buoc == "may")
    cd_b = next(cd for cd in lsx_map[b.id].cong_doans if cd.cong_doan_id == cd_a.cong_doan_id)
    lsx_map[a.id].quy_cach_json = {**(lsx_map[a.id].quy_cach_json or {}), "quy_cach_in": "mot_mat"}
    lsx_map[b.id].quy_cach_json = {**(lsx_map[b.id].quy_cach_json or {}), "quy_cach_in": "tu_tro"}
    db.commit()
    with pytest.raises(BaiGhepValidationError, match="CÙNG kiểu in"):
        bg_svc.gop(bai_ghep_id=bg.id, step_keys=[cd_a.step_key, cd_b.step_key], actor=admin)
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

```bash
cd backend && python -m pytest tests/test_bai_ghep_2_service.py -k "gop_chan_khac" -v
```
Expected: FAIL (không raise, hoặc raise message khác không khớp `match`).

- [ ] **Step 3: Sửa `gop()`**

```python
        cds = [theo_key[k][0] for k in keys]
        if len({cd.cong_doan_id for cd in cds}) != 1 or cds[0].cong_doan_id is None:
            raise BaiGhepValidationError("Chỉ gộp được các bước CÙNG một công đoạn")
        if len({(cd.don_vi_vao, cd.don_vi_ra) for cd in cds}) != 1:
            raise BaiGhepValidationError("Các bước chọn gộp phải CÙNG đơn vị vào/ra")
        lsx_ids = [theo_key[k][1].id for k in keys]
        kieu_ins = {
            str((theo_key[k][1].quy_cach_json or {}).get("quy_cach_in") or "")
            for k in keys
        }
        if len(kieu_ins) != 1:
            raise BaiGhepValidationError("Các lệnh chọn gộp phải CÙNG kiểu in (một mặt/tự trở/trở nhíp)")
        if len(set(lsx_ids)) != len(lsx_ids):
            raise BaiGhepValidationError("Mỗi lệnh chỉ góp một bước vào một lượt chạy chung")
```

- [ ] **Step 4: Chạy lại test, xác nhận PASS — và chạy thêm test `gop` cũ để chắc không vỡ luồng hợp lệ**

```bash
cd backend && python -m pytest tests/test_bai_ghep_2_service.py -v
```
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/bai_ghep_service.py backend/tests/test_bai_ghep_2_service.py
git commit -m "Bài ghép: chặn gộp bước khác đơn vị vào/ra hoặc khác kiểu in"
```

---

### Task 4: `_kieu_in_bai()` — helper dùng chung, sửa `muc_gop()` đoán nhầm kiểu in

**Files:**
- Modify: `backend/app/services/bai_ghep_service.py:1713-1741` (hàm `muc_gop`), `:1998-2016` (đoạn `kieu_in` trong `detail_dict`)
- Test: `backend/tests/test_bai_ghep_2_service.py`

**Interfaces:**
- Produces: `BaiGhepService._kieu_in_bai(bg: BaiGhep, lsx_map: dict[int, Lsx]) -> list[str]` — tập `quy_cach_in` (sắp xếp) đang khai trên các thành viên. `muc_gop()` trả `{}` (rỗng, không đoán) khi tập này khác đúng 1 phần tử — sau Task 3, một bài đã "Sẵn sàng" (đã qua gate gộp) LUÔN có đúng 1 kiểu in cho các bước đã gộp, nhưng thành viên MỚI THÊM chưa gộp bước in vẫn có thể tạo ra tập ≥2 phần tử trước khi gộp xong.

- [ ] **Step 1: Viết test thất bại — `muc_gop` không được lấy kiểu in của "thành viên đầu tiên tìm thấy" khi có ≥2 kiểu**

```python
def test_muc_gop_rong_khi_lech_kieu_in(db, orders, lsx_svc, admin, customer):
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg_svc = _bg2_svc(db)
    bg = bg_svc.tao(lsx_ids=[a.id, b.id], actor=admin)
    created = bg_svc._get(bg.id)
    lsx_map = bg_svc._lsx_map(created)
    lsx_map[a.id].quy_cach_json = {**(lsx_map[a.id].quy_cach_json or {}), "quy_cach_in": "mot_mat"}
    lsx_map[b.id].quy_cach_json = {**(lsx_map[b.id].quy_cach_json or {}), "quy_cach_in": "tu_tro"}
    db.commit()
    created = bg_svc._get(bg.id)
    lsx_map = bg_svc._lsx_map(created)
    assert bg_svc.muc_gop(created, lsx_map) == {}
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

```bash
cd backend && python -m pytest tests/test_bai_ghep_2_service.py -k "muc_gop_rong_khi_lech" -v
```
Expected: FAIL (hiện `muc_gop` vẫn trả về số kẽm tính theo kiểu in của thành viên đầu tiên tìm thấy trong `bg.thanh_viens`, không trả `{}`).

- [ ] **Step 3: Trích `_kieu_in_bai`, sửa `muc_gop()` và `detail_dict()`**

Thêm helper (đặt ngay trước `muc_gop`, cùng class `BaiGhepService`):

```python
    def _kieu_in_bai(self, bg: BaiGhep, lsx_map: dict[int, Lsx]) -> list[str]:
        """Tập `quy_cach_in` đang khai trên các thành viên — rỗng hoặc nhiều hơn 1 phần tử nghĩa
        là bài CHƯA có một kiểu in thống nhất để tính kẽm gộp/chờ kỹ thuật theo kiểu in."""
        return sorted({
            k for tv in bg.thanh_viens
            if (k := ((lsx_map[tv.lsx_id].quy_cach_json or {}) if tv.lsx_id in lsx_map else {})
                .get("quy_cach_in"))
        })
```

Sửa `muc_gop()`:

```python
        qc = self._qc_bai(bg, lsx_map)
        a, b = tap_muc(qc.get("muc_a")), tap_muc(qc.get("muc_b"))
        if not a and not b:
            a, b = tap_muc_tu_so(qc.get("so_mau_a"), qc.get("so_mau_b"), 0)
        if not a and not b:
            return {}
        kieu_in = self._kieu_in_bai(bg, lsx_map)
        if len(kieu_in) != 1:
            return {}
        sa, sb, sp = so_mau_dan_xuat(a, b)
        return {"so_mau_a": sa, "so_mau_b": sb, "so_mau_pha": sp,
                "so_kem": so_kem_moi_tay(a, b, kieu_in[0])}
```

Sửa `detail_dict()` (thay đoạn tính `kieu_in` cục bộ bằng gọi helper, DRY):

```python
        qc_bai = self._qc_bai(bg, lsx_map)
        muc = self.muc_gop(bg, lsx_map)
        kieu_in = self._kieu_in_bai(bg, lsx_map)
```

- [ ] **Step 4: Chạy lại test — và toàn bộ file để chắc `detail_dict`/`muc_gop` cũ không vỡ**

```bash
cd backend && python -m pytest tests/test_bai_ghep_2_service.py tests/test_bai_ghep_service.py -v
```
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/bai_ghep_service.py backend/tests/test_bai_ghep_2_service.py
git commit -m "Bài ghép: sửa muc_gop đoán nhầm kiểu in, gom logic vào _kieu_in_bai dùng chung"
```

---

### Task 5: FE — 5 nhãn lỗi mới trong `BAI_GHEP_THIEU_LABELS`

**Files:**
- Modify: `frontend/src/api/client.ts:525-552` (map `BAI_GHEP_THIEU_LABELS`)

**Interfaces:**
- Consumes: 5 mã mới sinh ra ở Task 1–2: `"khac_giay"`, `"buoc_chung_thieu_thanh_vien"`, `"thieu_buoc_chung_tren_giay"`, `"vuot_con_toi_da"`, `"vuot_dien_tich"`.
- Produces: không đổi kiểu `Record<string, string>` — chỉ thêm entry, màn Bài ghép đọc `BAI_GHEP_THIEU_LABELS[code] ?? code` nên thiếu entry không vỡ, chỉ hiện mã thô.

- [ ] **Step 1: Đọc đúng khối hiện tại rồi thêm 5 dòng**

Đọc `frontend/src/api/client.ts:525-552` trước khi sửa để lấy đúng format hiện có (indent, dấu phẩy). Thêm ngay sau các entry hiện có trong `BAI_GHEP_THIEU_LABELS`, TRƯỚC dòng đóng `};`:

```typescript
  khac_giay: "Giấy của bài lệch giấy đang khai ở một thành viên",
  buoc_chung_thieu_thanh_vien: "Bước dùng chung chưa gộp đủ mọi thành viên trong bài",
  thieu_buoc_chung_tren_giay: "Chưa có bước dùng chung nào nằm trên dòng giấy (điểm toả)",
  vuot_con_toi_da: "Số con/tờ vượt khả năng khổ tờ ghép",
  vuot_dien_tich: "Diện tích thành phẩm vượt quá tờ ghép",
```

- [ ] **Step 2: Kiểm type — không có test runtime cho map hằng số**

```bash
cd frontend && npx tsc --noEmit
```
Expected: 0 lỗi liên quan tới `client.ts`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "Bài ghép FE: thêm nhãn cho 5 mã lỗi thiếu/vượt mới"
```

---

### Task 6: Migration `0243` + model — cột `nguon_so_luong` trên `BaiGhepCongDoanVatTu`

**Files:**
- Modify: `backend/app/models/bai_ghep_cong_doan.py:168-187` (class `BaiGhepCongDoanVatTu`)
- Modify: `backend/app/db_migrations.py` (thêm hàm migration + append vào cuối file, sau dòng `MIGRATIONS.append(("0242_doi_ten_cot_markup", ...))`)
- Modify: `docs/DB_SCHEMA.md` (mục bảng `bai_ghep_cong_doan_vat_tu`)
- Test: `backend/tests/test_bai_ghep_service.py`

**Interfaces:**
- Produces: hằng số `NGUON_SL_DINH_MUC = "dinh_muc"`, `NGUON_SL_THU_CONG = "thu_cong"` (module `app.models.bai_ghep_cong_doan`); cột `BaiGhepCongDoanVatTu.nguon_so_luong: Mapped[str]` NOT NULL, mặc định `"thu_cong"`. Task 7 dùng hai hằng số này.

- [ ] **Step 1: Viết test thất bại (cột/hằng số chưa tồn tại → ImportError hoặc AttributeError)**

```python
def test_vat_tu_chung_mac_dinh_thu_cong(db, orders, lsx_svc, bg_svc, admin, customer):
    from app.models.bai_ghep_cong_doan import NGUON_SL_THU_CONG, BaiGhepCongDoanVatTu
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg = bg_svc.tao(lsx_ids=[a.id, b.id], actor=admin)
    created = bg_svc._get(bg.id)
    lsx_map = bg_svc._lsx_map(created)
    cd_a = next(cd for cd in lsx_map[a.id].cong_doans if cd.loai_buoc == "may")
    cd_b = next(cd for cd in lsx_map[b.id].cong_doans if cd.cong_doan_id == cd_a.cong_doan_id)
    bg_svc.gop(bai_ghep_id=bg.id, step_keys=[cd_a.step_key, cd_b.step_key], actor=admin)
    chung = bg_svc._buoc_chungs(bg_svc._get(bg.id))[0]
    vt = BaiGhepCongDoanVatTu(
        bai_ghep_cong_doan_id=chung.id, vat_tu_id=1,
        vat_tu_ma_snapshot="MUC-01", vat_tu_ten_snapshot="Mực đen", don_vi_snapshot="kg",
        so_luong=1.5, thu_tu=0,
    )
    db.add(vt)
    db.commit()
    db.refresh(vt)
    assert vt.nguon_so_luong == NGUON_SL_THU_CONG
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

```bash
cd backend && python -m pytest tests/test_bai_ghep_service.py -k "vat_tu_chung_mac_dinh_thu_cong" -v
```
Expected: FAIL với `ImportError: cannot import name 'NGUON_SL_THU_CONG'`.

- [ ] **Step 3: Thêm hằng số + cột vào model**

Ở đầu `backend/app/models/bai_ghep_cong_doan.py` (cạnh các hằng số module khác nếu có, hoặc ngay trước class `BaiGhepCongDoanVatTu` nếu file chưa có khối hằng số riêng):

```python
NGUON_SL_DINH_MUC = "dinh_muc"   # số lượng do server TỰ TÍNH lại theo công thức mỗi khi bài đổi số
NGUON_SL_THU_CONG = "thu_cong"   # người khai tay — không bị ghi đè khi bài đổi số
```

Sửa class:

```python
class BaiGhepCongDoanVatTu(Base):
    """Vật tư của bước chung — mực, kẽm, màng… dùng cho cả lượt, không của riêng lệnh nào."""

    __tablename__ = "bai_ghep_cong_doan_vat_tu"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bai_ghep_cong_doan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bai_ghep_cong_doan.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Mirror ĐÚNG `LsxCongDoanVatTu` (kể cả kiểu snapshot) để drawer dùng lại không phải rẽ nhánh.
    vat_tu_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    vat_tu_ma_snapshot: Mapped[str] = mapped_column(String(30), nullable=False)
    vat_tu_ten_snapshot: Mapped[str] = mapped_column(String(150), nullable=False)
    don_vi_snapshot: Mapped[str] = mapped_column(String(16), nullable=False)
    so_luong: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    thu_tu: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # `dinh_muc` = server tự tính lại theo công thức mỗi khi bài đổi số lượng/quy cách; `thu_cong` =
    # người khai tay, GIỮ NGUYÊN qua mọi lần tính lại (xem `_ap_dinh_muc_vat_tu`).
    nguon_so_luong: Mapped[str] = mapped_column(
        String(16), nullable=False, default=NGUON_SL_THU_CONG, server_default=NGUON_SL_THU_CONG
    )

    buoc_chung: Mapped["BaiGhepCongDoan"] = relationship(
        "BaiGhepCongDoan", back_populates="vat_tus"
    )
```

- [ ] **Step 4: Thêm migration `0243` vào cuối `db_migrations.py`**

Nối tiếp ngay sau `MIGRATIONS.append(("0242_doi_ten_cot_markup", _migrate_doi_ten_cot_markup))`:

```python
def _migrate_bai_ghep_vat_tu_nguon_so_luong(db: Session) -> None:
    """Bài ghép: thêm `bai_ghep_cong_doan_vat_tu.nguon_so_luong` — phân biệt dòng vật tư SERVER tự
    tính lại theo công thức (`dinh_muc`) với dòng người khai TAY (`thu_cong`, giữ nguyên qua mọi
    lần tính lại). NOT NULL DEFAULT 'thu_cong': dòng cũ coi như đã khai tay — an toàn hơn coi nhầm
    là định mức rồi tự ý ghi đè số người đã chốt. No-op DB fresh / bảng chưa có / cột đã có."""
    insp = inspect(db.get_bind())
    if "bai_ghep_cong_doan_vat_tu" not in insp.get_table_names():
        return
    if "nguon_so_luong" not in _existing_columns(insp, "bai_ghep_cong_doan_vat_tu"):
        db.execute(text(
            "ALTER TABLE bai_ghep_cong_doan_vat_tu "
            "ADD COLUMN nguon_so_luong VARCHAR(16) NOT NULL DEFAULT 'thu_cong'"
        ))
    db.commit()


MIGRATIONS.append(("0243_bai_ghep_vat_tu_nguon_so_luong", _migrate_bai_ghep_vat_tu_nguon_so_luong))
```

- [ ] **Step 5: Cập nhật `docs/DB_SCHEMA.md`**

Tìm mục bảng `bai_ghep_cong_doan_vat_tu`, thêm dòng cột mới vào đúng bảng liệt kê cột (theo đúng format Markdown các cột khác đang dùng ở đó — copy style một dòng liền kề, ví dụ dòng `thu_tu`), nội dung dòng mới:

```
| `nguon_so_luong` | VARCHAR(16) NOT NULL DEFAULT 'thu_cong' | Nguồn số lượng: `dinh_muc` (server tự tính lại) hoặc `thu_cong` (người khai tay, giữ nguyên khi tính lại). |
```

- [ ] **Step 6: Chạy lại test + guard test DB_SCHEMA**

```bash
cd backend && python -m pytest tests/test_bai_ghep_service.py -k "vat_tu_chung_mac_dinh_thu_cong" backend/tests/test_danh_muc_http_contract.py -v
```
Expected: PASS. (Nếu guard test DB_SCHEMA nằm ở file khác, tìm bằng `pytest -k db_schema -v` và chạy đúng file đó thay vì đoán tên.)

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/bai_ghep_cong_doan.py backend/app/db_migrations.py docs/DB_SCHEMA.md backend/tests/test_bai_ghep_service.py
git commit -m "Bài ghép: thêm cột nguon_so_luong cho vật tư bước chung (migration 0243)"
```

---

### Task 7: `_thay_vat_tu_chung()` nhận `nguon_so_luong` + `_ap_dinh_muc_vat_tu()` tự tính lại dòng định mức

**Files:**
- Modify: `backend/app/services/bai_ghep_service.py:934-964` (hàm `_thay_vat_tu_chung`)
- Modify: `backend/app/services/bai_ghep_service.py` (cuối hàm `_ap_so_luong_chung`, ~L1513-1519 — sau khi `qc_bien` đã tính và cả hai vòng lặp gán `so_luong_vao/ra` đã chạy xong)
- Test: `backend/tests/test_bai_ghep_service.py`

**Interfaces:**
- Consumes: `NGUON_SL_DINH_MUC`, `NGUON_SL_THU_CONG` (Task 6), `self._lsx_svc()._goi_y_luong_vat_tu(buoc, quy_cach) -> list[dict{vat_tu_id, so_luong, dien_giai, ly_do}]` (có sẵn, `lsx_service.py:606+`).
- Produces: `_thay_vat_tu_chung(chung, vat_tus)` nay đọc thêm khoá `"nguon_so_luong"` mỗi phần tử `vat_tus` (mặc định `thu_cong` nếu thiếu — payload cũ/FE chưa gửi vẫn hợp lệ); `_ap_dinh_muc_vat_tu(chung, qc_bien) -> None` — hàm mới, tự sinh khi `_ap_so_luong_chung` chạy (gộp/tách/đổi khổ/đổi số con đều đi qua `_tinh_lai` → `_ap_so_luong_chung`).

- [ ] **Step 1: Viết test thất bại — lưu `nguon_so_luong` qua `_thay_vat_tu_chung`, và dòng `thu_cong` không bị `_ap_dinh_muc_vat_tu` ghi đè khi đổi số con/tờ**

```python
def test_thay_vat_tu_chung_luu_nguon_so_luong(db, orders, lsx_svc, bg_svc, admin, customer):
    from app.models.bai_ghep_cong_doan import NGUON_SL_DINH_MUC, NGUON_SL_THU_CONG
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg = bg_svc.tao(lsx_ids=[a.id, b.id], actor=admin)
    created = bg_svc._get(bg.id)
    lsx_map = bg_svc._lsx_map(created)
    cd_a = next(cd for cd in lsx_map[a.id].cong_doans if cd.loai_buoc == "may")
    cd_b = next(cd for cd in lsx_map[b.id].cong_doans if cd.cong_doan_id == cd_a.cong_doan_id)
    bg_svc.gop(bai_ghep_id=bg.id, step_keys=[cd_a.step_key, cd_b.step_key], actor=admin)
    chung = bg_svc._buoc_chungs(bg_svc._get(bg.id))[0]

    bg_svc._thay_vat_tu_chung(chung, [
        {"vat_tu_id": 1, "so_luong": 2.0, "nguon_so_luong": NGUON_SL_THU_CONG},
        {"vat_tu_id": 2, "so_luong": 3.0, "nguon_so_luong": NGUON_SL_DINH_MUC},
    ])
    db.commit()

    by_id = {v.vat_tu_id: v for v in chung.vat_tus}
    assert by_id[1].nguon_so_luong == NGUON_SL_THU_CONG
    assert by_id[2].nguon_so_luong == NGUON_SL_DINH_MUC


def test_ap_dinh_muc_giu_nguyen_dong_thu_cong(db, orders, lsx_svc, bg_svc, admin, customer):
    from app.models.bai_ghep_cong_doan import NGUON_SL_THU_CONG
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    bg = bg_svc.tao(lsx_ids=[a.id, b.id], actor=admin)
    created = bg_svc._get(bg.id)
    lsx_map = bg_svc._lsx_map(created)
    cd_a = next(cd for cd in lsx_map[a.id].cong_doans if cd.loai_buoc == "may")
    cd_b = next(cd for cd in lsx_map[b.id].cong_doans if cd.cong_doan_id == cd_a.cong_doan_id)
    bg_svc.gop(bai_ghep_id=bg.id, step_keys=[cd_a.step_key, cd_b.step_key], actor=admin)
    chung = bg_svc._buoc_chungs(bg_svc._get(bg.id))[0]
    bg_svc._thay_vat_tu_chung(chung, [
        {"vat_tu_id": 1, "so_luong": 777.0, "nguon_so_luong": NGUON_SL_THU_CONG},
    ])
    db.commit()

    bg = bg_svc._get(bg.id)
    tv = next(t for t in bg.thanh_viens if t.lsx_id == a.id)
    tv.so_con_tren_to = int(tv.so_con_tren_to or 1) + 1  # đổi số con → kích _ap_so_luong_chung
    db.commit()
    bg_svc._tinh_lai(bg)
    db.commit()

    chung2 = bg_svc._buoc_chungs(bg_svc._get(bg.id))[0]
    vt = next(v for v in chung2.vat_tus if v.vat_tu_id == 1)
    assert float(vt.so_luong) == 777.0  # dòng thủ công KHÔNG bị tính lại đè số
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

```bash
cd backend && python -m pytest tests/test_bai_ghep_service.py -k "thay_vat_tu_chung_luu_nguon_so_luong or ap_dinh_muc_giu_nguyen" -v
```
Expected: FAIL (`nguon_so_luong` chưa được `_thay_vat_tu_chung` gán — luôn ra giá trị mặc định `server_default`, hai test đều fail ở assertion đầu tiên khác nhau).

- [ ] **Step 3: Sửa `_thay_vat_tu_chung`, thêm `_ap_dinh_muc_vat_tu`, gọi từ cuối `_ap_so_luong_chung`**

```python
    def _thay_vat_tu_chung(self, chung: BaiGhepCongDoan, vat_tus: list[dict]) -> None:
        """Thay toàn bộ vật tư của bước chung. Snapshot mã/tên/đơn vị để đổi danh mục không làm
        đổi kế hoạch đã chốt — cùng luật với `lsx_cong_doan_vat_tu`."""
        ids = [int(v.get("vat_tu_id") or 0) for v in vat_tus]
        if len(ids) != len(set(ids)):
            raise BaiGhepValidationError("Một vật tư không được chọn trùng trong cùng công đoạn")
        mats = {
            v.id: v for v in self.db.execute(
                select(VatTuInAn).where(VatTuInAn.id.in_(ids))
            ).scalars()
        } if ids else {}
        # Vật tư đã nằm trên bài ghép từ trước thì giữ lại được, kể cả khi danh mục đã ngừng nó —
        # chặn cả hai kiểu thì bài ghép cũ không lưu lại được dù chỉ sửa một con số khác.
        dang_co = {int(v.vat_tu_id) for v in chung.vat_tus if v.vat_tu_id}
        chung.vat_tus[:] = []
        for i, v in enumerate(vat_tus):
            mat = mats.get(int(v.get("vat_tu_id") or 0))
            if mat is None:
                raise BaiGhepValidationError("Vật tư không tồn tại")
            if not mat.active and mat.id not in dang_co:
                raise BaiGhepValidationError(
                    f"Vật tư “{mat.ten}” đã ngừng dùng — chọn vật tư khác")
            nguon_so_luong = str(v.get("nguon_so_luong") or NGUON_SL_THU_CONG)
            if nguon_so_luong not in (NGUON_SL_DINH_MUC, NGUON_SL_THU_CONG):
                raise BaiGhepValidationError("Nguồn số lượng không hợp lệ")
            chung.vat_tus.append(BaiGhepCongDoanVatTu(
                # `don_vi_gia`, KHÔNG phải `don_vi` — `VatTuInAn` không có cột nào tên `don_vi`.
                # Gõ nhầm ở đây là AttributeError lúc chạy, 500 ngay khi bấm Lưu; bước lệnh
                # (`lsx_service`) vẫn luôn dùng đúng `don_vi_gia`.
                # `or ""`: đơn vị gốc của vật tư có thể CHƯA KHAI (cột nullable từ 2026-08-08), mà
                # cột snapshot này NOT NULL — không chặn thì IntegrityError 500 lúc bấm Lưu.
                vat_tu_id=mat.id, vat_tu_ma_snapshot=mat.ma, vat_tu_ten_snapshot=mat.ten,
                don_vi_snapshot=mat.don_vi_gia or "", so_luong=_f(v.get("so_luong")), thu_tu=i,
                nguon_so_luong=nguon_so_luong,
            ))

    def _ap_dinh_muc_vat_tu(self, chung: BaiGhepCongDoan, qc_bien: dict) -> None:
        """Tính lại SỐ LƯỢNG các dòng vật tư `dinh_muc` của bước chung theo quy cách MỚI NHẤT.

        Dòng `thu_cong` giữ nguyên — người đã gõ tay thì không bị bài ghép tính lại đè số mỗi khi
        đổi số con/khổ tờ (khớp `_ghim_khoan_chung` — cùng nguyên tắc "không đè cái người vừa gõ")."""
        if not chung.vat_tus:
            return
        goi_y = {
            g["vat_tu_id"]: g["so_luong"]
            for g in self._lsx_svc()._goi_y_luong_vat_tu(chung, qc_bien)
        }
        for vt in chung.vat_tus:
            if vt.nguon_so_luong != NGUON_SL_DINH_MUC:
                continue
            moi = goi_y.get(vt.vat_tu_id)
            if moi is not None:
                vt.so_luong = moi
```

Thêm import 2 hằng số ở đầu file (cùng dòng import `BaiGhepCongDoanVatTu` đã có từ `bai_ghep_cong_doan`):

```python
from ..models.bai_ghep_cong_doan import (
    BaiGhepCongDoan, BaiGhepCongDoanMap, BaiGhepCongDoanVatTu,
    NGUON_SL_DINH_MUC, NGUON_SL_THU_CONG,
)
```
(Điều chỉnh đúng theo import block thật đang có trong file — chỉ thêm 2 tên mới vào cùng dòng `from ..models.bai_ghep_cong_doan import (...)` đã tồn tại, không tạo thêm dòng import trùng.)

Cuối `_ap_so_luong_chung` (sau khi cả hai vòng lặp gán `so_luong_vao/ra` xong và `qc_bien` đã có trong scope):

```python
        for c in chungs:
            self._ap_dinh_muc_vat_tu(c, qc_bien)
```

- [ ] **Step 4: Chạy lại test, xác nhận PASS + chạy cả file để chắc không vỡ luồng vật tư cũ**

```bash
cd backend && python -m pytest tests/test_bai_ghep_service.py -v
```
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/bai_ghep_service.py backend/tests/test_bai_ghep_service.py
git commit -m "Bài ghép: giữ dòng vật tư thủ công, tự tính lại dòng định mức khi bài đổi số"
```

---

### Task 8: FE — badge "Tự tính"/"Đã sửa" theo `nguon_so_luong` server-persisted

**Files:**
- Modify: `frontend/src/api/client.ts:692` (interface field `vat_tus` của bước chung), `:772` (`BaiGhepBuocChungBody.vat_tus`), serialization phía backend `backend/app/services/bai_ghep_service.py:1660-1665`
- Modify: `frontend/src/pages/BaiGhepBuocChungForm.tsx:164-165` (khởi tạo `vtHienTai`/`datVatTu`), `:785-806` (nút "Đồng bộ tất cả"), `:830-901` (badge + nút "Dùng số này" + input tay), `:936` (thêm vật tư mới)

**Interfaces:**
- Consumes: `nguon_so_luong` từ Task 6/7 (cột DB) + Task 7 (`_thay_vat_tu_chung` đọc đúng khoá này từ payload).
- Produces: kiểu hàng vật tư ở FE mở rộng thành `{ vat_tu_id: number; so_luong: number; nguon_so_luong?: string }`; badge NGUỒN SỐ đọc từ `row.nguon_so_luong` (SERVER lưu) thay vì so khớp số hiện tại với gợi ý (heuristic cũ, không đáng tin vì không phân biệt được "trùng số tình cờ" với "chủ định theo công thức").

- [ ] **Step 1: Sửa backend serialize — trả kèm `nguon_so_luong`**

`backend/app/services/bai_ghep_service.py:1660-1665`, hiện tại:

```python
                "vat_tus": [
                    {"vat_tu_id": v.vat_tu_id, "ma": v.vat_tu_ma_snapshot,
                     "ten": v.vat_tu_ten_snapshot, "don_vi": v.don_vi_snapshot,
                     "so_luong": _f(v.so_luong)}
                    for v in c.vat_tus
                ],
```

Sửa thành:

```python
                "vat_tus": [
                    {"vat_tu_id": v.vat_tu_id, "ma": v.vat_tu_ma_snapshot,
                     "ten": v.vat_tu_ten_snapshot, "don_vi": v.don_vi_snapshot,
                     "so_luong": _f(v.so_luong), "nguon_so_luong": v.nguon_so_luong}
                    for v in c.vat_tus
                ],
```

- [ ] **Step 2: Sửa 2 interface TS trong `client.ts`**

`:692` (đọc), hiện tại:
```typescript
  vat_tus: { vat_tu_id: number; ma: string; ten: string; don_vi: string; so_luong: number }[];
```
Sửa thành:
```typescript
  vat_tus: { vat_tu_id: number; ma: string; ten: string; don_vi: string; so_luong: number;
             nguon_so_luong: string }[];
```

`:772` (ghi, `BaiGhepBuocChungBody`), hiện tại:
```typescript
  vat_tus?: { vat_tu_id: number; so_luong: number }[];
```
Sửa thành:
```typescript
  vat_tus?: { vat_tu_id: number; so_luong: number; nguon_so_luong?: string }[];
```

- [ ] **Step 3: Sửa `BaiGhepBuocChungForm.tsx` — khởi tạo, các nút, badge, ô nhập tay**

`:164-165`, hiện tại:
```typescript
  const vtHienTai = (f.vat_tus ?? g.vat_tus.map((v) => ({ vat_tu_id: v.vat_tu_id, so_luong: v.so_luong })));
  const datVatTu = (rows: { vat_tu_id: number; so_luong: number }[]) => setF({ ...f, vat_tus: rows });
```
Sửa thành:
```typescript
  const vtHienTai = (f.vat_tus ?? g.vat_tus.map((v) => (
    { vat_tu_id: v.vat_tu_id, so_luong: v.so_luong, nguon_so_luong: v.nguon_so_luong }
  )));
  const datVatTu = (rows: { vat_tu_id: number; so_luong: number; nguon_so_luong?: string }[]) =>
    setF({ ...f, vat_tus: rows });
```

`:785-806`, nút "Đồng bộ tất cả theo công thức" — set TẤT CẢ về `dinh_muc` (người bấm nút này là chủ định theo công thức):
```typescript
                        onClick={() => {
                          const next = vtHienTai.map((row) => {
                            const goiY = g.vat_tu_goi_y.find((x) => x.vat_tu_id === row.vat_tu_id);
                            return goiY?.so_luong != null
                              ? { ...row, so_luong: goiY.so_luong, nguon_so_luong: "dinh_muc" }
                              : row;
                          });
                          datVatTu(next);
                          const nextVtGo = { ...vtGo };
                          for (const row of next) {
                            nextVtGo[row.vat_tu_id] = String(row.so_luong);
                          }
                          setVtGo(nextVtGo);
                        }}
```

`:830-901`, thân vòng lặp render từng dòng — badge đọc từ `row.nguon_so_luong` thay vì `khop`; `khop`/`lech` GIỮ NGUYÊN (vẫn cần cho khối "Lệch: ... Dùng số này" — đó là tín hiệu "số hiện tại có đang khớp gợi ý MỚI NHẤT hay không", một khái niệm khác với "nguồn số lượng là gì"); nút "Dùng số này" set `nguon_so_luong: "dinh_muc"`; ô nhập tay set `nguon_so_luong: "thu_cong"`:

```typescript
                        const goiY = g.vat_tu_goi_y.find((x) => x.vat_tu_id === row.vat_tu_id);
                        const soMay = goiY?.so_luong ?? null;
                        const soLuu = Number(row.so_luong);
                        const khop = soMay !== null && Number.isFinite(soLuu) && Math.abs(soMay - soLuu) <= 0.0005;
                        const lech = soMay !== null && Number.isFinite(soLuu) && !khop;
                        const laDinhMuc = (row.nguon_so_luong ?? "thu_cong") === "dinh_muc";
```

(giữa khối `dienGiai`/nút "Dùng số này", đổi `onClick`):
```typescript
                                        onClick={() => {
                                          setVtGo({ ...vtGo, [row.vat_tu_id]: String(soMay) });
                                          const next = [...vtHienTai];
                                          next[i] = { ...row, so_luong: Number(soMay), nguon_so_luong: "dinh_muc" };
                                          datVatTu(next);
                                        }}
```

Badge (`NGUỒN SỐ`), thay điều kiện `khop` bằng `laDinhMuc`:
```typescript
                            <td className="khsx-vattu-td khsx-vattu-td--status">
                              <span className={`khsx-vattu-src-badge ${laDinhMuc ? "is-auto" : "is-manual"}`}>
                                {laDinhMuc ? "Tự tính" : "Đã sửa"}
                              </span>
                            </td>
```

Ô nhập tay (`onChange`), người gõ tay = chủ định ghi đè công thức:
```typescript
                                  onChange={(e) => {
                                    setVtGo({ ...vtGo, [row.vat_tu_id]: e.target.value });
                                    const next = [...vtHienTai];
                                    next[i] = { ...row, so_luong: Number(e.target.value) || 0, nguon_so_luong: "thu_cong" };
                                    datVatTu(next);
                                  }}
```

`:936`, thêm vật tư mới từ dropdown — có gợi ý thì coi là định mức (server đã gợi ý sẵn số này), không có gợi ý thì để thủ công (số 0 không phải "theo công thức"):
```typescript
                                datVatTu([...vtHienTai, {
                                  vat_tu_id: item.id, so_luong: goiYMoi?.so_luong ?? 0,
                                  nguon_so_luong: goiYMoi?.so_luong != null ? "dinh_muc" : "thu_cong",
                                }]);
```

- [ ] **Step 2 (kiểm type):**

```bash
cd frontend && npx tsc --noEmit
```
Expected: 0 lỗi ở `client.ts`/`BaiGhepBuocChungForm.tsx`.

- [ ] **Step 3: Xác minh bằng dev-browser (bắt buộc — đây là luồng UI, KHÔNG dùng API/curl thay bước nào)**

Mở màn Bài ghép 2 → một bài đã gộp ≥1 bước chung có vật tư → mở drawer bước chung → tab Vật tư:
1. Xác nhận badge hiện đúng "Tự tính"/"Đã sửa" khớp dữ liệu đã lưu (F5 lại trang để chắc đọc từ server, không phải state cũ trên máy).
2. Gõ tay một số khác vào ô số lượng của một dòng đang "Tự tính" → badge phải chuyển "Đã sửa" NGAY (trước khi bấm Lưu, phản ánh state cục bộ).
3. Bấm "Dùng số này" (nếu có dòng lệch) → badge dòng đó chuyển "Tự tính".
4. Bấm Lưu → tải lại drawer (đóng rồi mở lại) → badge phải GIỮ NGUYÊN đúng trạng thái vừa đặt (chứng minh đã lưu ở server, không phải chỉ tính lại trên máy).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/pages/BaiGhepBuocChungForm.tsx backend/app/services/bai_ghep_service.py
git commit -m "Bài ghép FE: badge nguồn số lượng đọc từ cờ server thay vì so khớp số hiện tại"
```

---

### Task 9: `snapshot.dung_diem_toa()` + wiring vào `release.py` + `SanXuatRepository.thanh_vien_so_con()`

**Files:**
- Modify: `backend/app/repositories/san_xuat_repo.py` (thêm method, đặt cạnh `bai_ghep_ids_cua_lsx`)
- Modify: `backend/app/services/san_xuat/snapshot.py` (thêm hàm `dung_diem_toa`, thêm import)
- Modify: `backend/app/services/san_xuat/release.py:26-30,80-83` (import + gọi)
- Test: `backend/tests/test_san_xuat_release.py`

**Interfaces:**
- Consumes: `repo.routing_steps(lsx_id) -> list[LsxCongDoan]` (có sẵn, sort theo `thu_tu, id`), `cv_by_step: dict[str, SanXuatCongViec]` (do `dung_cong_viec` trả), `tren_dong_giay`/`ban_do_tram` (từ `..dong_giay`).
- Produces: `SanXuatRepository.thanh_vien_so_con(bg_ids: set[int]) -> dict[int, int]` (lsx_id → số con/tờ); `dung_diem_toa(repo, *, goi, phien_ban_so, lsx_ids, bai_ghep_ids, nhom_by_lsx, cv_by_step) -> int` (số cạnh đã tạo) — ghi thẳng `SanXuatPhuThuoc` với `ty_le_ghep` = số con/tờ của LSX đích. Task 11 (`san_luong._toa_san_luong`) đọc lại các cạnh này qua `SanXuatSanLuongRepository.canh_toa_di_tu`.

- [ ] **Step 1: Viết test thất bại — release một bài ghép 2 LSX có bước riêng sau bước chung, kỳ vọng có đúng 1 cạnh `SanXuatPhuThuoc` mỗi LSX với `ty_le_ghep` = số con của LSX đó**

```python
def test_dung_diem_toa_sinh_canh_theo_so_con(db, orders, lsx_svc, bg_svc, admin, customer):
    from tests.test_xep_lich_van_de import _gop_in_va_san_sang
    a, b = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    _nha_cho(db, [a.id, b.id])
    bg = bg_svc.tao(lsx_ids=[a.id, b.id], actor=admin)
    _gop_in_va_san_sang(db, bg_svc, bg, admin)
    bg = bg_svc._get(bg.id)
    for tv in bg.thanh_viens:
        tv.so_con_tren_to = 8 if tv.lsx_id == a.id else 4
    db.commit()

    repo = SanXuatRepository(db)
    covered = repo.step_keys_da_ghep(bg.id)
    goi = release.phat_hanh(db, lsx_ids={a.id, b.id}, bai_ghep_ids={bg.id}, actor=admin)
    db.commit()

    cvs_a = [
        cv for cv in db.query(SanXuatCongViec).filter_by(goi_id=goi.id, lsx_id=a.id).all()
    ]
    cvs_b = [
        cv for cv in db.query(SanXuatCongViec).filter_by(goi_id=goi.id, lsx_id=b.id).all()
    ]
    assert cvs_a and cvs_b  # mỗi LSX còn ít nhất một bước RIÊNG sau bước chung
    canh_a = db.query(SanXuatPhuThuoc).filter(
        SanXuatPhuThuoc.dich_cong_viec_id.in_([cv.id for cv in cvs_a])
    ).all()
    canh_b = db.query(SanXuatPhuThuoc).filter(
        SanXuatPhuThuoc.dich_cong_viec_id.in_([cv.id for cv in cvs_b])
    ).all()
    assert len(canh_a) == 1 and float(canh_a[0].ty_le_ghep) == 8.0
    assert len(canh_b) == 1 and float(canh_b[0].ty_le_ghep) == 4.0
    nguon_ids = {c.nguon_cong_viec_id for c in canh_a + canh_b}
    assert len(nguon_ids) == 1  # cùng một công việc chung là điểm toả cho cả hai nhánh
    cv_nguon = db.get(SanXuatCongViec, next(iter(nguon_ids)))
    assert cv_nguon.bai_ghep_id == bg.id
```

Ghi chú: `_nha_cho`, `_gop_in_va_san_sang`, `_hai_lsx_san_sang` import từ `tests.test_xep_lich_van_de`/`tests.test_xep_lich_service` đúng như `test_bai_ghep_mot_cong_viec_khong_de_trung` đã dùng (xem `backend/tests/test_san_xuat_release.py:140-166` để copy đúng khối import ở đầu file, KHÔNG viết lại từ đầu).

- [ ] **Step 2: Chạy test, xác nhận FAIL**

```bash
cd backend && python -m pytest tests/test_san_xuat_release.py -k "dung_diem_toa_sinh_canh_theo_so_con" -v
```
Expected: FAIL (`canh_a`/`canh_b` rỗng — chưa có `dung_diem_toa`).

- [ ] **Step 3: Thêm `thanh_vien_so_con` vào `SanXuatRepository`**

`backend/app/repositories/san_xuat_repo.py`, thêm ngay sau `bai_ghep_ids_cua_lsx` (L40-49):

```python
    def thanh_vien_so_con(self, bg_ids: set[int]) -> dict[int, int]:
        """`lsx_id → so_con_tren_to` của thành viên trong tập bài ghép — tỷ lệ toả sản lượng khi
        điểm toả tách batch chung thành sản lượng riêng từng LSX (§ điểm toả)."""
        if not bg_ids:
            return {}
        rows = self.db.execute(
            select(BaiGhepThanhVien.lsx_id, BaiGhepThanhVien.so_con_tren_to).where(
                BaiGhepThanhVien.bai_ghep_id.in_(bg_ids)
            )
        ).all()
        return {lsx_id: int(con or 0) for lsx_id, con in rows}
```

- [ ] **Step 4: Thêm `dung_diem_toa` vào `snapshot.py`**

Import thêm ở đầu `backend/app/services/san_xuat/snapshot.py`:

```python
from ..dong_giay import ban_do_tram, tren_dong_giay
```

Thêm hàm, ngay sau `dung_phu_thuoc`:

```python
def dung_diem_toa(
    repo: SanXuatRepository,
    *,
    goi: SanXuatGoiPhatHanh,
    phien_ban_so: int,
    lsx_ids: set[int],
    bai_ghep_ids: set[int],
    nhom_by_lsx: dict[int, SanXuatNhom],
    cv_by_step: dict[str, SanXuatCongViec],
) -> int:
    """Chụp cạnh TOẢ từ điểm-toả bài ghép sang từng nhánh LSX riêng thành `san_xuat_phu_thuoc`.

    Điểm toả = bước dùng chung CUỐI CÙNG trên dòng giấy của một LSX thành viên (theo `thu_tu`
    routing); đích = bước RIÊNG đầu tiên ngay sau đó của chính LSX đó. Chỉ nhận bước dùng chung
    nằm TRÊN DÒNG GIẤY (`tren_dong_giay`) — bước như ghi kẽm/CTP không đếm, tránh lấy nhầm điểm
    toả. LSX không còn bước riêng nào sau bước chung cuối (mọi bước đều dùng chung, hoặc bài ghép
    chưa có bước chung nào trên dòng giấy) thì không có gì để toả — bỏ qua, không phải lỗi."""
    if not bai_ghep_ids:
        return 0
    so_con = repo.thanh_vien_so_con(bai_ghep_ids)
    tram = ban_do_tram(repo.db)
    dem = 0
    for lsx_id in sorted(lsx_ids):
        con = so_con.get(lsx_id)
        if not con or con <= 0:
            continue
        steps = repo.routing_steps(lsx_id)
        diem_toa_idx = None
        for i, cd in enumerate(steps):
            cv = cv_by_step.get(cd.step_key)
            if cv is None or cv.bai_ghep_id is None:
                continue
            if not tren_dong_giay(cd.don_vi_vao, cd.don_vi_ra, tram, nhom=cd.nhom):
                continue
            diem_toa_idx = i
        if diem_toa_idx is None:
            continue
        nguon_cv = cv_by_step[steps[diem_toa_idx].step_key]
        dich_cd = next(
            (
                cd for cd in steps[diem_toa_idx + 1:]
                if cv_by_step.get(cd.step_key) and cv_by_step[cd.step_key].bai_ghep_id is None
            ),
            None,
        )
        if dich_cd is None:
            continue
        dich_cv = cv_by_step[dich_cd.step_key]
        grp = nhom_by_lsx.get(lsx_id)
        if grp is None:
            continue
        don_vi_ra = steps[diem_toa_idx].don_vi_ra
        don_vi_vao = dich_cd.don_vi_vao
        repo.add(SanXuatPhuThuoc(
            goi_id=goi.id, phien_ban_so=phien_ban_so,
            nhom_id=grp.id,
            nguon_cong_viec_id=nguon_cv.id, dich_cong_viec_id=dich_cv.id,
            ty_le_ghep=float(con),
            don_vi_nguon=don_vi_ra, don_vi_dich=don_vi_vao,
            quy_tac_quy_doi=(
                f"Điểm toả bài ghép: 1 {don_vi_ra or '?'} chung → {con} {don_vi_vao or '?'} riêng của lệnh"
            ),
        ))
        dem += 1
    repo.flush()
    return dem
```

- [ ] **Step 5: Nối vào `release.py`**

`:26-30`, thêm `dung_diem_toa` vào import:

```python
from .snapshot import (
    danh_dau_kcs_cuoi,
    dung_cong_viec,
    dung_diem_toa,
    dung_phu_thuoc,
)
```

`:80-84`, gọi ngay sau `dung_phu_thuoc`:

```python
    dung_phu_thuoc(
        repo, goi=goi, phien_ban_so=1,
        lsx_ids=lsx_ids, nhom_by_lsx=nhom_by_lsx, cv_by_step=cv_by_step,
    )
    dung_diem_toa(
        repo, goi=goi, phien_ban_so=1,
        lsx_ids=lsx_ids, bai_ghep_ids=bai_ghep_ids,
        nhom_by_lsx=nhom_by_lsx, cv_by_step=cv_by_step,
    )
    repo.flush()
    return goi
```

- [ ] **Step 6: Chạy lại test + toàn bộ file release để chắc không vỡ luồng bài-ghép-cũ**

```bash
cd backend && python -m pytest tests/test_san_xuat_release.py -v
```
Expected: PASS toàn bộ.

- [ ] **Step 7: Commit**

```bash
git add backend/app/repositories/san_xuat_repo.py backend/app/services/san_xuat/snapshot.py backend/app/services/san_xuat/release.py backend/tests/test_san_xuat_release.py
git commit -m "Thực hiện SX: chụp cạnh điểm toả bài ghép lúc phát hành"
```

---

### Task 10: Model `SanXuatKetQuaNhanh` + đăng ký + tài liệu

**Files:**
- Modify: `backend/app/models/san_xuat_san_luong.py` (thêm class, thêm dòng docstring đầu file)
- Modify: `backend/app/models/__init__.py:142-148,308-320` (import + `__all__`)
- Modify: `docs/DB_SCHEMA.md` (thêm mục bảng mới)

**Interfaces:**
- Produces: `SanXuatKetQuaNhanh(id, batch_id, lsx_id, so_luong, don_vi, ban_giao_id, created_at)` — bảng MỚI, `create_all` tự dựng (KHÔNG cần migration). Task 11 ghi vào bảng này; Task 13 đọc ra API.

- [ ] **Step 1: Viết test thất bại — bảng/cột chưa tồn tại**

```python
def test_ket_qua_nhanh_model_tao_duoc(db):
    from app.models.san_xuat_san_luong import SanXuatKetQuaNhanh
    kq = SanXuatKetQuaNhanh(batch_id=1, lsx_id=1, so_luong=10, don_vi="con")
    db.add(kq)
    db.commit()
    db.refresh(kq)
    assert kq.id is not None
    assert kq.ban_giao_id is None
```

(Đặt tạm trong `backend/tests/test_san_xuat_san_luong.py` — vị trí bất kỳ, sẽ được dùng lại/xoá khi Task 11 viết test thật có ràng buộc FK đầy đủ.)

- [ ] **Step 2: Chạy test, xác nhận FAIL**

```bash
cd backend && python -m pytest tests/test_san_xuat_san_luong.py -k "ket_qua_nhanh_model_tao_duoc" -v
```
Expected: FAIL với `ImportError`.

- [ ] **Step 3: Thêm class vào `san_xuat_san_luong.py`**

Cập nhật docstring đầu file (thêm dòng thứ 6 vào danh sách bảng, sau `san_xuat_vat_tu_nhan`):

```
  san_xuat_ket_qua_nhanh  — SẢN LƯỢNG RIÊNG từng LSX tách ra từ một batch điểm-toả bài ghép (§
                             điểm toả): `tot` của batch × `ty_le_ghep` (số con/tờ) của LSX đó.
                             CHỈ-THÊM, không sửa — batch mới thì đẻ dòng mới.
```

Thêm class, sau `SanXuatVatTuNhan` (cuối file — đọc `Read` xác nhận số dòng thật trước khi chèn, tránh chèn giữa docstring):

```python
class SanXuatKetQuaNhanh(Base):
    """Sản lượng RIÊNG từng LSX tách ra từ một batch của công việc ĐIỂM TOẢ bài ghép.

    Ghi khi `san_luong.tao_batch` phát hiện công việc vừa ghi có cạnh `san_xuat_phu_thuoc` toả đi
    (nguồn = chính công việc này) — mỗi cạnh một dòng: `so_luong` = `tot` của batch × `ty_le_ghep`
    (số con/tờ) của LSX đích. `ban_giao_id` neo bàn giao TỰ ĐỘNG-XÁC-NHẬN tương ứng (§11.2 biến
    thể: số suy MỘT CHIỀU từ `tot`, không thể vượt, nên bỏ qua vòng đề xuất/xác nhận hai bên).
    Bảng CHỈ-THÊM — dùng làm sổ cái quota để chặn LSX khác dùng nhầm phần đã toả (§10.3 biến thể)."""

    __tablename__ = "san_xuat_ket_qua_nhanh"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("san_xuat_batch.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lsx_id: Mapped[int] = mapped_column(
        ForeignKey("lsx.id", ondelete="CASCADE"), nullable=False, index=True
    )
    so_luong: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False)
    don_vi: Mapped[str] = mapped_column(String(24), nullable=False)
    ban_giao_id: Mapped[int | None] = mapped_column(
        ForeignKey("san_xuat_ban_giao.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
```

- [ ] **Step 4: Đăng ký ở `models/__init__.py`**

`:142-148`, thêm `SanXuatKetQuaNhanh` vào import (giữ thứ tự alphabet như các dòng khác):

```python
from .san_xuat_san_luong import (
    SanXuatBanGiao,
    SanXuatBanGiaoDieuChinh,
    SanXuatBatch,
    SanXuatBatchLotVao,
    SanXuatKetQuaNhanh,
    SanXuatVatTuNhan,
)
```

`:308-320`, thêm vào `__all__` (cạnh `"SanXuatVatTuNhan"`):

```python
    "SanXuatKetQuaNhanh",
```

- [ ] **Step 5: Cập nhật `docs/DB_SCHEMA.md`**

Thêm một mục bảng mới `san_xuat_ket_qua_nhanh`, theo đúng format các bảng `san_xuat_*` liền kề đã có ở đó (copy khối `san_xuat_batch_lot_vao` làm khuôn, đổi tên bảng/cột), liệt kê đủ 7 cột: `id, batch_id, lsx_id, so_luong, don_vi, ban_giao_id, created_at`.

- [ ] **Step 6: Chạy lại test**

```bash
cd backend && python -m pytest tests/test_san_xuat_san_luong.py -k "ket_qua_nhanh_model_tao_duoc" -v
```
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/san_xuat_san_luong.py backend/app/models/__init__.py docs/DB_SCHEMA.md backend/tests/test_san_xuat_san_luong.py
git commit -m "Thực hiện SX: thêm bảng san_xuat_ket_qua_nhanh (sổ cái sản lượng đã toả theo LSX)"
```

---

### Task 11: `san_luong._toa_san_luong()` — tự tỏa sản lượng + bàn giao tự xác nhận

**Files:**
- Modify: `backend/app/repositories/san_xuat_san_luong_repo.py` (thêm methods, cạnh `canh_phu_thuoc_toi`)
- Modify: `backend/app/services/san_xuat/san_luong.py` (thêm `_toa_san_luong`, sửa `_ket_qua_batch`, sửa `tao_batch`)
- Test: `backend/tests/test_san_xuat_san_luong.py`

**Interfaces:**
- Consumes: `SanXuatKetQuaNhanh`, `SanXuatBanGiao`/`BG_XAC_NHAN` (từ `...models.san_xuat_san_luong`), `SanXuatPhuThuoc` (từ `...models.san_xuat`), `_moc()` (từ `.thuc_thi`, đã import sẵn trong `san_luong.py`).
- Produces: `SanXuatSanLuongRepository.canh_toa_di_tu(nguon_cong_viec_id: int) -> list[SanXuatPhuThuoc]`; `_toa_san_luong(db, repo, *, cv, batch, tot, actor) -> list[dict{lsx_id, so_luong, don_vi, ban_giao_id}]`; `_ket_qua_batch(cv, batch, ket_qua_lsx=None) -> dict` (thêm khoá `"ket_qua_lsx"`); `tao_batch()` trả thêm khoá đó trong dict kết quả. Task 12 dùng `repo.co_ket_qua_nhanh`/`ket_qua_nhanh_cua`/`da_dung_nhanh` (thêm cùng lúc trong file repo này). Task 13 map `"ket_qua_lsx"` sang schema Pydantic.

- [ ] **Step 1: Viết test thất bại — ghi batch cho công việc điểm-toả, kỳ vọng tỏa đúng tỷ lệ ra 2 nhánh + bàn giao tự xác nhận**

```python
def test_toa_san_luong_hai_nhanh_dung_ty_le(db, orders, lsx_svc, admin, customer):
    from app.models.san_xuat import SanXuatPhuThuoc
    from app.models.san_xuat_san_luong import BG_XAC_NHAN, SanXuatBanGiao
    from tests.test_san_xuat_ban_giao import _hai_cv

    _to1, cv_nguon, cv_a, lsx_a = _hai_cv(db, orders, lsx_svc, admin, customer, ma="TO-TOA-1")
    _to2, cv_b, _cv_b2, lsx_b = _hai_cv(db, orders, lsx_svc, admin, customer, ma="TO-TOA-2")
    cv_a.lsx_id = lsx_a
    cv_b.lsx_id = lsx_b
    db.add(SanXuatPhuThuoc(
        goi_id=cv_nguon.goi_id, phien_ban_so=cv_nguon.phien_ban_so, nhom_id=cv_nguon.nhom_id,
        nguon_cong_viec_id=cv_nguon.id, dich_cong_viec_id=cv_a.id,
        ty_le_ghep=1.5, don_vi_nguon="tờ", don_vi_dich="con",
    ))
    db.add(SanXuatPhuThuoc(
        goi_id=cv_nguon.goi_id, phien_ban_so=cv_nguon.phien_ban_so, nhom_id=cv_nguon.nhom_id,
        nguon_cong_viec_id=cv_nguon.id, dich_cong_viec_id=cv_b.id,
        ty_le_ghep=1.0, don_vi_nguon="tờ", don_vi_dich="con",
    ))
    db.commit()

    res = san_luong.tao_batch(
        db, user=admin, cong_viec_id=cv_nguon.id,
        bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=1), tong=120, tot=120,
    )
    ket_qua = {k["lsx_id"]: k for k in res["ket_qua_lsx"]}
    assert ket_qua[lsx_a]["so_luong"] == 180.0
    assert ket_qua[lsx_b]["so_luong"] == 120.0
    bg_a = db.get(SanXuatBanGiao, ket_qua[lsx_a]["ban_giao_id"])
    assert bg_a.trang_thai == BG_XAC_NHAN
    assert bg_a.nguon_cong_viec_id == cv_nguon.id and bg_a.dich_cong_viec_id == cv_a.id
```

Import cần thêm ở đầu `test_san_xuat_san_luong.py`: `from datetime import timedelta`, `from app.services.san_xuat import san_luong`, `_T0` (nếu file chưa có sẵn hằng số mốc thời gian, định nghĩa `_T0 = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)` cạnh các fixture khác — cùng giá trị `test_san_xuat_ban_giao.py` đang dùng, không bắt buộc trùng nhưng tiện copy).

- [ ] **Step 2: Chạy test, xác nhận FAIL**

```bash
cd backend && python -m pytest tests/test_san_xuat_san_luong.py -k "toa_san_luong_hai_nhanh" -v
```
Expected: FAIL với `KeyError: 'ket_qua_lsx'`.

- [ ] **Step 3: Thêm methods vào `SanXuatSanLuongRepository`**

`backend/app/repositories/san_xuat_san_luong_repo.py`, thêm ngay sau `canh_phu_thuoc_toi` (L230-239):

```python
    def canh_toa_di_tu(self, nguon_cong_viec_id: int) -> list[SanXuatPhuThuoc]:
        """Cạnh TOẢ xuất phát từ một công việc (nó là điểm toả bài ghép). Rỗng với công việc
        thường → `_toa_san_luong` là no-op, an toàn cho mọi batch không phải điểm toả."""
        return list(
            self.db.scalars(
                select(SanXuatPhuThuoc).where(
                    SanXuatPhuThuoc.nguon_cong_viec_id == nguon_cong_viec_id
                )
            )
        )

    def co_ket_qua_nhanh(self, batch_id: int) -> bool:
        """Batch này có phải điểm toả (đã tách ra ≥1 nhánh LSX) hay không."""
        return self.db.scalar(
            select(SanXuatKetQuaNhanh.id).where(SanXuatKetQuaNhanh.batch_id == batch_id).limit(1)
        ) is not None

    def ket_qua_nhanh_cua(self, batch_id: int, lsx_id: int) -> SanXuatKetQuaNhanh | None:
        """Phần đã toả cho MỘT lsx cụ thể của một batch điểm toả — None nghĩa là lsx đó KHÔNG có
        phần trong batch này (không phải nhánh hợp lệ của điểm toả)."""
        return self.db.scalars(
            select(SanXuatKetQuaNhanh).where(
                SanXuatKetQuaNhanh.batch_id == batch_id, SanXuatKetQuaNhanh.lsx_id == lsx_id
            )
        ).first()

    def ket_qua_nhanh_cua_batch(self, batch_id: int) -> list[SanXuatKetQuaNhanh]:
        return list(
            self.db.scalars(
                select(SanXuatKetQuaNhanh).where(SanXuatKetQuaNhanh.batch_id == batch_id)
            )
        )

    def da_dung_nhanh(self, batch_id: int, lsx_id: int) -> float:
        """Tổng số lượng LSX này đã LẤY từ batch điểm-toả `batch_id` qua các lot đầu vào (§10.3) —
        cộng dồn mọi batch của LSX đó có lot trỏ về `batch_id`."""
        tong = self.db.scalar(
            select(func.coalesce(func.sum(SanXuatBatchLotVao.so_luong), 0))
            .select_from(SanXuatBatchLotVao)
            .join(SanXuatBatch, SanXuatBatch.id == SanXuatBatchLotVao.batch_id)
            .join(SanXuatCongViec, SanXuatCongViec.id == SanXuatBatch.cong_viec_id)
            .where(
                SanXuatBatchLotVao.nguon_batch_id == batch_id,
                SanXuatCongViec.lsx_id == lsx_id,
            )
        )
        return float(tong or 0)
```

Thêm import cần thiết ở đầu file: `SanXuatKetQuaNhanh` vào khối `from ..models.san_xuat_san_luong import (...)` đã có, và `func` vào import `sqlalchemy` nếu file chưa có (`from sqlalchemy import func, select` — kiểm import hiện tại trước khi thêm để tránh trùng).

- [ ] **Step 4: Thêm `_toa_san_luong`, sửa `_ket_qua_batch` và `tao_batch` trong `san_luong.py`**

Thêm import ở đầu file (mở rộng khối import từ `...models.san_xuat_san_luong` đã có, thêm `BG_XAC_NHAN, SanXuatBanGiao, SanXuatKetQuaNhanh`):

```python
from ...models.san_xuat_san_luong import (
    BG_XAC_NHAN,
    LOT_TU_BATCH,
    LOT_TU_KHO,
    NGUON_LOT,
    SanXuatBanGiao,
    SanXuatBatch,
    SanXuatBatchLotVao,
    SanXuatKetQuaNhanh,
)
```

Sửa `_ket_qua_batch`:

```python
def _ket_qua_batch(cv, batch: SanXuatBatch | None, ket_qua_lsx: list[dict] | None = None) -> dict:
    return {
        "cong_viec_id": cv.id,
        "department_id": cv.department_id,
        "trang_thai": cv.trang_thai,
        "version": cv.version,
        "batch_id": batch.id if batch is not None else None,
        "ket_qua_lsx": ket_qua_lsx or [],
    }
```

Thêm `_toa_san_luong`, ngay trước `tao_batch`:

```python
def _toa_san_luong(
    db: Session, repo: SanXuatSanLuongRepository, *, cv, batch: SanXuatBatch, tot: float, actor,
) -> list[dict]:
    """Tự TOẢ sản lượng TỐT của một batch điểm-toả sang các nhánh LSX riêng (§ điểm toả bài ghép).

    Mỗi cạnh `SanXuatPhuThuoc` xuất phát từ `cv` (điểm toả, do `dung_diem_toa` sinh lúc phát hành)
    mang `ty_le_ghep` = số con/tờ của lệnh đích — nhân thẳng với `tot` ra sản lượng nhánh, rồi bàn
    giao THẲNG dạng đã xác nhận (không qua đề xuất/xác nhận hai bên): số này suy MỘT CHIỀU từ
    `tot`, không thể vượt, nên không cần vòng thương lượng như bàn giao người khai tay (§11.2)."""
    if tot <= 0:
        return []
    canh = repo.canh_toa_di_tu(cv.id)
    if not canh:
        return []
    ket_qua: list[dict] = []
    now = _moc()
    for c in canh:
        dich_cv = repo.cong_viec(c.dich_cong_viec_id)
        if dich_cv is None or dich_cv.lsx_id is None or not c.ty_le_ghep:
            continue
        sl_nhanh = round(tot * float(c.ty_le_ghep), 3)
        if sl_nhanh <= 0:
            continue
        don_vi_nhanh = c.don_vi_dich or dich_cv.don_vi_vao or batch.don_vi
        kq = SanXuatKetQuaNhanh(
            batch_id=batch.id, lsx_id=dich_cv.lsx_id, so_luong=sl_nhanh, don_vi=don_vi_nhanh,
        )
        repo.add(kq)
        bg = SanXuatBanGiao(
            nguon_cong_viec_id=cv.id,
            dich_cong_viec_id=dich_cv.id,
            cung_to=False,
            so_luong=sl_nhanh,
            don_vi=don_vi_nhanh,
            trang_thai=BG_XAC_NHAN,
            de_xuat_by_id=getattr(actor, "id", None),
            de_xuat_luc=now,
            xac_nhan_by_id=getattr(actor, "id", None),
            xac_nhan_luc=now,
        )
        repo.add(bg)
        repo.flush()
        kq.ban_giao_id = bg.id
        ket_qua.append({
            "lsx_id": dich_cv.lsx_id, "so_luong": sl_nhanh, "don_vi": don_vi_nhanh,
            "ban_giao_id": bg.id,
        })
    return ket_qua
```

Sửa `tao_batch` — chèn trước `db.commit()` cuối hàm, và trả kèm `ket_qua_lsx`:

```python
    from ...repositories.audit_repo import AuditLogRepository
    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None),
        action="san_xuat_tao_batch",
        target=f"san_xuat_batch:{batch.id}",
        detail=f"cong_viec={cv.id} tot={tot_f} hong={hong_f}",
    )
    ket_qua_lsx = _toa_san_luong(db, repo, cv=cv, batch=batch, tot=tot_f, actor=user)
    db.commit()
    return _ket_qua_batch(cv, batch, ket_qua_lsx)
```

- [ ] **Step 5: Chạy lại test + toàn bộ file để chắc không vỡ luồng batch thường (không điểm toả)**

```bash
cd backend && python -m pytest tests/test_san_xuat_san_luong.py -v
```
Expected: PASS toàn bộ.

- [ ] **Step 6: Commit**

```bash
git add backend/app/repositories/san_xuat_san_luong_repo.py backend/app/services/san_xuat/san_luong.py backend/tests/test_san_xuat_san_luong.py
git commit -m "Thực hiện SX: tự toả sản lượng điểm-toả bài ghép ra từng LSX + bàn giao tự xác nhận"
```

---

### Task 12: `_chuan_hoa_lot()` — chặn LSX dùng nhầm phần đã toả cho LSX khác

**Files:**
- Modify: `backend/app/services/san_xuat/san_luong.py` (hàm `_chuan_hoa_lot`, hai call site `tao_batch`/`them_lot`)
- Test: `backend/tests/test_san_xuat_san_luong.py`

**Interfaces:**
- Consumes: `repo.co_ket_qua_nhanh`, `repo.ket_qua_nhanh_cua`, `repo.da_dung_nhanh` (Task 11).
- Produces: `_chuan_hoa_lot(repo, dich_cv: SanXuatCongViec, don_vi_mac_dinh, raw) -> SanXuatBatchLotVao` — đổi tham số thứ hai từ `cong_viec_id: int` sang `dich_cv: SanXuatCongViec` (cả hai call site trong cùng file đã có sẵn `cv` trong scope, chỉ đổi biến truyền vào — KHÔNG đổi hành vi khi batch nguồn không phải điểm toả).

Hiện trạng `_chuan_hoa_lot` (đã đọc ở Task 11 chuẩn bị — nhắc lại đoạn cần sửa):

```python
def _chuan_hoa_lot(repo: SanXuatSanLuongRepository, cong_viec_id: int, don_vi_mac_dinh: str, raw: dict) -> SanXuatBatchLotVao:
    ...
    if nguon_loai == LOT_TU_BATCH:
        if not nguon_batch_id:
            raise ValueError("Lot từ công đoạn trước phải chọn batch nguồn.")
        nguon = repo.batch(int(nguon_batch_id))
        if nguon is None:
            raise ValueError("Không tìm thấy batch nguồn của lot đầu vào.")
        if nguon.cong_viec_id == cong_viec_id:
            raise ValueError("Batch nguồn không được trùng chính công việc đang ghi.")
        nguon_lot_id = None
    else:  # LOT_TU_KHO
        ...
```

- [ ] **Step 1: Viết test thất bại — LSX không thuộc nhánh nào của điểm toả bị chặn dùng lot của nó; LSX có phần bị chặn khi vượt phần đã toả**

```python
def test_chan_lsx_khac_dung_lot_diem_toa(db, orders, lsx_svc, admin, customer):
    from app.models.san_xuat import SanXuatPhuThuoc
    from tests.test_san_xuat_ban_giao import _hai_cv

    _to1, cv_nguon, cv_a, lsx_a = _hai_cv(db, orders, lsx_svc, admin, customer, ma="TO-TOA-A1")
    _to2, cv_b, _cv_b2, lsx_b = _hai_cv(db, orders, lsx_svc, admin, customer, ma="TO-TOA-A2")
    _to3, cv_c, _cv_c2, lsx_c = _hai_cv(db, orders, lsx_svc, admin, customer, ma="TO-TOA-A3")
    cv_a.lsx_id, cv_b.lsx_id, cv_c.lsx_id = lsx_a, lsx_b, lsx_c
    db.add(SanXuatPhuThuoc(
        goi_id=cv_nguon.goi_id, phien_ban_so=cv_nguon.phien_ban_so, nhom_id=cv_nguon.nhom_id,
        nguon_cong_viec_id=cv_nguon.id, dich_cong_viec_id=cv_a.id,
        ty_le_ghep=1.0, don_vi_nguon="tờ", don_vi_dich="con",
    ))
    db.commit()
    res = san_luong.tao_batch(
        db, user=admin, cong_viec_id=cv_nguon.id,
        bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=1), tong=100, tot=100,
    )
    batch_nguon_id = res["batch_id"]

    # (1) LSX B có phần (100 con) → dùng trong hạn mức là được.
    ok = san_luong.tao_batch(
        db, user=admin, cong_viec_id=cv_a.id,
        bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=1), tong=60, tot=60,
        lot_vao=[{"nguon_loai": "batch", "nguon_batch_id": batch_nguon_id, "so_luong": 60}],
    )
    assert ok["batch_id"] is not None

    # (2) Vượt phần đã toả cho lsx_a (100) — 60 đã dùng + 60 nữa = 120 > 100 → chặn.
    with pytest.raises(ValueError, match="Vượt phần đã toả"):
        san_luong.tao_batch(
            db, user=admin, cong_viec_id=cv_a.id,
            bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=1), tong=60, tot=60,
            lot_vao=[{"nguon_loai": "batch", "nguon_batch_id": batch_nguon_id, "so_luong": 60}],
        )

    # (3) LSX C không có cạnh toả nào từ batch_nguon_id → không có phần, bị chặn dù số nhỏ.
    with pytest.raises(ValueError, match="không có phần"):
        san_luong.tao_batch(
            db, user=admin, cong_viec_id=cv_c.id,
            bat_dau=_T0, ket_thuc=_T0 + timedelta(hours=1), tong=1, tot=1,
            lot_vao=[{"nguon_loai": "batch", "nguon_batch_id": batch_nguon_id, "so_luong": 1}],
        )
```

- [ ] **Step 2: Chạy test, xác nhận FAIL ở nhánh (2)/(3)**

```bash
cd backend && python -m pytest tests/test_san_xuat_san_luong.py -k "chan_lsx_khac_dung_lot_diem_toa" -v
```
Expected: FAIL (nhánh (2)/(3) hiện không raise gì — lot được chấp nhận vô điều kiện).

- [ ] **Step 3: Sửa `_chuan_hoa_lot` + 2 call site**

```python
def _chuan_hoa_lot(
    repo: SanXuatSanLuongRepository, dich_cv, don_vi_mac_dinh: str, raw: dict,
) -> SanXuatBatchLotVao:
    """Dựng một dòng lot đầu vào từ payload thô, kiểm §10.3. KHÔNG add vào session (caller làm)."""
    nguon_loai = (raw.get("nguon_loai") or LOT_TU_BATCH).strip()
    if nguon_loai not in NGUON_LOT:
        raise ValueError(f"Nguồn lot không hợp lệ: {nguon_loai}.")
    so_luong = _so_khong_am(raw.get("so_luong"), "Số lượng lot")
    if so_luong <= 0:
        raise ValueError("Số lượng lot phải lớn hơn 0.")
    don_vi = (raw.get("don_vi") or don_vi_mac_dinh or "").strip()
    if not don_vi:
        raise ValueError("Lot đầu vào chưa có đơn vị.")

    nguon_batch_id = raw.get("nguon_batch_id")
    nguon_lot_id = raw.get("nguon_lot_id")
    if nguon_loai == LOT_TU_BATCH:
        if not nguon_batch_id:
            raise ValueError("Lot từ công đoạn trước phải chọn batch nguồn.")
        nguon = repo.batch(int(nguon_batch_id))
        if nguon is None:
            raise ValueError("Không tìm thấy batch nguồn của lot đầu vào.")
        if nguon.cong_viec_id == dich_cv.id:
            raise ValueError("Batch nguồn không được trùng chính công việc đang ghi.")
        # Batch nguồn là điểm toả bài ghép (đã tách theo LSX) — công việc đang ghi phải THUỘC một
        # LSX có phần trong đó, và không được dùng vượt phần đã toả cho LSX của chính nó.
        if dich_cv.lsx_id is not None and repo.co_ket_qua_nhanh(nguon.id):
            kq = repo.ket_qua_nhanh_cua(nguon.id, dich_cv.lsx_id)
            if kq is None:
                raise ValueError(
                    "Batch nguồn đã toả theo từng lệnh sản xuất — lệnh này không có phần trong đó."
                )
            da_dung = repo.da_dung_nhanh(nguon.id, dich_cv.lsx_id)
            if da_dung + so_luong > float(kq.so_luong) + _EPS:
                raise ValueError(
                    f"Vượt phần đã toả cho lệnh sản xuất này ({float(kq.so_luong):g} {kq.don_vi})."
                )
        nguon_lot_id = None
    else:  # LOT_TU_KHO
        if not nguon_lot_id:
            raise ValueError("Lot BTP kho phải có mã lot.")
        nguon_batch_id = None

    return SanXuatBatchLotVao(
        nguon_loai=nguon_loai,
        nguon_batch_id=int(nguon_batch_id) if nguon_batch_id else None,
        nguon_lot_id=int(nguon_lot_id) if nguon_lot_id else None,
        so_luong=so_luong,
        don_vi=don_vi,
    )
```

Sửa 2 call site — trong `tao_batch` (truyền `cv` thay vì `cong_viec_id`):

```python
    cac_lot = [
        _chuan_hoa_lot(repo, cv, don_vi_lot_mac_dinh, r)
        for r in (lot_vao or [])
    ]
```

Trong `them_lot`:

```python
    lot = _chuan_hoa_lot(
        repo,
        cv,
        don_vi_lot_mac_dinh,
        {
            "nguon_loai": nguon_loai,
            "nguon_batch_id": nguon_batch_id,
            "nguon_lot_id": nguon_lot_id,
            "so_luong": so_luong,
            "don_vi": don_vi,
        },
    )
```

- [ ] **Step 4: Chạy lại test + toàn bộ file, chắc luồng lot thường (không điểm toả) không vỡ**

```bash
cd backend && python -m pytest tests/test_san_xuat_san_luong.py backend/tests/test_san_xuat_ban_giao.py -v
```
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/san_xuat/san_luong.py backend/tests/test_san_xuat_san_luong.py
git commit -m "Thực hiện SX: chặn LSX dùng vượt/nhầm phần đã toả của batch điểm toả"
```

---

### Task 13: API — `SanLuongKetQuaOut.ket_qua_lsx` + client.ts `SxKetQuaNhanh`

**Files:**
- Modify: `backend/app/schemas/san_xuat.py:357-363` (class `SanLuongKetQuaOut`)
- Modify: `frontend/src/api/client.ts:1614-1620` (interface `SxSanLuongKetQua`)
- Test: `backend/tests/test_san_xuat_san_luong.py` (test HTTP nếu file có sẵn lớp test qua router; nếu không, test service-level đã đủ ở Task 11 — bước này chỉ cần xác nhận schema serialize đúng)

**Interfaces:**
- Produces: `KetQuaNhanhOut(lsx_id, so_luong, don_vi, ban_giao_id)`; `SanLuongKetQuaOut.ket_qua_lsx: list[KetQuaNhanhOut] = []`. FE: `SxKetQuaNhanh { lsx_id, so_luong, don_vi, ban_giao_id }`; `SxSanLuongKetQua.ket_qua_lsx?: SxKetQuaNhanh[]`.

- [ ] **Step 1: Viết test thất bại — gọi service trả `ket_qua_lsx` nhưng response_model (Pydantic) cắt mất field vì schema chưa khai (bẫy "Pydantic nuốt field im lặng")**

```python
def test_schema_san_luong_ket_qua_giu_ket_qua_lsx():
    from app.schemas.san_xuat import SanLuongKetQuaOut
    obj = SanLuongKetQuaOut(
        cong_viec_id=1, department_id=None, trang_thai="dang_chay", version=1, batch_id=1,
        ket_qua_lsx=[{"lsx_id": 9, "so_luong": 12.5, "don_vi": "con", "ban_giao_id": 3}],
    )
    assert obj.ket_qua_lsx[0].lsx_id == 9
    assert obj.ket_qua_lsx[0].so_luong == 12.5
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

```bash
cd backend && python -m pytest tests/test_san_xuat_san_luong.py -k "schema_san_luong_ket_qua_giu_ket_qua_lsx" -v
```
Expected: FAIL với `TypeError`/`ValidationError: ket_qua_lsx — Extra inputs are not permitted` (Pydantic v2 mặc định) hoặc bị bỏ qua âm thầm tuỳ cấu hình model — cả hai đều xác nhận field CHƯA được khai.

- [ ] **Step 3: Sửa schema backend**

`backend/app/schemas/san_xuat.py:357-363`, hiện tại:

```python
class SanLuongKetQuaOut(BaseModel):
    cong_viec_id: int
    department_id: int | None = None
    trang_thai: str
    version: int
    batch_id: int | None = None
```

Sửa thành:

```python
class KetQuaNhanhOut(BaseModel):
    lsx_id: int
    so_luong: float
    don_vi: str
    ban_giao_id: int | None = None


class SanLuongKetQuaOut(BaseModel):
    cong_viec_id: int
    department_id: int | None = None
    trang_thai: str
    version: int
    batch_id: int | None = None
    ket_qua_lsx: list[KetQuaNhanhOut] = []
```

- [ ] **Step 4: Sửa TS type ở `client.ts`**

`:1614-1620`, hiện tại:

```typescript
export interface SxSanLuongKetQua {
  cong_viec_id: number;
  department_id: number | null;
  trang_thai: string;
  version: number;
  batch_id?: number | null;
}
```

Sửa thành:

```typescript
export interface SxKetQuaNhanh {
  lsx_id: number;
  so_luong: number;
  don_vi: string;
  ban_giao_id: number | null;
}
export interface SxSanLuongKetQua {
  cong_viec_id: number;
  department_id: number | null;
  trang_thai: string;
  version: number;
  batch_id?: number | null;
  ket_qua_lsx?: SxKetQuaNhanh[];
}
```

- [ ] **Step 5: Chạy lại test backend + tsc frontend**

```bash
cd backend && python -m pytest tests/test_san_xuat_san_luong.py -v
```
```bash
cd frontend && npx tsc --noEmit
```
Expected: cả hai PASS/0 lỗi.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/san_xuat.py frontend/src/api/client.ts backend/tests/test_san_xuat_san_luong.py
git commit -m "Thực hiện SX: trả ket_qua_lsx trong API ghi batch sản lượng"
```

---

### Task 14: FE — panel "Đã toả theo lệnh sản xuất" trong Thực hiện sản xuất

**Files:**
- Modify: `frontend/src/pages/ThsxExecPanels.tsx:21` (interface `ThsxExec.taoBatch`), `:118-165` (`SanLuongSection`), `:168-199` (`BatchForm`)
- Modify: `frontend/src/pages/ThucHienSxPage.tsx:487` (implement `exec.taoBatch`)

**Interfaces:**
- Consumes: `SxKetQuaNhanh[]` (Task 13).
- Produces: `ThsxExec.taoBatch: (body: SxBatchIn) => Promise<SxKetQuaNhanh[] | null>` (đổi kiểu trả — `null` = thất bại, mảng kể cả rỗng = thành công; tương thích ngược với chỗ gọi cũ `if (await exec.taoBatch(body))` vì `[]` vẫn truthy trong JS).

- [ ] **Step 1: Sửa `ThucHienSxPage.tsx:487` — trả `ket_qua_lsx` thay vì thu gọn về boolean**

Hiện tại:
```typescript
      taoBatch: (b) => ok(mutate(() => api.sanXuat.taoBatch(token!, selectedId!, b), "Đã ghi mẻ sản lượng.")),
```
Sửa thành:
```typescript
      taoBatch: (b) => mutate(() => api.sanXuat.taoBatch(token!, selectedId!, b), "Đã ghi mẻ sản lượng.")
        .then((r) => (r ? r.ket_qua_lsx ?? [] : null)),
```

- [ ] **Step 2: Sửa `ThsxExec.taoBatch` interface + `BatchForm`/`SanLuongSection` trong `ThsxExecPanels.tsx`**

`:21`, hiện tại:
```typescript
  taoBatch: (body: SxBatchIn) => Promise<boolean>;
```
Sửa thành:
```typescript
  taoBatch: (body: SxBatchIn) => Promise<SxKetQuaNhanh[] | null>;
```
(thêm `SxKetQuaNhanh` vào import từ `../api/client` ở đầu file, cạnh `SxBatchIn`.)

`BatchForm` (`:168-199`) — đổi `onXong` để mang kết quả toả lên, và `luu()`:

```typescript
function BatchForm({
  cv, busy, loadLyDo, onXong, exec,
}: {
  cv: SxWorkItemChiTiet["cong_viec"]; busy: boolean;
  loadLyDo: Props["loadLyDo"]; onXong: (ketQua: SxKetQuaNhanh[]) => void; exec: ThsxExec;
}) {
  ...
  async function luu() {
    const body: SxBatchIn = {
      bat_dau: batDau, ket_thuc: ketThuc, tong: nTong, tot: nTot, hong,
      don_vi: donVi,
      nhom_loi_id: hong > 0 ? nhomLoiId : null,
      mo_ta_loi: hong > 0 && moTaLoi.trim() ? moTaLoi.trim() : null,
      ghi_chu: ghiChu.trim() || null,
    };
    const ketQua = await exec.taoBatch(body);
    if (ketQua) onXong(ketQua);
  }
  ...
```

`SanLuongSection` (`:118-165`) — state mới + banner kết quả toả, đặt ngay sau khối `thsx-x-stat`:

```typescript
function SanLuongSection({
  chiTiet, canAssign, busy, loadLyDo, exec, pbTheoBatch, tenNguoi, hoTroUngVien,
}: {
  chiTiet: SxWorkItemChiTiet; canAssign: boolean; busy: boolean;
  loadLyDo: Props["loadLyDo"]; exec: ThsxExec;
  pbTheoBatch: Map<number, SxPhanBo>; tenNguoi: Map<number, string>; hoTroUngVien: SxHoTroUngVien[];
}) {
  const sl = chiTiet.san_luong;
  const cv = chiTiet.cong_viec;
  const [formOpen, setFormOpen] = useState(false);
  const [ketQuaToa, setKetQuaToa] = useState<SxKetQuaNhanh[] | null>(null);

  return (
    <section className="thsx-psec thsx-x">
      <div className="thsx-psec__h">
        <span className="thsx-psec__title"><Icon name="layers" size={13} /> Sản lượng</span>
        {canAssign && (
          <Button variant="ghost" onClick={() => setFormOpen((o) => !o)} disabled={busy} aria-expanded={formOpen}>
            <Icon name="plus" size={13} /> Ghi mẻ
          </Button>
        )}
      </div>

      <div className="thsx-x-stat">
        <span className="thsx-x-stat__it"><b className="thsx-num">{num(sl.tong_tot)}</b> tốt</span>
        <span className="thsx-x-stat__sep">·</span>
        <span className="thsx-x-stat__it">đã giao <b className="thsx-num">{num(sl.da_giao)}</b></span>
        <span className="thsx-x-stat__sep">·</span>
        <span className="thsx-x-stat__it">còn <b className="thsx-num">{num(Math.max(0, sl.tong_tot - sl.da_giao))}</b></span>
      </div>

      {ketQuaToa && ketQuaToa.length > 0 && (
        <div className="thsx-x-toa-banner">
          <span className="thsx-x-toa-banner__title">Đã tự toả sang các lệnh sản xuất:</span>
          <ul className="thsx-x-toa-list">
            {ketQuaToa.map((k) => (
              <li key={k.lsx_id}>
                LSX #{k.lsx_id}: <b>{num(k.so_luong)}</b> {k.don_vi}
                {k.ban_giao_id != null ? " · đã tự bàn giao" : ""}
              </li>
            ))}
          </ul>
          <button
            type="button" className="thsx-x-toa-close" aria-label="Đóng"
            onClick={() => setKetQuaToa(null)}
          >
            ×
          </button>
        </div>
      )}

      {formOpen && (
        <BatchForm cv={cv} busy={busy} loadLyDo={loadLyDo}
          onXong={(kq) => { setFormOpen(false); setKetQuaToa(kq.length ? kq : null); }}
          exec={exec} />
      )}

      {sl.batches.length === 0 ? (
        <p className="thsx-note">Chưa ghi mẻ sản lượng nào.</p>
      ) : (
        <ul className="thsx-x-list">
          {sl.batches.map((b) => (
            <BatchRow key={b.id} b={b} canAssign={canAssign} busy={busy}
              pb={pbTheoBatch.get(b.id) ?? null} loadLyDo={loadLyDo}
              tenNguoi={tenNguoi} hoTroUngVien={hoTroUngVien} exec={exec} />
          ))}
        </ul>
      )}
    </section>
  );
}
```

CSS mới (`thsx-x-toa-banner`/`thsx-x-toa-list`/`thsx-x-toa-close`) — chạy `grep -rn "thsx-x-stat" frontend/src --include=*.css` để xác định đúng file CSS đang chứa các class `thsx-x-*` khác (nơi khai `.thsx-x-stat`), rồi thêm khối sau vào CUỐI file đó:

```css
.thsx-x-toa-banner {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 8px 0;
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid #b7d9c4;
  background: #eef8f1;
  font-size: 12.5px;
  color: #1f4b32;
}
.thsx-x-toa-banner__title {
  font-weight: 600;
  white-space: nowrap;
}
.thsx-x-toa-list {
  flex: 1;
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.thsx-x-toa-list li {
  line-height: 1.4;
}
.thsx-x-toa-close {
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  color: #1f4b32;
  padding: 0 2px;
}
.thsx-x-toa-close:hover {
  opacity: 0.7;
}
```

Đây là màu/khoảng cách tối giản độc lập (không phụ thuộc biến CSS chưa xác nhận tồn tại) — nếu file đích đã có biến `--*` dùng chung cho banner thành công/xanh lá (kiểm bằng `grep -n "^  --" <file>` trong cùng file), đổi các giá trị màu hex ở trên sang đúng biến đó cho nhất quán thị giác, KHÔNG bắt buộc phải giữ nguyên hex nếu đã có token sẵn.

- [ ] **Step 3: Kiểm type**

```bash
cd frontend && npx tsc --noEmit
```
Expected: 0 lỗi.

- [ ] **Step 4: Xác minh bằng dev-browser (luồng UI thật, không dùng API/curl thay bước)**

Chuẩn bị dữ liệu: cần MỘT công việc điểm-toả thật đã có cạnh toả (tức là một bài ghép đã release đúng theo Task 9 với ≥1 LSX còn bước riêng sau bước chung). Trên màn Thực hiện sản xuất:
1. Mở drawer công việc CHUNG (bước dùng chung của bài ghép, hiện trong danh sách việc của tổ đang thao tác).
2. Bấm "Ghi mẻ" → nhập Tổng/Tốt/khoảng thời gian hợp lệ → Lưu.
3. Xác nhận banner "Đã tự toả sang các lệnh sản xuất" xuất hiện NGAY, liệt kê đúng từng LSX + số lượng + "đã tự bàn giao".
4. Đóng banner (nút ×) → mở lại drawer công việc ĐÍCH của một trong các LSX đó → xác nhận mục Bàn giao đã có dòng "đã xác nhận" tương ứng số lượng vừa toả (không cần thao tác xác nhận tay).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ThsxExecPanels.tsx frontend/src/pages/ThucHienSxPage.tsx
git commit -m "Thực hiện SX FE: hiện kết quả toả theo LSX sau khi ghi mẻ sản lượng điểm toả"
```

---

### Task 15: Docs — hoàn thiện `DB_SCHEMA.md` + cập nhật 2 spec

**Files:**
- Modify: `docs/DB_SCHEMA.md` (rà lại toàn bộ thay đổi Task 6/10, đối chiếu guard test)
- Modify: `docs/spec-bai-ghep-dag.md`
- Modify: `docs/spec-thuc-hien-san-xuat.md`

**Interfaces:** Không có — thuần tài liệu, không có test tự động ngoài guard test DB_SCHEMA đã chạy ở Task 6/10.

- [ ] **Step 1: Chạy guard test DB_SCHEMA để chắc Task 6 + Task 10 đã ghi đủ**

```bash
cd backend && python -m pytest -k "db_schema" -v
```
Nếu FAIL, đọc thông báo lỗi (liệt kê đúng bảng/cột thiếu) và bổ sung vào `docs/DB_SCHEMA.md` cho khớp.

- [ ] **Step 2: Cập nhật `docs/spec-bai-ghep-dag.md`**

Thêm/sửa các mục mô tả đúng theo Architecture của plan này:
- Bốn gate cứng mới ở `thieu_cua()` (Task 1–2): liệt kê đúng 5 mã lỗi mới cùng ý nghĩa nghiệp vụ (khác giấy, bước chung thiếu thành viên, bước chung phải trên dòng giấy, vượt số con tối đa, vượt diện tích).
- Ràng buộc mới của `gop()`: chỉ gộp được các bước cùng đơn vị vào/ra và cùng kiểu in (Task 3).
- Vật tư bước chung có nguồn số lượng `dinh_muc`/`thu_cong` (Task 6–8), và dòng thủ công không bị ghi đè khi bài đổi số.
- Khái niệm ĐIỂM TOẢ được PERSISTED thành cạnh `san_xuat_phu_thuoc` lúc phát hành (Task 9) — khác với `_toa_tai` cũ (thuần bộ nhớ, chỉ phục vụ tính `so_con_tren_to` lúc lập kế hoạch).

- [ ] **Step 3: Cập nhật `docs/spec-thuc-hien-san-xuat.md`**

Thêm mục mô tả luồng sản lượng của công việc điểm-toả (Task 10–12): ghi một batch ở công việc chung → tự tách theo `ty_le_ghep` từng cạnh toả → ghi sổ `san_xuat_ket_qua_nhanh` → bàn giao THẲNG dạng đã xác nhận → LSX khác (không có phần, hoặc đã dùng hết phần) bị chặn khi cố dùng lot của batch đó. Ghi rõ đây là biến thể CỐ Ý khác `ban_giao.de_xuat()` thường (không qua đề xuất/xác nhận hai bên) và lý do (số suy một chiều, không thể vượt).

- [ ] **Step 4: Không cần commit riêng bước này — gộp cùng Step 5**

- [ ] **Step 5: Commit**

```bash
git add docs/DB_SCHEMA.md docs/spec-bai-ghep-dag.md docs/spec-thuc-hien-san-xuat.md
git commit -m "Docs: cập nhật spec bài ghép + thực hiện SX theo mô hình điểm toả"
```
