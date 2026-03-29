"""
Bondkoll — field overview: OpenWeather data, mock NDVI, health status.
"""

from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from datetime import date, timedelta

import pandas as pd
import requests
import streamlit as st

OW_CURRENT = "https://api.openweathermap.org/data/2.5/weather"
OW_FORECAST = "https://api.openweathermap.org/data/2.5/forecast"


class WeatherAPIError(Exception):
    """User-facing weather API failure."""


SWEDISH_LOCATIONS = sorted(
    {
        # Counties / län
        "Blekinge",
        "Dalarna",
        "Gotland",
        "Gävleborg",
        "Halland",
        "Jämtland",
        "Jönköping",
        "Kalmar",
        "Kronoberg",
        "Norrbotten",
        "Skåne",
        "Stockholm",
        "Södermanland",
        "Uppsala",
        "Värmland",
        "Västerbotten",
        "Västernorrland",
        "Västmanland",
        "Västra Götaland",
        "Örebro",
        "Östergötland",
        # Major cities / towns
        "Arboga",
        "Arvika",
        "Avesta",
        "Boden",
        "Borlänge",
        "Borås",
        "Danderyd",
        "Enköping",
        "Eskilstuna",
        "Falkenberg",
        "Falköping",
        "Falun",
        "Gällivare",
        "Gävle",
        "Gothenburg",
        "Göteborg",
        "Halmstad",
        "Haparanda",
        "Helsingborg",
        "Hudiksvall",
        "Huddinge",
        "Härnösand",
        "Jönköping",
        "Kalmar",
        "Karlshamn",
        "Karlskoga",
        "Karlskrona",
        "Karlstad",
        "Kristianstad",
        "Kungsbacka",
        "Köping",
        "Landskrona",
        "Lidköping",
        "Linköping",
        "Luleå",
        "Lund",
        "Malmö",
        "Motala",
        "Norrköping",
        "Nyköping",
        "Piteå",
        "Sala",
        "Sandviken",
        "Skellefteå",
        "Skövde",
        "Sollentuna",
        "Solna",
        "Stockholm",
        "Sundsvall",
        "Södertälje",
        "Trollhättan",
        "Trelleborg",
        "Täby",
        "Uddevalla",
        "Umeå",
        "Uppsala",
        "Varberg",
        "Västerås",
        "Växjö",
        "Ystad",
        "Ängelholm",
        "Örebro",
        "Örnsköldsvik",
        "Östersund",
    }
)

DEFAULT_FIELD_SUGGESTIONS_SV = [
    "Norra fältet",
    "Södra åkern",
    "Östra ängen",
    "Västra plotten",
    "Fält 1",
    "Fält 2",
    "Fält A",
    "Fält B",
]
DEFAULT_FIELD_SUGGESTIONS_EN = [
    "North forty",
    "South ridge",
    "East meadow",
    "West plot",
    "Field 1",
    "Field 2",
    "Field A",
    "Field B",
]


def t(sv: str, en: str) -> str:
    """Swedish or English from `st.session_state['lang']` ('sv' | 'en')."""
    return sv if st.session_state.get("lang", "sv") == "sv" else en


# Farmer-friendly explanations (hover on metrics via help=). Also used in glossary.
FIELD_TERM_HELP: dict[str, dict[str, str]] = {
    "field_status": {
        "sv": "Status bygger på senast simulerat NDVI. Färgerna visar tre nivåer av hur ”grönt” värdet är i modellen.",
        "en": "Status is based on the latest simulated NDVI. The colors show three levels of how “green” the value is in the model.",
    },
    "temperature": {
        "sv": "Visar hur varm eller kall luften är vid platsen just nu. Värdet kommer från vädertjänsten.",
        "en": "Shows how warm or cold the air is at your location right now. The value comes from the weather service.",
    },
    "rain_now": {
        "sv": "Visar hur mycket regn som nyligen fallit (eller 0 om inget registrerats). Värdet kommer från vädertjänsten.",
        "en": "Shows how much rain has recently fallen (or zero if none was recorded). The value comes from the weather service.",
    },
    "conditions": {
        "sv": "En kort beskrivning av vädret just nu, till exempel sol, moln eller regn.",
        "en": "A short description of the weather right now, such as sun, clouds, or rain.",
    },
    "forecast_table": {
        "sv": "Här ser du temperatur och regn dag för dag för de närmaste dagarna, enligt prognosen.",
        "en": "Here you see temperature and rain day by day for the coming days, according to the forecast.",
    },
    "ndvi": {
        "sv": "NDVI visar hur gröna växterna ser ut i datan. Högre värde betyder mer synligt grönt bladverk.",
        "en": "NDVI shows how green your crops look in this data. Higher values mean more green plant cover is visible.",
    },
    "evi": {
        "sv": "EVI beskriver grön växtlighet på ett liknande sätt som NDVI, särskilt när växterna står tätt.",
        "en": "EVI describes green plant cover in a similar way to NDVI, especially when plants stand close together.",
    },
    "ndwi": {
        "sv": "NDWI lyfter fram vatten och fukt i bilden. Högre värde kan betyda mer vatten eller fukt som syns.",
        "en": "NDWI highlights water and moisture in the picture. A higher value can mean more water or moisture showing up.",
    },
    "ph": {
        "sv": "Surhetsgrad i den simulerade jorden. Låga tal är mer surt, högre tal mer basiskt — bara exempelvärden.",
        "en": "Acidity of the simulated soil. Lower numbers are more acid, higher more alkaline — example values only.",
    },
    "organic_carbon": {
        "sv": "Hur mycket organiskt material jorden innehåller i exemplet, angivet i procent.",
        "en": "How much organic matter the soil holds in this example, given as a percent.",
    },
    "soil_moisture": {
        "sv": "Hur fuktig jorden är i exemplet. Lågt värde betyder torrare jord i modellen.",
        "en": "This shows how wet the soil is in the example. Low values mean drier soil in the model.",
    },
    "forest": {
        "sv": "Hur stor del av närheten som i exemplet täcks av skog. Det är en uppskattning, inte en exakt karta.",
        "en": "Roughly what share of the nearby area is forest in this example. It is an estimate, not an exact map.",
    },
    "trend": {
        "sv": "Kort text som kopplar ihop simulerad veckoförändring i NDVI med hur regnet ser ut i prognosen.",
        "en": "Short text that links the week-to-week change in simulated NDVI to how rain looks in the forecast.",
    },
    "confidence": {
        "sv": "En enkel siffra som säger ungefär hur mycket data som fanns och hur enkla antagandena var. Inte ett exakt mått.",
        "en": "A simple number that roughly reflects how much data was there and how simple the assumptions were. Not an exact score.",
    },
}

GLOSSARY_ORDER: list[tuple[str, str, str]] = [
    ("field_status", "Status & NDVI", "Status & NDVI"),
    ("temperature", "Temperatur", "Temperature"),
    ("rain_now", "Regn nu", "Rain now"),
    ("conditions", "Väderläge", "Conditions"),
    ("forecast_table", "5-dagarsprognos", "5-day forecast"),
    ("ndvi", "NDVI", "NDVI"),
    ("evi", "EVI", "EVI"),
    ("ndwi", "NDWI", "NDWI"),
    ("ph", "pH", "pH"),
    ("organic_carbon", "Organiskt kol", "Organic carbon"),
    ("soil_moisture", "Markfukt", "Soil moisture"),
    ("forest", "Skogstäckning", "Forest cover"),
    ("trend", "Trend", "Trend"),
    ("confidence", "Datatrohet", "Data confidence"),
]


def fh(term: str) -> str:
    h = FIELD_TERM_HELP[term]
    return t(h["sv"], h["en"])


def farmer_glossary_markdown() -> str:
    lines_sv: list[str] = []
    lines_en: list[str] = []
    for key, lsv, len_ in GLOSSARY_ORDER:
        h = FIELD_TERM_HELP[key]
        lines_sv.append(f"- **{lsv}**: {h['sv']}")
        lines_en.append(f"- **{len_}**: {h['en']}")
    return t("\n".join(lines_sv), "\n".join(lines_en))


def openweather_api_key() -> str | None:
    env = os.environ.get("OPENWEATHER_API_KEY")
    if env and env.strip():
        return env.strip()
    try:
        k = st.secrets["OPENWEATHER_API_KEY"]
        s = str(k).strip()
        return s if s else None
    except Exception:
        return None


def fetch_openweather_current(query: str, api_key: str) -> dict:
    r = requests.get(
        OW_CURRENT,
        params={"q": query, "appid": api_key, "units": "metric"},
        timeout=15,
    )
    if r.status_code == 401:
        raise WeatherAPIError(t("Ogiltig API-nyckel. Kontrollera OpenWeather-inställningarna.", "Invalid API key. Check OpenWeather settings."))
    if r.status_code == 404:
        raise WeatherAPIError(
            t(
                "Platsen hittades inte. Prova en större ort eller lägg till land, t.ex. `Uppsala,SE`.",
                "Location not found. Try a larger place or add country, e.g. `Uppsala,SE`.",
            )
        )
    r.raise_for_status()
    return r.json()


def fetch_openweather_forecast(query: str, api_key: str) -> dict:
    r = requests.get(
        OW_FORECAST,
        params={"q": query, "appid": api_key, "units": "metric"},
        timeout=15,
    )
    if r.status_code == 401:
        raise WeatherAPIError(t("Ogiltig API-nyckel. Kontrollera OpenWeather-inställningarna.", "Invalid API key. Check OpenWeather settings."))
    if r.status_code == 404:
        raise WeatherAPIError(
            t(
                "Platsen hittades inte. Prova en större ort eller lägg till land, t.ex. `Uppsala,SE`.",
                "Location not found. Try a larger place or add country, e.g. `Uppsala,SE`.",
            )
        )
    r.raise_for_status()
    return r.json()


def current_rainfall_mm(data: dict) -> tuple[float, str]:
    """Return (mm, short note). Uses 1h or 3h OpenWeather fields when present."""
    rain = data.get("rain") or {}
    if "1h" in rain:
        return float(rain["1h"]), t("senaste timmen", "last hour")
    if "3h" in rain:
        return float(rain["3h"]), t("senaste 3 timmarna", "last 3 hours")
    return 0.0, t("ingen nylig nederbörd", "no recent rain")


def forecast_daily_table(forecast_json: dict) -> pd.DataFrame:
    """One row per calendar day (up to 5), from 3-hourly forecast slots."""
    by_day: dict[str, dict] = defaultdict(
        lambda: {"temps": [], "rain_mm": 0.0, "desc": []}
    )
    for item in forecast_json.get("list") or []:
        dt_txt = item.get("dt_txt") or ""
        day = dt_txt[:10]
        if not day:
            continue
        main = item.get("main") or {}
        for k in ("temp", "temp_min", "temp_max"):
            if k in main and main[k] is not None:
                by_day[day]["temps"].append(float(main[k]))
        r3 = (item.get("rain") or {}).get("3h")
        if r3 is not None:
            by_day[day]["rain_mm"] += float(r3)
        wx = (item.get("weather") or [{}])[0].get("description")
        if wx:
            by_day[day]["desc"].append(wx)

    rows = []
    for day in sorted(by_day.keys())[:5]:
        d = by_day[day]
        temps = d["temps"]
        if not temps:
            continue
        descs = d["desc"]
        sky = descs[len(descs) // 2].title() if descs else "—"
        rows.append(
            {
                t("Dag", "Day"): day,
                t("Hög °C", "High °C"): round(max(temps), 1),
                t("Låg °C", "Low °C"): round(min(temps), 1),
                t("Regn (mm)", "Rain (mm)"): round(d["rain_mm"], 1),
                t("Förhållanden", "Conditions"): sky,
            }
        )
    return pd.DataFrame(rows)


def forecast_daily_rain_mm_ordered(forecast_json: dict) -> list[float]:
    """Daily rain totals (mm) in chronological order, up to 5 days — for simple trend rules."""
    by_day: dict[str, float] = defaultdict(float)
    for item in forecast_json.get("list") or []:
        dt_txt = item.get("dt_txt") or ""
        day = dt_txt[:10]
        if not day:
            continue
        r3 = (item.get("rain") or {}).get("3h")
        if r3 is not None:
            by_day[day] += float(r3)
    ordered = sorted(by_day.keys())[:5]
    return [by_day[d] for d in ordered]


def trend_summary_ndvi_weather(ndvi_df: pd.DataFrame, rains: list[float]) -> str:
    """Two short neutral sentences: simulated NDVI week change + forecast rainfall pattern."""
    s = ndvi_df["value"]
    if len(s) >= 7:
        d = float(s.iloc[-1] - s.iloc[-7])
        if abs(d) < 0.022:
            sv1 = "Simulerad NDVI är i stort sett oförändrad över senaste veckan."
            en1 = "Simulated NDVI is largely unchanged over the past week."
        elif d > 0:
            sv1 = "Simulerad NDVI har rört sig lätt uppåt över senaste veckan."
            en1 = "Simulated NDVI has moved slightly upward over the past week."
        else:
            sv1 = "Simulerad NDVI har rört sig lätt nedåt över senaste veckan."
            en1 = "Simulated NDVI has moved slightly downward over the past week."
    else:
        sv1 = "Det finns för få NDVI-punkter för en veckojämförelse."
        en1 = "Too few NDVI points for a one-week comparison."

    if not rains:
        sv2 = "Prognosen saknar sammanställd nederbörd."
        en2 = "The forecast has no aggregated rainfall."
    else:
        tot = sum(rains)
        if tot < 3.5:
            sv2 = "Den kortsiktiga prognosen pekar på låg nederbörd."
            en2 = "The short-range outlook points to low rainfall."
        elif len(rains) < 2:
            sv2 = "Nederbördsprognosen omfattar bara något enstaka dygn."
            en2 = "The rainfall forecast spans only a single day or two."
        else:
            mid = len(rains) // 2
            first = sum(rains[:mid]) / max(mid, 1)
            second = sum(rains[mid:]) / max(len(rains) - mid, 1)
            diff = second - first
            if abs(diff) < 0.8:
                sv2 = "Förväntad nederbörd i prognosen är jämn över dagarna."
                en2 = "Expected rainfall in the forecast is fairly even across days."
            elif diff > 0:
                sv2 = "Nederbörden i prognosen är något tyngre mot periodens senare del."
                en2 = "Rainfall in the forecast is somewhat heavier toward the later days."
            else:
                sv2 = "Nederbörden i prognosen är något tyngre i början av perioden."
                en2 = "Rainfall in the forecast is somewhat heavier early in the period."

    return t(f"{sv1} {sv2}", f"{en1} {en2}")


def mock_index_series(seed_base: str, key: str, days: int, lo: float, hi: float) -> pd.DataFrame:
    """Simulated daily index; deterministic from seed_base + key; values clipped to [lo, hi]."""
    seed = f"{seed_base}|{key}"
    h = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16)
    span = hi - lo
    rng = (h % 10000) / 10000.0
    base = lo + span * (0.2 + 0.6 * rng)
    drift = 0.18 * span * (((h >> 8) % 200) / 200.0 - 0.5)
    end = max(lo, min(hi, base + drift))

    today = date.today()
    dates = [today - timedelta(days=days - 1 - i) for i in range(days)]
    t_val = pd.Series(range(days), dtype=float) / max(days - 1, 1)
    noise_amp = 0.1 * span
    noise = pd.Series(
        [noise_amp * (((h >> (i % 16)) & 7) / 7.0 - 0.5) for i in range(days)]
    )
    values = (base + (end - base) * t_val + noise).clip(lo, hi)
    return pd.DataFrame({"date": dates, "value": values})


# Simulated plausible ranges (not real satellite data)
NDVI_RANGE = (0.3, 0.9)
EVI_RANGE = (0.15, 0.85)
NDWI_RANGE = (-0.45, 0.55)

VEGETATION_INDEX_SPECS: list[tuple[str, float, float, str, str, str, str]] = [
    (
        "NDVI",
        *NDVI_RANGE,
        "Mäter grön växtlighet genom skillnad mellan nära infrarött och rött ljus.",
        "Measures green vegetation using near-infrared versus red reflectance.",
        "Senaste NDVI",
        "Latest NDVI",
    ),
    (
        "EVI",
        *EVI_RANGE,
        "Vegetationsindex som minskar störningar från atmosfär och bakgrund jämfört med NDVI.",
        "Vegetation index that reduces atmosphere and background noise compared to NDVI.",
        "Senaste EVI",
        "Latest EVI",
    ),
    (
        "NDWI",
        *NDWI_RANGE,
        "Jämför grönt och nära infrarött för att lyfta fram vatten och fukt i ytan.",
        "Compares green and near-infrared to highlight surface water and moisture.",
        "Senaste NDWI",
        "Latest NDWI",
    ),
]


def mock_soil_metrics(seed_base: str) -> dict[str, float]:
    """Deterministic mock soil numbers from field + location (not measurements)."""
    raw = hashlib.sha256(f"{seed_base}|soil".encode()).digest()
    h = int.from_bytes(raw[:8], "big")
    u1 = (h & 0xFFFFFF) / 0xFFFFFF
    u2 = ((h >> 10) & 0xFFFFFF) / 0xFFFFFF
    u3 = ((h >> 20) & 0xFFFFFF) / 0xFFFFFF
    ph = 5.5 + 2.8 * u1
    oc = 0.8 + 5.4 * u2
    moist = 15 + 38 * u3
    return {
        "ph": ph,
        "organic_carbon_pct": oc,
        "soil_moisture_pct": moist,
    }


def soil_ph_level(ph: float) -> tuple[str, str]:
    if ph < 6.2:
        return ("Låg", "Low")
    if ph < 7.3:
        return ("Medel", "Medium")
    return ("Hög", "High")


def soil_oc_level(oc: float) -> tuple[str, str]:
    if oc < 2.0:
        return ("Låg", "Low")
    if oc < 4.0:
        return ("Medel", "Medium")
    return ("Hög", "High")


def soil_moist_level(m: float) -> tuple[str, str]:
    if m < 26:
        return ("Låg", "Low")
    if m < 38:
        return ("Medel", "Medium")
    return ("Hög", "High")


def mock_forest_cover_pct(seed_base: str) -> float:
    """Deterministic mock tree-cover share 0–100 % from field + location (not satellite truth)."""
    raw = hashlib.sha256(f"{seed_base}|forest".encode()).digest()
    u = int.from_bytes(raw[:4], "big") / 0xFFFFFFFF
    return round(100 * u, 1)


def mock_data_confidence_pct(seed_base: str) -> int:
    """Simple illustrative score 70–95 % from field + location (not a statistical confidence interval)."""
    raw = hashlib.sha256(f"{seed_base}|confidence".encode()).digest()
    v = int.from_bytes(raw[:4], "big")
    return 70 + (v % 26)


def health_from_ndvi(latest: float) -> tuple[str, str]:
    if latest >= 0.55:
        return t("Bra", "Good"), "green"
    if latest >= 0.35:
        return t("Medel", "Fair"), "orange"
    return t("Svag", "Poor"), "red"


def plain_field_summary_english(
    temp: float | None,
    rain_mm: float,
    sky: str,
    ndvi: float,
    soil_moisture_pct: float,
) -> str:
    """Exactly three short, neutral sentences (English only). No recommendations."""
    _, band_en = soil_moist_level(soil_moisture_pct)
    if temp is not None:
        temp_phrase = f"The air at the location is about {temp:.1f} °C with {sky}"
    else:
        temp_phrase = f"Temperature is not available; conditions are described as {sky}"
    return (
        f"{temp_phrase}; recent rain in the data is {rain_mm:.1f} mm. "
        f"Simulated NDVI is {ndvi:.2f} and describes how much green shows in the model. "
        f"Example soil moisture is {soil_moisture_pct:.0f} % ({band_en}), meaning how wet the soil is in the example."
    )


def main() -> None:
    st.set_page_config(page_title="Bondkoll", page_icon="🌾", layout="centered")

    if "lang" not in st.session_state:
        st.session_state["lang"] = "sv"
    if "show_plain_field_explain" not in st.session_state:
        st.session_state["show_plain_field_explain"] = False

    top_l, top_r = st.columns([4, 1])
    with top_l:
        st.markdown("# 🌾 Bondkoll")
    with top_r:
        en = st.toggle(
            "English",
            value=st.session_state["lang"] == "en",
            help="Visa på engelska · Show in English",
        )
    st.session_state["lang"] = "en" if en else "sv"

    field_suggestions = (
        DEFAULT_FIELD_SUGGESTIONS_SV
        if st.session_state["lang"] == "sv"
        else DEFAULT_FIELD_SUGGESTIONS_EN
    )

    st.caption(
        t(
            "Väder från OpenWeather. Övriga värden är simulerade.",
            "Weather from OpenWeather. Other values are simulated.",
        )
    )

    with st.form("field_form"):
        col1, col2 = st.columns(2)
        with col1:
            field_choice = st.selectbox(
                t("Fältförslag", "Field suggestions"),
                field_suggestions,
                help=t("Skriv för att filtrera listan.", "Type to filter the list."),
            )
            field_name = st.text_input(
                t("Eget fältnamn", "Custom field name"),
                value="",
                placeholder=t("t.ex. Kornet 3", "e.g. Barley 3"),
            )
        with col2:
            location_choice = st.selectbox(
                t("Platsförslag (Sverige)", "Location suggestions (Sweden)"),
                SWEDISH_LOCATIONS,
                help=t("Skriv för att filtrera listan.", "Type to filter the list."),
            )
            location = st.text_input(
                t("Egen plats", "Custom location"),
                value="",
                placeholder=t("t.ex. Uppsala, SE", "e.g. Uppsala, SE"),
            )

        submitted = st.form_submit_button(t("Ladda översikt", "Load overview"))

    if not submitted:
        st.info(t("Fyll i ett fält och en plats, och klicka sedan på **Ladda översikt**.", "Enter a field and location, then **Load overview**."))
        return

    final_field = field_name.strip() or field_choice.strip()
    final_location = location.strip() or location_choice.strip()

    if not final_field or not final_location:
        st.warning(t("Fyll i både fält och plats.", "Please enter both field and location."))
        return

    api_key = openweather_api_key()
    if not api_key:
        st.error(
            t(
                "Lägg in din OpenWeather API-nyckel: sätt **`OPENWEATHER_API_KEY`** i "
                "`.streamlit/secrets.toml` eller som miljövariabel.",
                "Add your OpenWeather API key: set **`OPENWEATHER_API_KEY`** in "
                "`.streamlit/secrets.toml` or as an environment variable.",
            )
        )
        return

    q = final_location
    with st.spinner(t("Hämtar väder…", "Fetching weather…")):
        try:
            current = fetch_openweather_current(q, api_key)
            forecast = fetch_openweather_forecast(q, api_key)
        except WeatherAPIError as e:
            st.error(e.args[0] if e.args else t("Väderförfrågan misslyckades.", "Weather request failed."))
            return
        except requests.RequestException:
            st.error(
                t(
                    "Kunde inte nå OpenWeather. Kontrollera din internetanslutning och försök igen.",
                    "Could not reach OpenWeather. Check your connection and try again.",
                )
            )
            return

    name = (current.get("name") or q).strip()
    country = (current.get("sys") or {}).get("country") or ""
    resolved_label = f"{name}, {country}" if country else name

    main = current.get("main") or {}
    temp = main.get("temp")
    rain_mm, _ = current_rainfall_mm(current)
    wx0 = (current.get("weather") or [{}])[0]
    sky = (wx0.get("description") or "—").title()

    seed = f"{final_field.strip()}|{resolved_label}"
    veg_frames = {
        name: mock_index_series(seed, name, 30, lo, hi)
        for name, lo, hi, _, _, _, _ in VEGETATION_INDEX_SPECS
    }
    soil = mock_soil_metrics(seed)
    forest_pct = mock_forest_cover_pct(seed)
    confidence_pct = mock_data_confidence_pct(seed)
    latest_ndvi = float(veg_frames["NDVI"]["value"].iloc[-1])
    health_label, health_color = health_from_ndvi(latest_ndvi)
    health_dot = {"green": "🟢", "orange": "🟡", "red": "🔴"}[health_color]

    forecast_df = forecast_daily_table(forecast)
    rain_for_trend = forecast_daily_rain_mm_ordered(forecast)

    st.divider()

    st.caption(
        t(
            "ℹ️ Håll muspekaren över frågetecknet (?) bredvid en siffra för en kort förklaring.",
            "ℹ️ Hover the question mark (?) next to a figure for a short explanation.",
        )
    )

    # 1 — Header: field, location, status
    st.markdown(f"## {final_field.strip()}")
    st.caption(resolved_label)
    st.markdown(
        f"{health_dot} **{t('Status', 'Status')}:** {health_label} · "
        f"{t('NDVI', 'NDVI')} {latest_ndvi:.2f} ({t('sim.', 'sim.')})"
    )
    st.caption(fh("field_status"))

    st.divider()

    # 2 — Weather
    st.markdown(t("### 🌤️ Väder", "### 🌤️ Weather"))
    w1, w2, w3 = st.columns(3)
    w1.metric(
        t("Temperatur ℹ️", "Temperature ℹ️"),
        f"{temp:.1f} °C" if temp is not None else "—",
        help=fh("temperature"),
    )
    rain_label = f"{rain_mm:.1f} mm" if rain_mm > 0 else "0 mm"
    w2.metric(
        t("Nederbörd (nu) ℹ️", "Rain (now) ℹ️"),
        rain_label,
        help=fh("rain_now"),
    )
    w3.metric(
        t("Förhållanden ℹ️", "Conditions ℹ️"),
        sky,
        help=fh("conditions"),
    )
    st.markdown(t("**5 dagar framåt**", "**Next 5 days**"))
    if forecast_df.empty:
        st.caption(t("Ingen prognosdata.", "No forecast data."))
    else:
        st.caption(fh("forecast_table"))
        st.dataframe(forecast_df, hide_index=True, use_container_width=True)

    st.divider()

    # 3 — Vegetation
    st.markdown(t("### 🌿 Vegetation", "### 🌿 Vegetation"))
    ndvi_df = veg_frames["NDVI"]
    evi_df = veg_frames["EVI"]
    ndwi_df = veg_frames["NDWI"]
    v1, v2, v3 = st.columns(3)
    v1.metric(
        t("NDVI ℹ️", "NDVI ℹ️"),
        f"{float(ndvi_df['value'].iloc[-1]):.2f}",
        help=fh("ndvi"),
    )
    v2.metric(
        t("EVI ℹ️", "EVI ℹ️"),
        f"{float(evi_df['value'].iloc[-1]):.2f}",
        help=fh("evi"),
    )
    v3.metric(
        t("NDWI ℹ️", "NDWI ℹ️"),
        f"{float(ndwi_df['value'].iloc[-1]):.3f}",
        help=fh("ndwi"),
    )
    veg_chart = pd.DataFrame(
        {
            "NDVI": ndvi_df["value"].values,
            "EVI": evi_df["value"].values,
            "NDWI": ndwi_df["value"].values,
        },
        index=ndvi_df["date"],
    )
    st.line_chart(veg_chart, height=200)
    st.caption(
        t(
            "NDVI ≈ grön vegetation, EVI tätare grönska, NDWI vatten/fukt i bilden — simulerat, 30 dagar.",
            "NDVI ≈ green vegetation, EVI denser greenness, NDWI water/moisture signal — simulated, 30 days.",
        )
    )

    st.divider()

    # 4 — Soil
    st.markdown(t("### 🪴 Jord", "### 🪴 Soil"))
    ph_sv, ph_en = soil_ph_level(soil["ph"])
    oc_sv, oc_en = soil_oc_level(soil["organic_carbon_pct"])
    mo_sv, mo_en = soil_moist_level(soil["soil_moisture_pct"])
    s1, s2, s3 = st.columns(3)
    s1.metric(
        t("pH ℹ️", "pH ℹ️"),
        f"{soil['ph']:.1f} · {t(ph_sv, ph_en)}",
        help=fh("ph"),
    )
    s2.metric(
        t("Organiskt kol ℹ️", "Organic carbon ℹ️"),
        f"{soil['organic_carbon_pct']:.1f} % · {t(oc_sv, oc_en)}",
        help=fh("organic_carbon"),
    )
    s3.metric(
        t("Markfukt ℹ️", "Soil moisture ℹ️"),
        f"{soil['soil_moisture_pct']:.0f} % · {t(mo_sv, mo_en)}",
        help=fh("soil_moisture"),
    )

    if st.button(
        t("Förklara mitt fält enkelt", "Explain my field in simple terms"),
        key="btn_plain_field_explain",
    ):
        st.session_state["show_plain_field_explain"] = True

    if st.session_state["show_plain_field_explain"]:
        if st.session_state["lang"] == "sv":
            st.caption(
                t(
                    "Enkel sammanfattning på engelska (väder, NDVI, markfukt).",
                    "Simple summary in plain English (weather, NDVI, soil moisture).",
                )
            )
        st.markdown(plain_field_summary_english(
            temp,
            rain_mm,
            sky,
            latest_ndvi,
            soil["soil_moisture_pct"],
        ))
        if st.button(
            t("Dölj", "Hide"),
            key="btn_plain_field_explain_hide",
        ):
            st.session_state["show_plain_field_explain"] = False

    st.divider()

    # 5 — Forest
    st.markdown(t("### 🌲 Skogstäckning", "### 🌲 Forest cover"))
    st.metric(
        t("Andel skog ℹ️", "Forest share ℹ️"),
        f"{forest_pct:.1f} %",
        help=fh("forest"),
    )

    st.divider()

    # 6 — Trend
    st.markdown(t("### 📈 Trend", "### 📈 Trend"))
    st.caption(fh("trend"))
    st.write(trend_summary_ndvi_weather(ndvi_df, rain_for_trend))

    st.divider()

    # 7 — Confidence
    st.markdown(t("### 📌 Datatrohet", "### 📌 Data confidence"))
    st.metric(
        t("Trohetsgrad ℹ️", "Confidence ℹ️"),
        f"{confidence_pct} %",
        help=fh("confidence"),
    )

    st.divider()
    st.markdown(
        t("### 📖 Förstå dina fältdata", "### 📖 Understanding your field data")
    )
    st.markdown(farmer_glossary_markdown())


if __name__ == "__main__":
    main()
