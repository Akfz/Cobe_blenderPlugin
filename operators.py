import bpy
import mathutils
from .lang import t

class COBE_OT_CreateBone(bpy.types.Operator):
    bl_idname = "cobe.create_bone"
    bl_label = "Create Bone"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("create_bone")
        return True

    def execute(self, context):
        scene = context.scene
        boneName = scene.cobe_new_bone_name if scene.cobe_new_bone_name else "bone"
        activeObj = scene.cobe_active_rig

        if activeObj and activeObj.type == 'ARMATURE':
            bpy.ops.object.mode_set(mode='EDIT')
            arm = activeObj.data
            newBone = arm.edit_bones.new(name=boneName)
            newBone.head = (0, 0, 0)
            newBone.tail = (0, 0, 1.0)
            arm.edit_bones.active = newBone
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.mode_set(mode='EDIT')
            activeObj.show_in_front = True
            activeObj.data.show_names = True
        else:
            armData = bpy.data.armatures.new(name="CobeRig")
            armObj = bpy.data.objects.new(name="CobeRig", object_data=armData)
            context.collection.objects.link(armObj)
            context.view_layer.objects.active = armObj
            bpy.ops.object.mode_set(mode='EDIT')
            rootBone = armData.edit_bones.new(name=boneName)
            rootBone.head = (0, 0, 0)
            rootBone.tail = (0, 0, 1.0)
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.mode_set(mode='EDIT')
            armObj.show_name = False
            armObj.show_in_front = True
            armObj.data.show_names = True
            scene.cobe_active_rig = armObj
            
        self.report({'INFO'}, t("bone_created").format(boneName))
        return {'FINISHED'}

class COBE_OT_CreateChildBone(bpy.types.Operator):
    bl_idname = "cobe.create_child_bone"
    bl_label = "Create Child Bone"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("create_child_bone")
        return True

    def execute(self, context):
        scene = context.scene
        boneName = scene.cobe_new_bone_name if scene.cobe_new_bone_name else "child_bone"
        activeObj = scene.cobe_active_rig

        if not activeObj or activeObj.type != 'ARMATURE':
            self.report({'ERROR'}, t("not_armature"))
            return {'CANCELLED'}

        armData = activeObj.data
        boneIndex = armData.cobe_active_bone_index
        if boneIndex < 0 or boneIndex >= len(armData.bones):
            self.report({'ERROR'}, t("select_parent"))
            return {'CANCELLED'}

        parentBoneName = armData.bones[boneIndex].name
        bpy.ops.object.mode_set(mode='EDIT')
        ebs = armData.edit_bones
        parentEb = ebs.get(parentBoneName)
        
        if not parentEb:
            bpy.ops.object.mode_set(mode='EDIT')
            self.report({'ERROR'}, t("parent_not_found"))
            return {'CANCELLED'}

        newBone = ebs.new(name=boneName)
        newBone.parent = parentEb
        newBone.head = parentEb.tail
        newBone.tail = parentEb.tail + mathutils.Vector((0, 0, 0.5))
        
        ebs.active = newBone
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.mode_set(mode='EDIT')
        self.report({'INFO'}, t("child_created").format(boneName))
        return {'FINISHED'}

class COBE_OT_DeleteBone(bpy.types.Operator):
    bl_idname = "cobe.delete_bone"
    bl_label = "Delete Bone"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("delete_bone_op")
        return True

    def execute(self, context):
        scene = context.scene
        activeObj = scene.cobe_active_rig
        if not activeObj or activeObj.type != 'ARMATURE':
            self.report({'ERROR'}, t("select_armature"))
            return {'CANCELLED'}

        armData = activeObj.data
        boneIndex = armData.cobe_active_bone_index
        if boneIndex < 0 or boneIndex >= len(armData.bones):
            self.report({'ERROR'}, t("select_bone"))
            return {'CANCELLED'}

        boneName = armData.bones[boneIndex].name
        bpy.ops.object.mode_set(mode='EDIT')
        eb = armData.edit_bones.get(boneName)
        if eb:
            armData.edit_bones.remove(eb)
            
        bpy.ops.object.mode_set(mode='POSE')
        armData.cobe_active_bone_index = max(0, boneIndex - 1)
        self.report({'INFO'}, t("bone_deleted").format(boneName))
        return {'FINISHED'}

class COBE_OT_RenameBone(bpy.types.Operator):
    bl_idname = "cobe.rename_bone"
    bl_label = "Rename Bone"
    bl_options = {'REGISTER', 'UNDO'}
    
    new_name: bpy.props.StringProperty(name="New Name")

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("rename_bone_op")
        return True

    def execute(self, context):
        scene = context.scene
        activeObj = scene.cobe_active_rig
        if not activeObj or activeObj.type != 'ARMATURE':
            self.report({'ERROR'}, t("select_armature"))
            return {'CANCELLED'}

        armData = activeObj.data
        boneIndex = armData.cobe_active_bone_index
        if boneIndex < 0 or boneIndex >= len(armData.bones):
            self.report({'ERROR'}, t("select_bone"))
            return {'CANCELLED'}

        bone = armData.bones[boneIndex]
        oldName = bone.name
        newName = self.new_name if self.new_name else scene.cobe_rename_bone_name
        if not newName:
            self.report({'ERROR'}, t("enter_new_bone"))
            return {'CANCELLED'}

        bone.name = newName
        
        for tp in scene.cobe_texture_paths:
            if tp.bone_name == oldName:
                tp.bone_name = newName

        self.report({'INFO'}, t("bone_renamed").format(oldName, newName))
        return {'FINISHED'}

    def invoke(self, context, event):
        activeObj = context.scene.cobe_active_rig
        if activeObj and activeObj.type == 'ARMATURE':
            armData = activeObj.data
            idx = armData.cobe_active_bone_index
            if 0 <= idx < len(armData.bones):
                self.new_name = armData.bones[idx].name
        return context.window_manager.invoke_props_dialog(self)

class COBE_OT_RenameRig(bpy.types.Operator):
    bl_idname = "cobe.rename_rig"
    bl_label = "Rename Rig"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("rename_rig_op")
        return True

    def execute(self, context):
        scene = context.scene
        newName = scene.cobe_rename_rig_name
        if not newName:
            self.report({'ERROR'}, t("enter_new_rig"))
            return {'CANCELLED'}

        activeObj = scene.cobe_active_rig
        if not activeObj or activeObj.type != 'ARMATURE':
            self.report({'ERROR'}, t("select_armature"))
            return {'CANCELLED'}

        activeObj.name = newName
        activeObj.data.name = newName
        self.report({'INFO'}, t("rig_renamed").format(newName))
        return {'FINISHED'}

class COBE_OT_CreateAnimation(bpy.types.Operator):
    bl_idname = "cobe.create_animation"
    bl_label = "Create Animation"
    bl_options = {'REGISTER', 'UNDO'}
    animName: bpy.props.StringProperty(default="new_animation")

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("create_anim_op")
        return True

    def execute(self, context):
        scene = context.scene
        armObj = scene.cobe_active_rig
        
        if not armObj:
            self.report({'ERROR'}, t("create_skeleton_first"))
            return {'CANCELLED'}
            
        newAction = bpy.data.actions.new(name=self.animName)
        newAction.use_fake_user = True
        
        if hasattr(newAction, "slots"):
            newAction.slots.new(id_type='OBJECT', name=armObj.name)
            
        if not armObj.animation_data:
            armObj.animation_data_create()
            
        armObj.animation_data.action = newAction
        
        if hasattr(armObj.animation_data, "action_slot") and newAction.slots:
            armObj.animation_data.action_slot = newAction.slots[0]
            
        scene.cobe_active_action_name = newAction.name
        self.report({'INFO'}, t("anim_created").format(newAction.name))
        return {'FINISHED'}
        
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

class COBE_OT_DeleteAnimation(bpy.types.Operator):
    bl_idname = "cobe.delete_animation"
    bl_label = "Delete Animation"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("delete_anim_op")
        return True

    def execute(self, context):
        scene = context.scene
        armObj = scene.cobe_active_rig
        
        if not armObj or not armObj.animation_data or not armObj.animation_data.action:
            self.report({'ERROR'}, t("no_active_anim"))
            return {'CANCELLED'}
            
        actionToDelete = armObj.animation_data.action
        actionName = actionToDelete.name
        bpy.data.actions.remove(actionToDelete)
        
        if bpy.data.actions:
            firstAction = bpy.data.actions[0]
            armObj.animation_data.action = firstAction
            if hasattr(armObj.animation_data, "action_slot") and firstAction.slots:
                armObj.animation_data.action_slot = firstAction.slots[0]
            scene.cobe_active_action_name = firstAction.name
        else:
            armObj.animation_data.action = None
            scene.cobe_active_action_name = ""
            
        self.report({'INFO'}, t("anim_deleted").format(actionName))
        return {'FINISHED'}

class COBE_OT_AutogenBones(bpy.types.Operator):
    bl_idname = "cobe.autogen_bones"
    bl_label = "Autogenerate Bones"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("autogen_op")
        return True

    def execute(self, context):
        scene = context.scene
        selectedMeshes = [o for o in context.selected_objects if o.type == 'MESH']
        
        if not selectedMeshes:
            self.report({'ERROR'}, t("select_mesh"))
            return {'CANCELLED'}
            
        armObj = scene.cobe_active_rig
                
        if not armObj:
            armData = bpy.data.armatures.new(name="CobeRig")
            armObj = bpy.data.objects.new(name="CobeRig", object_data=armData)
            context.collection.objects.link(armObj)
            armObj.show_name = False
            armObj.show_in_front = True
            armObj.data.show_names = True
            scene.cobe_active_rig = armObj
            
        armData = armObj.data
        context.view_layer.objects.active = armObj
        bpy.ops.object.mode_set(mode='EDIT')
        ebs = armData.edit_bones
        
        rootEb = ebs.get("root")
        if not rootEb:
            rootEb = ebs.new(name="root")
            rootEb.head = (0.0, 0.0, 0.0)
            rootEb.tail = (0.0, 0.0, 1.0)
        
        boneMappings = {}
        for meshObj in selectedMeshes:
            boneName = meshObj.name
            pivotBl = meshObj.matrix_world.to_translation()
            eb = ebs.new(name=boneName)
            eb.head = pivotBl
            eb.tail = pivotBl + mathutils.Vector((0, 0.2, 0))
            if rootEb and eb != rootEb:
                eb.parent = rootEb
            boneMappings[meshObj.name] = eb.name
            
        bpy.ops.object.mode_set(mode='OBJECT')
        
        for meshName, bName in boneMappings.items():
            meshObj = bpy.data.objects.get(meshName)
            if meshObj:
                matrixWorld = meshObj.matrix_world.copy()
                meshObj.parent = armObj
                meshObj.parent_type = 'BONE'
                meshObj.parent_bone = bName
                meshObj.matrix_parent_inverse = mathutils.Matrix.Identity(4)
                meshObj.matrix_world = matrixWorld
                
        self.report({'INFO'}, t("bones_created").format(len(boneMappings)))
        return {'FINISHED'}

class COBE_OT_ParentBonesToRoot(bpy.types.Operator):
    bl_idname = "cobe.parent_bones_to_root"
    bl_label = "Bind All to root"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("parent_root_op")
        return True

    def execute(self, context):
        scene = context.scene
        activeObj = scene.cobe_active_rig
        if not activeObj or activeObj.type != 'ARMATURE':
            self.report({'ERROR'}, t("select_armature"))
            return {'CANCELLED'}

        armData = activeObj.data
        bpy.ops.object.mode_set(mode='EDIT')
        ebs = armData.edit_bones
        
        rootEb = ebs.get("root")
        if not rootEb:
            rootEb = ebs.new(name="root")
            rootEb.head = (0.0, 0.0, 0.0)
            rootEb.tail = (0.0, 0.0, 1.0)
            
        count = 0
        for eb in ebs:
            if eb != rootEb and not eb.parent:
                eb.parent = rootEb
                count += 1
                
        bpy.ops.object.mode_set(mode='POSE')
        self.report({'INFO'}, t("bones_linked").format(count))
        return {'FINISHED'}

class COBE_OT_BakeBones(bpy.types.Operator):
    bl_idname = "cobe.bake_bones"
    bl_label = "Bake Physics"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("bake_op")
        return True

    def execute(self, context):
        scene = context.scene
        armObj = scene.cobe_active_rig
                
        if not armObj:
            self.report({'ERROR'}, t("select_armature"))
            return {'CANCELLED'}
            
        startFrame = scene.frame_start
        endFrame = scene.frame_end
        
        mappings = []
        for pb in armObj.pose.bones:
            meshObj = bpy.data.objects.get(pb.name)
            if meshObj and meshObj.type == 'MESH':
                mappings.append((pb, meshObj))
                
        if not mappings:
            self.report({'ERROR'}, t("no_meshes_found"))
            return {'CANCELLED'}
            
        actionName = "baked_animation"
        action = bpy.data.actions.get(actionName)
        if not action:
            action = bpy.data.actions.new(name=actionName)
            action.use_fake_user = True
            if hasattr(action, "slots"):
                action.slots.new(id_type='OBJECT', name=armObj.name)
                
        if not armObj.animation_data:
            armObj.animation_data_create()
        armObj.animation_data.action = action
        
        if hasattr(armObj.animation_data, "action_slot") and action.slots:
            armObj.animation_data.action_slot = action.slots[0]
            
        scene.cobe_active_action_name = action.name
        originalFrame = scene.frame_current
        
        for frame in range(startFrame, endFrame + 1):
            scene.frame_set(frame)
            for pb, meshObj in mappings:
                boneTargetMatrix = armObj.matrix_world.inverted() @ meshObj.matrix_world
                pb.matrix = boneTargetMatrix
                pb.keyframe_insert(data_path="location", frame=frame)
                if pb.rotation_mode == 'QUATERNION':
                    pb.keyframe_insert(data_path="rotation_quaternion", frame=frame)
                else:
                    pb.keyframe_insert(data_path="rotation_euler", frame=frame)
                pb.keyframe_insert(data_path="scale", frame=frame)
                
        scene.frame_set(originalFrame)
        self.report({'INFO'}, t("bones_baked").format(len(mappings)))
        return {'FINISHED'}

class COBE_OT_SetLanguage(bpy.types.Operator):
    bl_idname = "cobe.set_language"
    bl_label = "Set Language"
    language_code: bpy.props.StringProperty()

    def execute(self, context):
        context.scene.cobe_language = self.language_code
        for area in context.screen.areas:
            area.tag_redraw()
        return {'FINISHED'}

class COBE_OT_SetNullPose(bpy.types.Operator):
    bl_idname = "cobe.set_null_pose"
    bl_label = "Set Null Pose"

    def execute(self, context):
        armObj = context.scene.cobe_active_rig
        if not armObj:
            return {'CANCELLED'}
        poseDict = {}
        for pb in armObj.pose.bones:
            poseDict[pb.name] = [val for row in pb.matrix for val in row]
        import json
        armObj.data["cobe_null_pose"] = json.dumps(poseDict)
        for area in context.screen.areas:
            area.tag_redraw()
        return {'FINISHED'}

class COBE_OT_ClearNullPose(bpy.types.Operator):
    bl_idname = "cobe.clear_null_pose"
    bl_label = "Clear Null Pose"

    def execute(self, context):
        armObj = context.scene.cobe_active_rig
        if not armObj:
            return {'CANCELLED'}
        if "cobe_null_pose" in armObj.data:
            del armObj.data["cobe_null_pose"]
        for area in context.screen.areas:
            area.tag_redraw()
        return {'FINISHED'}