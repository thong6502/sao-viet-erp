"""Tách một công đoạn thành nhiều LẦN CHẠY (spec-thuc-te-vs-ke-hoach §2.4).

Xưởng vẫn chạy như vậy từ lâu — tầng thực thi đã cho nhiều `SanXuatBatch` cho một công việc — chỉ
tầng KẾ HOẠCH là chưa diễn đạt được. Module này thêm đúng chuyện đó và KHÔNG hơn: nó chia số
lượng và đánh số phân đoạn, còn xếp giờ/gán máy vẫn là việc của `service.py` như mọi dòng khác.

Ba luật xương sống:
1. **Tổng bất biến.** Σ `so_luong` các phân đoạn == số lượng dòng gốc. Lệch một tờ là lệch bảng
   cân đối vật tư lẫn định mức khoán.
2. **Phân đoạn đầu GIỮ id gốc.** Mọi thứ đang neo vào dòng đó (audit, vấn đề đang mở theo
   `issue_key`, dòng đã phát hành) không bị mất neo khi người ta bấm tách.
3. **Phân đoạn sau về CHỜ XẾP.** Thừa kế giờ của gốc là tự đặt hai lần chỗ trên cùng một máy —
   đúng thứ mà bộ dò `trung_may` sẽ la lên ngay sau đó.

Không có vòng import nào ở đây dù module này đứng dưới `service`: `xep_lich_service` gọi ngược lên
bằng import LAZY trong thân hàm. Lấy `XepLich2Error` thẳng từ `.service` (thay vì qua `__init__`)
chỉ để đường import chỉ đúng chỗ định nghĩa lỗi — hai lối kéo vào cùng một module.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models.bai_ghep_cong_doan import BaiGhepCongDoan
from ...models.lsx import LsxCongDoan
from ...models.xep_lich import NGUON_IN_GHEP, TT_CHO_XEP, XepLichCongDoan
from .service import XepLich2Error

_EPS = 0.0005   # cùng dung sai làm tròn với `san_luong.tao_batch`


def cac_phan_doan(db: Session, dong: XepLichCongDoan) -> list[XepLichCongDoan]:
    """Mọi phân đoạn cùng gốc với `dong`, sắp theo `phan_doan_so`. Dòng chưa tách trả [chính nó]."""
    goc_id = dong.goc_dong_id or dong.id
    ra = list(db.scalars(
        select(XepLichCongDoan)
        .where((XepLichCongDoan.id == goc_id) | (XepLichCongDoan.goc_dong_id == goc_id))
        .order_by(XepLichCongDoan.phan_doan_so, XepLichCongDoan.id)
    ))
    return ra or [dong]


def ty_le_trong_cum(dong: XepLichCongDoan, cum: list[XepLichCongDoan]) -> float:
    """Phần việc của dòng / cả bước — nhân vào SL đưa cho engine thời lượng.

    MỘT đường tính tỉ lệ duy nhất, và nó luôn lấy tổng từ chính cụm: các phần không đều nhau nên
    suy từ `phan_doan_tong` (kiểu 1/N) là sai ngay khi ai đó chia 6.000 + 4.000.

    Dòng chưa tách trả 1.0, kể cả khi `so_luong` NULL — NULL nghĩa "trọn bước", không phải
    "không biết".
    """
    if dong.phan_doan_tong <= 1 or dong.so_luong is None:
        return 1.0
    tong_cum = sum(float(d.so_luong or 0) for d in cum)
    if tong_cum <= 0:
        return 1.0
    return float(dong.so_luong or 0) / tong_cum


def _sl_vao_cua_buoc(db: Session, dong: XepLichCongDoan) -> float:
    """SL VÀO của bước mà dòng đang neo — tổng để chia khi bản thân dòng chưa mang `so_luong`.

    KHÔNG nơi nào trong hệ ghi `xep_lich_cong_doan.so_luong` lúc sinh dòng (số của bước tính lúc
    đọc từ routing), nên dòng thật gần như luôn NULL. Đọc lại từ chính bước là giữ MỘT nguồn số,
    thay vì bắt người bấm tách gõ lại tổng rồi tự chịu trách nhiệm gõ đúng.
    """
    if dong.lsx_cong_doan_id:
        buoc = db.get(LsxCongDoan, dong.lsx_cong_doan_id)
    elif dong.bai_ghep_cong_doan_id:
        buoc = db.get(BaiGhepCongDoan, dong.bai_ghep_cong_doan_id)
    else:
        buoc = None
    return float(buoc.so_luong_vao or 0) if buoc is not None else 0.0


def tach(db: Session, *, dong_id: int, cac_phan: list[float],
         tong_buoc: float | None = None, actor=None) -> list[XepLichCongDoan]:
    """Tách `dong_id` thành `len(cac_phan)` phân đoạn theo đúng các con số đã cho.

    `tong_buoc` là tổng NGƯỜI BẤM đang nhìn thấy trên màn: nó thắng số đọc lại từ bước, để hai bên
    không chia theo hai con số khác nhau. Bỏ trống ⇒ suy từ chính bước.
    """
    goc = db.get(XepLichCongDoan, dong_id)
    if goc is None:
        raise XepLich2Error("Không tìm thấy dòng lịch.")
    if goc.is_locked:
        raise XepLich2Error("Dòng đang khóa — mở khóa trước khi tách lần chạy.")
    if goc.phan_doan_tong > 1:
        raise XepLich2Error("Dòng đã tách rồi — gộp lại trước khi chia kiểu khác.")
    if len(cac_phan) < 2:
        raise XepLich2Error("Tách phải có ít nhất 2 phần.")
    # Dòng IN GHÉP kiểu cũ (trước mg 0151, chưa neo bước chung) đi nhánh thời lượng riêng
    # `_thoi_luong_in_ghep` — KHÔNG qua `_sl_tinh` nên tỉ lệ phân đoạn không có đường vào công
    # thức: chia đôi thì MỖI phần vẫn ăn trọn thời lượng cả bước, tức máy bị đặt gấp đôi.
    if goc.nguon == NGUON_IN_GHEP and goc.bai_ghep_cong_doan_id is None:
        raise XepLich2Error(
            "Dòng in ghép kiểu cũ chưa neo bước chung — chưa tách lần chạy được.")
    if any(float(p) <= 0 for p in cac_phan):
        raise XepLich2Error("Mỗi phần phải lớn hơn 0.")
    tong = round(
        float(goc.so_luong) if goc.so_luong is not None
        else (float(tong_buoc or 0) or _sl_vao_cua_buoc(db, goc)), 3)
    if tong <= 0:
        raise XepLich2Error(
            "Bước chưa biết số lượng nên chưa chia được — kiểm quy cách lệnh trước.")
    if abs(sum(float(p) for p in cac_phan) - tong) > _EPS:
        raise XepLich2Error(f"Tổng các phần phải bằng {tong:g}.")

    # Cột là NUMERIC(18,3): kiểm bất biến trên float rồi lưu 3 chữ số là để tổng trôi một tờ. Làm
    # tròn từng phần, rồi ép phần CUỐI gánh phần lẻ — Σ luôn khép đúng tổng.
    phan = [round(float(p), 3) for p in cac_phan]
    phan[-1] = round(tong - sum(phan[:-1]), 3)
    if phan[-1] <= 0:
        raise XepLich2Error("Mỗi phần phải lớn hơn 0.")

    n = len(phan)
    goc.so_luong = phan[0]
    goc.phan_doan_so = 1
    goc.phan_doan_tong = n
    goc.goc_dong_id = None
    ra = [goc]
    for i, p in enumerate(phan[1:], start=2):
        moi = XepLichCongDoan(
            nguon=goc.nguon, lsx_id=goc.lsx_id, lsx_cong_doan_id=goc.lsx_cong_doan_id,
            bai_ghep_id=goc.bai_ghep_id, bai_ghep_cong_doan_id=goc.bai_ghep_cong_doan_id,
            source_thu_tu=goc.source_thu_tu, loai_buoc=goc.loai_buoc,
            # Máy/tổ/NCC thừa kế làm GỢI Ý (người kế hoạch hay chạy tiếp trên cùng máy), nhưng
            # GIỜ thì không — hai phân đoạn cùng giờ cùng máy là xung đột dựng sẵn.
            may_id=goc.may_id, department_id=goc.department_id, nha_cung_cap=goc.nha_cung_cap,
            work_shift_id=goc.work_shift_id,
            start_at=None, finish_at=None, trang_thai=TT_CHO_XEP,
            so_luong=p, phan_doan_so=i, phan_doan_tong=n, goc_dong_id=goc.id,
            # Vết "ai đẻ ra dòng này" chỉ vào người BẤM TÁCH, không chép lại người đưa lệnh vào
            # kế hoạch — hai việc khác nhau, và chỉ có việc sau mới cần đi hỏi.
            created_by=getattr(actor, "id", None),
        )
        db.add(moi)
        ra.append(moi)
    # CHỈ flush: vết audit ở tầng service phải rơi vào CÙNG một commit với việc tách. Tự commit ở
    # đây thì audit lỗi ngay sau đó ⇒ dòng đã tách nằm vĩnh viễn trong DB mà không một vết nào.
    db.flush()
    return ra


def gop(db: Session, *, dong_id: int) -> XepLichCongDoan:
    """Gộp cả cụm phân đoạn về lại MỘT dòng — dòng gốc, giữ nguyên id và tổng số lượng."""
    dong = db.get(XepLichCongDoan, dong_id)
    if dong is None:
        raise XepLich2Error("Không tìm thấy dòng lịch.")
    cum = cac_phan_doan(db, dong)
    n = int(dong.phan_doan_tong or 1)
    if len(cum) <= 1 and n <= 1:
        return dong                     # dòng chưa tách — gộp là không-làm-gì
    if any(d.is_locked for d in cum):
        raise XepLich2Error("Có phân đoạn đang khóa — mở khóa trước khi gộp.")
    goc = cum[0]
    # Cụm KHUYẾT thì gộp im lặng sẽ nuốt mất phần thiếu: mất bản ghi gốc ⇒ `cum[0]` là phân đoạn 2
    # và tổng tụt 10.000 → 4.000. Hụt tổng là hụt cả bảng cân đối vật tư lẫn định mức khoán, nên
    # thà chặn để người ta đi soi còn hơn trả về một con số nhỏ trông như thật.
    if goc.phan_doan_so != 1 or len(cum) != int(goc.phan_doan_tong or 1):
        raise XepLich2Error(
            "Cụm lần chạy đã khuyết — gộp lại sẽ hụt tổng, kiểm lại các lần chạy của bước.")
    # Gộp xong `phan_doan_tong == 1` tức TRỌN bước ⇒ trả `so_luong` về NULL đúng nghĩa cột. Giữ
    # lại con số cứng là đẻ nguồn số thứ hai: đơn hạ xuống 8.000 mà đây vẫn nói 10.000.
    goc.so_luong = None
    goc.phan_doan_so = 1
    goc.phan_doan_tong = 1
    goc.goc_dong_id = None
    for d in cum[1:]:
        db.delete(d)
    db.flush()
    return goc
