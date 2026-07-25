# 🚀 Smart Attendance System - API Documentation

Welcome to the **Smart Biometric Attendance System API Documentation**. This document covers all available **REST APIs**, **Graph APIs (GraphQL)**, **Employee Login & Auth Endpoints**, **FCM Token Updates**, and **Firebase Admin SDK Push Notification Triggers**.

---

## 📌 Base Configuration

- **Base Server URL**: `http://localhost:5000` (or configured Flask host:port)
- **API Prefix**: `/api`
- **Data Format**: `JSON` (`Content-Type: application/json`)
- **Authentication Method**: Password hashing via `werkzeug.security` (`scrypt` / `PBKDF2`).
- **Firebase Service Account Key**: `smartattendance-47469-firebase-adminsdk-fbsvc-80e4f47be9.json`

---

## 🔥 1. Firebase Admin SDK Integration & Auto Push Notifications

The system automatically initializes **Firebase Admin SDK** using the service account credentials key:
`smartattendance-47469-firebase-adminsdk-fbsvc-80e4f47be9.json`

### 🎯 Attendance Check-In FCM Trigger
When an employee successfully marks attendance (via facial recognition scan API or scanner GUI):
1. The backend retrieves the employee's registered `fcm_token` from the `employees` table.
2. If an `fcm_token` is present, an FCM Push Notification is automatically sent to the employee's mobile device via Firebase Admin SDK.

#### 📨 FCM Push Notification Payload Structure

##### Notification Title & Body
- **Title**: `Attendance Checked-In! 🎯`
- **Body**: `Hello {full_name}, your attendance check-in was successfully recorded at {in_time}.`

##### Data Payload
```json
{
  "click_action": "FLUTTER_NOTIFICATION_CLICK",
  "type": "attendance_checkin",
  "emp_code": "EMP1236",
  "full_name": "Sandeep Kumar",
  "in_time": "16:33:14",
  "department": "Finance",
  "branch": "Headquarters",
  "timestamp": "2026-07-25T16:33:14.123456"
}
```

---

## 📱 2. Database Schema (`employees` table)

| Field Name | Type | Description |
|---|---|---|
| `username` | `VARCHAR(100)` | Employee account login username |
| `password` | `VARCHAR(255)` | Encrypted/hashed password |
| `fcm_token` | `TEXT` | Firebase Cloud Messaging (FCM) push notification token |
| `app_version` | `VARCHAR(50)` | Installed mobile app version (e.g. `1.0.4`) |
| `app_platform` | `VARCHAR(50)` | OS platform (e.g. `android`, `ios`) |
| `last_login_date` | `DATETIME` | Timestamp of the last logged-in session |

---

## 🔐 3. Employee Authentication REST API

### 🔑 Endpoint: Employee Login
Authenticates employee accounts from the `employees` table, updates FCM token and timestamp, and returns access token + profile.

- **URL**: `/api/v1/employee/login`
- **Method**: `POST`
- **Headers**: `Content-Type: application/json`

#### 📥 Request Body
```json
{
  "username": "sandeep",
  "password": "your_secure_password",
  "fcm_token": "fcm_push_token_xyz_123...",
  "app_version": "1.0.4",
  "app_platform": "android"
}
```

#### 📤 Success Response (`200 OK`)
```json
{
  "status": "success",
  "code": 200,
  "message": "Welcome back, Sandeep Kumar!",
  "auth_token": "a4d8c8ef92a10b42f61e890c37ad4d5f190c3b88019ab23a",
  "employee": {
    "id": 1,
    "emp_code": "EMP1236",
    "username": "sandeep",
    "full_name": "Sandeep Kumar",
    "email": "deep@gmail.com",
    "phone": "+123456987",
    "address": "Street Address",
    "status": "ACTIVE",
    "branch": "Headquarters",
    "department": "Finance",
    "designation": "Accountant",
    "fcm_token": "fcm_push_token_xyz_123...",
    "app_version": "1.0.4",
    "app_platform": "android",
    "last_logged_date": "2026-07-25 16:15:00",
    "photo_url": "/captured_photos/EMP1236.jpg"
  }
}
```

---

## 🔔 4. Employee FCM & App Info Update API

### 📲 Endpoint: Update FCM Token & Device Information
- **URL**: `/api/v1/employee/fcm-update` *(Alias: `/api/v1/employee/update-fcm`)*
- **Method**: `POST`
- **Headers**: `Content-Type: application/json`

#### 📥 Request Body
```json
{
  "emp_id": 1,
  "fcm_token": "fcm_push_token_xyz_123...",
  "app_version": "1.0.4",
  "app_platform": "android"
}
```

#### 📤 Success Response (`200 OK`)
```json
{
  "status": "success",
  "code": 200,
  "message": "FCM token and device information updated successfully for Sandeep Kumar",
  "updated_info": {
    "emp_id": 1,
    "emp_code": "EMP1236",
    "username": "sandeep",
    "fcm_token": "fcm_push_token_xyz_123...",
    "app_version": "1.0.4",
    "app_platform": "android",
    "last_logged_date": "2026-07-25 16:15:00"
  }
}
```

---

## 🌐 5. Graph API & GraphQL Endpoints

- **Endpoints**: `/api/graph` or `/api/graphql`
- **Method**: `POST`

### 🔹 Graph Operation A: `updateEmployeeFcm`
```json
{
  "operation": "updateEmployeeFcm",
  "variables": {
    "emp_id": 1,
    "fcm_token": "fcm_token_xyz...",
    "app_version": "1.0.4",
    "app_platform": "android"
  }
}
```

### 🔹 Graph Operation B: `loginEmployee`
```json
{
  "operation": "loginEmployee",
  "variables": {
    "username": "sandeep",
    "password": "your_password",
    "fcm_token": "fcm_token_xyz...",
    "app_version": "1.0.4",
    "app_platform": "android"
  }
}
```

---

## 📷 6. Biometrics & Attendance Facial Scan API

- **URL**: `/api/scan_attendance`
- **Method**: `POST`
- **Payload**:
  ```json
  {
    "photo": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQ..."
  }
  ```
- **FCM Action**: Upon matching an active face encoding and inserting attendance, FCM Push Notification is triggered automatically to the matched employee.

---

## 💻 Code Usage Examples

### 📱 JavaScript / Flutter FCM Update Example
```javascript
const response = await fetch('http://localhost:5000/api/v1/employee/fcm-update', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    emp_id: 1,
    fcm_token: await messaging().getToken(),
    app_version: '1.0.4',
    app_platform: Platform.OS // 'android' or 'ios'
  })
});

const result = await response.json();
console.log(result.message);
```
