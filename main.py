from flask import Flask, render_template, request, jsonify
import paho.mqtt.client as mqtt
import mysql.connector
import json
from datetime import datetime

app = Flask(__name__)

# Cấu hình MQTT (TLS, port 8883, user/pass)
MQTT_BROKER = "f03f9ea0745245ce996d7f35c388d455.s1.eu.hivemq.cloud"  # Địa chỉ broker của bạn
MQTT_PORT = 8883  # Port TLS chuẩn của MQTT
MQTT_USER = "ngtuananh24"  # Thay username broker MQTT
MQTT_PASS = "Anh2407@"  # Thay password broker MQTT
MQTT_TOPIC_DOOR = "door/control"
MQTT_TOPIC_FINGERPRINT = "fingerprint/control"

# Cấu hình MySQL
MYSQL_CONFIG = {
    'host': 'qlybaido.duckdns.org',
    'user': 'admin',
    'password': 'admin',  # Thay password DB
    'database': 'door_control'
}

mqtt_client = mqtt.Client()

def connect_mqtt():
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("Kết nối MQTT thành công!")
        else:
            print(f"Kết nối MQTT thất bại! Code: {rc}")

    mqtt_client.on_connect = on_connect
    mqtt_client.tls_set()
    mqtt_client.tls_insecure_set(True)
    mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_start()


def get_db_connection():
    return mysql.connector.connect(**MYSQL_CONFIG)


def init_database():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS door_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                action VARCHAR(50) NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                method VARCHAR(20) DEFAULT 'manual'
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fingerprints (
                id INT AUTO_INCREMENT PRIMARY KEY,
                fingerprint_id INT UNIQUE,
                name VARCHAR(100),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        cursor.close()
        conn.close()
        print("Database khởi tạo thành công!")
    except Exception as e:
        print(f"Lỗi khởi tạo database: {e}")


def log_door_action(action, method="manual"):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO door_history (action, method) VALUES (%s, %s)",
            (action, method)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Lỗi ghi log: {e}")


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/door/open', methods=['POST'])
def open_door():
    try:
        mqtt_client.publish(MQTT_TOPIC_DOOR, "1")
        log_door_action("Mở cửa", "web")
        return jsonify({"status": "success", "message": "Đã gửi lệnh mở cửa"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route('/door/close', methods=['POST'])
def close_door():
    try:
        mqtt_client.publish(MQTT_TOPIC_DOOR, "0")
        log_door_action("Đóng cửa", "web")
        return jsonify({"status": "success", "message": "Đã gửi lệnh đóng cửa"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route('/fingerprint/add', methods=['POST'])
def add_fingerprint():
    try:
        data = request.get_json()
        fingerprint_id = data.get('fingerprint_id')
        name = data.get('name', f'Vân tay {fingerprint_id}')

        mqtt_message = json.dumps({
            "action": "add",
            "fingerprint_id": fingerprint_id,
            "name": name
        })
        mqtt_client.publish(MQTT_TOPIC_FINGERPRINT, mqtt_message)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO fingerprints (fingerprint_id, name) VALUES (%s, %s) ON DUPLICATE KEY UPDATE name = %s",
            (fingerprint_id, name, name)
        )
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"status": "success", "message": "Đã thêm vân tay"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route('/fingerprint/delete', methods=['POST'])
def delete_fingerprint():
    try:
        data = request.get_json()
        fingerprint_id = data.get('fingerprint_id')

        mqtt_message = json.dumps({
            "action": "delete",
            "fingerprint_id": fingerprint_id
        })
        mqtt_client.publish(MQTT_TOPIC_FINGERPRINT, mqtt_message)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM fingerprints WHERE fingerprint_id = %s", (fingerprint_id,))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"status": "success", "message": "Đã xóa vân tay"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route('/fingerprints')
def get_fingerprints():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM fingerprints ORDER BY created_at DESC")
        fingerprints = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(fingerprints)
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/history')
def get_history():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM door_history ORDER BY timestamp DESC LIMIT 50")
        history = cursor.fetchall()
        cursor.close()
        conn.close()

        for record in history:
            record['timestamp'] = record['timestamp'].strftime('%d/%m/%Y %H:%M:%S')

        return jsonify(history)
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/history/clear', methods=['POST'])
def clear_history():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM door_history")
        deleted_count = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "status": "success",
            "message": f"Đã xóa {deleted_count} bản ghi lịch sử"
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route('/history/delete/<int:record_id>', methods=['POST'])
def delete_history_record(record_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM door_history WHERE id = %s", (record_id,))

        if cursor.rowcount == 0:
            return jsonify({"status": "error", "message": "Không tìm thấy bản ghi"})

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "status": "success",
            "message": "Đã xóa bản ghi lịch sử"
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


if __name__ == '__main__':
    init_database()
    connect_mqtt()
    app.run(debug=False, host='0.0.0.0', port=5000)
