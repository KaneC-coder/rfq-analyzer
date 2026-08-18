"""
RFQ智能报价助手 - Web应用
"""

import os
import json
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from PIL import Image
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'rfq-analyzer-secret-key-2026')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rfq_analyzer.db'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

db = SQLAlchemy(app)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('outputs', exist_ok=True)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(50), unique=True, nullable=False)
    free_count = db.Column(db.Integer, default=3)
    total_used = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used_at = db.Column(db.DateTime, default=datetime.utcnow)

class AnalysisRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    image_path = db.Column(db.String(255), nullable=False)
    product_info = db.Column(db.Text)
    report_path = db.Column(db.String(255))
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

def get_or_create_user(ip_address):
    user = User.query.filter_by(ip_address=ip_address).first()
    if not user:
        user = User(ip_address=ip_address, free_count=3)
        db.session.add(user)
        db.session.commit()
    return user

def check_usage_limit(user):
    if user.free_count > 0:
        return True, f"免费次数剩余：{user.free_count}次"
    return False, "免费次数已用完，请付费继续使用（0.5元/次）"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({'error': '没有上传文件'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '文件名为空'}), 400
    if not file.filename.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
        return jsonify({'error': '只支持JPG、PNG、WEBP格式'}), 400
    filename = f"{uuid.uuid4().hex}{os.path.splitext(file.filename)[1]}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    ip = request.remote_addr
    user = get_or_create_user(ip)
    can_use, message = check_usage_limit(user)
    if not can_use:
        return jsonify({'error': message, 'need_payment': True}), 402
    record = AnalysisRecord(user_id=user.id, image_path=filepath, status='processing')
    db.session.add(record)
    db.session.commit()
    return jsonify({'success': True, 'record_id': record.id, 'message': message, 'free_count': user.free_count})

@app.route('/api/analyze/<int:record_id>', methods=['POST'])
def analyze(record_id):
    record = AnalysisRecord.query.get_or_404(record_id)
    user = User.query.get(record.user_id)
    can_use, message = check_usage_limit(user)
    if not can_use:
        return jsonify({'error': message, 'need_payment': True}), 402
    try:
        product_info = {
            'product_name': '识别到的产品名称',
            'quantity': '数量',
            'buyer_country': '买家国家',
            'specifications': '规格参数'
        }
        record.product_info = json.dumps(product_info, ensure_ascii=False)
        record.status = 'completed'
        user.free_count -= 1
        user.total_used += 1
        user.last_used_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True, 'product_info': product_info, 'free_count': user.free_count})
    except Exception as e:
        record.status = 'failed'
        db.session.commit()
        return jsonify({'error': str(e)}), 500

@app.route('/api/report/<int:record_id>', methods=['POST'])
def generate_report(record_id):
    record = AnalysisRecord.query.get_or_404(record_id)
    if record.status != 'completed':
        return jsonify({'error': '分析未完成'}), 400
    try:
        product_info = json.loads(record.product_info) if record.product_info else {}
        doc = Document()
        title = doc.add_heading('RFQ报价分析报告', 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_heading('1. 买家信息', level=1)
        doc.add_paragraph(f"买家国家：{product_info.get('buyer_country', '未知')}")
        doc.add_heading('2. 产品需求', level=1)
        doc.add_paragraph(f"产品名称：{product_info.get('product_name', '未知')}")
        doc.add_paragraph(f"数量：{product_info.get('quantity', '未知')}")
        doc.add_paragraph(f"规格：{product_info.get('specifications', '未知')}")
        report_filename = f"RFQ_Report_{record.id}.docx"
        report_path = os.path.join('outputs', report_filename)
        doc.save(report_path)
        record.report_path = report_path
        db.session.commit()
        return jsonify({'success': True, 'report_path': report_path})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download/<int:record_id>')
def download_report(record_id):
    record = AnalysisRecord.query.get_or_404(record_id)
    if not record.report_path:
        return jsonify({'error': '报告未生成'}), 404
    return send_from_directory('outputs', os.path.basename(record.report_path), as_attachment=True)

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
