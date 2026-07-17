import type {
  LeaderboardEntry,
  MatchRead,
  MeResponse,
  PlayerRead,
  QueueBucketName,
  QueueState,
  RecentMatchListResponse,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const SESSION_TOKEN_KEY = "hostedpugs_session_token";

function captureOAuthSession(): void {
  const queryIndex = window.location.hash.indexOf("?");
  if (queryIndex < 0) return;

  const route = window.location.hash.slice(0, queryIndex) || "#/";
  const params = new URLSearchParams(window.location.hash.slice(queryIndex + 1));
  const token = params.get("session_token");
  if (!token) return;

  localStorage.setItem(SESSION_TOKEN_KEY, token);
  window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${route}`);
}

captureOAuthSession();

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const sessionToken = localStorage.getItem(SESSION_TOKEN_KEY);
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {}),
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(body.detail ?? "Request failed");
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export const api = {
  apiBaseUrl: API_BASE_URL,
  loginUrl: `${API_BASE_URL}/auth/discord/start`,
  getMe: () => request<MeResponse>("/api/me"),
  logout: async () => {
    try {
      return await request<{ message: string }>("/auth/logout", { method: "POST" });
    } finally {
      localStorage.removeItem(SESSION_TOKEN_KEY);
    }
  },
  getQueue: () => request<QueueState>("/api/queue"),
  joinQueue: (classes: string[], queueBucket: QueueBucketName = "active") =>
    request<QueueState>("/api/queue/join", {
      method: "POST",
      body: JSON.stringify({ classes, queue_bucket: queueBucket }),
    }),
  leaveQueue: (queueBucket: QueueBucketName = "active") =>
    request<QueueState>("/api/queue/leave", {
      method: "POST",
      body: JSON.stringify({ queue_bucket: queueBucket }),
    }),
  setReady: (ready: boolean) => request<{ message: string }>(`/api/queue/ready?ready=${ready}`, { method: "POST" }),
  getCurrentMatch: () => request<MatchRead | null>("/api/matches/current"),
  getRecentMatches: () => request<RecentMatchListResponse>("/api/matches/recent"),
  getPlayer: (id: string) => request<PlayerRead>(`/api/players/${id}`),
  getLeaderboard: () => request<LeaderboardEntry[]>("/api/leaderboard"),
  createMatch: (mapName?: string) =>
    request<MatchRead>("/api/admin/matches/create", {
      method: "POST",
      body: JSON.stringify({ map_name: mapName ?? null }),
    }),
  updateMatchState: (id: number, status: string, winner?: string, scoreRed?: number, scoreBlu?: number) =>
    request<MatchRead>(`/api/admin/matches/${id}/state`, {
      method: "POST",
      body: JSON.stringify({
        status,
        winner: winner ?? null,
        score_red: scoreRed ?? null,
        score_blu: scoreBlu ?? null,
      }),
    }),
  attachLog: (id: number, log: string) =>
    request<MatchRead>(`/api/admin/matches/${id}/attach-log`, {
      method: "POST",
      body: JSON.stringify(log.match(/^\d+$/) ? { log_id: Number(log) } : { log_url: log }),
    }),
  updatePlayerUsername: (id: number, username: string) =>
    request<PlayerRead>(`/api/admin/players/${id}/username`, {
      method: "PATCH",
      body: JSON.stringify({ username }),
    }),
};
