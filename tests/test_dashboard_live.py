"""
tests/test_dashboard_live.py
----------------------------
Demo interaktif: jalankan dashboard tanpa main.py / device nyata.

    cd "C:\\Users\\radit\\Project\\VisualStudioProject\\Skripsi\\MAS AI"
    python tests/test_dashboard_live.py

Buka browser ke http://localhost:8001 saat muncul pesan "Opened".
Script akan kirim event simulasi selama 30 detik lalu berhenti.

Tidak butuh ADB / device (video panel kosong, tapi feed + progress bar hidup).
"""

import sys, os, time, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from visual.monitor import BrowserDashboard

# ── Config ────────────────────────────────────────────────────────────
TOTAL_SCENARIOS = 5
STEPS_PER_SCENARIO = 4
DELAY_SCENARIO = 3.0   # detik antar scenario
DELAY_STEP    = 0.7    # detik antar step dalam scenario

FAKE_SCENARIOS = [
    {"tcs_id": f"FC-MN-00{i+1}", "title": f"Dummy Scenario {i+1}",
     "sub_steps": [f"Step {j+1}" for j in range(STEPS_PER_SCENARIO)]}
    for i in range(TOTAL_SCENARIOS)
]

FAKE_WIDGETS = [
    {"label": "Send Button", "bounds": [820, 2100, 1040, 2200], "actionable": True},
    {"label": "Message Input", "bounds": [60, 2080, 810, 2210], "actionable": True},
    {"label": "Chat Header",  "bounds": [0, 0, 1080, 160],     "actionable": False},
    {"label": "Back Arrow",   "bounds": [20, 60, 100, 140],    "actionable": True},
]

FAKE_TARGET = {"label": "Send Button", "bounds": [820, 2100, 1040, 2200], "action": "click"}

# ── Main demo ─────────────────────────────────────────────────────────
def run_demo(monitor: BrowserDashboard):
    time.sleep(2)  # beri waktu browser buka

    for s_idx, scenario in enumerate(FAKE_SCENARIOS, start=1):
        tcs_id = scenario["tcs_id"]
        steps  = scenario["sub_steps"]

        monitor.push_progress(s_idx, TOTAL_SCENARIOS, 0, len(steps), tcs_id, "Running")
        monitor.push_log("RUNNER", f"[{s_idx}/{TOTAL_SCENARIOS}] {tcs_id}", "Starting scenario")
        time.sleep(0.4)

        for step_idx, step in enumerate(steps, start=1):
            # Observer
            monitor.on_observer(FAKE_WIDGETS)
            monitor.push_log("OBSERVER", f"{len(FAKE_WIDGETS)} widgets detected", step)
            time.sleep(DELAY_STEP * 0.4)

            # Decider
            monitor.on_decider(FAKE_TARGET)
            monitor.push_log("DECIDER", f"Target: {FAKE_TARGET['label']} → {FAKE_TARGET['action']}", "")
            time.sleep(DELAY_STEP * 0.3)

            # Executor
            cx = (FAKE_TARGET["bounds"][0] + FAKE_TARGET["bounds"][2]) // 2
            cy = (FAKE_TARGET["bounds"][1] + FAKE_TARGET["bounds"][3]) // 2
            monitor.on_executor(cx, cy, "click")
            monitor.push_log("EXECUTOR", f"click @ ({cx}, {cy})", "")
            time.sleep(DELAY_STEP * 0.3)

            # Clear + progress
            monitor.on_clear()
            monitor.push_progress(s_idx, TOTAL_SCENARIOS, step_idx, len(steps), tcs_id, "Running")

        # Scenario done
        status = "PASSED" if s_idx % 3 != 0 else "FUNCTIONAL_ANOMALY"
        monitor.push_progress(s_idx, TOTAL_SCENARIOS, len(steps), len(steps), tcs_id, status)
        monitor.push_log("REFLECTOR", f"{tcs_id} → {status}", "")
        time.sleep(DELAY_SCENARIO)

    monitor.push_log("RUNNER", "All scenarios complete", f"{TOTAL_SCENARIOS} done")
    print("\n[test] Demo selesai. Tutup browser atau Ctrl+C untuk keluar.")


if __name__ == "__main__":
    print("[test] Starting BrowserDashboard demo...")
    monitor = BrowserDashboard(device_id="demo-no-device", device_w=1080, device_h=2400)
    ok = monitor.start()
    if not ok:
        print("[test] WARNING: WS server gagal start. Cek apakah 'websockets' terinstall:")
        print("       pip install websockets")

    demo_thread = threading.Thread(target=run_demo, args=(monitor,), daemon=True)
    demo_thread.start()

    try:
        demo_thread.join()
        # Biarkan server tetap hidup supaya user bisa lihat hasil akhir
        print("[test] Server masih hidup. Tekan Ctrl+C untuk stop.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[test] Stopping...")
        monitor.stop()
