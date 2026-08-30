"""Tổ trưởng đề nghị cấp vật tư cho công đoạn của mình (spec-de-nghi-cap-vat-tu-cong-doan §5).

Ranh giới an ninh THỰC nằm ở đây, không ở router: router chỉ gác bit thô `san_xuat:assign_work`
(mọi tổ trưởng SX đều có), còn "đúng tổ nào" thì chỉ tầng này biết. Tái dùng `_gate_to_truong` của
`vat_tu_nhan.py` — hai cổng cùng nghĩa mà viết hai lần là mời chúng lệch nhau.

Hai thang đơn vị chạy song song trong `tao()` (ruling 10): `SanXuatVatTuDeNghiDong.sl_yeu_cau` là
đơn vị TỔ KHAI (tờ, ram…) — giữ để bản đối chiếu hiện đúng chữ tổ gõ. `sl_yeu_cau_goc`/`dvt_goc` là
đơn vị GỐC — dùng để so lệch kế hoạch VÀ để gửi kho (`StockRequestLine.sl_de_nghi`/`dvt`). Giấy khai
bằng "tờ" không có cạnh quy đổi tĩnh sang đơn vị gốc (đo thật: "Ivory 350" không đổi được từ "to" về
tấn — xem `_ve_goc_dong`), nên `ve_don_vi_goc` ném lỗi và `StockRequestService.create` cũng chặn
`dvt="to"`. So sánh giữa `SanXuatVatTuDeNghiDong` và `StockRequestLine` vì thế PHẢI đi qua cặp
`sl_yeu_cau_goc`/`dvt_goc`, không phải `sl_yeu_cau`/`dvt`.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ...models.san_xuat_vat_tu import (
    DN_BO_SUNG, DN_LAN_DAU, SanXuatVatTuDeNghi, SanXuatVatTuDeNghiDong,
)
from ...models.stock_request import REQ_XUAT
from ...repositories.audit_repo import AuditLogRepository
from ...repositories.san_xuat_repo import SanXuatRepository
from ...repositories.san_xuat_vat_tu_repo import SanXuatVatTuRepository
from ...realtime import hub
from ..ke_hoach_vat_tu_service import KeHoachVatTuError
from .vat_tu_nhan import _gate_to_truong

_EPS = 0.0005      # cùng dung sai làm tròn với `san_luong.tao_batch`


class VatTuDeNghiError(Exception):
    """Lỗi NGHIỆP VỤ (400) — khác `PermissionError` (403)."""


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _ve_goc_dong(kh_svc, k, k_row, dvt, sl):
    """Quy số tổ khai về đơn vị gốc. Trả `(sl_goc, dvt_goc, theo_goc: bool)`.

    Giấy khai bằng "tờ" không có cạnh quy đổi tĩnh sang tấn (ruling 10). Ba nhánh:
      (1) tổ giữ NGUYÊN đơn vị kế hoạch ⇒ nội suy theo TỈ LỆ mà chính engine vừa tính cho ĐÚNG
          lệnh này (đã dùng khổ giấy thật): `sl * sl_goc_kh / sl_kh`. Chính xác, không cần cạnh
          quy đổi nào. Đây là ca thường gặp nhất.
      (2) tổ ĐỔI đơn vị, hoặc dòng ngoài kế hoạch ⇒ cầu quy đổi tĩnh (`ve_don_vi_goc`).
      (3) không quy được: nếu tổ đang xin số DƯƠNG thì NỔ lỗi nghiệp vụ — ta không thể xin kho
          một lượng không diễn đạt được bằng đơn vị kho nhận (`create` sẽ chặn y hệt). Nếu tổ xin
          0 thì không cần số gốc: trả 0 + `theo_goc=False`, `_chuan_hoa` so lệch theo đơn vị
          hiển thị.
    Ca `kh_row["sl_goc"] == 0` là có thật: mặt hàng chưa khai công thức lượng thì chính bảng cân
    đối cũng để `nhu_cau = 0` và gắn cảnh báo. Nó rơi vào nhánh (2)→(3) đúng như trên.
    """
    kh_sl = _f((k_row or {}).get("sl"))
    kh_goc = _f((k_row or {}).get("sl_goc"))
    cung_dvt = k_row is not None and (dvt or "") == (k_row.get("dvt") or "")
    if cung_dvt and kh_sl > _EPS and kh_goc > _EPS:
        return sl * kh_goc / kh_sl, k_row.get("dvt_goc") or "", True
    try:
        sl_goc, dvt_goc = kh_svc.ve_don_vi_goc(k[0], k[1], dvt, sl)
    except KeHoachVatTuError as e:
        if sl > _EPS:
            raise VatTuDeNghiError(str(e)) from None
        return 0.0, (k_row or {}).get("dvt_goc") or "", False
    return sl_goc, dvt_goc, True


def _chuan_hoa(db, kh_svc, cv, lines: list[dict], *, bat_buoc_ly_do: bool) -> list[dict]:
    """Trộn kế hoạch với số tổ khai, QUY ĐỔI LẠI ở BE, và bắt lý do đúng luật (§3, §4).

    Không tin đơn vị/số của client: nó chỉ nói "xin 3 ram" — quy 3 ram ra bao nhiêu kg là việc của
    engine đơn vị, và phải là CÙNG engine mà bảng cân đối dùng, không thì hai bên đếm hai kiểu.
    """
    kh = {(k["hang_loai"], int(k["hang_id"])): k for k in kh_svc.nhu_cau_cua_cong_viec(cv)}
    khai: dict[tuple, dict] = {}
    for ln in lines:
        k = (ln["hang_loai"], int(ln["hang_id"]))
        if k in khai:
            raise VatTuDeNghiError("Một mặt hàng chỉ được khai một dòng — gộp số lượng lại.")
        khai[k] = ln

    ra: list[dict] = []
    for k in list(kh) + [k for k in khai if k not in kh]:
        k_row = kh.get(k)
        ln = khai.get(k)
        # Dòng NGOÀI kế hoạch mà xin 0 là vô nghĩa — không lưu (§4).
        if k_row is None and (ln is None or _f(ln.get("sl_yeu_cau")) <= _EPS):
            continue
        dvt = (ln or {}).get("dvt") or (k_row or {})["dvt"]
        sl = _f((ln or {}).get("sl_yeu_cau"))
        sl_goc, dvt_goc, theo_goc = _ve_goc_dong(kh_svc, k, k_row, dvt, sl)
        kh_goc = _f((k_row or {}).get("sl_goc"))
        ly_do = ((ln or {}).get("ly_do_chenh_lech") or "").strip() or None
        # Quy được về gốc thì so ở gốc (đơn vị tổ khai có thể khác đơn vị kế hoạch). Không quy
        # được thì hai bên đang CÙNG đơn vị hiển thị nên so thẳng ở đó — đừng so 0 với 0 rồi kết
        # luận "không lệch", đó là nuốt mất chênh lệch thật.
        lech = (abs(sl_goc - kh_goc) > _EPS) if theo_goc \
            else (abs(sl - _f((k_row or {}).get("sl"))) > _EPS)
        # "Có xin" xét theo SỐ TỔ KHAI, không theo `sl_goc`.
        # Ngoài kế hoạch + số dương ⇒ luôn phải giải thích. Bổ sung ⇒ mọi dòng khác 0 phải giải
        # thích (kế hoạch đã dùng hết ở lần đầu, xin thêm là một quyết định mới).
        can_ly_do = lech or (k_row is None and sl > _EPS) or (bat_buoc_ly_do and sl > _EPS)
        if can_ly_do and not ly_do:
            ten = (k_row or {}).get("ten") or f"#{k[1]}"
            raise VatTuDeNghiError(f"«{ten}» lệch kế hoạch — phải ghi lý do.")
        ra.append({
            "hang_loai": k[0], "hang_id": k[1],
            "ten": (k_row or {}).get("ten") or f"#{k[1]}",
            "dvt": dvt, "dvt_goc": dvt_goc,
            "sl_ke_hoach": _f((k_row or {}).get("sl")), "sl_ke_hoach_goc": kh_goc,
            "sl_yeu_cau": sl, "sl_yeu_cau_goc": sl_goc,
            "ly_do_chenh_lech": ly_do,
        })
    return ra


def _lines_kho(cv, dongs: list[dict]) -> list[dict]:
    """Dòng yêu cầu kho = phần DƯƠNG của bản đối chiếu, quy về ĐƠN VỊ GỐC.

    Không gửi `dvt` hiển thị của kế hoạch: `StockRequestService.create` -> `_validate_lines` ->
    `VatLieuKhoService.quy_ve_goc` chỉ chấp nhận đơn vị có cạnh quy đổi TĨNH tới đơn vị gốc, mà
    giấy khai bằng "tờ" thì không có cạnh đó (đo thật: "Ivory 350" — không đổi được từ "to" về
    tấn, đơn vị dùng được là tấn/kg/g). Đơn vị gốc thì luôn nằm trong danh sách hợp lệ, nên đây
    là đường duy nhất chắc chắn qua được cửa kiểm của kho. Bản đối chiếu vẫn giữ NGUYÊN đơn vị tổ
    khai để tổ đọc đúng thứ họ gõ — chỉ ảnh chiếu sang kho đổi thang.
    """
    return [
        {"hang_loai": d["hang_loai"], "hang_id": d["hang_id"], "dvt": d["dvt_goc"],
         "sl_de_nghi": d["sl_yeu_cau_goc"],
         "lsx_id": cv.lsx_id, "bai_ghep_id": cv.bai_ghep_id}
        for d in dongs if d["sl_yeu_cau_goc"] > _EPS
    ]


def _kh_service(db: Session):
    """Dựng `KeHoachVatTuService` đúng bộ repo như `routers/ke_hoach_vat_tu.py::get_service()`.

    Ghép THIẾU một repo là engine im lặng trả rỗng — copy nguyên danh sách, không tự rút gọn.
    """
    from ...repositories.bai_ghep_repo import BaiGhepRepository
    from ...repositories.don_vi_do_repo import DonViDoRepository
    from ...repositories.lsx_repo import LsxRepository
    from ...repositories.purchase_repo import PurchaseRequestRepository, SupplierRepository
    from ...repositories.stock_lot_repo import StockLotRepository
    from ...repositories.stock_request_repo import StockRequestRepository
    from ...repositories.vat_lieu_kho_repo import VatLieuKhoRepository
    from ..ke_hoach_vat_tu_service import KeHoachVatTuService
    from ..vat_lieu_kho_service import VatLieuKhoService

    return KeHoachVatTuService(
        db,
        lsx_repo=LsxRepository(db),
        bai_ghep_repo=BaiGhepRepository(db),
        hang=VatLieuKhoService(VatLieuKhoRepository(db), DonViDoRepository(db)),
        lots=StockLotRepository(db),
        requests=StockRequestRepository(db),
        purchases=PurchaseRequestRepository(db),
        suppliers=SupplierRepository(db),
        don_vi=DonViDoRepository(db),
    )


def _req_service(db: Session):
    """Dựng `StockRequestService` đúng bộ repo như `routers/kho_request.py::get_service()`.

    `_validate_lines` cần `self.hang`; thiếu nó là mọi dòng lọt qua không kiểm.
    """
    from ...repositories.document_sequence_repo import DocumentSequenceRepository
    from ...repositories.don_vi_do_repo import DonViDoRepository
    from ...repositories.stock_lot_repo import StockLotRepository, StockThresholdRepository
    from ...repositories.stock_request_repo import StockRequestRepository
    from ...repositories.vat_lieu_kho_repo import VatLieuKhoRepository
    from ..sequence_service import SequenceService
    from ..stock_request_service import StockRequestService
    from ..vat_lieu_kho_service import VatLieuKhoService

    return StockRequestService(
        StockRequestRepository(db),
        StockLotRepository(db),
        StockThresholdRepository(db),
        SequenceService(DocumentSequenceRepository(db)),
        hang=VatLieuKhoService(VatLieuKhoRepository(db), DonViDoRepository(db)),
    )


def tao(db: Session, *, user, cong_viec_id: int, can_luc: datetime,
        lines: list[dict], kh_svc=None, req_svc=None) -> dict:
    """Tạo một LẦN đề nghị. Lần 1 = `lan_dau`, từ lần 2 trở đi = `bo_sung`."""
    repo = SanXuatRepository(db)
    cv = repo.cong_viec(cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công việc.")
    _gate_to_truong(db, user, cv.department_id)

    vt_repo = SanXuatVatTuRepository(db)
    cac = vt_repo.cac_de_nghi(cong_viec_id)
    if cac and not vt_repo.co_voucher(cac[-1].stock_request_id):
        raise VatTuDeNghiError(
            "Đang có đề nghị chưa được kho lập phiếu — hãy sửa đề nghị đó thay vì tạo lần mới.")

    lan_so = vt_repo.lan_ke_tiep(cong_viec_id)
    loai = DN_LAN_DAU if lan_so == 1 else DN_BO_SUNG
    kh_svc = kh_svc or _kh_service(db)
    dongs = _chuan_hoa(db, kh_svc, cv, lines, bat_buoc_ly_do=(loai == DN_BO_SUNG))

    dn = SanXuatVatTuDeNghi(
        cong_viec_id=cong_viec_id, lan_so=lan_so, loai=loai, can_luc=can_luc,
        created_by_id=getattr(user, "id", None), updated_by_id=getattr(user, "id", None),
    )
    db.add(dn)
    db.flush()
    for d in dongs:
        db.add(SanXuatVatTuDeNghiDong(de_nghi_id=dn.id, **{
            k: v for k, v in d.items() if k != "ten"
        }))

    kho_lines = _lines_kho(cv, dongs)
    if kho_lines:
        req_svc = req_svc or _req_service(db)
        req = req_svc.create(
            user=user, loai=REQ_XUAT, lines=kho_lines,
            # `bo_phan_id` phải khai TAY: mặc định của `create` là `user.department_id` — phòng của
            # người bấm, không phải TỔ của công đoạn. Để mặc định là yêu cầu hiện sai bộ phận trên
            # bản in và lệch scope `department` của kho.
            bo_phan_id=cv.department_id,
            ngay_can=can_luc.date(),
            ghi_chu=f"Cấp vật tư công đoạn «{cv.ten_cong_doan}» (lần {lan_so}).",
        )
        dn.stock_request_id = req.id

    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None), action="san_xuat_de_nghi_vat_tu",
        target=f"san_xuat_cong_viec:{cong_viec_id}",
        detail=f"lần {lan_so} · {len(kho_lines)} dòng gửi kho",
    )
    db.commit()
    hub.broadcast({"type": "san_xuat_vat_tu_de_nghi_changed",
                   "cong_viec_id": cong_viec_id})
    return {"de_nghi_id": dn.id, "stock_request_id": dn.stock_request_id, "lan_so": lan_so}
