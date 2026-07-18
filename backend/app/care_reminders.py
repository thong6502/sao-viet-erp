"""Ticker in-process nhắc lịch hẹn chăm sóc real-time (Pha B — redesign-lich-hen-cham-soc).

Mỗi `interval` giây quét các hẹn ĐANG MỞ có giờ hẹn vừa rơi vào cửa sổ (lần quét trước, bây giờ]
rồi đẩy sự kiện `care_due` (SSE) tới người phụ trách — badge "Khách hàng" tự nhảy + toast tức thì,
KHÔNG bắt refresh (CLAUDE.md: thông báo nội bộ = real-time).

Cửa sổ hở-trái/đóng-phải → mỗi hẹn chỉ "ting" ĐÚNG 1 LẦN khi giờ hẹn đi qua; hẹn quá hạn cũ (trước
lúc khởi động) KHÔNG bị nhắc lại, và restart cũng không spam. Chỉ đúng khi 1 uvicorn worker — giống
ràng buộc của hub (app/realtime.py); scale >1 worker thì chuyển sang Postgres LISTEN/NOTIFY.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from .db import SessionLocal
from .realtime import hub
from .repositories.customer_repo import CustomerRepository

log = logging.getLogger(__name__)


def _scan_once(after: datetime, until: datetime) -> int:
    """Quét (after, until] và đẩy `care_due` cho từng hẹn tới giờ. Trả số hẹn đã ting.

    Chạy trong thread riêng (to_thread) nên mở SessionLocal cục bộ; hub.publish an toàn luồng
    (tự schedule lên event loop)."""
    db = SessionLocal()
    try:
        rows = CustomerRepository(db).list_due_in_window(after=after, until=until)
        for task, customer in rows:
            hub.publish(task.assignee_user_id, {
                "type": "care_due",
                "customer": customer.name,
                "customer_id": customer.id,
                "note": task.note,
            })
        return len(rows)
    finally:
        db.close()


async def run_care_reminder_loop(interval: int) -> None:
    """Vòng lặp nền: ngủ `interval` giây rồi quét cửa sổ vừa trôi qua. Nuốt mọi lỗi để 1 lần
    fail (vd DB chớp) không giết vòng lặp."""
    after = datetime.now(timezone.utc)
    while True:
        await asyncio.sleep(interval)
        now = datetime.now(timezone.utc)
        try:
            n = await asyncio.to_thread(_scan_once, after, now)
            if n:
                log.info("care reminder: ting %d hẹn tới giờ", n)
        except Exception:  # noqa: BLE001 — vòng lặp nền phải sống sót mọi lỗi
            log.exception("care reminder loop scan failed")
        after = now
