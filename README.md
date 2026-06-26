Real-Time Sign Language Translation and Personalized Speech Generation System
1. Project Overview
The objective of this project is to develop a real-time Sign Language Recognition (SLR) system capable of translating American Sign Language (ASL) gestures into spoken English. The system will capture video from a webcam, extract human pose and hand landmarks using MediaPipe, recognize signs using deep learning models, convert recognized signs into text, and finally generate speech using a user-selected voice.
In addition to sign recognition, the system will support optional user identification through face recognition. Registered users may associate their profiles with a preferred voice, enabling personalized speech output.
The complete solution is designed for real-time operation on standard consumer hardware and deployment as a web-based application.

2. Sign Language and Vocabulary Strategy
2.1 Selection of American Sign Language (ASL)
American Sign Language (ASL) was selected because it provides the largest publicly available ecosystem of datasets suitable for machine learning research. Unlike many regional sign languages, ASL offers established benchmark datasets, allowing the project to focus on model development rather than large-scale data collection.
The system output language is English, making ASL a natural choice for the recognition component.

2.2 Dynamic Vocabulary Dataset
The primary dataset for dynamic sign recognition will be the WLASL (Word-Level American Sign Language) dataset.
The WLASL dataset contains thousands of sign videos from multiple signers and is widely used in sign language recognition research.
Dynamic Vocabulary Composition
Source
Classes
Type
WLASL100
100
Dynamic Signs
Selected WLASL300 Glosses
20–30
Dynamic Signs
Optional Custom Phrases
5–10
Dynamic Signs

The initial implementation will target approximately:
100–120 dynamic word classes
Examples include:
Hello
Thank You
Please
Sorry
Water
Help
Yes
No
Family
Friend
School
Work
Restricting the vocabulary to approximately 100–120 classes improves recognition accuracy and reduces model complexity while remaining sufficiently challenging for academic evaluation.

2.3 Static Vocabulary Dataset
Static handshape recognition will be treated as a separate task.
Instead of collecting all samples manually, publicly available ASL datasets will be used.
Static Vocabulary Composition
Source
Classes
ASL Alphabet Dataset
24 Static Letters
ASL Digits Dataset
10 Digits

The following classes are considered static:
Alphabet
A–Y excluding:
J
Z
since these involve motion.
Digits
0–9
This results in:
24 static letter classes
10 static digit classes
Total:
34 static classes

2.4 Dynamic Letters
The letters:
J
Z
contain motion and will therefore be treated as dynamic signs and included in the dynamic recognition model.

2.5 Total System Vocabulary
Category
Classes
Dynamic Words
100–120
Dynamic Letters (J,Z)
2
Static Letters
24
Static Digits
10

Expected total vocabulary:
Approximately 136–156 classes.
This scope is realistic for a Master's project and significantly reduces training complexity compared with attempting a 200+ class vocabulary.

3. System Architecture
The system follows a modular pipeline architecture.
Dynamic Sign Recognition Pipeline
Camera Input
→ MediaPipe Holistic
→ Landmark Extraction
→ Landmark Normalization
→ Temporal Buffer
→ Transformer Encoder
→ Confidence Filtering
→ Word Prediction
→ Sentence Assembly
→ Text-to-Speech

User Identification Pipeline
Camera Input
→ Face Detection
→ Face Embedding Extraction
→ User Matching
→ Profile Retrieval
→ Preferred Voice Selection

4. Rationale for Landmark-Based Recognition
A major design decision is the use of landmark-based recognition instead of video-based recognition.
The following architectures were intentionally excluded:
I3D
VideoMAE
ViViT
3D CNNs
SlowFast Networks
Although these models achieve strong benchmark performance, they require substantial computational resources and are impractical for real-time CPU deployment.
Instead, MediaPipe is used to convert each frame into a compact skeletal representation.
Benefits include:
Reduced computational cost
Smaller models
Faster training
Faster inference
Improved deployability
This design aligns with the project's real-time requirements.

5. Feature Extraction
MediaPipe Holistic will be used to extract:
Pose Landmarks
33 landmarks
Left Hand
21 landmarks
Right Hand
21 landmarks
Each landmark contains:
x coordinate
y coordinate
z coordinate
Total features per frame:
75 landmarks × 3 coordinates
= 225 features

6. Landmark Normalization
To improve robustness across users and camera positions:
Landmark coordinates will be centered using the shoulder midpoint.
Coordinates will be scaled using shoulder width.
Dynamic sequences will be resampled to a fixed length.
This ensures invariance to:
User position
Camera distance
Body size
while preserving gesture motion.

7. Recognition Models
7.1 Dynamic Sign Recognition Model
Dynamic signs involve temporal motion and require sequence modeling.
Model Architecture
Transformer Encoder
Configuration:
Input Dimension: 225
Transformer Layers: 2
Attention Heads: 4
Hidden Dimension: 128
Sequence Length: 40 Frames
The final sequence representation is classified into the dynamic vocabulary classes.
Justification
Compared to LSTM architectures, Transformer encoders provide:
Better long-range temporal modeling
Parallel processing
Competitive accuracy
Efficient inference
while remaining lightweight enough for CPU deployment.

7.2 Static Sign Recognition Model
Static signs require only a single frame.
Model Architecture
Multi-Layer Perceptron (MLP)
Input:
63 hand features
Architecture:
63 → 128 → 64 → Output Classes
Target Classes:
34
The MLP is computationally inexpensive and highly effective for static handshape classification.

8. Model Training Strategy
Training and deployment are separated.
Training Environment
Recommended:
Google Colab GPU
Kaggle GPU
Training on GPU significantly reduces experimentation time and hyperparameter tuning cycles.

Deployment Environment
The deployed application will run entirely on CPU.
Components suitable for CPU execution include:
MediaPipe
Transformer Inference
MLP Inference
Text-to-Speech
Face Recognition
This allows deployment on standard laptops without dedicated graphics hardware.

9. Real-Time Inference Strategy
A rolling temporal buffer of 40 frames is maintained.
Recognition occurs when:
Sufficient motion has been observed.
A pause is detected after the gesture.
The recognized sign is accepted only when:
Prediction Confidence ≥ 0.70
Predictions below this threshold are rejected.
This reduces false positives and improves system reliability.

10. User Registration and Personalization
Users may optionally create profiles containing:
Name
Preferred Voice
Face Embedding (optional)
The preferred voice can be:
Male
Female
The system does not automatically infer gender.
Instead, voice preference is explicitly selected during registration.
This approach is:
More reliable
More ethical
Easier to maintain
than automatic gender classification.

11. Face Recognition Module
User identification is optional.
The recommended implementation uses InsightFace.
Pipeline:
Face Detection
→ Face Embedding Extraction
→ Similarity Matching
→ User Identification
When a match is found, the system loads:
User Name
Preferred Voice
and personalizes the generated speech.

12. Speech Generation
Two deployment options are supported.
Desktop Version
pyttsx3
Advantages:
Offline
Free
Lightweight
Web Version
Browser SpeechSynthesis API
Advantages:
No server-side blocking
Built-in browser support
Better scalability
The web deployment will primarily use browser-side speech synthesis.

13. Web Application Architecture
Frontend:
HTML5
JavaScript
WebRTC
Socket.IO
Backend:
Python
Flask
Flask-SocketIO
AI Components:
MediaPipe
PyTorch
InsightFace
Database:
SQLite
Communication:
WebSockets

14. Expected Performance
Target performance metrics:
Metric
Target
Camera Rate
30 FPS
MediaPipe Processing
20–40 FPS
Sign Recognition Latency
<100 ms
TTS Latency
<200 ms
End-to-End Latency
<500 ms

These targets are achievable on modern consumer laptops.

15. Evaluation Methodology
The following metrics will be reported:
Dynamic Recognition
Accuracy
Precision
Recall
F1 Score
Confusion Matrix
Static Recognition
Accuracy
Precision
Recall
F1 Score
System Evaluation
End-to-End Latency
CPU Usage
Memory Consumption
Real-Time FPS
Additional ablation studies will investigate:
Window Length
Hands Only vs Hands + Pose
Confidence Threshold Selection

16. Known Limitations
The proposed system has several acknowledged limitations:
ASL grammar differs from English grammar, therefore direct gloss-to-English conversion may produce unnatural sentences.
Motion-based segmentation relies on heuristic pause detection and may occasionally split or merge signs incorrectly.
Signer variability remains a challenge despite multi-signer training data.
The vocabulary is limited to approximately 136–156 classes and does not represent the full ASL lexicon.
These limitations are acceptable within the scope of a Master's-level research project and provide opportunities for future work.

17. Final Technical Stack
MediaPipe Holistic


Transformer Encoder (Dynamic Signs)


MLP (Static Signs)


InsightFace (User Identification)


SpeechSynthesis API / pyttsx3


Flask-SocketIO


PyTorch


SQLite
This architecture provides an effective balance between accuracy, computational efficiency, deployment feasibility, and academic research value while remaining practical for real-time operation on standard hardware.

