import os
from pathlib import Path
from typing import List, Dict, Any

# Define model path
MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "models" / "best.pt"

# Initialize model variable
_model = None

# Class names as specified
CLASS_NAMES = [
    "cucumber", "tomato", "green_beans", "lemon", "eggplant", "green_chilli",
    "turnip", "coriander", "pumpkin", "potato", "cauliflower", "green_papaya",
    "bitter_gourd", "carrot", "bottle_gourd", "capsicum", "beetroot", "cabbage",
    "spring_onion", "snake_gourd", "radish", "green_banana"
]

def format_class_name(name: str) -> str:
    """Convert 'green_beans' to 'Green Beans'."""
    return name.replace('_', ' ').title()

def load_model():
    global _model
    if _model is not None:
        return _model
    
    if not MODEL_PATH.exists():
        return None
        
    try:
        from ultralytics import YOLO  # optional dependency (requirements-ml.txt)
    except ImportError:
        return None
    try:
        _model = YOLO(str(MODEL_PATH))
        return _model
    except Exception as e:
        print(f"Failed to load detection model: {type(e).__name__}")
        return None

def detect_ingredients(image_bytes: bytes, conf_threshold: float = 0.25) -> List[Dict[str, Any]]:
    model = load_model()
    if model is None:
        raise RuntimeError("Detection model is not available")
        
    import cv2
    import numpy as np
    
    # Decode image
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        raise ValueError("Invalid image data")
        
    # Run inference
    results = model.predict(source=img, conf=conf_threshold, verbose=False)
    
    detections = []
    
    if len(results) > 0:
        result = results[0]
        boxes = result.boxes
        
        for box in boxes:
            cls_id = int(box.cls[0].item())
            conf = float(box.conf[0].item())
            
            # Ensure class ID is within range, fallback to model's names if out of range
            if 0 <= cls_id < len(CLASS_NAMES):
                class_name = CLASS_NAMES[cls_id]
            else:
                class_name = result.names.get(cls_id, f"unknown_{cls_id}")
                
            display_name = format_class_name(class_name)
            
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            
            detections.append({
                "ingredient_id": class_name,
                "name": class_name,
                "display_name": display_name,
                "confidence": round(conf, 2),
                "bbox": {
                    "x1": int(x1),
                    "y1": int(y1),
                    "x2": int(x2),
                    "y2": int(y2)
                }
            })
            
    return detections
