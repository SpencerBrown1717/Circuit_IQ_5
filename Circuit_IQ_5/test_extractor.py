from datasheet_extractor import DatasheetExtractor

def validate_component_params(component):
    """Verify component parameters are within reasonable ranges"""
    warnings = []
    
    # Check voltage ranges
    if 'voltage' in component:
        voltage_str = component['voltage']
        try:
            voltage_vals = [float(v.replace('V', '')) for v in voltage_str.split(' to ')]
            if max(voltage_vals) > 50:
                warnings.append(f"High voltage component ({voltage_str}) - verify clearance requirements")
        except (ValueError, AttributeError):
            warnings.append(f"Unable to validate voltage format: {voltage_str}")
    
    # Check pin count
    if 'pins' in component and isinstance(component['pins'], (int, float)) and component['pins'] > 100:
        warnings.append(f"High pin count ({component['pins']}) - verify routing density")
    
    # Check current ratings
    if 'current' in component:
        current_str = component['current']
        try:
            # Extract numeric value regardless of unit
            if 'mA' in current_str:
                current_val = float(current_str.replace('mA', '').split(' to ')[0])
                current_val /= 1000  # Convert to A
            else:
                current_val = float(current_str.replace('A', '').split(' to ')[0])
                
            if component.get('type') == 'regulator' and current_val < 0.1:  # Less than 100mA
                warnings.append(f"Low current capacity regulator ({current_str}) - verify power requirements")
        except (ValueError, AttributeError):
            warnings.append(f"Unable to validate current format: {current_str}")
            
    return warnings

def check_signal_integrity(component, connections):
    """Check for high-speed signals that might need special routing"""
    warnings = []
    
    # Check for high-speed components
    if component.get('type', '').lower() in ['microcontroller', 'processor', 'fpga']:
        # Check for high-speed interfaces in pin descriptions
        high_speed_keywords = ['usb', 'ethernet', 'diff', 'lvds', 'hdmi', 'ddr', 'pcie']
        high_speed_pins = []
        
        for pin in connections.get('all_pins', []):
            desc = pin.get('description', '').lower()
            if any(keyword in desc for keyword in high_speed_keywords):
                high_speed_pins.append(pin.get('number', 'unknown'))
                
        if high_speed_pins:
            warnings.append(f"High-speed signals detected on pins {', '.join(map(str, high_speed_pins))} - "
                          f"trace length matching and controlled impedance recommended")
    
    return warnings

def test_basic_extraction():
    # Create an instance of DatasheetExtractor
    extractor = DatasheetExtractor()
    
    # Test sample text
    sample_text = """
    ATmega328P Microcontroller
    
    Type: Microcontroller
    Part Number: ATmega328P
    Package: PDIP-28
    Pins: 28
    
    Operating Voltage: 1.8V to 5.5V
    Maximum Current: 200mA
    Operating Temperature: -40°C to 85°C
    
    Pin Configuration:
    Pin 1: RESET
    Pin 7: VCC
    Pin 8: GND
    Pin 9: Crystal1
    Pin 10: Crystal2
    """
    
    # Process the sample text
    result = extractor.process_datasheet(sample_text)
    
    # Check if processing was successful
    if result.get('status') != 'success':
        print(f"Error processing datasheet: {result.get('error', 'Unknown error')}")
        return
    
    # Print results
    print("\nExtracted Parameters:")
    print("-" * 20)
    for key, value in result['parameters'].items():
        print(f"{key}: {value}")
    
    # Validate component parameters
    warnings = validate_component_params(result['parameters'])
    
    # Check signal integrity requirements
    if 'connections' in result:
        signal_warnings = check_signal_integrity(result['parameters'], result['connections'])
        warnings.extend(signal_warnings)
    
    # Display warnings if any
    if warnings:
        print("\nPCB Design Warnings:")
        print("-" * 20)
        for warning in warnings:
            print(f"WARNING: {warning}")
    
    print("\nPin Connections:")
    print("-" * 20)
    if 'connections' in result and 'all_pins' in result['connections']:
        for pin in result['connections']['all_pins']:
            print(f"Pin {pin['number']}: {pin.get('description', '')}")
            
            # Check for power/ground pins that need special consideration
            desc = pin.get('description', '').lower()
            if any(term in desc for term in ['vcc', 'vdd', 'power', '+v']):
                print(f"  NOTE: Power pin - ensure proper decoupling")
            elif any(term in desc for term in ['gnd', 'ground', 'vss']):
                print(f"  NOTE: Ground pin - ensure proper connectivity to ground plane")
    else:
        print("No pin connections found")

if __name__ == "__main__":
    test_basic_extraction()