"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";

import type {
  Activity,
  AdmitTier,
  InstitutionType,
  RecommendationResponse,
  Region,
  Scope,
  Setting,
  UniversitySummary,
} from "./contract";

/** Compare holds finalists, not a spreadsheet; a fourth column stops fitting. */
export const COMPARE_LIMIT = 3;

const STORAGE_KEY = "unimatch.v1";

export interface ListedSchool {
  id: string;
  name: string;
  fit: number | null;
  tier: AdmitTier | null;
  university: UniversitySummary;
}

export interface FormState {
  gpa: string;
  /** Weighted GPA, 0.0-5.0. Optional, displayed only - never scored or
   *  converted. Blank must be omitted from the request body entirely. */
  gpaWeighted: string;
  sat: string;
  major: string;
  maxNetPrice: string;
  scope: Scope;
  regions: Region[];
  settings: Setting[];
  institutionType: InstitutionType | null;
}

const EMPTY_FORM: FormState = {
  gpa: "3.8",
  gpaWeighted: "",
  sat: "",
  major: "Computer Science",
  maxNetPrice: "",
  scope: "both",
  regions: [],
  settings: [],
  institutionType: null,
};

interface Persisted {
  form: FormState;
  answers: Record<string, number>;
  activities: Activity[];
  list: ListedSchool[];
}

const EMPTY: Persisted = { form: EMPTY_FORM, answers: {}, activities: [], list: [] };

/** A malformed stored value must not white-screen the app - but recovering
 *  from one must not be silent either, or a student whose list vanished cannot
 *  tell a bug from a browser that wiped its storage. `recovered` says which
 *  happened; it is session-only, since the next write repairs the value. */
function readStored(): { state: Persisted; recovered: boolean } {
  if (typeof window === "undefined") return { state: EMPTY, recovered: false };
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { state: EMPTY, recovered: false };
    const parsed = JSON.parse(raw) as Partial<Persisted>;
    return {
      state: {
        form: { ...EMPTY_FORM, ...(parsed.form ?? {}) },
        answers: parsed.answers ?? {},
        activities: parsed.activities ?? [],
        list: parsed.list ?? [],
      },
      recovered: false,
    };
  } catch {
    return { state: EMPTY, recovered: true };
  }
}

/**
 * A tiny external store around localStorage, read through useSyncExternalStore.
 *
 * `getSnapshot` does the actual localStorage read, lazily, on its first call.
 * Reading happens inside `getSnapshot` (invoked synchronously during render)
 * rather than in a `useEffect` + `setState` — that pattern is what
 * `react-hooks/set-state-in-effect` flags as a cascading-render smell, and
 * it's also exactly what `useSyncExternalStore`'s `getServerSnapshot`
 * parameter exists to solve: the server (and the first client render) sees
 * `EMPTY`, and once mounted in a real browser React reconciles against the
 * true client snapshot on its own — no manual "hydrated" flag needed.
 */
function createLocalStore() {
  let current = EMPTY;
  let hydrated = false;
  let recovered = false;
  const listeners = new Set<() => void>();

  function ensureHydrated() {
    if (!hydrated && typeof window !== "undefined") {
      const read = readStored();
      current = read.state;
      recovered = read.recovered;
      hydrated = true;
    }
  }

  return {
    getSnapshot: (): Persisted => {
      ensureHydrated();
      return current;
    },
    getServerSnapshot: (): Persisted => EMPTY,
    /** Whether hydration had to discard an unreadable stored value. Read after
     *  getSnapshot, which is what performs the hydration. */
    wasRecovered: (): boolean => recovered,
    subscribe: (onStoreChange: () => void): (() => void) => {
      listeners.add(onStoreChange);
      return () => listeners.delete(onStoreChange);
    },
    update: (updater: (prev: Persisted) => Persisted) => {
      ensureHydrated();
      current = updater(current);
      listeners.forEach((listener) => listener());
    },
  };
}

interface Store extends Persisted {
  setForm: (next: FormState) => void;
  setAnswers: (next: Record<string, number>) => void;
  setActivities: (next: Activity[]) => void;
  addToList: (school: ListedSchool) => void;
  removeFromList: (id: string) => void;
  isListed: (id: string) => boolean;
  compare: ListedSchool[];
  addToCompare: (school: ListedSchool) => void;
  removeFromCompare: (id: string) => void;
  /**
   * The last recommendation run, held in memory only — same lifetime as
   * `compare`, not `localStorage`. Results are large (the full ranked list
   * plus rationale and trace) and go stale as soon as the catalog changes
   * underneath them, so persisting them across browser sessions would be
   * actively misleading. Session-scoped is exactly enough: it survives a
   * route change within the app (the provider lives in the root layout,
   * above the router outlet) but not a reload.
   */
  results: RecommendationResponse | null;
  setResults: (next: RecommendationResponse | null) => void;
  reset: () => void;
  /** True when a saved profile existed but could not be read, so this session
   *  started empty. Session-only: the next write repairs the stored value. */
  storageRecovered: boolean;
}

const Ctx = createContext<Store | null>(null);

export function ProfileProvider({ children }: { children: ReactNode }) {
  // Lazy useState initializer, not useRef: reading a ref's `.current` during
  // render is itself flagged (react-hooks/refs) — a lazy initializer runs
  // exactly once and gives the same "create it once, keep it stable" result
  // without touching a ref.
  const [localStore] = useState(() => createLocalStore());

  const state = useSyncExternalStore(
    localStore.subscribe,
    localStore.getSnapshot,
    localStore.getServerSnapshot,
  );
  // Read after useSyncExternalStore above, which is what triggers hydration.
  const storageRecovered = localStore.wasRecovered();
  const [compare, setCompare] = useState<ListedSchool[]>([]);
  const [results, setResultsState] = useState<RecommendationResponse | null>(null);

  // Mirror every change back to localStorage. This is a plain "sync an
  // external system with the latest React state" effect, not a setState — no
  // cascading-render concern here.
  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [state]);

  const setState = localStore.update;

  const setForm = useCallback((form: FormState) => setState((s) => ({ ...s, form })), [setState]);
  const setAnswers = useCallback(
    (answers: Record<string, number>) => setState((s) => ({ ...s, answers })),
    [setState],
  );
  const setActivities = useCallback(
    (activities: Activity[]) => setState((s) => ({ ...s, activities })),
    [setState],
  );
  const addToList = useCallback(
    (school: ListedSchool) =>
      setState((s) =>
        s.list.some((x) => x.id === school.id) ? s : { ...s, list: [...s.list, school] },
      ),
    [setState],
  );
  const removeFromList = useCallback(
    (id: string) => setState((s) => ({ ...s, list: s.list.filter((x) => x.id !== id) })),
    [setState],
  );
  const addToCompare = useCallback(
    (school: ListedSchool) =>
      setCompare((current) =>
        current.length >= COMPARE_LIMIT || current.some((x) => x.id === school.id)
          ? current
          : [...current, school],
      ),
    [],
  );
  const removeFromCompare = useCallback(
    (id: string) => setCompare((current) => current.filter((x) => x.id !== id)),
    [],
  );
  const setResults = useCallback(
    (next: RecommendationResponse | null) => setResultsState(next),
    [],
  );
  const reset = useCallback(() => {
    setState(() => EMPTY);
    setCompare([]);
    setResultsState(null);
  }, [setState]);

  const value = useMemo<Store>(
    () => ({
      ...state,
      setForm,
      setAnswers,
      setActivities,
      addToList,
      removeFromList,
      isListed: (id: string) => state.list.some((x) => x.id === id),
      compare,
      addToCompare,
      removeFromCompare,
      results,
      setResults,
      reset,
      storageRecovered,
    }),
    [state, compare, results, storageRecovered, setForm, setAnswers, setActivities, addToList,
     removeFromList, addToCompare, removeFromCompare, setResults, reset],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useProfileStore(): Store {
  const store = useContext(Ctx);
  if (!store) throw new Error("useProfileStore must be used inside ProfileProvider");
  return store;
}
