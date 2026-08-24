"""Công đoạn — service: CRUD + validate (§8).

Thân CRUD dùng chung ở `services/catalog_base.CatalogService`; ở đây chỉ còn luật riêng.
"""
from __future__ import annotations

from ..models.cong_doan import (
    CHE_DO_TINH, KIEU_BU_HAO, NHOM, PRICING_BASIS, TOOLING_TYPE, CongDoan,
)
from ..models.don_vi_do import tram_chay_xuoi
from ..repositories.cong_doan_repo import CongDoanRepository
from .catalog_base import (
    CatalogDuplicate, CatalogError, CatalogNotFound, CatalogService, CatalogValidationError,
)
from .quy_doi_service import bien_trong

# Hai chip là số của CHÍNH BƯỚC, không phải của lệnh — dùng chúng trong công thức của đơn vị RA là
# vòng tròn (xem `_validate`). Khai ở `bien_cong_thuc._BANG` với loại `quy_doi`.
_BIEN_CUA_BUOC = ("sl_vao", "sl_ra")


class CongDoanError(CatalogError):
    pass


class CongDoanValidationError(CongDoanError, CatalogValidationError):
    pass


class CongDoanDuplicate(CongDoanError, CatalogDuplicate):
    pass


class CongDoanNotFound(CongDoanError, CatalogNotFound):
    pass


class CongDoanService(CatalogService):
    LOAI = "cong_doan"
    E_NOT_FOUND = CongDoanNotFound
    E_DUPLICATE = CongDoanDuplicate
    E_VALIDATION = CongDoanValidationError
    MSG_NOT_FOUND = "Không tìm thấy công đoạn."
    MSG_DUPLICATE = "Mã công đoạn đã tồn tại."

    def __init__(self, repo: CongDoanRepository, audit=None) -> None:
        super().__init__(repo, audit)

    def _validate(self, data: dict, obj: CongDoan | None = None) -> None:
        if not (data.get("ma") or "").strip():
            raise CongDoanValidationError("Mã công đoạn không được trống.")
        if not (data.get("ten") or "").strip():
            raise CongDoanValidationError("Tên công đoạn không được trống.")
        if data.get("nhom") not in NHOM:
            raise CongDoanValidationError("Nhóm công đoạn không hợp lệ.")
        dinh_muc = data.get("dau_viec_dinh_muc") or []
        if dinh_muc:
            if data.get("department_id") is None:
                raise CongDoanValidationError("Muốn khai định mức đầu việc phải chọn tổ phụ trách.")
            ids = [int(r.get("piece_rate_id") or 0) for r in dinh_muc]
            if len(ids) != len(set(ids)):
                raise CongDoanValidationError("Một đầu việc không được chọn trùng.")
            rates = self.repo.piece_rates(set(ids))
            for r in dinh_muc:
                rid = int(r.get("piece_rate_id") or 0)
                rate = rates.get(rid)
                if rate is None or not rate.active:
                    raise CongDoanValidationError("Đầu việc không tồn tại hoặc đã ngừng dùng.")
                if rate.department_id != data.get("department_id"):
                    raise CongDoanValidationError("Đầu việc phải thuộc đúng tổ phụ trách.")
                ns = float(r.get("nang_suat_nguoi_gio") or 0)
                tt = int(r.get("so_nguoi_toi_thieu") or 1)
                tc = int(r.get("so_nguoi_tieu_chuan") or 0)
                td = int(r.get("so_nguoi_toi_da") or 0)
                if ns <= 0:
                    raise CongDoanValidationError("Năng suất một người phải lớn hơn 0.")
                if tt < 1 or tc < tt or td < tc:
                    raise CongDoanValidationError(
                        "Số người phải thỏa 1 ≤ tối thiểu ≤ tiêu chuẩn ≤ tối đa.")
                # Dải năng suất: khai mức nào thì mức đó phải đứng đúng phía của trung bình, không
                # thì "nhanh nhất" ra dài hơn "chậm nhất" và râu Gantt vẽ ngược.
                ns_min = r.get("nang_suat_nguoi_gio_min")
                ns_max = r.get("nang_suat_nguoi_gio_max")
                if ns_min is not None and float(ns_min) > ns:
                    raise CongDoanValidationError(
                        "Năng suất tối thiểu không được lớn hơn năng suất trung bình.")
                if ns_max is not None and float(ns_max) < ns:
                    raise CongDoanValidationError(
                        "Năng suất tối đa không được nhỏ hơn năng suất trung bình.")
            self._kiem_vat_tu_dau_viec(dinh_muc, self._vat_tu_dang_co(obj))
        che_do = data.get("che_do_tinh", "theo_san_luong")
        if che_do not in CHE_DO_TINH:
            raise CongDoanValidationError("Chế độ tính không hợp lệ.")
        if data.get("pricing_basis") not in PRICING_BASIS:
            raise CongDoanValidationError("Tính theo sản lượng cần pricing_basis hợp lệ. [E-CD-BASIS]")
        # GIỮ ĐƯỢC giá trị vốn có, chỉ chặn GÁN MỚI — cùng luật với đơn vị đã ngừng dùng
        # (`vat_lieu_kho_service._kiem_don_vi`). Cần vì `"kem"` vừa bị gỡ khỏi `TOOLING_TYPE`
        # (16/08/2026): công đoạn cũ nào còn mang giá trị đó thì sửa TÊN thôi cũng ăn lỗi
        # "Loại dụng cụ không hợp lệ", trong khi người dùng chẳng đụng vào ô ấy. Đo trên DB dev
        # là 0/13, nhưng prod chưa đếm được nên không đoán.
        tooling = data.get("tooling_type")
        if tooling not in (None, "") and tooling not in TOOLING_TYPE                 and tooling != getattr(obj, "tooling_type", None):
            raise CongDoanValidationError("Loại dụng cụ không hợp lệ.")
        if data.get("kieu_bu_hao", "khong") not in KIEU_BU_HAO:
            raise CongDoanValidationError("Kiểu bù hao không hợp lệ. [E-CD-BUHAO]")
        # Đơn vị vào/ra lấy từ DANH MỤC Đơn vị & quy đổi (không còn danh sách cứng 5 mã dòng giấy).
        # Ba ca hợp lệ:
        #   - cùng để TRỐNG          → bước chưa khai đơn vị (dữ liệu cũ), engine lùi về luật nhóm
        #   - hai đầu đều là TRẠM     → bước trên dòng giấy, phải đúng chiều (`tram_chay_xuoi`)
        #   - hai đầu đều NGOÀI trạm  → bước không chạm giấy (`bai → kem`, `cai → me`), tự do
        # Ca một-trong-một-ngoài (`cai → thung`) CHẶN ở lát này — xem `dong_giay.tren_dong_giay`.
        dv_vao = (data.get("don_vi_vao") or "").strip() or None
        dv_ra = (data.get("don_vi_ra") or "").strip() or None
        data["don_vi_vao"], data["don_vi_ra"] = dv_vao, dv_ra
        if (dv_vao is None) != (dv_ra is None):
            raise CongDoanValidationError(
                "Đơn vị đầu vào và đầu ra phải cùng khai, hoặc cùng để trống. [E-CD-DONVI]")
        if dv_vao is not None:
            tram = self.repo.don_vi_tram({dv_vao, dv_ra})
            if thieu := [m for m in dict.fromkeys((dv_vao, dv_ra)) if m not in tram]:
                raise CongDoanValidationError(
                    f"Đơn vị {' · '.join(thieu)} không có trong danh mục Đơn vị & quy đổi. "
                    f"Khai đơn vị ở màn Đơn vị trước. [E-CD-DONVI]")
            t_vao, t_ra = tram[dv_vao], tram[dv_ra]
            if (t_vao is None) != (t_ra is None):
                tren = dv_vao if t_vao else dv_ra
                ngoai = dv_ra if t_vao else dv_vao
                raise CongDoanValidationError(
                    f"Bước đổi từ {tren} (trên dòng giấy) sang {ngoai} (ngoài dòng giấy) chưa hỗ "
                    f"trợ — hệ số của cặp này là sức chứa của từng đơn, chưa có chỗ khai. "
                    f"[E-CD-DONVI]")
            # VÒNG TRÒN (14/08/2026, chuyển nguồn 17/08/2026): bước NGOÀI dòng giấy lấy `ra` từ
            # `cong_thuc_san_luong` của CHÍNH công đoạn (mg `0214`, trước là công thức của đơn vị
            # RA), rồi suy `vào` ngược từ `ra`. Công thức đó mà dùng `sl_vao`/`sl_ra` thì không có
            # chỗ bắt đầu — ra cần vào, vào cần ra. Chặn ngay lúc khai, đừng để lòi ra ô trống ở
            # lệnh.
            #
            # Chỉ chặn khi CẢ HAI đầu ngoài dòng giấy — trên dòng giấy thì `ra` lấy từ chuỗi bù hao,
            # cột này bị bỏ qua hoàn toàn nên chặn là chặn oan.
            if t_vao is None and t_ra is None:
                ct_sl = (data.get("cong_thuc_san_luong") or "").strip()
                if ct_sl and (lap := [b for b in bien_trong(ct_sl) if b in _BIEN_CUA_BUOC]):
                    raise CongDoanValidationError(
                        f"Công thức sản lượng dùng {' · '.join(lap)} — là số của CHÍNH bước, nên "
                        f"không tự tính được: SL ra phải xong trước thì mới suy được SL vào. Bỏ "
                        f"chip đó khỏi công thức. [E-CD-VONG-TRON]")
            if t_vao is not None and not tram_chay_xuoi(t_vao, t_ra):
                raise CongDoanValidationError(
                    f"Không quy đổi được {dv_vao} → {dv_ra}. Dòng giấy chỉ chảy một chiều: "
                    f"tờ nguyên → tờ in → con/tay → thành phẩm. [E-CD-DONVI]"
                )
        # W-CD-PRINT-SPOIL: bước in không nên có spoilage (bù hao lấy từ máy) — ép 0.
        if data.get("nhom") == "print" and data.get("spoilage_pct"):
            data["spoilage_pct"] = 0

    @staticmethod
    def _vat_tu_dang_co(obj: CongDoan | None) -> set[int]:
        """Vật tư ĐÃ khai trên công đoạn này — để `_kiem_vat_tu_dau_viec` biết cái nào là giữ lại
        chứ không phải gán mới. Rỗng khi tạo mới."""
        return {
            int(v.vat_tu_id)
            for dv in (getattr(obj, "dau_viec_dinh_muc", None) or [])
            for v in (getattr(dv, "vat_tus", None) or [])
            if v.vat_tu_id
        }

    def _kiem_vat_tu_dau_viec(self, dinh_muc: list[dict], dang_co: set[int] | None = None) -> None:
        """Vật tư gắn vào đầu việc (nền BOM, mg 0191) — id phải có thật và còn dùng.

        Vật tư đã ngừng dùng mà lọt vào đây thì tới lúc bung ở bước lệnh nó sẽ rơi im lặng (query
        bung lọc `active`), và người khai không hiểu vì sao dòng mình khai không hiện ra.
        Chỉ kiểm DANH SÁCH — không có số lượng ở tầng này, số suy lúc bung theo quy cách lệnh.

        `dang_co` = vật tư vốn đã khai trên công đoạn này. Chặn GÁN MỚI vật tư đã ngừng, nhưng
        không chặn khi giữ nguyên: nếu không thì đổi mỗi cái tên công đoạn cũng bị chặn chỉ vì một
        vật tư trong đó đã ngừng từ lâu, và người dùng không có đường nào sửa nữa.
        """
        can = {int(v) for r in dinh_muc for v in (r.get("vat_tu_ids") or [])}
        if not can:
            return
        for r in dinh_muc:
            ids = [int(v) for v in (r.get("vat_tu_ids") or [])]
            if len(ids) != len(set(ids)):
                raise CongDoanValidationError("Một vật tư không được chọn trùng trong cùng đầu việc.")
        co = self.repo.vat_tus(can)
        giu = dang_co or set()
        for vid in sorted(can):
            vt = co.get(vid)
            if vt is None:
                raise CongDoanValidationError("Vật tư không tồn tại hoặc đã ngừng sử dụng.")
            if not vt.active and vid not in giu:
                raise CongDoanValidationError(
                    f"Vật tư “{vt.ten}” đã ngừng dùng — chọn vật tư khác, "
                    f"hoặc bật lại ở màn Vật tư khác.")
            if not (vt.don_vi_gia or "").strip():
                raise CongDoanValidationError(
                    f"Vật tư “{vt.ten}” chưa chọn đơn vị tính — chưa quy đổi ra số lượng được. "
                    f"Khai đơn vị ở màn Vật tư khác trước.")

    def gan_ten_don_vi(self, items) -> None:
        """Điền TÊN đơn vị vào/ra cho cả trang bằng MỘT truy vấn.

        Bảng chỉ lưu MÃ (`to`, `cai`) mà mã không phải lúc nào cũng đọc được. Gán ở server chứ
        không để frontend tự tra: nó từng có bảng nhãn cứng riêng, và bảng đó **lệch với danh mục**
        (`to` = "Tờ in" ở danh sách nhưng "tờ" ở drawer). Một nguồn thì hết lệch, và xưởng đổi tên
        đơn vị là cả hai chỗ đổi theo.
        """
        ten = self.repo.don_vi_ten()
        for it in items:
            for dau in ("vao", "ra"):
                ma = (getattr(it, f"don_vi_{dau}", None) or "").strip().lower()
                setattr(it, f"don_vi_{dau}_ten", ten.get(ma) if ma else None)

    def dem_theo_nhom(self, **kw) -> dict[str, int]:
        """Số công đoạn theo giai đoạn — cho tab lọc của màn Công đoạn (xem repo)."""
        return self.repo.dem_theo_nhom(**kw)

    def phong_ban_options(self) -> list[dict]:
        """TỔ cho dropdown 'Phòng ban / Tổ phụ trách' ở form Công đoạn (`{id, ma, ten}`).

        Dùng ĐỊNH NGHĨA CHUNG `to_san_xuat()` = nút LÁ trong nhánh Khối Sản xuất (mục H). Trước
        đây endpoint này đổ CẢ CHA LẪN CON, nên người khai chọn được "Xưởng in" (một tầng giữa)
        làm tổ phụ trách — và quỹ giờ-người ở bàn xếp lịch đếm chồng quân số của chính tổ con.

        ⚠️ KHÔNG phá dữ liệu cũ: công đoạn đã trỏ nút cha thì GIỮ NGUYÊN giá trị đó, chỉ kèm nhãn
        "(không còn là tổ)" để người khai biết mà sửa dần. Không tự xoá, không chặn lưu, không
        đụng lệnh đang chạy — đổi định nghĩa mà đi dọn dữ liệu người ta là tự ý sửa số liệu vận
        hành.

        Ở tầng service chứ không phải router (trước 15/08/2026 nó nằm trong
        `routers/cong_doan.list_phong_ban_options`, và router tự dựng hai repository).
        """
        tos = self.repo.phong_ban_tos()
        items = [{"id": d.id, "ma": d.code, "ten": d.name} for d in tos]
        con_thieu = self.repo.department_ids_dang_dung() - {d.id for d in tos}
        if con_thieu:
            items.extend(
                {"id": d.id, "ma": d.code, "ten": f"{d.name} (không còn là tổ)"}
                for d in self.repo.phong_ban_tat_ca() if d.id in con_thieu
            )
        return items

    def dau_viec_options(self, department_id: int | None = None) -> list[dict]:
        # `don_vi` lưu MÃ (`to`, `kg`); mã trần thì người khai không đọc ra "tờ"/"kg". Gán kèm
        # `don_vi_ten` như mọi màn khác (Công việc khoán · Máy · Vật tư) để bảng định mức hiện
        # TÊN, chỉ lùi về mã khi mã lạ (ngoài danh mục Đơn vị). Một truy vấn cho cả danh sách.
        ten = self.repo.don_vi_ten()
        return [{"id": r.id, "ma": r.ma or f"DV-{r.id}", "ten": r.ten,
                 "department_id": r.department_id, "don_vi": r.unit,
                 "don_vi_ten": ten.get((r.unit or "").strip().lower()),
                 "don_gia": float(r.unit_price)}
                for r in self.repo.piece_rates_active(department_id)]
