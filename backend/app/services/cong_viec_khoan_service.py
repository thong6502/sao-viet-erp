"""Công việc khoán — service: CRUD trên nền `CatalogService` + luật riêng của bảng đơn giá.

Bảng `piece_rates` vào Cấu hình danh mục ngày 17/08/2026. Thân CRUD (canh trùng mã · ghi nhật ký
trong CÙNG giao dịch · mã tự sinh · bật/tắt bằng `dat_active`) nằm ở `services/catalog_base`; ở đây
chỉ còn ba việc bảng này khác 8 danh mục kia:

* `group_name` (nhãn tổ trên dòng) SUY từ `department_id` — client không gửi. Một sự thật một chỗ.
* Xoá: đơn giá bị `cong_doan_dau_viec.piece_rate_id` trỏ tới bằng ID THẬT, và bị bước lệnh / bài
  ghép GHIM ảnh chụp (`khoan_json.rate_id`). Còn nơi dùng ⇒ chỉ ngừng dùng, `_blockers` đếm hộ.
* Đơn vị lưu ĐÚNG chữ nhận được, chỉ cắt khoảng trắng — quyết định 31/07/2026 giữ nguyên: dòng cũ,
  seed và import đều mang đơn vị ngoài danh mục, chặn ở service là khoá luôn đường sửa chúng.
"""
from __future__ import annotations

from ..models.piece_work import UNIT_KHAC
from ..repositories.cong_viec_khoan_repo import CongViecKhoanRepository
from .catalog_base import (
    CatalogDuplicate, CatalogError, CatalogInUse, CatalogNotFound, CatalogService,
    CatalogValidationError,
)


class CongViecKhoanError(CatalogError):
    pass


class CongViecKhoanValidationError(CongViecKhoanError, CatalogValidationError):
    pass


class CongViecKhoanDuplicate(CongViecKhoanError, CatalogDuplicate):
    pass


class CongViecKhoanNotFound(CongViecKhoanError, CatalogNotFound):
    pass


class CongViecKhoanInUse(CongViecKhoanError, CatalogInUse):
    pass


class CongViecKhoanService(CatalogService):
    """`audit` có DEFAULT `None` để test dựng `CongViecKhoanService(repo)` trần."""

    LOAI = "cong_viec_khoan"
    E_NOT_FOUND = CongViecKhoanNotFound
    E_DUPLICATE = CongViecKhoanDuplicate
    E_VALIDATION = CongViecKhoanValidationError
    E_IN_USE = CongViecKhoanInUse
    MSG_NOT_FOUND = "Không tìm thấy công việc khoán."
    MSG_DUPLICATE = "Mã công việc khoán đã tồn tại."
    MSG_IN_USE = "Không xóa được — công việc này đang dùng: {ly_do}."
    # Mã do máy cấp (`KH-####`): màn không có ô Mã lúc tạo. Kèm theo đó, mã truyền tay qua API mà
    # trùng một dòng ĐÃ ngừng dùng thì tái dùng đúng dòng đó — xem `CatalogService.MA_TU_SINH`.
    MA_TU_SINH = True

    def __init__(self, repo: CongViecKhoanRepository, audit=None) -> None:
        super().__init__(repo, audit)

    # -- luật riêng ---------------------------------------------------------------------

    def _chuan_hoa(self, data: dict) -> dict:
        """Cắt khoảng trắng đơn vị + suy `group_name` từ tổ.

        `group_name` là NHÃN hiển thị, `department_id` là con trỏ. Client chỉ chọn tổ; nhãn lấy tên
        tổ ĐANG dùng để bảng không mang tên tổ của tháng trước. Tổ không còn tồn tại (id lạ) thì
        giữ nhãn cũ chứ không ghi đè bằng chuỗi rỗng — `group_name` là cột NOT NULL.
        """
        data = dict(data)
        if "unit" in data:
            data["unit"] = str(data.get("unit") or UNIT_KHAC).strip() or UNIT_KHAC
        if "department_id" in data:
            ten_to = self.repo.ten_to(data.get("department_id"))
            if ten_to:
                data["group_name"] = ten_to[:40]
        return data

    def _validate(self, data: dict, obj=None) -> None:
        if not (data.get("ten") or "").strip():
            raise CongViecKhoanValidationError("Tên công việc không được trống.")
        # Tổ là bắt buộc khi TẠO MỚI: bảng gom theo tổ, dòng không tổ rơi vào tab "chưa khai" và
        # không đầu việc nào của lệnh tìm thấy nó. Dòng CŨ chưa gắn tổ vẫn sửa được (obj != None)
        # — chặn cả đường sửa là khoá luôn cách duy nhất để gắn tổ cho chúng.
        #
        # `group_name` ở đây là kết quả của `_chuan_hoa`: rỗng nghĩa là KHÔNG tra ra tên tổ. Nên hai
        # ca lỗi khác nhau cần hai câu khác nhau — chưa chọn gì, và chọn một id không có thật (form
        # cầm id cũ của tổ đã xoá). Gộp một câu thì người khai sửa mãi không đúng chỗ.
        if obj is None and not (data.get("group_name") or "").strip():
            raise CongViecKhoanValidationError(
                "Không tìm thấy tổ đã chọn." if data.get("department_id")
                else "Chưa chọn tổ cho công việc khoán."
            )
        # Đường SỬA: chỉ chặn khi người ta ĐỔI SANG một tổ không có thật. Gửi lại đúng tổ cũ thì cho
        # qua kể cả khi tổ đó đã bị xoá khỏi cây tổ chức — form load ra chính giá trị đang lưu, chặn
        # cả ca đó là khoá luôn đường sửa tên/đơn giá của dòng ấy (giữ giá trị vốn có).
        if obj is not None and "department_id" in data:
            moi = data.get("department_id")
            if moi and moi != obj.department_id and not self.repo.ten_to(moi):
                raise CongViecKhoanValidationError("Không tìm thấy tổ đã chọn.")
        gia = data.get("unit_price")
        if gia is None and obj is None:
            raise CongViecKhoanValidationError("Thiếu đơn giá.")
        if gia is not None and float(gia) < 0:
            raise CongViecKhoanValidationError("Đơn giá không được âm.")

    def _blockers(self, obj) -> list[str]:
        """Nơi ĐANG DÙNG dòng này — có thì `delete()` trả 409 kèm lý do tiếng Việt.

        Cùng bộ đếm với hộp thoại xoá của màn (`GET /api/danh-muc/{loai}/{id}/kiem-xoa`), nên hai
        cửa không bao giờ trả lời khác nhau: màn hỏi trước để chọn "xoá hẳn" hay "ngừng dùng",
        service là cửa chặn thật cho ai gọi API trực tiếp.
        """
        from .danh_muc_tham_chieu import tham_chieu

        return tham_chieu(self.repo.db, self.LOAI, obj).chan

    # -- đọc ---------------------------------------------------------------------------

    def gan_ten_don_vi(self, objs: list) -> None:
        """Điền `don_vi_ten` cho cả trang bằng MỘT truy vấn.

        Bảng lưu MÃ đơn vị (`to`, `kg`) như `giay.don_vi_gia`; mã trần thì người đọc không hiểu
        ("kem" không ai đoán ra "bản kẽm"). Mã không có trong danh mục ⇒ để `None`, màn hiện nguyên
        mã kèm dấu hiệu chứ không bỏ trắng.
        """
        ten = self.repo.ten_don_vi({str(getattr(o, "unit", "") or "") for o in objs})
        for o in objs:
            o.don_vi_ten = ten.get(str(getattr(o, "unit", "") or "").strip().lower())

    def dem_theo_to(self, **kw) -> dict[str, int]:
        return self.repo.dem_theo_to(**kw)
