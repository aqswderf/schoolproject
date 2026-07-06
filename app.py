from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import uuid
import qrcode
from io import BytesIO
import base64

app = Flask(__name__)

# Конфигурация БД
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///students.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key-change-this'

db = SQLAlchemy(app)

# ============ МОДЕЛЬ УЧЕНИКА ============
class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(36), unique=True, nullable=False)
    fullname = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    grade = db.Column(db.String(10), nullable=False)
    qr_code = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'fullname': self.fullname,
            'email': self.email,
            'phone': self.phone,
            'grade': self.grade,
            'created_at': self.created_at.isoformat()
        }

# ============ МОДЕЛЬ СКАНИРОВАНИЯ QR-КОДА ============
class QRScan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(36), db.ForeignKey('student.student_id'), nullable=False)
    scanned_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'scanned_at': self.scanned_at.isoformat()
        }

# ============ СОЗДАНИЕ ТАБЛИЦ ============
with app.app_context():
    db.create_all()

# ============ МАРШРУТЫ (PAGES) ============
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register')
def register():
    return render_template('register.html')

@app.route('/scan')
def scan():
    return render_template('scan.html')

# ============ API ============

def generate_qr_code(data):
    """Генерирует QR-код и возвращает его в формате base64"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/png;base64,{img_str}"

# API Регистрация
@app.route('/api/register', methods=['POST'])
def api_register():
    try:
        data = request.get_json()
        
        if not all(k in data for k in ['fullname', 'email', 'phone', 'grade']):
            return jsonify({'message': 'Все поля обязательны'}), 400
        
        if Student.query.filter_by(email=data['email']).first():
            return jsonify({'message': 'Email уже зарегистрирован'}), 400
        
        if Student.query.filter_by(phone=data['phone']).first():
            return jsonify({'message': 'Номер телефона уже зарегистрирован'}), 400
        
        student_id = str(uuid.uuid4())
        qr_code = generate_qr_code(student_id)
        
        new_student = Student(
            student_id=student_id,
            fullname=data['fullname'],
            email=data['email'],
            phone=data['phone'],
            grade=data['grade'],
            qr_code=qr_code
        )
        
        db.session.add(new_student)
        db.session.commit()
        
        return jsonify({
            'message': 'Регистрация успешна!',
            'student': new_student.to_dict(),
            'qr_code': qr_code
        }), 201
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': f'Ошибка сервера: {str(e)}'}), 500

# API Получение студента по ID
@app.route('/api/student/<student_id>', methods=['GET'])
def api_get_student(student_id):
    try:
        student = Student.query.filter_by(student_id=student_id).first()
        
        if not student:
            return jsonify({'message': 'Ученик не найден'}), 404
        
        return jsonify(student.to_dict()), 200
    
    except Exception as e:
        return jsonify({'message': f'Ошибка сервера: {str(e)}'}), 500

# API Сканирование QR-кода
@app.route('/api/scan-qr', methods=['POST'])
def api_scan_qr():
    try:
        data = request.get_json()
        student_id = data.get('student_id')
        
        if not student_id:
            return jsonify({'message': 'ID ученика обязателен'}), 400
        
        # Проверяем существует ли такой ученик
        student = Student.query.filter_by(student_id=student_id).first()
        
        if not student:
            return jsonify({'message': 'Ученик не найден'}), 404
        
        # Создаём запись о сканировании
        scan = QRScan(student_id=student_id)
        db.session.add(scan)
        db.session.commit()
        
        return jsonify({
            'message': f'✅ QR-код отсканирован! Привет, {student.fullname}!',
            'student': student.to_dict(),
            'scan': scan.to_dict()
        }), 200
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': f'Ошибка сервера: {str(e)}'}), 500

# API История сканирований студента
@app.route('/api/scans/<student_id>', methods=['GET'])
def api_get_scans(student_id):
    try:
        scans = QRScan.query.filter_by(student_id=student_id).all()
        
        return jsonify({
            'student_id': student_id,
            'scans_count': len(scans),
            'scans': [s.to_dict() for s in scans]
        }), 200
    
    except Exception as e:
        return jsonify({'message': f'Ошибка сервера: {str(e)}'}), 500

# API Все студенты
@app.route('/api/students', methods=['GET'])
def api_students():
    try:
        students = Student.query.all()
        return jsonify([s.to_dict() for s in students]), 200
    
    except Exception as e:
        return jsonify({'message': f'Ошибка сервера: {str(e)}'}), 500

# API Статистика сканирований
@app.route('/api/stats', methods=['GET'])
def api_stats():
    try:
        total_students = Student.query.count()
        total_scans = QRScan.query.count()
        
        # Студенты, которые сканировали QR
        scanned_students = db.session.query(QRScan.student_id).distinct().count()
        
        # Топ сканируемые студенты
        top_scans = db.session.query(
            QRScan.student_id, 
            db.func.count(QRScan.id).label('count')
        ).group_by(QRScan.student_id).order_by(db.func.count(QRScan.id).desc()).limit(5).all()
        
        top_list = []
        for student_id, count in top_scans:
            student = Student.query.filter_by(student_id=student_id).first()
            if student:
                top_list.append({
                    'name': student.fullname,
                    'scans': count
                })
        
        return jsonify({
            'total_students': total_students,
            'total_scans': total_scans,
            'scanned_students': scanned_students,
            'top_scanned': top_list
        }), 200
    
    except Exception as e:
        return jsonify({'message': f'Ошибка сервера: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)