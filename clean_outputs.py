import os
import shutil

def clean_outputs():
    output_dir = "outputs"
    
    if not os.path.exists(output_dir):
        print(f"[*] Directory '{output_dir}' does not exist.")
        return

    print(f"[*] Wiping all contents from '{output_dir}'...")
    
    # for item in os.listdir(output_dir):
    #     item_path = os.path.join(output_dir, item)
    #     try:
    #         if os.path.isfile(item_path) or os.path.islink(item_path):
    #             os.unlink(item_path)
    #         elif os.path.isdir(item_path):
    #             shutil.rmtree(item_path)
    #         print(f"  - Removed: {item}")
    #     except Exception as e:
    #         print(f"    [!] Failed to delete {item_path}. Reason: {e}")
    print("  - [SAFE MODE] Deletion skipped to preserve step outputs.")

    # print("[*] Done! Outputs directory is now empty.")

if __name__ == "__main__":
    clean_outputs()
