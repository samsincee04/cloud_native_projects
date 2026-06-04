from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserIdResponse(BaseModel):
    id: UUID


class RecipeIngredientIn(BaseModel):
    ingredient_name: str
    quantity: float
    unit: str
    optional: bool = False
    category: str | None = None


class RecipeCreateRequest(BaseModel):
    name: str
    servings_base: float
    tags: list[str] = []
    ingredients: list[RecipeIngredientIn]
    steps: list[str] | None = None


class RecipeResponse(BaseModel):
    id: UUID
    name: str
    servings_base: float
    tags: list[str] = []
    created_at: datetime


class RecipeIngredientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ingredient_name: str
    quantity: float
    unit: str
    optional: bool
    category: str | None


class RecipeDetailResponse(BaseModel):
    recipe: RecipeResponse
    ingredients: list[RecipeIngredientResponse]
    steps: list | None = None


class RecipeScaleItem(BaseModel):
    ingredient_name: str
    unit: str
    qty_base: float
    qty_scaled: float
    optional: bool
    category: str | None


class RecipeScaleResponse(BaseModel):
    recipe_id: UUID
    recipe_name: str
    servings_base: float
    servings_target: float
    items: list[RecipeScaleItem]


class RecipeNutritionResponse(BaseModel):
    calories_per_serving: float | None
    notes: str


class PantryItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    ingredient_name: str
    quantity: float
    unit: str
    expires_at: datetime | None


class PantryItemCreateRequest(BaseModel):
    user_id: UUID
    ingredient_name: str
    quantity: float
    unit: str
    expires_at: datetime | None = None


class PantryItemUpdateRequest(BaseModel):
    quantity: float | None = None
    unit: str | None = None
    expires_at: datetime | None = None


class PantryItemsResponse(BaseModel):
    user_id: UUID
    items: list[PantryItemResponse]


class PantryEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    ingredient_name: str
    delta: float
    unit: str
    reason: str
    created_at: datetime


class PantryEventCreateRequest(BaseModel):
    user_id: UUID
    ingredient_name: str
    delta: float
    unit: str
    reason: str
    expires_at: datetime | None = None


class PantryEventsResponse(BaseModel):
    user_id: UUID
    items: list[PantryEventResponse]


class PantryEventApplyResponse(BaseModel):
    item: PantryItemResponse
    event: PantryEventResponse


class OkResponse(BaseModel):
    ok: bool = True


class SeedRecipesResponse(BaseModel):
    created: int
    updated: int
    total: int
    seed_file: str


MealType = Literal["breakfast", "lunch", "dinner"]


class MealPlanItemIn(BaseModel):
    day: int = Field(ge=0, le=6)
    meal_type: MealType
    recipe_id: UUID
    servings: float = Field(gt=0)


class MealPlanCreateOrUpdateRequest(BaseModel):
    week_start_date: date
    items: list[MealPlanItemIn] = Field(default_factory=list)


class MealPlanGenerateRequest(BaseModel):
    week_start_date: date
    meal_type: MealType = "dinner"
    servings: float = Field(gt=0)
    include_tags: list[str] = Field(default_factory=list)
    exclude_tags: list[str] = Field(default_factory=list)
    max_repeats_per_week: int = Field(default=1, ge=1)
    max_missing_ingredients: int = Field(default=4, ge=0)


class MealPlanItemOut(BaseModel):
    id: UUID
    day: int
    meal_type: str
    recipe_id: UUID
    servings: float


class MealPlanResponse(BaseModel):
    id: UUID
    user_id: UUID
    week_start_date: date
    items: list[MealPlanItemOut]


class CookableMissingIngredient(BaseModel):
    ingredient_name: str
    needed_qty: float
    unit: str
    pantry_qty: float


class CookableRecipeItem(BaseModel):
    recipe_id: UUID
    recipe_name: str
    servings_base: float
    cookable: bool
    missing_count: int
    missing: list[CookableMissingIngredient]


class CookNowRecipeItem(BaseModel):
    recipe_id: UUID
    name: str
    missing: list[str]
    substitutions: dict[str, list[str]] = Field(default_factory=dict)


class CookNowResponse(BaseModel):
    can_cook: list[CookNowRecipeItem]
    almost: list[CookNowRecipeItem]


class ShoppingListItemOut(BaseModel):
    id: UUID
    ingredient_name: str
    unit: str
    needed_qty: float
    in_pantry_qty: float
    to_buy_qty: float
    checked: bool


class ShoppingListResponse(BaseModel):
    id: UUID
    meal_plan_id: UUID
    items: list[ShoppingListItemOut]


class ShoppingListItemPatchRequest(BaseModel):
    checked: bool


class SubstituteEntry(BaseModel):
    substitute: str
    note: str
    category: str | None = None


class SubstitutesResponse(BaseModel):
    ingredient_name: str
    substitutes: list[SubstituteEntry]


class MissingSubstitutesRequest(BaseModel):
    missing: list[str]


class MissingSubstitutesResponse(BaseModel):
    substitutes: dict[str, list[SubstituteEntry]]


class ReminderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    type: str
    title: str
    body: str
    due_at: datetime | None
    created_at: datetime
    is_read: bool


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    type: str
    title: str
    body: str
    metadata_json: dict | list | None
    created_at: datetime
    read_at: datetime | None


class NotificationsListResponse(BaseModel):
    user_id: UUID
    items: list[NotificationResponse]


class NotificationsReadAllResponse(BaseModel):
    user_id: UUID
    updated_count: int
