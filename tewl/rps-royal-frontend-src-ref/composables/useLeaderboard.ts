import { computed, type Ref } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { fetchLeaderboard, fetchEnergyHolders } from "./useRpsApi";
import type { PlayerStats } from "@/types/game";

export type LeaderboardCategory =
  | "energy"
  | "ratio"
  | "survivor"
  | "spawns"
  | "roi"
  | "lifespan"
  | "domination";

export interface LeaderboardEntry {
  rank: number;
  address: string;
  value: number;
  label: string;
}

function formatAddress(addr: string): string {
  if (addr.length <= 12) return addr;
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`;
}

function sortByMetric(
  players: PlayerStats[],
  category: LeaderboardCategory
): LeaderboardEntry[] {
  const sorted = [...players].sort((a, b) => {
    switch (category) {
      case "ratio":
        return (
          b.total_kills / Math.max(1, b.total_deaths) -
          a.total_kills / Math.max(1, a.total_deaths)
        );
      case "survivor":
        return (
          b.total_blocks_alive / Math.max(1, b.total_deaths) -
          a.total_blocks_alive / Math.max(1, a.total_deaths)
        );
      case "spawns":
        return b.total_spawns - a.total_spawns;
      case "roi":
        return (
          b.energy_earned / Math.max(1, b.energy_spent) -
          a.energy_earned / Math.max(1, a.energy_spent)
        );
      case "lifespan":
        return b.max_piece_lifespan - a.max_piece_lifespan;
      case "domination":
        return b.peak_pieces - a.peak_pieces;
      default:
        return 0;
    }
  });

  return sorted.slice(0, 10).map((p, i) => {
    let value: number;
    let label: string;
    switch (category) {
      case "ratio":
        value = p.total_kills / Math.max(1, p.total_deaths);
        label = `${value.toFixed(2)} K/D`;
        break;
      case "survivor":
        value = p.total_blocks_alive / Math.max(1, p.total_deaths);
        label = `${Math.round(value)} blocks`;
        break;
      case "spawns":
        value = p.total_spawns;
        label = `${value} spawns`;
        break;
      case "roi":
        value = p.energy_earned / Math.max(1, p.energy_spent);
        label = `${value.toFixed(2)}x`;
        break;
      case "lifespan":
        value = p.max_piece_lifespan;
        label = `${value} blocks`;
        break;
      case "domination":
        value = p.peak_pieces;
        label = `${value} peak`;
        break;
      default:
        value = 0;
        label = "";
    }
    return {
      rank: i + 1,
      address: formatAddress(p.address),
      value,
      label,
    };
  });
}

export interface CategorySection {
  id: LeaderboardCategory;
  icon: string;
  name: string;
  desc: string;
  entries: LeaderboardEntry[];
}

const STAT_CATEGORIES: {
  id: LeaderboardCategory;
  icon: string;
  name: string;
  desc: string;
}[] = [
  { id: "ratio", icon: "🎯", name: "K/D Ratio", desc: "Kills per death" },
  { id: "survivor", icon: "⏱️", name: "Survivors", desc: "Avg lifespan per piece" },
  { id: "spawns", icon: "🚀", name: "Most Active", desc: "Total pieces spawned" },
  { id: "roi", icon: "💰", name: "Best ROI", desc: "Energy earned / spent" },
  { id: "lifespan", icon: "🐢", name: "Oldest Piece", desc: "Max blocks a piece survived" },
  { id: "domination", icon: "👑", name: "Peak Domination", desc: "Most pieces at once" },
];

const ENERGY_CATEGORY = {
  id: "energy" as LeaderboardCategory,
  icon: "⚡",
  name: "Energy Lords",
  desc: "% of total energy supply",
};

export function useLeaderboard(category: Ref<LeaderboardCategory>) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["leaderboard"],
    queryFn: fetchLeaderboard,
    refetchInterval: 10000,
    staleTime: 5000,
  });

  const entries = computed(() => {
    if (!data.value) return [];
    return sortByMetric(data.value, category.value);
  });

  const playerCount = computed(() => data.value?.length || 0);

  return {
    entries,
    playerCount,
    isLoading,
    error,
    refetch,
  };
}

export function useLeaderboardSections(topN = 3) {
  const { data: statsData, isLoading: statsLoading } = useQuery({
    queryKey: ["leaderboard"],
    queryFn: fetchLeaderboard,
    refetchInterval: 10000,
    staleTime: 5000,
  });

  const { data: energyData, isLoading: energyLoading } = useQuery({
    queryKey: ["energyHolders"],
    queryFn: fetchEnergyHolders,
    refetchInterval: 10000,
    staleTime: 5000,
  });

  const isLoading = computed(() => statsLoading.value || energyLoading.value);

  const sections = computed<CategorySection[]>(() => {
    const result: CategorySection[] = [];

    // Energy Lords section (from bank module)
    if (energyData.value) {
      result.push({
        ...ENERGY_CATEGORY,
        entries: energyData.value.slice(0, topN).map((h, i) => ({
          rank: i + 1,
          address: formatAddress(h.address),
          value: h.percent,
          label: `${h.percent.toFixed(1)}%`,
        })),
      });
    }

    // Stat-based categories (from game storage)
    if (statsData.value) {
      for (const cat of STAT_CATEGORIES) {
        result.push({
          ...cat,
          entries: sortByMetric(statsData.value, cat.id).slice(0, topN),
        });
      }
    }

    return result;
  });

  const playerCount = computed(() => statsData.value?.length || 0);

  return {
    sections,
    playerCount,
    isLoading,
  };
}

