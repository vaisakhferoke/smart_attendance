// DOM Elements
const video = document.getElementById('video');
const canvas = document.getElementById('canvas');
const snapBtn = document.getElementById('snapBtn');
const retakeBtn = document.getElementById('retakeBtn');
const photoInput = document.getElementById('photoInput');
const form = document.getElementById('empForm');
const submitBtn = document.getElementById('submitBtn');
const btnText = submitBtn.querySelector('.btn-text');
const btnSpinner = submitBtn.querySelector('.btn-spinner');

const videoContainer = document.getElementById('videoContainer');
const snapshotContainer = document.getElementById('snapshotContainer');
const snapshotPreview = document.getElementById('snapshotPreview');

const toast = document.getElementById('toast');
const toastIcon = document.getElementById('toastIcon');
const toastMsg = document.getElementById('toastMsg');

// Toast helper function
function showToast(message, type = 'info') {
    toastMsg.textContent = message;
    toast.className = `toast ${type}`;

    if (type === 'success') {
        toastIcon.className = 'fa-solid fa-circle-check';
    } else if (type === 'error') {
        toastIcon.className = 'fa-solid fa-circle-xmark';
    } else if (type === 'warning') {
        toastIcon.className = 'fa-solid fa-triangle-exclamation';
    } else {
        toastIcon.className = 'fa-solid fa-info-circle';
    }
}

// Access webcam stream
function initMainWebcam() {
    navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' } })
        .catch(() => navigator.mediaDevices.getUserMedia({ video: true }))
        .then(stream => {
            if (video) {
                video.srcObject = stream;
                video.onloadedmetadata = () => {
                    video.play().catch(err => console.warn('Video play error:', err));
                };
            }
            showToast('Webcam connected. Position your face in frame.', 'info');
        })
        .catch(err => {
            console.error('Camera access error:', err);
            showToast('Camera error: Unable to access webcam. Ensure camera is connected & permissions granted.', 'error');
        });
}

if (video) {
    initMainWebcam();
}

// Capture Photo Action
snapBtn.addEventListener('click', () => {
    if (!video.srcObject) {
        showToast('Webcam stream unavailable.', 'error');
        return;
    }

    const ctx = canvas.getContext('2d');
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    const dataURL = canvas.toDataURL('image/jpeg', 0.9);
    photoInput.value = dataURL;

    // Show snapshot preview
    snapshotPreview.src = dataURL;
    videoContainer.style.display = 'none';
    snapshotContainer.style.display = 'block';

    // Toggle Buttons
    snapBtn.style.display = 'none';
    retakeBtn.style.display = 'inline-flex';

    showToast('Face photo captured & ready!', 'success');
});

// Retake Photo Action
retakeBtn.addEventListener('click', () => {
    photoInput.value = '';
    snapshotContainer.style.display = 'none';
    videoContainer.style.display = 'block';

    snapBtn.style.display = 'inline-flex';
    retakeBtn.style.display = 'none';

    showToast('Frame your face and click capture.', 'info');
});

// Form Submit Handler
form.addEventListener('submit', e => {
    e.preventDefault();

    if (!photoInput.value) {
        showToast('Please capture or select your face photo before registering.', 'warning');
        return;
    }

    // Show loading state
    btnText.style.display = 'none';
    btnSpinner.style.display = 'inline-block';
    submitBtn.disabled = true;

    const formData = new FormData(form);

    fetch('/register', {
        method: 'POST',
        body: formData
    })
        .then(r => r.json())
        .then(res => {
            if (res.status === 'success') {
                showToast(res.msg, 'success');
                form.reset();
                photoInput.value = '';

                // Reset Camera view
                snapshotContainer.style.display = 'none';
                videoContainer.style.display = 'block';
                snapBtn.style.display = 'inline-flex';
                retakeBtn.style.display = 'none';
            } else {
                showToast(res.msg || 'Registration failed.', 'error');
            }
        })
        .catch(err => {
            console.error('Registration error:', err);
            showToast('Network error while saving data.', 'error');
        })
        .finally(() => {
            // Reset loading state
            btnText.style.display = 'inline-block';
            btnSpinner.style.display = 'none';
            submitBtn.disabled = false;
        });
});

// Mode Switching (Webcam vs File Upload)
function switchRegisterMode(mode) {
    const fileSection = document.getElementById('fileUploadSection');
    const cameraActions = document.getElementById('cameraActions');
    const modeCamBtn = document.getElementById('modeCamBtn');
    const modeUploadBtn = document.getElementById('modeUploadBtn');

    if (mode === 'upload') {
        fileSection.style.display = 'block';
        cameraActions.style.display = 'none';
        modeUploadBtn.className = 'photo-tab-btn active';
        modeCamBtn.className = 'photo-tab-btn';
    } else {
        fileSection.style.display = 'none';
        cameraActions.style.display = 'flex';
        modeUploadBtn.className = 'photo-tab-btn';
        modeCamBtn.className = 'photo-tab-btn active';
        videoContainer.style.display = 'block';
        snapshotContainer.style.display = 'none';
    }
}

function handleFileSelect(input) {
    if (input.files && input.files[0]) {
        const reader = new FileReader();
        reader.onload = function (e) {
            const dataURL = e.target.result;
            photoInput.value = dataURL;
            snapshotPreview.src = dataURL;
            videoContainer.style.display = 'none';
            snapshotContainer.style.display = 'block';
            document.getElementById('capturedBadge').innerHTML = '<i class="fa-solid fa-circle-check"></i> Profile Photo Loaded';
            showToast('Profile photo file loaded & ready!', 'success');
        };
        reader.readAsDataURL(input.files[0]);
    }
}