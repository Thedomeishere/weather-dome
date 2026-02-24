import { useQuery } from "@tanstack/react-query";
import { fetchDashboard, fetchZones } from "../api/client";

export function useDashboard(territory: string) {
  return useQuery({
    queryKey: ["dashboard", territory],
    queryFn: () => fetchDashboard(territory),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
}

export function useZones(territory?: string) {
  return useQuery({
    queryKey: ["zones", territory],
    queryFn: () => fetchZones(territory),
    staleTime: 300_000,
  });
}
