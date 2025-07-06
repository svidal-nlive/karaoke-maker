# api/api.py

import os
import json
import uuid
import datetime
import shutil
import secrets
import hashlib
from pathlib import Path
from flask import Flask, request, jsonify, Response, abort, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from flask_jwt_extended import (
    JWTManager, create_access_token,
    jwt_required, get_jwt_identity, get_jwt
)
from flasgger import Swagger, swag_from

# Import pipeline utilities
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline_utils import (
    redis_client, 
    setup_logger, 
    add_to_stream, 
    set_file_status,
    STREAM_QUEUED
)

# --- Config ---
UPLOAD_FOLDER = os.environ.get("INPUT_DIR", "/input")
ALLOWED_EXTENSIONS = {'mp3'}
API_PORT = int(os.environ.get("API_PORT", 5000))
MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_SIZE", 100 * 1024 * 1024))  # 100MB default

# Configure upload limits and settings
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.config['UPLOAD_EXTENSIONS'] = ALLOWED_EXTENSIONS

# Configure maximum request size and timeouts
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['UPLOAD_TIMEOUT'] = 3600  # 1 hour timeout for uploads

# Configure chunked transfer encoding
app.config['MAX_CONTENT_LENGTH'] = None  # Disable content length checking for chunked uploads

# Generate a secure JWT secret if not provided
def generate_jwt_secret():
    """Generate a secure random JWT secret."""
    return secrets.token_urlsafe(64)

JWT_SECRET = os.environ.get("JWT_SECRET", generate_jwt_secret())

# Hash the admin password for security
def hash_password(password):
    """Hash a password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

DEFAULT_ADMIN_PASSWORD = "admin"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)

# Setup logger
logger = setup_logger("api")

# --- Flask and JWT setup ---
app.config["JWT_SECRET_KEY"] = JWT_SECRET
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = datetime.timedelta(hours=1)  # Token expires in 1 hour
app.config["JWT_TOKEN_LOCATION"] = ["headers"]
app.config["JWT_HEADER_NAME"] = "Authorization"
app.config["JWT_HEADER_TYPE"] = "Bearer"
app.config["JWT_ERROR_MESSAGE_KEY"] = "error"  # Use "error" as the key for error messages
app.config["JWT_BLACKLIST_ENABLED"] = False  # Disable token blacklist for simplicity
app.config["JWT_ALGORITHM"] = "HS256"  # Explicitly set algorithm
app.config["PROPAGATE_EXCEPTIONS"] = True  # Allow JWT errors to propagate to the error handlers

jwt = JWTManager(app)

# JWT verification callback - will be called with each JWT token
@jwt.token_verification_loader
def verify_token_callback(jwt_header, jwt_payload):
    logger.debug(f"Verifying token with header: {jwt_header}")
    logger.debug(f"Payload: {jwt_payload}")
    return True  # Always verify the token for now

# JWT error handlers
@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    logger.error(f"Expired token: {jwt_payload}")
    return jsonify({
        'msg': 'The token has expired',
        'error': 'token_expired'
    }), 401

@jwt.invalid_token_loader
def invalid_token_callback(error):
    logger.error(f"Invalid token error: {error}")
    return jsonify({
        'msg': 'Invalid token',
        'error': str(error)
    }), 401

@jwt.unauthorized_loader
def unauthorized_callback(error):
    logger.error(f"Unauthorized error: {error}")
    return jsonify({
        'msg': 'Missing Authorization Header',
        'error': str(error)
    }), 401

# Swagger configuration
swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec",
            "route": "/apispec.json",
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/docs/"
}

swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "Karaoke Maker API",
        "description": "API for the Karaoke Maker application",
        "version": "1.0.0"
    },
    "securityDefinitions": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": "JWT Authorization header using the Bearer scheme. Example: 'Bearer {token}'"
        }
    }
}

swagger = Swagger(app, config=swagger_config, template=swagger_template)

# Configure CORS with specific origins for credential support
CORS(app, resources={
    r"/api/*": {
        "origins": ["*"],  # Allow all origins for testing
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "expose_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True,
        "send_wildcard": False
    },
    r"/docs/*": {
        "origins": ["*"]  # Allow all origins for docs
    },
    r"/apispec.json": {
        "origins": ["*"]  # Allow all origins for API spec  
    }
})

# Add CORS debugging middleware
@app.after_request
def after_request(response):
    # Log request details
    logger.debug(f"Request: {request.method} {request.path}")
    logger.debug(f"Request headers: {dict(request.headers)}")
    
    # Log response details 
    logger.debug(f"Response status: {response.status}")
    logger.debug(f"Response headers: {dict(response.headers)}")
    
    # Log auth header specifically for debugging
    auth_header = request.headers.get('Authorization', '')
    if auth_header:
        # Mask the actual token value for security but show more for debugging
        parts = auth_header.split()
        if len(parts) == 2:
            prefix, token = parts
            logger.debug(f"Auth header prefix: {prefix}")
            # Show token length and first/last few chars
            token_preview = f"{token[:10]}...{token[-10:]}" if len(token) > 20 else token
            logger.debug(f"Auth token preview: {token_preview} (length: {len(token)})")
        else:
            logger.warning(f"Malformed Authorization header: {auth_header[:20]}...")
    else:
        logger.debug("No Authorization header present")
    
    return response

# In-memory user store with persistent settings (replace with a database in production)
def get_user_store():
    """Get user store from Redis or initialize with defaults."""
    users_key = "karaoke:users"
    users = redis_client.hgetall(users_key)
    
    if not users:
        # Initialize with default admin user
        default_users = {
            "admin": json.dumps({
                "password": hash_password(DEFAULT_ADMIN_PASSWORD),
                "role": "admin",
                "needs_password_change": True
            })
        }
        redis_client.hset(users_key, mapping=default_users)
        return {k: json.loads(v) for k, v in default_users.items()}
    
    return {k: json.loads(v) for k, v in users.items()}

def save_user_store(users):
    """Save user store to Redis."""
    users_key = "karaoke:users"
    serialized_users = {k: json.dumps(v) for k, v in users.items()}
    redis_client.hset(users_key, mapping=serialized_users)

# --- Helper functions ---
def allowed_file(filename):
    """Check if a file has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Login Required Decorator (uses JWT) ---
def login_required(f):
    @jwt_required()
    def protected_route(*args, **kwargs):
        return f(*args, **kwargs)
    protected_route.__name__ = f.__name__  # Preserve the original function name
    return protected_route

# --- Admin Role Required ---
def admin_required(f):
    @jwt_required()
    def admin_protected_route(*args, **kwargs):
        claims = get_jwt()
        if claims.get("role") != "admin":
            return jsonify({"error": "Forbidden"}), 403
        return f(*args, **kwargs)
    admin_protected_route.__name__ = f.__name__  # Preserve the original function name
    return admin_protected_route

# --- API Routes ---
@app.route("/api/health", methods=["GET"])
def health_check():
    """
    Health check endpoint for Docker healthcheck
    ---
    tags:
      - System
    responses:
      200:
        description: Service is healthy
        schema:
          type: object
          properties:
            status:
              type: string
              example: healthy
      500:
        description: Service is unhealthy
        schema:
          type: object
          properties:
            status:
              type: string
              example: unhealthy
            error:
              type: string
    """
    try:
        # Check Redis connection
        redis_client.ping()
        # Check upload directory
        if not os.path.isdir(UPLOAD_FOLDER):
            return jsonify({"status": "error", "message": "Upload directory not found"}), 500
        return jsonify({"status": "healthy"})
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

@app.route("/api/login", methods=["POST"])
def login():
    """
    Login endpoint to get a JWT token
    ---
    tags:
      - Authentication
    parameters:
      - in: body
        name: credentials
        required: true
        schema:
          type: object
          properties:
            username:
              type: string
              example: admin
            password:
              type: string
              example: admin
    responses:
      200:
        description: Login successful
        schema:
          type: object
          properties:
            access_token:
              type: string
            user:
              type: object
              properties:
                username:
                  type: string
                role:
                  type: string
                needs_password_change:
                  type: boolean
      401:
        description: Invalid credentials
        schema:
          type: object
          properties:
            msg:
              type: string
    """
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    
    users = get_user_store()
    user_obj = users.get(username)
    
    if not user_obj or user_obj["password"] != hash_password(password):
        return jsonify({"msg": "Bad username or password"}), 401

    try:
        # Create JWT token with role claim and expiry
        expires = datetime.timedelta(hours=1)
        access_token = create_access_token(
            identity=username,
            additional_claims={
                "role": user_obj["role"],
                "type": "access"
            },
            expires_delta=expires
        )
        
        response_data = {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": int(expires.total_seconds()),
            "user": {
                "username": username,
                "role": user_obj["role"],
                "needs_password_change": user_obj.get("needs_password_change", False)
            }
        }
        
        logger.info(f"Login successful for user: {username}")
        logger.debug(f"Generated token length: {len(access_token)}")
        
        return jsonify(response_data)
    except Exception as e:
        logger.error(f"Error generating token: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

@app.route("/api/me", methods=["GET"])
@jwt_required()
def get_me():
    """
    Get current user information
    ---
    tags:
      - Authentication
    security:
      - Bearer: []
    responses:
      200:
        description: User information
        schema:
          type: object
          properties:
            username:
              type: string
            role:
              type: string
            needs_password_change:
              type: boolean
      401:
        description: Missing or invalid token
    """
    try:
        # Log the Authorization header for debugging
        auth_header = request.headers.get('Authorization', '')
        logger.debug(f"get_me - Authorization header: {auth_header}")
        
        # Manually parse token for debugging
        if auth_header and ' ' in auth_header:
            scheme, token = auth_header.split(' ', 1)
            logger.debug(f"get_me - Auth scheme: {scheme}, token length: {len(token)}")
        
        current_user = get_jwt_identity()
        logger.debug(f"get_me - Current user identity: {current_user}")
        
        current_claims = get_jwt()
        logger.debug(f"get_me - Current claims: {current_claims}")
        
        users = get_user_store()
        user = users.get(current_user, {})
        
        response_data = {
            "username": current_user,
            "role": current_claims.get("role", "user"),
            "needs_password_change": user.get("needs_password_change", False)
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Error in /api/me endpoint: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

@app.route("/api/change-password", methods=["POST"])
@login_required
def change_password():
    """
    Change user password
    ---
    tags:
      - Authentication
    security:
      - Bearer: []
    parameters:
      - in: body
        name: passwords
        required: true
        schema:
          type: object
          properties:
            current_password:
              type: string
            new_password:
              type: string
            new_username:
              type: string
              description: Optional new username
    responses:
      200:
        description: Password changed successfully
      400:
        description: Invalid request
      401:
        description: Current password is incorrect
    """
    data = request.get_json()
    current_password = data.get("current_password")
    new_password = data.get("new_password")
    new_username = data.get("new_username")
    
    current_username = get_jwt_identity()
    users = get_user_store()
    user_obj = users.get(current_username)
    
    if not user_obj:
        return jsonify({"error": "User not found"}), 404
    
    # Verify current password
    if user_obj["password"] != hash_password(current_password):
        return jsonify({"error": "Current password is incorrect"}), 401
    
    # Update password
    user_obj["password"] = hash_password(new_password)
    user_obj["needs_password_change"] = False
    
    # Handle username change
    if new_username and new_username != current_username:
        if new_username in users:
            return jsonify({"error": "Username already exists"}), 400
        users[new_username] = user_obj
        del users[current_username]
        username = new_username
    else:
        users[current_username] = user_obj
        username = current_username
    
    save_user_store(users)
    
    # Generate new token with updated info
    access_token = create_access_token(
        identity=username,
        additional_claims={"role": user_obj["role"]}
    )
    
    return jsonify({
        "message": "Password changed successfully",
        "access_token": access_token,
        "user": {
            "username": username,
            "role": user_obj["role"],
            "needs_password_change": False
        }
    })

@app.route("/api/upload", methods=["POST"])
@login_required
def upload_file():
    """
    Upload endpoint for audio files
    ---
    tags:
      - Files
    security:
      - Bearer: []
    consumes:
      - multipart/form-data
    parameters:
      - in: formData
        name: file
        type: file
        required: true
        description: MP3 audio file to upload
    responses:
      202:
        description: File uploaded successfully
        schema:
          type: object
          properties:
            status:
              type: string
            message:
              type: string
            filename:
              type: string
            job_id:
              type: string
      400:
        description: Bad request
        schema:
          type: object
          properties:
            error:
              type: string
    """
    # Check if the post request has the file part
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    
    # If user does not select file, browser also
    # submit an empty part without filename
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if file and allowed_file(file.filename):
        # Generate a secure filename
        filename = secure_filename(file.filename)
        
        # Add timestamp to ensure uniqueness
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        base, ext = os.path.splitext(filename)
        unique_filename = f"{base}_{timestamp}{ext}"
        
        # Save the file to input directory
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(file_path)
        
        # Copy the file to queue directory (similar to how watcher service does it)
        # Create queue directory if it doesn't exist
        queue_dir = os.environ.get("QUEUE_DIR", "/queue")
        os.makedirs(queue_dir, exist_ok=True)
        
        # Copy the file to queue directory
        queue_path = os.path.join(queue_dir, unique_filename)
        shutil.copy2(file_path, queue_path)
        
        # Create a job state file in the queue directory
        job_id = str(uuid.uuid4())
        job_state = {
            "filename": unique_filename,
            "original_filename": filename,
            "job_id": job_id,
            "timestamp": timestamp,
            "status": "queued"
        }
        
        # Write job state to queue directory
        job_state_path = os.path.join(queue_dir, f"{unique_filename}.jobstate.json")
        with open(job_state_path, 'w') as f:
            json.dump(job_state, f, indent=2)
        
        # Set initial file status
        set_file_status(unique_filename, "queued")
        
        # Add to processing queue
        add_to_stream(STREAM_QUEUED, {
            "filename": unique_filename,
            "original_filename": filename,
            "job_id": job_id,
            "timestamp": timestamp
        })
        
        logger.info(f"File uploaded: {unique_filename}, Job ID: {job_id}")
        logger.info(f"Copied file to queue: {queue_path}")
        
        return jsonify({
            "status": "success", 
            "message": "File uploaded successfully", 
            "filename": unique_filename,
            "job_id": job_id
        }), 202
    
    return jsonify({"error": "File type not allowed"}), 400

@app.route("/api/settings", methods=["GET"])
@admin_required
def get_settings():
    """
    Get current system settings
    ---
    tags:
      - Settings
    security:
      - Bearer: []
    responses:
      200:
        description: Current settings
        schema:
          type: object
          properties:
            splitter_type:
              type: string
            stems:
              type: string
            stem_types:
              type: string
            default_remove_vocals:
              type: string
    """
    # We'll store settings in Redis
    settings_key = "karaoke:settings"
    settings = redis_client.hgetall(settings_key)
    
    # Default settings if none exist
    if not settings:
        settings = {
            "splitter_type": "spleeter",
            "stems": "4",
            "stem_types": "vocals,drums,bass,other",
            "default_remove_vocals": "true"
        }
        redis_client.hset(settings_key, mapping=settings)
    
    return jsonify(settings)

@app.route("/api/settings", methods=["POST"])
@admin_required
def update_settings():
    """
    Update system settings
    ---
    tags:
      - Settings
    security:
      - Bearer: []
    parameters:
      - in: body
        name: settings
        required: true
        schema:
          type: object
          properties:
            splitter_type:
              type: string
              enum: [spleeter, demucs]
            stems:
              type: integer
              enum: [2, 4, 5]
            stem_types:
              type: string
            default_remove_vocals:
              type: string
    responses:
      200:
        description: Settings updated successfully
      400:
        description: Invalid settings
    """
    data = request.get_json()
    settings_key = "karaoke:settings"
    
    # Validate settings
    if "splitter_type" in data and data["splitter_type"] not in ["spleeter", "demucs"]:
        return jsonify({"error": "Invalid splitter_type"}), 400
    
    if "stems" in data:
        try:
            stems = int(data["stems"])
            if stems not in [2, 4, 5]:
                return jsonify({"error": "Invalid stems value, must be 2, 4, or 5"}), 400
            data["stems"] = str(stems)  # Convert back to string for Redis
        except ValueError:
            return jsonify({"error": "Invalid stems value, must be an integer"}), 400
    
    # Update settings in Redis
    redis_client.hset(settings_key, mapping=data)
    
    # Get updated settings
    updated_settings = redis_client.hgetall(settings_key)
    
    return jsonify(updated_settings)

@app.route("/api/jobs", methods=["GET"])
@login_required
def get_jobs():
    """
    Get all jobs and their status
    ---
    tags:
      - Jobs
    security:
      - Bearer: []
    parameters:
      - in: query
        name: limit
        type: integer
        description: Number of jobs to return per page
      - in: query
        name: offset
        type: integer
        description: Offset for pagination
      - in: query
        name: status
        type: string
        description: Filter by status
    responses:
      200:
        description: List of jobs with pagination info
        schema:
          type: object
          properties:
            jobs:
              type: array
              items:
                type: object
                properties:
                  filename:
                    type: string
                  status:
                    type: string
                  error:
                    type: string
                  created_at:
                    type: string
                  updated_at:
                    type: string
            total:
              type: integer
              description: Total number of jobs
    """
    try:
        # Parse query parameters
        limit = request.args.get('limit', type=int)
        offset = request.args.get('offset', type=int, default=0)
        status_filter = request.args.get('status')
        
        jobs = []
        
        # Get all file keys from Redis
        keys = redis_client.keys("file:*")
        for key in keys:
            try:
                data = redis_client.hgetall(key)
                # Apply status filter if provided
                if status_filter and data.get("status") != status_filter:
                    continue
                    
                filename = key.replace("file:", "")
                job = {
                    "id": filename,  # Use filename as ID for now
                    "filename": filename,
                    "status": data.get("status", "unknown"),
                    "error": data.get("error", None),
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at")
                }
                jobs.append(job)
            except Exception as e:
                logger.error(f"Error retrieving job {key}: {e}")
                continue
        
        # Sort by created_at, newest first
        # Handle None values in created_at to prevent comparison errors
        def safe_sort_key(job):
            created_at = job.get("created_at")
            if created_at is None:
                return ""  # Default value for None timestamps
            return created_at
            
        jobs.sort(key=safe_sort_key, reverse=True)
        
        # Calculate total before pagination
        total_jobs = len(jobs)
        
        # Apply pagination if limit is provided
        if limit is not None:
            jobs = jobs[offset:offset + limit]
        
        return jsonify({
            "jobs": jobs or [],
            "total": total_jobs
        })
        
    except Exception as e:
        logger.error(f"Error in get_jobs: {str(e)}")
        # Return valid response even on error
        return jsonify({
            "jobs": [],
            "total": 0,
            "error": "Internal server error"
        }), 500

@app.route("/api/jobs/<job_id>", methods=["GET"])
@login_required
def get_job(job_id):
    """
    Get details for a specific job
    ---
    tags:
      - Jobs
    security:
      - Bearer: []
    parameters:
      - in: path
        name: job_id
        type: string
        required: true
        description: Job ID to retrieve
    responses:
      200:
        description: Job details
        schema:
          type: object
          properties:
            filename:
              type: string
            status:
              type: string
            error:
              type: string
            created_at:
              type: string
            updated_at:
              type: string
      404:
        description: Job not found
    """
    # In a real implementation, we would look up the job by ID
    # For now, we'll use the job_id as the filename
    key = f"file:{job_id}"
    data = redis_client.hgetall(key)
    
    if not data:
        return jsonify({"error": "Job not found"}), 404
    
    job = {
        "filename": job_id,
        "status": data.get("status", "unknown"),
        "error": data.get("error", None),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at")
    }
    
    return jsonify(job)

@app.route("/api/debug", methods=["GET"])
def debug_info():
    """
    Debug endpoint to verify API is accessible and check headers
    ---
    tags:
      - System
    responses:
      200:
        description: Debug information
    """
    # Create a response with all the request information
    auth_header = request.headers.get('Authorization', 'None')
    # Mask the token if present
    if auth_header != 'None' and ' ' in auth_header:
        scheme, token = auth_header.split(' ', 1)
        masked_token = f"{token[:10]}...{token[-10:]}" if len(token) > 20 else token
        auth_header = f"{scheme} {masked_token}"
    
    response_data = {
        "request": {
            "method": request.method,
            "path": request.path,
            "headers": dict(request.headers),
            "auth_header": auth_header,
        },
        "timestamp": datetime.datetime.now().isoformat(),
        "api_status": "ok"
    }
    
    return jsonify(response_data)

# --- Start the application ---
if __name__ == "__main__":
    # Ensure the upload folder exists
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    # Start the Flask app
    app.run(host="0.0.0.0", port=API_PORT, debug=True)
