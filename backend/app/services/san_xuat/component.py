"""Thành phần liên thông của một lần phát hành (§4.1).

Đơn vị phát hành KHÔNG phải một LSX lẻ mà là cả một thành phần liên thông: một nhóm thành phẩm
+ các LSX của nhóm + phụ thuộc chéo + Bài ghép dùng chung + những nhóm khác bị nối qua CÙNG Bài
ghép đó. Không được phát hành một nhánh trong khi nhánh phụ thuộc còn lại chưa sẵn sàng.

Ta bao đóng (transitive closure) từ tập LSX hạt giống theo BA quan hệ tới khi ổn định:
  1. Cùng nhóm thành phẩm  (same order_id + same `nhom` — dòng không-nhom không kéo ai theo).
  2. Cùng một Bài ghép      (thành viên bài ghép kéo nhau vào).
  3. Phụ thuộc chéo          (cạnh nối hai LSX khác nhau).
"""
from __future__ import annotations

from dataclasses import dataclass

from ...repositories.san_xuat_repo import SanXuatRepository


@dataclass
class ThanhPhan:
    lsx_ids: set[int]
    bai_ghep_ids: set[int]


def thanh_phan_lien_thong(repo: SanXuatRepository, seed_lsx_ids: set[int]) -> ThanhPhan:
    lsx_ids: set[int] = set(seed_lsx_ids)
    bg_ids: set[int] = set()

    changed = True
    while changed:
        changed = False

        # (2) Bài ghép: kéo cả thành viên.
        new_bg = repo.bai_ghep_ids_cua_lsx(lsx_ids)
        if not new_bg.issubset(bg_ids):
            bg_ids |= new_bg
            changed = True
        bg_members = repo.lsx_ids_cua_bai_ghep(bg_ids)
        if not bg_members.issubset(lsx_ids):
            lsx_ids |= bg_members
            changed = True

        # (1) Cùng nhóm thành phẩm.
        same = repo.same_group_lsx(lsx_ids)
        if not same.issubset(lsx_ids):
            lsx_ids |= same
            changed = True

        # (3) Phụ thuộc chéo.
        nb = repo.cross_lsx_dep_neighbors(lsx_ids)
        if not nb.issubset(lsx_ids):
            lsx_ids |= nb
            changed = True

    return ThanhPhan(lsx_ids=lsx_ids, bai_ghep_ids=bg_ids)
