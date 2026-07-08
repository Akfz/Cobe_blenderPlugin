import bpy
import os

class Translator:
    _instance = None

    def __init__(self):
        self.dictionary = {}
        self.availableLanguages = []
        self.defaultLanguage = "EN"

    @staticmethod
    def getInstance():
        if Translator._instance is None:
            Translator._instance = Translator()
        return Translator._instance

    def loadLanguages(self, pluginPath):
        languagesPath = os.path.join(pluginPath, "languages")
        if not os.path.exists(languagesPath):
            try:
                os.makedirs(languagesPath)
            except Exception:
                pass

        self.dictionary.clear()
        self.availableLanguages.clear()

        if os.path.exists(languagesPath):
            for fileName in os.listdir(languagesPath):
                if fileName.endswith(".txt"):
                    languageCode = fileName.replace(".txt", "")
                    filePath = os.path.join(languagesPath, fileName)
                    try:
                        self.dictionary[languageCode] = self.parseFile(filePath)
                        self.availableLanguages.append((languageCode, languageCode.upper(), ""))
                    except Exception:
                        pass

        if not self.availableLanguages:
            self.availableLanguages.append((self.defaultLanguage, self.defaultLanguage.upper(), ""))

    def parseFile(self, filePath):
        parsedData = {}
        try:
            with open(filePath, "r", encoding="utf-8") as file:
                for line in file:
                    cleanedLine = line.strip()
                    if cleanedLine and "=" in cleanedLine and not cleanedLine.startswith("#"):
                        key, value = cleanedLine.split("=", 1)
                        parsedData[key.strip()] = value.strip()
        except Exception:
            pass
        return parsedData

    def getText(self, key, currentLanguage):
        if currentLanguage in self.dictionary:
            val = self.dictionary[currentLanguage].get(key)
            if val:
                return val
        if self.defaultLanguage in self.dictionary:
            val = self.dictionary[self.defaultLanguage].get(key)
            if val:
                return val
        return key

def getLanguageItems(self, context):
    items = Translator.getInstance().availableLanguages
    if not items:
        return [("EN", "EN", "")]
    return items

def t(key):
    currentLanguage = "EN"
    if hasattr(bpy.context, "scene") and bpy.context.scene and hasattr(bpy.context.scene, "cobe_language"):
        currentLanguage = bpy.context.scene.cobe_language
    return Translator.getInstance().getText(key, currentLanguage)

def updateLanguage(self, context):
    for area in context.screen.areas:
        area.tag_redraw()

class CobeReloadLanguages(bpy.types.Operator):
    bl_idname = "cobe.reload_languages"
    bl_label = "Reload Languages"
    
    def execute(self, context):
        Translator.getInstance().loadLanguages(os.path.dirname(__file__))
        updateLanguage(self, context)
        return {'FINISHED'}

def register():
    Translator.getInstance().loadLanguages(os.path.dirname(__file__))
    bpy.utils.register_class(CobeReloadLanguages)

def unregister():
    bpy.utils.unregister_class(CobeReloadLanguages)