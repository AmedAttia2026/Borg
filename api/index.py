import os
import io
import base64
from flask import Flask, render_template, request, jsonify, session, redirect
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from datetime import datetime
import pytz

from PIL import Image

import cloudinary
import cloudinary.uploader

app = Flask(__name__, template_folder='../templates')
app.secret_key = "Borg_Elarab_REALESTATE_VIP_2026_Secure"

cloudinary.config(
    cloud_name = "dshnysbzh",
    api_key = "962171128643913",
    api_secret = "ba-zKbXYNyw-qpkO4dKFFroVZOA", 
    secure = True
)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["500 per day", "100 per hour"],
    storage_uri="memory://"
)

MONGO_URI = "mongodb+srv://AmedAttia:01025816353aA@cluster0.tz66w.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client['borg_elarab_realestate']

users_col = db['users']
neighborhoods_col = db['neighborhoods']
properties_col = db['properties']
leads_col = db['leads']

def get_time():
    tz = pytz.timezone('Africa/Cairo')
    return datetime.now(tz).strftime('%Y-%m-%d %I:%M %p')

def convert_base64_to_jpeg_bytes(base64_str):
    try:
        if "," in base64_str:
            base64_str = base64_str.split(",")[1]
        img_data = base64.b64decode(base64_str)
        img = Image.open(io.BytesIO(img_data))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        out_buf = io.BytesIO()
        img.save(out_buf, format="JPEG", quality=85)
        return out_buf.getvalue()
    except Exception as e:
        print(f"❌ Error converting image: {str(e)}")
        return None

def init_system_realestate():
    if neighborhoods_col.count_documents({}) == 0:
        neighborhoods_col.insert_many([
            {"id": "DISTRICT_2", "name": "الحي الثاني"},
            {"id": "DISTRICT_3", "name": "الحي الثالث"}
        ])
    
    users_col.delete_many({"username": "admin"})
    users_col.insert_one({
        "username": "admin",
        "password": generate_password_hash("123"),
        "name": "المدير العام",
        "role": "super_admin",
        "total_sales_tracked": 0
    })

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin_panel():
    if 'user' not in session:
        return redirect('/')
    return render_template('admin.html')

@app.route('/api/data', methods=['GET'])
def get_dashboard_data():
    neighborhoods = list(neighborhoods_col.find({}, {"_id": 0}))
    properties = list(properties_col.find({}, {"_id": 0}))
    leads = list(leads_col.find({}, {"_id": 0}))
    
    return jsonify({
        "neighborhoods": neighborhoods,
        "properties": properties,
        "leads": leads
    })

@app.route('/api/auth', methods=['POST'])
def handle_auth():
    data = request.get_json()
    action = data.get('action')
    
    if action == 'login':
        user = users_col.find_one({"username": data['username']})
        if user and check_password_hash(user['password'], data['password']):
            session['user'] = {
                "username": user['username'],
                "name": user['name'],
                "role": user['role']
            }
            return jsonify({"status": "success", "user": session['user']})
        return jsonify({"status": "error", "message": "بيانات الدخول غير صحيحة"}), 401
        
    elif action == 'logout':
        session.pop('user', None)
        return jsonify({"status": "success"})

@app.route('/api/action', methods=['POST'])
def handle_action():
    if request.path.startswith('/api/action') and request.method == 'POST':
        pass
        
    data = request.get_json()
    action = data.get('action')
    
    if action == 'new_lead':
        lead = data['lead']
        leads_col.insert_one({
            "leadId": lead['leadId'],
            "propertyTitle": lead['propertyTitle'],
            "price": lead['price'],
            "clientName": lead['clientName'],
            "clientPhone": lead['clientPhone'],
            "status": "pending",
            "created_at": get_time()
        })
        return jsonify({"status": "success"})
        
    if 'user' not in session:
        return jsonify({"status": "error", "message": "غير مصرح به"}), 403
        
    curr = session['user']
    
    if action == 'complete_lead':
        leads_col.update_one({"leadId": data['leadId']}, {"$set": {"status": "completed"}})
        users_col.update_one({"username": curr['username']}, {"$inc": {"total_sales_tracked": 1}})
        
    elif action == 'property_manage':
        if data['sub'] == 'add':
            prop = data['property']
            try:
                main_bytes = convert_base64_to_jpeg_bytes(prop['image'])
                if not main_bytes:
                    return jsonify({"status": "error", "message": "الصورة الرئيسية تالفة"}), 400
                
                up_main = cloudinary.uploader.upload(main_bytes, folder="borg_elarab_properties")
                main_cloud_url = up_main.get("secure_url")
                
                uploaded_gallery_urls = []
                if 'images_gallery' in prop and isinstance(prop['images_gallery'], list):
                    for img_base64 in prop['images_gallery']:
                        gal_bytes = convert_base64_to_jpeg_bytes(img_base64)
                        if gal_bytes:
                            up_gal = cloudinary.uploader.upload(gal_bytes, folder="borg_elarab_properties")
                            uploaded_gallery_urls.append(up_gal.get("secure_url"))

                properties_col.insert_one({
                    "id": prop['id'],
                    "neighborhoodId": prop['neighborhoodId'],
                    "title": prop['title'],
                    "price": prop['price'],
                    "area": prop['area'],
                    "beds": prop['beds'],
                    "image": main_cloud_url,
                    "images_gallery": uploaded_gallery_urls,
                    "added_by": curr['name'],
                    "created_at": get_time()
                })
                return jsonify({"status": "success"})
                
            except Exception as e:
                print(f"❌ Cloudinary Runtime Error: {str(e)}")
                return jsonify({"status": "error", "message": f"خطأ ميديا: {str(e)}"}), 500
            
        elif data['sub'] == 'delete':
            properties_col.delete_one({"id": data['id']})
                    
    elif action == 'delete_lead':
        leads_col.delete_one({"leadId": data['leadId']})
    
    return jsonify({"status": "success"})

if __name__ == '__main__':
    init_system_realestate()
    app.run(host='0.0.0.0', port=8080)
