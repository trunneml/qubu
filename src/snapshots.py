#!/usr/bin/python
# -*- coding: utf-8 -*-
import os
import sys
import getopt
import datetime

class Profile:
	def __init__(self, sourceDir, snapshotDir, filterFile):
		self.sourceDir = sourceDir
		self.snapshotDir = snapshotDir
		self.filterFile = filterFile
	
class Snapshots:
	def __init__(self, profile):
		self.profile = profile

	def _cleanupPath(self, path):
		return os.path.abspath(os.path.expanduser(path))

	def getLastSnapshot(self ):
		snapshotDir = self.profile.snapshotDir
		if not os.path.isdir(snapshotDir):
			return None
		# collect all snapshots in the snapshotDirectory
		snapshots = filter( lambda x: os.path.isdir(os.path.join(snapshotDir, x)), os.listdir(snapshotDir))
		snapshots.sort(None, lambda x: os.path.getctime(os.path.join(snapshotDir, x)) )
		# return latest snapshot
		if len(snapshots):
			return self._cleanupPath(os.path.join(snapshotDir,snapshots[-1]))
		return None

	def generateSnapshotID(self):
		return datetime.datetime.today().strftime( '%Y%m%d-%H%M%S' )


	def takeSnapshot(self):
		sourceDir = self._cleanupPath(self.profile.sourceDir)
		snapshotDir = self._cleanupPath(self.profile.snapshotDir)
		filterFile = self._cleanupPath(self.profile.filterFile)
		if not os.path.isdir(snapshotDir):
			raise IOError(1, "Snapshot directory %s is not a directory" % snapshotDir)
		if not os.path.isdir(sourceDir):
			raise IOError(2, "Source directory %s is not a directory" % sourceDir)
		if not os.path.isfile(filterFile):
			raise IOError(3, "Filter file %s not found" % filterFile)
		
		newSnapshot = os.path.join(snapshotDir, self.generateSnapshotID())
		tmpSnapshot = os.path.join(snapshotDir, "tmpnew")
		if os.path.exists(tmpSnapshot):
			os.system( 'rm -Rf "%s"' % tmpSnapshot)
		
		lastSnapshot = self.getLastSnapshot()
		
		os.mkdir(tmpSnapshot, 0700)
		cmd  = 'rsync -aEAXHi'
		if lastSnapshot:
			cmd += ' --link-dest="%s"' % os.path.join(lastSnapshot, "backup")
		cmd += ' --include-from="%s"' % filterFile
		cmd += ' "%s" "%s"' % (sourceDir, os.path.join(tmpSnapshot, "backup"))
		cmd += ' > %s' % os.path.join(tmpSnapshot, "rsync.log")
		rsyncReturnValue = os.system( cmd )
		if rsyncReturnValue != 0:
			raise RuntimeError(1, "rsync exit with %i exit code" % rsyncReturnValue)
		os.rename( tmpSnapshot, newSnapshot )
		return newSnapshot

if __name__ == "__main__":
	if len(sys.argv) != 4:
		sys.exit("Wrong parameter usage")
	profile = Profile(sys.argv[1], sys.argv[2], sys.argv[3])
	snap = Snapshots(profile)
	print snap.takeSnapshot()
