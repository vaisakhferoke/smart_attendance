import mysql.connector

def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host="localhost", # http://localhost:8090/ മാറ്റുക
            user="root",        # XAMPP ലെ default username
            password="",        # നിങ്ങളുടെ MySQL password ഉണ്ടെങ്കിൽ ഇവിടെ നൽകുക
            database="attendance_db"
        )
        return connection
    except mysql.connector.Error as err:
        print(f"❌ Database Connection Error: {err}")
        return None

# കണക്ഷൻ ടെസ്റ്റ് ചെയ്യാൻ
if __name__ == "__main__":
    conn = get_db_connection()
    if conn and conn.is_connected():
        print("✅ MySQL Database Connected Successfully!")
        conn.close()