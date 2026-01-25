import json
from datetime import datetime

import streamlit as st

from scraper import StratfordPadelMatchScraper  # Make sure this is your scraper class

# --------------------
# Page config
# --------------------
st.set_page_config(
    page_title="Stratford Padel Match Finder",
    page_icon="🎾",
    layout="centered",
)

st.title("🎾 Stratford Padel Match Finder")
st.caption("Private tool · Configurable · Streamlit UI")

st.divider()

# --------------------
# Search settings
# --------------------
st.subheader("🔍 Search settings")

col1, col2 = st.columns(2)

with col1:
    level_min = st.number_input(
        "Minimum rating",
        min_value=1.0,
        max_value=5.0,
        value=2.0,
        step=0.25,
    )

with col2:
    level_max = st.number_input(
        "Maximum rating",
        min_value=1.0,
        max_value=5.0,
        value=2.5,
        step=0.25,
    )

weeks = st.slider(
    "Weeks to search ahead",
    min_value=1,
    max_value=6,
    value=3,
)

st.divider()

# --------------------
# Time filters
# --------------------
st.subheader("⏰ Time filters")


def day_block(label, default_start, default_end):
    enabled = st.checkbox(label, value=True)
    if not enabled:
        return {"enabled": False}

    start, end = st.slider(
        f"{label} time window",
        min_value=0,
        max_value=23,
        value=(default_start, default_end),
    )

    return {
        "enabled": True,
        "start_hour": start,
        "end_hour": end,
    }


# Weekdays
weekday_cfg = {
    "monday": day_block("Monday", 19, 23),
    "tuesday": day_block("Tuesday", 18, 23),
    "wednesday": day_block("Wednesday", 19, 23),
    "thursday": day_block("Thursday", 19, 23),
    "friday": day_block("Friday", 18, 23),
}

weekend_cfg = {
    "saturday": day_block("Saturday", 9, 22),
    "sunday": day_block("Sunday", 9, 22),
}

st.divider()


# --------------------
# Display function for matches
# --------------------
def display_matches_streamlit(matches):
    if not matches:
        st.warning("No matches found matching the criteria.")
        return

    st.markdown(f"### 🎾 Total matches: {len(matches)}")
    st.markdown("---")

    for i, match in enumerate(matches, 1):
        with st.expander(f"Match {i}: {match['date']} ({match['day_of_week']})"):
            col1, col2 = st.columns([2, 1])
            with col1:
                st.markdown(f"**Time:** {match['time']}")
                st.markdown(f"**Level:** {match['level_range']}")
                st.markdown(f"**Type:** {match['type']}")
            with col2:
                if match.get("link"):
                    st.markdown(f"[🔗 Match Link]({match['link']})", unsafe_allow_html=True)
            st.divider()


# --------------------
# Run scraper
# --------------------
st.subheader("🚀 Run search")

if st.button("Run scraper", type="primary"):
    with st.spinner("Searching for matches..."):
        scraper = StratfordPadelMatchScraper()

        # Apply Streamlit config
        scraper.config["search_settings"]["level_range"]["min"] = level_min
        scraper.config["search_settings"]["level_range"]["max"] = level_max
        scraper.config["search_settings"]["weeks_to_search"] = weeks
        scraper.config["time_filters"]["weekdays"] = weekday_cfg
        scraper.config["time_filters"]["weekends"] = weekend_cfg
        scraper.config["debug_settings"]["verbose_logging"] = True
        scraper.config["debug_settings"]["save_raw_html"] = False

        # Fetch matches across all weeks
        all_matches = []
        for start_date, end_date in scraper.get_week_ranges():
            html = scraper.fetch_matches_page(start_date, end_date)
            week_matches = scraper.parse_matches(html)
            all_matches.extend(week_matches)

        # Filter and add date info
        filtered_matches = scraper.filter_matches_by_time(all_matches)
        matches_with_dates = scraper.add_date_info(filtered_matches)

        # Display in Streamlit
        display_matches_streamlit(matches_with_dates)

    st.success("Search complete")
