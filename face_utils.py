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

# Standard SFace Cosine Match Threshold (range -1.0 to 1.0, >= 0.370 is same person)
MATCH_THRESHOLD = 0.370

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

# Initialize OpenCV DNN Detector and Recognizer with optimized thresholds
yunet_detector = cv2.FaceDetectorYN.create(YUNET_PATH, '', (320, 320), 0.35, 0.3, 5000)
sface_recognizer = cv2.FaceRecognizerSF.create(SFACE_PATH, '')
haar_cascade = cv2.CascadeClassifier(CASCADE_PATH)

def preprocess_image_lighting(image):
    """
    Applies CLAHE (Contrast Limited Adaptive Histogram Equalization) on LAB color space.
    Normalizes illumination, eliminates harsh shadows and low-light issues.
    """
    if image is None or image.size == 0:
        return image
    try:
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        cl = clahe.apply(l)
        limg = cv2.merge((cl, a, b))
        return cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
    except Exception:
        return image

def synthesize_face_landmarks(bbox):
    """
    Synthesizes a 15-element YuNet face array with estimated 5 facial landmarks
    from a bounding box (x, y, w, h) based on facial proportions.
    Used as an alignment fallback if YuNet landmark extraction fails.
    """
    x, y, w, h = bbox
    re_x, re_y = float(x + 0.33 * w), float(y + 0.38 * h) # Right eye
    le_x, le_y = float(x + 0.67 * w), float(y + 0.38 * h) # Left eye
    nt_x, nt_y = float(x + 0.50 * w), float(y + 0.58 * h) # Nose tip
    rc_x, rc_y = float(x + 0.36 * w), float(y + 0.78 * h) # Right mouth corner
    lc_x, lc_y = float(x + 0.64 * w), float(y + 0.78 * h) # Left mouth corner
    
    synth = np.array([
        float(x), float(y), float(w), float(h),
        re_x, re_y, le_x, le_y, nt_x, nt_y, rc_x, rc_y, lc_x, lc_y,
        0.95
    ], dtype=np.float32)
    return synth

def detect_faces(frame):
    """
    Detects faces in BGR image using YuNet with lighting enhancement & Haar fallback.
    Returns list of bounding boxes [(x, y, w, h)] and raw YuNet face objects (15-element landmark arrays).
    """
    if frame is None or frame.size == 0:
        return [], None

    h, w = frame.shape[:2]
    yunet_detector.setInputSize((w, h))

    # 1. Primary YuNet Detection
    _, faces = yunet_detector.detect(frame)

    # 2. Try CLAHE Enhanced frame if YuNet missed faces
    if faces is None or len(faces) == 0:
        enhanced = preprocess_image_lighting(frame)
        _, faces = yunet_detector.detect(enhanced)

    boxes = []
    if faces is not None and len(faces) > 0:
        for face in faces:
            bbox = face[0:4].astype(int)
            x, y, bw, bh = bbox[0], bbox[1], bbox[2], bbox[3]
            x, y = max(0, x), max(0, y)
            boxes.append((x, y, bw, bh))
        return boxes, faces

    # 3. Fallback to Haar Cascade
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    haabs = haar_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(40, 40))
    
    synth_faces = []
    for (x, y, bw, bh) in haabs:
        boxes.append((x, y, bw, bh))
        synth_faces.append(synthesize_face_landmarks((x, y, bw, bh)))

    yunet_faces_res = np.array(synth_faces, dtype=np.float32) if synth_faces else None
    return boxes, yunet_faces_res

def extract_face_encoding(frame, bbox=None, yunet_face=None):
    """
    Extracts a normalized 128-dimensional SFace embedding vector from a face in frame.
    Uses facial landmark alignment (alignCrop) for maximum accuracy.
    Returns 1D numpy array of shape (128,) or None if extraction fails.
    """
    try:
        if frame is None or frame.size == 0:
            return None

        h, w = frame.shape[:2]
        yunet_detector.setInputSize((w, h))

        target_yunet_face = yunet_face

        # If yunet_face is missing but bbox is provided, detect landmarks on cropped ROI
        if target_yunet_face is None and bbox is not None:
            bx, by, bw, bh = bbox
            pad_w, pad_h = int(bw * 0.2), int(bh * 0.2)
            crop_x1 = max(0, bx - pad_w)
            crop_y1 = max(0, by - pad_h)
            crop_x2 = min(w, bx + bw + pad_w)
            crop_y2 = min(h, by + bh + pad_h)

            roi = frame[crop_y1:crop_y2, crop_x1:crop_x2]
            if roi.size > 0:
                roi_h, roi_w = roi.shape[:2]
                yunet_detector.setInputSize((roi_w, roi_h))
                _, roi_faces = yunet_detector.detect(roi)
                if roi_faces is None or len(roi_faces) == 0:
                    enhanced_roi = preprocess_image_lighting(roi)
                    _, roi_faces = yunet_detector.detect(enhanced_roi)

                if roi_faces is not None and len(roi_faces) > 0:
                    best_rf = roi_faces[0].copy()
                    best_rf[0] += crop_x1
                    best_rf[1] += crop_y1
                    best_rf[4:14:2] += crop_x1
                    best_rf[5:14:2] += crop_y1
                    target_yunet_face = best_rf

            yunet_detector.setInputSize((w, h))

        # Fallback to synthesized landmarks if still None but bbox exists
        if target_yunet_face is None and bbox is not None:
            target_yunet_face = synthesize_face_landmarks(bbox)

        # Full frame detection if no target landmarks or bbox
        if target_yunet_face is None:
            _, faces = yunet_detector.detect(frame)
            if faces is None or len(faces) == 0:
                enhanced = preprocess_image_lighting(frame)
                _, faces = yunet_detector.detect(enhanced)
            if faces is not None and len(faces) > 0:
                target_yunet_face = faces[0]

        if target_yunet_face is not None:
            aligned_face = sface_recognizer.alignCrop(frame, target_yunet_face)
            feat = sface_recognizer.feature(aligned_face).flatten().astype(np.float32)
            norm = np.linalg.norm(feat)
            if norm > 0:
                feat = feat / norm
            return feat

    except Exception as e:
        print(f"Extraction error: {e}")
    return None

def compute_similarity(enc1, enc2):
    """
    Computes SFace cosine similarity score between two 128D vectors.
    Score ranges from -1.0 to 1.0 (Same person if score >= MATCH_THRESHOLD).
    """
    if enc1 is None or enc2 is None:
        return 0.0
    v1 = np.array(enc1, dtype=np.float32).flatten()
    v2 = np.array(enc2, dtype=np.float32).flatten()
    if len(v1) != 128 or len(v2) != 128:
        return 0.0
    
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 > 0: v1 = v1 / n1
    if n2 > 0: v2 = v2 / n2

    score = sface_recognizer.match(v1.reshape(1, 128), v2.reshape(1, 128), cv2.FaceRecognizerSF_FR_COSINE)
    return float(score)

def is_same_person(enc1, enc2, threshold=MATCH_THRESHOLD):
    """Returns True if cosine similarity >= threshold."""
    return compute_similarity(enc1, enc2) >= threshold

def auto_migrate_legacy_encodings(force_reencode=False):
    """
    Scans MySQL DB employees table.
    Upgrades legacy encodings and updates 128-dim SFace encodings from saved photos.
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

            needs_migration = force_reencode
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
                            print(f"✅ Re-encoded face embedding for {row['full_name']} ({emp_code}) using SFace alignment.")

    except Exception as err:
        print(f"❌ Auto-migration error: {err}")
    finally:
        conn.close()

    return migrated_count

