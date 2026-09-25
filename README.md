# Automated 3D Commercial Product Staging & Rendering Pipeline

An end-to-end automated 3D product staging pipeline built with **Blender 5.2 LTS**, **Cycles OptiX GPU Path Tracing**, and **HTML5 WebGL / <model-viewer>**.

## 🌟 Live Interactive Demo
[View Interactive 3D Product Viewer](https://tan7rex.github.io/3d-product-staging/index.html)

## 🛠️ Key Pipeline Deliverables
- **Automated Python Pipeline (staging_template.py):** Ingests CAD/3D meshes (.obj, .fbx, .stl, .glb), normalizes bounding dimensions to 2.0m, auto-seats geometry flush at  = 0.0\text{ m}$ on the studio floor, and re-aims cameras dynamically based on model bounding radius ({\text{ref}} \approx 1.732\text{ m}$).
- **Micro-Anisotropic PBR Normal Baking:**  \times 2048$ tangent space normal maps baked directly into glTF binary assets (.glb).
- **Interactive WebGL Viewer:** Embedded material swatching (Brushed Gold, Rose Gold, Dark Gunmetal Titanium, Chrome Mirror) running in real-time on browser GPUs with customizable lighting and canvas themes.
- **OptiX GPU Batch Turntables:** 120-frame 1080p 30 FPS MP4 video loops rendered with path tracing and warm rim studio lighting.

## 💻 Tech Stack
- **DCC & Renderer:** Blender 5.2.2 LTS (Cycles OptiX GPU)
- **Hardware Acceleration:** NVIDIA GeForce RTX 4090
- **Web Technologies:** HTML5, CSS3, JavaScript, Google <model-viewer> v3.4.0
- **Automation:** Python 3.13, FFmpeg (imageio-ffmpeg), PowerShell
