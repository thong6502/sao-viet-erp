"""Báo sự cố tại tổ — MỘT giao dịch, hai nhánh (31/08/2026).

KHÔNG có bảng sự cố riêng. `ky_thuat_yeu_cau_sua` ("Báo máy hỏng") đã là đúng cái cần: máy, bộ
phận hỏng, mô tả, mức độ tự thấy, cờ máy dừng, người báo là tài khoản đang đăng nhập, ảnh bằng
chứng, và một đường tiếp nhận → sinh phiếu sửa chữa đã chạy. Đẻ bảng thứ hai chỉ để có chữ "sự cố"
nghĩa là tổ sửa chữa phải nhìn hai hộp thư. Cái duy nhất bảng đó còn thiếu là NEO về sản xuất —
hai cột `cong_viec_id` / `lsx_id` (mg 0248), do SERVER chốt từ công việc đang chạy.

Nhánh DỪNG SẢN XUẤT phải NGUYÊN TỬ: ghi yêu cầu · tạm dừng công việc · đóng phiên máy. Rơi giữa
chừng là để lại một công việc "đang chạy" trên cái máy đã hỏng — sản lượng và giờ máy sau đó đều
sai. Trước 31/08/2026 đường này KHÔNG nguyên tử được vì ba tầng dưới đều tự `commit`
(`KyThuatMayRepository.create_yeu_cau`, `AuditLogRepository.create`, `thuc_thi.tam_dung`); cả ba
nay nhận cờ `commit=False`, mặc định vẫn `True` nên mọi người gọi cũ không đổi hành vi.

SSE bắn SAU commit, không sớm hơn một dòng: tổ sửa chữa nhận "có máy hỏng" cho một yêu cầu vừa bị
rollback là báo động giả trỏ vào hư không.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ...models.ky_thuat_may import MUC_DO
from ...models.san_xuat import CV_DANG_CHAY, CV_TAM_DUNG
from ...realtime import hub
from ...repositories.audit_repo import AuditLogRepository
from ...repositories.ky_thuat_may_repo import KyThuatMayRepository
from ..ky_thuat_may_service import KyThuatMayError, KyThuatMayService
from . import thuc_thi

# Độ dài tối đa của `ky_thuat_yeu_cau_sua.bo_phan_hong` (String(150)) và của
# `san_xuat_phien_chay.ly_do` (String(255)) — cắt ở service để chuỗi dài không nổ ở tầng DB.
MAX_BO_PHAN_HONG = 150
MAX_LY_DO_PHIEN = 255


def _bao_tin(db: Session, svc: KyThuatMayService, yc, cv) -> None:
    """Báo tin SAU khi thao tác chính đã commit — hỏng thì NUỐT, cùng khuôn `_thu_dong_nhom`
    (`routers/san_xuat.py`).

    `bao_to_sua_chua` không phải broadcast thuần bộ nhớ: nó còn `self._may(yc.may_id)` và join vai
    để tìm người tổ sửa chữa. Máy bị xoá khỏi danh mục xen giữa, hay kết nối rớt ngay sau commit,
    sẽ ném ở đây — mà `_chay` của router không dịch được loại lỗi đó nên tổ trưởng nhận 500 và FE
    in "Lỗi mạng, thử lại" TRONG KHI sự cố đã ghi và việc đã tạm dừng thật. Tổ trưởng bấm lại là
    đẻ yêu cầu thứ hai (lần này rơi nhánh `CV_TAM_DUNG` nên không dừng thêm, chỉ làm rác hộp thư
    sửa chữa). Thao tác chính đã chốt ⇒ khâu báo tin hỏng KHÔNG được hoá 500; tổ sửa chữa vẫn
    thấy yêu cầu ở hàng chờ khi mở màn, chỉ mất cái "ting" tức thì.
    """
    try:
        svc.bao_to_sua_chua(yc)      # đẩy riêng tới từng người tổ sửa chữa (hàng chờ + badge)
        hub.broadcast({              # bàn tổ đang mở tự cập nhật trạng thái công việc
            "type": "san_xuat_cong_viec_changed",
            "team_id": cv.department_id,
            "cong_viec_id": cv.id,
            "trang_thai": cv.trang_thai,
        })
    except Exception:
        db.rollback()


def bao_su_co(
    db: Session,
    *,
    user,
    cong_viec_id: int,
    bo_phan_hong: str,
    mo_ta: str | None,
    muc_do: str,
    dung_san_xuat: bool,
    expected_version: int | None = None,
) -> dict:
    """Ghi một sự cố lên công việc đang chạy/tạm dừng, kèm tuỳ chọn dừng sản xuất.

    Trả về dict đủ cho router: khoá của `LenhKetQuaOut` (công việc + version, để FE khoá lạc quan)
    cộng `yeu_cau_id`/`yeu_cau_ma` để màn hình chỉ thẳng sang yêu cầu vừa gửi.
    """
    repo = thuc_thi.SanXuatThucThiRepository(db)
    cv = thuc_thi._lay_cong_viec(repo, cong_viec_id)
    thuc_thi._gate(db, user, cv)
    thuc_thi._kiem_version(cv, expected_version)

    if cv.trang_thai not in (CV_DANG_CHAY, CV_TAM_DUNG):
        raise ValueError("Chỉ báo sự cố trên công việc đang chạy hoặc tạm dừng.")
    if not (bo_phan_hong or "").strip():
        raise ValueError(
            "Phải nêu chỗ hỏng — một yêu cầu chỉ có tên máy thì thợ sửa phải đi hỏi lại từ đầu. "
            "Không chắc thì ghi cái nhìn thấy: “in ra bị sọc”."
        )
    if dung_san_xuat and not (mo_ta or "").strip():
        raise ValueError("Dừng sản xuất bắt buộc có lý do — đây là mốc mất giờ máy của lệnh.")
    if muc_do not in MUC_DO:
        # Ném ValueError chứ KHÔNG để `KyThuatMayValidationError` lọt lên: router dùng `_chay`,
        # vốn chỉ dịch `ValueError`/`PermissionError` — lỗi khác thành 500 thay vì 400.
        # KHÔNG có vế `muc_do and ...` (review vòng 1, Minor 4): chuỗi rỗng lọt qua thì
        # `tao_yeu_cau` âm thầm đặt `trung_binh`, và sự cố xếp trên các yêu cầu Nhẹ THẬT theo
        # `uu_tien` mà không ai từng chọn mức đó. Ở đây mức độ là bắt buộc, rỗng = chưa chọn.
        raise ValueError(f"Mức độ không hợp lệ: {muc_do!r} (nhận: {', '.join(MUC_DO)})")
    if cv.may_id is None:
        raise ValueError("Công việc này không chạy máy — không có máy để báo hỏng.")

    cho_hong = bo_phan_hong.strip()[:MAX_BO_PHAN_HONG]
    svc = KyThuatMayService(db, KyThuatMayRepository(db), AuditLogRepository(db))
    try:
        # commit=False: yêu cầu + audit + tạm dừng phải cùng sống hoặc cùng chết. `flush()` trong
        # repo đã cấp `yc.id`, còn `yc.ma` do repo sinh trước khi ghi ⇒ dùng ngay được ở lý do
        # tạm dừng bên dưới, không phải đảo thứ tự hai bước.
        yc = svc.tao_yeu_cau(
            {
                "may_id": cv.may_id,
                "bo_phan_hong": cho_hong,
                "mo_ta": (mo_ta or "").strip() or None,
                "muc_do": muc_do,
                # Người báo BIẾT CHẮC máy có dừng hay không — đây chính là câu hỏi xếp hàng chờ
                # của tổ sửa chữa, và ở đây nó trùng khít với lựa chọn Dừng sản xuất / Vẫn chạy.
                "may_dung": bool(dung_san_xuat),
            },
            actor_id=getattr(user, "id", None),
            # Neo đi bằng THAM SỐ, không nhét vào dict: dict kia là khuôn thân request của client,
            # nhét neo vào đó là mở sẵn đường cho người sau khai nó ở `YeuCauIn`.
            cong_viec_id=cv.id,
            lsx_id=cv.lsx_id,
            commit=False,
        )

        if dung_san_xuat and cv.trang_thai == CV_DANG_CHAY:
            # Máy hỏng thì việc DỪNG THẬT ⇒ đi qua lõi Tạm dừng (phiên đóng với `loai_dong=
            # tam_dung`), KHÔNG phải `doi_may`. Lý do mang theo mã yêu cầu để người đọc lịch sử
            # phiên lần được sang hồ sơ sửa chữa.
            thuc_thi._tam_dung_lo(
                db, user=user, cong_viec_id=cv.id,
                ly_do=f"Sự cố {yc.ma}: {cho_hong}"[:MAX_LY_DO_PHIEN],
            )
        db.commit()
    except KyThuatMayError as exc:
        # Lỗi nghiệp vụ của module Kỹ thuật máy (vd máy đã bị xoá khỏi danh mục) — dịch sang
        # `ValueError` để router trả 400 chứ không 500.
        db.rollback()
        raise ValueError(str(exc)) from exc
    except Exception:
        db.rollback()
        raise

    # Chốt kết quả TRƯỚC khi báo tin: `_bao_tin` có thể `rollback()` để nuốt lỗi, mà rollback làm
    # hết hạn các đối tượng đang giữ — dựng dict sau đó là bắt session đi query lại vô ích.
    ket = {
        "cong_viec_id": cv.id,
        "department_id": cv.department_id,
        "trang_thai": cv.trang_thai,
        "version": cv.version,
        "yeu_cau_id": yc.id,
        "yeu_cau_ma": yc.ma,
    }
    _bao_tin(db, svc, yc, cv)
    return ket
