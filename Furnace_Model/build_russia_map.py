# Russia map for the «География поставок» section.
# Source: «Russia Map Карта России» by Mike (sketchfab.com/smirnov-mn), CC BY 4.0.
# Usage: blender -b --factory-startup -P build_russia_map.py -- <karta.glb> <out.glb> <centroids.json>
import bpy, bmesh, sys, json, math
from mathutils import Vector

a = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT, CEN = a[0], a[1], a[2]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)
bpy.context.view_layer.update()

top = bpy.data.materials.new("map_top"); side = bpy.data.materials.new("map_side")
regions = []
for o in list(bpy.data.objects):
    if o.type != "MESH": continue
    code = (o.parent.name if o.parent else o.name).split("_m_map")[0].split(".")[0]
    mw = o.matrix_world.copy()
    me = o.data.copy(); me.transform(mw)
    n = bpy.data.objects.new(code, me); bpy.context.scene.collection.objects.link(n)
    regions.append(n)
for o in list(bpy.data.objects):
    if o not in regions: bpy.data.objects.remove(o, do_unlink=True)
for o in regions: o.name = o.name.split(".")[0]
print("names", sorted(o.name for o in regions))

# fit: centre and scale to 10 units wide, map plane = XY (Blender Z up)
mn = Vector((1e9,) * 3); mx = Vector((-1e9,) * 3)
for o in regions:
    for v in o.data.vertices:
        for i in range(3): mn[i] = min(mn[i], v.co[i]); mx[i] = max(mx[i], v.co[i])
size = mx - mn
print("bounds", mn, mx)
thin = min(range(3), key=lambda i: size[i])
assert thin == 2, f"map not in XY: {size}"
k = 10.0 / size.x; c = (mn + mx) / 2
THICK = 0.11                                         # extruded slab height after scaling
cent = {}
for o in regions:
    me = o.data
    for v in me.vertices:
        p = (v.co - c) * k
        p.z = (THICK if v.co.z > c.z else 0.0)
        v.co = p
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.normal.z < -0.5], context="FACES")   # bottoms are never seen
    me.materials.clear(); me.materials.append(top); me.materials.append(side)
    A = 0.0; C = Vector((0, 0))
    for f in bm.faces:
        if f.normal.z > 0.5:
            f.material_index = 0; f.smooth = False; ar = f.calc_area(); A += ar; cc = f.calc_center_median(); C += Vector((cc.x, cc.y)) * ar
        else:
            f.material_index = 1; f.smooth = False
    bm.to_mesh(me); bm.free()
    if A > 0: cent[o.name] = [C.x / A, C.y / A, A]
# the source model is cut at the 180° meridian: add eastern Chukotka (Natural Earth 10m, public domain),
# aligned to the model by ICP + seam anchors (Furnace_Model/chukotka_east.json, map coordinates)
import os
EAST = os.path.join(os.path.dirname(os.path.abspath(CEN)), "chukotka_east.json")
if os.path.exists(EAST):
    chu = next(o for o in regions if o.name == "RUCHU")
    bm = bmesh.new(); bm.from_mesh(chu.data)
    for v in bm.verts:                               # model draws land south of 65°N on the cut: turn it into a sloping coast
        if v.co.x > 4.995 and v.co.y < -0.80: v.co.x = 5.0 - 0.45 * (-0.793 - v.co.y)
    for ring in json.load(open(EAST)):
        tv = [bm.verts.new((x, y, THICK)) for x, y in ring]; bv = [bm.verts.new((x, y, 0.0)) for x, y in ring]
        f = bm.faces.new(tv); f.material_index = 0; f.smooth = False
        f.normal_update()
        if f.normal.z < 0: f.normal_flip()
        n = len(ring)
        for i in range(n):
            j = (i + 1) % n
            q = bm.faces.new((tv[i], bv[i], bv[j], tv[j])); q.material_index = 1; q.smooth = False
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
    bm.to_mesh(chu.data); bm.free()
    print("east Chukotka added")
json.dump({"scale": k, "regions": cent}, open(CEN, "w"), indent=1)
print("regions", len(regions), "verts", sum(len(o.data.vertices) for o in regions))
for o in regions: o.select_set(True)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_apply=True,
                          export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=7,
                          export_draco_position_quantization=13, export_normals=True, export_materials="EXPORT")
