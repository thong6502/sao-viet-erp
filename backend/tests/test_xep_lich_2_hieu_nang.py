"""Xếp lịch 2 — GIỮ CHI PHÍ ĐỌC của bàn làm việc không phình theo số thanh.

Bàn là đường đọc nóng nhất của điều độ: mở màn là gọi `GET /xep-lich-2/ban-lam-viec` cho cả cửa
sổ. Mỗi thanh cần "mức nặng nhất tại chỗ đang đặt" + "râu bóc tách thời lượng", mà cả hai đều đi
qua bộ luật vốn viết cho MỘT thao tác kéo-thả. Không gộp thì mỗi thanh tự hỏi lại toàn bộ nền
(ca · nghỉ · khoá máy · việc trên máy · việc của tổ · quân số · sàn in-chung · hai hạn).

Đo ngày 09/09/2026 TRƯỚC khi sửa: ~23 câu SQL mỗi thanh (2 dòng → 67 câu, 22 → 534, 62 → 1463);
trên Postgres dev, bàn 9 thanh mất 0,9–1,2 giây và tăng THẲNG theo số thanh.

Test này KHÔNG chấm mili-giây (SQLite trong RAM không nói được gì về Postgres) mà chấm ĐỘ DỐC:
thêm một thanh vào bàn thì tốn thêm bao nhiêu câu SQL. Đó mới là thứ quyết định bàn 300 thanh có
mở nổi không.
"""
from __future__ import annotations

from datetime import timedelta, timezone

from sqlalchemy import event

from app.db import engine
from app.models.xep_lich import TT_DA_XEP, XepLichCongDoan
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.xep_lich_2_repo import XepLich2Repository
from app.services.xep_lich_2 import XepLich2Service

from tests.test_xep_lich_service import (  # noqa: F401 — fixture dùng chung
    _giu_cho_du, _hai_lsx_san_sang, _khai_ca_xuong,
    admin, bg_svc, customer, db, lsx_svc, orders, xl_svc,
)

#: Trần độ dốc: mỗi thanh thêm vào bàn được phép tốn thêm ngần này câu SQL. Sau khi gộp, phần còn
#: lại của mỗi thanh là engine THỜI LƯỢNG (bước routing · vật tư của bước · lệnh · máy) cộng cạnh
#: tiền nhiệm — thứ thật sự khác nhau giữa hai thanh. Trước khi sửa con số này là ~23.
TRAN_CAU_MOI_THANH = 4


class _DemSql:
    """Đếm câu SQL thật sự bắn xuống DB trong khối `with`."""

    def __init__(self) -> None:
        self.n = 0

    def __enter__(self) -> "_DemSql":
        def hook(conn, cur, stmt, params, ctx, many):
            self.n += 1

        self._hook = hook
        event.listen(engine, "before_cursor_execute", hook)
        return self

    def __exit__(self, *a) -> None:
        event.remove(engine, "before_cursor_execute", self._hook)


def _nhan_ban(db, mau: XepLichCongDoan, them: int, moc) -> None:
    """Nhân bản một dòng đã xếp thành `them` thanh nữa, rải theo giờ để không chồng nhau."""
    for i in range(them):
        db.add(XepLichCongDoan(
            nguon=mau.nguon, lsx_id=mau.lsx_id, lsx_cong_doan_id=mau.lsx_cong_doan_id,
            source_thu_tu=mau.source_thu_tu, loai_buoc=mau.loai_buoc,
            may_id=mau.may_id, department_id=mau.department_id,
            start_at=moc + timedelta(hours=3 * i), finish_at=moc + timedelta(hours=3 * i + 1),
            trang_thai=TT_DA_XEP,
        ))
    db.commit()


def test_ban_lam_viec_khong_phinh_truy_van_theo_so_thanh(
    db, orders, lsx_svc, xl_svc, admin, customer,
):
    _khai_ca_xuong(db)
    lsxs = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    svc = XepLich2Service(db, XepLich2Repository(db), AuditLogRepository(db))
    for l in lsxs:
        svc.tao_nhap(nguon="lsx", id=l.id, actor=admin)
    for l in lsxs:
        svc.tu_xep(nguon="lsx", id=l.id, actor=admin)

    co_gio = db.query(XepLichCongDoan).filter(XepLichCongDoan.start_at.is_not(None)).all()
    assert co_gio, "tự xếp không ra thanh nào — fixture hỏng, không phải chuyện hiệu năng"
    mau = co_gio[0]
    moc = mau.start_at if mau.start_at.tzinfo else mau.start_at.replace(tzinfo=timezone.utc)
    tu, den = (moc - timedelta(days=1)).date(), (moc + timedelta(days=14)).date()

    def do() -> tuple[int, int]:
        db.expire_all()
        s = XepLich2Service(db, XepLich2Repository(db), AuditLogRepository(db))
        with _DemSql() as dem:
            out = s.workspace(tu=tu, den=den)
        return len(out["dong"]), dem.n

    n1, q1 = do()
    _nhan_ban(db, mau, 30, moc)
    n2, q2 = do()

    assert n2 - n1 == 30, "bàn phải bày đủ số thanh vừa thêm"
    doc = (q2 - q1) / (n2 - n1)
    assert doc <= TRAN_CAU_MOI_THANH, (
        f"mỗi thanh thêm vào bàn tốn {doc:.1f} câu SQL (trần {TRAN_CAU_MOI_THANH}). "
        f"{n1} thanh → {q1} câu; {n2} thanh → {q2} câu. Nền của bàn (ca · khoá máy · việc trên "
        f"máy · việc của tổ · quân số) phải hỏi MỘT lần cho cả bàn, không hỏi lại theo từng thanh."
    )


def test_ban_lam_viec_dong_bang_khong_doi_ket_qua(
    db, orders, lsx_svc, xl_svc, admin, customer,
):
    """Gộp truy vấn là chuyện HIỆU NĂNG — số liệu trên bàn phải y hệt lúc hỏi lẻ từng thanh."""
    _khai_ca_xuong(db)
    lsxs = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)
    svc = XepLich2Service(db, XepLich2Repository(db), AuditLogRepository(db))
    for l in lsxs:
        svc.tao_nhap(nguon="lsx", id=l.id, actor=admin)
        svc.tu_xep(nguon="lsx", id=l.id, actor=admin)

    co_gio = db.query(XepLichCongDoan).filter(XepLichCongDoan.start_at.is_not(None)).all()
    moc = co_gio[0].start_at
    moc = moc if moc.tzinfo else moc.replace(tzinfo=timezone.utc)
    tu, den = (moc - timedelta(days=1)).date(), (moc + timedelta(days=14)).date()

    gop = svc.workspace(tu=tu, den=den)
    # Không đóng băng: mỗi dòng tự hỏi lại nền — đường cũ, dùng làm mốc đối chiếu.
    le = svc._workspace(tu=tu, den=den)

    assert [d["muc"] for d in gop["dong"]] == [d["muc"] for d in le["dong"]]
    assert [d["boc_tach"] for d in gop["dong"]] == [d["boc_tach"] for d in le["dong"]]
    assert gop["tai_may"] == le["tai_may"] and gop["tai_to"] == le["tai_to"]


def _mot_lenh_da_xep(db, orders, lsx_svc, admin, customer):
    """Một lệnh đã có nháp + đã tự xếp giờ — nguyên liệu chung cho hai chốt Panel dưới đây."""
    _khai_ca_xuong(db)
    lsx = _hai_lsx_san_sang(db, orders, lsx_svc, admin, customer)[0]
    svc = XepLich2Service(db, XepLich2Repository(db), AuditLogRepository(db))
    svc.tao_nhap(nguon="lsx", id=lsx.id, actor=admin)
    svc.tu_xep(nguon="lsx", id=lsx.id, actor=admin)
    rows = svc.repo.by_lsx(lsx.id)
    assert rows, "tự xếp không ra bước nào — fixture hỏng, không phải chuyện hiệu năng"
    return svc, lsx, rows


def test_boi_canh_cham_moi_buoc_dung_mot_luot(db, orders, lsx_svc, xl_svc, admin, customer):
    """Panel một lệnh chấm luật cho MỖI bước đúng MỘT lượt, và cân đối vật tư đúng MỘT lượt.

    Panel hỏi cùng một câu hai lần cho cùng một đối tượng: `kiem_phat_hanh` chấm từng bước để quyết
    có chặn phát hành không, rồi `_buoc_view` chấm lại chính bước ấy để bày số ra màn. Vật tư cũng
    vậy — cửa phát hành soi bảng cân đối, thẻ tóm tắt soi lại lần nữa. Cả hai đều là thứ đắt nhất
    trong panel (bộ luật kéo theo engine thời lượng; cân đối kéo theo cả dây kho·mua·quy đổi), nên
    chạy đôi là đắt gấp đôi mà không thêm một thông tin nào.

    Đo bằng SỐ LƯỢT TÍNH chứ không bằng số câu SQL: đây là chuyện gọi trùng ở tầng service, đếm
    thẳng chỗ đó thì hỏng là chỉ đúng một nguyên nhân.
    """
    from collections import Counter

    from app.services.giu_cho_service import GiuChoService

    svc, lsx, rows = _mot_lenh_da_xep(db, orders, lsx_svc, admin, customer)

    dem_buoc: Counter = Counter()
    dem_vt = {"n": 0}
    goc_tinh, goc_tt = XepLich2Service._tinh_moi, GiuChoService.trang_thai

    def spy_tinh(self, dong, patch, dur):
        if not patch:
            dem_buoc[dong.id] += 1
        return goc_tinh(self, dong, patch, dur)

    def spy_tt(self, **kw):
        dem_vt["n"] += 1
        return goc_tt(self, **kw)

    XepLich2Service._tinh_moi, GiuChoService.trang_thai = spy_tinh, spy_tt
    try:
        svc.boi_canh(nguon="lsx", id=lsx.id)
    finally:
        XepLich2Service._tinh_moi, GiuChoService.trang_thai = goc_tinh, goc_tt

    thua = {i: n for i, n in dem_buoc.items() if n > 1}
    assert not thua, (
        f"có bước bị chấm lại: {thua}. `kiem_phat_hanh` và `_buoc_view` phải dùng chung kết quả "
        f"`_tinh` của cùng một bước trong khối `ctx.dong_bang`."
    )
    assert dem_vt["n"] <= 1, (
        f"bảng cân đối vật tư chạy {dem_vt['n']} lượt cho một lệnh — cửa phát hành và thẻ tóm tắt "
        f"phải hỏi qua cùng một `release.PhienVatTu`."
    )


def test_boi_canh_dong_bang_khong_doi_ket_qua(db, orders, lsx_svc, xl_svc, admin, customer):
    """Gộp là chuyện hiệu năng — Panel phải nói y hệt số lúc mỗi chỗ tự hỏi lại."""
    svc, lsx, _rows = _mot_lenh_da_xep(db, orders, lsx_svc, admin, customer)
    gop = svc.boi_canh(nguon="lsx", id=lsx.id)
    le = svc._boi_canh(nguon="lsx", id=lsx.id)      # không đóng băng: đường cũ, dùng làm mốc
    assert gop == le
