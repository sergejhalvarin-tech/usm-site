import bpy, bmesh, math, os, sys, random
from mathutils import Vector

OUT = sys.argv[sys.argv.index("--") + 1]
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'

def coll(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or scene.collection).children.link(c)
    return c

ROOT = coll("Furnace")
C_BASE = coll("Plinth", ROOT)
C_CASE = coll("Casing", ROOT)
C_DOOR = coll("Doors", ROOT)
C_ROOF = coll("Roof_Removable", ROOT)
C_TOP = coll("Roof_Damper", ROOT)
C_IN = coll("Interior_Lining", ROOT)
C_CHIM = coll("Chimneys", ROOT)

# ---------------- materials ----------------
def mat(name, rgb, metal=0.0, rough=0.5, img=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    if img:
        t = m.node_tree.nodes.new("ShaderNodeTexImage")
        t.image = img
        m.node_tree.links.new(t.outputs["Color"], b.inputs["Base Color"])
    m.diffuse_color = (*rgb, 1)
    return m

def brick_image(w=512, h=512):
    img = bpy.data.images.new("Brick_Texture", w, h)
    bw, bh, mortar = 128, 64, 5
    px = [0.0] * (w * h * 4)
    random.seed(3); tint = {}
    for y in range(h):
        row = y // bh
        off = (bw // 2) if row % 2 else 0
        for x in range(w):
            xx = (x + off) % w
            i = (y * w + x) * 4
            if (y % bh) < mortar or (xx % bw) < mortar:
                c = (0.78, 0.74, 0.68)
            else:
                k = (row, xx // bw)
                t = tint.setdefault(k, random.uniform(-0.06, 0.06))
                c = (0.62 + t, 0.24 + t * 0.5, 0.18 + t * 0.4)
            px[i:i + 4] = (c[0], c[1], c[2], 1.0)
    img.pixels = px
    img.pack()
    return img

M_PANEL = mat("Paint_Graphite_Panel", (0.03, 0.032, 0.034), 0.35, 0.55)
M_BAR = mat("Paint_Graphite_Bar", (0.022, 0.023, 0.025), 0.45, 0.45)
M_BLACK = mat("Chimney_Black", (0.012, 0.012, 0.013), 0.5, 0.45)
M_RUST = mat("Rust_Hood", (0.42, 0.12, 0.04), 0.2, 0.7)
M_CONC = mat("Concrete", (0.26, 0.25, 0.23), 0.0, 0.9)
M_FIBER = mat("Ceramic_Fiber", (0.93, 0.93, 0.90), 0.0, 0.9)
M_BRICK = mat("Fire_Brick", (0.6, 0.25, 0.18), 0.0, 0.85, brick_image())
M_FLOOR = mat("Refractory_Floor", (0.55, 0.52, 0.48), 0.0, 0.9)

# ---------------- primitives ----------------
def box(name, c, center, size, m, bevel=0.0):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); c.objects.link(ob)
    ob.location = center
    me.materials.append(m)
    if bevel > 0:
        md = ob.modifiers.new("Bevel", 'BEVEL'); md.width = bevel; md.segments = 2
    return ob

def cyl(name, c, center, r, depth, m, axis='Z', seg=32):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r, depth=depth)
    bm.to_mesh(me); bm.free()
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new(name, me); c.objects.link(ob)
    ob.location = center
    if axis == 'X':
        ob.rotation_euler = (0, math.radians(90), 0)
    elif axis == 'Y':
        ob.rotation_euler = (math.radians(90), 0, 0)
    me.materials.append(m)
    return ob

def beam(name, c, p0, p1, t, m, d=None):
    p0, p1 = Vector(p0), Vector(p1)
    v = p1 - p0
    ob = box(name, c, (p0 + p1) / 2, (t, d or t, v.length), m)
    ob.rotation_euler = v.to_track_quat('Z', 'Y').to_euler()
    return ob

def pipe(name, c, pts, r, m):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'; cu.bevel_depth = r; cu.bevel_resolution = 6; cu.use_fill_caps = True
    sp = cu.splines.new('POLY'); sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (*p, 1)
    ob = bpy.data.objects.new(name, cu); c.objects.link(ob)
    cu.materials.append(m)
    return ob

def corrugated(name, c, base, r, h, amp, pitch, m, seg=32):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    steps = int(h / (pitch / 4))
    rings = []
    for k in range(steps + 1):
        z = h * k / steps
        rr = r + amp * math.sin(2 * math.pi * z / pitch)
        rings.append([bm.verts.new((rr * math.cos(2 * math.pi * i / seg), rr * math.sin(2 * math.pi * i / seg), z)) for i in range(seg)])
    for a, b in zip(rings, rings[1:]):
        for i in range(seg):
            bm.faces.new((a[i], a[(i + 1) % seg], b[(i + 1) % seg], b[i]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new(name, me); c.objects.link(ob)
    ob.location = base
    me.materials.append(m)
    return ob

def arch(name, c, x0, x1, r, thick, yc, zc, m, seg=32):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    rings = []
    for x in (x0, x1):
        rings.append([[bm.verts.new((x, yc + rr * math.cos(math.pi * i / seg), zc + rr * math.sin(math.pi * i / seg)))
                       for i in range(seg + 1)] for rr in (r, r + thick)])
    (a_in, a_out), (b_in, b_out) = rings
    for i in range(seg):
        bm.faces.new((a_in[i], a_in[i + 1], b_in[i + 1], b_in[i]))
        bm.faces.new((a_out[i], b_out[i], b_out[i + 1], a_out[i + 1]))
        bm.faces.new((a_in[i], a_out[i], a_out[i + 1], a_in[i + 1]))
        bm.faces.new((b_in[i], b_in[i + 1], b_out[i + 1], b_out[i]))
    for j in (0, seg):
        bm.faces.new((a_in[j], b_in[j], b_out[j], a_out[j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new(name, me); c.objects.link(ob)
    me.materials.append(m)
    return ob

def lug(name, c, center, rot_z=0.0):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    w, h, rr, t = 0.26, 0.17, 0.13, 0.03
    prof = [(-w / 2, 0), (w / 2, 0), (w / 2, h)]
    for i in range(1, 16):
        a = math.pi * i / 16
        prof.append((rr * math.cos(a), h + rr * math.sin(a)))
    prof.append((-w / 2, h))
    f = bm.faces.new([bm.verts.new((x, -t / 2, z)) for x, z in prof])
    ext = bmesh.ops.extrude_face_region(bm, geom=[f])
    bmesh.ops.translate(bm, vec=(0, t, 0), verts=[e for e in ext['geom'] if isinstance(e, bmesh.types.BMVert)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); c.objects.link(ob)
    me.materials.append(M_BAR)
    hole = cyl(name + "_hole", c, (0, 0, h + 0.01), 0.05, 0.2, M_BAR, axis='Y', seg=24)
    hole.parent = ob
    md = ob.modifiers.new("Hole", 'BOOLEAN'); md.object = hole; md.operation = 'DIFFERENCE'
    hole.hide_render = True
    ob.location = center
    ob.rotation_euler = (0, 0, rot_z)
    return ob

# ---------------- dimensions (from front photo: L/H ~ 2.3) ----------------
L, W = 6.0, 2.8
Z0, Z1 = 0.22, 2.82          # casing bottom / top (H = 2.6 m)
H = Z1 - Z0
XL, XR = -L / 2, L / 2
YF, YB = -W / 2, W / 2
CS = 0.51                    # half width of central section
PR = 0.1                     # main frame channel
LIN = 0.28

def zf(frac_from_top):
    return Z1 - frac_from_top * H

# ---------------- plinth ----------------
box("Concrete_Plinth", C_BASE, (0, 0, Z0 / 2), (L + 0.3, W + 0.25, Z0), M_CONC, bevel=0.02)

# ---------------- casing ----------------
T = 0.012
box("Wall_Front", C_CASE, (0, YF, Z0 + H / 2), (L, T, H), M_PANEL)
box("Wall_Back", C_CASE, (0, YB, Z0 + H / 2), (L, T, H), M_PANEL)
box("Wall_Left", C_CASE, (XL, 0, Z0 + H / 2), (T, W, H), M_PANEL)
box("Wall_Right", C_CASE, (XR, 0, Z0 + H / 2), (T, W, H), M_PANEL)
box("Casing_Bottom", C_CASE, (0, 0, Z0 + 0.01), (L, W, 0.02), M_PANEL)

for x in (XL, XR):
    for y in (YF, YB):
        box("Corner_Post", C_CASE, (x, y, Z0 + H / 2), (PR * 1.2, PR * 1.2, H), M_BAR)
# bottom channel & top angle rim
for y, s in ((YF, -1), (YB, 1)):
    box("Bottom_Channel", C_CASE, (0, y + s * 0.04, Z0 + 0.06), (L + 0.12, 0.08, 0.12), M_BAR)
    box("Top_Angle", C_CASE, (0, y + s * 0.05, Z1 - 0.05), (L + 0.14, 0.1, 0.1), M_BAR)
    box("Top_Angle_Flange", C_CASE, (0, y + s * 0.06, Z1 + 0.005), (L + 0.16, 0.12, 0.012), M_BAR)
for x, s in ((XL, -1), (XR, 1)):
    box("Bottom_Channel", C_CASE, (x + s * 0.04, 0, Z0 + 0.06), (0.08, W, 0.12), M_BAR)
    box("Top_Angle", C_CASE, (x + s * 0.05, 0, Z1 - 0.05), (0.1, W, 0.1), M_BAR)
    box("Top_Angle_Flange", C_CASE, (x + s * 0.06, 0, Z1 + 0.005), (0.12, W + 0.24, 0.012), M_BAR)

# front: section posts
for x in (-CS, CS):
    box("Section_Post", C_CASE, (x, YF - 0.05, Z0 + H / 2), (0.1, 0.1, H), M_BAR)

# back wall: vertical stiffeners + horizontal rib (photo 1)
nb = 8
for k in range(1, nb):
    x = XL + L * k / nb
    box("Back_Stiffener_V", C_CASE, (x, YB + 0.04, Z0 + H / 2), (0.08, 0.08, H), M_BAR)
box("Back_Stiffener_H", C_CASE, (0, YB + 0.04, zf(0.55)), (L, 0.08, 0.08), M_BAR)
for x in (-1.9, 0.6):
    cyl("Back_Pipe_Stub", C_CASE, (x, YB + 0.06, Z0 + 0.45), 0.05, 0.12, M_BAR, axis='Y')

# end walls: ribs + ports
for x, s in ((XL, -1), (XR, 1)):
    for k in (1, 2):
        box("End_Stiffener_V", C_CASE, (x + s * 0.04, YF + W * k / 3, Z0 + H / 2), (0.08, 0.08, H), M_BAR)
    box("End_Stiffener_H", C_CASE, (x + s * 0.05, 0, zf(0.42)), (0.1, W, 0.1), M_BAR)
    for y in (YF + W * 0.5, YF + W * 0.8):
        cyl("End_Port", C_CASE, (x + s * 0.02, y, zf(0.22)), 0.07, 0.04, M_BLACK, axis='X')

# top edge clamps (wedge clamps every ~0.35 m)
def top_clamps():
    for y, s in ((YF, -1), (YB, 1)):
        x = XL + 0.2
        while x < XR - 0.1:
            box("Top_Clamp", C_CASE, (x, y + s * 0.1, Z1 - 0.02), (0.05, 0.06, 0.14), M_BAR)
            cyl("Top_Clamp_Bolt", C_CASE, (x, y + s * 0.1, Z1 + 0.09), 0.012, 0.1, M_BAR, seg=8)
            x += 0.36
    for x, s in ((XL, -1), (XR, 1)):
        y = YF + 0.25
        while y < YB - 0.1:
            box("Top_Clamp", C_CASE, (x + s * 0.1, y, Z1 - 0.02), (0.06, 0.05, 0.14), M_BAR)
            cyl("Top_Clamp_Bolt", C_CASE, (x + s * 0.1, y, Z1 + 0.09), 0.012, 0.1, M_BAR, seg=8)
            y += 0.36
top_clamps()

# lifting lugs (front & back at +-1.83 m)
for x in (-1.83, 1.83):
    lug("Lifting_Lug", C_CASE, (x, YF + 0.06, Z1 + 0.01))
    lug("Lifting_Lug", C_CASE, (x, YB - 0.06, Z1 + 0.01))

# ---------------- chamber doors ----------------
YD = YF - 0.035           # door plate centre
def chamber_door(name, xa, xb, outer):  # outer = -1 left (outer edge xa), +1 right (outer edge xb)
    dz0, dz1 = Z0 + 0.12, Z1 - 0.12
    dw, dh = xb - xa, dz1 - dz0
    xc, zc = (xa + xb) / 2, (dz0 + dz1) / 2
    box(name + "_Plate", C_DOOR, (xc, YD, zc), (dw, 0.05, dh), M_PANEL, bevel=0.004)
    # perimeter flat bar
    yb = YD - 0.03
    for z in (dz0 + 0.02, dz1 - 0.02):
        box(name + "_Edge_H", C_DOOR, (xc, yb, z), (dw, 0.015, 0.05), M_BAR)
    for x in (xa + 0.02, xb - 0.02):
        box(name + "_Edge_V", C_DOOR, (x, yb, zc), (0.05, 0.015, dh), M_BAR)
    # inner grid 4 x 4 of flat bar
    ix0, ix1, iz0, iz1 = xa + 0.08, xb - 0.08, dz0 + 0.1, dz1 - 0.1
    box(name + "_Inner_Frame_T", C_DOOR, (xc, yb, iz1), (ix1 - ix0, 0.015, 0.035), M_BAR)
    box(name + "_Inner_Frame_B", C_DOOR, (xc, yb, iz0), (ix1 - ix0, 0.015, 0.035), M_BAR)
    box(name + "_Inner_Frame_L", C_DOOR, (ix0, yb, (iz0 + iz1) / 2), (0.035, 0.015, iz1 - iz0), M_BAR)
    box(name + "_Inner_Frame_R", C_DOOR, (ix1, yb, (iz0 + iz1) / 2), (0.035, 0.015, iz1 - iz0), M_BAR)
    for k in (1, 2, 3):
        x = ix0 + (ix1 - ix0) * k / 4
        box(name + "_Grid_V", C_DOOR, (x, yb, (iz0 + iz1) / 2), (0.03, 0.012, iz1 - iz0), M_BAR)
        z = iz0 + (iz1 - iz0) * k / 4
        box(name + "_Grid_H", C_DOOR, (xc, yb, z), (ix1 - ix0, 0.012, 0.03), M_BAR)
    # handles (vertical round bars) in middle row cells
    for k in (1.5, 2.5):
        x = ix0 + (ix1 - ix0) * k / 4
        z = iz0 + (iz1 - iz0) * 0.42
        cyl(name + "_Handle", C_DOOR, (x, yb - 0.04, z), 0.012, 0.2, M_BAR, seg=8)
        for dz in (-0.09, 0.09):
            box(name + "_Handle_Std", C_DOOR, (x, yb - 0.02, z + dz), (0.02, 0.04, 0.02), M_BAR)
    # hinge tabs top & bottom
    for k in (0.37, 0.7):
        x = xa + dw * (k if outer < 0 else 1 - k)
        for z, s in ((dz1, 1), (dz0, -1)):
            box(name + "_Tab", C_DOOR, (x, YD - 0.04, z + s * 0.0), (0.09, 0.05, 0.16), M_BAR)
    # inner-edge wedge latches
    xin = xb if outer < 0 else xa
    for frac in (0.3, 0.6):
        box(name + "_Latch", C_DOOR, (xin + (-0.03 if outer < 0 else 0.03), YD - 0.07, zf(frac)), (0.11, 0.07, 0.08), M_BAR)
    # locking frame: 2 horizontal channels across the door, 2 verticals, diagonal
    yf = YD - 0.09
    zt, zb = zf(0.30), zf(0.68)
    xo = xa if outer < 0 else xb
    sgn = 1 if outer < 0 else -1      # direction from outer edge inwards
    for z in (zt, zb):
        box(name + "_Bar_H", C_DOOR, (xc + outer * 0.04, yf, z), (dw + 0.1, 0.08, 0.08), M_BAR)
        box(name + "_Bar_Clamp", C_DOOR, (xo - sgn * 0.02, yf + 0.02, z), (0.07, 0.1, 0.16), M_BAR)
        box(name + "_Bar_Clamp", C_DOOR, (xin + sgn * 0.0 - sgn * 0.0, yf + 0.02, z), (0.07, 0.1, 0.14), M_BAR)
    v1 = xo + sgn * dw * 0.09
    v2 = xo + sgn * dw * 0.49
    for x in (v1, v2):
        box(name + "_Bar_V", C_DOOR, (x, yf, (zt + zb) / 2), (0.07, 0.07, zt - zb + 0.08), M_BAR)
    beam(name + "_Bar_Diag", C_DOOR, (v1 + sgn * 0.03, yf, zb + 0.04), (v2 - sgn * 0.03, yf, zt - 0.04), 0.06, M_BAR)

chamber_door("Door_Left", XL + 0.1, -CS - 0.07, -1)
chamber_door("Door_Right", CS + 0.07, XR - 0.1, 1)

# central section: upper panel with round hatch, lower small door
cz_split = zf(0.6)
box("Center_Upper_Panel", C_DOOR, (0, YD, (cz_split + Z1 - 0.12) / 2), (2 * CS - 0.14, 0.04, Z1 - 0.12 - cz_split), M_PANEL)
box("Center_Divider", C_DOOR, (0, YD - 0.03, cz_split), (2 * CS - 0.1, 0.05, 0.06), M_BAR)
cyl("Center_Hatch", C_DOOR, (0, YD - 0.04, zf(0.41)), 0.085, 0.04, M_BAR, axis='Y')
cyl("Center_Hatch_Knob", C_DOOR, (0, YD - 0.07, zf(0.41)), 0.025, 0.03, M_BAR, axis='Y')
box("Center_Bracket", C_DOOR, (0, YD - 0.06, cz_split + 0.06), (0.12, 0.05, 0.06), M_BAR)
# lower door
ldx0, ldx1, ldz0, ldz1 = -0.34, 0.34, zf(0.95), zf(0.62)
box("Lower_Door", C_DOOR, (0, YD - 0.01, (ldz0 + ldz1) / 2), (ldx1 - ldx0, 0.05, ldz1 - ldz0), M_PANEL, bevel=0.004)
for z in (ldz0, ldz1):
    box("Lower_Door_Frame_H", C_DOOR, (0, YD - 0.04, z), (ldx1 - ldx0 + 0.06, 0.03, 0.05), M_BAR)
for x in (ldx0, ldx1):
    box("Lower_Door_Frame_V", C_DOOR, (x, YD - 0.04, (ldz0 + ldz1) / 2), (0.05, 0.03, ldz1 - ldz0 + 0.06), M_BAR)
box("Lower_Door_Inner", C_DOOR, (0.03, YD - 0.045, (ldz0 + ldz1) / 2), (0.42, 0.012, ldz1 - ldz0 - 0.18), M_BAR)
for z in (ldz1 - 0.1, ldz0 + 0.12):
    box("Lower_Door_Hinge", C_DOOR, (ldx0 - 0.04, YD - 0.06, z), (0.1, 0.05, 0.05), M_BAR)
box("Lower_Door_Latch", C_DOOR, (ldx1 - 0.03, YD - 0.07, (ldz0 + ldz1) / 2 + 0.05), (0.08, 0.05, 0.12), M_BAR)
cyl("Lower_Door_Handle", C_DOOR, (0.0, YD - 0.08, ldz1 - 0.15), 0.01, 0.14, M_BAR, seg=8)
for x in (-CS + 0.08, CS - 0.08):
    for z in (zf(0.3), zf(0.68)):
        box("Center_Side_Tab", C_DOOR, (x, YD - 0.06, z), (0.06, 0.05, 0.12), M_BAR)

# ---------------- interior lining (same concept as CAD) ----------------
IZ0, IZ1 = Z0 + 0.02, Z1 - 0.02
box("Lining_Floor", C_IN, (0, 0, IZ0 + 0.1), (L - 0.04, W - 0.04, 0.2), M_FLOOR)
box("Lining_Front", C_IN, (0, YF + LIN / 2 + 0.01, (IZ0 + IZ1) / 2), (L - 0.04, LIN, IZ1 - IZ0), M_FIBER)
box("Lining_Back", C_IN, (0, YB - LIN / 2 - 0.01, (IZ0 + IZ1) / 2), (L - 0.04, LIN, IZ1 - IZ0), M_FIBER)
box("Lining_Left", C_IN, (XL + LIN / 2 + 0.01, 0, (IZ0 + IZ1) / 2), (LIN, W - 0.04, IZ1 - IZ0), M_FIBER)
box("Lining_Right", C_IN, (XR - LIN / 2 - 0.01, 0, (IZ0 + IZ1) / 2), (LIN, W - 0.04, IZ1 - IZ0), M_FIBER)
inner_w = W - 2 * LIN - 0.02
r_arch = inner_w / 2 - 0.02
z_spring = IZ0 + 0.2 + 0.3
for xa, xb in ((XL + LIN + 0.02, -CS - 0.02), (CS + 0.02, XR - LIN - 0.02)):
    arch("Chamber_Vault", C_IN, xa, xb, r_arch - 0.06, 0.06, 0, z_spring, M_FIBER)
    n = int((xb - xa) / 0.36)
    for i in range(n):
        x = xa + 0.06 + i * (xb - xa - 0.12) / max(n - 1, 1)
        arch("Vault_Rib", C_IN, x - 0.07, x + 0.07, r_arch, 0.09, 0, z_spring, M_FIBER)
    for y in (-inner_w / 2 + 0.1, inner_w / 2 - 0.1):
        box("Vault_Base", C_IN, ((xa + xb) / 2, y, z_spring - 0.15), (xb - xa, 0.2, 0.3), M_FIBER)
brick_h = 1.3
for x in (-CS + 0.12, CS - 0.12):
    box("Brick_Wall", C_IN, (x, 0, IZ0 + 0.2 + brick_h / 2), (0.24, inner_w, brick_h), M_BRICK)
box("Brick_Floor", C_IN, (0, 0, IZ0 + 0.26), (2 * CS, inner_w, 0.12), M_BRICK)
box("Brick_Back_Wall", C_IN, (0, inner_w / 2 - 0.12, IZ0 + 0.2 + brick_h / 2), (2 * CS - 0.48, 0.24, brick_h), M_BRICK)

# ---------------- roof ----------------
RZ = Z1 + 0.012
box("Roof_Panel", C_ROOF, (0, 0, RZ + 0.01), (L + 0.1, W + 0.1, 0.02), M_PANEL)
box("Roof_Insulation", C_ROOF, (0, 0, RZ - 0.12), (L - 2 * LIN, W - 2 * LIN, 0.22), M_FIBER)
for k in range(1, 8):
    box("Roof_Beam_X", C_ROOF, (XL + L * k / 8, 0, RZ + 0.06), (0.07, W + 0.1, 0.08), M_BAR)
for k in (1, 2):
    box("Roof_Beam_Y", C_ROOF, (0, YF + W * k / 3, RZ + 0.06), (L + 0.1, 0.07, 0.08), M_BAR)

# damper unit on top centre (box + 4 posts + screw + handwheel + lever)
TZ = RZ + 0.1
dy = -0.1
box("Damper_Housing", C_TOP, (0, dy, TZ + 0.15), (0.42, 0.42, 0.3), M_BLACK, bevel=0.01)
for sx in (-0.17, 0.17):
    for sy in (-0.17, 0.17):
        box("Damper_Post", C_TOP, (sx, dy + sy, TZ + 0.45), (0.04, 0.04, 0.32), M_BLACK)
box("Damper_Top_Plate", C_TOP, (0, dy, TZ + 0.62), (0.44, 0.44, 0.03), M_BLACK)
cyl("Damper_Screw", C_TOP, (0, dy, TZ + 0.55), 0.018, 0.45, M_BAR, seg=12)
box("Damper_Gate", C_TOP, (0, dy, TZ + 0.38), (0.3, 0.06, 0.12), M_BLACK)
bpy.ops.mesh.primitive_torus_add(major_radius=0.1, minor_radius=0.012, location=(0, dy, TZ + 0.78))
wheel = bpy.context.active_object; wheel.name = "Damper_Handwheel"
for c in wheel.users_collection: c.objects.unlink(wheel)
C_TOP.objects.link(wheel); wheel.data.materials.append(M_BLACK)
lev = cyl("Damper_Lever", C_TOP, (0.42, dy - 0.25, TZ + 0.22), 0.015, 0.6, M_BLACK, axis='X', seg=10)
cyl("Damper_Lever_Weight", C_TOP, (0.72, dy - 0.25, TZ + 0.22), 0.045, 0.1, M_BLACK, axis='X')
box("Damper_Lever_Pivot", C_TOP, (0.2, dy - 0.25, TZ + 0.12), (0.05, 0.05, 0.2), M_BLACK)
# rusty hood + roof rail bracket (photo 2)
hood = box("Rust_Hood", C_TOP, (-0.8, 0.35, TZ + 0.12), (0.45, 0.35, 0.22), M_RUST)
hood.rotation_euler = (0, math.radians(-25), 0)
for x in (-2.0, -1.6):
    box("Roof_Rail_Post", C_TOP, (x, 0.2, TZ + 0.15), (0.05, 0.05, 0.3), M_BAR)
box("Roof_Rail", C_TOP, (-1.8, 0.2, TZ + 0.3), (0.5, 0.06, 0.05), M_BAR)
box("Roof_Rail_Arm", C_TOP, (-1.55, 0.05, TZ + 0.3), (0.05, 0.35, 0.05), M_BAR)

# ---------------- corrugated chimneys on flue boxes ----------------
def chimney(name, xend, s):
    cx = xend + s * 0.33
    cy = YF + 0.5
    box(name + "_Flue_Box", C_CHIM, (cx, cy, 0.3), (0.6, 0.7, 0.6), M_BLACK, bevel=0.01)
    box(name + "_Flue_Duct", C_CHIM, (xend + s * 0.03, cy, 0.3), (0.06, 0.4, 0.35), M_BLACK)
    cyl(name + "_Collar", C_CHIM, (cx, cy, 0.66), 0.25, 0.12, M_BLACK)
    corrugated(name, C_CHIM, (cx, cy, 0.6), 0.21, 6.6, 0.012, 0.06, M_BLACK)
    cyl(name + "_Top_Ring", C_CHIM, (cx, cy, 7.2), 0.235, 0.05, M_BLACK)
    # side stub pipe into the end wall (upper part)
    cyl(name + "_Side_Pipe", C_CHIM, ((xend + cx) / 2 - s * 0.0, cy + 0.0, zf(0.32)), 0.11, abs(cx - xend) + 0.05, M_BLACK, axis='X')
    # cane-shaped bracket pipe beside chimney
    px = xend - s * 0.3
    pipe(name + "_Brace_Pipe", C_CHIM, [(px, cy + 0.05, RZ), (px, cy + 0.05, RZ + 0.95), (cx - s * 0.2, cy + 0.05, RZ + 0.95)], 0.035, M_BLACK)
    for z in (1.2, Z1 - 0.3):
        box(name + "_Wall_Bracket", C_CHIM, ((xend + cx) / 2, cy - 0.25, z), (abs(cx - xend), 0.05, 0.05), M_BAR)

chimney("Chimney_Left", XL, -1)
chimney("Chimney_Right", XR, 1)

# ---------------- brick UVs (box projection) ----------------
for ob in [o for o in bpy.data.objects if o.type == 'MESH' and any(m and m.name == M_BRICK.name for m in o.data.materials)]:
    me = ob.data
    uv = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        ax = max(range(3), key=lambda i: abs(poly.normal[i]))
        a, b = [(1, 2), (0, 2), (0, 1)][ax]
        for li in poly.loop_indices:
            co = ob.location + me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = (co[a] / 0.5, co[b] / 0.5)

# ---------------- finalize ----------------
dg = bpy.context.evaluated_depsgraph_get()
for ob in list(bpy.data.objects):
    if ob.type == 'CURVE':
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        new = bpy.data.objects.new(ob.name, me)
        for c in ob.users_collection:
            c.objects.link(new)
        new.matrix_world = ob.matrix_world
        bpy.data.objects.remove(ob)
dg = bpy.context.evaluated_depsgraph_get()
for ob in list(bpy.data.objects):
    if ob.type == 'MESH' and ob.modifiers:
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        ob.modifiers.clear()
        ob.data = me
for ob in list(bpy.data.objects):
    if ob.name.endswith("_hole"):
        bpy.data.objects.remove(ob)

# ---------------- scene: world, ground, sun, camera ----------------
world = bpy.data.worlds.new("World"); scene.world = world
world.use_nodes = True
bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
bg.inputs[0].default_value = (0.62, 0.72, 0.85, 1); bg.inputs[1].default_value = 1.0
gme = bpy.data.meshes.new("Ground")
bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=25); bm.to_mesh(gme); bm.free()
g = bpy.data.objects.new("Ground", gme); scene.collection.objects.link(g)
gme.materials.append(mat("Ground", (0.35, 0.32, 0.28), 0, 0.95))
sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", 'SUN'))
sun.data.energy = 4.0; sun.rotation_euler = (math.radians(55), math.radians(15), math.radians(-30))
scene.collection.objects.link(sun)
cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
scene.collection.objects.link(cam); scene.camera = cam

def aim(loc, target, lens=35):
    cam.data.lens = lens
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()

aim((-6.5, -9.0, 3.0), (0, 0, 2.2))
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "Furnace.blend"), compress=True)

for ob in bpy.data.objects:
    ob.select_set(ob.name not in ("Ground", "Camera", "Sun"))
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "Furnace.glb"), export_format='GLB', use_selection=True, export_apply=True)
bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, "Furnace.fbx"), use_selection=True, path_mode='COPY', embed_textures=True)
bpy.ops.wm.obj_export(filepath=os.path.join(OUT, "Furnace.obj"), export_selected_objects=True, path_mode='COPY')

# ---------------- previews ----------------
r = scene.render
r.resolution_x, r.resolution_y = 1280, 860
try:
    r.engine = 'BLENDER_EEVEE_NEXT'
except TypeError:
    r.engine = 'BLENDER_EEVEE'
vt = [i.identifier for i in bpy.types.ColorManagedViewSettings.bl_rna.properties['view_transform'].enum_items]
scene.view_settings.view_transform = 'AgX' if 'AgX' in vt else 'Filmic'

def shot(fname):
    r.filepath = os.path.join(OUT, fname); bpy.ops.render.render(write_still=True)

aim((0, -13.5, 2.0), (0, 0, 2.6), 32); shot("preview_front.png")
aim((-6.5, -9.0, 3.0), (0, 0, 2.2)); shot("preview_3quarter.png")
aim((8.0, 7.5, 3.0), (0, 0, 1.8)); shot("preview_back.png")
hide = list(C_ROOF.all_objects) + list(C_TOP.all_objects)
for o in hide: o.hide_render = True
aim((5.5, -7.5, 9.0), (0, 0.3, 1.2)); shot("preview_cutaway.png")
for o in hide: o.hide_render = False
print("DONE", len(bpy.data.objects), "objects")
