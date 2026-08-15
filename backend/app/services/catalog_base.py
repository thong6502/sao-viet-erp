"""Nền chung cho các SERVICE danh mục (`kho_hang`, `bu_hao`, `khuon_be`, `don_vi_do`,
`loai_san_pham`, `may_thiet_bi`, `cong_doan`).

Vì sao có file này: bảy service danh mục viết đi viết lại đúng một khuôn — `get()` (không thấy
thì ném NotFound), `create()` (validate → canh trùng mã → ghi → ghi nhật ký), `update()` (thêm
bước chụp ảnh trước để nhật ký biết cái gì đổi), `delete()`. `kho_hang_service` và
`khuon_be_service` từng là **30 dòng chép nguyên khối, kể cả comment** — chỉ khác tên lớp
exception, chuỗi `loai=` và câu báo lỗi.

⚠️ LỚP EXCEPTION GIỮ NGUYÊN CỦA TỪNG DANH MỤC. Nền này KHÔNG ném lớp cơ sở dùng chung: router
đang viết `except KhoHangNotFound` — nền mà ném lớp khác thì router không bắt được, 404 rơi
thành 500 trong im lặng (và test HTTP vẫn xanh nếu nó chỉ kiểm đường thành công). Vì vậy service
con PHẢI khai `E_NOT_FOUND` / `E_DUPLICATE` / `E_VALIDATION` trỏ về đúng lớp của mình, kèm câu
báo lỗi tiếng Việt riêng ("Không tìm thấy kho." khác "Không tìm thấy khuôn bế.").

GIAO DỊCH — service làm chủ, repo chỉ `flush()`::

    repo.create()  →  flush (chưa chốt)
    ghi nhật ký    →  AuditLogRepository.create() commit CẢ HAI cùng lúc
    repo.chot_giao_dich()  →  chốt nốt khi không có audit (test dựng `Service(repo)` trần)

Trước 15/08/2026 repo `commit()` TRƯỚC rồi service mới ghi audit — audit nổ là **mất vết mà bản
ghi vẫn nằm đó**. Nay hai việc đi chung một giao dịch. Repo nào còn `commit_on_write = True` thì
`chot_giao_dich()` là no-op, nền vẫn chạy đúng — nhờ vậy bật/tắt được từng repo một.

CÁCH DÙNG — service con chỉ khai thuộc tính + `_validate`, không chép lại thân hàm::

    class KhuonBeService(CatalogService):
        LOAI = "khuon_be"
        E_NOT_FOUND, E_DUPLICATE, E_VALIDATION = KhuonBeNotFound, KhuonBeDuplicate, KhuonBeValidationError
        MSG_NOT_FOUND = "Không tìm thấy khuôn bế."
        MSG_DUPLICATE = "Mã khuôn đã tồn tại."
        MA_TU_SINH = True

        def _validate(self, data, obj=None): ...
"""
from __future__ import annotations

from typing import Any, ClassVar

from . import nhat_ky_danh_muc as nk


# --- Họ exception CHUNG: chỉ để NHẬN DẠNG, không để ném thẳng -----------------------------
#
# Mỗi danh mục vẫn giữ lớp riêng và câu báo lỗi riêng của nó — nhưng lớp riêng đó kế thừa THÊM
# một lớp ở đây (`class KhoHangNotFound(KhoHangError, CatalogNotFound)`). Nhờ vậy:
#
#   * `except KhoHangNotFound` ở mọi nơi cũ vẫn bắt được y nguyên — không có 404 nào rơi thành 500;
#   * `routers/catalog_base.loi_http()` soi MỘT lần theo lớp chung, thay cho BẢY bản `_err()`
#     chép tay dịch cùng một bảng (404 · 409 · 422).
#
# Đây là lý do việc hợp nhất exception phải đi CÙNG NHỊP với `_err()`: đổi một nửa là router bắt
# hụt và lỗi nghiệp vụ hoá 500 trong im lặng.
class CatalogError(Exception):
    """Gốc của mọi lỗi NGHIỆP VỤ ở tầng danh mục (không kể lỗi lập trình)."""


class CatalogValidationError(CatalogError):
    """Dữ liệu khai sai → 422."""


class CatalogDuplicate(CatalogError):
    """Trùng mã → 409 (xung đột trạng thái, không phải dữ liệu sai)."""


class CatalogNotFound(CatalogError):
    """Không có bản ghi → 404."""


class CatalogInUse(CatalogError):
    """Còn nơi dùng nên không xoá được → 409."""


class CatalogService:
    """Khuôn CRUD của một service danh mục."""

    # -- khai báo của service con -------------------------------------------------------
    LOAI: ClassVar[str] = ""
    """Khoá loại dùng cho nhật ký (`audit_logs.target` = `"{LOAI}:{id}"`). PHẢI khớp key trong
    `routers/nhat_ky_danh_muc.LOAI_MODULE`, nếu không tab Nhật ký của màn mở ra rỗng."""

    E_NOT_FOUND: ClassVar[type[Exception]] = LookupError
    E_DUPLICATE: ClassVar[type[Exception]] = ValueError
    E_VALIDATION: ClassVar[type[Exception]] = ValueError
    """Lớp exception CỦA CHÍNH danh mục — xem cảnh báo ở docstring module."""

    E_IN_USE: ClassVar[type[Exception] | None] = None
    """Lớp ném khi `_blockers()` chặn xoá. None = dùng `E_VALIDATION`."""

    MSG_NOT_FOUND: ClassVar[str] = "Không tìm thấy bản ghi."
    MSG_DUPLICATE: ClassVar[str] = "Mã đã tồn tại."
    MSG_IN_USE: ClassVar[str] = "Không xóa được — đang dùng: {ly_do}."

    MA_TU_SINH: ClassVar[bool] = False
    """True = mã do server cấp khi client không gửi (`repo.next_ma()`), và mã gửi tay trùng một
    bản ghi ĐÃ XOÁ MỀM thì TÁI DÙNG đúng hàng đó (ghi đè + bật lại `active`) thay vì báo trùng —
    hai việc này đi cùng nhau: chỉ danh mục cấp mã ngầm mới có cảnh "mã truyền tay qua API"."""

    XOA_MEM: ClassVar[bool] = False
    """True = DELETE tắt cờ `active` thay vì xoá hàng — giữ FK cho chứng từ lịch sử."""

    def __init__(self, repo, audit=None) -> None:
        """`audit` có DEFAULT `None`: nhiều test dựng service bằng `Service(repo)` trần."""
        self.repo = repo
        self.audit = audit

    # -- điểm mở rộng -------------------------------------------------------------------

    def _validate(self, data: dict, obj: Any = None) -> None:
        """Luật riêng của danh mục. `obj` = bản ghi đang sửa (None khi tạo mới) — vài danh mục
        cần nó để phân biệt "gán mới" với "giữ nguyên giá trị cũ đã ngừng dùng"."""

    def _chuan_hoa(self, data: dict) -> dict:
        """Nắn dữ liệu trước khi validate (hạ chữ, cắt khoảng trắng). Mặc định: giữ nguyên."""
        return data

    def _mac_dinh_tao(self, data: dict) -> dict:
        """Giá trị mặc định CHỈ áp lúc tạo mới (vd `hieu_luc_tu = hôm nay`)."""
        return data

    def _blockers(self, obj) -> list[str]:
        """Lý do CHẶN xoá, dạng câu ngắn ghép được ("3 lô còn tồn"). Rỗng = xoá được."""
        return []

    def _sau_ghi(self) -> None:
        """Chạy sau mọi thao tác ghi — chỗ để service con quên cache nội bộ."""

    # -- ghi nhật ký (service con ghi đè khi có quy ước riêng) ---------------------------

    def _ghi_tao(self, actor_id: int | None, obj) -> None:
        nk.ghi_tao(self.audit, actor_id=actor_id, loai=self.LOAI, obj=obj)

    def _ghi_sua(self, actor_id: int | None, obj, truoc: dict) -> None:
        nk.ghi_sua(self.audit, actor_id=actor_id, loai=self.LOAI, obj=obj, truoc=truoc)

    def _ghi_xoa(self, actor_id: int | None, obj) -> None:
        nk.ghi_xoa(self.audit, actor_id=actor_id, loai=self.LOAI, obj=obj)

    # -- đọc ----------------------------------------------------------------------------

    def get(self, item_id: int):
        obj = self.repo.get(item_id)
        if obj is None:
            raise self.E_NOT_FOUND(self.MSG_NOT_FOUND)
        return obj

    def list(self, **kw):
        return self.repo.list(**kw)

    def ma_goi_y(self) -> str:
        """Mã kế tiếp cho form khai mới. Danh mục khai mã tay (`ma_prefix` None) thì repo ném
        `NotImplementedError` — router dịch thành 404 chứ không 500."""
        return self.repo.next_ma()

    # -- ghi ----------------------------------------------------------------------------

    def _chot(self) -> None:
        """Chốt giao dịch sau khi đã ghi nhật ký. No-op với repo còn tự commit."""
        self.repo.chot_giao_dich()
        self._sau_ghi()

    def _kiem_trung_ma(self, data: dict, obj=None):
        """Trả về bản ghi trùng mã ĐÃ XOÁ MỀM để `create()` tái dùng, hoặc None.

        Trùng với bản ghi ĐANG hoạt động = trùng thật → ném luôn. Bản ghi đang sửa không tự
        trùng với chính nó.
        """
        ma = (data.get("ma") or "").strip()
        if not ma:
            return None
        dup = self.repo.find_by_ma(ma)
        if dup is None or (obj is not None and dup.id == obj.id):
            return None
        if self.MA_TU_SINH and not getattr(dup, "active", True) and obj is None:
            return dup
        raise self.E_DUPLICATE(self.MSG_DUPLICATE)

    def create(self, data: dict, actor_id: int | None = None):
        data = self._mac_dinh_tao(self._chuan_hoa(data))
        self._validate(data)
        if self.MA_TU_SINH and not (data.get("ma") or "").strip():
            # Mã sinh NGẦM: UI không cho gõ mã tay. `next_ma()` tính trên MỌI hàng (kể cả đã xóa
            # mềm) nên luôn là mã mới, không đụng ai.
            data = {**data, "ma": self.repo.next_ma()}
        cu = self._kiem_trung_ma(data)
        # Trùng bản ghi ĐÃ XÓA MỀM (chỉ khi mã truyền tay qua API) → ghi đè dữ liệu mới + bật lại
        # `active` trên đúng hàng đó, không đẻ hàng rác.
        obj = self.repo.update(cu, {**data, "active": True}) if cu is not None \
            else self.repo.create(data)
        self._ghi_tao(actor_id, obj)
        self._chot()
        return obj

    def update(self, item_id: int, data: dict, actor_id: int | None = None):
        obj = self.get(item_id)
        data = self._chuan_hoa(data)
        self._validate(data, obj)
        self._kiem_trung_ma(data, obj)
        truoc = nk.anh_chup(obj)      # chụp TRƯỚC khi repo ghi đè lên chính object này
        obj = self.repo.update(obj, data)
        self._ghi_sua(actor_id, obj, truoc)
        self._chot()
        return obj

    def dat_active(self, item_id: int, active: bool, actor_id: int | None = None):
        """BẬT / NGỪNG dùng một dòng — đổi ĐÚNG cờ `active`, KHÔNG chạy `_validate`.

        `update()` kiểm cả bản khai (mã không được trống, đơn vị phải hợp lệ…) vì nó nhận thứ
        NGƯỜI TA GÕ. Ở đây không ai gõ gì, chỉ là một cái công tắc. Đẩy `{"active": …}` qua
        `update()` thì `_validate` soi đúng cái dict một khoá đó rồi kêu "Mã không được trống" —
        cùng với chuyện `PUT` đòi schema đầy đủ, đó là hai lớp đã làm nút "Ngừng dùng"/"Bật lại"
        bấm-không-ăn ở cả bốn danh mục xoá mềm (15/08/2026).

        VẪN ghi nhật ký: ngừng dùng một dòng danh mục là việc có hệ quả trên mọi ô chọn của hệ,
        phải biết ai tắt lúc nào.
        """
        obj = self.get(item_id)
        truoc = nk.anh_chup(obj)
        obj = self.repo.update(obj, {"active": bool(active)})
        self._ghi_sua(actor_id, obj, truoc)
        self._chot()
        return obj

    def delete_blockers(self, item_id: int) -> list[str]:
        """Soi trước khi xóa — màn hỏi trước để hiện hộp thoại đúng lý do."""
        return self._blockers(self.get(item_id))

    def delete(self, item_id: int, actor_id: int | None = None) -> None:
        obj = self.get(item_id)
        if blockers := self._blockers(obj):
            loi = self.E_IN_USE or self.E_VALIDATION
            raise loi(self.MSG_IN_USE.format(ly_do="; ".join(blockers)))
        # Ghi vết TRƯỚC khi bản ghi biến mất — sau `repo.delete()` thì `obj.id` đã hết hiệu lực.
        # Đổi lại: xoá nổ sau đó sẽ để lại một dòng nhật ký thừa. Chấp nhận — thà thừa một dòng
        # còn hơn mất hẳn vết của một lần xoá.
        self._ghi_xoa(actor_id, obj)
        if self.XOA_MEM:
            self.repo.update(obj, {"active": False})
        else:
            self.repo.delete(obj)
        self._chot()
