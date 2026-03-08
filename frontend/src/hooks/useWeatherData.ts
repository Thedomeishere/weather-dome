import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchDashboard, fetchZones, fetchOutageOverrides, setOutageOverride, clearOutageOverride } from "../api/client";
import type { OutageOverrideRequest } from "../api/types";

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

export function useOutageOverrides() {
  return useQuery({
    queryKey: ["outageOverrides"],
    queryFn: fetchOutageOverrides,
    refetchInterval: 30_000,
  });
}

export function useSetOverride() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: OutageOverrideRequest) => setOutageOverride(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["outageOverrides"] });
    },
  });
}

export function useClearOverride() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (zoneId: string) => clearOutageOverride(zoneId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["outageOverrides"] });
    },
  });
}
