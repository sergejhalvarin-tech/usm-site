"""PROMETHEY retort charcoal kiln — engineering model v3.

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
    "brick": "04_Под_и_кладка", "door": "05_Двери", "cup": "06_Топка_и_стаканы", "retL": "07_Реторта_левая",
    "retR": "08_Реторта_правая_выкачена", "gas": "09_Газоходы_пиролиз", "air": "10_Воздух_горения",
    "chim": "11_Дымовые_трубы", "roof": "12_Крыша", "ctrl": "13_КИП_и_управление", "track": "14_Выкатная_площадка",
    "dry": "15_Сушильная_камера", "cool": "16_Шкафы_остывания", "split": "17_Дровокол_ДГ360",
}.items()}

ASSEMBLY = {  # collection key -> report assembly name, part of passport mass?
    "found": ("Фундаментная плита", False), "frame": ("Рама и каркас", True), "case": ("Корпус (обшивка, внутренний лист)", True),
    "ins": ("Теплоизоляция", True), "brick": ("Под и огнеупорная кладка", True), "door": ("Двери загрузочные", True),
    "cup": ("Топка и стаканы камер сгорания", True), "retL": ("Реторта №1 (в камере)", False), "retR": ("Реторта №2 (на площадке)", False),
    "gas": ("Газоходы пиролизного газа", True), "air": ("Система воздуха горения", True), "chim": ("Дымовые трубы и газоходы", True),
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

# ------------------------------------------------------------------ main dimensions (m)
# X = length 6700, Y = depth (front -Y), Z = up; Z=0 top of concrete slab
XL, XR = -3.35, 3.35
YF, YB = -1.65, 1.58            # casing front face (front wall steel) / back face
CH_W, CH_D, CH_H = 1.9, 2.9, 1.9
CHX = 1.87                      # chamber centre |x| (from front photo: doors 2.5 m, centre section ~1.1 m)
CY0, CY1 = -1.48, 1.42          # chamber Y span (2.9 m)
Z_FRAME = 0.16                  # base channel frame height
FLOOR = 0.335                   # chamber floor (steel 10 + plate 100 + brick 65)
CEIL = FLOOR + CH_H             # 2.235
Z_TOP = 2.40                    # casing top (roof steel)
T5, T8, T12 = 0.005, 0.008, 0.012
INS = 0.15

# ------------------------------------------------------------------ foundation
box_mm("Фундаментная_плита", "found", "concrete", XL - 1.0, XR + 0.75, YF - 0.35, YB + 0.7, -0.20, 0.0)

# ------------------------------------------------------------------ base frame (channel 160)
for y in (YF + 0.08, -0.55, 0.55, YB - 0.08):
    box_mm("Рама_продольная_швеллер160", "frame", "steel_profile", XL, XR, y - 0.035, y + 0.035, 0, Z_FRAME)
for x in (XL + 0.08, -2.4, -1.2, 0.0, 1.2, 2.4, XR - 0.08):
    box_mm("Рама_поперечная_швеллер160", "frame", "steel_profile", x - 0.035, x + 0.035, YF, YB, 0.02, Z_FRAME - 0.02)

# ------------------------------------------------------------------ casing: outer skin
H_CASE = Z_TOP - Z_FRAME
box_mm("Днище_сталь10", "case", "steel_hot", XL, XR, YF, YB, Z_FRAME, Z_FRAME + 0.01)
box_mm("Задняя_стенка_5мм", "case", "steel_paint", XL, XR, YB - T5, YB, Z_FRAME, Z_TOP)
box_mm("Торец_левый_5мм", "case", "steel_paint", XL, XL + T5, YF, YB, Z_FRAME, Z_TOP)
box_mm("Торец_правый_5мм", "case", "steel_paint", XR - T5, XR, YF, YB, Z_FRAME, Z_TOP)
# front wall 8 mm with two door openings (opening = chamber section 1.9 x 1.9)
ox = [(-CHX - CH_W / 2, -CHX + CH_W / 2), (CHX - CH_W / 2, CHX + CH_W / 2)]
for nm, x0, x1 in (("Перед_край_лев", XL, ox[0][0]), ("Перед_центр", ox[0][1], ox[1][0]), ("Перед_край_прав", ox[1][1], XR)):
    box_mm(f"Передняя_стенка_8мм_{nm}", "case", "steel_paint", x0, x1, YF, YF + T8, Z_FRAME, Z_TOP, cut=True)
for (x0, x1) in ox:
    box_mm("Передняя_стенка_8мм_низ", "case", "steel_paint", x0, x1, YF, YF + T8, Z_FRAME, FLOOR, cut=True)
    box_mm("Передняя_стенка_8мм_верх", "case", "steel_paint", x0, x1, YF, YF + T8, CEIL, Z_TOP, cut=True)

# inner liner 5 mm (hot face) of each chamber + chamber lining
for s in (-1, 1):
    cx = s * CHX
    x0, x1 = cx - CH_W / 2, cx + CH_W / 2
    box_mm("Внутр_лист_потолок_5мм", "case", "steel_hot", x0, x1, CY0, CY1, CEIL, CEIL + T5, cut=True)
    box_mm("Внутр_лист_задний_5мм", "case", "steel_hot", x0, x1, CY1, CY1 + T5, FLOOR, CEIL)
    xo = x1 if s > 0 else x0  # outer (end) side
    box_mm("Внутр_лист_торцевой_5мм", "case", "steel_hot", xo - (T5 if s > 0 else 0), xo + (0 if s > 0 else T5), CY0, CY1, FLOOR, CEIL)

# ------------------------------------------------------------------ insulation 150 mm (3 x 50 blanket)
def ins_layers(name, x0, x1, y0, y1, z0, z1, axis, cut=False):
    """split a 150 mm insulation slab into 3 x 50 mm layers along axis"""
    for k in range(3):
        a = [x0, x1, y0, y1, z0, z1]
        i0 = {"x": 0, "y": 2, "z": 4}[axis]
        lo, hi = a[i0], a[i0 + 1]
        a[i0], a[i0 + 1] = lo + (hi - lo) * k / 3, lo + (hi - lo) * (k + 1) / 3
        box_mm(f"{name}_слой{k + 1}_50мм", "ins", "fiber", *a, cut=cut)

ins_layers("Изоляция_крыша", XL + T5, XR - T5, YF + T8, YB - T5, CEIL + T5, CEIL + T5 + INS, "z", cut=True)
ins_layers("Изоляция_задняя", XL + T5, XR - T5, YB - T5 - INS, YB - T5, FLOOR, CEIL, "y")
ins_layers("Изоляция_торец_лев", XL + T5, XL + T5 + INS, YF + T8, YB - T5 - INS, FLOOR, CEIL, "x")
ins_layers("Изоляция_торец_прав", XR - T5 - INS, XR - T5, YF + T8, YB - T5 - INS, FLOOR, CEIL, "x")
for nm, x0, x1 in (("лев", XL + T5 + INS, ox[0][0]), ("центр", ox[0][1], ox[1][0]), ("прав", ox[1][1], XR - T5 - INS)):
    ins_layers(f"Изоляция_перед_{nm}", x0, x1, YF + T8, CY0, FLOOR, CEIL, "y", cut=True)

# ------------------------------------------------------------------ floor: refractory plate 100 + fire brick 65
box_mm("Под_огнеупорная_плита_100мм", "brick", "plate", XL + T5, XR - T5, YF + T8, YB - T5, Z_FRAME + 0.01, Z_FRAME + 0.11)
for s in (-1, 1):
    box_mm("Под_шамотный_кирпич_65мм", "brick", "firebrick", s * CHX - CH_W / 2, s * CHX + CH_W / 2, CY0, CY1, Z_FRAME + 0.11, FLOOR)
# centre section brickwork: half-brick partitions (115 mm) + firebox lining
for s in (-1, 1):
    xin = s * (CHX - CH_W / 2)
    box_mm("Перегородка_кирпич_115мм", "brick", "firebrick", xin - s * 0.115, xin, CY0, CY1, Z_FRAME + 0.11, CEIL)
# firebox (startup) lining: front centre, behind the lower door
FB = dict(x0=-0.42, x1=0.42, y0=CY0, y1=-0.55, z0=Z_FRAME + 0.11, z1=0.95)
box_mm("Топка_под_кирпич", "brick", "firebrick", FB["x0"], FB["x1"], FB["y0"], FB["y1"], FB["z0"], FB["z0"] + 0.13)
for x in (FB["x0"], FB["x1"] - 0.115):
    box_mm("Топка_стенка_кирпич", "brick", "firebrick", x, x + 0.115, FB["y0"], FB["y1"], FB["z0"] + 0.13, FB["z1"])
box_mm("Топка_задняя_кирпич", "brick", "firebrick", FB["x0"] + 0.115, FB["x1"] - 0.115, FB["y1"] - 0.115, FB["y1"], FB["z0"] + 0.13, FB["z1"])
for i in range(7):  # cast-iron grate bars
    x = -0.27 + i * 0.09
    box_mm("Колосник_чугун", "cup", "cast_iron", x - 0.02, x + 0.02, FB["y0"] + 0.05, FB["y1"] - 0.15, 0.40, 0.44)
box_mm("Топка_свод_сталь12", "cup", "steel_hot", FB["x0"], FB["x1"], FB["y0"], FB["y1"], FB["z1"], FB["z1"] + T12)

# ------------------------------------------------------------------ combustion cups (стаканы) 12 mm
CUP_R, CUP_Y = 0.36, 0.55
for s in (-1, 1):
    cx = s * 0.33
    h = CEIL - 0.10 - (FLOOR - 0.02)
    tube("Стакан_камеры_сгорания_12мм", "cup", "steel_hot", (cx, CUP_Y, (FLOOR - 0.02) + h / 2), CUP_R, T12, h)
    cyl("Стакан_дно_12мм", "cup", "steel_hot", (cx, CUP_Y, FLOOR - 0.02 + T12 / 2), CUP_R, T12)
    # outlet windows to chamber at the top: short ducts through the partition
    box_mm("Окно_выхода_газов", "cup", "steel_hot", min(cx + s * CUP_R, s * (CHX - CH_W / 2)), max(cx + s * CUP_R, s * (CHX - CH_W / 2)), CUP_Y - 0.18, CUP_Y + 0.18, CEIL - 0.42, CEIL - 0.10, mass=shell_mass(0.23, 0.36, 0.32, T12, 4))
    # burner: tangential pyrolysis-gas nozzle + air ring
    tube("Горелка_пиролизного_газа_DN200", "cup", "steel_hot", (cx, CUP_Y + CUP_R + 0.2, 0.80), 0.1095, 0.006, 0.4, axis='Y')
    tube("Кольцо_вторичного_воздуха", "cup", "steel_hot", (cx, CUP_Y, 0.95), CUP_R + 0.03, 0.03, 0.06)
    cyl("Пламя_визуал", "cup", "glow", (cx, CUP_Y, 1.25), 0.2, 1.0, mass=0)
# flue gas from startup firebox up into the cups
box_mm("Канал_топка_стаканы", "cup", "steel_hot", -0.25, 0.25, FB["y1"], CUP_Y - CUP_R + 0.05, 0.62, 0.95, mass=shell_mass(0.5, 0.79, 0.33, T12, 4))

# ------------------------------------------------------------------ rails inside chambers
RAIL_Z = FLOOR + 0.05
for s in (-1, 1):
    for dx in (-0.6, 0.6):
        box_mm("Рельс_внутр_50х50", "brick", "steel_hot", s * CHX + dx - 0.025, s * CHX + dx + 0.025, CY0 + 0.02, CY1 - 0.02, FLOOR, RAIL_Z)

# ------------------------------------------------------------------ retorts (horizontal loading)
RT_W, RT_L, RT_H, RT_T = 1.75, 2.80, 1.60, 0.006
WHEEL_R = 0.10
RT_Z0 = RAIL_Z + WHEEL_R * 2 - 0.04          # bottom of retort body (underframe below)
def retort(ck, cx, y0, lid=True, charge=True):
    x0, x1 = cx - RT_W / 2, cx + RT_W / 2
    y1 = y0 + RT_L
    z0, z1 = RT_Z0, RT_Z0 + RT_H
    box_mm("Реторта_дно_6мм", ck, "steel_retort", x0, x1, y0, y1, z0, z0 + RT_T)
    box_mm("Реторта_бок_6мм", ck, "steel_retort", x0, x0 + RT_T, y0, y1, z0, z1)
    box_mm("Реторта_бок_6мм", ck, "steel_retort", x1 - RT_T, x1, y0, y1, z0, z1)
    box_mm("Реторта_задняя_6мм", ck, "steel_retort", x0, x1, y1 - RT_T, y1, z0, z1)
    box_mm("Реторта_верх_6мм", ck, "steel_retort", x0, x1, y0, y1, z1 - RT_T, z1, cut=(ck == "retL"))
    if lid:
        box_mm("Реторта_крышка_8мм", ck, "steel_retort", x0 - 0.03, x1 + 0.03, y0 - 0.008, y0, z0 - 0.03, z1 + 0.03, cut=(ck == "retL"))
        for k in range(4):
            z = z0 + 0.2 + k * (RT_H - 0.4) / 3
            for x in (x0 - 0.05, x1 + 0.05):
                box_mm("Реторта_клиновой_зажим", ck, "steel_profile", x - 0.03, x + 0.03, y0 - 0.05, y0 + 0.04, z - 0.04, z + 0.04, cut=(ck == "retL"))
        box_mm("Реторта_крышка_ребро", ck, "steel_profile", x0, x1, y0 - 0.06, y0 - 0.008, (z0 + z1) / 2 - 0.04, (z0 + z1) / 2 + 0.04, cut=(ck == "retL"))
        cyl("Реторта_тяговая_проушина", ck, "steel_profile", (cx, y0 - 0.09, z0 + 0.25), 0.05, 0.03, axis='Y', cut=(ck == "retL"))
    # stiffening ribs (angles) on sides
    for k in range(5):
        y = y0 + 0.2 + k * (RT_L - 0.4) / 4
        for x in (x0 - 0.03, x1 + 0.03):
            box_mm("Реторта_ребро_уголок", ck, "steel_profile", x - 0.03, x + 0.03, y - 0.03, y + 0.03, z0, z1)
    # underframe + 4 flanged wheels on 2 axles
    for dx in (-0.6, 0.6):
        box_mm("Реторта_ходовая_швеллер", ck, "steel_profile", cx + dx - 0.05, cx + dx + 0.05, y0 + 0.05, y1 - 0.05, z0 - 0.09, z0)
    for yy in (y0 + 0.45, y1 - 0.45):
        cyl("Реторта_ось_D60", ck, "steel_hot", (cx, yy, RAIL_Z + WHEEL_R), 0.03, 1.36, axis='X')
        for dx in (-0.6, 0.6):
            cyl("Реторта_колесо_чугун_D200", ck, "cast_iron", (cx + dx, yy, RAIL_Z + WHEEL_R), WHEEL_R, 0.06, axis='X')
            cyl("Реторта_реборда", ck, "cast_iron", (cx + dx - 0.04, yy, RAIL_Z + WHEEL_R), WHEEL_R + 0.018, 0.015, axis='X')
    # pyrolysis gas outlet DN150 at the back top + crane eyes
    tube("Реторта_патрубок_газа_DN200", ck, "steel_retort", (cx, y1 + 0.09, z1 - 0.25), 0.1095, 0.006, 0.18, axis='Y')
    cyl("Реторта_фланец_патрубка", ck, "steel_retort", (cx, y1 + 0.17, z1 - 0.25), 0.17, 0.02, axis='Y')
    for x in (x0 + 0.15, x1 - 0.15):
        for y in (y0 + 0.2, y1 - 0.2):
            box_mm("Реторта_рым_крановый", ck, "steel_profile", x - 0.06, x + 0.06, y - 0.012, y + 0.012, z1, z1 + 0.09, cut=(ck == "retL"))
    if charge:  # stacked logs (one mesh); mass from the yield calculation, not from the mesh
        bm = bmesh.new()
        r = 0.055; nx = int((RT_W - 0.04) / (2 * r + 0.01)); nz = int((RT_H - 0.06) / (2 * r + 0.005))
        for iz in range(nz):
            for ix in range(nx - (iz % 2)):
                for seg_y in range(2):
                    m = Matrix.Translation((x0 + 0.03 + r + ix * (2 * r + 0.01) + (iz % 2) * r, y0 + 0.05 + 0.65 + seg_y * 1.35, z0 + RT_T + r + iz * (2 * r + 0.004))) @ Matrix.Rotation(math.radians(90), 4, 'X')
                    bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=r, radius2=r, depth=1.3, matrix=m)
        ob = mesh_ob("Загрузка_дрова_полено_1.3м", bm)
        reg(ob, ck, "wood", 0.0)
        ob["note"] = "Масса загрузки — в отчёте (зависит от породы и влажности)"

retort("retL", -CHX, CY0 + 0.06)

# ------------------------------------------------------------------ loading doors (8 mm + 150 mm insulation plug)
D_W, D_H = 2.5, 2.25
D_Z0 = 0.17
YD = YF - 0.04      # door plate (front) y
def door(name, cx, hinge_side, open_deg=0.0):
    hx = cx + hinge_side * D_W / 2
    pivot = bpy.data.objects.new(name + "_ось_петель", None)
    pivot.location = (hx, YD, 0); pivot.empty_display_size = 0.3
    C["door"].objects.link(pivot)
    parts = []
    def P(ob): parts.append(ob); return ob
    x0, x1 = cx - D_W / 2, cx + D_W / 2
    P(box_mm(name + "_лист_8мм", "door", "steel_paint", x0, x1, YD - T8, YD, D_Z0, D_Z0 + D_H, cut=True))
    ins_y0 = YD
    for k in range(3):
        P(box_mm(name + f"_изоляция_слой{k + 1}", "door", "fiber", cx - 0.94, cx + 0.94, ins_y0 + k * 0.05, ins_y0 + (k + 1) * 0.05 - 0.002, FLOOR + 0.01, CEIL - 0.01, cut=True))
    P(box_mm(name + "_уплотнение_шнур", "door", "rubber", cx - 1.0, cx + 1.0, YD + 0.001, YD + 0.015, FLOOR - 0.04, FLOOR - 0.02, cut=True))
    yb = YD - T8
    # perimeter frame + grid 4x4 (flat bar 50x8)
    for z in (D_Z0 + 0.025, D_Z0 + D_H - 0.025):
        P(box_mm(name + "_рамка_гор", "door", "steel_profile", x0, x1, yb - 0.05, yb, z - 0.025, z + 0.025, cut=True))
    for x in (x0 + 0.025, x1 - 0.025):
        P(box_mm(name + "_рамка_верт", "door", "steel_profile", x - 0.025, x + 0.025, yb - 0.05, yb, D_Z0, D_Z0 + D_H, cut=True))
    for k in (1, 2, 3):
        xx = x0 + 0.08 + (D_W - 0.16) * k / 4
        P(box_mm(name + "_полоса_верт", "door", "steel_profile", xx - 0.02, xx + 0.02, yb - 0.02, yb, D_Z0 + 0.1, D_Z0 + D_H - 0.1, cut=True))
        zz = D_Z0 + 0.1 + (D_H - 0.2) * k / 4
        P(box_mm(name + "_полоса_гор", "door", "steel_profile", x0 + 0.08, x1 - 0.08, yb - 0.02, yb, zz - 0.02, zz + 0.02, cut=True))
    # locking frame: 2 horizontal channels + 2 verticals + diagonal, wedge clamps
    yf = yb - 0.1
    zt, zb = D_Z0 + D_H * 0.70, D_Z0 + D_H * 0.32
    for z in (zt, zb):
        P(box_mm(name + "_запорный_швеллер", "door", "steel_profile", x0 - 0.06, x1 + 0.06, yf - 0.04, yf + 0.04, z - 0.04, z + 0.04, cut=True))
    xo = x0 if hinge_side < 0 else x1
    sg = 1 if hinge_side < 0 else -1
    v1, v2 = xo + sg * D_W * 0.09, xo + sg * D_W * 0.49
    for x in (v1, v2):
        P(box_mm(name + "_запорная_стойка", "door", "steel_profile", x - 0.035, x + 0.035, yf - 0.035, yf + 0.035, zb, zt, cut=True))
    P(beam(name + "_раскос", "door", "steel_profile", (v1 + sg * 0.03, yf, zb + 0.04), (v2 - sg * 0.03, yf, zt - 0.04), 0.06)); parts[-1]["cutaway_hide"] = True
    for z in (D_Z0 + 0.45, D_Z0 + D_H - 0.45):
        P(cyl(name + "_петля_D60", "door", "steel_hot", (hx + hinge_side * 0.06, YD - 0.05, z), 0.03, 0.22))
    inv = Matrix.Translation(pivot.location).inverted()
    for p in parts:
        p.parent = pivot
        p.matrix_parent_inverse = inv
    pivot.rotation_euler = (0, 0, math.radians(open_deg) * hinge_side)
    pivot["assembly"] = ASSEMBLY["door"][0]
    return pivot
door("Дверь_левая", -CHX, -1, 0.0)
door("Дверь_правая", CHX, 1, 100.0)
# wedge clamps on the casing for the closed door
for z in (D_Z0 + D_H * 0.32, D_Z0 + D_H * 0.70):
    for x in (-CHX - D_W / 2 - 0.1, -CHX + D_W / 2 + 0.1):
        box_mm("Клиновой_прижим_корпус", "case", "steel_profile", x - 0.04, x + 0.04, YF - 0.12, YF, z - 0.08, z + 0.08, cut=True)

# centre section: upper inspection panel with round peephole, lower firebox door
box_mm("Смотровая_панель_центр", "door", "steel_paint", -0.5, 0.5, YF - 0.02, YF, 1.25, 2.3, cut=True)
cyl("Смотровой_люк_D200", "door", "steel_profile", (0, YF - 0.035, 1.75), 0.1, 0.03, axis='Y', cut=True)
box_mm("Дверца_топки_8мм", "door", "steel_paint", -0.34, 0.34, YF - 0.035, YF - 0.027, 0.30, 1.10, cut=True)
box_mm("Дверца_топки_изоляция", "door", "fiber", -0.3, 0.3, YF - 0.027, YF + 0.12, 0.34, 1.06, cut=True)
for z in (0.42, 0.98):
    box_mm("Дверца_топки_петля", "door", "steel_profile", -0.42, -0.34, YF - 0.06, YF - 0.03, z - 0.03, z + 0.03, cut=True)
box_mm("Дверца_топки_засов", "door", "steel_profile", 0.28, 0.40, YF - 0.07, YF - 0.035, 0.74, 0.80, cut=True)
box_mm("Поддувало_заслонка", "door", "steel_profile", -0.2, 0.2, YF - 0.05, YF - 0.035, 0.31, 0.38, cut=True)

# ------------------------------------------------------------------ external stiffening frame of casing
for x in (XL, XR):
    for y in (YF, YB):
        box_mm("Угловая_стойка_уголок100", "frame", "steel_profile", x - 0.05, x + 0.05, y - 0.05, y + 0.05, Z_FRAME, Z_TOP)
for z in (Z_FRAME + 0.05, Z_TOP - 0.05):
    box_mm("Пояс_задний", "frame", "steel_profile", XL, XR, YB, YB + 0.08, z - 0.04, z + 0.04)
    box_mm("Пояс_передний", "frame", "steel_profile", XL, XR, YF - 0.08, YF, z - 0.04, z + 0.04, cut=(z > 1))
    for x, s in ((XL, -1), (XR, 1)):
        box_mm("Пояс_торцевой", "frame", "steel_profile", x if s > 0 else x - 0.08, x + 0.08 if s > 0 else x, YF, YB, z - 0.04, z + 0.04)
for k in range(1, 8):
    x = XL + 6.7 * k / 8
    box_mm("Ребро_задней_стенки", "frame", "steel_profile", x - 0.04, x + 0.04, YB, YB + 0.08, Z_FRAME, Z_TOP)
box_mm("Ребро_задней_гор", "frame", "steel_profile", XL, XR, YB, YB + 0.08, 1.2, 1.28)
for x, s in ((XL, -1), (XR, 1)):
    for y in (-0.55, 0.55):
        box_mm("Ребро_торца", "frame", "steel_profile", x - 0.08 if s < 0 else x, x if s < 0 else x + 0.08, y - 0.04, y + 0.04, Z_FRAME, Z_TOP)
for x in (-0.55, 0.55):
    box_mm("Стойка_центральной_секции", "frame", "steel_profile", x - 0.05, x + 0.05, YF - 0.1, YF, Z_FRAME, Z_TOP, cut=True)

# ------------------------------------------------------------------ roof
box_mm("Крыша_лист_5мм", "roof", "steel_paint", XL, XR, YF, YB, Z_TOP - T5, Z_TOP, cut=True)
for k in range(1, 8):
    x = XL + 6.7 * k / 8
    box_mm("Крыша_балка", "roof", "steel_profile", x - 0.035, x + 0.035, YF, YB, Z_TOP, Z_TOP + 0.08, cut=True)
for y in (-0.55, 0.55):
    box_mm("Крыша_прогон", "roof", "steel_profile", XL, XR, y - 0.035, y + 0.035, Z_TOP, Z_TOP + 0.08, cut=True)
# rim clamps (prижимы крыши)
xx = XL + 0.2
while xx < XR - 0.1:
    for y, sgn in ((YF, -1), (YB, 1)):
        box_mm("Прижим_крыши", "roof", "steel_profile", xx - 0.025, xx + 0.025, y + sgn * 0.13 - 0.03, y + sgn * 0.13 + 0.03, Z_TOP - 0.15, Z_TOP + 0.05, cut=(y == YF))
        cyl("Прижим_болт_М20", "roof", "steel_hot", (xx, y + sgn * 0.13, Z_TOP + 0.1), 0.01, 0.12, seg=8, cut=(y == YF))
    xx += 0.4
# lifting lugs (4) — 30 mm plate
for x in (-1.83, 1.83):
    lug("Рым_строповочный_30мм", "roof", (x, YF + 0.06, Z_TOP), 0)
    lug("Рым_строповочный_30мм", "roof", (x, YB - 0.06, Z_TOP), 0)
# screw damper on top centre (bypass of hot gas to the dryer duct)
TZ = Z_TOP + 0.08
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

# ------------------------------------------------------------------ chimneys (corrugated, on flue boxes) + dampers
CHIM_Y = YF + 0.5
for s in (-1, 1):
    cx = s * (abs(XL) + 0.33)
    box_mm("Газоход_короб_у_трубы", "chim", "steel_black", cx - 0.3, cx + 0.3, CHIM_Y - 0.35, CHIM_Y + 0.35, 0.0, 0.62, mass=shell_mass(0.6, 0.7, 0.62, 0.005))
    box_mm("Газоход_врезка_в_торец", "chim", "steel_black", min(cx, s * abs(XL)), max(cx, s * abs(XL)), CHIM_Y - 0.2, CHIM_Y + 0.2, 0.18, 0.52, mass=shell_mass(0.33, 0.4, 0.34, 0.005, 4))
    tube("Труба_патрубок_D420", "chim", "steel_black", (cx, CHIM_Y, 0.70), 0.235, 0.004, 0.16)
    corrugated("Дымовая_труба_гофра_D420", "chim", "steel_black", (cx, CHIM_Y, 0.78), 0.21, 6.4, 0.012, 0.06, 0.0025)
    cyl("Дымовая_труба_оголовок", "chim", "steel_black", (cx, CHIM_Y, 7.2), 0.235, 0.05)
    cyl("Шибер_трубы_диск", "chim", "steel_hot", (cx, CHIM_Y, 3.0), 0.2, 0.006, mass=None)
    beam("Шибер_трубы_рычаг", "chim", "red_valve", (cx, CHIM_Y - 0.22, 3.0), (cx, CHIM_Y - 0.55, 2.9), 0.03)
    for z in (1.4, Z_TOP - 0.2):
        box_mm("Кронштейн_трубы", "chim", "steel_profile", min(cx, s * abs(XL)), max(cx, s * abs(XL)), CHIM_Y - 0.3, CHIM_Y - 0.25, z - 0.03, z + 0.03)
    pipe("Растяжка_трубы_тросом", "chim", "steel_hot", [(cx, CHIM_Y, 6.0), (cx + s * 1.8, CHIM_Y - 1.8, 0.0)], 0.006, wall=0.006)
    pipe("Растяжка_трубы_тросом", "chim", "steel_hot", [(cx, CHIM_Y, 6.0), (cx + s * 1.8, CHIM_Y + 2.2, 0.0)], 0.006, wall=0.006)

# ------------------------------------------------------------------ pyrolysis gas lines (retort -> cup), insulated
GZ = 2.05
for s in (-1, 1):
    rx, cx = s * CHX, s * 0.33
    box_mm("Гильза_вывода_газа_через_стенку", "gas", "steel_hot", rx - 0.13, rx + 0.13, CY1, YB, CEIL - 0.40, CEIL - 0.14, mass=shell_mass(0.26, 0.16, 0.26, 0.006, 4))
    GY = YB + 0.52
    pts = [(rx, YB, CEIL - 0.27), (rx, GY, CEIL - 0.27), (rx, GY, GZ + 0.2), (cx, GY, GZ + 0.2), (cx, GY, 0.80), (cx, CUP_Y + CUP_R + 0.4, 0.80)]
    pipe("Газопровод_пиролиз_DN200", "gas", "steel_hot", pts, 0.1095, wall=0.006)
    pipe("Газопровод_изоляция_кожух", "gas", "steel_galv", pts[1:-1], 0.17, wall=0.0007, extra=1.0)
    # tar / condensate trap at the low point + drain valve
    tube("Смолосборник_DN300", "gas", "steel_hot", (cx + s * 0.32, GY, 0.45), 0.16, 0.005, 0.45)
    pipe("Смолосборник_отвод", "gas", "steel_hot", [(cx, GY, 0.80), (cx + s * 0.32, GY, 0.80), (cx + s * 0.32, GY, 0.68)], 0.05)
    cyl("Смолосборник_кран", "gas", "red_valve", (cx + s * 0.32, GY, 0.18), 0.04, 0.08)
    cyl("Взрывной_клапан_газопровода", "gas", "orange", (rx, GY, GZ + 0.36), 0.09, 0.08)
    cyl("Задвижка_газа_DN200", "gas", "red_valve", (s * 1.1, GY, GZ + 0.2), 0.15, 0.13, axis='X', mass=65)

# ------------------------------------------------------------------ combustion air: blower + manifold DN200
AIR_Y, AIR_Z = YB + 0.17, 1.1
BX, BY = XL - 0.75, YB - 0.2
box_mm("Вентилятор_рама", "air", "steel_profile", BX - 0.35, BX + 0.35, BY - 0.35, BY + 0.35, 0.0, 0.25)
cyl("Вентилятор_улитка", "air", "steel_galv", (BX, BY, 0.62), 0.33, 0.25, axis='Y', mass=95)
cyl("Вентилятор_двигатель_1.5кВт", "air", "motor", (BX, BY - 0.3, 0.62), 0.11, 0.3, axis='Y', mass=22)
box_mm("Вентилятор_выход", "air", "steel_galv", BX - 0.1, BX + 0.1, BY, BY + 0.3, 0.85, 1.05, mass=12)
pipe("Воздуховод_DN200_коллектор", "air", "steel_galv", [(BX, BY + 0.2, 0.95), (BX, AIR_Y, AIR_Z), (XR - 0.3, AIR_Y, AIR_Z)], 0.1095, wall=0.0035)
for x, dn, label in ((-0.12, 0.057, "в_стакан"), (0.12, 0.057, "в_стакан"), (-CHX, 0.0445, "вторичный_в_камеру"), (CHX, 0.0445, "вторичный_в_камеру")):
    pipe(f"Отвод_воздуха_{label}", "air", "steel_galv", [(x, AIR_Y, AIR_Z), (x, YB, AIR_Z - 0.25 if 'стакан' in label else AIR_Z)], dn, wall=0.0035)
    cyl("Дроссель_заслонка", "air", "red_valve", (x, AIR_Y - 0.0, AIR_Z - 0.17 if 'стакан' in label else AIR_Z + 0.0), dn + 0.02, 0.05, axis='Y')

# ------------------------------------------------------------------ instrumentation & control
for s in (-1, 1):
    for y in (-0.6, 0.6):
        cyl("Термопара_ТХА_камера", "ctrl", "steel_hot", (s * CHX, y, Z_TOP + 0.05), 0.012, 0.6, seg=8)
        box_mm("Термопара_головка", "ctrl", "cabinet", s * CHX - 0.04, s * CHX + 0.04, y - 0.04, y + 0.04, Z_TOP + 0.33, Z_TOP + 0.41, mass=0.6)
    cyl("Термопара_ТХА_стакан", "ctrl", "steel_hot", (s * 0.33, CUP_Y, Z_TOP + 0.05), 0.012, 0.6, seg=8)
pipe("Кабельный_лоток", "ctrl", "steel_galv", [(XR - 0.3, YB - 0.2, Z_TOP + 0.1), (XL + 0.05, YB - 0.2, Z_TOP + 0.1), (XL - 0.05, YB - 0.2, Z_TOP + 0.1), (XL - 0.05, 0.3, 1.9)], 0.03, wall=0.0015)
box_mm("Шкаф_управления_АСУ", "ctrl", "cabinet", XL - 0.32, XL - 0.02, 0.0, 0.6, 1.1, 1.9, mass=48)
box_mm("Шкаф_управления_дисплей", "ctrl", "steel_black", XL - 0.325, XL - 0.32, 0.12, 0.48, 1.55, 1.8, mass=1)
box_mm("Шкаф_индикатор", "ctrl", "orange", XL - 0.33, XL - 0.32, 0.5, 0.56, 1.82, 1.86, mass=0.1)
# service ladder to the roof (left end)
LX = XL - 0.25
for y in (0.85, 1.35):
    box_mm("Лестница_тетива", "ctrl", "steel_profile", LX - 0.03, LX + 0.03, y - 0.03, y + 0.03, 0.0, Z_TOP + 1.0)
for k in range(9):
    cyl("Лестница_ступень", "ctrl", "steel_hot", (LX, 1.1, 0.3 + k * 0.3), 0.012, 0.5, axis='Y', seg=8)
for k in range(5):
    pipe("Лестница_ограждение_дуга", "ctrl", "steel_hot", [(LX, 0.85, 1.4 + k * 0.3), (LX - 0.35, 0.85, 1.4 + k * 0.3), (LX - 0.35, 1.35, 1.4 + k * 0.3), (LX, 1.35, 1.4 + k * 0.3)], 0.01)

# ------------------------------------------------------------------ external loading platform + winch (right chamber)
PY0, PY1 = YF - 0.12, YF - 3.6
for dx in (-0.6, 0.6):
    box_mm("Площадка_рельс_50х50", "track", "steel_hot", CHX + dx - 0.025, CHX + dx + 0.025, PY1, PY0, RAIL_Z - 0.05, RAIL_Z)
    box_mm("Площадка_балка_двутавр", "track", "steel_profile", CHX + dx - 0.06, CHX + dx + 0.06, PY1, PY0, FLOOR - 0.2, RAIL_Z - 0.05)
for k in range(5):
    y = PY0 - 0.2 - k * (abs(PY1 - PY0) - 0.4) / 4
    box_mm("Площадка_поперечина", "track", "steel_profile", CHX - 0.8, CHX + 0.8, y - 0.04, y + 0.04, FLOOR - 0.2, FLOOR - 0.05)
    for dx in (-0.7, 0.7):
        box_mm("Площадка_опора", "track", "steel_profile", CHX + dx - 0.05, CHX + dx + 0.05, y - 0.05, y + 0.05, -0.2, FLOOR - 0.2)
WY = PY1 - 0.35
box_mm("Лебёдка_стойка", "track", "steel_profile", CHX - 0.35, CHX + 0.35, WY - 0.2, WY + 0.2, -0.2, 0.6)
cyl("Лебёдка_барабан", "track", "steel_hot", (CHX, WY, 0.75), 0.12, 0.45, axis='X')
cyl("Лебёдка_мотор-редуктор", "track", "motor", (CHX + 0.4, WY, 0.75), 0.12, 0.3, axis='X', mass=60)
retort("retR", CHX, PY1 + 0.15)
pipe("Лебёдка_трос_D10", "track", "steel_hot", [(CHX, WY + 0.12, 0.75), (CHX, PY1 + 0.06, RT_Z0 + 0.25)], 0.005, wall=0.005)

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
rx = abs(XL) + 0.33
duct = [(rx + 0.3, CHIM_Y, 0.32), (4.35, CHIM_Y, 0.32), (4.35, -0.2, 0.32), (DX0, -0.2, 0.32)]
pipe("Газоход_на_сушилку_D400", "dry", "steel_black", duct, 0.2, wall=0.003)
pipe("Газоход_на_сушилку_изоляция", "dry", "steel_galv", duct[1:], 0.28, wall=0.0007)
cyl("Заслонка_с_электроприводом", "dry", "orange", (4.35, -0.75, 0.32), 0.3, 0.1, axis='Y', mass=38)
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
    "geometry": {"chamber": [CH_D, CH_W, CH_H], "retort_outer": [RT_L, RT_W, RT_H], "retort_wall": RT_T,
                 "retort_inner_volume_m3": round((RT_W - 2 * RT_T) * (RT_L - 2 * RT_T) * (RT_H - 2 * RT_T), 3),
                 "chamber_volume_m3": round(CH_W * CH_D * CH_H, 3),
                 "clearance_side_mm": round((CH_W - RT_W) / 2 * 1000), "clearance_top_mm": round((CEIL - (RT_Z0 + RT_H)) * 1000),
                 "clearance_length_mm": round((CH_D - RT_L) * 1000),
                 "footprint_m": [XR - XL, YB - YF], "overall_depth_with_air_pipe_m": round((AIR_Y + 0.1095) - YF, 3), "overall_depth_with_gas_lines_m": round((YB + 0.52 + 0.17) - YF, 3),
                 "chimney_top_m": 7.225, "chimney_d_m": 0.42, "z_top_m": Z_TOP, "lugs": 4,
                 "casing_outer_area_m2": round(2 * (6.7 * H_CASE) + 2 * ((YB - YF) * H_CASE) + 6.7 * (YB - YF), 2)},
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
        "RB_Печь": proxy_for(kiln_keys + ["retL"], "RB_Печь", bounds=((XL, YF, 0.0), (XR, YB, Z_TOP))),
        "RB_Площадка": proxy_for(["track"], "RB_Площадка", passive=True, bounds=((CHX - 0.8, PY1 - 0.6, -0.2), (CHX + 0.8, PY0, RAIL_Z))),
        "RB_Реторта_2": proxy_for(["retR"], "RB_Реторта_2", bounds=((CHX - RT_W / 2 - 0.1, PY1 + 0.0, RAIL_Z), (CHX + RT_W / 2 + 0.1, PY1 + 0.15 + RT_L + 0.2, RT_Z0 + RT_H + 0.1))),
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
H_ch = 7.225 - 0.3
rho_air = 1.293 * 273 / (273 + 20)
calc["chimney_draft"] = {}
for Tg in (200, 300, 400):
    rho_g = 1.30 * 273 / (273 + Tg)
    calc["chimney_draft"][f"{Tg}C"] = round(g0 * H_ch * (rho_air - rho_g), 1)
# pyrolysis gas pipe velocity & combustion air
t_active_h = 10.0
m_dot = volatiles / (t_active_h * 3600)                           # kg/s both retorts, average
rho_pg = 0.95 * 273 / (273 + 400)
A200 = math.pi * 0.1035 ** 2   # DN200, pipe 219 x 6
v_pg = m_dot / 2 / rho_pg / A200
air_ratio = 3.6 * 1.3                                            # kg air per kg volatiles (stoich ~3.6) x excess 1.3
air = m_dot * air_ratio
Q_air = air / 1.2
A_air = math.pi * 0.1025 ** 2
calc["gas_and_air"] = {"pyrolysis_gas_kg_s_avg": round(m_dot, 3), "gas_velocity_DN200_m_s": round(v_pg, 1), "gas_velocity_DN150_m_s_rejected": round(m_dot / 2 / rho_pg / (math.pi * 0.0705 ** 2), 1), "peak_factor_assumed": 2.0,
    "gas_velocity_DN200_peak_m_s": round(v_pg * 2, 1), "gas_velocity_DN150_peak_m_s_rejected": round(2 * m_dot / 2 / rho_pg / (math.pi * 0.0705 ** 2), 1), "air_kg_s": round(air, 3), "air_m3_h": round(Q_air * 3600), "air_velocity_DN200_m_s": round(Q_air / A_air, 1),
    "blower_power_kW_at_1kPa": round(Q_air * 1000 / 0.6 / 1000 * 2, 2)}
# thermal expansion
alpha = 12e-6
calc["thermal_expansion_mm"] = {"retort_length_2.8m_dT435": round(alpha * 435 * RT_L * 1000, 1), "retort_width": round(alpha * 435 * RT_W * 1000, 1),
    "retort_height": round(alpha * 435 * RT_H * 1000, 1), "liner_6.7m_dT430": round(alpha * 430 * 6.3 * 1000, 1), "cup_height_dT800": round(alpha * 800 * 1.9 * 1000, 1)}
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
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "PROMETHEY_kiln_v3.blend"), compress=True)

export_objs = [o for o in bpy.data.objects if o.type in ('MESH', 'EMPTY') and not o.name.startswith("RB_") and o.name not in ("Грунт",)]
bpy.ops.object.select_all(action='DESELECT')
for o in export_objs: o.select_set(True)
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "PROMETHEY_kiln_v3.glb"), export_format='GLB', use_selection=True, export_apply=True, export_extras=True,
                          export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=6)
bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, "PROMETHEY_kiln_v3.fbx"), use_selection=True, path_mode='COPY')

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
aim((-4.0, -9.0, 6.5), (-0.6, 0.2, 1.0), 30); shot("render_04_разрез.png")
for o in cut: o.hide_render = False
print("DONE", len(OBJS))
