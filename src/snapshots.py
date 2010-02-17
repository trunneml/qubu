#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import with_statement # This isn't required in Python 2.6
import os
import sys
import getopt
import datetime

import bz2
import pwd
import grp



def cleanupPath( path):
	return os.path.abspath(os.path.expanduser(path))

class FilterFileError(Exception):
	def __init__(self, value):
		self.value = value
	def __str__(self):
		return repr(self.value)

class Profile:
	def __init__(self, filterFile):
		self.filterFile = filterFile
		if not os.path.isfile(self.filterFile):
			raise IOError(3, "Filter file %s not found" % self.filterFile)
		with open(filterFile, "r") as ff:
			sourceLine = ff.readline()
			snapshotLine = ff.readline()
		
		if sourceLine[0] != "#":
			raise FilterFileError('First line must be an source directory line')
		if snapshotLine[0] != "#":
			raise FilterFileError('Second line must be an source directory line')
		self.sourceDirectory = sourceLine[1:].strip()
		self.snapshotDirectory = snapshotLine[1:].strip()
		

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
	FILEINFO = "fileinfo.bz2"
	RSYNCFILTERFILE = "rsync.rules"

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

	def _getCurrentInfo( self, path ):
		sourceDir = self.profile.sourceDirectory
		path = os.path.join( sourceDir, path)
		try:
			info = os.stat( path )
			user = '-'
			group = '-'

			try:
				user = pwd.getpwuid( info.st_uid ).pw_name
			except:
				pass
			try:
				group = grp.getgrgid( info.st_gid ).gr_name
			except:
				pass

			return  ( info.st_mode, user, group)
		except:
			return None

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
		
		# Save permissions of all files
		self.saveCurrentFileInfo(tmpSnapshot)
		
		# Save a copy of the filterFile
		cmd = "cp %s %s" % (filterFile, os.path.join(tmpSnapshot, self.RSYNCFILTERFILE))
		os.system( cmd )
		
		# Rename TMP folder to realname
		os.rename( tmpSnapshot, newSnapshot )
		# Return path to new snapshot
		return newSnapshot

	def saveCurrentFileInfo(self, snapshotPath):
		fileinfo = bz2.BZ2File( os.path.join(snapshotPath, self.FILEINFO), 'w' )
		for path, dirs, files in os.walk( os.path.join(snapshotPath, self.BACKUPDIR) ):
			dirs.extend( files )
			for item in dirs:
				item_path = os.path.join( path, item )[ len( os.path.join(snapshotPath, self.BACKUPDIR) ) : ]
				if item_path[0] == "/":
					item_path = item_path[1:]
				info = self._getCurrentInfo( item_path )
				if info:
					fileinfo.write("%s %s %s %s\n" % ( info[0], info[1], info[2], item_path ))
		fileinfo.close()

if __name__ == "__main__":
	if len(sys.argv) != 2:
		sys.exit("Wrong parameter usage")
	profile = Profile(sys.argv[1])
	snap = Snapshots(profile)
	print snap.takeSnapshot()

