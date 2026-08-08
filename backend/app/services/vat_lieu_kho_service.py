"""Danh mục Giấy & Vật tư — service CRUD (chủng loại giấy / giấy / vật tư in ấn).

Đây là DANH MỤC GỐC của mặt hàng: Kho và Nhà cung cấp đều trỏ về đây, không ai giữ sổ hàng riêng
nữa. Hai hệ quả nằm ở file này:

* **Đơn vị tính lấy từ `don_vi_do`**, không phải enum cứng — mỗi mặt hàng chọn một ĐƠN VỊ GỐC, và
  tồn kho cộng dồn theo đơn vị đó.
* **`tim_mat_hang` / `don_vi_cua_mat_hang`** là hai cửa duy nhất Kho + NCC dùng để chọn hàng và
  chọn đơn vị. Danh sách đơn vị TỰ THÍCH NGHI theo món (giấy có khổ → thấy tờ/ram; hoá chất không
  khổ → chỉ thấy kg/g/tấn) nhờ cạnh động bị loại khi thiếu biến.
"""
from __future__ import annotations

from decimal import Decimal

from ..models.vat_lieu_kho import BE_MAT_GIAY, HANG_LOAI, THO
from ..repositories.don_vi_do_repo import DonViDoRepository
from ..repositories.vat_lieu_kho_repo import VERSION_SNAPSHOT, VatLieuKhoRepository
from .quy_doi_service import canh_quy_cach, don_vi_dung_duoc, don_vi_map

# Nhãn nhóm hiện trên picker — người chọn phải phân biệt được hai nguồn khi tên gần giống nhau.
# Tên khác `HANG_LOAI` (tuple mã hợp lệ, ở models) để không ai nhầm "danh sách mã" với "bảng nhãn".
HANG_NHAN = {"giay": "Giấy", "vat_tu": "Vật tư khác"}


class VatLieuKhoError(Exception):
    pass


class VatLieuKhoValidationError(VatLieuKhoError):
    pass


class VatLieuKhoDuplicate(VatLieuKhoError):
    pass


class VatLieuKhoNotFound(VatLieuKhoError):
    pass


def _f(v) -> float:
    return float(v) if isinstance(v, Decimal) else float(v or 0)


class VatLieuKhoService:
    def __init__(self, repo: VatLieuKhoRepository, don_vi_repo: DonViDoRepository) -> None:
        self.repo = repo
        self.don_vi = don_vi_repo

    # --- đơn vị tính ---------------------------------------------------------
    def _kiem_don_vi(self, ma, nhan: str) -> None:
        """Đơn vị phải có trong danh mục `don_vi_do`. Để TRỐNG là hợp lệ ("chưa chọn").

        Không nhận đơn vị gõ tự do nữa: mã lạ thì mọi quy đổi về sau đều tắt lặng lẽ (đồ thị không
        có nút đó), tồn kho và giá cứ thế lệch mà không ai thấy lỗi ở đâu.
        """
        ma = (ma or "").strip().lower()
        if not ma:
            return
        if ma not in {d.ma.strip().lower() for d in self.don_vi.all_active()}:
            raise VatLieuKhoValidationError(
                f"{nhan} “{ma}” không có trong danh mục Đơn vị & quy đổi — khai ở đó trước."
            )

    def _kiem_quy_cach(self, data: dict) -> None:
        """Quy cách đóng gói: hai ô phải đi CÙNG NHAU, và phải khác đơn vị gốc."""
        dv_goi = (data.get("don_vi_dong_goi") or "").strip()
        he_so = _f(data.get("he_so_dong_goi"))
        if not dv_goi and he_so <= 0:
            return
        goc = (data.get("don_vi_gia") or "").strip()
        if not dv_goi:
            raise VatLieuKhoValidationError("Có hệ số quy cách thì phải chọn đơn vị đóng gói.")
        if he_so <= 0:
            raise VatLieuKhoValidationError(
                f"Khai hệ số quy cách: 1 {dv_goi} = ? {goc or 'đơn vị gốc'}."
            )
        if not goc:
            raise VatLieuKhoValidationError("Chọn đơn vị gốc trước rồi mới khai quy cách đóng gói.")
        if dv_goi.lower() == goc.lower():
            raise VatLieuKhoValidationError("Đơn vị đóng gói phải khác đơn vị gốc.")
        self._kiem_don_vi(dv_goi, "Đơn vị đóng gói")

    def _validate(self, kind: str, data: dict) -> None:
        if not (data.get("ma") or "").strip():
            raise VatLieuKhoValidationError("Mã không được trống.")
        if not (data.get("ten") or "").strip():
            raise VatLieuKhoValidationError("Tên không được trống.")
        if kind == "chung_loai_giay":
            if data.get("be_mat") not in (None, "") and data["be_mat"] not in BE_MAT_GIAY:
                raise VatLieuKhoValidationError("Bề mặt giấy không hợp lệ.")
            if data.get("tho_mac_dinh") not in (None, "") and data["tho_mac_dinh"] not in THO:
                raise VatLieuKhoValidationError("Thớ mặc định không hợp lệ.")
        elif kind == "giay":
            if not data.get("chung_loai_giay_id"):
                raise VatLieuKhoValidationError("Phải chọn Chủng loại giấy.")
            if _f(data.get("gsm")) <= 0:
                raise VatLieuKhoValidationError("GSM phải > 0.")
            self._kiem_don_vi(data.get("don_vi_gia"), "Đơn vị tính")
            if data.get("tho") not in (None, "") and data["tho"] not in THO:
                raise VatLieuKhoValidationError("Thớ không hợp lệ.")
        elif kind == "vat_tu":
            self._kiem_don_vi(data.get("don_vi_gia"), "Đơn vị tính")
            self._kiem_quy_cach(data)

    def get(self, kind: str, item_id: int):
        obj = self.repo.get(kind, item_id)
        if obj is None:
            raise VatLieuKhoNotFound("Không tìm thấy mặt hàng.")
        return obj

    def list(self, kind: str, **kw):
        return self.repo.list(kind, **kw)

    def create(self, kind: str, data: dict):
        self._validate(kind, data)
        if self.repo.find_by_ma(kind, data["ma"]) is not None:
            raise VatLieuKhoDuplicate("Mã đã tồn tại.")
        return self.repo.create(kind, data)

    def update(self, kind: str, item_id: int, data: dict):
        obj = self.get(kind, item_id)
        self._validate(kind, data)
        dup = self.repo.find_by_ma(kind, data["ma"])
        if dup is not None and dup.id != obj.id:
            raise VatLieuKhoDuplicate("Mã đã tồn tại.")
        return self.repo.update(obj, kind, data)

    def delete(self, kind: str, item_id: int) -> None:
        self.repo.delete(self.get(kind, item_id))

    def gan_ten_don_vi(self, items) -> None:
        """Điền TÊN đơn vị cho cả trang bằng MỘT truy vấn.

        Bảng chỉ có mã (`kem`, `to`) mà mã không phải lúc nào cũng đọc được — `kem` là "bản kẽm",
        `to` là "tờ". Gán ở đây chứ không để frontend tự tra: danh sách đơn vị chỉ được nạp trong
        drawer, cột bảng không với tới. Một `dict` cho cả trang nên không đẻ N+1.
        """
        ten = {(d.ma or "").strip().lower(): d.ten for d in self.don_vi.all_active()}
        for it in items:
            ma = (getattr(it, "don_vi_gia", None) or "").strip().lower()
            if ma:
                it.don_vi_ten = ten.get(ma)
            goi = (getattr(it, "don_vi_dong_goi", None) or "").strip().lower()
            if goi:
                it.don_vi_dong_goi_ten = ten.get(goi)

    # --- MẶT HÀNG GỐC: cửa dùng chung cho Kho + NCC ---------------------------
    @staticmethod
    def _mat_hang_row(loai: str, obj) -> dict:
        return {
            "hang_loai": loai,
            "hang_id": obj.id,
            "nhom": HANG_NHAN[loai],
            "ma": obj.ma,
            "ten": obj.ten,
            "don_vi_goc": obj.don_vi_gia or None,
        }

    def map_theo_cap(self, hangs) -> dict[tuple, object]:
        """`{(hang_loai, hang_id): bản ghi}` — nạp cả trang bằng 2 query (mỗi danh mục 1 lượt).

        Kho serialize danh sách đề nghị/phiếu/lô đều cần mã + tên mặt hàng; tra từng dòng là N+1.
        """
        can: dict[str, set[int]] = {}
        for h in hangs or []:
            loai, hid = tuple(h)
            if loai in HANG_LOAI and hid:
                can.setdefault(loai, set()).add(int(hid))
        ra: dict[tuple, object] = {}
        for loai, ids in can.items():
            for obj in self.repo.by_ids(loai, sorted(ids)):
                ra[(loai, obj.id)] = obj
        return ra

    def don_vi_goc_map(self, hangs) -> dict[tuple, str | None]:
        """Đơn vị gốc của nhiều mặt hàng — cho cột "ĐVT" của bảng tồn/lô."""
        return {k: (getattr(v, "don_vi_gia", None) or None)
                for k, v in self.map_theo_cap(hangs).items()}

    def tim_mat_hang(self, q: str | None = None, size: int = 20) -> list[dict]:
        """Tìm GỘP Giấy + Vật tư khác — nguồn duy nhất của picker mặt hàng ở Kho và NCC.

        Gộp ở tầng service chứ không bắt frontend gọi hai lần rồi tự trộn: thứ tự và giới hạn số
        dòng phải nhất quán, mà quan trọng hơn là chỉ có một chỗ định nghĩa "mặt hàng gốc là gì".
        Chỉ trả hàng `active` — hàng đã ngừng dùng mà vẫn chọn được thì siết cũng như không.
        """
        moi_ben = max(1, size)
        ra: list[dict] = []
        for loai in ("giay", "vat_tu"):
            rows, _t = self.repo.list(loai, q=q, active=True, page=1, size=moi_ben)
            ra.extend(self._mat_hang_row(loai, r) for r in rows)
        ra.sort(key=lambda d: (d["ma"] or "").upper())
        return ra[:size]

    def _quy_cach_cua(self, loai: str, obj) -> tuple[dict | None, list[dict]]:
        """Biến cho quy đổi ĐỘNG + cạnh riêng của món.

        GIẤY: KHÔNG bơm khổ (chủ chốt 2026-08-08 — "giấy chỉ đếm theo kg"). Về kỹ thuật thì bơm
        được, vì `giay_nguyen` có sẵn `kho_dai`/`kho_rong`; nhưng form danh mục Giấy KHÔNG có ô khổ
        (chủ bỏ 2026-07-21) nên chỉ mấy dòng do seed ghi mới có số. Bơm vào thì giấy seed đếm được
        tờ/ram còn giấy người dùng tự tạo lại không — cùng một màn, hai cách cư xử, không ai đoán
        được vì sao. Thà đồng nhất: mọi giấy chỉ đổi trong nhóm đơn vị của chính nó.

        Muốn một loại giấy đếm theo TỜ thì chọn thẳng đơn vị gốc là `tờ` — khi đó `ram ↔ tờ` (cặp
        SỐ CỐ ĐỊNH, không cần khổ) vẫn chạy và kho nhập được "10 ram". Không cần khổ cho việc đó.

        VẬT TƯ KHÁC: cạnh đóng gói riêng của món ("1 thùng = 3 kg").
        """
        if loai == "giay":
            return None, []
        return None, canh_quy_cach(obj.don_vi_dong_goi, obj.he_so_dong_goi, obj.don_vi_gia)

    def quy_ve_goc(self, hang_loai: str, hang_id: int, dvt: str, so_luong: float) -> dict:
        """Quy `so_luong` từ đơn vị `dvt` về ĐƠN VỊ GỐC của mặt hàng.

        MỘT cửa duy nhất cho cả đề nghị (kiểm lúc khai) lẫn phiếu (chốt lúc ghi sổ) — hai nơi tự
        tính là hai nơi có thể lệch, mà lệch ở đây là lệch tồn kho.

        Trả `{sl_goc, don_vi_goc, he_so_ve_goc, dien_giai}`. Không đổi được thì raise kèm ĐÚNG lý
        do (thiếu đường quy đổi / mặt hàng chưa khai đơn vị), chứ không lặng lẽ lấy hệ số 1 —
        hệ số 1 sai thì tồn kho sai mà không ai thấy dòng lỗi nào.
        """
        ra = self.don_vi_cua_mat_hang(hang_loai, hang_id)
        if not ra["don_vi_goc"]:
            raise VatLieuKhoValidationError(ra["ly_do"])
        ma = (dvt or "").strip().lower()
        if not ma:
            raise VatLieuKhoValidationError(f"“{ra['ten']}”: chưa chọn đơn vị tính cho dòng này.")
        hop = {d["ma"].lower(): d for d in ra["ds"]}
        # Nhận cả TÊN đơn vị ("tờ") lẫn mã ("to") — hai phía gọi tên khác nhau, xem `don_vi_map`.
        hop.update({(d["ten"] or "").strip().lower(): d for d in ra["ds"] if d["ten"]})
        d = hop.get(ma)
        if d is None:
            duoc = ", ".join(x["ten"] for x in ra["ds"]) or "(chưa có đơn vị nào)"
            raise VatLieuKhoValidationError(
                f"“{ra['ten']}” không đổi được từ “{dvt}” về {ra['don_vi_goc_ten']}. "
                f"Đơn vị dùng được: {duoc}."
            )
        return {
            "sl_goc": float(so_luong) * float(d["he_so_ve_goc"]),
            "don_vi_goc": ra["don_vi_goc"],
            "don_vi_goc_ten": ra["don_vi_goc_ten"],
            "he_so_ve_goc": float(d["he_so_ve_goc"]),
            "dien_giai": d["dien_giai"],
        }

    def don_vi_cua_mat_hang(self, hang_loai: str, hang_id: int) -> dict:
        """Đơn vị gốc + MỌI đơn vị đổi được với nó — nguồn của dropdown ĐVT ở Kho / NCC."""
        if hang_loai not in HANG_LOAI:
            raise VatLieuKhoValidationError("Loại mặt hàng không hợp lệ.")
        obj = self.get(hang_loai, hang_id)
        goc = (obj.don_vi_gia or "").strip()
        dvs = don_vi_map(self.don_vi.all_active())
        if not goc:
            # Chưa khai đơn vị gốc → KHÔNG đoán. UI khoá ô ĐVT và chỉ đường về danh mục.
            return {"hang_loai": hang_loai, "hang_id": obj.id, "ma": obj.ma, "ten": obj.ten,
                    "don_vi_goc": None, "don_vi_goc_ten": None, "ds": [],
                    "ly_do": f"“{obj.ten}” chưa chọn đơn vị tính — khai ở Cấu hình danh mục "
                             f"→ {HANG_NHAN[hang_loai]}."}
        quy_cach, canh_them = self._quy_cach_cua(hang_loai, obj)
        ds = don_vi_dung_duoc(goc, dvs, list(self.don_vi.cap_rows()) + canh_them, quy_cach)
        return {
            "hang_loai": hang_loai, "hang_id": obj.id, "ma": obj.ma, "ten": obj.ten,
            "don_vi_goc": goc,
            "don_vi_goc_ten": (dvs.get(goc.lower()) or {}).get("ten") or goc,
            "ds": ds, "ly_do": None,
        }

    # -- Phiên bản giá giấy (lịch sử) --
    def _ensure_v1(self, giay) -> None:
        """Backfill v1 từ bản ghi Giấy hiện tại nếu chưa có phiên bản nào (giấy tạo trước tính năng)."""
        if not self.repo.has_versions(giay.id):
            snap = {k: getattr(giay, k, None) for k in VERSION_SNAPSHOT}
            self.repo.create_version(giay.id, snap, ghi_chu="Phiên bản đầu")

    def list_giay_versions(self, giay_id: int):
        giay = self.get("giay", giay_id)
        self._ensure_v1(giay)
        return self.repo.list_versions(giay_id)

    def add_giay_version(self, giay_id: int, data: dict, created_by: int | None = None):
        giay = self.get("giay", giay_id)
        if _f(data.get("gsm")) <= 0:
            raise VatLieuKhoValidationError("GSM phải > 0.")
        self._kiem_don_vi(data.get("don_vi_gia"), "Đơn vị tính")
        self._ensure_v1(giay)
        v = self.repo.create_version(
            giay_id, data, ngay_hieu_luc=data.get("ngay_hieu_luc"),
            ghi_chu=data.get("ghi_chu"), created_by=created_by,
        )
        # Mirror bản ghi Giấy (hiện hành) = version mới nhất + số phiên bản.
        for k in VERSION_SNAPSHOT:
            if k in data and data[k] is not None:
                setattr(giay, k, data[k])
        giay.version_no = v.version_no
        self.repo.db.commit()
        return v
