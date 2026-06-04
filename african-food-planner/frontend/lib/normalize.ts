/** Mirrors backend/app/normalize.py so UI matches server canonical names. */

function singularizeToken(word: string): string {
  if (word.length <= 2) return word;
  if (word.endsWith("ies") && word.length > 4) return word.slice(0, -3) + "y";
  if (word.endsWith("oes")) return word.slice(0, -2);
  if (word.endsWith("es") && word.length > 3) return word.slice(0, -2);
  if (word.endsWith("s") && !word.endsWith("ss") && !word.endsWith("us") && !word.endsWith("is")) {
    return word.slice(0, -1);
  }
  return word;
}

export function normalizeIngredientName(name: string): string {
  const collapsed = name.trim().toLowerCase().replace(/\s+/g, " ");
  if (!collapsed) return collapsed;
  return collapsed.split(" ").map(singularizeToken).join(" ");
}

/** Display helper: always show backend-canonical form (idempotent). */
export function displayIngredientName(name: string): string {
  return normalizeIngredientName(name);
}
