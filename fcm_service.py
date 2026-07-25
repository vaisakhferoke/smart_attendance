import os, sys, glob
from datetime import datetime
from db_config import get_db_connection

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))

FIREBASE_INITIALIZED = False
FIREBASE_MODULE_AVAILABLE = False

try:
    import firebase_admin
    from firebase_admin import credentials, messaging
    FIREBASE_MODULE_AVAILABLE = True
except ImportError:
    FIREBASE_MODULE_AVAILABLE = False
    print("[FCM Notice]: 'firebase-admin' Python module not installed. Run 'pip install firebase-admin' to enable live Firebase push notifications.")

def find_service_account_file():
    """Locate the Firebase Admin SDK JSON credentials file"""
    target_filename = "smartattendance-47469-firebase-adminsdk-fbsvc-80e4f47be9.json"
    
    # 1. Check exact target file path in project root
    exact_path = os.path.join(PROJECT_ROOT, target_filename)
    if os.path.exists(exact_path):
        return exact_path

    # 2. Check inside subdirectories (web, api, doc)
    for sub in ['', 'web', 'api', 'doc']:
        p = os.path.join(PROJECT_ROOT, sub, target_filename)
        if os.path.exists(p):
            return p

    # 3. Fallback: Search for any *firebase-adminsdk*.json file
    pattern = os.path.join(PROJECT_ROOT, "**", "*firebase-adminsdk*.json")
    matches = glob.glob(pattern, recursive=True)
    if matches:
        return matches[0]

    return exact_path

def init_firebase():
    """Initializes Firebase Admin SDK using the service account JSON key"""
    global FIREBASE_INITIALIZED

    if not FIREBASE_MODULE_AVAILABLE:
        return False

    if FIREBASE_INITIALIZED or (hasattr(firebase_admin, '_apps') and firebase_admin._apps):
        FIREBASE_INITIALIZED = True
        return True

    cred_file = find_service_account_file()

    if not os.path.exists(cred_file):
        print(f"[FCM Warning]: Service account JSON key '{os.path.basename(cred_file)}' not found in workspace.")
        return False

    try:
        cred = credentials.Certificate(cred_file)
        firebase_admin.initialize_app(cred)
        FIREBASE_INITIALIZED = True
        print(f"[Firebase SDK Initialized] Successfully loaded '{os.path.basename(cred_file)}'")
        return True
    except Exception as e:
        print(f"[Firebase SDK Init Error]: {e}")
        return False

# Attempt auto-init on module import
init_firebase()

def send_attendance_notification(emp_code, full_name, in_time, department_name="General", branch_name="Main HQ", fcm_token=None):
    """
    Sends Firebase Cloud Messaging (FCM) Push Notification to an employee
    upon successful attendance check-in.
    """
    conn = None
    try:
        # Fetch FCM token from DB if not passed
        if not fcm_token:
            conn = get_db_connection()
            if conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT fcm_token FROM employees WHERE emp_code = %s OR full_name = %s LIMIT 1", (emp_code, full_name))
                row = cursor.fetchone()
                if row and row.get('fcm_token'):
                    fcm_token = row['fcm_token']

        if not fcm_token:
            print(f"[FCM Notice]: No FCM token registered for employee '{full_name}' ({emp_code}). Push notification skipped.")
            return False, "No FCM Token registered for employee."

        if not FIREBASE_INITIALIZED:
            if not init_firebase():
                print(f"[FCM Notification Pending]: Firebase SDK not ready. FCM Token present for {full_name}, but SDK uninitialized.")
                return False, "Firebase Admin SDK not initialized."

        # Format push notification message
        title = "Attendance Checked-In!"
        body = f"Hello {full_name}, your attendance check-in was successfully recorded at {in_time}."

        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body
            ),
            data={
                "click_action": "FLUTTER_NOTIFICATION_CLICK",
                "type": "attendance_checkin",
                "emp_code": str(emp_code or ""),
                "full_name": str(full_name or ""),
                "in_time": str(in_time or ""),
                "department": str(department_name or "General"),
                "branch": str(branch_name or "Main HQ"),
                "timestamp": datetime.now().isoformat()
            },
            token=fcm_token
        )

        response_id = messaging.send(message)
        print(f"[FCM SUCCESS]: Sent Push Notification to {full_name} ({emp_code})! Message ID: {response_id}")
        return True, response_id

    except Exception as err:
        print(f"[FCM Send Error]: Failed sending push notification to {full_name}: {err}")
        return False, str(err)
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    print("Testing FCM Service initialization...")
    print("Firebase Available:", FIREBASE_MODULE_AVAILABLE)
    print("Firebase Initialized:", FIREBASE_INITIALIZED)
    print("Service Account File Path:", find_service_account_file())
