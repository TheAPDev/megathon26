"""Typed data contracts. The same models are the API schemas and the LLM tool schemas."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

DwellingType = Literal["apartment", "independent_house", "row_house"]
FloorPosition = Literal["ground", "middle", "top"]
Tenure = Literal["owner", "tenant"]
WallType = Literal["solid_brick", "hollow_block", "aac"]
Shading = Literal["none", "partial", "full"]
AcTech = Literal["fixed", "inverter"]
WaterHeating = Literal["electric_geyser", "solar", "heat_pump", "gas", "none"]
Cooking = Literal["lpg", "png", "induction"]
Backup = Literal["none", "lead_acid", "lithium", "dg_set"]
DataSource = Literal["smart_meter", "bill_ocr", "bbps", "survey"]


class Home(BaseModel):
    """A home as the engine sees it. Missing values are allowed and flagged, never filled with zero."""

    home_id: str
    city: str
    dwelling_type: DwellingType = "apartment"
    floor_position: FloorPosition = "middle"
    tenure: Tenure = "owner"
    carpet_area_m2: Optional[float] = Field(None, gt=10, lt=2000)
    occupants: int = Field(4, ge=1, le=15)
    building_age_years: Optional[float] = Field(None, ge=0, le=120)
    roof_area_m2: Optional[float] = Field(None, ge=0)
    roof_access: bool = False  # private usable roof for this household
    wall_type: WallType = "solid_brick"
    window_to_wall: float = Field(0.2, ge=0, le=0.9)
    west_glass: bool = False
    shading: Shading = "none"
    cool_roof: bool = False
    roof_insulation: bool = False
    solar_film: bool = False
    n_ac: int = Field(0, ge=0, le=10)
    ac_tech: AcTech = "fixed"
    ac_star: int = Field(3, ge=1, le=5)
    ac_age_years: float = Field(5, ge=0, le=30)
    ac_tonnage: float = Field(1.5, ge=0.75, le=3)
    ac_setpoint_c: float = Field(24, ge=16, le=30)
    n_coolers: int = Field(0, ge=0, le=6)
    n_fans: int = Field(4, ge=0, le=20)
    bldc_fan_share: float = Field(0.0, ge=0, le=1)
    fridge_star: int = Field(3, ge=1, le=5)
    fridge_age_years: float = Field(6, ge=0, le=30)
    light_points: int = Field(12, ge=0, le=80)
    led_share: float = Field(0.6, ge=0, le=1)
    water_heating: WaterHeating = "electric_geyser"
    cooking: Cooking = "lpg"
    lpg_cylinders_per_year: Optional[float] = Field(None, ge=0, le=40)
    pv_kw: float = Field(0, ge=0, le=50)
    net_metered: bool = False
    backup: Backup = "none"
    outage_hours_month: float = Field(4, ge=0, le=300)
    smart_meter: bool = False
    tod_tariff: bool = False
    smart_plugs: bool = False
    bee_star_label: Optional[int] = Field(None, ge=1, le=5)
    sanctioned_load_kw: float = Field(3, ge=0.5, le=50)
    income_band: Literal["low", "middle", "upper_middle", "high"] = "middle"
    wfh: bool = False
    data_source: DataSource = "survey"
    monthly_kwh: Optional[list[Optional[float]]] = None  # last 12 months grid import, Jan..Dec order
    has_retrofit_history: bool = False

    @model_validator(mode="after")
    def _houses_have_roofs(self):
        if self.dwelling_type != "apartment" and self.floor_position != "top":
            object.__setattr__(self, "floor_position", "top")  # a house's top floor is its own roof
        return self

    @field_validator("monthly_kwh")
    @classmethod
    def _twelve(cls, v):
        if v is not None and len(v) != 12:
            raise ValueError("monthly_kwh must have 12 entries (use null for missing months)")
        return v


class SubScore(BaseModel):
    component: str
    weight: float
    score: float
    contribution: float
    why: str
    estimated: bool = False


class ScoreResult(BaseModel):
    home_id: str
    score: int
    band: str
    raw_score: float
    components: list[SubScore]
    confidence: Literal["high", "medium", "low"]
    confidence_reasons: list[str]
    warnings: list[str]
    annual_grid_kwh: Optional[float]
    annual_grid_kwh_estimated: bool
    intensity_kwh_m2: Optional[float]
    peer_percentile: Optional[float] = None


class Recommendation(BaseModel):
    retrofit_id: str
    name: str
    category: str
    order_rank: int
    suitability: Literal["High", "Medium", "Low", "Infeasible"]
    reason: str
    cost_inr_min: float = 0
    cost_inr_max: float = 0
    saving_kwh_electricity: float = 0
    saving_kwh_lpg: float = 0
    saving_inr_year: float = 0
    co2_kg_year: float = 0
    payback_years: Optional[float] = None
    rank_score: float = 0


class ScenarioRequest(BaseModel):
    retrofits: list[str] = Field(default_factory=list)
    params: dict[str, float] = Field(default_factory=dict)  # e.g. pv_kw, ac_setpoint_c


class EnergyBreakdown(BaseModel):
    cooling: float
    fans_coolers: float
    fridge: float
    lighting: float
    water_heating: float
    plug_other: float
    cooking_electric: float
    backup_losses: float
    total_electric_demand: float
    pv_generation: float
    pv_self_consumed: float
    pv_exported: float
    grid_import: float
    lpg_kwh: float
    dg_kwh: float
    monthly_grid_import: list[float]
    monthly_pv_generation: list[float] = Field(default_factory=list)
    monthly_enduse: dict[str, list[float]] = Field(default_factory=dict)
