import streamlit as st

from activities_scraper import StratfordPadelActivityScraper
from matches_scraper import StratfordPadelMatchScraper

# --------------------
# Page config
# --------------------
st.set_page_config(
    page_title="SPC Match & Activity Finder",
    page_icon="🎾",
    layout="wide",
)

# --------------------
# Custom CSS for bigger tabs and full-width
# --------------------
st.markdown(
    """
    <style>
    /* Make tabs bigger */
    div[data-baseweb="tab-list"] button {
        font-size: 18px;
        padding: 12px 24px;
    }
    /* Make cards full width */
    .full-width-card {
        width: 100%;
        margin-bottom: 12px;
        padding: 12px;
        border-radius: 12px;
        background: #013A63;
        color: white;
    }
    /* Add spacing between controls */
    .control-spacing {
        margin-bottom: 12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def line(icon, label, value):
    if value not in [None, "", " "]:
        return f"{icon} <b>{label}:</b> {value}<br>"
    return ""


st.title("🎾 SPC Finder")
st.caption("Private tool")
st.divider()

# --------------------
# Tabs
# --------------------
tab_games, tab_activities = st.tabs(["🎾 Find Games", "🏃 Find Activities"])

# =====================================================
# 🎾 FIND GAMES TAB
# =====================================================
with tab_games:
    st.subheader("Find Matches")

    # Level inputs
    col1, col2 = st.columns(2)
    with col1:
        level_min = st.number_input("Min level", 1.5, 7.0, 3.0, 0.5, key="g_min_level")
    with col2:
        level_max = st.number_input("Max level", 1.5, 7.0, 3.5, 0.5, key="g_max_level")

    weeks = st.slider("Weeks ahead", 1, 5, 5, key="g_weeks")

    st.subheader("⏰ Time filters")

    def day_cfg(label, default_start=18, default_end=23):
        enabled = st.checkbox(label, True, key=f"g_{label}")
        if not enabled:
            return {"enabled": False}
        start, end = st.slider(f"{label} time", 8, 23, (default_start, default_end), key=f"g_s_{label}")
        return {"enabled": True, "start_hour": start, "end_hour": end}

    weekdays_g = {
        day: day_cfg(day.capitalize()) for day in ["monday", "tuesday", "wednesday", "thursday", "friday"]
    }
    weekends_g = {day: day_cfg(day.capitalize()) for day in ["saturday", "sunday"]}

    @st.cache_data(ttl=3600, show_spinner=False)
    def run_match_search(level_min, level_max, weeks, weekdays, weekends):
        scraper = StratfordPadelMatchScraper()
        scraper.config["search_settings"]["level_range"]["min"] = level_min
        scraper.config["search_settings"]["level_range"]["max"] = level_max
        scraper.config["search_settings"]["weeks_to_search"] = weeks
        scraper.config["time_filters"]["weekdays"] = weekdays
        scraper.config["time_filters"]["weekends"] = weekends

        all_matches = []
        for start, end in scraper.get_week_ranges():
            html = scraper.fetch_matches_page(start, end)
            if html:
                all_matches.extend(scraper.parse_matches(html))

        filtered = scraper.filter_matches_by_time(all_matches)
        return scraper.add_date_info(filtered)

    if st.button("Search Matches", type="primary", key="search_games"):
        with st.spinner("Searching matches..."):
            matches = run_match_search(level_min, level_max, weeks, weekdays_g, weekends_g)

        if not matches:
            st.warning("No matches found")
        else:
            for m in matches:
                st.markdown(
                    f"""
                    <div class="full-width-card">
                        <b>📅 {m['date']} ({m['day_of_week']})</b><br>
                        {line("⏰", "Start Time", m.get("time"))}
                        {line("👤", "Level Range", m.get("level_range"))}

                        <a href="{m['link'].replace('Match.aspx','Share.aspx')}" 
                           style="color:#1E90FF" target="_blank">🔗 Open booking</a>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

# =====================================================
# 🏃 FIND ACTIVITIES TAB
# =====================================================
with tab_activities:
    st.subheader("Find Activities")

    days_ahead = st.slider("Days ahead", 1, 42, 7, key="a_days_ahead")

    st.subheader("🎾 Activity types")

    ACTIVITY_OPTIONS = [
        "Train and Play Green",
        "Train and Play Blue",
        "Train and Play Orange",
        "Train and Play Yellow",
        "Padel Academy Green",
        "Padel Academy Orange",
        "Padel Academy Blue",
        "Padel Academy Yellow",
        "Ball machine training",
        "Private Class",
        "PadelConnect Intermediates",
        "PadelConnect Beginners",
        "PadelConnect Improvers",
        "PadelConnect Advanced",
        "Matchplay with coach",
    ]
    DEFAULT_OPTIONS = [
        "Private Class",
        "Train and Play Green",
        "Padel Academy Green",
    ]

    selected_activities = st.multiselect(
        "Select activities", options=ACTIVITY_OPTIONS, default=DEFAULT_OPTIONS, key="a_selected_activities"
    )

    st.subheader("⏰ Time filters")

    def activity_day(label, default_start=8, default_end=22):
        enabled = st.checkbox(label, True, key=f"a_{label}")
        if not enabled:
            return {"enabled": False}
        start, end = st.slider(f"{label} time", 8, 22, (default_start, default_end), key=f"a_s_{label}")
        return {"enabled": True, "start_hour": start, "end_hour": end}

    weekdays_a = {
        day: activity_day(day.capitalize())
        for day in ["monday", "tuesday", "wednesday", "thursday", "friday"]
    }
    weekends_a = {day: activity_day(day.capitalize()) for day in ["saturday", "sunday"]}

    @st.cache_data(ttl=3600, show_spinner=False)
    def run_activity_search(days_ahead, weekdays, weekends, selected_activities):
        scraper = StratfordPadelActivityScraper()
        scraper.config["activity_search"]["days_to_search"] = days_ahead
        scraper.config["time_filters"]["weekdays"] = weekdays
        scraper.config["time_filters"]["weekends"] = weekends
        scraper.config["activity_search"]["activity_name"] = list(selected_activities)
        return scraper.search_for_sessions()  # returns filtered + sorted sessions

    if st.button("🔍 Search Activities", type="primary", key="search_activities"):
        if not selected_activities:
            st.warning("Please select at least one activity type.")
        else:
            with st.spinner("Searching activities..."):
                activities = run_activity_search(
                    days_ahead, weekdays_a, weekends_a, tuple(selected_activities)
                )

            if not activities:
                st.info("No activities found for the selected filters.")
            else:
                st.success(f"Found {len(activities)} activities")

                for a in activities:
                    st.markdown(
                        f"""
                        <div class="full-width-card">
                            <b>{a['type']}</b><br>
                            📅 {a['date']} ({a['day_of_week']})<br>

                            {line("⏰", "Time", a.get("time"))}
                            {line("👤", "Instructor", a.get("instructor"))}
                            {line("🎟️", "Vacancies", a.get("vacancies"))}
                            {line("📍", "Court", a.get("court"))}

                            <a href="{a['sign_up_link'].replace('Info.aspx','Share.aspx')}"
                            target="_blank"
                            style="color:#4FC3F7;font-weight:bold">
                            🔗 Open booking
                            </a>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
