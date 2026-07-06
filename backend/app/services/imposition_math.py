"""Imposition math — phần số học BÌNH BÀI dùng chung giữa pricing_engine và endpoint
Kiểm thử (preview) của Kiểu bình bài.

Mục tiêu: KHÔNG lệch client/server. Ba hàm lõi (số con thành phẩm/tờ, số bản kẽm, số
lượt-màu mực) được `pricing_engine` gọi trực tiếp ở đường tính giá thật; endpoint
`POST /api/imposition-types/preview` cũng gọi CHÍNH các hàm này → cùng một nguồn công thức.

Các đại lượng suy diễn (số tờ lý thuyết, lượt qua máy, giờ chạy) là con số "lý thuyết"
phục vụ kiểm thử hệ số bình bài — không kèm hao hụt/yield hay perfecting/multi-pass của máy
(những thứ đó thuộc về DM Máy + đường tính giá đầy đủ, không thuộc bản thân quy tắc bình bài).
"""
from __future__ import annotations

import math


def finished_pieces_per_sheet(geometric_pieces: int, finished_factor: float) -> int:
    """Số con THÀNH PHẨM trên 1 tờ = số con hình học × hệ số thành phẩm (tự trở = ½).

    Giữ đúng nhánh của pricing_engine: hệ số = 1.0 → giữ nguyên số con hình học; khác 1.0
    → floor rồi kẹp sàn 1 (một tờ luôn ra ≥ 1 con)."""
    geo = int(geometric_pieces)
    if finished_factor == 1.0:
        return geo
    return max(1, int(math.floor(geo * float(finished_factor))))


def plates_count(colors: int, plate_set_factor: float, forms: int) -> int:
    """Số BẢN KẼM = số màu × hệ số bộ kẽm × số form/tay (làm tròn)."""
    return int(round(int(colors) * float(plate_set_factor) * int(forms)))


def ink_impressions(total_sheets: int, colors: int, ink_pass_factor: float) -> int:
    """Số LƯỢT-MÀU (nuôi tiền mực) = số tờ sản xuất × số màu × hệ số lượt in màu (làm tròn)."""
    return int(round(int(total_sheets) * int(colors) * float(ink_pass_factor)))


def preview(
    *,
    finished_factor: float,
    pass_count: float,
    plate_set_factor: float,
    ink_pass_factor: float,
    geometric_pieces: int,
    quantity: int,
    production_sheets: int,
    colors: int,
    forms: int,
    machine_speed: float,
) -> dict:
    """Chạy thử một quy tắc bình bài với input giống tình huống tính giá thật.

    Trả về đúng các biến engine dùng: số con TP/tờ, số tờ lý thuyết, lượt qua máy,
    giờ chạy, số bản kẽm, số lượt-màu mực."""
    finished_pieces = finished_pieces_per_sheet(geometric_pieces, finished_factor)
    theoretical_sheets = (
        math.ceil(int(quantity) / finished_pieces)
        if finished_pieces > 0 and int(quantity) > 0
        else 0
    )
    machine_sheets = int(round(int(production_sheets) * float(pass_count)))
    run_hours = (
        machine_sheets / float(machine_speed) if float(machine_speed) > 0 else 0.0
    )
    plates = plates_count(colors, plate_set_factor, forms)
    impressions = ink_impressions(production_sheets, colors, ink_pass_factor)
    return {
        "finished_pieces_per_sheet": finished_pieces,
        "theoretical_sheets": theoretical_sheets,
        "machine_sheets": machine_sheets,
        "run_hours": round(run_hours, 4),
        "plates": plates,
        "ink_impressions": impressions,
    }
