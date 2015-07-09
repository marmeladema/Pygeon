from twisted.web import client
from twisted.internet import reactor

import urlparse

class LocalDownloader(object):
	def __init__(self, manager, config):
		self.manager = manager

	def schemes(self):
		return ['file']

	def download(self, url, fd):
		print('Downloading: %s' % (url,))
		parsed_url = urlparse.urlparse(url)
		factory = client.HTTPDownloader(url, fd)
		if ':' in parsed_url.netloc:
			host, port = parsed_url.netloc.split(':')
			port = int(port)
		else:
			host, port = parsed_url.netloc, 80
		reactor.connectTCP(host, port, factory)
		return factory.deferred

module = {
    "name" : "LocalDownloader",
    "class" : LocalDownloader
}