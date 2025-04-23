from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_cors import CORS
import json
import uuid
import os
from datetime import datetime
import hashlib
import sqlite3
from functools import wraps
from pymongo import MongoClient
from bson import ObjectId
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)
app.secret_key = 'caresync_secret_key'  # For session management

# MongoDB Configuration
try:
    MONGO_URI = "mongodb://localhost:27017/"
    logger.info("Attempting to connect to MongoDB...")
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    # Test the connection
    mongo_client.server_info()
    db = mongo_client['caresync_db']
    logger.info("Successfully connected to MongoDB")
except Exception as e:
    logger.error(f"Error connecting to MongoDB: {str(e)}")
    db = None
    # Don't raise the exception, let the app start and handle DB errors gracefully

# Function to get clinic-specific collection
def get_clinic_collection(clinic_id):
    try:
        if not mongo_client:
            logger.error("MongoDB client is not initialized")
            raise Exception("MongoDB connection not available")
        return db[f'clinic_{clinic_id}_patients']
    except Exception as e:
        logger.error(f"Error getting clinic collection: {str(e)}")
        raise Exception("Failed to access database")

# Function to initialize clinic collection if it doesn't exist
def init_clinic_collection(clinic_id):
    try:
        if not mongo_client:
            logger.error("MongoDB client is not initialized")
            raise Exception("MongoDB connection not available")
        collection = get_clinic_collection(clinic_id)
        if not collection.find_one():
            collection.create_index([("patient_id", 1)], unique=True)
        return collection
    except Exception as e:
        logger.error(f"Error initializing clinic collection: {str(e)}")
        raise Exception("Failed to initialize database")

# Database setup
def init_db():
    """Initialize the SQLite database with required tables"""
    conn = sqlite3.connect('caresync.db')
    c = conn.cursor()
    
    # Create users table for authentication
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create nursing_homes table
    c.execute('''
        CREATE TABLE IF NOT EXISTS nursing_homes (
            clinic_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            location TEXT NOT NULL,
            contact_person TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create hospitals table
    c.execute('''
        CREATE TABLE IF NOT EXISTS hospitals (
            hospital_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            location TEXT NOT NULL,
            contact_number TEXT NOT NULL,
            total_beds INTEGER NOT NULL,
            available_beds INTEGER NOT NULL,
            icu_total INTEGER NOT NULL,
            icu_available INTEGER NOT NULL,
            specialties TEXT NOT NULL,
            ambulance_services BOOLEAN NOT NULL,
            mental_health_support BOOLEAN NOT NULL,
            financial_assistance BOOLEAN NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create patients table
    c.execute('''
        CREATE TABLE IF NOT EXISTS patients (
            patient_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            age INTEGER NOT NULL,
            gender TEXT NOT NULL,
            contact_number TEXT NOT NULL,
            address TEXT NOT NULL,
            medical_history TEXT NOT NULL,
            current_status TEXT NOT NULL,
            assigned_hospital_id TEXT,
            referred_by TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (referred_by) REFERENCES nursing_homes(clinic_id),
            FOREIGN KEY (assigned_hospital_id) REFERENCES hospitals(hospital_id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Initialize database
init_db()

# Load healthcare data
try:
    # Create data directory if it doesn't exist
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    os.makedirs(data_dir, exist_ok=True)
    
    json_path = os.path.join(data_dir, 'caresync_updated_seed_data.json')
    # Create the file if it doesn't exist
    if not os.path.exists(json_path):
        initial_data = {
            'patients': [],
            'ambulance_requests': [],
            'pros': [],
            'multispeciality_hospitals': [],
            'nursing_homes': [],
            'counseling_resources': []
        }
        with open(json_path, 'w') as file:
            json.dump(initial_data, file, indent=4)
        healthcare_data = initial_data
    else:
        with open(json_path, 'r') as file:
            healthcare_data = json.load(file)
except FileNotFoundError:
    logger.error("caresync_updated_seed_data.json not found and could not be created")
    healthcare_data = {
        'patients': [],
        'ambulance_requests': [],
        'pros': [],
        'multispeciality_hospitals': [],
        'nursing_homes': [],
        'counseling_resources': []
    }
except json.JSONDecodeError:
    logger.error("caresync_updated_seed_data.json is not valid JSON")
    healthcare_data = {
        'patients': [],
        'ambulance_requests': [],
        'pros': [],
        'multispeciality_hospitals': [],
        'nursing_homes': [],
        'counseling_resources': []
    }
except Exception as e:
    logger.error(f"Error loading healthcare data: {str(e)}")
    healthcare_data = {
        'patients': [],
        'ambulance_requests': [],
        'pros': [],
        'multispeciality_hospitals': [],
        'nursing_homes': [],
        'counseling_resources': []
    }

def save_healthcare_data():
    """Save the healthcare data back to the JSON file"""
    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        
        # Create a backup of the existing file if it exists
        if os.path.exists(json_path):
            backup_path = f"{json_path}.backup"
            try:
                import shutil
                shutil.copy2(json_path, backup_path)
            except Exception as e:
                logger.warning(f"Failed to create backup: {e}")
        
        # Write the new data with proper permissions
        temp_path = f"{json_path}.temp"
        with open(temp_path, 'w') as file:
            json.dump(healthcare_data, file, indent=4)
        
        # Verify the temp file was written correctly
        if not os.path.exists(temp_path):
            raise Exception("Temporary file was not created successfully")
            
        # Try to read it back to verify it's valid JSON
        with open(temp_path, 'r') as file:
            json.load(file)
        
        # If verification passed, replace the original file
        if os.path.exists(json_path):
            os.remove(json_path)
        os.rename(temp_path, json_path)
            
        logger.info("Successfully saved healthcare data")
        return True
    except Exception as e:
        logger.error(f"Error saving healthcare data: {e}")
        # Try to restore from backup if available
        if os.path.exists(f"{json_path}.backup"):
            try:
                import shutil
                shutil.copy2(f"{json_path}.backup", json_path)
                logger.info("Restored from backup after failed save")
            except Exception as backup_error:
                logger.error(f"Failed to restore from backup: {backup_error}")
        return False

# Initialize session data if not exists
def init_session_data():
    if 'patients' not in session:
        session['patients'] = healthcare_data['patients']
    if 'ambulance_requests' not in session:
        session['ambulance_requests'] = healthcare_data['ambulance_requests']
    if 'pros' not in session:
        session['pros'] = healthcare_data['pros']

def hash_password(password):
    """Hash a password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def init_nursing_home_credentials():
    """Initialize nursing home credentials in the database"""
    conn = sqlite3.connect('caresync.db')
    c = conn.cursor()
    
    for home in healthcare_data['nursing_homes']:
        # Check if nursing home exists in database
        c.execute("SELECT * FROM nursing_homes WHERE clinic_id = ?", (home['clinic_id'],))
        if not c.fetchone():
            # Insert nursing home into database
            c.execute("""
                INSERT INTO nursing_homes (clinic_id, name, location, contact_person, phone, email)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                home['clinic_id'],
                home['name'],
                home['location'],
                home['contact_person'],
                home['phone'],
                home['email']
            ))
            
            # Create default username and password
            username = f"clinic_{home['clinic_id'].lower()}"
            password = f"{home['clinic_id']}123"
            
            # Insert user credentials
            c.execute("""
                INSERT INTO users (username, password, role, entity_id)
                VALUES (?, ?, ?, ?)
            """, (
                username,
                hash_password(password),
                'nursing_home',
                home['clinic_id']
            ))
    
    conn.commit()
    conn.close()

# Initialize nursing home credentials
init_nursing_home_credentials()

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page.', 'error')
            return redirect(url_for('nursing_home_login'))
        return f(*args, **kwargs)
    return decorated_function

# Role-based access control decorator
def role_required(roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please login to access this page.', 'error')
                return redirect(url_for('nursing_home_login'))
            if session.get('role') not in roles:
                flash('You do not have permission to access this page.', 'error')
                return redirect(url_for('nursing_home_login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/nursing-home/login', methods=['GET', 'POST'])
def nursing_home_login():
    if request.method == 'POST':
        clinic_id = request.form.get('clinic_id')
        password = request.form.get('password')
        
        conn = sqlite3.connect('caresync.db')
        c = conn.cursor()
        
        # Find the nursing home
        c.execute("""
            SELECT u.*, n.name 
            FROM users u
            JOIN nursing_homes n ON u.entity_id = n.clinic_id
            WHERE u.entity_id = ? AND u.password = ? AND u.role = 'nursing_home'
        """, (clinic_id, hash_password(password)))
        
        user = c.fetchone()
        conn.close()
        
        if user:
            # Store nursing home info in session
            session['user_id'] = user[0]
            session['username'] = user[1]
            session['role'] = user[3]
            session['entity_id'] = user[4]
            session['nursing_home_name'] = user[5]  # nursing home name
            
            # Initialize session data
            init_session_data()
            
            flash('Login successful!', 'success')
            return redirect(url_for('nursing_home_dashboard'))
        else:
            flash('Invalid clinic ID or password.', 'error')
    
    return render_template('nursing_home_login.html')

@app.route('/nursing-home/logout')
def nursing_home_logout():
    # Clear all session data
    session.clear()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('nursing_home_login'))

@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect(url_for('nursing_home_login'))
    return redirect(url_for('nursing_home_dashboard'))

@app.route('/about')
@login_required
def about():
    return render_template('about.html', 
                         hospitals=healthcare_data['multispeciality_hospitals'],
                         nursing_homes=healthcare_data['nursing_homes'])

@app.route('/contact', methods=['GET', 'POST'])
@login_required
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        message = request.form.get('message')
        return jsonify({"status": "success", "message": "Thank you for your message!"})
    return render_template('contact.html', 
                         hospitals=healthcare_data['multispeciality_hospitals'],
                         counseling=healthcare_data['counseling_resources'])

@app.route('/add-patient', methods=['GET', 'POST'])
@login_required
@role_required(['nursing_home', 'admin'])
def add_patient():
    if request.method == 'POST':
        try:
            # Check MongoDB connection
            if not mongo_client:
                logger.error("MongoDB client is not initialized")
                raise Exception("MongoDB connection not available")

            # Get form data with validation
            name = request.form.get('name')
            if not name:
                raise ValueError("Patient name is required")

            try:
                age = int(request.form.get('age'))
                if age < 0 or age > 120:
                    raise ValueError("Age must be between 0 and 120")
            except (TypeError, ValueError):
                raise ValueError("Invalid age value")

            gender = request.form.get('gender')
            if not gender:
                raise ValueError("Gender is required")

            contact_number = request.form.get('contact_number')
            if not contact_number:
                raise ValueError("Contact number is required")

            address = request.form.get('address')
            if not address:
                raise ValueError("Address is required")

            medical_history = request.form.get('medical_history', '').strip()
            if not medical_history:
                medical_history = []
            else:
                medical_history = [condition.strip() for condition in medical_history.split(',')]

            assigned_hospital_id = request.form.get('assigned_hospital_id')
            if not assigned_hospital_id:
                raise ValueError("Hospital assignment is required")

            referred_by = session.get('entity_id')
            if not referred_by:
                raise ValueError("Clinic ID not found in session")

            # Generate a unique patient ID
            patient_id = str(uuid.uuid4())[:8]
            
            # Create patient document
            patient_doc = {
                'patient_id': patient_id,
                'name': name,
                'age': age,
                'gender': gender,
                'contact_number': contact_number,
                'address': address,
                'medical_history': medical_history,
                'current_status': 'Pending',
                'assigned_hospital_id': assigned_hospital_id,
                'referred_by': referred_by,
                'created_at': datetime.now().isoformat()
            }
            
            logger.info(f"Attempting to add patient: {patient_doc}")
            
            # Get clinic-specific collection
            clinic_collection = init_clinic_collection(referred_by)
            
            # Insert patient document
            result = clinic_collection.insert_one(patient_doc)
            
            if result.inserted_id:
                logger.info(f"Successfully added patient with ID: {patient_id}")
                flash('Patient added successfully!', 'success')
                return redirect(url_for('patient_details', patient_id=patient_id))
            else:
                raise Exception("Failed to insert patient document")
            
        except ValueError as e:
            error_msg = str(e)
            logger.error(f"Validation error: {error_msg}")
            flash(f'Error: {error_msg}', 'error')
            return redirect(url_for('add_patient'))
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error adding patient: {error_msg}")
            flash('An error occurred while adding the patient. Please try again.', 'error')
            return redirect(url_for('add_patient'))
    
    # GET request - show the form
    return render_template('add_patient.html', 
                         hospitals=healthcare_data['multispeciality_hospitals'],
                         nursing_homes=healthcare_data['nursing_homes'])

@app.route('/patient/<patient_id>')
@login_required
def patient_details(patient_id):
    try:
        # Get the clinic ID from session
        clinic_id = session.get('entity_id')
        
        # Get clinic-specific collection
        clinic_collection = get_clinic_collection(clinic_id)
        
        # Find patient in the clinic's collection
        patient = clinic_collection.find_one({'patient_id': patient_id})
        
        if not patient:
            flash('Patient not found!', 'error')
            return redirect(url_for('home'))
        
        # Check if user has permission to view this patient
        if session['user']['role'] == 'nursing_home' and patient['referred_by'] != session['user']['entity_id']:
            flash('You do not have permission to view this patient.', 'error')
            return redirect(url_for('nursing_home_dashboard'))
        
        # Get hospital details from healthcare_data
        hospital = None
        if patient.get('assigned_hospital_id'):
            hospital = next((h for h in healthcare_data['multispeciality_hospitals'] 
                           if h['hospital_id'] == patient['assigned_hospital_id']), None)
        
        # Get nursing home details from healthcare_data
        nursing_home = next((h for h in healthcare_data['nursing_homes'] 
                           if h['clinic_id'] == patient['referred_by']), None)
        
        return render_template('patient_details.html', 
                             patient=patient,
                             hospital=hospital,
                             nursing_home=nursing_home)
                             
    except Exception as e:
        flash('An error occurred while fetching patient details.', 'error')
        print(f"Error fetching patient details: {str(e)}")
        return redirect(url_for('home'))

@app.route('/patient/<patient_id>/request-ambulance', methods=['POST'])
@login_required
@role_required(['nursing_home', 'admin'])
def request_ambulance(patient_id):
    # Find the patient in the session
    patients = session.get('patients', [])
    patient = next((p for p in patients if p['patient_id'] == patient_id), None)
    
    if not patient:
        return jsonify({"status": "error", "message": "Patient not found"}), 404
    
    # Check if user has permission to request ambulance for this patient
    if session['user']['role'] == 'nursing_home' and patient.get('referred_by') != session['user']['entity_id']:
        return jsonify({"status": "error", "message": "You do not have permission to request ambulance for this patient"}), 403
    
    # Get the request data
    data = request.json
    pickup_location = data.get('pickup_location')
    drop_location = data.get('drop_location')
    
    if not pickup_location or not drop_location:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400
    
    # Create a new ambulance request
    ambulance_request = {
        'request_id': str(uuid.uuid4())[:8],
        'patient_id': patient_id,
        'pickup_location': pickup_location,
        'drop_location': drop_location,
        'status': 'Pending',
        'created_at': datetime.now().isoformat()
    }
    
    # Add the request to the session
    ambulance_requests = session.get('ambulance_requests', [])
    ambulance_requests.append(ambulance_request)
    session['ambulance_requests'] = ambulance_requests
    
    # Update the patient status
    patient['current_status'] = 'In Transit'
    session['patients'] = patients
    
    return jsonify({"status": "success", "message": "Ambulance requested successfully"})

@app.route('/api/patients')
@login_required
def get_patients():
    # Filter patients based on user role
    if session['user']['role'] == 'nursing_home':
        patients = [p for p in session.get('patients', []) 
                   if p.get('referred_by') == session['user']['entity_id']]
    else:
        patients = session.get('patients', [])
    
    return jsonify(patients)

@app.route('/api/hospitals')
@login_required
def get_hospitals():
    return jsonify(healthcare_data['multispeciality_hospitals'])

@app.route('/api/ambulance-requests')
@login_required
def get_ambulance_requests():
    # Filter ambulance requests based on user role
    if session['user']['role'] == 'nursing_home':
        requests = [r for r in session.get('ambulance_requests', []) 
                   if r.get('requested_by') == session['user']['entity_id']]
    else:
        requests = session.get('ambulance_requests', [])
    
    return jsonify(requests)

@app.route('/api/pros')
@login_required
def get_pros():
    return jsonify(healthcare_data.get('pros', []))

@app.route('/patient/<patient_id>/assign-pro', methods=['POST'])
@login_required
@role_required(['nursing_home', 'admin'])
def assign_pro(patient_id):
    # Find the patient in the session
    patients = session.get('patients', [])
    patient = next((p for p in patients if p['patient_id'] == patient_id), None)
    
    if not patient:
        return jsonify({"status": "error", "message": "Patient not found"}), 404
    
    # Check if user has permission to assign PRO for this patient
    if session['user']['role'] == 'nursing_home' and patient.get('referred_by') != session['user']['entity_id']:
        return jsonify({"status": "error", "message": "You do not have permission to assign PRO for this patient"}), 403
    
    # Get the request data
    data = request.json
    pro_id = data.get('pro_id')
    
    if not pro_id:
        return jsonify({"status": "error", "message": "Missing PRO ID"}), 400
    
    # Find the PRO
    pros = healthcare_data.get('pros', [])
    pro = next((p for p in pros if p['pro_id'] == pro_id), None)
    
    if not pro:
        return jsonify({"status": "error", "message": "PRO not found"}), 404
    
    # Update the patient with the assigned PRO
    patient['assigned_pro_id'] = pro_id
    session['patients'] = patients
    
    # Update the PRO's assigned patients
    if 'patients_assigned' not in pro:
        pro['patients_assigned'] = []
    
    if patient_id not in pro['patients_assigned']:
        pro['patients_assigned'].append(patient_id)
    
    return jsonify({"status": "success", "message": "PRO assigned successfully"})

@app.route('/hospital/add', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def add_hospital():
    # Log user session info for debugging
    logger.info(f"User attempting to add hospital - User ID: {session.get('user_id')}, Role: {session.get('role')}")
    
    if request.method == 'POST':
        try:
            # Validate required fields
            required_fields = ['name', 'location', 'contact_number', 'total_beds', 
                             'available_beds', 'icu_total', 'icu_available', 'specialties']
            for field in required_fields:
                if not request.form.get(field):
                    raise ValueError(f"{field.replace('_', ' ').title()} is required")
            
            # Validate numeric fields
            try:
                total_beds = int(request.form.get('total_beds'))
                available_beds = int(request.form.get('available_beds'))
                icu_total = int(request.form.get('icu_total'))
                icu_available = int(request.form.get('icu_available'))
                
                if total_beds < 0 or available_beds < 0 or icu_total < 0 or icu_available < 0:
                    raise ValueError("Bed counts cannot be negative")
                if available_beds > total_beds:
                    raise ValueError("Available beds cannot exceed total beds")
                if icu_available > icu_total:
                    raise ValueError("Available ICU beds cannot exceed total ICU beds")
            except ValueError as e:
                if "invalid literal for int()" in str(e):
                    raise ValueError("Invalid number format for bed counts")
                raise e
            
            # Generate a unique hospital ID
            hospital_id = f"H{str(uuid.uuid4())[:8].upper()}"
            
            # Create new hospital record
            new_hospital = {
                "hospital_id": hospital_id,
                "name": request.form.get('name').strip(),
                "location": request.form.get('location').strip(),
                "contact_number": request.form.get('contact_number').strip(),
                "total_beds": total_beds,
                "available_beds": available_beds,
                "icu_beds": {
                    "total": icu_total,
                    "available": icu_available
                },
                "specialties": [s.strip() for s in request.form.get('specialties').split(',') if s.strip()],
                "ambulance_services": 'ambulance_services' in request.form,
                "mental_health_support": 'mental_health_support' in request.form,
                "financial_assistance": 'financial_assistance' in request.form
            }
            
            # Validate specialties
            if not new_hospital['specialties']:
                raise ValueError("At least one specialty is required")
            
            # Add to healthcare data
            healthcare_data['multispeciality_hospitals'].append(new_hospital)
            
            # Save to file
            if save_healthcare_data():
                flash('Hospital added successfully!', 'success')
                logger.info(f"Successfully added hospital: {new_hospital['name']} ({hospital_id})")
            else:
                # Remove the hospital from memory if save failed
                healthcare_data['multispeciality_hospitals'].remove(new_hospital)
                flash('Error saving hospital data. Please try again.', 'error')
                logger.error(f"Failed to save hospital data for: {new_hospital['name']}")
            
            return redirect(url_for('list_hospitals'))
            
        except ValueError as e:
            flash(f'Validation error: {str(e)}', 'error')
            logger.warning(f"Hospital addition validation error: {str(e)}")
            return redirect(url_for('add_hospital'))
        except Exception as e:
            flash('An error occurred while adding the hospital. Please try again.', 'error')
            logger.error(f"Error adding hospital: {str(e)}")
            return redirect(url_for('add_hospital'))
    
    return render_template('add_hospital.html')

@app.route('/hospitals')
@login_required
def list_hospitals():
    """View all hospitals with option to edit"""
    return render_template('hospitals.html', 
                         hospitals=healthcare_data['multispeciality_hospitals'])

@app.route('/hospital/<hospital_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def edit_hospital(hospital_id):
    """Edit an existing hospital"""
    hospital = next((h for h in healthcare_data['multispeciality_hospitals'] 
                    if h['hospital_id'] == hospital_id), None)
    
    if not hospital:
        flash('Hospital not found!', 'error')
        return redirect(url_for('list_hospitals'))
    
    if request.method == 'POST':
        # Update hospital data
        hospital.update({
            "name": request.form.get('name'),
            "location": request.form.get('location'),
            "contact_number": request.form.get('contact_number'),
            "total_beds": int(request.form.get('total_beds')),
            "available_beds": int(request.form.get('available_beds')),
            "icu_beds": {
                "total": int(request.form.get('icu_total')),
                "available": int(request.form.get('icu_available'))
            },
            "specialties": [s.strip() for s in request.form.get('specialties').split(',')],
            "ambulance_services": 'ambulance_services' in request.form,
            "mental_health_support": 'mental_health_support' in request.form,
            "financial_assistance": 'financial_assistance' in request.form
        })
        
        # Save changes
        if save_healthcare_data():
            flash('Hospital updated successfully!', 'success')
        else:
            flash('Error saving hospital data. Please try again.', 'error')
        
        return redirect(url_for('list_hospitals'))
    
    return render_template('edit_hospital.html', hospital=hospital)

@app.route('/hospital/<hospital_id>/delete', methods=['POST'])
@login_required
@role_required(['admin'])
def delete_hospital(hospital_id):
    """Delete an existing hospital"""
    hospital = next((h for h in healthcare_data['multispeciality_hospitals'] 
                    if h['hospital_id'] == hospital_id), None)
    
    if not hospital:
        flash('Hospital not found!', 'error')
        return redirect(url_for('list_hospitals'))
    
    # Remove the hospital from the list
    healthcare_data['multispeciality_hospitals'] = [h for h in healthcare_data['multispeciality_hospitals'] 
                                                  if h['hospital_id'] != hospital_id]
    
    # Save changes
    if save_healthcare_data():
        flash('Hospital deleted successfully!', 'success')
    else:
        flash('Error deleting hospital. Please try again.', 'error')
    
    return redirect(url_for('list_hospitals'))

@app.route('/nursing-home/dashboard')
@login_required
@role_required(['nursing_home'])
def nursing_home_dashboard():
    try:
        # Get the nursing home's ID
        nursing_home_id = session.get('entity_id')
        if not nursing_home_id:
            flash('Session expired. Please login again.', 'error')
            return redirect(url_for('nursing_home_login'))
        
        # Get clinic-specific collection
        try:
            clinic_collection = get_clinic_collection(nursing_home_id)
        except Exception as e:
            flash('Database connection error. Please try again later.', 'error')
            logger.error(f"Database error in nursing_home_dashboard: {str(e)}")
            return redirect(url_for('nursing_home_login'))
        
        # Get all patients for this clinic
        patients = list(clinic_collection.find())
        
        # Add hospital names to patient data
        for patient in patients:
            if patient.get('assigned_hospital_id'):
                hospital = next((h for h in healthcare_data['multispeciality_hospitals'] 
                               if h['hospital_id'] == patient['assigned_hospital_id']), None)
                patient['hospital_name'] = hospital['name'] if hospital else 'Not Assigned'
            else:
                patient['hospital_name'] = 'Not Assigned'
        
        return render_template('nursing_home_dashboard.html', 
                             nursing_home_name=session.get('nursing_home_name'),
                             patients=patients,
                             hospitals=healthcare_data['multispeciality_hospitals'])
                             
    except Exception as e:
        flash('An error occurred while fetching patient data.', 'error')
        logger.error(f"Error in nursing_home_dashboard: {str(e)}")
        return redirect(url_for('nursing_home_login'))

@app.route('/admin/dashboard')
@login_required
@role_required(['admin'])
def admin_dashboard():
    return render_template('admin_dashboard.html',
                         patients=session.get('patients', []),
                         hospitals=healthcare_data['multispeciality_hospitals'],
                         nursing_homes=healthcare_data['nursing_homes'])

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        # Get form data
        name = request.form.get('name')
        location = request.form.get('location')
        contact_person = request.form.get('contact_person')
        phone = request.form.get('phone')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate passwords match
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('signup.html')
        
        # Generate a unique clinic ID
        clinic_id = f"CL{str(uuid.uuid4())[:8].upper()}"
        
        conn = sqlite3.connect('caresync.db')
        c = conn.cursor()
        
        try:
            # Insert nursing home into database
            c.execute("""
                INSERT INTO nursing_homes (clinic_id, name, location, contact_person, phone, email)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (clinic_id, name, location, contact_person, phone, email))
            
            # Create username and password
            username = f"clinic_{clinic_id.lower()}"
            
            # Insert user credentials
            c.execute("""
                INSERT INTO users (username, password, role, entity_id)
                VALUES (?, ?, ?, ?)
            """, (username, hash_password(password), 'nursing_home', clinic_id))
            
            conn.commit()
            flash(f'Registration successful! Your Clinic ID is: {clinic_id}. Please use this ID to login.', 'success')
            return redirect(url_for('nursing_home_login'))
            
        except sqlite3.IntegrityError:
            flash('An error occurred during registration. Please try again.', 'error')
            conn.rollback()
        finally:
            conn.close()
    
    return render_template('signup.html')

def migrate_hospital_data():
    """Migrate hospital data from JSON to database"""
    try:
        conn = sqlite3.connect('caresync.db')
        c = conn.cursor()
        
        # Check if hospitals table is empty
        c.execute('SELECT COUNT(*) FROM hospitals')
        if c.fetchone()[0] == 0:
            # Insert hospitals from healthcare_data
            for hospital in healthcare_data['multispeciality_hospitals']:
                c.execute('''
                    INSERT INTO hospitals (
                        hospital_id, name, location, contact_number,
                        total_beds, available_beds, icu_total, icu_available,
                        specialties, ambulance_services, mental_health_support,
                        financial_assistance
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    hospital['hospital_id'],
                    hospital['name'],
                    hospital['location'],
                    hospital['contact_number'],
                    hospital['total_beds'],
                    hospital['available_beds'],
                    hospital['icu_beds']['total'],
                    hospital['icu_beds']['available'],
                    ','.join(hospital['specialties']),
                    hospital['ambulance_services'],
                    hospital['mental_health_support'],
                    hospital['financial_assistance']
                ))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error migrating hospital data: {e}")
        return False

# Initialize database and migrate data
init_db()
migrate_hospital_data()

@app.route('/test-db')
def test_db():
    try:
        if not mongo_client:
            return jsonify({"status": "error", "message": "MongoDB client not initialized"})
        
        # Test the connection
        mongo_client.server_info()
        
        # Try to access a collection
        test_collection = db['test_collection']
        test_collection.insert_one({"test": "connection"})
        test_collection.delete_one({"test": "connection"})
        
        return jsonify({
            "status": "success",
            "message": "MongoDB connection successful",
            "collections": db.list_collection_names()
        })
    except Exception as e:
        logger.error(f"Database test error: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        })

if __name__ == '__main__':
    app.run(debug=True)