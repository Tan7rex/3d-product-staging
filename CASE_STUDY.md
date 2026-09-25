# Case Study: Automated 3D Product Staging & Turntable Rendering

**Live demo:** [tan7rex.github.io/3d-product-staging](https://tan7rex.github.io/3d-product-staging/index.html)

## Problem Statement

Staging products by hand in DCC software (digital content creation tools like Blender or Maya) is slow and inconsistent. For each model an artist has to import it, fix its orientation, scale it, place it on the floor, reframe the camera, and set up a turntable render. Every manual step can go wrong in a different way:

- **Scale drift.** Models arrive in millimetres, centimetres or metres, so products in the same catalogue render at different apparent sizes.
- **Framing inconsistency.** Tall, flat or wide products each need their own camera distance and aim. Adjusting them by eye gives uneven margins and crops the product in some shots.
- **Floor contact errors.** Products end up floating above the studio floor or sunk into it, which breaks the contact shadows.
- **Axis mismatches.** FBX files exported from Y-up tools (Maya, Unity) can import lying on their side.

## Technical Solution

The solution is a headless Python staging engine built on **Blender 5.2.2 LTS**. It renders with **Cycles path tracing on OptiX GPU acceleration** on an **NVIDIA GeForce RTX 4090**. You pass it a model file, and it produces a finished 120-frame, 30 FPS, 360° turntable MP4 with no manual steps.

| Stage | What happens |
|---|---|
| Ingest | Imports `.obj`, `.fbx`, `.stl`, `.gltf` and `.glb`. Bakes modifiers and armature poses, removes helper objects, and joins the meshes into one `Product` mesh. |
| Orient | Optional `--up-axis` correction (`±X`, `±Y`, `±Z`) is applied before any measurement. |
| Normalise | Scales the product uniformly so its longest side is 2.0 m, then centres it on the turntable axis. |
| Seat | Sets the bottom of the bounding box to Z = 0.0 m. |
| Frame | Moves the camera along its original viewing line to a distance based on the product's bounding radius, and aims it at the product's vertical midpoint. |
| Render | Renders 120 frames with Cycles on the OptiX GPU and encodes them to H.264 MP4 with FFmpeg. Intermediate frames are deleted afterwards. |
| Batch | `batch_process.py` renders every model in `Input_Models/`, each in its own headless Blender process. |

## Key Innovations

### Dynamic camera distance from the bounding radius

The studio camera was originally framed for a reference sphere with a bounding radius of **R_ref = √3 ≈ 1.732 m**. For each new product, the engine measures its bounding radius R, meaning the distance from the focus point to the farthest bounding-box corner. Because the product spins about Z, a sphere of radius R contains it on every frame. The camera stays on its original elevation and heading, and its distance is scaled by R / R_ref, clamped to 0.5–2×. The effect is that every product fills the frame the same way, whatever its proportions.

### Ground plane seating (Z = 0.0 m)

After scaling, the product's origin is moved to its bounding-box centre so it spins in place. The mesh is then lowered until its lowest point sits exactly at Z = 0.0 m, which gives correct contact shadows on the studio floor with no manual nudging.

### Vertical midpoint camera tracking

A `Camera_Focus_Target` empty is placed at the product's vertical midpoint, (0, 0, (z_min + z_max) / 2). The camera follows it through a `TRACK_TO` constraint. Light constraints that pointed at the original placeholder are re-linked to the new product, so the studio lighting follows it automatically.

### Axis correction for cross-DCC assets

Passing `--up-axis +Y` rotates a Y-up asset +90° about X and applies the rotation before the bounding box is measured. Scaling, seating and camera distance are therefore all computed from the upright mesh.

### Live HTML5 WebGL material swatching

The web viewer uses Google `<model-viewer>` to show a glTF binary (`.glb`) with a baked 2048 × 2048 tangent-space normal map for brushed anisotropy. Viewers can switch between Brushed Gold, Rose Gold, Dark Gunmetal Titanium and Chrome Mirror in real time on their own GPU. The same page also plays the rendered turntable loops.

## Results

- **One command per product:** `blender -b --python staging_template.py -- model.fbx Name --up-axis +Y`
- **Unattended catalogue rendering:** drop files into `Input_Models/` and run `py batch_process.py`.
- **Consistent output:** every turntable has the same scale, floor contact and framing margins.

## Tech Stack

- **DCC and renderer:** Blender 5.2.2 LTS, Cycles with OptiX GPU acceleration
- **Hardware:** NVIDIA GeForce RTX 4090
- **Automation:** Python 3.13 (`bpy`), FFmpeg via `imageio-ffmpeg`
- **Web:** HTML5, CSS3, JavaScript, Google `<model-viewer>`
