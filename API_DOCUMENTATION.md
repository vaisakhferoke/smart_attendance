# 🚀 Smart Attendance System - API Documentation

Welcome to the **Smart Biometric Attendance System API Documentation**. This document covers all available **REST APIs**, **Graph APIs (GraphQL)**, and **Employee Authentication Endpoints**.

---

## 📌 Base Configuration

- **Base Server URL**: `http://localhost:5000` (or configured Flask host:port)
- **API Prefix**: `/api`
- **Data Format**: `JSON` (`Content-Type: application/json`)
- **Authentication Method**: Password hashing via `werkzeug.security` (scrypt / PBKDF2).

---

## 🔐 1. Employee Authentication REST API

### 🔑 Endpoint: Employee Login
Authenticates employee accounts from the `employees` database table using `username`, `emp_code`, or `email` along with their encrypted password.

- **URL**: `/api/v1/employee/login`
- **Method**: `POST`
- **Headers**:
  ```http
  Content-Type: application/json
  ```

#### 📥 Request Body
```json
{
  "username": "sandeep",
  "password": "your_secure_password"
}
```
> *Note: `username` can be the employee's assigned username, employee code (e.g. `EMP1236`), or email address.*

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
    "address": "Qjfnbjd",
    "status": "ACTIVE",
    "branch": "Headquarters",
    "department": "Finance",
    "designation": "Accountant",
    "photo_url": "/captured_photos/EMP1236.jpg",
    "registered_at": "2026-07-25 10:15:00"
  }
}
```

#### ⚠️ Error Responses

- **`400 Bad Request`**: Missing credentials.
  ```json
  {
    "status": "error",
    "code": 400,
    "message": "Username/EmpCode/Email and Password are required."
  }
  ```
- **`401 Unauthorized`**: Invalid username or password.
  ```json
  {
    "status": "error",
    "code": 401,
    "message": "Invalid password."
  }
  ```
- **`403 Forbidden`**: Employee account is inactive.
  ```json
  {
    "status": "error",
    "code": 403,
    "message": "Employee account is INACTIVE. Please contact administration."
  }
  ```

---

### 👤 Endpoint: Get Employee Profile
Fetches profile and organizational details for a specific employee ID.

- **URL**: `/api/v1/employee/profile/<emp_id>`
- **Method**: `GET`

#### 📤 Success Response (`200 OK`)
```json
{
  "status": "success",
  "employee": {
    "id": 1,
    "emp_code": "EMP1236",
    "username": "sandeep",
    "full_name": "Sandeep Kumar",
    "email": "deep@gmail.com",
    "phone": "+123456987",
    "address": "Qjfnbjd",
    "status": "ACTIVE",
    "branch": "Headquarters",
    "department": "Finance",
    "designation": "Accountant",
    "photo_url": "/captured_photos/EMP1236.jpg",
    "registered_at": "2026-07-25 10:15:00"
  }
}
```

---

## 🌐 2. Employee Graph API & GraphQL Endpoint

The Graph API supports both standard **GraphQL queries** and **Graph Operation payloads**.

- **Endpoints**: `/api/graph` or `/api/graphql`
- **Method**: `POST`
- **Headers**: `Content-Type: application/json`

---

### 🔹 Graph Operation A: `loginEmployee`

#### Option 1: Standard GraphQL Request
```json
{
  "query": "mutation { loginEmployee(username: \"sandeep\", password: \"your_password\") { success message employee { id emp_code full_name email status branch department designation photo_url } } }"
}
```

#### Option 2: Graph Operation Request (REST-like Graph)
```json
{
  "operation": "loginEmployee",
  "variables": {
    "username": "sandeep",
    "password": "your_password"
  }
}
```

#### 📤 Graph Success Response (`200 OK`)
```json
{
  "data": {
    "loginEmployee": {
      "success": true,
      "message": "Authentication successful for Sandeep Kumar",
      "employee": {
        "id": 1,
        "emp_code": "EMP1236",
        "username": "sandeep",
        "full_name": "Sandeep Kumar",
        "email": "deep@gmail.com",
        "phone": "+123456987",
        "status": "ACTIVE",
        "branch": "Headquarters",
        "department": "Finance",
        "designation": "Accountant",
        "photo_url": "/captured_photos/EMP1236.jpg"
      }
    }
  }
}
```

---

### 🔹 Graph Operation B: `getEmployee`

#### Request Payload
```json
{
  "operation": "getEmployee",
  "variables": {
    "id": 1
  }
}
```

#### 📤 Response Payload
```json
{
  "data": {
    "employee": {
      "id": 1,
      "emp_code": "EMP1236",
      "username": "sandeep",
      "full_name": "Sandeep Kumar",
      "email": "deep@gmail.com",
      "phone": "+123456987",
      "status": "ACTIVE",
      "branch_name": "Headquarters",
      "department_name": "Finance",
      "designation_name": "Accountant"
    }
  }
}
```

---

### 🔹 Graph Operation C: `listEmployees`

#### Request Payload
```json
{
  "operation": "listEmployees"
}
```

#### 📤 Response Payload
```json
{
  "data": {
    "employees": [
      {
        "id": 1,
        "emp_code": "EMP1236",
        "username": "sandeep",
        "full_name": "Sandeep Kumar",
        "status": "ACTIVE",
        "branch_name": "Headquarters",
        "department_name": "Finance",
        "designation_name": "Accountant"
      }
    ]
  }
}
```

---

## 📷 3. Biometrics & Attendance API

### Endpoint: Scan Facial Attendance
Receives a base64 camera image frame, matches it against stored SFace 128D encodings in MySQL, and logs attendance.

- **URL**: `/api/scan_attendance`
- **Method**: `POST`
- **Headers**: `Content-Type: application/json`

#### Request Payload
```json
{
  "photo": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQ..."
}
```

#### Response Payload (`200 OK`)
```json
{
  "status": "success",
  "message": "Attendance marked successfully!",
  "employee": {
    "emp_code": "EMP1236",
    "full_name": "Sandeep Kumar",
    "department": "Finance",
    "designation": "Accountant",
    "branch": "Headquarters",
    "in_time": "16:05:22",
    "similarity_score": 0.94
  }
}
```

---

## 🏢 4. System Metadata API

### Endpoint: Fetch Organizational Metadata
Returns available branches, departments, and designations.

- **URL**: `/api/metadata`
- **Method**: `GET`

#### Response Payload (`200 OK`)
```json
{
  "branches": [
    { "id": 1, "branch_name": "Headquarters", "branch_code": "HQ-01" }
  ],
  "departments": [
    { "id": 1, "department_name": "Finance" }
  ],
  "designations": [
    { "id": 1, "designation_name": "Accountant" }
  ]
}
```

---

## 🛠 Code Usage Examples

### 💻 cURL Example (Employee Login REST API)
```bash
curl -X POST http://localhost:5000/api/v1/employee/login \
  -H "Content-Type: application/json" \
  -d '{"username": "sandeep", "password": "your_password"}'
```

### 🟨 JavaScript Fetch Example (Graph API Login)
```javascript
const response = await fetch('http://localhost:5000/api/graph', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    operation: 'loginEmployee',
    variables: {
      username: 'sandeep',
      password: 'your_password'
    }
  })
});

const result = await response.json();
console.log(result.data.loginEmployee);
```

### 🐍 Python Requests Example
```python
import requests

url = "http://localhost:5000/api/v1/employee/login"
payload = {
    "username": "sandeep",
    "password": "your_password"
}

response = requests.post(url, json=payload)
data = response.json()
print("Auth Token:", data.get("auth_token"))
print("Employee Name:", data.get("employee", {}).get("full_name"))
```
