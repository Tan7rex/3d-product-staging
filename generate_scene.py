"""Build the gold-sphere studio scene from scratch and save gold_sphere_studio.blend.

Run: blender -b --python generate_scene.py
"""
import math

import bmesh
import bpy
from mathutils import Vector

BLEND_PATH = r'C:\Users\HI\OneDrive\Desktop\Blender\gold_sphere_studio.blend'

# Cyclorama backdrop (metres)
BACKDROP_SIZE = 40.0
BACKDROP_WALL_HEIGHT = 25.0
BACKDROP_BEVEL_WIDTH = 10.0
BACKDROP_BEVEL_SEGMENTS = 16

# Product turntable: fixed camera, the product spins
FRAME_START, FRAME_END = 1, 120
CAMERA_NAME = 'Turntable_Camera'
CAMERA_ELEVATION_DEG = 20.0
CAMERA_LENS = 50.0
RES_X, RES_Y = 1920, 1080

# Deep brushed gold
GOLD_COLOR = (1.0, 0.65, 0.05)
GOLD_METALLIC = 1.0
GOLD_ROUGHNESS = 0.18
# Coarse brushed bump: noise stretched by the mapping scale into bands wide enough to survive
# the denoiser at 1080p. Object coordinates lock the bands to the sphere so the spin reads.
BRUSH_MAPPING_SCALE = (1.0, 12.0, 1.0)
BRUSH_NOISE_SCALE = 4.0
BRUSH_NOISE_DETAIL = 8.0
BRUSH_BUMP_STRENGTH = 1.0

# Dark sweep so the metal reflects something other than blown-out white
BACKDROP_COLOR = (0.25, 0.25, 0.25)
BACKDROP_ROUGHNESS = 0.6

# Matte black flags either side of the sphere: dark reflection bands on the gold.
# Hidden from camera rays (they'd sit at the frame edges) but still seen in reflections.
FLAG_NAMES = ('Contrast_Flag_L', 'Contrast_Flag_R')
FLAG_X = 3.5
FLAG_SIZE = (2.0, 5.0)  # width, height (m)
FLAG_COLOR = (0.01, 0.01, 0.01)
FLAG_ROUGHNESS = 0.9

# High-contrast strip light for long metallic highlights
STRIP_LIGHT_NAME = 'Studio_Strip_Light'
STRIP_LIGHT_ENERGY = 2500.0
STRIP_LIGHT_SIZE = (0.3, 6.0)
STRIP_LIGHT_LOCATION = (-4.0, -3.0, 5.0)

# World ambient fill
WORLD_COLOR = (0.8, 0.8, 0.8)
WORLD_STRENGTH = 0.45
# Glossy visibility stays ON: with it off, reflection rays that reach the world return
# black, which is exactly what darkened the top of the metallic sphere.
WORLD_GLOSSY_VISIBLE = True


def clear_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights, bpy.data.actions,
                 bpy.data.worlds):
        for block in list(coll):
            if block.users == 0:
                coll.remove(block)


def principled_material(name, base_color, metallic, roughness):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*base_color, 1.0)
    bsdf.inputs['Metallic'].default_value = metallic
    bsdf.inputs['Roughness'].default_value = roughness
    mat.diffuse_color = (*base_color, 1.0)  # viewport solid-mode colour
    return mat


def add_brushed_bump(mat):
    """Texture Coordinate (Object) -> Mapping (stretched) -> Noise -> Bump -> BSDF Normal."""
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    texco = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value = BRUSH_MAPPING_SCALE
    noise = nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = BRUSH_NOISE_SCALE
    noise.inputs['Detail'].default_value = BRUSH_NOISE_DETAIL
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = BRUSH_BUMP_STRENGTH
    links.new(texco.outputs['Object'], mapping.inputs['Vector'])
    links.new(mapping.outputs['Vector'], noise.inputs['Vector'])
    links.new(noise.outputs['Fac'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    for i, node in enumerate((texco, mapping, noise, bump)):
        node.location = (-1000 + 220 * i, -300)


def add_gold_sphere():
    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=1.0, location=(0.0, 0.0, 1.0))
    sphere = bpy.context.active_object
    sphere.name = sphere.data.name = 'Gold_Sphere'
    sphere.data.shade_smooth()
    mat = principled_material('PBR_Gold', GOLD_COLOR, GOLD_METALLIC, GOLD_ROUGHNESS)
    add_brushed_bump(mat)
    sphere.data.materials.append(mat)
    return sphere


def add_backdrop():
    """Curved cyclorama: 30 m floor whose back (+Y) edge is extruded upward into a wall,
    with a Bevel modifier rounding the floor/wall seam into a seamless studio sweep."""
    bpy.ops.mesh.primitive_plane_add(size=BACKDROP_SIZE, location=(0.0, 0.0, 0.0))
    plane = bpy.context.active_object
    plane.name = plane.data.name = 'Studio_Backdrop'

    # Extrude the back edge (max Y) straight up to form the cyc wall.
    bm = bmesh.new()
    bm.from_mesh(plane.data)
    bm.edges.ensure_lookup_table()
    half = BACKDROP_SIZE / 2.0
    back_edges = [e for e in bm.edges if all(abs(v.co.y - half) < 1e-4 for v in e.verts)]
    ret = bmesh.ops.extrude_edge_only(bm, edges=back_edges)
    new_verts = [g for g in ret['geom'] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=new_verts, vec=(0.0, 0.0, BACKDROP_WALL_HEIGHT))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(plane.data)
    bm.free()
    plane.data.update()
    plane.data.shade_smooth()

    bevel = plane.modifiers.new('Cyc_Bevel', 'BEVEL')
    bevel.affect = 'EDGES'
    bevel.limit_method = 'ANGLE'
    bevel.width = BACKDROP_BEVEL_WIDTH
    bevel.segments = BACKDROP_BEVEL_SEGMENTS
    bevel.profile = 0.5  # circular sweep
    bevel.harden_normals = False

    plane.data.materials.append(principled_material('Sweep_Matte_Gray', BACKDROP_COLOR, 0.0, BACKDROP_ROUGHNESS))
    return plane


def add_contrast_flags():
    """Vertical matte black cards at +/-FLAG_X, facing the sphere, invisible to the camera."""
    mat = principled_material('Flag_Matte_Black', FLAG_COLOR, 0.0, FLAG_ROUGHNESS)
    width, height = FLAG_SIZE
    flags = []
    for name, x in zip(FLAG_NAMES, (-FLAG_X, FLAG_X)):
        bpy.ops.mesh.primitive_plane_add(size=1.0, location=(x, 0.0, height / 2.0),
                                         rotation=(0.0, math.radians(90.0), 0.0))
        flag = bpy.context.active_object
        flag.name = flag.data.name = name
        flag.scale = (height, width, 1.0)  # local X is world Z after the 90 deg Y rotation
        flag.data.materials.append(mat)
        flag.visible_camera = False
        flag.visible_shadow = False  # shape reflections only; don't shade the sweep
        flags.append(flag)
    return flags


def add_key_light():
    light = bpy.data.lights.new('Studio_Key_Light', 'AREA')
    light.shape = 'DISK'
    light.size = 6.0
    light.energy = 1500.0
    ob = bpy.data.objects.new('Studio_Key_Light', light)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = (4.0, -4.0, 7.0)
    track = ob.constraints.new('TRACK_TO')
    track.target = bpy.data.objects['Gold_Sphere']
    track.track_axis = 'TRACK_NEGATIVE_Z'
    track.up_axis = 'UP_Y'
    return ob


def add_strip_light():
    light = bpy.data.lights.new(STRIP_LIGHT_NAME, 'AREA')
    light.shape = 'RECTANGLE'
    light.size, light.size_y = STRIP_LIGHT_SIZE
    light.energy = STRIP_LIGHT_ENERGY
    ob = bpy.data.objects.new(STRIP_LIGHT_NAME, light)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = STRIP_LIGHT_LOCATION
    track = ob.constraints.new('TRACK_TO')
    track.target = bpy.data.objects['Gold_Sphere']
    track.track_axis = 'TRACK_NEGATIVE_Z'
    track.up_axis = 'UP_Y'
    return ob


def _fcurves(ob):
    ad = ob.animation_data
    if not ad or not ad.action:
        return []
    action = ad.action
    if hasattr(action, 'fcurves'):
        return list(action.fcurves)
    curves = []  # layered actions (Blender 4.4+/5.x)
    for layer in action.layers:
        for strip in layer.strips:
            for cb in strip.channelbags:
                curves += list(cb.fcurves)
    return curves


def animate_product_rotation(ob):
    """0 deg at FRAME_START -> 360 deg at FRAME_END + 1, linear, so 1..120 loops without a repeated pose."""
    ob.rotation_mode = 'XYZ'
    ob.rotation_euler = (0.0, 0.0, 0.0)
    ob.keyframe_insert('rotation_euler', index=2, frame=FRAME_START)
    ob.rotation_euler[2] = 2.0 * math.pi
    ob.keyframe_insert('rotation_euler', index=2, frame=FRAME_END + 1)
    for fc in _fcurves(ob):
        fc.extrapolation = 'LINEAR'
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'
    ob.rotation_euler[2] = 0.0


def add_fixed_camera(target):
    """Static camera at CAMERA_ELEVATION_DEG, on -Y looking toward the +Y cyc wall. No animation."""
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = RES_X, RES_Y
    scene.render.resolution_percentage = 100
    pts = [target.matrix_world @ Vector(c) for c in target.bound_box]
    center = sum(pts, Vector()) / len(pts)
    radius = max((p - center).length for p in pts)
    cam_data = bpy.data.cameras.new(CAMERA_NAME)
    cam_data.lens = CAMERA_LENS
    aspect = RES_X / RES_Y
    half_h = math.atan(cam_data.sensor_width / (2.0 * cam_data.lens))
    half_v = math.atan(math.tan(half_h) / aspect) if aspect >= 1 else half_h
    dist = radius / math.sin(min(half_h, half_v)) * 1.25
    elev = math.radians(CAMERA_ELEVATION_DEG)
    cam = bpy.data.objects.new(CAMERA_NAME, cam_data)
    scene.collection.objects.link(cam)
    cam.location = center + Vector((0.0, -dist * math.cos(elev), dist * math.sin(elev)))
    cam.rotation_euler = (center - cam.location).to_track_quat('-Z', 'Y').to_euler()
    scene.camera = cam
    return cam


def setup_world():
    scene = bpy.context.scene
    world = bpy.data.worlds.new('Studio_World')
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get('Background')
    bg.inputs['Color'].default_value = (*WORLD_COLOR, 1.0)
    bg.inputs['Strength'].default_value = WORLD_STRENGTH
    world.color = WORLD_COLOR
    world.cycles_visibility.glossy = WORLD_GLOSSY_VISIBLE
    return world


def main():
    clear_scene()
    sphere = add_gold_sphere()
    add_backdrop()
    add_contrast_flags()
    add_key_light()
    add_strip_light()
    setup_world()
    add_fixed_camera(sphere)
    animate_product_rotation(sphere)
    scene = bpy.context.scene
    scene.frame_start, scene.frame_end = FRAME_START, FRAME_END
    scene.frame_set(FRAME_START)
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    print(f'=== generate_scene: saved {BLEND_PATH} ===')
    for ob in bpy.context.scene.objects:
        print(f'  {ob.name:<18} {ob.type:<6} {tuple(round(v, 3) for v in ob.location)}')


if __name__ == '__main__':
    main()
