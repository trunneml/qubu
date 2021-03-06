#!/usr/bin/python2
# -*- coding: utf-8 -*-

# QUBU -- Quick user backup
# Copyright (C) 2009 Michael Trunner
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from __future__ import with_statement # This isn't required in Python 2.6
import os
import subprocess
import sys
import getopt
import datetime

# To improve usability on the console
import optparse
import logging

# Needed to save file permissions
import bz2
import pwd
import grp

# Make some fancy PopUps under KDE4 and Gnome
import dbus

# Needed for removing old Snapshots
import time
import datetime

logger = None
notify = None
appName = "qubu"

def cleanupPath( path):
	return os.path.abspath(os.path.expanduser(path))

class Notify:

	STARTBACKUP = 1
	STOPBACKUP = 2
	TIMEOUT = 5000
	
	def __init__(self):
		try:
			if "DISPLAY" not in os.environ:
				os.environ["DISPLAY"] = ":0"
			self.notifyDbus = dbus.SessionBus().get_object("org.freedesktop.Notifications", "/org/freedesktop/Notifications")
		except:
			self.notifyDbus = None

	def notify(self, eventType, msg):
		headline = ""
		if not self.notifyDbus:
			return False
		headline = ""
		hints = {"category" : "transfer"}
		if eventType == self.STARTBACKUP:
			hints = {"category" : "transfer", "urgency" : 0}
		elif eventType == self.STOPBACKUP:
			hints = {"category" : "transfer.complete", "urgency" : 0}
		#self.notifyDbus.Notify("noteer", 0, "document-save", "Headline", m, [], {"category" : "transfer" }, 0, dbus_interface='org.freedesktop.Notifications')
		return self.notifyDbus.Notify(appName, 0, "document-save", headline, msg, [], hints, self.TIMEOUT, dbus_interface='org.freedesktop.Notifications')

class FilterFileError(Exception):
	def __init__(self, value):
		self.value = value
	def __str__(self):
		return repr(self.value)

class RsyncError(Exception):
	def __init__(self, returnValue):
		self.exitCode = returnValue
	def __str__(self):
		return "RSYNC exit code was %i" % self.exitCode

class Profile:
	def __init__(self, filterFile):
		logger.info("Loading qubu filter file")
		self.filterFile = filterFile
		if not os.path.isfile(self.filterFile):
			raise IOError(3, "Filter file %s not found" % self.filterFile)
		with open(filterFile, "r") as ff:
			sourceLine = ff.readline()
			snapshotLine = ff.readline()
			rsyncCMDLine = ff.readline()
		
		if sourceLine[0] != "#":
			raise FilterFileError('First line must be an source directory line')
		if snapshotLine[0] != "#":
			raise FilterFileError('Second line must be an snapshot directory line')
		self.sourceDirectory = sourceLine[1:].strip()
		logger.info("Setting source directory to: %s" % self.sourceDirectory)
		self.snapshotDirectory = snapshotLine[1:].strip()
		logger.info("Setting snapshot directory to: %s" % self.snapshotDirectory)
		self.rsyncCMD = "rsync -aEAXH"
		if rsyncCMDLine[0] == "#":
			self.rsyncCMD = rsyncCMDLine[1:].strip()

	def __str__(self):
		return os.path.split(self.filterFile)[1]
		

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

	RSYNCLOG    = "rsync.log"
	RSYNCOUTPUT = "rsync.out"
	BACKUPDIR   = "backup"
	FILEINFO    = "fileinfo.bz2"
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
			snap = cleanupPath(os.path.join(snapshotDir,snapshots[-1]))
			logger.info("Latest snapshot found in: %s" % snap)
			return snap
		logger.warn("No snapshot found in snapshot directory (%s)" % snapshotDir)
		return None

	def generateSnapshotID(self):
		return datetime.datetime.today().strftime( '%Y%m%d-%H%M%S' )

	def takeSnapshot(self):
		snapshotDir = self.profile.snapshotDirectory
		sourceDir = self.profile.sourceDirectory
		filterFile = self.profile.filterFile
		rsyncCMD = self.profile.rsyncCMD
		
		logger.info("Checking snapshot configuration of profile %s" % self.profile)
		# Proof profile settings
		if not os.path.isdir(snapshotDir):
			raise IOError(1, 'Snapshot directory "%s" is not a directory' % snapshotDir)
		if not os.path.isdir(sourceDir):
			raise IOError(2, 'Source directory "%s" is not a directory' % sourceDir)
		if not os.path.isfile(filterFile):
			raise IOError(3, 'Filter file "%s" not found' % filterFile)
		
		# RSYNC behaves different with a / at the end of the source folder
		if sourceDir[-1] != "/":
			sourceDir += "/"
		notify.notify(Notify.STARTBACKUP, "Starting Backup with profile %s" % self.profile)
		
		# Define folder names for tmp dir and new snapshot
		snapshotID = self.generateSnapshotID()
		newSnapshot = os.path.join(snapshotDir, snapshotID)
		tmpSnapshot = os.path.join(snapshotDir, "tmpnew")
		if os.path.exists(tmpSnapshot):
			logger.warn("Found tmp folder! Maybe backup is already running")
			notify.notify(Notify.STOPBACKUP, "TEMP-Folder found for profile %s. No backup was taken!" % self.profile)
			return False
		
		lastSnapshot = self.getLastSnapshot()
		
		# Create TMP Folder for new Snapshot
		logger.info("Creating tmp folder for snapshot")
		os.mkdir(tmpSnapshot, 0700)
		
		# Create Rsync CMD
		logger.info("Starting rsync")
		cmd  = '%s --stats' % rsyncCMD
		if lastSnapshot:
			cmd += ' --link-dest="%s"' % os.path.join(lastSnapshot, self.BACKUPDIR)
		cmd += ' --include-from="%s"' % filterFile
		cmd += ' --log-file="%s"' % os.path.join(tmpSnapshot, self.RSYNCLOG)
		cmd += ' "%s" "%s"' % (sourceDir, cleanupPath(os.path.join(tmpSnapshot, self.BACKUPDIR)))
		cmd += ' > %s' % os.path.join(tmpSnapshot, self.RSYNCOUTPUT)
		# Run RSYNC and proof return value
		logger.debug( "Running command: %s" % cmd) 
		rsyncReturnValue = subprocess.call( cmd, shell=True )
		if rsyncReturnValue not in [0,24]:
			cmd = 'rm -Rf %s' % tmpSnapshot
			logger.debug( "Running command: %s" % cmd) 
			os.system( cmd )
			raise RsyncError(rsyncReturnValue)
		
		# Save a copy of the filterFile
		logger.info("Copy qubu filter file")
		cmd = "cp %s %s" % (filterFile, os.path.join(tmpSnapshot, self.RSYNCFILTERFILE))
		logger.debug( "Running command: %s" % cmd) 
		os.system( cmd )
		
		# Rename TMP folder to realname
		os.rename( tmpSnapshot, newSnapshot )
		# Return path to new snapshot
		logger.info("New snapshot %s created" % snapshotID)
		notify.notify(Notify.STOPBACKUP, "New snapshot %s created" % snapshotID)
		return newSnapshot

	def restoreFromPath(self, path):
		snapshotDir = self.profile.snapshotDirectory
		path = cleanupPath(path)
		prefix = os.path.commonprefix( [snapshotDir, path])
		if prefix != snapshotDir:
			raise FilterFileError('%s belongs not to filter file %s' % (path, self.profile.filterFile ))
		if prefix[-1] != "/":
			prefix += "/"
		path = path [len(prefix) :]
		pathParts =  path.split('/',2)
		if len(pathParts) <= 1:
			raise IOError(1, "Restore path is invalid")
		if len(pathParts) == 2:
			restorePath = ""
		else:
			restorePath = pathParts[2]
		snapshotPath = os.path.join(snapshotDir, pathParts[0])
		self.restoreFromSnapshot(snapshotPath,restorePath)

	def restoreFromSnapshot(self, snapshotPath, restorePath):
		logger.info('Restoring "%s" out of snapshot "%s"' % (restorePath, snapshotPath))
		sourceDir = self.profile.sourceDirectory
		# We wan't to remove the last part of the sourceDir path with
		# os.path.split. With an tailing / that won't work
		if sourceDir[-1] == "/":
			sourceDir = sourceDir[:-1]
		restoreDestination = cleanupPath(os.path.join(sourceDir, restorePath))
		restoreSource = os.path.join(snapshotPath, self.BACKUPDIR, restorePath)
		if os.path.isdir(restoreSource):
			restoreSource += "/"
		cmd  = "%s --copy-unsafe-links --whole-file" % self.profile.rsyncCMD
		cmd += " --backup --suffix=.%s" % self.generateSnapshotID()
		cmd += " \"%s\" \"%s\"" % (restoreSource, restoreDestination)
		logger.debug( "Running command: %s" % cmd) 
		retVal = os.system( cmd )
		return retVal == 0

	def removeOldSnapshots(self):
		snapshotDir = self.profile.snapshotDirectory
		
		logger.info("Checking snapshot configuration of profile %s" % self.profile)
		# Proof profile settings
		if not os.path.isdir(snapshotDir):
			raise IOError(1, 'Snapshot directory "%s" is not a directory' % snapshotDir)

		# collect all snapshots in the snapshotDirectory
		snapshots = filter( lambda x: os.path.isdir(os.path.join(snapshotDir, x)), os.listdir(snapshotDir))
		snapshots.sort(None, lambda x: os.path.getctime(os.path.join(snapshotDir, x)) )
		snapshots = map ( lambda x: cleanupPath(os.path.join(snapshotDir, x)), snapshots ) 
		snapshots = map ( lambda x: ( os.path.getctime(x), x), snapshots ) 
		if len(snapshots) == 0:
			logger.warn("No old snapshots found in: %s" % snapshotDir)
			return
		logger.info("Found %i old snapshots in: %s" % (len(snapshots) , snapshotDir) )

		nowt = time.time()
		dayt = 60*60*24
		weekt = dayt * 7
		# Do not remove a backup of the last 7 days
		logger.debug("Keeping all backups of the last 7 days" )
		snapshots = filter ( lambda x: (nowt - weekt) > x[0] , snapshots)
		beforeKeeped = None
		for snap in snapshots:
			snapDate = datetime.date.fromtimestamp(snap[0]) 
			if snapDate == beforeKeeped:
				logger.info("Removing backup: %s" % snap[1] )
				cmd  = 'rm -Rf "%s"' % snap[1]
				logger.debug( "Running command: %s" % cmd) 
				os.system( cmd )
			else:
				logger.debug("Keeping backup: %s" % snap[1] )
				beforeKeeped = snapDate
	
def main():
	global logger
	global notify
	usage = "usage: %prog [options] profile"
	parser = optparse.OptionParser(usage=usage)
	#parser.add_option("-p", "--profile", dest="profileFile", help="PATH to QUBU profile", metavar="PATH")
	parser.add_option("-r", "--restore", dest="restorePath", help="restore PATH from snapshot (Full path including snapshot path)", metavar="PATH")
	parser.add_option("-c", "--clean", dest="removeOld", help="Remove/reduce old Snapshots", action="store_true")
	parser.add_option("-q", "--quiet", dest="quiet", action="store_true", help="Decrease Verbose Level (only Warnings and above)")
	parser.add_option("-d", "--debug", dest="debug", action="store_true", help="Debug Output")
	(options, args) = parser.parse_args()
	if options.debug:
		logging.basicConfig(level=logging.DEBUG)
	elif options.quiet:
		logging.basicConfig(level=logging.WARNING)
	else:
		logging.basicConfig(level=logging.INFO)
	logger = logging.getLogger(appName)
	notify = Notify()
		
	if len(args) != 1:
		sys.exit("Missing profile file argument")
	profile = Profile(args[0])
	snap = Snapshots(profile)
	if options.restorePath:
		try:
			snap.restoreFromPath(options.restorePath)
		except FilterFileError as e:
			logger.error(e)
		except IOError as e:
			logger.error(e)
	elif options.removeOld:
		try:
			snap.removeOldSnapshots()
		except FilterFileError as e:
			logger.error(e)
		except IOError as e:
			logger.error(e)	
	else:
		try:
			path = snap.takeSnapshot()
		except RsyncError as e:
			logger.error(e)
			sys.exit(e.exitCode)
		except IOError as e:
			logger.error(e)
			sys.exit('%s' % e)
			

if __name__ == "__main__":
	main()
