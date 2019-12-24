# -*- coding: utf-8 -*-
from Components.ActionMap import ActionMap
from Components.config import config, ConfigSubsection, getConfigListEntry, ConfigSelection, ConfigYesNo
from Components.ConfigList import ConfigListScreen
from Components.ServiceEventTracker import ServiceEventTracker
from Components.Sources.StaticText import StaticText
from Plugins.Plugin import PluginDescriptor
from Screens.Screen import Screen
from ServiceReference import ServiceReference
from enigma import iPlayableService, eTimer, evfd
from time import localtime, strftime, sleep
from Components.Language import language
from Tools.Directories import fileExists, pathExists, resolveFilename, SCOPE_PLUGINS, SCOPE_LANGUAGE
from translit import translify
from os import environ
from os import system
import gettext
import os

lang = language.getLanguage()
environ["LANGUAGE"] = lang[:2]
gettext.bindtextdomain("enigma2", resolveFilename(SCOPE_LANGUAGE))
gettext.textdomain("enigma2")
gettext.bindtextdomain("VFD-Icons", "%s%s" % (resolveFilename(SCOPE_PLUGINS), "SystemPlugins/VFD-Icons/locale/"))

def _(txt):
    t = gettext.dgettext("VFD-Icons", txt)
    if t == txt:
        t = gettext.gettext(txt)
    return t

config.plugins.vfdicon = ConfigSubsection()
config.plugins.vfdicon.translit = ConfigYesNo(default = True)
config.plugins.vfdicon.displayshow = ConfigSelection(default = "channel",
    choices = [("channel", _("channel name")), ("channel number", _("channel number")), ("clock", _("clock")), ("blank", _("blank"))])
config.plugins.vfdicon.stbdisplayshow = ConfigSelection(default = "clock",
    choices = [("clock", _("clock")), ("blank", _("blank"))])
config.plugins.vfdicon.stbled = ConfigSelection(default = "fp_control -l 0 1 ; fp_control -l 1 0",
    choices = [
    ("fp_control -l 0 1 ; fp_control -l 1 0", _("red")),
    ("fp_control -l 0 0 ; fp_control -l 1 1", _("green")),
    ("fp_control -l 0 1 ; fp_control -l 1 1", _("green & red")),
    ("fp_control -l 0 0 ; fp_control -l 1 0", _("blank"))])
config.plugins.vfdicon.led = ConfigSelection(default = "fp_control -l 0 0 ; fp_control -l 1 0",
    choices = [
    ("fp_control -l 0 1 ; fp_control -l 1 0", _("red")),
    ("fp_control -l 0 0 ; fp_control -l 1 1", _("green")),
    ("fp_control -l 0 1 ; fp_control -l 1 1", _("green & red")),
    ("fp_control -l 0 0 ; fp_control -l 1 0", _("blank"))])

class ConfigVFDDisplay(Screen, ConfigListScreen):
    def __init__(self, session):
        Screen.__init__(self, session)
        self.skinName = ["Setup"]
        self.setTitle(_("VFD display configuration"))
        self["key_red"] = StaticText(_("Cancel"))
        self["key_green"] = StaticText(_("OK"))
        self["actions"] = ActionMap(["SetupActions"],
            {
                "cancel": self.cancel,
                "ok": self.keySave,
                "save": self.keySave,
                "red": self.cancel,
            }, -2)

        list = []
        list.append(getConfigListEntry(_("Show on VFD display"), config.plugins.vfdicon.displayshow))
        list.append(getConfigListEntry(_("Show on VFD in standby"), config.plugins.vfdicon.stbdisplayshow))
        list.append(getConfigListEntry(_("LED on VFD display"), config.plugins.vfdicon.led))
        list.append(getConfigListEntry(_("LED on VFD in standby"), config.plugins.vfdicon.stbled))
        list.append(getConfigListEntry(_("Enable translit?"), config.plugins.vfdicon.translit))

        ConfigListScreen.__init__(self, list)

    def cancel(self):
        main(self)
        ConfigListScreen.keyCancel(self)

    def keySave(self):
        for x in self["config"].list:
            x[1].save()
        VFDpath = "/bin/"
        pluginpath = "/usr/lib/enigma2/python/Plugins/SystemPlugins/VFD-Icons/"
        os.system("cp %svdstandby %svdstandby" % (pluginpath, VFDpath))
        os.system("sed -i 's~#STB_OFF~%s~g' %svdstandby" % (config.plugins.vfdicon.led.value, VFDpath))
        os.system("sed -i 's~#STB_ON~%s~g' %svdstandby" % (config.plugins.vfdicon.stbled.value, VFDpath))
        os.system("chmod 755 /bin/vdstandby")
        os.system(" %s " % (config.plugins.vfdicon.led.value))
        main(self)
        ConfigListScreen.keySave(self)

def opencfg(session, **kwargs):
        session.open(ConfigVFDDisplay)
        evfd.getInstance().vfd_write_string( "VFD SETUP" )

def VFDdisplay(menuid, **kwargs):
    if menuid == "system":
        return [(_("VFD Display"), opencfg, "vfd_display", 44)]
    else:
        return []

class VFDIcons:
    def __init__(self, session):
        self.session = session
        self.onClose = []
        self.timer = eTimer()
        self.timer.callback.append(self.timerEvent)
        self.__event_tracker = ServiceEventTracker(screen = self,eventmap =
            {
                iPlayableService.evStart: self.WriteName,
            })

    def WriteName(self):
        if config.plugins.vfdicon.displayshow.value != "clock":
            servicename = "    "
            if config.plugins.vfdicon.displayshow.value != "blank":
                service = self.session.nav.getCurrentlyPlayingServiceOrGroup()
                if service:
                    path = service.getPath()
                    if path and not path.__contains__('://'):
                        servicename = "PLAY"
                    else:
                        if config.plugins.vfdicon.displayshow.value == "channel number":
                            servicename = str(service.getChannelNum())
                        else:
                            servicename = ServiceReference(service).getServiceName()
                            if config.plugins.vfdicon.translit.value:
                                servicename = translify(servicename)
            evfd.getInstance().vfd_write_string(servicename[0:20])

    def timerEvent(self):
        if config.plugins.vfdicon.displayshow.value == "clock":
            tm = localtime()
            servicename = strftime("%H%M", tm)
            evfd.getInstance().vfd_write_string(servicename[0:4])
            self.timer.startLongTimer(60-tm.tm_sec)

VFDIconsInstance = None

def main(session, **kwargs):
    global VFDIconsInstance
    if VFDIconsInstance is None:
        VFDIconsInstance = VFDIcons(session)
    if config.plugins.vfdicon.displayshow.value == "clock":
        sleep(1)
        VFDIconsInstance.timerEvent()
    else:
        VFDIconsInstance.WriteName()

def Plugins(**kwargs):
    return [
    PluginDescriptor(name = _("VFD Display"), description = _("VFD display config"), where = PluginDescriptor.WHERE_MENU, fnc = VFDdisplay),
    PluginDescriptor(where = PluginDescriptor.WHERE_SESSIONSTART, fnc = main )]
