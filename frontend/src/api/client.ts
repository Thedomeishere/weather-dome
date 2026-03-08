import axios from "axios";
import type { DashboardResponse, OutageOverride, OutageOverrideRequest, ZoneInfo } from "./types";

const api = axios.create({
  baseURL: "/api/v1",
  timeout: 10000,
});

export async function fetchDashboard(
  territory: string
): Promise<DashboardResponse> {
  const { data } = await api.get<DashboardResponse>("/dashboard/", {
    params: { territory },
  });
  return data;
}

export async function fetchZones(
  territory?: string
): Promise<ZoneInfo[]> {
  const { data } = await api.get<ZoneInfo[]>("/territory/zones/", {
    params: territory ? { territory } : {},
  });
  return data;
}

export async function fetchOutageOverrides(): Promise<OutageOverride[]> {
  const { data } = await api.get<OutageOverride[]>("/outages/overrides");
  return data;
}

export async function setOutageOverride(req: OutageOverrideRequest): Promise<OutageOverride> {
  const { data } = await api.post<OutageOverride>("/outages/override", req);
  return data;
}

export async function clearOutageOverride(zoneId: string): Promise<void> {
  await api.delete(`/outages/override/${zoneId}`);
}

export default api;
