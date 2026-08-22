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

from ..models.vat_lieu_kho import HANG_LOAI, THO
from ..repositories.audit_repo import AuditLogRepository
from ..repositories.don_vi_do_repo import DonViDoRepository
from ..repositories.purchase_repo import SupplierRepository
from ..repositories.vat_lieu_kho_repo import VERSION_SNAPSHOT, VatLieuKhoRepository
from . import nhat_ky_danh_muc as nk
from .catalog_base import (
    CatalogDuplicate, CatalogError, CatalogNotFound, CatalogValidationError,
)
from .quy_doi_service import don_vi_dung_duoc, don_vi_map

# Nhãn nhóm hiện trên picker — người chọn phải phân biệt được hai nguồn khi tên gần giống nhau.
# Tên khác `HANG_LOAI` (tuple mã hợp lệ, ở models) để không ai nhầm "danh sách mã" với "bảng nhãn".
# `thanh_pham` là MÀN danh mục thứ ba, KHÔNG phải `hang_loai` thứ ba — nó chung bảng
# `vat_tu_in_an` và với kho vẫn là "vat_tu" (xem `_mat_hang_row`, docs/prd-thanh-pham.md §3).
HANG_NHAN = {"giay": "Giấy", "vat_tu": "Vật tư khác", "thanh_pham": "Thành phẩm"}


class VatLieuKhoError(CatalogError):
    pass


class VatLieuKhoValidationError(VatLieuKhoError, CatalogValidationError):
    pass


class VatLieuKhoDuplicate(VatLieuKhoError, CatalogDuplicate):
    pass


class VatLieuKhoNotFound(VatLieuKhoError, CatalogNotFound):
    pass


def _f(v) -> float:
    return float(v) if isinstance(v, Decimal) else float(v or 0)


class VatLieuKhoService:
    def __init__(self, repo: VatLieuKhoRepository, don_vi_repo: DonViDoRepository,
                 audit: AuditLogRepository | None = None,
                 suppliers: SupplierRepository | None = None) -> None:
        self.repo = repo
        self.don_vi = don_vi_repo
        # `audit` để None được: engine tính giá dựng service này chỉ để ĐỌC danh mục, không ghi vết.
        self.audit = audit
        self.suppliers = suppliers

    # --- đơn vị tính ---------------------------------------------------------
    def _kiem_don_vi(self, ma, nhan: str, *, dang_co=None) -> None:
        """Đơn vị phải có trong danh mục `don_vi_do`. Để TRỐNG là hợp lệ ("chưa chọn").

        Không nhận đơn vị gõ tự do: mã lạ thì mọi quy đổi về sau đều tắt lặng lẽ (đồ thị không có
        nút đó), tồn kho và giá cứ thế lệch mà không ai thấy lỗi ở đâu.

        `dang_co` = đơn vị vốn đã nằm trên bản ghi. Chặn GÁN MỚI đơn vị đã ngừng dùng, nhưng KHÔNG
        chặn khi người ta giữ nguyên nó — nếu không thì sửa mỗi cái tên của một loại giấy cũ cũng
        bị chặn chỉ vì đơn vị của nó đã ngừng từ lâu (luật đã chốt cho lương 27/07).
        """
        ma = (ma or "").strip().lower()
        if not ma or ma == (dang_co or "").strip().lower():
            return
        if ma in {d.ma.strip().lower() for d in self.don_vi.all_active()}:
            return
        # Có trong danh mục nhưng đã ngừng — nói đúng bệnh, đừng bảo "không có" làm người ta đi
        # khai lại một mã đang tồn tại rồi ăn lỗi trùng mã.
        if ma in {d.ma.strip().lower() for d in self.don_vi.all_rows()}:
            raise VatLieuKhoValidationError(
                f"{nhan} “{ma}” đã ngừng dùng — chọn đơn vị khác, hoặc bật lại ở Đơn vị & quy đổi."
            )
        raise VatLieuKhoValidationError(
            f"{nhan} “{ma}” không có trong danh mục Đơn vị & quy đổi — khai ở đó trước."
        )

    def _validate(self, kind: str, data: dict, *, obj=None) -> None:
        if not (data.get("ma") or "").strip():
            raise VatLieuKhoValidationError("Mã không được trống.")
        if not (data.get("ten") or "").strip():
            raise VatLieuKhoValidationError("Tên không được trống.")
        # `chung_loai_giay` không còn ô nào cần kiểm ngoài mã/tên (gỡ `be_mat`/`tho_mac_dinh`
        # 15/08/2026) — nhánh riêng của nó bỏ luôn, đừng để lại `if` rỗng.
        # `thanh_pham` KHÔNG còn cổng nào ngoài mã/tên (21/08/2026): ô Khách hàng đã bỏ vì thành
        # phẩm là một CÁI TÊN dùng lại, không thuộc về ai. Công tắc màn nay là `la_thanh_pham`,
        # do lớp `MotDanhMucVatLieu` đặt lúc tạo — người dùng không khai.
        if kind == "giay":
            if not data.get("chung_loai_giay_id"):
                raise VatLieuKhoValidationError("Phải chọn Chủng loại giấy.")
            if _f(data.get("gsm")) <= 0:
                raise VatLieuKhoValidationError("GSM phải > 0.")
            self._kiem_don_vi(data.get("don_vi_gia"), "Đơn vị tính",
                              dang_co=getattr(obj, "don_vi_gia", None))
            if data.get("tho") not in (None, "") and data["tho"] not in THO:
                raise VatLieuKhoValidationError("Thớ không hợp lệ.")
        elif kind == "vat_tu":
            self._kiem_don_vi(data.get("don_vi_gia"), "Đơn vị tính",
                              dang_co=getattr(obj, "don_vi_gia", None))

    def get(self, kind: str, item_id: int):
        obj = self.repo.get(kind, item_id)
        if obj is None:
            raise VatLieuKhoNotFound("Không tìm thấy mặt hàng.")
        return obj

    def list(self, kind: str, **kw):
        return self.repo.list(kind, **kw)

    def create(self, kind: str, data: dict, actor_id: int | None = None):
        self._validate(kind, data)
        if self.repo.find_by_ma(kind, data["ma"]) is not None:
            raise VatLieuKhoDuplicate("Mã đã tồn tại.")
        obj = self.repo.create(kind, data)
        nk.ghi_tao(self.audit, actor_id=actor_id, loai=kind, obj=obj)
        # Repo chỉ `flush()`; chốt Ở ĐÂY để bản ghi và dòng nhật ký đi chung một giao dịch —
        # cùng luật với 7 danh mục dùng `services/catalog_base.CatalogService`.
        self.repo.chot_giao_dich()
        return obj

    def update(self, kind: str, item_id: int, data: dict, actor_id: int | None = None):
        obj = self.get(kind, item_id)
        self._validate(kind, data, obj=obj)   # `obj` để giữ được đơn vị vốn có, xem `_kiem_don_vi`
        dup = self.repo.find_by_ma(kind, data["ma"])
        if dup is not None and dup.id != obj.id:
            raise VatLieuKhoDuplicate("Mã đã tồn tại.")
        truoc = nk.anh_chup(obj)          # chụp TRƯỚC khi repo ghi đè lên chính object này
        obj = self.repo.update(obj, kind, data)
        nk.ghi_sua(self.audit, actor_id=actor_id, loai=kind, obj=obj, truoc=truoc)
        self.repo.chot_giao_dich()
        return obj

    def dat_active(self, kind: str, item_id: int, active: bool, actor_id: int | None = None):
        """BẬT / NGỪNG dùng — đổi ĐÚNG cờ `active`, không chạy `_validate`. Xem bản chú thích đầy
        đủ ở `services/catalog_base.CatalogService.dat_active` (ba danh mục này không kế thừa nền
        vì mọi phương thức của chúng nhận thêm `kind`)."""
        obj = self.get(kind, item_id)
        truoc = nk.anh_chup(obj)
        obj = self.repo.update(obj, kind, {"active": bool(active)})
        nk.ghi_sua(self.audit, actor_id=actor_id, loai=kind, obj=obj, truoc=truoc)
        self.repo.chot_giao_dich()
        return obj

    @staticmethod
    def _chan_go_tay(kind: str, viec: str) -> None:
        """Thành phẩm KHÔNG XOÁ được — dòng này có thể đang có lô tồn, xoá là làm mồ côi (PRD L7).

        Ngừng dùng thì tắt `active`, đảo lại được. Xoá thì không.

        ⚠️ TẠO thì CHO (nới 19/08/2026). Bản đầu chặn cả tạo, viện luật siết 08/08/2026 của kho —
        đọc sai: luật đó bỏ ô tên TỰ DO TRÊN PHIẾU XUẤT (`stock_request_lines.ten_tu_do`), nó
        không cấm khai danh mục. Mọi danh mục khác đều khai tay được; chặn ở đây là không cho
        Bán hàng khai trước một món khách sắp đặt.
        """
        if kind == "thanh_pham":
            raise VatLieuKhoValidationError(
                f"Không {viec} thành phẩm được — nó có thể đang có tồn kho hoặc phiếu đã ghi sổ. "
                "Muốn ngừng dùng thì tắt ô Đang dùng."
            )

    def delete(self, kind: str, item_id: int, actor_id: int | None = None) -> None:
        self._chan_go_tay(kind, "xoá")
        obj = self.get(kind, item_id)
        nk.ghi_xoa(self.audit, actor_id=actor_id, loai=kind, obj=obj)
        self.repo.delete(obj)
        self.repo.chot_giao_dich()

    def set_anh(self, kind: str, item_id: int, url: str | None):
        """Gắn/gỡ ẢNH minh hoạ cho mặt hàng GỐC (chỉ giấy / vật tư khác — chủng loại không có ảnh).

        `url` = đường `/api/files/…` đã lưu file, hoặc None để gỡ. Trả về object đã cập nhật; caller
        (router) tự xoá file cũ trên storage. Không ghi nhật ký danh mục — ảnh không phải trường giá.
        """
        if kind not in ("giay", "vat_tu"):
            raise VatLieuKhoValidationError("Loại mặt hàng không nhận ảnh.")
        obj = self.get(kind, item_id)
        return self.repo.set_anh(obj, url)

    def gan_ten_don_vi(self, items) -> None:
        """Điền TÊN đơn vị cho cả trang bằng MỘT truy vấn.

        Bảng chỉ có mã (`kem`, `to`) mà mã không phải lúc nào cũng đọc được — `kem` là "bản kẽm",
        `to` là "tờ". Gán ở đây chứ không để frontend tự tra: danh sách đơn vị chỉ được nạp trong
        drawer, cột bảng không với tới. Một `dict` cho cả trang nên không đẻ N+1.
        """
        # `all_rows` chứ không `all_active`: đây chỉ để HIỆN TÊN. Mặt hàng cũ trỏ đơn vị đã ngừng
        # mà lọc ở đây thì cột ĐVT trống trơn, người dùng tưởng chưa khai.
        ten = {(d.ma or "").strip().lower(): d.ten for d in self.don_vi.all_rows()}
        for it in items:
            ma = (getattr(it, "don_vi_gia", None) or "").strip().lower()
            if ma:
                it.don_vi_ten = ten.get(ma)

    # --- MẶT HÀNG GỐC: cửa dùng chung cho Kho + NCC ---------------------------
    @staticmethod
    def _mat_hang_row(loai: str, obj) -> dict:
        return {
            # ⚠️ MẮT XÍCH SỐ MỘT của docs/prd-thanh-pham.md §3.
            #
            # `loai` = MÀN danh mục nào (chuyện của người khai). `hang_loai` = BẢNG nào (chuyện
            # của sổ kho). Hai không gian tên khác nhau. Thành phẩm nằm chung bảng
            # `vat_tu_in_an` nên với kho nó LÀ "vat_tu".
            #
            # Trả thẳng "thanh_pham" ra đây là đẻ ra `hang_loai` thứ ba mà `stock_lots` /
            # `stock_vouchers` / `stock_requests` không nhận — kho nhập được nhưng tra ngược ra
            # rỗng, và không có lỗi nào báo.
            "hang_loai": "vat_tu" if loai == "thanh_pham" else loai,
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

    def tim_mat_hang(
        self, q: str | None = None, size: int = 20, *, chi_co_nha_cung_cap: bool = False,
    ) -> list[dict]:
        """Tìm GỘP Giấy + Vật tư khác — nguồn duy nhất của picker mặt hàng ở Kho và NCC.

        Gộp ở tầng service chứ không bắt frontend gọi hai lần rồi tự trộn: thứ tự và giới hạn số
        dòng phải nhất quán, mà quan trọng hơn là chỉ có một chỗ định nghĩa "mặt hàng gốc là gì".
        Chỉ trả hàng `active` — hàng đã ngừng dùng mà vẫn chọn được thì siết cũng như không.
        """
        moi_ben = max(1, size)
        cap_co_ncc = (
            self.suppliers.active_hang_pairs()
            if chi_co_nha_cung_cap and self.suppliers
            else None
        )
        ra: list[dict] = []
        # `thanh_pham` PHẢI có mặt: đây là ô kho gõ để chọn mặt hàng lúc nhập kho / lập phiếu.
        # Thiếu nó thì kho KHÔNG TÌM THẤY thành phẩm để nhập kho, mà ô tìm chỉ trả về rỗng —
        # không lỗi, không thông báo, không ai biết vì sao (docs/prd-thanh-pham.md §10.3).
        for loai in ("giay", "vat_tu", "thanh_pham"):
            rows, _t = self.repo.list(loai, q=q, active=True, page=1, size=moi_ben)
            ra.extend(
                self._mat_hang_row(loai, r)
                for r in rows
                if cap_co_ncc is None or (loai, r.id) in cap_co_ncc
            )
        ra.sort(key=lambda d: (d["ma"] or "").upper())
        return ra[:size]

    def _quy_cach_cua(self, loai: str, obj) -> tuple[dict | None, list[dict]]:
        """Biến cho quy đổi ĐỘNG của món. Hiện KHÔNG món nào cần biến riêng.

        GIẤY: KHÔNG bơm khổ (chủ chốt 2026-08-08 — "giấy chỉ đếm theo kg"). Về kỹ thuật thì bơm
        được, vì `giay_nguyen` có sẵn `kho_dai`/`kho_rong`; nhưng form danh mục Giấy KHÔNG có ô khổ
        (chủ bỏ 2026-07-21) nên chỉ mấy dòng do seed ghi mới có số. Bơm vào thì giấy seed đếm được
        tờ/ram còn giấy người dùng tự tạo lại không — cùng một màn, hai cách cư xử, không ai đoán
        được vì sao. Thà đồng nhất: mọi giấy chỉ đổi trong nhóm đơn vị của chính nó.

        Muốn một loại giấy đếm theo TỜ thì chọn thẳng đơn vị gốc là `tờ` — khi đó `ram ↔ tờ` (cặp
        SỐ CỐ ĐỊNH, không cần khổ) vẫn chạy và kho nhập được "10 ram". Không cần khổ cho việc đó.

        VẬT TƯ KHÁC: quy cách đóng gói ĐÃ BỎ (10/08/2026) — cần "thùng keo = 20 kg" thì khai
        thẳng đơn vị đó ở danh mục Đơn vị & quy đổi, một nơi duy nhất cho mọi quy đổi.
        """
        return None, []

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
        # `all_rows`: mặt hàng cũ có thể lấy đơn vị gốc là một đơn vị nay đã ngừng. Lọc ở đây thì
        # `quy_ve_goc` không tìm ra nút gốc và NÉM LỖI ⇒ mọi dòng phiếu kho cũ hiện cảnh báo đỏ.
        dvs = don_vi_map(self.don_vi.all_rows())
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
        truoc = nk.anh_chup(giay)
        v = self.repo.create_version(
            giay_id, data, ngay_hieu_luc=data.get("ngay_hieu_luc"),
            ghi_chu=data.get("ghi_chu"), created_by=created_by,
        )
        # Mirror bản ghi Giấy (hiện hành) = version mới nhất + số phiên bản.
        for k in VERSION_SNAPSHOT:
            if k in data and data[k] is not None:
                setattr(giay, k, data[k])
        giay.version_no = v.version_no
        self.repo.chot_giao_dich()      # trước 15/08/2026 service gọi thẳng `self.repo.db.commit()`
        # Nhập đơn giá mới là thao tác đáng soi nhất của màn Giấy → phải có trong nhật ký, và ghi
        # y như một lần sửa (Đơn giá cũ → mới) chứ không phải dòng trống "đã thêm phiên bản".
        nk.ghi_sua(self.audit, actor_id=created_by, loai="giay", obj=giay, truoc=truoc)
        return v


class MotDanhMucVatLieu:
    """MỘT trong ba danh mục của `VatLieuKhoService`, phơi ra ĐÚNG khuôn danh mục.

    `VatLieuKhoService` nhận `kind` ở MỌI phương thức (`create("giay", …)`) vì ba danh mục —
    Chủng loại giấy · Giấy · Vật tư khác — dùng chung một thân, chỉ khác model. Nền router
    (`routers/catalog_base.make_catalog_router`) thì gọi theo chữ ký chuẩn không có `kind`. Lớp
    mỏng này ghim sẵn `kind`, rẻ hơn hẳn việc nhồi vào nền một tham số chỉ ba nơi dùng.
    """

    def __init__(self, goc: VatLieuKhoService, kind: str) -> None:
        self.goc = goc
        self.kind = kind

    def list(self, **kw):
        return self.goc.list(self.kind, **kw)

    def _dung_man(self, item_id: int) -> None:
        """Chặn tra CHÉO id giữa hai màn dùng chung bảng `vat_tu_in_an`.

        "Vật tư khác" và "Thành phẩm" là hai MÀN trên cùng một bảng, chia nhau bằng
        `customer_id` (docs/prd-thanh-pham.md §3). `list()` đã lọc, nhưng đường tra theo id thì
        không — không chặn thì màn Vật tư sửa/xoá được thành phẩm qua đường vòng.

        ⚠️ Chặn Ở ĐÂY chứ KHÔNG ở repo. Bản đầu chặn trong `_VatTuRepo.get()` và VỠ ngay: kho tra
        mặt hàng `hang_loai="vat_tu"` đi qua đúng repo đó, mà thành phẩm với kho LÀ "vat_tu" —
        14 test đỏ với câu "Không tìm thấy mặt hàng." ở bước lập yêu cầu xuất kho. Lớp này thì
        chỉ nền CRUD của MÀN danh mục đi qua, kho không dùng.
        """
        if self.kind not in ("vat_tu", "thanh_pham"):
            return
        obj = self.goc.get(self.kind, item_id)      # ném NotFound nếu không có
        # ⚠️ Phân biệt bằng `la_thanh_pham` — ĐÚNG cột mà `_VatTuRepo` / `_ThanhPhamRepo` lọc.
        #
        # Đây là cột thứ BA giữ vai này, và hai cột trước đều vỡ vì cùng một lý do: chúng SUY RA
        # câu trả lời thay vì nói thẳng.
        #   · `order_line_id` (20/08/2026) — thành phẩm KHAI TAY không có nó ⇒ khai xong không
        #     sửa được, báo "Không tìm thấy mặt hàng.";
        #   · `customer_id` (mg 0204) — đúng khi thành phẩm còn thuộc về một khách, hỏng ngay khi
        #     chủ bỏ ô Khách (21/08/2026) vì dòng mới không còn khách để suy.
        # Nay là cột cờ nói thẳng, không suy từ gì cả.
        la_thanh_pham = bool(getattr(obj, "la_thanh_pham", False))
        if la_thanh_pham != (self.kind == "thanh_pham"):
            raise VatLieuKhoNotFound("Không tìm thấy mặt hàng.")

    def get(self, item_id: int):
        self._dung_man(item_id)
        return self.goc.get(self.kind, item_id)

    def create(self, data: dict, actor_id: int | None = None):
        return self.goc.create(self.kind, data, actor_id=actor_id)

    def update(self, item_id: int, data: dict, actor_id: int | None = None):
        self._dung_man(item_id)
        return self.goc.update(self.kind, item_id, data, actor_id=actor_id)

    def dat_active(self, item_id: int, active: bool, actor_id: int | None = None):
        self._dung_man(item_id)
        return self.goc.dat_active(self.kind, item_id, active, actor_id=actor_id)

    def delete(self, item_id: int, actor_id: int | None = None) -> None:
        self._dung_man(item_id)
        self.goc.delete(self.kind, item_id, actor_id=actor_id)

    def gan_ten_don_vi(self, items) -> None:
        self.goc.gan_ten_don_vi(items)
