import type { University } from "./contract";

/**
 * Local search over the catalog.
 *
 * The whole catalog arrives in one request, so filtering happens in memory and
 * results update as you type - no request per keystroke.
 */
export function searchUniversities(
  catalog: University[],
  query: string,
  filters: { country?: string; size?: string } = {},
): University[] {
  const needle = query.trim().toLowerCase();

  return catalog.filter((uni) => {
    if (filters.country && uni.country !== filters.country) return false;
    if (filters.size && uni.size !== filters.size) return false;
    if (!needle) return true;
    // Name, place and subject all count: someone may search "Boston", "music"
    // or "Berkeley" and expect the same box to work.
    return (
      uni.name.toLowerCase().includes(needle) ||
      uni.location.toLowerCase().includes(needle) ||
      uni.country.toLowerCase().includes(needle) ||
      uni.majors.some((major) => major.toLowerCase().includes(needle))
    );
  });
}

/** Countries present in the catalog, most-populous first then alphabetical. */
export function countriesOf(catalog: University[]): string[] {
  const counts = new Map<string, number>();
  for (const uni of catalog) counts.set(uni.country, (counts.get(uni.country) ?? 0) + 1);
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([country]) => country);
}
