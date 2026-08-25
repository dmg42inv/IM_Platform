from __future__ import annotations

import hmac
import json
import os
import re
import sqlite3
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_HISTORY_PATH = ROOT / "data" / "source_of_truth" / "Portfolio_Snapshot_History.xlsx"
MONTHLY_DIFF_PATH = ROOT / "data" / "outputs" / "Portfolio_Monthly_Diff.xlsx"
PORTFOLIO_DB_PATH = ROOT / "data" / "portfolio" / "portfolio.sqlite"
ACCOUNTS_ATTRS_PATH = ROOT / "data" / "outputs" / "accounts_team" / "accounts_attributes.json"
BASIS_BRIDGE_PATH = ROOT / "data" / "portfolio" / "basis_bridge.json"
SNAPSHOT_SHEET = "Portfolio_Snapshot_History"
MONTHLY_DIFF_SHEET = "Latest_Diff"
APP_TITLE = "Investments Portfolio"


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide", page_icon=":material/insights:",
                       initial_sidebar_state="collapsed")
    _inject_theme()
    _init_state()

    # Open access until credentials are configured (env vars or secrets.toml),
    # so the app can be shared before a username/password is agreed.
    expected_user, expected_password = _configured_credentials()
    if not (expected_user and expected_password):
        st.session_state["authenticated"] = True
        if not st.session_state.get("username"):
            st.session_state["username"] = "guest"

    if not st.session_state["authenticated"]:
        _render_login()
        return

    history = _load_snapshot_history(str(SNAPSHOT_HISTORY_PATH), _path_mtime(SNAPSHOT_HISTORY_PATH))
    monthly_diff = _load_monthly_diff(str(MONTHLY_DIFF_PATH), _path_mtime(MONTHLY_DIFF_PATH))
    months_df = _load_portfolio_months(str(PORTFOLIO_DB_PATH), _path_mtime(PORTFOLIO_DB_PATH))
    positions_df = _load_portfolio_positions(str(PORTFOLIO_DB_PATH), _path_mtime(PORTFOLIO_DB_PATH))
    _render_app(history, monthly_diff, months_df, positions_df)


_QUALIFIER_RE = re.compile(
    r"\s*\((?:\d+|warrant\s*\d+|debt|equity|fvoci|jv|world\s*coins?)\)\s*$", re.IGNORECASE)


def _consolidate_name(name: str) -> str:
    """Collapse instrument qualifiers so one company plots as one line
    (e.g. 'Cerebras Systems Inc (1)'/'(2)' -> 'Cerebras Systems Inc')."""
    s = str(name or "").strip()
    prev = None
    while s != prev:
        prev = s
        s = _QUALIFIER_RE.sub("", s).strip()
    return s or str(name or "").strip()


def _inject_theme() -> None:
    """Structural chrome only — palette (light/dark) and Garamond come from
    .streamlit/config.toml. A few theme-aware touches (3D boxes) use the active
    theme type so the panel fill is right in both modes."""
    try:
        dark = getattr(st.context.theme, "type", "light") == "dark"
    except Exception:  # noqa: BLE001 - context may be unavailable
        dark = False
    box_bg = "#1E2C25" if dark else "#EEF4EC"
    box_shadow = "0 10px 26px rgba(0,0,0,.50)" if dark else "0 10px 24px rgba(34,48,42,.17)"
    metric_shadow = "0 4px 14px rgba(0,0,0,.40)" if dark else "0 4px 12px rgba(34,48,42,.12)"
    st.markdown(
        f"""
        <style>
        section[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {{ display:none !important; }}
        /* Keep the top-right menu (Settings → light/dark theme) reachable; hide only Deploy. */
        [data-testid="stAppDeployButton"] {{ display:none !important; }}
        [data-testid="stHeader"] {{ background:transparent; }}
        .block-container {{ padding-top:1.1rem; max-width:1520px; }}
        [data-testid="stIconMaterial"] {{ font-family:'Material Symbols Rounded' !important; }}
        h1, h2, h3, h4 {{ letter-spacing:.2px; }}
        .g42-brand {{ display:flex; align-items:center; gap:11px; }}
        .g42-brand .g42-mark {{ font-weight:600; font-size:30px; color:#2F6B45;
            letter-spacing:.5px; line-height:1; }}
        .g42-brand .g42-title {{ font-weight:500; font-size:22px; opacity:.85; }}
        .g42-asof {{ opacity:.7; font-size:11.5px; text-transform:uppercase; letter-spacing:.06em; }}
        /* Right-align the header action buttons. */
        .st-key-hdr_theme, .st-key-hdr_signout {{ display:flex; justify-content:flex-end; }}
        /* 3D section boxes (bordered containers) and metric cards — theme-aware fill. */
        [data-testid="stVerticalBlockBorderWrapper"], .st-emotion-cache-1jffxlp {{
            background:{box_bg}; box-shadow:{box_shadow}; border-radius:14px;
            border:1px solid rgba(128,128,128,.16); }}
        [data-testid="stMetric"] {{ border-left:4px solid #2F6B45; background:{box_bg};
            box-shadow:{metric_shadow}; border-radius:12px; padding:12px 16px; }}
        [data-testid="stMetricLabel"] p {{ text-transform:uppercase; letter-spacing:.05em;
            font-size:11px; font-weight:700; opacity:.75; }}
        /* Keep KPI values on one line without ellipsis in narrow 5-across layouts. */
        [data-testid="stMetricValue"] {{ font-size:1.65rem; white-space:nowrap; overflow:visible; }}
        [data-testid="stMetricValue"] > div {{ overflow:visible; text-overflow:clip; }}
        .g42-tbl {{ width:100%; border-collapse:collapse; font-size:14px; margin-top:2px; }}
        .g42-tbl th, .g42-tbl td {{ text-align:center; padding:7px 10px;
            border-bottom:1px solid rgba(128,128,128,.22); }}
        .g42-tbl th {{ font-weight:700; opacity:.7; text-transform:uppercase;
            font-size:11px; letter-spacing:.04em; }}
        /* Nav styled as folder/binder tabs so it reads differently from the scope filter below. */
        .st-key-nav_section [data-testid="stButtonGroup"] {{ background:transparent !important;
            border-bottom:2px solid #2F6B45; gap:4px; padding:0; flex-wrap:wrap; }}
        .st-key-nav_section button[data-variant="segmented_control"] {{
            border-radius:11px 11px 0 0 !important; border:1px solid rgba(128,128,128,.22) !important;
            border-bottom:none !important; margin-bottom:-2px !important; padding:9px 16px !important;
            background:rgba(128,128,128,.09) !important; }}
        .st-key-nav_section button[data-variant="segmented_control"][aria-checked="true"] {{
            background:#2F6B45 !important; color:#ffffff !important; border-color:#2F6B45 !important; }}
        /* Mark the four original sections (positions 2-5) in orange so they are easy to spot. */
        .st-key-nav_section button[data-variant="segmented_control"]:nth-of-type(n+2):nth-of-type(-n+5) {{
            background:#FBEBD8 !important; color:#B25A12 !important; border-color:#E8A867 !important; }}
        .st-key-nav_section button[data-variant="segmented_control"]:nth-of-type(n+2):nth-of-type(-n+5)[aria-checked="true"] {{
            background:#E07B1A !important; color:#ffffff !important; border-color:#E07B1A !important; }}
        /* Book of Record view band — same binder/folder-tab style as the section nav. */
        .st-key-bor_view [data-testid="stButtonGroup"] {{ background:transparent !important;
            border-bottom:2px solid #2F6B45; gap:4px; padding:0; flex-wrap:wrap; }}
        .st-key-bor_view button[data-variant="segmented_control"] {{
            border-radius:11px 11px 0 0 !important; border:1px solid rgba(128,128,128,.22) !important;
            border-bottom:none !important; margin-bottom:-2px !important; padding:9px 16px !important;
            background:rgba(128,128,128,.09) !important; }}
        .st-key-bor_view button[data-variant="segmented_control"][aria-checked="true"] {{
            background:#2F6B45 !important; color:#ffffff !important; border-color:#2F6B45 !important; }}
        .conf-badge {{ background:#b3253a; color:#fff; font-size:10px; font-weight:700;
            letter-spacing:.08em; padding:2px 8px; border-radius:4px; margin-left:10px;
            vertical-align:middle; text-transform:uppercase; }}
        /* Company-details left rail: name buttons rendered as a clean vertical list. */
        [class*="st-key-borco_"] button {{ justify-content:flex-start !important;
            text-align:left !important; padding:5px 12px !important; font-size:13px !important;
            min-height:0 !important; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


NAV_SECTIONS = ["Overview", "Portfolio", "Company Profiles", "Historical", "Accounts team",
                "Analytics", "Misc", "Parking"]

# Sections whose figures are position-derived, so the entity scope filter applies.
_SCOPED_SECTIONS = {"Overview", "Company Profiles", "Historical", "Analytics"}
_SCOPE_OPTIONS = ["Consolidated", "G42", "MOZN", "MGX"]


def _scope_mask(df: pd.DataFrame, scope: str) -> pd.Series:
    """Entity scope from the tracker's own holding-company (section)/entity fields.
    MOZN and MGX are the two named sub-books; G42 = everything that isn't MOZN
    (MGX sits inside G42); Consolidated = all."""
    sec = df["section"].astype(str).str.upper()
    is_mozn = sec.str.contains("MOZN", na=False)
    is_mgx = sec.str.contains("MGX", na=False) | df["deal_type"].astype(str).str.upper().str.startswith("MGX")
    if scope == "MOZN":
        return is_mozn
    if scope == "MGX":
        return is_mgx
    if scope == "G42":
        return ~is_mozn
    return pd.Series(True, index=df.index)


def _scoped_positions(positions_df: pd.DataFrame, scope: str) -> pd.DataFrame:
    if scope == "Consolidated" or positions_df.empty:
        return positions_df
    return positions_df[_scope_mask(positions_df, scope)].copy()


def _scoped_months(months_df: pd.DataFrame, positions_df: pd.DataFrame, scope: str) -> pd.DataFrame:
    """Per-month totals recomputed for the chosen entity, matching the columns of
    the consolidated months table so every downstream chart just works."""
    if scope == "Consolidated" or positions_df.empty:
        return months_df
    p = _scoped_positions(positions_df, scope)
    live = p[p["tab"] == "Live"]
    exi = p[p["tab"] == "Exited"]
    agg = (live.groupby("month_id")
           .agg(as_of_date=("as_of_date", "first"),
                live_count=("deal_name", "nunique"),
                live_invested=("invested", "sum"),
                live_carrying=("carrying_value", "sum"),
                live_gain=("gain", "sum")).reset_index())
    ex = exi.groupby("month_id")["deal_name"].nunique().rename("exited_count").reset_index()
    out = agg.merge(ex, on="month_id", how="left")
    out = out.merge(months_df[["month_id", "label"]], on="month_id", how="left")
    out["exited_count"] = out["exited_count"].fillna(0).astype(int)
    return out.sort_values("month_id").reset_index(drop=True)


def _render_header(months_df: pd.DataFrame, positions_df: pd.DataFrame) -> tuple[str, str]:
    """Top bar: brand + guest/sign-out on one line; full-width section nav below;
    a persistent entity-scope control on the sections it applies to."""
    as_of = ""
    if len(months_df):
        latest = months_df.sort_values("month_id").iloc[-1]
        d = pd.to_datetime(latest["as_of_date"], errors="coerce")
        as_of = d.strftime("%d %b %Y") if pd.notna(d) else str(latest.get("label", ""))
    top = st.columns([7, 1.1, 1.1], vertical_alignment="center")
    with top[0]:
        st.markdown(
            "<div class='g42-brand'><span class='g42-mark'>G42</span>"
            "<span class='g42-title'>Investments Portfolio</span></div>",
            unsafe_allow_html=True)
    with top[1]:
        if st.button("Theme", key="hdr_theme", icon=":material/brightness_6:"):
            st.session_state["_flip_theme"] = True
    with top[2]:
        if st.button("Sign out", key="hdr_signout", icon=":material/logout:"):
            st.session_state["authenticated"] = False
            st.session_state["username"] = ""
            st.rerun()
    # Toggle the native Streamlit theme by flipping its localStorage key, then reload.
    if st.session_state.pop("_flip_theme", False):
        components.html(
            "<script>const k='stActiveTheme-/-v2';const ls=window.parent.localStorage;"
            "let c='Light';try{c=JSON.parse(ls.getItem(k)||'\"Light\"');}catch(e){}"
            "ls.setItem(k,JSON.stringify(c==='Dark'?'Light':'Dark'));"
            "window.parent.location.reload();</script>", height=0)
    # Nav on its own full-width row so all items lay out without wrapping/overlap.
    section = st.segmented_control(
        "nav", NAV_SECTIONS, default="Overview",
        label_visibility="collapsed", key="nav_section") or "Overview"
    scope = "Consolidated"
    if section in _SCOPED_SECTIONS:
        if section == "Overview":
            # Overview renders the scope tabs beside its own title, not here.
            scope = st.session_state.get("scope_sel", "Consolidated") or "Consolidated"
        else:
            scope = st.segmented_control(
                "Entity scope", _SCOPE_OPTIONS, default="Consolidated",
                key="scope_sel", label_visibility="collapsed") or "Consolidated"
    st.markdown("<hr style='margin:8px 0 16px;border-top:2px solid #2F6B45'>", unsafe_allow_html=True)
    return section, scope


def _init_state() -> None:
    st.session_state.setdefault("authenticated", False)
    st.session_state.setdefault("username", "")


def _render_login() -> None:
    st.title(APP_TITLE)
    st.caption("Local access to saved monthly portfolio snapshots.")

    expected_user, expected_password = _configured_credentials()
    if not expected_user or not expected_password:
        st.error("Login is not configured for this local app.")
        st.markdown(
            "Set `IM_PLATFORM_APP_USER` and `IM_PLATFORM_APP_PASSWORD`, or create "
            "`.streamlit/secrets.toml` from `.streamlit/secrets.example.toml`."
        )
        st.stop()

    with st.form("login", border=True):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", icon=":material/login:")

    if not submitted:
        return

    user_ok = hmac.compare_digest(username, expected_user)
    password_ok = hmac.compare_digest(password, expected_password)
    if user_ok and password_ok:
        st.session_state["authenticated"] = True
        st.session_state["username"] = username
        st.rerun()

    st.error("Invalid username or password.")


def _configured_credentials() -> tuple[str, str]:
    secrets_user = ""
    secrets_password = ""
    try:
        auth = st.secrets.get("auth", {})
        secrets_user = str(auth.get("username", ""))
        secrets_password = str(auth.get("password", ""))
    except Exception:
        pass

    return (
        os.environ.get("IM_PLATFORM_APP_USER", secrets_user),
        os.environ.get("IM_PLATFORM_APP_PASSWORD", secrets_password),
    )


@st.cache_data(show_spinner=False)
def _load_snapshot_history(path: str, mtime_ns: int) -> pd.DataFrame:
    del mtime_ns
    workbook = Path(path)
    if not workbook.exists():
        return pd.DataFrame()
    history = pd.read_excel(workbook, sheet_name=SNAPSHOT_SHEET).fillna("")
    for col in [
        "committed",
        "invested",
        "remaining_commitment",
        "distributions",
        "carrying_value",
        "gain",
        "tvpi",
        "irr",
    ]:
        if col in history.columns:
            history[col] = pd.to_numeric(history[col], errors="coerce")
    return history


@st.cache_data(show_spinner=False)
def _load_monthly_diff(path: str, mtime_ns: int) -> pd.DataFrame:
    del mtime_ns
    workbook = Path(path)
    if not workbook.exists():
        return pd.DataFrame()
    diff = pd.read_excel(workbook, sheet_name=MONTHLY_DIFF_SHEET).fillna("")
    numeric_cols = {
        "previous_committed", "previous_invested", "previous_remaining_commitment",
        "previous_distributions", "previous_carrying_value", "previous_gain", "previous_tvpi", "previous_irr",
        "current_committed", "current_invested", "current_remaining_commitment",
        "current_distributions", "current_carrying_value", "current_gain", "current_tvpi", "current_irr",
        "delta_committed", "delta_invested", "delta_remaining_commitment",
        "delta_distributions", "delta_carrying_value", "delta_gain", "delta_tvpi", "delta_irr",
    }
    for col in numeric_cols.intersection(diff.columns):
            diff[col] = pd.to_numeric(diff[col], errors="coerce")
    return diff


def _path_mtime(path: Path) -> int:
    return path.stat().st_mtime_ns if path.exists() else 0


@st.cache_data(show_spinner=False)
def _load_portfolio_months(path: str, mtime_ns: int) -> pd.DataFrame:
    """Per-month portfolio totals from the time-series DB (parsed months only)."""
    del mtime_ns
    if not Path(path).exists():
        return pd.DataFrame()
    with sqlite3.connect(path) as conn:
        df = pd.read_sql_query(
            "SELECT month_id, as_of_date, label, live_count, exited_count, "
            "live_invested, live_carrying, live_gain FROM tracker_months "
            "WHERE parsed_ok = 1 ORDER BY month_id",
            conn,
        )
    if len(df):
        df["as_of_date"] = pd.to_datetime(df["as_of_date"], errors="coerce")
    return df


@st.cache_data(show_spinner=False)
def _load_portfolio_positions(path: str, mtime_ns: int) -> pd.DataFrame:
    """One row per deal per month, for the snapshot table and NAV explorer."""
    del mtime_ns
    if not Path(path).exists():
        return pd.DataFrame()
    with sqlite3.connect(path) as conn:
        df = pd.read_sql_query(
            "SELECT month_id, as_of_date, tab, section, deal_name, status, "
            "investing_entity, vintage, instrument, geography, sector, deal_type, "
            "committed, invested, remaining_commitment, distributions, "
            "carrying_value, gain, tvpi, notes "
            "FROM monthly_positions",
            conn,
        )
    if len(df):
        df["as_of_date"] = pd.to_datetime(df["as_of_date"], errors="coerce")
        for col in ("committed", "invested", "remaining_commitment",
                    "distributions", "carrying_value", "gain", "tvpi"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(show_spinner=False)
def _load_accounts_attrs(mtime_ns: int) -> list[dict]:
    """Accounts-team per-holding attributes (IFRS class, valuation method, etc.),
    parsed from their Pack. Their remit; adopted as classification only."""
    del mtime_ns
    if not ACCOUNTS_ATTRS_PATH.exists():
        return []
    return json.loads(ACCOUNTS_ATTRS_PATH.read_text(encoding="utf-8"))


@st.cache_data(show_spinner=False)
def _load_basis_bridge(mtime_ns: int) -> dict:
    """Per-holding reconciliation between the Live-register and NAV+CAS bases."""
    del mtime_ns
    if not BASIS_BRIDGE_PATH.exists():
        return {}
    return json.loads(BASIS_BRIDGE_PATH.read_text(encoding="utf-8"))


def _norm_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


@st.cache_data(show_spinner=False)
def _accounts_by_key(mtime_ns: int) -> dict:
    attrs = _load_accounts_attrs(mtime_ns)
    return {_norm_key(r.get("name", "")): r for r in attrs}


def _lookup_accounts(name: str) -> dict:
    by_key = _accounts_by_key(_path_mtime(ACCOUNTS_ATTRS_PATH))
    k = _norm_key(name)
    hit = by_key.get(k)
    if not hit and k:
        hit = next((v for kk, v in by_key.items() if k in kk or kk in k), None)
    return hit or {}


def _attach_accounts_attrs(live: pd.DataFrame) -> pd.DataFrame:
    """Add the accounts team's classification attributes to each live holding,
    matched by normalised name. Unmatched holdings show 'Pending'."""
    lc = live.copy()
    recs = [_lookup_accounts(n) for n in lc["deal_name"]]
    lc["ifrs_class"] = [(r.get("IFRS classification") or "Pending") for r in recs]
    lc["valuation_method"] = [(r.get("Valuation method") or "Pending") for r in recs]
    lc["fv_hierarchy"] = [(r.get("Fair value hierarchy") or "Pending") for r in recs]
    lc["valuation_basis"] = [(r.get("Valuation basis") or "Pending") for r in recs]
    return lc


def _render_app(history: pd.DataFrame, monthly_diff: pd.DataFrame,
                months_df: pd.DataFrame, positions_df: pd.DataFrame) -> None:
    label_map = dict(zip(months_df["month_id"], months_df["label"])) if len(months_df) else {}
    section, scope = _render_header(months_df, positions_df)
    # Entity-scoped frames for the position-derived views.
    s_months = _scoped_months(months_df, positions_df, scope)
    s_positions = _scoped_positions(positions_df, scope)

    if section == "Portfolio":
        _render_current_month()
        return
    if section == "Company Profiles":
        _render_company_profiles(s_months, s_positions)
        return
    if section == "Accounts team":
        _render_accounts_team()
        return
    if section == "Overview":
        _render_ov_overview(s_months, s_positions)
        return
    if section == "Analytics":
        _render_ov_analytics(s_months, s_positions)
        return
    if section == "Misc":
        _render_misc(months_df, positions_df)
        return
    if section == "Parking":
        _render_parking()
        return

    # Historical
    sub = st.segmented_control(
        "Historical view", ["NAV evolution", "Snapshot", "Monthly diff"],
        default="NAV evolution", key="hist_view", label_visibility="collapsed") or "NAV evolution"

    if sub == "NAV evolution":
        _render_nav_evolution(s_months, s_positions)
        return
    if sub == "Monthly diff":
        _render_monthly_diff_celllevel(s_positions, s_months)
        return

    if s_months.empty or s_positions.empty:
        st.info("No portfolio database found yet. Run the tracker ingester to build it.")
        st.stop()
    month_opts = list(s_months.sort_values("month_id", ascending=False)["month_id"])
    pick = st.columns([1.6, 1.6, 5], vertical_alignment="bottom")
    with pick[0]:
        selected_month = st.selectbox("Month", month_opts, format_func=lambda m: label_map.get(m, m))
    with pick[1]:
        status_filter = st.segmented_control(
            "Show", ["All", "Live", "Exited"], default="All", key="snap_status") or "All"
    month_snapshot = s_positions[s_positions["month_id"] == selected_month].copy()
    if status_filter != "All":
        month_snapshot = month_snapshot[month_snapshot["tab"] == status_filter].copy()

    st.subheader(f"Portfolio snapshot \u2014 {label_map.get(selected_month, selected_month)}")
    st.caption("Figures are USD millions unless noted. Source: portfolio time-series database.")

    _render_kpis(month_snapshot)
    _render_snapshot_table(month_snapshot)


def _render_company_profiles(months_df: pd.DataFrame, positions_df: pd.DataFrame) -> None:
    """Grounded per-company detail (identity, economics, carry history, cited cash
    movements) followed by the visual one-pagers from the tracker embed."""
    st.markdown("<h2 class='g42-serif'>Company profiles</h2>", unsafe_allow_html=True)
    if not positions_df.empty:
        # Full investment register (every holding in scope) — sortable, exportable.
        m0 = _latest_month(months_df)
        reg = positions_df[positions_df["month_id"] == m0].copy()
        with st.container(border=True):
            st.subheader("Investment register")
            regview = (reg[["deal_name", "tab", "investing_entity", "geography", "sector",
                            "instrument", "vintage", "invested", "distributions",
                            "carrying_value", "gain", "tvpi"]]
                       .sort_values(["tab", "carrying_value"], ascending=[False, False]))
            st.dataframe(regview, hide_index=True, width="stretch", column_config={
                "deal_name": st.column_config.TextColumn("Holding"),
                "tab": st.column_config.TextColumn("Status"),
                "investing_entity": st.column_config.TextColumn("Entity"),
                "geography": st.column_config.TextColumn("Geography"),
                "sector": st.column_config.TextColumn("Sector"),
                "instrument": st.column_config.TextColumn("Instrument"),
                "vintage": st.column_config.TextColumn("Vintage"),
                "invested": st.column_config.NumberColumn("Invested", format="$%.1f"),
                "distributions": st.column_config.NumberColumn("Distributions", format="$%.1f"),
                "carrying_value": st.column_config.NumberColumn("Fair value", format="$%.1f"),
                "gain": st.column_config.NumberColumn("Value created", format="$%.1f"),
                "tvpi": st.column_config.NumberColumn("TVPI", format="%.2fx"),
            })
            st.caption(f"Every holding in scope, as of {dict(zip(months_df['month_id'], months_df['label'])).get(m0, m0)}. "
                       f"Sort any column; search and download via the table toolbar. USD millions.")

        facts, dom = _load_company_facts(), _load_domicile_legal()
        pos = positions_df.copy()
        pos["company"] = pos["deal_name"].map(_consolidate_name)
        companies = sorted(pos["company"].dropna().unique())
        company = st.selectbox("Company", companies, key="co_pick")
        sub = pos[pos["company"] == company]
        m = _latest_month(months_df)
        latest = sub[sub["month_id"] == m]
        fact = {**facts.get(company.strip().lower(), {}), **(dom.get(company.strip().lower()) or {})}

        def _first(col: str) -> str:
            vals = [v for v in latest[col].tolist() if str(v).strip()] if len(latest) else []
            return vals[0] if vals else ""

        st.subheader(company)
        if fact.get("description"):
            st.write(f"{fact['description']}  \n_source: {fact.get('source', 'pending')}_")
        idc = st.columns(4)
        idc[0].metric("Sector", _first("sector") or fact.get("sector") or "\u2014")
        idc[1].metric("Geography", _first("geography") or fact.get("hq") or "\u2014")
        dom_v = fact.get("domicile")
        idc[2].metric("Domicile", dom_v or "\u2014")
        idc[3].metric("Instrument", _first("instrument") or "\u2014")
        if dom_v:
            st.caption(f"Domicile source: {fact.get('domicile_source', 'legal docs')} (candidate \u2014 confirm).")

        with st.container(horizontal=True):
            st.metric("Invested", _fmt_money(latest["invested"].sum()), border=True)
            st.metric("Fair value", _fmt_money(latest["carrying_value"].sum()), border=True)
            st.metric("Distributions", _fmt_money(latest["distributions"].sum()), border=True)
            st.metric("Gain", _fmt_money(latest["gain"].sum()), border=True)

        with st.container(border=True):
            st.subheader("Carrying value history")
            st.line_chart(sub.groupby("as_of_date")["carrying_value"].sum().rename("Fair value"),
                          height=240, x_label="Month", y_label="Fair value, USD m")

        cf = _load_cashflows(str(PORTFOLIO_DB_PATH), _path_mtime(PORTFOLIO_DB_PATH))
        if len(cf):
            cf = cf.copy()
            cf["company"] = cf["deal_name"].map(_consolidate_name)
            cfc = cf[cf["company"] == company].sort_values("flow_date")
            if len(cfc):
                with st.container(border=True):
                    st.subheader("Cash movements \u2014 cited to source cell")
                    view = cfc[["flow_date", "accounting_entity", "contribution", "distribution",
                                "currency", "sheet", "excel_row", "filename"]].copy()
                    view["cell"] = view["sheet"].astype(str) + "!row" + view["excel_row"].astype(str)
                    view = view.drop(columns=["sheet", "excel_row"])
                    st.dataframe(view, hide_index=True, width="stretch", column_config={
                        "flow_date": st.column_config.TextColumn("Date"),
                        "accounting_entity": st.column_config.TextColumn("Entity"),
                        "contribution": st.column_config.NumberColumn("Contribution", format="%.2f"),
                        "distribution": st.column_config.NumberColumn("Distribution", format="%.2f"),
                        "cell": st.column_config.TextColumn("Source cell"),
                        "filename": st.column_config.TextColumn("Source file"),
                    })

    st.markdown("<hr style='margin:18px 0;border-top:1px solid #E4E0D0'>", unsafe_allow_html=True)
    st.caption("Visual one-pagers (from the Portfolio Summary):")
    html_path = ROOT / "data" / "outputs" / "Tracker_Style_Dashboard.html"
    if not html_path.exists():
        st.info("Tracker dashboard not generated yet.")
        return
    html = html_path.read_text(encoding="utf-8")
    # The companies nav button was removed from the tracker; reveal the panel directly.
    html += ("<script>window.addEventListener('load',function(){"
             "document.querySelectorAll('section.tab').forEach(function(s){s.classList.remove('active');});"
             "var c=document.getElementById('companies');if(c){c.classList.add('active');}});</script>")
    components.html(html, height=1600, scrolling=True)


def _render_accounts_team() -> None:
    st.markdown("<h2 class='g42-serif'>Accounts team pack</h2>", unsafe_allow_html=True)
    pack = ROOT / "data" / "outputs" / "accounts_team" / "G42_Accounts_Pack.html"
    if not pack.exists():
        st.info("Accounts team pack not loaded yet.")
        return
    components.html(pack.read_text(encoding="utf-8"), height=1700, scrolling=True)


_DIFF_METRICS = [
    ("committed", "Committed"), ("invested", "Invested"),
    ("distributions", "Distributions"), ("carrying_value", "Carrying value"),
    ("gain", "Gain"), ("tvpi", "TVPI"),
]


def _render_monthly_diff_celllevel(positions_df: pd.DataFrame, months_df: pd.DataFrame) -> None:
    st.markdown("<h2 class='g42-serif'>Monthly diff \u2014 cell-level changes</h2>", unsafe_allow_html=True)
    if months_df.empty or positions_df.empty or len(months_df) < 2:
        st.info("Need at least two months in the database.")
        return
    ordered = list(months_df.sort_values("month_id")["month_id"])
    label_map = dict(zip(months_df["month_id"], months_df["label"]))
    cur, prev = ordered[-1], ordered[-2]
    st.caption(f"{label_map.get(prev, prev)} \u2192 {label_map.get(cur, cur)}. "
               "Each row is a single changed value, traceable to the tracker.")

    cur_df = (positions_df[positions_df["month_id"] == cur]
              .drop_duplicates("deal_name").set_index("deal_name"))
    prev_df = (positions_df[positions_df["month_id"] == prev]
               .drop_duplicates("deal_name").set_index("deal_name"))
    rows = []
    for deal in sorted(set(cur_df.index) | set(prev_df.index)):
        in_cur, in_prev = deal in cur_df.index, deal in prev_df.index
        if in_cur and not in_prev:
            rows.append({"Deal": deal, "Metric": "\u2014", "Status": "New",
                         "Previous": None, "Current": None, "Change": None})
            continue
        if in_prev and not in_cur:
            rows.append({"Deal": deal, "Metric": "\u2014", "Status": "Removed",
                         "Previous": None, "Current": None, "Change": None})
            continue
        for key, label in _DIFF_METRICS:
            pv = pd.to_numeric(prev_df.loc[deal, key], errors="coerce") if key in prev_df.columns else None
            cv = pd.to_numeric(cur_df.loc[deal, key], errors="coerce") if key in cur_df.columns else None
            pvv = 0.0 if pv is None or pd.isna(pv) else float(pv)
            cvv = 0.0 if cv is None or pd.isna(cv) else float(cv)
            if abs(cvv - pvv) < 1e-9:
                continue
            rows.append({"Deal": deal, "Metric": label, "Status": "Changed",
                         "Previous": round(pvv, 2), "Current": round(cvv, 2),
                         "Change": round(cvv - pvv, 2)})
    if not rows:
        st.success("No changes between the two most recent months.")
        return
    diff = pd.DataFrame(rows)
    changed = diff[diff["Status"] == "Changed"]
    with st.container(horizontal=True):
        st.metric("Changed cells", f"{len(changed):,}", border=True)
        st.metric("Carrying value \u0394",
                  _fmt_money(changed[changed["Metric"] == "Carrying value"]["Change"].sum()), border=True)
        st.metric("New / removed",
                  f"{int((diff['Status'] == 'New').sum())} / {int((diff['Status'] == 'Removed').sum())}",
                  border=True)
    with st.container(border=True):
        st.dataframe(
            diff, hide_index=True, width="stretch",
            column_config={
                "Previous": st.column_config.NumberColumn("Previous", format="%.2f"),
                "Current": st.column_config.NumberColumn("Current", format="%.2f"),
                "Change": st.column_config.NumberColumn("Change", format="%.2f"),
            },
        )
        st.download_button(
            "Download cell-level diff", diff.to_csv(index=False).encode("utf-8"),
            file_name="monthly_cell_diff.csv", mime="text/csv", icon=":material/download:")


def _load_company_facts() -> dict:
    try:
        with open("data/source_of_truth/company_descriptive_facts.json", encoding="utf-8") as fh:
            data = json.load(fh)
        return {str(k).strip().lower(): v for k, v in data.items() if not str(k).startswith("_")}
    except Exception:  # noqa: BLE001 - optional file
        return {}


def _load_domicile_legal() -> dict:
    try:
        with open("data/source_of_truth/company_domicile_legal.json", encoding="utf-8") as fh:
            data = json.load(fh)
        return {str(k).strip().lower(): v for k, v in data.items() if not str(k).startswith("_")}
    except Exception:  # noqa: BLE001 - optional file
        return {}


def _line_usd(df: pd.DataFrame, xcol: str, ycol: str, y_title: str = "USD, millions") -> None:
    d = df[[xcol, ycol]].dropna().copy()
    d.columns = ["date", "value"]
    chart = (alt.Chart(d).mark_area(
                color="#2F6B45", opacity=0.16,
                line={"color": "#2F6B45", "strokeWidth": 2})
             .encode(
                x=alt.X("date:T", axis=alt.Axis(title=None, format="%b '%y", labelAngle=-40)),
                y=alt.Y("value:Q", axis=alt.Axis(title=y_title)))
             .properties(height=280))
    st.altair_chart(chart, width="stretch")


# TEMP (2026-08-24, user-approved): FY2020/FY2021 have no tracker data yet. Until
# the user supplies real FY20/FY21 investment NAVs, estimate each year-end by
# taking the earliest real snapshot (Sep'22 live rows), keeping only investments
# whose vintage year <= that year, valued at their earliest tracker carrying
# value (or at cost where that is 0/unknown). Display-only; never fed back into
# the grounded figures or reconciliation. REPLACE with actuals when provided.
def _fy_backfill_points(positions_df: pd.DataFrame) -> pd.DataFrame:
    if positions_df.empty:
        return pd.DataFrame()
    first_m = positions_df["month_id"].min()
    snap = positions_df[(positions_df["month_id"] == first_m) & (positions_df["tab"] == "Live")].copy()
    if snap.empty:
        return pd.DataFrame()
    snap["vy"] = pd.to_numeric(snap["vintage"].astype(str).str.extract(r"(\d{4})")[0], errors="coerce")
    val = snap["carrying_value"].where(snap["carrying_value"] > 0, snap["invested"])
    snap["val"] = pd.to_numeric(val, errors="coerce").fillna(0.0)
    pts = []
    for fy, asof in ((2020, "2020-12-31"), (2021, "2021-12-31")):
        pts.append({"as_of_date": pd.Timestamp(asof),
                    "value": float(snap.loc[snap["vy"] <= fy, "val"].sum())})
    return pd.DataFrame(pts)


def _render_nav_since_inception(months_df: pd.DataFrame, positions_df: pd.DataFrame) -> None:
    """Tracker NAV since inception, with FY2020/FY2021 shown as a temporary
    estimate (dashed) until real NAVs for those years are provided."""
    real = (months_df.sort_values("month_id")[["as_of_date", "live_carrying"]]
            .rename(columns={"live_carrying": "value"}).dropna())
    real["date_lbl"] = pd.to_datetime(real["as_of_date"]).dt.strftime("%b %Y")
    real["value_lbl"] = real["value"].map(lambda v: f"${v:,.1f}m")
    est = _fy_backfill_points(positions_df)
    if len(est):
        est["date_lbl"] = pd.to_datetime(est["as_of_date"]).dt.strftime("%Y year-end")
        est["value_lbl"] = est["value"].map(lambda v: f"${v:,.1f}m")
    x = alt.X("as_of_date:T", axis=alt.Axis(title=None, format="%b '%y", labelAngle=-40))
    y = alt.Y("value:Q", axis=alt.Axis(title="USD, millions"))
    tip = [alt.Tooltip("date_lbl:N", title="As of"),
           alt.Tooltip("value_lbl:N", title="Fair value")]
    layers = []
    if len(est) and len(real):
        bridge = pd.concat([est, real.iloc[[0]][["as_of_date", "value"]]], ignore_index=True)
        full = pd.concat([est[["as_of_date", "value"]], real[["as_of_date", "value"]]],
                         ignore_index=True).sort_values("as_of_date")
        layers.append(alt.Chart(full).mark_area(color="#2F6B45", opacity=0.12).encode(x=x, y=y))
        layers.append(alt.Chart(bridge).mark_line(color="#B25A12", strokeWidth=2,
                      strokeDash=[5, 4]).encode(x=x, y=y))
        layers.append(alt.Chart(est).mark_point(color="#B25A12", filled=True, size=70).encode(
            x=x, y=y, tooltip=[alt.Tooltip("date_lbl:N", title="Year-end"),
                               alt.Tooltip("value_lbl:N", title="Estimated fair value")]))
    else:
        layers.append(alt.Chart(real).mark_area(color="#2F6B45", opacity=0.16,
                      line={"color": "#2F6B45", "strokeWidth": 2}).encode(x=x, y=y))
    layers.append(alt.Chart(real).mark_line(color="#2F6B45", strokeWidth=2).encode(x=x, y=y))
    # Invisible points give a clean, formatted hover across the real series.
    layers.append(alt.Chart(real).mark_circle(color="#2F6B45", opacity=0).encode(
        x=x, y=y, tooltip=tip))
    st.altair_chart(alt.layer(*layers).properties(height=280), width="stretch")
    if len(est):
        first_lbl = months_df.sort_values("month_id")["label"].iloc[0] if len(months_df) else "?"
        st.caption(f"FY2020 and FY2021 (dashed, orange) are a **temporary estimate** \u2014 "
                   f"investments made by each year-end, held at their earliest recorded NAV, or at "
                   f"cost where unknown. Actual recorded data starts {first_lbl}. Pending your real "
                   f"FY20/FY21 investment NAVs; positions exited before {first_lbl} are not yet included.")


@st.cache_data(show_spinner=False)
def _load_cashflows(path: str, mtime_ns: int) -> pd.DataFrame:
    del mtime_ns
    if not Path(path).exists():
        return pd.DataFrame()
    with sqlite3.connect(path) as conn:
        df = pd.read_sql_query(
            "SELECT cf.flow_date, cf.accounting_entity, cf.deal_name, cf.contribution, "
            "cf.distribution, cf.currency, cf.sheet, cf.excel_row, s.filename "
            "FROM cashflows cf LEFT JOIN sources s ON s.source_id = cf.source_id",
            conn,
        )
    for col in ("contribution", "distribution"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(show_spinner=False)
def _load_sources(path: str, mtime_ns: int) -> pd.DataFrame:
    del mtime_ns
    if not Path(path).exists():
        return pd.DataFrame()
    with sqlite3.connect(path) as conn:
        return pd.read_sql_query(
            "SELECT kind, filename, month_id, version, sha256, size_bytes, ingested_at "
            "FROM sources ORDER BY kind, month_id", conn)


def _latest_month(months_df: pd.DataFrame) -> str | None:
    if months_df.empty:
        return None
    return months_df.sort_values("month_id")["month_id"].iloc[-1]


# ---- New consolidated sections (built for review, alongside the existing tabs) ----

def _instrument_bucket(deal_type: str, instrument: str, sector: str) -> str:
    """Three-way split the way we hold capital: funds vs loans vs equity-like.
    Rule is deliberately explicit so the Overview breakdown is auditable."""
    dt, inst, sec = (str(deal_type or "").lower(), str(instrument or "").lower(),
                     str(sector or "").lower())
    if "fund" in dt or sec == "fund":
        return "Funds"
    if any(k in inst for k in ("note", "loan", "debt", "convertible", "bond")):
        return "Loans / debt-like"
    return "Equity / equity-like"


def _bar_h(df: pd.DataFrame, cat: str, val: str, x_title: str = "Fair value, USD m",
           height: int | None = None) -> None:
    h = height if height is not None else max(200, 30 * len(df))
    chart = (alt.Chart(df).mark_bar(color="#2F6B45", cornerRadiusEnd=3).encode(
                x=alt.X(f"{val}:Q", axis=alt.Axis(title=x_title, format=",.0f")),
                y=alt.Y(f"{cat}:N", sort="-x", axis=alt.Axis(title=None)),
                tooltip=[alt.Tooltip(f"{cat}:N", title=cat.replace('_', ' ').title()),
                         alt.Tooltip(f"{val}:Q", title=x_title, format="$,.1f")])
             .properties(height=h))
    st.altair_chart(chart, width="stretch")


def _html_table(df: pd.DataFrame, col_labels: dict, fmts: dict | None = None) -> None:
    """Centre-aligned HTML table (st.dataframe can't centre-align). Inherits the
    theme text colour so it works in both light and dark; loses interactive sort."""
    fmts = fmts or {}
    cols = list(col_labels.keys())
    head = "".join(f"<th>{col_labels[c]}</th>" for c in cols)
    body = []
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            cells.append("<td></td>" if pd.isna(v)
                         else f"<td>{fmts[c](v) if c in fmts else v}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    st.markdown(f"<table class='g42-tbl'><thead><tr>{head}</tr></thead>"
                f"<tbody>{''.join(body)}</tbody></table>", unsafe_allow_html=True)


def _exec_observations(live: pd.DataFrame) -> list[str]:
    """Short narrative bullets generated from the tracker's own grounded figures
    for the current scope — no estimates, just what the numbers say."""
    if live.empty:
        return []
    comp = (live.assign(company=live["deal_name"].map(_consolidate_name))
            .groupby("company")["carrying_value"].sum().sort_values(ascending=False))
    total = float(comp.sum())
    if total <= 0:
        return []
    obs: list[str] = []
    obs.append(f"The **top 5** holdings are **{comp.head(5).sum() / total * 100:.0f}%** of value; "
               f"the top 10 are **{comp.head(10).sum() / total * 100:.0f}%**.")
    obs.append(f"The single largest holding, **{comp.index[0]}**, carries "
               f"**{_fmt_money(comp.iloc[0])}** \u2014 **{comp.iloc[0] / total * 100:.0f}%** of value.")
    hhi = float(((comp / total) ** 2).sum())
    if hhi:
        obs.append(f"The book's Herfindahl index is **{hhi:.3f}** \u2014 it behaves like roughly "
                   f"**{1 / hhi:.0f}** equally-sized positions across {len(comp)} holdings.")
    geo = live[live["geography"].astype(str) != ""].groupby("geography")["carrying_value"].sum().sort_values(ascending=False)
    if len(geo):
        tgn = live[live["geography"] == geo.index[0]]["deal_name"].nunique()
        obs.append(f"**{geo.iloc[0] / total * 100:.0f}%** of value sits in **{geo.index[0]}** "
                   f"({_fmt_money(geo.iloc[0])} across {tgn}); the three largest geographies are "
                   f"{', '.join(list(geo.head(3).index))}.")
    sc = live.assign(s=live["sector"].map(_norm_sector))
    sec = sc[sc["s"].astype(str) != ""].groupby("s")["carrying_value"].sum().sort_values(ascending=False)
    if len(sec):
        obs.append(f"The largest sector is **{sec.index[0]}** at "
                   f"**{sec.iloc[0] / total * 100:.0f}%** ({_fmt_money(sec.iloc[0])}).")
    inv, gain, dist = (float(live["invested"].sum()), float(live["gain"].sum()),
                       float(live["distributions"].sum()))
    moic = (dist + total) / inv if inv else None
    if moic:
        obs.append(f"Value created is **{_fmt_money(gain)}** \u2014 a **{moic:.2f}x** gross multiple "
                   f"on **{_fmt_money(inv)}** of capital deployed.")
    sec_up = live["section"].astype(str).str.upper()
    mozn_mask = sec_up.str.contains("MOZN", na=False)
    mozn_v, g42_v = float(live[mozn_mask]["carrying_value"].sum()), float(live[~mozn_mask]["carrying_value"].sum())
    if mozn_v > 0 and g42_v > 0:
        obs.append(f"By holder, **G42** holds **{g42_v / total * 100:.0f}%** "
                   f"({_fmt_money(g42_v)} across {live[~mozn_mask]['deal_name'].nunique()}) and "
                   f"**MOZN {mozn_v / total * 100:.0f}%** "
                   f"({_fmt_money(mozn_v)} across {live[mozn_mask]['deal_name'].nunique()}).")
    return obs


def _render_ov_overview(months_df: pd.DataFrame, positions_df: pd.DataFrame) -> None:
    if months_df.empty or positions_df.empty:
        st.markdown("<h1 class='g42-serif'>Overview</h1>", unsafe_allow_html=True)
        st.info("No portfolio database yet.")
        return
    m = _latest_month(months_df)
    lbl = dict(zip(months_df["month_id"], months_df["label"])).get(m, m)
    month_pos = positions_df[positions_df["month_id"] == m]
    live = month_pos[month_pos["tab"] == "Live"]
    exited = month_pos[month_pos["tab"] == "Exited"]
    inv, carry, dist, gain = (live["invested"].sum(), live["carrying_value"].sum(),
                              live["distributions"].sum(), live["gain"].sum())
    moic = (dist + carry) / inv if inv else None
    tcol = st.columns([1.5, 5], vertical_alignment="bottom")
    with tcol[0]:
        st.markdown("<h1 class='g42-serif' style='margin:0'>Overview</h1>",
                    unsafe_allow_html=True)
    with tcol[1]:
        st.segmented_control(
            "Entity scope", _SCOPE_OPTIONS, default="Consolidated",
            key="scope_sel", label_visibility="collapsed")

    with st.container(border=True):
        st.markdown(
            f"<div style='text-align:right;font-size:12px;opacity:.6;margin:-2px 0 6px'>"
            f"Fair value as of {lbl}</div>", unsafe_allow_html=True)
        kc = st.columns(5)
        kc[0].metric("Current fair value", _fmt_money(carry), border=True)
        kc[1].metric("Capital deployed", _fmt_money(inv), border=True)
        kc[2].metric("Value created", _fmt_money(gain), border=True)
        kc[3].metric("Gross MOIC (TVPI)", (f"{moic:.2f}x" if moic else "n/a"), border=True)
        kc[4].metric("Live investments", f"{len(live):,}", border=True)
        st.caption(f"Figures reflect the {len(live)} live (unrealised) investments only; a further "
                   f"{len(exited)} investments have been realised or written off and are excluded.")
        st.caption("Amounts in USD millions, sourced from the monthly Portfolio Summary. "
                   "Prior-year figures, where indicated, are estimated.")

    # How we hold capital: equity-like / loans / funds.
    with st.container(border=True):
        st.subheader("Live portfolio by holding type")
        lv = live.copy()
        lv["bucket"] = [
            _instrument_bucket(dt, ins, sec)
            for dt, ins, sec in zip(lv["deal_type"], lv["instrument"], lv["sector"])
        ]
        order = ["Equity / equity-like", "Loans / debt-like", "Funds"]
        grp = (lv.groupby("bucket")
               .agg(holdings=("deal_name", "nunique"), invested=("invested", "sum"),
                    fair_value=("carrying_value", "sum"))
               .reindex(order).fillna(0).reset_index())
        cols = st.columns(3)
        for c, (_, r) in zip(cols, grp.iterrows()):
            c.metric(r["bucket"], _fmt_money(r["fair_value"]),
                     delta=f"{int(r['holdings'])} holdings · {_fmt_money(r['invested'])} in",
                     delta_color="off", border=True)
        st.caption("Buckets by tracker Type/Instrument: funds = fund vehicles; loans = "
                   "note/loan/debt/convertible instruments; everything else is equity or "
                   "equity-like (prefs, ordinary, SARs, LP co-investments).")

    # Composition: direct vs indirect (funds), with the MGX split inside funds.
    with st.container(border=True):
        st.subheader("Portfolio composition")
        cc = st.columns(2)
        with cc[0]:
            st.caption("Direct vs indirect")
            lc = live.copy()
            lc["indirect"] = [_instrument_bucket(dt, ins, sec) == "Funds"
                              for dt, ins, sec in zip(lc["deal_type"], lc["instrument"], lc["sector"])]
            direct = lc[~lc["indirect"]]
            indirect = lc[lc["indirect"]]
            mgx_in = indirect[indirect["deal_type"].astype(str).str.upper().str.startswith("MGX")]
            other_funds = indirect[~indirect["deal_type"].astype(str).str.upper().str.startswith("MGX")]
            for label, part in (("Direct investments", direct),
                                ("Indirect investments (funds)", indirect)):
                fv = float(part["carrying_value"].sum())
                wt = (fv / carry * 100) if carry else 0
                st.metric(label, _fmt_money(fv),
                          delta=f"{part['deal_name'].nunique()} holdings \u00b7 {wt:.0f}%",
                          delta_color="off", border=True)
            st.caption((f"Direct = investments we hold directly; Indirect = fund vehicles.  \n"
                        f"Within funds: **MGX** {_fmt_money(mgx_in['carrying_value'].sum())} "
                        f"\u00b7 **other funds** {_fmt_money(other_funds['carrying_value'].sum())}.")
                       .replace("$", "\\$"))
        with cc[1]:
            # By-holder is trivial for single-entity scopes (MGX/MOZN); show holdings instead.
            entities = live[live["investing_entity"].astype(str) != ""]["investing_entity"].nunique()
            if entities > 1:
                st.caption("By holder (investing entity)")
                hold = (live[live["investing_entity"].astype(str) != ""]
                        .groupby("investing_entity", as_index=False)["carrying_value"].sum()
                        .sort_values("carrying_value", ascending=False))
                _bar_h(hold, "investing_entity", "carrying_value", height=300)
            else:
                st.caption("By holding")
                byco = (live.assign(company=live["deal_name"].map(_consolidate_name))
                        .groupby("company", as_index=False)["carrying_value"].sum()
                        .sort_values("carrying_value", ascending=False).head(12))
                _bar_h(byco, "company", "carrying_value", height=300)

    with st.container(border=True):
        st.subheader("Portfolio value since inception")
        _render_nav_since_inception(months_df, positions_df)

    # Portfolio exposure — geography and sector, grounded from the tracker.
    with st.container(border=True):
        st.subheader("Portfolio exposure")
        wcols = st.columns(2)
        with wcols[0]:
            st.caption("By geography")
            geo = (live[live["geography"] != ""].groupby("geography", as_index=False)
                   ["carrying_value"].sum().sort_values("carrying_value", ascending=False))
            _bar_h(geo, "geography", "carrying_value", height=390)
        with wcols[1]:
            st.caption("By sector")
            sec = (live[live["sector"] != ""].groupby("sector", as_index=False)
                   ["carrying_value"].sum().sort_values("carrying_value", ascending=False))
            _bar_h(sec, "sector", "carrying_value", height=390)

    # MGX sub-group — grounded from tracker Type = MGX*.
    mgx = live[live["deal_type"].str.startswith("MGX", na=False)]
    if len(mgx):
        with st.container(border=True):
            st.subheader("MGX sub-group")
            m_inv, m_fv, m_gain = (mgx["invested"].sum(), mgx["carrying_value"].sum(),
                                   mgx["gain"].sum())
            m_mult = m_fv / m_inv if m_inv else None
            with st.container(horizontal=True):
                st.metric("MGX fair value", _fmt_money(m_fv), border=True)
                st.metric("Capital deployed", _fmt_money(m_inv), border=True)
                st.metric("Value created", _fmt_money(m_gain), border=True)
                st.metric("Multiple", (f"{m_mult:.2f}x" if m_mult else "n/a"), border=True)
                st.metric("Vehicles", f"{mgx['deal_name'].nunique():,}", border=True)
            mt = (mgx.groupby("deal_name", as_index=False)
                  .agg(deal_type=("deal_type", "first"), geography=("geography", "first"),
                       invested=("invested", "sum"), carrying_value=("carrying_value", "sum"),
                       gain=("gain", "sum")))
            mt["multiple"] = mt["carrying_value"] / mt["invested"].where(mt["invested"] != 0)
            share = mt["carrying_value"].sum()
            mt["share_of_mgx"] = mt["carrying_value"] / share if share else 0
            _html_table(mt.sort_values("carrying_value", ascending=False), {
                "deal_name": "Vehicle", "deal_type": "Type", "geography": "Geography",
                "invested": "Capital deployed", "carrying_value": "Fair value",
                "gain": "Value created", "multiple": "Multiple", "share_of_mgx": "Share of MGX",
            }, fmts={
                "invested": lambda v: f"${v:,.1f}", "carrying_value": lambda v: f"${v:,.1f}",
                "gain": lambda v: f"${v:,.1f}", "multiple": lambda v: f"{v:.2f}x",
                "share_of_mgx": lambda v: f"{v * 100:.1f}%",
            })
            st.caption(f"Each row is a distinct MGX vehicle as carried in the Portfolio Summary's "
                       f"Live register ({mgx['deal_name'].nunique()} in total); fair value = "
                       f"carrying value. The Portfolio Summary does not break these out any further.")

    with st.container(border=True):
        st.subheader("Ten largest holdings")
        top = (live.assign(company=live["deal_name"].map(_consolidate_name))
               .groupby("company", as_index=False)[["invested", "carrying_value", "gain"]].sum()
               .sort_values("carrying_value", ascending=False).head(10))
        top["weight"] = top["carrying_value"] / carry if carry else 0
        mid = st.columns([1, 3, 1])
        with mid[1]:
            _html_table(top, {
                "company": "Company", "invested": "Invested", "carrying_value": "Fair value",
                "gain": "Gain", "weight": "Weight",
            }, fmts={
                "invested": lambda v: f"${v:,.1f}", "carrying_value": lambda v: f"${v:,.1f}",
                "gain": lambda v: f"${v:,.1f}", "weight": lambda v: f"{v * 100:.1f}%",
            })

    obs = _exec_observations(live)
    if obs:
        with st.container(border=True):
            st.subheader("Key observations")
            # Escape $ so Streamlit doesn't read paired amounts as LaTeX math.
            st.markdown("\n".join(f"- {o.replace('$', chr(92) + '$')}" for o in obs))
            st.caption("Auto-generated from the tracker's own grounded figures for the current scope.")


_BOR_VIEWS = ["Overview", "Portfolio", "Company details", "Analytics",
              "Change Log", "Parked"]


def _render_book_of_record(view: str, months_df: pd.DataFrame, positions_df: pd.DataFrame) -> None:
    """Tracker 2 — Portfolio Book of Record. Dispatches to the selected view; the view
    band and scope band live in the app shell (tracker2_app)."""
    if months_df.empty or positions_df.empty:
        st.info("No portfolio database yet.")
        return
    if view == "Overview":
        _render_bor_overview(months_df, positions_df)
    elif view == "Portfolio":
        st.markdown(
            "<div style='font-size:12px;font-style:italic;color:#8a8f88;line-height:1.5;"
            "margin:2px 0 12px'>Why the totals here differ from the Overview: this operational "
            "view carries each fund / LP position at its latest Capital Account Statement NAV, "
            "whereas the Overview uses the summary Live-register figure. Every direct holding "
            "matches exactly; the difference is entirely the fund vehicles — principally the MGX "
            "vehicles. On this basis invested is ~&#36;2,160m and fair value ~&#36;4,568m, versus "
            "~&#36;1,903m and ~&#36;3,735m on the Overview. Both are grounded in our data; the "
            "figures will be aligned in next month's reporting.</div>", unsafe_allow_html=True)
        _render_current_month()
    elif view == "Company details":
        _render_bor_register(months_df, positions_df)
    elif view == "Analytics":
        _render_bor_analytics(months_df, positions_df)
    elif view == "Change Log":
        _render_bor_changelog()
    elif view == "Parked":
        _render_bor_parked(months_df, positions_df)
    else:
        st.info(f"**{view}** — planned.")


def _render_bor_overview(months_df: pd.DataFrame, positions_df: pd.DataFrame) -> None:
    m = _latest_month(months_df)
    lbl = dict(zip(months_df["month_id"], months_df["label"])).get(m, m)
    month_pos = positions_df[positions_df["month_id"] == m]
    live = month_pos[month_pos["tab"] == "Live"]
    exited = month_pos[month_pos["tab"] == "Exited"]
    if live.empty:
        st.info("No live holdings in this scope.")
        return
    live = _attach_accounts_attrs(live)
    inv = live["invested"].sum()
    carry = live["carrying_value"].sum()
    dist = live["distributions"].sum()
    gain = live["gain"].sum()
    moic = (dist + carry) / inv if inv else None
    ms = months_df.sort_values("month_id")
    first_carry = float(ms["live_carrying"].iloc[0]) if len(ms) else 0.0
    growth = (carry / first_carry - 1) * 100 if first_carry else 0.0
    prev_carry = float(ms["live_carrying"].iloc[-2]) if len(ms) > 1 else carry
    movement = carry - prev_carry
    measures, score, cshare, _tot = _concentration_measures(live)
    top10 = float(cshare.head(10).sum()) * 100
    band, _bc = _risk_band(score)
    indep_mask = (~live["valuation_method"].str.startswith("Not covered", na=False)) & \
                 (live["valuation_method"] != "Pending")
    indep_pct = live.loc[indep_mask, "carrying_value"].sum() / carry * 100 if carry else 0.0
    n_sectors = int(live[live["sector"] != ""]["sector"].nunique())
    n_geos = int(live[live["geography"] != ""]["geography"].nunique())

    with st.container(border=True):
        st.subheader("Overview")
        st.markdown(
            (f"As at {lbl}, the portfolio comprises **{len(live)} live investments** carried at a "
             f"fair value of **{_fmt_money(carry)}**, against **{_fmt_money(inv)}** of capital "
             f"deployed — a gross multiple of **{moic:.2f}x** and **{_fmt_money(gain)}** of value "
             f"created since inception. Exposure spans **{n_sectors} sectors** across "
             f"**{n_geos} geographies**, with the ten largest holdings accounting for "
             f"**{top10:.0f}%** of fair value. A further **{len(exited)} investments** have been "
             f"realised or written off and are excluded from the figures below.").replace("$", "\\$"))

    # At a glance — two rows of five, uniform tiles (no deltas), for a symmetric grid.
    with st.container(border=True):
        st.markdown(f"<div style='text-align:right;font-size:12px;opacity:.6;margin:-2px 0 6px'>"
                    f"As of {lbl}</div>", unsafe_allow_html=True)
        r1 = st.columns(5)
        r1[0].metric("Current fair value", _fmt_money(carry), border=True)
        r1[1].metric("Capital deployed", _fmt_money(inv), border=True)
        r1[2].metric("Value created", _fmt_money(gain), border=True)
        r1[3].metric("Gross multiple", (f"{moic:.2f}x" if moic else "n/a"), border=True)
        r1[4].metric("Live investments", f"{len(live):,}", border=True)
        r2 = st.columns(5)
        r2[0].metric("Exited investments", f"{len(exited):,}", border=True)
        r2[1].metric("Growth since inception", f"{growth:+.0f}%", border=True)
        r2[2].metric("Movement in period", _fmt_money(movement), border=True)
        r2[3].metric("Independently valued", f"{indep_pct:.0f}%", border=True)
        r2[4].metric("Concentration risk", f"{score * 100:.1f}%", border=True)
        st.caption(f"Concentration risk reads **{band}**. Amounts in USD millions, sourced from the "
                   "monthly Portfolio Summary. IFRS classification and valuation method are the "
                   "accounts team's (Ardent / Project Matrix), adopted as their classification; all "
                   "economics are our own figures.")

    with st.container(border=True):
        st.subheader("The portfolio since inception")
        _render_nav_since_inception(months_df, positions_df)

    with st.container(border=True):
        st.subheader("What the portfolio is made of")
        cc = st.columns(2)
        with cc[0]:
            st.caption("By sector")
            sec = (live[live["sector"] != ""].groupby("sector", as_index=False)["carrying_value"]
                   .sum().sort_values("carrying_value", ascending=False))
            _bar_h(sec, "sector", "carrying_value", height=260)
        with cc[1]:
            st.caption("By holding type")
            lv = live.copy()
            lv["bucket"] = [_instrument_bucket(dt, ins, s)
                           for dt, ins, s in zip(lv["deal_type"], lv["instrument"], lv["sector"])]
            lv["bucket"] = lv["bucket"].map(
                {"Equity / equity-like": "Equity", "Loans / debt-like": "Loans"}).fillna(lv["bucket"])
            bt = (lv.groupby("bucket", as_index=False)["carrying_value"].sum()
                  .sort_values("carrying_value", ascending=False))
            _bar_h(bt, "bucket", "carrying_value", height=260)
        st.caption("Equity includes equity and equity-like instruments (preference shares, "
                   "ordinary shares, SARs and LP co-investments); loans are note/loan/debt/"
                   "convertible instruments; funds are fund vehicles.")

    with st.container(border=True):
        st.subheader("Ten largest holdings")
        try:
            _dark = getattr(st.context.theme, "type", "light") == "dark"
        except Exception:  # noqa: BLE001
            _dark = False
        fv_col = "#EAF3E6" if _dark else "#14261c"
        by_co = live.assign(company=live["deal_name"].map(_consolidate_name))
        top = (by_co.groupby("company", as_index=False)[["invested", "carrying_value", "gain"]]
               .sum().sort_values("carrying_value", ascending=False).head(10))
        top["weight"] = top["carrying_value"] / carry if carry else 0
        ifrs_by_co = by_co.groupby("company")["ifrs_class"].first()
        top["ifrs"] = top["company"].map(ifrs_by_co)
        _html_table(top[["company", "ifrs", "invested", "carrying_value", "gain", "weight"]], {
            "company": "Investment", "ifrs": "IFRS", "invested": "Capital deployed",
            "carrying_value": "Fair value", "gain": "Value created", "weight": "Weight",
        }, fmts={
            "invested": lambda v: f"${v:,.1f}",
            "carrying_value": lambda v: f"<span style='color:{fv_col};font-weight:700'>${v:,.1f}</span>",
            "gain": lambda v: f"${v:,.1f}", "weight": lambda v: f"{v * 100:.1f}%",
        })
        st.caption("Ranked by fair value. Weight = each holding's fair value as a share of the "
                   "total portfolio fair value (the live holdings sum to 100%).")

    with st.container(border=True):
        st.subheader("How concentrated is it")
        st.markdown(
            "<div style='position:relative;height:16px;border-radius:8px;overflow:hidden;"
            "background:linear-gradient(90deg,#2F6B45 0 35%,#C9862B 35% 55%,"
            "#D2691E 55% 70%,#b3253a 70% 100%);'>"
            f"<div style='position:absolute;left:calc({min(score, 1.0) * 100:.1f}% - 1px);top:-3px;"
            "width:3px;height:22px;background:#22302A;'></div></div>"
            "<div style='display:flex;justify-content:space-between;font-size:11px;"
            "color:#6b746a;margin-top:3px'><span>0% low</span><span>moderate</span>"
            "<span>elevated</span><span>high 100%</span></div>", unsafe_allow_html=True)
        mdf = pd.DataFrame([{"Measure": n, "Reading": f"{r * 100:.1f}%", "Weight": f"{w * 100:.0f}%"}
                            for n, r, w, _ in measures])
        _html_table(mdf, {"Measure": "Measure", "Reading": "Reading", "Weight": "Weight"})
        st.caption(f"Weighted composite risk score {score * 100:.1f}% — {band}. "
                   "**Reading** is each measure's own value (e.g. the share of value held in the "
                   "top five holdings); **Weight** is how much that measure counts toward the "
                   "composite score, and the weights sum to 100%. The score is the weighted "
                   "average of the readings. A presentation aid, not a regulatory capital measure.")

    obs = _exec_observations(live)
    if obs:
        with st.container(border=True):
            st.subheader("What stands out")
            st.markdown("\n".join(f"- {o.replace('$', chr(92) + '$')}" for o in obs))
            st.caption("Derived from the underlying portfolio figures for the selected scope.")


def _render_bor_register(months_df: pd.DataFrame, positions_df: pd.DataFrame) -> None:
    m = _latest_month(months_df)
    live = positions_df[(positions_df["month_id"] == m) & (positions_df["tab"] == "Live")].copy()
    if live.empty:
        st.info("No live holdings in this scope.")
        return
    live = _attach_accounts_attrs(live)
    by_co = live.assign(company=live["deal_name"].map(_consolidate_name))
    order = (by_co.groupby("company", as_index=False)["carrying_value"].sum()
             .sort_values("carrying_value", ascending=False)["company"].tolist())
    if st.session_state.get("bor_reg_pick") not in order:
        st.session_state["bor_reg_pick"] = order[0]
    with st.container(border=True):
        st.subheader("Company details")
        lc, rc = st.columns([1, 3.2])
        with lc:
            for name in order:
                sel = st.session_state["bor_reg_pick"] == name
                if st.button(name, key=f"borco_{_norm_key(name)}",
                             type=("primary" if sel else "secondary"),
                             use_container_width=True):
                    st.session_state["bor_reg_pick"] = name
                    st.rerun()
        with rc:
            _render_bor_factsheet(st.session_state["bor_reg_pick"], by_co, positions_df)


def _render_bor_factsheet(company: str, by_co: pd.DataFrame, positions_df: pd.DataFrame) -> None:
    sub = by_co[by_co["company"] == company]
    if sub.empty:
        st.info("No data for this holding.")
        return
    attrs = _lookup_accounts(company)
    facts = _load_company_facts().get(company.strip().lower(), {})
    dom = _load_domicile_legal().get(company.strip().lower(), {})
    inv = float(sub["invested"].sum())
    fv = float(sub["carrying_value"].sum())
    gain = float(sub["gain"].sum())
    mult = fv / inv if inv else None
    weight = fv / float(by_co["carrying_value"].sum()) if by_co["carrying_value"].sum() else 0

    def _dl(keys: list[str]) -> str:
        return "  \n".join(f"**{k}:** {attrs.get(k) or 'Pending'}" for k in keys)

    st.markdown(f"#### {company}")
    if facts.get("description"):
        line = f"_{facts['description']}_"
        if facts.get("website"):
            line += f"  \u00b7  [{facts['website']}]({facts['website']})"
        st.markdown(line)
    with st.container(horizontal=True):
        st.metric("Fair value", _fmt_money(fv), border=True)
        st.metric("Capital deployed", _fmt_money(inv), border=True)
        st.metric("Value created", _fmt_money(gain), border=True)
        st.metric("Multiple", (f"{mult:.2f}x" if mult else "n/a"), border=True)
    st.markdown("**Identity and provenance**")
    st.markdown(_dl(["Legal entity", "Sub-group", "Holding type", "Sector", "Instrument",
                     "Listed status", "Jurisdiction", "Region", "First recognised", "Source"]))
    st.markdown("**Measurement basis**")
    st.markdown(_dl(["IFRS classification", "Valuation method", "Fair value hierarchy",
                     "Valuation basis", "Influence band", "Holding"]))
    if dom.get("domicile"):
        st.markdown(f"**Domicile (our legal documents):** {dom['domicile']}  \n"
                    f"<span style='font-size:11px;opacity:.6'>Source: "
                    f"{dom.get('domicile_source', 'legal docs')}</span>",
                    unsafe_allow_html=True)
    st.caption("Identity and classification fields are the accounts team's (adopted); fair value, "
               "capital deployed and value created are our own figures. "
               f"Weight in portfolio {weight * 100:.1f}%.")

    allp = positions_df.assign(company=positions_df["deal_name"].map(_consolidate_name))
    hist = (allp[allp["company"] == company].groupby("as_of_date")["carrying_value"].sum()
            .rename("Fair value"))
    if len(hist) > 1:
        with st.container(border=True):
            st.markdown("**Value-creation timeline**")
            st.line_chart(hist, height=220, x_label="Month", y_label="Fair value, USD m")

    cf = _load_cashflows(str(PORTFOLIO_DB_PATH), _path_mtime(PORTFOLIO_DB_PATH))
    if len(cf):
        cf = cf.copy()
        cf["company"] = cf["deal_name"].map(_consolidate_name)
        cfc = cf[cf["company"] == company].sort_values("flow_date")
        if len(cfc):
            with st.container(border=True):
                st.markdown("**Cash movements on record**")
                view = cfc[["flow_date", "accounting_entity", "contribution", "distribution",
                            "currency"]].copy()
                st.dataframe(view, hide_index=True, width="stretch", column_config={
                    "flow_date": st.column_config.TextColumn("Date"),
                    "accounting_entity": st.column_config.TextColumn("Entity"),
                    "contribution": st.column_config.NumberColumn("Contribution", format="%.2f"),
                    "distribution": st.column_config.NumberColumn("Distribution", format="%.2f"),
                    "currency": st.column_config.TextColumn("Currency"),
                })
                st.caption("Source file and cell for every line are tracked internally and can be "
                           "produced on request.")


def _render_bor_parked(months_df: pd.DataFrame, positions_df: pd.DataFrame) -> None:
    st.markdown("<h1 class='g42-serif' style='margin:0'>Parked</h1>", unsafe_allow_html=True)
    st.caption("Holding area for sections taken out of other views — nothing is deleted; "
               "we will place these where they belong later.")
    sub = st.segmented_control(
        "Parked view", ["Complete investment register", "IFRS & Audit Trail"],
        default="Complete investment register", key="bor_parked_view",
        label_visibility="collapsed") or "Complete investment register"
    if sub == "IFRS & Audit Trail":
        _render_bor_ifrs(months_df, positions_df)
        return
    _render_bor_parked_register(months_df, positions_df)


def _render_bor_parked_register(months_df: pd.DataFrame, positions_df: pd.DataFrame) -> None:
    m = _latest_month(months_df)
    live = positions_df[(positions_df["month_id"] == m) & (positions_df["tab"] == "Live")].copy()
    if live.empty:
        st.info("No live holdings in this scope.")
        return
    live = _attach_accounts_attrs(live)
    by_co = live.assign(company=live["deal_name"].map(_consolidate_name))
    reg = (by_co.groupby("company", as_index=False)
           .agg(ifrs=("ifrs_class", "first"), valuation=("valuation_method", "first"),
                sector=("sector", "first"), geography=("geography", "first"),
                status=("status", "first"), invested=("invested", "sum"),
                carrying_value=("carrying_value", "sum"), gain=("gain", "sum")))
    reg["multiple"] = reg["carrying_value"] / reg["invested"].where(reg["invested"] != 0)
    tot = reg["carrying_value"].sum()
    reg["weight"] = reg["carrying_value"] / tot if tot else 0
    reg = reg.sort_values("carrying_value", ascending=False)
    with st.container(border=True):
        st.subheader("Complete investment register")
        st.dataframe(reg, hide_index=True, width="stretch", column_config={
            "company": st.column_config.TextColumn("Investment"),
            "ifrs": st.column_config.TextColumn("IFRS"),
            "valuation": st.column_config.TextColumn("Valuation method"),
            "sector": st.column_config.TextColumn("Sector"),
            "geography": st.column_config.TextColumn("Geography"),
            "status": st.column_config.TextColumn("Status"),
            "invested": st.column_config.NumberColumn("Capital deployed", format="$%.1f"),
            "carrying_value": st.column_config.NumberColumn("Fair value", format="$%.1f"),
            "gain": st.column_config.NumberColumn("Value created", format="$%.1f"),
            "multiple": st.column_config.NumberColumn("Multiple", format="%.2fx"),
            "weight": st.column_config.NumberColumn("Weight", format="percent"),
        })
        st.caption("Every live holding in scope. Economics are our own figures; IFRS "
                   "classification and valuation method are the accounts team's. USD millions.")


def _render_bor_analytics(months_df: pd.DataFrame, positions_df: pd.DataFrame) -> None:
    sub = st.segmented_control(
        "Analytics view", ["Value creation", "Portfolio evolution", "Geography", "Sector",
                           "Concentration risk"],
        default="Value creation", key="bor_an_view", label_visibility="collapsed") or "Value creation"
    if sub == "Value creation":
        _render_value_creation(months_df, positions_df)
    elif sub == "Portfolio evolution":
        _render_portfolio_growth(months_df, positions_df)
    elif sub == "Geography":
        _render_geography(months_df, positions_df)
    elif sub == "Sector":
        _render_sector(months_df, positions_df)
    elif sub == "Concentration risk":
        _render_concentration(months_df, positions_df)


def _render_bor_ifrs(months_df: pd.DataFrame, positions_df: pd.DataFrame) -> None:
    m = _latest_month(months_df)
    live = positions_df[(positions_df["month_id"] == m) & (positions_df["tab"] == "Live")].copy()
    if live.empty:
        st.info("No live holdings in this scope.")
        return
    live = _attach_accounts_attrs(live)
    by_co = live.assign(company=live["deal_name"].map(_consolidate_name))
    sched = (by_co.groupby("company", as_index=False)
             .agg(ifrs=("ifrs_class", "first"), valuation=("valuation_method", "first"),
                  fvh=("fv_hierarchy", "first"), vbasis=("valuation_basis", "first"),
                  carrying_value=("carrying_value", "sum")))
    tot = sched["carrying_value"].sum()
    sched["weight"] = sched["carrying_value"] / tot if tot else 0
    sched = sched.sort_values(["ifrs", "carrying_value"], ascending=[True, False])

    with st.container(border=True):
        st.subheader("The reporting view — classification schedule")
        st.dataframe(sched, hide_index=True, width="stretch", column_config={
            "company": st.column_config.TextColumn("Investment"),
            "ifrs": st.column_config.TextColumn("IFRS classification"),
            "valuation": st.column_config.TextColumn("Valuation method"),
            "fvh": st.column_config.TextColumn("Fair value hierarchy"),
            "vbasis": st.column_config.TextColumn("Valuation basis"),
            "carrying_value": st.column_config.NumberColumn("Fair value", format="$%.1f"),
            "weight": st.column_config.NumberColumn("Weight", format="percent"),
        })
        st.caption("IFRS classification, valuation method, fair-value hierarchy and valuation basis "
                   "are the accounts team's (Ardent / Project Matrix), adopted as their "
                   "classification. Fair value and weight are our own figures.")

    with st.container(border=True):
        st.subheader("How the book is classified")
        gc = st.columns(2)
        with gc[0]:
            st.caption("By IFRS classification")
            grp = (live.groupby("ifrs_class", as_index=False)["carrying_value"].sum()
                   .sort_values("carrying_value", ascending=False))
            _bar_h(grp, "ifrs_class", "carrying_value", height=220)
        with gc[1]:
            st.caption("By fair-value hierarchy")
            grp2 = (live.groupby("fv_hierarchy", as_index=False)["carrying_value"].sum()
                    .sort_values("carrying_value", ascending=False))
            _bar_h(grp2, "fv_hierarchy", "carrying_value", height=220)

    with st.container(border=True):
        st.subheader("Reconciliation")
        section_tot = float(live.groupby("section")["carrying_value"].sum().sum())
        tie = abs(section_tot - float(tot)) < 0.5
        _html_table(pd.DataFrame([
            {"check": "Sum of the holdings' fair value", "value": float(tot)},
            {"check": "Sum of the entity subtotals", "value": section_tot},
        ]), {"check": "Check", "value": "USD m"}, fmts={"value": lambda v: f"${v:,.1f}"})
        st.caption(("Internal figures tie. " if tie else "Internal figures do not tie — investigate. ")
                   + "Reconciliation to the signed statutory statements and the board deck is not "
                   "yet wired into our data — flagged as an open item, not estimated.")

        bridge = _load_basis_bridge(_path_mtime(BASIS_BRIDGE_PATH))
        if bridge.get("drivers"):
            st.markdown("**Live-register basis vs NAV + Capital Account Statement basis**")
            bdf = pd.DataFrame(bridge["drivers"])
            _html_table(bdf[["holding", "invested_live", "invested_nav", "inv_delta",
                             "carrying_live", "carrying_nav", "cv_delta"]], {
                "holding": "Holding", "invested_live": "Invested (Live)",
                "invested_nav": "Invested (NAV+CAS)", "inv_delta": "\u0394 inv",
                "carrying_live": "Fair value (Live)", "carrying_nav": "Fair value (NAV+CAS)",
                "cv_delta": "\u0394 FV"}, fmts={
                "invested_live": lambda v: f"{v:,.1f}", "invested_nav": lambda v: f"{v:,.1f}",
                "inv_delta": lambda v: f"{v:+,.1f}", "carrying_live": lambda v: f"{v:,.1f}",
                "carrying_nav": lambda v: f"{v:,.1f}", "cv_delta": lambda v: f"{v:+,.1f}"})
            t = bridge.get("totals", {})
            st.caption(
                f"Differences vs the Live-register basis arise solely on fund / LP positions "
                f"carried at their latest Capital Account Statement NAV — principally the MGX "
                f"vehicles; {bridge.get('n_tie', '?')} of {bridge.get('n_holdings', '?')} holdings "
                f"tie exactly. Totals (USD m): invested {t.get('invested_live', 0):,.1f} → "
                f"{t.get('invested_nav', 0):,.1f}; fair value {t.get('carrying_live', 0):,.1f} → "
                f"{t.get('carrying_nav', 0):,.1f}.")

    with st.container(border=True):
        st.subheader("Basis of preparation")
        st.markdown(
            "- Amounts in USD millions unless stated otherwise.\n"
            "- Economics (capital deployed, fair value, value created) are our own figures from "
            "the monthly Portfolio Summary, on the live report-tab basis.\n"
            "- IFRS classification and valuation method are adopted from the accounts team "
            "(Ardent Advisory / Project Matrix) and treated as their classification.\n"
            "- Prior-year (FY2020\u2013FY2021) portfolio values are estimated, pending our own "
            "historical NAVs, and are shown as such.\n"
            "- This book presents our 26 live holdings; accounts-pack lines we do not track are "
            "out of scope rather than omitted in error.")

    src = _load_sources(str(PORTFOLIO_DB_PATH), _path_mtime(PORTFOLIO_DB_PATH))
    with st.container(border=True):
        st.subheader("Audit trail — source registry")
        if len(src):
            st.dataframe(src, hide_index=True, width="stretch")
        else:
            st.caption("Source registry not available in this build.")


def _render_bor_changelog() -> None:
    with st.container(border=True):
        st.subheader("Open items")
        st.markdown(
            "- **FY2020\u2013FY2021** portfolio value on the since-inception charts is a temporary "
            "estimate, pending our own historical NAVs.\n"
            "- **Independently-valued %** is derived from the accounts team's Ardent coverage flag "
            "(June basis); to be confirmed against the latest independent valuation.\n"
            "- **Statutory reconciliation** to the signed financial statements and board deck is "
            "not yet wired into our data \u2014 planned for the IFRS & Audit Trail view.\n"
            "- **Scope**: this book shows our 26 live holdings; accounts-pack lines we do not track "
            "(MGX look-through, warrant splits, Presight / Space42) are out of scope, not errors.")
    with st.container(border=True):
        st.subheader("Version history")
        st.markdown(
            "- **v0.1** \u2014 Portfolio Book of Record established as its own application "
            "(codename Tracker 2), reusing the shared engine and house style.\n"
            "- Views live: Executive Overview, Investment Register (with per-holding fact sheets), "
            "Value Creation, Portfolio Evolution, Geography, Sector, Concentration Risk, "
            "IFRS & Audit Trail, Change Log, and the operational Portfolio view.\n"
            "- IFRS classification and valuation method adopted from the accounts team; 26/26 "
            "holdings matched.")


def _render_ov_analytics(months_df: pd.DataFrame, positions_df: pd.DataFrame) -> None:
    st.markdown("<h1 class='g42-serif'>Analytics</h1>", unsafe_allow_html=True)
    if months_df.empty or positions_df.empty:
        st.info("No portfolio database yet.")
        return
    view = st.segmented_control(
        "Analytics view", ["Value creation", "Concentration", "Portfolio growth",
                           "Geography", "Sector"],
        default="Value creation", key="an_view", label_visibility="collapsed") or "Value creation"
    if view == "Value creation":
        _render_value_creation(months_df, positions_df)
        return
    if view == "Portfolio growth":
        _render_portfolio_growth(months_df, positions_df)
        return
    if view == "Geography":
        _render_geography(months_df, positions_df)
        return
    if view == "Sector":
        _render_sector(months_df, positions_df)
        return
    _render_concentration(months_df, positions_df)


def _render_value_creation(months_df: pd.DataFrame, positions_df: pd.DataFrame) -> None:
    """Capital deployed vs fair value, and who created/lost value — grounded on our
    tracker's live holdings."""
    m = _latest_month(months_df)
    lbl = dict(zip(months_df["month_id"], months_df["label"])).get(m, m)
    live = positions_df[(positions_df["month_id"] == m) & (positions_df["tab"] == "Live")]
    inv, fv, vc = live["invested"].sum(), live["carrying_value"].sum(), live["gain"].sum()
    mult = fv / inv if inv else None
    with st.container(horizontal=True):
        st.metric("Capital deployed", _fmt_money(inv), border=True)
        st.metric("Current fair value", _fmt_money(fv), border=True)
        st.metric("Value created", _fmt_money(vc), border=True)
        st.metric("Gross multiple", (f"{mult:.2f}x" if mult else "n/a"), border=True)
        st.metric("Live holdings", f"{len(live):,}", border=True)
    st.caption(f"Live holdings only, as of {lbl}. Capital deployed = invested; value created = "
               f"fair value \u2212 invested. Our {len(live)} holdings. USD millions.")

    with st.container(border=True):
        st.subheader("Value created since inception")
        vseries = months_df.sort_values("month_id").copy()
        vseries["value_created"] = vseries["live_carrying"] - vseries["live_invested"]
        _line_usd(vseries, "as_of_date", "value_created", y_title="Value created, USD m")
        first_lbl = vseries["label"].iloc[0] if len(vseries) else "?"
        st.caption(f"Sourced from our monthly Portfolio Summary, from {first_lbl}. Earlier years "
                   f"(FY2020\u2013FY2021) need our own historical NAVs \u2014 not fabricated here.")

    by_co = (live.assign(company=live["deal_name"].map(_consolidate_name))
             .groupby("company", as_index=False)[["invested", "carrying_value", "gain"]].sum())
    by_co["multiple"] = by_co["carrying_value"] / by_co["invested"].where(by_co["invested"] != 0)
    with st.container(border=True):
        st.subheader("Who created \u2014 and who lost \u2014 value")
        ranked = by_co.sort_values("gain")
        bar = (alt.Chart(ranked).mark_bar().encode(
                    x=alt.X("gain:Q", axis=alt.Axis(title="Value created, USD m")),
                    y=alt.Y("company:N", sort="-x", axis=alt.Axis(title=None)),
                    color=alt.condition(alt.datum.gain >= 0, alt.value("#2F6B45"),
                                        alt.value("#b3253a")),
                    tooltip=["company", "invested", "carrying_value", "gain"])
               .properties(height=max(280, 22 * len(ranked))))
        st.altair_chart(bar, width="stretch")

    with st.container(border=True):
        st.subheader("Capital deployed against fair value")
        tbl = by_co.sort_values("carrying_value", ascending=False)
        st.dataframe(tbl, hide_index=True, width="stretch", column_config={
            "company": st.column_config.TextColumn("Company"),
            "invested": st.column_config.NumberColumn("Capital deployed", format="$%.1f"),
            "carrying_value": st.column_config.NumberColumn("Fair value", format="$%.1f"),
            "gain": st.column_config.NumberColumn("Value created", format="$%.1f"),
            "multiple": st.column_config.NumberColumn("Multiple", format="%.2fx"),
        })

    # Waterfall: exact identity carrying = invested + gain - distributions.
    dist = float(live["distributions"].sum())
    with st.container(border=True):
        st.subheader("Waterfall \u2014 how we get to fair value")
        steps = [("Capital deployed", inv), ("+ Value created", vc), ("\u2212 Distributions", -dist)]
        rows, cum = [], 0.0
        for label, delta in steps:
            lo, hi = cum, cum + delta
            rows.append({"step": label, "lo": min(lo, hi), "hi": max(lo, hi), "amount": delta,
                         "dir": "up" if delta >= 0 else "down"})
            cum = hi
        rows.append({"step": "Fair value today", "lo": 0.0, "hi": float(fv), "amount": float(fv),
                     "dir": "total"})
        wf = pd.DataFrame(rows)
        order = ["Capital deployed", "+ Value created", "\u2212 Distributions", "Fair value today"]
        bar = (alt.Chart(wf).mark_bar().encode(
                    y=alt.Y("step:N", sort=order, axis=alt.Axis(title=None)),
                    x=alt.X("lo:Q", axis=alt.Axis(title="USD, millions")),
                    x2="hi:Q",
                    color=alt.Color("dir:N", scale=alt.Scale(
                        domain=["up", "down", "total"],
                        range=["#2F6B45", "#b3253a", "#1f4d33"]), legend=None),
                    tooltip=[alt.Tooltip("step:N"), alt.Tooltip("amount:Q", format=",.1f")])
               .properties(height=200))
        st.altair_chart(bar, width="stretch")
        st.caption((f"Capital deployed {_fmt_money(inv)} + value created {_fmt_money(vc)} "
                    f"\u2212 distributions {_fmt_money(dist)} = fair value {_fmt_money(fv)}. "
                    f"An exact identity from the Portfolio Summary's own figures.").replace("$", "\\$"))

    # Year-on-year movement from the last tracker month of each calendar year.
    ys = months_df.sort_values("month_id").copy()
    ys["year"] = pd.to_datetime(ys["as_of_date"]).dt.year
    yr = ys.groupby("year").tail(1).copy()
    yr["value_created"] = yr["live_carrying"] - yr["live_invested"]
    yr["yoy_fair_value"] = yr["live_carrying"].diff()
    with st.container(border=True):
        st.subheader("Year-on-year movement")
        show = yr[["label", "live_invested", "live_carrying", "value_created", "yoy_fair_value"]]
        st.dataframe(show, hide_index=True, width="stretch", column_config={
            "label": st.column_config.TextColumn("Year-end (last tracker month)"),
            "live_invested": st.column_config.NumberColumn("Capital deployed", format="$%.1f"),
            "live_carrying": st.column_config.NumberColumn("Fair value", format="$%.1f"),
            "value_created": st.column_config.NumberColumn("Value created", format="$%.1f"),
            "yoy_fair_value": st.column_config.NumberColumn("YoY \u0394 fair value", format="$%.1f"),
        })
        yb = yr.dropna(subset=["yoy_fair_value"])
        if len(yb):
            chart = (alt.Chart(yb).mark_bar().encode(
                        x=alt.X("label:N", sort=list(yb["label"]), axis=alt.Axis(title=None, labelAngle=0)),
                        y=alt.Y("yoy_fair_value:Q", axis=alt.Axis(title="YoY \u0394 fair value, USD m")),
                        color=alt.condition(alt.datum.yoy_fair_value >= 0, alt.value("#2F6B45"),
                                            alt.value("#b3253a")),
                        tooltip=[alt.Tooltip("label:N", title="Year-end"),
                                 alt.Tooltip("yoy_fair_value:Q", title="YoY change", format=",.1f")])
                     .properties(height=240))
            st.altair_chart(chart, width="stretch")
        st.caption("Fair value at the last reported month of each calendar year, and the change "
                   "on the prior year. Within our data window; FY2020/FY2021 pending real NAVs.")


_REGION = {
    "USA": "Americas", "Canada": "Americas", "Cayman": "Americas",
    "UK": "Europe", "Luxembourg": "Europe",
    "Israel": "Middle East", "UAE": "Middle East", "UAE/UK": "Middle East",
    "PRC": "Asia",
}


def _region_of(geo: str) -> str:
    return _REGION.get(str(geo or "").strip(), "Other")


def _norm_sector(s: str) -> str:
    s = str(s or "").strip()
    return "Semiconductors" if s.lower() in ("semiconductor", "semiconductors") else s


def _exposure_table(live: pd.DataFrame, col: str) -> pd.DataFrame:
    total = float(live["carrying_value"].sum())
    g = (live[live[col].astype(str) != ""].groupby(col, as_index=False)
         .agg(fair_value=("carrying_value", "sum"), holdings=("deal_name", "nunique")))
    g["weight"] = g["fair_value"] / total if total else 0.0
    return g.sort_values("fair_value", ascending=False)


def _render_geography(months_df: pd.DataFrame, positions_df: pd.DataFrame) -> None:
    m = _latest_month(months_df)
    live = positions_df[(positions_df["month_id"] == m) & (positions_df["tab"] == "Live")].copy()
    if live.empty:
        st.info("No live holdings in this scope.")
        return
    with st.container(border=True):
        st.subheader("Where the money is \u2014 by country")
        geo = _exposure_table(live, "geography")
        _bar_h(geo.rename(columns={"geography": "country"}), "country", "fair_value")
        st.dataframe(geo, hide_index=True, width="stretch", column_config={
            "geography": st.column_config.TextColumn("Geography"),
            "fair_value": st.column_config.NumberColumn("Fair value", format="$%.1f"),
            "holdings": st.column_config.NumberColumn("Holdings"),
            "weight": st.column_config.NumberColumn("Weight", format="percent"),
        })

    live["region"] = live["geography"].map(_region_of)
    live["sector_n"] = live["sector"].map(_norm_sector)
    with st.container(border=True):
        st.subheader("Regional exposure")
        reg = _exposure_table(live, "region")
        cc = st.columns([3, 2])
        with cc[0]:
            _bar_h(reg, "region", "fair_value")
        with cc[1]:
            st.dataframe(reg, hide_index=True, width="stretch", column_config={
                "region": st.column_config.TextColumn("Region"),
                "fair_value": st.column_config.NumberColumn("Fair value", format="$%.1f"),
                "holdings": st.column_config.NumberColumn("Holdings"),
                "weight": st.column_config.NumberColumn("Weight", format="percent"),
            })

    with st.container(border=True):
        st.subheader("Region \u00d7 sector")
        rs = live.groupby(["region", "sector_n"], as_index=False)["carrying_value"].sum()
        heat = (alt.Chart(rs).mark_rect().encode(
                    x=alt.X("sector_n:N", axis=alt.Axis(title=None, labelAngle=-40)),
                    y=alt.Y("region:N", axis=alt.Axis(title=None)),
                    color=alt.Color("carrying_value:Q", scale=alt.Scale(scheme="greens"),
                                    legend=alt.Legend(title="Fair value, $m")),
                    tooltip=["region", "sector_n", alt.Tooltip("carrying_value:Q", format=",.1f")])
                .properties(height=220))
        st.altair_chart(heat, width="stretch")
    st.caption("Sourced from the Portfolio Summary's Geography field. Regions are a simple grouping "
               "(Americas / Europe / Middle East / Asia); UAE/UK counted as Middle East.")


def _render_sector(months_df: pd.DataFrame, positions_df: pd.DataFrame) -> None:
    m = _latest_month(months_df)
    live = positions_df[(positions_df["month_id"] == m) & (positions_df["tab"] == "Live")].copy()
    if live.empty:
        st.info("No live holdings in this scope.")
        return
    live["sector_n"] = live["sector"].map(_norm_sector)
    with st.container(border=True):
        st.subheader("What we are exposed to \u2014 by sector")
        sec = (_exposure_table(live.rename(columns={"sector_n": "_s"}), "_s")
               .rename(columns={"_s": "sector"}))
        _bar_h(sec, "sector", "fair_value")
        st.dataframe(sec, hide_index=True, width="stretch", column_config={
            "sector": st.column_config.TextColumn("Sector"),
            "fair_value": st.column_config.NumberColumn("Fair value", format="$%.1f"),
            "holdings": st.column_config.NumberColumn("Holdings"),
            "weight": st.column_config.NumberColumn("Weight", format="percent"),
        })

    with st.container(border=True):
        st.subheader("Contribution to value creation")
        vc = (live.groupby("sector_n", as_index=False)["gain"].sum()
              .rename(columns={"sector_n": "sector"}).sort_values("gain"))
        bar = (alt.Chart(vc).mark_bar().encode(
                    x=alt.X("gain:Q", axis=alt.Axis(title="Value created, USD m")),
                    y=alt.Y("sector:N", sort="-x", axis=alt.Axis(title=None)),
                    color=alt.condition(alt.datum.gain >= 0, alt.value("#2F6B45"),
                                        alt.value("#b3253a")),
                    tooltip=["sector", alt.Tooltip("gain:Q", format=",.1f")])
               .properties(height=max(220, 26 * len(vc))))
        st.altair_chart(bar, width="stretch")
    st.caption("Sector splits are sourced from the latest Portfolio Summary. Sector growth **over "
               "time** is not shown: the Portfolio Summary only carries the Sector column from "
               "Jun'26 onward, so we have no historical sector history to plot yet \u2014 flagged "
               "in Misc, not estimated.")


def _concentration_measures(live: pd.DataFrame):
    """Five exposure measures + weighted composite risk score
    (weights 30/25/15/15/15)."""
    comp = (live.assign(company=live["deal_name"].map(_consolidate_name))
            .groupby("company")["carrying_value"].sum())
    total = float(comp.sum())
    cshare = (comp / total).sort_values(ascending=False) if total else comp

    def _maxshare(col: str) -> float:
        g = live[live[col].astype(str) != ""].groupby(col)["carrying_value"].sum()
        return float(g.max() / total) if total and len(g) else 0.0

    measures = [
        ("Top five holdings", float(cshare.head(5).sum()), 0.30,
         "Share of value in the five largest positions"),
        ("Herfindahl index", float((cshare ** 2).sum()), 0.25,
         "Sum of squared weights; 1.00 is a single holding"),
        ("Largest single holding", float(cshare.iloc[0]) if len(cshare) else 0.0, 0.15,
         "Share of value in the largest position"),
        ("Largest jurisdiction", _maxshare("geography"), 0.15,
         "Share of value in one geography"),
        ("Largest sector", _maxshare("sector"), 0.15,
         "Share of value in one sector"),
    ]
    score = sum(r * w for _, r, w, _ in measures)
    return measures, score, cshare, total


def _risk_band(score: float) -> tuple[str, str]:
    if score < 0.35:
        return "Low", "#2F6B45"
    if score < 0.55:
        return "Moderate", "#C9862B"
    if score < 0.70:
        return "Elevated", "#D2691E"
    return "High", "#b3253a"


def _render_concentration(months_df: pd.DataFrame, positions_df: pd.DataFrame) -> None:
    with st.container(border=True):
        st.subheader("Value evolution")
        st.line_chart(months_df.set_index("as_of_date")[["live_invested", "live_carrying"]]
                      .rename(columns={"live_invested": "Invested", "live_carrying": "Fair value"}),
                      height=280, x_label="Month", y_label="USD, millions")
    m = _latest_month(months_df)
    live = positions_df[(positions_df["month_id"] == m) & (positions_df["tab"] == "Live")]
    if live.empty:
        st.info("No live holdings in this scope.")
        return
    measures, score, cshare, total = _concentration_measures(live)
    hhi = float((cshare ** 2).sum())
    band, band_color = _risk_band(score)

    with st.container(horizontal=True):
        st.metric("Concentration risk score", f"{score * 100:.1f}%", delta=band,
                  delta_color="off", border=True)
        st.metric("Top 5", f"{cshare.head(5).sum() * 100:.0f}%", border=True)
        st.metric("Top 10", f"{cshare.head(10).sum() * 100:.0f}%", border=True)
        st.metric("HHI", f"{hhi:.3f}", border=True)
        st.metric("Effective # holdings", (f"{1 / hhi:.1f}" if hhi else "n/a"), border=True)

    with st.container(border=True):
        st.subheader("Concentration risk score")
        # Banded gauge with a marker at the score.
        st.markdown(
            "<div style='position:relative;height:16px;border-radius:8px;overflow:hidden;"
            "background:linear-gradient(90deg,#2F6B45 0 35%,#C9862B 35% 55%,"
            "#D2691E 55% 70%,#b3253a 70% 100%);'>"
            f"<div style='position:absolute;left:calc({min(score,1.0)*100:.1f}% - 1px);top:-3px;"
            "width:3px;height:22px;background:#22302A;'></div></div>"
            "<div style='display:flex;justify-content:space-between;font-size:11px;"
            "color:#6b746a;margin-top:3px'><span>0% low</span><span>moderate</span>"
            "<span>elevated</span><span>high 100%</span></div>",
            unsafe_allow_html=True)
        mdf = pd.DataFrame(
            [{"Measure": n, "Reading": r, "Weight": w, "Contribution": r * w, "What it means": d}
             for n, r, w, d in measures])
        st.dataframe(mdf, hide_index=True, width="stretch", column_config={
            "Reading": st.column_config.NumberColumn("Reading", format="percent"),
            "Weight": st.column_config.NumberColumn("Weight", format="percent"),
            "Contribution": st.column_config.NumberColumn("Contribution", format="percent"),
        })
        st.caption(f"Weighted composite of five exposure measures \u2014 **{score * 100:.1f}%, "
                   f"{band}**. Bands: low &lt;35%, moderate to 55%, elevated to 70%, high above. "
                   f"A presentation aid, not a regulatory capital measure.")

    cc = st.columns(2)
    with cc[0]:
        with st.container(border=True):
            st.subheader("Largest holdings")
            top = cshare.head(12).rename("weight").reset_index()
            st.bar_chart(top.set_index("company"), height=300, x_label="Company", y_label="Share of value")
    with cc[1]:
        with st.container(border=True):
            st.subheader("Concentration curve")
            cum = cshare.sort_values(ascending=False).cumsum().reset_index(drop=True)
            curve = pd.DataFrame({"holdings": range(1, len(cum) + 1),
                                  "cumulative_share": cum.values})
            area = (alt.Chart(curve).mark_area(color="#2F6B45", opacity=0.16,
                        line={"color": "#2F6B45", "strokeWidth": 2}).encode(
                        x=alt.X("holdings:Q", axis=alt.Axis(title="Number of holdings")),
                        y=alt.Y("cumulative_share:Q", axis=alt.Axis(title="Cumulative share",
                                format="%")))
                    .properties(height=300))
            st.altair_chart(area, width="stretch")
            st.caption("How quickly value accumulates across holdings, largest first.")


def _render_portfolio_growth(months_df: pd.DataFrame, positions_df: pd.DataFrame) -> None:
    """How the live portfolio has grown since inception, and the quarterly cash
    picture — moved here from the Current-month tracker view."""
    mser = months_df.sort_values("month_id").copy()
    latest = mser.iloc[-1]
    first = mser.iloc[0]
    with st.container(horizontal=True):
        st.metric("Fair value now", _fmt_money(latest["live_carrying"]),
                  delta=f"from {_fmt_money(first['live_carrying'])} at {first['label']}", border=True)
        st.metric("Live holdings now", f"{int(latest['live_count']):,}",
                  delta=f"from {int(first['live_count'])} at {first['label']}", border=True)
        st.metric("Months tracked", f"{len(mser):,}", border=True)
    with st.container(border=True):
        st.subheader("Fair value since inception")
        _render_nav_since_inception(months_df, positions_df)
    with st.container(border=True):
        st.subheader("Invested vs fair value")
        st.line_chart(mser.set_index("as_of_date")[["live_invested", "live_carrying"]]
                      .rename(columns={"live_invested": "Invested", "live_carrying": "Fair value"}),
                      height=280, x_label="Month", y_label="USD, millions")

    with st.container(border=True):
        st.subheader("What drove the change \u2014 opened / closed per year")
        alld = positions_df.copy()
        opened = (alld.groupby("deal_name")["vintage"].min().astype(str)
                  .str.extract(r"(\d{4})")[0].dropna().astype(int))
        opened_by_year = opened.value_counts()
        exq = alld[alld["tab"] == "Exited"].groupby("deal_name")["month_id"].min()
        livemin = alld[alld["tab"] == "Live"].groupby("deal_name")["month_id"].min()
        closed_years = {d: int(str(exm)[:4]) for d, exm in exq.items()
                        if d in livemin.index and str(livemin[d]) < str(exm)}
        closed_by_year = pd.Series(closed_years).value_counts() if closed_years else pd.Series(dtype=int)
        years = sorted(set(opened_by_year.index) | set(closed_by_year.index))
        oc = pd.DataFrame({"year": years})
        oc["Opened"] = oc["year"].map(opened_by_year).fillna(0).astype(int)
        oc["Closed"] = oc["year"].map(closed_by_year).fillna(0).astype(int)
        long = oc.melt("year", value_vars=["Opened", "Closed"], var_name="type", value_name="count")
        chart = (alt.Chart(long).mark_bar().encode(
                    x=alt.X("year:O", axis=alt.Axis(title=None, labelAngle=0)),
                    xOffset="type:N",
                    y=alt.Y("count:Q", axis=alt.Axis(title="Investments")),
                    color=alt.Color("type:N", scale=alt.Scale(
                        domain=["Opened", "Closed"], range=["#2F6B45", "#b3253a"]),
                        legend=alt.Legend(title=None)),
                    tooltip=["year:O", "type:N", "count:Q"])
                 .properties(height=260))
        st.altair_chart(chart, width="stretch")
        st.caption("Opened = new investments by vintage year. Closed = positions we saw move "
                   "Live \u2192 Exited within our data window (Sep'22 on); exits before then aren't dated.")

    cf = _load_cashflows(str(PORTFOLIO_DB_PATH), _path_mtime(PORTFOLIO_DB_PATH))
    if len(cf):
        cf = cf.copy()
        cf["dt"] = pd.to_datetime(cf["flow_date"], errors="coerce")
        cf = cf.dropna(subset=["dt"])
        if len(cf):
            cf["quarter"] = cf["dt"].dt.to_period("Q").astype(str)
            q = (cf.groupby("quarter", as_index=False)
                 .agg(Contributions=("contribution", "sum"), Distributions=("distribution", "sum")))
            with st.container(border=True):
                st.subheader("Quarterly cash flows")
                st.bar_chart(q.set_index("quarter")[["Contributions", "Distributions"]], height=260,
                             x_label="Quarter", y_label="USD, millions")
                st.caption("From the Portfolio Summary's dated cash-flow sheets (CF Equity/Debt and CF Funds).")


def _render_misc(months_df: pd.DataFrame, positions_df: pd.DataFrame) -> None:
    """Housekeeping: reconciliation, source registry, cell-level diff and open
    action items. Absorbs the old Audit tab and the tracker's Data Quality view."""
    st.markdown("<h1 class='g42-serif'>Misc &amp; action items</h1>", unsafe_allow_html=True)
    if months_df.empty or positions_df.empty:
        st.info("No portfolio database yet.")
        return
    m = _latest_month(months_df)
    mrow = months_df[months_df["month_id"] == m].iloc[0]
    live = positions_df[(positions_df["month_id"] == m) & (positions_df["tab"] == "Live")]
    recompute = float(live["carrying_value"].sum())
    stored = float(mrow["live_carrying"] or 0)
    reconciles = abs(recompute - stored) < 0.5
    with st.container(horizontal=True):
        st.metric("Latest month", str(mrow["label"]), border=True)
        st.metric("Live carrying (sum of rows)", _fmt_money(recompute), border=True)
        st.metric("Reconciles to month total", "PASS" if reconciles else "CHECK", border=True)

    with st.container(border=True):
        st.subheader("Open action items")
        st.markdown(
            "- **FY2020 / FY2021 NAVs \u2014 TEMP FIX** \u2014 those two points on the since-inception "
            "chart are *estimated* (investments live by each year-end, held at their earliest "
            "tracker NAV, or at cost where unknown). **Please provide the real FY20/FY21 investment "
            "NAVs** so we can replace the estimate; positions exited before Sep\u201922 also need adding.\n"
            "- **Detail workbook** \u2014 not applicable: we ground on our own tracker. Extend NAV "
            "history before Sep'22 from our own historical records.\n"
            "- **Sector / Geography history** \u2014 the tracker only carries the Sector & Geography "
            "columns from Jun'26 onward; earlier months are blank, so historical sector/geography "
            "trends can't be plotted until backfilled.\n"
            "- **Domicile** \u2014 legal-KB domiciles are candidates; confirm before publishing.\n"
            "- **Loans bucket** \u2014 confirm whether any live holding is a standalone loan/note "
            "(currently none classified as debt).\n"
            "- **Fund figures** \u2014 North Summit / New Space use Capital Account Statements; keep "
            "watching for mis-tagged tracker cash-flow rows."
        )

    with st.container(border=True):
        st.subheader("Basis of preparation")
        st.markdown(
            "- Figures are USD millions from the monthly **Portfolio Summary** tracker (the Live / "
            "Exited register) — our single source of truth for the 26-name book.\n"
            "- Capital deployed = cumulative **Invested**; Fair value = **Carrying Value**; Value "
            "created = Fair value + Distributions − Invested (the tracker's own definition); "
            "MOIC = (Distributions + Fair value) / Invested.\n"
            "- Every figure traces to a tracker cell (see the source-cell citations in Company "
            "Profiles); source files are SHA-256 fingerprinted below.\n"
            "- Entity scope: **MOZN** = the MOZN holding company; **MGX** = the GX Investments / MGX "
            "sub-book (inside G42); **G42** = everything that isn't MOZN; **Consolidated** = all."
        )

    with st.container(border=True):
        st.subheader("IFRS classification & valuation — not yet in our data")
        st.warning(
            "These aren't carried in our tracker, so they are **not shown rather than estimated**; "
            "they will be captured from **our own accounting / valuation records** when available:\n\n"
            "- IFRS classification (FVOCI / FVTPL / equity-accounted) per holding.\n"
            "- Valuation methodology / independently-valued share.\n"
            "- Tie-out to our signed statutory statements."
        )

    src = _load_sources(str(PORTFOLIO_DB_PATH), _path_mtime(PORTFOLIO_DB_PATH))
    with st.container(border=True):
        st.subheader(f"Source registry \u2014 {len(src)} files (SHA-256 fingerprinted)")
        v = src.copy()
        if len(v):
            v["sha256"] = v["sha256"].str.slice(0, 16) + "\u2026"
        st.dataframe(v, hide_index=True, width="stretch", column_config={
            "size_bytes": st.column_config.NumberColumn("Bytes"),
        })
    with st.container(border=True):
        st.subheader("Build & version history")
        st.markdown(
            "- Entity scope selector (Consolidated / G42 / MGX / MOZN) across the position-derived views.\n"
            "- Analytics: value-creation waterfall + year-on-year, concentration-risk score, "
            "geography & sector cuts, portfolio growth (opened/closed per year).\n"
            "- Overview: holding-type & composition breakdowns, MGX sub-group, executive observations.\n"
            "- Company Profiles: investment register sourced from the Portfolio Summary + per-company cited cash movements.\n"
            "- Full parity analysis & roadmap in `docs/planning/Accounts_Team_Parity_Plan.md`."
        )
    _render_monthly_diff_celllevel(positions_df, months_df)
    st.info("All figures on this app are computed from our monthly Portfolio Summary "
            "(the Live / Exited register) — our single source of truth for the 26-name book. "
            "Source files are SHA-256 fingerprinted above.")


def _render_parking() -> None:
    """Holding area for sections removed from other tabs — nothing is deleted, so
    anything parked here can be restored to any tab on request."""
    st.markdown("<h1 class='g42-serif'>Parking</h1>", unsafe_allow_html=True)
    st.caption("A holding area for sections we take out of other tabs. Kept here so nothing is "
               "lost and any of it can be moved back on request. Empty for now.")


def _render_current_month() -> None:
    """Embed the generated tracker-style dashboard (company profiles) for the
    latest reporting month."""
    html_path = ROOT / "data" / "outputs" / "Tracker_Style_Dashboard.html"
    if not html_path.exists():
        st.info("Tracker dashboard not generated yet. Run "
                "`im_platform generate-tracker-dashboard` to build it.")
        return
    html = html_path.read_text(encoding="utf-8")
    components.html(html, height=1600, scrolling=True)


def _render_nav_evolution(months_df: pd.DataFrame, positions_df: pd.DataFrame) -> None:
    st.title("Portfolio NAV evolution")
    if months_df.empty:
        st.info("No portfolio time-series database found yet. Run "
                "`python -m scripts.portfolio_db.ingest_trackers` to build it.")
        return

    st.caption("Live-portfolio invested vs carrying value across the monthly Portfolio Summary "
               "reports (USD millions). Sourced from the portfolio time-series database.")

    latest = months_df.iloc[-1]
    peak_idx = months_df["live_carrying"].idxmax()
    peak = months_df.loc[peak_idx]
    with st.container(horizontal=True):
        st.metric("Months tracked", f"{len(months_df)}", border=True)
        st.metric("Range", f"{months_df.iloc[0]['label']} \u2192 {latest['label']}", border=True)
        st.metric("Latest carrying value", _fmt_money(latest["live_carrying"]), border=True)
        st.metric("Latest invested", _fmt_money(latest["live_invested"]), border=True)
        st.metric("Peak carrying value", f"{_fmt_money(peak['live_carrying'])} ({peak['label']})", border=True)

    chart_df = months_df.set_index("as_of_date")[["live_invested", "live_carrying"]].rename(
        columns={"live_invested": "Invested", "live_carrying": "Carrying value"})
    with st.container(border=True):
        st.subheader("Invested vs carrying value")
        st.line_chart(chart_df, height=340, x_label="Month", y_label="USD, millions")

    with st.container(border=True):
        st.subheader("Cumulative gain (carrying \u2212 invested)")
        gain_df = (months_df.set_index("as_of_date")["live_carrying"]
                   - months_df.set_index("as_of_date")["live_invested"]).rename("Unrealised gain")
        st.area_chart(gain_df, height=220, x_label="Month", y_label="USD, millions")

    _render_company_nav_explorer(positions_df)

    with st.expander("Monthly totals (table)"):
        table = months_df[["label", "live_count", "exited_count",
                            "live_invested", "live_carrying", "live_gain"]].copy()
        st.dataframe(
            table, hide_index=True, width="stretch",
            column_config={
                "label": st.column_config.TextColumn("Month"),
                "live_count": st.column_config.NumberColumn("Live #"),
                "exited_count": st.column_config.NumberColumn("Exited #"),
                "live_invested": st.column_config.NumberColumn("Invested", format="$%.0f"),
                "live_carrying": st.column_config.NumberColumn("Carrying value", format="$%.0f"),
                "live_gain": st.column_config.NumberColumn("Gain", format="$%.0f"),
            },
        )
        st.download_button(
            "Download monthly totals",
            data=table.to_csv(index=False).encode("utf-8"),
            file_name="portfolio_nav_evolution.csv",
            mime="text/csv",
            icon=":material/download:",
        )


def _render_company_nav_explorer(positions_df: pd.DataFrame) -> None:
    if positions_df.empty:
        return
    with st.container(border=True):
        st.subheader("Per-company carrying value over time")
        live = positions_df[positions_df["tab"] == "Live"].copy()
        if live.empty:
            st.info("No live positions available.")
            return
        # One line per company: collapse instrument qualifiers like (1)/(2)/(Debt).
        live["company"] = live["deal_name"].map(_consolidate_name)
        latest_date = live["as_of_date"].max()
        top = (live[live["as_of_date"] == latest_date]
               .groupby("company")["carrying_value"].sum()
               .sort_values(ascending=False).head(5).index.tolist())
        companies = sorted(live["company"].dropna().unique())
        picks = st.multiselect("Companies", companies, default=top)
        if not picks:
            st.caption("Select one or more companies to plot their carrying-value history.")
            return
        sub = live[live["company"].isin(picks)]
        pivot = sub.pivot_table(index="as_of_date", columns="company",
                                values="carrying_value", aggfunc="sum")
        st.line_chart(pivot, height=320, x_label="Month", y_label="Fair value, USD m")


def _render_monthly_diff(monthly_diff: pd.DataFrame) -> None:
    st.title(APP_TITLE)
    st.caption("Latest month-over-month movement from the persisted snapshot history.")

    if monthly_diff.empty:
        st.info("No month-over-month differences are available yet.")
        return

    previous_month = str(monthly_diff["previous_month"].iloc[0])
    current_month = str(monthly_diff["current_month"].iloc[0])

    with st.container(horizontal=True):
        st.metric("Comparison", f"{_format_month(previous_month)} -> {_format_month(current_month)}", border=True)
        st.metric("Changed rows", f"{len(monthly_diff):,}", border=True)
        st.metric("Carrying value delta", _fmt_money(monthly_diff["delta_carrying_value"].sum()), border=True)
        st.metric("Gain delta", _fmt_money(monthly_diff["delta_gain"].sum()), border=True)

    display_cols = [
        "change_type",
        "deal_name",
        "previous_month",
        "current_month",
        "previous_tab",
        "current_tab",
        "changed_metrics",
        "delta_committed",
        "delta_invested",
        "delta_distributions",
        "delta_carrying_value",
        "delta_gain",
        "delta_irr",
    ]
    visible = monthly_diff[[col for col in display_cols if col in monthly_diff.columns]].copy()
    visible = visible.sort_values(["change_type", "deal_name"], kind="stable")

    with st.container(border=True):
        st.subheader("Monthly diff")
        st.dataframe(
            visible,
            hide_index=True, width="stretch",
            column_config={
                "change_type": st.column_config.TextColumn("Change"),
                "deal_name": st.column_config.TextColumn("Deal"),
                "previous_month": st.column_config.TextColumn("Previous"),
                "current_month": st.column_config.TextColumn("Current"),
                "previous_tab": st.column_config.TextColumn("Prev tab"),
                "current_tab": st.column_config.TextColumn("Current tab"),
                "changed_metrics": st.column_config.TextColumn("Changed metrics"),
                "delta_committed": st.column_config.NumberColumn("Committed delta", format="$%.1f"),
                "delta_invested": st.column_config.NumberColumn("Invested delta", format="$%.1f"),
                "delta_distributions": st.column_config.NumberColumn("Distributions delta", format="$%.1f"),
                "delta_carrying_value": st.column_config.NumberColumn("Carrying delta", format="$%.1f"),
                "delta_gain": st.column_config.NumberColumn("Gain delta", format="$%.1f"),
                "delta_irr": st.column_config.NumberColumn("IRR delta", format="percent"),
            },
        )

        csv = visible.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download monthly diff",
            data=csv,
            file_name="portfolio_monthly_diff.csv",
            mime="text/csv",
            icon=":material/download:",
        )


def _render_kpis(snapshot: pd.DataFrame) -> None:
    with st.container(horizontal=True):
        st.metric("Deals", f"{len(snapshot):,}", border=True)
        st.metric("Committed", _fmt_money(snapshot["committed"].sum()), border=True)
        st.metric("Invested", _fmt_money(snapshot["invested"].sum()), border=True)
        st.metric("Carrying value", _fmt_money(snapshot["carrying_value"].sum()), border=True)
        st.metric("Gain", _fmt_money(snapshot["gain"].sum()), border=True)


def _render_snapshot_table(snapshot: pd.DataFrame) -> None:
    display_cols = [
        "tab",
        "deal_name",
        "status",
        "investing_entity",
        "vintage",
        "instrument",
        "committed",
        "invested",
        "remaining_commitment",
        "distributions",
        "carrying_value",
        "gain",
        "tvpi",
        "irr",
        "valuation_date",
        "assumption_note",
    ]
    visible = snapshot[[col for col in display_cols if col in snapshot.columns]].copy()
    visible = visible.sort_values(["tab", "section", "deal_name"], kind="stable")

    with st.container(border=True):
        st.subheader("Portfolio snapshot")
        st.dataframe(
            visible,
            hide_index=True, width="stretch",
            column_config={
                "tab": st.column_config.TextColumn("Tab"),
                "deal_name": st.column_config.TextColumn("Deal"),
                "status": st.column_config.TextColumn("Status"),
                "investing_entity": st.column_config.TextColumn("Investing entity"),
                "committed": st.column_config.NumberColumn("Committed", format="$%.1f"),
                "invested": st.column_config.NumberColumn("Invested", format="$%.1f"),
                "remaining_commitment": st.column_config.NumberColumn("Remaining", format="$%.1f"),
                "distributions": st.column_config.NumberColumn("Distributions", format="$%.1f"),
                "carrying_value": st.column_config.NumberColumn("Carrying value", format="$%.1f"),
                "gain": st.column_config.NumberColumn("Gain", format="$%.1f"),
                "tvpi": st.column_config.NumberColumn("TVPI", format="%.2fx"),
                "irr": st.column_config.NumberColumn("IRR", format="percent"),
                "valuation_date": st.column_config.TextColumn("Valuation date"),
                "assumption_note": st.column_config.TextColumn("Source / last-revised note"),
            },
        )

        csv = visible.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download selected snapshot",
            data=csv,
            file_name="portfolio_snapshot.csv",
            mime="text/csv",
            icon=":material/download:",
        )


def _format_month(value: str) -> str:
    parsed = pd.to_datetime(f"{value}-01", errors="coerce")
    if pd.isna(parsed):
        return value
    return parsed.strftime("%b %Y")


def _fmt_money(value: float) -> str:
    if pd.isna(value):
        value = 0.0
    return f"${value:,.1f}m"


if __name__ == "__main__":
    main()