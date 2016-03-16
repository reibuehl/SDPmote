#  File: mjpegcam.py
#  Description: HTTP Interface to mjpeg-streamer, screenshots and Timed (TL) screenshots
#  
#  Copyright 2016  Martin Bienz, bienzma@gmail.com
#  
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.
#  
#
import httplib
import urllib
import urllib2
import os
import threading
import time
import datetime
import StringIO
import pygame
import helpers

#HELPER DEVS
def pinger_urllib(host):

	try: 
		urllib2.urlopen(host,None,1)
		#print "Host is live"
		return True
	except:
		#print "Host is not reachable"
		return False

		
#VIDEO Streaming preview, PROTOTYPE NOT USED!
class mjpegStream:
	def __init__(self, ip, myport=80, thepath=''):

		self.ip = ip
		self.myport = myport
		self.cmd = thepath
		self.connected = False

	def connect(self):
		try:
			h = httplib.HTTP(self.ip, self.myport)
			h.putrequest('GET', self.cmd)
			h.endheaders()
			errcode, errmsg, headers = h.getreply()
			self.file = h.getfile()
			self.connected = True
			return True
		except Exception, x:
			print x
			self.connected = False
			return False
	
	def isconnected(self):
		return self.connected	
	
	def update(self, window, size, offset):          
		data = self.file.readline()  
		if data[0:15] == 'Content-Length:':  
			count = int(data[16:])  
			s = self.file.read(count)      
			while s[0] != chr(0xff):  
				s = s[1:]       
				p = StringIO.StringIO(s)  
			try:  
				campanel = pygame.image.load(p).convert()  
				campanel = pygame.transform.scale(campanel, size)  
				window.blit(campanel, offset)  
			except Exception, x:  
				print x  

			p.close()  
			
#MAINCLASS		
class mjpegCamera(object):
	def __init__(self, ip = "127.0.0.1", port = "80", snapshot = "/?action=snapshot", rootfolder = os.path.join("web", "timelapse") , singlepicfolder = os.path.join("web", "timelapse", "general"), interval=5):
		self._timer     = None
		self.interval   = interval

		self.is_running = False
		self.piccounter=1
		
		self.rootfolder = rootfolder
		self.tlfolder = ""
		self.tlfolder_full = ""
		
		self.singlepicfolder = singlepicfolder
		
		if not os.path.exists(self.singlepicfolder):
			os.makedirs(self.singlepicfolder)
			helpers.fix_ownership(self.singlepicfolder)
				
		self.urlsnapshot="/?action=snapshot"
		self.ip=ip
		self.port=str(port)
		self.cmd_snapshot = "http://" + self.ip+ ":" + self.port + self.urlsnapshot
		self.cmd_ipport = "http://" + self.ip + ":" + self.port + "/"
		
		self.connected = False
		self.pygamesurface = None
					
	
	def UpdatePygameSurface(self):
		f = StringIO.StringIO(urllib.urlopen(self.cmd_snapshot).read())
		im_surf = pygame.image.load(f, "cam.jpg").convert()
		campanel = pygame.transform.scale(im_surf, (320,240))  
		self.pygamesurface = campanel
		
	def BlitPygameSurface(self, screen):
		if not self.pygamesurface==None:
			screen.blit(self.pygamesurface, (0,0))  
	
	def connect(self):
		if pinger_urllib(self.cmd_ipport):
			self.connected = True
			print "Camera connect to "+self.cmd_ipport
			return True
		else:
			print "Error: Camera, could not connect to "+self.cmd_ipport
			self.connected = False
			return False
			
	def resetcounter(self):
		self.piccounter=1
		
	def getCurrentTLFolder(self):
		return self.tlfolder
		
	def getindex(self):
		return self.piccounter
	
	def toggleTL(self, foldername=""):
		if self.is_running:
			self.stop()
		else:
			self.starttimelapse(foldername)

	def _run(self):
		if self.is_running:
			self.grab_jpg_tl()
			self.is_running = False
			self.start()
		
	def starttimelapse(self, foldername = ""):
		self.setCurrentTLFolder(foldername)
		self.resetcounter()
		self.grab_jpg_tl()
		self.start()
		
	
	def start(self):
		if not self.is_running:
			self._timer = threading.Timer(self.interval, self._run)
			self._timer.start()
			self.is_running = True

	def stop(self):
		self._timer.cancel()
		# take one last picture to make sure we have one on stop
		self.grab_jpg_tl()
		
		self.resetcounter()
		self.is_running = False
	
	def createDTfolder(self):
		return "tl"+datetime.datetime.now().strftime("%Y.%m.%d %H.%M.%S")
		
	def createDTFile(self):
		return "s"+datetime.datetime.now().strftime("%Y.%m.%d %H.%M.%S")
	
	def setCurrentTLFolder(self, setfoldername):
		if setfoldername == "":
			self.tlfolder=self.createDTfolder()
		else:
			self.tlfolder=setfoldername

		fullpath = os.path.join(self.rootfolder,self.tlfolder)
		
		if os.path.exists(fullpath):
			fullpath = os.path.join(self.rootfolder, self.tlfolder+self.createDTfolder())
			os.makedirs(fullpath)
			helpers.fix_ownership(fullpath)
			self.tlfolder=self.tlfolder+self.createDTfolder()
		else:
			os.makedirs(fullpath)
			helpers.fix_ownership(fullpath)
		
		self.tlfolder_full = fullpath
	
	def TakeScreenShot(self, filename=""):
		
		#check again if folder exists...
		if not os.path.exists(self.singlepicfolder):
			os.makedirs(self.singlepicfolder)
			helpers.fix_ownership(self.singlepicfolder)
		
		if filename=="":
			img_temp = self.createDTFile() + ".jpg"
		else:
			img_temp = filename
			
		urllib.urlretrieve(self.cmd_snapshot, os.path.join(self.singlepicfolder,  img_temp))
		helpers.fix_ownership(os.path.join(self.singlepicfolder,  img_temp))
		return img_temp
		#print "ScreenShot Saved:" + img_temp
	
	def grab_jpg_tl(self):
		img_temp = "tl" + str(self.piccounter).zfill(5) + ".jpg"
		urllib.urlretrieve(self.cmd_snapshot, os.path.join(self.rootfolder, self.tlfolder,  img_temp))
		print "TL Saved:" + img_temp
		helpers.fix_ownership(os.path.join(self.rootfolder, self.tlfolder,  img_temp))
		self.piccounter = self.piccounter + 1
	
