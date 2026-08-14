"""Công đoạn — service: CRUD + validate (§8)."""
from __future__ import annotations

from ..models.cong_doan import (
    CHE_DO_TINH, KIEU_BU_HAO, NHOM, PRICING_BASIS, TOOLING_TYPE, CongDoan,
)
from ..models.don_vi_do import tram_chay_xuoi
from ..repositories.cong_doan_repo import CongDoanRepository
from .quy_doi_service import bien_trong

# Hai chip là số của CHÍNH BƯỚC, không phải của lệnh — dùng chúng trong công thức của đơn vị RA là
# vòng tròn (xem `_validate`). Khai ở `bien_cong_thuc._BANG` với loại `quy_doi`.
_BIEN_CUA_BUOC = ("sl_vao", "sl_ra")
from . import nhat_ky_danh_muc as nk


class CongDoanError(Exception):
    pass


class CongDoanValidationError(CongDoanError):
    pass


class CongDoanDuplicate(CongDoanError):
    pass


class CongDoanNotFound(CongDoanError):
    pass


class CongDoanService:
    def __init__(self, repo: CongDoanRepository, audit=None) -> None:
        self.repo = repo
        self.audit = audit

    def _validate(self, data: dict) -> None:
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
                if rate is None or not rate.is_active:
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
            self._kiem_vat_tu_dau_viec(dinh_muc)
        che_do = data.get("che_do_tinh", "theo_san_luong")
        if che_do not in CHE_DO_TINH:
            raise CongDoanValidationError("Chế độ tính không hợp lệ.")
        if data.get("pricing_basis") not in PRICING_BASIS:
            raise CongDoanValidationError("Tính theo sản lượng cần pricing_basis hợp lệ. [E-CD-BASIS]")
        if data.get("tooling_type") not in (None, "") and data["tooling_type"] not in TOOLING_TYPE:
            raise CongDoanValidationError("Loại khuôn/kẽm không hợp lệ.")
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
            # VÒNG TRÒN (14/08/2026): bước NGOÀI dòng giấy lấy `ra` từ công thức của đơn vị RA,
            # rồi suy `vào` ngược từ `ra`. Công thức đó mà dùng `sl_vao`/`sl_ra` thì không có chỗ
            # bắt đầu — ra cần vào, vào cần ra. Chặn ngay lúc khai, đừng để lòi ra ô trống ở lệnh.
            #
            # Chỉ soi đơn vị RA (chỉ nó được đọc), và chỉ khi CẢ HAI ngoài dòng — trên dòng giấy
            # thì `ra` lấy từ chuỗi, công thức của đơn vị bị bỏ qua hoàn toàn, chặn là chặn oan.
            if t_vao is None and t_ra is None:
                ct_ra = self.repo.don_vi_cong_thuc(dv_ra)
                if ct_ra and (lap := [b for b in bien_trong(ct_ra) if b in _BIEN_CUA_BUOC]):
                    raise CongDoanValidationError(
                        f"“{dv_ra}” có công thức dùng {' · '.join(lap)} — là số của CHÍNH bước, "
                        f"nên không khai làm đơn vị đầu ra được: SL ra phải tính xong trước thì "
                        f"mới suy được SL vào. Bỏ chip đó khỏi công thức, hoặc chọn đơn vị ra "
                        f"khác. [E-CD-VONG-TRON]")
            if t_vao is not None and not tram_chay_xuoi(t_vao, t_ra):
                raise CongDoanValidationError(
                    f"Không quy đổi được {dv_vao} → {dv_ra}. Dòng giấy chỉ chảy một chiều: "
                    f"tờ nguyên → tờ in → con/tay → thành phẩm. [E-CD-DONVI]"
                )
        # W-CD-PRINT-SPOIL: bước in không nên có spoilage (bù hao lấy từ máy) — ép 0.
        if data.get("nhom") == "print" and data.get("spoilage_pct"):
            data["spoilage_pct"] = 0

    def _kiem_vat_tu_dau_viec(self, dinh_muc: list[dict]) -> None:
        """Vật tư gắn vào đầu việc (nền BOM, mg 0191) — id phải có thật và còn dùng.

        Vật tư đã ngừng dùng mà lọt vào đây thì tới lúc bung ở bước lệnh nó sẽ rơi im lặng (query
        bung lọc `active`), và người khai không hiểu vì sao dòng mình khai không hiện ra.
        Chỉ kiểm DANH SÁCH — không có số lượng ở tầng này, số suy lúc bung theo quy cách lệnh.
        """
        can = {int(v) for r in dinh_muc for v in (r.get("vat_tu_ids") or [])}
        if not can:
            return
        for r in dinh_muc:
            ids = [int(v) for v in (r.get("vat_tu_ids") or [])]
            if len(ids) != len(set(ids)):
                raise CongDoanValidationError("Một vật tư không được chọn trùng trong cùng đầu việc.")
        co = self.repo.vat_tus(can)
        for vid in sorted(can):
            vt = co.get(vid)
            if vt is None or not vt.active:
                raise CongDoanValidationError("Vật tư không tồn tại hoặc đã ngừng sử dụng.")
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

    def get(self, cd_id: int) -> CongDoan:
        cd = self.repo.get(cd_id)
        if cd is None:
            raise CongDoanNotFound("Không tìm thấy công đoạn.")
        return cd

    def list(self, **kw):
        return self.repo.list(**kw)

    def dem_theo_nhom(self, **kw) -> dict[str, int]:
        """Số công đoạn theo giai đoạn — cho tab lọc của màn Công đoạn (xem repo)."""
        return self.repo.dem_theo_nhom(**kw)

    def dau_viec_options(self, department_id: int | None = None) -> list[dict]:
        return [{"id": r.id, "ma": r.code or f"DV-{r.id}", "ten": r.name,
                 "department_id": r.department_id, "don_vi": r.unit,
                 "don_gia": float(r.unit_price)}
                for r in self.repo.piece_rates_active(department_id)]

    def create(self, data: dict, actor_id: int | None = None) -> CongDoan:
        self._validate(data)
        if self.repo.find_by_ma(data["ma"]) is not None:
            raise CongDoanDuplicate("Mã công đoạn đã tồn tại.")
        cd = self.repo.create(data)
        nk.ghi_tao(self.audit, actor_id=actor_id, loai="cong_doan", obj=cd)
        return cd

    def update(self, cd_id: int, data: dict, actor_id: int | None = None) -> CongDoan:
        cd = self.get(cd_id)
        self._validate(data)
        dup = self.repo.find_by_ma(data["ma"])
        if dup is not None and dup.id != cd.id:
            raise CongDoanDuplicate("Mã công đoạn đã tồn tại.")
        truoc = nk.anh_chup(cd)
        cd = self.repo.update(cd, data)
        nk.ghi_sua(self.audit, actor_id=actor_id, loai="cong_doan", obj=cd, truoc=truoc)
        return cd

    def delete(self, cd_id: int, actor_id: int | None = None) -> None:
        cd = self.get(cd_id)
        nk.ghi_xoa(self.audit, actor_id=actor_id, loai="cong_doan", obj=cd)
        self.repo.delete(cd)
