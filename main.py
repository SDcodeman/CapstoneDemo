import streamlit as st
import pandas as pd
from streamlit_folium import st_folium
import struct # This is the key library for decoding binary data
import colorsys
from folium import Map, CircleMarker, LayerControl, PolyLine

# typedef struct {
#     uint32_t iTOW;   // GPS time of week [ms]
#     int32_t lon;     // Longitude [1e-7 deg]
#     int32_t lat;     // Latitude [1e-7 deg]
#     uint32_t hAcc;   // Horizontal accuracy [mm]
# } UBX_NAV_POSLLH_t;

# --- 1. MOCK DATA & DECODING ---
#This is the arrangement I am least certain about prior to being given example data will return to this once Joel sends me things

def encode_to_hex(time_of_week, longitude, latitude, h_acc, battery_mv):
    """
    Convert values to a packed hex string.
    - time_of_week: uint32 (e.g., GPS time in seconds)
    - longitude: int32 (e.g., in 1e-7 degrees)
    - latitude: int32 (e.g., in 1e-7 degrees)
    - h_acc: uint32 (horizontal accuracy in mm or similar)
    - battery_mv: uint16 (battery in millivolts)
    """
    packed = struct.pack(">IiiIH", time_of_week, longitude, latitude, h_acc, battery_mv)
    return packed.hex().upper()

# --- DECODE ---
def decode_from_hex(hex_string):
    """
    Decode a hex string back into values.
    """
    byte_data = bytes.fromhex(hex_string)
    unpacked = struct.unpack(">IiiIH", byte_data)
    return {
        "time_of_week": str(gps_time_of_week_ms_to_utc(unpacked[0])),
        "longitude": unpacked[1],
        "latitude": unpacked[2],
        "horizontal_accuracy": unpacked[3],
        "battery_mv": unpacked[4]
    }

from datetime import datetime, timedelta, timezone

# --- Constants You Need ---
# The GPS clock started at midnight, Jan 6, 1980.
GPS_EPOCH = datetime(1980, 1, 6, tzinfo=timezone.utc) 

# GPS time does not have leap seconds, so it's ahead of UTC.
# As of 2024, the difference is 18 seconds.
LEAP_SECONDS = 18 

# Number of seconds in one week.
SECONDS_IN_WEEK = 7 * 24 * 3600

def gps_time_of_week_ms_to_utc(itow_ms: int) -> datetime:
    """
    Converts GPS Time of Week (iTOW) in milliseconds to a UTC datetime object,
    assuming the time is in the current GPS week.
    """
    # 1. Find the current GPS week number.
    #    - Get the current time in UTC.
    #    - Convert it to GPS time by adding the leap seconds.
    #    - Calculate how many seconds have passed since the GPS epoch.
    #    - Divide by seconds_in_a_week to get the current week number.
    now_utc = datetime.now(timezone.utc)
    now_gps = now_utc + timedelta(seconds=LEAP_SECONDS)
    seconds_since_epoch = (now_gps - GPS_EPOCH).total_seconds()
    current_gps_week = int(seconds_since_epoch // SECONDS_IN_WEEK)

    # 2. Calculate the total seconds from the GPS epoch to your data point.
    #    This is the number of full weeks plus the time into the current week.
    total_seconds_in_gps_time = (current_gps_week * SECONDS_IN_WEEK) + (itow_ms / 1000.0)

    # 3. Convert these total seconds into an absolute GPS datetime.
    absolute_gps_time = GPS_EPOCH + timedelta(seconds=total_seconds_in_gps_time)

    # 4. Convert the absolute GPS time to UTC by subtracting the leap seconds.
    utc_time = absolute_gps_time - timedelta(seconds=LEAP_SECONDS)
    
    return utc_time


def utc_to_gps_time_of_week(dt: datetime) -> int:
    """
    Convert a UTC datetime to GPS time-of-week in milliseconds.
    """
    delta = dt - GPS_EPOCH
    total_seconds = int(delta.total_seconds())
    gps_week_start = total_seconds - (total_seconds % (7 * 24 * 3600))
    tow_seconds = total_seconds - gps_week_start
    return tow_seconds * 1000  # to milliseconds

#Page Layout
st.set_page_config(layout="wide")

testing_data = ['04F2DC68B6D39ED51D5211DA000021AB0FFF','050B61C0B6D3A2991D52165100001F370FFF']

st.title("Data Collection")
st.markdown("This portion of the app visualized the process by which data is collected from the pcb and sent off to the argos servers for processing by reaserchers.")

st.subheader("Testing Data Table")
st.dataframe(testing_data)

#Decode and create DataFrame
values = []
for i in testing_data:
    values.append(decode_from_hex(i))

testing_results = pd.DataFrame(values)
st.subheader("Decoded Data Table")
st.dataframe(testing_results)

st.subheader("Enter a Hex String to Decode")

# Initialize session state
if "user_input_hex_list" not in st.session_state:
    st.session_state.user_input_hex_list = []

with st.form("hex_input_form", clear_on_submit=True):
    user_input_hex = st.text_input("Hex string (36 characters):")
    submitted = st.form_submit_button("Decode Hex")

if submitted:
    user_input_hex = user_input_hex.strip().upper()

    if len(user_input_hex) < 36:
        st.error("❌ Input must be exactly 36 hexadecimal characters (18 bytes). Please enter " + str(36 - len(user_input_hex)) + " more.")
    elif len(user_input_hex) > 36: 
        st.error("❌ Input must be exactly 36 hexadecimal characters (18 bytes). Please enter " + str(len(user_input_hex) - 36) + " less.")
    elif not all(c in "0123456789ABCDEF" for c in user_input_hex):
        st.error("❌ Input contains invalid characters. Only 0-9 and A-F are allowed.")
    else:
        try:
            decoded = decode_from_hex(user_input_hex)

            formatted = {
                "Time of Week (s)": decoded["time_of_week"],
                "Longitude (°)": decoded["longitude"] / 1e7,
                "Latitude (°)": decoded["latitude"] / 1e7,
                "Horizontal Accuracy (mm)": decoded["horizontal_accuracy"],
                "Battery (mV)": decoded["battery_mv"],
                "Raw Hex": user_input_hex
            }

            st.session_state.user_input_hex_list.append(formatted)

        except Exception as e:
            st.error(f"❌ Decoding failed: {str(e)}")

# Display the list
if st.session_state.user_input_hex_list:
    st.subheader("All Decoded Entries")
    st.dataframe(pd.DataFrame(st.session_state.user_input_hex_list))





# --- ENCODE SECTION ---
st.subheader("Enter Individual Values to Encode into Hex")

# Initialize persistent storage for encoded entries
if "user_encoded_data" not in st.session_state:
    st.session_state.user_encoded_data = []

# Input fields
col1, col2 = st.columns(2)
with col1:
    date = st.date_input("Select UTC Date", value=datetime.utcnow().date())
    time = st.time_input("Select UTC Time", value=datetime.utcnow().time())

    # Combine into a single datetime object
    time_of_week = datetime.combine(date, time).replace(tzinfo=timezone.utc)
    battery_mv = st.number_input("Battery Voltage (mV)", min_value=0, max_value=65535, step=1)

with col2:
    latitude = st.number_input("Latitude (°)", format="%.7f")
    longitude = st.number_input("Longitude (°)", format="%.7f")
    h_acc = st.number_input("Horizontal Accuracy (mm)", min_value=0, step=1)


# Submit button
if st.button("Encode to Hex"):
    try:
        # Convert to required internal formats
        lon_raw = int(longitude * 1e7)
        lat_raw = int(latitude * 1e7)

        # Encode using your function
        encoded_hex = encode_to_hex(utc_to_gps_time_of_week(time_of_week), lon_raw, lat_raw, int(h_acc), int(battery_mv))

        entry = {
            "Time of Week (s)": time_of_week,
            "Longitude (°)": longitude,
            "Latitude (°)": latitude,
            "Horizontal Accuracy (mm)": int(h_acc),
            "Battery (mV)": int(battery_mv),
            "Encoded Hex": encoded_hex
        }

        st.session_state.user_encoded_data.append(entry)
        st.success("✅ Successfully encoded!")

    except Exception as e:
        st.error(f"❌ Encoding failed: {str(e)}")

# Show the encoded results
if st.session_state.user_encoded_data:
    st.subheader("All Encoded Entries")
    st.dataframe(pd.DataFrame(st.session_state.user_encoded_data))







#Map Part!!!

st.subheader("📍 Visualize All Coordinates on Map")

# --- Function to create fading color gradients ---
def generate_faded_colors(base_hex, n):
    """Generate n shades of a color from vibrant to pale."""
    base_hex = base_hex.lstrip('#')
    r, g, b = [int(base_hex[i:i+2], 16) for i in (0, 2, 4)]
    hsv = colorsys.rgb_to_hsv(r/255, g/255, b/255)
    colors = []
    for i in range(n):
        value = 0.4 + 0.6 * (1 - i / max(n - 1, 1))  # fade down
        r_f, g_f, b_f = colorsys.hsv_to_rgb(hsv[0], hsv[1], value)
        color = '#{:02X}{:02X}{:02X}'.format(int(r_f * 255), int(g_f * 255), int(b_f * 255))
        colors.append(color)
    return colors

# --- Collect valid points ---
map_data = []

if not st.session_state.get("user_input_hex_list"):
    st.session_state.user_input_hex_list = []

if not st.session_state.get("user_encoded_data"):
    st.session_state.user_encoded_data = []

# Base map initialization after checking data
m = None

# Dataset 1: Static decoded testing data
dataset1 = pd.DataFrame(values) if values else pd.DataFrame()
show1 = st.checkbox("Show Decoded Testing Data", value=True)
if show1 and not dataset1.empty:
    colors1 = generate_faded_colors("#FF5733", len(dataset1))  # Red gradient
    points1 = []
    for idx, row in dataset1[::-1].reset_index(drop=True).iterrows():
        lat = row["latitude"] / 1e7
        lon = row["longitude"] / 1e7
        points1.append((lat, lon))

        # --- MODIFIED POPUP ---
        popup_html = f"""
        <b>Testing Data Point {idx}</b><br>
        --------------------<br>
        <b>Time:</b> {row['time_of_week']}<br>
        <b>Latitude:</b> {lat:.7f}<br>
        <b>Longitude:</b> {lon:.7f}<br>
        <b>Accuracy:</b> {row['horizontal_accuracy']} mm<br>
        <b>Battery:</b> {row['battery_mv']} mV
        """

        map_data.append({
            "lat": lat,
            "lon": lon,
            "popup": popup_html, # <-- CHANGED
            "color": colors1[idx]
        })

# Dataset 2: User-decoded hex inputs
dataset2 = pd.DataFrame(st.session_state.user_input_hex_list)
show2 = st.checkbox("Show User-Decoded Data", value=True)
if show2 and not dataset2.empty:
    colors2 = generate_faded_colors("#1F77B4", len(dataset2))  # Blue gradient
    points2 = []
    for idx, row in dataset2[::-1].reset_index(drop=True).iterrows():
        lat = row["Latitude (°)"]
        lon = row["Longitude (°)"]
        points2.append((lat, lon))

        # --- MODIFIED POPUP ---
        popup_html = f"""
        <b>Decoded Entry {idx}</b><br>
        --------------------<br>
        <b>Time:</b> {row['Time of Week (s)']}<br>
        <b>Latitude:</b> {lat:.7f}<br>
        <b>Longitude:</b> {lon:.7f}<br>
        <b>Accuracy:</b> {row['Horizontal Accuracy (mm)']} mm<br>
        <b>Battery:</b> {row['Battery (mV)']} mV
        """

        map_data.append({
            "lat": lat,
            "lon": lon,
            "popup": popup_html, # <-- CHANGED
            "color": colors2[idx]
        })

# Dataset 3: User-encoded inputs
dataset3 = pd.DataFrame(st.session_state.user_encoded_data)
show3 = st.checkbox("Show Encoded Data", value=True)
if show3 and not dataset3.empty:
    colors3 = generate_faded_colors("#2ECC71", len(dataset3))  # Green gradient
    points3 = []
    for idx, row in dataset3[::-1].reset_index(drop=True).iterrows():
        lat = row["Latitude (°)"]
        lon = row["Longitude (°)"]
        points3.append((lat, lon))
        
        # --- MODIFIED POPUP ---
        popup_html = f"""
        <b>Encoded Entry {idx}</b><br>
        --------------------<br>
        <b>Time:</b> {row['Time of Week (s)']}<br>
        <b>Latitude:</b> {lat:.7f}<br>
        <b>Longitude:</b> {lon:.7f}<br>
        <b>Accuracy:</b> {row['Horizontal Accuracy (mm)']} mm<br>
        <b>Battery:</b> {row['Battery (mV)']} mV
        """

        map_data.append({
            "lat": lat,
            "lon": lon,
            "popup": popup_html, # <-- CHANGED
            "color": colors3[idx]
        })

# --- Map Center ---
if map_data:
    avg_lat = sum([pt["lat"] for pt in map_data]) / len(map_data)
    avg_lon = sum([pt["lon"] for pt in map_data]) / len(map_data)
    m = Map(location=[avg_lat, avg_lon], zoom_start=5, tiles="CartoDB positron")

    # Add all point markers
    for pt in map_data:
        CircleMarker(
            location=[pt["lat"], pt["lon"]],
            radius=6,
            color=pt["color"],
            fill=True,
            fill_opacity=0.8,
            popup=pt["popup"]
        ).add_to(m)

    # Add polylines per dataset if applicable
    if show1 and dataset1.shape[0] > 1:
        PolyLine(points1[::-1], color="#FF5733", weight=2, opacity=0.5).add_to(m)

    if show2 and dataset2.shape[0] > 1:
        PolyLine(points2[::-1], color="#1F77B4", weight=2, opacity=0.5).add_to(m)

    if show3 and dataset3.shape[0] > 1:
        PolyLine(points3[::-1], color="#2ECC71", weight=2, opacity=0.5).add_to(m)

    LayerControl().add_to(m)
    st_folium(m, width=800, height=600)
else:
    st.info("No GPS data available yet to plot on the map.")