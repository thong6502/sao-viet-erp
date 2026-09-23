import { useEffect, useRef, useState } from "react";
import type { Feature, Polygon } from "geojson";
import {
  Map,
  Marker,
  NavigationControl,
  type GeoJSONSource,
  type MapMouseEvent,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

const EARTH_RADIUS_M = 6_371_008.8;

export function radiusCircleFeature(
  latitude: number,
  longitude: number,
  radiusM: number,
): Feature<Polygon> {
  const lat1 = latitude * Math.PI / 180;
  const lon1 = longitude * Math.PI / 180;
  const angularDistance = Math.max(0, radiusM) / EARTH_RADIUS_M;
  const ring: number[][] = [];

  for (let step = 0; step <= 64; step += 1) {
    const bearing = step / 64 * Math.PI * 2;
    const lat2 = Math.asin(
      Math.sin(lat1) * Math.cos(angularDistance)
      + Math.cos(lat1) * Math.sin(angularDistance) * Math.cos(bearing),
    );
    const lon2 = lon1 + Math.atan2(
      Math.sin(bearing) * Math.sin(angularDistance) * Math.cos(lat1),
      Math.cos(angularDistance) - Math.sin(lat1) * Math.sin(lat2),
    );
    ring.push([lon2 * 180 / Math.PI, lat2 * 180 / Math.PI]);
  }

  return {
    type: "Feature",
    properties: {},
    geometry: { type: "Polygon", coordinates: [ring] },
  };
}

export function LocationMapPicker({
  latitude,
  longitude,
  radiusM,
  onChange,
}: {
  latitude: number;
  longitude: number;
  radiusM: number;
  onChange: (latitude: number, longitude: number) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Map | null>(null);
  const markerRef = useRef<Marker | null>(null);
  const onChangeRef = useRef(onChange);
  const radiusRef = useRef(radiusM);
  const [ready, setReady] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
  const hasCoordinates = Number.isFinite(latitude)
    && Number.isFinite(longitude)
    && (latitude !== 0 || longitude !== 0);
  const didAutoFocusRef = useRef(hasCoordinates);

  useEffect(() => { onChangeRef.current = onChange; }, [onChange]);
  useEffect(() => { radiusRef.current = radiusM; }, [radiusM]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const initialCenter: [number, number] = hasCoordinates
      ? [longitude, latitude]
      : [106.7009, 10.7769];

    try {
      const map = new Map({
        container,
        style: "https://tiles.openfreemap.org/styles/liberty",
        center: initialCenter,
        zoom: hasCoordinates ? 17 : 12,
      });
      mapRef.current = map;
      map.addControl(new NavigationControl({ showCompass: false }), "top-right");

      const placeMarker = (lat: number, lng: number, notify: boolean) => {
        if (!markerRef.current) {
          const marker = new Marker({ draggable: true, color: "#c5400a" })
            .setLngLat([lng, lat])
            .addTo(map);
          marker.on("dragend", () => {
            const point = marker.getLngLat();
            onChangeRef.current(point.lat, point.lng);
          });
          markerRef.current = marker;
        } else {
          markerRef.current.setLngLat([lng, lat]);
        }
        const source = map.getSource("work-location-radius") as GeoJSONSource | undefined;
        source?.setData(radiusCircleFeature(lat, lng, radiusRef.current));
        if (notify) onChangeRef.current(lat, lng);
      };

      map.on("load", () => {
        map.addSource("work-location-radius", {
          type: "geojson",
          data: hasCoordinates
            ? radiusCircleFeature(latitude, longitude, radiusRef.current)
            : { type: "FeatureCollection", features: [] },
        });
        map.addLayer({
          id: "work-location-radius-fill",
          type: "fill",
          source: "work-location-radius",
          paint: {
            "fill-color": "#c5400a",
            "fill-opacity": 0.14,
          },
        });
        map.addLayer({
          id: "work-location-radius-outline",
          type: "line",
          source: "work-location-radius",
          paint: {
            "line-color": "#c5400a",
            "line-width": 2,
            "line-opacity": 0.8,
          },
        });
        if (hasCoordinates) placeMarker(latitude, longitude, false);
        setReady(true);
      });
      map.on("click", (event: MapMouseEvent) => {
        placeMarker(event.lngLat.lat, event.lngLat.lng, true);
      });
    } catch {
      setMapError("Không thể mở bản đồ trên thiết bị này. Bạn vẫn có thể nhập tọa độ hoặc dùng GPS.");
    }

    return () => {
      markerRef.current?.remove();
      markerRef.current = null;
      mapRef.current?.remove();
      mapRef.current = null;
    };
    // Bản đồ chỉ được khởi tạo một lần; các giá trị form được đồng bộ ở effect phía dưới.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!hasCoordinates || !mapRef.current) return;
    const map = mapRef.current;
    if (!markerRef.current) {
      const marker = new Marker({ draggable: true, color: "#c5400a" })
        .setLngLat([longitude, latitude])
        .addTo(map);
      marker.on("dragend", () => {
        const point = marker.getLngLat();
        onChangeRef.current(point.lat, point.lng);
      });
      markerRef.current = marker;
    } else {
      markerRef.current.setLngLat([longitude, latitude]);
    }
    if (didAutoFocusRef.current) {
      map.jumpTo({ center: [longitude, latitude] });
    } else {
      map.jumpTo({ center: [longitude, latitude], zoom: 16 });
      didAutoFocusRef.current = true;
    }
    const source = map.getSource("work-location-radius") as GeoJSONSource | undefined;
    source?.setData(radiusCircleFeature(latitude, longitude, radiusM));
  }, [hasCoordinates, latitude, longitude, radiusM, ready]);

  return (
    <section className="cc-location-map-picker" aria-labelledby="cc-location-map-title">
      <div className="cc-location-map-picker__head">
        <div>
          <h3 id="cc-location-map-title">Chọn vị trí trên bản đồ</h3>
          <p>Kéo ghim hoặc bấm trực tiếp lên bản đồ để đặt tâm chấm công.</p>
        </div>
        <span className={`cc-location-map-picker__status${ready ? " is-ready" : ""}`}>
          {ready ? `${radiusM} m` : "Đang tải bản đồ…"}
        </span>
      </div>
      <div className="cc-location-map-picker__viewport-wrap">
        <div
          ref={containerRef}
          className="cc-location-map-picker__viewport"
          aria-label="Bản đồ chọn tâm điểm chấm công"
        />
        {!hasCoordinates && !mapError && (
          <div className="cc-location-map-picker__hint">
            Bấm lên bản đồ để đặt tâm chấm công
          </div>
        )}
        {mapError && <div className="cc-location-map-picker__error">{mapError}</div>}
      </div>
    </section>
  );
}
