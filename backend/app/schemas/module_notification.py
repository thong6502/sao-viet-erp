from pydantic import BaseModel


class ModuleNotificationSummaryOut(BaseModel):
    thu_mua: int = 0
    ke_toan: int = 0
