"""Ports (interfaces) the Sản phẩm (Product catalog) screen DEPENDS ON.

Implemented live using materials tables (type='paper') — SEAM-03.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from ..models.material import Material

class PaperMasterRef:
    def __init__(self, paper_id: int, family: str, gsm: int, w: float, h: float, display_name: str):
        self.paper_master_id = paper_id
        self.family = family
        self.gsm = gsm
        self.sheet_w_cm = w
        self.sheet_h_cm = h
        self.display_name = display_name

def get_paper_master(paper_master_id: int, db: Session) -> PaperMasterRef:
    material = db.execute(
        select(Material)
        .where(Material.id == paper_master_id)
        .where(Material.material_type == "paper")
    ).scalars().first()
    if not material:
        raise ValueError(f"Không tìm thấy giấy với ID {paper_master_id}")
    return PaperMasterRef(
        paper_id=material.id,
        family=material.paper_family or "",
        gsm=material.gsm or 0,
        w=float(material.width_cm or 0),
        h=float(material.height_cm or 0),
        display_name=material.name,
    )

def list_paper_masters(db: Session, q: str | None = None) -> list[PaperMasterRef]:
    stmt = select(Material).where(Material.material_type == "paper").where(Material.is_active == True)
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(Material.name.like(like))
    rows = db.execute(stmt).scalars().all()
    return [
        PaperMasterRef(
            paper_id=m.id,
            family=m.paper_family or "",
            gsm=m.gsm or 0,
            w=float(m.width_cm or 0),
            h=float(m.height_cm or 0),
            display_name=m.name,
        )
        for m in rows
    ]
