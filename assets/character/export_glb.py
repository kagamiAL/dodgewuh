"""Export RedGuy (redguy.blend, collection "RedGuy") to frontend/public/models/redguy.glb.

Run from the repo root (the .blend is never saved, only exported):

    /Applications/Blender.app/Contents/MacOS/Blender -b assets/character/redguy.blend \
        --python assets/character/export_glb.py

The browser rig needs pivots, so loose parts are joined into rig pieces with their
origin at the joint they rotate around:

    RedGuy_Root
      RG_LegRig_L / RG_LegRig_R    origin at the hip
      RG_TorsoRig                  origin at the hips (lower body segment + dark core)
        RG_ChestRig                origin at the waist (upper body segment)
          RG_HeadRig               origin at the neck (head, eyes, pupils)
          RG_ArmRig_L / _R         origin at the shoulder (tube, shoulder, palm, fingers, thumb)

frontend/src/game/characterModel.ts looks these names up; keep them in sync.
Ragdoll spring settings come from custom properties (see spring_props.py).
Dense meshes are decimated for the web (about 20k triangles total).
"""

import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spring_props  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(bpy.data.filepath), "..", ".."))
OUT = os.path.join(REPO, "frontend", "public", "models", "redguy.glb")
DECIMATE_RATIO = 0.3

# Joint positions in Blender space; must match redguy_build.py.
SHOULDER = {"L": Vector((0.58, 0, 2.38)), "R": Vector((-0.58, 0, 2.38))}
HIP = {"L": Vector((0.30, 0, 1.40)), "R": Vector((-0.30, 0, 1.40))}
HIPS_CENTRE = Vector((0, 0, 1.35))
WAIST = Vector((0, 0, 1.975))  # gap between RG_BodyLower (top 1.95) and RG_BodyUpper (bottom 2.0)
NECK = Vector((0, 0, 2.67))

col = bpy.data.collections["RedGuy"]
root = bpy.data.objects["RedGuy_Root"]
view_layer = bpy.context.view_layer


def select_only(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    view_layer.objects.active = objs[0]


# 0. Spring settings travel as custom properties -> glTF node extras.
spring_props.ensure()

# 1. Decimate dense meshes, then bake every modifier and curve into plain meshes.
for o in col.objects:
    if o.type == "MESH" and len(o.data.polygons) > 400:
        o.modifiers.new("WebDecimate", "DECIMATE").ratio = DECIMATE_RATIO
parts = [o for o in col.objects if o.type in ("MESH", "CURVE")]
select_only(parts)
bpy.ops.object.convert(target="MESH")


def join(name, names, origin):
    objs = [bpy.data.objects[n] for n in names]
    select_only(objs)
    if len(objs) > 1:
        bpy.ops.object.join()
    rig = view_layer.objects.active
    rig.name = name
    bpy.context.scene.cursor.location = origin
    bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
    return rig


def parent_keep(child, parent):
    world = child.matrix_world.copy()
    child.parent = parent
    child.matrix_world = world


torso = join("RG_TorsoRig", ["RG_BodyLower", "RG_Core"], HIPS_CENTRE)
chest = join("RG_ChestRig", ["RG_BodyUpper"], WAIST)
parent_keep(chest, torso)
head = join("RG_HeadRig", ["RG_Head", "RG_Eye_L", "RG_Pupil_L", "RG_Eye_R", "RG_Pupil_R"], NECK)
parent_keep(head, chest)
for side in ("L", "R"):
    arm = join(
        f"RG_ArmRig_{side}",
        [f"RG_Arm_{side}", f"RG_Shoulder_{side}", f"RG_Palm_{side}",
         f"RG_Finger_{side}0", f"RG_Finger_{side}1", f"RG_Finger_{side}2", f"RG_Thumb_{side}"],
        SHOULDER[side],
    )
    parent_keep(arm, chest)
    join(f"RG_LegRig_{side}", [f"RG_Leg_{side}", f"RG_Knee_{side}", f"RG_Foot_{side}"], HIP[side])

# 2. Export only the character.
select_only([root] + [o for o in col.objects if o is not root])
tris = 0
for o in col.objects:
    if o.type == "MESH":
        o.data.calc_loop_triangles()
        tris += len(o.data.loop_triangles)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
bpy.ops.export_scene.gltf(
    filepath=OUT, export_format="GLB", use_selection=True,
    export_apply=True, export_yup=True, export_materials="EXPORT", export_extras=True,
)
print(f"exported {OUT} ({tris} triangles)")
