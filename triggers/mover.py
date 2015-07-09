import os, re, glob

def insensitive_glob(pattern):
    def either(c):
        return '[%s%s]'%(c.lower(),c.upper()) if c.isalpha() else c
    return glob.glob(''.join(map(either,pattern)))

class MoverTrigger:
	def __init__(self, config):
		self._selector = re.compile(config['selector'], re.UNICODE)
		self._target = config['target']
		self._options = config.get('options', {})
		self._debug = config.get('debug', False)

	def on_finished(self, f):
		m = self._selector.match(f._filename)
		if m:
			target = self._target.format(*m.groups())
			if not os.path.isdir(target) and self._options.get('insensitive', False):
				targets = insensitive_glob(target)
				target = targets[0] if targets else target

			if not os.path.isdir(target) and self._options.get('create', False):
				if self._debug:
					print("Creating %s" % (target,))
				os.makedirs(target)

			if os.path.isdir(target):
				f.move(target)
				return True
		return False

module = {
    "name" : "MoverTrigger",
    "class" : MoverTrigger
}

import unittest
import tempfile
import random
import shutil

class FakeFile:
		def __init__(self, target, filename):
			self._target = target
			self._filename = filename

		def path(self):
			return os.path.join(self._target, self._filename)

		def create(self):
			self._fd = open(self.path(), "w+")
			self._fd.write(''.join([chr(random.randint(0, 255)) for i in range(0, 1024)]))
			self._fd.close()

		def move(self, target):
			p1 = os.path.join(self._target, self._filename)
			p2 = os.path.join(target, self._filename)
			os.rename(p1, p2)

class TestMoverTrigger(unittest.TestCase):
	def setUp(self):
		self._target = tempfile.mkdtemp()

	def tearDown(self):
		shutil.rmtree(self._target)

	def test_no_move(self):
		subdir = 'Halt.and.Catch.Fire'
		name = 'Halt.and.Catch.Fire.S02E01.PROPER.HDTV.x264-KILLERS.mp4'
		config = {
			"selector" : "(.*)\\.S[0-9]+E[0-9]+(-E[0-9]+)?\\..*",
			"target" : os.path.join(self._target, "{0}"),
		}
		f = FakeFile(self._target, name)
		f.create()
		self.assertEqual(os.path.isfile(f.path()), True)
		mover = MoverTrigger(config)
		self.assertEqual(mover.on_finished(f), False)
		self.assertEqual(os.path.isfile(os.path.join(self._target, subdir, name)), False)

	def test_simple_move(self):
		subdir = 'Halt.and.Catch.Fire'
		name = 'Halt.and.Catch.Fire.S02E01.PROPER.HDTV.x264-KILLERS.mp4'
		os.mkdir(os.path.join(self._target, subdir))
		config = {
			"selector" : "(.*)\\.S[0-9]+E[0-9]+(-E[0-9]+)?\\..*",
			"target" : os.path.join(self._target, "{0}"),
		}
		f = FakeFile(self._target, name)
		f.create()
		self.assertEqual(os.path.isfile(f.path()), True)
		mover = MoverTrigger(config)
		self.assertEqual(mover.on_finished(f), True)
		self.assertEqual(os.path.isfile(os.path.join(self._target, subdir, name)), True)

	def test_insensitive_move(self):
		subdir = 'Halt.and.Catch.Fire'
		name = 'Halt.And.Catch.Fire.S02E01.PROPER.HDTV.x264-KILLERS.mp4'
		os.mkdir(os.path.join(self._target, subdir))
		config = {
			"selector" : "(.*)\\.S[0-9]+E[0-9]+(-E[0-9]+)?\\..*",
			"target" : os.path.join(self._target, "{0}"),
			"options" : {
				"insensitive" : True
			}
		}
		f = FakeFile(self._target, name)
		f.create()
		self.assertEqual(os.path.isfile(f.path()), True)
		mover = MoverTrigger(config)
		self.assertEqual(mover.on_finished(f), True)
		self.assertEqual(os.path.isfile(os.path.join(self._target, subdir, name)), True)

	def test_simple_move_ceate(self):
		subdir = 'Halt.and.Catch.Fire'
		name = 'Halt.and.Catch.Fire.S02E01.PROPER.HDTV.x264-KILLERS.mp4'
		config = {
			"selector" : "(.*)\\.S[0-9]+E[0-9]+(-E[0-9]+)?\\..*",
			"target" : os.path.join(self._target, "{0}"),
			"options" : {
				"create": True
			}
		}
		f = FakeFile(self._target, name)
		f.create()
		self.assertEqual(os.path.isfile(f.path()), True)
		mover = MoverTrigger(config)
		self.assertEqual(mover.on_finished(f), True)
		self.assertEqual(os.path.isfile(os.path.join(self._target, subdir, name)), True)

	def test_insensitive_move_ceate(self):
		subdir = 'Halt.and.Catch.Fire'
		name = 'Halt.and.Catch.Fire.S02E01.PROPER.HDTV.x264-KILLERS.mp4'
		config = {
			"selector" : "(.*)\\.S[0-9]+E[0-9]+(-E[0-9]+)?\\..*",
			"target" : os.path.join(self._target, "{0}"),
			"options" : {
				"create": True,
				"insensitive" : True
			}
		}
		f = FakeFile(self._target, name)
		f.create()
		self.assertEqual(os.path.isfile(f.path()), True)
		mover = MoverTrigger(config)
		self.assertEqual(mover.on_finished(f), True)
		self.assertEqual(os.path.isfile(os.path.join(self._target, subdir, name)), True)

if __name__ == "__main__":
	unittest.main()