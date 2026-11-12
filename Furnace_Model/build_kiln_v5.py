"""PROMETHEY kiln v5 = v4 (drawing УП040.003-4 СБ) + full automation / safety package.
Usage: blender -b --factory-startup -P build_kiln_v5.py -- <PROMETHEY_kiln_v4.blend> <out_dir> <web_glb>
Adds (names start with «АСУ_» / «Безоп_» so the website can find them):
  PLC cabinet HMI + signal tower, VFD of the combustion-air fan, thermocouples (existing), pressure transmitters
  of both shells, UV flame sensors of the afterburning zones, O2/CO analysers in both chimneys, electric actuators
  of the chimney dampers / air dampers / pyrolysis-pipe vents, door limit switches, emergency stops,
  shell relief valves, fire extinguisher. Removes retorts, dryer, cooling cabinets, splitter, loading platform;
  closes both loading doors.
"""
import bpy, bmesh, math, os, sys
from mathutils import Vector, Matrix

a = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT, WEB = a[0], a[1], a[2]
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=SRC)
scene = bpy.context.scene

# --- detach from rigid-body proxies (keep world transforms), drop proxies and site equipment
for o in bpy.data.objects:
    if o.parent is not None and o.parent.name.startswith("RB_"):
        mw = o.matrix_world.copy(); o.parent = None; o.matrix_world = mw
bpy.context.view_layer.update()
drop = ("07_Реторта_левая", "08_Реторта_правая_выкачена", "14_Выкатная_площадка", "15_Сушильная_камера", "16_Шкафы_остывания", "17_Дровокол_ДГ360")
for c in bpy.data.collections:
    if c.name in drop:
        for o in list(c.all_objects): bpy.data.objects.remove(o)
for o in list(bpy.data.objects):
    n = o.name
    if n.startswith("RB_") or n in ("Грунт", "Camera", "Sun") or n.startswith("Сушилка_фундамент") or n.startswith("Шкаф_остывания_фундамент") \
       or n.startswith("Дровокол") or n.startswith("Растяжка") or n.startswith("Шибер_трубы_рычаг") or n.startswith("Газоход_на_сушилку") \
       or n.startswith("Заслонка_с_электроприводом") or n.startswith("Электропривод_заслонки"):
        bpy.data.objects.remove(o)
# close both loading doors
for o in bpy.data.objects:
    if o.type == "EMPTY" and o.name.startswith("Дверь_загрузочная"):
        o.rotation_euler = (0, 0, 0)
bpy.context.view_layer.update()

# --- materials
def mat(name, rgb, metal=0.3, rough=0.5, emit=None):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*rgb, 1); b.inputs["Metallic"].default_value = metal; b.inputs["Roughness"].default_value = rough
    if emit:
        b.inputs["Emission Color"].default_value = (*emit[0], 1); b.inputs["Emission Strength"].default_value = emit[1]
    m.diffuse_color = (*rgb, 1)
    return m
M = {
    "cab": mat("АСУ_шкаф_RAL7035", (0.62, 0.64, 0.66), 0.2, 0.45),
    "act": mat("АСУ_привод", (0.12, 0.30, 0.62), 0.3, 0.45),
    "sens": mat("АСУ_датчик_нерж", (0.70, 0.72, 0.75), 0.85, 0.3),
    "black": mat("АСУ_чёрный", (0.02, 0.02, 0.025), 0.2, 0.5),
    "screen": mat("АСУ_экран", (0.05, 0.25, 0.55), 0.0, 0.2, ((0.15, 0.45, 1.0), 2.0)),
    "red": mat("Безоп_красный", (0.80, 0.05, 0.04), 0.1, 0.4),
    "yellow": mat("Безоп_жёлтый", (0.95, 0.75, 0.05), 0.1, 0.45),
    "green_l": mat("АСУ_лампа_зелёная", (0.1, 0.8, 0.3), 0.0, 0.3, ((0.1, 1.0, 0.3), 3.0)),
    "amber_l": mat("АСУ_лампа_жёлтая", (0.9, 0.6, 0.05), 0.0, 0.3),
    "red_l": mat("АСУ_лампа_красная", (0.7, 0.05, 0.05), 0.0, 0.3),
    "orange": mat("Безоп_оранжевый", (1.0, 0.3, 0.05), 0.1, 0.4),
}
coll = bpy.data.collections.new("18_Автоматика_и_безопасность"); scene.collection.children.link(coll)

def box(name, c, s, m, rot=None):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0); bmesh.ops.scale(bm, vec=Vector(s), verts=bm.verts)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); o.location = c
    if rot: o.rotation_euler = rot
    me.materials.append(M[m]); coll.objects.link(o); o["material"] = M[m].name; return o
def cyl(name, c, r, d, m, axis='Z', seg=24):
    bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r, depth=d)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for p in me.polygons: p.use_smooth = True
    o = bpy.data.objects.new(name, me); o.location = c
    o.rotation_euler = {'X': (0, math.radians(90), 0), 'Y': (math.radians(90), 0, 0), 'Z': (0, 0, 0)}[axis]
    me.materials.append(M[m]); coll.objects.link(o); o["material"] = M[m].name; return o

# geometry constants of v4
XL, XR, YF, YB, ZB, Z_TOP, Z_FR = -3.0, 3.0, -1.65, 1.65, 0.10, 2.60, 2.66
CHX, PP_X, PP_Y, PP_ZTOP = 1.748, 0.703, 1.102, 3.444
CHIM_X, CHIM_Y = 3.28, -1.20
AIR_Y, AIR_Z = YB + 0.11, ZB + 0.517
CAB = Vector((XL - 0.19, -0.15, 1.45))

# PLC cabinet: HMI + signal tower + main switch
box("АСУ_ПЛК_панель_оператора_HMI", (XL - 0.345, -0.15, 1.62), (0.02, 0.34, 0.24), "screen")
cyl("АСУ_ПЛК_вводной_выключатель", (XL - 0.35, 0.08, 1.3), 0.04, 0.03, "red", axis='X')
for i, (mk, h) in enumerate((("black", 0.04), ("green_l", 0.07), ("amber_l", 0.07), ("red_l", 0.07))):
    cyl(f"АСУ_Сигнальная_колонна_{i}", (XL - 0.19, -0.35, 1.87 + 0.035 + sum([0.04, 0.07, 0.07, 0.07][:i]) + h / 2 - 0.035), 0.045, h, mk)
box("Безоп_Аварийный_стоп_шкаф_основание", (XL - 0.35, -0.40, 1.15), (0.03, 0.09, 0.09), "yellow")
cyl("Безоп_Аварийный_стоп_шкаф", (XL - 0.375, -0.40, 1.15), 0.035, 0.03, "red", axis='X')
# VFD of the combustion-air fan (next to the blower)
# VFD in its own cooled section next to the control cabinet (not on the hot wall): screened cable to the motor
box("АСУ_ЧРП_вентилятора", (XL - 0.19, 0.31, 1.45), (0.30, 0.30, 0.80), "cab")
box("АСУ_ЧРП_вентилятора_дисплей", (XL - 0.345, 0.31, 1.58), (0.01, 0.12, 0.07), "screen")
box("АСУ_ЧРП_вентилятора_решётка", (XL - 0.345, 0.31, 1.18), (0.01, 0.20, 0.14), "black")

for s in (-1, 1):
    # pressure transmitters of the shells (impulse line through the roof into the shell crown)
    cyl("АСУ_Датчик_давления_стакан_импульс", (s * CHX, 0.25, (2.31 + Z_FR) / 2 + 0.05), 0.008, Z_FR - 2.31 + 0.25, "sens", seg=8)
    cyl("АСУ_Датчик_давления_стакан", (s * CHX, 0.25, Z_FR + 0.25), 0.035, 0.12, "sens")
    box("АСУ_Датчик_давления_стакан_головка", (s * CHX, 0.25, Z_FR + 0.36), (0.09, 0.09, 0.09), "act")
    # shell relief valves (protection against over-pressure / gas deflagration)
    cyl("Безоп_Клапан_предохранительный_стакана", (s * (CHX - 0.5), 0.55, Z_FR + 0.12), 0.11, 0.18, "orange")
    cyl("Безоп_Клапан_предохранительный_стакана_патрубок", (s * (CHX - 0.5), 0.55, (2.31 + Z_FR) / 2), 0.06, Z_FR - 2.2, "sens")
    # UV flame sensors looking into the afterburning zone (back wall)
    cyl("АСУ_Датчик_пламени_УФ", (s * 0.42, YB + 0.09, ZB + 0.80), 0.035, 0.18, "sens", axis='Y')
    box("АСУ_Датчик_пламени_УФ_головка", (s * 0.42, YB + 0.21, ZB + 0.80), (0.08, 0.07, 0.08), "act")
    # actuators of the air dampers (afterburning zones)
    box("АСУ_Привод_заслонки_воздуха_дожиг", (s * 0.62 + s * 0.13, AIR_Y, ZB + 0.70), (0.14, 0.12, 0.12), "act")
    # actuators of the pyrolysis-pipe vents («свеча»)
    box("АСУ_Привод_свечи_пиролизной_трубы", (s * PP_X + s * 0.16, PP_Y, PP_ZTOP - 0.12), (0.14, 0.12, 0.16), "act")
    # chimney damper actuators + O2/CO analysers
    box("АСУ_Привод_шибера_трубы", (s * CHIM_X, CHIM_Y - 0.33, 3.0), (0.22, 0.16, 0.2), "act")
    cyl("АСУ_Привод_шибера_трубы_вал", (s * CHIM_X, CHIM_Y - 0.25, 3.0), 0.012, 0.12, "sens", axis='Y')
    cyl("АСУ_Газоанализатор_O2_CO_зонд", (s * (CHIM_X - 0.32), CHIM_Y, 2.25), 0.02, 0.3, "sens", axis='X')
    box("АСУ_Газоанализатор_O2_CO", (s * (CHIM_X - 0.52), CHIM_Y, 2.25), (0.16, 0.2, 0.26), "cab")
    box("АСУ_Газоанализатор_O2_CO_дисплей", (s * (CHIM_X - 0.52), CHIM_Y - 0.105, 2.3), (0.1, 0.01, 0.06), "screen")
    # door limit switches (loading doors closed & locked -> permissive for firing)
    box("АСУ_Концевик_двери", (s * 0.60, YF - 0.05, ZB + 2.25), (0.06, 0.06, 0.1), "yellow")
    # emergency stop stations at the front corners
    box("Безоп_Аварийный_стоп_основание", (s * 2.88, YF - 0.06, 1.3), (0.1, 0.06, 0.1), "yellow")
    cyl("Безоп_Аварийный_стоп", (s * 2.88, YF - 0.105, 1.3), 0.035, 0.035, "red", axis='Y')
# firebox air damper actuator
box("АСУ_Привод_заслонки_воздуха_топка", (0.15, YB + 0.05, ZB + 0.46), (0.14, 0.12, 0.12), "act")
# fire extinguisher OP-10 next to the control cabinet
cyl("Безоп_Огнетушитель_ОП10", (XL - 0.3, -0.75, 0.42), 0.085, 0.62, "red")
cyl("Безоп_Огнетушитель_ОП10_головка", (XL - 0.3, -0.75, 0.78), 0.03, 0.1, "black")

for o in coll.objects:
    o["assembly"] = "Автоматика и безопасность"

# --- service access (owner review 2026-11-12): free the ladder, move the fan to the back wall, no cage hoops
# Ladder by ГОСТ 23120: clear width 0.6 m, rung pitch 0.3 m, toe clearance ≥ 0.2 m, stringers 1.1 m above the roof
# edge with a gooseneck onto the roof; hoops are not required below 5 m — removed (they were 0.36 m deep: unusable).
from mathutils import Matrix
bpy.context.view_layer.update()                    # objects created above need valid world matrices
def world_edit(o, fn):
    if o.data.users > 1: o.data = o.data.copy()
    mw = o.matrix_world.copy(); inv = mw.inverted()
    for v in o.data.vertices: v.co = inv @ fn(mw @ v.co)
def move_group(prefixes, pivot, target, turn_deg):
    T = Matrix.Translation(Vector(target)) @ Matrix.Rotation(math.radians(turn_deg), 4, 'Z') @ Matrix.Translation(-Vector(pivot))
    for o in list(bpy.data.objects):
        if o.name.startswith(prefixes) and o.parent is None: o.matrix_world = T @ o.matrix_world

for o in list(bpy.data.objects):
    if o.name.startswith("Лестница_ограждение_дуга"): bpy.data.objects.remove(o, do_unlink=True)
LAD_Y0, LAD_Y1 = 0.85, 1.51                       # stringer axes → 0.60 m between them
for o in [o for o in bpy.data.objects if o.name.startswith("Лестница_тетива")]:
    yc = 0.95 if o.name == "Лестница_тетива" else 1.45
    ny = LAD_Y0 if o.name == "Лестница_тетива" else LAD_Y1
    world_edit(o, lambda p, yc=yc, ny=ny: Vector((p.x, p.y - yc + ny, 3.76 if p.z > 3.6 else p.z)))
for o in [o for o in bpy.data.objects if o.name.startswith("Лестница_ступень")]:
    world_edit(o, lambda p: Vector((p.x, LAD_Y0 + 0.03 if p.y < 1.2 else LAD_Y1 - 0.03, p.z)))
for i, y in enumerate((LAD_Y0, LAD_Y1)):           # gooseneck: stringer → over the roof edge → down to the roof
    box(f"Лестница_поручень_выход_{i}", (-3.0, y, 3.76), (0.5, 0.05, 0.05), "black")
    box(f"Лестница_поручень_выход_стойка_{i}", (-2.75, y, (3.76 + Z_FR) / 2), (0.05, 0.05, 3.76 - Z_FR), "black")
# roof guardrail at the ladder end: 1.1 m, knee rail, toe board; self-closing gate over the ladder opening
RZ = Z_FR
def rail_run(name, a, b):
    (x0, y0), (x1, y1) = a, b
    L = math.hypot(x1 - x0, y1 - y0); cx, cy = (x0 + x1) / 2, (y0 + y1) / 2; ang = math.atan2(y1 - y0, x1 - x0)
    for k, (z, h) in enumerate(((RZ + 1.1, 0.045), (RZ + 0.55, 0.035), (RZ + 0.075, 0.15))):
        box(f"Безоп_Ограждение_кровли_{name}_{k}", (cx, cy, z), (L, 0.04, h), "yellow" if k == 0 else "black", (0, 0, ang))
    n = max(2, int(L / 1.2) + 1)
    for j in range(n + 1):
        t = j / n; box(f"Безоп_Ограждение_кровли_{name}_стойка_{j}", (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, RZ + 0.55), (0.04, 0.04, 1.1), "black")
rail_run("торец", (-2.92, -1.6), (-2.92, LAD_Y0 - 0.12))
rail_run("угол", (-2.92, LAD_Y1 + 0.12), (-2.92, 1.6))
rail_run("тыл", (-2.92, 1.6), (-1.2, 1.6))
box("Безоп_Калитка_самозакрывающаяся", (-2.86, (LAD_Y0 + LAD_Y1) / 2, RZ + 1.0), (0.04, LAD_Y1 - LAD_Y0 - 0.12, 0.05), "yellow")
box("Безоп_Калитка_самозакрывающаяся_низ", (-2.86, (LAD_Y0 + LAD_Y1) / 2, RZ + 0.55), (0.04, LAD_Y1 - LAD_Y0 - 0.12, 0.04), "yellow")
cyl("Безоп_Анкерная_точка_страховки", (-2.35, 1.2, RZ + 0.08), 0.05, 0.16, "orange")
cyl("Безоп_Анкерная_точка_кольцо", (-2.35, 1.2, RZ + 0.19), 0.045, 0.02, "orange", axis='X')

# fan + motor to the back wall, at the start of the DN200 air main; VFD next to it — the ladder base stays clear (0.8 m)
FAN_C = (-2.55, 2.23)                               # 0.25 m off the main: room for flexible insert + check valve
move_group(("Вентилятор_",), (-3.85, 1.40, 0), (FAN_C[0], FAN_C[1], 0), 180)
for o in bpy.data.objects:
    if o.name.startswith("Труба_подачи_кислорода_DN200"):
        world_edit(o, lambda p: Vector((max(p.x, FAN_C[0] - 0.11), p.y, p.z)))
FX, FZ = FAN_C[0] - 0.11, 0.62                      # outlet axis: from the volute (y≈2.12) to the main (y≈1.80)
cyl("Вентилятор_патрубок_выход", (FX, 1.84, FZ), 0.105, 0.08, "sens", axis='Y')
cyl("Вентилятор_клапан_обратный", (FX, 1.94, FZ), 0.13, 0.12, "act", axis='Y')            # closes when the fan stops
cyl("Вентилятор_клапан_обратный_фланец", (FX, 1.875, FZ), 0.15, 0.015, "black", axis='Y')
cyl("Вентилятор_вставка_гибкая", (FX, 2.055, FZ), 0.115, 0.11, "black", axis='Y')          # vibration + thermal expansion
for k, y in enumerate((2.0, 2.11)): cyl(f"Вентилятор_вставка_хомут_{k}", (FX, y, FZ), 0.125, 0.012, "sens", axis='Y')
# guards (ТР ТС 010/2011): mesh on the suction, coupling guard, rain hood
cyl("Вентилятор_всас_сетка", (FAN_C[0] + 0.33, FAN_C[1], 0.5), 0.17, 0.03, "black", axis='X')
cyl("Вентилятор_всас_сетка_обод", (FAN_C[0] + 0.345, FAN_C[1], 0.5), 0.18, 0.012, "yellow", axis='X')
box("Вентилятор_кожух_муфты", (FAN_C[0] - 0.0, FAN_C[1] + 0.13, 0.5), (0.16, 0.08, 0.16), "yellow")
for k, (dx, dy) in enumerate(((-0.33, -0.3), (0.33, -0.3), (-0.33, 0.3), (0.33, 0.3))):
    box(f"Вентилятор_козырёк_стойка_{k}", (FAN_C[0] + dx, FAN_C[1] + dy, 0.6), (0.04, 0.04, 1.0), "black")
box("Вентилятор_козырёк", (FAN_C[0], FAN_C[1], 1.12), (0.78, 0.72, 0.03), "black", (math.radians(-6), 0, 0))
# local isolation (repair) switch in sight of the motor (ПУЭ), lockable
box("АСУ_Ремонтный_выключатель_стойка", (FAN_C[0] + 0.62, FAN_C[1] + 0.1, 0.55), (0.06, 0.06, 1.1), "black")
box("АСУ_Ремонтный_выключатель", (FAN_C[0] + 0.62, FAN_C[1] + 0.16, 1.05), (0.16, 0.08, 0.2), "cab")
box("АСУ_Ремонтный_выключатель_рукоять", (FAN_C[0] + 0.62, FAN_C[1] + 0.21, 1.05), (0.03, 0.03, 0.1), "red")
box("АСУ_Ремонтный_выключатель_шильд", (FAN_C[0] + 0.62, FAN_C[1] + 0.205, 1.05), (0.1, 0.005, 0.14), "yellow")
for o in bpy.data.objects:                         # widen the foundation slab behind the kiln for the fan skid
    if o.name.startswith("Фундаментная_плита"):
        world_edit(o, lambda p: Vector((p.x, 2.75 if p.y > 2.3 else p.y, p.z)))
bpy.context.view_layer.update()

# --- industrial colour scheme: graphite body (RAL 7021), signal red door leaves (RAL 3020), black frames & chimneys
def paint(name, rgb, metal, rough, clear=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*rgb, 1); b.inputs["Metallic"].default_value = metal; b.inputs["Roughness"].default_value = rough
    try: b.inputs["Coat Weight"].default_value = clear
    except KeyError: pass
    m.diffuse_color = (*rgb, 1); return m
GRAPHITE = paint("PROM_Графит_RAL7021", (0.024, 0.026, 0.029), 0.25, 0.52)
RED = paint("PROM_Оранжевый_Огонёк_RAL2004", (0.92, 0.17, 0.016), 0.05, 0.36, 0.4)   # flame orange of the mascot (#ff7417)
BLACK = paint("PROM_Чёрный_рама", (0.010, 0.010, 0.012), 0.35, 0.42)
bpy.context.view_layer.update()
for o in bpy.data.objects:
    if o.type != 'MESH' or not o.data.materials: continue
    mn = o.data.materials[0].name
    if o.name.startswith("Дверь_загрузочная"):
        if mn == "steel_paint":                       # door leaf 8 mm
            o.data.materials[0] = RED; continue
        if mn in ("steel_profile", "steel_hot"):
            # locking frame (rails, posts, diagonal) and hinges stand ~70 mm proud of the leaf -> black; grid & rim strips -> red
            yw = o.matrix_world.translation.y
            o.data.materials[0] = BLACK if (yw < -1.755 or mn == "steel_hot") else RED
            continue
    if mn == "steel_paint": o.data.materials[0] = GRAPHITE
    elif mn in ("steel_profile", "steel_black"): o.data.materials[0] = BLACK

# --- save + exports
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "PROMETHEY_kiln_v5.blend"), compress=True)
bpy.ops.object.select_all(action='DESELECT')
for o in bpy.data.objects:
    if o.type in ('MESH', 'EMPTY'): o.select_set(True)
kw = dict(export_format='GLB', use_selection=True, export_apply=True, export_extras=True,
          export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=7)
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "PROMETHEY_kiln_v5.glb"), **kw)
bpy.ops.export_scene.gltf(filepath=WEB, **kw)
print("V5 DONE", len([o for o in bpy.data.objects if o.type == 'MESH']), "automation parts", len(coll.objects))
