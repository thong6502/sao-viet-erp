import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LocationForm } from "./LocationForm";

const gpsFakes = vi.hoisted(() => ({
  getPosition: vi.fn(),
}));

vi.mock("../../../../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../../../../api/client")>();
  return {
    ...original,
    api: {
      ...original.api,
      attendance: {
        ...original.api.attendance,
        createLocation: vi.fn(),
        updateLocation: vi.fn(),
      },
    },
  };
});

vi.mock("../components/LocationMapPicker", () => ({
  LocationMapPicker: ({
    onChange,
  }: {
    onChange?: (latitude: number, longitude: number) => void;
  }) => (
    <section>
      <h3>Chọn vị trí trên bản đồ</h3>
      <p>Kéo ghim hoặc bấm trực tiếp lên bản đồ để đặt tâm chấm công.</p>
      <button type="button" onClick={() => onChange?.(10.7769123, 106.7009456)}>
        Giả lập chọn điểm
      </button>
    </section>
  ),
}));

vi.mock("../shared/helpers", async (importOriginal) => {
  const original = await importOriginal<typeof import("../shared/helpers")>();
  return { ...original, getPosition: gpsFakes.getPosition };
});

describe("LocationForm", () => {
  it("gộp bộ chọn vị trí bản đồ vào form hiện tại", () => {
    render(
      <LocationForm
        token="token"
        location={null}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    );

    expect(screen.getByText("Chọn vị trí trên bản đồ")).toBeInTheDocument();
    expect(screen.getByText(/kéo ghim hoặc bấm trực tiếp/i)).toBeInTheDocument();
  });

  it("đồng bộ điểm chọn trên bản đồ vào hai ô tọa độ hiện có", () => {
    render(
      <LocationForm
        token="token"
        location={null}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Giả lập chọn điểm" }));

    expect(screen.getByLabelText("Vĩ độ (latitude)")).toHaveValue(10.7769123);
    expect(screen.getByLabelText("Kinh độ (longitude)")).toHaveValue(106.7009456);
  });

  it("chỉ báo đang lấy vị trí, không bắt người dùng đọc sai số", () => {
    gpsFakes.getPosition.mockImplementation(() => new Promise(() => undefined));
    render(
      <LocationForm
        token="token"
        location={null}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /lấy vị trí gps/i }));

    expect(screen.getByText("Đang lấy vị trí…")).toBeInTheDocument();
    expect(screen.queryByText(/sai số/i)).not.toBeInTheDocument();
  });

  it("nhận tọa độ dù sai số lớn, không hiện băng đỏ", async () => {
    gpsFakes.getPosition.mockResolvedValue({
      coords: { latitude: 11.0394672, longitude: 106.4310998, accuracy: 76 },
    });
    render(
      <LocationForm
        token="token"
        location={null}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /lấy vị trí gps/i }));

    expect(await screen.findByDisplayValue("11.0394672")).toBeInTheDocument();
    expect(screen.getByLabelText("Kinh độ (longitude)")).toHaveValue(106.4310998);
    expect(document.querySelector(".banner--error")).toBeNull();
  });
});
