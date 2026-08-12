"use client";

import { useMemo, useState } from "react";

import { CATALOG_SIZE } from "@/lib/catalogStats";
import type { University } from "@/lib/contract";
import { formatStat } from "@/lib/format";
import { COMPARE_LIMIT, useProfileStore } from "@/lib/profileStore";
import { countriesOf, searchUniversities } from "@/lib/search";

const PAGE = 24;

/**
 * Browse every school in the catalog, independent of whether it happened to
 * surface in a match. The catalog arrives once and is filtered in memory, so
 * results update as you type.
 */
export function BrowseSection({
  catalog,
  error,
  onOpen,
}: {
  catalog: University[] | null;
  error: string | null;
  onOpen: (uni: University) => void;
}) {
  const [query, setQuery] = useState("");
  const [country, setCountry] = useState("");
  const [size, setSize] = useState("");
  const [shown, setShown] = useState(PAGE);

  const { addToList, isListed, addToCompare, compare } = useProfileStore();

  // Changing a filter resets paging. Done here rather than in an effect, which
  // would trigger a cascading render.
  const applyQuery = (value: string) => {
    setQuery(value);
    setShown(PAGE);
  };
  const applyCountry = (value: string) => {
    setCountry(value);
    setShown(PAGE);
  };
  const applySize = (value: string) => {
    setSize(value);
    setShown(PAGE);
  };

  const countries = useMemo(() => (catalog ? countriesOf(catalog) : []), [catalog]);
  const matches = useMemo(
    () => (catalog ? searchUniversities(catalog, query, { country, size }) : []),
    [catalog, query, country, size],
  );

  return (
    <section className="section" id="browse">
      <h2>Browse &amp; search all schools</h2>
      <p className="lead">
        Look up any of the {catalog?.length ?? CATALOG_SIZE} schools by name, city, country or
        subject — then open it for the full profile.
      </p>

      <div className="grid3" style={{ marginBottom: 18 }}>
        <div style={{ gridColumn: "span 1" }}>
          <label className="fld" htmlFor="browse-q">
            Search
          </label>
          <input
            id="browse-q"
            type="text"
            value={query}
            onChange={(e) => applyQuery(e.target.value)}
            placeholder="e.g. Berkeley, Boston, music, nursing"
            autoComplete="off"
          />
        </div>
        <div>
          <label className="fld" htmlFor="browse-country">
            Country
          </label>
          <select id="browse-country" value={country} onChange={(e) => applyCountry(e.target.value)}>
            <option value="">All countries</option>
            {countries.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="fld" htmlFor="browse-size">
            Campus size
          </label>
          <select id="browse-size" value={size} onChange={(e) => applySize(e.target.value)}>
            <option value="">Any size</option>
            <option value="small">Small</option>
            <option value="medium">Medium</option>
            <option value="large">Large</option>
          </select>
        </div>
      </div>

      {error && <p className="notice error">{error}</p>}
      {!catalog && !error && <p className="muted">Loading the catalog…</p>}

      {catalog && (
        <>
          <p className="muted" style={{ fontSize: 13, marginBottom: 12 }}>
            {matches.length} school{matches.length === 1 ? "" : "s"}
            {query && <> matching &ldquo;{query}&rdquo;</>}
          </p>

          {matches.length === 0 ? (
            <p className="notice empty">
              Nothing matched. Try a shorter search, or clear the country and size filters.
            </p>
          ) : (
            <div className="cards">
              {matches.slice(0, shown).map((uni) => {
                const price = formatStat(uni.net_price, uni.provenance.net_price, "money");
                const rate = formatStat(
                  uni.acceptance_rate,
                  uni.provenance.acceptance_rate,
                  "percent",
                );
                const listed = isListed(uni.id);
                const compareFull = compare.length >= COMPARE_LIMIT;
                const inCompare = compare.some((s) => s.id === uni.id);
                const asListed = { id: uni.id, name: uni.name, fit: null, tier: null, university: uni };
                return (
                  <div key={uni.id} className="card" role="group" aria-label={uni.name}>
                    <div className="card-head">
                      <div>
                        <h3>{uni.name}</h3>
                        <div className="loc">
                          {uni.location} · {uni.country} · {uni.size}
                        </div>
                      </div>
                      <span className="muted" style={{ fontSize: 13, whiteSpace: "nowrap" }}>
                        {price.text} · {rate.text} admit
                      </span>
                    </div>

                    <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
                      <button type="button" className="chip" onClick={() => onOpen(uni)}>
                        Full profile
                      </button>
                      <button
                        type="button"
                        className={`chip ${listed ? "on" : ""}`}
                        disabled={listed}
                        onClick={() => addToList(asListed)}
                      >
                        {listed ? "On your list" : "Add to my list"}
                      </button>
                      <button
                        type="button"
                        className={`chip ${inCompare ? "on" : ""}`}
                        disabled={inCompare || compareFull}
                        title={
                          compareFull && !inCompare
                            ? "Compare is full — remove one to add another"
                            : undefined
                        }
                        onClick={() => addToCompare(asListed)}
                      >
                        {inCompare ? "Comparing" : compareFull ? "Compare full" : "Compare"}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {matches.length > shown && (
            <div style={{ textAlign: "center", marginTop: 18 }}>
              <button className="btn ghost" onClick={() => setShown(shown + PAGE)}>
                Show more schools
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
