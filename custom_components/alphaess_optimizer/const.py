"""Constanten voor AlphaESS Battery Optimizer."""
from __future__ import annotations

DOMAIN = "alphaess_optimizer"
PLATFORMS = ["sensor", "number", "select"]

ALPHAESS_DOMAIN = "alphaess_modbus"
NORDPOOL_DOMAIN = "nordpool"

# Entities van ha-alphaess-modbus, gevonden via het achtervoegsel van de unique_id
# (formaat: <config_entry_id>_<sleutel>). Live gecontroleerd 24-11-2026.
ALPHAESS_SUFFIX = {
    "soc": "_soc_battery",
    "capacity": "_battery_capacity_kwh",
    "house_load": "_current_house_load",
    "pv_power": "_current_pv_production",
}

# --- config entry (data) --------------------------------------------------------
CONF_DEVICE = "device_id"
CONF_SOC = "soc_entity"
CONF_CAPACITY = "capacity_entity"
CONF_HOUSE_LOAD = "house_load_entity"
CONF_PRICE = "price_entity"
CONF_PV_REMAINING = "pv_remaining_entity"
CONF_EV_POWER = "ev_power_entity"
CONF_HOLIDAY = "holiday_entity"

# --- instelbaar (data, ook via options) ----------------------------------------
CONF_POWER_KW = "power_kw"
CONF_FLOOR_PCT = "floor_pct"
CONF_MAX_SOC = "max_soc_pct"
CONF_ETA = "eta"
CONF_PRICE_ALL_IN = "price_all_in"
CONF_FEE_IN = "fee_in"
CONF_FEE_OUT = "fee_out"
CONF_NETTING_DEDUCTION = "netting_deduction"
CONF_VAT_PCT = "vat_pct"
CONF_HOLIDAY_FACTOR = "holiday_factor"
CONF_YEARLY_KWH = "yearly_kwh"

DEFAULTS = {
    CONF_POWER_KW: 10.0,
    CONF_FLOOR_PCT: 4.4,
    CONF_MAX_SOC: 98.0,
    CONF_ETA: 0.95,
    CONF_PRICE_ALL_IN: True,
    CONF_FEE_IN: 0.018,
    CONF_FEE_OUT: 0.018,
    CONF_NETTING_DEDUCTION: 0.0248,
    CONF_VAT_PCT: 21.0,
    CONF_HOLIDAY_FACTOR: 0.45,
    CONF_YEARLY_KWH: 3000.0,
}

# --- runtime-instellingen (eigen number/select-entities) ------------------------
KEY_AGGRESSIVENESS = "aggressiveness"
KEY_BACKUP_TARGET = "backup_target"
KEY_BACKUP_WEIGHT = "backup_weight"
KEY_ENERGY_TAX = "energy_tax"
KEY_WEAR = "wear_cost"
KEY_REGIME = "netting_regime"

RUNTIME_DEFAULTS = {
    KEY_AGGRESSIVENESS: 5,
    KEY_BACKUP_TARGET: 40.0,
    KEY_BACKUP_WEIGHT: 1.0,
    KEY_ENERGY_TAX: 0.0916,   # 2026, EUR/kWh excl. btw
    KEY_WEAR: 0.03,
    KEY_REGIME: "2026",
}
REGIMES = ["2026", "2027"]

# --- rekenmodel (zelfde als de live pyscript-versie) ---------------------------
SOC_STEP_KWH = 0.25
RESERVE_FACTOR = 1.2
TIEBREAK = 1e-5
HOLD_AT_CEILING = True
BACKUP_PENALTY_PER_WEIGHT = 0.0005
RESERVE_HOLD_FREE = True
RESERVE_MARGIN_FIXED = True
MIN_SELL_KWH = 0.5

# niveau: (strategie, verkoopdrempel EUR/kWh, eindwaarde-kwantiel, cycluslimiet, vasthouden)
AGGRESSIVENESS_TABLE = {
    1: ("eigen_verbruik_eerst", 0.15, 0.50, 1.0, False),
    2: ("eigen_verbruik_eerst", 0.12, 0.45, 1.0, False),
    3: ("eigen_verbruik_eerst", 0.10, 0.40, 1.0, True),
    4: ("eigen_verbruik_eerst", 0.07, 0.30, 1.5, True),
    5: ("eigen_verbruik_eerst", 0.05, 0.25, 1.5, True),
    6: ("eigen_verbruik_eerst", 0.03, 0.20, 1.5, True),
    7: ("eigen_verbruik_eerst", 0.02, 0.15, 1.5, True),
    8: ("optimaal", 0.05, 0.15, 1.5, True),
    9: ("optimaal", 0.02, 0.10, 2.0, True),
    10: ("optimaal", 0.00, 0.10, 2.0, True),
}

ACTIONS = {"L": "charge", "O": "discharge", "B": "balance", "H": "hold"}

PROFILE_DAYS = 28
