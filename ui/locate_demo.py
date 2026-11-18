"""
EMSO -- Live Wi-Fi geolocation demo.
Proves the RSSI-based localization concept with REAL signal strength from
your own router, using manually-entered local coordinates (meters) since
we don't have GPS hardware yet. Same math will apply to radio signals
and real GPS once that hardware arrives.

Run from the ui/ folder:  python locate_demo.py
"""
from wifi_scanner import scan_wifi
from geolocation import rssi_to_distance, trilaterate, local_to_latlon
from geomap import open_in_browser, save_static_map

print("=" * 60)
print("EMSO -- Live Wi-Fi Source Geolocation Demo")
print("=" * 60)
print("\nPick a fixed origin point in your room (e.g. a corner) as (0, 0).")
print("You'll walk to at least 3 different spots, enter your position in")
print("meters from that origin, and we'll scan your real Wi-Fi signal")
print("strength at each spot.\n")

target_ssid = input("Enter the exact SSID (network name) you want to locate: ").strip()

print("\nCalibration: we need to know the signal strength at exactly 1 meter")
print("from the access point. You can measure this live right now, or type")
print("a value manually (remember: Wi-Fi RSSI is always NEGATIVE, e.g. -40).")
calib_choice = input("Type 'measure' to measure it live now, or press Enter to type a value: ").strip()

if calib_choice.lower() == "measure":
    input("Stand exactly 1 meter from the access point, then press Enter...")
    print("  Scanning...")
    cal_networks = scan_wifi(top_n=20, wait_seconds=2.5)
    cal_match = next((net for net in cal_networks if net["ssid"] == target_ssid), None)
    if cal_match:
        rssi_ref = cal_match["strength"]
        print(f"  Measured reference at 1m: {rssi_ref} dBm")
    else:
        print(f"  '{target_ssid}' not found -- falling back to default -40 dBm.")
        rssi_ref = -40.0
else:
    raw = input("Signal strength at 1m from the router in dBm [default -40]: ").strip()
    rssi_ref = float(raw) if raw else -40.0
    if rssi_ref > 0:
        print(f"  WARNING: {rssi_ref} dBm is positive -- Wi-Fi RSSI is always negative.")
        fix = input(f"  Did you mean -{rssi_ref}? [Y/n]: ").strip().lower()
        if fix != "n":
            rssi_ref = -rssi_ref
            print(f"  Using {rssi_ref} dBm.")

n_exp = input("Path loss exponent (2.0=open space, 2.7=typical indoors) [default 2.7]: ").strip()
n_exp = float(n_exp) if n_exp else 2.7

points = []
reading_num = 1

while True:
    print(f"\n--- Reading {reading_num} ---")
    if len(points) >= 3:
        cmd = input("Move to a new spot and press Enter to scan, or type 'done' to estimate: ").strip()
        if cmd.lower() == "done":
            break
    else:
        input(f"Move to spot {reading_num} and press Enter when ready to scan...")

    x = float(input("  Your X position (meters): "))
    y = float(input("  Your Y position (meters): "))

    print("  Scanning (this takes a few seconds)...")
    networks = scan_wifi(top_n=20, wait_seconds=2.5)
    match = next((net for net in networks if net["ssid"] == target_ssid), None)

    if not match:
        print(f"  '{target_ssid}' not found in this scan. Try again at this spot.")
        continue

    rssi = match["strength"]
    distance = rssi_to_distance(rssi, rssi_ref_at_1m=rssi_ref, path_loss_exponent=n_exp)
    print(f"  Found it: {rssi} dBm -> estimated distance {distance:.2f} m")

    points.append((x, y, distance))
    reading_num += 1

if len(points) < 3:
    print("\nNeed at least 3 readings to estimate a location. Exiting.")
else:
    est_x, est_y = trilaterate(points)
    print("\n" + "=" * 60)
    print(f"ESTIMATED ROUTER LOCATION: x = {est_x:.2f} m, y = {est_y:.2f} m")
    print("=" * 60)
    print("\nNow measure the router's REAL position (meters from your origin)")
    print("and compare -- that difference is your system's accuracy.")

    show_map = input("\nShow this location on Google Maps? [Y/n]: ").strip().lower()
    if show_map != "n":
        print("\nWe need ONE real GPS point to anchor your local (x,y) grid to the")
        print("real world: the GPS coordinates of your origin (0,0) spot.")
        print("Get this from your phone's GPS/Google Maps 'My Location' right now,")
        print("standing at your origin point.")
        origin_lat = float(input("  Origin latitude (e.g. -1.9441): "))
        origin_lon = float(input("  Origin longitude (e.g. 30.0619): "))

        est_lat, est_lon = local_to_latlon(origin_lat, origin_lon, est_x, est_y)
        print(f"\nEstimated real-world coordinates: {est_lat:.6f}, {est_lon:.6f}")

        open_in_browser(est_lat, est_lon, label=target_ssid)

        want_image = input("\nAlso save a map image with a marker? Needs a Google Maps API key [y/N]: ").strip().lower()
        if want_image == "y":
            api_key = input("  Paste your Google Maps Static API key: ").strip()
            save_static_map(est_lat, est_lon, api_key)
