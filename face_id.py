import cv2
import json
import sys
import os
import numpy as np


# --------------------------------------------------
# Model paths
# --------------------------------------------------

FACE_DETECTOR_CONFIG = "models/face_detection.prototxt"
FACE_DETECTOR_MODEL = "models/face_detection.caffemodel"

FACE_RECOGNITION_MODEL = (
    "models/face_recognition_sface_2021dec.onnx"
)


# --------------------------------------------------
# Face processing
# --------------------------------------------------

def process_face(
    image_path,
    out_json="face_data.json",
    out_face="face.jpg"
):
    # --------------------------------------------------
    # 1. Read input image
    # --------------------------------------------------

    image = cv2.imread(image_path)

    if image is None:
        raise ValueError(
            f"Could not read image: {image_path}"
        )

    image_height, image_width = image.shape[:2]

    # --------------------------------------------------
    # 2. Check required models
    # --------------------------------------------------

    if not os.path.exists(FACE_DETECTOR_CONFIG):
        raise FileNotFoundError(
            f"Face detector config not found: "
            f"{FACE_DETECTOR_CONFIG}"
        )

    if not os.path.exists(FACE_DETECTOR_MODEL):
        raise FileNotFoundError(
            f"Face detector model not found: "
            f"{FACE_DETECTOR_MODEL}"
        )

    if not os.path.exists(FACE_RECOGNITION_MODEL):
        raise FileNotFoundError(
            f"Face recognition model not found: "
            f"{FACE_RECOGNITION_MODEL}"
        )

    # --------------------------------------------------
    # 3. Load face detector
    # --------------------------------------------------

    face_net = cv2.dnn.readNetFromCaffe(
        FACE_DETECTOR_CONFIG,
        FACE_DETECTOR_MODEL
    )

    # --------------------------------------------------
    # 4. Prepare image for DNN detector
    # --------------------------------------------------

    blob = cv2.dnn.blobFromImage(
        cv2.resize(
            image,
            (300, 300)
        ),
        1.0,
        (300, 300),
        (104.0, 177.0, 123.0)
    )

    face_net.setInput(blob)

    detections = face_net.forward()

    # --------------------------------------------------
    # 5. Find detected faces
    # --------------------------------------------------

    faces = []

    for i in range(
        detections.shape[2]
    ):

        confidence = float(
            detections[0, 0, i, 2]
        )

        # Ignore weak detections
        if confidence < 0.5:
            continue

        box = (
            detections[0, 0, i, 3:7]
            * [
                image_width,
                image_height,
                image_width,
                image_height
            ]
        )

        x1, y1, x2, y2 = box.astype(int)

        # Keep coordinates inside image
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(image_width, x2)
        y2 = min(image_height, y2)

        width = x2 - x1
        height = y2 - y1

        if width > 0 and height > 0:
            faces.append(
                {
                    "x": x1,
                    "y": y1,
                    "width": width,
                    "height": height,
                    "confidence": confidence
                }
            )

    # --------------------------------------------------
    # 6. No face found
    # --------------------------------------------------

    if len(faces) == 0:

        result = {
            "face_detected": False,
            "source_image": image_path,
            "encoding": None
        }

        with open(
            out_json,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                result,
                f,
                indent=2
            )

        print("No face detected.")

        return result

    # --------------------------------------------------
    # 7. Select the largest detected face
    # --------------------------------------------------

    face = max(
        faces,
        key=lambda item:
        item["width"] * item["height"]
    )

    x = face["x"]
    y = face["y"]
    w = face["width"]
    h = face["height"]

    confidence = face["confidence"]

    # --------------------------------------------------
    # 8. Bounding box
    # --------------------------------------------------

    left = x
    top = y
    right = x + w
    bottom = y + h

    # --------------------------------------------------
    # 9. Crop face
    # --------------------------------------------------

    cropped = image[
        top:bottom,
        left:right
    ]

    if cropped.size == 0:
        raise ValueError(
            "Detected face crop is empty."
        )

    # --------------------------------------------------
    # 10. Save cropped face
    # --------------------------------------------------

    success = cv2.imwrite(
        out_face,
        cropped
    )

    if not success:
        raise IOError(
            f"Could not save face image: {out_face}"
        )

    # --------------------------------------------------
    # 11. Load SFace recognition model
    # --------------------------------------------------

    recognizer = cv2.FaceRecognizerSF_create(
        FACE_RECOGNITION_MODEL,
        ""
    )

    # --------------------------------------------------
    # 12. Align face
    # --------------------------------------------------

    import numpy as np

    face_box = np.array(
    [left, top, w, h],
    dtype=np.int32
    )

    aligned_face = recognizer.alignCrop(
        image,
        face_box
    )

    # --------------------------------------------------
    # 13. Generate face encoding
    # --------------------------------------------------

    encoding = recognizer.feature(
        aligned_face
    )

    encoding_list = (
        encoding
        .flatten()
        .astype(float)
        .tolist()
    )

    # --------------------------------------------------
    # 14. Build face_data.json
    # --------------------------------------------------

    result = {
        "face_detected": True,

        "source_image": image_path,

        "bounding_box": {
            "top": int(top),
            "right": int(right),
            "bottom": int(bottom),
            "left": int(left)
        },

        "detection_confidence": confidence,

        "cropped_face_path": out_face,

        "encoding": encoding_list,

        "encoding_model": (
            "OpenCV SFace "
            "face_recognition_sface_2021dec.onnx"
        ),

        "encoding_dimensions": len(
            encoding_list
        )
    }

    # --------------------------------------------------
    # 15. Save JSON
    # --------------------------------------------------

    with open(
        out_json,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            result,
            f,
            indent=2
        )

    # --------------------------------------------------
    # 16. Print result
    # --------------------------------------------------

    print(
        "Face detected successfully."
    )

    print(
        f"Detection confidence: "
        f"{confidence:.3f}"
    )

    print(
        f"Bounding box: "
        f"top={top}, right={right}, "
        f"bottom={bottom}, left={left}"
    )

    print(
        f"Saved cropped face: {out_face}"
    )

    print(
        f"Saved face data: {out_json}"
    )

    print(
        f"Encoding dimensions: "
        f"{len(encoding_list)}"
    )

    return result


# --------------------------------------------------
# Command-line entry point
# --------------------------------------------------

if __name__ == "__main__":

    if len(sys.argv) < 2:

        print(
            "Usage: "
            "python face_id.py <image_path>"
        )

        sys.exit(1)

    image_path = sys.argv[1]

    if not os.path.exists(image_path):

        print(
            f"File not found: {image_path}"
        )

        sys.exit(1)

    try:

        process_face(
            image_path
        )

    except Exception as error:

        print(
            f"\nERROR: {error}"
        )

        sys.exit(1)

    if len(sys.argv) < 2:

        print(
            "Usage: "
            "python face_id.py <image_path>"
        )

        sys.exit(1)

    image_path = sys.argv[1]

    if not os.path.exists(image_path):

        print(
            f"File not found: {image_path}"
        )

        sys.exit(1)

    process_face(image_path)

"""import cv2
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

    process_face(image_path)  _____________          replacing code with new relaiable one           ________________"""