import axios from "axios";
import type { DashboardResponse, ZoneInfo } from "./types";

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

export default api;
