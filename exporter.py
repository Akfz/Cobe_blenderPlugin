import bpy
import json
import traceback
import mathutils
from bpy_extras.io_utils import ExportHelper
from .lang import t
from .utils import is_exportable_action, assign_action_to_armature
from .cobe_format import (
    collectUvsAndFaces,
    cleanList,
    cleanFloat,
    getActionFcurves,
    boneRegex,
    getBezierArgs,
    getInterpolationAtFrameCached,
    mapInterpolation,
    mapEasing,
    convertVec,
    convertQuat
)


SCALE_BASE = 16.0


def isTransformEqual(first, second, tolerance=0.001):
    if abs(first["posX"] - second["posX"]) > tolerance:
        return False
    if abs(first["posY"] - second["posY"]) > tolerance:
        return False
    if abs(first["posZ"] - second["posZ"]) > tolerance:
        return False

    if abs(first["scaleX"] - second["scaleX"]) > tolerance:
        return False
    if abs(first["scaleY"] - second["scaleY"]) > tolerance:
        return False
    if abs(first["scaleZ"] - second["scaleZ"]) > tolerance:
        return False

    dot = (
        first["rotX"] * second["rotX"] +
        first["rotY"] * second["rotY"] +
        first["rotZ"] * second["rotZ"] +
        first["rotW"] * second["rotW"]
    )

    return abs(dot) >= (1.0 - tolerance)


def isRestPose(transform, rest_loc, rest_rot, rest_scl, tolerance=0.001):
    if abs(transform["posX"] - rest_loc.x) > tolerance:
        return False
    if abs(transform["posY"] - rest_loc.y) > tolerance:
        return False
    if abs(transform["posZ"] - rest_loc.z) > tolerance:
        return False

    if abs(transform["scaleX"] - rest_scl.x) > tolerance:
        return False
    if abs(transform["scaleY"] - rest_scl.y) > tolerance:
        return False
    if abs(transform["scaleZ"] - rest_scl.z) > tolerance:
        return False

    dot = (
        transform["rotX"] * rest_rot.x +
        transform["rotY"] * rest_rot.y +
        transform["rotZ"] * rest_rot.z +
        transform["rotW"] * rest_rot.w
    )

    return abs(dot) >= (1.0 - tolerance)


def getBoneRestMatrix(arm_obj, bone_name):
    pose_bone = arm_obj.pose.bones.get(bone_name)
    default_matrix = pose_bone.bone.matrix_local if pose_bone else mathutils.Matrix.Identity(4)

    if "cobe_null_pose" in arm_obj.data:
        try:
            pose_dict = json.loads(arm_obj.data["cobe_null_pose"])
            if bone_name in pose_dict:
                flat_matrix = pose_dict[bone_name]
                return mathutils.Matrix([flat_matrix[i:i + 4] for i in range(0, 16, 4)])
        except Exception:
            pass

    return default_matrix


def applyNullPose(arm_obj):
    def apply_recursive(pose_bone):
        pose_bone.matrix = getBoneRestMatrix(arm_obj, pose_bone.name)
        for child in pose_bone.children:
            apply_recursive(child)

    for pose_bone in arm_obj.pose.bones:
        if not pose_bone.parent:
            apply_recursive(pose_bone)

    bpy.context.view_layer.update()


def savePose(arm_obj):
    saved = {}

    for pose_bone in arm_obj.pose.bones:
        saved[pose_bone.name] = (
            pose_bone.location.copy(),
            pose_bone.rotation_quaternion.copy(),
            pose_bone.rotation_euler.copy(),
            pose_bone.scale.copy(),
            pose_bone.rotation_mode
        )

    return saved


def restorePose(arm_obj, saved):
    for pose_bone in arm_obj.pose.bones:
        data = saved.get(pose_bone.name)
        if not data:
            continue

        pose_bone.rotation_mode = data[4]
        pose_bone.location = data[0]

        if data[4] == 'QUATERNION':
            pose_bone.rotation_quaternion = data[1]
        else:
            pose_bone.rotation_euler = data[2]

        pose_bone.scale = data[3]

    bpy.context.view_layer.update()


def exportMeshGeometry(obj, pose_bone, arm_obj, scale):
    mesh = obj.data
    vertices_mc = []
    is_skinned = obj.parent_type != 'BONE' and len(obj.vertex_groups) > 0

    bone_rest_matrix = arm_obj.matrix_world @ getBoneRestMatrix(arm_obj, pose_bone.name)
    bone_position = bone_rest_matrix.to_translation()
    bone_rotation = bone_rest_matrix.to_quaternion()
    arm_world_inverse = arm_obj.matrix_world.inverted()

    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_object = obj.evaluated_get(depsgraph)
    eval_mesh = eval_object.to_mesh()
    eval_world = eval_object.matrix_world

    for vertex in eval_mesh.vertices:
        world_position = eval_world @ vertex.co

        if is_skinned:
            local_position = arm_world_inverse @ world_position
        else:
            local_position = bone_rotation.inverted() @ (world_position - bone_position)

        local_position = local_position * scale
        converted = convertVec(local_position)
        vertices_mc.append([cleanFloat(converted[0]), cleanFloat(converted[1]), cleanFloat(converted[2])])

    skinning_data = []

    for vertex in mesh.vertices:
        joints = ["", "", "", ""]
        weights = [0.0, 0.0, 0.0, 0.0]

        if is_skinned:
            skin_joints = []

            for group_element in vertex.groups:
                if group_element.group < len(obj.vertex_groups):
                    group_name = obj.vertex_groups[group_element.group].name
                    if group_name in arm_obj.pose.bones:
                        skin_joints.append((group_name, group_element.weight))

            skin_joints.sort(key=lambda item: item[1], reverse=True)
            skin_joints = skin_joints[:4]

            total_weight = sum(item[1] for item in skin_joints)

            for index, (bone_name, weight) in enumerate(skin_joints):
                joints[index] = bone_name
                weights[index] = weight / total_weight if total_weight > 0.0 else 0.0

            weights = [cleanFloat(value) for value in weights]
        else:
            joints[0] = pose_bone.name
            weights[0] = 1.0

        skinning_data.append({
            "joints": joints,
            "weights": weights
        })

    unique_uvs, faces = collectUvsAndFaces(eval_mesh)
    eval_object.to_mesh_clear()

    return {
        "vertices": vertices_mc,
        "uvs": unique_uvs,
        "faces": faces,
        "skinningData": skinning_data if is_skinned else None
    }


def exportPoseBone(pose_bone, arm_obj, mesh_parent_map, scale):
    bone_rest_matrix = getBoneRestMatrix(arm_obj, pose_bone.name)
    bone_position = bone_rest_matrix.to_translation()
    bone_rotation = bone_rest_matrix.to_quaternion()
    bone_scale = bone_rest_matrix.to_scale()
    bone_tail = pose_bone.bone.tail_local

    if pose_bone.parent:
        parent_rest_matrix = getBoneRestMatrix(arm_obj, pose_bone.parent.name)
        parent_position = parent_rest_matrix.to_translation()
        parent_rotation = parent_rest_matrix.to_quaternion()

        relative_position = parent_rotation.inverted() @ (bone_position - parent_position)
        relative_tail = bone_rotation.inverted() @ (bone_tail - bone_position)
        relative_rotation = parent_rotation.inverted() @ bone_rotation
    else:
        relative_position = bone_position
        relative_tail = bone_rotation.inverted() @ (bone_tail - bone_position)
        relative_rotation = bone_rotation

    pivot = convertVec(relative_position * scale)
    pivot_end = convertVec(relative_tail * scale)
    rotation = convertQuat(relative_rotation)
    scale_mc = convertVec(bone_scale)

    meshes = []
    for mesh_obj in mesh_parent_map.get(pose_bone.name, []):
        meshes.append(exportMeshGeometry(mesh_obj, pose_bone, arm_obj, scale))

    children = []
    for child_bone in pose_bone.bone.children:
        child_pose_bone = arm_obj.pose.bones.get(child_bone.name)
        if child_pose_bone:
            children.append(exportPoseBone(child_pose_bone, arm_obj, mesh_parent_map, scale))

    return {
        "name": pose_bone.name,
        "pivot": cleanList(pivot),
        "pivotEnd": cleanList(pivot_end),
        "rotation": cleanList(rotation),
        "scale": cleanList(scale_mc),
        "renderTypes": "SOLID",
        "meshes": meshes,
        "children": children
    }


class CobeExportJson(bpy.types.Operator, ExportHelper):
    bl_idname = "cobe.export_json"
    bl_label = "Export JSON"
    filename_ext = ".json"

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("export_json")
        return True

    def execute(self, context):
        scene = context.scene
        model_name = scene.cobe_model_name
        scale = scene.cobe_scale_factor / SCALE_BASE

        texture_paths = [
            {"nameBone": item.bone_name, "location": item.texture_path}
            for item in scene.cobe_texture_paths
        ]

        arm_obj = scene.cobe_active_rig

        if not arm_obj or arm_obj.type != 'ARMATURE':
            self.report({'ERROR'}, t("select_armature"))
            return {'CANCELLED'}

        try:
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            context.view_layer.objects.active = arm_obj
        except Exception:
            pass

        mesh_parent_map = {}
        root_bone_name = next((pose_bone.name for pose_bone in arm_obj.pose.bones if not pose_bone.parent), "root")

        for obj in context.view_layer.objects:
            if obj.type != 'MESH':
                continue

            if obj.parent == arm_obj:
                if obj.parent_type == 'BONE' and obj.parent_bone:
                    mesh_parent_map.setdefault(obj.parent_bone, []).append(obj)
                else:
                    mesh_parent_map.setdefault(root_bone_name, []).append(obj)
            elif any(mod.type == 'ARMATURE' and mod.object == arm_obj for mod in obj.modifiers):
                mesh_parent_map.setdefault(root_bone_name, []).append(obj)

        original_pose_position = arm_obj.data.pose_position
        saved_pose = savePose(arm_obj)

        try:
            arm_obj.data.pose_position = 'POSE'
            applyNullPose(arm_obj)
            root_bones = [exportPoseBone(pose_bone, arm_obj, mesh_parent_map, scale) for pose_bone in arm_obj.pose.bones if not pose_bone.parent]
        except Exception as error:
            restorePose(arm_obj, saved_pose)
            arm_obj.data.pose_position = original_pose_position
            context.view_layer.update()
            self.report({'ERROR'}, str(error))
            traceback.print_exc()
            return {'CANCELLED'}

        restorePose(arm_obj, saved_pose)
        arm_obj.data.pose_position = original_pose_position
        context.view_layer.update()

        with open(self.filepath, 'w', encoding='utf-8') as file:
            json.dump({
                "loadVer": 1,
                "nameOfModel": model_name,
                "texturePaths": texture_paths,
                "bones": root_bones
            }, file, indent=4, ensure_ascii=False)

        self.report({'INFO'}, t("model_exported"))
        return {'FINISHED'}


def frame_to_ms(frame, start_frame, fps):
    return int(((frame - start_frame) / fps) * 1000)


def collect_fps_points(action, arm_obj):
    for fcurve in getActionFcurves(action, arm_obj):
        if fcurve.data_path == "cobe_anim_fps":
            points = list(fcurve.keyframe_points)
            if points:
                points.sort(key=lambda point: point.co[0])
                return points
    return None


def build_fps_keyframes(points, start_frame, base_fps, length_ms):
    if not points:
        return [{
            "startTime": 0,
            "startValue": base_fps,
            "endTime": length_ms,
            "endValue": base_fps,
            "interpolation": "LINEAR",
            "easing": "AUTOMATIC",
            "bezierArgs": None
        }]

    keyframes = []

    for index, point in enumerate(points):
        point_frame = int(round(point.co[0]))
        point_value = max(1, int(round(point.co[1])))
        start_ms = frame_to_ms(point_frame, start_frame, base_fps)

        if index + 1 < len(points):
            next_point = points[index + 1]
            end_ms = frame_to_ms(int(round(next_point.co[0])), start_frame, base_fps)
            end_value = max(1, int(round(next_point.co[1])))
        else:
            next_point = None
            end_ms = length_ms
            end_value = point_value

        interpolation = mapInterpolation(point.interpolation)
        easing = mapEasing(point.easing)

        keyframes.append({
            "startTime": start_ms,
            "startValue": point_value,
            "endTime": end_ms,
            "endValue": end_value,
            "interpolation": interpolation,
            "easing": easing,
            "bezierArgs": cleanList(getBezierArgs(point, next_point)) if interpolation == 'BEZIER' and next_point else None
        })

    return keyframes


def collectBoneKeyframes(context, arm_obj, action, fps, scale):
    fcurves = getActionFcurves(action, arm_obj)
    bone_fcurves_map = {}
    all_frames = set()

    for fcurve in fcurves:
        match = boneRegex.search(fcurve.data_path)
        if match and match.group(1) in arm_obj.pose.bones:
            bone_fcurves_map.setdefault(match.group(1), []).append(fcurve)

        if fcurve.data_path == "cobe_anim_fps":
            continue

        for key_point in fcurve.keyframe_points:
            all_frames.add(int(round(key_point.co[0])))

    if all_frames:
        sorted_frames = sorted(all_frames)
    else:
        sorted_frames = [int(action.frame_range[0]), int(action.frame_range[1])]

    start_frame = int(action.frame_range[0])
    last_key_frame = sorted_frames[-1]

    bone_poses = {pose_bone.name: [] for pose_bone in arm_obj.pose.bones}
    bone_rests = {}

    for pose_bone in arm_obj.pose.bones:
        rest_matrix = getBoneRestMatrix(arm_obj, pose_bone.name)
        bone_position = rest_matrix.to_translation()
        bone_rotation = rest_matrix.to_quaternion()
        bone_scale = rest_matrix.to_scale()

        if pose_bone.parent:
            parent_rest_matrix = getBoneRestMatrix(arm_obj, pose_bone.parent.name)
            parent_position = parent_rest_matrix.to_translation()
            parent_rotation = parent_rest_matrix.to_quaternion()

            relative_position = parent_rotation.inverted() @ (bone_position - parent_position)
            relative_rotation = parent_rotation.inverted() @ bone_rotation
        else:
            relative_position = bone_position
            relative_rotation = bone_rotation

        rest_loc = convertVec(relative_position * scale)
        rest_rot = convertQuat(relative_rotation)
        rest_scl = convertVec(bone_scale)

        bone_rests[pose_bone.name] = (
            mathutils.Vector(rest_loc),
            mathutils.Quaternion((rest_rot[3], rest_rot[0], rest_rot[1], rest_rot[2])),
            mathutils.Vector(rest_scl)
        )

    for index, frame_start in enumerate(sorted_frames):
        frame_end = sorted_frames[index + 1] if index + 1 < len(sorted_frames) else last_key_frame

        context.scene.frame_set(frame_start)
        depsgraph = context.evaluated_depsgraph_get()
        arm_eval = arm_obj.evaluated_get(depsgraph)

        start_ms = frame_to_ms(frame_start, start_frame, fps)
        end_ms = frame_to_ms(frame_end, start_frame, fps)

        for pose_bone in arm_obj.pose.bones:
            pose_bone_eval = arm_eval.pose.bones.get(pose_bone.name)
            if not pose_bone_eval:
                continue

            bone_position = pose_bone_eval.matrix.to_translation()
            bone_rotation = pose_bone_eval.matrix.to_quaternion()
            bone_scale = pose_bone_eval.matrix.to_scale()

            if pose_bone_eval.parent:
                parent_eval = arm_eval.pose.bones.get(pose_bone_eval.parent.name)
                if parent_eval:
                    parent_position = parent_eval.matrix.to_translation()
                    parent_rotation = parent_eval.matrix.to_quaternion()
                    relative_position = parent_rotation.inverted() @ (bone_position - parent_position)
                    relative_rotation = parent_rotation.inverted() @ bone_rotation
                else:
                    relative_position = bone_position
                    relative_rotation = bone_rotation
            else:
                relative_position = bone_position
                relative_rotation = bone_rotation

            loc_mc = convertVec(relative_position * scale)
            rot_mc = convertQuat(relative_rotation)
            scl_mc = convertVec(bone_scale)

            interpolation, easing, current_point, next_point = getInterpolationAtFrameCached(
                bone_fcurves_map.get(pose_bone.name),
                frame_start
            )

            bone_poses[pose_bone.name].append({
                "startValue": start_ms,
                "endValue": end_ms,
                "data": {
                    "transform": {
                        "posX": cleanFloat(loc_mc[0]),
                        "posY": cleanFloat(loc_mc[1]),
                        "posZ": cleanFloat(loc_mc[2]),
                        "rotX": cleanFloat(rot_mc[0]),
                        "rotY": cleanFloat(rot_mc[1]),
                        "rotZ": cleanFloat(rot_mc[2]),
                        "rotW": cleanFloat(rot_mc[3]),
                        "scaleX": cleanFloat(scl_mc[0]),
                        "scaleY": cleanFloat(scl_mc[1]),
                        "scaleZ": cleanFloat(scl_mc[2])
                    },
                    "interpolation": interpolation,
                    "easing": easing,
                    "bezierArgs": cleanList(getBezierArgs(current_point, next_point)) if interpolation == 'BEZIER' else None
                }
            })

    return bone_poses, bone_rests


def evaluateAction(context, arm_obj, action, speed, scale):
    base_fps = getattr(arm_obj, "cobe_anim_fps", None)
    if not base_fps:
        base_fps = getattr(action, "cobe_anim_fps", 20)
    base_fps = max(1, int(base_fps))

    start_frame = int(action.frame_range[0])
    last_frame = int(action.frame_range[1])

    if arm_obj.animation_data is None:
        arm_obj.animation_data_create()

    old_action = arm_obj.animation_data.action
    old_slot = getattr(arm_obj.animation_data, "action_slot", None)

    assign_action_to_armature(arm_obj, action)
    context.view_layer.update()

    bone_poses, bone_rests = collectBoneKeyframes(context, arm_obj, action, base_fps, scale)

    length_ms = frame_to_ms(last_frame, start_frame, base_fps)

    for keyframes in bone_poses.values():
        for keyframe in keyframes:
            if keyframe["startValue"] > length_ms:
                length_ms = keyframe["startValue"]
            if keyframe["endValue"] > length_ms:
                length_ms = keyframe["endValue"]

    length_ms = max(1, length_ms)
    bones_data = []

    for bone_name, keyframes in bone_poses.items():
        if not keyframes:
            continue

        first_transform = keyframes[0]["data"]["transform"]
        is_constant = all(isTransformEqual(keyframe["data"]["transform"], first_transform) for keyframe in keyframes)

        if is_constant:
            rest_loc, rest_rot, rest_scl = bone_rests[bone_name]
            if isRestPose(first_transform, rest_loc, rest_rot, rest_scl):
                continue

            keyframes = [{
                "startValue": 0,
                "endValue": length_ms,
                "data": {
                    "transform": first_transform,
                    "interpolation": "LINEAR",
                    "easing": "AUTOMATIC",
                    "bezierArgs": None
                }
            }]

        pose_bone = arm_obj.pose.bones.get(bone_name)
        is_deform = pose_bone.bone.cobe_is_deform if pose_bone and pose_bone.bone else True

        bones_data.append({
            "boneName": bone_name,
            "isDeform": is_deform,
            "keyframes": keyframes
        })

    arm_obj.animation_data.action = old_action
    if hasattr(arm_obj.animation_data, "action_slot"):
        try:
            arm_obj.animation_data.action_slot = old_slot
        except Exception:
            pass

    fps_points = collect_fps_points(action, arm_obj)
    fps_keyframes = build_fps_keyframes(fps_points, start_frame, base_fps, length_ms)

    return {
        "bones": bones_data,
        "name": action.name,
        "length": length_ms,
        "fps": base_fps,
        "speed": speed,
        "fpsKeyframes": fps_keyframes
    }


class CobeExportAnimationsJson(bpy.types.Operator, ExportHelper):
    bl_idname = "cobe.export_animations_json"
    bl_label = "Export Animations"
    filename_ext = ".json"

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("export_anims")
        return True

    def execute(self, context):
        try:
            scene = context.scene
            arm_obj = scene.cobe_active_rig

            if not arm_obj or arm_obj.type != 'ARMATURE':
                arm_obj = context.active_object

            if not arm_obj or arm_obj.type != 'ARMATURE':
                self.report({'ERROR'}, t("select_armature"))
                return {'CANCELLED'}

            scene.cobe_active_rig = arm_obj

            try:
                if context.mode != 'OBJECT':
                    bpy.ops.object.mode_set(mode='OBJECT')
                context.view_layer.objects.active = arm_obj
            except Exception:
                pass

            actions = [action for action in bpy.data.actions if is_exportable_action(action) and action.cobe_export_enabled]

            if not actions:
                active_action = arm_obj.animation_data.action if arm_obj.animation_data else None
                if active_action and is_exportable_action(active_action):
                    actions = [active_action]
                else:
                    named_action = bpy.data.actions.get(scene.cobe_active_action_name)
                    if named_action and is_exportable_action(named_action):
                        actions = [named_action]

            if not actions:
                self.report({'ERROR'}, t("no_active_anim"))
                return {'CANCELLED'}

            animations = []
            original_frame = scene.frame_current
            scale = scene.cobe_scale_factor / SCALE_BASE

            try:
                for action in actions:
                    animation_data = evaluateAction(context, arm_obj, action, scene.cobe_anim_speed, scale)
                    if animation_data["bones"]:
                        animations.append(animation_data)
            finally:
                scene.frame_set(original_frame)

            if not animations:
                self.report({'ERROR'}, t("select_anims"))
                return {'CANCELLED'}

            with open(self.filepath, 'w', encoding='utf-8') as file:
                json.dump({
                    "loadVer": 1,
                    "animations": animations
                }, file, indent=4, ensure_ascii=False)

            self.report({'INFO'}, t("anims_exported").format(len(animations)))
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error))
            traceback.print_exc()
            return {'CANCELLED'}


classes = (
    CobeExportJson,
    CobeExportAnimationsJson
)
