import sys, io
try:
    if hasattr(sys.stdout, 'buffer') and not getattr(sys.stdout, 'closed', False):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace') if hasattr(sys.stdout, 'reconfigure') else None
except Exception:
    pass

import cv2
import json
import os
import numpy as np
from db_config import get_db_connection
import face_utils

def capture_and_process_face():
    """Webcam photo capture and 128D SFace feature extraction"""
    cam = cv2.VideoCapture(0)
    print("\n📸 [INFO] Camera opening... Frame your face and press 's' to Capture, 'q' to Quit.")
    
    captured_face_features = None
    captured_frame = None

    while True:
        ret, frame = cam.read()
        if not ret:
            print("❌ Failed to access camera.")
            break

        boxes, yunet_faces = face_utils.detect_faces(frame)

        for (x, y, w, h) in boxes:
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)

        cv2.putText(frame, "Press 's' to Capture | 'q' to Quit", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        cv2.imshow("Register Employee - Camera", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('s'):
            if len(boxes) == 0:
                print("⚠️ [WARNING] No face detected! Please face the camera properly.")
            else:
                yunet_face = yunet_faces[0] if yunet_faces is not None and len(yunet_faces) > 0 else None
                encoding = face_utils.extract_face_encoding(frame, bbox=boxes[0], yunet_face=yunet_face)
                
                if encoding is not None:
                    captured_face_features = encoding.tolist()
                    captured_frame = frame
                    print("✅ Face Captured and Encoded Successfully (128D SFace)!")
                    break
                else:
                    print("❌ Face feature extraction failed. Try again.")

        elif key == ord('q'):
            break

    cam.release()
    cv2.destroyAllWindows()
    return captured_frame, captured_face_features

def register_new_employee():
    print("========================================")
    print("   NEW EMPLOYEE REGISTRATION SYSTEM")
    print("========================================")

    emp_code = input("Enter Employee Code (e.g., EMP101): ").strip()
    full_name = input("Enter Full Name: ").strip()
    email = input("Enter Email: ").strip()
    phone = input("Enter Phone Number: ").strip()
    address = input("Enter Address: ").strip()
    
    dept_id = input("Enter Department ID (default 1): ").strip() or "1"
    desig_id = input("Enter Designation ID (default 1): ").strip() or "1"

    # 1. ക്യാമറയിൽ നിന്ന് ഫേസ് ഡാറ്റ എടുക്കുന്നു
    frame, face_encoding = capture_and_process_face()
    if frame is None or face_encoding is None:
        print("❌ Registration cancelled.")
        return

    face_encoding_str = json.dumps(face_encoding)

    # 2. ഫോട്ടോ ഫോൾഡറിലേക്ക് സേവ് ചെയ്യുന്നു
    images_dir = "captured_photos"
    if not os.path.exists(images_dir):
        os.makedirs(images_dir)

    photo_path = os.path.join(images_dir, f"{emp_code}.jpg")
    cv2.imwrite(photo_path, frame)

    # 3. MySQL ഡാറ്റാബേസിലേക്ക് ഡാറ്റ ഇൻസേർട്ട് ചെയ്യുന്നു
    conn = get_db_connection()
    if conn is None:
        return

    try:
        cursor = conn.cursor()
        query = """
            INSERT INTO employees 
            (emp_code, full_name, email, phone, address, department_id, designation_id, face_encoding, photo_path)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        values = (emp_code, full_name, email, phone, address, int(dept_id), int(desig_id), face_encoding_str, photo_path)

        cursor.execute(query, values)
        conn.commit()

        print("\n🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉")
        print(f"✅ SUCCESS: Employee {full_name} ({emp_code}) Registered Successfully!")
        print("🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉\n")

    except Exception as err:
        print(f"❌ [Database Error]: {err}")
    finally:
        conn.close()

if __name__ == "__main__":
    register_new_employee()