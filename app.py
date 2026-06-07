import os
import datetime
import requests
from requests.auth import HTTPBasicAuth
import streamlit as st
from google import genai
from google.genai import types

# 1. Page Config & Interface Setup
st.set_page_config(page_title="Alpine Endurance Coach", page_icon="🏔️", layout="centered")
st.title("🏔️ Elite Mountain Endurance Coach")
st.subheader("Uphill Athlete Analytics Engine")

# 2. Secure Access to Environment Secrets
try:
    os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]
    athlete_id = st.secrets["INTERVALS_ATHLETE_ID"]
    api_key = st.secrets["INTERVALS_API_KEY"]
except KeyError:
    st.error("Configuration Error: Missing credentials in Streamlit Secrets.")
    st.stop()

# ==========================================
# TOOL 1: PHYSIOLOGICAL WELLNESS METRICS
# ==========================================
def get_daily_wellness(days: int = 7) -> dict:
    """Fetches biological wellness markers (CTL, ATL, TSB, HRV) from Intervals.icu."""
    url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/wellness"
    try:
        response = requests.get(url, auth=HTTPBasicAuth('API_KEY', api_key))
        if response.status_code == 200:
            recent_days = response.json()[-days:]
            wellness_log = []
            for d in recent_days:
                ctl = d.get("ctl", 0) or 0
                atl = d.get("atl", 0) or 0
                calculated_tsb = ctl - atl if (ctl or atl) else (d.get("form", 0) or 0)
                wellness_log.append({
                    "date": d.get("id"),
                    "fitness_ctl": ctl,
                    "fatigue_atl": atl,
                    "form_tsb": calculated_tsb,
                    "hrv_rmssd": d.get("hrv"),
                    "resting_hr": d.get("restingHr")
                })
            return {"status": "success", "wellness_history": wellness_log}
        return {"status": "error", "message": f"Wellness API failed: {response.status_code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ==========================================
# TOOL 2: TRAINING ACTIVITIES PERFORMANCE AUDIT
# ==========================================
def get_weekly_activities(days: int = 7) -> dict:
    """Fetches raw activity logs and processes required pace, duration, VAM, and 80/20 intensity fields."""
    url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/activities"
    try:
        response = requests.get(url, auth=HTTPBasicAuth('API_KEY', api_key))
        if response.status_code == 200:
            now = datetime.datetime.now()
            cutoff_date = (now - datetime.timedelta(days=days)).strftime('%Y-%m-%d')
            raw_activities = [a for a in response.json() if a.get("start_date_local", "") >= cutoff_date]
            
            processed_activities = []
            for act in raw_activities:
                moving_sec = act.get("moving_time", 0) or 0
                elev_gain = act.get("total_elevation_gain", 0) or 0
                avg_speed = act.get("average_speed", 0) or 0
                
                dist_km = round(act.get("distance", 0) / 1000, 2) if act.get("distance") else 0
                duration_hms = str(datetime.timedelta(seconds=moving_sec)) if moving_sec else "00:00:00"
                
                pace_str = "0:00"
                if avg_speed > 0:
                    pace_decimal = 16.6667 / avg_speed
                    p_min = int(pace_decimal)
                    p_sec = int((pace_decimal - p_min) * 60)
                    pace_str = f"{p_min}:{p_sec:02d}"
                
                low_intensity_pct = 0.0
                if moving_sec > 0:
                    z1 = act.get("hr_z1_secs", 0) or 0
                    z2 = act.get("hr_z2_secs", 0) or 0
                    low_intensity_pct = round(((z1 + z2) / moving_sec) * 100, 1)
                
                vam_m_per_hour = 0
                if moving_sec > 0 and elev_gain > 0:
                    vam_m_per_hour = round((elev_gain / moving_sec) * 3600)
                
                processed_activities.append({
                    "date": act.get("start_date_local", "")[:10],
                    "name": act.get("name"),
                    "type": act.get("type"),
                    "distance_km": dist_km,
                    "duration": duration_hms,
                    "pace_min_km": pace_str,
                    "training_load_tss": act.get("icu_training_load"),
                    "low_intensity_percentage": low_intensity_pct,
                    "climbing_vam_m_hr": vam_m_per_hour,
                    "efficiency_factor": act.get("icu_efficiency"),
                    "cardiac_drift_decoupling_pct": act.get("icu_pm_ftp_decoupling")
                })
            return {"status": "success", "processed_completed_workouts": processed_activities}
        return {"status": "error", "message": f"Activities API failed: {response.status_code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ==========================================
# 3. CHAT ENGINE & PERSISTENT SESSION STATE
# ==========================================
if "messages" not in st.session_state:
    st.session_state.messages = []

if "chat_session" not in st.session_state:
    client = genai.Client()
    system_prompt = (
        "Purpose & Persona:\n"
        "You are an elite ultra-trail running and mountain endurance coach. Your role is to act as a sounding board, "
        "an analytical engine, and an unyielding accountability partner. Your athlete is a busy corporate communications "
        "manager balancing a demanding executive career with rigorous alpine training.\n\n"
        "You must analyze weekly workout data, track physiological adaptation, and ensure strict adherence to the "
        "'Training for the Uphill Athlete' methodology. Speak with a frank, highly analytical, completely no-nonsense tone. "
        "Do not sugarcoat missed workouts or poor discipline. Speak like a top-tier coach who respects the brutal difficulty "
        "of the mountains and demands consistency, but always anchor your toughness in deep motivation that inspires the athlete to stay disciplined.\n\n"
        "Core Methodology Workflow:\n"
        "1. The Holy Trinity Analysis: Always state and interpret current Fitness (CTL), Fatigue (ATL), and Form (TSB). "
        "Identify whether the athlete is in the Optimal Training zone (TSB -10 to -30), Overload (below -30), or Fresh/Injury Risk. "
        "Track HRV (rMSSD) trends according to Marco Altini's principles to evaluate autonomic nervous system recovery.\n"
        "2. 80/20 Rule Check: Ensure easy and long runs are strictly in Zone 1/Zone 2. Actively audit for 'gray zone' running "
        "(Zone 3 creeping into aerobic days). If low-intensity time drops below 80% for the week or during designated long runs, flag this as a critical failure.\n"
        "3. Aerobic Decoupling: Analyze long weekend efforts to check for cardiac drift, ensuring the cardiovascular engine is stabilizing.\n"
        "4. Muscular Endurance (ME): Verify execution of sport-specific strength progressions. Heavily penalize skipped ME sessions.\n\n"
        "Weekly Feedback Structure:\n"
        "You must strictly format your entire response using the following four headings:\n"
        "## ## The Numbers\n"
        "## ## The Bright Spots\n"
        "## ## The Brutal Truth\n"
        "## ## The Next Move\n\n"
        "Hard Guardrails & Constraints:\n"
        "- DO NOT ask the athlete to 'make up' or double-down on lost workouts from a previous week. Move forward.\n"
        "- DO NOT instruct or encourage the athlete to push through acute physical injuries, deep joint pain, or illness."
    )
    st.session_state.chat_session = client.chats.create(
        model="gemini-3.5-flash",
        config=types.GenerateContentConfig(
            tools=[get_daily_wellness, get_weekly_activities],
            temperature=0.2,
            system_instruction=system_prompt
        )
    )

# Render chat interface history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 4. Interactive Live Conversation Execution
if user_input := st.chat_input("Message your coach..."):
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)
        
    with st.chat_message("assistant"):
        with st.spinner("Analyzing performance logs..."):
            response = st.session_state.chat_session.send_message(user_input)
            st.markdown(response.text)
    st.session_state.messages.append({"role": "assistant", "content": response.text})
