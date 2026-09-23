import { afterEach, describe, expect, it, vi } from "vitest";
import { getPosition } from "./helpers";

function position(accuracy: number): GeolocationPosition {
  return {
    coords: {
      latitude: 10.7769,
      longitude: 106.7009,
      accuracy,
      altitude: null,
      altitudeAccuracy: null,
      heading: null,
      speed: null,
      toJSON: () => ({}),
    },
    timestamp: Date.now(),
    toJSON: () => ({}),
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function stubGeolocation(
  getCurrentPosition: Geolocation["getCurrentPosition"],
): { watchPosition: ReturnType<typeof vi.fn> } {
  const watchPosition = vi.fn(() => {
    throw new Error("không được dò nhiều mẫu nữa");
  });
  vi.stubGlobal("navigator", {
    ...navigator,
    geolocation: { getCurrentPosition, watchPosition, clearWatch: vi.fn() },
  });
  return { watchPosition };
}

describe("lấy vị trí chấm công", () => {
  it("dùng ngay mẫu đầu tiên, không chờ dò thêm", async () => {
    const getCurrentPosition = vi.fn((ok: PositionCallback) => ok(position(76)));
    const { watchPosition } = stubGeolocation(getCurrentPosition);

    await expect(getPosition()).resolves.toMatchObject({
      coords: { accuracy: 76 },
    });
    expect(watchPosition).not.toHaveBeenCalled();
    expect(getCurrentPosition).toHaveBeenCalledWith(
      expect.any(Function),
      expect.any(Function),
      expect.objectContaining({ enableHighAccuracy: true }),
    );
  });

  it("không từ chối tọa độ vì sai số lớn", async () => {
    stubGeolocation(vi.fn((ok: PositionCallback) => ok(position(420))));

    await expect(getPosition()).resolves.toMatchObject({
      coords: { accuracy: 420 },
    });
  });

  it("cho dùng lại fix vừa lấy nên bấm liên tiếp không phải dò lại", async () => {
    // Khai đủ BA tham số của `getCurrentPosition`: chỉ nhận `ok` thì tuple `mock.calls[0]` dài 1,
    // đọc `[2]` là lỗi biên dịch. Hai tham số sau mở đầu bằng `_` nên `noUnusedParameters` bỏ qua.
    const getCurrentPosition = vi.fn(
      (
        ok: PositionCallback,
        _fail?: PositionErrorCallback | null,
        _options?: PositionOptions,
      ) => ok(position(50)),
    );
    stubGeolocation(getCurrentPosition);

    await getPosition();

    const options = getCurrentPosition.mock.calls[0][2] as PositionOptions;
    expect(options.maximumAge).toBeGreaterThan(0);
    expect(options.timeout).toBeGreaterThan(0);
  });

  it("trả nguyên lỗi của trình duyệt để hiện đúng lý do", async () => {
    const denied = { code: 1, message: "User denied" } as GeolocationPositionError;
    stubGeolocation(
      vi.fn((_ok: PositionCallback, fail?: PositionErrorCallback | null) =>
        fail?.(denied),
      ),
    );

    await expect(getPosition()).rejects.toBe(denied);
  });

  it("báo lỗi khi trình duyệt không hỗ trợ định vị", async () => {
    vi.stubGlobal("navigator", {});

    await expect(getPosition()).rejects.toThrow("không hỗ trợ định vị");
  });
});
