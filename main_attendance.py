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

            # Send FCM Push Notification to Employee upon successful check-in
            try:
                import fcm_service
                fcm_service.send_attendance_notification(
                    emp_code=emp_code,
                    full_name=emp_name,
                    in_time=current_time
                )
            except Exception as fcm_err:
                print(f"FCM notification exception: {fcm_err}")

            return True, f"ATTENDANCE MARKED: {emp_name}"

    except Exception as e:
        print(f"❌ [Database Error]: {e}")
        return False, f"DB Error: {e}"
    finally:
        conn.close()

def open_camera():
    """Tries opening camera with CAP_ANY first, then CAP_DSHOW / MSMF across device indices."""
    backends = [
        ("CAP_ANY", cv2.CAP_ANY),
        ("CAP_DSHOW", cv2.CAP_DSHOW),
        ("CAP_MSMF", cv2.CAP_MSMF)
    ]
    for bname, backend in backends:
        for index in [0, 1, 2]:
            try:
                cam = cv2.VideoCapture(index, backend)
                if cam.isOpened():
                    valid_read = False
                    for _ in range(15):
                        ret, frame = cam.read()
                        if ret and frame is not None and frame.size > 0:
                            valid_read = True
                            break
                        time.sleep(0.05)
                    if valid_read:
                        print(f"📷 [INFO] Camera connected successfully (index {index}, backend {bname}).")
                        return cam
                    cam.release()
            except Exception:
                pass
    return None

def start_attendance_system():
    print("\n🔄 Checking database face encodings...")
    face_utils.auto_migrate_legacy_encodings(force_reencode=False)

    registered_employees = fetch_all_registered_employees()
    if not registered_employees:
        print("⚠️ No registered employees found in database! Please register employees first.")
        return

    cam = open_camera()
    if cam is None:
        print("\n❌ Camera Error: Could not access webcam.")
        print("💡 TIP: Please close any open web browser tabs using the camera and try again.\n")
        return

    print("\n🎥 [INFO] Smart Attendance Scanner Started (High Accuracy SFace Engine)...")
    print("Press 'q' in the camera window to exit.\n")

    status_message = ""
    status_time = 0
    consecutive_tracker = {}
    CONSECUTIVE_REQUIRED = 2  # Requires 2 consecutive positive frames to confirm attendance
    MIN_FACE_SIZE = 45        # Filter out tiny distant noise faces (< 45x45 px)

    while True:
        ret, frame = cam.read()
        if not ret or frame is None:
            print("❌ Camera error during frame read.")
            break

        boxes, yunet_faces = face_utils.detect_faces(frame)
        current_frame_matched_codes = set()

        for i, (x, y, w, h) in enumerate(boxes):
            # Skip tiny background face regions
            if w < MIN_FACE_SIZE or h < MIN_FACE_SIZE:
                continue

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
                emp_code = matched_emp["emp_code"]
                name = matched_emp["name"]
                current_frame_matched_codes.add(emp_code)

                consecutive_tracker[emp_code] = consecutive_tracker.get(emp_code, 0) + 1
                match_count = consecutive_tracker[emp_code]

                if match_count >= CONSECUTIVE_REQUIRED:
                    # Verified match -> Green Box
                    cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                    cv2.putText(frame, f"✅ {name} ({emp_code}) [{best_similarity:.2f}]", (x, max(20, y-10)), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

                    # Mark attendance in database once verified
                    success, msg = mark_attendance_in_db(emp_code, name)
                    status_message = msg
                    status_time = time.time()
                else:
                    # Multi-frame verification in progress -> Yellow Box
                    cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 255), 2)
                    cv2.putText(frame, f"Verifying {name}... [{best_similarity:.2f}]", (x, max(20, y-10)), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
            else:
                # Unrecognized face -> Red Box
                label = f"Unknown ({best_similarity:.2f})" if best_similarity > -1.0 else "Unknown Face"
                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 0, 255), 2)
                cv2.putText(frame, label, (x, max(20, y-10)), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        # Decay consecutive match counts for employees not detected in current frame
        for code in list(consecutive_tracker.keys()):
            if code not in current_frame_matched_codes:
                consecutive_tracker[code] = max(0, consecutive_tracker[code] - 1)
                if consecutive_tracker[code] == 0:
                    del consecutive_tracker[code]

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