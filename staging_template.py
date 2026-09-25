"""Stage any mesh in the gold-sphere studio and render a 120-frame 360 turntable MP4.

Reuses gold_sphere_studio.blend (cyclorama, flags, lights, fixed camera) and swaps Gold_Sphere for the
imported model: joined into one 'Product' mesh, normalised to a 2 m bounding box, centred on the
turntable axis with its bottom flush on the floor (Z = 0) and spun 0 -> 360 deg over frames 1..120.
The camera tracks a Camera_Focus_Target empty at the product's vertical midpoint and keeps its elevation
and heading, but its distance scales with the product's bounding radius (relative to the sphere's, clamped
to 0.5-2x). Light constraints that targeted the sphere are re-linked to the product.

Run:  blender -b --python-exit-code 1 --python staging_template.py -- <model.(obj|fbx|stl|gltf|glb)> [output_name]
          [--up-axis {+Y,-Y,+X,-X,+Z,-Z}]
--up-axis names the axis that points up in the source file; the product is rotated so it points up +Z before
it is measured and seated (e.g. '+Y' for Maya/Unity FBX exports that arrive lying on their back).
With no model path it only checks that the environment is ready (dry run) and renders nothing.
The .blend is never saved.
"""
import sys
import os
import site

# imageio_ffmpeg was pip-installed into the user site-packages (Blender's install dir is read-only):
# %APPDATA%\Python\Python313\site-packages
user_site = os.path.join(os.environ['APPDATA'], 'Python',
                         f'Python{sys.version_info.major}{sys.version_info.minor}', 'site-packages')
for path in (user_site, site.getusersitepackages()):
    if path not in sys.path:
        sys.path.insert(0, path)

import math
import bpy
import mathutils
import subprocess
import shutil
import time
import imageio_ffmpeg

BASE_DIR = r"C:\Users\HI\OneDrive\Desktop\Blender"
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
from generate_scene import animate_product_rotation, FRAME_START, FRAME_END  # 1..120, linear loop

BLEND_FILE = os.path.join(BASE_DIR, "gold_sphere_studio.blend")
RENDERS_DIR = os.path.join(BASE_DIR, "Renders")
PLACEHOLDER_NAME = "Gold_Sphere"
FALLBACK_MATERIAL = "PBR_Gold"  # studio gold, given to meshes that import with no material
TARGET_SIZE = 2.0  # m, longest bounding-box side after normalisation
RELINK_CONSTRAINTS = {'TRACK_TO', 'DAMPED_TRACK', 'COPY_LOCATION'}
RELINK_OBJECT_TYPES = {'LIGHT', 'CAMERA'}
CAMERA_NAME = "Turntable_Camera"
FOCUS_TARGET_NAME = "Camera_Focus_Target"
# Camera distance scales with the product's bounding radius relative to the radius the studio camera was
# framed for (Gold_Sphere's bbox corner radius, sqrt(3) m; used if the placeholder is missing), clamped.
REFERENCE_RADIUS_FALLBACK = math.sqrt(3.0)
REFERENCE_CENTER_FALLBACK = mathutils.Vector((0.0, 0.0, 1.0))
DISTANCE_FACTOR_MIN, DISTANCE_FACTOR_MAX = 0.5, 2.0
FPS = 30
# Source up axis -> (rotation axis, angle) that turns it into +Z.
UP_AXIS_ROTATIONS = {
    "+Z": None,
    "-Z": ('X', math.pi),
    "+Y": ('X', math.pi / 2),   # +90 deg pitch: +Y -> +Z
    "-Y": ('X', -math.pi / 2),
    "+X": ('Y', -math.pi / 2),
    "-X": ('Y', math.pi / 2),
}

IMPORTERS = {  # extension -> import operator
    ".obj": "wm.obj_import",
    ".fbx": "import_scene.fbx",
    ".stl": "wm.stl_import",
    ".gltf": "import_scene.gltf",
    ".glb": "import_scene.gltf",
}


def importer(ext):
    module, name = IMPORTERS[ext].split(".")
    return getattr(getattr(bpy.ops, module), name)


def log(msg):
    print(f"[STAGING] {msg}", flush=True)


def select_only(objects, active):
    bpy.ops.object.select_all(action='DESELECT')
    for ob in objects:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = active


def load_studio():
    bpy.ops.wm.open_mainfile(filepath=BLEND_FILE)


def remove_placeholder():
    """Delete Gold_Sphere; call after relink_constraints so nothing is left pointing at it."""
    placeholder = bpy.data.objects.get(PLACEHOLDER_NAME)
    if placeholder is None:
        return
    mesh = placeholder.data
    bpy.data.objects.remove(placeholder, do_unlink=True)
    if mesh.users == 0:
        bpy.data.meshes.remove(mesh)
    log(f"removed {PLACEHOLDER_NAME}")


def import_model(path):
    """Import, bake modifiers/pose into plain meshes, drop helper objects, join into one 'Product' mesh."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in IMPORTERS:
        raise ValueError(f"unsupported format {ext!r}; expected one of {sorted(IMPORTERS)}")
    if not os.path.isfile(path):
        raise FileNotFoundError(path)

    before = set(bpy.data.objects)
    importer(ext)(filepath=path)
    new = [ob for ob in bpy.data.objects if ob not in before]
    meshes = [ob for ob in new if ob.type == 'MESH']
    if not meshes:
        raise RuntimeError(f"{path} contains no mesh objects")
    log(f"imported {os.path.basename(path)}: {len(new)} objects, {len(meshes)} meshes")

    # Convert applies modifiers and armature poses; parent_clear keeps each mesh's world placement
    # once the empties/armatures/cameras/lights that came with the file are removed.
    select_only(meshes, meshes[0])
    bpy.ops.object.convert(target='MESH')
    bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
    for ob in new:
        if ob not in meshes:
            bpy.data.objects.remove(ob, do_unlink=True)

    select_only(meshes, meshes[0])
    if len(meshes) > 1:
        bpy.ops.object.join()
    product = bpy.context.view_layer.objects.active
    product.name = "Product"
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    if not any(slot.material for slot in product.material_slots):
        fallback = bpy.data.materials.get(FALLBACK_MATERIAL)
        if fallback is not None:
            product.data.materials.clear()
            product.data.materials.append(fallback)
            log(f"no material on import; assigned {FALLBACK_MATERIAL}")
    return product


def correct_up_axis(product, up_axis):
    """Rotate the product about the world origin so its source up axis points +Z, then apply the rotation.

    Must run before normalize() so the bounding box, floor seating and camera radius use the upright mesh.
    """
    rotation = UP_AXIS_ROTATIONS[up_axis]
    if rotation is None:
        return
    axis, angle = rotation
    select_only([product], product)
    product.matrix_world = mathutils.Matrix.Rotation(angle, 4, axis) @ product.matrix_world
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    log(f"up axis {up_axis}: rotated {math.degrees(angle):+.0f} deg about {axis} and applied")


def world_bounds(ob):
    pts = [ob.matrix_world @ mathutils.Vector(c) for c in ob.bound_box]
    lo = mathutils.Vector(tuple(min(p[i] for p in pts) for i in range(3)))
    hi = mathutils.Vector(tuple(max(p[i] for p in pts) for i in range(3)))
    return lo, hi


def normalize(product):
    """Uniformly scale the longest side to TARGET_SIZE, centre it on the turntable axis and seat it on Z = 0.

    Returns z_center, the vertical bbox midpoint. With the bottom at 0 it equals (max_z - min_z) / 2.
    """
    lo, hi = world_bounds(product)
    dims = hi - lo
    longest = max(dims)
    if longest <= 0:
        raise RuntimeError("imported mesh has zero size")
    factor = TARGET_SIZE / longest
    select_only([product], product)
    product.scale = (factor, factor, factor)
    bpy.ops.object.transform_apply(scale=True)

    # Origin at the bbox centre so the product spins in place, then drop it until the bottom touches the floor.
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
    product.location = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    min_z = world_bounds(product)[0].z
    product.location.z -= min_z
    bpy.context.view_layer.update()

    lo, hi = world_bounds(product)
    z_center = (lo.z + hi.z) / 2.0
    log(f"normalised x{factor:.4f}: size {tuple(round(v, 3) for v in hi - lo)} m, "
        f"bottom Z {lo.z:.4f} m, top Z {hi.z:.4f} m, z_center {z_center:.4f} m")
    return z_center


def bounding_radius(ob, z_center):
    """Largest distance from the focus point (0, 0, z_center) to a bbox corner; the product spins about Z,
    so this sphere contains it on every frame."""
    return max(math.sqrt(c.x ** 2 + c.y ** 2 + (c.z - z_center) ** 2)
               for c in (ob.matrix_world @ mathutils.Vector(corner) for corner in ob.bound_box))


def reference_framing():
    """(centre, radius) the studio camera was framed for: Gold_Sphere's bbox centre and corner radius."""
    placeholder = bpy.data.objects.get(PLACEHOLDER_NAME)
    if placeholder is None:
        return REFERENCE_CENTER_FALLBACK.copy(), REFERENCE_RADIUS_FALLBACK
    lo, hi = world_bounds(placeholder)
    center = (lo + hi) / 2
    radius = max(((placeholder.matrix_world @ mathutils.Vector(c)) - center).length for c in placeholder.bound_box)
    return center, radius


def add_focus_target(z_center):
    """Create or move the Camera_Focus_Target empty to the product's vertical midpoint on the turntable axis."""
    focus = bpy.data.objects.get(FOCUS_TARGET_NAME)
    if focus is None:
        focus = bpy.data.objects.new(FOCUS_TARGET_NAME, None)
        focus.empty_display_type = 'PLAIN_AXES'
        bpy.context.scene.collection.objects.link(focus)
    focus.location = (0.0, 0.0, z_center)
    log(f"{FOCUS_TARGET_NAME} at (0, 0, {z_center:.4f})")
    return focus


def relink_constraints(product, focus):
    """Point light/camera constraints aimed at Gold_Sphere at the product (lights) or the focus target (cameras).

    Runs while Gold_Sphere still exists, so only constraints that really targeted it are touched.
    """
    placeholder = bpy.data.objects.get(PLACEHOLDER_NAME)
    if placeholder is None:
        return
    for ob in bpy.data.objects:
        if ob.type not in RELINK_OBJECT_TYPES:
            continue
        for con in ob.constraints:
            if con.type in RELINK_CONSTRAINTS and con.target == placeholder:
                con.target = focus if ob.type == 'CAMERA' else product
                log(f"re-linked {ob.name} {con.type} -> {con.target.name}")


def aim_camera(focus, radius, ref_center, ref_radius):
    """Move the camera along its original viewing line (same elevation and heading) to a distance scaled by
    the product's bounding radius, then aim it at the focus target with a TRACK_TO constraint."""
    camera = bpy.data.objects.get(CAMERA_NAME) or bpy.context.scene.camera
    cam_vec = camera.matrix_world.translation - ref_center  # focus -> camera, along the view axis
    distance_factor = max(DISTANCE_FACTOR_MIN, min(radius / ref_radius, DISTANCE_FACTOR_MAX))
    new_cam_loc = focus.location + cam_vec * distance_factor
    camera.location = new_cam_loc
    log(f"bounding radius {radius:.4f} m / reference {ref_radius:.4f} m -> distance factor {distance_factor:.4f}: "
        f"{camera.name} {cam_vec.length:.3f} m -> {(cam_vec * distance_factor).length:.3f} m from focus, "
        f"at {tuple(round(v, 3) for v in new_cam_loc)}")
    con = next((c for c in camera.constraints if c.type == 'TRACK_TO'), None)
    if con is None:
        con = camera.constraints.new('TRACK_TO')
    con.target = focus
    con.track_axis = 'TRACK_NEGATIVE_Z'
    con.up_axis = 'UP_Y'
    bpy.context.view_layer.update()
    log(f"{camera.name} TRACK_TO -> {focus.name}")


def configure_render(scene, frames_dir):
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'OPTIX'
    prefs.get_devices()
    optix = [d for d in prefs.devices if d.type == 'OPTIX']
    for d in prefs.devices:
        d.use = d.type == 'OPTIX'
    if not optix:
        raise RuntimeError("no OptiX device available")
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'GPU'
    scene.frame_start, scene.frame_end = FRAME_START, FRAME_END
    scene.render.fps = FPS
    scene.render.image_settings.file_format = 'PNG'
    # Blender's frame-number placeholder is '#': 'frame_####' -> frame_0001.png
    scene.render.filepath = os.path.join(frames_dir, "frame_####")
    log(f"Cycles OptiX on {', '.join(d.name for d in optix)}, samples={scene.cycles.samples}, "
        f"frames {FRAME_START}-{FRAME_END}, camera={scene.camera.name}")


def render_frames(frames_dir):
    render_start = time.time()
    bpy.ops.render.render(animation=True)
    frames = [os.path.join(frames_dir, f"frame_{f:04d}.png") for f in range(FRAME_START, FRAME_END + 1)]
    fresh = [p for p in frames if os.path.isfile(p) and os.path.getmtime(p) >= render_start]
    if len(fresh) != len(frames):
        raise RuntimeError(f"only {len(fresh)}/{len(frames)} fresh frames in {frames_dir}")
    log(f"rendered {len(fresh)}/{len(frames)} frames in {time.time() - render_start:.1f}s")


def encode_mp4(frames_dir, output_mp4):
    subprocess.run([
        imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
        "-framerate", str(FPS), "-start_number", str(FRAME_START),
        "-i", os.path.join(frames_dir, "frame_%04d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
        output_mp4,
    ], check=True)
    n_frames, secs = imageio_ffmpeg.count_frames_and_secs(output_mp4)
    expected = FRAME_END - FRAME_START + 1
    if n_frames != expected:
        raise RuntimeError(f"{output_mp4} has {n_frames} frames, expected {expected}")
    log(f"encoded {output_mp4} ({os.path.getsize(output_mp4) / 2**20:.2f} MB, {n_frames} frames, {secs:.2f}s)")


def run_staging_pipeline(import_file_path, output_name="Custom_Product", up_axis="+Z"):
    if up_axis not in UP_AXIS_ROTATIONS:
        raise ValueError(f"unsupported up axis {up_axis!r}; expected one of {sorted(UP_AXIS_ROTATIONS)}")
    t0 = time.perf_counter()
    frames_dir = os.path.join(RENDERS_DIR, f"{output_name}_Frames")
    output_mp4 = os.path.join(RENDERS_DIR, f"{output_name}_Turntable_360.mp4")
    log(f"staging {import_file_path} as {output_name!r} (up axis {up_axis})")

    load_studio()
    product = import_model(import_file_path)
    correct_up_axis(product, up_axis)
    z_center = normalize(product)
    radius = bounding_radius(product, z_center)
    ref_center, ref_radius = reference_framing()  # before Gold_Sphere is removed
    focus = add_focus_target(z_center)
    relink_constraints(product, focus)
    aim_camera(focus, radius, ref_center, ref_radius)
    remove_placeholder()
    animate_product_rotation(product)
    scene = bpy.context.scene
    scene.frame_set(FRAME_START)

    if os.path.isdir(frames_dir):
        shutil.rmtree(frames_dir)  # no stale frames from an earlier run can reach the encode
    os.makedirs(frames_dir)
    configure_render(scene, frames_dir)
    try:
        render_frames(frames_dir)
        encode_mp4(frames_dir, output_mp4)
    finally:
        shutil.rmtree(frames_dir, ignore_errors=True)
        log(f"purged {frames_dir}")
    log(f"done in {(time.perf_counter() - t0) / 60:.1f} min -> {output_mp4}")
    return output_mp4


def dry_check():
    """Confirm dependencies, importers, studio file and OptiX without rendering."""
    log(f"imageio_ffmpeg {imageio_ffmpeg.__version__}: {imageio_ffmpeg.get_ffmpeg_exe()}")
    for ext, op_id in IMPORTERS.items():
        importer(ext).get_rna_type()  # raises if the operator/add-on is missing
        log(f"importer for {ext}: bpy.ops.{op_id}")
    bpy.ops.wm.open_mainfile(filepath=BLEND_FILE)
    linked = [f"{ob.name}:{c.type}" for ob in bpy.data.objects if ob.type in RELINK_OBJECT_TYPES
              for c in ob.constraints
              if c.type in RELINK_CONSTRAINTS and c.target and c.target.name == PLACEHOLDER_NAME]
    log(f"studio loaded: camera={bpy.context.scene.camera.name}, placeholder="
        f"{'present' if PLACEHOLDER_NAME in bpy.data.objects else 'absent'}, constraints to re-link={linked}")
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'OPTIX'
    prefs.get_devices()
    log(f"OptiX devices: {[d.name for d in prefs.devices if d.type == 'OPTIX'] or 'NONE'}")
    log("dry check passed (pass a model path after '--' to render)")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(prog="staging_template.py")
    parser.add_argument("model", nargs="?", help="model to stage; omit for a dry check")
    parser.add_argument("output_name", nargs="?", default="Custom_Product")
    parser.add_argument("--up-axis", default="+Z", choices=sorted(UP_AXIS_ROTATIONS),
                        help="axis pointing up in the source file (default +Z, no correction)")
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    # argparse reads a separate '-Y'/'-X' as a flag, so fold '--up-axis -Y' into '--up-axis=-Y'.
    if "--up-axis" in argv and argv.index("--up-axis") + 1 < len(argv):
        i = argv.index("--up-axis")
        argv[i:i + 2] = [f"--up-axis={argv[i + 1]}"]
    args = parser.parse_args(argv)
    if args.model:
        run_staging_pipeline(args.model, args.output_name, args.up_axis)
    else:
        dry_check()
