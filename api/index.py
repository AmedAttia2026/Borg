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

# استيراد مكتبة Pillow لمعالجة وتحويل كافة امتدادات الصور
from PIL import Image

# استيراد مكتبات Cloudinary الرسمية
import cloudinary
import cloudinary.uploader

# تعيين مسار مجلد القوالب للخروج خطوة للخلف للوصول للجذر (Root) من داخل مجلد api
app = Flask(__name__, template_folder='../templates')
app.secret_key = "Borg_Elarab_REALESTATE_VIP_2026_Secure"

# تكوين مفاتيح حسابك من Cloudinary
cloudinary.config(
    cloud_name = "dshnysbzh",
    api_key = "962171128643913",
    api_secret = "ba-zKbXYNyw-qpkO4dKFFroVZOA", 
    secure = True
)

# تفعيل نظام الحماية من إغراق السيرفر
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["500 per day", "100 per hour"],
    storage_uri="memory://"
)

# الاتصال بقاعدة بيانات مونجو أطلس
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

# تحويل أي امتداد صورة قادم (Base64) هيدروليكياً إلى JPEG قياسي عالي النقاء
def convert_base64_to_jpeg_bytes(base64_str):
    try:
        if "," in base64_str:
            base64_str = base64_str.split(",")[1]
        img_data = base64.b64decode(base64_str)
        img = Image.open(io.BytesIO(img_data))
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        out_buf = io.BytesIO()
        img.save(out_buf, format="JPEG", quality=85)
        return out_buf.getvalue()
    except Exception as e:
        print(f"❌ Error converting image: {str(e)}")
        return None

# دالة تهيئة النظام الافتراضية
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

# --- الروابط والمسارات (Routes) ---

@app.route('/')
def index():
    return render_template('index.html')

# فتح صفحة الـ admin مباشرة دون توجيه داخلي لمنع الـ Loop على سيرفر Vercel
@app.route('/admin')
def admin_page():
    return render_template('admin.html')

@app.route('/admin-login', methods=['POST'])
def login():
    username = str(request.json.get('username', '')).strip()
    password = str(request.json.get('password', '')).strip()
    user = users_col.find_one({"username": username})
    if user and check_password_hash(user['password'], password):
        session['user'] = {"username": user['username'], "role": user['role'], "name": user['name']}
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "بيانات الدخول العقارية غير صحيحة"}), 401

@app.route('/admin-logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/api/data')
def get_data():
    neighborhoods = list(neighborhoods_col.find({}, {"_id": 0}))
    properties = list(properties_col.find({}, {"_id": 0}))
    
    if 'user' in session:
        all_leads = list(leads_col.find({}, {"_id": 0}))
        completed_leads = [l for l in all_leads if l.get('status') == 'completed']
        
        # دالة حماية لاحتساب الأسعار بأمان
        def get_float(v):
            try: return float(str(v).replace(',', '').split()[0]) if v else 0.0
            except: return 0.0

        stats = {
            "totalVolume": sum([get_float(l.get('price', 0)) for l in completed_leads]),
            "todayLeads": len(all_leads),
            "pendingCount": len([l for l in all_leads if l.get('status') == 'pending'])
        }
        return jsonify({"neighborhoods": neighborhoods, "properties": properties, "leads": all_leads, "stats": stats, "currentUser": session['user']})
    
    return jsonify({"neighborhoods": neighborhoods, "properties": properties})

@app.route('/api/action', methods=['POST'])
def handle_action():
    data = request.json
    action = data.get('action')
    
    if action == 'new_lead':
        lead_data = data['lead']
        leads_col.insert_one({
            "leadId": lead_data['leadId'],
            "propertyTitle": lead_data['propertyTitle'],
            "price": lead_data['price'],
            "clientName": lead_data['clientName'],
            "clientPhone": lead_data['clientPhone'],
            "date": get_time(),
            "status": "pending",
            "handled_by": ""
        })
        return jsonify({"status": "success"})
    
    if 'user' not in session: 
        return jsonify({"status": "unauthorized"}), 403
        
    curr = session['user']
    
    if action == 'complete_lead':
        leads_col.update_one({"leadId": data['leadId']}, {"$set": {"status": "completed", "handled_by": curr['name'], "handled_at": get_time()}})
        users_col.update_one({"username": curr['username']}, {"$inc": {"total_sales_tracked": 1}})
            
    elif action == 'manage_property':
        if data['sub'] == 'add':
            try:
                prop = data['property']
                main_cloud_url = ""
                if prop.get('image'):
                    img_bytes = convert_base64_to_jpeg_bytes(prop['image'])
                    if img_bytes:
                        up_main = cloudinary.uploader.upload(img_bytes, folder="borg_elarab_properties")
                        main_cloud_url = up_main.get("secure_url")

                uploaded_gallery_urls = []
                if prop.get('images_gallery') and len(prop['images_gallery']) > 0:
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
                return jsonify({"status": "error", "message": f"خطأ ميديا: {str(e)}"}), 500
            
        elif data['sub'] == 'delete':
            properties_col.delete_one({"id": data['id']})
                    
    elif action == 'delete_lead':
        leads_col.delete_one({"leadId": data['leadId']})
    
    return jsonify({"status": "success"})

# حصر تشغيل الدالة التلقائي للمحلي فقط لمنع حظر خوادم Vercel
if __name__ == '__main__':
    init_system_realestate()
    app.run(host='0.0.0.0', port=8080)
