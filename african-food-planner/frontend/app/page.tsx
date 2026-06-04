"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { displayIngredientName, normalizeIngredientName } from "../lib/normalize";

const USER_ID_KEY = "user_id";
const WEEK_START_KEY = "week_start_date";
const PANTRY_UNITS = ["g", "kg", "ml", "l", "tsp", "tbsp", "cup", "piece"] as const;
const MEAL_TYPES = ["breakfast", "lunch", "dinner"] as const;
const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MODES = [
  "pantry",
  "recipes",
  "meal_plan",
  "shopping",
  "cook_now",
  "reminders",
] as const;

const MODE_LABELS: Record<Mode, string> = {
  pantry: "Pantry",
  recipes: "Recipes",
  meal_plan: "Meal Plan",
  shopping: "Shopping",
  cook_now: "Cook Now",
  reminders: "Reminders",
};

const theme = {
  bg: "var(--color-bg, #fff)",
  text: "var(--color-text, #111)",
  border: "var(--color-border, #ddd)",
  borderLight: "var(--color-border-light, #eee)",
  muted: "var(--color-muted, #666)",
  subtle: "var(--color-subtle, #555)",
  error: "var(--color-error, #b00020)",
  success: "var(--color-success, #0a6b0a)",
  surfaceActive: "var(--color-surface-active, #eee)",
  surface: "var(--color-surface, #fff)",
  chipBg: "var(--color-chip-bg, #f0f0f0)",
};

type PantryUnit = (typeof PANTRY_UNITS)[number];
type MealType = (typeof MEAL_TYPES)[number];
type Mode = (typeof MODES)[number];

const FETCH_NO_CACHE: RequestInit = { cache: "no-store" };

const apiBase = () => process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";

type RecipeResponse = {
  id: string;
  name: string;
  servings_base: number;
  tags: string[];
  created_at: string;
};

type RecipeIngredientResponse = {
  id: string;
  ingredient_name: string;
  quantity: number;
  unit: string;
  optional: boolean;
  category: string | null;
};

type RecipeDetailResponse = {
  recipe: RecipeResponse;
  ingredients: RecipeIngredientResponse[];
  steps?: string[] | null;
};

type RecipeScaleItem = {
  ingredient_name: string;
  unit: string;
  qty_base: number;
  qty_scaled: number;
  optional: boolean;
  category: string | null;
};

type RecipeScaleResponse = {
  recipe_id: string;
  recipe_name: string;
  servings_base: number;
  servings_target: number;
  items: RecipeScaleItem[];
};

type PantryItem = {
  id: string;
  user_id: string;
  ingredient_name: string;
  quantity: number;
  unit: string;
  expires_at: string | null;
};

type PantryEvent = {
  id: string;
  user_id: string;
  ingredient_name: string;
  delta: number;
  unit: string;
  reason: string;
  created_at: string;
};

type MealPlanItem = {
  id: string;
  day: number;
  meal_type: string;
  recipe_id: string;
  servings: number;
};

type MealPlanResponse = {
  id: string;
  user_id: string;
  week_start_date: string;
  items: MealPlanItem[];
};

type PlanItemDraft = {
  day: number;
  meal_type: MealType;
  recipe_id: string;
  servings: number;
};

type CookNowRecipe = {
  recipe_id: string;
  name: string;
  missing: string[];
  substitutions?: Record<string, string[]>;
};

type CookNowResponse = {
  can_cook: CookNowRecipe[];
  almost: CookNowRecipe[];
};

type RecipeNutrition = {
  calories_per_serving: number | null;
  notes: string;
};

type SubstituteEntry = {
  substitute: string;
  note: string;
  category?: string | null;
};

type ShoppingLine = {
  id: string;
  ingredient_name: string;
  unit: string;
  needed_qty: number;
  in_pantry_qty: number;
  to_buy_qty: number;
  checked: boolean;
};

type Reminder = {
  id: string;
  user_id: string;
  type: string;
  title: string;
  body: string;
  due_at: string | null;
  created_at: string;
  is_read: boolean;
};

type Notification = {
  id: string;
  user_id: string;
  type: string;
  title: string;
  body: string;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
  read_at: string | null;
};

type NewRecipeIngredient = {
  ingredient_name: string;
  quantity: string;
  unit: PantryUnit;
};

function planItemsToApiPayload(items: PlanItemDraft[]) {
  return items.map((item) => ({
    day: item.day,
    meal_type: item.meal_type,
    recipe_id: item.recipe_id,
    servings: item.servings,
  }));
}

function mealPlanItemsToDrafts(items: MealPlanItem[]): PlanItemDraft[] {
  return items.map((item) => ({
    day: item.day,
    meal_type: item.meal_type as MealType,
    recipe_id: item.recipe_id,
    servings: item.servings,
  }));
}

function quickStep(unit: string): number {
  if (unit === "g" || unit === "ml") return 100;
  if (unit === "kg" || unit === "l") return 0.1;
  return 1;
}

function consumedStep(unit: string): number {
  if (unit === "g" || unit === "ml") return 100;
  if (unit === "kg" || unit === "l") return 0.1;
  return 1;
}

function formatTimeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function formatExpiryLabel(expiresAt: string | null): string | null {
  if (!expiresAt) return null;
  const end = new Date(expiresAt).getTime();
  if (Number.isNaN(end)) return null;
  const days = Math.ceil((end - Date.now()) / (24 * 60 * 60 * 1000));
  if (days < 0) return "expired";
  if (days === 0) return "expires today";
  return `expires in ${days}d`;
}

function dateInputToExpiresAt(dateStr: string): string | null {
  const trimmed = dateStr.trim();
  if (!trimmed) return null;
  return `${trimmed}T23:59:59.000Z`;
}

function expiresAtToDateInput(expiresAt: string | null): string {
  if (!expiresAt) return "";
  const d = new Date(expiresAt);
  if (Number.isNaN(d.getTime())) return "";
  return d.toISOString().slice(0, 10);
}

function formatEventLine(event: PantryEvent): string {
  const sign = event.delta >= 0 ? "+" : "";
  const name = displayIngredientName(event.ingredient_name);
  return `${sign}${event.delta} ${event.unit} ${name} — ${event.reason} — ${formatTimeAgo(event.created_at)}`;
}

async function parseApiError(res: Response, fallback: string): Promise<string> {
  const body = await res.json().catch(() => ({}));
  const detail = (body as { detail?: string | { msg: string }[] }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
  return fallback;
}

export default function HomePage() {
  const [mode, setMode] = useState<Mode>("pantry");
  const [userId, setUserId] = useState<string | null>(null);
  const [recipes, setRecipes] = useState<RecipeResponse[]>([]);
  const [pantry, setPantry] = useState<PantryItem[]>([]);
  const [events, setEvents] = useState<PantryEvent[]>([]);
  const [editQty, setEditQty] = useState<Record<string, string>>({});
  const [pantryVersion, setPantryVersion] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [addName, setAddName] = useState("");
  const [addQty, setAddQty] = useState("");
  const [addUnit, setAddUnit] = useState<PantryUnit>("g");
  const [addExpiresAt, setAddExpiresAt] = useState("");
  const [editExpiresAt, setEditExpiresAt] = useState<Record<string, string>>({});

  const [weekStartDate, setWeekStartDate] = useState("");
  const [mealPlan, setMealPlan] = useState<MealPlanResponse | null>(null);
  const [planItems, setPlanItems] = useState<PlanItemDraft[]>([]);
  const [addPlanDay, setAddPlanDay] = useState(0);
  const [addPlanMealType, setAddPlanMealType] = useState<MealType>("dinner");
  const [addPlanRecipeId, setAddPlanRecipeId] = useState("");
  const [addPlanServings, setAddPlanServings] = useState("4");
  const [generateServings, setGenerateServings] = useState("2");
  const [generateMaxMissing, setGenerateMaxMissing] = useState("4");
  const [shoppingLines, setShoppingLines] = useState<ShoppingLine[]>([]);
  const [shoppingSubstitutions, setShoppingSubstitutions] = useState<
    Record<string, string[]>
  >({});
  const [cookNow, setCookNow] = useState<CookNowResponse | null>(null);

  const [selectedRecipeId, setSelectedRecipeId] = useState("");
  const [recipeDetail, setRecipeDetail] = useState<RecipeDetailResponse | null>(null);
  const [scaleServings, setScaleServings] = useState("4");
  const [scaledRecipe, setScaledRecipe] = useState<RecipeScaleResponse | null>(null);
  const [recipeNutrition, setRecipeNutrition] = useState<RecipeNutrition | null>(null);
  const [nutritionServings, setNutritionServings] = useState("2");
  const [newRecipeName, setNewRecipeName] = useState("");
  const [newRecipeServingsBase, setNewRecipeServingsBase] = useState("4");
  const [newRecipeTags, setNewRecipeTags] = useState("");
  const [newRecipeIngredients, setNewRecipeIngredients] = useState<NewRecipeIngredient[]>(
    [{ ingredient_name: "", quantity: "", unit: "g" }]
  );

  const [reminders, setReminders] = useState<Reminder[]>([]);

  useEffect(() => {
    setUserId(localStorage.getItem(USER_ID_KEY));
    setWeekStartDate(localStorage.getItem(WEEK_START_KEY) ?? "");
  }, []);

  const syncPantryEdits = useCallback((items: PantryItem[]) => {
    const qty: Record<string, string> = {};
    const exp: Record<string, string> = {};
    for (const item of items) {
      qty[item.id] = String(item.quantity);
      exp[item.id] = expiresAtToDateInput(item.expires_at);
    }
    setEditQty(qty);
    setEditExpiresAt(exp);
  }, []);

  const fetchRecipes = useCallback(async () => {
    const res = await fetch(`${apiBase()}/recipes`, FETCH_NO_CACHE);
    if (!res.ok) throw new Error("Failed to load recipes");
    return res.json() as Promise<RecipeResponse[]>;
  }, []);

  const fetchRecipeDetail = useCallback(async (recipeId: string) => {
    const res = await fetch(`${apiBase()}/recipes/${recipeId}`, FETCH_NO_CACHE);
    if (!res.ok) throw new Error(await parseApiError(res, "Failed to load recipe"));
    return res.json() as Promise<RecipeDetailResponse>;
  }, []);

  const fetchRecipeScale = useCallback(async (recipeId: string, servings: number) => {
    const res = await fetch(
      `${apiBase()}/recipes/${recipeId}/scale?servings=${encodeURIComponent(String(servings))}`,
      FETCH_NO_CACHE
    );
    if (!res.ok) throw new Error(await parseApiError(res, "Failed to scale recipe"));
    return res.json() as Promise<RecipeScaleResponse>;
  }, []);

  const fetchPantryItems = useCallback(async (uid: string) => {
    const res = await fetch(
      `${apiBase()}/pantry/items?user_id=${encodeURIComponent(uid)}`,
      FETCH_NO_CACHE
    );
    if (!res.ok) throw new Error("Failed to load pantry");
    return ((await res.json()) as { items: PantryItem[] }).items;
  }, []);

  const fetchPantryEvents = useCallback(async (uid: string) => {
    const res = await fetch(
      `${apiBase()}/pantry/events?user_id=${encodeURIComponent(uid)}&limit=25`,
      FETCH_NO_CACHE
    );
    if (!res.ok) throw new Error("Failed to load events");
    return ((await res.json()) as { items: PantryEvent[] }).items;
  }, []);

  const fetchNotifications = useCallback(async (uid: string) => {
    const res = await fetch(
      `${apiBase()}/notifications?user_id=${encodeURIComponent(uid)}`,
      FETCH_NO_CACHE
    );
    if (!res.ok) {
      throw new Error(await parseApiError(res, "Failed to load notifications"));
    }
    const data = (await res.json()) as { items: Notification[] };
    return data.items;
  }, []);

  const fetchReminders = useCallback(async (uid: string) => {
    const res = await fetch(
      `${apiBase()}/reminders?user_id=${encodeURIComponent(uid)}`,
      FETCH_NO_CACHE
    );
    if (!res.ok) throw new Error(await parseApiError(res, "Failed to load reminders"));
    return res.json() as Promise<Reminder[]>;
  }, []);

  const afterPantryChange = useCallback(
    async (uid: string) => {
      const [items, eventList] = await Promise.all([
        fetchPantryItems(uid),
        fetchPantryEvents(uid),
      ]);
      setPantry(items);
      syncPantryEdits(items);
      setEvents(eventList);
      setPantryVersion((v) => v + 1);
    },
    [fetchPantryItems, fetchPantryEvents, syncPantryEdits]
  );

  const applyMealPlan = useCallback((plan: MealPlanResponse) => {
    setMealPlan(plan);
    setPlanItems(mealPlanItemsToDrafts(plan.items));
  }, []);

  const loadShoppingSubstitutions = useCallback(async (lines: ShoppingLine[]) => {
    if (lines.length === 0) {
      setShoppingSubstitutions({});
      return;
    }
    const names = Array.from(new Set(lines.map((l) => l.ingredient_name)));
    const res = await fetch(`${apiBase()}/substitutions/missing`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ missing: names }),
    });
    if (!res.ok) {
      setShoppingSubstitutions({});
      return;
    }
    const data = (await res.json()) as {
      substitutes: Record<string, SubstituteEntry[]>;
    };
    const mapped: Record<string, string[]> = {};
    for (const [ing, entries] of Object.entries(data.substitutes)) {
      const subs = entries.map((e) => e.substitute).filter(Boolean);
      if (subs.length) mapped[ing] = subs;
    }
    setShoppingSubstitutions(mapped);
  }, []);

  const loadShoppingListForPlan = useCallback(
    async (planId: string) => {
      const res = await fetch(
        `${apiBase()}/meal_plans/${planId}/shopping_list`,
        FETCH_NO_CACHE
      );
      if (res.status === 404) {
        setShoppingLines([]);
        setShoppingSubstitutions({});
        return;
      }
      if (!res.ok) {
        throw new Error(await parseApiError(res, "Failed to load shopping list"));
      }
      const data = (await res.json()) as { items: ShoppingLine[] };
      setShoppingLines(data.items);
      await loadShoppingSubstitutions(data.items);
    },
    [loadShoppingSubstitutions]
  );

  const recipeNameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const r of recipes) map.set(r.id, r.name);
    return map;
  }, [recipes]);

  const planItemsByDay = useMemo(() => {
    const grouped: Record<number, PlanItemDraft[]> = {};
    for (let day = 0; day < 7; day += 1) grouped[day] = [];
    for (const item of planItems) {
      grouped[item.day].push(item);
    }
    for (const day of Object.keys(grouped)) {
      grouped[Number(day)].sort((a, b) =>
        MEAL_TYPES.indexOf(a.meal_type) - MEAL_TYPES.indexOf(b.meal_type)
      );
    }
    return grouped;
  }, [planItems]);

  const refreshAll = useCallback(
    async (uid: string | null) => {
      setLoading(true);
      setError(null);
      try {
        setRecipes(await fetchRecipes());
        if (uid) {
          await afterPantryChange(uid);
          const [reminderList, notifList] = await Promise.all([
            fetchReminders(uid),
            fetchNotifications(uid),
          ]);
          setReminders(reminderList);
          setNotifications(notifList);
        } else {
          setPantry([]);
          setEvents([]);
          setEditQty({});
          setEditExpiresAt({});
          setReminders([]);
          setNotifications([]);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Something went wrong");
      } finally {
        setLoading(false);
      }
    },
    [fetchRecipes, afterPantryChange, fetchReminders, fetchNotifications]
  );

  useEffect(() => {
    refreshAll(userId);
  }, [userId, refreshAll]);

  const runPantryMutation = useCallback(
    async (mutation: () => Promise<void>) => {
      if (!userId) {
        setError("Create a profile first");
        return;
      }
      setLoading(true);
      setError(null);
      try {
        await mutation();
        await afterPantryChange(userId);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Something went wrong");
      } finally {
        setLoading(false);
      }
    },
    [userId, afterPantryChange]
  );

  const recipeOptions = useMemo(
    () => [...recipes].sort((a, b) => a.name.localeCompare(b.name)),
    [recipes]
  );

  const notificationsSorted = useMemo(() => {
    const copy = [...notifications];
    copy.sort((a, b) => {
      const aUnread = a.read_at == null ? 0 : 1;
      const bUnread = b.read_at == null ? 0 : 1;
      if (aUnread !== bUnread) return aUnread - bUnread;
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });
    return copy;
  }, [notifications]);

  const remindersSorted = useMemo(() => {
    const copy = [...reminders];
    copy.sort((a, b) => {
      if (a.is_read !== b.is_read) return a.is_read ? 1 : -1;
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });
    return copy;
  }, [reminders]);

  async function createProfile() {
    setError(null);
    setLoading(true);
    try {
      const res = await fetch(`${apiBase()}/users`, { method: "POST" });
      if (!res.ok) throw new Error("Failed to create profile");
      const data = (await res.json()) as { id: string };
      localStorage.setItem(USER_ID_KEY, data.id);
      setUserId(data.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  async function loadWeek() {
    if (!userId) {
      setError("Create a profile first");
      return;
    }
    if (!weekStartDate) {
      setError("Pick a week start date");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      localStorage.setItem(WEEK_START_KEY, weekStartDate);
      const res = await fetch(
        `${apiBase()}/meal_plans/current?user_id=${encodeURIComponent(userId)}&week_start_date=${encodeURIComponent(weekStartDate)}`,
        FETCH_NO_CACHE
      );
      if (res.status === 404) {
        setMealPlan(null);
        setPlanItems([]);
        setShoppingLines([]);
        setShoppingSubstitutions({});
        return;
      }
      if (!res.ok) {
        throw new Error(await parseApiError(res, "Failed to load meal plan"));
      }
      const plan = (await res.json()) as MealPlanResponse;
      applyMealPlan(plan);
      await loadShoppingListForPlan(plan.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  function addToPlanList() {
    if (!addPlanRecipeId) {
      setError("Select a recipe");
      return;
    }
    const servings = parseFloat(addPlanServings);
    if (Number.isNaN(servings) || servings <= 0) {
      setError("Servings must be a positive number");
      return;
    }
    setError(null);
    const next: PlanItemDraft = {
      day: addPlanDay,
      meal_type: addPlanMealType,
      recipe_id: addPlanRecipeId,
      servings,
    };
    setPlanItems((prev) => {
      const rest = prev.filter(
        (item) => !(item.day === next.day && item.meal_type === next.meal_type)
      );
      return [...rest, next];
    });
  }

  function removeFromPlanList(day: number, mealType: MealType) {
    setPlanItems((prev) =>
      prev.filter((item) => !(item.day === day && item.meal_type === mealType))
    );
  }

  async function savePlan() {
    if (!userId) {
      setError("Create a profile first");
      return;
    }
    if (!weekStartDate) {
      setError("Pick a week start date");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      localStorage.setItem(WEEK_START_KEY, weekStartDate);
      const payload = {
        week_start_date: weekStartDate,
        items: planItemsToApiPayload(planItems),
      };
      const res = mealPlan
        ? await fetch(`${apiBase()}/meal_plans/${mealPlan.id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          })
        : await fetch(`${apiBase()}/meal_plans?user_id=${encodeURIComponent(userId)}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
      if (!res.ok) {
        throw new Error(await parseApiError(res, "Failed to save meal plan"));
      }
      applyMealPlan((await res.json()) as MealPlanResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  async function autoGenerateWeek() {
    if (!userId) {
      setError("Create a profile first");
      return;
    }
    if (!weekStartDate) {
      setError("Pick a week start date");
      return;
    }
    const servings = parseFloat(generateServings);
    const maxMissing = parseInt(generateMaxMissing, 10);
    if (Number.isNaN(servings) || servings <= 0) {
      setError("Servings must be a positive number");
      return;
    }
    if (Number.isNaN(maxMissing) || maxMissing < 0) {
      setError("Max missing must be 0 or more");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      localStorage.setItem(WEEK_START_KEY, weekStartDate);
      const res = await fetch(
        `${apiBase()}/meal_plans/generate?user_id=${encodeURIComponent(userId)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            week_start_date: weekStartDate,
            meal_type: "dinner",
            servings,
            max_missing_ingredients: maxMissing,
            max_repeats_per_week: 1,
          }),
        }
      );
      if (!res.ok) {
        throw new Error(await parseApiError(res, "Failed to auto-generate meal plan"));
      }
      const plan = (await res.json()) as MealPlanResponse;
      applyMealPlan(plan);
      setShoppingLines([]);
      setShoppingSubstitutions({});
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  async function loadCookNow() {
    if (!userId) {
      setError("Create a profile first");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${apiBase()}/cook_now?user_id=${encodeURIComponent(userId)}&max_missing=3`,
        FETCH_NO_CACHE
      );
      if (!res.ok) {
        throw new Error(await parseApiError(res, "Failed to load recommendations"));
      }
      setCookNow((await res.json()) as CookNowResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  function openRecipeFromCookNow(recipeId: string) {
    setMode("recipes");
    handleSelectRecipe(recipeId);
  }

  async function generateShoppingList() {
    if (!mealPlan) {
      setError("Create or load a meal plan first");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${apiBase()}/meal_plans/${mealPlan.id}/shopping_list/generate`,
        { method: "POST" }
      );
      if (!res.ok) {
        throw new Error(await parseApiError(res, "Failed to generate shopping list"));
      }
      const data = (await res.json()) as { items: ShoppingLine[] };
      setShoppingLines(data.items);
      await loadShoppingSubstitutions(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  async function toggleShoppingChecked(line: ShoppingLine) {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase()}/shopping_list_items/${line.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ checked: !line.checked }),
      });
      if (!res.ok) {
        throw new Error(await parseApiError(res, "Failed to update shopping item"));
      }
      const updated = (await res.json()) as ShoppingLine;
      setShoppingLines((prev) =>
        prev.map((row) => (row.id === updated.id ? updated : row))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  async function markNotificationRead(notificationId: string) {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${apiBase()}/notifications/${notificationId}/read`,
        { method: "POST" }
      );
      if (!res.ok) {
        throw new Error(await parseApiError(res, "Failed to mark notification read"));
      }
      const updated = (await res.json()) as Notification;
      setNotifications((prev) =>
        prev.map((n) => (n.id === updated.id ? updated : n))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  async function addToPantry(e: FormEvent) {
    e.preventDefault();
    const qty = parseFloat(addQty);
    const ingredient_name = normalizeIngredientName(addName);
    if (!ingredient_name || Number.isNaN(qty) || qty <= 0) {
      setError("Enter a valid ingredient and positive quantity");
      return;
    }
    await runPantryMutation(async () => {
      const res = await fetch(`${apiBase()}/pantry/items`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          ingredient_name,
          quantity: qty,
          unit: addUnit,
          expires_at: dateInputToExpiresAt(addExpiresAt),
        }),
      });
      if (!res.ok) throw new Error(await parseApiError(res, "Failed to add to pantry"));
      setAddName("");
      setAddQty("");
      setAddExpiresAt("");
    });
  }

  async function savePantryItem(item: PantryItem) {
    const qty = parseFloat(editQty[item.id] ?? "");
    if (Number.isNaN(qty) || qty < 0) {
      setError("Quantity must be a number >= 0");
      return;
    }
    await runPantryMutation(async () => {
      const res = await fetch(`${apiBase()}/pantry/items/${item.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          quantity: qty,
          expires_at: dateInputToExpiresAt(editExpiresAt[item.id] ?? ""),
        }),
      });
      if (!res.ok) throw new Error(await parseApiError(res, "Failed to update pantry item"));
    });
  }

  async function postPantryEvent(item: PantryItem, delta: number, reason: "added" | "consumed") {
    await runPantryMutation(async () => {
      const res = await fetch(`${apiBase()}/pantry/events`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          ingredient_name: displayIngredientName(item.ingredient_name),
          delta,
          unit: item.unit,
          reason,
        }),
      });
      if (!res.ok) throw new Error(await parseApiError(res, "Failed to update pantry"));
    });
  }

  async function handleSelectRecipe(recipeId: string) {
    setSelectedRecipeId(recipeId);
    setScaledRecipe(null);
    setRecipeNutrition(null);
    if (!recipeId) {
      setRecipeDetail(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const detail = await fetchRecipeDetail(recipeId);
      setRecipeDetail(detail);
      setScaleServings(String(detail.recipe.servings_base));
      setNutritionServings(String(detail.recipe.servings_base));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  async function handleLoadNutrition() {
    if (!selectedRecipeId) return;
    const servings = parseFloat(nutritionServings);
    if (Number.isNaN(servings) || servings <= 0) {
      setError("Nutrition servings must be a positive number");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${apiBase()}/recipes/${selectedRecipeId}/nutrition?servings=${encodeURIComponent(String(servings))}`,
        FETCH_NO_CACHE
      );
      if (!res.ok) {
        throw new Error(await parseApiError(res, "Failed to load nutrition"));
      }
      setRecipeNutrition((await res.json()) as RecipeNutrition);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  async function handleScaleRecipe() {
    if (!selectedRecipeId) return;
    const servings = parseFloat(scaleServings);
    if (Number.isNaN(servings) || servings <= 0) {
      setError("Scale servings must be a positive number");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setScaledRecipe(await fetchRecipeScale(selectedRecipeId, servings));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateRecipe(e: FormEvent) {
    e.preventDefault();
    const name = newRecipeName.trim();
    const servings_base = parseFloat(newRecipeServingsBase);
    if (!name) {
      setError("Recipe name is required");
      return;
    }
    if (Number.isNaN(servings_base) || servings_base <= 0) {
      setError("servings_base must be positive");
      return;
    }

    const ingredients = newRecipeIngredients
      .map((r) => ({
        ingredient_name: normalizeIngredientName(r.ingredient_name),
        quantity: parseFloat(r.quantity),
        unit: r.unit,
      }))
      .filter((r) => r.ingredient_name);

    if (ingredients.length === 0) {
      setError("Add at least one ingredient");
      return;
    }
    for (const ing of ingredients) {
      if (Number.isNaN(ing.quantity) || ing.quantity <= 0) {
        setError("Ingredient quantity must be positive");
        return;
      }
    }

    const tags = newRecipeTags
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);

    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase()}/recipes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, servings_base, tags, ingredients }),
      });
      if (!res.ok) throw new Error(await parseApiError(res, "Failed to create recipe"));
      const created = (await res.json()) as RecipeDetailResponse;
      setRecipes(await fetchRecipes());
      await handleSelectRecipe(created.recipe.id);
      setNewRecipeName("");
      setNewRecipeServingsBase("4");
      setNewRecipeTags("");
      setNewRecipeIngredients([{ ingredient_name: "", quantity: "", unit: "g" }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  async function markRead(reminderId: string) {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase()}/reminders/${reminderId}/read`, {
        method: "POST",
      });
      if (!res.ok) throw new Error(await parseApiError(res, "Failed to mark read"));
      setReminders((await res.json()) as Reminder[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  const sectionStyle = {
    marginTop: 24,
    paddingTop: 16,
    borderTop: `1px solid ${theme.border}`,
  };
  const inputStyle = {
    display: "block",
    marginBottom: 8,
    padding: 6,
    width: "100%",
    maxWidth: 320,
  };
  const rowStyle = {
    marginBottom: 16,
    paddingBottom: 16,
    borderBottom: `1px solid ${theme.borderLight}`,
  };
  const btnStyle = { padding: "4px 10px", marginRight: 6, cursor: "pointer" };
  const cardStyle = {
    marginTop: 16,
    marginBottom: 16,
    padding: 14,
    border: `1px solid ${theme.borderLight}`,
    borderRadius: 8,
    background: theme.surface,
  };

  const navBtnStyle = (active: boolean) => ({
    padding: "6px 10px",
    marginRight: 8,
    marginBottom: 8,
    cursor: "pointer",
    border: `1px solid ${theme.border}`,
    background: active ? theme.surfaceActive : theme.surface,
  });
  const chipStyle = {
    display: "inline-block",
    marginRight: 6,
    marginTop: 4,
    padding: "2px 8px",
    fontSize: 12,
    borderRadius: 4,
    background: theme.chipBg,
    color: theme.subtle,
  };

  const mainStyle = {
    maxWidth: 960,
    margin: "0 auto",
    padding: 24,
    background: theme.bg,
    color: theme.text,
    ["--color-bg" as string]: "#fff",
    ["--color-text" as string]: "#111",
    ["--color-border" as string]: "#ddd",
    ["--color-border-light" as string]: "#eee",
    ["--color-muted" as string]: "#666",
    ["--color-subtle" as string]: "#555",
    ["--color-error" as string]: "#b00020",
    ["--color-success" as string]: "#0a6b0a",
    ["--color-surface-active" as string]: "#eee",
    ["--color-surface" as string]: "#fff",
    ["--color-chip-bg" as string]: "#f0f0f0",
  };

  return (
    <main style={mainStyle}>
      <h1 style={{ marginTop: 0 }}>African Food Planner</h1>

      <div style={{ marginBottom: 12 }}>
        {MODES.map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            style={navBtnStyle(mode === m)}
          >
            {MODE_LABELS[m]}
          </button>
        ))}
      </div>

      <button
        type="button"
        onClick={createProfile}
        disabled={loading}
        style={{ padding: "8px 16px", cursor: "pointer" }}
      >
        Create Profile
      </button>
      {userId && (
        <p style={{ color: theme.subtle, fontSize: 14 }}>
          Profile: <code>{userId}</code>
        </p>
      )}

      {error && <p style={{ color: theme.error }}>{error}</p>}
      {loading && <p style={{ color: theme.muted }}>Loading...</p>}

      {userId && (
        <section style={cardStyle}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: 8,
              marginBottom: 10,
            }}
          >
            <h2 style={{ margin: 0, fontSize: 18 }}>Inbox</h2>
            <button
              type="button"
              onClick={async () => {
                if (!userId) return;
                setLoading(true);
                setError(null);
                try {
                  setNotifications(await fetchNotifications(userId));
                } catch (err) {
                  setError(err instanceof Error ? err.message : "Something went wrong");
                } finally {
                  setLoading(false);
                }
              }}
              disabled={loading}
              style={{ padding: "4px 10px", cursor: "pointer", fontSize: 13 }}
            >
              Refresh
            </button>
          </div>
          {notificationsSorted.length === 0 && !loading && (
            <p style={{ margin: 0, color: theme.muted, fontSize: 14 }}>No new alerts</p>
          )}
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {notificationsSorted.map((n) => {
              const unread = n.read_at == null;
              return (
                <li
                  key={n.id}
                  style={{
                    marginBottom: 10,
                    paddingBottom: 10,
                    borderBottom: `1px solid ${theme.borderLight}`,
                    opacity: unread ? 1 : 0.7,
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      gap: 8,
                      alignItems: "flex-start",
                    }}
                  >
                    <div>
                      <strong style={{ fontSize: 14 }}>{n.title}</strong>
                      {unread && (
                        <span
                          style={{
                            marginLeft: 8,
                            fontSize: 11,
                            color: theme.success,
                            fontWeight: 600,
                          }}
                        >
                          new
                        </span>
                      )}
                      <p style={{ margin: "4px 0 0", fontSize: 13, color: theme.subtle }}>
                        {n.body}
                      </p>
                      <p style={{ margin: "4px 0 0", fontSize: 12, color: theme.muted }}>
                        {formatTimeAgo(n.created_at)}
                      </p>
                    </div>
                    {unread && (
                      <button
                        type="button"
                        onClick={() => markNotificationRead(n.id)}
                        disabled={loading}
                        style={{ ...btnStyle, flexShrink: 0 }}
                      >
                        Mark read
                      </button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {mode === "pantry" && (
        <section style={sectionStyle}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: 8,
            }}
          >
            <h2 style={{ marginTop: 0, marginBottom: 0 }}>Pantry</h2>
            <button
              type="button"
              onClick={() => userId && runPantryMutation(async () => {})}
              disabled={loading || !userId}
              style={{ padding: "6px 12px", cursor: "pointer" }}
            >
              Refresh pantry
            </button>
          </div>

          {!userId && <p>Create a profile to manage your pantry.</p>}

          {userId && (
            <>
              <h3 style={{ fontSize: 16, marginTop: 20 }}>Add ingredient</h3>
              <form onSubmit={addToPantry}>
                <label style={{ display: "block", marginBottom: 12 }}>
                  Ingredient name
                  <input
                    style={inputStyle}
                    value={addName}
                    onChange={(e) => setAddName(e.target.value)}
                    required
                  />
                </label>
                {addName.trim() && (
                  <p style={{ fontSize: 13, color: "#555", marginTop: -4 }}>
                    Stored as: <strong>{displayIngredientName(addName)}</strong>
                  </p>
                )}
                <label style={{ display: "block", marginBottom: 12 }}>
                  Quantity
                  <input
                    style={inputStyle}
                    type="number"
                    min="0"
                    step="any"
                    value={addQty}
                    onChange={(e) => setAddQty(e.target.value)}
                    required
                  />
                </label>
                <label style={{ display: "block", marginBottom: 12 }}>
                  Unit
                  <select
                    style={{ ...inputStyle, maxWidth: 160 }}
                    value={addUnit}
                    onChange={(e) => setAddUnit(e.target.value as PantryUnit)}
                  >
                    {PANTRY_UNITS.map((u) => (
                      <option key={u} value={u}>
                        {u}
                      </option>
                    ))}
                  </select>
                </label>
                <label style={{ display: "block", marginBottom: 12 }}>
                  Expiry date (optional)
                  <input
                    type="date"
                    value={addExpiresAt}
                    onChange={(e) => setAddExpiresAt(e.target.value)}
                    style={{ ...inputStyle, maxWidth: 200 }}
                  />
                </label>
                <button type="submit" disabled={loading} style={{ padding: "8px 16px" }}>
                  Add to pantry
                </button>
              </form>

              <h3 style={{ fontSize: 16, marginTop: 24 }}>Your items</h3>
              {pantry.length === 0 && !loading && <p>Pantry is empty.</p>}
              {pantry.map((item) => {
                const expiryLabel = formatExpiryLabel(item.expires_at);
                return (
                <div key={`${item.id}-${pantryVersion}`} style={rowStyle}>
                  <div style={{ marginBottom: 8 }}>
                    <strong>{displayIngredientName(item.ingredient_name)}</strong>
                    <span style={{ color: theme.muted }}> ({item.unit})</span>
                    <span style={{ color: theme.subtle, marginLeft: 8 }}>
                      — {item.quantity} {item.unit}
                    </span>
                    {expiryLabel && (
                      <span
                        style={{
                          marginLeft: 8,
                          fontSize: 13,
                          color: expiryLabel === "expired" ? theme.error : theme.muted,
                        }}
                      >
                        · {expiryLabel}
                      </span>
                    )}
                  </div>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      flexWrap: "wrap",
                      marginBottom: 8,
                    }}
                  >
                    <input
                      type="number"
                      min="0"
                      step="any"
                      value={editQty[item.id] ?? String(item.quantity)}
                      onChange={(e) =>
                        setEditQty((prev) => ({ ...prev, [item.id]: e.target.value }))
                      }
                      style={{ width: 100, padding: 6 }}
                    />
                    <span>{item.unit}</span>
                    <label style={{ fontSize: 13, color: theme.subtle }}>
                      Expires
                      <input
                        type="date"
                        value={editExpiresAt[item.id] ?? ""}
                        onChange={(e) =>
                          setEditExpiresAt((prev) => ({
                            ...prev,
                            [item.id]: e.target.value,
                          }))
                        }
                        style={{ display: "block", marginTop: 4, padding: 6 }}
                      />
                    </label>
                    <button
                      type="button"
                      onClick={() => savePantryItem(item)}
                      disabled={loading}
                      style={btnStyle}
                    >
                      Save
                    </button>
                  </div>
                  <div>
                    <button
                      type="button"
                      onClick={() => postPantryEvent(item, quickStep(item.unit), "added")}
                      disabled={loading}
                      style={btnStyle}
                    >
                      +
                    </button>
                    <button
                      type="button"
                      onClick={() => postPantryEvent(item, -quickStep(item.unit), "consumed")}
                      disabled={loading}
                      style={btnStyle}
                    >
                      -
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        postPantryEvent(item, -consumedStep(item.unit), "consumed")
                      }
                      disabled={loading}
                      style={btnStyle}
                    >
                      Consumed
                    </button>
                  </div>
                </div>
              );
              })}

              <h3 style={{ fontSize: 16, marginTop: 24 }}>Event history</h3>
              {events.length === 0 && !loading && <p>No events yet.</p>}
              <ul style={{ paddingLeft: 20, margin: 0 }} key={pantryVersion}>
                {events.map((ev) => (
                  <li key={ev.id} style={{ marginBottom: 6, fontSize: 14 }}>
                    {formatEventLine(ev)}
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      )}

      {mode === "meal_plan" && (
        <section style={sectionStyle}>
          <h2 style={{ marginTop: 0 }}>Meal Plan</h2>
          {!userId && <p>Create a profile to plan meals.</p>}
          {userId && (
            <>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "end" }}>
                <label>
                  Week start (Mon)
                  <input
                    type="date"
                    value={weekStartDate}
                    onChange={(e) => setWeekStartDate(e.target.value)}
                    style={{ display: "block", padding: 6, marginTop: 4 }}
                  />
                </label>
                <button
                  type="button"
                  onClick={loadWeek}
                  disabled={loading}
                  style={{ padding: "8px 16px", cursor: "pointer" }}
                >
                  Load plan
                </button>
                <button
                  type="button"
                  onClick={savePlan}
                  disabled={loading || !weekStartDate}
                  style={{ padding: "8px 16px", cursor: "pointer" }}
                >
                  {mealPlan ? "Save plan" : "Save plan (create new)"}
                </button>
              </div>
              <p style={{ fontSize: 14, color: theme.subtle, marginTop: 8 }}>
                {mealPlan
                  ? `Editing plan ${mealPlan.id.slice(0, 8)}…`
                  : "No saved plan for this week — add items and save to create."}
              </p>

              <div
                style={{
                  marginTop: 16,
                  padding: 12,
                  border: `1px solid ${theme.borderLight}`,
                  borderRadius: 6,
                }}
              >
                <h3 style={{ fontSize: 16, marginTop: 0 }}>Auto-generate week</h3>
                <p style={{ fontSize: 13, color: theme.muted, marginTop: 0 }}>
                  Fills Mon–Sun dinners from pantry-aware recipes (overwrites this week if
                  saved).
                </p>
                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    gap: 12,
                    alignItems: "end",
                  }}
                >
                  <label>
                    Servings
                    <input
                      type="number"
                      min="0.5"
                      step="any"
                      value={generateServings}
                      onChange={(e) => setGenerateServings(e.target.value)}
                      style={{ display: "block", marginTop: 4, padding: 6, width: 80 }}
                    />
                  </label>
                  <label>
                    Max missing
                    <input
                      type="number"
                      min="0"
                      step="1"
                      value={generateMaxMissing}
                      onChange={(e) => setGenerateMaxMissing(e.target.value)}
                      style={{ display: "block", marginTop: 4, padding: 6, width: 80 }}
                    />
                  </label>
                  <button
                    type="button"
                    onClick={autoGenerateWeek}
                    disabled={loading || !weekStartDate}
                    style={{ padding: "8px 16px", cursor: "pointer" }}
                  >
                    Auto-generate week
                  </button>
                </div>
              </div>

              <h3 style={{ fontSize: 16, marginTop: 20 }}>Add meal</h3>
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: 12,
                  alignItems: "end",
                  marginBottom: 12,
                }}
              >
                <label>
                  Day
                  <select
                    value={addPlanDay}
                    onChange={(e) => setAddPlanDay(Number(e.target.value))}
                    style={{ display: "block", marginTop: 4, padding: 6, minWidth: 100 }}
                  >
                    {DAY_LABELS.map((label, day) => (
                      <option key={label} value={day}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Meal
                  <select
                    value={addPlanMealType}
                    onChange={(e) => setAddPlanMealType(e.target.value as MealType)}
                    style={{ display: "block", marginTop: 4, padding: 6, minWidth: 120 }}
                  >
                    {MEAL_TYPES.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Recipe
                  <select
                    value={addPlanRecipeId}
                    onChange={(e) => setAddPlanRecipeId(e.target.value)}
                    style={{ display: "block", marginTop: 4, padding: 6, minWidth: 200 }}
                  >
                    <option value="">- choose -</option>
                    {recipeOptions.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Servings
                  <input
                    type="number"
                    min="0.5"
                    step="any"
                    value={addPlanServings}
                    onChange={(e) => setAddPlanServings(e.target.value)}
                    style={{ display: "block", marginTop: 4, padding: 6, width: 80 }}
                  />
                </label>
                <button
                  type="button"
                  onClick={addToPlanList}
                  disabled={loading}
                  style={{ padding: "8px 16px", cursor: "pointer" }}
                >
                  Add to plan list
                </button>
              </div>

              <h3 style={{ fontSize: 16, marginTop: 16 }}>Current plan</h3>
              {planItems.length === 0 && (
                <p style={{ color: theme.muted, fontSize: 14 }}>No meals in the list yet.</p>
              )}
              {DAY_LABELS.map((label, day) => {
                const dayItems = planItemsByDay[day];
                if (dayItems.length === 0) return null;
                return (
                  <div key={label} style={{ marginBottom: 16 }}>
                    <strong>{label}</strong>
                    <ul style={{ paddingLeft: 20, margin: "8px 0 0" }}>
                      {dayItems.map((item) => (
                        <li key={`${item.day}-${item.meal_type}`} style={{ marginBottom: 6 }}>
                          <span style={{ textTransform: "capitalize" }}>{item.meal_type}</span>:{" "}
                          <strong>
                            {recipeNameById.get(item.recipe_id) ?? "Recipe"}
                          </strong>{" "}
                          ({item.servings} servings)
                          <button
                            type="button"
                            onClick={() => removeFromPlanList(item.day, item.meal_type)}
                            disabled={loading}
                            style={{ ...btnStyle, marginLeft: 8 }}
                          >
                            Remove
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })}
            </>
          )}
        </section>
      )}

      {mode === "shopping" && (
        <section style={sectionStyle}>
          <h2 style={{ marginTop: 0 }}>Shopping List</h2>
          {!userId && <p>Create a profile first.</p>}
          {userId && (
            <>
              <p style={{ fontSize: 14, color: theme.subtle }}>
                {mealPlan
                  ? `Using meal plan week ${mealPlan.week_start_date}`
                  : "Load a meal plan in Meal Plan mode first."}
              </p>
              <button
                type="button"
                onClick={generateShoppingList}
                disabled={loading || !mealPlan}
                style={{ padding: "8px 16px", cursor: "pointer", marginBottom: 12 }}
              >
                Generate shopping list
              </button>
              {shoppingLines.length === 0 && !loading && (
                <p style={{ color: theme.muted, fontSize: 14 }}>No items yet.</p>
              )}
              <ul style={{ paddingLeft: 0, margin: 0, listStyle: "none" }}>
                {shoppingLines.map((line) => (
                  <li
                    key={line.id}
                    style={{
                      marginBottom: 10,
                      padding: "8px 10px",
                      border: `1px solid ${theme.borderLight}`,
                      borderRadius: 6,
                      opacity: line.checked ? 0.65 : 1,
                      background: line.checked ? theme.surfaceActive : theme.surface,
                      textDecoration: line.checked ? "line-through" : "none",
                    }}
                  >
                    <label style={{ cursor: "pointer", display: "block" }}>
                      <input
                        type="checkbox"
                        checked={line.checked}
                        disabled={loading}
                        onChange={() => toggleShoppingChecked(line)}
                        style={{ marginRight: 8 }}
                      />
                      <strong>{displayIngredientName(line.ingredient_name)}</strong>
                      <div style={{ fontSize: 13, marginTop: 4, color: theme.subtle }}>
                        Need {line.needed_qty} {line.unit} · In pantry {line.in_pantry_qty}{" "}
                        {line.unit} · To buy <strong>{line.to_buy_qty} {line.unit}</strong>
                        {line.checked && (
                          <span style={{ marginLeft: 8, color: theme.success }}>✓ checked</span>
                        )}
                      </div>
                      {(shoppingSubstitutions[line.ingredient_name] ?? []).length > 0 && (
                        <p
                          style={{
                            fontSize: 12,
                            color: theme.muted,
                            margin: "6px 0 0",
                            fontStyle: "italic",
                          }}
                        >
                          Swap ideas:{" "}
                          {shoppingSubstitutions[line.ingredient_name]
                            .map((s) => displayIngredientName(s))
                            .join(", ")}
                        </p>
                      )}
                    </label>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      )}

      {mode === "cook_now" && (
        <section style={sectionStyle}>
          <h2 style={{ marginTop: 0 }}>Cook Now</h2>
          {!userId && <p>Create a profile first.</p>}
          {userId && (
            <>
              <button
                type="button"
                onClick={loadCookNow}
                disabled={loading}
                style={{ padding: "8px 16px", cursor: "pointer", marginBottom: 16 }}
              >
                Load recommendations
              </button>
              {!cookNow && !loading && (
                <p style={{ color: theme.muted, fontSize: 14 }}>Tap load to see what you can cook.</p>
              )}
              {cookNow && (
                <>
                  <h3 style={{ fontSize: 16, marginTop: 0 }}>Can cook now</h3>
                  {cookNow.can_cook.length === 0 && (
                    <p style={{ color: theme.muted, fontSize: 14 }}>None right now.</p>
                  )}
                  <ul style={{ paddingLeft: 20, margin: "0 0 20px" }}>
                    {cookNow.can_cook.map((r) => (
                      <li key={r.recipe_id} style={{ marginBottom: 8 }}>
                        <button
                          type="button"
                          onClick={() => openRecipeFromCookNow(r.recipe_id)}
                          style={{
                            border: "none",
                            background: "none",
                            padding: 0,
                            cursor: "pointer",
                            color: "inherit",
                            fontWeight: 600,
                            textDecoration: "underline",
                          }}
                        >
                          {r.name}
                        </button>
                        <span style={{ color: theme.success, fontSize: 13, marginLeft: 8 }}>
                          ready
                        </span>
                      </li>
                    ))}
                  </ul>

                  <h3 style={{ fontSize: 16 }}>Almost</h3>
                  {cookNow.almost.length === 0 && (
                    <p style={{ color: theme.muted, fontSize: 14 }}>No close matches.</p>
                  )}
                  <ul style={{ paddingLeft: 20, margin: 0 }}>
                    {cookNow.almost.map((r) => (
                      <li key={r.recipe_id} style={{ marginBottom: 12 }}>
                        <button
                          type="button"
                          onClick={() => openRecipeFromCookNow(r.recipe_id)}
                          style={{
                            border: "none",
                            background: "none",
                            padding: 0,
                            cursor: "pointer",
                            color: "inherit",
                            fontWeight: 600,
                            textDecoration: "underline",
                          }}
                        >
                          {r.name}
                        </button>
                        {r.missing.length > 0 && (
                          <div style={{ marginTop: 4 }}>
                            {r.missing.map((ing) => (
                              <div key={ing} style={{ marginBottom: 8 }}>
                                <span style={chipStyle}>
                                  {displayIngredientName(ing)}
                                </span>
                                {(r.substitutions?.[ing] ?? []).length > 0 && (
                                  <p
                                    style={{
                                      fontSize: 12,
                                      color: theme.muted,
                                      margin: "4px 0 0",
                                    }}
                                  >
                                    Swap ideas:{" "}
                                    {(r.substitutions?.[ing] ?? [])
                                      .map((sub) => displayIngredientName(sub))
                                      .join(", ")}
                                  </p>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </>
          )}
        </section>
      )}

      {mode === "recipes" && (
        <section style={sectionStyle}>
          <h2 style={{ marginTop: 0 }}>Recipes</h2>

          <div style={{ marginBottom: 16 }}>
            <label>
              Select recipe
              <select
                value={selectedRecipeId}
                onChange={(e) => handleSelectRecipe(e.target.value)}
                style={{ display: "block", marginTop: 4, padding: 6, minWidth: 300 }}
              >
                <option value="">- choose -</option>
                {recipeOptions.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {recipeDetail && (
            <div style={{ marginBottom: 20 }}>
              <h3 style={{ marginTop: 0 }}>{recipeDetail.recipe.name}</h3>
              <p style={{ color: theme.muted, fontSize: 14 }}>
                Base servings: {recipeDetail.recipe.servings_base}
              </p>
              <ul style={{ paddingLeft: 20 }}>
                {recipeDetail.ingredients.map((ing) => (
                  <li key={ing.id}>
                    {displayIngredientName(ing.ingredient_name)}: {ing.quantity} {ing.unit}
                  </li>
                ))}
              </ul>

              <div
                style={{
                  marginTop: 12,
                  marginBottom: 12,
                  padding: 12,
                  border: `1px solid ${theme.borderLight}`,
                  borderRadius: 6,
                }}
              >
                <div style={{ display: "flex", gap: 12, alignItems: "end", flexWrap: "wrap" }}>
                  <label>
                    Servings for estimate
                    <input
                      type="number"
                      min="0.5"
                      step="any"
                      value={nutritionServings}
                      onChange={(e) => setNutritionServings(e.target.value)}
                      style={{ display: "block", marginTop: 4, padding: 6, width: 120 }}
                    />
                  </label>
                  <button
                    type="button"
                    onClick={handleLoadNutrition}
                    disabled={loading}
                    style={{ padding: "8px 16px", cursor: "pointer" }}
                  >
                    Nutrition (rough)
                  </button>
                </div>
                {recipeNutrition && (
                  <p style={{ fontSize: 14, margin: "10px 0 0", color: theme.subtle }}>
                    {recipeNutrition.calories_per_serving != null ? (
                      <>
                        <strong>{recipeNutrition.calories_per_serving}</strong> kcal per
                        serving
                      </>
                    ) : (
                      <>Could not estimate calories</>
                    )}
                    <span style={{ marginLeft: 8, fontSize: 12 }}>({recipeNutrition.notes})</span>
                  </p>
                )}
              </div>

              <div style={{ display: "flex", gap: 12, alignItems: "end", flexWrap: "wrap" }}>
                <label>
                  Scale to servings
                  <input
                    type="number"
                    min="0.5"
                    step="any"
                    value={scaleServings}
                    onChange={(e) => setScaleServings(e.target.value)}
                    style={{ display: "block", marginTop: 4, padding: 6, width: 140 }}
                  />
                </label>
                <button
                  type="button"
                  onClick={handleScaleRecipe}
                  disabled={loading}
                  style={{ padding: "8px 16px", cursor: "pointer" }}
                >
                  Scale
                </button>
              </div>

              {scaledRecipe && (
                <ul style={{ paddingLeft: 20, marginTop: 12 }}>
                  {scaledRecipe.items.map((it, idx) => (
                    <li key={idx}>
                      {displayIngredientName(it.ingredient_name)}: {it.qty_scaled} {it.unit}
                      <span style={{ color: "#666", fontSize: 13 }}> (base {it.qty_base})</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <h3 style={{ marginTop: 0 }}>Add recipe</h3>
          <form onSubmit={handleCreateRecipe}>
            <label style={{ display: "block", marginBottom: 10 }}>
              Name
              <input
                value={newRecipeName}
                onChange={(e) => setNewRecipeName(e.target.value)}
                style={inputStyle}
                required
              />
            </label>
            <label style={{ display: "block", marginBottom: 10 }}>
              Servings base
              <input
                type="number"
                min="0.5"
                step="any"
                value={newRecipeServingsBase}
                onChange={(e) => setNewRecipeServingsBase(e.target.value)}
                style={inputStyle}
                required
              />
            </label>
            <label style={{ display: "block", marginBottom: 10 }}>
              Tags (comma separated)
              <input
                value={newRecipeTags}
                onChange={(e) => setNewRecipeTags(e.target.value)}
                style={inputStyle}
              />
            </label>

            <div style={{ marginBottom: 12 }}>
              <strong>Ingredients</strong>
              {newRecipeIngredients.map((row, idx) => (
                <div key={idx} style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
                  <input
                    placeholder="ingredient"
                    value={row.ingredient_name}
                    onChange={(e) =>
                      setNewRecipeIngredients((prev) =>
                        prev.map((r, i) =>
                          i === idx ? { ...r, ingredient_name: e.target.value } : r
                        )
                      )
                    }
                    style={{ padding: 6, minWidth: 220 }}
                  />
                  <input
                    type="number"
                    min="0"
                    step="any"
                    placeholder="qty"
                    value={row.quantity}
                    onChange={(e) =>
                      setNewRecipeIngredients((prev) =>
                        prev.map((r, i) =>
                          i === idx ? { ...r, quantity: e.target.value } : r
                        )
                      )
                    }
                    style={{ padding: 6, width: 100 }}
                  />
                  <select
                    value={row.unit}
                    onChange={(e) =>
                      setNewRecipeIngredients((prev) =>
                        prev.map((r, i) =>
                          i === idx ? { ...r, unit: e.target.value as PantryUnit } : r
                        )
                      )
                    }
                    style={{ padding: 6 }}
                  >
                    {PANTRY_UNITS.map((u) => (
                      <option key={u} value={u}>
                        {u}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={() =>
                      setNewRecipeIngredients((prev) =>
                        prev.length === 1 ? prev : prev.filter((_, i) => i !== idx)
                      )
                    }
                    style={{ padding: "6px 10px", cursor: "pointer" }}
                  >
                    Remove
                  </button>
                </div>
              ))}
              <button
                type="button"
                onClick={() =>
                  setNewRecipeIngredients((prev) => [
                    ...prev,
                    { ingredient_name: "", quantity: "", unit: "g" },
                  ])
                }
                style={{ marginTop: 8, padding: "6px 10px", cursor: "pointer" }}
              >
                Add ingredient row
              </button>
            </div>

            <button type="submit" disabled={loading} style={{ padding: "8px 16px" }}>
              Create recipe
            </button>
          </form>
        </section>
      )}

      {mode === "reminders" && (
        <section style={sectionStyle}>
          <h2 style={{ marginTop: 0 }}>Reminders</h2>
          {!userId && <p>Create a profile first.</p>}
          {userId && (
            <>
              <button
                type="button"
                onClick={async () => setReminders(await fetchReminders(userId))}
                style={{ padding: "8px 16px", cursor: "pointer", marginBottom: 12 }}
              >
                Refresh reminders
              </button>
              {remindersSorted.length === 0 && <p>No reminders yet.</p>}
              <div>
                {remindersSorted.map((r) => (
                  <div key={r.id} style={rowStyle}>
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                      <strong>
                        {r.title}{" "}
                        {!r.is_read && <span style={{ color: "#b00020", fontSize: 12 }}>(unread)</span>}
                      </strong>
                      {!r.is_read && (
                        <button
                          type="button"
                          onClick={() => markRead(r.id)}
                          style={{ padding: "6px 10px", cursor: "pointer" }}
                        >
                          Mark read
                        </button>
                      )}
                    </div>
                    <p style={{ margin: "6px 0" }}>{r.body}</p>
                    <p style={{ margin: 0, color: "#666", fontSize: 13 }}>
                      Created: {new Date(r.created_at).toLocaleString()}
                      {r.due_at ? ` • Due: ${new Date(r.due_at).toLocaleString()}` : ""}
                    </p>
                  </div>
                ))}
              </div>
            </>
          )}
        </section>
      )}
    </main>
  );
}
