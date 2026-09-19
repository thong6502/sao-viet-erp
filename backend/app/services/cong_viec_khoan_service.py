"""Công việc khoán — service: CRUD trên nền `CatalogService` + luật riêng của bảng đơn giá.

Bảng `piece_rates` vào Cấu hình danh mục ngày 17/08/2026. Thân CRUD (canh trùng mã · ghi nhật ký
trong CÙNG giao dịch · mã tự sinh · bật/tắt bằng `dat_active`) nằm ở `services/catalog_base`; ở đây
chỉ còn ba việc bảng này khác 8 danh mục kia:

* TỔ là DANH SÁCH (`department_ids`, bảng nối `cong_viec_khoan_to`, 17/09/2026) — một việc làm được
  ở nhiều tổ, cùng một đơn giá. Tạo mới phải có ít nhất một tổ, tổ phải có thật.
* Xoá: đơn giá bị MẺ SẢN XUẤT trỏ tới bằng ID THẬT (`san_xuat_batch.piece_rate_id`, 18/09/2026).
  Còn nơi dùng ⇒ chỉ ngừng dùng, `_blockers` đếm hộ.
* Đơn vị lưu ĐÚNG chữ nhận được, chỉ cắt khoảng trắng — quyết định 31/07/2026 giữ nguyên: dòng cũ,
  seed và import đều mang đơn vị ngoài danh mục, chặn ở service là khoá luôn đường sửa chúng.
* VIỆC PHÁT SINH (bảng con `cong_viec_khoan_phat_sinh`, 14/09/2026): ba ô tên · đơn giá · đơn vị,
  kiểm ở `_kiem_viec_phat_sinh`, nhân bản chép theo ở `_anh_chup_nhan_ban`.
* CÔNG THỨC KHOÁN (`cong_thuc_khoan`, 18/09/2026, mg `0317`) — tab thứ hai của drawer. Soi bằng
  `kiem_cong_thuc` họ `quy_doi` như mọi ô công thức khác, để câu lỗi là tiếng Việt chứ không 500.
"""
from __future__ import annotations

from ..models.piece_work import UNIT_KHAC
from ..repositories.cong_viec_khoan_repo import CongViecKhoanRepository
from .bien_cong_thuc import LOAI_QUY_DOI
from .catalog_base import (
    CatalogDuplicate, CatalogError, CatalogInUse, CatalogNotFound, CatalogService,
    CatalogValidationError,
)
from .thanh_phan_engine import kiem_cong_thuc


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
        """Cắt khoảng trắng đơn vị + khử trùng danh sách tổ (giữ thứ tự chọn).

        `department_ids = None` là VẮNG (giữ nguyên danh sách đang có) — bỏ khoá hẳn để repo không
        tưởng đó là "xoá hết tổ".
        """
        data = dict(data)
        if "unit" in data:
            data["unit"] = str(data.get("unit") or UNIT_KHAC).strip() or UNIT_KHAC
        if "cong_thuc_khoan" in data:
            # Khoảng trắng thừa làm `if cong_thuc:` ở engine tưởng có khai rồi `safe_eval("  ")` nổ
            # — cùng luật đang áp cho các ô công thức của màn Công đoạn.
            data["cong_thuc_khoan"] = (str(data.get("cong_thuc_khoan") or "").strip()) or None
        if "department_ids" in data:
            ids = data.get("department_ids")
            if ids is None:
                data.pop("department_ids")
            else:
                data["department_ids"] = list(dict.fromkeys(int(i) for i in ids if i))
        if isinstance(data.get("viec_phat_sinh"), list):
            # Mã đơn vị hạ chữ thường: danh mục Đơn vị lưu mã thường (`don_vi_do_repo.ma_case`).
            data["viec_phat_sinh"] = [
                {**r, "ten": str(r.get("ten") or "").strip(),
                 "don_vi": str(r.get("don_vi") or "").strip().lower()}
                for r in data["viec_phat_sinh"]
            ]
        return data

    def _validate(self, data: dict, obj=None) -> None:
        if not (data.get("ten") or "").strip():
            raise CongViecKhoanValidationError("Tên công việc không được trống.")
        self._kiem_to(data, obj)
        gia = data.get("unit_price")
        if gia is None and obj is None:
            raise CongViecKhoanValidationError("Thiếu đơn giá.")
        if gia is not None and float(gia) < 0:
            raise CongViecKhoanValidationError("Đơn giá không được âm.")
        if isinstance(data.get("viec_phat_sinh"), list):
            self._kiem_viec_phat_sinh(data["viec_phat_sinh"])
        if data.get("cong_thuc_khoan"):
            try:
                kiem_cong_thuc(data["cong_thuc_khoan"], nhan="Công thức khoán", loai=LOAI_QUY_DOI)
            except ValueError as e:
                raise CongViecKhoanValidationError(str(e)) from e

    def _kiem_to(self, data: dict, obj=None) -> None:
        """Luật chọn TỔ — ít nhất một tổ, và tổ MỚI thêm vào phải có thật.

        Tạo mới thiếu tổ thì chặn: dòng không tổ không đầu việc nào của lệnh tìm thấy. Sửa mà gửi
        danh sách RỖNG cũng chặn — đó là gỡ hết tổ, việc thành mồ côi; muốn thôi dùng thì Ngừng dùng.
        Dòng đời cũ chưa có tổ vẫn sửa được tên/đơn giá khi client KHÔNG gửi `department_ids`.

        Tổ không có thật chỉ chặn khi nó là tổ MỚI thêm: form nạp lại đúng danh sách đang lưu, kể cả
        một tổ đã bị xoá khỏi cây tổ chức — chặn cả ca đó là khoá luôn đường sửa đơn giá của dòng.

        Gỡ tổ KHÔNG bị chặn nữa (18/09/2026): công đoạn thôi khai đầu việc nên chẳng còn định mức
        nào mồ côi. Tổ hết việc khoán thì cổng "Sẵn sàng lập kế hoạch" của lệnh báo thiếu.
        """
        if "department_ids" not in data:
            if obj is None:
                raise CongViecKhoanValidationError("Chưa chọn tổ cho công việc khoán.")
            return
        ids = data["department_ids"]
        if not ids:
            raise CongViecKhoanValidationError("Chưa chọn tổ cho công việc khoán.")
        cu = set(obj.department_ids) if obj is not None else set()
        # ⚠️ Cổng "gỡ tổ mà công đoạn còn khai định mức đầu việc này" GỠ 18/09/2026 (mg `0320`):
        #    công đoạn thôi khai đầu việc nên không còn định mức nào mồ côi được. Hậu quả của việc
        #    tổ hết việc khoán chuyển sang CỔNG "Sẵn sàng lập kế hoạch" của lệnh
        #    (`thieu_viec_khoan_to`) — chặn đúng lúc nó gây hại, không chặn ở danh mục.
        moi = [i for i in ids if i not in cu]
        co_that = self.repo.to_theo_id(set(moi))
        if any(i not in co_that for i in moi):
            raise CongViecKhoanValidationError("Không tìm thấy tổ đã chọn.")

    def _kiem_viec_phat_sinh(self, rows: list[dict]) -> None:
        """Luật khai VIỆC PHÁT SINH — đủ ba ô, tên không trùng trong cùng công việc khoán.

        Câu lỗi gọi TÊN việc (hoặc số dòng khi chưa có tên): danh sách dài vài dòng, báo chung
        chung thì người khai phải soi từng dòng mới ra chỗ sai.

        Đơn vị PHẢI có trong danh mục Đơn vị & quy đổi — khác ô `unit` của cha (còn nhận chữ ngoài
        danh mục để đỡ dòng đời cũ). Bảng này mới, không có dòng cũ nào cần đỡ; chặn từ đầu thì sau
        này quy đổi/tính lương không vấp một mã lạ nào.
        """
        da_co: set[str] = set()
        for i, r in enumerate(rows, start=1):
            ten = r.get("ten") or ""
            if not ten:
                raise CongViecKhoanValidationError(
                    f"Tên việc phát sinh (dòng {i}) không được trống.")
            khoa = " ".join(ten.lower().split())
            if khoa in da_co:
                raise CongViecKhoanValidationError(f'Việc phát sinh "{ten}" bị trùng tên.')
            da_co.add(khoa)
            gia = r.get("don_gia")
            if gia is None:
                raise CongViecKhoanValidationError(
                    f'Chưa nhập đơn giá cho việc phát sinh "{ten}".')
            if float(gia) < 0:
                raise CongViecKhoanValidationError(
                    f'Đơn giá của việc phát sinh "{ten}" không được âm.')
            if not r.get("don_vi"):
                raise CongViecKhoanValidationError(
                    f'Chưa chọn đơn vị tính cho việc phát sinh "{ten}".')
        co_that = self.repo.ten_don_vi({r["don_vi"] for r in rows})
        for r in rows:
            if r["don_vi"] not in co_that:
                raise CongViecKhoanValidationError(
                    f'Đơn vị tính "{r["don_vi"]}" của việc phát sinh "{r["ten"]}" không có trong '
                    "danh mục Đơn vị & quy đổi.")

    def _blockers(self, obj) -> list[str]:
        """Nơi ĐANG DÙNG dòng này — có thì `delete()` trả 409 kèm lý do tiếng Việt.

        Cùng bộ đếm với hộp thoại xoá của màn (`GET /api/danh-muc/{loai}/{id}/kiem-xoa`), nên hai
        cửa không bao giờ trả lời khác nhau: màn hỏi trước để chọn "xoá hẳn" hay "ngừng dùng",
        service là cửa chặn thật cho ai gọi API trực tiếp.
        """
        from .danh_muc_tham_chieu import tham_chieu

        return tham_chieu(self.repo.db, self.LOAI, obj).chan

    def _anh_chup_nhan_ban(self, goc) -> dict:
        """Bản sao chép luôn các việc phát sinh — thành dòng MỚI (không id), không dùng chung dòng
        với bản gốc. Ảnh chụp nhật ký mang chúng dưới dạng chữ để so, không dựng lại được."""
        data = super()._anh_chup_nhan_ban(goc)
        data["department_ids"] = list(goc.department_ids)
        data["cong_thuc_khoan"] = goc.cong_thuc_khoan
        data["viec_phat_sinh"] = [
            {"ten": v.ten, "don_gia": float(v.don_gia), "don_vi": v.don_vi}
            for v in goc.viec_phat_sinh
        ]
        return data

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

    def gan_to(self, objs: list) -> None:
        """Điền `tos` (id · mã · tên từng tổ) cho cả trang bằng MỘT truy vấn.

        Tổ đã bị xoá khỏi cây tổ chức vẫn nằm trong danh sách với `ten = None` — màn đánh dấu để
        người khai tự gỡ, không lặng lẽ bỏ nó đi (bỏ đi rồi bấm Lưu là mất dấu).
        """
        tra = self.repo.to_theo_id({i for o in objs for i in o.department_ids})
        for o in objs:
            o.tos = []
            for i in o.department_ids:
                ma, ten = tra.get(i, (None, None))
                o.tos.append({"id": i, "ma": ma, "ten": ten})

    def dem_theo_to(self, **kw) -> dict[str, int]:
        return self.repo.dem_theo_to(**kw)

    def dem_tong(self, **kw) -> int:
        return self.repo.dem_tong(**kw)
