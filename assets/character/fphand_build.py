"""First-person view model: RedGuy's right hand gripping the dodgeball.

Builds into the current scene (collection "FPHand", rebuilt on every run). Units
match redguy_build.py (character 3.55 units = 1.8 m), so the ball radius is 0.30
(game BALL_RADIUS 0.15 m) and its colour is BALL_COLOR. The hand is HAND_SCALE x the
character's hand so it reads on screen.

Layout: FPHand_Root sits at the ball centre. The view looks along +Y, so the
camera is behind the hand at -Y and the forearm comes in from the lower right
toward it.
"""

import bpy
from mathutils import Quaternion, Vector

CN = "FPHand"
ROOT_AT = Vector((-6.0, 0.0, 1.5))  # out of the way of RedGuy in the shared .blend
BALL_R = 0.30
HAND_SCALE = 1.25

scene = bpy.context.scene
col = bpy.data.collections.get(CN)
if col:
    for o in list(col.objects):
        bpy.data.objects.remove(o, do_unlink=True)
else:
    col = bpy.data.collections.new(CN)
    scene.collection.children.link(col)


def mat(name, color, rough, coat=0.0):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.diffuse_color = (*color, 1)
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Coat Weight"].default_value = coat
    return m


RED = bpy.data.materials.get("RG_Red") or mat("RG_Red", (0.45, 0.012, 0.012), 0.6)
BALL = mat("FP_Ball", (0.95, 0.85, 0.2), 0.45, coat=0.3)
SEAM = mat("FP_BallSeam", (0.55, 0.42, 0.05), 0.6)

root = bpy.data.objects.new("FPHand_Root", None)
root.empty_display_type = 'SPHERE'
root.empty_display_size = BALL_R
col.objects.link(root)
root.location = ROOT_AT


def own(o, m, name):
    o.name = name
    for c in list(o.users_collection):
        c.objects.unlink(o)
    col.objects.link(o)
    o.data.materials.clear()
    o.data.materials.append(m)
    o.parent = root
    if o.type == 'MESH':
        for p in o.data.polygons:
            p.use_smooth = True
    return o


def sphere(name, loc, r, m, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=r, location=loc)
    o = bpy.context.active_object
    o.scale = scale
    return own(o, m, name)


def on_ball(d, r):
    """Centre of a blob of radius r resting on the ball surface in direction d."""
    return d.normalized() * (BALL_R + r * 0.55)


# ---------- ball ----------
sphere("FP_Ball", (0, 0, 0), BALL_R, BALL)
bpy.ops.mesh.primitive_torus_add(major_radius=BALL_R * 0.995, minor_radius=0.007,
                                 major_segments=64, minor_segments=8, location=(0, 0, 0))
own(bpy.context.active_object, SEAM, "FP_BallSeam")

# ---------- hand ----------
up = Vector((0, 0, 1))
palm_dir = Vector((0.35, -0.75, -0.55)).normalized()   # behind, below, right of the ball
side = palm_dir.cross(up).normalized()                  # across the back of the hand

PALM_R = 0.12 * HAND_SCALE
FINGER_R = 0.09 * HAND_SCALE
THUMB_R = 0.08 * HAND_SCALE

def turn(d, toward, angle):
    """Rotate direction d by angle (radians) toward another direction, over the ball."""
    axis = d.cross(toward).normalized()
    return Quaternion(axis, angle) @ d


palm = on_ball(palm_dir, PALM_R)
sphere("FP_Palm", palm, PALM_R, RED)
# Clover grip: three fingers packed just above the palm, spread across the ball.
over = turn(palm_dir, up, 0.55)
for i, s in enumerate((-0.42, 0.0, 0.42)):
    d = turn(over, side, s) if s > 0 else turn(over, -side, -s) if s < 0 else over
    sphere(f"FP_Finger{i}", on_ball(d, FINGER_R), FINGER_R, RED)
# Thumb tucked against the inner side of the palm.
sphere("FP_Thumb", on_ball(turn(palm_dir, -side, 0.5), THUMB_R), THUMB_R, RED)

# ---------- forearm ----------
wrist = palm + (palm - Vector()).normalized() * PALM_R * 0.6
elbow = wrist + Vector((0.35, -0.75, -0.55))
cu = bpy.data.curves.new("FP_Arm", 'CURVE')
cu.dimensions = '3D'
cu.bevel_depth = 0.055 * HAND_SCALE
cu.bevel_resolution = 6
cu.use_fill_caps = True
sp = cu.splines.new('BEZIER')
sp.bezier_points.add(2)
for bp, p in zip(sp.bezier_points, (elbow + Vector((0.2, -0.4, -0.3)), elbow, wrist)):
    bp.co = p
    bp.handle_left_type = bp.handle_right_type = 'AUTO'
arm = bpy.data.objects.new("FP_Arm", cu)
col.objects.link(arm)
own(arm, RED, "FP_Arm")

print("built", len(col.objects), "objects in", CN)
