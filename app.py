"""
RFQ智能报价助手 - Web应用（简化版，兼容Vercel）
"""

import os
import json
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_from_directory
from PIL import Image
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'rfq-analyzer-secret-key-2026')
app.config['UPLOAD_FOLDER'] = '/tmp/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# 确保目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('/tmp/outputs', exist_ok=True)

# 使用JSON文件代替数据库
DATA_FILE = '/tmp/users.json'
RECORDS_FILE = '/tmp/records.json'

def load_data(filepath):
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_data(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)

def get_or_create_user(ip_address):
    users = load_data(DATA_FILE)
    if ip_address not in users:
        users[ip_address] = {'free_count': 3, 'total_used': 0, 'created_at': datetime.now().isoformat()}
        save_data(DATA_FILE, users)
    return users[ip_address]

def save_record(record_id, record_data):
    records = load_data(RECORDS_FILE)
    records[str(record_id)] = record_data
    save_data(RECORDS_FILE, records)

def get_record(record_id):
    records = load_data(RECORDS_FILE)
    return records.get(str(record_id))

def update_record(record_id, updates):
    records = load_data(RECORDS_FILE)
    if str(record_id) in records:
        records[str(record_id)].update(updates)
        save_data(RECORDS_FILE, records)

def check_usage_limit(user):
    if user['free_count'] > 0:
        return True, f"免费次数剩余：{user['free_count']}次"
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

    record_id = uuid.uuid4().hex
    record_data = {
        'record_id': record_id,
        'user_ip': ip,
        'image_path': filepath,
        'status': 'processing',
        'product_info': None,
        'report_path': None,
        'created_at': datetime.now().isoformat()
    }
    save_record(record_id, record_data)

    return jsonify({
        'success': True,
        'record_id': record_id,
        'message': message,
        'free_count': user['free_count']
    })

@app.route('/api/analyze/<record_id>', methods=['POST'])
def analyze(record_id):
    record = get_record(record_id)
    if not record:
        return jsonify({'error': '记录不存在'}), 404

    users = load_data(DATA_FILE)
    user = users.get(record['user_ip'])
    if not user:
        return jsonify({'error': '用户不存在'}), 404

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
        update_record(record_id, {'product_info': product_info, 'status': 'completed'})
        user['free_count'] -= 1
        user['total_used'] += 1
        users[record['user_ip']] = user
        save_data(DATA_FILE, users)

        return jsonify({'success': True, 'product_info': product_info, 'free_count': user['free_count']})
    except Exception as e:
        update_record(record_id, {'status': 'failed'})
        return jsonify({'error': str(e)}), 500

@app.route('/api/report/<record_id>', methods=['POST'])
def generate_report(record_id):
    record = get_record(record_id)
    if not record or record['status'] != 'completed':
        return jsonify({'error': '分析未完成'}), 400

    try:
        product_info = record.get('product_info', {})
        doc = Document()
        title = doc.add_heading('RFQ报价分析报告', 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_heading('1. 买家信息', level=1)
        doc.add_paragraph(f"买家国家：{product_info.get('buyer_country', '未知')}")
        doc.add_heading('2. 产品需求', level=1)
        doc.add_paragraph(f"产品名称：{product_info.get('product_name', '未知')}")
        doc.add_paragraph(f"数量：{product_info.get('quantity', '未知')}")
        doc.add_paragraph(f"规格：{product_info.get('specifications', '未知')}")

        report_filename = f"RFQ_Report_{record_id}.docx"
        report_path = os.path.join('/tmp/outputs', report_filename)
        doc.save(report_path)
        update_record(record_id, {'report_path': report_path})

        return jsonify({'success': True, 'report_path': report_path})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download/<record_id>')
def download_report(record_id):
    record = get_record(record_id)
    if not record or not record.get('report_path'):
        return jsonify({'error': '报告未生成'}), 404
    return send_from_directory('/tmp/outputs', os.path.basename(record['report_path']), as_attachment=True)

# Vercel 部署入口
def handler(request, response):
    return app(request, response)
