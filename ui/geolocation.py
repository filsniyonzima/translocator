"""
RSSI-based geolocation core.
Converts signal strength (dBm) to an estimated distance, then combines
3+ (position, distance) readings to estimate the transmitter's location
via linear-algebra trilateration (no scipy needed, just numpy).

This same module will later take GPS coordinates instead of manually-entered
local coordinates, and radio RSSI instead of Wi-Fi RSSI -- the math doesn't change.
"""
import math
import numpy as np


def rssi_to_distance(rssi_dbm, rssi_ref_at_1m=-40, path_loss_exponent=2.7):
    """
    Log-distance path loss model: converts a signal strength reading into
    an estimated distance in meters.

    rssi_ref_at_1m: the signal strength you'd measure exactly 1 meter from
        the source. -40 dBm is a common default for Wi-Fi; you can calibrate
        this by standing exactly 1m from your router and reading its RSSI.
    path_loss_exponent: how fast signal fades with distance.
        ~2.0 = free space/outdoors, ~2.7-3.5 = indoors with walls/furniture.
    """
    return 10 ** ((rssi_ref_at_1m - rssi_dbm) / (10 * path_loss_exponent))


def trilaterate(points):
    """
    points: list of (x, y, distance) tuples, at least 3 required.
    Returns (x_est, y_est) -- the estimated transmitter location.

    Uses the standard linearized trilateration method: subtract the last
    point's circle equation from every other point's circle equation to
    cancel the squared terms, producing a linear system solved by least
    squares (robust even with imperfect/noisy distance estimates).
    """
    if len(points) < 3:
        raise ValueError("Need at least 3 points to trilaterate.")

    xN, yN, dN = points[-1]
    A = []
    b = []
    for (xi, yi, di) in points[:-1]:
        A.append([2 * (xN - xi), 2 * (yN - yi)])
        b.append((di**2 - dN**2) + (xN**2 - xi**2) + (yN**2 - yi**2))

    A = np.array(A)
    b = np.array(b)
    solution, *_ = np.linalg.lstsq(A, b, rcond=None)
    return float(solution[0]), float(solution[1])


def local_to_latlon(origin_lat, origin_lon, x, y):
    """
    Converts a local (x, y) offset in meters -- measured from an origin point --
    into real latitude/longitude. Uses a flat-earth approximation, which is
    accurate to within centimeters at room/building scale (this breaks down
    over many kilometers, but is perfect for our use case).

    x = east-west offset in meters (positive = east)
    y = north-south offset in meters (positive = north)
    """
    meters_per_degree_lat = 111320.0
    meters_per_degree_lon = 111320.0 * math.cos(math.radians(origin_lat))

    lat = origin_lat + (y / meters_per_degree_lat)
    lon = origin_lon + (x / meters_per_degree_lon)
    return lat, lon


if __name__ == "__main__":
    # Quick self-test with made-up numbers: a transmitter actually at (5, 5)
    test_points = [
        (0, 0, 7.07),
        (10, 0, 7.07),
        (0, 10, 7.07),
    ]
    est = trilaterate(test_points)
    print(f"Test trilateration result: {est} (should be close to (5.0, 5.0))")
