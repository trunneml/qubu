#!/usr/bin/python
# -*- coding: utf-8 -*-
import os
import sys
import getopt
import datetime

def cleanupPath( path):
	return os.path.abspath(os.path.expanduser(path))

class Profile:
	def __init__(self, sourceDir, snapshotDir, filterFile):
		self.sourceDirectory = sourceDir
		self.snapshotDirectory = snapshotDir
		self.filterFile = filterFile
	
	_sourceDirectory = None
	def getSourceDirectory(self):
		return cleanupPath(self._sourceDirectory)
	def setSourceDirectory(self,sourceDirectory):
		self._sourceDirectory = sourceDirectory
	sourceDir = property(getSourceDirectory, setSourceDirectory)
	
	_snapshotDirectory = None
	def getSnapshotDirectory(self):
		return cleanupPath(self._snapshotDirectory)
	def setSnapshotDirectory(self, snapshotDir):
		self._snapshotDirectory = snapshotDir
	snapshotDirectory = property(getSnapshotDirectory, setSnapshotDirectory)
	
	_filterFile = None
	def getFilterFile(self):
		return cleanupPath(self._filterFile)
	def setFilterFile(self, filterFile):
		self._filterFile = filterFile
	filterFile = property(getFilterFile, setFilterFile)
	

class Snapshots:

	RSYNCLOG = "rsync.log"
	BACKUPDIR = "backup"

	def __init__(self, profile):
		self.profile = profile

	def getLastSnapshot(self ):
		snapshotDir = self.profile.snapshotDirectory
		if not os.path.isdir(self.profile.snapshotDirectory):
			raise IOError(1, "Snapshot directory %s is not a directory" % snapshotDir)
		# collect all snapshots in the snapshotDirectory
		snapshots = filter( lambda x: os.path.isdir(os.path.join(snapshotDir, x)), os.listdir(snapshotDir))
		snapshots.sort(None, lambda x: os.path.getctime(os.path.join(snapshotDir, x)) )
		# return latest snapshot
		if len(snapshots):
			return cleanupPath(os.path.join(snapshotDir,snapshots[-1]))
		return None

	def generateSnapshotID(self):
		return datetime.datetime.today().strftime( '%Y%m%d-%H%M%S' )


	def takeSnapshot(self):
		snapshotDir = self.profile.snapshotDirectory
		sourceDir = self.profile.sourceDirectory
		filterFile = self.profile.filterFile
		
		# Proof profile settings
		if not os.path.isdir(snapshotDir):
			raise IOError(1, "Snapshot directory %s is not a directory" % snapshotDir)
		if not os.path.isdir(sourceDir):
			raise IOError(2, "Source directory %s is not a directory" % sourceDir)
		if not os.path.isfile(filterFile):
			raise IOError(3, "Filter file %s not found" % filterFile)
		
		# Define folder names for tmp dir and new snapshot
		newSnapshot = os.path.join(snapshotDir, self.generateSnapshotID())
		tmpSnapshot = os.path.join(snapshotDir, "tmpnew")
		if os.path.exists(tmpSnapshot):
			os.system( 'rm -Rf "%s"' % tmpSnapshot)
		
		lastSnapshot = self.getLastSnapshot()
		
		# Create TMP Folder for new Snapshot
		os.mkdir(tmpSnapshot, 0700)
		
		# Create Rsync CMD
		cmd  = 'rsync -aEAXHi'
		if lastSnapshot:
			cmd += ' --link-dest="%s"' % os.path.join(lastSnapshot, self.BACKUPDIR)
		cmd += ' --include-from="%s"' % filterFile
		cmd += ' "%s" "%s"' % (sourceDir, os.path.join(tmpSnapshot, self.BACKUPDIR))
		cmd += ' > %s' % os.path.join(tmpSnapshot, self.RSYNCLOG)
		# Run RSYNC and proof return value
		rsyncReturnValue = os.system( cmd )
		if rsyncReturnValue != 0:
			raise RuntimeError(1, "rsync exit with %i exit code" % rsyncReturnValue)
		
		# Rename TMP folder to realname
		os.rename( tmpSnapshot, newSnapshot )
		# Return path to new snapshot
		return newSnapshot

if __name__ == "__main__":
	if len(sys.argv) != 4:
		sys.exit("Wrong parameter usage")
	profile = Profile(sys.argv[1], sys.argv[2], sys.argv[3])
	snap = Snapshots(profile)
	print snap.takeSnapshot()

