import { MapContainer, TileLayer, CircleMarker, Popup, Tooltip } from "react-leaflet";
import type { ZoneImpact } from "../../api/types";
import "leaflet/dist/leaflet.css";

const TERRITORY_CENTERS: Record<string, [number, number]> = {
  CONED: [40.78, -73.95],
  OR: [41.25, -74.3],
};

const TERRITORY_ZOOM: Record<string, number> = {
  CONED: 10,
  OR: 9,
};

// Zone approximate coordinates for markers
const ZONE_COORDS: Record<string, [number, number]> = {
  "CONED-MAN": [40.783, -73.971],
  "CONED-BRX": [40.845, -73.865],
  "CONED-BKN": [40.678, -73.944],
  "CONED-QNS": [40.728, -73.795],
  "CONED-SI": [40.58, -74.15],
  "CONED-WST": [41.122, -73.795],
  "OR-ORA": [41.402, -74.312],
  "OR-ROC": [41.149, -73.983],
  "OR-SUL": [41.717, -74.771],
  "OR-BER": [41.053, -74.131],
  "OR-SSX": [41.139, -74.69],
};

function riskColor(level: string): string {
  switch (level) {
    case "Low":
      return "#22c55e";
    case "Moderate":
      return "#eab308";
    case "High":
      return "#f97316";
    case "Extreme":
      return "#ef4444";
    default:
      return "#9ca3af";
  }
}

interface Props {
  zones: ZoneImpact[];
  territory: string;
}

export default function TerritoryMap({ zones, territory }: Props) {
  const center = TERRITORY_CENTERS[territory] || TERRITORY_CENTERS.CONED;
  const zoom = TERRITORY_ZOOM[territory] || 10;

  return (
    <div className="bg-white rounded-lg shadow overflow-hidden" style={{ height: 420 }}>
      <MapContainer
        center={center}
        zoom={zoom}
        style={{ height: "100%", width: "100%" }}
        key={territory}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {zones.map((zone) => {
          const coords = ZONE_COORDS[zone.zone_id];
          if (!coords) return null;
          return (
            <CircleMarker
              key={zone.zone_id}
              center={coords}
              radius={18}
              pathOptions={{
                fillColor: riskColor(zone.overall_risk_level),
                fillOpacity: 0.7,
                color: riskColor(zone.overall_risk_level),
                weight: 2,
              }}
            >
              <Tooltip direction="top" permanent>
                <span className="font-medium text-xs">{zone.zone_name}</span>
              </Tooltip>
              <Popup>
                <div className="text-sm">
                  <div className="font-bold">{zone.zone_name}</div>
                  <div>Risk: {zone.overall_risk_level} ({zone.overall_risk_score})</div>
                  {zone.outage_risk && (
                    <div>Est. Outages: {zone.outage_risk.estimated_outages}</div>
                  )}
                  {zone.load_forecast && (
                    <div>Load: {zone.load_forecast.pct_capacity}%</div>
                  )}
                </div>
              </Popup>
            </CircleMarker>
          );
        })}
      </MapContainer>
    </div>
  );
}
