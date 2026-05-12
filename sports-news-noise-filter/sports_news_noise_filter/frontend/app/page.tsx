"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000";

type Mode = "preferences" | "feed" | "detail";

type FeedClusterRow = {
  cluster_id: string;
  headline: string | null;
  source_count: number;
  latest_published_at: string | null;
  sport?: string | null;
  topic?: string | null;
  /** If backend adds competition to payloads; safe if omitted. */
  competition?: string | null;
  /** Present only if backend adds it to /feed_clusters; otherwise omit. */
  summary?: string | null;
};

type ClusterDetail = {
  id: string;
  headline: string | null;
  /** Optional if backend adds it later; safe if omitted. */
  sport?: string | null;
  created_at: string;
  articles: Array<{ id: string; title: string; url: string }>;
  summary?: string | null;
  what_changed?: string | null;
  facts_json?: unknown;
  entities_json?: unknown;
  llm_model_name?: string | null;
  llm_updated_at?: string | null;
};

const SPORT_OPTIONS = ["soccer", "f1", "nba", "other"] as const;

/** Topic slugs sent to the API (must match worker / GET /feed_clusters filter). */
const TOPIC_OPTIONS = [
  "match",
  "preview",
  "lineup",
  "transfer",
  "injury",
  "discipline",
  "manager",
  "finance",
  "standings",
  "tactics",
  "opinion",
  "other",
] as const;

const STORAGE_HIDDEN_STORY_IDS = "hidden_story_ids";
const STORAGE_USER_ID = "user_id";
const STORAGE_USER_SPORTS = "user_sports";
const STORAGE_USER_TOPICS = "user_topics";
const STORAGE_RUMOR_TOLERANCE = "rumor_tolerance";
const STORAGE_THEME = "theme";
const STORAGE_FEED_SORT = "feed_sort";
const STORAGE_MY_TEAMS = "my_teams";
const STORAGE_LAST_REFRESH_ISO = "last_refresh_iso";
const STORAGE_LAST_SEEN_LATEST_ISO = "last_seen_latest_iso";
const STORAGE_TOP_COVERAGE_SPORT = "top_coverage_sport";
type ThemeMode = "light" | "dark";
type FeedSortMode = "recent" | "coverage";
type TopCoverageSport = "all" | "soccer" | "nba" | "f1" | "other";

function hasSavedPreferencesInStorage(): boolean {
  if (typeof window === "undefined") return false;
  return (
    localStorage.getItem(STORAGE_USER_SPORTS) !== null ||
    localStorage.getItem(STORAGE_USER_TOPICS) !== null
  );
}

function clearProfileLocalStorage() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(STORAGE_USER_ID);
  localStorage.removeItem(STORAGE_USER_SPORTS);
  localStorage.removeItem(STORAGE_USER_TOPICS);
  localStorage.removeItem(STORAGE_RUMOR_TOLERANCE);
  localStorage.removeItem(STORAGE_HIDDEN_STORY_IDS);
}

function loadHiddenStoryIds(): string[] {
  if (typeof window === "undefined") return [];
  const raw = localStorage.getItem(STORAGE_HIDDEN_STORY_IDS);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return [
      ...new Set(
        parsed.filter((x): x is string => typeof x === "string" && x !== ""),
      ),
    ];
  } catch {
    return [];
  }
}

function parseCommaList(s: string): string[] {
  return s
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
}

function loadSportsFromStorage(): string[] {
  if (typeof window === "undefined") return [];
  const raw = localStorage.getItem(STORAGE_USER_SPORTS);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (Array.isArray(parsed)) {
      const mapped = parsed
        .filter((x): x is string => typeof x === "string")
        .map((x) => (x.toLowerCase() === "wnba" ? "other" : x));
      const filtered = mapped.filter((x): x is string =>
        (SPORT_OPTIONS as readonly string[]).includes(x as (typeof SPORT_OPTIONS)[number]),
      );
      return [...new Set(filtered)];
    }
  } catch {
    /* legacy comma-separated ignored — fixed set only */
  }
  return [];
}

function loadTopicsFromStorage(): string[] {
  if (typeof window === "undefined") return [];
  const raw = localStorage.getItem(STORAGE_USER_TOPICS);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (Array.isArray(parsed)) {
      return parsed.filter(
        (x): x is string =>
          typeof x === "string" &&
          (TOPIC_OPTIONS as readonly string[]).includes(x),
      );
    }
  } catch {
    /* legacy comma-separated string */
  }
  return parseCommaList(raw)
    .map((x) => x.trim().toLowerCase())
    .filter((x) => (TOPIC_OPTIONS as readonly string[]).includes(x));
}

function sportFanLabel(sport: string | null | undefined): string {
  if (sport == null || sport === "") return "Other";
  const s = sport.toLowerCase();
  const map: Record<string, string> = {
    soccer: "Soccer",
    f1: "F1",
    nba: "NBA",
    wnba: "Other",
    other: "Other",
  };
  return (
    map[s] ?? sport.charAt(0).toUpperCase() + sport.slice(1).toLowerCase()
  );
}

function topicFanLabel(topic: string | null | undefined): string {
  if (topic == null || topic === "") return "Other";
  const t = topic.toLowerCase();
  const map: Record<string, string> = {
    match: "Match",
    preview: "Preview",
    lineup: "Lineup",
    transfer: "Transfer",
    injury: "Injury",
    discipline: "Discipline",
    manager: "Manager",
    finance: "Finance",
    standings: "Standings",
    tactics: "Tactics",
    opinion: "Opinion",
    other: "Other",
  };
  return map[t] ?? "Other";
}

/** Relative time for feed + AI lines: just now, 7m ago, 3h ago, yesterday, 2d ago, or locale date. */
function formatRelativeTime(iso: string | null | undefined): string {
  if (iso == null || iso === "") return "—";
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return String(iso);
  const then = new Date(t);
  const now = new Date();
  const diffSec = Math.floor((now.getTime() - t) / 1000);
  if (diffSec < 60) return "just now";
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  const startOf = (d: Date) =>
    new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const yest = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate() - 1,
  );
  if (startOf(then) === startOf(yest)) return "yesterday";
  const daySec = 86400;
  if (diffSec < 7 * daySec) return `${Math.floor(diffSec / daySec)}d ago`;
  return then.toLocaleDateString(undefined, { dateStyle: "medium" });
}

type LeagueInput = {
  headline?: string | null;
  sport?: string | null;
  competition?: string | null;
};

const COMP_NAME_TO_BADGE: Record<string, string> = {
  epl: "EPL",
  ucl: "UCL",
  laliga: "LaLiga",
  "serie a": "Serie A",
  bundesliga: "Bundesliga",
  wsl: "WSL",
  nba: "NBA",
  wnba: "WNBA",
  f1: "F1",
};

function inferLeague(
  row: FeedClusterRow | ClusterDetail | LeagueInput,
): string | null {
  const comp = "competition" in row ? row.competition : undefined;
  if (comp && typeof comp === "string" && comp.trim()) {
    const k = comp.trim().toLowerCase();
    if (COMP_NAME_TO_BADGE[k]) return COMP_NAME_TO_BADGE[k];
    if (k.includes("ucl") || k.includes("champions")) return "UCL";
    if (k.includes("premier") && k.includes("league")) return "EPL";
  }
  const h = (row.headline ?? "").toLowerCase();
  if (h.includes("premier league") || h.includes("epl")) return "EPL";
  if (h.includes("champions league") || h.includes(" ucl") || h.startsWith("ucl "))
    return "UCL";
  if (h.includes("laliga") || h.includes("la liga") || h.includes("real madrid") || h.includes("barcelona"))
    return "LaLiga";
  if (
    h.includes("serie a") ||
    h.includes("juventus") ||
    h.includes("inter milan") ||
    h.includes("ac milan") ||
    h.includes("milan")
  )
    return "Serie A";
  if (h.includes("bundesliga") || h.includes("bayern") || h.includes("dortmund"))
    return "Bundesliga";
  if (h.includes("wsl") || h.includes("women's super league") || h.includes("womens super league"))
    return "WSL";
  const s = (row.sport ?? "").toLowerCase();
  if (s === "nba") return "NBA";
  if (s === "wnba") return "WNBA";
  if (s === "f1") return "F1";
  return null;
}

function inferCompetitionMark(
  row: FeedClusterRow | ClusterDetail | LeagueInput,
): { code: string; mark: string } | null {
  const league = inferLeague(row);
  if (!league) return null;
  const marks: Record<string, string> = {
    EPL: "🦁",
    UCL: "⭐",
    LaLiga: "🌞",
    "Serie A": "🇮🇹",
    Bundesliga: "🇩🇪",
    WSL: "👟",
    NBA: "🏀",
    WNBA: "🏀",
    F1: "🏎️",
  };
  const mark = marks[league];
  if (!mark) return null;
  return { code: league, mark };
}

function cleanHeadline(s: string | null | undefined): string | null {
  if (typeof s !== "string") return null;
  const t = s
    .replace(/\[\s*placeholder\s*\]|\(\s*placeholder\s*\)|\bplaceholder\b/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
  return t || null;
}

function isRumorLikeStory(row: FeedClusterRow): boolean {
  const topic = (row.topic ?? "").trim().toLowerCase();
  if (topic === "transfer") return true;
  const h = (cleanHeadline(row.headline) ?? "").toLowerCase();
  const rumorTerms = [
    "gossip",
    "rumor",
    "rumour",
    "linked",
    "target",
    "in talks",
    "set to",
    "could",
    "might",
    "sources",
    "reports",
    "odds",
    "betting",
  ];
  return rumorTerms.some((term) => h.includes(term));
}

function passesRumorTolerance(
  row: FeedClusterRow,
  tolerance: "low" | "balanced" | "high",
): boolean {
  if (tolerance === "high") return true;
  if (tolerance === "low") return !isRumorLikeStory(row);
  const h = (cleanHeadline(row.headline) ?? "").toLowerCase();
  return !(
    h.includes("gossip") ||
    h.includes("rumor") ||
    h.includes("rumour") ||
    h.includes("odds") ||
    h.includes("betting")
  );
}

function myTeamTokens(input: string): string[] {
  return input
    .split(",")
    .map((x) => x.trim().toLowerCase())
    .filter(Boolean);
}

function passesMyTeamsFilter(
  headline: string | null | undefined,
  tokens: string[],
): boolean {
  if (tokens.length === 0) return true;
  const h = (headline ?? "").toLowerCase();
  return tokens.some((t) => h.includes(t));
}

function recencyBoostMs(iso: string | null | undefined): number {
  if (!iso) return 0;
  const n = Date.parse(iso);
  if (!Number.isFinite(n)) return 0;
  const ageH = (Date.now() - n) / 3600000;
  if (ageH < 3) return 6;
  if (ageH < 12) return 3;
  return 0;
}

function asFactsRecord(v: unknown): Record<string, unknown> | null {
  if (v === null || v === undefined) return null;
  if (typeof v !== "object" || Array.isArray(v)) return null;
  return v as Record<string, unknown>;
}

function asEntitiesRecord(v: unknown): Record<string, unknown> | null {
  if (v === null || v === undefined) return null;
  if (typeof v !== "object" || Array.isArray(v)) return null;
  return v as Record<string, unknown>;
}

function strVal(v: unknown): string {
  if (typeof v === "string") return v;
  if (v == null) return "";
  return String(v);
}

function stringList(v: unknown, max: number): string[] {
  if (!Array.isArray(v)) return [];
  const out: string[] = [];
  for (const x of v) {
    if (typeof x === "string" && x.trim()) out.push(x.trim());
    if (out.length >= max) break;
  }
  return out;
}

type ManagerQuote = { speaker: string; quote: string };

function managerQuotesList(v: unknown, max: number): ManagerQuote[] {
  if (!Array.isArray(v)) return [];
  const out: ManagerQuote[] = [];
  for (const x of v) {
    if (out.length >= max) break;
    if (x !== null && typeof x === "object" && !Array.isArray(x)) {
      const o = x as Record<string, unknown>;
      const speaker = strVal(o.speaker);
      const quote = strVal(o.quote);
      if (speaker || quote) out.push({ speaker, quote });
    }
  }
  return out;
}

function feedSummaryHint(summary: string | null | undefined): string | null {
  if (typeof summary !== "string") return null;
  const t = summary.trim();
  if (!t) return null;
  return t.length > 120 ? `${t.slice(0, 120)}…` : t;
}

const shell: React.CSSProperties = {
  minHeight: "100vh",
  fontFamily:
    'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif',
  background: "var(--bg)",
  color: "var(--text)",
};

const container: React.CSSProperties = {
  maxWidth: 720,
  margin: "0 auto",
  padding: "28px 20px 48px",
};

const h1: React.CSSProperties = {
  fontSize: "1.5rem",
  fontWeight: 700,
  letterSpacing: "-0.02em",
  margin: "0 0 8px",
  color: "var(--text)",
};

const sub: React.CSSProperties = {
  fontSize: "0.875rem",
  color: "var(--muted)",
  margin: "0 0 24px",
};

const playerSetupBox: React.CSSProperties = {
  marginBottom: 22,
  padding: "16px 18px",
  borderRadius: 10,
  border: "1px solid var(--border)",
  background: "var(--card)",
  boxShadow: "var(--shadowSm)",
};

const statusPill: React.CSSProperties = {
  display: "inline-block",
  fontSize: "0.8125rem",
  fontWeight: 600,
  padding: "6px 12px",
  borderRadius: 999,
  background: "var(--pillNeutralBg)",
  color: "var(--pillNeutralText)",
};

const navRow: React.CSSProperties = {
  display: "flex",
  gap: 10,
  marginBottom: 24,
};

const btnBase: React.CSSProperties = {
  padding: "8px 16px",
  borderRadius: 8,
  border: "1px solid var(--btnBorder)",
  background: "var(--btnBg)",
  color: "var(--text)",
  fontSize: "0.875rem",
  fontWeight: 500,
  cursor: "pointer",
};

const btnPrimary: React.CSSProperties = {
  ...btnBase,
  background: "var(--btnPrimaryBg)",
  color: "var(--btnPrimaryText)",
  borderColor: "var(--btnPrimaryBorder)",
};

const labelStyle: React.CSSProperties = {
  display: "block",
  marginBottom: 14,
  fontSize: "0.8125rem",
  fontWeight: 600,
  color: "var(--label)",
};

const inputStyle: React.CSSProperties = {
  display: "block",
  width: "100%",
  marginTop: 6,
  padding: "10px 12px",
  borderRadius: 8,
  border: "1px solid var(--inputBorder)",
  background: "var(--inputBg)",
  color: "var(--text)",
  fontSize: "0.9375rem",
  boxSizing: "border-box",
};

const metaMuted: React.CSSProperties = {
  fontSize: "0.75rem",
  color: "var(--muted)",
  textTransform: "uppercase",
  letterSpacing: "0.04em",
  fontWeight: 600,
};

const panelBox: React.CSSProperties = {
  marginBottom: 16,
  padding: "14px 16px",
  borderRadius: 10,
  border: "1px solid var(--panelBorder)",
  background: "var(--panelBg)",
  boxShadow: "var(--shadowSm)",
};

const sectionTitle: React.CSSProperties = {
  fontSize: "0.8125rem",
  fontWeight: 700,
  color: "var(--panelTitle)",
  textTransform: "uppercase",
  letterSpacing: "0.06em",
  margin: "0 0 10px",
};

export default function Page() {
  const [bootstrapping, setBootstrapping] = useState(true);
  const [pending, setPending] = useState(false);
  const [feedLoading, setFeedLoading] = useState(false);
  const [appError, setAppError] = useState<string | null>(null);
  const [feedError, setFeedError] = useState<string | null>(null);
  const [userId, setUserId] = useState<string | null>(null);

  const [mode, setMode] = useState<Mode>("feed");
  const [selectedSports, setSelectedSports] = useState<string[]>([]);
  const [selectedTopics, setSelectedTopics] = useState<string[]>([]);
  const [rumorTolerance, setRumorTolerance] = useState<
    "low" | "balanced" | "high"
  >("balanced");

  const [clusters, setClusters] = useState<FeedClusterRow[]>([]);
  const [selectedStoryId, setSelectedStoryId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ClusterDetail | null>(null);
  const [hiddenStoryIds, setHiddenStoryIds] = useState<string[]>([]);
  const [onlyMultiSource, setOnlyMultiSource] = useState(false);
  const [feedUpdatedAt, setFeedUpdatedAt] = useState<Date | null>(null);
  const [refreshingFeed, setRefreshingFeed] = useState(false);

  const [theme, setTheme] = useState<ThemeMode>("light");
  const [feedSort, setFeedSort] = useState<FeedSortMode>("coverage");
  const [myTeamsInput, setMyTeamsInput] = useState("");
  const [topCoverageSport, setTopCoverageSport] =
    useState<TopCoverageSport>("all");
  const [runningIngest, setRunningIngest] = useState(false);
  const [toast, setToast] = useState<{ visible: boolean; lastHiddenId?: string }>(
    { visible: false },
  );
  const [newSinceLastRefresh, setNewSinceLastRefresh] = useState(0);

  const busy = bootstrapping || pending || feedLoading;

  const teamTokens = useMemo(() => myTeamTokens(myTeamsInput), [myTeamsInput]);

  const pubMs = useCallback((iso: string | null | undefined): number | null => {
    if (!iso) return null;
    const n = Date.parse(iso);
    return Number.isFinite(n) ? n : null;
  }, []);

  const baseFilteredStories = useMemo(() => {
    const hidden = new Set(hiddenStoryIds);
    let rows = clusters.filter((c) => !hidden.has(c.cluster_id));
    if (onlyMultiSource) {
      rows = rows.filter((c) => c.source_count >= 2);
    }
    rows = rows.filter((c) => passesMyTeamsFilter(c.headline, teamTokens));
    rows = rows.filter((c) => passesRumorTolerance(c, rumorTolerance));
    return rows;
  }, [
    clusters,
    hiddenStoryIds,
    onlyMultiSource,
    rumorTolerance,
    teamTokens,
  ]);

  const feedStories = useMemo(() => {
    let rows = [...baseFilteredStories];
    rows.sort((a, b) => {
      if (feedSort === "coverage") {
        const sc = b.source_count - a.source_count;
        if (sc !== 0) return sc;
        const at = pubMs(a.latest_published_at);
        const bt = pubMs(b.latest_published_at);
        if (at === null && bt === null) return 0;
        if (at === null) return 1;
        if (bt === null) return -1;
        return bt - at;
      }
      const at = pubMs(a.latest_published_at);
      const bt = pubMs(b.latest_published_at);
      if (at !== null && bt !== null && bt !== at) return bt - at;
      if (at === null && bt === null) {
        return b.source_count - a.source_count;
      }
      if (at === null) return 1;
      if (bt === null) return -1;
      return b.source_count - a.source_count;
    });
    return rows;
  }, [baseFilteredStories, feedSort, pubMs]);

  const hotStories = useMemo(() => {
    const scored = baseFilteredStories.map((c) => ({
      row: c,
      score:
        c.source_count * 2 + recencyBoostMs(c.latest_published_at),
    }));
    scored.sort((x, y) => y.score - x.score);
    return scored.slice(0, 3).map((s) => s.row);
  }, [baseFilteredStories]);
  const topCoverageStories = useMemo(() => {
    const hidden = new Set(hiddenStoryIds);
    const allRows = [...clusters].filter((c) => !hidden.has(c.cluster_id));
    const filteredByUser = allRows
      .filter((c) => passesMyTeamsFilter(c.headline, teamTokens))
      .filter((c) => passesRumorTolerance(c, rumorTolerance));

    function matchesSport(row: FeedClusterRow, sel: TopCoverageSport): boolean {
      if (sel === "all") return true;
      const s = (row.sport ?? "").trim().toLowerCase();
      if (sel === "soccer") return s === "soccer";
      if (sel === "nba") return s === "nba";
      if (sel === "f1") return s === "f1";
      // other: treat wnba and unknown tags as Other
      return s === "other" || s === "wnba" || !s || (s !== "soccer" && s !== "nba" && s !== "f1");
    }

    const primary = filteredByUser.filter((c) => matchesSport(c, topCoverageSport));
    const base =
      primary.length === 0 && filteredByUser.length > 0
        ? filteredByUser
        : filteredByUser.length > 0
          ? primary
          : allRows;

    return base
      .slice()
      .sort((a, b) => {
        const byCoverage = b.source_count - a.source_count;
        if (byCoverage !== 0) return byCoverage;
        const at = pubMs(a.latest_published_at);
        const bt = pubMs(b.latest_published_at);
        if (at === null && bt === null) return 0;
        if (at === null) return 1;
        if (bt === null) return -1;
        return bt - at;
      })
      .slice(0, 7);
  }, [clusters, hiddenStoryIds, pubMs, rumorTolerance, teamTokens, topCoverageSport]);

  useEffect(() => {
    try {
      setAppError(null);
      const th = localStorage.getItem(STORAGE_THEME);
      if (th === "dark" || th === "light") setTheme(th);
      const fs = localStorage.getItem(STORAGE_FEED_SORT);
      if (fs === "recent" || fs === "coverage") setFeedSort(fs);
      else localStorage.setItem(STORAGE_FEED_SORT, "coverage");
      const mt = localStorage.getItem(STORAGE_MY_TEAMS);
      if (typeof mt === "string") setMyTeamsInput(mt);
      const tcs = localStorage.getItem(STORAGE_TOP_COVERAGE_SPORT);
      if (
        tcs === "all" ||
        tcs === "soccer" ||
        tcs === "nba" ||
        tcs === "f1" ||
        tcs === "other"
      ) {
        setTopCoverageSport(tcs);
      }
      const uid =
        typeof window !== "undefined"
          ? localStorage.getItem(STORAGE_USER_ID)
          : null;
      setUserId(uid);
      if (uid) {
        setSelectedSports(loadSportsFromStorage());
        setSelectedTopics(loadTopicsFromStorage());
        setHiddenStoryIds(loadHiddenStoryIds());
        const rt = localStorage.getItem(STORAGE_RUMOR_TOLERANCE);
        if (rt === "low" || rt === "balanced" || rt === "high") {
          setRumorTolerance(rt);
        }
      }
    } catch (e) {
      setAppError(e instanceof Error ? e.message : String(e));
    } finally {
      setBootstrapping(false);
    }
  }, []);

  function setThemePersist(next: ThemeMode) {
    setTheme(next);
    localStorage.setItem(STORAGE_THEME, next);
  }

  function setFeedSortPersist(next: FeedSortMode) {
    setFeedSort(next);
    localStorage.setItem(STORAGE_FEED_SORT, next);
  }

  useEffect(() => {
    if (!toast.visible || !toast.lastHiddenId) return;
    const t = window.setTimeout(() => {
      setToast({ visible: false });
    }, 6000);
    return () => window.clearTimeout(t);
  }, [toast.visible, toast.lastHiddenId]);

  async function createMyProfile() {
    setPending(true);
    setAppError(null);
    try {
      const res = await fetch(`${API_BASE}/users`, { method: "POST" });
      if (!res.ok) {
        throw new Error(`POST /users failed: ${res.status}`);
      }
      const data = (await res.json()) as { id: string };
      const id = data.id;
      localStorage.setItem(STORAGE_USER_ID, id);
      setUserId(id);
      setSelectedSports(loadSportsFromStorage());
      setSelectedTopics(loadTopicsFromStorage());
      setHiddenStoryIds(loadHiddenStoryIds());
      const rt = localStorage.getItem(STORAGE_RUMOR_TOLERANCE);
      if (rt === "low" || rt === "balanced" || rt === "high") {
        setRumorTolerance(rt);
      } else {
        setRumorTolerance("balanced");
      }
      setClusters([]);
      setFeedError(null);
      setDetail(null);
      setSelectedStoryId(null);
      setMode(hasSavedPreferencesInStorage() ? "feed" : "preferences");
    } catch (e) {
      setAppError(e instanceof Error ? e.message : String(e));
    } finally {
      setPending(false);
    }
  }

  function resetProfile() {
    setAppError(null);
    setFeedError(null);
    clearProfileLocalStorage();
    setUserId(null);
    setSelectedSports([]);
    setSelectedTopics([]);
    setRumorTolerance("balanced");
    setHiddenStoryIds([]);
    setClusters([]);
    setDetail(null);
    setSelectedStoryId(null);
    setMode("feed");
    setFeedUpdatedAt(null);
  }

  const loadFeed = useCallback(
    async (opts?: { bypassCache?: boolean }) => {
      if (!userId) return;
      setFeedLoading(true);
      setFeedError(null);
      if (opts?.bypassCache) {
        setRefreshingFeed(true);
      }
      try {
        let url = `${API_BASE}/feed_clusters?user_id=${encodeURIComponent(userId)}`;
        if (opts?.bypassCache) {
          url += "&refresh=1";
        }
        const res = await fetch(url);
        if (!res.ok) {
          throw new Error(`Could not load story feed (${res.status})`);
        }
        const data = (await res.json()) as { items: FeedClusterRow[] };
        const items = data.items ?? [];
        setClusters(items);
        setFeedUpdatedAt(new Date());
        const nowIso = new Date().toISOString();
        localStorage.setItem(STORAGE_LAST_REFRESH_ISO, nowIso);
        let maxLatest = "";
        let maxMs = -Infinity;
        for (const it of items) {
          const iso = it.latest_published_at;
          if (!iso) continue;
          const ms = Date.parse(iso);
          if (Number.isFinite(ms) && ms > maxMs) {
            maxMs = ms;
            maxLatest = iso;
          }
        }
        const prevSeen = localStorage.getItem(STORAGE_LAST_SEEN_LATEST_ISO);
        let nNew = 0;
        if (prevSeen && maxLatest) {
          const prevMs = Date.parse(prevSeen);
          if (Number.isFinite(prevMs)) {
            for (const it of items) {
              const iso = it.latest_published_at;
              if (!iso) continue;
              const ms = Date.parse(iso);
              if (Number.isFinite(ms) && ms > prevMs) nNew += 1;
            }
          }
        }
        setNewSinceLastRefresh(nNew);
        if (maxLatest) {
          localStorage.setItem(STORAGE_LAST_SEEN_LATEST_ISO, maxLatest);
        }
      } catch (e) {
        setFeedError(e instanceof Error ? e.message : String(e));
      } finally {
        setFeedLoading(false);
        setRefreshingFeed(false);
      }
    },
    [userId],
  );

  useEffect(() => {
    if (!userId || mode !== "feed") return;
    void loadFeed();
  }, [userId, mode, loadFeed]);

  const loadDetail = useCallback(async (clusterId: string) => {
    setPending(true);
    setAppError(null);
    try {
      const res = await fetch(
        `${API_BASE}/clusters/${encodeURIComponent(clusterId)}`,
      );
      if (!res.ok) {
        throw new Error(`Could not load story (${res.status})`);
      }
      const data = (await res.json()) as ClusterDetail;
      setDetail(data);
    } catch (e) {
      setAppError(e instanceof Error ? e.message : String(e));
    } finally {
      setPending(false);
    }
  }, []);

  useEffect(() => {
    if (mode !== "detail" || !selectedStoryId) return;
    void loadDetail(selectedStoryId);
  }, [mode, selectedStoryId, loadDetail]);

  async function runIngestion() {
    setRunningIngest(true);
    setAppError(null);
    try {
      const res = await fetch(`${API_BASE}/admin/run_once`, { method: "POST" });
      if (!res.ok) {
        throw new Error(`Update sources failed (${res.status})`);
      }
      await loadFeed({ bypassCache: true });
    } catch (e) {
      setAppError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunningIngest(false);
    }
  }

  function toggleSport(sport: (typeof SPORT_OPTIONS)[number]) {
    setSelectedSports((prev) =>
      prev.includes(sport) ? prev.filter((s) => s !== sport) : [...prev, sport],
    );
  }

  function toggleTopic(topic: (typeof TOPIC_OPTIONS)[number]) {
    setSelectedTopics((prev) =>
      prev.includes(topic) ? prev.filter((t) => t !== topic) : [...prev, topic],
    );
  }

  async function savePreferences() {
    if (!userId) return;
    setPending(true);
    setAppError(null);
    try {
      const sportList = [...selectedSports].sort();
      const topicList = [...selectedTopics].sort();
      const res = await fetch(`${API_BASE}/users/${userId}/preferences`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topics: topicList, sports: sportList }),
      });
      if (!res.ok) {
        throw new Error(`PUT /preferences failed: ${res.status}`);
      }
      localStorage.setItem(STORAGE_USER_SPORTS, JSON.stringify(sportList));
      localStorage.setItem(STORAGE_USER_TOPICS, JSON.stringify(topicList));
      localStorage.setItem(STORAGE_RUMOR_TOLERANCE, rumorTolerance);
      setMode("feed");
      await loadFeed({ bypassCache: true });
      setOnlyMultiSource((prev) => {
        if (!prev) return prev;
        // If multi-source filter would hide everything after refresh, relax it.
        const anyMulti = clusters.some((c) => c.source_count >= 2);
        return anyMulti ? prev : false;
      });
    } catch (e) {
      setAppError(e instanceof Error ? e.message : String(e));
    } finally {
      setPending(false);
    }
  }

  function openStory(storyId: string) {
    setDetail(null);
    setSelectedStoryId(storyId);
    setMode("detail");
  }

  function backToFeed() {
    setAppError(null);
    setDetail(null);
    setSelectedStoryId(null);
    setMode("feed");
  }

  function hideCurrentStory() {
    if (!selectedStoryId) return;
    setHiddenStoryIds((prev) => {
      const next = prev.includes(selectedStoryId)
        ? prev
        : [...prev, selectedStoryId];
      localStorage.setItem(STORAGE_HIDDEN_STORY_IDS, JSON.stringify(next));
      return next;
    });
    backToFeed();
  }

  function clearHiddenStories() {
    localStorage.removeItem(STORAGE_HIDDEN_STORY_IDS);
    setHiddenStoryIds([]);
  }

  function hideFeedStory(storyId: string) {
    setHiddenStoryIds((prev) => {
      const next = prev.includes(storyId) ? prev : [...prev, storyId];
      localStorage.setItem(STORAGE_HIDDEN_STORY_IDS, JSON.stringify(next));
      return next;
    });
    setToast({ visible: true, lastHiddenId: storyId });
  }

  function undoLastHide() {
    const id = toast.lastHiddenId;
    if (!id) {
      setToast({ visible: false });
      return;
    }
    setHiddenStoryIds((prev) => {
      const next = prev.filter((x) => x !== id);
      localStorage.setItem(STORAGE_HIDDEN_STORY_IDS, JSON.stringify(next));
      return next;
    });
    setToast({ visible: false });
  }

  if (bootstrapping) {
    return (
      <div style={shell} data-theme={theme}>
        <div style={container}>
          <p style={{ margin: 0, color: "var(--muted)" }}>Loading session…</p>
          {appError ? (
            <p style={{ color: "var(--danger)", marginTop: 12 }} role="alert">
              {appError}
            </p>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div style={shell} data-theme={theme}>
      <style jsx global>{`
        [data-theme="light"] {
          --bg: #f1f5f9;
          --text: #0f172a;
          --muted: #64748b;
          --cardText: #0f172a;
          --cardMuted: #475569;
          --border: #e2e8f0;
          --card: #ffffff;
          --shadowSm: 0 1px 2px rgba(15, 23, 42, 0.06);
          --shadowLg: 0 8px 20px rgba(15, 23, 42, 0.1);
          --label: #334155;
          --inputBorder: #cbd5e1;
          --inputBg: #ffffff;
          --btnBg: #ffffff;
          --btnBorder: #cbd5e1;
          --btnPrimaryBg: #0f172a;
          --btnPrimaryText: #ffffff;
          --btnPrimaryBorder: #0f172a;
          --pillSportBg: #e0f2fe;
          --pillSportText: #0369a1;
          --pillTopicBg: #f3e8ff;
          --pillTopicText: #6b21a8;
          --pillLeagueBg: #ecfdf5;
          --pillLeagueText: #047857;
          --pillNeutralBg: #f1f5f9;
          --pillNeutralText: #475569;
          --pillOkBg: #dcfce7;
          --pillOkText: #166534;
          --panelBorder: #c7d2fe;
          --panelBg: linear-gradient(180deg, #eef2ff 0%, #ffffff 48%);
          --panelTitle: #3730a3;
          --link: #1d4ed8;
          --danger: #b91c1c;
          --alertBg: #fff7ed;
          --alertBorder: #fed7aa;
          --alertText: #9a3412;
          --errBg: #fef2f2;
          --errBorder: #fecaca;
          --errText: #991b1b;
        }
        [data-theme="dark"] {
          --bg: #0b1220;
          --text: #e6edf7;
          --muted: #b2c0d4;
          --cardText: #eaf2ff;
          --cardMuted: #bfd0e8;
          --border: #2a3a52;
          --card: #172236;
          --shadowSm: 0 1px 2px rgba(0, 0, 0, 0.35);
          --shadowLg: 0 8px 24px rgba(0, 0, 0, 0.45);
          --label: #d2deee;
          --inputBorder: #3c4b64;
          --inputBg: #0f1a2d;
          --btnBg: #1a2a42;
          --btnBorder: #3c4b64;
          --btnPrimaryBg: #5dd4ff;
          --btnPrimaryText: #051425;
          --btnPrimaryBorder: #5dd4ff;
          --pillSportBg: #0d5e8e;
          --pillSportText: #e7f6ff;
          --pillTopicBg: #5a2b84;
          --pillTopicText: #f8edff;
          --pillLeagueBg: #0d5948;
          --pillLeagueText: #e3fff8;
          --pillNeutralBg: #334863;
          --pillNeutralText: #e9f2ff;
          --pillOkBg: #14532d;
          --pillOkText: #bbf7d0;
          --panelBorder: #2d3d56;
          --panelBg: linear-gradient(180deg, #1d2a45 0%, #172236 60%);
          --panelTitle: #d9e4ff;
          --link: #9fcbff;
          --danger: #fca5a5;
          --alertBg: #451a03;
          --alertBorder: #92400e;
          --alertText: #fdba74;
          --errBg: #450a0a;
          --errBorder: #991b1b;
          --errText: #fecaca;
        }
        .story-card-wrap {
          position: relative;
          list-style: none;
          margin-bottom: 12px;
        }
        .story-card {
          display: block;
          width: 100%;
          text-align: left;
          padding: 16px 18px;
          padding-right: 72px;
          border-radius: 10px;
          border: 1px solid var(--border);
          background: var(--card);
          color: var(--text);
          box-shadow: var(--shadowSm);
          cursor: pointer;
          transition:
            border-color 0.15s ease,
            box-shadow 0.15s ease,
            transform 0.15s ease;
        }
        .story-card:hover:not(:disabled) {
          border-color: var(--muted);
          box-shadow: var(--shadowLg);
          transform: translateY(-2px);
        }
        .story-card:disabled {
          opacity: 0.65;
          cursor: not-allowed;
          transform: none;
          box-shadow: var(--shadowSm);
        }
        .story-hide-btn {
          position: absolute;
          top: 10px;
          right: 10px;
          z-index: 2;
          padding: 4px 8px;
          font-size: 0.75rem;
          font-weight: 600;
          border-radius: 6px;
          border: 1px solid var(--btnBorder);
          background: var(--btnBg);
          color: var(--muted);
          cursor: pointer;
        }
        .story-hide-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        .story-pill {
          display: inline-block;
          padding: 4px 10px;
          border-radius: 999px;
          font-size: 0.7rem;
          font-weight: 700;
          letter-spacing: 0.02em;
        }
        .story-pill-sport {
          background: var(--pillSportBg);
          color: var(--pillSportText);
        }
        .story-pill-topic {
          background: var(--pillTopicBg);
          color: var(--pillTopicText);
        }
        .story-pill-league {
          background: var(--pillLeagueBg);
          color: var(--pillLeagueText);
        }
        .sort-seg {
          display: inline-flex;
          border-radius: 8px;
          border: 1px solid var(--border);
          overflow: hidden;
          background: var(--card);
        }
        .sort-seg button {
          border: none;
          background: transparent;
          color: var(--muted);
          padding: 6px 12px;
          font-size: 0.8125rem;
          font-weight: 600;
          cursor: pointer;
        }
        .sort-seg button.active {
          background: var(--btnPrimaryBg);
          color: var(--btnPrimaryText);
        }
        .sort-seg button:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
      `}</style>

      <main style={container}>
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "space-between",
            alignItems: "flex-start",
            gap: 16,
            marginBottom: 8,
          }}
        >
          <div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                marginBottom: 8,
              }}
            >
              <span
                aria-hidden
                style={{
                  width: 30,
                  height: 30,
                  borderRadius: 999,
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: "0.9rem",
                  border: "1px solid var(--border)",
                  background: "var(--card)",
                  boxShadow: "var(--shadowSm)",
                }}
              >
                ⚽🏀
              </span>
              <h1 style={{ ...h1, margin: 0 }}>Sports news</h1>
            </div>
            <p style={sub}>
              All the headlines, none of the noise — pick your sports, then tap
              a story to see who’s talking about it.
            </p>
          </div>
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "flex-end",
              gap: 8,
              minWidth: 160,
            }}
          >
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <button
                type="button"
                aria-pressed={theme === "dark"}
                disabled={busy}
                onClick={() =>
                  setThemePersist(theme === "light" ? "dark" : "light")
                }
                style={{
                  ...btnBase,
                  padding: "6px 12px",
                  fontSize: "0.8125rem",
                  opacity: busy ? 0.6 : 1,
                }}
              >
                {theme === "dark" ? "Light" : "Dark"}
              </button>
              {userId ? (
                <>
                  <button
                    type="button"
                    disabled={runningIngest || feedLoading}
                    onClick={() => void runIngestion()}
                    style={{
                      ...btnBase,
                      padding: "8px 16px",
                      fontSize: "0.875rem",
                      opacity: runningIngest || feedLoading ? 0.65 : 1,
                      cursor:
                        runningIngest || feedLoading ? "not-allowed" : "pointer",
                    }}
                  >
                    {runningIngest ? "Updating…" : "Get latest"}
                  </button>
                  <button
                    type="button"
                    disabled={feedLoading || runningIngest}
                    onClick={() => void loadFeed({ bypassCache: true })}
                    style={{
                      ...btnPrimary,
                      padding: "8px 16px",
                      fontSize: "0.875rem",
                      opacity: feedLoading || runningIngest ? 0.65 : 1,
                      cursor:
                        feedLoading || runningIngest ? "not-allowed" : "pointer",
                    }}
                  >
                    {refreshingFeed ? "Refreshing…" : "Refresh"}
                  </button>
                </>
              ) : null}
            </div>
            {userId ? (
              <>
                {feedLoading && refreshingFeed ? (
                  <span style={{ fontSize: "0.75rem", color: "var(--muted)" }}>
                    Refreshing…
                  </span>
                ) : null}
                {feedLoading && !refreshingFeed && mode === "feed" ? (
                  <span style={{ fontSize: "0.75rem", color: "var(--muted)" }}>
                    Loading feed…
                  </span>
                ) : null}
                {!feedLoading && feedUpdatedAt ? (
                  <span
                    style={{
                      fontSize: "0.75rem",
                      color: "var(--muted)",
                      textAlign: "right",
                    }}
                  >
                    Updated{" "}
                    {formatRelativeTime(feedUpdatedAt.toISOString())}
                    {newSinceLastRefresh > 0 ? (
                      <span
                        style={{
                          marginLeft: 8,
                          fontWeight: 700,
                          color: "var(--pillOkText)",
                        }}
                      >
                        +{newSinceLastRefresh} new
                      </span>
                    ) : null}
                  </span>
                ) : null}
              </>
            ) : null}
          </div>
        </div>

        {mode !== "detail" ? (
          <section style={playerSetupBox} aria-label="Player setup">
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 12,
                marginBottom: 12,
              }}
            >
              <h2
                style={{
                  margin: 0,
                  fontSize: "1rem",
                  fontWeight: 700,
                  color: "var(--text)",
                }}
              >
                Player Setup
              </h2>
              <span
                style={{
                  ...statusPill,
                  background: userId ? "var(--pillOkBg)" : "var(--pillNeutralBg)",
                  color: userId ? "var(--pillOkText)" : "var(--pillNeutralText)",
                }}
              >
                {userId ? "🏟️ Fan Profile Ready" : "Not set up yet"}
              </span>
            </div>
            <p
              style={{
                margin: "0 0 8px",
                fontSize: "0.8125rem",
                color: "var(--muted)",
                lineHeight: 1.5,
              }}
            >
              Set your fan profile — lock in your sports and get a cleaner feed
              every time.
            </p>
            <p
              style={{
                margin: "0 0 14px",
                fontSize: "0.8125rem",
                color: "var(--muted)",
                lineHeight: 1.5,
              }}
            >
              Reset clears your picks and hidden stories so you can start fresh.
            </p>
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: 10,
                alignItems: "center",
              }}
            >
              <button
                type="button"
                disabled={busy || !!userId}
                onClick={() => void createMyProfile()}
                style={{
                  ...btnPrimary,
                  opacity: busy || userId ? 0.65 : 1,
                  cursor: busy || userId ? "not-allowed" : "pointer",
                }}
              >
                Create profile
              </button>
              <button
                type="button"
                disabled={busy || !userId}
                onClick={resetProfile}
                style={{
                  ...btnBase,
                  opacity: busy || !userId ? 0.65 : 1,
                  cursor: busy || !userId ? "not-allowed" : "pointer",
                }}
              >
                Reset profile
              </button>
              {pending && !userId ? (
                <span style={{ fontSize: "0.8125rem", color: "var(--muted)" }}>
                  Creating profile…
                </span>
              ) : null}
            </div>
          </section>
        ) : null}

        {appError ? (
          <div
            role="alert"
            style={{
              padding: "12px 14px",
              borderRadius: 8,
              background: "var(--errBg)",
              border: "1px solid var(--errBorder)",
              color: "var(--errText)",
              fontSize: "0.875rem",
              marginBottom: 20,
            }}
          >
            {appError}
          </div>
        ) : null}

        {mode === "feed" && feedError ? (
          <div
            role="alert"
            style={{
              padding: "14px 16px",
              borderRadius: 10,
              background: "var(--alertBg)",
              border: "1px solid var(--alertBorder)",
              color: "var(--alertText)",
              fontSize: "0.875rem",
              marginBottom: 20,
            }}
          >
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                gap: 12,
                justifyContent: "space-between",
                marginBottom: 6,
              }}
            >
              <span style={{ fontWeight: 600 }}>
                Can’t reach the feed right now.
              </span>
              <button
                type="button"
                disabled={feedLoading}
                onClick={() => void loadFeed({ bypassCache: true })}
                style={{
                  ...btnPrimary,
                  padding: "6px 14px",
                  fontSize: "0.8125rem",
                }}
              >
                {feedLoading ? "Retrying…" : "Retry"}
              </button>
            </div>
            <p
              style={{
                margin: 0,
                fontSize: "0.75rem",
                color: "var(--muted)",
                lineHeight: 1.4,
              }}
            >
              {feedError}
            </p>
          </div>
        ) : null}

        {mode !== "detail" ? (
          <nav style={navRow}>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setAppError(null);
                setMode("preferences");
              }}
              style={{
                ...btnBase,
                opacity: busy ? 0.6 : 1,
                cursor: busy ? "not-allowed" : "pointer",
              }}
            >
              Preferences
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setAppError(null);
                setMode("feed");
                if (userId) {
                  void loadFeed({ bypassCache: true });
                }
              }}
              style={{
                ...btnBase,
                opacity: busy ? 0.6 : 1,
                cursor: busy ? "not-allowed" : "pointer",
              }}
            >
              Feed
            </button>
          </nav>
        ) : null}

        {mode === "preferences" && !userId ? (
          <section>
            <p
              style={{
                margin: "0 0 8px",
                padding: "18px 16px",
                borderRadius: 10,
                border: "1px dashed var(--border)",
                background: "var(--card)",
                color: "var(--cardMuted)",
                fontSize: "0.9375rem",
                lineHeight: 1.5,
              }}
            >
              Create your profile in <strong>Player Setup</strong> above to set
              sports, topics, and save preferences.
            </p>
          </section>
        ) : null}

        {mode === "preferences" && userId ? (
          <section>
            <span style={labelStyle}>Sports (filter story feed)</span>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 10,
                marginBottom: 18,
                marginTop: 6,
              }}
            >
              {SPORT_OPTIONS.map((sport) => (
                <label
                  key={sport}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    fontSize: "0.9375rem",
                    fontWeight: 500,
                    color: "var(--label)",
                    cursor: busy ? "not-allowed" : "pointer",
                  }}
                >
                  <input
                    type="checkbox"
                    checked={selectedSports.includes(sport)}
                    onChange={() => toggleSport(sport)}
                    disabled={busy}
                  />
                  <span style={{ textTransform: "capitalize" }}>{sport}</span>
                </label>
              ))}
            </div>
            <p style={{ fontSize: "0.75rem", color: "var(--muted)", margin: "0 0 18px", lineHeight: 1.45 }}>
              None checked = show all sports. One or more = only those stories.
            </p>
            <span style={labelStyle}>Topics (filter story feed)</span>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 10,
                marginBottom: 18,
                marginTop: 6,
              }}
            >
              {TOPIC_OPTIONS.map((topic) => (
                <label
                  key={topic}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    fontSize: "0.9375rem",
                    fontWeight: 500,
                    color: "var(--label)",
                    cursor: busy ? "not-allowed" : "pointer",
                  }}
                >
                  <input
                    type="checkbox"
                    checked={selectedTopics.includes(topic)}
                    onChange={() => toggleTopic(topic)}
                    disabled={busy}
                  />
                  <span>{topicFanLabel(topic)}</span>
                </label>
              ))}
            </div>
            <p style={{ fontSize: "0.75rem", color: "var(--muted)", margin: "0 0 18px", lineHeight: 1.45 }}>
              None checked = all story types. One or more = only stories tagged with those topics.
            </p>
            <label style={labelStyle}>
              Rumor tolerance
              <select
                style={{ ...inputStyle, cursor: busy ? "not-allowed" : "pointer" }}
                value={rumorTolerance}
                onChange={(e) =>
                  setRumorTolerance(e.target.value as "low" | "balanced" | "high")
                }
                disabled={busy}
              >
                <option value="low">low</option>
                <option value="balanced">balanced</option>
                <option value="high">high</option>
              </select>
            </label>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <button
                type="button"
                disabled={busy}
                onClick={() => void savePreferences()}
                style={{
                  ...btnPrimary,
                  opacity: busy ? 0.65 : 1,
                  cursor: busy ? "not-allowed" : "pointer",
                }}
              >
                Save preferences
              </button>
              {pending && mode === "preferences" && userId ? (
                <span style={{ fontSize: "0.8125rem", color: "var(--muted)" }}>
                  Saving preferences…
                </span>
              ) : null}
            </div>
            <p
              style={{
                fontSize: "0.8125rem",
                color: "var(--muted)",
                marginTop: 8,
                lineHeight: 1.5,
              }}
            >
              Lock in your favorites — we’ll tune your feed to the leagues and
              story types you care about.
            </p>
          </section>
        ) : null}

        {mode === "feed" && !userId ? (
          <section>
            <p
              style={{
                margin: 0,
                padding: "20px 16px",
                borderRadius: 10,
                border: "1px dashed var(--border)",
                background: "var(--card)",
                color: "var(--cardMuted)",
                fontSize: "0.9375rem",
                textAlign: "center",
                lineHeight: 1.5,
              }}
            >
              Create your profile in <strong>Player Setup</strong> above to load
              your personalized story feed.
            </p>
          </section>
        ) : null}

        {mode === "feed" && userId ? (
          <section>
            <div style={panelBox} aria-label="Top coverage">
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 10,
                  flexWrap: "wrap",
                  marginBottom: 10,
                }}
              >
                <h2 style={{ ...sectionTitle, margin: 0 }}>📣 Top Coverage</h2>
                <label
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 8,
                    fontSize: "0.8125rem",
                    color: "var(--muted)",
                    fontWeight: 600,
                  }}
                >
                  Sport:
                  <select
                    value={topCoverageSport}
                    onChange={(e) => {
                      const next = e.target.value as TopCoverageSport;
                      setTopCoverageSport(next);
                      localStorage.setItem(STORAGE_TOP_COVERAGE_SPORT, next);
                    }}
                    disabled={busy}
                    style={{
                      ...inputStyle,
                      width: 120,
                      marginTop: 0,
                      padding: "6px 8px",
                      fontSize: "0.8125rem",
                    }}
                  >
                    <option value="all">All</option>
                    <option value="soccer">Soccer</option>
                    <option value="nba">NBA</option>
                    <option value="f1">F1</option>
                    <option value="other">Other</option>
                  </select>
                </label>
              </div>
              {topCoverageStories.length === 0 ? (
                <p style={{ margin: 0, fontSize: "0.875rem", color: "var(--muted)" }}>
                  No stories yet.
                </p>
              ) : (
                <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                  {topCoverageStories.map((c) => {
                    const clean = cleanHeadline(c.headline);
                    const title = clean ?? "Untitled";
                    const comp = inferCompetitionMark({
                      ...c,
                      headline: clean,
                    }) ?? { mark: "🏟️", code: "Story" };
                    return (
                      <li key={`top-${c.cluster_id}`} style={{ marginBottom: 10 }}>
                        <button
                          type="button"
                          onClick={() => openStory(c.cluster_id)}
                          disabled={busy}
                          aria-label={`Open story: ${title}`}
                          style={{
                            width: "100%",
                            textAlign: "left",
                            padding: "10px 12px",
                            borderRadius: 8,
                            border: "1px solid var(--border)",
                            background: "var(--bg)",
                            color: "var(--text)",
                            cursor: busy ? "not-allowed" : "pointer",
                            fontSize: "0.9375rem",
                          }}
                        >
                          <div style={{ fontWeight: 700, marginBottom: 6, lineHeight: 1.35 }}>
                            {title}
                          </div>
                          <div
                            style={{
                              fontSize: "0.8125rem",
                              color: "var(--muted)",
                              display: "flex",
                              flexWrap: "wrap",
                              gap: "6px 10px",
                              alignItems: "center",
                            }}
                          >
                            <span className="story-pill story-pill-league">
                              {comp.mark} {comp.code}
                            </span>
                            <span>
                              Covered by {c.source_count} outlet
                              {c.source_count === 1 ? "" : "s"} • Updated{" "}
                              {formatRelativeTime(c.latest_published_at)}
                            </span>
                          </div>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>

            <label style={{ ...labelStyle, marginBottom: 8 }}>
              My teams (optional)
              <input
                type="text"
                placeholder="Arsenal, Lakers, Verstappen…"
                value={myTeamsInput}
                onChange={(e) => {
                  const v = e.target.value;
                  setMyTeamsInput(v);
                  localStorage.setItem(STORAGE_MY_TEAMS, v);
                }}
                disabled={busy}
                style={inputStyle}
              />
            </label>

            <div
              style={{
                display: "flex",
                alignItems: "center",
                flexWrap: "wrap",
                gap: 10,
                marginBottom: 14,
              }}
            >
              <span
                style={{
                  fontSize: "0.8125rem",
                  fontWeight: 600,
                  color: "var(--muted)",
                }}
              >
                Sort:
              </span>
              <div className="sort-seg" role="group" aria-label="Feed sort">
                <button
                  type="button"
                  className={feedSort === "recent" ? "active" : ""}
                  disabled={busy}
                  onClick={() => setFeedSortPersist("recent")}
                >
                  Recent
                </button>
                <button
                  type="button"
                  className={feedSort === "coverage" ? "active" : ""}
                  disabled={busy}
                  onClick={() => setFeedSortPersist("coverage")}
                >
                  Coverage
                </button>
              </div>
            </div>

            {hotStories.length > 0 ? (
              <div
                style={{
                  marginBottom: 18,
                  padding: "14px 16px",
                  borderRadius: 10,
                  border: "1px solid var(--border)",
                  background: "var(--card)",
                  boxShadow: "var(--shadowSm)",
                }}
              >
                <h3
                  style={{
                    margin: "0 0 12px",
                    fontSize: "0.9375rem",
                    fontWeight: 700,
                    color: "var(--text)",
                  }}
                >
                  🔥 Hot right now
                </h3>
                <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                  {hotStories.map((c) => {
                    const clean = cleanHeadline(c.headline);
                    const comp = inferCompetitionMark({
                      ...c,
                      headline: clean,
                    }) ?? { mark: "🏟️", code: "Story" };
                    return (
                      <li key={`hot-${c.cluster_id}`} style={{ marginBottom: 10 }}>
                        <button
                          type="button"
                          onClick={() => openStory(c.cluster_id)}
                          disabled={busy}
                          style={{
                            width: "100%",
                            textAlign: "left",
                            padding: "10px 12px",
                            borderRadius: 8,
                            border: "1px solid var(--border)",
                            background: "var(--bg)",
                            color: "var(--text)",
                            cursor: busy ? "not-allowed" : "pointer",
                            fontSize: "0.9375rem",
                          }}
                        >
                          <div
                            style={{
                              fontWeight: 700,
                              marginBottom: 6,
                              lineHeight: 1.35,
                            }}
                          >
                            {clean ?? "Untitled"}
                          </div>
                          <div
                            style={{
                              fontSize: "0.8125rem",
                              color: "var(--muted)",
                              display: "flex",
                              flexWrap: "wrap",
                              gap: "6px 10px",
                              alignItems: "center",
                            }}
                          >
                            <span className="story-pill story-pill-league">
                              {comp.mark} {comp.code}
                            </span>
                            <span>
                              Covered by {c.source_count} outlet
                              {c.source_count === 1 ? "" : "s"} • Updated{" "}
                              {formatRelativeTime(c.latest_published_at)}
                            </span>
                          </div>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ) : null}

            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: 14,
                minHeight: 24,
              }}
            >
              <span
                style={{
                  fontSize: "0.8125rem",
                  fontWeight: 600,
                  color: "var(--label)",
                }}
              >
                Story feed
              </span>
            </div>

            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 10,
                marginBottom: 16,
                padding: "12px 14px",
                background: "var(--card)",
                borderRadius: 10,
                border: "1px solid var(--border)",
              }}
            >
              <label
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  cursor: busy ? "not-allowed" : "pointer",
                  fontSize: "0.875rem",
                  fontWeight: 500,
                  color: "var(--label)",
                }}
              >
                <input
                  type="checkbox"
                  checked={onlyMultiSource}
                  onChange={() => setOnlyMultiSource((v) => !v)}
                  disabled={busy}
                />
                Only show stories getting lots of coverage (2+ outlets)
              </label>
            </div>

            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                flexWrap: "wrap",
                gap: 10,
                marginBottom: 14,
                fontSize: "0.8125rem",
                color: "var(--muted)",
              }}
            >
              <span>Hidden stories: {hiddenStoryIds.length}</span>
              {hiddenStoryIds.length > 0 ? (
                <button
                  type="button"
                  disabled={busy}
                  onClick={clearHiddenStories}
                  style={{
                    ...btnBase,
                    padding: "6px 12px",
                    fontSize: "0.8125rem",
                  }}
                >
                  Clear hidden
                </button>
              ) : null}
            </div>

            {!feedLoading && clusters.length === 0 && !feedError ? (
              <p
                style={{
                  margin: 0,
                  padding: "20px 16px",
                  background: "var(--card)",
                  borderRadius: 10,
                  border: "1px dashed var(--border)",
                  color: "var(--muted)",
                  fontSize: "0.9375rem",
                  textAlign: "center",
                }}
              >
                No stories yet. Tap Get latest to ingest articles.
              </p>
            ) : null}

            {!feedLoading &&
            clusters.length > 0 &&
            feedStories.length === 0 &&
            !feedError ? (
              <p
                style={{
                  margin: "0 0 12px",
                  padding: "20px 16px",
                  background: "var(--card)",
                  borderRadius: 10,
                  border: "1px dashed var(--border)",
                  color: "var(--muted)",
                  fontSize: "0.9375rem",
                  textAlign: "center",
                }}
              >
                No stories match these filters. Try turning off the 2+ outlets
                filter, adjusting preferences
                {hiddenStoryIds.length > 0
                  ? ", or tap Clear hidden above."
                  : "."}
              </p>
            ) : null}

            {feedStories.length > 0 ? (
              <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                {feedStories.map((c) => {
                  const clean = cleanHeadline(c.headline);
                  const hint = feedSummaryHint(c.summary);
                  const comp = inferCompetitionMark({
                    ...c,
                    headline: clean,
                  }) ?? { mark: "🏟️", code: "Story" };
                  return (
                    <li key={c.cluster_id} className="story-card-wrap">
                      <button
                        type="button"
                        className="story-hide-btn"
                        disabled={busy}
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          hideFeedStory(c.cluster_id);
                        }}
                      >
                        Hide
                      </button>
                      <button
                        type="button"
                        className="story-card"
                        disabled={busy}
                        onClick={() => openStory(c.cluster_id)}
                        aria-label={`Open story: ${clean ?? "Untitled"}`}
                      >
                        <div
                          style={{
                            fontSize: "1.25rem",
                            fontWeight: 700,
                            color: "var(--text)",
                            lineHeight: 1.3,
                            marginBottom: 12,
                          }}
                        >
                          {clean ?? "Untitled"}
                        </div>
                        {hint ? (
                          <p
                            style={{
                              margin: "0 0 12px",
                              fontSize: "0.8125rem",
                              color: "var(--muted)",
                              lineHeight: 1.4,
                            }}
                          >
                            {hint}
                          </p>
                        ) : null}
                        <div
                          style={{
                            display: "flex",
                            flexWrap: "wrap",
                            alignItems: "center",
                            gap: "8px 10px",
                            marginBottom: 8,
                          }}
                        >
                          <span
                            className="story-pill story-pill-sport"
                            title="Sport"
                          >
                            {sportFanLabel(c.sport)}
                          </span>
                          <span
                            className="story-pill story-pill-topic"
                            title="Topic"
                          >
                            {topicFanLabel(c.topic)}
                          </span>
                          <span
                            className="story-pill story-pill-league"
                            title="Competition"
                          >
                            {comp.mark} {comp.code}
                          </span>
                        </div>
                        <div
                          style={{
                            fontSize: "0.8125rem",
                            color: "var(--muted)",
                            lineHeight: 1.5,
                          }}
                        >
                          <span
                            style={{ fontWeight: 600, color: "var(--label)" }}
                          >
                            Covered by {c.source_count} outlet
                            {c.source_count === 1 ? "" : "s"}
                          </span>
                          <span
                            style={{ color: "var(--border)", margin: "0 8px" }}
                          >
                            ·
                          </span>
                          <span>
                            Updated{" "}
                            {formatRelativeTime(c.latest_published_at)}
                          </span>
                        </div>
                      </button>
                    </li>
                  );
                })}
              </ul>
            ) : null}
          </section>
        ) : null}

        {mode === "detail" && userId ? (
          <section>
            <p
              style={{
                margin: "0 0 12px",
                fontSize: "0.75rem",
                fontWeight: 700,
                color: "var(--muted)",
                textTransform: "uppercase",
                letterSpacing: "0.08em",
              }}
            >
              Story detail
            </p>
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: 10,
                marginBottom: 20,
              }}
            >
              <button
                type="button"
                disabled={busy}
                onClick={backToFeed}
                style={{
                  ...btnBase,
                  opacity: busy ? 0.65 : 1,
                  cursor: busy ? "not-allowed" : "pointer",
                }}
              >
                ← Back to feed
              </button>
              <button
                type="button"
                disabled={busy || !selectedStoryId}
                onClick={hideCurrentStory}
                style={{
                  ...btnBase,
                  opacity: busy || !selectedStoryId ? 0.65 : 1,
                  cursor:
                    busy || !selectedStoryId ? "not-allowed" : "pointer",
                }}
              >
                Hide story
              </button>
            </div>

            {pending && !detail && !appError ? (
              <p style={{ color: "var(--muted)", fontSize: "0.875rem" }}>
                Loading story…
              </p>
            ) : null}

            {detail ? (
              (() => {
                const detailHeadline = cleanHeadline(detail.headline);
                const detailComp = inferCompetitionMark({
                  ...detail,
                  headline: detailHeadline,
                });
                return (
              <>
                <h2
                  style={{
                    fontSize: "1.125rem",
                    fontWeight: 700,
                    color: "var(--text)",
                    lineHeight: 1.35,
                    margin: "0 0 8px",
                  }}
                >
                  {detailHeadline ?? "Untitled"}
                </h2>
                {detailComp ? (
                  <p style={{ margin: "0 0 10px" }}>
                    <span className="story-pill story-pill-league">
                      {detailComp.mark} {detailComp.code}
                    </span>
                  </p>
                ) : null}
                {detail.llm_updated_at ? (
                  <p
                    style={{
                      margin: "0 0 16px",
                      fontSize: "0.8125rem",
                      color: "var(--muted)",
                    }}
                  >
                    Updated by AI:{" "}
                    {formatRelativeTime(detail.llm_updated_at)}
                    {detail.llm_model_name ? (
                      <span
                        style={{
                          display: "block",
                          marginTop: 4,
                          fontSize: "0.7rem",
                          color: "var(--muted)",
                        }}
                      >
                        {detail.llm_model_name}
                      </span>
                    ) : null}
                  </p>
                ) : null}

                {detail.summary ? (
                  <div
                    style={{
                      marginBottom: 16,
                      padding: "12px 14px",
                      background: "var(--card)",
                      borderRadius: 10,
                      border: "1px solid var(--border)",
                    }}
                  >
                    <h3
                      style={{
                        margin: "0 0 8px",
                        fontSize: "0.8125rem",
                        fontWeight: 700,
                        color: "var(--label)",
                        textTransform: "uppercase",
                        letterSpacing: "0.04em",
                      }}
                    >
                      Quick summary
                    </h3>
                    <p
                      style={{
                        margin: 0,
                        fontSize: "0.9375rem",
                        lineHeight: 1.55,
                        color: "var(--cardText)",
                        whiteSpace: "pre-wrap",
                      }}
                    >
                      {detail.summary}
                    </p>
                  </div>
                ) : null}

                {detail.what_changed ? (
                  <div
                    style={{
                      marginBottom: 16,
                      padding: "12px 14px",
                      background: "var(--card)",
                      borderRadius: 10,
                      border: "1px solid var(--border)",
                    }}
                  >
                    <h3
                      style={{
                        margin: "0 0 8px",
                        fontSize: "0.8125rem",
                        fontWeight: 700,
                        color: "var(--label)",
                        textTransform: "uppercase",
                        letterSpacing: "0.04em",
                      }}
                    >
                      What changed
                    </h3>
                    <p
                      style={{
                        margin: 0,
                        fontSize: "0.875rem",
                        lineHeight: 1.5,
                        color: "var(--cardMuted)",
                        whiteSpace: "pre-wrap",
                      }}
                    >
                      {detail.what_changed}
                    </p>
                  </div>
                ) : null}

                {(() => {
                  const facts = asFactsRecord(detail.facts_json);
                  if (!facts) return null;
                  const comp = strVal(facts.competition);
                  const score = strVal(facts.score);
                  const venue = strVal(facts.venue);
                  const kick = strVal(facts.kickoff_time);
                  const inj = stringList(facts.injuries, 10);
                  const susp = stringList(facts.suspensions, 10);
                  const quotes = managerQuotesList(facts.manager_quotes, 3);
                  const hasAny =
                    comp ||
                    score ||
                    venue ||
                    kick ||
                    inj.length ||
                    susp.length ||
                    quotes.length;
                  if (!hasAny) return null;
                  return (
                    <div
                      style={{
                        marginBottom: 16,
                        padding: "12px 14px",
                        background: "var(--card)",
                        borderRadius: 10,
                        border: "1px solid var(--border)",
                      }}
                    >
                      <h3
                        style={{
                          margin: "0 0 10px",
                          fontSize: "0.8125rem",
                          fontWeight: 700,
                          color: "var(--label)",
                          textTransform: "uppercase",
                          letterSpacing: "0.04em",
                        }}
                      >
                        Key facts
                      </h3>
                      <ul
                        style={{
                          margin: "0 0 10px",
                          paddingLeft: 18,
                          fontSize: "0.875rem",
                          color: "var(--cardText)",
                          lineHeight: 1.5,
                        }}
                      >
                        {comp ? <li>Competition: {comp}</li> : null}
                        {score ? <li>Score: {score}</li> : null}
                        {venue ? <li>Venue: {venue}</li> : null}
                        {kick ? <li>Kickoff: {kick}</li> : null}
                      </ul>
                      {inj.length ? (
                        <div style={{ marginBottom: 8 }}>
                          <span style={metaMuted}>Injuries</span>
                          <ul
                            style={{
                              margin: "6px 0 0",
                              paddingLeft: 18,
                              fontSize: "0.8125rem",
                              color: "var(--cardText)",
                            }}
                          >
                            {inj.map((x) => (
                              <li key={x}>{x}</li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                      {susp.length ? (
                        <div style={{ marginBottom: 8 }}>
                          <span style={metaMuted}>Suspensions</span>
                          <ul
                            style={{
                              margin: "6px 0 0",
                              paddingLeft: 18,
                              fontSize: "0.8125rem",
                              color: "var(--cardText)",
                            }}
                          >
                            {susp.map((x) => (
                              <li key={x}>{x}</li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                      {quotes.length ? (
                        <div>
                          <span style={metaMuted}>Manager quotes</span>
                          <ul
                            style={{
                              margin: "6px 0 0",
                              paddingLeft: 18,
                              fontSize: "0.8125rem",
                              color: "var(--cardMuted)",
                            }}
                          >
                            {quotes.map((q, i) => (
                              <li key={`${q.speaker}-${i}`}>
                                {q.speaker ? (
                                  <strong>{q.speaker}: </strong>
                                ) : null}
                                {q.quote}
                              </li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                    </div>
                  );
                })()}

                {(() => {
                  const ent = asEntitiesRecord(detail.entities_json);
                  if (!ent) return null;
                  const teams = stringList(ent.teams, 5);
                  const players = stringList(ent.players, 5);
                  const managers = stringList(ent.managers, 5);
                  const league = strVal(ent.league);
                  const hasAny =
                    teams.length ||
                    players.length ||
                    managers.length ||
                    league;
                  if (!hasAny) return null;
                  return (
                    <div
                      style={{
                        marginBottom: 16,
                        padding: "12px 14px",
                        background: "var(--card)",
                        borderRadius: 10,
                        border: "1px solid var(--border)",
                      }}
                    >
                      <h3
                        style={{
                          margin: "0 0 10px",
                          fontSize: "0.8125rem",
                          fontWeight: 700,
                          color: "var(--label)",
                          textTransform: "uppercase",
                          letterSpacing: "0.04em",
                        }}
                      >
                        Key names
                      </h3>
                      {league ? (
                        <p
                          style={{
                            margin: "0 0 8px",
                            fontSize: "0.875rem",
                            color: "var(--cardText)",
                          }}
                        >
                          <span style={metaMuted}>League</span>{" "}
                          <span style={{ fontWeight: 600 }}>{league}</span>
                        </p>
                      ) : null}
                      {teams.length ? (
                        <p
                          style={{
                            margin: "0 0 6px",
                            fontSize: "0.8125rem",
                            color: "var(--cardText)",
                          }}
                        >
                          <span style={metaMuted}>Teams</span>{" "}
                          {teams.join(" · ")}
                        </p>
                      ) : null}
                      {players.length ? (
                        <p
                          style={{
                            margin: "0 0 6px",
                            fontSize: "0.8125rem",
                            color: "var(--cardText)",
                          }}
                        >
                          <span style={metaMuted}>Players</span>{" "}
                          {players.join(" · ")}
                        </p>
                      ) : null}
                      {managers.length ? (
                        <p
                          style={{
                            margin: 0,
                            fontSize: "0.8125rem",
                            color: "var(--cardText)",
                          }}
                        >
                          <span style={metaMuted}>Managers</span>{" "}
                          {managers.join(" · ")}
                        </p>
                      ) : null}
                    </div>
                  );
                })()}

                <h3
                  style={{
                    margin: "0 0 10px",
                    fontSize: "0.8125rem",
                    fontWeight: 700,
                    color: "var(--label)",
                    textTransform: "uppercase",
                    letterSpacing: "0.04em",
                  }}
                >
                  Sources
                </h3>
                <ul style={{ paddingLeft: 18, margin: 0 }}>
                  {detail.articles.map((a) => (
                    <li key={a.id} style={{ marginBottom: 12 }}>
                      <a
                        href={a.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ color: "var(--link)", fontSize: "0.9375rem" }}
                      >
                        {a.title}
                      </a>
                    </li>
                  ))}
                </ul>
              </>
                );
              })()
            ) : null}
          </section>
        ) : null}

        {toast.visible ? (
          <div
            role="status"
            style={{
              position: "fixed",
              left: "50%",
              bottom: 24,
              transform: "translateX(-50%)",
              zIndex: 1000,
              maxWidth: "min(90vw, 400px)",
              padding: "12px 16px",
              borderRadius: 10,
              border: "1px solid var(--border)",
              background: "var(--card)",
              color: "var(--text)",
              boxShadow: "var(--shadowLg)",
              display: "flex",
              alignItems: "center",
              flexWrap: "wrap",
              gap: 8,
              fontSize: "0.875rem",
            }}
          >
            <span>Story hidden</span>
            <span style={{ color: "var(--muted)" }} aria-hidden>
              •
            </span>
            <button
              type="button"
              onClick={undoLastHide}
              style={{
                background: "none",
                border: "none",
                padding: 0,
                color: "var(--link)",
                fontWeight: 700,
                cursor: "pointer",
                textDecoration: "underline",
                fontSize: "inherit",
              }}
            >
              Undo
            </button>
          </div>
        ) : null}
      </main>
    </div>
  );
}
