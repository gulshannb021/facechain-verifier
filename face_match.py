import os
import sys
import urllib.request
import tempfile

import cv2
import numpy as np


# ------------------------------------------------------------
# Paths to existing Person A models
# ------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DETECTOR_PROTO = os.path.join(
    BASE_DIR,
    "models",
    "face_detection.prototxt"
)

DETECTOR_MODEL = os.path.join(
    BASE_DIR,
    "models",
    "face_detection.caffemodel"
)

FACE_MODEL = os.path.join(
    BASE_DIR,
    "models",
    "face_recognition_sface_2021dec.onnx"
)


# ------------------------------------------------------------
# Face Match Verifier
# ------------------------------------------------------------

class FaceMatchVerifier:

    def __init__(self, threshold=0.45):

        self.threshold = threshold

        if not os.path.exists(DETECTOR_PROTO):
            raise FileNotFoundError(
                f"Missing face detector prototxt: {DETECTOR_PROTO}"
            )

        if not os.path.exists(DETECTOR_MODEL):
            raise FileNotFoundError(
                f"Missing face detector model: {DETECTOR_MODEL}"
            )

        if not os.path.exists(FACE_MODEL):
            raise FileNotFoundError(
                f"Missing face recognition model: {FACE_MODEL}"
            )

        # Load face detector
        self.detector = cv2.dnn.readNetFromCaffe(
            DETECTOR_PROTO,
            DETECTOR_MODEL
        )

        # Load SFace recognition model
        self.recognizer = cv2.FaceRecognizerSF_create(
            FACE_MODEL,
            ""
        )

    # --------------------------------------------------------
    # Load image from local path or URL
    # --------------------------------------------------------

    def load_image(self, image_input):

        # Local image
        if os.path.isfile(image_input):

            image = cv2.imread(image_input)

            if image is None:
                raise ValueError(
                    f"Could not read image: {image_input}"
                )

            return image

        # URL image
        if image_input.startswith(("http://", "https://")):

            try:
                request = urllib.request.Request(
                    image_input,
                    headers={
                        "User-Agent": "Mozilla/5.0"
                    }
                )

                with urllib.request.urlopen(
                    request,
                    timeout=15
                ) as response:

                    image_bytes = response.read()

                array = np.frombuffer(
                    image_bytes,
                    dtype=np.uint8
                )

                image = cv2.imdecode(
                    array,
                    cv2.IMREAD_COLOR
                )

                if image is None:
                    raise ValueError(
                        "Downloaded file is not a valid image."
                    )

                return image

            except Exception as error:
                raise ValueError(
                    f"Could not download image: {error}"
                )

        raise FileNotFoundError(
            f"Image not found: {image_input}"
        )

    # --------------------------------------------------------
    # Detect faces
    # --------------------------------------------------------

    def detect_faces(self, image):

        h, w = image.shape[:2]

        blob = cv2.dnn.blobFromImage(
            cv2.resize(image, (300, 300)),
            1.0,
            (300, 300),
            (104.0, 177.0, 123.0)
        )

        self.detector.setInput(blob)

        detections = self.detector.forward()

        faces = []

        for i in range(detections.shape[2]):

            confidence = float(
                detections[0, 0, i, 2]
            )

            if confidence < 0.5:
                continue

            box = detections[
                0, 0, i, 3:7
            ] * np.array(
                [w, h, w, h]
            )

            x1, y1, x2, y2 = box.astype(int)

            x1 = max(0, min(x1, w - 1))
            y1 = max(0, min(y1, h - 1))
            x2 = max(0, min(x2, w))
            y2 = max(0, min(y2, h))

            if x2 <= x1 or y2 <= y1:
                continue

            faces.append(
                {
                    "box": (x1, y1, x2, y2),
                    "confidence": confidence
                }
            )

        return faces

    # --------------------------------------------------------
    # Get SFace embedding
    # --------------------------------------------------------

    def get_feature(self, image, face):

        x1, y1, x2, y2 = face["box"]

        face_box = np.array(
            [x1, y1, x2 - x1, y2 - y1],
            dtype=np.int32
        )

        aligned_face = self.recognizer.alignCrop(
            image,
            face_box
        )

        feature = self.recognizer.feature(
            aligned_face
        )

        return feature

    # --------------------------------------------------------
    # Compare two faces
    # --------------------------------------------------------

    def compare(self, feature1, feature2):

        score = self.recognizer.match(
            feature1,
            feature2,
            cv2.FaceRecognizerSF_FR_COSINE
        )

        return float(score)

    # --------------------------------------------------------
    # Verify input face against candidate images
    # --------------------------------------------------------

    def verify(
        self,
        input_image,
        candidate_images
    ):

        source_image = self.load_image(
            input_image
        )

        source_faces = self.detect_faces(
            source_image
        )

        if not source_faces:

            print(
                "❌ No face detected in input image."
            )

            return False, 0.0, None

        # Use the largest face from input
        source_face = max(
            source_faces,
            key=lambda f:
                (f["box"][2] - f["box"][0])
                *
                (f["box"][3] - f["box"][1])
        )

        source_feature = self.get_feature(
            source_image,
            source_face
        )

        best_score = -1.0
        best_image = None

        for candidate in candidate_images:

            try:

                print(
                    f"Checking candidate image: {candidate}"
                )

                candidate_image = self.load_image(
                    candidate
                )

                candidate_faces = self.detect_faces(
                    candidate_image
                )

                if not candidate_faces:

                    print(
                        "  ❌ No face found in candidate."
                    )

                    continue

                for candidate_face in candidate_faces:

                    candidate_feature = self.get_feature(
                        candidate_image,
                        candidate_face
                    )

                    score = self.compare(
                        source_feature,
                        candidate_feature
                    )

                    print(
                        f"  Similarity: {score:.4f}"
                    )

                    if score > best_score:

                        best_score = score
                        best_image = candidate

            except Exception as error:

                print(
                    f"  ⚠️ Could not check candidate: {error}"
                )

        matched = (
            best_score >= self.threshold
        )

        return (
            matched,
            max(best_score, 0.0),
            best_image
        )


# ------------------------------------------------------------
# Command-line test
# ------------------------------------------------------------

def main():

    if len(sys.argv) != 3:

        print(
            "Usage:"
        )

        print(
            "python face_match.py "
            "<input_face> <candidate_image>"
        )

        sys.exit(1)

    input_face = sys.argv[1]
    candidate_image = sys.argv[2]

    print("=" * 60)
    print("FACE MATCH VERIFICATION")
    print("=" * 60)

    print(
        f"Input face:      {input_face}"
    )

    print(
        f"Candidate image: {candidate_image}"
    )

    try:

        verifier = FaceMatchVerifier(
            threshold=0.45
        )

        matched, similarity, matched_image = (
            verifier.verify(
                input_face,
                [candidate_image]
            )
        )

        print("\n" + "=" * 60)

        print(
            f"Best similarity: {similarity:.4f}"
        )

        print(
            f"Threshold:       {verifier.threshold:.2f}"
        )

        if matched:

            print(
                "✅ FACE MATCH CONFIRMED"
            )

            print(
                f"Matched image: {matched_image}"
            )

        else:

            print(
                "❌ FACE MATCH REJECTED"
            )

        print("=" * 60)

    except Exception as error:

        print(
            f"\n❌ Face matching failed: {error}"
        )

        sys.exit(1)


if __name__ == "__main__":
    main()