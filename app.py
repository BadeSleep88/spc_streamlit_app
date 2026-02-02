import hashlib
from datetime import datetime, timedelta
from urllib.parse import quote

import streamlit as st

from activities_scraper import StratfordPadelActivityScraper
from fetch_matches import StratfordPadelMatchFetcher, UpcomingItem
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
    /* Tabs scrollable horizontally on small screens */
    div[data-baseweb="tab-list"] {
        overflow-x: auto;
        display: flex;
    }
    div[data-baseweb="tab-list"] button {
        flex-shrink: 0;  /* prevent buttons from shrinking */
        font-size: 16px;
        padding: 8px 16px;
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
tab_games, tab_activities, tab_calendar = st.tabs(["🎾 Find Games", "🏃 Find Activities", "📅 Calendar Sync"])


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

    weeks = st.slider("Weeks to search ahead", 1, 5, 5, key="g_weeks")

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
        scraper.config["match_search"]["search_settings"]["level_range"]["min"] = level_min
        scraper.config["match_search"]["search_settings"]["level_range"]["max"] = level_max
        scraper.config["match_search"]["search_settings"]["weeks_to_search"] = weeks
        scraper.config["time_filters"]["weekdays"] = weekdays
        scraper.config["time_filters"]["weekends"] = weekends

        return scraper.search_matches()

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
                style="color:#1E90FF"
                target="_blank">🔗 Open booking</a>
                </div>
                """,
                    unsafe_allow_html=True,
                )


# =====================================================
# 🏃 FIND ACTIVITIES TAB
# =====================================================
with tab_activities:
    st.subheader("Find Activities")

    days_ahead = st.slider("Days to search ahead", 1, 42, 7, key="a_days_ahead")

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
                        <b>{a['type']}{f" (Level {a['levels']})" if a.get("levels") else ""}</b><br>
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

# =====================================================
# 🏃 CALENDAR SYNC TAB
# =====================================================
with tab_calendar:
    st.subheader("📅 Sync Upcoming Matches & Activities")
    st.caption("Import SPC events into your Calendar")

    col1, col2 = st.columns(2)
    with col1:
        email = st.text_input("Email")
    with col2:
        password = st.text_input("Password", type="password")

    # -------------------------------
    # Helpers
    # -------------------------------
    def generate_uid(item):
        raw = f"{item.match_id}|{item.date}|{item.time_start}"
        return hashlib.sha1(raw.encode()).hexdigest()

    def build_vevent(item: UpcomingItem):
        start = datetime.strptime(f"{item.date} {item.time_start}", "%d/%m/%Y %H:%M")
        end = datetime.strptime(f"{item.date} {item.time_end}", "%d/%m/%Y %H:%M")

        uid = generate_uid(item)

        return f"""BEGIN:VEVENT
UID:{uid}
DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}
DTSTART:{start.strftime('%Y%m%dT%H%M%S')}
DTEND:{end.strftime('%Y%m%dT%H%M%S')}
SUMMARY:🎾 Padel – {item.court}
DESCRIPTION:{item.description}\\n{item.url}
URL:{item.url}
BEGIN:VALARM
TRIGGER:-PT30M
ACTION:DISPLAY
DESCRIPTION:Padel in 30 minutes
END:VALARM
END:VEVENT
"""

    def build_calendar(events: list[str]):
        body = "\n".join(events)
        return f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//SPC Finder//EN
CALSCALE:GREGORIAN
{body}
END:VCALENDAR
"""

    # -------------------------------
    # Fetch button
    # -------------------------------
    fetch_clicked = st.button("📡 Fetch upcoming items", type="primary")

    if fetch_clicked:
        if not email or not password:
            st.warning("Please enter email and password")
        else:
            with st.spinner("Logging in and fetching events..."):
                client = StratfordPadelMatchFetcher(
                    username=email,
                    password=password,
                    verbose=False,
                )

                authenticated = client.is_authenticated
                items = client.get_upcoming_items() if authenticated else []

            # spinner ALWAYS ends before we reach here ✅

            if not authenticated:
                st.error("❌ Login failed. Please check credentials.")
            elif not items:
                st.info("No upcoming items found.")
            else:
                st.session_state["calendar_items"] = items
                st.session_state["calendar_selection"] = {generate_uid(i): True for i in items}

    # -------------------------------
    # Render items + selection
    # -------------------------------
    items = st.session_state.get("calendar_items", [])

    if items:
        st.success(f"Found {len(items)} upcoming events")

        st.markdown("### Select events to add")
        for item in items:
            uid = generate_uid(item)

            st.session_state["calendar_selection"][uid] = st.checkbox(
                f"🎾 {item.court} · {item.date} · {item.time_start}–{item.time_end}",
                value=st.session_state["calendar_selection"].get(uid, True),
                key=f"chk_{uid}",
            )

        # -------------------------------
        # Add to calendar (single button)
        # -------------------------------
        st.divider()
        right = st.columns([3, 1])[1]

        with right:
            if st.button("➕ Add selected to calendar", type="primary"):
                selected_events = []

                for item in items:
                    uid = generate_uid(item)
                    if st.session_state["calendar_selection"].get(uid):
                        selected_events.append(build_vevent(item))

                if not selected_events:
                    st.warning("No events selected.")
                else:
                    calendar_ics = build_calendar(selected_events)

                    st.download_button(
                        label="📥 Download calendar file",
                        data=calendar_ics,
                        file_name="spc_matches.ics",
                        mime="text/calendar",
                    )

                    st.info(
                        "On iOS this opens Calendar directly. " "On Android, open the file once to import."
                    )
