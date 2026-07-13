import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import type { MeResponse } from "../api/types";

interface ShellProps {
  me: MeResponse | null;
  loginHref: string;
  onLogout: () => Promise<void>;
  children: ReactNode;
}

export function Shell({ me, loginHref, onLogout, children }: ShellProps) {
  return (
    <div className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Team Fortress 2 6v6 Pugs</p>
          <Link className="brand" to="/">
            HostedPugs
          </Link>
          <p className="subtitle">
            Queue management, Discord auth, live match state, and logs.tf-powered player stats.
          </p>
        </div>
        <div className="hero-card">
          {me ? (
            <>
              <strong>{me.player.display_name ?? me.player.discord_username}</strong>
              <span>{me.player.steam_connected ? me.player.steam_name : "Steam not linked"}</span>
              <button onClick={() => void onLogout()}>Log out</button>
            </>
          ) : (
            <>
              <strong>Discord login required</strong>
              <span>Authenticate to queue, ready up, and manage matches.</span>
              <a className="button-link" href={loginHref}>
                Log in with Discord
              </a>
            </>
          )}
        </div>
      </header>
      <nav className="nav">
        <NavLink to="/">Home</NavLink>
        <NavLink to="/queue">Queue</NavLink>
        <NavLink to="/leaderboard">Leaderboard</NavLink>
        <NavLink to="/admin">Admin</NavLink>
      </nav>
      <main className="content">{children}</main>
    </div>
  );
}
