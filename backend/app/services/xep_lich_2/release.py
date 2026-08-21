"""Cửa phát hành DÙNG CHUNG — vật tư phải giữ đủ mới cho phát hành (spec §5, §9.3).

Đây là điểm mấu chốt của "một lịch, hai cửa": cả màn v2 lẫn màn cũ đều gọi vào `van_de_vat_tu`,
nên không có đường vòng nào phát hành được lệnh chưa có giấy. Khác với `_chan_chua_giu_du` của
engine cũ (ném lỗi chặn LÚC ĐẶT lịch), ở đây ta CHỈ soi rồi trả `issue` — nháp vẫn đặt được khi
thiếu vật tư, chỉ chặn đúng lúc phát hành.

Dịch vụ giữ chỗ dựng TRỄ và bọc `try` y như bản gốc: bảng cân đối hỏng thì NÓI ra (một vấn đề
`vat_tu_chua_xac_dinh`) chứ không im lặng mở cửa cho lệnh không giấy.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .constraint import MUC_CANH_BAO, MUC_CHAN_PHAT_HANH, issue


def _giu_cho_service(db: Session):
    """Dựng GiuChoService kèm KeHoachVatTuService — sao đúng dây của `xep_lich_service._chan_chua_giu_du`."""
    from ...repositories.bai_ghep_repo import BaiGhepRepository
    from ...repositories.don_vi_do_repo import DonViDoRepository
    from ...repositories.lsx_repo import LsxRepository
    from ...repositories.purchase_repo import (
        PurchaseRequestRepository, SupplierRepository,
    )
    from ...repositories.stock_lot_repo import StockLotRepository
    from ...repositories.stock_request_repo import StockRequestRepository
    from ...repositories.vat_lieu_kho_repo import VatLieuKhoRepository
    from ..giu_cho_service import GiuChoService
    from ..ke_hoach_vat_tu_service import KeHoachVatTuService
    from ..vat_lieu_kho_service import VatLieuKhoService

    kh = KeHoachVatTuService(
        db, lsx_repo=LsxRepository(db),
        bai_ghep_repo=BaiGhepRepository(db),
        hang=VatLieuKhoService(VatLieuKhoRepository(db), DonViDoRepository(db)),
        lots=StockLotRepository(db), requests=StockRequestRepository(db),
        purchases=PurchaseRequestRepository(db),
        suppliers=SupplierRepository(db), don_vi=DonViDoRepository(db),
    )
    return GiuChoService(db, kh)


def trang_thai_giu_cho(db: Session, *, lsx_id: int | None = None,
                       bai_ghep_id: int | None = None) -> dict:
    return _giu_cho_service(db).trang_thai(lsx_id=lsx_id, bai_ghep_id=bai_ghep_id)


def soat_vat_tu(db: Session, *, lsx_id: int | None = None,
                bai_ghep_id: int | None = None) -> dict:
    """Soi vật tư của MỘT chủ thể, MỘT lần cân đối, tách làm HAI rổ (spec §5, §7.2, §12.6).

    · `chan` (chặn phát hành): chưa quy đổi được đơn vị · thiếu hàng CHƯA có phiếu mua
      (`vat_tu_chua_du`) · thiếu hàng ĐÃ đặt mua nhưng NCC chưa hẹn ngày (`vat_tu_chua_co_ngay`).
    · `canh_bao` (chỉ nhắc): đã giữ ĐỦ nhưng một phần dựa vào lô ĐANG VỀ có ngày hứa
      (`vat_tu_dang_ve`) — phần CHẶN GIỜ do luật `truoc_ngay_vat_tu` lo, đây chỉ để UI nhắc.

    Vì sao phải tách "chưa có ngày" khỏi "chưa mua": cả hai đều đỏ trên bảng cân đối, nhưng việc
    người dùng phải làm KHÁC nhau — một bên đi mua, một bên giục NCC chốt ngày. Gộp một thông điệp
    là chỉ sai đường cho một nửa số ca.

    Màn CŨ chỉ hỏi rổ `chan` qua `van_de_vat_tu`; `canh_bao` chỉ v2 dùng nên KHÔNG được lọt vào đó
    (`_chan_thieu_vat_tu` của màn cũ chặn trên MỌI vấn đề, cảnh báo lọt sang là chặn oan).
    """
    try:
        giu = _giu_cho_service(db)
        tt = giu.trang_thai(lsx_id=lsx_id, bai_ghep_id=bai_ghep_id)
    except Exception as exc:                                    # noqa: BLE001
        return {"chan": [issue(
            "vat_tu_chua_xac_dinh", MUC_CHAN_PHAT_HANH,
            f"Chưa kiểm được vật tư ({type(exc).__name__}) — mở màn Kế hoạch vật tư xem lỗi thật.",
            goi_y="Mở màn Kế hoạch vật tư kiểm lại rồi phát hành lại.",
        )], "canh_bao": []}

    chan: list[dict] = []
    if not tt["du"]:
        if tt["khong_ro"]:
            chan.append(issue(
                "vat_tu_chua_xac_dinh", MUC_CHAN_PHAT_HANH,
                "Có vật tư chưa quy đổi được về đơn vị kho nên chưa biết cần bao nhiêu.",
                goi_y="Kiểm lại đơn vị của mặt hàng ở màn Kế hoạch vật tư.",
            ))
        elif tt["thieu"]:
            short = {(loai, int(hid)) for (loai, hid) in tt["thieu"].keys()}
            no_eta = giu.kh.hang_dang_mua_khong_ngay()
            if short & no_eta:
                chan.append(issue(
                    "vat_tu_chua_co_ngay", MUC_CHAN_PHAT_HANH,
                    "Vật tư đã đặt mua nhưng NCC chưa hẹn ngày về — chưa cam kết được lịch.",
                    goi_y="Vào màn Kế hoạch vật tư giục NCC chốt ngày, hoặc mua nguồn khác.",
                ))
            if short - no_eta:
                chan.append(issue(
                    "vat_tu_chua_du", MUC_CHAN_PHAT_HANH,
                    "Vật tư chưa giữ đủ — đã xếp lịch nghĩa là vật tư phải có chủ.",
                    goi_y="Vào màn Kế hoạch vật tư bấm Giữ chỗ (hàng về hệ tự giữ nốt).",
                ))
        else:
            # Không đủ mà cũng không nêu được thiếu món nào (chưa phát sinh nhu cầu vật tư) —
            # giữ nguyên hành vi cũ: coi như chưa đủ điều kiện phát hành.
            chan.append(issue(
                "vat_tu_chua_du", MUC_CHAN_PHAT_HANH,
                "Vật tư chưa giữ đủ — đã xếp lịch nghĩa là vật tư phải có chủ.",
                goi_y="Vào màn Kế hoạch vật tư bấm Giữ chỗ (hàng về hệ tự giữ nốt).",
            ))

    canh_bao: list[dict] = []
    if tt.get("xep_som_nhat"):
        canh_bao.append(issue(
            "vat_tu_dang_ve", MUC_CANH_BAO,
            f"Một phần vật tư dựa vào lô đang về, hứa ngày {tt['xep_som_nhat']}.",
            goi_y="Lịch không đặt trước ngày này; hàng về sớm thì dời lên.",
        ))
    return {"chan": chan, "canh_bao": canh_bao}


def van_de_vat_tu(db: Session, *, lsx_id: int | None = None,
                  bai_ghep_id: int | None = None) -> list[dict]:
    """Danh sách vấn đề vật tư ở MỨC chặn-phát-hành (rỗng nghĩa là đã đủ giấy để phát hành).

    Đây là cửa DÙNG CHUNG với màn cũ nên CHỈ trả rổ `chan` — cảnh báo đang-về giữ ở `soat_vat_tu`.
    """
    return soat_vat_tu(db, lsx_id=lsx_id, bai_ghep_id=bai_ghep_id)["chan"]
