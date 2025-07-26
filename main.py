import streamlit as st
import pandas as pd
from streamlit_folium import st_folium
import struct # This is the key library for decoding binary data
import colorsys
from folium import Map, CircleMarker, LayerControl, PolyLine
import time
import hashlib

MINIMUM_ACCURACY = 5000
VOLTAGE_SKEW = 0.00143678161

# typedef struct {
#     uint32_t iTOW;   // GPS time of week [ms]
#     int32_t lon;     // Longitude [1e-7 deg]
#     int32_t lat;     // Latitude [1e-7 deg]
#     uint32_t hAcc;   // Horizontal accuracy [mm]
# } UBX_NAV_POSLLH_t;

# --- 1. MOCK DATA & DECODING ---
#This is the arrangement I am least certain about prior to being given example data will return to this once Joel sends me things

def get_file_hash(file):
    file.seek(0)
    content = file.read()
    file.seek(0)
    return hashlib.md5(content).hexdigest(), content

def encode_to_hex(time_of_week, longitude, latitude, h_acc, battery_v):
    """
    Convert values to a packed hex string.
    - time_of_week: uint32 (e.g., GPS time in seconds)
    - longitude: int32 (e.g., in 1e-7 degrees)
    - latitude: int32 (e.g., in 1e-7 degrees)
    - h_acc: uint32 (horizontal accuracy in mm or similar)
    - battery_v: uint16 (battery in volts)
    """
    packed = struct.pack(">IiiIH", time_of_week, longitude, latitude, h_acc, battery_v)
    return packed.hex().upper()

# --- DECODE ---
def decode_from_hex(hex_string):
    """
    Decode a hex string back into values.
    """
    byte_data = bytes.fromhex(hex_string)
    unpacked = struct.unpack(">IiiIH", byte_data)
    return {
        "time_of_week": str(gps_time_of_week_ms_to_local(unpacked[0])),
        "longitude": unpacked[1],
        "latitude": unpacked[2],
        "horizontal_accuracy": unpacked[3],
        "battery_v": unpacked[4]
    }

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# --- Constants You Need ---
# The GPS clock started at midnight, Jan 6, 1980.
GPS_EPOCH = datetime(1980, 1, 6, tzinfo=timezone.utc) 

# GPS time does not have leap seconds, so it's ahead of UTC.
# As of 2024, the difference is 18 seconds.
LEAP_SECONDS = 18 

# Number of seconds in one week.
SECONDS_IN_WEEK = 7 * 24 * 3600

TIMEZONE_NAME = "America/Vancouver"

def gps_time_of_week_ms_to_local(itow_ms: int) -> datetime:
    # Get current GPS week number
    now_utc = datetime.now(timezone.utc)
    now_gps = now_utc + timedelta(seconds=LEAP_SECONDS)
    current_gps_week = int((now_gps - GPS_EPOCH).total_seconds() // SECONDS_IN_WEEK)
    
    # Calculate absolute GPS time
    total_seconds = current_gps_week * SECONDS_IN_WEEK + itow_ms / 1000.0
    absolute_gps_time = GPS_EPOCH + timedelta(seconds=total_seconds)
    
    # Convert GPS time to UTC
    utc_time = absolute_gps_time - timedelta(seconds=LEAP_SECONDS)
    
    # Make UTC aware, then convert to local timezone
    utc_time = utc_time.replace(tzinfo=timezone.utc)
    local_time = utc_time.astimezone(ZoneInfo(TIMEZONE_NAME))
    
    return local_time


def utc_to_gps_time_of_week(dt: datetime) -> int:
    """
    Convert a UTC datetime to GPS time-of-week in milliseconds.
    """
    delta = dt - GPS_EPOCH
    total_seconds = int(delta.total_seconds())
    gps_week_start = total_seconds - (total_seconds % (7 * 24 * 3600))
    tow_seconds = total_seconds - gps_week_start
    return tow_seconds * 1000  # to milliseconds


def highlight_bad_accuracy(row):
    if row["Horizontal Accuracy (mm)"] > MINIMUM_ACCURACY:
        return ["color: #a00; text-decoration: line-through"] * len(row)
        # return ["background-color: #fdd; color: #a00; text-decoration: line-through"] * len(row)
    else:
        return [""] * len(row)

#Page Layout
st.set_page_config(layout="wide")

testing_data = ['04F2DC68B6D39ED51D5211DA000021AB0FFF','050B61C0B6D3A2991D52165100001F370FFF']

st.title("Data Collection")
st.markdown("This portion of the app visualized the process by which data is collected from the pcb and sent off to the argos servers for processing by reaserchers.")

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
                "Battery (V)": decoded["battery_v"] * VOLTAGE_SKEW,
                "Raw Hex": user_input_hex
            }

            st.session_state.user_input_hex_list.append(formatted)

        except Exception as e:
            st.error(f"❌ Decoding failed: {str(e)}")


st.subheader("Upload CSV with Hex Strings")

uploaded_file = st.file_uploader(
    "Upload CSV file with hex strings", 
    type=["csv"], 
    accept_multiple_files=False
)

if "uploaded_files_data" not in st.session_state:
    st.session_state.uploaded_files_data = {}  # key: file_id, value: list of decoded entries

if "last_file_hash" not in st.session_state:
    st.session_state.last_file_hash = None

if uploaded_file is not None:
    filename = uploaded_file.name

    if filename not in st.session_state.uploaded_files_data:
        try:
            # Read CSV (assuming hex strings are in a column named 'hex' or similar)
            df = pd.read_csv(uploaded_file, header=None, names=["hex"])
            
            # Adjust the column name below to match your CSV
            hex_column = "hex"  # <-- change this if your column has a different name
            decoded_entries = []

            # Process each hex string row
            for hex_str in df[hex_column]:
                hex_str = str(hex_str).strip().upper()
                if len(hex_str) != 36 or any(c not in "0123456789ABCDEF" for c in hex_str):
                    st.warning(f"Skipping invalid hex string: {hex_str}")
                    continue
                try:
                    decoded = decode_from_hex(hex_str)
                    formatted = {
                        "Time of Week (s)": decoded["time_of_week"],
                        "Longitude (°)": decoded["longitude"] / 1e7,
                        "Latitude (°)": decoded["latitude"] / 1e7,
                        "Horizontal Accuracy (mm)": decoded["horizontal_accuracy"],
                        "Battery (V)": decoded["battery_v"] * VOLTAGE_SKEW,
                        "Raw Hex": hex_str
                    }
                    decoded_entries.append(formatted)
                except Exception as e:
                    st.warning(f"Failed to decode {filename}: {e}")

            st.session_state.uploaded_files_data[filename] = decoded_entries
            # st.success(f"Processed {len(df)} entries from CSV.")
        except Exception as e:
            st.error(f"Failed to read CSV file: {e}")


if st.session_state.uploaded_files_data:
    for file_name in list(st.session_state.uploaded_files_data.keys()):
        # file_name = file_id[0]
        if st.button(f"Remove {file_name}", key=f"remove_{file_name}"):
            del st.session_state.uploaded_files_data[file_name]
            st.rerun()

# Display the list
if st.session_state.user_input_hex_list:
    if st.session_state.get("user_input_hex_list"):

        if "confirm_clear" not in st.session_state:
            st.session_state.confirm_clear = False

        if not st.session_state.confirm_clear:
            if st.button("🗑️ Clear All Manual Entries"):
                st.session_state.confirm_clear = True
                st.rerun()
        else:
            col1, col2 = st.columns(2)
            if col1.button("✅ Confirm"):
                st.session_state.user_input_hex_list.clear()
                st.session_state.confirm_clear = False
                st.rerun()
            if col2.button("❌ Cancel"):
                st.session_state.confirm_clear = False
                st.rerun()

    st.subheader("Manual Entries")
    styled_df = pd.DataFrame(st.session_state.user_input_hex_list).style.apply(highlight_bad_accuracy, axis=1)
    st.dataframe(styled_df)

if st.session_state.uploaded_files_data:
    for file_name in st.session_state.uploaded_files_data:
        st.subheader(file_name)
        styled_df = pd.DataFrame(st.session_state.uploaded_files_data[file_name]).style.apply(highlight_bad_accuracy, axis=1)
        st.dataframe(styled_df)


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


# --- Map Center ---
if st.session_state.user_input_hex_list is not None or st.session_state.uploaded_files_data is not [] :
    st.session_state.uploaded_files_data["Manual Data"] = st.session_state.user_input_hex_list
    m = Map(tiles="CartoDB positron")

    lat_large = float('-inf')
    lat_small = float('inf')
    lon_large = float('-inf')
    lon_small = float('inf')



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
    for file_name in st.session_state.uploaded_files_data:
        dataset = pd.DataFrame(st.session_state.uploaded_files_data[file_name])
        show = st.checkbox(f"Show {file_name}", key=f"Show {file_name}", value=True)
        if show and not dataset.empty:
            filtered_dataset = dataset[dataset["Horizontal Accuracy (mm)"] <= MINIMUM_ACCURACY]

            colors = generate_faded_colors("#1F77B4", len(dataset))  # Blue gradient
            points = []
            for idx, row in filtered_dataset[::-1].reset_index(drop=True).iterrows():
                lat = row["Latitude (°)"]
                lon = row["Longitude (°)"]
                points.append((lat, lon))

                if lat > lat_large:
                    lat_large = lat
                if lat < lat_small:
                    lat_small = lat
                if lon > lon_large:
                    lon_large = lon
                if lon < lon_small:
                    lon_small = lon

                # --- MODIFIED POPUP ---
                popup_html = f"""
                <div style="width: 300px;">
                    <b>Decoded Entry {idx}</b><br>
                    --------------------<br>
                    <b>Time:</b> {row['Time of Week (s)']}<br>
                    <b>Latitude:</b> {lat:.7f}<br>
                    <b>Longitude:</b> {lon:.7f}<br>
                    <b>Accuracy:</b> {row['Horizontal Accuracy (mm)']} mm<br>
                    <b>Battery:</b> {row['Battery (V)']} V
                </div>
                """ # <-- CHANGED: Wrapped in a div with a width style

                map_data.append({
                    "lat": lat,
                    "lon": lon,
                    "popup": popup_html,
                    "color": colors[idx]
                })

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
            if show and dataset.shape[0] > 1:
                PolyLine(points[::-1], color="#1F77B4", weight=2, opacity=0.5).add_to(m)

    LayerControl().add_to(m)


    # Compute bounds
    bounds = [[lat_small, lon_small], [lat_large, lon_large]]

    # Fit map to bounds
    m.fit_bounds(bounds)

    del st.session_state.uploaded_files_data["Manual Data"]


    # --- CHANGED: Increased width and height for a larger map ---
    st_folium(m, width=1200, height=800)
else:
    st.info("No GPS data available yet to plot on the map.")