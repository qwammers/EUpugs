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
import { MatchesPage } from "./pages/MatchesPage";
import { PlayerPage } from "./pages/PlayerPage";
import { QueuePage } from "./pages/QueuePage";

function RoutedApp() {
  const meState = useAsyncData<MeResponse | null>(() => api.getMe().catch(() => null), []);
  const queueState = useAsyncData<QueueState>(() => api.getQueue(), []);
  const currentMatchState = useAsyncData<MatchRead | null>(() => api.getCurrentMatch(), []);
  const activeMatchesState = useAsyncData(() => api.getActiveMatches(), []);
  const leaderboardState = useAsyncData(() => api.getLeaderboard(), []);
  const recentMatchesState = useAsyncData(() => api.getRecentMatches(), []);

  const refreshQueue = async () => {
    const queue = await api.getQueue();
    queueState.setData(queue);
  };

  const refreshAll = async () => {
    const [queue, match, activeMatches, leaderboard, recent] = await Promise.all([
      api.getQueue(),
      api.getCurrentMatch(),
      api.getActiveMatches(),
      api.getLeaderboard(),
      api.getRecentMatches(),
    ]);
    queueState.setData(queue);
    currentMatchState.setData(match);
    activeMatchesState.setData(activeMatches);
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
              activeMatches={activeMatchesState.data?.matches ?? []}
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
          element={<MatchRoute />}
        />
        <Route path="/matches" element={<MatchesPage matches={recentMatchesState.data?.matches ?? []} />} />
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

function MatchRoute() {
  const { id } = useParams();
  const matchState = useAsyncData<MatchRead | null>(
    () => id ? api.getMatch(id).catch(() => null) : Promise.resolve(null),
    [id],
  );
  return <MatchPage match={matchState.data} />;
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
