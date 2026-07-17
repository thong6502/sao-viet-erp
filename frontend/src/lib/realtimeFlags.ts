// Cờ dùng chung để KHÔNG hiện toast "có YCMH mới" cho chính người vừa tạo (họ đã thấy toast
// "đã gửi yêu cầu" tại chỗ). Người tạo set cờ; AppShell tiêu thụ đúng 1 lần ở sự kiện SSE kế tiếp.
let skipPurchaseToast = false;

export function markOwnPurchaseRequest(): void {
  skipPurchaseToast = true;
}

export function consumePurchaseToastSkip(): boolean {
  const v = skipPurchaseToast;
  skipPurchaseToast = false;
  return v;
}
