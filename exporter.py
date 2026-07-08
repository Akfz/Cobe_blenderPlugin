import bpy
import json
import traceback
import mathutils
from bpy_extras.io_utils import ExportHelper
from .lang import t
from .cobe_format import (
    collectUvsAndFaces, cleanList, cleanFloat, 
    getActionFcurves, boneRegex,
    getBezierArgs, getInterpolationAtFrameCached, TransformConverter,
    convertVec, convertQuat
)

def isTransformEqual(t1, t2, tol=0.001):
    """Сравнение двух матриц трансформаций кости"""
    if abs(t1["posX"] - t2["posX"]) > tol or abs(t1["posY"] - t2["posY"]) > tol or abs(t1["posZ"] - t2["posZ"]) > tol: 
        return False
    if abs(t1["scaleX"] - t2["scaleX"]) > tol or abs(t1["scaleY"] - t2["scaleY"]) > tol or abs(t1["scaleZ"] - t2["scaleZ"]) > tol: 
        return False
    dot = (t1["rotX"]*t2["rotX"] + t1["rotY"]*t2["rotY"] + t1["rotZ"]*t2["rotZ"] + t1["rotW"]*t2["rotW"])
    if abs(dot) < (1.0 - tol): 
        return False
    return True

def isRestPose(tVal, rest_loc, rest_rot, rest_scl, tol=0.001):
    """Проверка, совпадает ли поза с базовой позой покоя"""
    if abs(tVal["posX"] - rest_loc.x) > tol or abs(tVal["posY"] - rest_loc.y) > tol or abs(tVal["posZ"] - rest_loc.z) > tol: 
        return False
    if abs(tVal["scaleX"] - rest_scl.x) > tol or abs(tVal["scaleY"] - rest_scl.y) > tol or abs(tVal["scaleZ"] - rest_scl.z) > tol: 
        return False
    dot = (tVal["rotX"]*rest_rot.x + tVal["rotY"]*rest_rot.y + tVal["rotZ"]*rest_rot.z + tVal["rotW"]*rest_rot.w)
    if abs(dot) < (1.0 - tol): 
        return False
    return True

def getBoneRestMatrix(armObj, boneName):
    """Считывание сохраненной матрицы базовой позы Null (T) Pose"""
    armData = armObj.data
    pose_bone = armObj.pose.bones.get(boneName)
    defaultMatrix = pose_bone.bone.matrix_local if pose_bone else mathutils.Matrix.Identity(4)
    if "cobe_null_pose" in armData:
        try:
            poseDict = json.loads(armData["cobe_null_pose"])
            if boneName in poseDict:
                flatList = poseDict[boneName]
                return mathutils.Matrix([flatList[i:i+4] for i in range(0, 16, 4)])
        except Exception:
            pass
    return defaultMatrix

def exportMeshGeometry(obj, poseBone, armObj, scale):
    """Рассчитывает координаты вершин и веса скиннинга меша"""
    mesh = obj.data
    verticesMc = []
    objRestWorldBl = obj.matrix_world
    
    is_skinned = obj.parent_type != 'BONE' and len(obj.vertex_groups) > 0
    
    boneRestMat = armObj.matrix_world @ getBoneRestMatrix(armObj, poseBone.name)
    bonePosBl = boneRestMat.to_translation()
    boneRotBl = boneRestMat.to_quaternion()
    
    armWorldInv = armObj.matrix_world.inverted()

    for v in mesh.vertices:
        vWorldRestBl = objRestWorldBl @ v.co
        
        if is_skinned:
            vLocalBl = armWorldInv @ vWorldRestBl
        else:
            vLocalBl = boneRotBl.inverted() @ (vWorldRestBl - bonePosBl)
            
        vLocalMc = convertVec(vLocalBl)
        verticesMc.append([cleanFloat(vLocalMc[0]), cleanFloat(vLocalMc[1]), cleanFloat(vLocalMc[2])])
        
    skinning_list = []
    for v in mesh.vertices:
        joints = ["", "", "", ""]
        weights = [0.0, 0.0, 0.0, 0.0]
        
        if is_skinned:
            skin_joints = []
            for g in v.groups:
                group_name = obj.vertex_groups[g.group].name
                if group_name in armObj.pose.bones:
                    skin_joints.append((group_name, g.weight))
            
            skin_joints.sort(key=lambda x: x[1], reverse=True)
            skin_joints = skin_joints[:4]
            
            total_w = sum(x[1] for x in skin_joints)
            for idx, (b_name, w) in enumerate(skin_joints):
                joints[idx] = b_name
                weights[idx] = w / total_w if total_w > 0.0 else 0.0
                
            weights = [cleanFloat(x) for x in weights]
        else:
            joints[0] = poseBone.name
            weights[0] = 1.0
            
        skinning_list.append({
            "joints": joints,
            "weights": weights
        })
        
    uniqueUvs, faces = collectUvsAndFaces(mesh)
    return {
        "vertices": verticesMc, 
        "uvs": uniqueUvs, 
        "faces": faces,
        "skinningData": skinning_list if is_skinned else None
    }

def exportPoseBone(poseBone, armObj, scale, meshParentMap):
    """Экспортирует кость покоя с её мешами, пивотами и дочерними костями"""
    boneRestMat = getBoneRestMatrix(armObj, poseBone.name)
    bonePosBl = boneRestMat.to_translation()
    boneRotBl = boneRestMat.to_quaternion()
    boneSclBl = boneRestMat.to_scale()
    
    boneTailBl = poseBone.bone.tail_local

    if poseBone.parent:
        parentRestMat = getBoneRestMatrix(armObj, poseBone.parent.name)
        parentPosBl = parentRestMat.to_translation()
        parentRotBl = parentRestMat.to_quaternion()
        
        relPosBl = parentRotBl.inverted() @ (bonePosBl - parentPosBl)
        relTailBl = boneRotBl.inverted() @ (boneTailBl - bonePosBl)
        relRotBl = parentRotBl.inverted() @ boneRotBl
    else:
        relPosBl = bonePosBl
        relTailBl = boneRotBl.inverted() @ (boneTailBl - bonePosBl)
        relRotBl = boneRotBl
        
    pivotMc = convertVec(relPosBl)
    pivotEndMc = convertVec(relTailBl)
    rotationMc = convertQuat(relRotBl)
    scaleMc = convertVec(boneSclBl)
    
    render_type = poseBone.bone.cobe_render_type if hasattr(poseBone.bone, "cobe_render_type") else "SOLID"
    
    meshes, children = [], []
    for meshObj in meshParentMap.get(poseBone.name, []):
        meshes.append(exportMeshGeometry(meshObj, poseBone, armObj, scale))
                    
    for childBone in poseBone.bone.children:
        childPb = armObj.pose.bones.get(childBone.name)
        if childPb: 
            children.append(exportPoseBone(childPb, armObj, scale, meshParentMap))
        
    return {
        "name": poseBone.name,
        "pivot": cleanList(pivotMc),
        "pivotEnd": cleanList(pivotEndMc),
        "rotation": cleanList(rotationMc),
        "scale": cleanList(scaleMc),
        "renderTypes": render_type,
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
        print("[Cobe Debug] === ЗАПУСК АБСОЛЮТНОГО ЭКСПОРТА МОДЕЛИ ===")
        scale = context.scene.cobe_scale_factor
        model_name = context.scene.cobe_model_name 
        texturePaths = [{"nameBone": tp.bone_name, "location": tp.texture_path} for tp in context.scene.cobe_texture_paths]
            
        armObj = context.scene.cobe_active_rig
        if not armObj: 
            return {'CANCELLED'}
        
        meshParentMap = {}
        root_bone = next((b.name for b in armObj.pose.bones if not b.parent), "root")
        
        for obj in context.view_layer.objects:
            if obj.type == 'MESH':
                if obj.parent == armObj:
                    if obj.parent_type == 'BONE' and obj.parent_bone:
                        meshParentMap.setdefault(obj.parent_bone, []).append(obj)
                    else:
                        meshParentMap.setdefault(root_bone, []).append(obj)
                elif any(mod.type == 'ARMATURE' and mod.object == armObj for mod in obj.modifiers):
                    meshParentMap.setdefault(root_bone, []).append(obj)
     
        original_pose = armObj.data.pose_position
        armObj.data.pose_position = 'REST'
        context.view_layer.update()

        rootBones = [exportPoseBone(pb, armObj, scale, meshParentMap) for pb in armObj.pose.bones if not pb.parent]

        armObj.data.pose_position = original_pose
        context.view_layer.update()

        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump({"loadVer": 1, "nameOfModel": model_name, "texturePaths": texturePaths, "bones": rootBones}, f, indent=4, ensure_ascii=False)
        self.report({'INFO'}, t("model_exported"))
        return {'FINISHED'}

def collectBoneKeyframes(context, armObj, action, scale, fps):
    """Собирает ключевые кадры анимации и рассчитывает локальные относительные позы"""
    fcurves = getActionFcurves(action, armObj)
    boneFcurvesMap, allFrames = {}, set()
    for fcurve in fcurves:
        match = boneRegex.search(fcurve.data_path)
        if match and match.group(1) in armObj.pose.bones:
            boneFcurvesMap.setdefault(match.group(1), []).append(fcurve)
            for kp in fcurve.keyframe_points: 
                allFrames.add(int(round(kp.co[0])))
                
    sortedFrames = sorted(list(allFrames)) if allFrames else [int(action.frame_range[0]), int(action.frame_range[1])]
    startFrame = int(action.frame_range[0])
    bonePoses = {pb.name: [] for pb in armObj.pose.bones}
    boneRests = {}
    
    for pb in armObj.pose.bones:
        restMat = getBoneRestMatrix(armObj, pb.name)
        bonePosBl = restMat.to_translation()
        boneRotBl = restMat.to_quaternion()
        boneSclBl = restMat.to_scale()
        
        if pb.parent:
            parentRestMat = getBoneRestMatrix(armObj, pb.parent.name)
            parentPosBl = parentRestMat.to_translation()
            parentRotBl = parentRestMat.to_quaternion()
            
            relPosBl = parentRotBl.inverted() @ (bonePosBl - parentPosBl)
            relRotBl = parentRotBl.inverted() @ boneRotBl
        else:
            relPosBl = bonePosBl
            relRotBl = boneRotBl
            
        rest_loc = convertVec(relPosBl)
        rest_rot = convertQuat(relRotBl)
        rest_scl = convertVec(boneSclBl)
        
        boneRests[pb.name] = (
            mathutils.Vector(rest_loc),
            mathutils.Quaternion((rest_rot[3], rest_rot[0], rest_rot[1], rest_rot[2])),
            mathutils.Vector(rest_scl)
        )
        
    for i in range(len(sortedFrames)):
        fStart = sortedFrames[i]
        fEnd = sortedFrames[i+1] if (i + 1 < len(sortedFrames)) else int(action.frame_range[1])
        context.scene.frame_set(fStart)
        depsgraph = context.evaluated_depsgraph_get()
        armEval = armObj.evaluated_get(depsgraph)
        
        startMs = int(((fStart - startFrame) / fps) * 1000)
        endMs = int(((fEnd - startFrame) / fps) * 1000)
        
        for pb in armObj.pose.bones:
            pbEval = armEval.pose.bones.get(pb.name)
            
            bonePosBl = pbEval.matrix.to_translation()
            boneRotBl = pbEval.matrix.to_quaternion()
            boneSclBl = pbEval.matrix.to_scale()
            
            if pbEval.parent:
                parentEval = armEval.pose.bones.get(pbEval.parent.name)
                parentPosBl = parentEval.matrix.to_translation()
                parentRotBl = parentEval.matrix.to_quaternion()
                
                relPosBl = parentRotBl.inverted() @ (bonePosBl - parentPosBl)
                relRotBl = parentRotBl.inverted() @ boneRotBl
            else:
                relPosBl = bonePosBl
                relRotBl = boneRotBl
                
            locMc = convertVec(relPosBl)
            rotMc = convertQuat(relRotBl)
            sclMc = convertVec(boneSclBl)

            interpType, easingType, kpCurr, kpNext = getInterpolationAtFrameCached(boneFcurvesMap.get(pb.name), fStart)
            
            bonePoses[pb.name].append({
                "startValue": startMs, "endValue": endMs,
                "data": {
                    "transform": {
                        "posX": cleanFloat(locMc[0]), "posY": cleanFloat(locMc[1]), "posZ": cleanFloat(locMc[2]),
                        "rotX": cleanFloat(rotMc[0]), "rotY": cleanFloat(rotMc[1]), "rotZ": cleanFloat(rotMc[2]), "rotW": cleanFloat(rotMc[3]),
                        "scaleX": cleanFloat(sclMc[0]), "scaleY": cleanFloat(sclMc[1]), "scaleZ": cleanFloat(sclMc[2])
                    },
                    "interpolation": interpType,
                    "easing": easingType, 
                    "bezierArgs": cleanList(getBezierArgs(kpCurr, kpNext)) if interpType == 'BEZIER' else None
                }
            })
    return bonePoses, boneRests

def evaluateAction(context, armObj, action, scale, fps, speed):
    """Оценка и расчет кадров выбранной анимации"""
    if armObj.animation_data is None: 
        armObj.animation_data_create()
    oldAction = armObj.animation_data.action
    oldSlot = getattr(armObj.animation_data, "action_slot", None)
    
    armObj.animation_data.action = action
    
    if hasattr(armObj.animation_data, "action_slot") and hasattr(action, "slots") and action.slots:
        slot = None
        for s in action.slots:
            name_to_check = getattr(s, "name_display", getattr(s, "identifier", ""))
            if name_to_check == armObj.name or name_to_check.endswith(armObj.name):
                slot = s
                break
        if not slot:
            slot = action.slots[0]
        armObj.animation_data.action_slot = slot
        
    context.view_layer.update()
    lengthMs = int(((int(action.frame_range[1]) - int(action.frame_range[0])) / fps) * 1000)
    bonesDataJson = []
    
    bonePoses, boneRests = collectBoneKeyframes(context, armObj, action, scale, fps)
    
    for pbName, keyframes in bonePoses.items():
        if not keyframes: 
            continue
        
        isConstant = all(isTransformEqual(kf["data"]["transform"], keyframes[0]["data"]["transform"]) for kf in keyframes)
        
        if isConstant:
            tVal = keyframes[0]["data"]["transform"]
            rest_loc, rest_rot, rest_scl = boneRests[pbName]
            
            if isRestPose(tVal, rest_loc, rest_rot, rest_scl):
                continue
            keyframes = [{"startValue": 0, "endValue": lengthMs, "data": {"transform": tVal, "interpolation": "LINEAR", "easing": "AUTOMATIC", "bezierArgs": None}}]
            
        pb = armObj.pose.bones.get(pbName)
        is_deform = pb.bone.cobe_is_deform if (pb and pb.bone) else True
            
        bonesDataJson.append({
            "boneName": pbName, 
            "isDeform": is_deform,
            "keyframes": keyframes
        })
        
    armObj.animation_data.action = oldAction
    if hasattr(armObj.animation_data, "action_slot"): 
        armObj.animation_data.action_slot = oldSlot
    
    return {"bones": bonesDataJson, "name": action.name, "length": lengthMs, "fps": fps, "speed": speed}

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
            print("[Cobe Debug] === ЗАПУСК АБСОЛЮТНОГО ЭКСПОРТА АНИМАЦИЙ ===")
            scene = context.scene
            armObj = scene.cobe_active_rig
            if not armObj: 
                self.report({'ERROR'}, "Select an Armature first!")
                return {'CANCELLED'}
                
            actions = [a for a in bpy.data.actions if a.cobe_export_enabled]
            
            if not actions:
                active_action = armObj.animation_data.action if armObj.animation_data else None
                if active_action:
                    actions = [active_action]
                    self.report({'INFO'}, f"No actions checked. Automatically exporting active action: '{active_action.name}'")
            
            if not actions:
                self.report({'ERROR'}, "No animations checked in Cobe Settings, and no active animation assigned to the armature.")
                return {'CANCELLED'}
                
            animationsList = []
            origFrame = scene.frame_current
            
            for action in actions:
                animData = evaluateAction(context, armObj, action, scene.cobe_scale_factor, scene.cobe_anim_fps, scene.cobe_anim_speed)
                if animData["bones"]: 
                    animationsList.append(animData)
                    
            scene.frame_set(origFrame)
            if not animationsList: 
                self.report({'ERROR'}, "Selected animations do not contain any bone movement keyframes.")
                return {'CANCELLED'}
                
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump({"loadVer": 1, "animations": animationsList}, f, indent=4, ensure_ascii=False)
            self.report({'INFO'}, t("anims_exported").format(len(animationsList)))
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {str(e)}")
            traceback.print_exc()
            return {'CANCELLED'}