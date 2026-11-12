"""PROMETHEY retort charcoal kiln — engineering model v4 (per drawing УП040.003-4 СБ «Корпус печь сборка этап 4»).

Usage:
  blender -b --factory-startup -P build_furnace_v3.py -- <out_dir>

Real data (manufacturer, promethey-pechi.ru): kiln 6700 x 3520 mm (width incl. air-supply pipe),
mass 19 500 kg, 2 loading chambers 2900 x 1900 x 1900 mm, horizontal retort loading, pyrolysis-gas
afterburning, steel 09G2S, combustion cups 12 mm, front wall 8 mm, side walls & roof 5 mm,
insulation 150 mm (3 x 50 mm ceramic needled blanket), floor = refractory plate + fire brick,
built-in raw-material drying. Dryer 2300 x 2200 x 2500 mm, 1700 kg, 5.5 m3.
Everything else is an engineering assumption and is listed in the report.

Every mesh carries custom properties: material, density, volume_m3, mass_kg, assembly.
Masses are computed from the real mesh volume x material density.
"""
import bpy, bmesh, math, os, sys, json
from mathutils import Vector, Matrix

OUT = sys.argv[sys.argv.index("--") + 1]
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.length_unit = 'MILLIMETERS'

# ------------------------------------------------------------------ materials (PBR + physics)
# density kg/m3; "steel_profile" = rolled sections (channels/angles) modelled as solid bars:
# the effective density is reduced by the section fill factor (~0.15) so the mass stays real.
MAT = {}
def mat(key, rgb, metal, rough, density, label, emission=None):
    m = bpy.data.materials.new(key)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    if emission:
        b.inputs["Emission Color"].default_value = (*emission[0], 1)
        b.inputs["Emission Strength"].default_value = emission[1]
    m.diffuse_color = (*rgb, 1)
    m["density_kg_m3"] = density
    m["label"] = label
    MAT[key] = m
    return m

mat("steel_paint",   (0.030, 0.032, 0.034), 0.35, 0.55, 7850, "Сталь 09Г2С, окраска графит")
mat("steel_profile", (0.022, 0.023, 0.025), 0.45, 0.45, 7850 * 0.15, "Прокат 09Г2С (швеллер/уголок)")
mat("steel_hot",     (0.10, 0.09, 0.085), 0.8, 0.5, 7850, "Сталь 09Г2С, жаровая (без окраски)")
mat("steel_retort",  (0.16, 0.15, 0.14), 0.75, 0.55, 7850, "Сталь 09Г2С, реторта")
mat("steel_black",   (0.012, 0.012, 0.013), 0.5, 0.45, 7850, "Сталь, термостойкая краска")
mat("steel_galv",    (0.50, 0.52, 0.55), 0.6, 0.5, 7850, "Оцинкованная сталь / кожух изоляции")
mat("cast_iron",     (0.06, 0.06, 0.06), 0.6, 0.6, 7200, "Чугун (колосники, колёса)")
mat("fiber",         (0.93, 0.93, 0.90), 0.0, 0.92, 128, "Керамоволокно иглопробивное 128 кг/м³")
mat("plate",         (0.78, 0.76, 0.70), 0.0, 0.9, 350, "Огнеупорная теплоизоляционная плита")
mat("firebrick",     (0.62, 0.27, 0.17), 0.0, 0.85, 1900, "Шамотный кирпич ШБ")
mat("concrete",      (0.26, 0.25, 0.23), 0.0, 0.92, 2400, "Бетон")
mat("wood",          (0.45, 0.30, 0.17), 0.0, 0.85, 0, "Загрузка (масса задаётся расчётом)")
mat("orange",        (1.0, 0.25, 0.05), 0.0, 0.4, 7850, "Сигнальная окраска (арматура)")
mat("red_valve",     (0.75, 0.06, 0.05), 0.2, 0.4, 7850, "Запорная арматура")
mat("cabinet",       (0.60, 0.62, 0.64), 0.2, 0.4, 7850 * 0.12, "Шкаф управления (полый)")
mat("motor",         (0.16, 0.32, 0.55), 0.4, 0.4, 7850 * 0.35, "Электродвигатель")
mat("rubber",        (0.02, 0.02, 0.02), 0.0, 0.8, 1200, "Резина / уплотнение")
mat("glow",          (0.9, 0.3, 0.05), 0.0, 0.5, 7850, "Пламя (визуал)", emission=((1.0, 0.35, 0.05), 6.0))
MAT["glow"]["density_kg_m3"] = 0
mat("ground",        (0.33, 0.31, 0.27), 0.0, 0.95, 0, "Грунт")

# ------------------------------------------------------------------ collections
def coll(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or scene.collection).children.link(c)
    return c
ROOT = coll("PROMETHEY_kiln")
C = {k: coll(v, ROOT) for k, v in {
    "found": "00_Фундамент", "frame": "01_Рама_и_каркас", "case": "02_Корпус_сталь", "ins": "03_Теплоизоляция",
    "brick": "04_Под_и_кладка", "door": "05_Двери", "cup": "06_Стаканы_камеры_сгорания_и_топка", "retL": "07_Реторта_левая",
    "retR": "08_Реторта_правая_выкачена", "gas": "09_Трубы_пиролизные_ТП200", "air": "10_Воздух_горения",
    "chim": "11_Дымовые_трубы", "roof": "12_Крыша", "ctrl": "13_КИП_и_управление", "track": "14_Выкатная_площадка",
    "dry": "15_Сушильная_камера", "cool": "16_Шкафы_остывания", "split": "17_Дровокол_ДГ360",
}.items()}

ASSEMBLY = {  # collection key -> report assembly name, part of passport mass?
    "found": ("Фундаментная плита", False), "frame": ("Рама и каркас", True), "case": ("Корпус (обшивка, внутренний лист)", True),
    "ins": ("Теплоизоляция", True), "brick": ("Под и огнеупорная кладка", True), "door": ("Двери (ДК011-2, ДС010, ДТ010) и навесы", True),
    "cup": ("Стаканы — камеры сгорания Ø1924×12 и топка", True), "retL": ("Реторта №1 (в камере)", False), "retR": ("Реторта №2 (на площадке)", False),
    "gas": ("Трубы пиролизные ТП200 (поз. 5, 6)", True), "air": ("Система воздуха горения", True), "chim": ("Дымовые трубы и газоходы", True),
    "roof": ("Крыша и шибер", True), "ctrl": ("КИП, шкаф управления, лестница", True), "track": ("Выкатная площадка и лебёдка", False),
    "dry": ("Сушильная камера", False), "cool": ("Шкафы остывания (2 шт.)", False), "split": ("Дровокол ДГ 360", False),
}

OBJS = []
def reg(ob, ckey, mkey, mass_override=None, cut=False):
    C[ckey].objects.link(ob)
    if ob.type == 'MESH' and not ob.data.materials:
        ob.data.materials.append(MAT[mkey])
    ob["material"] = MAT[mkey]["label"]
    ob["density_kg_m3"] = MAT[mkey]["density_kg_m3"]
    ob["assembly"] = ASSEMBLY[ckey][0]
    ob["_ckey"] = ckey
    if mass_override is not None:
        ob["mass_override_kg"] = float(mass_override)
    if cut:
        ob["cutaway_hide"] = True
    OBJS.append(ob)
    return ob

def mesh_ob(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    return bpy.data.objects.new(name, me)

def box(name, ck, mk, center, size, rot=None, mass=None, cut=False):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    ob = mesh_ob(name, bm)
    ob.location = center
    if rot: ob.rotation_euler = rot
    return reg(ob, ck, mk, mass, cut)

def shell_mass(dx, dy, dz, t, faces=6, rho=7850):
    """mass of a hollow welded box made of sheet t (faces: 6 closed, 5 open top, 4 open both ends)"""
    a = [dx * dy, dx * dy, dy * dz, dy * dz, dx * dz, dx * dz][:faces]
    return sum(a) * t * rho

def box_mm(name, ck, mk, x0, x1, y0, y1, z0, z1, **kw):
    return box(name, ck, mk, ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), (abs(x1 - x0), abs(y1 - y0), abs(z1 - z0)), **kw)

def cyl(name, ck, mk, center, r, depth, axis='Z', seg=32, mass=None, cut=False):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r, depth=depth)
    ob = mesh_ob(name, bm)
    for p in ob.data.polygons: p.use_smooth = True
    ob.location = center
    ob.rotation_euler = {'X': (0, math.radians(90), 0), 'Y': (math.radians(90), 0, 0), 'Z': (0, 0, 0)}[axis]
    return reg(ob, ck, mk, mass, cut)

def tube(name, ck, mk, center, r_out, t, h, axis='Z', seg=40, cut=False):
    """hollow cylinder (real wall thickness -> real volume)"""
    bm = bmesh.new()
    rings = []
    for z in (-h / 2, h / 2):
        rings.append([[bm.verts.new((rr * math.cos(2 * math.pi * i / seg), rr * math.sin(2 * math.pi * i / seg), z)) for i in range(seg)] for rr in (r_out, r_out - t)])
    (bo, bi), (to, ti) = rings
    for i in range(seg):
        j = (i + 1) % seg
        bm.faces.new((bo[i], bo[j], to[j], to[i]))
        bm.faces.new((bi[j], bi[i], ti[i], ti[j]))
        bm.faces.new((bo[j], bo[i], bi[i], bi[j]))
        bm.faces.new((to[i], to[j], ti[j], ti[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = mesh_ob(name, bm)
    for p in ob.data.polygons: p.use_smooth = True
    ob.location = center
    ob.rotation_euler = {'X': (0, math.radians(90), 0), 'Y': (math.radians(90), 0, 0), 'Z': (0, 0, 0)}[axis]
    return reg(ob, ck, mk, None, cut)

def beam(name, ck, mk, p0, p1, t, d=None, mass=None):
    p0, p1 = Vector(p0), Vector(p1)
    v = p1 - p0
    ob = box(name, ck, mk, (p0 + p1) / 2, (t, d or t, v.length), mass=mass)
    ob.rotation_euler = v.to_track_quat('Z', 'Y').to_euler()
    return ob

def pipe(name, ck, mk, pts, r, wall=0.004, rho=7850, extra=1.0):
    """bent pipe from a polyline; mass = hollow pipe pi*D*t*L*rho*extra"""
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'; cu.bevel_depth = r; cu.bevel_resolution = 5; cu.use_fill_caps = True
    sp = cu.splines.new('POLY'); sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts): sp.points[i].co = (*p, 1)
    L = sum((Vector(a) - Vector(b)).length for a, b in zip(pts, pts[1:]))
    ob = bpy.data.objects.new(name, cu)
    cu.materials.append(MAT[mk])
    return reg(ob, ck, mk, math.pi * 2 * r * wall * L * rho * extra)

def corrugated(name, ck, mk, base, r, h, amp, pitch, wall, seg=32):
    bm = bmesh.new()
    steps = int(h / (pitch / 4)); rings = []
    for k in range(steps + 1):
        z = h * k / steps
        rr = r + amp * math.sin(2 * math.pi * z / pitch)
        rings.append([bm.verts.new((rr * math.cos(2 * math.pi * i / seg), rr * math.sin(2 * math.pi * i / seg), z)) for i in range(seg)])
    for a, b in zip(rings, rings[1:]):
        for i in range(seg):
            bm.faces.new((a[i], a[(i + 1) % seg], b[(i + 1) % seg], b[i]))
    bm.faces.new(list(reversed(rings[0]))); bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = mesh_ob(name, bm)
    for p in ob.data.polygons: p.use_smooth = True
    ob.location = base
    corr = math.sqrt(1 + (2 * math.pi * amp / pitch) ** 2)  # developed length factor
    return reg(ob, ck, mk, 2 * math.pi * r * wall * h * 7850 * corr)

def lug(name, ck, center, rot_z=0.0):
    """lifting lug plate 30 mm, R130, hole D90 (09G2S)"""
    bm = bmesh.new()
    w, h, R, t, rh = 0.26, 0.17, 0.13, 0.03, 0.045
    prof = [(-w / 2, 0), (w / 2, 0), (w / 2, h)] + [(R * math.cos(math.pi * i / 16), h + R * math.sin(math.pi * i / 16)) for i in range(1, 16)] + [(-w / 2, h)]
    f = bm.faces.new([bm.verts.new((x, -t / 2, z)) for x, z in prof])
    ext = bmesh.ops.extrude_face_region(bm, geom=[f])
    bmesh.ops.translate(bm, vec=(0, t, 0), verts=[e for e in ext['geom'] if isinstance(e, bmesh.types.BMVert)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = mesh_ob(name, bm)
    ob.location = center; ob.rotation_euler = (0, 0, rot_z)
    hole_area = math.pi * rh * rh
    area = w * h + math.pi * R * R / 2
    return reg(ob, ck, "steel_profile", (area - hole_area) * t * 7850)

# ------------------------------------------------------------------ main dimensions — drawing УП040.003-4 СБ (М 1:15)
# Front view: 2460 | 60 | 960 | 60 | 2460 = 6000; panels 2500 high on a 100 mm base, 60 mm top frame.
# Side view: depth 3300 (+ O2 pipe 220 = 3520 passport). Section Д-Д: two horizontal combustion
# shells («стаканы») Ø1924 x 12 (inner Ø1900), length 2900 = passport chamber 2900 x 1900 x 1900.
XL, XR = -3.0, 3.0
YF, YB = -1.65, 1.65
ZB = 0.10                         # base frame height -> bottom of casing panels
Z_TOP = ZB + 2.50                 # top of casing panels (2.60)
Z_FR = Z_TOP + 0.06               # top frame 60 mm (2.66)
T5, T8, T12, INS = 0.005, 0.008, 0.012, 0.15
CHX = 1.748                       # shell / door axis |x| (front view: door centre 1252 mm from casing end)
SK_RO, SK_T, SK_L = 0.962, 0.012, 2.90
SK_RI = SK_RO - SK_T
SK_ZC = ZB + 1.25                 # shell axis height (Д-Д: 1238..1258 above panel bottom)
SK_Y0 = YF + T8
SK_Y1 = SK_Y0 + SK_L
PX = 0.51                         # partitions between chamber sections and centre section
PP_X, PP_Y = 0.703, YB - 0.548    # pyrolysis pipes ТП200 (side view: 548 mm from back wall)
PP_RO, PP_T = 0.0795, 0.006       # Ø159 x 6 (68.46 kg per spec)
PP_ZTOP, PP_ZBOT, PP_ZSTUB = ZB + 3.344, ZB + 0.845, ZB + 1.897
FLOOR = ZB + 0.005 + 0.10 + 0.065  # 5 mm bottom sheet + refractory plate 100 + fire brick 65
RAIL_IN = SK_ZC - math.sqrt(SK_RI ** 2 - 0.45 ** 2) + 0.04   # rail top inside the shell
WR = 0.06                          # retort wheel radius
RT_RO, RT_T, RT_L = 0.88, 0.006, 2.80
RT_AXIS_OFF = WR + math.sqrt(RT_RO ** 2 - 0.45 ** 2) + 0.02  # rail top -> retort axis

def bake_round_holes(ob, holes):
    """cut round holes (centre, radius, axis) with booleans and bake them into the mesh"""
    cutters = []
    for (c, r, ax) in holes:
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=64, radius1=r, radius2=r, depth=1.0)
        cu = mesh_ob("_cutter", bm); cu.location = c
        cu.rotation_euler = {'X': (0, math.radians(90), 0), 'Y': (math.radians(90), 0, 0), 'Z': (0, 0, 0)}[ax]
        scene.collection.objects.link(cu); cutters.append(cu)
        md = ob.modifiers.new("hole", 'BOOLEAN'); md.object = cu; md.operation = 'DIFFERENCE'; md.solver = 'EXACT'
    bpy.context.view_layer.update()
    dgx = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dgx))
    ob.modifiers.clear(); old = ob.data; ob.data = me
    bpy.data.meshes.remove(old)
    for cu in cutters: bpy.data.objects.remove(cu)
    return ob

# ------------------------------------------------------------------ foundation
box_mm("Фундаментная_плита", "found", "concrete", XL - 1.15, XR + 0.95, YF - 0.35, YB + 0.7, -0.20, 0.0)

# ------------------------------------------------------------------ base frame (channel 100)
for y in (YF + 0.05, -0.55, 0.55, YB - 0.05):
    box_mm("Рама_продольная_швеллер100", "frame", "steel_profile", XL, XR, y - 0.025, y + 0.025, 0, ZB)
for k in range(11):
    x = XL + 0.05 + k * (6.0 - 0.1) / 10
    box_mm("Рама_поперечная_швеллер100", "frame", "steel_profile", x - 0.025, x + 0.025, YF, YB, 0.01, ZB - 0.01)

# ------------------------------------------------------------------ casing skin (5 mm, front 8 mm with two Ø1900 openings)
box_mm("Днище_5мм", "case", "steel_hot", XL, XR, YF, YB, ZB, ZB + T5)
box_mm("Задняя_стенка_5мм", "case", "steel_paint", XL, XR, YB - T5, YB, ZB, Z_TOP)
box_mm("Торец_левый_5мм", "case", "steel_paint", XL, XL + T5, YF, YB, ZB, Z_TOP)
box_mm("Торец_правый_5мм", "case", "steel_paint", XR - T5, XR, YF, YB, ZB, Z_TOP)
fw = box_mm("Передняя_стенка_8мм", "case", "steel_paint", XL, XR, YF, YF + T8, ZB, Z_TOP, cut=True)
bake_round_holes(fw, [((s * CHX, YF, SK_ZC), SK_RI, 'Y') for s in (-1, 1)])
for s in (-1, 1):  # partitions between chamber sections and the centre section
    box_mm("Перегородка_секций_5мм", "case", "steel_hot", s * PX - 0.0025, s * PX + 0.0025, YF + T8, YB - T5, ZB + T5, Z_TOP - T5)
# end-wall flue openings (to chimney flue boxes) and Ø159 ports (side view)
for s in (-1, 1):
    box_mm("Торец_рамка_проёма_газохода", "case", "steel_profile", s * XR - 0.01, s * XR + 0.01, -1.38, -0.84, ZB + 0.14, ZB + 0.67)
    for y in (YB - 1.066, YB - 2.537):
        tube("Патрубок_торцевой_D159", "case", "steel_hot", (s * (XR + 0.05), y, ZB + 1.805), 0.0795, 0.006, 0.2, axis='X')
        cyl("Патрубок_фланец", "case", "steel_hot", (s * (XR + 0.15), y, ZB + 1.805), 0.13, 0.016, axis='X')

# ------------------------------------------------------------------ external frame (square tube 60, side view belts)
for x in (XL, XR):
    for y in (YF + 0.03, 0.0, YB - 0.03):
        box_mm("Стойка_каркаса_60", "frame", "steel_profile", x - 0.03, x + 0.03, y - 0.03, y + 0.03, ZB, Z_TOP, cut=(y < -1))
for x in (-PX - 0.03, PX + 0.03):
    box_mm("Стойка_центральной_секции_60", "frame", "steel_profile", x - 0.03, x + 0.03, YF - 0.06, YF, ZB, Z_TOP, cut=True)
for z in (Z_TOP + 0.03, ZB + 1.25):
    box_mm("Пояс_задний_60", "frame", "steel_profile", XL, XR, YB, YB + 0.06, z - 0.03, z + 0.03)
    for x, s in ((XL, -1), (XR, 1)):
        box_mm("Пояс_торцевой_60", "frame", "steel_profile", x - 0.06 if s < 0 else x, x if s < 0 else x + 0.06, YF, YB, z - 0.03, z + 0.03)
box_mm("Пояс_передний_верх_60", "frame", "steel_profile", XL, XR, YF - 0.06, YF, Z_TOP - 0.06, Z_TOP, cut=True)
box_mm("Ригель_центр_60", "frame", "steel_profile", -PX, PX, YF - 0.06, YF, ZB + 0.90, ZB + 0.96, cut=True)
for (x0_, x1_, y0_, y1_) in ((XL, XR, YF, YF + 0.06), (XL, XR, YB - 0.06, YB), (XL, XL + 0.06, YF, YB), (XR - 0.06, XR, YF, YB)):
    box_mm("Рама_верхняя_труба_60х60х4", "frame", "steel_profile", x0_, x1_, y0_, y1_, Z_TOP, Z_FR, mass=max(x1_ - x0_, y1_ - y0_) * 4 * 0.06 * 0.004 * 7850, cut=(y1_ < -1.5))

# ------------------------------------------------------------------ insulation 150 mm (3 x 50 blanket)
def ins_layers(name, x0, x1, y0, y1, z0, z1, axis, cut=False, holes=None):
    for k in range(3):
        a = [x0, x1, y0, y1, z0, z1]
        i0 = {"x": 0, "y": 2, "z": 4}[axis]
        lo, hi = a[i0], a[i0 + 1]
        a[i0], a[i0 + 1] = lo + (hi - lo) * k / 3, lo + (hi - lo) * (k + 1) / 3
        ob = box_mm(f"{name}_слой{k + 1}_50мм", "ins", "fiber", *a, cut=cut)
        if holes: bake_round_holes(ob, holes)

ins_layers("Изоляция_крыша", XL + T5, XR - T5, YF + T8, YB - T5, Z_TOP - T5 - INS, Z_TOP - T5, "z", cut=True,
           holes=[((s * PP_X, PP_Y, Z_TOP), PP_RO + 0.01, 'Z') for s in (-1, 1)])
ins_layers("Изоляция_задняя", XL + T5, XR - T5, YB - T5 - INS, YB - T5, FLOOR, Z_TOP - T5 - INS, "y")
ins_layers("Изоляция_торец_лев", XL + T5, XL + T5 + INS, YF + T8 + INS, YB - T5 - INS, FLOOR, Z_TOP - T5 - INS, "x")
ins_layers("Изоляция_торец_прав", XR - T5 - INS, XR - T5, YF + T8 + INS, YB - T5 - INS, FLOOR, Z_TOP - T5 - INS, "x")
ins_layers("Изоляция_передняя", XL + T5, XR - T5, YF + T8, YF + T8 + INS, FLOOR, Z_TOP - T5 - INS, "y", cut=True,
           holes=[((s * CHX, YF, SK_ZC), SK_RO, 'Y') for s in (-1, 1)])

# ------------------------------------------------------------------ floor: refractory plate 100 + fire brick 65 (passport)
box_mm("Под_огнеупорная_плита_100мм", "brick", "plate", XL + T5, XR - T5, YF + T8, YB - T5, ZB + T5, ZB + T5 + 0.10)
for s in (-1, 1):
    box_mm("Под_шамотный_кирпич_65мм", "brick", "firebrick", s * PX + (0.0025 if s > 0 else -0.0025), s * (XR - T5 - INS), YF + T8 + INS, YB - T5 - INS, ZB + T5 + 0.10, FLOOR)
# centre section: startup firebox, fire-brick lined (behind the firebox door)
FB = dict(x0=-0.40, x1=0.40, y0=YF + T8 + INS, y1=YF + 1.30, z0=ZB + T5 + 0.10, z1=ZB + 0.85)
box_mm("Топка_под_кирпич", "brick", "firebrick", FB["x0"], FB["x1"], FB["y0"], FB["y1"], FB["z0"], FB["z0"] + 0.13)
for x in (FB["x0"], FB["x1"] - 0.115):
    box_mm("Топка_стенка_кирпич", "brick", "firebrick", x, x + 0.115, FB["y0"], FB["y1"], FB["z0"] + 0.13, FB["z1"])
box_mm("Топка_задняя_кирпич", "brick", "firebrick", FB["x0"] + 0.115, FB["x1"] - 0.115, FB["y1"] - 0.115, FB["y1"], FB["z0"] + 0.13, FB["z1"])
box_mm("Топка_свод_сталь12", "cup", "steel_hot", FB["x0"], FB["x1"], FB["y0"], FB["y1"], FB["z1"], FB["z1"] + T12)
for i in range(6):
    x = -0.225 + i * 0.09
    box_mm("Колосник_чугун", "cup", "cast_iron", x - 0.02, x + 0.02, FB["y0"] + 0.05, FB["y1"] - 0.15, ZB + 0.33, ZB + 0.37)
for s in (-1, 1):  # hot-gas windows from the firebox through the partitions into the chamber sections
    box_mm("Окно_топки_в_секцию", "cup", "steel_hot", min(s * FB["x1"], s * (PX + 0.06)), max(s * FB["x1"], s * (PX + 0.06)), FB["y0"] + 0.2, FB["y0"] + 0.6, ZB + 0.45, ZB + 0.75, mass=shell_mass(0.17, 0.4, 0.3, T12, 4))

# ------------------------------------------------------------------ combustion shells «стаканы» Ø1924 x 12, L 2900 (2 pcs)
for s in (-1, 1):
    cut = (s < 0)
    yc = (SK_Y0 + SK_Y1) / 2
    tube("Стакан_камера_сгорания_D1924x12", "cup", "steel_hot", (s * CHX, yc, SK_ZC), SK_RO, SK_T, SK_L, axis='Y', seg=72, cut=cut)
    cyl("Стакан_днище_12мм", "cup", "steel_hot", (s * CHX, SK_Y1 + SK_T / 2, SK_ZC), SK_RO, SK_T, axis='Y', seg=72)
    tube("Стакан_фланец_устья", "cup", "steel_hot", (s * CHX, SK_Y0 + 0.012, SK_ZC), SK_RO + 0.06, 0.06 + SK_T, 0.024, axis='Y', seg=72, cut=True)
    for k in range(4):  # stiffening rings, flat bar 50 x 12
        tube("Стакан_кольцо_жёсткости_50х12", "cup", "steel_hot", (s * CHX, SK_Y0 + 0.40 + k * 0.70, SK_ZC), SK_RO + 0.05, 0.05, 0.012, axis='Y', seg=72, cut=cut)
    for k in range(3):  # saddles on the floor
        y = SK_Y0 + 0.40 + k * 1.05
        box_mm("Стакан_опора_ложемент", "cup", "steel_profile", s * CHX - 0.30, s * CHX + 0.30, y - 0.06, y + 0.06, FLOOR, SK_ZC - SK_RO + 0.06)
    for dx in (-0.45, 0.45):  # rails inside the shell for the retort wheels
        box_mm("Стакан_рельс_40х40", "cup", "steel_hot", s * CHX + dx - 0.02, s * CHX + dx + 0.02, SK_Y0 + 0.02, SK_Y1 - 0.02, RAIL_IN - 0.05, RAIL_IN, cut=cut)
    tube("Стакан_штуцер_слива_конденсата", "cup", "steel_hot", (s * CHX, SK_Y1 - 0.35, SK_ZC - SK_RO - 0.05), 0.025, 0.004, 0.1)

# ------------------------------------------------------------------ pyrolysis pipes ТП200Л-2 / ТП200П-2 (pos. 5, 6): Ø159 x 6, 68.46 kg each
for s, nm in ((-1, "ТП200Л-2_левая_поз5"), (1, "ТП200П-2_правая_поз6")):
    x = s * PP_X
    main = pipe(f"Труба_пиролизная_{nm}", "gas", "steel_hot",
                [(x, PP_Y, PP_ZTOP), (x, PP_Y, PP_ZBOT), (x - s * 0.03, PP_Y, PP_ZBOT - 0.08), (x - s * 0.08, PP_Y, PP_ZBOT - 0.10), (x - s * 0.10, PP_Y, PP_ZBOT - 0.04)], PP_RO, wall=PP_T)
    x_in = s * (CHX - math.sqrt(SK_RI ** 2 - (PP_ZSTUB - SK_ZC) ** 2))   # inner face of the shell (protrusion trimmed per note)
    stub = pipe(f"Труба_пиролизная_отвод_в_стакан_{nm}", "gas", "steel_hot", [(x, PP_Y, PP_ZSTUB), (x_in, PP_Y, PP_ZSTUB)], PP_RO, wall=PP_T)
    L_main = 2 * (PP_ZTOP - PP_ZBOT) / 2 + 0.36
    L_stub = abs(x_in - x)
    main["mass_override_kg"] = 68.46 * L_main / (L_main + L_stub)
    stub["mass_override_kg"] = 68.46 * L_stub / (L_main + L_stub)
    tube("Гильза_прохода_крыши", "gas", "steel_hot", (x, PP_Y, Z_TOP + 0.03), PP_RO + 0.03, 0.004, 0.12)
    cyl("Свеча_откидная_заслонка", "gas", "orange", (x, PP_Y, PP_ZTOP + 0.012), PP_RO + 0.02, 0.012, mass=3.0)

# ------------------------------------------------------------------ retorts (cylindrical, horizontal loading on rails)
def retort(ck, cx, y0, rail_top, charge=True):
    axz = rail_top + RT_AXIS_OFF
    lidcut = (ck == "retL")
    yc = y0 + RT_L / 2
    tube("Реторта_обечайка_D1760x6", ck, "steel_retort", (cx, yc, axz), RT_RO, RT_T, RT_L, axis='Y', seg=64)
    cyl("Реторта_днище_6мм", ck, "steel_retort", (cx, y0 + RT_L - RT_T / 2, axz), RT_RO, RT_T, axis='Y', seg=64)
    cyl("Реторта_крышка_8мм", ck, "steel_retort", (cx, y0 - 0.004, axz), RT_RO + 0.025, 0.008, axis='Y', seg=64, cut=lidcut)
    for k in range(8):
        a = 2 * math.pi * k / 8
        box("Реторта_клиновой_зажим", ck, "steel_profile", (cx + (RT_RO + 0.03) * math.cos(a), y0 + 0.01, axz + (RT_RO + 0.03) * math.sin(a)), (0.06, 0.08, 0.06), cut=lidcut)
    cyl("Реторта_тяговая_проушина", ck, "steel_profile", (cx, y0 - 0.05, axz - 0.55), 0.05, 0.03, axis='Y', cut=lidcut)
    for k in range(2):
        tube("Реторта_кольцо_20мм", ck, "steel_retort", (cx, y0 + 0.9 + k * 1.0, axz), RT_RO + 0.02, 0.02, 0.012, axis='Y', seg=64)
    for yy in (y0 + 0.45, y0 + RT_L - 0.45):
        cyl("Реторта_ось_D50", ck, "steel_hot", (cx, yy, rail_top + WR), 0.025, 1.0, axis='X')
        for dx in (-0.45, 0.45):
            cyl("Реторта_колесо_чугун_D120", ck, "cast_iron", (cx + dx, yy, rail_top + WR), WR, 0.05, axis='X')
            cyl("Реторта_реборда", ck, "cast_iron", (cx + dx - 0.035, yy, rail_top + WR), WR + 0.015, 0.012, axis='X')
            box_mm("Реторта_кронштейн_колеса", ck, "steel_profile", cx + dx + 0.03, cx + dx + 0.05, yy - 0.06, yy + 0.06, rail_top + WR, axz - math.sqrt(RT_RO ** 2 - (abs(dx) + 0.04) ** 2) + 0.01)
    for dx in (-0.3, 0.3):   # gas outlet holes in the back head -> shell volume -> pyrolysis pipe
        tube("Реторта_газовыпуск_D100", ck, "steel_retort", (cx + dx, y0 + RT_L + 0.04, axz + 0.55), 0.05, 0.004, 0.08, axis='Y')
    for dx in (-0.55, 0.55):
        box_mm("Реторта_рым_крановый", ck, "steel_profile", cx + dx - 0.05, cx + dx + 0.05, yc - 0.012, yc + 0.012, axz + RT_RO - 0.05, axz + RT_RO + 0.07, cut=lidcut)
    if charge:   # stacked logs filling the round section (mass from the yield calculation)
        bm = bmesh.new()
        r = 0.055; R_in = RT_RO - RT_T - 0.01
        z = -R_in + r
        row = 0
        while z < R_in - r:
            half = math.sqrt(max(R_in ** 2 - (abs(z) + r) ** 2, 0)) - r
            n = int((2 * half) / (2 * r + 0.008)) + 1
            if n > 0:
                x0r = -((n - 1) * (2 * r + 0.008)) / 2 + (row % 2) * 0.004
                for i in range(n):
                    for seg_y in range(2):
                        m = Matrix.Translation((cx + x0r + i * (2 * r + 0.008), y0 + 0.05 + 0.68 + seg_y * 1.36, axz + z)) @ Matrix.Rotation(math.radians(90), 4, 'X')
                        bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=r, radius2=r, depth=1.32, matrix=m)
            z += 2 * r + 0.004; row += 1
        ob = mesh_ob("Загрузка_дрова_полено_1.3м", bm)
        reg(ob, ck, "wood", 0.0)
        ob["note"] = "Масса загрузки — в отчёте (зависит от породы и влажности)"
    return axz

RET_AXIS_IN = retort("retL", -CHX, SK_Y0 + 0.04, RAIL_IN)

# ------------------------------------------------------------------ doors: loading «Дверь квадратная» ДК011-2 2250 x 2250 (pos. 9, 2 pcs)
D_W = D_H = 2.25
D_ZC = ZB + 1.258
YD = YF - 0.04
def door(name, cx, hinge_side, open_deg=0.0):
    hx = cx + hinge_side * D_W / 2
    pivot = bpy.data.objects.new(name + "_ось_навесов", None)
    pivot.location = (hx, YD, 0); pivot.empty_display_size = 0.3
    C["door"].objects.link(pivot)
    parts = []
    def P(ob): parts.append(ob); return ob
    x0, x1 = cx - D_W / 2, cx + D_W / 2
    z0, z1 = D_ZC - D_H / 2, D_ZC + D_H / 2
    P(box_mm(name + "_лист_8мм", "door", "steel_paint", x0, x1, YD - T8, YD, z0, z1, cut=True))
    for k in range(3):
        P(cyl(name + f"_пробка_изоляции_слой{k + 1}", "door", "fiber", (cx, YD + 0.025 + k * 0.05, SK_ZC), SK_RI - 0.012, 0.048, axis='Y', seg=64, cut=True))
    P(tube(name + "_уплотнение_шнур", "door", "rubber", (cx, YD + 0.004, SK_ZC), SK_RO + 0.03, 0.025, 0.008, axis='Y', seg=64, cut=True))
    yb = YD - T8
    for z in (z0 + 0.025, z1 - 0.025):
        P(box_mm(name + "_рамка_гор", "door", "steel_profile", x0, x1, yb - 0.05, yb, z - 0.025, z + 0.025, cut=True))
    for x in (x0 + 0.025, x1 - 0.025):
        P(box_mm(name + "_рамка_верт", "door", "steel_profile", x - 0.025, x + 0.025, yb - 0.05, yb, z0, z1, cut=True))
    for k in (1, 2, 3):
        xx = x0 + 0.08 + (D_W - 0.16) * k / 4
        P(box_mm(name + "_полоса_верт", "door", "steel_profile", xx - 0.02, xx + 0.02, yb - 0.02, yb, z0 + 0.1, z1 - 0.1, cut=True))
        zz = z0 + 0.1 + (D_H - 0.2) * k / 4
        P(box_mm(name + "_полоса_гор", "door", "steel_profile", x0 + 0.08, x1 - 0.08, yb - 0.02, yb, zz - 0.02, zz + 0.02, cut=True))
    # locking frame per drawing: rails at +1745 / +685 mm, posts 379 / 1120 mm from the casing end, channel 6.5П
    yf = yb - 0.07
    xe = hinge_side * XR                        # casing end on the hinge side
    sg = -hinge_side                            # direction towards the centre
    for z in (ZB + 1.745, ZB + 0.685):
        P(box_mm(name + "_запорный_ригель_6.5П", "door", "steel_profile", min(xe + sg * 0.019, xe + sg * 1.229), max(xe + sg * 0.019, xe + sg * 1.229), yf - 0.018, yf + 0.018, z - 0.0325, z + 0.0325, cut=True))
    v1, v2 = xe + sg * 0.379, xe + sg * 1.120
    for x in (v1, v2):
        P(box_mm(name + "_запорная_стойка_6.5П", "door", "steel_profile", x - 0.0325, x + 0.0325, yf - 0.018, yf + 0.018, ZB + 0.685, ZB + 1.745, cut=True))
    P(beam(name + "_раскос", "door", "steel_profile", (v1 - sg * 0.03, yf, ZB + 0.72), (v2 + sg * 0.03, yf, ZB + 1.71), 0.06)); parts[-1]["cutaway_hide"] = True
    for z in (z0 + 0.25, z0 + 0.85, z1 - 0.85, z1 - 0.25):   # «Навес 40x170» ДО040 (4 per door)
        P(cyl(name + "_навес_40х170_ДО040", "door", "steel_hot", (hx + hinge_side * 0.03, YD - 0.03, z), 0.02, 0.17, mass=1.63))
    inv = Matrix.Translation(pivot.location).inverted()
    for p in parts:
        p.parent = pivot
        p.matrix_parent_inverse = inv
    pivot.rotation_euler = (0, 0, math.radians(open_deg) * hinge_side)
    pivot["assembly"] = ASSEMBLY["door"][0]
    return pivot

door("Дверь_загрузочная_левая_ДК011-2", -CHX, -1, 0.0)
door("Дверь_загрузочная_правая_ДК011-2", CHX, 1, 100.0)
for s in (-1, 1):   # «Кронштейн двери загрузочной камеры» КД030, 2 pcs, 32.42 kg
    box_mm("Кронштейн_двери_КД030", "door", "steel_profile", s * XR - 0.04 if s < 0 else s * XR, s * XR if s < 0 else s * XR + 0.04, YF - 0.12, YF, ZB + 0.30, ZB + 2.20, mass=32.42)
    for z in (ZB + 1.745, ZB + 0.685):   # wedge clamps for the locking rails (inner ends)
        x = s * (XR - 1.229 - 0.06)
        box_mm("Клиновой_прижим_ригеля", "case", "steel_profile", x - 0.04, x + 0.04, YF - 0.12, YF, z - 0.08, z + 0.08, cut=True)

# centre section: service door ДС010 (pos. 1) and firebox door ДТ010 (pos. 2) with «Навес» hinges
SD = dict(x0=-0.415, x1=0.415, z0=ZB + 2.50 - 0.46 - 0.72, z1=ZB + 2.50 - 0.46)
box_mm("Дверь_сервисная_ДС010_лист", "door", "steel_paint", SD["x0"], SD["x1"], YF - 0.035, YF - 0.027, SD["z0"], SD["z1"], cut=True)
box_mm("Дверь_сервисная_рамка", "door", "steel_profile", SD["x0"] + 0.02, SD["x1"] - 0.02, YF - 0.055, YF - 0.035, SD["z0"] + 0.02, SD["z0"] + 0.06, cut=True)
box_mm("Дверь_сервисная_рамка", "door", "steel_profile", SD["x0"] + 0.02, SD["x1"] - 0.02, YF - 0.055, YF - 0.035, SD["z1"] - 0.06, SD["z1"] - 0.02, cut=True)
box_mm("Дверь_сервисная_изоляция", "door", "fiber", SD["x0"] + 0.03, SD["x1"] - 0.03, YF - 0.027, YF + T8 + INS, SD["z0"] + 0.03, SD["z1"] - 0.03, cut=True)
cyl("Дверь_сервисная_глазок_D100", "door", "steel_hot", (0, YF - 0.06, SD["z0"] + 0.05 + 0.05), 0.05, 0.03, axis='Y', cut=True)
for z in (SD["z0"] + 0.12, SD["z1"] - 0.12):
    cyl("Дверь_сервисная_навес_ДО040", "door", "steel_hot", (SD["x0"] - 0.03, YF - 0.035, z), 0.02, 0.17, mass=1.63, cut=True)
    box_mm("Пластина_кронштейна_сервисной_двери_ДО050_ДО051", "door", "steel_profile", SD["x0"] - 0.075, SD["x0"] - 0.005, YF - 0.012, YF, z - 0.05, z + 0.05, mass=0.4, cut=True)
box_mm("Ответная_планка_ДТ010.008", "door", "steel_profile", SD["x1"], SD["x1"] + 0.06, YF - 0.04, YF, (SD["z0"] + SD["z1"]) / 2 - 0.05, (SD["z0"] + SD["z1"]) / 2 + 0.05, mass=0.30, cut=True)
FD = dict(x0=-0.285, x1=0.285, z0=ZB + 0.103, z1=ZB + 0.793)
box_mm("Дверь_топки_ДТ010_лист", "door", "steel_paint", FD["x0"], FD["x1"], YF - 0.035, YF - 0.027, FD["z0"], FD["z1"], cut=True)
box_mm("Дверь_топки_изоляция", "door", "fiber", FD["x0"] + 0.03, FD["x1"] - 0.03, YF - 0.027, YF + T8 + INS, FD["z0"] + 0.03, FD["z1"] - 0.03, cut=True)
for z in (FD["z0"] + 0.12, FD["z1"] - 0.12):
    cyl("Дверь_топки_навес_ДО040", "door", "steel_hot", (FD["x0"] - 0.03, YF - 0.035, z), 0.02, 0.17, mass=1.63, cut=True)
    box_mm("Пластина_кронштейна_двери_топки_ДО052", "door", "steel_profile", FD["x0"] - 0.075, FD["x0"] - 0.005, YF - 0.012, YF, z - 0.05, z + 0.05, mass=0.38, cut=True)
box_mm("Дверь_топки_засов", "door", "steel_profile", FD["x1"] - 0.06, FD["x1"] + 0.06, YF - 0.07, YF - 0.035, ZB + 0.46, ZB + 0.52, cut=True)
box_mm("Дверь_топки_поддувало", "door", "steel_profile", -0.18, 0.18, YF - 0.05, YF - 0.035, FD["z0"] + 0.04, FD["z0"] + 0.11, cut=True)
for x in (-0.12, 0.12):   # profiles ДО033 / ДО035 (channel 6.5П, L 75 / 135) — door stops
    box_mm("Профиль_ДО033_швеллер6.5П_L75", "door", "steel_profile", x - 0.0325, x + 0.0325, YF - 0.11, YF - 0.035, ZB + 0.92, ZB + 0.95, mass=0.68, cut=True)
    box_mm("Профиль_ДО035_швеллер6.5П_L135", "door", "steel_profile", x - 0.0325, x + 0.0325, YF - 0.17, YF - 0.035, Z_TOP - 0.10, Z_TOP - 0.07, mass=0.8, cut=True)

# ------------------------------------------------------------------ roof
roof = box_mm("Крыша_лист_5мм", "roof", "steel_paint", XL, XR, YF, YB, Z_TOP - T5, Z_TOP, cut=True)
bake_round_holes(roof, [((s * PP_X, PP_Y, Z_TOP), PP_RO + 0.01, 'Z') for s in (-1, 1)])
for k in range(1, 8):
    x = XL + 6.0 * k / 8
    if abs(abs(x) - PP_X) < 0.12: x += 0.15
    box_mm("Крыша_балка", "roof", "steel_profile", x - 0.03, x + 0.03, YF, YB, Z_FR - 0.06, Z_FR, cut=True)
xx = XL + 0.2
while xx < XR - 0.1:
    for y, sgn in ((YF, -1), (YB, 1)):
        box_mm("Прижим_крыши", "roof", "steel_profile", xx - 0.025, xx + 0.025, y + sgn * 0.09 - 0.03, y + sgn * 0.09 + 0.03, Z_TOP - 0.15, Z_FR, cut=(y == YF))
        cyl("Прижим_болт_М20", "roof", "steel_hot", (xx, y + sgn * 0.09, Z_FR + 0.05), 0.01, 0.12, seg=8, cut=(y == YF))
    xx += 0.4
for x in (-1.83, 1.83):
    lug("Рым_строповочный_30мм", "roof", (x, YF + 0.06, Z_FR), 0)
    lug("Рым_строповочный_30мм", "roof", (x, YB - 0.06, Z_FR), 0)
TZ = Z_FR
box_mm("Шибер_корпус", "roof", "steel_black", -0.21, 0.21, -0.31, 0.11, TZ, TZ + 0.3, mass=shell_mass(0.42, 0.42, 0.3, 0.006) + 25)
for sx in (-0.17, 0.17):
    for sy in (-0.27, 0.07):
        box_mm("Шибер_стойка", "roof", "steel_profile", sx - 0.02, sx + 0.02, sy - 0.02, sy + 0.02, TZ + 0.3, TZ + 0.62)
box_mm("Шибер_плита", "roof", "steel_black", -0.22, 0.22, -0.32, 0.12, TZ + 0.62, TZ + 0.65)
cyl("Шибер_винт_Tr30", "roof", "steel_hot", (0, -0.1, TZ + 0.6), 0.015, 0.5, seg=12)
bpy.ops.mesh.primitive_torus_add(major_radius=0.12, minor_radius=0.012, location=(0, -0.1, TZ + 0.86))
w = bpy.context.active_object; w.name = "Шибер_штурвал"
for c in w.users_collection: c.objects.unlink(w)
reg(w, "roof", "steel_black")

# ------------------------------------------------------------------ chimneys on flue boxes (6000 + 2 x 350 = 6700 passport length)
CHIM_Y = -1.20
for s in (-1, 1):
    cx = s * (XR + 0.28)
    box_mm("Газоход_короб_350", "chim", "steel_black", s * XR, s * (XR + 0.55), CHIM_Y - 0.35, CHIM_Y + 0.35, 0.0, 0.80, mass=shell_mass(0.55, 0.7, 0.8, 0.005, 5))
    tube("Труба_патрубок_D420", "chim", "steel_black", (cx, CHIM_Y, 0.88), 0.235, 0.004, 0.16)
    corrugated("Дымовая_труба_гофра_D420", "chim", "steel_black", (cx, CHIM_Y, 0.96), 0.21, 6.2, 0.012, 0.06, 0.0025)
    cyl("Дымовая_труба_оголовок", "chim", "steel_black", (cx, CHIM_Y, 7.18), 0.235, 0.05)
    cyl("Шибер_трубы_диск", "chim", "steel_hot", (cx, CHIM_Y, 3.0), 0.2, 0.006)
    beam("Шибер_трубы_рычаг", "chim", "red_valve", (cx, CHIM_Y - 0.22, 3.0), (cx, CHIM_Y - 0.55, 2.9), 0.03)
    for z in (1.4, Z_TOP - 0.2):
        box_mm("Кронштейн_трубы", "chim", "steel_profile", min(cx, s * XR), max(cx, s * XR), CHIM_Y - 0.3, CHIM_Y - 0.25, z - 0.03, z + 0.03)
    pipe("Растяжка_трубы_тросом", "chim", "steel_hot", [(cx, CHIM_Y, 6.0), (cx + s * 1.8, CHIM_Y - 1.8, 0.0)], 0.006, wall=0.006)
    pipe("Растяжка_трубы_тросом", "chim", "steel_hot", [(cx, CHIM_Y, 6.0), (cx + s * 1.8, CHIM_Y + 2.4, 0.0)], 0.006, wall=0.006)

# ------------------------------------------------------------------ O2 / combustion-air pipe along the back (3300 + 220 = 3520 passport width)
AIR_Y, AIR_Z = YB + 0.11, ZB + 0.517
BX, BY = XL - 0.85, YB - 0.25
box_mm("Вентилятор_рама", "air", "steel_profile", BX - 0.3, BX + 0.3, BY - 0.3, BY + 0.3, 0.0, 0.2)
cyl("Вентилятор_улитка", "air", "steel_galv", (BX, BY, 0.5), 0.28, 0.22, axis='Y', mass=80)
cyl("Вентилятор_двигатель_1.5кВт", "air", "motor", (BX, BY - 0.27, 0.5), 0.1, 0.28, axis='Y', mass=22)
pipe("Труба_подачи_кислорода_DN200", "air", "steel_galv", [(BX, BY + 0.11, 0.62), (BX, AIR_Y, AIR_Z), (XR - 0.2, AIR_Y, AIR_Z)], 0.1095, wall=0.0035)
pipe("Отвод_воздуха_в_топку", "air", "steel_galv", [(0, AIR_Y, AIR_Z), (0, YB - 0.02, ZB + 0.417)], 0.095, wall=0.0035)
cyl("Дроссель_топка", "air", "red_valve", (0, YB + 0.05, ZB + 0.46), 0.11, 0.05, axis='Y')
for s in (-1, 1):   # air to the pyrolysis-gas burning zone (outlet of the J-pipe)
    pipe("Отвод_воздуха_к_дожигу", "air", "steel_galv", [(s * 0.62, AIR_Y, AIR_Z), (s * 0.62, AIR_Y, ZB + 0.80), (s * 0.62, PP_Y + 0.15, ZB + 0.80)], 0.0445, wall=0.0035)
    cyl("Дроссель_дожига", "air", "red_valve", (s * 0.62, AIR_Y, ZB + 0.70), 0.065, 0.04)

# ------------------------------------------------------------------ instrumentation & control
for s in (-1, 1):
    for y in (-0.6, 0.6):
        cyl("Термопара_ТХА_стакан", "ctrl", "steel_hot", (s * CHX, y, Z_TOP), 0.012, 0.7, seg=8)
        box_mm("Термопара_головка", "ctrl", "cabinet", s * CHX - 0.04, s * CHX + 0.04, y - 0.04, y + 0.04, Z_FR + 0.30, Z_FR + 0.38, mass=0.6)
    cyl("Термопара_ТХА_зона_дожига", "ctrl", "steel_hot", (s * 0.62, 0.2, Z_TOP), 0.012, 0.7, seg=8)
pipe("Кабельный_лоток", "ctrl", "steel_galv", [(XR - 0.3, YB - 0.2, Z_FR + 0.08), (XL + 0.05, YB - 0.2, Z_FR + 0.08), (XL - 0.08, YB - 0.2, Z_FR + 0.08), (XL - 0.08, -0.15, 1.9)], 0.03, wall=0.0015)
box_mm("Шкаф_управления_АСУ", "ctrl", "cabinet", XL - 0.34, XL - 0.04, -0.45, 0.15, 1.05, 1.85, mass=48)
box_mm("Шкаф_управления_дисплей", "ctrl", "steel_black", XL - 0.345, XL - 0.34, -0.33, 0.03, 1.5, 1.75, mass=1)
LX = XL - 0.25
for y in (0.95, 1.45):
    box_mm("Лестница_тетива", "ctrl", "steel_profile", LX - 0.03, LX + 0.03, y - 0.03, y + 0.03, 0.0, Z_FR + 1.0)
for k in range(9):
    cyl("Лестница_ступень", "ctrl", "steel_hot", (LX, 1.2, 0.3 + k * 0.3), 0.012, 0.5, axis='Y', seg=8)
for k in range(5):
    pipe("Лестница_ограждение_дуга", "ctrl", "steel_hot", [(LX, 0.95, 1.4 + k * 0.3), (LX - 0.35, 0.95, 1.4 + k * 0.3), (LX - 0.35, 1.45, 1.4 + k * 0.3), (LX, 1.45, 1.4 + k * 0.3)], 0.01)

# ------------------------------------------------------------------ external loading platform + winch (right shell), rails at the shell rail level
PY0, PY1 = YF - 0.14, YF - 3.6
for dx in (-0.45, 0.45):
    box_mm("Площадка_рельс_40х40", "track", "steel_hot", CHX + dx - 0.02, CHX + dx + 0.02, PY1, PY0, RAIL_IN - 0.05, RAIL_IN)
    box_mm("Площадка_балка_двутавр", "track", "steel_profile", CHX + dx - 0.06, CHX + dx + 0.06, PY1, PY0, RAIL_IN - 0.25, RAIL_IN - 0.05)
for k in range(5):
    y = PY0 - 0.2 - k * (abs(PY1 - PY0) - 0.4) / 4
    box_mm("Площадка_поперечина", "track", "steel_profile", CHX - 0.7, CHX + 0.7, y - 0.04, y + 0.04, RAIL_IN - 0.35, RAIL_IN - 0.25)
    for dx in (-0.6, 0.6):
        box_mm("Площадка_опора", "track", "steel_profile", CHX + dx - 0.05, CHX + dx + 0.05, y - 0.05, y + 0.05, -0.2, RAIL_IN - 0.35)
WY = PY1 - 0.35
box_mm("Лебёдка_стойка", "track", "steel_profile", CHX - 0.35, CHX + 0.35, WY - 0.2, WY + 0.2, -0.2, 0.55)
cyl("Лебёдка_барабан", "track", "steel_hot", (CHX, WY, 0.7), 0.12, 0.45, axis='X')
cyl("Лебёдка_мотор-редуктор", "track", "motor", (CHX + 0.4, WY, 0.7), 0.12, 0.3, axis='X', mass=60)
RET_AXIS_OUT = retort("retR", CHX, PY1 + 0.15, RAIL_IN)
pipe("Лебёдка_трос_D10", "track", "steel_hot", [(CHX, WY + 0.12, 0.7), (CHX, PY1 + 0.10, RET_AXIS_OUT - 0.55)], 0.005, wall=0.005)

# ------------------------------------------------------------------ dryer (сушильная камера) on kiln waste heat
DX0, DX1, DY0, DY1, DH = 4.75, 7.05, -1.0, 1.2, 2.5
box_mm("Сушилка_фундамент", "found", "concrete", DX0 - 0.15, DX1 + 0.15, DY0 - 0.15, DY1 + 0.15, -0.2, 0.0)
# double wall: outer 3 mm + 50 mm blanket + inner 4 mm (front = double doors)
TOPZ = 0.1 + DH
IX0, IX1, IY1 = DX0 + 0.057, DX1 - 0.057, DY1 - 0.057
box_mm("Сушилка_пол_4мм", "dry", "steel_hot", DX0, DX1, DY0, DY1, 0.1, 0.104)
for nm, (ox0, ox1, oy0, oy1) in (("зад", (DX0, DX1, DY1 - 0.003, DY1)), ("лев", (DX0, DX0 + 0.003, DY0, DY1)), ("прав", (DX1 - 0.003, DX1, DY0, DY1))):
    box_mm(f"Сушилка_наружная_3мм_{nm}", "dry", "steel_paint", ox0, ox1, oy0, oy1, 0.1, TOPZ)
box_mm("Сушилка_крыша_3мм", "dry", "steel_paint", DX0, DX1, DY0, DY1, TOPZ - 0.003, TOPZ)
box_mm("Сушилка_изоляция_50мм_зад", "dry", "fiber", DX0 + 0.003, DX1 - 0.003, IY1 + 0.004, DY1 - 0.003, 0.104, TOPZ - 0.057)
box_mm("Сушилка_изоляция_50мм_лев", "dry", "fiber", DX0 + 0.003, IX0 - 0.004, DY0 + 0.06, IY1 + 0.004, 0.104, TOPZ - 0.057)
box_mm("Сушилка_изоляция_50мм_прав", "dry", "fiber", IX1 + 0.004, DX1 - 0.003, DY0 + 0.06, IY1 + 0.004, 0.104, TOPZ - 0.057)
box_mm("Сушилка_изоляция_50мм_крыша", "dry", "fiber", DX0 + 0.003, DX1 - 0.003, DY0 + 0.06, DY1 - 0.003, TOPZ - 0.053, TOPZ - 0.003)
box_mm("Сушилка_внутр_стакан_4мм_зад", "dry", "steel_hot", IX0 - 0.004, IX1 + 0.004, IY1, IY1 + 0.004, 0.104, TOPZ - 0.057)
box_mm("Сушилка_внутр_стакан_4мм_лев", "dry", "steel_hot", IX0 - 0.004, IX0, DY0 + 0.06, IY1, 0.104, TOPZ - 0.057)
box_mm("Сушилка_внутр_стакан_4мм_прав", "dry", "steel_hot", IX1, IX1 + 0.004, DY0 + 0.06, IY1, 0.104, TOPZ - 0.057)
box_mm("Сушилка_внутр_стакан_4мм_потолок", "dry", "steel_hot", IX0 - 0.004, IX1 + 0.004, DY0 + 0.06, IY1 + 0.004, TOPZ - 0.057, TOPZ - 0.053)
for s in (-1, 1):
    xc = (DX0 + DX1) / 2 + s * 0.575
    box_mm("Сушилка_дверь_створка", "dry", "steel_paint", xc - 0.565, xc + 0.565, DY0 - 0.06, DY0, 0.2, 0.1 + DH - 0.1, mass=1.13 * 2.4 * 0.003 * 7850 + 12)
    box_mm("Сушилка_дверь_изоляция", "dry", "fiber", xc - 0.53, xc + 0.53, DY0, DY0 + 0.05, 0.25, 0.1 + DH - 0.15)
    for z in (0.5, 1.35, 2.2):
        box_mm("Сушилка_дверь_ребро", "dry", "steel_profile", xc - 0.53, xc + 0.53, DY0 - 0.09, DY0 - 0.06, z - 0.025, z + 0.025)
box_mm("Сушилка_запорная_балка", "dry", "steel_profile", (DX0 + DX1) / 2 - 0.3, (DX0 + DX1) / 2 + 0.3, DY0 - 0.13, DY0 - 0.09, 1.4, 1.48)
for x in (DX0, DX1):
    for y in (DY0, DY1):
        box_mm("Сушилка_стойка", "dry", "steel_profile", x - 0.05, x + 0.05, y - 0.05, y + 0.05, 0.0, 0.1 + DH)
cyl("Сушилка_труба_сброса_D340", "dry", "steel_black", (DX1 - 0.45, 0.45, 0.1 + DH + 0.9), 0.17, 1.8, mass=math.pi * 0.34 * 0.003 * 1.8 * 7850)
cyl("Сушилка_клапан_сброса_автомат", "dry", "orange", (DX1 - 0.45, 0.45, 0.1 + DH + 0.3), 0.2, 0.12, mass=28)
cyl("Сушилка_вытяжка_влаги", "dry", "steel_galv", (DX0 + 0.6, 0.2, 0.1 + DH + 0.3), 0.12, 0.6, mass=8)
box_mm("Сушилка_шкаф_автоматики", "dry", "cabinet", DX1, DX1 + 0.18, -0.7, -0.2, 1.1, 1.75, mass=25)
cyl("Сушилка_датчик_T_RH", "dry", "steel_galv", (DX1 + 0.05, 0.4, 2.0), 0.03, 0.12, axis='X', mass=0.5)
# hot-gas duct from right chimney flue box to dryer (insulated D400, motorised damper)
duct = [(XR + 0.55, CHIM_Y, 0.40), (4.35, CHIM_Y, 0.40), (4.35, -0.2, 0.40), (DX0, -0.2, 0.40)]
pipe("Газоход_на_сушилку_D400", "dry", "steel_black", duct, 0.2, wall=0.003)
pipe("Газоход_на_сушилку_изоляция", "dry", "steel_galv", duct[1:], 0.28, wall=0.0007)
cyl("Заслонка_с_электроприводом", "dry", "orange", (4.35, -0.75, 0.40), 0.3, 0.1, axis='Y', mass=38)
box_mm("Электропривод_заслонки", "dry", "motor", 4.25, 4.45, -0.85, -0.65, 0.62, 0.8, mass=9)

# ------------------------------------------------------------------ retort cooling cabinets (2)
for i, cx in enumerate((5.0, 7.4)):
    x0, x1, y0, y1 = cx - 1.05, cx + 1.05, -5.4, -2.2
    box_mm("Шкаф_остывания_фундамент", "found", "concrete", x0 - 0.1, x1 + 0.1, y0 - 0.1, y1 + 0.1, -0.2, 0.0)
    for (a, b, c, d) in ((x0, x0 + 0.004, y0, y1), (x1 - 0.004, x1, y0, y1), (x0, x1, y1 - 0.004, y1)):
        box_mm("Шкаф_остывания_стенка_4мм", "cool", "steel_paint", a, b, c, d, 0.0, 2.15)
    box_mm("Шкаф_остывания_крыша_4мм", "cool", "steel_paint", x0, x1, y0, y1, 2.15, 2.154)
    box_mm("Шкаф_остывания_дверь", "cool", "steel_paint", x0 + 0.05, x1 - 0.05, y0 - 0.06, y0, 0.05, 2.1, mass=2.0 * 2.05 * 0.004 * 7850 + 30)
    box_mm("Шкаф_остывания_уплотнение_песок", "cool", "rubber", x0 + 0.05, x1 - 0.05, y0, y0 + 0.02, 0.05, 0.09)
    for dx in (-0.6, 0.6):
        box_mm("Шкаф_остывания_рельс", "cool", "steel_hot", cx + dx - 0.025, cx + dx + 0.025, y0, y1, 0.0, 0.05)
    for z in (0.6, 1.5):
        box_mm("Шкаф_остывания_запор", "cool", "steel_profile", x0 + 0.1, x1 - 0.1, y0 - 0.1, y0 - 0.06, z - 0.03, z + 0.03)
    for x in (x0, x1):
        for y in (y0, y1):
            box_mm("Шкаф_остывания_стойка", "cool", "steel_profile", x - 0.04, x + 0.04, y - 0.04, y + 0.04, 0.0, 2.2)

# ------------------------------------------------------------------ hydraulic log splitter ДГ 360 (15 kW, 380 V)
SX, SY = 8.9, 0.1
box_mm("Дровокол_площадка", "found", "concrete", SX - 0.7, SX + 1.0, SY - 1.6, SY + 1.6, -0.2, 0.0)
box_mm("Дровокол_балка_двутавр", "split", "steel_profile", SX - 0.12, SX + 0.12, SY - 1.3, SY + 1.3, 0.7, 0.95, mass=260)
for y in (SY - 1.1, SY + 1.1):
    for x in (SX - 0.35, SX + 0.35):
        beam("Дровокол_опора", "split", "steel_profile", (x, y, 0.0), (SX, y, 0.7), 0.06, mass=12)
cyl("Дровокол_гидроцилиндр", "split", "steel_paint", (SX, SY + 0.55, 1.12), 0.1, 1.4, axis='Y', mass=180)
box_mm("Дровокол_толкатель", "split", "steel_hot", SX - 0.15, SX + 0.15, SY - 0.2, SY - 0.1, 0.95, 1.3, mass=45)
box_mm("Дровокол_нож_крестовой", "split", "orange", SX - 0.02, SX + 0.02, SY - 1.25, SY - 1.0, 0.95, 1.45, mass=60)
box_mm("Дровокол_нож_гор", "split", "orange", SX - 0.25, SX + 0.25, SY - 1.25, SY - 1.0, 1.18, 1.22, mass=20)
box_mm("Дровокол_маслобак", "split", "steel_paint", SX + 0.25, SX + 0.75, SY + 0.6, SY + 1.3, 0.0, 0.55, mass=140)
cyl("Дровокол_двигатель_15кВт", "split", "motor", (SX + 0.5, SY + 0.95, 0.75), 0.17, 0.5, axis='Y', mass=110)
box_mm("Дровокол_пульт", "split", "orange", SX - 0.45, SX - 0.3, SY + 0.2, SY + 0.4, 1.0, 1.3, mass=6)

# ------------------------------------------------------------------ curves -> meshes
dg = bpy.context.evaluated_depsgraph_get()
for ob in [o for o in OBJS if o.type == 'CURVE']:
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    new = bpy.data.objects.new(ob.name, me)
    for k in ob.keys():
        new[k] = ob[k]
    for c in ob.users_collection:
        c.objects.link(new)
    new.matrix_world = ob.matrix_world
    OBJS[OBJS.index(ob)] = new
    bpy.data.objects.remove(ob)

# ------------------------------------------------------------------ physics: volume -> mass, centre of mass
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
def mesh_volume_and_centroid(ob):
    bm = bmesh.new()
    bm.from_object(ob, dg)
    bm.transform(ob.matrix_world)
    vol = abs(bm.calc_volume(signed=False))
    # centroid of the solid via tetrahedra from origin
    cx = cy = cz = 0.0; vs = 0.0
    bmesh.ops.triangulate(bm, faces=bm.faces)
    for f in bm.faces:
        a, b, c = (v.co for v in f.verts)
        v6 = a.dot(b.cross(c)) / 6.0
        vs += v6; cx += v6 * (a.x + b.x + c.x) / 4; cy += v6 * (a.y + b.y + c.y) / 4; cz += v6 * (a.z + b.z + c.z) / 4
    bm.free()
    cen = Vector((cx / vs, cy / vs, cz / vs)) if abs(vs) > 1e-9 else ob.matrix_world.translation.copy()
    return vol, cen

assemblies = {}
for ob in OBJS:
    if ob.type != 'MESH':
        continue
    vol, cen = mesh_volume_and_centroid(ob)
    mass = ob.get("mass_override_kg", vol * ob["density_kg_m3"])
    ob["volume_m3"] = round(vol, 5)
    ob["mass_kg"] = round(mass, 2)
    a = assemblies.setdefault(ob["_ckey"], {"mass": 0.0, "mom": Vector((0, 0, 0)), "n": 0, "by_mat": {}})
    a["mass"] += mass; a["mom"] += cen * mass; a["n"] += 1
    a["by_mat"][ob["material"]] = a["by_mat"].get(ob["material"], 0) + mass

kiln_keys = [k for k, (_, inpass) in ASSEMBLY.items() if inpass]
kiln_mass = sum(assemblies[k]["mass"] for k in kiln_keys if k in assemblies)
kiln_com = sum((assemblies[k]["mom"] for k in kiln_keys if k in assemblies), Vector()) / kiln_mass
retort_mass = assemblies["retL"]["mass"]
# exclude the charge (mass 0) — retort steel only
res = {
    "assemblies": {ASSEMBLY[k][0]: {"mass_kg": round(v["mass"], 1), "com_m": [round(c, 3) for c in (v["mom"] / v["mass"] if v["mass"] else Vector())], "parts": v["n"], "in_passport_mass": ASSEMBLY[k][1], "by_material_kg": {m: round(x, 1) for m, x in v["by_mat"].items()}} for k, v in assemblies.items()},
    "kiln_mass_kg": round(kiln_mass, 1),
    "kiln_com_m": [round(c, 3) for c in kiln_com],
    "retort_mass_kg": round(retort_mass, 1),
    "geometry": {"casing_LxWxH_m": [XR - XL, YB - YF, Z_TOP - ZB], "overall_height_m": round(Z_FR, 3),
                 "length_with_flue_boxes_m": round((XR + 0.55) - (XL - 0.55), 2), "width_with_O2_pipe_m": round((AIR_Y + 0.1095) - YF, 3),
                 "shell": {"D_out_mm": round(2 * SK_RO * 1000), "D_in_mm": round(2 * SK_RI * 1000), "t_mm": round(SK_T * 1000), "L_mm": round(SK_L * 1000), "axis_z_m": round(SK_ZC, 3), "x_m": CHX},
                 "retort": {"D_out_mm": round(2 * RT_RO * 1000), "t_mm": round(RT_T * 1000), "L_mm": round(RT_L * 1000)},
                 "retort_inner_volume_m3": round(math.pi * (RT_RO - RT_T) ** 2 * (RT_L - 2 * RT_T), 3),
                 "shell_volume_m3": round(math.pi * SK_RI ** 2 * SK_L, 3),
                 "clearance_radial_mm": round((SK_RI - RT_RO) * 1000), "clearance_top_mm": round(((SK_ZC + SK_RI) - (RET_AXIS_IN + RT_RO)) * 1000),
                 "clearance_bottom_mm": round(((RET_AXIS_IN - RT_RO) - (SK_ZC - SK_RI)) * 1000),
                 "clearance_length_mm": round((SK_L - RT_L) * 1000), "gap_shell_to_end_insulation_mm": round(((XR - T5 - INS) - (CHX + SK_RO)) * 1000),
                 "gap_shell_to_partition_mm": round(((CHX - SK_RO) - PX) * 1000),
                 "pyro_pipe": {"OD_mm": 159, "t_mm": 6, "x_m": PP_X, "from_back_mm": 548, "top_m": PP_ZTOP, "stub_z_m": PP_ZSTUB, "outlet_z_m": round(PP_ZBOT - 0.1, 3)},
                 "chimney_top_m": 7.23, "chimney_d_m": 0.42, "lugs": 4,
                 "casing_outer_area_m2": round(2 * ((XR - XL) * (Z_TOP - ZB)) + 2 * ((YB - YF) * (Z_TOP - ZB)) + (XR - XL) * (YB - YF), 2)},
}

# ------------------------------------------------------------------ rigid body physics (real masses) + settle test
def proxy_for(keys, name, passive=False, bounds=None):
    obs = [o for o in OBJS if o.type == 'MESH' and o["_ckey"] in keys]
    mn = Vector((min(min((o.matrix_world @ Vector(c)).x for c in o.bound_box) for o in obs),
                 min(min((o.matrix_world @ Vector(c)).y for c in o.bound_box) for o in obs),
                 min(min((o.matrix_world @ Vector(c)).z for c in o.bound_box) for o in obs)))
    mx = Vector((max(max((o.matrix_world @ Vector(c)).x for c in o.bound_box) for o in obs),
                 max(max((o.matrix_world @ Vector(c)).y for c in o.bound_box) for o in obs),
                 max(max((o.matrix_world @ Vector(c)).z for c in o.bound_box) for o in obs)))
    if bounds:  # explicit contact box (casing body only / rail level for the platform)
        mn, mx = Vector(bounds[0]), Vector(bounds[1])
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0); bmesh.ops.scale(bm, vec=mx - mn, verts=bm.verts)
    px = mesh_ob(name, bm); px.location = (mn + mx) / 2
    scene.collection.objects.link(px)
    bpy.context.view_layer.update()
    px.display_type = 'WIRE'; px.hide_render = True
    mass = sum(assemblies[k]["mass"] for k in keys if k in assemblies)
    with bpy.context.temp_override(object=px, active_object=px, selected_objects=[px], selected_editable_objects=[px]):
        bpy.ops.rigidbody.object_add()
    rb = px.rigid_body
    rb.type = 'PASSIVE' if passive else 'ACTIVE'
    rb.collision_shape = 'BOX'; rb.friction = 0.6; rb.restitution = 0.0
    rb.mass = max(mass, 1.0)
    rb.collision_margin = 0.0
    px["mass_kg"] = round(mass, 1)
    for o in obs:
        if o.parent is None:
            mw = o.matrix_world.copy(); o.parent = px; o.matrix_world = mw
    for o in [o for o in bpy.data.objects if o.type == 'EMPTY' and o.get("assembly") in [ASSEMBLY[k][0] for k in keys] and o.parent is None]:
        mw = o.matrix_world.copy(); o.parent = px; o.matrix_world = mw
    return px

physics = {}
try:
    with bpy.context.temp_override(scene=scene):
        bpy.ops.rigidbody.world_add()
    rbw = scene.rigidbody_world
    rbw.point_cache.frame_start = 1; rbw.point_cache.frame_end = 120
    rbw.substeps_per_frame = 20; rbw.solver_iterations = 20
    bpy.ops.object.select_all(action='DESELECT')
    # ground
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0); bmesh.ops.scale(bm, vec=(40, 40, 1), verts=bm.verts)
    g = mesh_ob("Грунт", bm); g.location = (2, -1, -0.7); scene.collection.objects.link(g); g.data.materials.append(MAT["ground"])
    with bpy.context.temp_override(object=g, active_object=g, selected_objects=[g], selected_editable_objects=[g]):
        bpy.ops.rigidbody.object_add()
    g.rigid_body.type = 'PASSIVE'; g.rigid_body.collision_shape = 'BOX'; g.rigid_body.collision_margin = 0.0
    proxies = {
        "RB_Фундамент": proxy_for(["found"], "RB_Фундамент", passive=True),
        "RB_Печь": proxy_for(kiln_keys + ["retL"], "RB_Печь", bounds=((XL, YF, 0.0), (XR, YB, Z_FR))),
        "RB_Площадка": proxy_for(["track"], "RB_Площадка", passive=True, bounds=((CHX - 0.75, PY1 - 0.6, -0.2), (CHX + 0.75, PY0, RAIL_IN))),
        "RB_Реторта_2": proxy_for(["retR"], "RB_Реторта_2", bounds=((CHX - RT_RO - 0.05, PY1 + 0.0, RAIL_IN), (CHX + RT_RO + 0.05, PY1 + 0.15 + RT_L + 0.15, RET_AXIS_OUT + RT_RO + 0.1))),
        "RB_Сушилка": proxy_for(["dry"], "RB_Сушилка"),
        "RB_Шкафы": proxy_for(["cool"], "RB_Шкафы"),
        "RB_Дровокол": proxy_for(["split"], "RB_Дровокол"),
    }
    # foundation proxy covers several slabs: replace by the kiln slab only to avoid overlaps
    start = {n: p.matrix_world.translation.copy() for n, p in proxies.items()}
    for f in range(1, 121):
        scene.frame_set(f)
    end = {n: p.matrix_world.translation.copy() for n, p in proxies.items()}
    for n in proxies:
        d = (end[n] - start[n]).length
        physics[n] = {"mass_kg": proxies[n]["mass_kg"], "displacement_mm_after_4s": round(d * 1000, 2), "type": proxies[n].rigid_body.type}
    scene.frame_set(1)
except Exception as e:  # physics is optional — never break the build
    physics["error"] = repr(e)
res["rigid_body_test"] = physics

# ------------------------------------------------------------------ engineering calculations (written to report)
g0 = 9.81
calc = {}
M = kiln_mass
Mr = retort_mass
V_ret = res["geometry"]["retort_inner_volume_m3"]
k_stack = 0.70                                  # coefficient of stacking (поленница)
V_solid = V_ret * k_stack                       # m3 solid wood per retort
species = {"Берёза": (500, 150), "Сосна": (400, 120), "Лиственница": (520, 160)}  # basic density kg/m3, yield kg/m3 (manufacturer)
W_in = 0.25                                     # moisture, wet basis, at loading (after drying)
calc["charge"] = {}
for sp, (rho_b, y_kg) in species.items():
    dry = V_solid * rho_b
    wet = dry / (1 - W_in)
    char = V_solid * y_kg
    calc["charge"][sp] = {"solid_m3": round(V_solid, 2), "dry_t": round(dry / 1000, 2), "wet_t": round(wet / 1000, 2),
                          "char_per_retort_kg": round(char), "char_per_cycle_t": round(2 * char / 1000, 2),
                          "mass_yield_dry_pct": round(100 * char / dry, 1),
                          "cycles_for_25t": round(25000 / (2 * char), 1), "cycles_for_41t": round(41000 / (2 * char), 1),
                          "hours_per_cycle_25t": round(720 / (25000 / (2 * char)), 1), "hours_per_cycle_41t": round(720 / (41000 / (2 * char)), 1)}
# heat balance per cycle (2 retorts, birch)
b = calc["charge"]["Берёза"]
dry_kg = b["dry_t"] * 1000 * 2; water = dry_kg * W_in / (1 - W_in)
Q_evap = water * (4.19 * (100 - 15) + 2257) / 1e6                # GJ
Q_wood = dry_kg * 1.5 * (450 - 15) / 1e6                          # GJ (cp dry wood/char ~1.5 kJ/kgK)
Q_ret = 2 * Mr * 0.48 * (450 - 15) / 1e6                          # GJ, retort steel
char_kg = b["char_per_cycle_t"] * 1000
volatiles = dry_kg - char_kg
LHV_vol = 12.0                                                    # MJ/kg, pyrolysis vapours+gas (lit. 10-16)
Q_gas = volatiles * LHV_vol / 1000                                # GJ
# wall losses
A = res["geometry"]["casing_outer_area_m2"]
def lam_fiber(Tm):  # W/mK, 128 kg/m3 needled blanket (manufacturer tables, approx.)
    return 0.035 + 0.000135 * Tm + 1.1e-7 * Tm * Tm
Ti, Ta, h_out = 450.0, 20.0, 10.0
Ts = 40.0
for _ in range(30):
    lam = lam_fiber((Ti + Ts) / 2)
    q = (Ti - Ta) / (INS / lam + 1 / h_out)
    Ts = Ta + q / h_out
Q_loss_kW = q * A / 1000
cycle_h = 24.0
Q_loss = Q_loss_kW * cycle_h * 3600 / 1e6 * 0.75                   # GJ, average 75 % of peak over the cycle
Q_need = Q_evap + Q_wood + Q_ret + Q_loss
calc["heat_balance_GJ_per_cycle_birch"] = {"water_evaporated_t": round(water / 1000, 2), "Q_evaporation": round(Q_evap, 2), "Q_heat_wood_to_450C": round(Q_wood, 2),
    "Q_heat_retort_steel": round(Q_ret, 2), "Q_wall_losses_24h": round(Q_loss, 2), "Q_required_total": round(Q_need, 2),
    "volatiles_t": round(volatiles / 1000, 2), "Q_pyrolysis_gas_available": round(Q_gas, 1), "autothermal_ratio": round(Q_gas / Q_need, 1),
    "startup_firewood_t_estimate": round((Q_evap * 0.35 + Q_wood * 0.25) / (15e-3 * 0.55) / 1000, 2)}
calc["wall_heat_loss"] = {"T_inside_C": Ti, "lambda_mean_W_mK": round(lam, 3), "q_W_m2": round(q, 1), "T_surface_C": round(Ts, 1), "area_m2": A, "Q_peak_kW": round(Q_loss_kW, 1)}
# chimney draft
H_ch = 7.23 - 0.8
rho_air = 1.293 * 273 / (273 + 20)
calc["chimney_draft"] = {}
for Tg in (200, 300, 400):
    rho_g = 1.30 * 273 / (273 + Tg)
    calc["chimney_draft"][f"{Tg}C"] = round(g0 * H_ch * (rho_air - rho_g), 1)
# pyrolysis gas pipe velocity & combustion air
t_active_h = 10.0
m_dot = volatiles / (t_active_h * 3600)                           # kg/s both retorts, average
rho_pg = 0.95 * 273 / (273 + 400)
D_pp = 0.159 - 2 * 0.006
A_pp = math.pi * D_pp ** 2 / 4
v_pg = m_dot / 2 / rho_pg / A_pp
L_pp = (PP_ZSTUB - PP_ZBOT) + abs(CHX - math.sqrt(SK_RI ** 2 - (PP_ZSTUB - SK_ZC) ** 2) - PP_X) + 0.35
zeta = 0.5 + 1.1 + 1.0 + 0.6        # entry from the shell + tee + exit + J-bend
def dp(v): return (0.03 * L_pp / D_pp + zeta) * rho_pg * v * v / 2
air_ratio = 3.6 * 1.3                                            # kg air per kg volatiles (stoich ~3.6) x excess 1.3
air = m_dot * air_ratio
Q_air = air / 1.2
A_air = math.pi * 0.1025 ** 2
calc["gas_and_air"] = {"pyrolysis_gas_kg_s_avg": round(m_dot, 3), "pipe": "Ø159×6 (ТП200, чертёж)", "gas_velocity_m_s": round(v_pg, 1), "peak_factor_assumed": 2.0,
    "gas_velocity_peak_m_s": round(v_pg * 2, 1), "gas_path_length_m": round(L_pp, 2), "dp_avg_Pa": round(dp(v_pg)), "dp_peak_Pa": round(dp(2 * v_pg)),
    "air_kg_s": round(air, 3), "air_m3_h": round(Q_air * 3600), "air_velocity_DN200_m_s": round(Q_air / A_air, 1),
    "blower_power_kW_at_1kPa": round(Q_air * 1000 / 0.6 / 1000 * 2, 2)}
# thermal expansion
alpha = 12e-6
calc["thermal_expansion_mm"] = {"shell_length_2.9m_dT600": round(alpha * 600 * SK_L * 1000, 1), "shell_diameter_dT600": round(alpha * 600 * 2 * SK_RO * 1000, 1),
    "retort_length_dT435": round(alpha * 435 * RT_L * 1000, 1), "retort_diameter_dT435": round(alpha * 435 * 2 * RT_RO * 1000, 1),
    "pyro_pipe_vertical_2.5m_dT400": round(alpha * 400 * (PP_ZTOP - PP_ZBOT) * 1000, 1)}
# lifting
F_lug = M * g0 / (4 * math.sin(math.radians(60)))
t_l, R_l, r_h = 0.030, 0.13, 0.045
A_net = 2 * (R_l - r_h) * t_l
sigma = F_lug / A_net / 1e6
calc["lifting"] = {"mass_t": round(M / 1000, 2), "sling_angle_deg": 60, "F_per_lug_kN": round(F_lug / 1000, 1), "net_section_mm2": round(A_net * 1e6),
    "stress_MPa": round(sigma, 1), "yield_09G2S_MPa": 325, "safety_factor": round(325 / sigma, 1)}
# retort handling
wet_birch = b["wet_t"] * 1000
m_loaded = Mr + wet_birch
calc["retort_handling"] = {"retort_steel_kg": round(Mr), "charge_wet_birch_kg": round(wet_birch), "loaded_kg": round(m_loaded),
    "wheel_load_kN": round(m_loaded * g0 / 4 / 1000, 1), "rolling_coeff": 0.015, "push_force_kN": round(m_loaded * g0 * 0.015 / 1000, 2),
    "after_cycle_kg": round(Mr + b["char_per_retort_kg"])}
# foundation & stability
loaded = M + 2 * m_loaded
area = (XR - XL) * (YB - YF)
com = kiln_com
calc["foundation"] = {"operating_mass_t": round(loaded / 1000, 1), "contact_area_m2": round(area, 1), "pressure_kPa": round(loaded * g0 / area / 1000, 1),
    "com_height_m": round(com.z, 2), "tip_angle_deg": round(math.degrees(math.atan(min(com.y - YF, YB - com.y) / com.z)), 1)}
# dryer
V_d = 5.5 * k_stack; dry_d = V_d * 500
w0, w1 = 0.40, 0.25
water_d = dry_d * (w0 / (1 - w0) - w1 / (1 - w1))
Q_d = water_d * 2.6 / 0.5 / 1000                                 # GJ incl. heating, efficiency 0.5
flue_kg_s = m_dot + air
Q_avail_kW = flue_kg_s * 1.1 * (300 - 120)
calc["dryer"] = {"solid_m3": round(V_d, 2), "dry_mass_t": round(dry_d / 1000, 2), "moisture_from_to_pct": [40, 25], "water_removed_t": round(water_d / 1000, 2),
    "Q_GJ": round(Q_d, 2), "Q_avg_kW_over_24h": round(Q_d * 1e6 / 86400, 1), "flue_heat_available_kW": round(Q_avail_kW, 1)}
steel_labels = ("Сталь", "Прокат", "Чугун", "Сигнальная", "Запорная")
st4 = 0.0
for k in ("frame", "case", "door", "cup", "gas"):
    for m_, x_ in assemblies.get(k, {"by_mat": {}})["by_mat"].items():
        if m_.startswith(steel_labels): st4 += x_
calc["drawing_stage4"] = {"model_steel_structure_kg": round(st4), "drawing_mass_kg": 7910.29,
    "note": "Каркас + обшивка + двери + стаканы + пиролизные трубы, без изоляции, кирпича, крыши и навесного оборудования"}
res["calc"] = calc

with open(os.path.join(OUT, "calc_results.json"), "w", encoding="utf-8") as f:
    json.dump(res, f, ensure_ascii=False, indent=2)
print("KILN_MASS", round(kiln_mass), "RETORT", round(retort_mass), "COM", [round(c, 3) for c in kiln_com])
print("PHYS", json.dumps(physics, ensure_ascii=False))

# ------------------------------------------------------------------ scene, save, export
world = bpy.data.worlds.new("World"); scene.world = world; world.use_nodes = True
bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
bg.inputs[0].default_value = (0.60, 0.70, 0.84, 1); bg.inputs[1].default_value = 1.0
sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", 'SUN'))
sun.data.energy = 4.0; sun.rotation_euler = (math.radians(52), math.radians(12), math.radians(-35))
scene.collection.objects.link(sun)
cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera")); scene.collection.objects.link(cam); scene.camera = cam
def aim(loc, target, lens=35):
    cam.data.lens = lens; cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
aim((-9.5, -14.0, 7.5), (2.2, -1.0, 1.4), 30)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "PROMETHEY_kiln_v4.blend"), compress=True)

export_objs = [o for o in bpy.data.objects if o.type in ('MESH', 'EMPTY') and not o.name.startswith("RB_") and o.name not in ("Грунт",)]
bpy.ops.object.select_all(action='DESELECT')
for o in export_objs: o.select_set(True)
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "PROMETHEY_kiln_v4.glb"), export_format='GLB', use_selection=True, export_apply=True, export_extras=True,
                          export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=6)
bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, "PROMETHEY_kiln_v4.fbx"), use_selection=True, path_mode='COPY')

# ------------------------------------------------------------------ renders
for o in bpy.data.objects:
    if o.name.startswith("RB_"): o.hide_render = True
r = scene.render; r.resolution_x, r.resolution_y = 1600, 1000
try: r.engine = 'BLENDER_EEVEE_NEXT'
except TypeError: r.engine = 'BLENDER_EEVEE'
vt = [i.identifier for i in bpy.types.ColorManagedViewSettings.bl_rna.properties['view_transform'].enum_items]
scene.view_settings.view_transform = 'AgX' if 'AgX' in vt else 'Filmic'
def shot(fname): r.filepath = os.path.join(OUT, fname); bpy.ops.render.render(write_still=True)
shot("render_01_площадка.png")
aim((0.0, -15.5, 2.6), (0.0, 0, 2.4), 32); shot("render_02_фасад.png")
aim((-7.0, 9.5, 5.5), (-0.5, 0.8, 1.2), 32); shot("render_03_тыл_газ_воздух.png")
cut = [o for o in bpy.data.objects if o.get("cutaway_hide")]
for o in cut: o.hide_render = True
aim((-3.2, -9.5, 7.0), (-0.6, 0.2, 1.2), 30); shot("render_04_разрез.png")
for o in cut: o.hide_render = False
print("DONE", len(OBJS))

