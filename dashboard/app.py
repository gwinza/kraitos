"""
Kraitos Streamlit dashboard.

Run with:
    streamlit run dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.data_service import DashboardDataService, DashboardSnapshot

st.set_page_config(
    page_title="Kraitos Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

REFRESH_SECONDS = 10


@st.cache_data(ttl=REFRESH_SECONDS)
def load_snapshot() -> DashboardSnapshot:
    return DashboardDataService(PROJECT_ROOT).load_snapshot()


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _money(value: float) -> str:
    return f"${value:,.2f}"


def render_header(snapshot: DashboardSnapshot) -> None:
    left, right = st.columns([3, 1])
    with left:
        st.title("Kraitos")
        st.caption("Modular forex trading platform")
    with right:
        mode_label = "LIVE" if snapshot.mode == "live" else "PAPER"
        mode_color = "#dc2626" if snapshot.mode == "live" else "#2563eb"
        st.markdown(
            f"""
            <div style="text-align:right; padding-top:1rem;">
                <span style="
                    background:{mode_color};
                    color:white;
                    padding:0.35rem 0.75rem;
                    border-radius:999px;
                    font-weight:600;
                    font-size:0.85rem;
                ">{mode_label} MODE</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_metrics(snapshot: DashboardSnapshot) -> None:
    cols = st.columns(4)
    cols[0].metric("Account Balance", _money(snapshot.account_balance))
    cols[1].metric("Equity", _money(snapshot.equity))
    cols[2].metric("Win Rate", _pct(snapshot.win_rate))
    cols[3].metric("Max Drawdown", _pct(snapshot.max_drawdown))


def render_pair_rankings(snapshot: DashboardSnapshot) -> None:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Best Pairs")
        if snapshot.best_pairs:
            for pair in snapshot.best_pairs:
                st.success(pair)
        else:
            st.info("No pair data yet")
    with col2:
        st.subheader("Worst Pairs")
        if snapshot.worst_pairs:
            for pair in snapshot.worst_pairs:
                st.warning(pair)
        else:
            st.info("No pair data yet")


def render_regime_and_decision(snapshot: DashboardSnapshot) -> None:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Current Market Regime")
        st.metric(
            label="Regime",
            value=snapshot.regime.replace("_", " ").title(),
            delta=f"{snapshot.regime_confidence * 100:.0f}% confidence" if snapshot.regime_confidence else None,
        )
        st.write(snapshot.regime_reason)

    with col2:
        st.subheader("Latest Trade Decision")
        st.metric("Action", snapshot.latest_decision_action.replace("_", " ").title())
        st.write(snapshot.latest_decision)


def render_tables(snapshot: DashboardSnapshot) -> None:
    st.subheader("Open Trades")
    if snapshot.open_trades.empty:
        st.info("No open trades")
    else:
        st.dataframe(snapshot.open_trades, use_container_width=True, hide_index=True)

    left, right = st.columns(2)

    with left:
        st.subheader("Recent Trades")
        if snapshot.recent_trades.empty:
            st.info("No recent trades")
        else:
            st.dataframe(snapshot.recent_trades, use_container_width=True, hide_index=True)

    with right:
        st.subheader("Rejected Trades")
        if snapshot.rejected_trades.empty:
            st.info("No rejected trades")
        else:
            st.dataframe(snapshot.rejected_trades, use_container_width=True, hide_index=True)


def main() -> None:
    st.markdown(
        """
        <style>
            .block-container { padding-top: 1.5rem; max-width: 1200px; }
            [data-testid="stMetricValue"] { font-size: 1.6rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    try:
        snapshot = load_snapshot()
    except Exception as exc:
        st.error(f"Failed to load dashboard data: {exc}")
        return

    render_header(snapshot)
    st.divider()
    render_metrics(snapshot)
    st.divider()
    render_pair_rankings(snapshot)
    st.divider()
    render_regime_and_decision(snapshot)
    st.divider()
    render_tables(snapshot)

    st.caption(f"Auto-refresh every {REFRESH_SECONDS}s")


if __name__ == "__main__":
    main()
