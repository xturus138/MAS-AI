"""
tests/test_dashboard_live.py
Jalankan: python tests/test_dashboard_live.py
Demo dashboard tanpa device dan tanpa main.py.
"""
import sys, time, threading
sys.path.insert(0, ".")

from visual.monitor import TkDashboard

TOTAL = 69

def _demo(mon: TkDashboard):
    time.sleep(1.5)   # tunggu window ready
    agents = [
        ("OBSERVER",     "detect_visual_elements"),
        ("DECIDER",      "select target widget"),
        ("EXECUTOR",     "tap 540 1200"),
        ("REFLECTOR",    "verdict PASSED"),
        ("ORCHESTRATOR", "next step"),
    ]
    for sc in range(1, TOTAL + 1):
        mon.push_progress(sc - 1, TOTAL, tcs_id=f"FC-MN-{sc:03d}", status="RUNNING")
        for comp, msg in agents:
            mon.push_log(comp, msg)
            time.sleep(0.25)
        mon.push_progress(sc, TOTAL, tcs_id=f"FC-MN-{sc:03d}",
                          status="PASSED" if sc % 5 != 0 else "FUNCTIONAL_ANOMALY")
        time.sleep(0.4)

    print("[test] Demo selesai. Tutup window untuk keluar.")

def main():
    print("[test] Memulai dashboard demo...")
    mon = TkDashboard(device_id="")   # kosong = tidak ada ADB, hanya UI
    ok = mon.start()
    if not ok:
        print("[test] Dashboard disabled (LIVE_DASHBOARD_ENABLED=false)")
        return
    t = threading.Thread(target=_demo, args=(mon,), daemon=True)
    t.start()
    # Biarkan tkinter mainloop jalan di thread utama (sudah daemon)
    # Tunggu sampai window ditutup user
    t.join(timeout=TOTAL * 2)

if __name__ == "__main__":
    main()
