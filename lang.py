import bpy
import os
from .prefs import get_preferences, tag_redraw


class Translator:
    _instance = None

    def __init__(self):
        self.dictionary = {}
        self.availableLanguages = []
        self.defaultLanguage = "EN"
        self.current_language = "EN"

    @staticmethod
    def getInstance():
        if Translator._instance is None:
            Translator._instance = Translator()
        return Translator._instance

    def loadLanguages(self, pluginPath):
        languagesPath = os.path.join(pluginPath, "languages")
        self.dictionary.clear()
        self.availableLanguages.clear()

        if os.path.exists(languagesPath):
            for fileName in os.listdir(languagesPath):
                if fileName.endswith(".txt"):
                    languageCode = fileName.replace(".txt", "")
                    filePath = os.path.join(languagesPath, fileName)
                    data = self.parseFile(filePath)
                    if data:
                        self.dictionary[languageCode] = data
                        self.availableLanguages.append((languageCode, languageCode.upper(), ""))

        if self.defaultLanguage not in self.dictionary:
            self.dictionary[self.defaultLanguage] = {}

        if self.defaultLanguage not in [item[0] for item in self.availableLanguages]:
            self.availableLanguages.append((self.defaultLanguage, self.defaultLanguage.upper(), ""))

        if self.current_language not in self.dictionary and self.availableLanguages:
            self.current_language = self.availableLanguages[0][0]

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

    def getText(self, key, languageCode):
        if languageCode in self.dictionary:
            value = self.dictionary[languageCode].get(key)
            if value:
                return value

        if self.defaultLanguage in self.dictionary:
            value = self.dictionary[self.defaultLanguage].get(key)
            if value:
                return value

        return key


def load_translations():
    Translator.getInstance().loadLanguages(os.path.dirname(__file__))


def get_language_items(self, context):
    items = Translator.getInstance().availableLanguages
    if not items:
        return [("EN", "EN", "")]
    return items


def get_current_language_code():
    prefs = get_preferences()
    if prefs and getattr(prefs, "cobe_language", ""):
        return prefs.cobe_language
    return Translator.getInstance().current_language


def t(key):
    return Translator.getInstance().getText(key, get_current_language_code())


def update_language(self, context):
    Translator.getInstance().current_language = self.cobe_language
    tag_redraw()


class COBE_OT_SetLanguage(bpy.types.Operator):
    bl_idname = "cobe.set_language"
    bl_label = "Set Language"

    language_code: bpy.props.StringProperty()

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("set_language")
        return True

    def execute(self, context):
        prefs = get_preferences()
        if prefs:
            prefs.cobe_language = self.language_code
        else:
            Translator.getInstance().current_language = self.language_code

        tag_redraw()
        return {'FINISHED'}


class COBE_OT_ReloadLanguages(bpy.types.Operator):
    bl_idname = "cobe.reload_languages"
    bl_label = "Reload Languages"

    @classmethod
    def poll(cls, context):
        cls.bl_label = t("reload_lang")
        return True

    def execute(self, context):
        load_translations()
        tag_redraw()
        return {'FINISHED'}


load_translations()

classes = (
    COBE_OT_SetLanguage,
    COBE_OT_ReloadLanguages
)
