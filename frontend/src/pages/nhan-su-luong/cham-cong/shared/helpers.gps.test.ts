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

function stubGeolocation(getCurrentPosition: Geolocation["getCurrentPosition"]): void {
  vi.stubGlobal("navigator", {
    ...navigator,
    geolocation: {
      getCurrentPosition,
      watchPosition: vi.fn(),
      clearWatch: vi.fn(),
    },
  });
}

describe("lấy vị trí chấm công", () => {
  it("yêu cầu tọa độ mới với độ chính xác cao nhất", async () => {
    const getCurrentPosition = vi.fn((ok: PositionCallback) => ok(position(12)));
    stubGeolocation(getCurrentPosition);

    await expect(getPosition()).resolves.toMatchObject({ coords: { accuracy: 12 } });
    expect(getCurrentPosition).toHaveBeenCalledWith(
      expect.any(Function),
      expect.any(Function),
      expect.objectContaining({
        enableHighAccuracy: true,
        maximumAge: 0,
      }),
    );
  });

  it("không dùng tọa độ có sai số lớn hơn 50 m để quyết định geofence", async () => {
    const getCurrentPosition = vi.fn((ok: PositionCallback) => ok(position(120)));
    stubGeolocation(getCurrentPosition);

    await expect(getPosition()).rejects.toThrow(
      "Độ chính xác GPS hiện chỉ khoảng 120 m",
    );
  });
});
