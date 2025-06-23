"""
QR code generation utilities
"""

import qrcode
from pathlib import Path
from PIL import Image
import base64
import io


def generate_qr_code(data: str, output_path: str = None) -> str:
    """Generate QR code from data"""
    try:
        # Create QR code instance
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        
        # Add data
        qr.add_data(data)
        qr.make(fit=True)
        
        # Create image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Save if path provided
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            img.save(output_path)
            return output_path
        
        return "QR code generated in memory"
        
    except Exception as e:
        print(f"Error generating QR code: {e}")
        return "QR code generation failed"


def display_qr_in_terminal(data: str):
    """Display QR code in terminal using ASCII characters"""
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=1,
        )
        qr.add_data(data)
        qr.make(fit=True)
        
        # Print QR code to terminal
        qr.print_ascii(invert=True)
        
    except Exception as e:
        print(f"Error displaying QR code in terminal: {e}")


def qr_from_canvas_data(canvas_data: str, output_path: str) -> str:
    """Convert canvas data URL to QR code image"""
    try:
        if canvas_data.startswith("data:image/png;base64,"):
            # Extract base64 data
            base64_data = canvas_data.split(",")[1]
            
            # Decode and save
            image_data = base64.b64decode(base64_data)
            
            # Save to file
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(image_data)
            
            return output_path
        
        return "Invalid canvas data format"
        
    except Exception as e:
        return f"Error processing canvas data: {e}"