import streamlit as st

from activities import StratfordPadelActivityScraper
from scraper import StratfordPadelMatchScraper

# --------------------
# Page config
# --------------------
st.set_page_config(
    page_title="SPC Match & Activity Finder",
    page_icon="🎾",
    layout="wide",
)

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
    st.subheader("Search Padel Matches")

    col1, col2 = st.columns(2)
    with col1:
        level_min = st.number_input("Min level", 1.5, 7.0, 2.5, 0.5)
    with col2:
        level_max = st.number_input("Max level", 1.5, 7.0, 3.0, 0.5)

    weeks = st.slider("Weeks ahead", 1, 5, 5)

    st.subheader("⏰ Time filters")

    def day_cfg(label):
        enabled = st.checkbox(label, True)
        if not enabled:
            return {"enabled": False}
        start, end = st.slider(f"{label} time", 8, 23, (18, 23))
        return {"enabled": True, "start_hour": start, "end_hour": end}

    weekdays = {
        "monday": day_cfg("Monday"),
        "tuesday": day_cfg("Tuesday"),
        "wednesday": day_cfg("Wednesday"),
        "thursday": day_cfg("Thursday"),
        "friday": day_cfg("Friday"),
    }

    weekends = {
        "saturday": day_cfg("Saturday"),
        "sunday": day_cfg("Sunday"),
    }

    @st.cache_data(ttl=3600)
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

    if st.button("Search Matches", type="primary"):
        with st.spinner("Searching matches..."):
            matches = run_match_search(level_min, level_max, weeks, weekdays, weekends)

        if not matches:
            st.warning("No matches found")
        else:
            for m in matches:
                st.markdown(
                    f"""
                    <div style="background:#013A63;color:white;padding:10px;border-radius:10px;margin-bottom:8px">
                        <b>{m['date']} ({m['day_of_week']})</b><br>
                        ⏰ {m['time']}<br>
                        🎯 {m['level_range']}<br>
                        <a href="{m['link'].replace('Match.aspx','Share.aspx')}"
                           style="color:#1E90FF" target="_blank">🔗 Open</a>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

# =====================================================
# 🏃 FIND ACTIVITIES TAB
# =====================================================
with tab_activities:
    st.subheader("🏃 Find Activities at Stratford Padel Club")

    # -------------------------
    # Search controls
    # -------------------------
    days_ahead = st.slider("Days ahead", 1, 42, 7)

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
        "Train and Play Green",
        "Padel Academy Green",
        "Private Class",
        "PadelConnect Intermediates",
    ]

    selected_activities = st.multiselect(
        "Select activities",
        options=ACTIVITY_OPTIONS,
        default=DEFAULT_OPTIONS,
    )

    st.subheader("⏰ Time filters")

    def activity_day(label, default_start, default_end):
        enabled = st.checkbox(label, True, key=f"a_{label}")
        if not enabled:
            return {"enabled": False}

        start, end = st.slider(
            f"{label} time",
            8,
            22,
            (default_start, default_end),
            key=f"s_{label}",
        )

        return {
            "enabled": True,
            "start_hour": start,
            "end_hour": end,
        }

    time_filters = {
        "monday": activity_day("Monday", 8, 22),
        "tuesday": activity_day("Tuesday", 8, 22),
        "wednesday": activity_day("Wednesday", 8, 22),
        "thursday": activity_day("Thursday", 8, 22),
        "friday": activity_day("Friday", 8, 22),
        "saturday": activity_day("Saturday", 8, 22),
        "sunday": activity_day("Sunday", 8, 22),
    }

    # -------------------------
    # Cached search runner
    # -------------------------
    @st.cache_data(ttl=3600, show_spinner=False)
    def run_activity_search(days_ahead, time_filters, keywords):
        scraper = StratfordPadelActivityScraper()
        scraper.config["days_ahead"] = days_ahead
        scraper.config["time_filters"] = time_filters
        scraper.config["keywords"] = keywords
        print(scraper.config)
        return scraper.search()

    # -------------------------
    # Run search
    # -------------------------
    if st.button("🔍 Search Activities", type="primary"):
        if not selected_activities:
            st.warning("Please select at least one activity type.")
        else:
            with st.spinner("Searching activities..."):
                activities = run_activity_search(
                    days_ahead,
                    time_filters,
                    tuple(selected_activities),  # cache-safe
                )
                print(activities)
            if not activities:
                st.info("No activities found for the selected filters.")
            else:
                st.success(f"Found {len(activities)} activities")

                for a in activities:
                    st.markdown(
                        f"""
                        <div style="
                            background:#013A63;
                            color:white;
                            padding:12px;
                            border-radius:12px;
                            margin-bottom:10px;
                        ">
                            <b>{a['title']}</b><br>
                            📅 {a['date']} ({a['day_name']})<br>
                            ⏰ {a['time']}<br>
                            {"👤 <b>Instructor:</b> " + a["instructor"] + "<br>" if a.get("instructor") else ""}
                            {"🎟️ <b>Vacancies:</b> " + str(a["vacancies"]) + "<br>" if a.get("vacancies") is not None else ""}
                            {"🎯 <b>Level:</b> " + a["levels"] + "<br>" if a.get("levels") else ""}
                            {"📍 <b>Court:</b> " + a["court"] + "<br>" if a.get("court") else ""}
                            <a href="{a['link']}"
                            target="_blank"
                            style="color:#4FC3F7;font-weight:bold">
                            🔗 Open booking
                            </a>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
