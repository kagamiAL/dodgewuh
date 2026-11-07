import bpy, bmesh, math
from mathutils import Vector

CN = "RedGuy"
scene = bpy.context.scene

# ---------- reset ----------
for name in (CN, "Stage"):
    c = bpy.data.collections.get(name)
    if c:
        for o in list(c.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.collections.remove(c)
for m in list(bpy.data.meshes) + list(bpy.data.curves):
    if m.users == 0:
        (bpy.data.meshes if isinstance(m, bpy.types.Mesh) else bpy.data.curves).remove(m)

def new_col(name):
    c = bpy.data.collections.new(name)
    scene.collection.children.link(c)
    return c

col = new_col(CN)
stage = new_col("Stage")

def link(o, c=col):
    for uc in list(o.users_collection):
        uc.objects.unlink(o)
    c.objects.link(o)
    return o

# ---------- materials ----------
def make_mat(name, color, rough, bump=0.0, coat=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    m.diffuse_color = (*color, 1)
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Coat Weight"].default_value = coat
    nt.links.new(b.outputs[0], out.inputs[0])
    if bump:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        vor = nt.nodes.new("ShaderNodeTexVoronoi")
        vor.feature = 'DISTANCE_TO_EDGE'
        vor.inputs["Scale"].default_value = 14
        noi = nt.nodes.new("ShaderNodeTexNoise")
        noi.inputs["Scale"].default_value = 45
        noi.inputs["Detail"].default_value = 8
        add = nt.nodes.new("ShaderNodeMath"); add.operation = 'MULTIPLY_ADD'
        add.inputs[1].default_value = 0.35
        bp = nt.nodes.new("ShaderNodeBump")
        bp.inputs["Strength"].default_value = bump
        bp.inputs["Distance"].default_value = 0.02
        nt.links.new(tc.outputs["Object"], vor.inputs["Vector"])
        nt.links.new(tc.outputs["Object"], noi.inputs["Vector"])
        nt.links.new(noi.outputs["Fac"], add.inputs[0])
        nt.links.new(vor.outputs["Distance"], add.inputs[2])
        nt.links.new(add.outputs[0], bp.inputs["Height"])
        nt.links.new(bp.outputs[0], b.inputs["Normal"])
        # subtle colour variation
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (color[0]*0.7, color[1]*0.7, color[2]*0.7, 1)
        ramp.color_ramp.elements[1].color = (*color, 1)
        nt.links.new(noi.outputs["Fac"], ramp.inputs[0])
        nt.links.new(ramp.outputs[0], b.inputs["Base Color"])
    return m

RED   = make_mat("RG_Red",   (0.45, 0.012, 0.012), 0.6, bump=0.45)
CORE  = make_mat("RG_Core",  (0.10, 0.006, 0.006), 0.7)
WHITE = make_mat("RG_EyeWhite", (0.9, 0.9, 0.88), 0.15, coat=0.6)
BLACK = make_mat("RG_Pupil", (0.005, 0.005, 0.005), 0.1, coat=1.0)
FLOOR = make_mat("RG_Floor", (0.035, 0.035, 0.037), 0.8)

# ---------- helpers ----------
root = bpy.data.objects.new("RedGuy_Root", None)
root.empty_display_type = 'PLAIN_AXES'
link(root)

def finish(o, m, name, smooth=True, by_angle=False):
    o.name = name
    o.data.materials.clear()
    o.data.materials.append(m)
    link(o)
    o.parent = root
    if smooth and o.type == 'MESH':
        for p in o.data.polygons:
            p.use_smooth = True
        if by_angle:
            bpy.ops.object.select_all(action='DESELECT')
            o.select_set(True); bpy.context.view_layer.objects.active = o
            bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
    return o

def sphere(name, loc, r, m, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=r, location=loc)
    o = bpy.context.active_object
    o.scale = scale
    return finish(o, m, name)

def segment(name, z0, h, r, m, bevel=0.09):
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=r, depth=h, location=(0, 0, z0 + h / 2))
    o = bpy.context.active_object
    bv = o.modifiers.new("Bevel", 'BEVEL')
    bv.width = bevel; bv.segments = 6; bv.limit_method = 'ANGLE'
    finish(o, m, name, by_angle=True)
    return o

def tube(name, pts, radius, m):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = radius
    cu.bevel_resolution = 6
    cu.use_fill_caps = True
    sp = cu.splines.new('BEZIER')
    sp.bezier_points.add(len(pts) - 1)
    for bp, p in zip(sp.bezier_points, pts):
        bp.co = p
        bp.handle_left_type = bp.handle_right_type = 'AUTO'
    o = bpy.data.objects.new(name, cu)
    cu.materials.append(m)
    link(o)
    o.parent = root
    return o

# ---------- body ----------
BODY_R = 0.62
segment("RG_BodyLower", 1.35, 0.60, BODY_R, RED)
segment("RG_BodyUpper", 2.00, 0.60, BODY_R, RED)
segment("RG_Core", 1.40, 1.35, BODY_R * 0.82, CORE, bevel=0.02)   # dark gaps between segments

# head: one seamless mesh - dome on top of a short cylinder wall
HEAD_R, HEAD_WALL, HEAD_Z0 = 0.62, 0.40, 2.67
bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=HEAD_R, location=(0, 0, 0))
head = bpy.context.active_object
bm = bmesh.new(); bm.from_mesh(head.data)
for v in bm.verts:
    v.co.z *= 0.85
res = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                             plane_co=(0, 0, 0), plane_no=(0, 0, 1), clear_inner=True)
rim = [e for e in bm.edges if e.is_boundary]
ext = bmesh.ops.extrude_edge_only(bm, edges=rim)
newv = [g for g in ext["geom"] if isinstance(g, bmesh.types.BMVert)]
for v in newv:
    v.co.z = -HEAD_WALL
bmesh.ops.contextual_create(bm, geom=[g for g in ext["geom"] if isinstance(g, bmesh.types.BMEdge)])
bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.004)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
bm.to_mesh(head.data); bm.free()
head.location = (0, 0, HEAD_Z0 + HEAD_WALL)
bv = head.modifiers.new("Bevel", 'BEVEL')
bv.width = 0.08; bv.segments = 6; bv.limit_method = 'ANGLE'; bv.angle_limit = math.radians(60)
finish(head, RED, "RG_Head", by_angle=True)
head.modifiers.get("Smooth by Angle") and head.modifiers.move(head.modifiers.find("Smooth by Angle"), len(head.modifiers)-1)

# eyes
EYE_R = 0.30
for side, sx in (("L", 1), ("R", -1)):
    c = Vector((sx * 0.29, -0.47, 3.07))
    sphere(f"RG_Eye_{side}", c, EYE_R, WHITE)
    d = Vector((sx * 0.22, -1, 0.12)).normalized()
    sphere(f"RG_Pupil_{side}", c + d * (EYE_R - 0.035), 0.085, BLACK, scale=(1, 0.6, 1))

# ---------- arms ----------
for side, sx in (("L", 1), ("R", -1)):
    sh = Vector((sx * 0.58, 0, 2.38))
    el = Vector((sx * 1.15, -0.05, 2.30))
    wr = Vector((sx * 1.72, -0.12, 1.98))
    tube(f"RG_Arm_{side}", [sh, el, wr], 0.055, RED)
    sphere(f"RG_Shoulder_{side}", sh, 0.085, RED)
    # clover hand: palm + 3 fingers + thumb
    d = (wr - el).normalized()
    up = Vector((0, 0, 1))
    palm = wr + d * 0.06
    sphere(f"RG_Palm_{side}", palm, 0.12, RED)
    perp = d.cross(Vector((0, 1, 0))).normalized()
    if perp.z < 0:
        perp = -perp
    for i, (a, b) in enumerate(((1, 0), (0.55, 0.85), (0.55, -0.85))):
        fp = palm + (d * a + perp * b).normalized() * 0.18
        sphere(f"RG_Finger_{side}{i}", fp, 0.09, RED)
    sphere(f"RG_Thumb_{side}", palm + Vector((0, -0.15, 0.04)), 0.08, RED)

# ---------- legs ----------
for side, sx in (("L", 1), ("R", -1)):
    hip = Vector((sx * 0.30, 0, 1.40))
    kn  = Vector((sx * 0.34, -0.06, 0.80))
    an  = Vector((sx * 0.42, 0, 0.26))
    tube(f"RG_Leg_{side}", [hip, kn, an], 0.065, RED)
    sphere(f"RG_Knee_{side}", kn, 0.08, RED)
    sphere(f"RG_Foot_{side}", (sx * 0.45, -0.14, 0.15), 0.26, RED, scale=(1.05, 1.45, 0.6))

# ---------- stage ----------
bpy.ops.mesh.primitive_plane_add(size=400, location=(0, 0, 0))
fl = bpy.context.active_object; fl.name = "RG_Floor"
fl.data.materials.append(FLOOR); link(fl, stage)

target = bpy.data.objects.new("RG_CamTarget", None); link(target, stage)
target.location = (0, 0, 1.75)

cam = bpy.data.objects.get("Camera")
if cam:
    cam.constraints.clear()
    cam.location = (0, -11.5, 1.9)
    cam.data.lens = 50
    cam.data.clip_end = 1000
    tr = cam.constraints.new('TRACK_TO'); tr.target = target
    scene.camera = cam

def area(name, loc, energy, size):
    ld = bpy.data.lights.get(name) or bpy.data.lights.new(name, 'AREA')
    ld.energy = energy; ld.size = size
    o = bpy.data.objects.new(name, ld); link(o, stage)
    o.location = loc
    t = o.constraints.new('TRACK_TO'); t.target = target
    return o

area("RG_Key", (4, -6, 6), 900, 4)
area("RG_Fill", (-6, -4, 3), 250, 6)
area("RG_Rim", (0, 6, 5), 600, 3)
old_light = bpy.data.objects.get("Light")
if old_light:
    old_light.hide_render = True; old_light.hide_viewport = True

w = scene.world or bpy.data.worlds.new("World")
scene.world = w
w.use_nodes = True
bg = w.node_tree.nodes.get("Background")
if bg:
    bg.inputs[0].default_value = (0.012, 0.012, 0.013, 1)
    bg.inputs[1].default_value = 1.0

bpy.ops.object.select_all(action='DESELECT')
print("built", len(col.objects), "objects")
