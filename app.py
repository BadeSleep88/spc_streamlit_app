import json
import subprocess
import streamlit as st

# --------------------
# Page config
# --------------------
st.set_page_config(
    page_title="Stratford Padel Match Finder",
    page_icon="🎾",
    layout="centered",
)

st.title("🎾 Stratford Padel Match Finder")
st.caption("Private tool · Configurable · CLI-backed")

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

st.markdown("### Weekdays")


def weekday_block(label, default_start, default_end):
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


weekday_cfg = {
    "monday": weekday_block("Monday", 19, 23),
    "tuesday": weekday_block("Tuesday", 18, 23),
    "wednesday": weekday_block("Wednesday", 19, 23),
    "thursday": weekday_block("Thursday", 19, 23),
    "friday": weekday_block("Friday", 18, 23),
}

st.markdown("### Weekend (always enabled)")

weekend_start, weekend_end = st.slider(
    "Weekend time window",
    min_value=0,
    max_value=23,
    value=(9, 22),
)

weekend_cfg = {
    "start_hour": weekend_start,
    "end_hour": weekend_end,
}

st.divider()

# --------------------
# Run
# --------------------
st.subheader("🚀 Run search")

if st.button("Run scraper", type="primary"):
    with st.spinner("Searching for matches..."):
        cmd = [
            "python",
            "scraper.py",
            "run",
            "--level-min",
            str(level_min),
            "--level-max",
            str(level_max),
            "--weeks",
            str(weeks),
            "--weekdays",
            json.dumps(weekday_cfg),
            "--weekend-times",
            json.dumps(weekend_cfg),
            "--verbose",
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )

    st.success("Search complete")

    if result.stdout:
        st.text_area(
            "Output",
            value=result.stdout,
            height=350,
        )

    if result.stderr:
        st.error(result.stderr)
