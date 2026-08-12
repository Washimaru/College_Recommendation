"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { GraduationCap, Moon, Sun, UserRound, Search, Compass, ListChecks } from "lucide-react";

import { CompareTray } from "@/components/CompareTray";
import { CATALOG_SIZE } from "@/lib/catalogStats";
import { useProfileStore } from "@/lib/profileStore";

const ROUTES: [string, string, ReactNode][] = [
  ["/", "Your profile", <UserRound key="i" size={16} aria-hidden />],
  ["/browse", "Browse schools", <Search key="i" size={16} aria-hidden />],
  ["/majors", "Major Finder", <Compass key="i" size={16} aria-hidden />],
  ["/list", "My college list", <ListChecks key="i" size={16} aria-hidden />],
];

export function AppShell({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<"dark" | "light">("light");
  const pathname = usePathname();
  const { list, storageRecovered } = useProfileStore();
  const [recoveryDismissed, setRecoveryDismissed] = useState(false);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  return (
    <>
      <nav className="nav">
        <div className="nav-inner">
          <Link href="/" className="brand">
            <span className="dot">
              <GraduationCap size={18} aria-hidden />
            </span>
            Uni<b>Match</b>
          </Link>
          <div style={{ marginLeft: "auto" }} />
          <button
            className="icon-btn"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            title="Toggle theme"
            aria-label="Toggle theme"
          >
            {theme === "dark" ? <Sun size={18} aria-hidden /> : <Moon size={18} aria-hidden />}
          </button>
        </div>
      </nav>

      <header className="hero wrap">
        <span className="eyebrow">Holistic matching · not just filters</span>
        <h1>
          Find the university that <span className="g">fits who you are</span>
        </h1>
        <p>
          Put in your real profile, then explore. Compare the schools you like, keep a list of
          where you mean to apply, and see how balanced that list actually is.
        </p>
        <div className="hero-stats">
          <div>
            <b>{CATALOG_SIZE}</b>
            <span>universities · 26 countries</span>
          </div>
          <div>
            <b>6</b>
            <span>culture dimensions</span>
          </div>
          <div>
            <b>6</b>
            <span>scored dimensions</span>
          </div>
        </div>
      </header>

      <div className="wrap">
        <nav className="tabs" aria-label="Sections">
          {ROUTES.map(([href, label, icon]) => (
            <Link
              key={href}
              href={href}
              className={`tab ${pathname === href ? "on" : ""}`}
              aria-current={pathname === href ? "page" : undefined}
            >
              {icon}
              {label}
              {href === "/list" && list.length > 0 && (
                <span className="tab-count">{list.length}</span>
              )}
            </Link>
          ))}
        </nav>
      </div>

      {/* Recovering from unreadable storage is correct behaviour; doing it in
          silence is not. Shown on every route because the store is global, and
          dismissible because it is about a session, not a task. */}
      {storageRecovered && !recoveryDismissed && (
        <div className="wrap">
          <p className="notice error" role="status" style={{ display: "flex", gap: 12, alignItems: "baseline" }}>
            <span style={{ flex: 1 }}>
              We couldn&rsquo;t read your saved profile and college list, so this session
              started empty. Nothing you do now is affected — the next change saves normally.
            </span>
            <button type="button" className="chip" onClick={() => setRecoveryDismissed(true)}>
              Dismiss
            </button>
          </p>
        </div>
      )}

      {children}
      <CompareTray />

      <footer>
        UniMatch · figures are approximate and for exploration only — always verify on official
        sites.
        <br />
        Admitted-GPA and campus-culture ratings are editorial estimates; admissions, cost and
        outcome figures come from the U.S. Dept. of Education College Scorecard where available.
      </footer>
    </>
  );
}
