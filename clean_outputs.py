import os
import shutil

def clean_outputs():
    output_dir = "outputs"
    
    if not os.path.exists(output_dir):
        print(f"[*] Directory '{output_dir}' does not exist. Nothing to clean.")
        return

    print(f"[*] Cleaning contents of '{output_dir}' subdirectories...")
    
    for item in os.listdir(output_dir):
        item_path = os.path.join(output_dir, item)
        if os.path.isdir(item_path):
            print(f"  - Cleaning subfolder: {item}")
            for filename in os.listdir(item_path):
                file_path = os.path.join(item_path, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    print(f"    [!] Failed to delete {file_path}. Reason: {e}")
        else:
            try:
                os.unlink(item_path)
                print(f"  - Deleted file: {item}")
            except Exception as e:
                print(f"    [!] Failed to delete {item_path}. Reason: {e}")

    print("[*] Done! All outputs subdirectories are now empty.")

if __name__ == "__main__":
    clean_outputs()
