import cv2
import numpy as np
import json
import os
import sys
import io
import urllib.request
from db_config import get_db_connection

# Fix Windows console encoding for Unicode/emoji print statements
try:
    if hasattr(sys.stdout, 'buffer') and not getattr(sys.stdout, 'closed', False):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace') if hasattr(sys.stdout, 'reconfigure') else None
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
YUNET_PATH = os.path.join(BASE_DIR, 'face_detection_yunet_2023mar.onnx')
SFACE_PATH = os.path.join(BASE_DIR, 'face_recognition_sface_2021dec.onnx')
CASCADE_PATH = os.path.join(BASE_DIR, 'haarcascade_frontalface_default.xml')

# Standard SFace Cosine Match Threshold (range 0.0 to 1.0, >= 0.363 is same person)
MATCH_THRESHOLD = 0.383

def ensure_models_exist():
    """Download YuNet, SFace, and Haar cascade XML if not found locally."""
    if not os.path.exists(YUNET_PATH):
        print("📥 Downloading YuNet face detection model...")
        url = 'https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx'
        urllib.request.urlretrieve(url, YUNET_PATH)

    if not os.path.exists(SFACE_PATH):
        print("📥 Downloading SFace face recognition model...")
        url = 'https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx'
        urllib.request.urlretrieve(url, SFACE_PATH)

    if not os.path.exists(CASCADE_PATH):
        default_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml' if hasattr(cv2, 'data') else ''
        if os.path.exists(default_path):
            import shutil
            shutil.copy(default_path, CASCADE_PATH)
        else:
            print("📥 Downloading Haar cascade XML...")
            url = 'https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_frontalface_default.xml'
            urllib.request.urlretrieve(url, CASCADE_PATH)

ensure_models_exist()

# Initialize OpenCV DNN Detector and Recognizer
yunet_detector = cv2.FaceDetectorYN.create(YUNET_PATH, '', (320, 320), 0.5, 0.3, 5000)
sface_recognizer = cv2.FaceRecognizerSF.create(SFACE_PATH, '')
haar_cascade = cv2.CascadeClassifier(CASCADE_PATH)

def detect_faces(frame):
    """
    Detects faces in BGR image using YuNet with Haar cascade fallback.
    Returns list of bounding boxes [(x, y, w, h)] and raw YuNet face objects if available.
    """
    h, w = frame.shape[:2]
    yunet_detector.setInputSize((w, h))
    _, faces = yunet_detector.detect(frame)

    boxes = []
    if faces is not None and len(faces) > 0:
        for face in faces:
            bbox = face[0:4].astype(int)
            x, y, bw, bh = bbox[0], bbox[1], bbox[2], bbox[3]
            x, y = max(0, x), max(0, y)
            boxes.append((x, y, bw, bh))
        return boxes, faces

    # Fallback to Haar Cascade
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    haabs = haar_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(40, 40))
    for (x, y, bw, bh) in haabs:
        boxes.append((x, y, bw, bh))
    return boxes, None

def extract_face_encoding(frame, bbox=None, yunet_face=None):
    """
    Extracts a 128-dimensional SFace embedding vector from a face in frame.
    Returns 1D numpy array of shape (128,) or None if extraction fails.
    """
    try:
        if frame is None or frame.size == 0:
            return None

        h, w = frame.shape[:2]
        yunet_detector.setInputSize((w, h))

        if yunet_face is not None:
            aligned_face = sface_recognizer.alignCrop(frame, yunet_face)
            feat = sface_recognizer.feature(aligned_face)
            return feat.flatten().astype(np.float32)

        if bbox is not None:
            x, y, bw, bh = bbox
            face_roi = frame[max(0, y):y+bh, max(0, x):x+bw]
            if face_roi.size > 0:
                resized = cv2.resize(face_roi, (112, 112))
                feat = sface_recognizer.feature(resized)
                return feat.flatten().astype(np.float32)

        # Full frame detect
        _, faces = yunet_detector.detect(frame)
        if faces is not None and len(faces) > 0:
            aligned_face = sface_recognizer.alignCrop(frame, faces[0])
            feat = sface_recognizer.feature(aligned_face)
            return feat.flatten().astype(np.float32)

    except Exception as e:
        print(f"Extraction error: {e}")
    return None

def compute_similarity(enc1, enc2):
    """
    Computes SFace cosine similarity score between two 128D vectors.
    Score ranges from -1.0 to 1.0 (Same person if score >= 0.383).
    """
    if enc1 is None or enc2 is None:
        return 0.0
    v1 = np.array(enc1, dtype=np.float32).reshape(1, 128)
    v2 = np.array(enc2, dtype=np.float32).reshape(1, 128)
    score = sface_recognizer.match(v1, v2, cv2.FaceRecognizerSF_FR_COSINE)
    return float(score)

def is_same_person(enc1, enc2, threshold=MATCH_THRESHOLD):
    """Returns True if cosine similarity >= threshold."""
    return compute_similarity(enc1, enc2) >= threshold

def auto_migrate_legacy_encodings():
    """
    Scans MySQL DB employees table.
    Upgrades legacy 4096-dim encodings to 128-dim SFace encodings from saved photos.
    """
    conn = get_db_connection()
    if conn is None:
        return 0

    migrated_count = 0
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, emp_code, full_name, face_encoding, photo_path FROM employees WHERE status = 'ACTIVE'")
        rows = cursor.fetchall()

        for row in rows:
            emp_id = row['id']
            emp_code = row['emp_code']
            encoding_str = row['face_encoding']
            photo_path = row['photo_path']

            needs_migration = False
            if not encoding_str:
                needs_migration = True
            else:
                try:
                    vec = json.loads(encoding_str)
                    if len(vec) != 128:
                        needs_migration = True
                except Exception:
                    needs_migration = True

            if needs_migration and photo_path:
                abs_photo_path = photo_path
                if not os.path.isabs(photo_path):
                    abs_photo_path = os.path.join(BASE_DIR, photo_path)

                if os.path.exists(abs_photo_path):
                    img = cv2.imread(abs_photo_path)
                    if img is not None:
                        new_encoding = extract_face_encoding(img)
                        if new_encoding is not None and len(new_encoding) == 128:
                            enc_json = json.dumps(new_encoding.tolist())
                            cursor.execute("UPDATE employees SET face_encoding = %s WHERE id = %s", (enc_json, emp_id))
                            conn.commit()
                            migrated_count += 1
                            print(f"✅ Migrated face encoding for {row['full_name']} ({emp_code}) to 128D SFace.")

    except Exception as err:
        print(f"❌ Auto-migration error: {err}")
    finally:
        conn.close()

    return migrated_count
