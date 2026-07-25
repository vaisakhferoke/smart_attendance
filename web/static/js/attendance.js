// DOM Elements
const video = document.getElementById('video');
const canvas = document.getElementById('canvas');
const scanStatus = document.getElementById('scanStatus');

const idleState = document.getElementById('idleState');
const resultState = document.getElementById('resultState');

const empFullName = document.getElementById('empFullName');
const empCodeBadge = document.getElementById('empCodeBadge');
const empDepartment = document.getElementById('empDepartment');
const empDesignation = document.getElementById('empDesignation');
const empInTime = document.getElementById('empInTime');
const empStatusPill = document.getElementById('empStatusPill');
const resetProgressBar = document.getElementById('resetProgressBar');

let isScanning = true;
let scanInterval = null;
let cooldownTimer = null;
let currentStream = null;

function initWebcam() {
    if (currentStream) {
        currentStream.getTracks().forEach(track => track.stop());
    }

    scanStatus.className = 'scan-status-text';
    scanStatus.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Initializing camera stream...';

    const constraints = {
        video: {
            width: { ideal: 1280, max: 1920 },
            height: { ideal: 720, max: 1080 },
            facingMode: 'user'
        }
    };

    navigator.mediaDevices.getUserMedia(constraints)
        .catch(() => navigator.mediaDevices.getUserMedia({ video: true }))
        .then(stream => {
            currentStream = stream;
            video.srcObject = stream;
            video.onloadedmetadata = () => {
                video.play().catch(err => console.warn('Video play error:', err));
            };

            scanStatus.innerHTML = '<i class="fa-solid fa-face-viewfinder"></i> Auto-scanning face... Position in camera.';

            if (scanInterval) clearInterval(scanInterval);
            scanInterval = setInterval(captureAndScanFrame, 1200);
        })
        .catch(err => {
            console.error('Camera access error:', err);
            scanStatus.className = 'scan-status-text error';
            scanStatus.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> Camera Access Denied or Device Busy. <button onclick="initWebcam()" style="background:#2563eb; color:#fff; border:none; padding:4px 10px; border-radius:4px; margin-left:8px; cursor:pointer;"><i class="fa-solid fa-rotate-right"></i> Retry</button>';
        });
}

// Start webcam on page load
initWebcam();

function captureAndScanFrame() {
    if (!isScanning || !video.srcObject) return;

    const ctx = canvas.getContext('2d');
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    const dataURL = canvas.toDataURL('image/jpeg', 0.85);

    fetch('/api/scan_attendance', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ photo: dataURL })
    })
        .then(r => r.json())
        .then(res => {
            if (!isScanning) return; // if scanning was paused while request was in-flight

            if (res.status === 'success') {
                if (res.recognized && res.employee) {
                    // Face recognized! Pause scanning and display employee details popup
                    triggerRecognizedEmployee(res.employee, res.msg, res.already_marked);
                } else {
                    scanStatus.innerHTML = `<i class="fa-solid fa-face-viewfinder"></i> ${res.msg || 'Position face clearly...'}`;
                }
            } else {
                console.warn('Scan notice:', res.msg);
            }
        })
        .catch(err => {
            console.error('Scan API error:', err);
        });
}

function triggerRecognizedEmployee(emp, message, alreadyMarked) {
    isScanning = false; // Pause scanner during display

    // Populate Recognized Employee Card
    empFullName.textContent = emp.full_name || 'N/A';
    empCodeBadge.textContent = emp.emp_code || 'EMP-000';
    empDepartment.textContent = emp.department_name || 'General';
    empDesignation.textContent = emp.designation_name || 'Staff';
    empInTime.textContent = emp.in_time || '--:--';

    if (alreadyMarked) {
        empStatusPill.className = 'status-pill warning';
        empStatusPill.innerHTML = '<i class="fa-solid fa-circle-info"></i> ALREADY CHECKED IN';
    } else {
        empStatusPill.className = 'status-pill success';
        empStatusPill.innerHTML = '<i class="fa-solid fa-circle-check"></i> PRESENT - MARKED';
    }

    // Update scanner status bar
    scanStatus.innerHTML = `<i class="fa-solid fa-circle-check" style="color: #10b981;"></i> ${message}`;

    // Show Result Panel with animation
    idleState.style.display = 'none';
    resultState.style.display = 'block';

    // Start progress bar animation (4 seconds)
    resetProgressBar.style.transition = 'none';
    resetProgressBar.style.width = '100%';

    setTimeout(() => {
        resetProgressBar.style.transition = 'width 4s linear';
        resetProgressBar.style.width = '0%';
    }, 50);

    // Reset after 4 seconds for next employee scan
    clearTimeout(cooldownTimer);
    cooldownTimer = setTimeout(() => {
        resultState.style.display = 'none';
        idleState.style.display = 'flex';
        scanStatus.innerHTML = '<i class="fa-solid fa-face-viewfinder"></i> Auto-scanning face... Position in camera.';
        isScanning = true; // Resume scanner
    }, 4000);
}
