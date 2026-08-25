"""Tracker 2 — Portfolio Book of Record.

A standalone Streamlit app that reuses the shared engine and renderers from the
Tracker 1 codebase (`streamlit_app`) but presents ONLY the Book of Record views.
Run on its own port, e.g.:

    python -m streamlit run src/frontend/tracker2_app.py --server.port 8502
"""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from streamlit_app import (
    PORTFOLIO_DB_PATH,
    _BOR_VIEWS,
    _SCOPE_OPTIONS,
    _configured_credentials,
    _init_state,
    _inject_theme,
    _load_portfolio_months,
    _load_portfolio_positions,
    _path_mtime,
    _render_book_of_record,
    _render_login,
    _scoped_months,
    _scoped_positions,
)

BOR_TITLE = "Portfolio Book of Record"


def main() -> None:
    st.set_page_config(page_title=BOR_TITLE, layout="wide",
                       page_icon=":material/menu_book:", initial_sidebar_state="collapsed")
    _inject_theme()
    _init_state()

    expected_user, expected_password = _configured_credentials()
    if not (expected_user and expected_password):
        st.session_state["authenticated"] = True
        if not st.session_state.get("username"):
            st.session_state["username"] = "guest"
    if not st.session_state["authenticated"]:
        _render_login()
        return

    months_df = _load_portfolio_months(str(PORTFOLIO_DB_PATH), _path_mtime(PORTFOLIO_DB_PATH))
    positions_df = _load_portfolio_positions(str(PORTFOLIO_DB_PATH), _path_mtime(PORTFOLIO_DB_PATH))

    top = st.columns([7, 1.1, 1.1], vertical_alignment="center")
    with top[0]:
        st.markdown(
            "<div class='g42-brand'><span class='g42-mark'>G42</span>"
            "<span class='g42-title'>Portfolio Book of Record</span>"
            "<span class='conf-badge'>Confidential</span></div>", unsafe_allow_html=True)
    with top[1]:
        if st.button("Theme", key="hdr_theme", icon=":material/brightness_6:"):
            st.session_state["_flip_theme"] = True
    with top[2]:
        if st.button("Sign out", key="hdr_signout", icon=":material/logout:"):
            st.session_state["authenticated"] = False
            st.session_state["username"] = ""
            st.rerun()
    if st.session_state.pop("_flip_theme", False):
        components.html(
            "<script>const k='stActiveTheme-/-v2';const ls=window.parent.localStorage;"
            "let c='Light';try{c=JSON.parse(ls.getItem(k)||'\"Light\"');}catch(e){}"
            "ls.setItem(k,JSON.stringify(c==='Dark'?'Light':'Dark'));"
            "window.parent.location.reload();</script>", height=0)

    # View band on top (binder/folder tabs), entity-scope band below it.
    view = st.segmented_control(
        "Book of Record view", _BOR_VIEWS, default="Overview",
        key="bor_view", label_visibility="collapsed") or "Overview"
    # The operational Portfolio view already segments by investing entity, so it
    # carries its own sub-tabs (Live / Exited / Vintage / …) and needs no scope band.
    if view == "Portfolio":
        scope = "Consolidated"
    else:
        scope = st.segmented_control(
            "Entity scope", _SCOPE_OPTIONS, default="Consolidated",
            key="scope_sel", label_visibility="collapsed") or "Consolidated"
        st.markdown("<hr style='margin:8px 0 16px;border-top:2px solid #2F6B45'>",
                    unsafe_allow_html=True)

    s_months = _scoped_months(months_df, positions_df, scope)
    s_positions = _scoped_positions(positions_df, scope)
    _render_book_of_record(view, s_months, s_positions)


if __name__ == "__main__":
    main()
