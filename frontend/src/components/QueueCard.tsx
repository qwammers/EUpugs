import type { QueueBucket } from "../api/types";

interface QueueCardProps {
  bucket: QueueBucket;
}

export function QueueCard({ bucket }: QueueCardProps) {
  return (
    <section className="panel">
      <div className="panel-header">
        <h2>{bucket.queue_bucket === "active" ? "Active Queue" : "Next Match Queue"}</h2>
        <span>{bucket.count} players</span>
      </div>
      <div className="queue-list">
        {bucket.players.length === 0 ? (
          <p className="muted">Nobody is queued yet.</p>
        ) : (
          bucket.players.map((player) => (
            <article className="queue-row" key={`${bucket.queue_bucket}-${player.player_id}`}>
              <div>
                <strong>{player.display_name ?? player.discord_username}</strong>
                <p>{player.steam_name ?? "No Steam name"}</p>
              </div>
              <div>
                <span className={`pill ${player.ready ? "pill-good" : "pill-warn"}`}>
                  {player.ready ? "Ready" : "Not ready"}
                </span>
                <p>{player.classes.join(", ")}</p>
              </div>
            </article>
          ))
        )}
      </div>
    </section>
  );
}

