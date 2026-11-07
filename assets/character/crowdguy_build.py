"""Low-poly, upper-body-only RedGuy for the stadium crowd.

Builds crowdguy.blend and exports frontend/public/models/crowdguy.glb. Run from the
repo root:

    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup \
        --python assets/character/crowdguy_build.py

Same proportions and units as redguy_build.py, minus the legs: one barrel body (two
segments + dark core), dome head, googly eyes, stubby arms with ball hands.

Objects in the GLB (each a single joined mesh, both modelled at the origin):

    CrowdGuy_Idle    arms hanging at the sides
    CrowdGuy_Cheer   arms up in a V

Origin is the bottom-centre of the body (where it sits on a seat). Front is Blender
-Y (glTF +Z, same as redguy.glb). Idle is about 2.0 wide x 2.25 tall, Cheer about
2.7 x 2.3 (arms up); about 610 triangles each. Body radius is 0.62, same as RedGuy;
scale in the engine to taste.

Materials (recolour CG_Body per fan; the others stay fixed):

    CG_Body      body, head, arms, hands
    CG_Core      dark gaps between body segments
    CG_EyeWhite  eyeballs
    CG_Pupil     pupils
"""

import math
import os

import bmesh
import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
BLEND_OUT = os.path.join(HERE, "crowdguy.blend")
GLB_OUT = os.path.join(REPO, "frontend", "public", "models", "crowdguy.glb")

# ---------- fresh scene ----------
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def make_mat(name, color, rough, coat=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.diffuse_color = (*color, 1)
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Coat Weight"].default_value = coat
    return m


BODY = make_mat("CG_Body", (0.45, 0.012, 0.012), 0.6)
CORE = make_mat("CG_Core", (0.10, 0.006, 0.006), 0.7)
WHITE = make_mat("CG_EyeWhite", (0.9, 0.9, 0.88), 0.2)
BLACK = make_mat("CG_Pupil", (0.005, 0.005, 0.005), 0.2)


def finish(o, mat):
    o.data.materials.clear()
    o.data.materials.append(mat)
    for p in o.data.polygons:
        p.use_smooth = True
    return o


def cylinder(z0, h, r, mat, verts=12, caps=True):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=h, location=(0, 0, z0 + h / 2),
                                        end_fill_type='NGON' if caps else 'NOTHING')
    o = bpy.context.active_object
    finish(o, mat)
    # Hard edge at the caps so smooth shading doesn't smear them.
    o.modifiers.new("EdgeSplit", 'EDGE_SPLIT').split_angle = math.radians(50)
    return o


def sphere(loc, r, mat, segs=8, rings=6, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segs, ring_count=rings, radius=r, location=loc)
    o = bpy.context.active_object
    o.scale = scale
    return finish(o, mat)


def tube(pts, r, mat):
    cu = bpy.data.curves.new("tube", 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = r
    cu.bevel_resolution = 0  # 4-sided
    cu.resolution_u = 3
    cu.use_fill_caps = True
    sp = cu.splines.new('BEZIER')
    sp.bezier_points.add(len(pts) - 1)
    for bp, p in zip(sp.bezier_points, pts):
        bp.co = p
        bp.handle_left_type = bp.handle_right_type = 'AUTO'
    o = bpy.data.objects.new("tube", cu)
    scene.collection.objects.link(o)
    cu.materials.append(mat)
    bpy.ops.object.select_all(action='DESELECT')
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.convert(target='MESH')
    o = bpy.context.active_object
    for p in o.data.polygons:
        p.use_smooth = True
    return o


def head(z0, r, wall, mat):
    """Dome on a short cylinder wall, one seamless mesh (like RedGuy's head)."""
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=r, location=(0, 0, 0))
    o = bpy.context.active_object
    bm = bmesh.new()
    bm.from_mesh(o.data)
    for v in bm.verts:
        v.co.z *= 0.85
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                           plane_co=(0, 0, 0), plane_no=(0, 0, 1), clear_inner=True)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.004)
    rim = [e for e in bm.edges if e.is_boundary]
    ext = bmesh.ops.extrude_edge_only(bm, edges=rim)
    for g in ext["geom"]:
        if isinstance(g, bmesh.types.BMVert):
            g.co.z = -wall
    bmesh.ops.contextual_create(bm, geom=[g for g in ext["geom"] if isinstance(g, bmesh.types.BMEdge)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(o.data)
    bm.free()
    o.location = (0, 0, z0 + wall)
    finish(o, mat)
    o.modifiers.new("EdgeSplit", 'EDGE_SPLIT').split_angle = math.radians(50)
    return o


# ---------- proportions (RedGuy units, body bottom at z=0) ----------
BODY_R = 0.62
SEG_H = 0.60
GAP = 0.05
HEAD_Z0 = 2 * SEG_H + GAP + 0.07   # 1.32
HEAD_R, HEAD_WALL = 0.62, 0.40
EYE_Z = HEAD_Z0 + 0.40
EYE_R = 0.30
SHOULDER_Z = 1.03


def build_guy(name, arm_pose):
    parts = [
        cylinder(0.0, SEG_H, BODY_R, BODY, caps=False),
        cylinder(SEG_H + GAP, SEG_H, BODY_R, BODY),
        cylinder(0.03, 2 * SEG_H + GAP + 0.08, BODY_R * 0.82, CORE, verts=8, caps=False),
        head(HEAD_Z0, HEAD_R, HEAD_WALL, BODY),
    ]
    for sx in (1, -1):
        c = Vector((sx * 0.29, -0.47, EYE_Z))
        parts.append(sphere(c, EYE_R, WHITE))
        d = Vector((sx * 0.22, -1, 0.12)).normalized()
        parts.append(sphere(c + d * (EYE_R - 0.03), 0.09, BLACK, segs=6, rings=4, scale=(1, 0.6, 1)))

        sh = Vector((sx * 0.58, 0, SHOULDER_Z))
        el, wr = (Vector((sx * x, y, z)) for x, y, z in arm_pose)
        parts.append(tube([sh, el, wr], 0.08, BODY))
        parts.append(sphere(wr + (wr - el).normalized() * 0.08, 0.15, BODY, segs=6, rings=4))

    bpy.ops.object.select_all(action='DESELECT')
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.convert(target='MESH')  # applies scale-free modifiers (edge split)
    bpy.ops.object.join()
    o = bpy.context.active_object
    o.name = o.data.name = name
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return o


# (elbow, wrist) for the +X arm; mirrored for the other side.
IDLE = ((0.82, -0.08, 0.70), (0.88, -0.22, 0.32))
CHEER = ((0.98, -0.05, 1.55), (1.18, -0.12, 2.10))

guys = [build_guy("CrowdGuy_Idle", IDLE), build_guy("CrowdGuy_Cheer", CHEER)]
for g in guys:
    tris = sum(len(p.vertices) - 2 for p in g.data.polygons)
    dims = g.dimensions
    print(f"{g.name}: {tris} tris, size {dims.x:.2f} x {dims.y:.2f} x {dims.z:.2f}")

os.makedirs(os.path.dirname(GLB_OUT), exist_ok=True)
bpy.ops.object.select_all(action='DESELECT')
for g in guys:
    g.select_set(True)
bpy.ops.export_scene.gltf(filepath=GLB_OUT, export_format='GLB', use_selection=True,
                          export_apply=True, export_yup=True)
bpy.ops.wm.save_as_mainfile(filepath=BLEND_OUT)
print("wrote", GLB_OUT, "and", BLEND_OUT)
