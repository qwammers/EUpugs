export type QueueBucketName = "active" | "next";

export interface QueuePlayer {
  player_id: number;
  discord_username: string;
  display_name: string | null;
  steam_name: string | null;
  ready: boolean;
  joined_at: string;
  classes: string[];
}

export interface QueueBucket {
  queue_bucket: QueueBucketName;
  players: QueuePlayer[];
  count: number;
}

export interface QueueState {
  active: QueueBucket;
  next: QueueBucket;
  matchable: boolean;
  needed_by_class: Record<string, number>;
}

export interface MatchSlot {
  player_id: number;
  display_name: string | null;
  discord_username: string;
  assigned_class: string;
  team: string;
  slot_order: number;
}

export interface MatchRead {
  id: number;
  status: string;
  map_name: string | null;
  winner: string | null;
  score_red: number | null;
  score_blu: number | null;
  ready_check_expires_at: string | null;
  created_at: string;
  completed_at: string | null;
  log_ids: number[];
  slots: MatchSlot[];
}

export interface Aggregate {
  matches_played: number;
  wins: number;
  kills: number;
  deaths: number;
  assists: number;
  damage: number;
  healing: number;
  last_log_id: number | null;
}

export interface PlayerRead {
  id: number;
  discord_user_id: string;
  discord_username: string;
  display_name: string | null;
  avatar_url: string | null;
  steam_id: string | null;
  steam_name: string | null;
  steam_connected: boolean;
  guild_role_ids: string[];
  last_synced_at: string | null;
  aggregate: Aggregate | null;
}

export interface MeResponse {
  player: PlayerRead;
  is_admin: boolean;
}

export interface LeaderboardEntry {
  player_id: number;
  display_name: string | null;
  discord_username: string;
  steam_name: string | null;
  matches_played: number;
  wins: number;
  kills: number;
  deaths: number;
  assists: number;
  damage: number;
  healing: number;
}

export interface RecentMatchListResponse {
  matches: MatchRead[];
}

