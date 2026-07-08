import bpy
import math
import mathutils
import re

boneRegex = re.compile(r'pose\.bones\["([^"]+)"\]')

def cleanFloat(val, decimals=4):
    rounded = round(float(val), decimals)
    return 0.0 if abs(rounded) < 1e-9 else rounded

def cleanList(lst, decimals=4):
    return [cleanFloat(x, decimals) for x in lst]

def convertVec(v):
    """Прямой и понятный перевод вектора: x -> x, y -> z, z -> y"""
    return [v[0], v[2], v[1]]

def convertQuat(q):
    """Конвертация кватерниона со сменой осей Y и Z и инверсией W"""
    return [q.x, q.z, q.y, -q.w]

class TransformConverter:
    @staticmethod
    def convertTranslation(vec, scale=1.0):
        return convertVec(vec)

    @staticmethod
    def convertTranslationMcToBl(vec, scale=1.0):
        return [vec[0], vec[2], vec[1]]

def mapInterpolation(bl_interp):
    """Сопоставляет типы интерполяции Blender с Java-Enum InterpolationType"""
    mapping = {
        'CONSTANT': 'STEP',
        'LINEAR': 'LINEAR',
        'BEZIER': 'BEZIER',
        'SINE': 'SINUSOIDAL',
        'QUAD': 'QUADRATIC',
        'CUBIC': 'CUBIC',
        'QUART': 'QUARTIC',
        'QUINT': 'QUINTIC',
        'EXPO': 'EXPONENTIAL',
        'CIRC': 'CIRCULAR',
        'BACK': 'BACK',
        'BOUNCE': 'BOUNCE',
        'ELASTIC': 'ELASTIC'
    }
    return mapping.get(bl_interp, 'LINEAR')

def mapEasing(bl_easing):
    """Сопоставляет типы затухания Blender с Java-Enum Easing"""
    mapping = {
        'AUTO': 'AUTOMATIC',
        'EASE_IN': 'EASE_IN',
        'EASE_OUT': 'EASE_OUT',
        'EASE_IN_OUT': 'EASE_IN_OUT'
    }
    return mapping.get(bl_easing, 'AUTOMATIC')

def getActionFcurves(action, armObj=None):
    """Безопасно извлекает F-Curves для Blender <4.4 и Blender 5.0+ / 5.1"""
    if not hasattr(action, "layers") or not action.layers:
        return action.fcurves if hasattr(action, "fcurves") else []
        
    try:
        slot = None
        if armObj and hasattr(armObj, "animation_data") and armObj.animation_data:
            slot = getattr(armObj.animation_data, "action_slot", None)
            
        if not slot and hasattr(action, "slots") and action.slots:
            slot = action.slots[0]
            
        if not slot:
            return []
            
        try:
            from bpy_extras import anim_utils
            cb = anim_utils.action_get_channelbag_for_slot(action, slot)
            if cb and hasattr(cb, "fcurves"):
                return cb.fcurves
        except Exception:
            pass
            
        if action.layers and action.layers[0].strips:
            strip = action.layers[0].strips[0]
            cb = strip.channelbag(slot)
            if cb and hasattr(cb, "fcurves"):
                return cb.fcurves
    except Exception as e:
        print(f"[Cobe] Warning: Failed to extract fcurves for action '{action.name}': {e}")
        
    return []

def collectUvsAndFaces(mesh):
    """Собирает уникальные UV-координаты и полигоны меша"""
    uvLayer = mesh.uv_layers.active.data if mesh.uv_layers.active else None
    uniqueUvs = []
    uvMap = {}
    faces = []
    
    for poly in mesh.polygons:
        vertexIndices = list(poly.vertices)
        uvIndices = []
        for loopIdx in poly.loop_indices:
            if uvLayer:
                uv = uvLayer[loopIdx].uv
                uvVal = (cleanFloat(uv[0]), cleanFloat(1.0 - uv[1]))
                if uvVal not in uvMap:
                    uvMap[uvVal] = len(uniqueUvs)
                    uniqueUvs.append([uvVal[0], uvVal[1]])
                uvIndices.append(uvMap[uvVal])
            else:
                if (0.0, 0.0) not in uvMap:
                    uvMap[(0.0, 0.0)] = len(uniqueUvs)
                    uniqueUvs.append([0.0, 0.0])
                uvIndices.append(uvMap[(0.0, 0.0)])
                
        vertexIndices.reverse()
        uvIndices.reverse()
                
        faces.append({"vertexIndices": vertexIndices, "uvIndices": uvIndices})
    return uniqueUvs, faces

def getInterpolationAtFrameCached(boneFcurves, frame):
    """Определяет тип интерполяции и затухания для ключевого кадра"""
    if not boneFcurves: 
        return 'LINEAR', 'AUTOMATIC', None, None
    fcurve = boneFcurves[0]
    kps = fcurve.keyframe_points
    if not kps: 
        return 'LINEAR', 'AUTOMATIC', None, None
        
    kpCurr, kpNext = None, None
    for i, kp in enumerate(kps):
        kpFrame = int(round(kp.co[0]))
        if kpFrame == frame:
            kpCurr = kp
            if i + 1 < len(kps): kpNext = kps[i+1]
            break
        elif kpFrame > frame:
            if i > 0:
                kpCurr = fcurve.keyframe_points[i-1]
                kpNext = kp
            break
            
    if not kpCurr and len(kps) > 0:
        if frame < fcurve.keyframe_points[0].co[0]:
            kpCurr = fcurve.keyframe_points[0]
            if len(kps) > 1: kpNext = fcurve.keyframe_points[1]
        else:
            kpCurr = fcurve.keyframe_points[-1]
            
    if kpCurr:
        interp = mapInterpolation(kpCurr.interpolation)
        easing = mapEasing(kpCurr.easing)
        return interp, easing, kpCurr, kpNext
    return 'LINEAR', 'AUTOMATIC', None, None

def getBezierArgs(kpCurr, kpNext):
    """Вычисляет аргументы кривой Безье для интерполяции ключевого кадра"""
    if not kpCurr or not kpNext: return [0.25, 0.25, 0.75, 0.75]
    xCurr, yCurr = kpCurr.co
    xNext, yNext = kpNext.co
    dx, dy = xNext - xCurr, yNext - yCurr
    if dx <= 0: return [0.25, 0.25, 0.75, 0.75]
        
    hrX, hrY = kpCurr.handle_right
    hlX, hlY = kpNext.handle_left
    
    x1 = max(0.0, min(1.0, (hrX - xCurr) / dx))
    y1 = (hrY - yCurr) / dy if abs(dy) > 1e-5 else 0.0
    x2 = max(0.0, min(1.0, (hlX - xCurr) / dx))
    y2 = (hlY - yCurr) / dy if abs(dy) > 1e-5 else 0.0
    return [x1, y1, x2, y2]