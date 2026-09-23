import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as mapPicker from "./LocationMapPicker";

const mapFakes = vi.hoisted(() => ({
  mapHandlers: {} as Record<string, (event?: unknown) => void>,
  markerHandlers: {} as Record<string, () => void>,
  markerLngLat: { lng: 106.7009, lat: 10.7769 },
  setData: vi.fn(),
  jumpTo: vi.fn(),
  sourceReady: false,
}));

vi.mock("maplibre-gl", () => ({
  Map: class {
    on(event: string, handler: (value?: unknown) => void) {
      mapFakes.mapHandlers[event] = handler;
      return this;
    }
    addControl() { return this; }
    addSource() {
      mapFakes.sourceReady = true;
      return this;
    }
    addLayer() { return this; }
    getSource() {
      return mapFakes.sourceReady ? { setData: mapFakes.setData } : undefined;
    }
    jumpTo(value: unknown) {
      mapFakes.jumpTo(value);
      return this;
    }
    remove() { return undefined; }
  },
  Marker: class {
    setLngLat(value: [number, number]) {
      mapFakes.markerLngLat = { lng: value[0], lat: value[1] };
      return this;
    }
    addTo() { return this; }
    on(event: string, handler: () => void) {
      mapFakes.markerHandlers[event] = handler;
      return this;
    }
    getLngLat() { return mapFakes.markerLngLat; }
    remove() { return undefined; }
  },
  NavigationControl: class {},
}));

describe("LocationMapPicker", () => {
  beforeEach(() => {
    mapFakes.mapHandlers = {};
    mapFakes.markerHandlers = {};
    mapFakes.sourceReady = false;
    mapFakes.setData.mockClear();
    mapFakes.jumpTo.mockClear();
  });

  it("tạo vòng geofence khép kín theo bán kính cấu hình", () => {
    const radiusCircleFeature = (
      mapPicker as unknown as {
        radiusCircleFeature?: (lat: number, lng: number, radiusM: number) => {
          geometry: { type: string; coordinates: number[][][] };
        };
      }
    ).radiusCircleFeature;

    expect(radiusCircleFeature).toBeTypeOf("function");
    const feature = radiusCircleFeature!(10.7769, 106.7009, 150);
    const ring = feature.geometry.coordinates[0];

    expect(feature.geometry.type).toBe("Polygon");
    expect(ring).toHaveLength(65);
    expect(ring[0]).toEqual(ring[ring.length - 1]);
    expect(ring[0]).not.toEqual([106.7009, 10.7769]);
  });

  it("đổi tọa độ khi người dùng bấm lên bản đồ", () => {
    const onChange = vi.fn();
    render(
      <mapPicker.LocationMapPicker
        latitude={10.7769}
        longitude={106.7009}
        radiusM={150}
        onChange={onChange}
      />,
    );

    expect(screen.getByLabelText("Bản đồ chọn tâm điểm chấm công")).toBeInTheDocument();
    act(() => mapFakes.mapHandlers.load?.());
    act(() => mapFakes.mapHandlers.click?.({ lngLat: { lat: 10.78, lng: 106.71 } }));

    expect(onChange).toHaveBeenCalledWith(10.78, 106.71);
  });

  it("vẽ vòng geofence nếu tọa độ đổi trước khi bản đồ tải xong", () => {
    const { rerender } = render(
      <mapPicker.LocationMapPicker
        latitude={0}
        longitude={0}
        radiusM={150}
        onChange={vi.fn()}
      />,
    );

    rerender(
      <mapPicker.LocationMapPicker
        latitude={10.78}
        longitude={106.71}
        radiusM={150}
        onChange={vi.fn()}
      />,
    );
    act(() => mapFakes.mapHandlers.load?.());

    expect(mapFakes.setData).toHaveBeenCalledWith(
      expect.objectContaining({ geometry: expect.objectContaining({ type: "Polygon" }) }),
    );
    expect(mapFakes.jumpTo).toHaveBeenCalledWith({
      center: [106.71, 10.78],
      zoom: 16,
    });
  });
});
