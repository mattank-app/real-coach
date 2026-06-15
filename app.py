import os
import datetime
import time
import requests
from requests.auth import HTTPBasicAuth
import streamlit as st
from google import genai
from google.genai import types

# 1. Page Config & Interface Setup
st.set_page_config(page_title="Trail Endurance Coach", page_icon="🏔️", layout="centered")

# ==========================================
# NEW: SECURITY LOCK SCREEN
# ==========================================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔒 Restricted Access")
    st.markdown("This is a private athletic coaching environment.")
    pwd_attempt = st.text_input("Enter Passcode", type="password")
    
    if st.button("Unlock"):
        # The script looks for the label "APP_PASSWORD" in your cloud vault
        if pwd_attempt == st.secrets["APP_PASSWORD"]:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Access Denied.")
            
    st.stop() # This entirely stops the rest of the app from loading
    # ==========================================
st.title("🏔️ Trail Endurance Coach")
st.subheader("Your Training Analytics Engine")

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
    st.toast(f"📡 Coach is pulling your wellness data for the last {days} days...", icon="❤️")
    
    # 1. Calculate exact date range...
    now = datetime.datetime.now()
    oldest_date = (now - datetime.timedelta(days=days)).strftime('%Y-%m-%d')
    newest_date = now.strftime('%Y-%m-%d')
    
    # 2. Attach the date parameters to the URL
    url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/wellness?oldest={oldest_date}&newest={newest_date}"
    
    try:
        response = requests.get(url, auth=HTTPBasicAuth('API_KEY', api_key))
        if response.status_code == 200:
            # The API now only returns the exact days we asked for
            recent_days = response.json() 
            
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
        else:
            print(f"CRITICAL API ERROR: {response.status_code} - {response.text}")
            return {"status": "error", "message": f"Wellness API failed: {response.status_code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ==========================================
# TOOL 2: TRAINING ACTIVITIES PERFORMANCE AUDIT
# ==========================================
def get_weekly_activities(days: int = 7) -> dict:
    """Fetches raw activity logs and processes required pace, duration, VAM, and 80/20 intensity fields."""
    st.toast(f"📡 Coach is pulling your activity logs for the last {days} days...", icon="🏃")
    
    # 1. Calculate the date range FIRST...
    now = datetime.datetime.now()
    cutoff_date = (now - datetime.timedelta(days=days)).strftime('%Y-%m-%d')
    newest_date = now.strftime('%Y-%m-%d')
    
    # 2. Attach the mandatory date parameters directly to the URL
    url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/activities?oldest={cutoff_date}&newest={newest_date}"
    
    try:
        response = requests.get(url, auth=HTTPBasicAuth('API_KEY', api_key))
        if response.status_code == 200:
            raw_activities = response.json()
            
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
                
                # FIX 1: Extract HR zones directly from the API's array list
                hr_zones = act.get("icu_hr_zone_times", [])
                z1 = hr_zones[0] if len(hr_zones) > 0 else 0
                z2 = hr_zones[1] if len(hr_zones) > 1 else 0
                
                low_intensity_pct = 0.0
                if moving_sec > 0:
                    low_intensity_pct = round(((z1 + z2) / moving_sec) * 100, 1)
                
                vam_m_per_hour = 0
                if moving_sec > 0 and elev_gain > 0:
                    vam_m_per_hour = round((elev_gain / moving_sec) * 3600)

                # FIX 2: Check for multiple types of decoupling (Power or Pace)
                cardiac_drift = act.get("icu_pm_ftp_decoupling") or act.get("icu_hr_pw_decoupling") or act.get("decoupling") or 0
                
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
                    "cardiac_drift_decoupling_pct": cardiac_drift
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

# Cached function to initialize client
@st.cache_resource
def get_genai_client():
    return genai.Client()

client = get_genai_client()

# Cached function to load the PDF (Only runs once!)
@st.cache_resource
def load_knowledge_base():
    """Uploads the document and waits for Google to finish processing it."""
    file_name = "Knowledge feed trail running.pdf" 
    if os.path.exists(file_name):
        uploaded_file = client.files.upload(file=file_name)
        
        # NEW: Force the app to wait until the AI has actually read the PDF
        while uploaded_file.state == "PROCESSING":
            time.sleep(2)
            uploaded_file = client.files.get(name=uploaded_file.name)
            
        return uploaded_file
    return None

# 👇 ADD THIS EXACT LINE HERE 👇
knowledge_document = load_knowledge_base()

# Initialize the session ONLY if it doesn't exist
if "chat_session" not in st.session_state:
   # 1. Define the core persona text
    system_text = (
        "Purpose & Persona:\n"
        "You are an elite ultra-trail running and mountain endurance coach. Your role is to act as a sounding board, "
        "an analytical engine, and an unyielding accountability partner. Your athlete is a busy corporate communications "
        "manager balancing a demanding executive career with rigorous alpine training.\n\n"
        "Core Methodology Workflow:\n"
        "1. The Holy Trinity Analysis: Always state and interpret current Fitness (CTL), Fatigue (ATL), and Form (TSB).\n"
        "2. 80/20 Rule Check: Ensure easy and long runs are strictly in Zone 1/Zone 2.\n"
        "3. Aerobic Decoupling: Analyze long weekend efforts to check for cardiac drift.\n"
        "4. Muscular Endurance (ME): Verify execution of sport-specific strength progressions.\n\n"
        "Weekly Feedback Structure:\n"
        "If you successfully retrieved the athlete's data, you MUST strictly format your entire response using the following four headings:\n"
        "## ## The Numbers\n"
        "## ## The Bright Spots\n"
        "## ## The Brutal Truth\n"
        "## ## The Next Move\n\n"
        "CRITICAL ESCAPE HATCH:\n"
        "If you call your tools and they return an error, OR if no data is found, YOU MUST IGNORE the four headings above. "
        "Instead, immediately output a plain text response telling the athlete exactly what the error message was or that their log is empty."
    )

    # 2. Pack the text AND the PDF together into the System Instructions
    system_parts = [system_text]
    if knowledge_document:
        system_parts.append(types.Part.from_uri(file_uri=knowledge_document.uri, mime_type=knowledge_document.mime_type))
        system_parts.append("CRITICAL: Read the attached manual. Use its frameworks to judge the athlete's data.")

    # 3. Create the session cleanly without faking the chat history
    st.session_state.chat_session = client.chats.create(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(
            tools=[get_daily_wellness, get_weekly_activities],
            temperature=0.2,
            system_instruction=system_parts,
            safety_settings=[
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_ONLY_HIGH"),
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_ONLY_HIGH")
            ]
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
        with st.spinner("Analyzing performance logs against the manual..."):
            response = st.session_state.chat_session.send_message(user_input)
            
            if response.text:
                st.markdown(response.text)
                st.session_state.messages.append({"role": "assistant", "content": response.text})
            else:
                # NEW: Check if the AI generated a hidden tool command instead of text
                if response.function_calls:
                    tool_name = response.function_calls[0].name
                    error_msg = f"⚠️ The AI tried to trigger Intervals.icu ({tool_name}), but the automatic loop stalled."
                else:
                    finish_reason = response.candidates[0].finish_reason if response.candidates else "Unknown"
                    error_msg = f"⚠️ The AI generated a blank response. Finish Reason: {finish_reason}"
                
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
