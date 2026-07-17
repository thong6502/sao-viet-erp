"""CỘNG THÊM (không wipe) phiếu golden 'Hộp bộ đôi Đậu trái Italy + Rổ bông' vào dev.db → hiện trên UI.

Idempotent: get-or-create theo `ma`. Thêm 1 giấy (D250 khổ 44,5×64, 17.100đ/kg) + 8 công đoạn box
(mã 'CDB-*') + 1 loại SP + phiếu PTG-2026-0006. KHÔNG đụng 5 phiếu PTG-2026-0001..0005 đang có.

Đơn giá công đoạn để ở `run_rate` (KHÔNG override ở dòng) vì resolver chỉ gắn công thức khi
dòng don_gia=0. Số tờ thủ công (tắt bù hao tự): net 2000 → +250 bù = 2250 (giấy) → −150 hao = 2100 (sau in).

Chạy:  cd backend && PYTHONIOENCODING=utf-8 python scripts/seed_hop_doi_add.py
"""
from __future__ import annotations

import sys
from sqlalchemy import select, text

sys.path.insert(0, ".")
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models.cong_doan import CongDoan  # noqa: E402
from app.models.loai_san_pham import LoaiSanPham  # noqa: E402
from app.models.vat_lieu_kho import ChungLoaiGiay, GiayNguyen  # noqa: E402
from app.models.phieu_tinh_gia import PhieuThanhPham, PhieuThanhPhan, PhieuTinhGia  # noqa: E402
from app.services.tinh_gia_service import compute_phieu_snapshot  # noqa: E402

WEIGHT = "dinh_luong * dai_nguyen * rong_nguyen * don_gia_kg * to_nguyen"


def _vi(n) -> str:
    n = float(n or 0)
    if n == int(n):
        return f"{int(n):,}".replace(",", ".")
    return f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def get_or_create(db, model, ma, **fields):
    obj = db.execute(select(model).where(model.ma == ma)).scalar_one_or_none()
    if obj is None:
        obj = model(ma=ma, **fields)
        db.add(obj)
    else:
        for k, v in fields.items():
            setattr(obj, k, v)
    db.flush()
    return obj


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # ── 1. Chủng loại + Giấy D250 khổ 44,5×64 (mua theo cân, 17.100đ/kg) ──────────
        cl = get_or_create(db, ChungLoaiGiay, "DUPLEX", ten="Duplex (2 mặt: 1 bóng 1 xám)", be_mat="nham")
        giay = get_or_create(
            db, GiayNguyen, "D250-BOI-44.5x64",
            ten="Giấy D250 bồi 44,5×64 (17.100đ/kg)", chung_loai_giay_id=cl.id, gsm=250,
            kho_rong=445, kho_dai=640, tho="canh_dai", don_vi_gia="kg", don_gia=17100,
            cong_thuc_gia=WEIGHT,
        )

        # ── 2. Công đoạn cho hộp bồi sóng (mã CDB-*) — đơn giá ở run_rate ─────────────
        def cdb(ma, ten, nhom, ct, run_rate):
            return get_or_create(db, CongDoan, ma, ten=ten, nhom=nhom, cong_thuc_gia=ct,
                                 che_do_tinh="theo_san_luong", pricing_basis="per_other",
                                 run_rate=run_rate, kieu_bu_hao="khong")

        c_in = cdb("CDB-IN", "In offset 4 màu (khoán, gồm kẽm)", "print",
                   "1200000 + 100000 * so_mau", 0)
        c_can = cdb("CDB-CAN", "Cán màng bóng (m²)", "finishing",
                    "dai_in * rong_in * don_gia * to_sau_in", 1950)
        c_song = cdb("CDB-BOI-SONG", "Bồi sóng E 2 lớp 120/120 (m²)", "finishing",
                     "0.43 * 0.635 * don_gia * to_sau_in", 4100)
        c_boi = cdb("CDB-BOI-NEN", "Bồi nền (m²)", "finishing",
                    "0.43 * 0.635 * don_gia * to_sau_in", 1000)
        c_khuon = cdb("CDB-KHUON-BE", "Khuôn bế (một lần)", "finishing", "don_gia", 800000)
        c_be = cdb("CDB-BE", "Bế thành phẩm (theo con)", "finishing",
                   "so_luong / so_tp * don_gia", 300)
        c_dan = cdb("CDB-DAN", "Dán thành phẩm (/sp)", "finishing", "so_luong * don_gia", 300)
        c_dong = cdb("CDB-DONG-GOI", "Đóng gói (/sp)", "finishing", "so_luong * don_gia", 50)
        c_gh = cdb("CDB-GH", "Giao hàng (khoán chuyến)", "finishing", "don_gia", 800000)

        # ── 3. Loại sản phẩm ─────────────────────────────────────────────────────────
        lsp = get_or_create(
            db, LoaiSanPham, "LSP-HOP-BOI", ten="Hộp bồi sóng E (ghép bài)",
            structural_type="box", box_sub_type="corrugated",
            routing_template=[c_in.id, c_can.id, c_song.id, c_boi.id, c_khuon.id,
                              c_be.id, c_dan.id, c_dong.id, c_gh.id],
        )
        db.commit()

        # ── 4. Phiếu PTG-2026-0006 (xoá bản cũ SẠCH — SQLite không cascade FK, phải xoá con
        #       tường minh theo thứ tự: thành phẩm/vật tư → thành phần → phiếu) ───────────────
        ph_ids = [r[0] for r in db.execute(
            text("SELECT id FROM phieu_tinh_gia WHERE ma = 'PTG-2026-0006'"))]
        if ph_ids:
            ph = ",".join(str(i) for i in ph_ids)
            tp_ids = [r[0] for r in db.execute(
                text(f"SELECT id FROM phieu_thanh_phan WHERE phieu_id IN ({ph})"))]
            if tp_ids:
                tps = ",".join(str(i) for i in tp_ids)
                db.execute(text(f"DELETE FROM phieu_thanh_pham WHERE thanh_phan_id IN ({tps})"))
                db.execute(text(f"DELETE FROM phieu_vat_tu WHERE thanh_phan_id IN ({tps})"))
            db.execute(text(f"DELETE FROM phieu_thanh_phan WHERE phieu_id IN ({ph})"))
            db.execute(text(f"DELETE FROM phieu_tinh_gia WHERE id IN ({ph})"))
            db.commit()

        p = PhieuTinhGia(
            ma="PTG-2026-0006",
            ten_san_pham="Hộp bộ đôi Đậu trái Italy + Rổ bông (ghép bài)",
            kho_thanh_pham="130×67×145 + 73×73×233 mm (mỗi loại 2000)",
            so_luong=4000, loai_san_pham_id=lsp.id, ktv="Sếp Sơn",
            ghi_chu="Báo giá gốc (Excel): giá vốn 3.001đ/sp · nhận 10% → 3.301 · duyệt 3.300. "
                    "Đóng gói + Giao hàng tính như công đoạn sau in.",
        )
        tp = PhieuThanhPhan(
            thu_tu=0, ten="Hộp bộ đôi (ghép 2 con/tờ)", loai_san_pham_id=lsp.id,
            giay_id=giay.id, quy_cach_in="mot_mat", so_mau_a=4, so_mau_b=0,
            kho_nguyen_dai=640, kho_nguyen_rong=445,  # khổ giấy nguyên 44,5×64 (nhập trên phiếu, đè danh mục)
            kho_in_dai=640, kho_in_rong=435,          # khổ tờ in 43,5×64
            dai_thanh_pham=145, rong_thanh_pham=130,  # chỉ hiển thị (con_auto tắt)
            con_auto=False, so_con=2,                 # ghép 2 con/tờ
            co_in=False,                              # kẽm gộp trong khoán In
            tinh_bu_hao_cd=False, bu_hao_so_to=250, hao_so_to=150,  # 2000 → 2250 giấy → 2100 sau in
        )
        tp.thanh_phams = [
            PhieuThanhPham(thu_tu=0, cong_doan_id=c_in.id, ten="In offset 4 màu (khoán, gồm kẽm)"),
            PhieuThanhPham(thu_tu=1, cong_doan_id=c_can.id, ten="Cán màng bóng"),
            PhieuThanhPham(thu_tu=2, cong_doan_id=c_song.id, ten="Bồi sóng E 2 lớp 120/120"),
            PhieuThanhPham(thu_tu=3, cong_doan_id=c_boi.id, ten="Bồi (nền) 1.000đ/m²"),
            PhieuThanhPham(thu_tu=4, cong_doan_id=c_khuon.id, ten="Khuôn bế (một lần)"),
            PhieuThanhPham(thu_tu=5, cong_doan_id=c_be.id, ten="Bế thành phẩm"),
            PhieuThanhPham(thu_tu=6, cong_doan_id=c_dan.id, ten="Dán thành phẩm"),
            PhieuThanhPham(thu_tu=7, cong_doan_id=c_dong.id, ten="Đóng gói"),
            PhieuThanhPham(thu_tu=8, cong_doan_id=c_gh.id, ten="Giao hàng (Củ Chi)"),
        ]
        p.thanh_phans = [tp]
        db.add(p)
        db.flush()
        res = compute_phieu_snapshot(db, p)
        db.commit()

        # ── 5. In kết quả để soi ─────────────────────────────────────────────────────
        m = res["meta"]
        comp = m["components"][0]
        print("=" * 90)
        print(f"✔ ĐÃ THÊM {p.ma}: {p.ten_san_pham}")
        print(f"  con/tờ={comp['con']} · net={comp['to_net']} · giấy(to_nguyen)={comp['to_nguyen']} · "
              f"sau in={comp['to_sau_in']} · bù tay={comp['bu_hao_tay']} · hao tay={comp['hao_tay']}")
        print("-" * 90)
        for g in res["groups"]:
            for r in g["rows"]:
                print(f"  {r['ten'].split(' · ')[-1][:38]:38} {_vi(round(r['gia_don_sp'])):>10}đ/sp   "
                      f"[{r['thanh_tien'] and _vi(r['thanh_tien'])}đ]")
        print("-" * 90)
        print(f"  ĐƠN GIÁ VỐN: {_vi(round(m['gia_von_don']))}đ/sp  (Excel 3.001)   |  "
              f"Tổng {_vi(res['grand_total'])}đ")
        if res.get("warnings"):
            print("  ⚠", res["warnings"])
        print("=" * 90)
    finally:
        db.close()


if __name__ == "__main__":
    main()
