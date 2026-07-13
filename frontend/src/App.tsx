import { useMemo } from "react";
import { HashRouter, Link, Route, Routes, useLocation, useParams } from "react-router-dom";
import { api } from "./api/client";
import type { MatchRead, MeResponse, PlayerRead, QueueState } from "./api/types";
import { MatchCard } from "./components/MatchCard";
import { Shell } from "./components/Shell";
import { useAsyncData } from "./hooks/useAsyncData";
import { AdminPage } from "./pages/AdminPage";
import { HomePage } from "./pages/HomePage";
import { LeaderboardPage } from "./pages/LeaderboardPage";
import { MatchPage } from "./pages/MatchPage";
import { PlayerPage } from "./pages/PlayerPage";
import { QueuePage } from "./pages/QueuePage";

function RoutedApp() {
  const meState = useAsyncData<MeResponse | null>(() => api.getMe().catch(() => null), []);
  const queueState = useAsyncData<QueueState>(() => api.getQueue(), []);
  const currentMatchState = useAsyncData<MatchRead | null>(() => api.getCurrentMatch(), []);
  const leaderboardState = useAsyncData(() => api.getLeaderboard(), []);
  const recentMatchesState = useAsyncData(() => api.getRecentMatches(), []);

  const refreshQueue = async () => {
    const queue = await api.getQueue();
    queueState.setData(queue);
  };

  const refreshAll = async () => {
    const [queue, match, leaderboard, recent] = await Promise.all([
      api.getQueue(),
      api.getCurrentMatch(),
      api.getLeaderboard(),
      api.getRecentMatches(),
    ]);
    queueState.setData(queue);
    currentMatchState.setData(match);
    leaderboardState.setData(leaderboard);
    recentMatchesState.setData(recent);
  };

  const onLogout = async () => {
    await api.logout();
    meState.setData(null);
  };

  const loginHref = useMemo(() => api.loginUrl, []);

  return (
    <Shell me={meState.data} loginHref={loginHref} onLogout={onLogout}>
      {!meState.data && (
        <section className="panel login-banner">
          <div>
            <strong>Discord authentication</strong>
            <p>Use Discord OAuth to link your Steam connection and join the queue.</p>
          </div>
          <a className="button-link" href={loginHref}>
            Log in with Discord
          </a>
        </section>
      )}
      <Routes>
        <Route path="/" element={<HomePage queue={queueState.data} currentMatch={currentMatchState.data} />} />
        <Route
          path="/queue"
          element={<QueuePage me={meState.data} queue={queueState.data} refreshQueue={refreshQueue} />}
        />
        <Route
          path="/leaderboard"
          element={<LeaderboardPage entries={leaderboardState.data ?? []} />}
        />
        <Route
          path="/admin"
          element={
            <AdminPage
              me={meState.data}
              queue={queueState.data}
              currentMatch={currentMatchState.data}
              refreshAll={refreshAll}
            />
          }
        />
        <Route
          path="/players/:id"
          element={<PlayerRoute />}
        />
        <Route
          path="/matches/:id"
          element={<MatchRoute fallback={currentMatchState.data} recent={recentMatchesState.data?.matches ?? []} />}
        />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Shell>
  );
}

function PlayerRoute() {
  const { id } = useParams();
  const playerState = useAsyncData<PlayerRead | null>(
    () => (id ? api.getPlayer(id).catch(() => null) : Promise.resolve(null)),
    [id],
  );
  return <PlayerPage player={playerState.data} />;
}

function MatchRoute({ fallback, recent }: { fallback: MatchRead | null; recent: MatchRead[] }) {
  const { id } = useParams();
  const match = useMemo(() => {
    const numericId = Number(id);
    if (!Number.isFinite(numericId)) return null;
    if (fallback?.id === numericId) return fallback;
    return recent.find((entry) => entry.id === numericId) ?? null;
  }, [fallback, id, recent]);
  return <MatchPage match={match} />;
}

function NotFound() {
  const location = useLocation();
  return (
    <section className="panel">
      <h1>Page not found</h1>
      <p className="muted">
        No route exists for <code>{location.pathname}</code>.
      </p>
      <Link className="button-link" to="/">
        Return home
      </Link>
    </section>
  );
}

export default function App() {
  return (
    <HashRouter>
      <RoutedApp />
    </HashRouter>
  );
}
