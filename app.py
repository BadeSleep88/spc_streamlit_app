import json
import threading
from datetime import datetime

import streamlit as st

from scraper import StratfordPadelMatchScraper

# --------------------
# Page config
# --------------------
st.set_page_config(
    page_title="SPC Padel Match Finder",
    page_icon="🎾",
    layout="wide",
)

st.title("🎾 SPC Padel Match Finder")
st.caption("Private tool")

st.divider()

# --------------------
# Search settings
# --------------------
st.subheader("🔍 Search settings")

col1, col2 = st.columns(2)
with col1:
    level_min = st.number_input("Minimum rating", min_value=1.5, max_value=7.0, value=2.5, step=0.5)
with col2:
    level_max = st.number_input("Maximum rating", min_value=1.5, max_value=7.0, value=3.0, step=0.5)

weeks = st.slider("Weeks to search ahead", min_value=1, max_value=5, value=5)
st.divider()

# --------------------
# Time filters
# --------------------
st.subheader("⏰ Time filters")


def day_block(label, default_start, default_end):
    enabled = st.checkbox(label, value=True)
    if not enabled:
        return {"enabled": False}
    start, end = st.slider(f"{label} time window", 8, 22, (default_start, default_end))
    return {"enabled": True, "start_hour": start, "end_hour": end}


weekday_cfg = {
    "monday": day_block("Monday", 8, 22),
    "tuesday": day_block("Tuesday", 8, 22),
    "wednesday": day_block("Wednesday", 8, 22),
    "thursday": day_block("Thursday", 8, 22),
    "friday": day_block("Friday", 8, 22),
}

weekend_cfg = {
    "saturday": day_block("Saturday", 8, 22),
    "sunday": day_block("Sunday", 8, 22),
}

st.divider()

# --------------------
# Session state for non-blocking scraper
# --------------------
if "scrape_status" not in st.session_state:
    st.session_state.scrape_status = "idle"
if "scrape_results" not in st.session_state:
    st.session_state.scrape_results = []
if "scrape_time" not in st.session_state:
    st.session_state.scrape_time = None


# --------------------
# Cached scraper function
# --------------------
@st.cache_data(show_spinner=False)
def cached_scraper(level_min, level_max, weeks, weekday_cfg, weekend_cfg):
    scraper = StratfordPadelMatchScraper()
    scraper.config["search_settings"]["level_range"]["min"] = level_min
    scraper.config["search_settings"]["level_range"]["max"] = level_max
    scraper.config["search_settings"]["weeks_to_search"] = weeks
    scraper.config["time_filters"]["weekdays"] = weekday_cfg
    scraper.config["time_filters"]["weekends"] = weekend_cfg
    scraper.config["debug_settings"]["verbose_logging"] = False
    scraper.config["debug_settings"]["save_raw_html"] = False

    all_matches = []
    for start_date, end_date in scraper.get_week_ranges():
        html = scraper.fetch_matches_page(start_date, end_date)
        week_matches = scraper.parse_matches(html)
        all_matches.extend(week_matches)

    filtered_matches = scraper.filter_matches_by_time(all_matches)
    matches_with_dates = scraper.add_date_info(filtered_matches)
    return matches_with_dates


# --------------------
# Function to display matches
# --------------------
def display_matches_grid(matches):
    if not matches:
        st.warning("No matches found matching the criteria.")
        return

    st.markdown(f"### 🎾 Total matches: {len(matches)}")
    st.divider()

    num_cols = 2
    for i in range(0, len(matches), num_cols):
        cols = st.columns(num_cols)
        for j, match in enumerate(matches[i : i + num_cols]):
            with cols[j]:
                st.markdown(
                    f"""
                    <div style="
                        padding: 10px; 
                        border-radius: 10px; 
                        background-color: #013A63;  /* French Navy Blue */
                        color: white;               /* White text */
                        margin-bottom: 10px;
                    ">
                        <p style='margin:2px'><strong>{match['date']} ({match['day_of_week']})</strong></p>
                        <p style='margin:2px'>Time: {match['time']}</p>
                        <p style='margin:2px'>Level: {match['level_range']}</p>
                        <p style='margin:2px'>Type: {match['type']}</p>
                        {"<p style='margin:2px'><a href=\"" + match['link'].replace('Match.aspx', 'Share.aspx') + "\" target='_blank' style='color:#1E90FF; text-decoration: underline;'>🔗 Match Link</a></p>" if match.get("link") else ""}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


# --------------------
# Run scraper button
# --------------------
st.subheader("🚀 Run search")

if st.button("Search Matches", type="primary"):
    if st.session_state.scrape_status == "running":
        st.warning("Scraper is already running!")
    else:
        st.session_state.scrape_status = "running"

        def run_threaded_scraper():
            results = cached_scraper(level_min, level_max, weeks, weekday_cfg, weekend_cfg)
            st.session_state.scrape_results = results
            st.session_state.scrape_status = "done"
            st.session_state.scrape_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        threading.Thread(target=run_threaded_scraper, daemon=True).start()

# --------------------
# Show status / results
# --------------------
if st.session_state.scrape_status == "running":
    st.info("Scraper is running... please wait 🕐")

if st.session_state.scrape_status == "done":
    st.success(f"Scraping done! Results generated at {st.session_state.scrape_time}")
    display_matches_grid(st.session_state.scrape_results)
