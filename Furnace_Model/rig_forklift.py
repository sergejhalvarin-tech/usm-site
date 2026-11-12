"""Split the telehandler glb (merged by material) into animatable parts with real pivots, in metres.
Usage: blender -b -P rig_forklift.py -- <in.glb> <out.glb>
Model axes: up = -Y, forward (forks) = +Z, units ~2.05 cm (tyre Ø51 u = 1.05 m).
Output (Blender): Z up, forward = +Y  ->  glTF: Y up, forward = -Z.
Groups: body, boom (pivot = boom heel pin), carriage (pivot = boom-tip pin), wheel_FL/FR/RL/RR (pivot = hub),
outrigger (pivot = top of the stabiliser legs).
"""
import bpy, bmesh, sys, math
from mathutils import Vector, Matrix
import numpy as np

a = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT = a[0], a[1]
S = 0.0205
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)
for o in list(bpy.data.objects):
    if o.name == "_gltfNode_13":   # shadow plane
        bpy.data.objects.remove(o)

BOOM_P0 = np.array([-64.0, -52.0])    # (z, y) boom heel pin
BOOM_P1 = np.array([220.0, -129.0])   # (z, y) boom tip pin
WHEELS = {"wheel_RL": (-57.5, 8.0, -28.0), "wheel_RR": (33.0, 8.0, -28.0), "wheel_FL": (-54.0, 8.0, 119.0), "wheel_FR": (33.0, 8.0, 119.0)}
OUTR_PIVOT = (-12.0, -25.0, 180.0)

def classify(c, size):
    x, y, z = c
    for name, (wx, wy, wz) in WHEELS.items():
        if abs(x - wx) < 15 and math.hypot(y - wy, z - wz) < 29:
            return name
    if z > 226:
        return "carriage"
    d = BOOM_P1 - BOOM_P0
    t = ((z - BOOM_P0[0]) * d[0] + (y - BOOM_P0[1]) * d[1]) / (d @ d)
    n = np.array([-d[1], d[0]]) / np.linalg.norm(d)            # normal pointing "down" (towards +y)
    sd = (z - BOOM_P0[0]) * n[0] + (y - BOOM_P0[1]) * n[1]
    if -0.02 <= t <= 1.02 and abs(x + 12) < 30 and (-17 <= sd <= 9 or (-17 <= sd <= 17 and size[2] > 100)):
        return "boom_inner" if (t > 0.6 and size[2] < 150) else "boom"
    if z > 150 and y < -100:
        return "boom_inner"
    if 160 <= z <= 205 and y > -32:
        return "outrigger"
    return "body"

for o in [o for o in bpy.data.objects if o.type == 'MESH']:
    mw = o.matrix_world.copy()
    o.parent = None
    o.data.transform(mw)
    o.matrix_world = Matrix.Identity(4)
groups = {}
for o in [o for o in bpy.data.objects if o.type == 'MESH']:
    me = o.data
    nv = len(me.vertices)
    co = np.empty(nv * 3); me.vertices.foreach_get("co", co); co = co.reshape(-1, 3)
    ed = np.empty(len(me.edges) * 2, dtype=np.int64); me.edges.foreach_get("vertices", ed); ed = ed.reshape(-1, 2)
    parent = np.arange(nv)
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for u, v in ed:
        ru, rv = find(u), find(v)
        if ru != rv: parent[ru] = rv
    roots = np.array([find(i) for i in range(nv)])
    labels = {}
    vgroup = np.empty(nv, dtype=object)
    for r in np.unique(roots):
        idx = np.where(roots == r)[0]
        pts = co[idx]
        c = (pts.min(0) + pts.max(0)) / 2
        g = classify(c, pts.max(0) - pts.min(0))
        vgroup[idx] = g
    for g in set(vgroup):
        dup = o.copy(); dup.data = me.copy(); bpy.context.scene.collection.objects.link(dup)
        bm = bmesh.new(); bm.from_mesh(dup.data); bm.verts.ensure_lookup_table()
        kill = [v for v in bm.verts if vgroup[v.index] != g]
        bmesh.ops.delete(bm, geom=kill, context='VERTS')
        bm.to_mesh(dup.data); bm.free()
        if len(dup.data.vertices) == 0:
            bpy.data.objects.remove(dup); continue
        groups.setdefault(g, []).append(dup)
    bpy.data.objects.remove(o)

print({g: sum(len(o.data.vertices) for o in obs) for g, obs in groups.items()})

# model -> Blender metres: (mx, my, mz) -> (mx, mz, -my) * S, machine centred on x = -12 (track centre), rear axle at y = 0
def M(p):
    return Vector(((p[0] + 12.0) * S, (p[2] + 28.0) * S, -(p[1] - 34.0) * S))   # ground (y=34) -> z=0
T = Matrix(((S, 0, 0, 12.0 * S), (0, 0, S, 28.0 * S), (0, -S, 0, 34.0 * S), (0, 0, 0, 1)))

pivots = {"body": (-12.0, 34.0, -28.0), "boom": (-12.0, BOOM_P0[1], BOOM_P0[0]), "boom_inner": (-12.0, BOOM_P1[1], BOOM_P1[0]), "carriage": (-12.0, BOOM_P1[1], BOOM_P1[0]),
          "outrigger": OUTR_PIVOT, **WHEELS}
out_objs = []
for g, obs in groups.items():
    for o in obs:
        o.data.transform(T); o.matrix_world = Matrix.Identity(4)
    bpy.ops.object.select_all(action='DESELECT')
    for o in obs: o.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]
    if len(obs) > 1:
        with bpy.context.temp_override(active_object=obs[0], selected_editable_objects=obs, selected_objects=obs):
            bpy.ops.object.join()
    ob = obs[0]; ob.name = g; ob.data.name = g
    pv = M(pivots[g])
    ob.data.transform(Matrix.Translation(-pv)); ob.location = pv
    nv = len(ob.data.vertices)
    target = {"body": 90000, "boom": 20000, "boom_inner": 15000, "carriage": 12000, "outrigger": 6000}.get(g, 9000)
    if nv > target:
        md = ob.modifiers.new("dec", 'DECIMATE'); md.ratio = max(target / nv, 0.08)
        with bpy.context.temp_override(object=ob, active_object=ob):
            bpy.ops.object.modifier_apply(modifier=md.name)
    print(g, "verts", nv, "->", len(ob.data.vertices), "pivot", [round(v, 3) for v in pv])
    out_objs.append(ob)

for im in bpy.data.images:
    if im.size[0] > 1024:
        im.scale(1024, int(1024 * im.size[1] / im.size[0]))
bpy.ops.object.select_all(action='DESELECT')
for o in out_objs: o.select_set(True)
bpy.ops.export_scene.gltf(filepath=OUT, export_format='GLB', use_selection=True, export_apply=True,
                          export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=7,
                          export_image_format='JPEG', export_jpeg_quality=80)
print("RIG DONE")
