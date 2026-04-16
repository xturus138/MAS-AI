import uiautomator2 as u2
import cv2
import os
import sys

sys.path.append(os.getcwd())
try:
    from shared import config
    device_id = config.TARGET_DEVICE
except:
    device_id = "T8SGEE5TF695ZPV4"

def check_res():
    print(f"[*] Testing connection to {device_id}...")
    try:
        d = u2.connect(device_id)
        if not d.active:
            print("[-] Device not active/online")
            return
            
        print(f"[+] Device Info: {d.info}")
        print(f"[+] Window Size: {d.window_size()}")
        
        # Take a test screenshot
        test_path = "test_res.png"
        print("[*] Taking test screenshot...")
        d.screenshot(test_path)
        img = cv2.imread(test_path)
        if img is not None:
            h, w = img.shape[:2]
            print(f"[+] Screenshot Resolution: {w}x{h}")
            
            dw = d.info.get('displayWidth')
            dh = d.info.get('displayHeight')
            print(f"[+] Display Size Info: {dw}x{dh}")
            
            if w != dw or h != dh:
                print("[!] MISMATCH DETECTED!")
                print(f"    Scale Factor X: {dw/w:.4f}")
                print(f"    Scale Factor Y: {dh/h:.4f}")
            else:
                print("[+] Resolution matches perfectly.")
                
            os.remove(test_path)
        else:
            print("[-] Failed to read screenshot")
    except Exception as e:
        print(f"[-] Error: {e}")

if __name__ == "__main__":
    check_res()
