"""
Real Wi-Fi scanner using pywifi (cross-platform: Windows now, Linux later if we move).
Forces an ACTIVE scan (not a stale OS cache, which was the earlier netsh problem),
then returns the strongest networks found, sorted by signal.

Install first:  pip install pywifi comtypes
"""
import time

try:
    import pywifi
    from pywifi import const
    PYWIFI_OK = True
except ImportError:
    PYWIFI_OK = False


def _security_label(akm_list):
    names = []
    for akm in akm_list:
        if akm == const.AKM_TYPE_NONE:
            return "Open (unsecured)"
        elif akm in (const.AKM_TYPE_WPA, const.AKM_TYPE_WPAPSK):
            names.append("WPA")
        elif akm in (const.AKM_TYPE_WPA2, const.AKM_TYPE_WPA2PSK):
            names.append("WPA2")
        else:
            names.append("WPA3/Other")
    return "/".join(sorted(set(names))) if names else "Unknown"


def scan_wifi(top_n=6, wait_seconds=2.5):
    """Returns up to top_n dicts: label, freq, freq_num, strength, security, ssid"""
    if not PYWIFI_OK:
        print("[wifi_scanner] pywifi not installed -- run: pip install pywifi comtypes")
        return []

    try:
        wifi = pywifi.PyWiFi()
        iface = wifi.interfaces()[0]
        iface.scan()  # force an ACTIVE scan, not a stale cached one
        time.sleep(wait_seconds)  # give the adapter time to complete the scan
        results = iface.scan_results()
    except Exception as e:
        print(f"[wifi_scanner] scan failed: {e}")
        return []

    seen_bssids = set()
    parsed = []
    for r in results:
        if r.bssid in seen_bssids:
            continue  # same AP reported twice
        seen_bssids.add(r.bssid)

        freq_mhz = round(r.freq / 1000) if getattr(r, "freq", 0) else 0
        band_label = "5 GHz Wi-Fi" if freq_mhz >= 3000 else "2.4 GHz Wi-Fi" if freq_mhz else "Wi-Fi"
        ssid = r.ssid if r.ssid else "(hidden network)"

        parsed.append({
            "label": f'{band_label} -- "{ssid}"',
            "freq": f"{freq_mhz} MHz" if freq_mhz else "Unknown",
            "freq_num": freq_mhz,
            "strength": r.signal,  # already in dBm
            "security": _security_label(r.akm),
            "ssid": ssid,
            "bssid": r.bssid,  # MAC address, needed for Wi-Fi-based geolocation
        })

    parsed.sort(key=lambda d: d["strength"], reverse=True)
    return parsed[:top_n]


if __name__ == "__main__":
    # quick manual test: run this file directly to see the strongest nearby networks
    for net in scan_wifi():
        print(net)
