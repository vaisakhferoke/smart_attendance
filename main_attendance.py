import sys, io, time
# Fix Windows console encoding for Unicode/emoji print statements
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import cv2
import json
import numpy as np
from datetime import datetime
from db_config import get_db_connection
import urllib.request
import os

def get_cascade_path():
    default_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml' if hasattr(cv2, 'data') else 'haarcascade_frontalface_default.xml'
    if os.path.exists(default_path):
        return default_path
    local_path = os.path.join(os.path.dirname(__file__), 'haarcascade_frontalface_default.xml')
    if not os.path.exists(local_path):
        url = 'https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_frontalface_default.xml'
        urllib.request.urlretrieve(url, local_path)
    return local_path

cascade_path = get_cascade_path()
face_cascade = cv2.CascadeClassifier(cascade_path)

def fetch_all_registered_employees():
    """Fetch active employee face encodings from MySQL database."""
    conn = get_db_connection()
    if conn is None:
        return []

    employees = []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, emp_code, full_name, face_encoding FROM employees WHERE status = 'ACTIVE'")
        rows = cursor.fetchall()

        for row in rows:
            if row['face_encoding']:
                try:
                    encoding_vector = json.loads(row['face_encoding'])
                    if len(encoding_vector) == 4096:
                        employees.append({
                            "id": row['id'],
                            "emp_code": row['emp_code'],
                            "name": row['full_name'],
                            "encoding": np.array(encoding_vector, dtype=np.float32)
                        })
                except Exception as parse_err:
                    print(f"Error parsing encoding for {row['emp_code']}: {parse_err}")

        print(f"✅ Loaded {len(employees)} active employee(s) with face encodings from database.")
    except Exception as e:
        print(f"❌ Error fetching employees: {e}")
    finally:
        conn.close()

    return employees

def mark_attendance_in_db(emp_code, emp_name):
    """Saves attendance in database matching attendance table schema (emp_code, attendance_date, in_time, status)."""
    conn = get_db_connection()
    if conn is None:
        return False, "DB connection failed"

    today_date = datetime.now().strftime('%Y-%m-%d')
    current_time = datetime.now().strftime('%H:%M:%S')

    try:
        cursor = conn.cursor(dictionary=True)
        
        # Check if attendance already marked today for this employee code
        check_query = "SELECT id FROM attendance WHERE emp_code = %s AND attendance_date = %s"
        cursor.execute(check_query, (emp_code, today_date))
        record = cursor.fetchone()

        if record:
            return True, f"Already Marked Today: {emp_name}"
        else:
            insert_query = """
                INSERT INTO attendance (emp_code, attendance_date, in_time, status)
                VALUES (%s, %s, %s, 'PRESENT')
            """
            cursor.execute(insert_query, (emp_code, today_date, current_time))
            conn.commit()
            print(f"🎉 [ATTENDANCE MARKED SUCCESS] {emp_name} ({emp_code}) at {current_time}")
            return True, f"ATTENDANCE MARKED: {emp_name}"

    except Exception as e:
        print(f"❌ [Database Error]: {e}")
        return False, f"DB Error: {e}"
    finally:
        conn.close()

def compute_similarity(enc1, enc2):
    """Cosine similarity between two 1D vectors."""
    dot = np.dot(enc1, enc2)
    norm1 = np.linalg.norm(enc1)
    norm2 = np.linalg.norm(enc2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(dot / (norm1 * norm2))

def open_camera():
    """Tries opening camera with DirectShow backend first, then MSMF / fallback indices."""
    for backend in [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]:
        for index in [0, 1, 2]:
            cam = cv2.VideoCapture(index, backend)
            if cam.isOpened():
                # Allow camera sensor to warm up & auto-exposure to adjust
                valid_frame = False
                for _ in range(10):
                    ret, frame = cam.read()
                    if ret and frame is not None and frame.size > 0 and np.mean(frame) > 5.0:
                        valid_frame = True
                if valid_frame:
                    return cam
                cam.release()
    return None

def start_attendance_system():
    registered_employees = fetch_all_registered_employees()
    if not registered_employees:
        print("⚠️ No registered employees found in database! Please register employees first.")
        return

    cam = open_camera()
    if cam is None:
        print("\n❌ Camera Error: Could not access webcam.")
        print("💡 TIP: Please close any open web browser tabs using the camera and try again.\n")
        return

    print("\n🎥 [INFO] Smart Attendance Scanner Started...")
    print("Press 'q' in the camera window to exit.\n")

    # Tracking recent attendance popups
    status_message = ""
    status_time = 0

    while True:
        ret, frame = cam.read()
        if not ret or frame is None:
            print("❌ Camera error during frame read.")
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(40, 40))

        for (x, y, w, h) in faces:
            face_roi = gray[y:y+h, x:x+w]
            resized_face = cv2.resize(face_roi, (64, 64))
            current_encoding = (resized_face.flatten() / 255.0).astype(np.float32)

            matched_emp = None
            best_similarity = 0.0

            for emp in registered_employees:
                sim = compute_similarity(emp["encoding"], current_encoding)
                dist = np.linalg.norm(emp["encoding"] - current_encoding)
                
                # Match condition: high cosine similarity OR low Euclidean distance
                if sim > best_similarity:
                    best_similarity = sim
                    if sim >= 0.55 or dist <= 20.0:
                        matched_emp = emp

            if matched_emp:
                name = matched_emp["name"]
                emp_code = matched_emp["emp_code"]

                # Green box around recognized face
                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                cv2.putText(frame, f"{name} ({emp_code})", (x, y-10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

                # Mark attendance in database
                success, msg = mark_attendance_in_db(emp_code, name)
                status_message = msg
                status_time = time.time()
            else:
                # Red box for unrecognized face
                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 0, 255), 2)
                cv2.putText(frame, "Unknown Face", (x, y-10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        # On-Screen Notification Banner
        if status_message and (time.time() - status_time < 3.5):
            cv2.rectangle(frame, (0, 0), (frame.shape[1], 45), (0, 150, 0), -1)
            cv2.putText(frame, status_message, (15, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)
        else:
            cv2.putText(frame, "Press 'q' to Exit Attendance System", (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        cv2.imshow("Smart Attendance Scanner", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cam.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    start_attendance_system()