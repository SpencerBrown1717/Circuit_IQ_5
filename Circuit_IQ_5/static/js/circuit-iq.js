// Circuit IQ - Frontend Integration with DatasheetExtractor
// Simple JavaScript implementation for handling datasheet uploads and processing

document.addEventListener('DOMContentLoaded', function() {
    // Initialize datasheet handling
    setupDatasheetHandling();
    
    // Set up the PCB design form
    document.getElementById('pcbDesignForm').addEventListener('submit', handleFormSubmit);
});

/**
 * Setup datasheet handling functionality
 */
function setupDatasheetHandling() {
    // Initial setup for existing datasheet containers
    setupFileDropAreas();
    
    // Add event listener for adding new datasheets
    document.getElementById('addDatasheet').addEventListener('click', function() {
        const datasheetList = document.getElementById('datasheetList');
        const newDatasheet = createDatasheetContainer();
        datasheetList.appendChild(newDatasheet);
        
        // Setup the new drop area
        setupFileDropArea(
            newDatasheet.querySelector('.file-drop-area'),
            newDatasheet.querySelector('.datasheet-file')
        );
        
        // Add remove functionality
        newDatasheet.querySelector('.remove-datasheet').addEventListener('click', function() {
            datasheetList.removeChild(newDatasheet);
        });
    });
}

/**
 * Create a new datasheet container element
 * @returns {HTMLElement} The created container
 */
function createDatasheetContainer() {
    const container = document.createElement('div');
    container.className = 'datasheet-container';
    container.innerHTML = `
        <div class="d-flex justify-content-between mb-3">
            <input type="text" class="form-control component-name" placeholder="Component Name (e.g., ATmega328P, LM7805)">
            <button type="button" class="btn btn-outline-secondary ms-2 remove-datasheet">
                <i class="fas fa-times"></i>
            </button>
        </div>
        <div class="file-drop-area">
            <i class="fas fa-file-pdf mb-2"></i>
            <p class="mb-1">Drag & drop component datasheet (PDF)</p>
            <small class="text-muted">or click to browse files</small>
            <input type="file" class="datasheet-file form-control d-none" accept=".pdf">
        </div>
        <div class="extracted-data mt-3" style="display: none;">
            <h6>Extracted Component Information</h6>
            <div class="extracted-parameters"></div>
        </div>
    `;
    return container;
}

/**
 * Setup all file drop areas in the document
 */
function setupFileDropAreas() {
    document.querySelectorAll('.file-drop-area').forEach(dropArea => {
        const fileInput = dropArea.querySelector('.datasheet-file');
        setupFileDropArea(dropArea, fileInput);
    });
}

/**
 * Setup a single file drop area
 * @param {HTMLElement} dropArea - The drop area element
 * @param {HTMLElement} fileInput - The file input element
 */
function setupFileDropArea(dropArea, fileInput) {
    // Click to browse files
    dropArea.addEventListener('click', () => {
        fileInput.click();
    });
    
    // File input change handler
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFile(e.target.files[0], dropArea, fileInput);
        }
    });
    
    // Drag and drop handlers
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, preventDefaults, false);
    });
    
    ['dragenter', 'dragover'].forEach(eventName => {
        dropArea.addEventListener(eventName, () => {
            dropArea.style.borderColor = '#2563eb';
            dropArea.style.backgroundColor = '#dbeafe';
        }, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, () => {
            dropArea.style.borderColor = '#e2e8f0';
            dropArea.style.backgroundColor = '#f8fafc';
        }, false);
    });
    
    // Handle file drop
    dropArea.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0) {
            handleFile(files[0], dropArea, fileInput);
        }
    }, false);
}

/**
 * Prevent default browser behavior for events
 * @param {Event} e - The event object
 */
function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

/**
 * Handle an uploaded datasheet file
 * @param {File} file - The uploaded file
 * @param {HTMLElement} dropArea - The drop area element
 * @param {HTMLElement} fileInput - The file input element
 */
function handleFile(file, dropArea, fileInput) {
    const container = dropArea.closest('.datasheet-container');
    const componentNameInput = container.querySelector('.component-name');
    const extractedDataSection = container.querySelector('.extracted-data');
    const extractedParametersDiv = container.querySelector('.extracted-parameters');
    
    // Update drop area to show file name
    dropArea.innerHTML = `
        <i class="fas fa-file-pdf mb-2"></i>
        <p class="mb-1">${file.name}</p>
        <small class="text-muted">Click to change</small>
        <input type="file" class="datasheet-file form-control d-none" accept=".pdf">
    `;
    
    // Re-attach click handler to the file input
    const newFileInput = dropArea.querySelector('.datasheet-file');
    newFileInput.addEventListener('change', function(e) {
        if (e.target.files.length > 0) {
            handleFile(e.target.files[0], dropArea, newFileInput);
        }
    });
    
    // Extract file name as potential component name if not already filled
    if (!componentNameInput.value) {
        const nameWithoutExtension = file.name.replace(/\.[^/.]+$/, "");
        const cleanedName = nameWithoutExtension.replace(/_/g, ' ');
        componentNameInput.value = cleanedName;
    }
    
    // Create FormData and send to server
    const formData = new FormData();
    formData.append('datasheets', file);
    
    // Show loading state
    extractedDataSection.style.display = 'block';
    extractedParametersDiv.innerHTML = `
        <div class="text-center">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <p class="mt-2">Processing datasheet...</p>
        </div>
    `;
    
    // Send to server
    fetch('/api/process-datasheets', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success && data.components && data.components.length > 0) {
            displayExtractedParameters(data.components[0], extractedParametersDiv);
        } else {
            throw new Error(data.error || 'Failed to process datasheet');
        }
    })
    .catch(error => {
        extractedParametersDiv.innerHTML = `
            <div class="alert alert-warning">
                <i class="fas fa-exclamation-triangle me-2"></i>
                ${error.message}
            </div>
        `;
    });
}

/**
 * Display extracted parameters in the UI
 * @param {Object} component - The component data
 * @param {HTMLElement} container - The container element to display in
 */
function displayExtractedParameters(component, container) {
    if (!component) {
        container.innerHTML = '<div class="alert alert-warning">No data could be extracted</div>';
        return;
    }
    
    let html = '<div class="card p-3 bg-light">';
    
    // Add parameters
    for (const [key, value] of Object.entries(component)) {
        if (value && value !== 'Unknown' && typeof value !== 'object') {
            html += `<div><strong>${key.replace('_', ' ')}:</strong> ${value}</div>`;
        }
    }
    
    // Add pins if available
    if (component.connections && component.connections.all_pins && component.connections.all_pins.length > 0) {
        html += '<div class="mt-2"><strong>Pins:</strong>';
        html += '<div class="small">';
        
        // Only show first 5 pins if there are many
        const pinsToShow = component.connections.all_pins.slice(0, 5);
        pinsToShow.forEach(pin => {
            html += `<div>Pin ${pin.number}: ${pin.description}</div>`;
        });
        
        if (component.connections.all_pins.length > 5) {
            html += `<div>...and ${component.connections.all_pins.length - 5} more pins</div>`;
        }
        
        html += '</div></div>';
    }
    
    html += '</div>';
    container.innerHTML = html;
}

/**
 * Handle form submission (generate PCB design)
 * @param {Event} e - The form submit event
 */
function handleFormSubmit(e) {
    e.preventDefault();
    
    // Hide empty state and any previous errors
    document.getElementById('emptyState').style.display = 'none';
    document.getElementById('errorContainer').style.display = 'none';
    document.getElementById('outputContainer').style.display = 'none';
    
    // Show loading indicator
    document.getElementById('loadingIndicator').style.display = 'block';
    
    // Collect form data
    const projectName = document.getElementById('projectName').value || 'Untitled PCB';
    const requirements = document.getElementById('requirements').value;
    const boardWidth = document.getElementById('boardWidth').value;
    const boardHeight = document.getElementById('boardHeight').value;
    const boardLayers = document.getElementById('boardLayers').value;
    
    // Validate requirements
    if (!requirements) {
        showError('Please describe your circuit requirements');
        return;
    }
    
    // Collect component information
    const components = [];
    document.querySelectorAll('.datasheet-container').forEach(container => {
        const name = container.querySelector('.component-name').value.trim();
        const extractedData = container.querySelector('.extracted-parameters');
        
        if (name) {
            // Try to get extracted data if available
            let componentData = { name };
            try {
                const extractedHtml = extractedData.innerHTML;
                if (extractedHtml && !extractedHtml.includes('alert-warning')) {
                    componentData.extracted = true;
                }
            } catch (e) {
                console.warn('Could not parse extracted data:', e);
            }
            components.push(componentData);
        }
    });
    
    // Prepare request data
    const requestData = {
        project_name: projectName,
        requirements: requirements,
        board_params: {
            width: parseFloat(boardWidth),
            height: parseFloat(boardHeight),
            layers: parseInt(boardLayers)
        },
        components: components
    };
    
    // Send to server
    fetch('/api/generate-design', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showGeneratedDesign(data.design);
        } else {
            throw new Error(data.error || 'Failed to generate design');
        }
    })
    .catch(error => {
        showError(error.message);
    });
}

/**
 * Show an error message
 * @param {string} message - The error message
 */
function showError(message) {
    document.getElementById('loadingIndicator').style.display = 'none';
    document.getElementById('emptyState').style.display = 'block';
    
    const errorContainer = document.getElementById('errorContainer');
    errorContainer.style.display = 'block';
    errorContainer.innerHTML = `<i class="fas fa-exclamation-circle me-2"></i> ${message}`;
}

/**
 * Display the generated PCB design
 * @param {Object} design - The design data from the server
 */
function showGeneratedDesign(design) {
    document.getElementById('loadingIndicator').style.display = 'none';
    
    const outputContainer = document.getElementById('outputContainer');
    outputContainer.style.display = 'block';
    
    // Display PCB preview image
    const pcbPreview = document.getElementById('pcbPreview');
    pcbPreview.src = design.preview_url || generatePreviewImageUrl(design, 'front');
    
    // Set up view buttons
    document.getElementById('viewFront').classList.add('active');
    document.getElementById('viewBack').classList.remove('active');
    
    document.getElementById('viewFront').addEventListener('click', function() {
        pcbPreview.src = generatePreviewImageUrl(design, 'front');
        this.classList.add('active');
        document.getElementById('viewBack').classList.remove('active');
    });
    
    document.getElementById('viewBack').addEventListener('click', function() {
        pcbPreview.src = generatePreviewImageUrl(design, 'back');
        this.classList.add('active');
        document.getElementById('viewFront').classList.remove('active');
    });
    
    // Populate Gerber files table
    const gerberList = document.getElementById('gerberFilesList');
    gerberList.innerHTML = '';
    
    if (design.gerber_files && design.gerber_files.length > 0) {
        design.gerber_files.forEach(file => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${file.name}</td>
                <td>${file.description || 'Gerber file'}</td>
                <td>
                    <a href="${file.url}" class="btn btn-sm btn-outline-secondary" download>
                        <i class="fas fa-download"></i>
                    </a>
                </td>
            `;
            gerberList.appendChild(row);
        });
    }
    
    // Setup "Download All" button for Gerber zip file
    const downloadAllBtn = document.getElementById('downloadAllBtn');
    if (design.gerber_zip_url) {
        downloadAllBtn.addEventListener('click', function() {
            window.location.href = design.gerber_zip_url;
        });
        downloadAllBtn.disabled = false;
    } else {
        downloadAllBtn.disabled = true;
        downloadAllBtn.title = "Gerber zip file not available";
    }
    
    // Show design suggestions
    if (design.suggestions && design.suggestions.length > 0) {
        const suggestionsContainer = document.getElementById('suggestionsContainer');
        const suggestionsList = document.getElementById('suggestionsList');
        
        suggestionsList.innerHTML = '';
        design.suggestions.forEach(suggestion => {
            const item = document.createElement('div');
            item.className = 'alert alert-info mb-2';
            item.innerHTML = `<i class="fas fa-lightbulb me-2"></i> ${suggestion}`;
            suggestionsList.appendChild(item);
        });
        
        suggestionsContainer.style.display = 'block';
    }
}

/**
 * Generate a URL for a PCB preview image
 * @param {Object} design - The design data
 * @param {string} view - The view type ('front' or 'back')
 * @returns {string} The preview image URL
 */
function generatePreviewImageUrl(design, view = 'front') {
    // If we have a direct preview URL, use it for front view
    if (view === 'front' && design.preview_url) {
        return design.preview_url;
    }
    
    const width = Math.round(design.board_params?.width || 100);
    const height = Math.round(design.board_params?.height || 80);
    
    // For demo, use placeholder image with parameters
    const color = view === 'front' ? '1e8f5e' : '2563eb';
    
    // Include component names in the placeholder text
    let componentText = '';
    if (design.components && design.components.length > 0) {
        componentText = ' with ' + design.components.map(c => c.name).join(', ');
        if (componentText.length > 30) {
            componentText = componentText.substring(0, 30) + '...';
        }
    }
    
    return `https://via.placeholder.com/600x400/${color}/ffffff?text=PCB+${width}x${height}mm${componentText}`;
}

/**
 * Add text to the requirements field based on a template
 * @param {string} suggestion - The template suggestion to add
 */
window.addSuggestion = function(suggestion) {
    const requirementsField = document.getElementById('requirements');
    if (requirementsField.value.trim() === '') {
        switch(suggestion) {
            case 'Arduino':
                requirementsField.value = 'An Arduino-based circuit that reads from analog sensors and controls multiple LEDs. It should be powered by a 9V battery with an on/off switch.';
                break;
            case 'Power Supply':
                requirementsField.value = 'A power supply circuit that converts 120V AC to 5V and 3.3V DC with at least 1A current capacity for each output. Include proper filtering and safety features.';
                break;
            case 'LED Controller':
                requirementsField.value = 'An LED controller that can drive 8 high-power RGB LEDs with individual brightness control. The circuit should accept 12V input and include proper current limiting for each channel.';
                break;
            case 'Sensor Interface':
                requirementsField.value = 'A sensor interface board that can connect to temperature, humidity, and pressure sensors. It should include signal conditioning circuits and an I2C interface to connect to a main control board.';
                break;
            case 'Motor Driver':
                requirementsField.value = 'A motor driver circuit for two DC motors with direction control and PWM speed adjustment. The circuit should handle motors that operate at 6-12V with up to 2A current draw each.';
                break;
        }
    } else {
        // If there's already text, ask before replacing
        if (confirm('Replace current description with template?')) {
            switch(suggestion) {
                case 'Arduino':
                    requirementsField.value = 'An Arduino-based circuit that reads from analog sensors and controls multiple LEDs. It should be powered by a 9V battery with an on/off switch.';
                    break;
                case 'Power Supply':
                    requirementsField.value = 'A power supply circuit that converts 120V AC to 5V and 3.3V DC with at least 1A current capacity for each output. Include proper filtering and safety features.';
                    break;
                case 'LED Controller':
                    requirementsField.value = 'An LED controller that can drive 8 high-power RGB LEDs with individual brightness control. The circuit should accept 12V input and include proper current limiting for each channel.';
                    break;
                case 'Sensor Interface':
                    requirementsField.value = 'A sensor interface board that can connect to temperature, humidity, and pressure sensors. It should include signal conditioning circuits and an I2C interface to connect to a main control board.';
                    break;
                case 'Motor Driver':
                    requirementsField.value = 'A motor driver circuit for two DC motors with direction control and PWM speed adjustment. The circuit should handle motors that operate at 6-12V with up to 2A current draw each.';
                    break;
            }
        }
    }
};