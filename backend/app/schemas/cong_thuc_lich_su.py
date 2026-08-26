"""Schema Out cho `GET /{item_id}/lich-su-cong-thuc` — xem models/cong_thuc_lich_su.py."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CongThucLichSuOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    gia_tri_cu: str | None = None
    gia_tri_moi: str | None = None
    sua_boi: int | None = None
    sua_luc: datetime
