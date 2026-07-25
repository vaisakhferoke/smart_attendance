import cv2
import json
import os
import numpy as np
from db_config import get_db_connection
import urllib.request

def get_cascade_path():
    """
    Returns the path to Haar cascade XML file.
    Downloads it if not present.
    """
    default_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    if os.path.exists(default_path):
        return default_path
    # Fallback: download to script directory
    local_path = os.path.join(os.path.dirname(__file__), 'haarcascade_frontalface_default.xml')
    if not os.path.exists(local_path):
        url = 'https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_frontalface_default.xml'
        print('[INFO] Downloading Haar cascade file...')
        urllib.request.urlretrieve(url, local_path)
    return local_path

cascade_path = get_cascade_path()
face_cascade = cv2.CascadeClassifier(cascade_path)
if face_cascade.empty():
    raise RuntimeError('Failed to load Haar cascade classifier from ' + cascade_path)

def capture_and_process_face():
    """വെബ്‌ക്യാം വഴി ഫോട്ടോ എടുത്ത് ഫേസ് ക്രോപ്പ് ചെയ്ത് Feature Vector ഉണ്ടാക്കുന്നു"""
    cam = cv2.VideoCapture(0)
    print("\n📸 [INFO] Camera opening... Frame your face and press 's' to Capture, 'q' to Quit.")
    
    captured_face_features = None
    captured_frame = None

    while True:
        ret, frame = cam.read()
        if not ret:
            print("❌ Failed to access camera.")
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Face Detection
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100))

        # ക്യാമറ സ്ക്രീനിൽ ഫേസിന് ചുറ്റും ബോക്സ് വരയ്ക്കാൻ
        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)

        cv2.putText(frame, "Press 's' to Capture | 'q' to Quit", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        cv2.imshow("Register Employee - Camera", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('s'):
            if len(faces) == 0:
                print("⚠️ [WARNING] No face detected! Please face the camera properly.")
            else:
                # മുഖമുള്ള ഭാഗം മാത്രം ക്രോപ്പ് ചെയ്യുന്നു
                (x, y, w, h) = faces[0]
                face_roi = gray[y:y+h, x:x+w]
                
                # Resize to 64x64
                resized_face = cv2.resize(face_roi, (64, 64))
                
                # Normalize values
                captured_face_features = (resized_face.flatten() / 255.0).tolist()
                captured_frame = frame
                print("✅ Face Captured and Encoded Successfully!")
                break

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