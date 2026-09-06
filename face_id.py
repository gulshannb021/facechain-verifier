import cv2
import json
import sys
import os

def process_face(image_path, out_json="face_data.json", out_face="face.jpg"):
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Could not read image: {image_path}")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Haar Cascade face detector, bundled with opencv-python
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)

    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))

    if len(faces) == 0:
        result = {"face_detected": False, "source_image": image_path}
        with open(out_json, "w") as f:
            json.dump(result, f, indent=2)
        print("No face detected.")
        return result

    # Take the first detected face
    x, y, w, h = faces[0]
    left, top, right, bottom = x, y, x + w, y + h

    cropped = image[top:bottom, left:right]
    cv2.imwrite(out_face, cropped)

    result = {
        "face_detected": True,
        "source_image": image_path,
        "bounding_box": {"top": int(top), "right": int(right), "bottom": int(bottom), "left": int(left)},
        "cropped_face_path": out_face
    }

    with open(out_json, "w") as f:
        json.dump(result, f, indent=2)

    print(f"Face detected. Saved to {out_json} and {out_face}")
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python face_id.py <image_path>")
        sys.exit(1)

    image_path = sys.argv[1]
    if not os.path.exists(image_path):
        print(f"File not found: {image_path}")
        sys.exit(1)

    process_face(image_path)