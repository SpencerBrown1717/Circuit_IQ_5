import os
import logging
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, render_template, abort
from flask_caching import Cache
from flask_compress import Compress
from werkzeug.utils import secure_filename
from datasheet_extractor import DatasheetExtractor
from pcb_designer import PCBDesigner
import time
from functools import wraps
import uuid
import json
from datetime import datetime
import yaml

def load_config():
    """Load configuration from YAML file or environment variables"""
    config = {
        'MAX_UPLOAD_SIZE': 16 * 1024 * 1024,  # Default 16MB
        'UPLOAD_FOLDER': 'uploads',
        'RESULTS_FOLDER': 'results',
        'CACHE_TYPE': 'simple',
        'CACHE_TIMEOUT': 300,
        'CACHE_THRESHOLD': 500,
        'API_KEYS_FILE': 'api_keys.json',
        'USAGE_LOG_FILE': 'usage_logs.json',
        'ALLOWED_ORIGINS': '*',
        'HOST': '127.0.0.1',
        'PORT': 5000,
        'DEBUG': False
    }

    # Try to load from config file
    config_file = os.environ.get('CIRCUIT_IQ_CONFIG', 'config.yaml')
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                yaml_config = yaml.safe_load(f)
                if yaml_config:
                    config.update(yaml_config)
        except Exception as e:
            print(f"Warning: Error loading config file: {e}")

    # Environment variables override config file
    env_mapping = {
        'CIRCUIT_IQ_MAX_UPLOAD_SIZE': 'MAX_UPLOAD_SIZE',
        'CIRCUIT_IQ_UPLOAD_FOLDER': 'UPLOAD_FOLDER',
        'CIRCUIT_IQ_RESULTS_FOLDER': 'RESULTS_FOLDER',
        'CIRCUIT_IQ_CACHE_TYPE': 'CACHE_TYPE',
        'CIRCUIT_IQ_CACHE_TIMEOUT': 'CACHE_TIMEOUT',
        'CIRCUIT_IQ_CACHE_THRESHOLD': 'CACHE_THRESHOLD',
        'CIRCUIT_IQ_API_KEYS_FILE': 'API_KEYS_FILE',
        'CIRCUIT_IQ_USAGE_LOG_FILE': 'USAGE_LOG_FILE',
        'CIRCUIT_IQ_ALLOWED_ORIGINS': 'ALLOWED_ORIGINS',
        'CIRCUIT_IQ_HOST': 'HOST',
        'CIRCUIT_IQ_PORT': 'PORT',
        'CIRCUIT_IQ_DEBUG': 'DEBUG'
    }

    for env_var, config_key in env_mapping.items():
        if env_var in os.environ:
            value = os.environ[env_var]
            # Convert types if necessary
            if config_key in ['PORT', 'MAX_UPLOAD_SIZE', 'CACHE_TIMEOUT', 'CACHE_THRESHOLD']:
                value = int(value)
            elif config_key == 'DEBUG':
                value = value.lower() == 'true'
            elif config_key == 'ALLOWED_ORIGINS':
                value = value.split(',')
            config[config_key] = value

    return config

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('CircuitIQ')

# Initialize Flask app
app = Flask(__name__)

# Base directory setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Load configuration
config = load_config()

# Update Flask configuration
app.config.update(
    MAX_CONTENT_LENGTH=config['MAX_UPLOAD_SIZE'],
    UPLOAD_FOLDER=os.path.join(BASE_DIR, config['UPLOAD_FOLDER']),
    RESULTS_FOLDER=os.path.join(BASE_DIR, config['RESULTS_FOLDER']),
    CACHE_TYPE=config['CACHE_TYPE'],
    CACHE_DEFAULT_TIMEOUT=config['CACHE_TIMEOUT'],
    CACHE_THRESHOLD=config['CACHE_THRESHOLD'],
    API_KEYS_FILE=os.path.join(BASE_DIR, config['API_KEYS_FILE']),
    USAGE_LOG_FILE=os.path.join(BASE_DIR, config['USAGE_LOG_FILE']),
    ALLOWED_ORIGINS=config['ALLOWED_ORIGINS']
)

# Initialize extensions
cache = Cache(app)
Compress(app)

# Ensure directories exist
Path(app.config['UPLOAD_FOLDER']).mkdir(exist_ok=True, parents=True)
Path(app.config['RESULTS_FOLDER']).mkdir(exist_ok=True, parents=True)

# Initialize core components
datasheet_extractor = DatasheetExtractor()
pcb_designer = PCBDesigner()

# Simple API key management
def load_api_keys():
    try:
        if os.path.exists(app.config['API_KEYS_FILE']):
            with open(app.config['API_KEYS_FILE'], 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Error loading API keys: {e}")
        return {}

def save_api_keys(api_keys):
    with open(app.config['API_KEYS_FILE'], 'w') as f:
        json.dump(api_keys, f, indent=2)

# Usage tracking
def log_api_usage(api_key, endpoint, success):
    try:
        usage_data = {
            'timestamp': datetime.now().isoformat(),
            'api_key': api_key,
            'endpoint': endpoint,
            'success': success
        }
        
        with open(app.config['USAGE_LOG_FILE'], 'a') as f:
            f.write(json.dumps(usage_data) + '\n')
    except Exception as e:
        logger.error(f"Error logging API usage: {e}")

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return jsonify({"status": "error", "message": "API key required"}), 401
        
        api_keys = load_api_keys()
        if api_key not in api_keys:
            return jsonify({"status": "error", "message": "Invalid API key"}), 401
        
        try:
            result = f(*args, **kwargs)
            log_api_usage(api_key, request.endpoint, True)
            return result
        except Exception as e:
            log_api_usage(api_key, request.endpoint, False)
            raise e
            
    return decorated_function

@app.route('/api/register', methods=['POST'])
def register_api_key():
    """Register a new API key for B2B customers"""
    data = request.json
    if not data or 'company_name' not in data:
        return jsonify({"status": "error", "message": "Company name required"}), 400
    
    api_key = str(uuid.uuid4())
    api_keys = load_api_keys()
    api_keys[api_key] = {
        'company_name': data['company_name'],
        'created_at': datetime.now().isoformat(),
        'active': True
    }
    save_api_keys(api_keys)
    
    return jsonify({
        "status": "success",
        "api_key": api_key,
        "message": "API key generated successfully"
    })

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/analyze_requirements', methods=['POST'])
@cache.memoize(timeout=300)
def api_analyze_requirements():
    """Analyze text requirements and suggest components and parameters"""
    data = request.json
    if not data or 'text' not in data:
        return jsonify({"status": "error", "message": "No requirements text provided"}), 400
    
    try:
        requirements_text = data['text']
        analysis = pcb_designer.analyze_requirements(requirements_text)
        return jsonify({"status": "success", "analysis": analysis})
    except Exception as e:
        logger.error(f"Error analyzing requirements: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

def process_datasheet(file_path):
    """Process datasheets synchronously"""
    try:
        # Fixed to use the correct method name from datasheet_extractor
        result = datasheet_extractor.process_datasheet(file_path)
        return result['parameters']
    except Exception as e:
        logger.error(f"Error processing datasheet: {e}", exc_info=True)
        raise
    finally:
        # Ensure file cleanup happens in all cases
        if os.path.exists(file_path):
            try:
                os.unlink(file_path)
            except Exception as e:
                logger.error(f"Error cleaning up file {file_path}: {e}")

@app.route('/api/process-datasheets', methods=['POST'])
def api_process_datasheets():
    """Extract component information from a datasheet file or text - endpoint matches frontend js"""
    try:
        if 'datasheets' in request.files:
            datasheet_file = request.files['datasheets']
            if not datasheet_file.filename:
                return jsonify({"success": False, "error": "No file selected"}), 400
            
            # Save to temporary location
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], 
                                   secure_filename(f"{time.time()}_{datasheet_file.filename}"))
            datasheet_file.save(file_path)
            
            # Process synchronously
            component = process_datasheet(file_path)
            return jsonify({
                "success": True,
                "components": [component],
                "message": "Datasheet processed successfully"
            })
            
        elif request.json and 'text' in request.json:
            datasheet_text = request.json['text']
            # Fixed to use the correct method name from datasheet_extractor
            result = datasheet_extractor.process_datasheet(datasheet_text)
            component = result['parameters']
            return jsonify({
                "success": True, 
                "components": [component]
            })
        
        else:
            return jsonify({"success": False, "error": "No datasheet provided"}), 400
            
    except Exception as e:
        logger.error(f"Error extracting from datasheet: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

# Keep the original API endpoint for backwards compatibility
@app.route('/api/extract_from_datasheet', methods=['POST'])
def api_extract_from_datasheet():
    """Extract component information from a datasheet file or text - original API endpoint"""
    try:
        if 'file' in request.files:
            datasheet_file = request.files['file']
            if not datasheet_file.filename:
                return jsonify({"status": "error", "message": "No file selected"}), 400
            
            # Save to temporary location
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], 
                                   secure_filename(f"{time.time()}_{datasheet_file.filename}"))
            datasheet_file.save(file_path)
            
            # Process synchronously
            component = process_datasheet(file_path)
            return jsonify({
                "status": "success",
                "component": component,
                "message": "Datasheet processed successfully"
            })
            
        elif request.json and 'text' in request.json:
            datasheet_text = request.json['text']
            result = datasheet_extractor.process_datasheet(datasheet_text)
            component = result['parameters']
            return jsonify({
                "status": "success", 
                "component": component
            })
        
        else:
            return jsonify({"status": "error", "message": "No datasheet provided"}), 400
            
    except Exception as e:
        logger.error(f"Error extracting from datasheet: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

def generate_pcb_design(data, result_dir):
    """Generate PCB design synchronously"""
    try:
        return pcb_designer.generate_design(
            project_name=data.get('project_name', 'Untitled'),
            requirements=data.get('requirements', ''),
            board_params=data.get('board_params', {}),
            components=data.get('components', []),
            output_dir=result_dir
        )
    except Exception as e:
        logger.error(f"Error generating PCB design: {e}", exc_info=True)
        raise

@app.route('/api/generate-design', methods=['POST'])
def frontend_design_pcb():
    """Generate PCB design endpoint that matches the frontend JS"""
    try:
        data = request.json
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400
        
        # Generate unique result directory
        project_name = data.get('project_name', 'Untitled')
        result_id = f"pcb_{int(time.time())}"
        result_dir = os.path.join(app.config['RESULTS_FOLDER'], result_id)
        os.makedirs(result_dir, exist_ok=True)
        
        # Generate PCB design synchronously
        design_result = generate_pcb_design(data, result_dir)
        
        if not design_result:
            return jsonify({
                "success": False, 
                "error": "Failed to generate PCB design"
            }), 500
        
        # Generate relative URLs for results
        preview_url = f"/results/{result_id}/preview.png"
        
        # Add gerber zip URL if it exists
        gerber_zip_url = None
        if design_result.get('gerber_zip'):
            gerber_zip_filename = os.path.basename(design_result['gerber_zip'])
            gerber_zip_url = f"/results/{result_id}/{gerber_zip_filename}"
        
        gerber_files = []
        
        gerber_dir = os.path.join(result_dir, "gerber")
        if os.path.exists(gerber_dir):
            for f in os.listdir(gerber_dir):
                if f.endswith(('.gbr', '.drl')):
                    gerber_files.append({
                        'name': f,
                        'description': f"Gerber file for {f.split('.')[0]} layer",
                        'url': f'/results/{result_id}/gerber/{f}'
                    })
        
        return jsonify({
            "success": True,
            "design": {
                "design_id": result_id,
                "preview_url": preview_url,
                "gerber_zip_url": gerber_zip_url,
                "components": design_result.get('components', 0),
                "board_params": {
                    "width": data.get('board_params', {}).get('width', 100),
                    "height": data.get('board_params', {}).get('height', 80),
                },
                "board_dimensions": design_result.get('dims', ''),
                "layers": data.get('board_params', {}).get('layers', 2),
                "gerber_files": gerber_files,
                "suggestions": design_result.get('suggestions', [])
            }
        })
    
    except Exception as e:
        logger.error(f"Error generating PCB design: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"Failed to generate PCB: {str(e)}"
        }), 500

# Keep the original API endpoint for backwards compatibility
@app.route('/api/design_pcb', methods=['POST'])
def design_pcb():
    """Generate PCB design from components and parameters - original API endpoint"""
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400
        
        # Generate unique result directory
        project_name = data.get('project_name', 'Untitled')
        result_id = f"pcb_{int(time.time())}"
        result_dir = os.path.join(app.config['RESULTS_FOLDER'], result_id)
        os.makedirs(result_dir, exist_ok=True)
        
        # Generate PCB design synchronously
        design_result = generate_pcb_design(data, result_dir)
        
        if not design_result:
            return jsonify({
                "status": "error", 
                "message": "Failed to generate PCB design"
            }), 500
        
        # Generate relative URLs for results
        preview_url = f"/results/{result_id}/preview.png"
        
        # Add gerber zip URL if it exists
        gerber_zip_url = None
        if design_result.get('gerber_zip'):
            gerber_zip_filename = os.path.basename(design_result['gerber_zip'])
            gerber_zip_url = f"/results/{result_id}/{gerber_zip_filename}"
        
        gerber_files = []
        
        gerber_dir = os.path.join(result_dir, "gerber")
        if os.path.exists(gerber_dir):
            for f in os.listdir(gerber_dir):
                if f.endswith(('.gbr', '.drl')):
                    gerber_files.append({
                        'name': f, 
                        'url': f'/results/{result_id}/gerber/{f}'
                    })
        
        return jsonify({
            "status": "success",
            "design_id": result_id,
            "preview_url": preview_url,
            "gerber_zip_url": gerber_zip_url,
            "components": design_result.get('components', 0),
            "board_dimensions": design_result.get('dims', ''),
            "layers": data.get('board_params', {}).get('layers', 2),
            "gerber_files": gerber_files
        })
    
    except Exception as e:
        logger.error(f"Error generating PCB design: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": f"Failed to generate PCB: {str(e)}"
        }), 500

@app.route('/results/<design_id>/<path:filename>')
def serve_result_file(design_id, filename):
    """Serve files from the results directory"""
    result_dir = os.path.join(app.config['RESULTS_FOLDER'], design_id)
    if not os.path.exists(result_dir):
        abort(404)
    
    # Handle gerber subdirectory
    if filename.startswith('gerber/'):
        gerber_filename = filename.split('/', 1)[1]
        return send_from_directory(os.path.join(result_dir, 'gerber'), gerber_filename)
    
    return send_from_directory(result_dir, filename)

@app.route('/api/component_types', methods=['GET'])
def get_component_types():
    """Return a list of available component types"""
    component_types = []
    
    for comp_type, details in pcb_designer.component_library.items():
        component_types.append({
            "type": comp_type,
            "description": details.get("description", ""),
            "pins": details.get("pins", 0)
        })
    
    return jsonify({
        "status": "success",
        "component_types": component_types
    })

@app.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "Circuit IQ API",
        "timestamp": int(time.time())
    })

@app.route('/api/usage', methods=['GET'])
@require_api_key
def get_usage():
    """Get API usage statistics for the authenticated key"""
    api_key = request.headers.get('X-API-Key')
    usage_stats = {'total_calls': 0, 'successful_calls': 0, 'endpoints': {}}
    
    try:
        with open(app.config['USAGE_LOG_FILE'], 'r') as f:
            for line in f:
                usage = json.loads(line)
                if usage['api_key'] == api_key:
                    usage_stats['total_calls'] += 1
                    if usage['success']:
                        usage_stats['successful_calls'] += 1
                    
                    endpoint = usage['endpoint']
                    if endpoint not in usage_stats['endpoints']:
                        usage_stats['endpoints'][endpoint] = {'total': 0, 'successful': 0}
                    
                    usage_stats['endpoints'][endpoint]['total'] += 1
                    if usage['success']:
                        usage_stats['endpoints'][endpoint]['successful'] += 1
    
        return jsonify({
            "status": "success",
            "usage": usage_stats
        })
    except Exception as e:
        logger.error(f"Error getting usage stats: {e}")
        return jsonify({"status": "error", "message": "Error retrieving usage statistics"}), 500

if __name__ == '__main__':
    # Create required directories if they don't exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['RESULTS_FOLDER'], exist_ok=True)
    
    # Get port from command line argument or environment variable, default to 5000
    port = int(os.environ.get('PORT', 5000))
    
    # Get host from environment variable, default to localhost
    host = os.environ.get('HOST', '127.0.0.1')
    
    # Get debug mode from environment variable, default to False
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    print(f"\nCircuit IQ API Server")
    print(f"=====================")
    print(f"Server running at: http://{host}:{port}")
    print(f"API endpoints available:")
    print(f"  - POST /api/analyze_requirements")
    print(f"  - POST /api/process-datasheets (frontend)")
    print(f"  - POST /api/extract_from_datasheet (API)")
    print(f"  - POST /api/generate-design (frontend)")
    print(f"  - POST /api/design_pcb (API)")
    print(f"  - GET  /api/component_types")
    print(f"  - GET  /health")
    print(f"  - POST /api/register")
    print(f"  - GET  /api/usage")
    print(f"\nTo customize the server:")
    print(f"  - Set PORT environment variable to change the port (default: 5000)")
    print(f"  - Set HOST environment variable to change the host (default: 127.0.0.1)")
    print(f"  - Set DEBUG=True environment variable to enable debug mode")
    print(f"\nPress Ctrl+C to stop the server\n")
    
    # Run the Flask application
    app.run(host=host, port=port, debug=debug)