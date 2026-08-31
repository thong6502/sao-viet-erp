"""Tổ trưởng đề nghị cấp vật tư cho công đoạn của mình (spec-de-nghi-cap-vat-tu-cong-doan §5).

Ranh giới an ninh THỰC nằm ở đây, không ở router: router chỉ gác bit thô `san_xuat:assign_work`
(mọi tổ trưởng SX đều có), còn "đúng tổ nào" thì chỉ tầng này biết. Tái dùng `_gate_to_truong` của
`vat_tu_nhan.py` — hai cổng cùng nghĩa mà viết hai lần là mời chúng lệch nhau.

BA thang đơn vị chạy song song trong `tao()` — xem docstring của hàm đó.
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
from ...repositories.stock_request_repo import StockRequestRepository
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


def _chuan_hoa(kh_svc, cv, lines: list[dict], *, bat_buoc_ly_do: bool) -> list[dict]:
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
        ten = (k_row or {}).get("ten") or f"#{k[1]}"
        sl = _f((ln or {}).get("sl_yeu_cau"))
        # Số âm không có nghĩa cho "xin cấp" — chặn NGAY, đừng để lọt vào bản đối chiếu rồi mới
        # bị `_lines_kho` âm thầm loại (bảng sản xuất khi đó ghi được "−50 tờ").
        if sl < 0:
            raise VatTuDeNghiError(f"«{ten}» không nhận số âm.")
        # Dòng NGOÀI kế hoạch mà xin 0 là vô nghĩa — không lưu (§4).
        if k_row is None and (ln is None or sl <= _EPS):
            continue
        dvt = (ln or {}).get("dvt") or (k_row or {})["dvt"]
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
            raise VatTuDeNghiError(f"«{ten}» lệch kế hoạch — phải ghi lý do.")
        ra.append({
            "hang_loai": k[0], "hang_id": k[1],
            "ten": ten,
            "dvt": dvt, "dvt_goc": dvt_goc,
            "sl_ke_hoach": _f((k_row or {}).get("sl")), "sl_ke_hoach_goc": kh_goc,
            "sl_yeu_cau": sl, "sl_yeu_cau_goc": sl_goc,
            "ly_do_chenh_lech": ly_do,
        })
    return ra


def moi_dong_deu_0(dn) -> bool:
    """Mọi dòng của lần đề nghị này đều xin 0 ⇒ yêu cầu kho (nếu đang `cancelled`) là do CHÍNH SẢN
    XUẤT tự đưa về 0, không phải kho hủy. Hai bên đọc cùng một vị ngữ: `sua()` dùng nó để chọn
    đường khôi phục (`khoi_phuc_tu_san_xuat` so với `dong_bo_tu_san_xuat`), `board._vat_tu_cap`
    dùng nó để biết có mở ô "sửa lần cuối" cho tổ hay không (Task 7 — ruling task-7 27: kho ĐÃ hủy
    thì `sua()` sẽ ném lỗi, mời tổ bấm sửa để rồi ăn 400 là lỗi giao diện)."""
    return all(float(d.sl_yeu_cau or 0) <= _EPS for d in (dn.dongs or []))


def _don_vi_gui_kho(hang, hang_loai, hang_id, sl_goc: float) -> tuple[str, float]:
    """Chọn đơn vị gửi kho cho một lượng đã quy về gốc. Trả `(dvt, so_luong_theo_dvt)`.

    KHÔNG mặc định dùng đơn vị gốc: `StockRequestLine.sl_de_nghi` là `Numeric(14, 2)` kèm
    `CheckConstraint("> 0")`, nên với giấy (gốc = "tấn") một đề nghị 10 tờ ≈ 0.003 tấn bị ép về
    0.00 và vỡ ràng buộc ngay lúc commit — SQLite của test không ép scale nên test không thấy.
    Cả khi không về 0 thì bước lượng tử 0.01 tấn cũng ≈ 33 tờ giấy, đủ để số kho lệch số tổ khai.

    Luật chọn: trong các đơn vị mà chính danh mục cho phép quy về gốc, lấy đơn vị THÔ NHẤT mà
    lượng vẫn ≥ 1. Vật tư đếm bằng "cái"/"kg" giữ nguyên đơn vị gốc như trước (50 cái vẫn là
    "cái"); chỉ khi đơn vị gốc biến lượng thành số lẻ dưới 1 mới bước xuống đơn vị mịn hơn
    (0.335 tấn → 335.14 kg). Không đơn vị nào đạt ≥ 1 thì lấy đơn vị mịn nhất.
    """
    ra = hang.don_vi_cua_mat_hang(hang_loai, hang_id)
    ds = [d for d in (ra.get("ds") or []) if float(d.get("he_so_ve_goc") or 0) > 0]
    if not ds:
        return (ra.get("don_vi_goc") or ""), float(sl_goc)
    # `sl_goc = so_luong_theo_dvt * he_so_ve_goc` ⇒ đảo lại để ra số theo từng đơn vị.
    cap = sorted(((float(d["he_so_ve_goc"]), d) for d in ds), key=lambda x: -x[0])
    for he_so, d in cap:                      # thô → mịn
        sl = float(sl_goc) / he_so
        if sl >= 1.0:
            return d["ma"], sl
    he_so, d = cap[-1]                        # mịn nhất
    return d["ma"], float(sl_goc) / he_so


def _lines_kho(hang, cv, dongs: list[dict]) -> list[dict]:
    """Dòng yêu cầu kho = phần DƯƠNG của bản đối chiếu, quy sang đơn vị kho ghi được.

    Bản đối chiếu (bảng sản xuất) giữ NGUYÊN đơn vị tổ khai để tổ đọc đúng thứ họ gõ; chỉ ảnh
    chiếu sang kho mới đổi thang — xem `_don_vi_gui_kho` để biết vì sao không dùng thẳng đơn vị gốc.

    Lọc "có xin hay không" phải xét theo `sl_yeu_cau` (đơn vị TỔ KHAI — đúng thang với ô tổ gõ),
    KHÔNG phải `sl_yeu_cau_goc` (đơn vị GỐC, có thể lệch thang cả nghìn lần: 0.0005 tấn ≈ 1.6 tờ).
    Trước fix (ruling 14), lọc theo `sl_yeu_cau_goc` khiến tổ xin 1 tờ bị loại IM LẶNG — nếu đó là
    dòng dương duy nhất thì không yêu cầu kho nào được đẻ ra mà tổ không hề biết. Sau fix, mọi dòng
    tổ thật sự xin (`sl_yeu_cau > _EPS`) đều đi qua `_don_vi_gui_kho`; nếu lượng quy đổi vẫn quá
    nhỏ để kho ghi được thì rơi vào chốt chặn `round(sl, 2) <= 0` bên dưới — NỔ lỗi đọc được, không
    còn đường thứ ba nào âm thầm bỏ dòng.
    """
    ra = []
    for d in dongs:
        if d["sl_yeu_cau"] <= _EPS:
            continue
        dvt, sl = _don_vi_gui_kho(hang, d["hang_loai"], d["hang_id"], d["sl_yeu_cau_goc"])
        # Cột kho là `Numeric(14, 2)` + `CHECK > 0`: lượng nhỏ hơn nửa đơn vị làm tròn sẽ thành
        # 0.00 và vỡ ràng buộc lúc commit. Chặn ở đây, có câu người dùng đọc được, thay vì để
        # `IntegrityError` thoát ra thành 500.
        if round(sl, 2) <= 0:
            raise VatTuDeNghiError(
                f"«{d['ten']}» xin quá ít so với đơn vị kho ghi được ({sl:g} {dvt}) — "
                f"gộp vào lần cấp sau hoặc đổi đơn vị."
            )
        ra.append({
            "hang_loai": d["hang_loai"], "hang_id": d["hang_id"], "dvt": dvt,
            "sl_de_nghi": sl, "lsx_id": cv.lsx_id, "bai_ghep_id": cv.bai_ghep_id,
        })
    return ra


def _hang_service(db: Session):
    """`VatLieuKhoService` DÙNG CHUNG cho cả `_kh_service` lẫn `_req_service`.

    Hai nơi trước đây tự dựng riêng — cùng repo, cùng `db`, dựng hai lần vô ích. `tao()` dựng
    MỘT LẦN rồi truyền vào cả hai.
    """
    from ...repositories.don_vi_do_repo import DonViDoRepository
    from ...repositories.vat_lieu_kho_repo import VatLieuKhoRepository
    from ..vat_lieu_kho_service import VatLieuKhoService

    return VatLieuKhoService(VatLieuKhoRepository(db), DonViDoRepository(db))


def _kh_service(db: Session, hang):
    """Dựng `KeHoachVatTuService` đúng bộ repo như `routers/ke_hoach_vat_tu.py::get_service()`.

    Ghép THIẾU một repo là engine im lặng trả rỗng — copy nguyên danh sách, không tự rút gọn.
    """
    from ...repositories.bai_ghep_repo import BaiGhepRepository
    from ...repositories.don_vi_do_repo import DonViDoRepository
    from ...repositories.lsx_repo import LsxRepository
    from ...repositories.purchase_repo import PurchaseRequestRepository, SupplierRepository
    from ...repositories.stock_lot_repo import StockLotRepository
    from ...repositories.stock_request_repo import StockRequestRepository
    from ..ke_hoach_vat_tu_service import KeHoachVatTuService

    return KeHoachVatTuService(
        db,
        lsx_repo=LsxRepository(db),
        bai_ghep_repo=BaiGhepRepository(db),
        hang=hang,
        lots=StockLotRepository(db),
        requests=StockRequestRepository(db),
        purchases=PurchaseRequestRepository(db),
        suppliers=SupplierRepository(db),
        don_vi=DonViDoRepository(db),
    )


def _req_service(db: Session, hang):
    """Dựng `StockRequestService` đúng bộ repo như `routers/kho_request.py::get_service()`.

    `_validate_lines` cần `self.hang`; thiếu nó là mọi dòng lọt qua không kiểm.
    """
    from ...repositories.document_sequence_repo import DocumentSequenceRepository
    from ...repositories.stock_lot_repo import StockLotRepository, StockThresholdRepository
    from ...repositories.stock_request_repo import StockRequestRepository
    from ..sequence_service import SequenceService
    from ..stock_request_service import StockRequestService

    return StockRequestService(
        StockRequestRepository(db),
        StockLotRepository(db),
        StockThresholdRepository(db),
        SequenceService(DocumentSequenceRepository(db)),
        hang=hang,
    )


def tao(db: Session, *, user, cong_viec_id: int, can_luc: datetime,
        lines: list[dict], kh_svc=None, req_svc=None) -> dict:
    """Tạo một LẦN đề nghị. Lần 1 = `lan_dau`, từ lần 2 trở đi = `bo_sung`.

    BA thang đơn vị chạy song song ở đây:
      · `SanXuatVatTuDeNghiDong.sl_yeu_cau`/`dvt` — đơn vị TỔ KHAI (tờ, ram…), giữ để bản đối
        chiếu hiện đúng chữ tổ gõ (ruling 10).
      · `sl_yeu_cau_goc`/`dvt_goc` — đơn vị GỐC của danh mục, dùng để SO LỆCH kế hoạch. Giấy khai
        bằng "tờ" không có cạnh quy đổi tĩnh sang gốc (đo thật: "Ivory 350" không đổi được từ "to"
        về tấn — xem `_ve_goc_dong`), nên `ve_don_vi_goc` ném lỗi khi không quy được.
      · `StockRequestLine.sl_de_nghi`/`dvt` — đơn vị GỬI KHO, do `_don_vi_gui_kho` chọn từ
        `sl_yeu_cau_goc` (ruling 11b, thay ruling 11 cũ). KHÔNG PHẢI lúc nào cũng trùng `dvt_goc`:
        giấy gốc là "tấn" nhưng gửi kho bằng "kg" — `StockRequestLine.sl_de_nghi` là
        `Numeric(14, 2)` kèm `CHECK > 0`, tấn thì bước lượng tử 0.01 tấn ≈ 33 tờ, lệch xa số tổ
        khai; lượng nhỏ còn bị ép về 0.00 và vỡ ràng buộc.
    So sánh giữa `SanXuatVatTuDeNghiDong` và `StockRequestLine` vì thế PHẢI đi qua
    `sl_yeu_cau_goc`/`dvt_goc`, không phải `sl_yeu_cau`/`dvt` lẫn `sl_de_nghi`/`dvt` của dòng kho.
    """
    repo = SanXuatRepository(db)
    cv = repo.cong_viec(cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công việc.")
    _gate_to_truong(db, user, cv.department_id)

    vt_repo = SanXuatVatTuRepository(db)
    cac = vt_repo.cac_de_nghi(cong_viec_id)
    if cac and not StockRequestRepository(db).co_voucher(cac[-1].stock_request_id):
        raise VatTuDeNghiError(
            "Đang có đề nghị chưa được kho lập phiếu — hãy sửa đề nghị đó thay vì tạo lần mới.")

    lan_so = vt_repo.lan_ke_tiep(cong_viec_id)
    loai = DN_LAN_DAU if lan_so == 1 else DN_BO_SUNG
    hang = _hang_service(db)
    kh_svc = kh_svc or _kh_service(db, hang)
    dongs = _chuan_hoa(kh_svc, cv, lines, bat_buoc_ly_do=(loai == DN_BO_SUNG))
    kho_lines = _lines_kho(hang, cv, dongs)

    # Tạo yêu cầu kho TRƯỚC khi đụng tới hai bảng SX (ruling minor-5): `stock_request_repo.create`
    # / `save` tự COMMIT. Nếu tạo yêu cầu kho SAU khi đã `db.add()` đề nghị SX, commit nội bộ đó
    # ghi luôn đề nghị SX (còn thiếu `stock_request_id`) VÀ yêu cầu kho trong cùng một nhát — chết
    # giữa chừng (giữa commit đó và `db.commit()` cuối) để lại CẢ hai bên mồ côi: đề nghị đã chiếm
    # `lan_so` nhưng `stock_request_id` mãi NULL, mà `co_voucher(None)` lại khoá cứng không cho
    # sửa/tạo lần mới. Tạo kho trước: chết giữa chừng khi đó chỉ để lại một yêu cầu kho THỪA —
    # `SanXuatVatTuDeNghi` của lượt này chưa hề tồn tại, `lan_so` vẫn trống, tổ gọi lại `tao()` là
    # xong, không kẹt.
    req = None
    if kho_lines:
        req_svc = req_svc or _req_service(db, hang)
        req = req_svc.create(
            user=user, loai=REQ_XUAT, lines=kho_lines,
            # `bo_phan_id` phải khai TAY: mặc định của `create` là `user.department_id` — phòng của
            # người bấm, không phải TỔ của công đoạn. Để mặc định là yêu cầu hiện sai bộ phận trên
            # bản in và lệch scope `department` của kho.
            bo_phan_id=cv.department_id,
            ngay_can=can_luc.date(),
            ghi_chu=f"Cấp vật tư công đoạn «{cv.ten_cong_doan}» (lần {lan_so}).",
        )

    dn = SanXuatVatTuDeNghi(
        cong_viec_id=cong_viec_id, lan_so=lan_so, loai=loai, can_luc=can_luc,
        stock_request_id=(req.id if req is not None else None),
        created_by_id=getattr(user, "id", None), updated_by_id=getattr(user, "id", None),
    )
    db.add(dn)
    db.flush()
    for d in dongs:
        db.add(SanXuatVatTuDeNghiDong(de_nghi_id=dn.id, **{
            k: v for k, v in d.items() if k != "ten"
        }))

    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None), action="san_xuat_de_nghi_vat_tu",
        target=f"san_xuat_cong_viec:{cong_viec_id}",
        detail=f"lần {lan_so} · {len(kho_lines)} dòng gửi kho",
    )
    db.commit()
    hub.broadcast({"type": "san_xuat_vat_tu_de_nghi_changed",
                   "cong_viec_id": cong_viec_id})
    return {"de_nghi_id": dn.id, "stock_request_id": dn.stock_request_id, "lan_so": lan_so}


def sua(db: Session, *, user, cong_viec_id: int, de_nghi_id: int,
        can_luc: datetime, lines: list[dict], kh_svc=None, req_svc=None) -> dict:
    """Sửa một lần đề nghị CHƯA bị kho lập phiếu (spec §5.2–§5.4).

    Kiểm khoá phải chạy TRONG transaction, ngay trước khi ghi — kiểm ở router rồi mới vào service
    là mở đúng khe cho kho bấm "lập phiếu" ở giữa hai thời điểm đó (`co_voucher` bên dưới đọc lại
    ngay trước khi ghi bảng SX).

    Ba nhánh đích cho yêu cầu kho, theo đúng combo (đã-có-yêu-cầu?, còn-dòng-dương?):
      · CHƯA có `stock_request_id`, giờ có dòng dương ⇒ lần đầu toàn 0 nay xin lại — mới đẻ
        chứng từ kho (giống `tao()`).
      · ĐÃ có `stock_request_id`, còn dòng dương, VÀ bản TRƯỚC KHI SỬA toàn 0 ⇒ chính sản xuất đã
        hủy yêu cầu đó — khôi phục qua `khoi_phuc_tu_san_xuat`.
      · ĐÃ có `stock_request_id`, còn dòng dương, nhưng bản TRƯỚC KHI SỬA còn dòng dương (sản xuất
        chưa hủy gì) ⇒ đồng bộ thường qua `dong_bo_tu_san_xuat`; nếu yêu cầu đang `cancelled` thì
        đó là KHO hủy (ruling task-4 important-2) và hàm này tự chặn, không cho lật quyết định
        của kho.
      · ĐÃ có `stock_request_id`, hết dòng dương ⇒ huỷ yêu cầu (`huy_tu_san_xuat`), giữ mã + link
        để tổ nhập lại số dương sau này khôi phục đúng chứng từ đó.
    """
    repo = SanXuatRepository(db)
    cv = repo.cong_viec(cong_viec_id)
    if cv is None:
        raise ValueError("Không tìm thấy công việc.")
    _gate_to_truong(db, user, cv.department_id)

    vt_repo = SanXuatVatTuRepository(db)
    dn = vt_repo.de_nghi(de_nghi_id)
    if dn is None or dn.cong_viec_id != cong_viec_id:
        raise ValueError("Không tìm thấy đề nghị của công đoạn này.")
    if StockRequestRepository(db).co_voucher(dn.stock_request_id):
        raise VatTuDeNghiError("Kho đã lập phiếu cho đề nghị này — hãy tạo yêu cầu bổ sung.")

    # Chụp TRƯỚC khi xoá dòng cũ: dùng để biết cái `cancelled` (nếu có) là do sản xuất tự đưa về 0
    # hay do kho hủy. Xoá xong mới hỏi là mất luôn câu trả lời (ruling task-4 important-2).
    truoc_do_toan_0 = moi_dong_deu_0(dn)

    hang = _hang_service(db)
    kh_svc = kh_svc or _kh_service(db, hang)
    dongs = _chuan_hoa(kh_svc, cv, lines, bat_buoc_ly_do=(dn.loai == DN_BO_SUNG))
    kho_lines = _lines_kho(hang, cv, dongs)

    # Khối `req_svc` chạy TRƯỚC khi đụng `dn.dongs` (ruling task-4 minor-5, cùng lý do `tao()` đã
    # vá): các hàm dưới đây tự COMMIT bên trong (`stock_request_repo.create`/`save`). Nếu `dn.dongs`
    # đã bị xoá/dựng lại ở phía TRÊN thì một commit nội bộ giữa chừng của `req_svc` ghi luôn phần
    # dở đó vào DB — chết giữa chừng để lại một yêu cầu kho ĐÃ đổi số nhưng bảng SX vẫn dở dang.
    # Làm req_svc trước: chết giữa chừng chỉ để lại đúng NỬA đầu (yêu cầu kho), `dn.dongs` của lần
    # sửa vẫn chưa động tới — tổ gọi lại `sua()` với cùng số là xong, không mồ côi.
    req_svc = req_svc or _req_service(db, hang)
    req_id_moi = None
    if dn.stock_request_id is None:
        # Lần đầu toàn 0, nay có số dương ⇒ giờ mới đẻ chứng từ kho.
        if kho_lines:
            req = req_svc.create(
                user=user, loai=REQ_XUAT, lines=kho_lines, bo_phan_id=cv.department_id,
                ngay_can=can_luc.date(),
                ghi_chu=f"Cấp vật tư công đoạn «{cv.ten_cong_doan}» (lần {dn.lan_so}).",
            )
            req_id_moi = req.id
    elif kho_lines:
        if truoc_do_toan_0:
            req_svc.khoi_phuc_tu_san_xuat(dn.stock_request_id, kho_lines,
                                          user=user, ngay_can=can_luc.date())
        else:
            # Trước đó vẫn còn dòng dương ⇒ sản xuất chưa hủy gì. Đi đường đồng bộ thường; nếu
            # yêu cầu đang `cancelled` thì đó là kho hủy và `dong_bo_tu_san_xuat` sẽ chặn.
            req_svc.dong_bo_tu_san_xuat(dn.stock_request_id, kho_lines,
                                        user=user, ngay_can=can_luc.date())
    else:
        req_svc.huy_tu_san_xuat(dn.stock_request_id, user=user)

    dn.dongs.clear()
    db.flush()
    for d in dongs:
        db.add(SanXuatVatTuDeNghiDong(de_nghi_id=dn.id, **{
            k: v for k, v in d.items() if k != "ten"
        }))
    dn.can_luc = can_luc
    dn.updated_by_id = getattr(user, "id", None)
    if req_id_moi is not None:
        dn.stock_request_id = req_id_moi

    AuditLogRepository(db).create(
        actor_user_id=getattr(user, "id", None), action="san_xuat_sua_de_nghi_vat_tu",
        target=f"san_xuat_vat_tu_de_nghi:{dn.id}",
        detail=f"{len(kho_lines)} dòng gửi kho",
    )
    db.commit()
    hub.broadcast({"type": "san_xuat_vat_tu_de_nghi_changed", "cong_viec_id": cong_viec_id})
    # KHÔNG broadcast thêm `stock_request_pending_changed` toàn hệ ở đây (ruling task-4 minor-6):
    # mỗi nhánh `req_svc` ở trên đã tự `_notify(..., targeted=False)`, mà `_notify` cố ý đẩy THEO
    # PHẠM VI (xem `stock_request_service.py`), không broadcast toàn hệ. `tao()` cũng không có
    # dòng này.
    return {"de_nghi_id": dn.id, "stock_request_id": dn.stock_request_id}
