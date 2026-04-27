import requests
import sys
import os

# Add current directory to path so we can import shared.config
sys.path.append(os.getcwd())

try:
    from shared import config
except ImportError:
    print("[-] Error: Could not import shared.config. Make sure you are running this from the project root.")
    sys.exit(1)

def check_figma_connection():
    """Checks if the FIGMA_ACCESS_TOKEN in .env is valid."""
    print("[*] Checking Figma Connection...")
    
    token = config.FIGMA_ACCESS_TOKEN
    if not token or token == "your_figma_access_token_here":
        print("[-] Error: FIGMA_ACCESS_TOKEN is missing or not set in .env")
        return False

    headers = {"X-FIGMA-TOKEN": token}
    url = f"{config.FIGMA_API_BASE}/me"

    print(f"[*] Accessing: {url}")
    try:
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            user_data = response.json()
            print("[+] Connection Successful!")
            print(f"    - User: {user_data.get('handle', 'Unknown')}")
            print(f"    - Email: {user_data.get('email', 'Unknown')}")
            print(f"    - ID: {user_data.get('id', 'Unknown')}")
            return True
        elif response.status_code == 403:
            print("[-] Connection Failed: 403 Forbidden. Your token might be expired or invalid.")
        elif response.status_code == 401:
            print("[-] Connection Failed: 401 Unauthorized. Invalid token.")
        else:
            print(f"[-] Connection Failed: Received status code {response.status_code}")
            print(f"    Response: {response.text}")
            
    except Exception as e:
        print(f"[-] Error during connection check: {e}")
    
    return False

if __name__ == "__main__":
    success = check_figma_connection()
    if not success:
        sys.exit(1)
    sys.exit(0)
