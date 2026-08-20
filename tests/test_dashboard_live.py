"""
tests/test_dashboard_live.py
----------------------------
Demo dashboard tanpa device / main.py.

    cd "C:\\Users\\radit\\Project\\VisualStudioProject\\Skripsi\\MAS AI"
    python tests/test_dashboard_live.py

Browser terbuka otomatis. Demo 5 skenario dummy ~30 detik lalu tunggu Ctrl+C.
"""

import sys, os, time, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from visual.monitor import BrowserDashboard

TOTAL      = 5
STEPS      = 4
TCS_IDS    = [f"FC-MN-00{i+1}" for i in range(TOTAL)]

FAKE_SCENARIOS = [
    {"tcs_id": tid, "sub_steps": [f"Step {j+1}" for j in range(STEPS)]}
    for tid in TCS_IDS
]

def run_demo(monitor: BrowserDashboard):
    time.sleep(2)  # beri waktu browser terbuka

    for idx, sc in enumerate(FAKE_SCENARIOS, start=1):
        tcs = sc["tcs_id"]
        steps = sc["sub_steps"]

        # Mulai scenario
        monitor.push_progress(idx, TOTAL, 0, len(steps), tcs, "Running")
        time.sleep(0.5)

        # Simulasi tiap step
        for si in range(1, len(steps) + 1):
            monitor.push_progress(idx, TOTAL, si, len(steps), tcs, "Running")
            time.sleep(0.6)

        # Selesai — skenario ke-3 sengaja anomali
        status = "FUNCTIONAL_ANOMALY" if idx == 3 else "PASSED"
        monitor.push_progress(idx, TOTAL, len(steps), len(steps), tcs, status)
        time.sleep(2)

    # Semua selesai
    monitor.push_progress(TOTAL, TOTAL, STEPS, STEPS, TCS_IDS[-1], "PASSED")
    monitor.push_log("RUNNER", "Semua skenario selesai", "")
    print("[test] Demo selesai. Ctrl+C untuk keluar.")

if __name__ == "__main__":
    print("[test] Memulai dashboard demo...")
    monitor = BrowserDashboard(device_id="demo", device_w=1080, device_h=2400)
    ok = monitor.start()
    if not ok:
        print("[test] Gagal start — pastikan: pip install websockets")
        sys.exit(1)

    t = threading.Thread(target=run_demo, args=(monitor,), daemon=True)
    t.start()

    try:
        t.join()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[test] Stopping...")
        monitor.stop()
