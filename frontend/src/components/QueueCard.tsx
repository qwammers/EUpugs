import type { QueueBucket } from "../api/types";

interface QueueCardProps {
  bucket: QueueBucket;
  isAdmin?: boolean;
  onRemove?: (playerId: number) => void;
}

export function QueueCard({ bucket, isAdmin = false, onRemove }: QueueCardProps) {
  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Current Match Queue</h2>
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
                <p>{player.steam_name ?? "No Steam name"} · {player.pug_rating ?? "Unseeded"} PUG Rating</p>
              </div>
              <div>
                <span className={`pill ${player.ready ? "pill-good" : "pill-warn"}`}>
                  {player.ready ? "Ready" : "Not ready"}
                </span>
                <p>{player.classes.join(", ")}</p>
                {isAdmin && <button className="danger-button" onClick={() => onRemove?.(player.player_id)}>
                  Remove
                </button>}
              </div>
            </article>
          ))
        )}
      </div>
    </section>
  );
}
