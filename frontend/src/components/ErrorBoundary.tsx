import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** Thay cho khối con khi nó ném lỗi lúc vẽ. `thuLai` xoá lỗi và vẽ lại khối con từ đầu. */
  fallback: (thuLai: () => void) => ReactNode;
}

interface State {
  loi: boolean;
}

/** Khoanh lỗi VẼ giao diện vào đúng khối bị hỏng.
 *
 *  React không bắt được lỗi ném ra lúc render thì gỡ CẢ cây — người dùng thấy trang trắng, tải lại
 *  thì ứng dụng khởi động lại từ đầu (access token chỉ nằm trong bộ nhớ) và phiên tự chuyển sang tài
 *  khoản đăng nhập gần nhất trên máy. Sự cố 17/09/2026: ngăn chi tiết Bàn tổ ném lỗi giữa lúc
 *  nạp nóng mã, cả tab đổi sang Admin.
 *
 *  Chỉ bắt lỗi lúc vẽ + vòng đời component; lỗi trong hàm bấm nút hay lời gọi máy chủ vẫn đi
 *  đường xử lý riêng của màn đó. Đổi `key` của ranh giới (vd chọn việc khác) là tự xoá lỗi. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { loi: false };

  static getDerivedStateFromError(): State {
    return { loi: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Giữ nguyên văn lỗi ở console cho người sửa — giao diện chỉ nói bằng lời nghiệp vụ.
    console.error("Khối giao diện gặp lỗi khi vẽ:", error, info.componentStack);
  }

  thuLai = () => this.setState({ loi: false });

  render() {
    return this.state.loi ? this.props.fallback(this.thuLai) : this.props.children;
  }
}
