"""Dọn các bảng Kho MỒ CÔI/cũ trong dev.db (từ bản WMS đã gỡ) để tránh xung đột
schema với Kho P0. GIỮ NGUYÊN mọi dữ liệu khác (warehouses, materials, customers,
orders, quotations...). create_all sẽ dựng lại stock_lots + stock_moves sạch khi
khởi động backend.

Chạy khi ĐÃ DỪNG backend (file dev.db không bị khóa):
    cd backend && python scripts/clean_stale_kho_tables.py
"""
import os
import sqlite3

# Bảng cũ/mồ côi cần bỏ (schema khác Kho P0 hoặc không còn dùng).
STALE = [
    "stock_moves",            # cũ: item_id-based → đụng stock_moves mới (material_id)
    "stock_vouchers",
    "stock_voucher_lines",
    "wh_items",
    "wh_lots",
    "wh_locations",
    "wh_item_groups",
    "wh_item_statuses",
    "wh_uoms",
    "wh_uom_conversions",
    "wh_voucher_types",
    "wh_reasons",
    "wh_voucher_type_reasons",
    "wh_stock_norms",
    "wh_pricing_rules",
]

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dev.db")

if not os.path.exists(DB):
    print(f"Không thấy {DB} — bỏ qua (backend sẽ tự tạo mới).")
    raise SystemExit(0)

# Sao lưu trước cho chắc.
import shutil

bak = DB + ".bak"
shutil.copy2(DB, bak)
print(f"Đã sao lưu: {bak}")

conn = sqlite3.connect(DB)
cur = conn.cursor()
existing = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
dropped = []
for t in STALE:
    if t in existing:
        cur.execute(f'DROP TABLE IF EXISTS "{t}"')
        dropped.append(t)
# Bỏ dấu migration 0012 (nếu có) để không lẫn — migration đó đã bị gỡ khỏi code.
try:
    cur.execute("DELETE FROM schema_migrations WHERE id = '0012_warehouse_expand'")
except sqlite3.OperationalError:
    pass
conn.commit()
conn.close()

print("Đã bỏ bảng cũ:", ", ".join(dropped) if dropped else "(không có bảng cũ nào)")
print("Xong. Khởi động lại backend — create_all sẽ dựng stock_lots + stock_moves mới.")
