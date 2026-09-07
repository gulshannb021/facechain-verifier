# 🔗 FaceChain Verifier

### 🧠 AI-Powered Face Discovery × 🌐 Web Search × ⛓️ Blockchain Verification

**FaceChain Verifier** is an end-to-end verification pipeline that connects **face identification, reverse-image/post discovery, cryptographic fingerprinting, and blockchain verification** into a single workflow.

Instead of simply finding a face or a social-media post, the system creates a **verifiable digital fingerprint** of the discovered content and records that fingerprint on-chain.

> **Find it. Fingerprint it. Store it. Verify it. 🔐**

---

## ✨ What Does It Do?

Given an input image containing a person, FaceChain Verifier automatically:

```text
📷 Input Image
      │
      ▼
🧠 Face Detection & Recognition
      │
      ▼
🌐 Reverse Image / Web Discovery
      │
      ▼
📄 Structured Post Data
      │
      ▼
🔐 SHA-256 Fingerprint
      │
      ▼
⛓️ Blockchain Storage
      │
      ▼
✅ Integrity Verification
```

The complete pipeline can be executed with **one command**.

---

## 🚀 Key Features

| Feature                      | Description                                                       |
| ---------------------------- | ----------------------------------------------------------------- |
| 🧠 **Face Detection**        | Detects faces from the supplied image                             |
| 🎯 **Face Extraction**       | Automatically selects and crops the detected face                 |
| 🔍 **Face Encoding**         | Generates a 128-dimensional face representation                   |
| 🌐 **Reverse Search**        | Searches the web for matching image/content sources               |
| 📱 **Social Discovery**      | Extracts supported social/web post information                    |
| 🧹 **Data Normalization**    | Converts discovered data into a consistent structure              |
| 🔐 **SHA-256 Hashing**       | Generates a deterministic content fingerprint                     |
| ⛓️ **Blockchain Storage**    | Stores the fingerprint on an Ethereum-compatible blockchain       |
| 🔎 **On-Chain Verification** | Recalculates and verifies the fingerprint against blockchain data |
| 🛡️ **Retry Handling**       | Handles transient HTTP failures and rate limits                   |
| 🧪 **Automated Tests**       | Includes tests for the post-discovery pipeline                    |

---

# 🏗️ Architecture

FaceChain Verifier is divided into three major stages.

### 👤 Face Identification

Responsible for extracting the face from the input image.

```text
Input Image
     │
     ▼
Face Detection
     │
     ▼
Largest Face Selection
     │
     ▼
Face Alignment
     │
     ▼
Face Encoding
     │
     ├──► face.jpg
     └──► face_data.json
```

---

### 🔎 Post Discovery

Receives the extracted face and searches for related online content.

```text
face.jpg
   │
   ▼
Reverse Image Search
   │
   ├── Hacker News
   ├── Bluesky
   ├── Reddit
   └── GitHub
   │
   ▼
Post Extraction
   │
   ▼
Validation & Deduplication
   │
   ▼
Canonical Post Data
```

The discovery engine is designed around **dynamic provider selection** rather than depending on one hardcoded source.

---

### ⛓️ Blockchain Verification

Receives the canonical post data and creates a cryptographic fingerprint.

```text
Canonical Post
      │
      ▼
Deterministic JSON
      │
      ▼
SHA-256
      │
      ▼
bytes32
      │
      ▼
Smart Contract
      │
      ▼
Blockchain
```

During verification:

```text
Current Post
     │
     ▼
SHA-256
     │
     ▼
Calculated Hash
     │
     │       Compare
     ├──────────────────┐
     │                  │
     ▼                  ▼
Calculated Hash   On-Chain Hash
     │                  │
     └────────┬─────────┘
              ▼
        ✅ MATCH / ❌ MISMATCH
```

---

# 📂 Project Structure

```text
facechain-verifier/
│
├── 🧠 face_id.py
├── 🔎 post_discovery.py
├── 🚀 main.py
├── 🧪 test_post_discovery.py
│
├── 📄 face_data.json
├── 📄 post.json
├── 📄 discovered_posts.json
├── 🖼️ face.jpg
│
├── 🤖 models/
│   ├── face_detection.caffemodel
│   ├── face_detection.prototxt
│   └── face_recognition_sface_2021dec.onnx
│
└── ⛓️ person_c_blockchain/
    └── contracts/
        └── contracts/
            ├── blockchain.py
            ├── compile_contract.py
            ├── deploy.py
            ├── hash_utils.py
            ├── store_hash.py
            ├── verify.py
            │
            ├── PostVerification_abi.json
            ├── PostVerification_bytecode.txt
            ├── chain_record.json
            │
            └── contracts/
                └── PostVerification.sol
```

---

# 🛠️ Tech Stack

### 🧠 AI / Computer Vision

* Python
* OpenCV
* OpenCV DNN
* SFace

### 🌐 Web & Data Discovery

* Python HTTP clients
* Reverse image search providers
* Hacker News
* Bluesky
* Reddit
* GitHub

### 🔐 Security & Integrity

* SHA-256
* Deterministic JSON canonicalization
* Cryptographic fingerprints

### ⛓️ Blockchain

* Solidity
* Web3.py
* Ethereum-compatible networks
* Smart Contracts
* Local development blockchain

### 🧪 Testing

* Python `unittest`

---

# ⚡ Quick Start

## 1️⃣ Clone the Repository

```bash
git clone <repository-url>
cd facechain-verifier
```

---

## 2️⃣ Create a Virtual Environment

### Windows

```bash
python -m venv .venv
.venv\Scripts\activate
```

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
```

---

## 3️⃣ Install Dependencies

```bash
pip install -r person_c_blockchain/contracts/contracts/requirements.txt
```

Install the additional project dependencies if required:

```bash
pip install opencv-python numpy python-dotenv certifi
```

---

# 🔑 Configuration

Create your environment file:

```text
person_c_blockchain/contracts/contracts/.env
```

You can use:

```text
.env.example
```

as the starting point.

Example configuration:

```env
LOCAL_RPC_URL=http://***.*.*.*:****
LOCAL_PRIVATE_KEY=YOUR_PRIVATE_KEY
CONTRACT_ADDRESS=YOUR_CONTRACT_ADDRESS

GOOGLE_VISION_API_KEY=YOUR_API_KEY
SERPAPI_API_KEY=YOUR_API_KEY
SEARCHAPI_API_KEY=YOUR_API_KEY
BING_VISUAL_SEARCH_API_KEY=YOUR_API_KEY
TINEYE_API_KEY=YOUR_API_KEY
IMGBB_API_KEY=YOUR_API_KEY

GITHUB_TOKEN=YOUR_GITHUB_TOKEN
```

> ⚠️ **Never commit `.env`, API keys, or private keys to GitHub.**

---

# ▶️ Run the Complete Pipeline

The easiest way to run the system is:

```bash
python main.py test.jpeg
```

The system automatically executes:

```text
[1] 🧠 FACE IDENTIFICATION

[2] 🌐 WEB / SOCIAL MEDIA SEARCH

[3] 🔐 CONTENT FINGERPRINT

[4] ⛓️ BLOCKCHAIN

[5] ✅ VERIFICATION
```

A successful execution ends with:

```text
========================================
       ✅ VERIFICATION SUCCESSFUL
========================================

✓ Face identified
✓ Matching web/social post discovered
✓ Content fingerprint generated
✓ Hash stored on blockchain
✓ On-chain hash matches calculated hash
✓ Content integrity verified
```

---

# 🧠 Face Identification

You can also execute Person A independently:

```bash
python face_id.py test.jpeg
```

The module:

1. Loads the image 📷
2. Detects available faces
3. Selects the largest detected face
4. Crops the face
5. Aligns the face
6. Generates the face encoding
7. Saves the processed data

Output:

```text
face.jpg
face_data.json
```

---

# 🔎 Post Discovery

Person B can be executed independently.

### Reverse Image Search

```bash
python post_discovery.py --image face.jpg --output post.json
```

### Query-Based Discovery

```bash
python post_discovery.py \
    --query "example search" \
    --output discovered_posts.json
```

### Limit Results

```bash
python post_discovery.py \
    --query "example search" \
    --limit 10 \
    --output discovered_posts.json
```

---

# 🌍 Supported Sources

The discovery engine currently works with:

```text
🟠 Hacker News
🔵 Bluesky
🔴 Reddit
⚫ GitHub
```

The architecture allows additional discovery providers to be integrated without changing the complete verification pipeline.

---

# 🔐 Content Fingerprinting

Before storing anything on-chain, the post is converted into a **canonical representation**.

The canonical structure contains information such as:

```json
{
  "post_id": "...",
  "platform": "...",
  "author": "...",
  "author_id": "...",
  "content": "...",
  "timestamp": "...",
  "url": "...",
  "media_urls": [],
  "engagement": {}
}
```

The data is then processed:

```text
📄 Post Data
     ↓
🧹 Canonicalization
     ↓
📦 Deterministic JSON
     ↓
🔐 SHA-256
     ↓
⛓️ Blockchain
```

This means:

> **Identical canonical data → identical SHA-256 fingerprint**

while changing the canonical content produces a different fingerprint.

---

# ⛓️ Smart Contract

The blockchain component uses the:

```text
PostVerification.sol
```

smart contract.

It records information associated with a content hash, including:

* 🔐 Content hash
* ⏱️ Blockchain timestamp
* 👛 Submitting address
* ✅ Existence status

The contract prevents the same hash from being stored repeatedly.

---

# 🧰 Blockchain Setup

Move into the blockchain directory:

```bash
cd person_c_blockchain/contracts/contracts
```

### Compile Contract

```bash
python compile_contract.py
```

### Deploy Contract

```bash
python deploy.py
```

After deployment, configure the resulting contract address in `.env`:

```env
CONTRACT_ADDRESS=YOUR_DEPLOYED_CONTRACT_ADDRESS
```

---

# 📌 Store a Hash

Once `post.json` exists:

```bash
python store_hash.py
```

The system:

```text
post.json
   ↓
canonical_data
   ↓
SHA-256
   ↓
bytes32
   ↓
Smart Contract
   ↓
Transaction
   ↓
chain_record.json
```

---

# ✅ Verify the Content

Run:

```bash
python verify.py
```

The verifier recalculates the hash from the canonical post data and checks it against the value stored on-chain.

```text
                 ┌─────────────────┐
                 │   post.json     │
                 └────────┬────────┘
                          │
                          ▼
                     SHA-256
                          │
                          ▼
                 ┌─────────────────┐
                 │ Calculated Hash │
                 └────────┬────────┘
                          │
                       Compare
                          │
             ┌────────────┴────────────┐
             ▼                         ▼
      🔐 Calculated Hash         ⛓️ Blockchain Hash
             │                         │
             └────────────┬────────────┘
                          ▼
                    ✅ VERIFIED
```

---

# 🧪 Testing

Run the automated tests:

```bash
python -m unittest test_post_discovery.py
```

The tests cover areas including:

* ✅ Post validation
* ✅ Dynamic extraction
* ✅ Invalid targets
* ✅ Missing optional fields
* ✅ Deduplication
* ✅ HTTP error handling
* ✅ Rate-limit handling
* ✅ Retry behavior
* ✅ Person A → Person B integration
* ✅ Output persistence

---

# 🛡️ Reliability

The discovery layer includes configurable:

### ⏱️ Request Timeout

```env
POST_DISCOVERY_TIMEOUT=10
```

### 🔁 Retry Attempts

```env
POST_DISCOVERY_RETRIES=2
```

### 📝 Logging

```env
POST_DISCOVERY_LOG_LEVEL=INFO
```

### 🌐 User Agent

```env
POST_DISCOVERY_USER_AGENT=PersonB_PostDiscoveryEngine/2.0
```

Transient failures such as HTTP `429` can be retried, while permanent errors such as `401`, `403`, and `404` are handled without unnecessary retries.

---

# 🔄 End-to-End Example

One command drives the complete workflow:

```bash
python main.py test.jpeg
```

### Behind the scenes:

```text
                    📷 test.jpeg
                         │
                         ▼
                ┌─────────────────┐
                │  🧠 Face Engine │
                └────────┬────────┘
                         │
                    face.jpg
                         │
                         ▼
                ┌─────────────────┐
                │ 🔎 Discovery    │
                │     Engine      │
                └────────┬────────┘
                         │
                      post.json
                         │
                         ▼
                ┌─────────────────┐
                │ 🔐 SHA-256      │
                │   Fingerprint   │
                └────────┬────────┘
                         │
                         ▼
                ┌─────────────────┐
                │ ⛓️ Blockchain    │
                │    Storage      │
                └────────┬────────┘
                         │
                         ▼
                ┌─────────────────┐
                │ ✅ Verification │
                └────────┬────────┘
                         │
                         ▼
                 🎉 VERIFIED!
```

---

# 🎯 Project Goal

FaceChain Verifier demonstrates how **AI-based identity discovery and blockchain-based data integrity** can work together.

The important distinction is:

> 🧠 **AI helps discover the content.**
> 🔐 **Cryptography fingerprints the content.**
> ⛓️ **Blockchain provides an immutable verification record.**

The blockchain does **not** prove that a discovered post is inherently truthful or authentic. It proves that the canonical data being verified matches the fingerprint that was previously recorded on-chain.

---

# 🔮 Future Improvements

Potential extensions include:

* 🤖 More reverse-image search providers
* 📱 Additional social platforms
* 🧬 Advanced face matching
* 🗄️ Persistent database storage
* 🌐 Web-based verification dashboard
* 📊 Verification history
* 🔔 Automated monitoring
* 🔗 Multi-chain support
* 📦 Containerized deployment
* 🔑 Improved secret management
* 🚀 Production-grade API service

---

# 🔒 Security

Please make sure:

* ❌ `.env` is never committed
* ❌ Private blockchain keys are never exposed
* ❌ API keys are never hardcoded
* ✅ Secrets are loaded through environment variables
* ✅ Only fingerprints are stored on-chain
* ✅ Original content remains outside the blockchain

---

# 📜 License

This project is intended for **research, development, and digital-content verification purposes**.

---

<div align="center">

### 🚀 FaceChain Verifier

**From pixels → to discovery → to cryptographic proof → to blockchain verification.**

**🧠 Discover • 🔎 Extract • 🔐 Fingerprint • ⛓️ Verify**

</div>
