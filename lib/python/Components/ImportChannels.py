import threading, urllib2, os, shutil, tempfile
from json import loads
from enigma import eDVBDB, eEPGCache
from Screens.MessageBox import MessageBox
from Tools import Notifications
from twisted.web.http_headers import Headers
from base64 import encodestring
import xml.etree.ElementTree as et

SETTINGFILES = ('lamedb', 'bouquets.', 'userbouquet.', 'blacklist', 'whitelist', 'alternatives.')
TMPDIR = "/tmp/.importchannels"

class Import:
	isRunning = False

class ImportChannels():
	def __init__(self):
		if config.usage.remote_fallback_enabled.value and config.usage.remote_fallback_import.value and config.usage.remote_fallback.value and not Import.isRunning:
			Import.isRunning = True
			self.headers = {}
			if config.usage.remote_fallback_enabled.value and config.usage.remote_fallback_import.value and config.usage.remote_fallback_import_url.value != "same" and config.usage.remote_fallback_import_url.value:
				self.url = config.usage.remote_fallback_import_url.value.rsplit(":", 1)[0]
			else:
				self.url = config.usage.remote_fallback.value.rsplit(":", 1)[0]
			if config.usage.remote_fallback_openwebif_customize.value:
				self.url = "%s:%s" % (self.url, config.usage.remote_fallback_openwebif_port.value)
				if config.usage.remote_fallback_openwebif_userid.value and config.usage.remote_fallback_openwebif_password.value:
					self.header = "Basic %s" % encodestring("%s:%s" % (config.usage.remote_fallback_openwebif_userid.value, config.usage.remote_fallback_openwebif_password.value)).strip()
			self.thread = threading.Thread(target=self.threaded_function, name="ChannelsImport")
			self.thread.start()

	def getUrl(self, url, timeout=5):
		request = urllib2.Request(url)
		if self.header:
			request.add_header("Authorization", self.header)
		return urllib2.urlopen(request, timeout=timeout)

	def getTerrestrialUrl(self):
		url = config.usage.remote_fallback_dvb_t.value
		return url[:url.rfind(":")] if url else self.url

	def getFallbackSettings(self):
		return self.getUrl("%s/web/settings" % self.getTerrestrialUrl()).read()

	def getFallbackSettingsValue(self, settings, e2settingname):
		root = et.fromstring(settings)
		for e2setting in root:
			if e2settingname in e2setting[0].text:
				return e2setting[1].text
		return ""

	def getTerrestrialRegion(self, settings):
		description = ""
		descr = self.getFallbackSettingsValue(settings, ".terrestrial")
		if "Europe" in descr:
			description = "fallback DVB-T/T2 Europe"
		if "Australia" in descr:
			description = "fallback DVB-T/T2 Australia"
		config.usage.remote_fallback_dvbt_region.value = description

	def threaded_function(self):
		settings = self.getFallbackSettings()
		self.getTerrestrialRegion(settings)
		self.tmp_dir = tempfile.mkdtemp(prefix="ImportChannels")
		if "epg" in config.usage.remote_fallback_import.value:
			print "Writing epg.dat file on sever box"
			try:
				self.getUrl("%s/web/saveepg" % self.url, timeout=30).read()
			except:
				self.ImportChannelsDone(False, _("Error when writing epg.dat on server"))
				return
			print "[Import Channels] Get EPG Location"
			try:
				epgdatfile = self.getFallbackSettingsValue(settings, "config.misc.epgcache_filename") or "/hdd/epg.dat"
				try:
					files = [file for file in loads(self.getUrl("%s/file?dir=%s" % (self.url, os.path.dirname(epgdatfile))).read())["files"] if os.path.basename(file).startswith(os.path.basename(epgdatfile))]
				except:
					files = [file for file in loads(self.getUrl("%s/file?dir=/" % self.url).read())["files"] if os.path.basename(file).startswith("epg.dat")]
				epg_location = files[0] if files else None
			except:
				self.ImportChannelsDone(False, _("Error while retreiving location of epg.dat on server"))
				return
			if epg_location:
				print "[Import Channels] Copy EPG file..."
				try:
					open(os.path.join(self.tmp_dir, "epg.dat"), "wb").write(self.getUrl("%s/file?file=%s" % (self.url, epg_location)).read())
					shutil.move(os.path.join(self.tmp_dir, "epg.dat"), config.misc.epgcache_filename.value)
				except:
					self.ImportChannelsDone(False, _("Error while retreiving epg.dat from server"))
					return
			else:
				self.startDownloadSettings()

	def setMessage(self, message):
		self.message = _(message)
		print "[ImportChannels] %s" % message

	def getUrl(self, url, timeout=5):
		from twisted.web.client import getPage
		self.setMessage("getting url %s/%s" % (self.url, url))
		return getPage("%s/%s" % (self.url, url), headers=self.headers, timeout=timeout)

	def downloadUrl(self, url, file, timeout=5):
		from twisted.web.client import downloadPage
		self.setMessage("downloading %s/%s" % (self.url, url))
		return downloadPage("%s/%s" % (self.url, url.encode("utf-8")), file.encode("utf-8"), headers=self.headers, timeout=timeout)

	def saveEpgCallback(self, data):
		if xml.etree.cElementTree.fromstring(data).find("e2state").text == "True":
			self.getUrl("file?file=/etc/enigma2/settings").addCallback(self.getSettingsCallback).addErrback(self.endFallback)
		else:
			self.endFallback()

	def getSettingsCallback(self, data):
		self.epgdatfile = [x for x in data if x.startswith('config.misc.epgcache_filename=')]
		self.epgdatfile = self.epgdatfile and self.epgdatfile[0].split('=')[1].strip() or "/hdd/epg.dat"
		self.getUrl("file?dir=%s" % os.path.dirname(self.epgdatfile)).addCallback(self.getEPGDatLocationFallback).addErrback(self.getEPGDatLocationError)

	def getEPGDatLocationError(self, message=None):
		self.getUrl("file?dir=/").addCallback(self.getEPGDatLocationFallback).addErrback(self.endFallback)

	def getEPGDatLocationFallback(self, data):
		files = [file for file in loads(data)["files"] if os.path.basename(file).startswith(os.path.basename(self.epgdatfile))]
		if files:
			self.downloadUrl("file?file=%s" % files[0], os.path.join(TMPDIR, "epg.dat")).addCallback(self.EPGDatDownloadedCallback).addErrback(self.endFallback)
		elif os.path.dirname(self.epgdatfile) != os.sep:
			self.epgdatfile = "/epg.dat"
			self.getEPGDatLocationError()
		else:
			self.endFallback(_("Could not locate epg file on fallback tuner"))

	def EPGDatDownloadedCallback(self, data=None):
		destination = config.misc.epgcache_filename.value if os.path.isdir(os.path.dirname(config.misc.epgcache_filename.value)) else "/epg.dat"
		shutil.move(os.path.join(TMPDIR, "epg.dat"), destination)
		self.startDownloadSettings()

	def startDownloadSettings(self):
		if "channels" in config.usage.remote_fallback_import.value:
			print "[Import Channels] reading dir"
			try:
				files = [file for file in loads(self.getUrl("%s/file?dir=/etc/enigma2" % self.url).read())["files"] if os.path.basename(file).startswith(settingfiles)]
				for file in files:
					file = file.encode("UTF-8")
					print "[Import Channels] Downloading %s" % file
					try:
						open(os.path.join(self.tmp_dir, os.path.basename(file)), "wb").write(self.getUrl("%s/file?file=%s" % (self.url, file)).read())
					except:
						self.ImportChannelsDone(False, _("ERROR downloading file %s") % file)
						return
			except:
				self.ImportChannelsDone(False, _("Error %s") % self.url)
				return
			print "[Import Channels] Removing files..."
			files = [file for file in os.listdir("/etc/enigma2") if file.startswith(settingfiles)]
			for file in files:
				os.remove(os.path.join("/etc/enigma2", file))
			print "[Import Channels] copying files..."
			files = [x for x in os.listdir(self.tmp_dir) if x.startswith(settingfiles)]
			for file in files:
				shutil.move(os.path.join(self.tmp_dir, file), os.path.join("/etc/enigma2", file))
		self.ImportChannelsDone(True, {"channels": _("Channels"), "epg": _("EPG"), "channels_epg": _("Channels and EPG")}[config.usage.remote_fallback_import.value])

	def ImportChannelsDone(self, flag, message=None):
		shutil.rmtree(self.tmp_dir, True)
		if flag:
			Notifications.AddNotificationWithID("ChannelsImportOK", MessageBox, _("%s imported from fallback tuner") % message, type=MessageBox.TYPE_INFO, timeout=5)
		else:
			message = {"channels": _("Channels"), "epg": _("EPG"), "channels_epg": _("Channels and EPG")}[config.usage.remote_fallback_import.value]
			Notifications.AddNotificationWithID("ChannelsImportOK", MessageBox, _("%s imported from fallback tuner") % message, MessageBox.TYPE_INFO, timeout=5)
		if os.path.isdir(TMPDIR):
			os.rmdir(TMPDIR)
		Import.isRunning = False
