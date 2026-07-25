import sys, io, time
# Fix Windows console encoding for Unicode/emoji print statements
try:
    if hasattr(sys.stdout, 'buffer') and not getattr(sys.stdout, 'closed', False):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace') if hasattr(sys.stdout, 'reconfigure') else None
except Exception:
    pass

import cv2
import json
import numpy as np
from datetime import datetime
from db_config import get_db_connection
import os
import face_utils

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
                    if len(encoding_vector) == 128:
                        employees.append({
                            "id": row['id'],
                            "emp_code": row['emp_code'],
                            "name": row['full_name'],
                            "encoding": np.array(encoding_vector, dtype=np.float32)
                        })
                except Exception as parse_err:
                    print(f"Error parsing encoding for {row['emp_code']}: {parse_err}")

        print(f"✅ Loaded {len(employees)} active employee(s) with 128D SFace encodings from database.")
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
    print("\n🔄 Checking and migrating database face encodings...")
    face_utils.auto_migrate_legacy_encodings()

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

    status_message = ""
    status_time = 0

    while True:
        ret, frame = cam.read()
        if not ret or frame is None:
            print("❌ Camera error during frame read.")
            break

        boxes, yunet_faces = face_utils.detect_faces(frame)

        for i, (x, y, w, h) in enumerate(boxes):
            yunet_face = yunet_faces[i] if yunet_faces is not None and i < len(yunet_faces) else None
            current_encoding = face_utils.extract_face_encoding(frame, bbox=(x, y, w, h), yunet_face=yunet_face)

            matched_emp = None
            best_similarity = -1.0

            if current_encoding is not None:
                for emp in registered_employees:
                    sim = face_utils.compute_similarity(emp["encoding"], current_encoding)
                    if sim > best_similarity:
                        best_similarity = sim
                        if sim >= face_utils.MATCH_THRESHOLD:
                            matched_emp = emp

            if matched_emp:
                name = matched_emp["name"]
                emp_code = matched_emp["emp_code"]

                # Green box around recognized face
                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                cv2.putText(frame, f"{name} ({emp_code}) [{best_similarity:.2f}]", (x, max(20, y-10)), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

                # Mark attendance in database
                success, msg = mark_attendance_in_db(emp_code, name)
                status_message = msg
                status_time = time.time()
            else:
                # Red box for unrecognized face
                label = f"Unknown ({best_similarity:.2f})" if best_similarity > -1.0 else "Unknown Face"
                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 0, 255), 2)
                cv2.putText(frame, label, (x, max(20, y-10)), 
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