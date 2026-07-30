"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { CompareTray } from "@/components/CompareTray";
import { useProfileStore } from "@/lib/profileStore";

const ROUTES: [string, string][] = [
  ["/", "Your profile"],
  ["/browse", "Browse schools"],
  ["/majors", "Major Finder"],
  ["/list", "My college list"],
];

export function AppShell({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const pathname = usePathname();
  const { list } = useProfileStore();

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  return (
    <>
      <nav className="nav">
        <div className="nav-inner">
          <Link href="/" className="brand">
            <span className="dot" />
            Uni<b>Match</b>
          </Link>
          <div style={{ marginLeft: "auto" }} />
          <button
            className="icon-btn"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            title="Toggle theme"
            aria-label="Toggle theme"
          >
            {theme === "dark" ? "🌙" : "☀️"}
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
            <b>358</b>
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
          {ROUTES.map(([href, label]) => (
            <Link
              key={href}
              href={href}
              className={`tab ${pathname === href ? "on" : ""}`}
              aria-current={pathname === href ? "page" : undefined}
            >
              {label}
              {href === "/list" && list.length > 0 && (
                <span className="tab-count">{list.length}</span>
              )}
            </Link>
          ))}
        </nav>
      </div>

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
