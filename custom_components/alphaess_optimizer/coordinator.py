"""Coordinator: verzamelt invoer uit HA, rekent elk kwartier een nieuw plan."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import planner
from .const import (
    CONF_CAPACITY,
    CONF_ETA,
    CONF_EV_POWER,
    CONF_FEE_IN,
    CONF_FEE_OUT,
    CONF_FLOOR_PCT,
    CONF_HOLIDAY,
    CONF_HOLIDAY_FACTOR,
    CONF_HOUSE_LOAD,
    CONF_MAX_SOC,
    CONF_NETTING_DEDUCTION,
    CONF_POWER_KW,
    CONF_PRICE,
    CONF_PRICE_ALL_IN,
    CONF_PV_REMAINING,
    CONF_SOC,
    CONF_VAT_PCT,
    CONF_YEARLY_KWH,
    DEFAULTS,
    DOMAIN,
    KEY_AGGRESSIVENESS,
    KEY_BACKUP_TARGET,
    KEY_BACKUP_WEIGHT,
    KEY_ENERGY_TAX,
    KEY_REGIME,
    KEY_WEAR,
    PROFILE_DAYS,
    RUNTIME_DEFAULTS,
)

_LOGGER = logging.getLogger(__name__)
STORE_VERSION = 1


def _float(hass: HomeAssistant, entity_id: str | None) -> float | None:
    if not entity_id:
        return None
    st = hass.states.get(entity_id)
    if st is None:
        return None
    try:
        return float(st.state)
    except (TypeError, ValueError):
        return None


class OptimizerCoordinator(DataUpdateCoordinator[dict]):
    """Plant elk kwartier (seconde 0) en bij een gewijzigde instelling."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=None,
                         config_entry=entry)
        self.entry = entry
        # runtime-instellingen; number/select-entities zetten deze bij het opstarten terug
        self.settings: dict = dict(RUNTIME_DEFAULTS)
        self._store = Store(hass, STORE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._counter = {"date": None, "kwh": 0.0, "prev_soc_kwh": None}
        self._profile: tuple[list[float], list[float]] | None = None
        self._profile_source = "flat"
        self._profile_date = None
        self._unsub = None

    @property
    def conf(self) -> dict:
        return {**DEFAULTS, **self.entry.data, **self.entry.options}

    async def async_setup(self) -> None:
        stored = await self._store.async_load()
        if stored:
            self._counter.update(stored.get("counter", {}))
        self._unsub = async_track_time_change(
            self.hass, self._on_quarter, minute=[0, 15, 30, 45], second=0)

    async def async_shutdown(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None
        await super().async_shutdown()

    @callback
    def _on_quarter(self, _now: datetime) -> None:
        self.hass.async_create_task(self.async_refresh())

    async def async_set_setting(self, key: str, value) -> None:
        """Aangeroepen door de number/select-entities."""
        if self.settings.get(key) == value:
            return
        self.settings[key] = value
        if self.data is not None:
            await self.async_request_refresh()

    # ------------------------------------------------------------------ invoer
    def _prices(self, now: datetime, energy_tax: float) -> tuple[list, bool]:
        c = self.conf
        st = self.hass.states.get(c[CONF_PRICE])
        if st is None:
            return [], False
        attrs = st.attributes
        raw = list(attrs.get("raw_today") or [])
        tomorrow = bool(attrs.get("tomorrow_valid"))
        if tomorrow:
            raw += list(attrs.get("raw_tomorrow") or [])
        prices = planner.parse_nordpool_raw(raw, now.tzinfo)
        if attrs.get("price_in_cents"):
            prices = [(t, v / 100.0) for t, v in prices]
        if not c[CONF_PRICE_ALL_IN]:
            vat = 1 + c[CONF_VAT_PCT] / 100.0
            prices = [(t, planner.to_all_in(v, energy_tax, c[CONF_FEE_IN], vat))
                      for t, v in prices]
        return prices, tomorrow

    def _ceiling(self, cap: float) -> float:
        """Laadplafond: ruimte vrijhouden voor de resterende zon van vandaag."""
        c = self.conf
        max_soc = float(c[CONF_MAX_SOC])
        ent = c.get(CONF_PV_REMAINING)
        remaining = _float(self.hass, ent)
        if remaining is None:
            return max_soc
        unit = self.hass.states.get(ent).attributes.get("unit_of_measurement")
        if unit == UnitOfEnergy.WATT_HOUR:
            remaining /= 1000.0
        return max(0.0, min(max_soc, 100.0 - remaining / cap * 100.0))

    def _discharged_today(self, soc_kwh: float, today: str, eta: float) -> float:
        """Som van de SoC-dalingen vandaag (AC), zoals de pyscript-teller."""
        c = self._counter
        if c["date"] != today:
            c.update({"date": today, "kwh": 0.0, "prev_soc_kwh": None})
        prev = c["prev_soc_kwh"]
        if prev is not None and prev - soc_kwh > 0:
            c["kwh"] += (prev - soc_kwh) * eta
        c["prev_soc_kwh"] = round(soc_kwh, 3)
        self._store.async_delay_save(lambda: {"counter": self._counter}, 5)
        return c["kwh"]

    async def _load_profile(self, now: datetime) -> None:
        """Verbruiksprofiel per uur uit de long-term statistics, weekdag en weekend apart.

        Gemiddeld vermogen (kW) over een uur = kWh in dat uur. EV-vermogen gaat eraf.
        """
        from homeassistant.components.recorder import get_instance
        from homeassistant.components.recorder.statistics import statistics_during_period

        c = self.conf
        house = c[CONF_HOUSE_LOAD]
        ev = c.get(CONF_EV_POWER)
        ids = {house} | ({ev} if ev else set())
        start = dt_util.start_of_local_day(now) - timedelta(days=PROFILE_DAYS)
        end = dt_util.start_of_local_day(now)
        try:
            stats = await get_instance(self.hass).async_add_executor_job(
                statistics_during_period, self.hass, start, end, ids, "hour",
                {"power": UnitOfPower.KILO_WATT}, {"mean"})
        except Exception as err:  # noqa: BLE001 - terugval op vlak profiel
            _LOGGER.warning("Statistics niet leesbaar, vlak profiel: %s", err)
            stats = {}

        def per_hour(rows):
            out = {}
            for r in rows or []:
                if r.get("mean") is None:
                    continue
                t = r["start"]
                t = dt_util.utc_from_timestamp(t) if isinstance(t, (int, float)) else t
                out[dt_util.as_local(t).replace(minute=0, second=0, microsecond=0)] = r["mean"]
            return out

        h = per_hour(stats.get(house))
        e = per_hour(stats.get(ev)) if ev else {}
        sums = {False: [0.0] * 24, True: [0.0] * 24}
        counts = {False: [0] * 24, True: [0] * 24}
        for t, kw in h.items():
            v = max(0.0, kw - e.get(t, 0.0))
            we = t.weekday() >= 5
            sums[we][t.hour] += v
            counts[we][t.hour] += 1
        if min(counts[False]) >= 3 and min(counts[True]) >= 2:
            wd = [sums[False][i] / counts[False][i] / 4.0 for i in range(24)]
            we = [sums[True][i] / counts[True][i] / 4.0 for i in range(24)]
            self._profile = (wd, we)
            self._profile_source = f"statistics ({PROFILE_DAYS} days)"
        else:
            flat = planner.flat_profile(float(c[CONF_YEARLY_KWH]))
            self._profile = (flat, flat)
            self._profile_source = "flat (not enough statistics)"
        self._profile_date = now.date()

    # ------------------------------------------------------------------ plan
    async def _async_update_data(self) -> dict:
        c = self.conf
        now = dt_util.now()
        if self._profile is None or self._profile_date != now.date():
            await self._load_profile(now)

        soc_pct = _float(self.hass, c[CONF_SOC])
        if soc_pct is None:
            raise UpdateFailed("SoC unavailable")
        cap = _float(self.hass, c[CONF_CAPACITY])
        if not cap or cap <= 0:
            raise UpdateFailed("Battery capacity unavailable")

        s = self.settings
        energy_tax = float(s[KEY_ENERGY_TAX])
        prices, tomorrow = self._prices(now, energy_tax)
        if not prices:
            raise UpdateFailed("No prices available")

        wd, we = self._profile
        holiday = c.get(CONF_HOLIDAY)
        if holiday and (st := self.hass.states.get(holiday)) and st.state == STATE_ON:
            f = float(c[CONF_HOLIDAY_FACTOR])
            wd = [x * f for x in wd]
            we = [x * f for x in we]

        eta = float(c[CONF_ETA])
        used = self._discharged_today(soc_pct / 100.0 * cap, now.date().isoformat(), eta)
        inp = planner.PlanInput(
            now=now, prices=prices, soc_pct=soc_pct, capacity_kwh=cap,
            ceiling_pct=self._ceiling(cap), floor_pct=float(c[CONF_FLOOR_PCT]),
            power_kw=float(c[CONF_POWER_KW]), eta=eta, load_weekday=wd, load_weekend=we,
            discharged_today_kwh=used, regime=str(s[KEY_REGIME]), energy_tax=energy_tax,
            vat=1 + float(c[CONF_VAT_PCT]) / 100.0, fee_in=float(c[CONF_FEE_IN]),
            fee_out=float(c[CONF_FEE_OUT]), netting_deduction=float(c[CONF_NETTING_DEDUCTION]),
            wear=float(s[KEY_WEAR]), aggressiveness=int(s[KEY_AGGRESSIVENESS]),
            backup_target_pct=float(s[KEY_BACKUP_TARGET]),
            backup_weight=float(s[KEY_BACKUP_WEIGHT]), tomorrow_known=tomorrow,
            extra={"profile": self._profile_source},
        )
        t0 = time.monotonic()
        result = await self.hass.async_add_executor_job(planner.make_plan, inp)
        result["calc_time_s"] = round(time.monotonic() - t0, 2)
        result["updated"] = now.isoformat()
        return result
