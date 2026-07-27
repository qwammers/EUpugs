import type { MatchRead, QueueState } from "../api/types";
import { MatchCard } from "../components/MatchCard";
import { QueueCard } from "../components/QueueCard";

interface HomePageProps {
  queue: QueueState | null;
  currentMatch: MatchRead | null;
}

export function HomePage({ queue, currentMatch }: HomePageProps) {
  return (
    <div className="page-grid">
      <section className="panel spotlight">
        <p className="eyebrow">Single-guild TF2 6s</p>
        <h1>Queue for the next match in one click.</h1>
        <p>
          HostedPugs keeps Discord-authenticated players, class preferences, ready checks, match state,
          and logs.tf stats in one place.
        </p>
        {queue && (
          <div className="stat-grid">
            <div>
              <strong>{queue.active.count}</strong>
              <span>Active queue</span>
            </div>
            <div>
              <strong>#{queue.match_id}</strong>
              <span>Forming match</span>
            </div>
            <div>
              <strong>{queue.matchable ? "Ready" : "Waiting"}</strong>
              <span>Match status</span>
            </div>
          </div>
        )}
      </section>
      <MatchCard match={currentMatch} />
      {queue && <QueueCard bucket={queue.active} />}
    </div>
  );
}
