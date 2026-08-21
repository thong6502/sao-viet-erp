"""Seed demo module KỸ THUẬT MÁY — lịch bảo trì trên máy + phiếu sửa chữa + phiếu bảo trì.

Ba lớp, phải theo thứ tự vì lớp sau ăn lớp trước:

1. **Gói bảo trì** khai lên `may_thiet_bi.fields_theo_loai.lich_bao_tri` — nguồn của mọi "kỳ dự
   kiến" trên màn Lịch. Không có nó thì lịch trống trơn và không bấm tạo phiếu định kỳ được.
2. **Phiếu sửa chữa** — phủ đủ 4 trạng thái để nhìn ra dải màu trên bảng.
3. **Phiếu bảo trì** — phủ: hoàn thành (mốc tính kỳ sau) · đang làm · chờ · QUÁ HẠN · ĐÃ DỜI · đột xuất.

Ngày dùng OFFSET so với hôm nay chứ không cắm ngày cứng: seed cắm "12/08/2026" thì tháng sau mở
lên, phiếu "quá hạn" thành quá hạn 30 ngày và "hạn hôm nay" chẳng còn hôm nay nữa.

Ảnh: sinh PNG thật rồi ghi qua `storage` — phiếu đã đóng BẮT BUỘC có ảnh chứng thực (service chặn),
nên seed mà chỉ ghi bản ghi ảnh trỏ vào hư không thì mở lên là ô ảnh vỡ.

Guard idempotent theo mã phiếu `SC-0001`: đã có thì thôi, chạy lại uvicorn không đẻ thêm.
"""
from __future__ import annotations

import struct
import zlib
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models.ky_thuat_may import (
    GIAI_DOAN_SAU,
    GIAI_DOAN_TRUOC,
    LOAI_BT_DINH_KY,
    LOAI_BT_DOT_XUAT,
    LOAI_PHIEU_BAO_TRI,
    LOAI_PHIEU_SUA_CHUA,
    BaoTriMay,
    KyThuatMayAnh,
    SuaChuaMay,
)
from .models.may_thiet_bi import MayThietBi
from .repositories.user_repo import UserRepository
from .storage import get_storage, make_key, url_from_key

HOM_NAY = None  # đặt trong seed() để mọi mốc trong một lần chạy dùng CHUNG một "hôm nay"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Gói bảo trì theo NHÓM MÁY (thực tế xưởng in offset) ─────────────────────────────────────
# `(mã máy, [(tên gói, số, đơn vị, lệch ngày bắt đầu so với hôm nay, [việc con])])`
# Lệch ngày cố ý rải ra để lịch tháng không dồn hết vào một ô.
_LICH: list[tuple[str, list[tuple[str, int, str, int, list[str]]]]] = [
    ("IN-01", [
        ("Bảo trì tuần máy in", 1, "tuan", -3, [
            "Vệ sinh lô mực & lô nước", "Xả nước bình khí nén", "Kiểm tra đầu phun ẩm",
        ]),
        ("Bảo trì 3 tháng máy in", 3, "thang", -40, [
            "Thay lọc gió máy nén khí", "Bơm mỡ ổ trục & xích truyền",
            "Kiểm tra & căn áp lực lô", "Thay dầu hộp số",
        ]),
    ]),
    ("IN-02", [
        ("Bảo trì tuần máy in", 1, "tuan", -9, [
            "Vệ sinh lô mực & lô nước", "Xả nước bình khí nén",
        ]),
    ]),
    ("IN-04", [
        ("Bảo trì tuần máy in", 1, "tuan", 2, [
            "Vệ sinh lô mực & lô nước", "Kiểm tra đầu phun ẩm",
        ]),
        ("Bảo trì năm máy in", 12, "thang", -300, [
            "Hiệu chuẩn bộ ẩm", "Thay dầu hộp số", "Kiểm tra hệ sấy UV",
        ]),
    ]),
    ("IN-05", [
        ("Bảo trì 3 tháng máy in", 3, "thang", 5, [
            "Thay lọc gió máy nén khí", "Bơm mỡ ổ trục & xích truyền", "Căn áp lực lô",
        ]),
    ]),
    ("CM-03", [
        ("Bảo trì tháng máy cán", 1, "thang", -1, [
            "Vệ sinh trục cán & dao cắt", "Kiểm tra nhiệt trục sấy & cảm biến",
            "Tra dầu bạc đạn trục cán",
        ]),
    ]),
    ("CM-04", [
        ("Bảo trì tháng máy cán", 1, "thang", 8, [
            "Vệ sinh trục cán & dao cắt", "Kiểm tra nhiệt trục sấy & cảm biến",
        ]),
    ]),
    ("BE-01", [
        ("Bảo trì tháng máy bế", 1, "thang", 0, [
            "Kiểm tra bàn ép & thay dao bế mòn", "Bơm mỡ khớp truyền động",
            "Kiểm tra hệ thuỷ lực & dầu",
        ]),
    ]),
    ("BE-03", [
        ("Bảo trì 3 tháng máy bế", 3, "thang", 12, [
            "Tháo & kiểm tra bộ dao bế", "Hiệu chỉnh áp lực bế", "Chạy thử mẫu bế",
        ]),
    ]),
    ("BOI-01", [
        ("Bảo trì tuần máy bồi", 1, "tuan", -2, [
            "Vệ sinh hệ keo & lô tra keo", "Căn chỉnh băng tải & xích",
        ]),
    ]),
]

# ── Phiếu SỬA CHỮA: (máy, bộ phận, mức độ, triệu chứng, nguyên nhân, người báo, lệch ngày, trạng thái)
_SUA_CHUA = [
    ("CM-01", "Bơm đèn UV số 2", "nghiem_trong",
     "Chạy được 20 phút thì đèn UV số 2 tắt, mực không khô, tờ ra dính mặt sau.",
     "Bơm cấp nguồn đèn tụt áp, nghi tụ lọc phồng. Đã gọi hãng mang tụ sang thay.",
     "CN Phạm Văn Nam", -2, "dang_sua"),
    ("BE-01", "Bộ dao bế", "trung_binh",
     "Dao bế gãy một cạnh giữa ca đêm, tờ bế ra bị rách góc.",
     "Dao mòn quá hạn thay. Đã đặt set dao mới, chờ về.",
     "CN Lê Văn Tuấn", -4, "cho_vat_tu"),
    ("IN-02", "Lô nước số 3", "trung_binh",
     "In lem nhẹ ở đơn Catalogue, canh màu mãi không đều ở vùng giữa tờ.",
     None, "TT Bùi Tổ Trưởng", -1, "cho_sua"),
    ("BOI-02", "Băng tải cấp phôi", "nhe",
     "Băng tải trượt khi bồi tấm dày, phôi vào lệch mép 3-4mm.",
     None, "CN Trần Văn Hải", 0, "cho_sua"),
    ("IN-05", "Bơm mực spot color", "trung_binh",
     "Màu Pantone 185C lên không đều, nhạt dần về cuối sản lượng.",
     "Bơm mực spot yếu do bẩn đầu hút. Đã tháo vệ sinh, chạy thử 500 tờ đạt.",
     "CN Nguyễn Văn Bình", -9, "da_sua_xong"),
    ("CM-03", "Cảm biến nhiệt trục sấy", "nhe",
     "Nhiệt trục sấy thỉnh thoảng tụt 15°C rồi tự lên lại, màng cán nổi bọt.",
     "Cảm biến nhiệt lỏng chân, tiếp xúc chập chờn. Đã siết lại và bọc chống rung.",
     "CN Đỗ Thị Mai", -16, "da_sua_xong"),
]

# ── Phiếu BẢO TRÌ: (máy, tên gói/nội dung, loại, lệch ngày kế hoạch, trạng thái, lệch ngày hoàn thành)
_BAO_TRI = [
    ("IN-01", "Bảo trì 3 tháng máy in", LOAI_BT_DINH_KY, -40, "hoan_thanh", -38),
    ("CM-03", "Bảo trì tháng máy cán", LOAI_BT_DINH_KY, -12, "hoan_thanh", -11),
    ("BE-01", "Bảo trì tháng máy bế", LOAI_BT_DINH_KY, 0, "cho_thuc_hien", None),
    ("IN-02", "Bảo trì tuần máy in", LOAI_BT_DINH_KY, -9, "cho_thuc_hien", None),   # QUÁ HẠN
    ("BOI-01", "Bảo trì tuần máy bồi", LOAI_BT_DINH_KY, 4, "cho_thuc_hien", None),  # đã DỜI (bên dưới)
    ("IN-04", "Kiểm tra nhiệt & cảm biến sau sự cố", LOAI_BT_DOT_XUAT, 1, "cho_thuc_hien", None),
]


def _png(rgb: tuple[int, int, int], w: int = 480, h: int = 320) -> bytes:
    """PNG đơn sắc, không cần thư viện ngoài.

    Ảnh demo cố ý TRƠN chứ không cố giả làm ảnh chụp máy thật — nó ở đây để chứng minh luồng
    "không có ảnh thì không đóng được phiếu" chạy đúng, không phải để đánh lừa người xem.
    """
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))

    def _chunk(typ: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(raw, 9))
            + _chunk(b"IEND", b""))


def _them_anh(db: Session, loai_phieu: str, phieu_id: int, giai_doan: str, ten: str) -> None:
    """Ghi file THẬT vào storage rồi tạo bản ghi ảnh — hai việc, thiếu một là ô ảnh vỡ."""
    mau = (0x6B, 0x5B, 0x4A) if giai_doan == GIAI_DOAN_TRUOC else (0x2F, 0x5D, 0x3A)
    key, safe = make_key(f"ky-thuat-may/{loai_phieu}", phieu_id, ten)
    get_storage().save(key, _png(mau), "image/png")
    db.add(KyThuatMayAnh(
        loai_phieu=loai_phieu, phieu_id=phieu_id, giai_doan=giai_doan,
        file_name=safe, file_url=url_from_key(key), file_type="image/png",
    ))


def _may_map(db: Session) -> dict[str, MayThietBi]:
    return {m.ma: m for m in db.execute(select(MayThietBi)).scalars()}


def _hm_id(ma_may: str, i: int, j: int) -> str:
    """`id` gói ỔN ĐỊNH — phiếu bảo trì neo vào đây, đổi tên gói không mất mốc."""
    return f"hm-seed-{ma_may.lower()}-{i}{j}"


def _ensure_lich_bao_tri(db: Session, may: dict[str, MayThietBi]) -> None:
    """Khai gói bảo trì lên máy. KHÔNG đè máy đã có gói — người dùng khai tay là quyền của họ."""
    for i, (ma, goi_list) in enumerate(_LICH):
        m = may.get(ma)
        if m is None:
            continue
        box = dict(m.fields_theo_loai or {})
        if box.get("lich_bao_tri"):
            continue
        box["lich_bao_tri"] = [
            {
                "id": _hm_id(ma, i, j),
                "viec": ten,
                "so": so,
                "don_vi": don_vi,
                "ngay_bat_dau": (HOM_NAY + timedelta(days=lech)).isoformat(),
                "hang_muc": [{"id": f"{_hm_id(ma, i, j)}-{k}", "ten": v} for k, v in enumerate(viec)],
            }
            for j, (ten, so, don_vi, lech, viec) in enumerate(goi_list)
        ]
        m.fields_theo_loai = box      # gán DICT MỚI: sửa tại chỗ thì SQLAlchemy không thấy gì đổi
    db.flush()


def _seed_sua_chua(db: Session, may: dict[str, MayThietBi], tho_id: int | None) -> int:
    from .repositories.ky_thuat_may_repo import KyThuatMayRepository
    repo = KyThuatMayRepository(db)

    n = 0
    for ma, bo_phan, muc_do, trieu_chung, nguyen_nhan, nguoi_bao, lech, tt in _SUA_CHUA:
        m = may.get(ma)
        if m is None:
            continue
        thoi_diem = datetime.combine(HOM_NAY + timedelta(days=lech),
                                     datetime.min.time()).replace(tzinfo=timezone.utc) + timedelta(hours=9, minutes=20)
        p = SuaChuaMay(
            # Mã lấy từ repo chứ KHÔNG cắm cứng: DB có thể đã có phiếu người dùng tự tạo mang
            # đúng `SC-0001`, cắm cứng là vỡ ràng buộc unique ngay lúc khởi động uvicorn.
            ma=repo.next_ma_sua_chua(), may_id=m.id, bo_phan_hong=bo_phan, mo_ta=trieu_chung,
            muc_do=muc_do, nguoi_bao_ten=nguoi_bao, thoi_diem=thoi_diem,
            nguyen_nhan_phuong_an=nguyen_nhan, trang_thai=tt,
            created_at=thoi_diem, updated_at=thoi_diem,
        )
        if tt == "cho_vat_tu":
            p.ghi_chu = "Chờ set dao bế mới của Bobst VN, hẹn 3 ngày nữa về kho."
        if tt == "da_sua_xong":
            p.hoan_thanh_at = thoi_diem + timedelta(days=1)
            p.hoan_thanh_boi = tho_id
        db.add(p)
        db.flush()

        # Ảnh: hiện trạng cho phiếu nặng/đang dở; ảnh chứng thực BẮT BUỘC cho phiếu đã đóng.
        if muc_do != "nhe" or tt == "da_sua_xong":
            _them_anh(db, LOAI_PHIEU_SUA_CHUA, p.id, GIAI_DOAN_TRUOC, "hien_trang.png")
        if tt == "da_sua_xong":
            _them_anh(db, LOAI_PHIEU_SUA_CHUA, p.id, GIAI_DOAN_SAU, "sau_sua.png")
        n += 1
    return n


def _seed_bao_tri(db: Session, may: dict[str, MayThietBi], tho_id: int | None,
                  tho_ten: str | None) -> int:
    from .repositories.ky_thuat_may_repo import KyThuatMayRepository
    repo = KyThuatMayRepository(db)

    # Tra ngược gói theo (máy, tên gói) để phiếu neo đúng `goi_id` + chép chu kỳ/việc con.
    goi_theo_may: dict[tuple[str, str], dict] = {}
    for ma, m in may.items():
        for g in (m.fields_theo_loai or {}).get("lich_bao_tri", []) or []:
            if isinstance(g, dict) and g.get("viec"):
                goi_theo_may[(ma, g["viec"])] = g

    n = 0
    for ma, ten_goi, loai, lech_kh, tt, lech_xong in _BAO_TRI:
        m = may.get(ma)
        if m is None:
            continue
        goi = goi_theo_may.get((ma, ten_goi))
        ngay_kh = HOM_NAY + timedelta(days=lech_kh)
        p = BaoTriMay(
            ma=repo.next_ma_bao_tri(), may_id=m.id, loai=loai,
            goi_id=(goi or {}).get("id"), goi_ten=ten_goi,
            chu_ky_so=(goi or {}).get("so"), chu_ky_don_vi=(goi or {}).get("don_vi"),
            ngay_ke_hoach=ngay_kh, ngay_ke_hoach_goc=ngay_kh,
            hang_muc=[
                {"id": h.get("id"), "ten": h.get("ten"), "xong": False}
                for h in ((goi or {}).get("hang_muc") or [])
            ] or None,
            trang_thai=tt,
        )
        if loai == LOAI_BT_DOT_XUAT:
            p.ghi_chu = "Phát sinh sau sự cố tụt nhiệt ở CM-03, kiểm tra phòng ngừa cùng dòng máy."
        if tt == "hoan_thanh":
            # Người làm = người bấm xác nhận xong; phiếu chưa xong thì KHÔNG mang tên ai.
            p.nguoi_thuc_hien_id, p.nguoi_thuc_hien = tho_id, tho_ten
        if tt == "hoan_thanh" and lech_xong is not None:
            p.ngay_hoan_thanh = HOM_NAY + timedelta(days=lech_xong)
            p.hoan_thanh_boi = tho_id
            p.hang_muc = [{**h, "xong": True} for h in (p.hang_muc or [])]
        db.add(p)
        db.flush()

        # Phiếu BOI-01: minh hoạ ĐÃ DỜI LỊCH — "đã dời" là cờ dẫn xuất từ `ngay_ke_hoach_goc`.
        if ma == "BOI-01":
            p.ngay_ke_hoach_goc = ngay_kh - timedelta(days=5)
            p.ly_do_doi = "Máy đang chạy đơn gấp của An Phát, dời sang đầu tuần sau."
        if tt == "hoan_thanh":
            _them_anh(db, LOAI_PHIEU_BAO_TRI, p.id, GIAI_DOAN_TRUOC, "truoc_bao_tri.png")
            _them_anh(db, LOAI_PHIEU_BAO_TRI, p.id, GIAI_DOAN_SAU, "sau_bao_tri.png")
        n += 1
    return n


def _tho_sua_chua(db: Session) -> tuple[int | None, str | None]:
    """Tài khoản demo cho vai "Thợ sửa chữa" (seed ROLES đã tạo vai, chưa có người)."""
    from .repositories.rbac_repo import DepartmentRepository, RoleRepository
    from .security import hash_password

    users = UserRepository(db)
    u = users.get_by_username("kythuat1")
    if u is None:
        u = users.create(username="kythuat1", name="Vũ Kỹ Thuật",
                         password_hash=hash_password("123456"))
    sx = DepartmentRepository(db).get_by_name("Sản xuất")
    if sx is not None:
        role = RoleRepository(db).get_by_name_and_department("Thợ sửa chữa", sx.id)
        users.set_assignment(u, department_id=sx.id,
                             role_id=(role.id if role else None), is_active=True)
    return u.id, u.name


def _da_seed(db: Session, may: dict[str, MayThietBi]) -> bool:
    """Đã seed chưa — nhận biết bằng GÓI mang tiền tố `hm-seed-`, thứ chỉ seed này tạo ra.

    ⚠️ ĐỪNG guard theo mã phiếu `SC-0001`: mã sinh tuần tự nên phiếu người dùng tự tạo đầu tiên
    cũng mang đúng mã đó — guard kiểu ấy tưởng đã seed rồi và im lặng bỏ qua (đã dính 12/08/2026).
    """
    for m in may.values():
        for g in (m.fields_theo_loai or {}).get("lich_bao_tri", []) or []:
            if isinstance(g, dict) and str(g.get("id") or "").startswith("hm-seed-"):
                return True
    return False


def seed_ky_thuat_may(db: Session) -> None:
    """Idempotent theo gói `hm-seed-*` (xem `_da_seed`)."""
    global HOM_NAY
    may = _may_map(db)
    if not may or _da_seed(db, may):
        return   # chưa có máy thì seed phiếu cũng vô nghĩa; đã seed thì thôi

    HOM_NAY = _utcnow().date()
    tho_id, tho_ten = _tho_sua_chua(db)
    _ensure_lich_bao_tri(db, may)
    may = _may_map(db)          # nạp lại để lấy gói vừa khai
    _seed_sua_chua(db, may, tho_id)
    _seed_bao_tri(db, may, tho_id, tho_ten)
    db.commit()
