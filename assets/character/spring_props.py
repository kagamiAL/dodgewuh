"""Ragdoll spring settings stored on RedGuy's objects as Blender custom properties.

Edit them in Blender: select a part -> Object Properties -> Custom Properties.
They ride along into redguy.glb as node "extras" and the browser reads them
(frontend/src/game/ragdoll.ts). Re-export with export_glb.py after changing them.

Add any missing properties (keeps values you've already edited) and save the .blend:

    /Applications/Blender.app/Contents/MacOS/Blender -b assets/character/redguy.blend \
        --python assets/character/spring_props.py

Re-run this after redguy_build.py, which rebuilds the objects from scratch.

Units: frequency in rad/s (higher = stiffer), damping ratio (below 1 wobbles,
lower = floppier), limits and swings in degrees, gains in degrees per m/s² of body
acceleration, whip = how much the parent joint's motion flings this one.
"""

import bpy

# Object name in redguy.blend -> spring properties. The export joins parts into rig
# pieces; each rig piece keeps the properties of its first part listed here.
DEFAULTS = {
    "RedGuy_Root": {
        "spring_accel_smoothing_s": 0.1,
        "spring_throw_twist": 520.0,
        "spring_throw_torso": 220.0,
    },
    "RG_BodyLower": {  # hips -> RG_TorsoRig
        "spring_frequency": 9.0,
        "spring_damping": 0.35,
        "spring_limit_deg": 30.0,
        "spring_gain": 0.55,
        "spring_run_lean": 4.0,
    },
    "RG_BodyUpper": {  # waist -> RG_ChestRig
        "spring_frequency": 6.0,
        "spring_damping": 0.22,
        "spring_limit_deg": 40.0,
        "spring_gain": 0.9,
        "spring_whip": 0.06,
        "spring_twist_frequency": 8.0,
        "spring_twist_damping": 0.4,
        "spring_twist_limit_deg": 80.0,
    },
    "RG_Head": {  # neck -> RG_HeadRig
        "spring_frequency": 7.0,
        "spring_damping": 0.18,
        "spring_limit_deg": 30.0,
        "spring_whip": 0.08,
    },
    "RG_Arm_L": {  # left shoulder -> RG_ArmRig_L
        "spring_frequency": 5.0,
        "spring_damping": 0.14,
        "spring_limit_deg": 75.0,
        "spring_gain": 2.2,
        "spring_whip": 0.12,
    },
    "RG_Arm_R": {  # right (throwing) shoulder -> RG_ArmRig_R
        "spring_frequency": 5.5,
        "spring_damping": 0.16,
        "spring_limit_deg": 75.0,
        "spring_gain": 2.2,
        "spring_whip": 0.1,
        "spring_throw_kick": -1100.0,
    },
    "RG_Leg_L": {  # hips yaw + walk cycle -> RG_LegRig_L
        "spring_swing_deg": 30.0,
        "spring_stride_m": 1.1,
        "spring_twist_limit_deg": 70.0,
        "spring_twist_frequency": 6.0,
        "spring_twist_damping": 0.7,
        "spring_twist_min_speed": 0.4,
    },
}


def ensure():
    """Add missing properties; never overwrite edited values. Returns count added."""
    added = 0
    for name, props in DEFAULTS.items():
        obj = bpy.data.objects.get(name)
        if obj is None:
            print(f"spring_props: object {name!r} not found, skipped")
            continue
        for key, value in props.items():
            if key not in obj.keys():
                obj[key] = value
                added += 1
    return added


if __name__ == "__main__":
    n = ensure()
    bpy.ops.wm.save_mainfile()
    print(f"spring_props: added {n} properties, saved {bpy.data.filepath}")
