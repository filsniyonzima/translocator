"""
Shows an estimated location on Google Maps, two ways:
1. open_in_browser() -- instant, no API key, no account needed.
2. save_static_map() -- saves an actual PNG map image with a marker,
   requires a free Google Cloud API key (Maps Static API enabled).
   Great for embedding in a report or presentation slide.
"""
import webbrowser

try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False


def locate_via_ip():
    """
    FREE position lookup -- no API key, no billing, no account needed.
    Uses ip-api.com, a free IP-based geolocation service.

    Honest trade-off: accuracy is city-level (hundreds of meters to a few
    km), since it's based on your internet connection's registered location,
    not real Wi-Fi/GPS positioning. Good enough as a free starting point;
    a real GPS module will give building-level accuracy later.
    """
    if not REQUESTS_OK:
        print("[geomap] 'requests' not installed -- run: pip install requests")
        return None
    try:
        response = requests.get("http://ip-api.com/json/", timeout=8)
        response.raise_for_status()
        data = response.json()
        if data.get("status") != "success":
            print(f"[geomap] IP geolocation returned: {data}")
            return None
        return data["lat"], data["lon"]
    except Exception as e:
        print(f"[geomap] IP geolocation failed: {e}")
        return None


def locate_via_wifi(networks, api_key):
    """
    Estimates YOUR current position using nearby Wi-Fi access points --
    the same technique Google/your phone use for location without GPS.
    Sends BSSIDs (MAC addresses) + signal strengths to Google's Geolocation
    API, which matches them against its crowd-sourced AP location database.

    networks: list of dicts from wifi_scanner.scan_wifi(), each with
              'bssid' and 'strength' keys.
    api_key: a Google Cloud API key with the 'Geolocation API' enabled.

    Returns (lat, lon, accuracy_meters) or None if it fails.
    """
    if not REQUESTS_OK:
        print("[geomap] 'requests' not installed -- run: pip install requests")
        return None
    if not networks:
        print("[geomap] No Wi-Fi networks to use for positioning.")
        return None

    url = f"https://www.googleapis.com/geolocation/v1/geolocate?key={api_key}"
    payload = {
        "considerIp": False,
        "wifiAccessPoints": [
            {"macAddress": n["bssid"], "signalStrength": n["strength"]}
            for n in networks if n.get("bssid")
        ],
    }
    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()
        lat = data["location"]["lat"]
        lon = data["location"]["lng"]
        accuracy = data.get("accuracy")
        return lat, lon, accuracy
    except Exception as e:
        print(f"[geomap] Wi-Fi geolocation failed: {e}")
        return None


def embed_url(lat, lon, zoom=17):
    """
    Builds a URL that can be loaded into an embedded browser view (e.g.
    PyQt's QWebEngineView) to show a map centered on (lat, lon), with no
    API key needed. Note: this uses Google's widely-used '?output=embed'
    pattern, which is unofficial (not a documented, guaranteed API) --
    it works today but Google could change it. The officially supported
    equivalent is the Maps Embed API, which requires its own API key.
    """
    return f"https://www.google.com/maps?q={lat},{lon}&z={zoom}&output=embed"


def open_in_browser(lat, lon, label="Estimated source"):
    """Opens the default browser straight to the coordinate, pinned, no API key needed."""
    url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
    print(f"Opening in browser: {url}")
    webbrowser.open(url)
    return url


def save_static_map(lat, lon, api_key, filename="estimated_location_map.png",
                     zoom=18, size="640x480"):
    """
    Saves a static map image with a red marker at (lat, lon).
    Requires: pip install requests, and a Google Cloud API key with the
    'Maps Static API' enabled (console.cloud.google.com).
    """
    if not REQUESTS_OK:
        print("[geomap] 'requests' not installed -- run: pip install requests")
        return None

    base_url = "https://maps.googleapis.com/maps/api/staticmap"
    params = {
        "center": f"{lat},{lon}",
        "zoom": zoom,
        "size": size,
        "maptype": "roadmap",
        "markers": f"color:red|label:S|{lat},{lon}",
        "key": api_key,
    }
    try:
        response = requests.get(base_url, params=params, timeout=15)
        response.raise_for_status()
        with open(filename, "wb") as f:
            f.write(response.content)
        print(f"Map image saved: {filename}")
        return filename
    except Exception as e:
        print(f"[geomap] Failed to fetch static map: {e}")
        return None


if __name__ == "__main__":
    # quick manual test with a sample coordinate
    test_lat, test_lon = -1.9441, 30.0619  # example: Kigali, Rwanda
    open_in_browser(test_lat, test_lon)
