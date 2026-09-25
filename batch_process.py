"""Batch-render 360 turntables for every model in Input_Models.

Scans Input_Models for .obj/.fbx/.stl/.glb/.gltf files and, for each one, runs staging_template.py in its own
headless Blender process (run_staging_pipeline needs bpy, and a fresh process per model keeps scenes isolated).
Each model renders to Renders/<model_name>_Turntable_360.mp4, where model_name is the file stem. One failed
model is logged and skipped; the exit code is 1 if any model failed.

Run with any Python 3 (not Blender's):
    python batch_process.py [--up-axis +Y] [--lighting-rig {warm_accent,high_key_commercial}] [--preserve-materials] [--dry-run]
Set BLENDER_EXE to override the Blender path.
"""
import argparse
import os
import re
import subprocess
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, "Input_Models")
STAGING_SCRIPT = os.path.join(BASE_DIR, "staging_template.py")
BLENDER_EXE = os.environ.get("BLENDER_EXE", r"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
SUPPORTED_EXTENSIONS = {".obj", ".fbx", ".stl", ".glb", ".gltf"}
UP_AXES = ["+Z", "-Z", "+Y", "-Y", "+X", "-X"]
LIGHTING_RIGS = ["warm_accent", "high_key_commercial"]  # generate_scene.LIGHTING_RIGS (needs bpy, so not imported)


def log(msg):
    print(f"[BATCH] {msg}", flush=True)


def find_models():
    return sorted(os.path.join(INPUT_DIR, f) for f in os.listdir(INPUT_DIR)
                  if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS
                  and os.path.isfile(os.path.join(INPUT_DIR, f)))


def model_name(path):
    """File stem made safe for output file names: 'My Chair (v2).fbx' -> 'My_Chair_v2'."""
    stem = os.path.splitext(os.path.basename(path))[0]
    return re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_") or "Model"


def run_staging_pipeline(file_path, name, up_axis, lighting_rig, preserve_materials):
    """Render one model through staging_template.run_staging_pipeline in headless Blender."""
    cmd = [BLENDER_EXE, "-b", "--python-exit-code", "1", "--python", STAGING_SCRIPT, "--",
           file_path, name, f"--up-axis={up_axis}", "--lighting-rig", lighting_rig]
    if preserve_materials:
        cmd.append("--preserve-materials")
    return subprocess.run(cmd, cwd=BASE_DIR).returncode == 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--up-axis", default="+Z", choices=UP_AXES,
                        help="up axis applied to every model (default +Z, no correction)")
    parser.add_argument("--lighting-rig", default="warm_accent", choices=LIGHTING_RIGS,
                        help="studio lighting preset applied to every model (default warm_accent)")
    parser.add_argument("--preserve-materials", action="store_true",
                        help="keep each model's imported materials (e.g. OBJ .mtl) and export one native GLB "
                             "per model to Renders/<model_name>_Interactive.glb instead of the metallic variants")
    parser.add_argument("--dry-run", action="store_true", help="list what would be rendered and exit")
    args = parser.parse_args([f"--up-axis={a}" if prev == "--up-axis" else a
                              for prev, a in zip([None] + sys.argv[1:], sys.argv[1:])
                              if a != "--up-axis"])

    os.makedirs(INPUT_DIR, exist_ok=True)
    models = find_models()
    if not models:
        log(f"no {'/'.join(sorted(SUPPORTED_EXTENSIONS))} files in {INPUT_DIR}")
        return 0
    names = [model_name(m) for m in models]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        log(f"models share output names {sorted(dupes)}; rename them so no turntable is overwritten")
        return 1
    log(f"{len(models)} model(s), up axis {args.up_axis}, lighting rig {args.lighting_rig}, "
        f"{'native' if args.preserve_materials else 'studio'} materials: {', '.join(os.path.basename(m) for m in models)}")
    if args.dry_run:
        return 0
    if not os.path.isfile(BLENDER_EXE):
        log(f"Blender not found at {BLENDER_EXE}; set BLENDER_EXE")
        return 1

    failed = []
    t0 = time.perf_counter()
    for i, (path, name) in enumerate(zip(models, names), 1):
        log(f"[{i}/{len(models)}] {os.path.basename(path)} -> {name}_Turntable_360.mp4")
        start = time.perf_counter()
        ok = run_staging_pipeline(path, name, args.up_axis, args.lighting_rig, args.preserve_materials)
        log(f"[{i}/{len(models)}] {'done' if ok else 'FAILED'} in {(time.perf_counter() - start) / 60:.1f} min")
        if not ok:
            failed.append(os.path.basename(path))

    log(f"finished {len(models) - len(failed)}/{len(models)} in {(time.perf_counter() - t0) / 60:.1f} min"
        + (f"; failed: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
