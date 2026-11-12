"""Kiln v4 for the website retort-loading scene: no retorts / platform / proxies; right door open."""
import bpy, sys
a = sys.argv[sys.argv.index("--") + 1:]
bpy.ops.wm.open_mainfile(filepath=a[0])
# detach everything from the rigid-body proxies first, keeping world transforms
for o in bpy.data.objects:
    if o.parent is not None and o.parent.name.startswith("RB_"):
        mw = o.matrix_world.copy(); o.parent = None; o.matrix_world = mw
bpy.context.view_layer.update()
drop_colls = ("07_Реторта_левая", "08_Реторта_правая_выкачена", "14_Выкатная_площадка", "17_Дровокол_ДГ360")
for c in bpy.data.collections:
    if c.name in drop_colls:
        for o in list(c.all_objects): bpy.data.objects.remove(o)
for o in list(bpy.data.objects):
    if o.name.startswith("RB_") or o.name in ("Грунт", "Camera", "Sun") or o.name.startswith("Дровокол"):
        bpy.data.objects.remove(o)
    elif o.name.startswith("Растяжка"):
        bpy.data.objects.remove(o)
bpy.ops.object.select_all(action='DESELECT')
for o in bpy.data.objects:
    if o.type in ('MESH', 'EMPTY'): o.select_set(True)
bpy.ops.export_scene.gltf(filepath=a[1], export_format='GLB', use_selection=True, export_apply=True, export_extras=True,
                          export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=7)
print("KILN SCENE DONE", len([o for o in bpy.data.objects if o.type == 'MESH']))
