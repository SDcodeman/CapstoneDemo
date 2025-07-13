import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import struct # This is the key library for decoding binary data

# This is the C struct definition you provided, for reference.
# typedef struct {
#     uint32_t iTOW;   // GPS time of week [ms]
#     int32_t lon;     // Longitude [1e-7 deg]
#     int32_t lat;     // Latitude [1e-7 deg]
#     uint32_t hAcc;   // Horizontal accuracy [mm]
# } UBX_NAV_POSLLH_t;

# --- 1. MOCK DATA & DECODING ---
# This function simulates fetching data from the Argos API.
# In a real application, you would replace this with a call using the `requests` library.
def mock_fetch_argos_data():
    """
    Returns a list of fake Argos messages. Each message contains a
    platform ID and a hex-encoded payload representing your GPS data.
    """
    st.info("Using mock data. Replace `mock_fetch_argos_data` with your real API call.")
    # Payloads are 16 bytes (4 fields * 4 bytes/field), represented as 32 hex characters.
    # These are little-endian hex representations of the struct.
    mock_messages = [
        {"platformId": "12345", "timestamp": "2023-10-27T10:00:00Z", "hex_payload": "00cd9b3b821894f710a7472c00e80300"},
        {"platformId": "12345", "timestamp": "2023-10-27T10:05:00Z", "hex_payload": "c0e0b33b851b94f71fa8472c001a0400"},
        {"platformId": "12345", "timestamp": "2023-10-27T10:10:00Z", "hex_payload": "80f4cb3b7d1e94f72ec9472c004c0400"},
        {"platformId": "12345", "timestamp": "2023-10-27T10:15:00Z", "hex_payload": "4008e43b6a2194f73ddb472c007e0400"},
        {"platformId": "12345", "timestamp": "2023-10-27T10:20:00Z", "hex_payload": "001ceb3b4f2494f74ceb472c00a00400"},
        # This payload is intentionally malformed (too short) to show error handling
        {"platformId": "12345", "timestamp": "2023-10-27T10:25:00Z", "hex_payload": "aabbccdd"}
    ]
    return mock_messages

def decode_payload(hex_payload: str):
    """
    Decodes a hex string payload into GPS data based on the UBX_NAV_POSLLH_t struct.
    """
    try:
        # The payload should be 16 bytes (32 hex characters).
        if len(hex_payload) != 32:
            raise ValueError("Payload length is not 32 hex characters.")

        payload_bytes = bytes.fromhex(hex_payload)

        # The format string '<IiiI' tells `struct.unpack` how to interpret the bytes:
        # < : Little-endian byte order (most common)
        # I : Unsigned 32-bit integer (for iTOW)
        # i : Signed 32-bit integer (for lon)
        # i : Signed 32-bit integer (for lat)
        # I : Unsigned 32-bit integer (for hAcc)
        iTOW, lon_raw, lat_raw, hAcc_raw = struct.unpack('<IiiI', payload_bytes)

        # Scale the raw integer values to their final floating-point form
        latitude = lat_raw / 1e7
        longitude = lon_raw / 1e7
        accuracy_mm = hAcc_raw

        return {
            "iTOW_ms": iTOW,
            "latitude": latitude,
            "longitude": longitude,
            "hAcc_mm": accuracy_mm,
        }
    except (ValueError, struct.error) as e:
        # Return None if the payload is malformed or can't be decoded
        st.warning(f"Could not decode payload '{hex_payload}': {e}")
        return None

# --- 2. STREAMLIT APP LAYOUT ---

st.set_page_config(layout="wide")
st.title("Argos GPS Data Visualizer")
st.markdown("This app fetches data from the Argos network, decodes the custom GPS payload, and displays it on a map.")

# Fetch and process data
with st.spinner("Fetching and decoding Argos data..."):
    messages = mock_fetch_argos_data()
    decoded_data = []
    for msg in messages:
        decoded_point = decode_payload(msg["hex_payload"])
        if decoded_point:
            # Combine Argos metadata with decoded payload data
            full_record = {
                "platformId": msg["platformId"],
                "timestamp": msg["timestamp"],
                **decoded_point # Unpacks the dictionary
            }
            decoded_data.append(full_record)

# Create a Pandas DataFrame for easy manipulation and display
if not decoded_data:
    st.error("No valid data could be decoded. Cannot display table or map.")
else:
    df = pd.DataFrame(decoded_data)

    # Display the decoded data in a table
    st.header("Decoded GPS Data")
    st.dataframe(df)

    # Create and display the map
    st.header("GPS Track Map")
    
    # Center the map on the average location of the points
    map_center = [df['latitude'].mean(), df['longitude'].mean()]
    m = folium.Map(location=map_center, zoom_start=10)

    # Add points (the track) to the map
    points = df[['latitude', 'longitude']].values.tolist()
    folium.PolyLine(points, color="blue", weight=2.5, opacity=1).add_to(m)

    # Add a marker for each point with a helpful popup
    for idx, row in df.iterrows():
        popup_html = f"""
        <b>Timestamp:</b> {row['timestamp']}<br>
        <b>Lat:</b> {row['latitude']:.6f}<br>
        <b>Lon:</b> {row['longitude']:.6f}<br>
        <b>Accuracy:</b> {row['hAcc_mm']} mm
        """
        folium.Marker(
            location=[row['latitude'], row['longitude']],
            popup=folium.Popup(popup_html, max_width=200),
            icon=folium.Icon(color="blue", icon="circle")
        ).add_to(m)

    # Display the map in the Streamlit app
    st_folium(m, width="100%", height=500)