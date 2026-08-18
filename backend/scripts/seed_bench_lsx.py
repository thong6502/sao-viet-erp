"""Seed dữ liệu ĐO TẢI cho module Kế hoạch sản xuất — mặc định 100.000 lệnh.

Vì sao có file này: DB dev chỉ có vài lệnh nên truy vấn nào cũng nhanh, không cách gì biết chỗ nào
vỡ ở quy mô thật. Script bơm dữ liệu đúng HÌNH DẠNG THẬT (đơn → dòng đơn → lệnh → công đoạn) để đo
`EXPLAIN ANALYZE` và thời gian API trước/sau khi tối ưu.

Sinh ra (mặc định):
  20.000 `orders` (đã chốt + đã chuyển xuống SX) × 5 `order_lines` = 100.000 dòng đơn
  → ~98.000 `lsx` × 4 `lsx_cong_doan` = ~392.000 bước.
  Cứ 10 đơn CHỪA 1 dòng chưa lên lệnh ⇒ ~2.000 đơn ở lại HÀNG CHỜ (để đo luôn tab đó).
  `trang_thai` rải đều 5 mã ⇒ số trên tab (facets) có ý nghĩa.

`loai` để `san_xuat_moi` (KHÔNG phải `noi_bo`) là CỐ Ý: guard chống sinh lệnh trùng
(`LsxRepository.by_order_lines`) chỉ soi `san_xuat_moi`; để mã khác thì hàng chờ tưởng cả 100.000
dòng đơn đều chưa có lệnh, số đo tab Hàng chờ thành rác.

⚠ Script GHI THẲNG vào DB ở `backend/.env` — tức Postgres dev `127.0.0.1:5433/svn_erp_local`,
không phải SQLite vứt đi. Nên có hai cửa chặn: `SEED_BENCH=1` và một lần gõ `yes` (bỏ qua bằng
`--yes` khi chạy không tương tác).

Chạy:
    cd backend && SEED_BENCH=1 python scripts/seed_bench_lsx.py --yes
    cd backend && SEED_BENCH=1 python scripts/seed_bench_lsx.py --so-luong 20000 --yes
    cd backend && SEED_BENCH=1 python scripts/seed_bench_lsx.py --xoa --yes     # dọn sạch
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import insert, select, text

sys.path.insert(0, ".")
from app.db import SessionLocal, engine  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.lsx import LOAI_MOI, Lsx, LsxCongDoan  # noqa: E402
from app.models.order import STATUS_ORDERED, Order, OrderLine  # noqa: E402
from app.models.user import User  # noqa: E402

# Tiền tố nhận diện — MỌI thứ script đẻ ra đều mang nó, và `--xoa` chỉ xoá theo nó.
TIEN_TO = "BENCH-"
DONG_MOI_DON = 5
BUOC_MOI_LENH = 4
# 1 lô = 1 vòng insert cho cả 4 bảng. 2.000 đơn/lô ⇒ 40.000 dòng bước/lô, vừa tay Postgres.
DON_MOI_LO = 2000

TRANG_THAI_RAI = ["nhap", "nhap", "san_sang", "da_lap_ke_hoach", "da_phat_hanh", "cho_bo_sung"]
TEN_SP = [
    "Catalogue A4 - 32 trang", "Hop giay couche 300", "Tem nhan decal 7 mau",
    "Sach A5 ruot 160 trang", "Tui giay quai lua", "Bao bi banh trung thu",
    "Voucher 2 mat can mo", "Kep file A4 be noi",
]
TEN_BUOC = ["Che ban", "In offset", "Can mang", "Be - dan"]
NHOM_BUOC = ["prepress", "print", "finishing", "finishing"]


def _xac_nhan(bo_qua: bool, viec: str) -> None:
    if os.getenv("SEED_BENCH") != "1":
        raise SystemExit("Thieu SEED_BENCH=1 — script nay ghi vao DB dev that, khong chay ho duoc.")
    print(f"DB   : {engine.url.render_as_string(hide_password=True)}")
    print(f"VIEC : {viec}")
    if bo_qua:
        return
    if input("Go 'yes' de chay: ").strip().lower() != "yes":
        raise SystemExit("Da huy.")


def _mot_lo(db, *, lo: int, so_don: int, khach: list[int], sale: int | None, moc: datetime) -> int:
    """Ghi 1 lô: đơn → dòng đơn → lệnh → bước. Trả số LỆNH đã ghi."""
    dau = lo * DON_MOI_LO

    don_ids = db.scalars(
        insert(Order).returning(Order.id),
        [
            {
                "order_no": f"{TIEN_TO}O{dau + i:06d}",
                "customer_id": khach[(dau + i) % len(khach)] if khach else None,
                "sale_user_id": sale,
                "status": STATUS_ORDERED,
                # Hai mốc này là điều kiện vào HÀNG CHỜ — thiếu một cái là đơn không bao giờ hiện.
                "ordered_at": moc - timedelta(minutes=dau + i),
                "san_xuat_released_at": moc - timedelta(minutes=dau + i),
                "delivery_committed_date": (moc + timedelta(days=(dau + i) % 45)).date(),
                "is_rush": (dau + i) % 17 == 0,
                "created_at": moc - timedelta(minutes=dau + i),
            }
            for i in range(so_don)
        ],
    ).all()

    dong = []
    for k, oid in enumerate(don_ids):
        for j in range(DONG_MOI_DON):
            dong.append({
                "order_id": oid,
                "description": TEN_SP[(dau + k + j) % len(TEN_SP)],
                "qty": 500 + ((dau + k + j) % 40) * 250,
                "don_vi_tinh": "cái",
            })
    dong_ids = db.scalars(insert(OrderLine).returning(OrderLine.id), dong).all()

    lenh = []
    for n, (lid, d) in enumerate(zip(dong_ids, dong)):
        # Cứ 10 đơn chừa 1 dòng chưa lên lệnh ⇒ đơn đó ở lại hàng chờ.
        if (n // DONG_MOI_DON) % 10 == 0 and n % DONG_MOI_DON == DONG_MOI_DON - 1:
            continue
        stt = dau * DONG_MOI_DON + n
        lenh.append({
            "ma": f"{TIEN_TO}{stt:07d}",
            "loai": LOAI_MOI,
            "ten": d["description"],
            "order_id": d["order_id"],
            "order_line_id": lid,
            "so_luong_dat": d["qty"],
            "don_vi_tinh": "cái",
            "so_to_ke_hoach": d["qty"] // 4 + 120,
            "so_to_nguyen": d["qty"] // 8 + 60,
            "so_con": 4,
            "han_giao_khach": (moc + timedelta(days=stt % 45)).date(),
            "han_hoan_thanh_sx": (moc + timedelta(days=max(0, stt % 45 - 3))).date(),
            "is_rush": stt % 17 == 0,
            "trang_thai": TRANG_THAI_RAI[stt % len(TRANG_THAI_RAI)],
            "created_by": sale,
            "nguoi_phu_trach_id": sale,
            # Rải theo PHÚT để `ORDER BY created_at DESC` có thứ tự thật; cả trăm nghìn dòng cùng
            # một mốc thì index nào trông cũng như nhau, đo ra số vô nghĩa.
            "created_at": moc - timedelta(minutes=stt),
            "updated_at": moc - timedelta(minutes=stt),
        })
    lenh_ids = db.scalars(insert(Lsx).returning(Lsx.id), lenh).all()

    buoc = []
    for lsx_id in lenh_ids:
        for t in range(BUOC_MOI_LENH):
            buoc.append({
                "step_key": str(uuid4()),
                "lsx_id": lsx_id,
                "thu_tu": t,
                "ten": TEN_BUOC[t],
                "nhom": NHOM_BUOC[t],
                "loai_buoc": "may",
                "so_luong_vao": 1000,
                "so_luong_ra": 1000,
                "don_vi_vao": "to",
                "don_vi_ra": "to" if t < BUOC_MOI_LENH - 1 else "cai",
            })
    db.execute(insert(LsxCongDoan), buoc)
    db.commit()
    return len(lenh_ids)


def _seed(db, so_lenh: int) -> None:
    khach = list(db.execute(select(Customer.id).limit(30)).scalars())
    sale = db.execute(select(User.id).limit(1)).scalar_one_or_none()
    if not khach:
        print("⚠ DB chua co khach hang nao — lenh se khong co ten khach (van do duoc).")
    so_don = -(-so_lenh // DONG_MOI_DON)  # làm tròn LÊN
    moc = datetime.now(timezone.utc)
    t0, da_ghi = time.time(), 0
    for lo in range(-(-so_don // DON_MOI_LO)):
        n = min(DON_MOI_LO, so_don - lo * DON_MOI_LO)
        da_ghi += _mot_lo(db, lo=lo, so_don=n, khach=khach, sale=sale, moc=moc)
        print(f"  lo {lo + 1}: {da_ghi:,} lenh · {time.time() - t0:.0f}s", flush=True)
    print(f"XONG: {da_ghi:,} lenh trong {time.time() - t0:.0f}s")


def _xoa(db) -> None:
    # Thứ tự bắt buộc: `lsx` trỏ FK vào `orders`/`order_lines` mà KHÔNG có ondelete, nên phải xoá
    # lệnh trước. `lsx_cong_doan` và `order_lines` tự đi theo nhờ ondelete=CASCADE.
    n1 = db.execute(text("DELETE FROM lsx WHERE ma LIKE :p"), {"p": f"{TIEN_TO}%"}).rowcount
    n2 = db.execute(text("DELETE FROM orders WHERE order_no LIKE :p"), {"p": f"{TIEN_TO}%"}).rowcount
    db.commit()
    print(f"Da xoa {n1:,} lenh · {n2:,} don (buoc + dong don theo CASCADE).")


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed / don du lieu do tai module Ke hoach SX.")
    ap.add_argument("--so-luong", type=int, default=100_000, help="so LENH can sinh (mac dinh 100000)")
    ap.add_argument("--xoa", action="store_true", help="xoa sach du lieu mang tien to BENCH-")
    ap.add_argument("--yes", action="store_true", help="bo qua cau hoi xac nhan")
    a = ap.parse_args()

    _xac_nhan(a.yes, "XOA du lieu BENCH-" if a.xoa else f"GHI ~{a.so_luong:,} lenh BENCH-")
    db = SessionLocal()
    try:
        if a.xoa:
            _xoa(db)
        else:
            _seed(db, a.so_luong)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
