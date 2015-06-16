# twisted imports
from twisted.web.server import Site
from twisted.web.resource import Resource, NoResource, getChildForRequest
from twisted.web.util import redirectTo
from twisted.internet import reactor, task, defer
from twisted.python import log
from twisted.web.static import File

# system imports
import time
import sys
import json
import urlparse
import tempfile
import os
import re
import datetime
import urllib
import string

# template imports
import jinja2

class RequestRedirection(Exception):
    pass

class FileState:
    states = ["WAITING", "REQUESTED", "DOWNLOADING", "FINISHED", "ERROR"]

    def __init__(self):
    	self._status = 0

    def status(self):
    	return self._status

    def __str__(self):
    	return self.states[self._status]

    def set(self, status):
    	self._status = self.states.index(status)

    def equal(self, state):
    	return self._status == self.states.index(state)

    def active(self):
    	return self.equal('REQUESTED') or self.equal('DOWNLOADING')

	def __repr__(self):
		return ("<%s at %x: %s>" % (self.__class__, id(self), self.status()))

class DownloaderFile:
	def __init__(self, manager, url, name = '', filename = '', size = None, temp = False):
		self._manager = manager
		self._name = name
		self._filename = filename
		self._module, self._url = url.encode('ascii').split(':', 1)
		self._received = 0
		if size:
			self._size = self.parse_size(size)
		else:
			self._size = None
		self._temp = temp
		self._download_time = None
		self._success = None
		self._error = None
		self._start_time = 0.0
		self._end_time = 0.0
		self._good = False
		self._active = False
		self._state = FileState()

	def open(self, filename  = ''):
		if filename:
			self._filename = filename
		else:
			self._filename = self._name
		if self._temp:
			self._fd = tempfile.NamedTemporaryFile(delete = False)
		else:
			self._manager.active.files.append(self)
			self._fd = open(self._filename, 'wb')
		self.state().set("DOWNLOADING")
		return self

	def write(self, data):
		self._fd.write(data)
		self._received += len(data)

	def close(self):
		self._fd.close()

	def download(self, success = None, error = None):
		self._good = False
		self._success = success
		self._error = error
		self._start_time = time.time()
		self._active = True
		self.state().set("REQUESTED")
		self._deferred = self._manager.enabled[self._module].download(self)
		self._deferred.addCallback(self.success).addErrback(self.error)

	def success(self, d):
		print('success')
		self._active = False
		self._good = True
		self._end_time = time.time()
		self.state().set("FINISHED")
		if callable(self._success):
			self._success(d)

	def error(self, d):
		print('error: %s' % (d,))
		self._active = False
		self._good = False
		self._end_time = time.time()
		self.state().set("ERROR")
		if callable(self._error):
			self._error(d)

	def active(self):
		return self._active

	def good(self):
		return self._good

	def url(self):
		return self._url

	def state(self):
		return self._state

	def progress(self):
		if not self._size:
			return 0
		return int(100.0 * self._received / self._size)

	def size_fmt(self, suffix='B'):
		num = self._size
		for unit in ['','Ki','Mi','Gi','Ti','Pi','Ei','Zi']:
			if abs(num) < 1024.0:
				return "%3.1f%s%s" % (num, unit, suffix)
			num /= 1024.0
		return "%.1f%s%s" % (num, 'Yi', suffix)

	def parse_size(self, str):
		int_part = ''
		while str and str[0] in string.digits:
			int_part += str[0]
			str = str[1:]
		if str and str[0] == '.':
			int_part += str[0]
			str = str[1:]
			while str and str[0] in string.digits:
				int_part += str[0]
				str = str[1:]
		print(int_part)
		size = float(int_part)
		unite = {
			'kio' : 2**10, 'mio' : 2**20, 'gio' : 2**30, 'tio' : 2**40, 'pio' : 2**50, 'eio' : 2**60, 'zio' : 2**70,
			'ko' : 10**3, 'mo' : 10**6, 'go' : 10**9, 'to' : 10**12, 'po' : 10**15, 'eo' : 10**18, 'zo' : 10**21,
		}
		if str:
			print(str)
			if str.lower() in unite:
				size *= unite[str.lower()]
			else:
				size *= unite[str.lower()+'o']
		return int(size)

class DownloaderSource:
	files = []

	def __init__(self, manager, name, config):
		self._manager = manager
		self._name = name
		self._file = DownloaderFile(self._manager, config['source'], temp = True)
		self._refresh = config.get('refresh', 0.0)
		self._pattern = config['pattern']
		self._re_pattern = re.compile(self._pattern, re.UNICODE)
		self._url = config['url']
		self._filename = config.get('filename', '')
		self._filesize = config.get('filesize', '')
		self._task = None
		self.refresh_loop()

	def refresh_loop(self):
		if self._task:
			self._task.stop()
			self._task = None
		if self._refresh > 0.0:
			self._task = task.LoopingCall(self.refresh)
			self._task.start(int(self._refresh*60), now = True)
		else:
			self.refresh()

	def refresh(self):
		self._file.download(self.success, self.error)

	def success(self, d):
		fd = open(self._file._fd.name)
		self.data = fd.read()
		fd.close()
		os.remove(self._file._fd.name)
		
		config = {}
		files = []
		for match in self._re_pattern.findall(self.data):
			match = [m.decode('utf-8') for m in match]
			print('match:',match)
			print('replace:',self.replace(self._url, match))
			url = self.replace(self._url, match).encode('ascii')
			print(url)
			config['name'] = self.replace(self._filename, match)
			if self._filesize:
				config['size'] = self.replace(self._filesize, match)
			print(config)
			files.append(DownloaderFile(self._manager, url, **config))
		self.files = files

	def error(self, d):
		print('error: ' + str(d))

	def replace(self, param, match):
		for i in range(0, len(match)):
			param = param.replace('$%d$' % (i,), match[i])
		return param

	def last_update(self):
		return datetime.datetime.fromtimestamp(self._file._end_time)

	def name(self):
		return self._name

	def render(self, path):
		print(path)
		if len(path) > 0:
			if path[0] == 'download':
				try:
					self.files[int(path[1])].download()
				except ValueError,IndexError:
					pass
			elif path == ['refresh']:
				print('Refreshing:',self.state().status())
				if not self.state().active():
					self.refresh_loop()
				raise RequestRedirection('/source/' + urllib.quote(self.name()) + '/')
		return self._manager.jinja.get_template('source.html').render(app=self._manager, source=self)

	def state(self):
		return self._file.state()

class ActiveSource(DownloaderSource):
	def __init__(self):
		self._name = 'Active Downloads'

	def last_update(self):
		return datetime.datetime.fromtimestamp(time.time())

class Downloader(Resource):
	modules = {}
	schemes = {}
	sources = {}
	active = ActiveSource()
	#isLeaf = True

	@classmethod
	def register(cls, name, module):
		if name in cls.modules:
			raise KeyError('Module %s is already registered' % (module,))
		cls.modules[name] = module

	def __init__(self, config = {}):
		print('Downloader.__init__')
		Resource.__init__(self)
		self.jinja = jinja2.Environment(loader=jinja2.FileSystemLoader('.'))
		self.enabled = {}
		if 'modules' in config:
			for module in config['modules']:
				self.enable(module.encode('ascii'), config['modules'][module])
				print(module.encode('ascii'))
				#self.putChild(module.encode('ascii'), self.enabled[module.encode('ascii')])
		#self.putChild('module', self)
		self.putChild("static", File("static"))

		if 'sources' in config:
			for source in config['sources']:
				self.sources[source] = DownloaderSource(self, source, config['sources'][source])
		print(self.sources)

	def enable(self, name, config):
		if name in self.enabled:
			raise KeyError('Module %s is already enabled' % (module,))
		self.enabled[name] = self.modules[name](self, config)

	def getChildForLeafRequest(self, request):
		self.isLeaf = False
		child = getChildForRequest(self, request)
		self.isLeaf = True
		return child

	def getChild(self, path, request):
		return self

	def render(self, request):
		#request.setHeader("Content-Type", "text/plain; charset=utf-8")
		content = ''
		try:
			if len(request.prepath) >= 2 and request.prepath[0] == 'module' and request.prepath[1] in self.enabled:
				module = request.prepath[1]
				path = request.prepath[2:]

				if path == ['schemes']:
					return json.dumps(self.enabled[module].schemes())
				else:
					content = self.enabled[module].render(path) + '\n'
			elif len(request.prepath) >= 2 and request.prepath[0] == 'source' and request.prepath[1] in self.sources:
				content = self.sources[request.prepath[1]].render(request.prepath[2:])
			elif request.prepath == ['download']:
				content = self.jinja.get_template('download.html').render(app=self)
			elif request.prepath[0:1] == ['sources']:
				for source in self.sources:
					content += self.jinja.get_template('source.html').render(app=self, source=self.sources[source])
			elif request.prepath == ['active']:
				return self.jinja.get_template('file_list.html').render(app=self, source=self.active).encode('utf-8')
			else:
				content = self.jinja.get_template('active.html').render(app=self, source=self.active)
		except RequestRedirection as e:
			url = e.args[0]
			return redirectTo(url.encode('ascii'), request)
		#child = self.getChildForLeafRequest(request)
		#print(repr(child))
		#return html+child.render(request)
		m = self.jinja.get_template('index.html')
		return m.render(app=self, content=content).encode('utf-8')

from modules.irc import XdccDownloader
from modules.http import HttpDownloader
from modules.local import LocalDownloader
from modules.fake import FakeDownloader

Downloader.register(XdccDownloader.name, XdccDownloader)
Downloader.register(HttpDownloader.name, HttpDownloader)
Downloader.register(LocalDownloader.name, LocalDownloader)
Downloader.register(FakeDownloader.name, FakeDownloader)

if __name__ == '__main__':
	# initialize logging
	log.startLogging(sys.stdout)
	
	# create factory protocol and application
	config = json.load(open('config.json'))
	web_factory = Site(Downloader(config))

	reactor.listenTCP(config["web"]["port"], web_factory)

	# run bot
	reactor.run()