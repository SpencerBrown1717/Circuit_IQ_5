import os
import re
import PyPDF2
import logging
import spacy
import hashlib
from functools import lru_cache
from typing import Dict, List, Optional, Any
from pathlib import Path

# Enhanced logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('CircuitIQ-Extractor')

class DatasheetExtractor:
    """
    Enhanced DatasheetExtractor for Circuit IQ PCB Designer
    
    Extracts component parameters from datasheets in PDF format or text content.
    Features:
    - PDF text extraction with caching
    - Enhanced regex patterns for robust parameter extraction
    - Support for tables and structured data
    - Parameter validation
    - Improved error handling
    """
    
    def __init__(self, cache_dir: Optional[str] = None):
        """Initialize the DatasheetExtractor with enhanced patterns and caching"""
        # Set up caching
        self.cache_dir = cache_dir or os.path.join(os.path.expanduser("~"), ".circuit_iq", "cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Load spaCy model for NLP
        try:
            self.nlp = spacy.load("en_core_web_md")
        except OSError:
            logger.warning("Downloading spaCy model...")
            os.system("python -m spacy download en_core_web_md")
            self.nlp = spacy.load("en_core_web_md")
        
        # Enhanced component type detection keywords
        self.component_types = {
            'regulator': ['regulator', 'voltage regulator', 'ldo', 'voltage', 'U', 'LM78', 'LM79'],
            'resistor': ['resistor', 'resistance', 'ohm', 'Ω', 'R'],
            'capacitor': ['capacitor', 'capacitance', 'farad', 'pF', 'nF', 'µF', 'C'],
            'inductor': ['inductor', 'inductance', 'henry', 'µH', 'mH', 'L'],
            'diode': ['diode', 'rectifier', 'schottky', 'D'],
            'LED': ['led', 'light emitting diode', 'LED'],
            'transistor': ['transistor', 'bjt', 'fet', 'mosfet', 'Q'],
            'microcontroller': ['microcontroller', 'mcu', 'processor', 'µC', 'IC', 'arduino', 'atmega', 'pic', 'stm32'],
            'crystal': ['crystal', 'oscillator', 'resonator', 'Y'],
            'connector': ['connector', 'header', 'socket', 'jack', 'J'],
            'fuse': ['fuse', 'polyfuse', 'F'],
            'switch': ['switch', 'button', 'SW']
        }
        
        # Enhanced parameter patterns
        self.parameter_patterns = {
            'part_number': [
                r'(?i)Part\s*(?:Number|No|#):\s*([\w\d-]+)',
                r'(?i)P/N:\s*([\w\d-]+)',
                r'(?i)Model(?:\s*Number)?:\s*([\w\d-]+)',
                r'(?<![\w\d])([A-Z\d]{2,15}-[\w\d-]+)(?![\w\d])'
            ],
            'package': [
                r'(?i)Package(?:\s*Type)?:\s*([\w\d-]+)',
                r'(?i)Case(?:\s*Style)?:\s*([\w\d-]+)',
                r'(?i)Footprint:\s*([\w\d-]+)',
                r'(?i)(SO(?:IC)?-\d+|TSSOP-\d+|QFP-\d+|DIP-\d+|TO-\d+)'
            ],
            'voltage': [
                r'(?i)(?:Operating|Input|Supply|Output)\s*Voltage\s*:\s*([\d\.]+)\s*(?:V)?\s*(?:to|-)\s*([\d\.]+)\s*V',
                r'(?i)V(?:CC|DD)\s*:\s*([\d\.]+)\s*(?:V)?\s*(?:to|-)\s*([\d\.]+)\s*V',
                r'(?i)(?:Operating|Input|Supply|Output)\s*Voltage\s*:\s*([\d\.]+)\s*V'
            ],
            'current': [
                r'(?i)(?:Operating|Supply|Output|Max(?:imum)?)\s*Current\s*:\s*([\d\.]+)\s*(?:to|-)\s*([\d\.]+)\s*(?:m|µ|u)?A',
                r'(?i)I(?:CC|DD)\s*:\s*([\d\.]+)\s*(?:to|-)\s*([\d\.]+)\s*(?:m|µ|u)?A',
                r'(?i)(?:Operating|Supply|Output|Max(?:imum)?)\s*Current\s*:\s*([\d\.]+)\s*(?:m|µ|u)?A'
            ],
            'temperature': [
                r'(?i)(?:Operating|Storage)\s*Temp(?:erature)?\s*:\s*([-\d\.]+)\s*(?:°|deg)?C\s*(?:to|-)\s*([-\d\.]+)\s*(?:°|deg)?C',
                r'(?i)T(?:A|J)\s*:\s*([-\d\.]+)\s*(?:°|deg)?C\s*(?:to|-)\s*([-\d\.]+)\s*(?:°|deg)?C',
                r'(?i)(?:Operating|Storage)\s*Temp(?:erature)?\s*:\s*([-\d\.]+)\s*(?:°|deg)?C'
            ]
        }
    
    @lru_cache(maxsize=100)
    def _get_cache_key(self, pdf_path: str) -> str:
        """Generate a cache key for a PDF file based on its content and modification time"""
        mtime = os.path.getmtime(pdf_path)
        with open(pdf_path, 'rb') as f:
            content_hash = hashlib.md5(f.read()).hexdigest()
        return f"{content_hash}_{mtime}"
    
    def _get_cached_text(self, pdf_path: str) -> Optional[str]:
        """Get cached text content for a PDF if available"""
        cache_key = self._get_cache_key(pdf_path)
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.txt")
        
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                logger.warning(f"Failed to read cache file: {e}")
        return None
    
    def _cache_text(self, pdf_path: str, text: str) -> None:
        """Cache extracted text content from a PDF"""
        try:
            cache_key = self._get_cache_key(pdf_path)
            cache_file = os.path.join(self.cache_dir, f"{cache_key}.txt")
            with open(cache_file, 'w', encoding='utf-8') as f:
                f.write(text)
        except Exception as e:
            logger.warning(f"Failed to write cache file: {e}")
    
    def extract_from_pdf(self, pdf_path: str) -> str:
        """Extract text content from a PDF datasheet with caching"""
        if not os.path.exists(pdf_path):
            logger.error(f"PDF file not found: {pdf_path}")
            return ""
            
        # Check cache first
        cached_text = self._get_cached_text(pdf_path)
        if cached_text is not None:
            return cached_text
        
        text = ""
        try:
            with open(pdf_path, 'rb') as file:
                try:
                    reader = PyPDF2.PdfReader(file)
                except PyPDF2.PdfReadError as e:
                    logger.error(f"Invalid or corrupted PDF file: {e}")
                    return ""
                    
                # Process first 15 pages max - usually contains the important info
                pages_to_process = min(len(reader.pages), 15)
                
                for page_num in range(pages_to_process):
                    try:
                        page_text = reader.pages[page_num].extract_text()
                        # Clean up common PDF extraction issues
                        page_text = self._clean_extracted_text(page_text)
                        text += page_text + "\n"
                    except Exception as e:
                        logger.warning(f"Failed to extract text from page {page_num}: {e}")
                        continue
                
                # Cache the extracted text
                self._cache_text(pdf_path, text)
        except Exception as e:
            logger.error(f"Error extracting text from PDF: {e}")
        
        return text
    
    def _clean_extracted_text(self, text: str) -> str:
        """Clean up common issues in extracted PDF text"""
        # Remove multiple spaces
        text = re.sub(r'\s+', ' ', text)
        # Fix common encoding issues
        text = text.replace('â€"', '-')
        text = text.replace('â€™', "'")
        # Remove form feed characters
        text = text.replace('\f', '\n')
        # Fix broken numbers
        text = re.sub(r'(\d)\s+(\d)', r'\1\2', text)
        return text.strip()
    
    def extract_parameters(self, text: str) -> Dict[str, Any]:
        """Extract key component parameters from datasheet text"""
        parameters = {}
        
        # Determine component type
        component_type = self._determine_component_type(text)
        if component_type:
            parameters['type'] = component_type
        
        # Extract parameters using enhanced patterns
        for param_name, patterns in self.parameter_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    try:
                        if param_name in ['voltage', 'current', 'temperature']:
                            # Handle range values
                            if len(match.groups()) > 1 and match.group(2):
                                if param_name == 'temperature':
                                    parameters[param_name] = f"{match.group(1)}°C to {match.group(2)}°C"
                                elif param_name == 'voltage':
                                    parameters[param_name] = f"{match.group(1)}V to {match.group(2)}V"
                                else:  # current
                                    unit = 'mA' if 'mA' in match.group(0) else 'A'
                                    parameters[param_name] = f"{match.group(1)}{unit} to {match.group(2)}{unit}"
                            else:
                                if param_name == 'temperature':
                                    parameters[param_name] = f"{match.group(1)}°C"
                                elif param_name == 'voltage':
                                    parameters[param_name] = f"{match.group(1)}V"
                                else:  # current
                                    unit = 'mA' if 'mA' in match.group(0) else 'A'
                                    parameters[param_name] = f"{match.group(1)}{unit}"
                        else:
                            parameters[param_name] = match.group(1)
                        break
                    except (IndexError, AttributeError) as e:
                        logger.debug(f"Error extracting {param_name}: {e}")
                        continue
        
        # Extract pin count
        pin_count = self._extract_pin_count(text)
        if pin_count:
            parameters['pins'] = pin_count
        
        # Validate and clean parameters
        self._validate_parameters(parameters)
        
        return parameters
    
    def _extract_pin_count(self, text: str) -> Optional[int]:
        """Extract pin count from text using multiple methods"""
        # Method 1: Direct pin count statements
        pin_patterns = [
            r'(?i)Pins:\s*(\d+)',
            r'(?i)Pin Count:\s*(\d+)',
            r'(?i)Number of Pins:\s*(\d+)',
            r'(?i)(\d+)-Pin',
            r'(?i)(\d+) Pin Package'
        ]
        
        for pattern in pin_patterns:
            match = re.search(pattern, text)
            if match:
                return int(match.group(1))
        
        # Method 2: Count unique pin references
        pin_refs = re.findall(r'Pin\s*(\d+)', text, re.IGNORECASE)
        if pin_refs:
            return max(int(x) for x in pin_refs)
        
        # Method 3: Extract from package name
        package_pins = re.search(r'(?i)(SOIC|DIP|QFP|TQFP|LQFP)-(\d+)', text)
        if package_pins:
            return int(package_pins.group(2))
        
        return None
    
    def _validate_parameters(self, parameters: Dict[str, Any]) -> None:
        """Validate and clean extracted parameters"""
        if not isinstance(parameters, dict):
            logger.error("Invalid parameters type")
            return
            
        # Validate part number if present
        if 'part_number' in parameters:
            if not isinstance(parameters['part_number'], str) or len(parameters['part_number']) < 2:
                logger.warning(f"Invalid part number format: {parameters.get('part_number')}")
                del parameters['part_number']
                
        # Validate package if present
        if 'package' in parameters:
            if not isinstance(parameters['package'], str) or len(parameters['package']) < 2:
                logger.warning(f"Invalid package format: {parameters.get('package')}")
                del parameters['package']
                
        # Validate voltage
        if 'voltage' in parameters:
            voltage = parameters['voltage']
            if isinstance(voltage, str):
                # Convert to standard format
                voltage = voltage.replace(' ', '')
                if not re.match(r'^\d+\.?\d*V(?:to\d+\.?\d*V)?$', voltage):
                    logger.warning(f"Invalid voltage format: {voltage}")
                    del parameters['voltage']
        
        # Validate current
        if 'current' in parameters:
            current = parameters['current']
            if isinstance(current, str):
                current = current.replace(' ', '')
                if not re.match(r'^\d+\.?\d*(?:m)?A(?:to\d+\.?\d*(?:m)?A)?$', current):
                    logger.warning(f"Invalid current format: {current}")
                    del parameters['current']
        
        # Validate temperature
        if 'temperature' in parameters:
            temp = parameters['temperature']
            if isinstance(temp, str):
                temp = temp.replace(' ', '')
                if not re.match(r'^-?\d+\.?\d*°C(?:to-?\d+\.?\d*°C)?$', temp):
                    logger.warning(f"Invalid temperature format: {temp}")
                    del parameters['temperature']
        
        # Validate pin count
        if 'pins' in parameters:
            try:
                parameters['pins'] = int(parameters['pins'])
                if parameters['pins'] <= 0 or parameters['pins'] > 1000:
                    logger.warning(f"Invalid pin count: {parameters['pins']}")
                    del parameters['pins']
            except (ValueError, TypeError):
                logger.warning(f"Invalid pin count: {parameters['pins']}")
                del parameters['pins']
    
    def _determine_component_type(self, text: str) -> Optional[str]:
        """Determine the type of component based on keywords in the text"""
        text_lower = text.lower()
        
        # Try to find an explicit type declaration
        type_patterns = [
            r'(?i)Type:\s*([\w\s-]+)',
            r'(?i)Component Type:\s*([\w\s-]+)'
        ]
        
        for pattern in type_patterns:
            match = re.search(pattern, text)
            if match:
                declared_type = match.group(1).strip().lower()
                # Map declared type to known types
                for comp_type, keywords in self.component_types.items():
                    if any(keyword.lower() in declared_type for keyword in keywords):
                        return comp_type
        
        # Count keyword matches for each type
        type_scores = {}
        for comp_type, keywords in self.component_types.items():
            score = sum(1 for keyword in keywords if keyword.lower() in text_lower)
            if score > 0:
                type_scores[comp_type] = score
        
        # Return the type with the highest score
        if type_scores:
            return max(type_scores.items(), key=lambda x: x[1])[0]
        
        return None
    
    def detect_component_connections(self, text: str) -> Dict[str, List[Dict[str, Any]]]:
        """Identify pin connections based on datasheet content"""
        connections = []
        
        # Match pin descriptions - look for "Pin X: Description" format
        pin_pattern = r'Pin\s*(\d+)[:\s]+([A-Za-z0-9_\s/]+)'
        pin_functions = re.findall(pin_pattern, text)
        
        # Also try alternative format "[Pin Name] (X): Description"
        alt_pattern = r'([A-Za-z0-9_]+)\s*\(?(\d+)\)?[:\s]+([A-Za-z0-9_\s/]+)'
        alt_functions = re.findall(alt_pattern, text)
        
        # Process standard pin format
        for pin_num, description in pin_functions:
            connections.append({
                'number': int(pin_num),
                'description': description.strip(),
                'category': self._categorize_pin(description)
            })
        
        # Process alternative pin format if standard format didn't find anything
        if not connections:
            for pin_name, pin_num, description in alt_functions:
                connections.append({
                    'number': int(pin_num),
                    'name': pin_name.strip(),
                    'description': description.strip(),
                    'category': self._categorize_pin(description)
                })
        
        # Sort connections by pin number
        connections.sort(key=lambda x: x['number'])
        
        # Group pins by category
        power_pins = [pin for pin in connections if pin['category'] == 'power']
        ground_pins = [pin for pin in connections if pin['category'] == 'ground']
        io_pins = [pin for pin in connections if pin['category'] == 'io']
        
        return {
            'all_pins': connections,
            'power_pins': power_pins,
            'ground_pins': ground_pins,
            'io_pins': io_pins
        }
    
    def _categorize_pin(self, description: str) -> str:
        """Categorize a pin based on its description"""
        desc_lower = description.lower()
        
        if any(term in desc_lower for term in ['vcc', 'vdd', 'power', 'supply', '+v']):
            return 'power'
        elif any(term in desc_lower for term in ['gnd', 'ground', 'vss', '-v']):
            return 'ground'
        elif any(term in desc_lower for term in ['i/o', 'gpio', 'input', 'output', 'data']):
            return 'io'
        else:
            return 'other'
    
    def process_datasheet(self, source: str) -> Dict[str, Any]:
        """Process a datasheet file or text content and extract all relevant information"""
        if not source:
            logger.error("Empty source provided")
            return {
                'status': 'error',
                'error': 'Empty source provided'
            }
            
        try:
            # Determine if source is a file path or text content
            if os.path.exists(source):
                if source.lower().endswith('.pdf'):
                    text = self.extract_from_pdf(source)
                else:
                    with open(source, 'r', encoding='utf-8', errors='ignore') as f:
                        text = f.read()
            else:
                text = source
            
            # Extract parameters and connections
            parameters = self.extract_parameters(text)
            connections = self.detect_component_connections(text)
            
            return {
                'parameters': parameters,
                'connections': connections,
                'status': 'success'
            }
            
        except Exception as e:
            logger.error(f"Error processing datasheet: {e}")
            return {
                'status': 'error',
                'error': str(e)
            } 