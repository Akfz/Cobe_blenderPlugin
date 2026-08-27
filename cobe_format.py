import re
from .utils import get_action_slot

boneRegex = re.compile(r'pose\.bones\["([^"]+)"\]')


def cleanFloat(value, decimals=4):
    rounded = round(float(value), decimals)
    return 0.0 if abs(rounded) < 1e-9 else rounded


def cleanList(values, decimals=4):
    return [cleanFloat(value, decimals) for value in values]


def convertVec(v):
    return [v[0], v[2], v[1]]


def convertQuat(q):
    return [q.x, q.z, q.y, -q.w]


def mapInterpolation(blender_interpolation):
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
    return mapping.get(blender_interpolation, 'LINEAR')


def mapEasing(blender_easing):
    mapping = {
        'AUTO': 'AUTOMATIC',
        'EASE_IN': 'EASE_IN',
        'EASE_OUT': 'EASE_OUT',
        'EASE_IN_OUT': 'EASE_IN_OUT'
    }
    return mapping.get(blender_easing, 'AUTOMATIC')


def getActionFcurves(action, arm_obj=None):
    if not hasattr(action, "layers") or not action.layers:
        return action.fcurves if hasattr(action, "fcurves") else []

    try:
        slot = None

        if arm_obj and hasattr(arm_obj, "animation_data") and arm_obj.animation_data:
            slot = getattr(arm_obj.animation_data, "action_slot", None)

        if not slot and hasattr(action, "slots") and action.slots:
            slot = get_action_slot(action, arm_obj) if arm_obj else action.slots[0]

        if not slot:
            return []

        try:
            from bpy_extras import anim_utils
            channel_bag = anim_utils.action_get_channelbag_for_slot(action, slot)
            if channel_bag and hasattr(channel_bag, "fcurves"):
                return channel_bag.fcurves
        except Exception:
            pass

        if action.layers and action.layers[0].strips:
            strip = action.layers[0].strips[0]
            channel_bag = strip.channelbag(slot)
            if channel_bag and hasattr(channel_bag, "fcurves"):
                return channel_bag.fcurves
    except Exception:
        return []

    return []


def collectUvsAndFaces(mesh):
    uv_layer = mesh.uv_layers.active.data if mesh.uv_layers.active else None
    unique_uvs = []
    uv_map = {}
    faces = []

    for poly in mesh.polygons:
        vertex_indices = list(poly.vertices)
        uv_indices = []

        for loop_index in poly.loop_indices:
            if uv_layer:
                uv = uv_layer[loop_index].uv
                uv_value = (cleanFloat(uv[0]), cleanFloat(1.0 - uv[1]))

                if uv_value not in uv_map:
                    uv_map[uv_value] = len(unique_uvs)
                    unique_uvs.append([uv_value[0], uv_value[1]])

                uv_indices.append(uv_map[uv_value])
            else:
                if (0.0, 0.0) not in uv_map:
                    uv_map[(0.0, 0.0)] = len(unique_uvs)
                    unique_uvs.append([0.0, 0.0])

                uv_indices.append(uv_map[(0.0, 0.0)])

        vertex_indices.reverse()
        uv_indices.reverse()
        faces.append({"vertexIndices": vertex_indices, "uvIndices": uv_indices})

    return unique_uvs, faces


def getInterpolationAtFrameCached(bone_fcurves, frame):
    if not bone_fcurves:
        return 'LINEAR', 'AUTOMATIC', None, None

    fcurve = bone_fcurves[0]
    key_points = fcurve.keyframe_points

    if not key_points:
        return 'LINEAR', 'AUTOMATIC', None, None

    current_point = None
    next_point = None

    for index, point in enumerate(key_points):
        point_frame = int(round(point.co[0]))

        if point_frame == frame:
            current_point = point
            if index + 1 < len(key_points):
                next_point = key_points[index + 1]
            break

        if point_frame > frame:
            if index > 0:
                current_point = key_points[index - 1]
                next_point = point
            break

    if not current_point:
        if frame < key_points[0].co[0]:
            current_point = key_points[0]
            if len(key_points) > 1:
                next_point = key_points[1]
        else:
            current_point = key_points[-1]

    if current_point:
        return mapInterpolation(current_point.interpolation), mapEasing(current_point.easing), current_point, next_point

    return 'LINEAR', 'AUTOMATIC', None, None


def getBezierArgs(current_point, next_point):
    if not current_point or not next_point:
        return [0.25, 0.25, 0.75, 0.75]

    x_current, y_current = current_point.co
    x_next, y_next = next_point.co

    dx = x_next - x_current
    dy = y_next - y_current

    if dx <= 0:
        return [0.25, 0.25, 0.75, 0.75]

    handle_right_x, handle_right_y = current_point.handle_right
    handle_left_x, handle_left_y = next_point.handle_left

    x1 = max(0.0, min(1.0, (handle_right_x - x_current) / dx))
    y1 = (handle_right_y - y_current) / dy if abs(dy) > 1e-5 else 0.0

    x2 = max(0.0, min(1.0, (handle_left_x - x_current) / dx))
    y2 = (handle_left_y - y_current) / dy if abs(dy) > 1e-5 else 0.0

    return [x1, y1, x2, y2]
