#!/usr/bin/env python
#
#  File: main.py
#  Description: Main Program
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

#application name
mytitle="SDPmote v0.2"
print "------------------------------------------------------------------"
print mytitle+" Copyright (C) 2016 Martin Bienz, bienzma@gmail.com"
print "This program comes with ABSOLUTELY NO WARRANTY."
print "This is free software, and you are welcome to redistribute it"
print "under certain conditions; check the license for details."
print "------------------------------------------------------------------"
print "importing modules..."


import os
import sys

#check if the current working directory is the main directory, if not abort or change to it

script_dir = os.path.dirname(os.path.realpath(__file__)) + os.sep
if not os.path.dirname(__file__) == "":
	#change it to the script directory here	
	print ""
	print "WARNING: Working directory changing to the scripts root directory."
	os.chdir(script_dir)
	print "OK: Changed to "+script_dir
	print ""
	#print "ERROR: Working directory must be the applications root directory, aborting."
	#sys.exit()

import time
import datetime
import math
import platform
import getopt

#Files Stuff
import shutil
import zipfile

#threading stuff
import multiprocessing 	#for the Q / Serial

#web stuff
import tornado.ioloop
import tornado.web
import tornado.websocket
import uuid
import json

#pygame stuff
import pygame
from pygame.locals import *

#my own classes
import serialProcess
import gpioProcess
import mjpegcam
import helpers

print "importing modules...done."

#GLOBALS--------------------------------------------------------------------------------------------
inifile="settings.ini"

screens = {1: "Home", 2: "Camera preview", 3: "Timelapse folders"}
screens_count=len(screens)
current_screen = 1

recordingstatus="Loading..."

#TL Flag for autostart identification... NOT really used... just in case
autostarted=False

#Enable to allow for touch input
touchenabled = True
mousevisible = True

#VARS for PYGAME custom events
MOUSELONGPRESS=pygame.USEREVENT+1
SWIPE=pygame.USEREVENT+2

#headless (no render pygame) and windowed vs fullscreen (will set via cmdline args)
headless = False
windowed = True

#Used to set Tornado to debugmode (will not pre-cache but allways reload)....PUT TO False if not developping!
TornadoDebug=False

# Global DICTs
#printerstatus = {}
printerstatus = {"status": "connecting..",
				"isheatingup": False,
				"isprinting": False,
				"temp": (0.0, 0.0,0.0,0.0),
				"progress": (0.0, 0 ,0),
				"progress_time": (datetime.datetime.now().strftime("%d.%B %Y %H:%M"), helpers.seconds_to_dhms_string(datetime.timedelta(seconds=+1).total_seconds()), "00:00:00"),
				"file": ("", 0),
				"sdrefresh": time.time(),
				"sdfiles": [],
				"print_start_countdown": -1
				}

systemuser = {"hostname": helpers.gethostname(), "system": platform.system(), "username": None, "sudo": False, "sudo_uid": None, "sudo_gid": None, "gpio_enabled": gpioProcess.gpioProcess_mp.enabled}
				
websocketclients = dict()

#GLOBALS - Path -------------------------------------------------------------------------------------
resourcesdir = os.path.join("resources")#"./resources/"
timelapsedir = os.path.join("web", "timelapse")#"./web/timelapse"
generalpicsdir = os.path.join(timelapsedir, "general") #"./web/timelapse"
#tempdir = os.path.join("web", "temp")#"./web/temp" for uploads
#cwd = os.path.join("web")#os.getcwd() # used by static file server
cwd = os.path.join(script_dir, os.path.join("web")) # used by static file server, better to use the full path for tornado's template handler

#SKIN settings--------------------------------------------------------------------------------------
bgcolor = pygame.Color('#cccccc')

button_red = pygame.Color(240,150,150)
button_red_on = pygame.Color(240,40,40)
button_green = pygame.Color(150,240,150)
button_green_on = pygame.Color(40,240,40)
button_blue = pygame.Color(150,150,240)
button_blue_on = pygame.Color(40,40,240)
button_yellow = pygame.Color(240,240,150)
button_yellow_on = pygame.Color(240,240,40)

buttoncolor = pygame.Color('#969696')
buttonhighlightcolor = pygame.Color('#eddb26') #YELLOW
buttonhighlightcolor = pygame.Color('#d67979') #RED
buttonhighlightcolor = pygame.Color('#fafafa') #almost WHITE
buttonfontcolor = pygame.Color('#404040')
buttonbordercolor =  pygame.Color('#8a8a8a')
generalfontcolor = pygame.Color('#404040')
darkfontcolor = pygame.Color('#101010')
lightfontcolor = pygame.Color('#eeeeee')
progress_fg_color = pygame.Color('#3c82c8') #blue
buttonborder = 4
buttonfontsize=30
buttonfontsize_sm=15
generalfontsize=20

#webserver / command handler helper defs------------------------------------------------------------
def gettldirs(d):
	return sorted(filter(os.path.isdir, [os.path.join(d,f) for f in os.listdir(d)]), None, None, False)
	
def gettlfiles(d):
	return sorted([name for name in os.listdir(d) if os.path.isfile(os.path.join(d,name))], None, None, False)

def deltldir(d):
	try:
		os.remove(os.path.join(timelapsedir, d+'.zip'))
	except OSError:
		pass
	return shutil.rmtree(os.path.join(timelapsedir, d))
	
def deltlfiles(d):
	for myfile in d:
		try:
			os.remove(myfile)
		except OSError:
			print OSError
	
def rentldir(d, newd):
	try:
		os.rename(os.path.join(timelapsedir, d), os.path.join(timelapsedir, newd))
		helpers.fix_ownership(os.path.join(timelapsedir, newd))
	except OSError:
		pass
	
def zipdir(path, zip):
	for root, dirs, files in os.walk(path):
		for file in files:
			zip.write(os.path.join(root, file), os.path.basename(os.path.join(root, file)))

def ziptldir(d):
	try:
		os.remove(os.path.join(timelapsedir, d+'.zip'))
	except OSError:
		pass
	zipf = zipfile.ZipFile(os.path.join(timelapsedir, d+'.zip'), 'w')
	zipdir(os.path.join(timelapsedir, d), zipf)
	zipf.close()
	helpers.fix_ownership(os.path.join(timelapsedir, d+'.zip'))
	
def writetldirs(handler):
	mydirs=gettldirs(timelapsedir)
	
	content=[]
	
	for item in mydirs:
	
		fcount = len([name for name in os.listdir(item) if os.path.isfile(os.path.join(item,name))])
		totsize = helpers.bytes2human(sum(os.path.getsize(os.path.join(item,name)) for name in os.listdir(item) if os.path.isfile(os.path.join(item,name))))
		
		if not fcount == 0:
			thumbnail=sorted([ name for name in os.listdir(item) if os.path.isfile(os.path.join(item,name))])[-1]
		else:
			thumbnail="../../images/nocam.png"
		
		info = {
		"directory":    item,
		"count": fcount,
		"size":  totsize,
		"thumbnail": thumbnail,
		}
		content.append(info)

	handler.write(json.dumps({"info": content}))
	
#webserver------------------------------------------------------------------------------------------------------------
#WebsocketHandler HTML5 and other websocket capable clients
class WebSocketHandler(tornado.websocket.WebSocketHandler):
	
	def open(self, *args):
		#self.id = self.get_argument("Id")
		self.id = uuid.uuid4()
		self.stream.set_nodelay(True)
		websocketclients[self.id] = {"id": self.id, "object": self}
		self.write_message("You are connected with id " + str(self.id))
		self.write_message({"cmd": "TEMP", "data": (25.0,30.1)})

	def on_message(self, message):        
		"""
		when we receive some message we want some message handler..
		for this example i will just print message to console
		"""
		print "Client %s received a message : %s" % (self.id, message)
		
	def on_close(self):
		if self.id in websocketclients:
			del websocketclients[self.id]
			print 'closed connection'+ str(self.id)
	
	def check_origin(self, origin):
		#print origin
		return True

# Classic COMMAND handler
class CommandHandler(tornado.web.RequestHandler):

	def get(self, url = '/'):
		#print 'get'
		self.handleRequest()
	def post(self, url = '/'):
		#print 'post'
		self.handleRequest()
		
	# handle both GET and POST requests with the same function
	def handleRequest( self ):
		global serialQ	
		global printerstatus
		
		# is op to decide what kind of command is being sent
		op = self.get_argument('op',None)
		#print op
		#print self.request.arguments
		
		if op == "serialstatus":
			#print myfiles
			self.write(json.dumps({"seriallog": serialQ}))
		
		if op == "sendgcode":
			gcodecmd=self.get_argument('command',"M105")
			SendGodeLog(gcodecmd)
			
			#q = self.application.settings.get('queue')
			#q.put({"CMD": "SERIAL", "DATA": gcodecmd})
			#updateSerialLog("sent: "+gcodecmd)
		
		if op == "sendgcodespecial":
			#cmd = self.get_argument('command', None)
			#q = self.application.settings.get('queue')
			SendGcodeSpecial(self.request.arguments)
		
				
		if op == "restartserver":
			if self.get_argument('mode',None) == "app":
				RestartApplication()
			
			if self.get_argument('mode',None) == "server":
				RestartServer()
			
			if self.get_argument('mode',None) == "shutdown":
				ShutdownServer()
			
		
		if op == "getsettings":
			
			self.write(json.dumps(cfg.settings))
						
					
			
		if op == "savesettings":
			
			settingstemp = json.loads(self.get_argument('config', None))
			cfg.settings=settingstemp
									
			cfg.Save()
			
			#need to set new timer intervall
			mjpgCam.interval=int(cfg.settings["General"]["pics_per_second"])

			self.write(json.dumps({"status": "ok"}))
			
		
		#received a "checkup" operation command from the browser:
		if op == "toggletimelapse": 
			ToggleTimeLapse(self.get_argument('tlfolder',None))
			#mjpgCam.toggleTL(self.get_argument('tlfolder',None))
			#self.write("OK")
		
		if op == "screenshot":
			ssfile = mjpgCam.TakeScreenShot() 
			self.write(json.dumps({"ssfile": ssfile}))
			
		if op == "testmail":
		
			#if mjpgCam.connected:
			email_attachement = os.path.join("web", "images", "nocam.png")#"./web/timelapse"
			#email_attachement = None
			email_text="Test e-mail Done.\n"
			helpers.send_mail_async(cfg.settings["General"]["email_to"], cfg.settings["General"]["email_from"],
											mytitle + " - Test e-mail " + datetime.datetime.now().strftime("%d.%B %Y %H:%M"), email_text,email_attachement,
											cfg.settings["General"]["email_user"], cfg.settings["General"]["email_pw"],
											cfg.settings["General"]["email_server"], int(cfg.settings["General"]["email_server_port"])
											)
			#ssfile = mjpgCam.TakeScreenShot() 
			#self.write(json.dumps({"email_status": email_status}))
		
		if op == "deltldir":
			deltldir(self.get_argument('tlfolder',None))
			
			writetldirs(self)
		
		if op == "deltlfiles":
			filestodel=self.get_arguments('tlfiles',None)
			filespathtodel = []
			for f in filestodel:
				filespathtodel.append (os.path.join(timelapsedir, self.get_argument('tlfolder',None),f))
			
			deltlfiles(filespathtodel)
			
			myfiles=gettlfiles(os.path.join(timelapsedir, self.get_argument('tlfolder',None)))
			self.write(json.dumps({"files": myfiles, "foldername": self.get_argument('tlfolder',None) }))
		
		if op == "rentldir":
			rentldir(self.get_argument('tlfolder',None), self.get_argument('tlfolder_new',None))
			
			writetldirs(self)
			
		
		if op == "ziptldir":
			ziptldir(self.get_argument('tlfolder',None))
			self.write(json.dumps({"zip": os.path.join(timelapsedir, self.get_argument('tlfolder',None)+'.zip')}))
		
		if op == "gettlfiles":
			myfiles=gettlfiles(os.path.join(timelapsedir, self.get_argument('tlfolder',None)))
			#print myfiles
			self.write(json.dumps({"files": myfiles, "foldername": self.get_argument('tlfolder',None) }))
		
		if op == "gettldirs":
			writetldirs(self)
		
		if op == "checkup":
			usage=helpers.disk_usage(cwd)
			spaceusedpercent=round(float(usage.used)/float(usage.total)*100,2)
			spacefreepercent=round(float(usage.free)/float(usage.total)*100,2)
		
			if mjpgCam.is_running: 
				tlstat="stop timelapse"
				tlmsg="Rec: " + mjpgCam.tlfolder + ", " + str(mjpgCam.getindex()-1) + " ps/"+ str(cfg.settings["General"]["pics_per_second"]) +"s."
			else:
				tlstat="start timelapse"
				tlmsg="Not recording."
				if not mjpgCam.connected: tlmsg+=" Cam offline."		
			
			recordingstatus=tlmsg
				
			status = {	"camonline": mjpgCam.connected, 
						"spacetotal": helpers.bytes2human(usage.total),
						"spaceused": helpers.bytes2human(usage.used),
						"spacefree": helpers.bytes2human(usage.free),
						"spacefreepercent": spacefreepercent,
						"spaceusedpercent": spaceusedpercent,
						"tlon": mjpgCam.is_running,
						"tlstatus": tlstat,
						"piccounter": mjpgCam.getindex(),
						"tlfolder": mjpgCam.tlfolder_full,
						"tlfolder_name": mjpgCam.tlfolder,
						"recordingstatus": recordingstatus
					 }
			#turn it to JSON and send it to the browser
			self.write( json.dumps({"cam": status, "printer": printerstatus} ) )

# forms that post /upload land here and save the files in /temp/
class UploadHandler(tornado.web.RequestHandler):
	def post(self):
		
		file1 = self.request.files['InputFile'][0]
		original_fname = file1['filename']

		output_file = open(os.path.join(cwd, "temp/" + original_fname), 'wb')
		output_file.write(file1['body'])

		self.finish("file " + original_fname + " is uploaded")
		print "Uploaded file: temp/" + original_fname
			
# send the index file
class IndexHandler(tornado.web.RequestHandler):
    def get(self, url = "/"):
		#global serverip, tornadoport
		
		if (url=="/"):
			the_file="index.html"
			
		else:
			the_file=url
			
		#if (url == "base.html"):
		#	self.render(os.path.join(cwd, url), servername=helpers.gethostname())
		#else:
		self.render(os.path.join(cwd, the_file), servername=helpers.gethostname(), osname=platform.system(), title=mytitle)
		
    def post(self, url ='/'):
		self.get(url)
		
#Pygame Classes & DEFs-----------------------------------------------------------------------------------------------
class RenderMonitorScreen:
	def __init__ (self):
		#320 x 200 surface with alpha
		self.notiscreen = pygame.Surface((320, 200),SRCALPHA)
		
		self.left=0
		self.width=self.notiscreen.get_width()

		self.height=self.notiscreen.get_height()
		self.top=0

		#icons
		self.icon_cam = pygame.image.load(os.path.join(resourcesdir, "icon_camera-50.png")).convert_alpha()
		self.icon_hdd = pygame.image.load(os.path.join(resourcesdir, "icon_hdd-50.png")).convert_alpha()
		self.icon_3dp = pygame.image.load(os.path.join(resourcesdir, "icon_3dprinter-50.png")).convert_alpha()
		

		#Font
		self.font = pygame.font.Font(None, generalfontsize)

		#Progressbars
		self.surf_progress_hdd=RenderProgressBar(50,11)
		self.surf_progress_print=RenderProgressBar(50,11)
		
		self.mycounter = 0 #testing the redraw process
		
		
	def draw(self):
		#get all status stuff first

		#Diskstatus
		usage=helpers.disk_usage(cwd)
		spaceusedpercent=round(float(usage.used)/float(usage.total)*100,2)
		spacefreepercent=round(float(usage.free)/float(usage.total)*100,2)
		txt_free_space=helpers.bytes2human(usage.free) + " (" + str(spacefreepercent) + "%)"
		
		#Camera status
		if mjpgCam.is_running:
			txt_cam_status="online, recording"
			txt_cam_folder=mjpgCam.tlfolder 
			txt_cam_pic_status=str(mjpgCam.getindex()-1) + " ps/"+ str(cfg.settings["General"]["pics_per_second"]) +"s."
		else:
			txt_cam_status="not recording"
			if not mjpgCam.connected: txt_cam_status+=", camera offline"
			txt_cam_folder="n/a"
			txt_cam_pic_status="0" + " ps/"+ str(cfg.settings["General"]["pics_per_second"]) +"s."
		
		#Printerstatus
		if not printerstatus:
			printer_status = "n/a"
			printer_isprinting = False
			printer_file = "n/a"
			
			printer_nozzle = "n/a"
			printer_HB = "n/a"
			printer_progress = 0
			printer_progress_timeleft = "00:00:00"
				
		else:
			printer_status = printerstatus["status"]
			printer_isprinting = printerstatus["isprinting"]
			
			printer_file = printerstatus["file"][0] + " (" + helpers.bytes2human(printerstatus["file"][1]) + ")"
			
			printer_nozzle = str(printerstatus["temp"][0]) + " / " + str(printerstatus["temp"][1])
			printer_HB = str(printerstatus["temp"][2]) + " / " + str(printerstatus["temp"][3])
			printer_progress = round(float(printerstatus["progress"][0])/100,2)
			printer_progress_timeleft = printerstatus["progress_time"][2]
		
		#clear the surface
		self.notiscreen.fill((204, 204, 204,200))
		
		#draw the icons
		self.notiscreen.blit(self.icon_cam,(10,10))
		self.notiscreen.blit(self.icon_hdd,(10,70))
		self.notiscreen.blit(self.icon_3dp,(10,130))
			
		#Titles and Text
		#CAMERA
		self.notiscreen.blit(self.font.render(txt_cam_status, True, darkfontcolor),(65,16))
		
		title_surf=self.font.render("name: ", True, generalfontcolor)
		self.notiscreen.blit(title_surf,(65,29))
		self.notiscreen.blit(self.font.render(txt_cam_folder, True, darkfontcolor),(65+title_surf.get_width(),29))
		
		title_surf=self.font.render("status: ", True, generalfontcolor)
		self.notiscreen.blit(title_surf,(65,42))
		self.notiscreen.blit(self.font.render(txt_cam_pic_status, True, darkfontcolor),(65+title_surf.get_width(),42))
		
		#HDD
		title_surf=self.font.render("diskstatus: ", True, generalfontcolor)
		self.notiscreen.blit(title_surf,(65,81))
		self.notiscreen.blit(self.surf_progress_hdd.updatesurface(usage.used/float(usage.total)),(65+title_surf.get_width(),81))
		
		title_surf=self.font.render("freespace: ", True, generalfontcolor)
		self.notiscreen.blit(title_surf,(65,94))
		self.notiscreen.blit(self.font.render(txt_free_space, True, darkfontcolor),(65+title_surf.get_width(),94))
		
		#3dprinter
		# status
		self.notiscreen.blit(self.font.render(printer_status, True, darkfontcolor),(65,136))
		
		# Temperatures
		title_surf=self.font.render("nozzle: ", True, generalfontcolor)
		self.notiscreen.blit(title_surf,(65,149))
		title_nozzle=self.font.render(printer_nozzle, True, darkfontcolor)
		self.notiscreen.blit(title_nozzle,(65+title_surf.get_width(),149))
		dist=65+title_surf.get_width()+5+title_nozzle.get_width()
		
		title_surf=self.font.render("hb: ", True, generalfontcolor)
		self.notiscreen.blit(title_surf,(dist,149))
		self.notiscreen.blit(self.font.render(printer_HB, True, darkfontcolor),(dist+title_surf.get_width(),149))
		
		if printer_isprinting:
			# File and status printing
			title_surf=self.font.render("printing: ", True, generalfontcolor)
			self.notiscreen.blit(title_surf,(65,163))
			title_file=self.font.render(printer_file, True, darkfontcolor)
			self.notiscreen.blit(title_file,(65+title_surf.get_width(),163))
			self.notiscreen.blit(self.surf_progress_print.updatesurface(printer_progress),(65+title_surf.get_width()+5+title_file.get_width(),163))
		
			title_surf=self.font.render("print time left: ", True, generalfontcolor)
			self.notiscreen.blit(title_surf,(65,176))
			self.notiscreen.blit(self.font.render(printer_progress_timeleft, True, darkfontcolor),(65+title_surf.get_width(),176))

		#blit the finished screen
		screen.blit(self.notiscreen,(0,0))

class RenderMenuScreen:
	def __init__ (self):
		#320 x 200 surface with alpha
		self.notiscreen = pygame.Surface((320, 200),SRCALPHA)
		
		self.left=0
		self.width=self.notiscreen.get_width()

		self.height=self.notiscreen.get_height()
		self.top=0
			#Font
		self.font = pygame.font.Font(None, generalfontsize+3)
		
		self.mainmenu = RenderMenu(False, False)
		
		self.mainmenu.AddButton(os.path.join(resourcesdir, "icon_3dprinter-50.png"), "", "mainmenuscreen.toggle(); set_mode(1); ", size=(50,40), xb=10, yb=5)
		self.mainmenu.AddButton(os.path.join(resourcesdir, "icon_camera-50.png"), "", "mainmenuscreen.toggle(); set_mode(2); ", size=(50,40), xb=70, yb=5)
		self.mainmenu.AddButton(os.path.join(resourcesdir, "icon_folder-50.png"), "", "mainmenuscreen.toggle(); set_mode(3); ", size=(50,40), xb=130, yb=5)
		
		self.mainmenu.AddButton(os.path.join(resourcesdir, "icon_timer-50.png"), "start timelapse", "ToggleTimeLapse();", size=(145,40), xb=10, yb=65, font_size=20, icon_size=(20,20))
		self.mainmenu.AddButton(os.path.join(resourcesdir, "icon_camera-50.png"), "take picture", "TakePicture();", size=(145,40), xb=160, yb=65, font_size=20, icon_size=(20,20))
		
		
		self.mainmenu.AddButton(os.path.join(resourcesdir, "icon_lights_off-50.png"), "Off", "mynotism.triggershow(1, 'Sending light OFF ('+cfg.settings['Printer']['gcode_lights_off']+')'); SendGodeLog(cfg.settings['Printer']['gcode_lights_off']); ", size=(70,40), xb=160, yb=110, font_size=20, icon_size=(20,20))
		self.mainmenu.AddButton(os.path.join(resourcesdir, "icon_lights_on-50.png"), "On", "mynotism.triggershow(1, 'Sending light ON ('+cfg.settings['Printer']['gcode_lights_on']+')'); SendGodeLog(cfg.settings['Printer']['gcode_lights_on']); ", size=(70,40), xb=235, yb=110, font_size=20, icon_size=(20,20))
		
		#self.mainmenu.AddButton(os.path.join(resourcesdir, "icon_restart-50.png"), "restart", "RestartServer(); mainmenuscreen.toggle()", size=(145,40), xb=10, yb=155, font_size=20, icon_size=(20,20))
		#self.mainmenu.AddButton(os.path.join(resourcesdir, "icon_shutdown-50.png"), "shutdown", "ShutdownServer(); mainmenuscreen.toggle()", size=(145,40), xb=160, yb=155, font_size=20, icon_size=(20,20))
		
		#update, now calls the Dialog to ask for shutdown / restart
		self.mainmenu.AddButton(os.path.join(resourcesdir, "icon_shutdown-50.png"), "Power", "PowerOptionsDialog()", size=(145,40), xb=10, yb=110, font_size=20, icon_size=(20,20))

		
		self.visible = False

	def checkinput(self, event):
		self.mainmenu.checkinput(event)
	
	def toggle(self):
		if self.visible == True:
			self.visible = False
		else:
			self.visible = True
	
	def draw(self):
		if not self.visible: return
		
		#clear the surface
		self.notiscreen.fill((234, 234, 234, 220))
					
		#self.notiscreen.blit(self.font.render("Menu", True, darkfontcolor),(10,1))
		self.notiscreen.blit(self.font.render("Commands", True, darkfontcolor),(10,50))
		
		#self.notiscreen.blit(self.font.render("Lights", True, darkfontcolor),(110,120))
		
		#blit the finished screen
		screen.blit(self.notiscreen,(0,0))
		self.mainmenu.draw()
		
class RenderSimpleDialog:
	def __init__ (self):
		#320 x 200 surface with alpha
		self.notiscreen = pygame.Surface((320, 240),SRCALPHA)
		
		self.str_title = "n/a"
		self.str_text = "n/a"
		
		self.myfunc = None
		
		self.left=0
		self.width=self.notiscreen.get_width()

		self.height=self.notiscreen.get_height()
		self.top=0
		#Fonts
		self.font = pygame.font.Font(None, generalfontsize+5)
		self.font_b =  pygame.font.Font(None, generalfontsize+5)
		#self.font_b.set_bold(True)
		
		self.mainmenu = RenderMenu(False, False)
		
		self.update_window()
		
		self.visible = False
		
		self.name="default"
	
	def reset(self):
		self.remove_all_buttons()
		self.str_title = "n/a"
		self.str_text = "n/a"
		self.name="default"
		self.myfunc = None
		
	def set_specialsurface_function(self, func):
		self.myfunc = func
		self.update_window()
	
	def set_button_text(self, index, mytext):
		self.mainmenu.updatebuttontext(index, mytext)
		
	def set_button_action(self, index, action):
		self.mainmenu.updatebuttonaction(index, action)
		
	def set_window_title(self, newtitle):
		self.str_title=newtitle
		self.update_window()
		
	def set_text(self, newtext):
		self.str_text=newtext
		self.update_window()
	
	def add_button(self, icon=None, text="", action="", size=(90,40), xb=10, yb=185, col=buttoncolor, col_over=buttonhighlightcolor):
		self.mainmenu.AddButton(icon, text, action , size=size, xb=xb, yb=yb, font_size=20, icon_size=(20,20), bc_on=col_over, bc_off=col)
	
	def remove_button(self, index):
		self.mainmenu.RemoveButton(index)
		
	def remove_all_buttons(self):
		self.mainmenu.RemoveAllButtons()
		return True
		
	def update_window(self):
		#create Background the surface
		self.notiscreen.fill((234, 234, 234, 220))
		
		#create the rounded window and blit it to the screen
		window=GetWindowSurface((310, 230))
		self.notiscreen.blit(window, (5,5))
		
		pygame.draw.line(self.notiscreen, buttonbordercolor, (5, 175), (314,175), 2)
		
		#write the title on top
		self.notiscreen.blit(self.font_b.render(self.str_title, True, generalfontcolor),(10,10))
		
		if not self.myfunc:
			#write the text
			drawTextSurface(self.notiscreen, self.str_text, lightfontcolor, (10,45,300,120), self.font, aa=False, bkg=pygame.Color('#bbbbbb'))
		
	def checkinput(self, event):
		self.mainmenu.checkinput(event)
	
	def toggle(self):
		if self.visible == True:
			self.visible = False
		else:
			self.visible = True
	
	def draw(self):
		if not self.visible: return
		#blit the special surface if set
		if self.myfunc:
			self.notiscreen = self.myfunc(self.notiscreen)
		#blit the finished screen
		screen.blit(self.notiscreen,(0,0))
		
		#draw the menu / buttons on top
		self.mainmenu.draw()

class RenderProgressBar:
	def __init__ (self, w, h):
		#indicator, progressbar
		self.w=w
		self.h=h
		
		self.x=0
		self.y=0
		
		self.progress_surface = pygame.Surface((self.w+1, self.h+1))
		self.progress_surface = self.progress_surface.convert_alpha()
		
		
	def updatesurface(self, value):
		self.progress_surface.fill((255, 255, 255,0)) # 4 = 0 for full alpha
				
		pygame.draw.rect(self.progress_surface, (140,140,140), (self.x,self.y, self.w ,self.h), 2)
		neww=(value)*(self.w-5)
		pygame.draw.rect(self.progress_surface, progress_fg_color, (self.x+3, self.y+3 , neww, self.h-5), 0)
		
		return self.progress_surface

class RenderStatusBar:
	def __init__ (self):
		
		self.notiscreen = pygame.Surface((320, 40),SRCALPHA)
		self.notiscreen.fill((110, 110, 110, 240) ,special_flags=BLEND_RGBA_MAX)
		#Blit the UM Logo
		self.notiscreen.blit(my_logo,(185,0))
	
		self.left=0
		self.width=self.notiscreen.get_width()
		
		self.height=self.notiscreen.get_height()
		self.top=pygame.display.Info().current_h-self.height
		
		#prep font
		self.font_title = pygame.font.Font(None, 35)
		self.font_subtitle = pygame.font.Font(None, 15)
		
		self.mainmenucontrol = RenderMenu(False, False)
		self.mainmenucontrol.AddButton(os.path.join(resourcesdir, "icon_menu_black-40.png"), "", "mainmenuscreen.toggle()",  size=(40,38), xb=280-5, yb=201)
		
		#self.temp_menu = pygame.image.load(os.path.join(resourcesdir, "icon_menu_white-40.png")).convert_alpha()
	
	def checkinput(self, event):
		self.mainmenucontrol.checkinput(event)
	
	def draw(self):
		
		text_title = self.font_title.render(mytitle, True, (255, 255, 255))
		text_subtitle =self.font_subtitle.render("server @ http://"+ cfg.settings["Webserver"]["mjpg_ip"] + ":" + cfg.settings["Webserver"]["mjpg_port"], True, (10, 10, 10))
		
		#BLIT the screen noti background
		screen.blit(self.notiscreen,(self.left, self.top))
		
		#screen.blit(self.temp_menu,(self.width-55,self.top))
		
		screen.blit(text_title, (self.left+10, self.top+4))
		screen.blit(text_subtitle, (self.left+10, self.top+30))
		
		self.mainmenucontrol.draw()

class RenderNotification:
	def __init__ (self, size=(300,40)):
		
		bottom_spacing = 5 #distance from the bottom screen
		border=buttonborder
		

		self.notiscreen = GetRoundedRectSurface(rect=(0,0,size[0],size[1]), color=buttonbordercolor)
				
		#blitt inner over outer, makes a nice border...
		inner = GetRoundedRectSurface(rect=(0,0,size[0]-border,size[1]-border), color=buttoncolor)
											
		#then inner button color
		self.notiscreen.blit(inner,((border/2),(border/2)))
		
		
		self.left=(pygame.display.Info().current_w-self.notiscreen.get_width()) / 2
		self.width=self.notiscreen.get_width()
		
		self.height=self.notiscreen.get_height()
		self.top=pygame.display.Info().current_h-bottom_spacing-self.height
		
		#prep font
		self.font_fps = pygame.font.Font(None, 20)
		self.rect_fps = pygame.Rect(self.left, self.top, self.width, self.height)

		self.showit=False
		self.ticksave=0
		self.showseconds=0
		self.duration=0
		self.msg="test"
	
	def triggershow(self, seconds, msg=""):
		self.msg=msg
		self.duration=0
		self.showseconds=seconds
		self.showit=True
	def triggershow_fix(self, msg=""):
		self.msg=msg
		self.showit=True
		
	def show(self, tick):
		
		if self.showit:
		
			self.duration+=tick
			#print self.duration
			if self.duration < self.showseconds:
				self.draw()
			else:
				self.showit=False
	def show_fix(self):
		if self.showit:
			self.draw()
	
	def hide_fix(self):
		self.showit=False
	
	def draw(self):
		#draw Clock and FPS
		text_fps = self.font_fps.render(self.msg, 1, (255, 255, 255))
		textpos_fps = text_fps.get_rect(centerx=current_w/2, centery=self.top+(self.height/2))
		
		#BLIT the screen noti background
		screen.blit(self.notiscreen,(self.rect_fps))
		#BLIT the content, text or submitted surface

		screen.blit(text_fps, textpos_fps)

class RenderMenu:
	def __init__ (self, renderbackground=True, autopos=True):
		self.buttons={}
		self.buttons_actions={}
		self.buttons_pos={}
		self.currentindex=0
		self.button_count=0
		
		self.autopos=autopos
		
		self.mousedown=False
		
		#this will enable the navigation with a keyboard or other input method, index will be rendered active
		self.enablekeyboard = False
		
		if self.autopos:
			self.start_x=10
			self.start_y=10
			self.y_diff=55
		
	def AddButton (self, buttonicon=None, text="Default", action=None, but_on_file=None, but_off_file=None, size=(300,50), border=buttonborder, r=0.2, tl=True, bl=True, tr=True, br=True, xb=None,yb=None, bc_on=buttonhighlightcolor, bc_off=buttoncolor, bbc=buttonbordercolor, bf_c=buttonfontcolor, font_size=None, icon_size=None):
		self.buttons[self.button_count]=RenderButton(buttonicon, text, but_on_file, but_off_file, size, border, r, tl, bl, tr, br, bc_on,bc_off,bbc,bf_c,font_size, icon_size)
		self.buttons_actions[self.button_count]=action
		self.buttons_pos[self.button_count]=(xb, yb)
		self.button_count=self.button_count+1
	
	def RemoveButton(self, index):
		del self.buttons[index]
		del self.buttons_actions[index]
		del self.buttons_pos[index]
		self.button_count=self.button_count-1
		self.currentindex=0
	
	def RemoveAllButtons(self):
		self.buttons={}
		self.buttons_actions={}
		self.buttons_pos={}
		self.currentindex=0
		self.button_count=0
	
	def updatebuttontext(self, index, text):
		self.buttons[index].settext(text)
	
	def updatebuttonaction(self, index, action):
		self.buttons_actions[index] = action
	
	def draw (self):
		
		#if not buttons defined...
		if self.button_count==0:
			return
		
		if self.autopos:
			for x in range (0, self.button_count):
				self.buttons[x].draw(self.start_x, self.start_y+(self.y_diff*x))
		else:
			for x in range (0, self.button_count):
				x_p, y_p=self.buttons_pos[x]
				self.buttons[x].draw(x_p, y_p)
				
		if self.mousedown or self.enablekeyboard:
			self.buttons[self.currentindex].draw_over()
	
	def next(self):
		idx=self.currentindex
		idx+=1
	
		if idx==-1:
			idx=self.button_count-1
		if idx==self.button_count:
			idx=0		
		self.currentindex=idx
	def previous(self):
		idx=self.currentindex
		idx-=1
	
		if idx==-1:
			idx=self.button_count-1
		if idx==self.button_count:
			idx=0		
		self.currentindex=idx
	def getselected(self):
		return self.currentindex
	
	def checkinput (self, event):
		idx=self.currentindex
		
		#Mouse stuff but only if touch is enabled
		if touchenabled:
			if event.type == MOUSEBUTTONDOWN:
				for x in range (0, self.button_count):
					if self.buttons[x].getrect().collidepoint(pygame.mouse.get_pos()):
						self.currentindex = x
						self.mousedown=True
						return
		
			if event.type == MOUSEBUTTONUP:
				self.mousedown=False
				for x in range (0, self.button_count):
					if self.buttons[x].getrect().collidepoint(pygame.mouse.get_pos()):
						self.RunAction(x)
						return

		
		if event.type == pygame.KEYDOWN:
			if event.key == pygame.K_UP:
				idx=idx-1
			if event.key == pygame.K_DOWN:
				idx=idx+1
			if event.key == pygame.K_RETURN:
				self.RunAction(idx)
				return
		
		if idx==-1:
			idx=self.button_count-1
		if idx==self.button_count:
			idx=0
		
		self.currentindex=idx
			
		
	def RunAction(self, index_b):
		exec self.buttons_actions[index_b]

class RenderButton:
	def __init__ (self, buttonicon=None, text="", but_off_file=None, but_over_file=None,  size=(300,50), border=4, r=0.2, tl=True, bl=True, tr=True, br=True, bc_on=buttonhighlightcolor, bc_off=buttoncolor, bbc=buttonbordercolor, bf_c=buttonfontcolor, font_size=None, icon_size=None):
		
		self.over=False
		self.bf_c=bf_c
		
		icon_margin=12
		self.font_margin=12
						
		if but_off_file==None:
			
			#self.button = pygame.image.load(os.path.join(resourcesdir, "button_large_off.png")).convert_alpha()
			#self.button_over = pygame.image.load(os.path.join(resourcesdir, "button_large_on.png")).convert_alpha()
			
			#speed=helpers.SpeedTest()
		
			#Draw instead of having a file
			
			if border == 0: # no border
				self.button = GetRoundedRectSurface((0,0,size[0],size[1]),  bc_off  ,r, tl, bl, tr, br)
				self.button_over = GetRoundedRectSurface((0,0,size[0],size[1]),   bc_on,r, tl, bl, tr, br)
			
			else:
				self.button = GetRoundedRectSurface((0,0,size[0],size[1]), bbc ,r, tl, bl, tr, br)
				self.button_over = GetRoundedRectSurface((0,0,size[0],size[1]),  bbc   ,r, tl, bl, tr, br)
				
				#blitt inner over outer, makes a nice border...
				inner = GetRoundedRectSurface((0,0,size[0]-border,size[1]-border), bc_off ,r, tl, bl, tr, br)
				inner_over = GetRoundedRectSurface((0,0,size[0]-border,size[1]-border),  bc_on ,r, tl, bl, tr, br)
									
				#then inner button color
				self.button.blit(inner,((border/2),(border/2)))
				self.button_over.blit(inner_over,((border/2),(border/2)))

			
			
			
			
			#delta, ms =  speed.stop()
			#print delta
			
		
		else:
			self.button = pygame.image.load(but_off_file).convert_alpha()
			self.button_over = pygame.image.load(but_over_file).convert_alpha()
		
	
				
		self.b_width=self.button.get_width()
		self.b_height=self.button.get_height()
		
		#set the font height to shrink with the button height... of IF set manual font_size
		if font_size==None:
			self.font_height=self.b_height-self.font_margin
		else:
			self.font_height=font_size
		
		
		self.buttonicon=buttonicon
		
		if not self.buttonicon==None:
			self.button_icon = pygame.image.load(buttonicon).convert_alpha()
			if icon_size==None:
				self.button_icon = aspect_scale(self.button_icon,(self.b_width-icon_margin,self.b_height-icon_margin))
			else:
				self.button_icon = aspect_scale(self.button_icon, icon_size)
			
		self.text=text
	
		self.updatesurface()
	
	def getrect(self):
		return (Rect(self.posx, self.posy, self.b_width, self.b_height))
			
	def updatesurface(self):	
		#prep and render font
		#self.font = pygame.font.Font(os.path.join(resourcesdir, "Survivant.ttf"), 30)
		
		self.font = pygame.font.Font(None, self.font_height)
		self.button_text = self.font.render(self.text, 1, self.bf_c)
		font_offset=0 #-3for Survivant 30, put -3
		
		#create surfaces for normal and over state
		self.button_surface = pygame.Surface((self.b_width, self.b_height))
		self.button_surface = self.button_surface.convert_alpha()
		self.button_surface.fill((255, 255, 255,0)) # 4 = 0 for full alpha
		
		self.button_surface_over=pygame.Surface((self.b_width, self.b_height))
		self.button_surface_over = self.button_surface_over.convert_alpha()
		self.button_surface_over.fill((255, 255, 255,0)) # 4 = 0 for full alpha
		
		self.button_surface.blit(self.button,(0,0))
		self.button_surface_over.blit(self.button_over,(0,0))
		
		
		dist_it=10
		if not self.buttonicon==None:
			
			#only icon, not text?
			if self.text=="":

				start_left=(self.b_width/2)-(self.button_icon.get_width()/2)
				
				self.button_surface.blit(self.button_icon,(start_left,(self.b_height/2)-(self.button_icon.get_height()/2)))
				self.button_surface_over.blit(self.button_icon,(start_left,(self.b_height/2)-(self.button_icon.get_height()/2)))
				
			else:
				dist_total=self.button_icon.get_width()+dist_it+self.button_text.get_width()
				start_left=(self.b_width/2)-(dist_total/2)
				start_left_text=start_left+self.button_icon.get_width()+dist_it
				
				#blit on std button surface
				self.button_surface.blit(self.button_icon,(start_left,(self.b_height/2)-(self.button_icon.get_height()/2)))
				self.button_surface.blit(self.button_text,(start_left_text,(self.b_height/2)-(self.button_text.get_height()/2)+font_offset))
				#blit also on over surface
				self.button_surface_over.blit(self.button_icon,(start_left,(self.b_height/2)-(self.button_icon.get_height()/2)))
				self.button_surface_over.blit(self.button_text,(start_left_text,(self.b_height/2)-(self.button_text.get_height()/2)+font_offset))
			
			
		else:
			#only text, no icon
			start_left_text=(self.b_width/2)-(self.button_text.get_width()/2)
			
			#blit on std button 
			self.button_surface.blit(self.button_text,(start_left_text,(self.b_height/2)-(self.button_text.get_height()/2)+font_offset))
			#blit also on over surface
			self.button_surface_over.blit(self.button_text,(start_left_text,(self.b_height/2)-(self.button_text.get_height()/2)+font_offset))
			
		
	def GetSetOver(self, over=None):
		if over==None:
			return self.over
		else:
			self.over=over
	
	def draw(self, x,y):
		self.posx=x
		self.posy=y
		if self.over:
			screen.blit(self.button_surface_over,(x,y))
		else:
			screen.blit(self.button_surface,(x,y))
	
	def draw_over(self):
		screen.blit(self.button_surface_over,(self.posx,self.posy))
	
	def settext(self, text):
		self.text=text
		self.updatesurface()

class RenderListView:
	def __init__ (self):
		self.buttons={}
		self.ctrl_buttons={}
		
		self.buttons_pos={}
		self.currentindex=0
		self.button_count=0
		
		self.offset=0
		self.offsetto=0
		
		self.itemsperpage=3
		self.pages=1
		self.current_page=1
		
		self.ctrl_buttons[0]=RenderButton(buttonicon=os.path.join(resourcesdir, "icon_down-50.png"), text="", size=(50,50), tl=False, tr=False)
		self.ctrl_buttons[1]=RenderButton(buttonicon=os.path.join(resourcesdir, "icon_up-50.png"), text="", size=(50,50), bl=False, br=False)
		self.ctrl_buttons[2]=RenderButton(buttonicon=os.path.join(resourcesdir, "icon_back-50.png"), text="", size=(50,30) )

		
		#font for display
		self.font = pygame.font.Font(None, buttonfontsize-10)
		
		self.start_x=10
		self.start_y=10
		self.y_diff=55
						
	def AddItem (self, size=None, buttonicon=None, Title="", Desc="", Key="", action=None, xb=None,yb=None, enabled=True):
		self.buttons[self.button_count]=RenderListViewItem(size, buttonicon, Title, Desc, Key, action, enabled)
		self.buttons_pos[self.button_count]=(xb, yb)
		self.button_count=self.button_count+1

		#page calculation
		self.pages=int(math.ceil((self.button_count+self.itemsperpage-1)/self.itemsperpage))
		#print str(self.button_count) +" - "  + str(self.pages)
		self.setpage(0)

	def updateitemtext(self, index, text):
		pass
		#self.buttons[index].settext(text)
	
	def setpage(self, idx):
		self.current_page=int(math.ceil(idx/self.itemsperpage)+1)
		
		self.offset=(self.current_page*self.itemsperpage)-self.itemsperpage
		self.offsetto=(self.current_page*self.itemsperpage)
		if self.offsetto>self.button_count: self.offsetto=self.button_count
	
	def draw (self):
		
		#outer left
		pygame.draw.rect(screen, (160, 160, 160), (7, 7, 250+5,150+10+13), 0)
		#outer left - bottom panel
		pygame.draw.rect(screen, (150,150,150), (7, 150+10+14+6,  250+5, 20-6), 0)
		#outer right
		pygame.draw.rect(screen, (100,100,100), (250+10+2, 7, 50+5,150+10+5+22), 0)
		# lv controls
		self.ctrl_buttons[0].draw(250+15,65)
		self.ctrl_buttons[1].draw(250+15,10)
		self.ctrl_buttons[2].draw(250+15,160)
		#status text
		statustext = self.font.render("Item "+str(self.currentindex+1)+" of "+str(self.button_count) + " (Page "+ str(self.current_page) +"/" + str(self.pages) + ")", 1, (20,20,20))
		screen.blit(statustext ,(10,180))
		
		pos=0
		for x in range (self.offset, self.offsetto):
			if x==self.currentindex : self.buttons[x].GetSetOver(True)
			else: self.buttons[x].GetSetOver(False)
			self.buttons[x].draw(self.start_x, self.start_y+(self.y_diff*pos))
			pos+=1
			
	
	
	def setselected(self, idx):
		self.currentindex=idx
		self.setpage(self.currentindex)
	
	def next(self):
		if self.button_count == 0: return
		
		idx=self.currentindex
		idx+=1
		
		if idx==-1:
			idx=self.button_count-1
		if idx==self.button_count:
			idx=0
		
		self.currentindex=idx
		self.setpage(self.currentindex)
	def previous(self):
		if self.button_count == 0: return
		
		idx=self.currentindex
		idx-=1
			
		if idx==-1:
			idx=self.button_count-1
		if idx==self.button_count:
			idx=0
		
		self.currentindex=idx
		self.setpage(self.currentindex)
	def getselected(self):
		return self.currentindex
	
	def checkinput (self, event):
		#Mouse stuff but only if touch is enabled
		if touchenabled:
			if event.type == MOUSEBUTTONDOWN:
				for x in range (self.offset, self.offsetto):
			
					if self.buttons[x].getrect().collidepoint(pygame.mouse.get_pos()):
						self.buttons[x].GetSetOver(True)
						self.setselected(x)
						return
				
				for x in range (0, 3):				
					if self.ctrl_buttons[x].getrect().collidepoint(pygame.mouse.get_pos()):
						self.ctrl_buttons[x].GetSetOver(True)

					
			if event.type == MOUSEBUTTONUP:
				
				for x in range (self.offset, self.offsetto):
					if self.buttons[x].getrect().collidepoint(pygame.mouse.get_pos()):
						self.RunAction(x)
						return
				
				for x in range (0, 3):
					self.ctrl_buttons[x].GetSetOver(False)
					if self.ctrl_buttons[x].getrect().collidepoint(pygame.mouse.get_pos()):
						
						if x == 0: self.next()
						if x == 1: self.previous()
						if x == 2: set_mode(1); return
		
		if event.type == pygame.KEYDOWN:
			if event.key == pygame.K_UP:
				self.previous()
			if event.key == pygame.K_DOWN:
				self.next()
			if event.key == pygame.K_RETURN:
				self.RunAction(self.currentindex)
				return
		
		
	def RunAction(self, index_b):
		self.buttons[index_b].RunAction()

class RenderListViewItem:
	def __init__ (self, size=None, icon=None, Title="", Desc="", Key="", action=None, enabled=True, border=4):
		self.over=False
		if size==None: size=(250,50)	
		self.b_width=size[0]
		self.b_height=size[1]
		
		self.enabled=enabled
		
		self.font = pygame.font.Font(None, buttonfontsize-5)
		self.font_sm = pygame.font.Font(None, buttonfontsize_sm)
		
		self.previewicon_size=(40,40)
		
		if icon==None:
			pass
			self.button_icon=None
			#icon=os.path.join(resourcesdir, "icon_folder.png")
		else:
			self.button_icon = pygame.image.load(icon).convert_alpha()
			self.button_icon = pygame.transform.scale(self.button_icon, self.previewicon_size) 
		
		
		if border == 0: # no border
			self.item_off_image = GetRoundedRectSurface((0,0,size[0],size[1]),  buttoncolor  ,0.2)
			self.item_on_image = GetRoundedRectSurface((0,0,size[0],size[1]),  buttonhighlightcolor,0.2)
			
		else:
			self.item_off_image = GetRoundedRectSurface((0,0,size[0],size[1]), buttonbordercolor  ,0.2)
			self.item_on_image = GetRoundedRectSurface((0,0,size[0],size[1]),  buttonbordercolor    ,0.2)
			
			#blitt inner over outer, makes a nice border...
			inner = GetRoundedRectSurface((0,0,size[0]-border,size[1]-border), buttoncolor ,0.2)
			inner_over = GetRoundedRectSurface((0,0,size[0]-border,size[1]-border), buttonhighlightcolor ,0.2)
								
			#then inner button color
			self.item_off_image.blit(inner,((border/2),(border/2)))
			self.item_on_image.blit(inner_over,((border/2),(border/2)))
		
		self.Title=Title
		self.Desc=Desc
		
		self.Key=Key
		
		self.action=action
		
		self.RenderSurface()
	
	def getenabled(self):
		return self.enabled
	
	def getrect(self):
		return (Rect(self.posx, self.posy, self.b_width, self.b_height))
	
	def RenderSurface(self):	
		#prep and render font
		
		#create top and bottom text

		self.button_text_name = self.font.render(self.Title, 1, buttonfontcolor)
		self.button_text_desc = self.font_sm.render(self.Desc, 1, buttonfontcolor)
		
		
		#create surfaces for normal and over state
		self.button_surface = pygame.Surface((self.b_width, self.b_height)).convert_alpha()
		self.button_surface_over = pygame.Surface((self.b_width, self.b_height)).convert_alpha()

		self.button_surface.fill((255, 255, 255,0)) # 4 = 0 for full alpha
		self.button_surface_over.fill((255, 255, 255,0)) # 4 = 0 for full alpha
	

		self.button_surface.blit(self.item_off_image,(0,0))
		self.button_surface_over.blit(self.item_on_image,(0,0))
		
		
		if self.button_icon == None:
			icon_x_dist=10
		
		else:
			icon_x=10
			icon_y=5
			icon_x_dist=icon_x+self.previewicon_size[0]+5
			
			self.button_surface.blit(self.button_icon,(icon_x,icon_y))
			self.button_surface_over.blit(self.button_icon,(icon_x,icon_y))
		
		self.button_surface.blit(self.button_text_name,(icon_x_dist,10))
		self.button_surface.blit(self.button_text_desc,(icon_x_dist,35))
		
		self.button_surface_over.blit(self.button_text_name,(icon_x_dist,10))
		self.button_surface_over.blit(self.button_text_desc,(icon_x_dist,35))
		
	def draw(self, x,y):
		self.posx=x
		self.posy=y
		if self.over:
			screen.blit(self.button_surface_over,(x,y))
		else:
			screen.blit(self.button_surface,(x,y))
	def draw_over(self):
		screen.blit(self.button_surface_over,(self.posx,self.posy))
		
	def GetSetOver(self, over=None):
		if over==None:
			return self.over
		else:
			self.over=over
	
	def RunAction(self):
		exec self.action	

class ScreenActivity:
	def __init__(self, screensaver_timeout_sec=30, screenblank_timeout_sec=180):
		#timeout in seconds
		self.timeoutscreensaver=screensaver_timeout_sec
		self.timeoutscreenblank=screenblank_timeout_sec
		
		self.inactivecounter=0
		
		self.screensaver=False
		self.screenblank=False
		
		self.enabled=True
		
	def run(self, seconds):
		if self.enabled==False:
			return
		
		self.inactivecounter+=seconds
		if (round(self.inactivecounter,0)==self.timeoutscreensaver) and (self.screensaver==False):
			 #print "ScreenSaver Trigger"
			 self.screensaver=True
		if (round(self.inactivecounter,0)==self.timeoutscreenblank) and (self.screenblank==False):
			 #print "Screen OFF Trigger"
			 self.screenblank=True
			 self.screenoff(self.screenblank)
		
	def screenoff(self, state):
		if state:
			os.system("./pitft off")
		else:
			os.system("./pitft on")
	
	def reset(self):
		#print "Activity detected... resetting counter"
		self.inactivecounter=0
		self.screensaver=False
		
		if self.screenblank:
			self.screenblank=False
			self.screenoff(self.screenblank)

class PygameCustomEvents:
	def __init__(self):
		self.lmcount=0
		self.longpressticks = 30 #ticks for long press to be realise
		#self.swipedistancemin = 100 #min distance in px for swipe detection
		min_swipedistance_x_percent = 0.3 #swipe distance in % of screensize h
		min_swipedistance_y_percent = 0.3 #swipe distance in % of screensize w
		self.swipedistx = pygame.display.Info().current_w*min_swipedistance_x_percent
		self.swipedisty =  pygame.display.Info().current_h*min_swipedistance_y_percent
	
	def setswipe(self):
		x,y=pygame.mouse.get_rel()
	
	def checkswipe(self):
		x,y=pygame.mouse.get_rel()
		#print x,y
		
		if abs(x)<=self.swipedistx: 
			if abs(y)<=self.swipedisty: 
				#no swipe detected
				return False
			elif y>self.swipedisty: 
				#swiped topdown
				pygame.event.clear()
				pygame.event.post(pygame.event.Event(SWIPE, {'type':'SWIPE','direction':'TD'}))
				return True
			elif y<-self.swipedisty: 
				#swiped bottomup
				pygame.event.clear()
				pygame.event.post(pygame.event.Event(SWIPE, {'type':'SWIPE','direction':'BU'}))
				return True
			
		elif abs(y)<=self.swipedisty: 
			if x>self.swipedistx: 
				#swiped lefttoright
				pygame.event.clear()
				pygame.event.post(pygame.event.Event(SWIPE, {'type':'SWIPE','direction':'LR'}))
				return True
			elif x<-self.swipedistx: 
				#swiped righttoleft
				pygame.event.clear()
				pygame.event.post(pygame.event.Event(SWIPE, {'type':'SWIPE','direction':'RL'}))
				return True
		return False
		
	
	def checklongpress(self):
		m1,m2,m3 = pygame.mouse.get_pressed()
		
		if m1 == 1:
			
			self.lmcount=self.lmcount+1
			if self.lmcount==self.longpressticks:
				#print "long press event"
				evt = pygame.event.Event(MOUSELONGPRESS, {'mousebutton':1})
				pygame.event.post(evt)

		else:
			self.lmcount=0
# not used, testing with PITFT
class pitft:
    screen = None;
    colourBlack = (0, 0, 0)
 
    def __init__(self):
        "Ininitializes a new pygame screen using the framebuffer"
        # Based on "Python GUI in Linux frame buffer"
        # http://www.karoltomala.com/blog/?p=679
        disp_no = os.getenv("DISPLAY")
        if disp_no:
            print "I'm running under X display = {0}".format(disp_no)
 
        os.putenv('SDL_FBDEV', '/dev/fb1')
 
        # Select frame buffer driver
        # Make sure that SDL_VIDEODRIVER is set
        driver = 'fbcon'
        if not os.getenv('SDL_VIDEODRIVER'):
            os.putenv('SDL_VIDEODRIVER', driver)
        try:
            pygame.display.init()
        except pygame.error:
            print 'Driver: {0} failed.'.format(driver)
            exit(0)
 
        size = (pygame.display.Info().current_w, pygame.display.Info().current_h)
        self.screen = pygame.display.set_mode(size, pygame.FULLSCREEN)
        # Clear the screen to start
        self.screen.fill((0, 0, 0))
        # Initialise font support
        pygame.font.init()
        # Render the screen
        pygame.display.update()
 
    def __del__(self):
        "Destructor to make sure pygame shuts down, etc."
			
def blit_alpha(target, source, location, opacity):
        x = location[0]
        y = location[1]
        temp = pygame.Surface((source.get_width(), source.get_height())).convert()
        temp.blit(target, (-x, -y))
        temp.blit(source, (0, 0))
        temp.set_alpha(opacity)        
        target.blit(temp, location)
		
def GetRoundedRectSurface(rect,color,radius=0.4, topleft=True, bottomleft=True, topright=True, bottomright=True):
	rect         = Rect(rect)
	color        = Color(*color)
	alpha        = color.a
	color.a      = 0
	pos          = rect.topleft
	rect.topleft = 0,0
	rectangle    = pygame.Surface(rect.size,SRCALPHA)
	radius_save  = radius
	
	circle       = pygame.Surface([min(rect.size)*3]*2,SRCALPHA)
	pygame.draw.ellipse(circle,(0,0,0),circle.get_rect(),0)

	try:
		circle       = pygame.transform.smoothscale(circle,[int(min(rect.size)*radius)]*2)
	except:
		circle       = pygame.transform.scale(circle,[int(min(rect.size)*radius)]*2)
	
	# This to simulate not smoothscale options ... like on the pi :(
	#circle       = pygame.transform.scale(circle,[int(min(rect.size)*radius)]*2)
	
	#creating the circle surface / radius ! BLIT is allready TOPLEFT if you want to overwrite it, needs to be blitted again... (not border)
	radius              = rectangle.blit(circle,(0,0))
	if not topleft: pygame.draw.rect(rectangle, (0,0,0), radius, 0)
	
	radius.bottomright  = rect.bottomright
	rectangle.blit(circle,radius)
	if not bottomright: pygame.draw.rect(rectangle, (0,0,0), radius, 0)
	
	radius.topright     = rect.topright
	rectangle.blit(circle,radius)
	if not topright: pygame.draw.rect(rectangle, (0,0,0), radius, 0)
	
	radius.bottomleft   = rect.bottomleft
	rectangle.blit(circle,radius)
	if not bottomleft: pygame.draw.rect(rectangle, (0,0,0), radius, 0)

	rectangle.fill((0,0,0),rect.inflate(-radius.w,0))
	rectangle.fill((0,0,0),rect.inflate(0,-radius.h))

	rectangle.fill(color,special_flags=BLEND_RGBA_MAX)
	rectangle.fill((255,255,255,alpha),special_flags=BLEND_RGBA_MIN)

	return rectangle #.blit(rectangle,pos)

def GetWindowSurface(size):
	r=0.04
	bc_off=pygame.Color('#bbbbbb')#buttoncolor
	bbc=buttonbordercolor
	border = 4
	
	outer = GetRoundedRectSurface((0,0,size[0],size[1]), bbc ,r, True, True, True, True)
	inner = GetRoundedRectSurface((0,0,size[0]-border,size[1]-border), bc_off ,r, True,True, True, True)

	#blitt inner over outer, makes a nice border...
	outer.blit(inner,((border/2),(border/2)))
	
	return outer

# draw some text into an area of a surface, automatically wraps words returns any text that didn't get blitted
def drawTextSurface(surface, text, color, rect, font, aa=False, bkg=None):
	rect = Rect(rect)
	y = rect.top
	lineSpacing = -2

	# get the height of the font
	fontHeight = font.size("Tg")[1]
 
	while text:
		i = 1

		# determine if the row of text will be outside our area
		if y + fontHeight > rect.bottom:
			break

		# determine maximum width of line
		while font.size(text[:i])[0] < rect.width and i < len(text):
			i += 1

		# if we've wrapped the text, then adjust the wrap to the last word      
		if i < len(text): 
			i = text.rfind(" ", 0, i) + 1

		# render the line and blit it to the surface
		if bkg:
			image = font.render(text[:i], 1, color, bkg)
			image.set_colorkey(bkg)
		else:
			image = font.render(text[:i], aa, color)

		surface.blit(image, (rect.left, y))
		y += fontHeight + lineSpacing

		# remove the text we just blitted
		text = text[i:]
	return text
	
def aspect_scale(img,(bx,by)):
	# Scales 'img' to fit into box bx/by. This method will retain the original image's aspect ratio
	ix,iy = img.get_size()
	scaled = None

	if ix > iy:
		# fit to width
		scale_factor = bx/float(ix)
		sy = scale_factor * iy
		if sy > by:
			scale_factor = by/float(iy)
			sx = scale_factor * ix
			sy = by
		else:
			sx = bx
	else:
		# fit to height
		scale_factor = by/float(iy)
		sx = scale_factor * ix
		if sx > bx:
			scale_factor = bx/float(ix)
			sx = bx
			sy = scale_factor * iy
		else:
			sy = by

	try:
		scaled = pygame.transform.smoothscale(img, (int(sx),int(sy)))
	except:
		scaled = pygame.transform.scale(img, (int(sx),int(sy)))
	return scaled

def getlastpic(folder):
	my_pics = ['.jpg', '.png', '.gif']
	try:
		file = os.path.join(folder, sorted([ name for name in os.listdir(folder) if os.path.isfile(os.path.join(folder,name))])[-1])
		
		fileName, fileExtension = os.path.splitext(file)
		if not fileExtension.lower() in my_pics:
			file=None
	except:
		thumbfile=None
	
	return file
	
def InitFolderList(path, list, thumbs=True, filesandfolders=True):
	my_pics = ['.jpg', '.png', '.gif']
		
	
	if filesandfolders == True:
		#ALL	
		onlyfiles = [ os.path.join(path,file) for file in os.listdir(path) ]
	else:
		#FOLDERS only
		onlyfiles = [ os.path.join(path,file) for file in os.listdir(path) if os.path.isdir(os.path.join(path,file))]
	
	
	for file in onlyfiles:
		
		isfolder=False
		enabled=True
		
		if os.path.isfile(file): 
			isfolder=False
		elif os.path.isdir(file):
			isfolder=True
		else:
			return "No file / Folder, incorrect path..."
		
		if isfolder:
			#get folder details
			#first, get folder thumbnail
			
			#DO NOT get thumbfile if currently recording into the folder
			if mjpgCam.is_running and mjpgCam.tlfolder_full  == file:
				thumbfile=None
				recstr="REC: "
				enabled=False
			else:
				recstr=""
				try:
					thumbfile= os.path.join(file, sorted([ name for name in os.listdir(file) if os.path.isfile(os.path.join(file,name))])[-1])
					
					fileName, fileExtension = os.path.splitext(thumbfile)
					if not fileExtension.lower() in my_pics:
						thumbfile=None
				except:
					thumbfile=None
			
			if thumbs==False: thumbfile=None
			
			filecount = len([name for name in os.listdir(file) if os.path.isfile(os.path.join(file,name))])
			totalsize =  helpers.bytes2human(sum(os.path.getsize(os.path.join(file,name)) for name in os.listdir(file) if os.path.isfile(os.path.join(file,name))))
			name = recstr+os.path.basename(file)
			date = time.strftime('%d.%m.%Y', time.gmtime(os.path.getmtime(file)))
			
			list.AddItem((250,50), thumbfile , name , "Folder: " +str(filecount)+" f, "+ totalsize + ", " + date, file, "FileListClick(self.Key)", enabled)

		else:
			#get files details
			filesize =helpers.bytes2human(os.path.getsize(file))
			name = os.path.basename(file)
			date = time.strftime('%d.%m.%Y', time.gmtime(os.path.getmtime(file)))
			
			fileName, fileExtension = os.path.splitext(file)
			if not fileExtension.lower() in my_pics:
				thumbfile=None
			else:
				thumbfile= file
			
			if thumbs==False: thumbfile=None
			
			list.AddItem((250,50), thumbfile , name , "File: "+ filesize + ", "+ date, file, "FileListClick(self.Key)", enabled)
		
def FileListClick(item):
	print item
	
def initscreen(width, height) :
	
	#Initialisation	
	pygame.init()
	
	if headless:
		#will not anymore be enabled as pygame will not init the screen if headless
		
		os.putenv('SDL_VIDEODRIVER', 'dummy')
		screen = pygame.display.set_mode((1,1))
		
		size = (pygame.display.Info().current_w, pygame.display.Info().current_h)
		print "Pygame interface started in dummy mode, framebuffer size: %d x %d" % (size[0], size[1])
		
	else:
	
		#init screen / window or fullscreen
		if windowed:
			#window mode with w and h submitted to the function
			screen = pygame.display.set_mode((width,height),0,32)
			pygame.display.set_caption(mytitle)
			
			size = (pygame.display.Info().current_w, pygame.display.Info().current_h)
			print "Pygame interface started in window mode, framebuffer size: %d x %d" % (size[0], size[1])
		else:
			#if FS PUT fb1 as the framebuffer device => pitft, res, 320 x 240
			# 29.03.2015... not working anymore on the pitft... with PRE "export SDL_FBDEV=/dev/fb1" IT WORKS!
			
			os.environ["SDL_FBDEV"] = "/dev/fb1"
			os.environ["SDL_MOUSEDRV"] = "TSLIB"
			os.environ["SDL_MOUSEDEV"] = "/dev/input/touchscreen"
			
			#os.putenv('SDL_VIDEODRIVER', 'fbcon')
			#os.putenv('SDL_FBDEV'      , '/dev/fb1')
			#os.putenv('SDL_MOUSEDRV'   , 'TSLIB')
			#os.putenv('SDL_MOUSEDEV'   , '/dev/input/touchscreen')

			#screen = pygame.display.set_mode((0,0), pygame.FULLSCREEN) #not working anymore...
			screen = pygame.display.set_mode([320, 240], pygame.FULLSCREEN) #try like so OR without FS Flag?
			
			size = (pygame.display.Info().current_w, pygame.display.Info().current_h)
			print "Pygame interface started in fullscreen mode, framebuffer size: %d x %d" % (size[0], size[1])
	
	return screen

def initPyGame():
	global clock, screen, ScreenTimer, background, mystatusbar, mainmenu, campreviewmenu, mynotism, mynotiwait, current_w, current_h, my_logo, mymonitorscreen, mainmenucontrol, mainmenuscreen, mySimpleDialog
	
	screen = initscreen(320, 240)
	clock = pygame.time.Clock()

	#Hide mouse
	if mousevisible == False:
		pygame.mouse.set_visible(False)
	
	#disable motion tracking for events
	pygame.event.set_blocked(pygame.MOUSEMOTION)

	#setup pygame to enable key presses / repeats
	pygame.key.set_repeat(100, 100)

	#get current window  /screen size
	current_w = pygame.display.Info().current_w #background.get_width()
	current_h = pygame.display.Info().current_h
 
	
	#Render Background
	background = pygame.Surface((320,240)) 
	background.fill(bgcolor)
	
	#render UM Logo on top of BG (bottom, right)
	my_logo = pygame.image.load(os.path.join(resourcesdir, "logo_ori.png")).convert_alpha()
	my_logo.fill((buttonbordercolor.r, buttonbordercolor.g, buttonbordercolor.b , 0), special_flags = BLEND_RGBA_MAX) #blend logo to dark grey
	my_logo.fill((215, 215, 215 , 0), special_flags = BLEND_RGBA_MAX) #blend logo to white
	background.blit(my_logo,(185,200))
		
	initUpdateStatus("icon_menu-50.png", "Creating Menu structure...")
	
	#Initstatus SCREEN DONE
	
	mainmenuscreen=RenderMenuScreen()
	#draw once to init 
	mainmenuscreen.visible = True
	mainmenuscreen.draw()
	mainmenuscreen.visible = False
		
	campreviewmenu = RenderMenu(False, False)
	campreviewmenu.AddButton(os.path.join(resourcesdir, "icon_back-50.png"), "", "set_mode(1)",  size=(68,25), xb=247, yb=5 )
	campreviewmenu.AddButton(os.path.join(resourcesdir, "icon_refresh-50.png"), "", "set_mode(2)",  size=(68,25), xb=247, yb=35)
	
	mynotism = RenderNotification((300,40))
	mynotiwait = RenderNotification((300,40))
	
	mystatusbar = RenderStatusBar()
	
	mymonitorscreen = RenderMonitorScreen()
	
	#Simple Dialog object
	mySimpleDialog = RenderSimpleDialog()
	
	#Sreensaver / Activity timer
	ScreenTimer = ScreenActivity()
	
	info_sm = False

def initUpdateStatus (icon_file, text):
	global current_w, current_h, background, screen
	
	#re-fill surface with bg colorr
	screen.blit(background, (0,0))
	
	myicon = pygame.image.load(os.path.join(resourcesdir, icon_file)).convert_alpha()
	
	#center it
	icon_x = (current_w/2)-(myicon.get_width()/2)
	icon_y = (current_h/2)-(myicon.get_height()/2) - 50
	
	screen.blit(myicon,(icon_x,icon_y))
	
	font = pygame.font.Font(None, generalfontsize)
	text_surface = font.render(text, 1, generalfontcolor)
	
	text_x = (current_w/2)-(text_surface.get_width()/2)
	text_y = icon_y + myicon.get_height() + 10 
	
	screen.blit(text_surface,(text_x,text_y))
	
	#update the screen
	pygame.display.update()
	#and wait x ms to ensure readability	#pygame.event.wait() could also be used to test stuff
	pygame.time.delay(150)

def inc_mode(val):
	global current_screen, screens
	current_screen = current_screen + val
	if current_screen == 0: current_screen = len(screens)
	if current_screen > len(screens): current_screen = 1
	set_mode(current_screen)
		
def set_mode(mymode):
	global screens, current_screen, mylist
	
	mode=screens[mymode]
	current_screen=mymode
	
	print mode
	
	if mode=="Home":
		pass
	
	if mode=="Timelapse folders":
		
		mynotiwait.triggershow_fix("loading directory ...please wait.")
		mynotiwait.show_fix()
		pygame.display.update()
		
		mylist=RenderListView()
		InitFolderList(path=os.path.join(timelapsedir), list=mylist, thumbs=True, filesandfolders=True)
		mynotiwait.hide_fix()
		#mynotism.triggershow(1, "feature disabled")
		#set_mode("MAIN")
	if mode=="Camera preview":
		if not mjpgCam.connected:
			mynotism.triggershow(1, "Camera NOT connected, can't start.")
			#set_mode(1)
		else:
			mynotiwait.triggershow_fix("generating preview ...please wait.")
			mynotiwait.show_fix()
			pygame.display.update()
			
			#cam_preview.updatesurface()
			mjpgCam.UpdatePygameSurface()
			
			#also update the background picture!
			mjpgCam.BlitPygameSurface(background)
			background.blit(my_logo,(185,200))
			
			mynotiwait.hide_fix()
			
def PyInterfaceMainLoop():
	milliseconds = clock.tick(30)  # milliseconds passed since last frame
	seconds = milliseconds / 1000.0 # seconds passed since last frame (float)
	
	#handle mouse click events when they happen (register long presses)
	custevt.checklongpress()
	
	for event in pygame.event.get():
		

		#reset the activity counter here if any events come in... (mouse, keyboard, whatever)
		#this will only do it if screenblank is on and then we will swallow the first input with break
		if ScreenTimer.screenblank:
			ScreenTimer.reset()
			#pygame.event.clear()
			break
		
		#EXIT Event
		if event.type == QUIT:	
			EndMe(True)
		
		if event.type == MOUSELONGPRESS:
			print "Mouse Longpress Event, Key: "+str(event.mousebutton)
		
		
		if event.type == SWIPE:
			print "Swipe Event, direction: " +event.direction
			
			if not mainmenuscreen.visible:
				pass
				#if event.direction == "LR": inc_mode(-1)
				#if event.direction == "RL": inc_mode(1)
		
		if event.type == pygame.MOUSEBUTTONDOWN:
			custevt.setswipe()
		
		if event.type == pygame.MOUSEBUTTONUP:
			if custevt.checkswipe():
				break
				

		#Standard KEYS	Events
		if event.type == pygame.KEYDOWN:
			
			if event.key == pygame.K_q:
				PrintIsStartingDialog()
				#resultQ.put({"CMD": "COMMAND", "DO": "PRINTSTART"})

			if event.key == pygame.K_w:
				resultQ.put({"CMD": "COMMAND", "DO": "PRINTSTOP"})
			
			if event.key == pygame.K_x:
				EndMe(True)
			
			if event.key == pygame.K_ESCAPE:
				EndMe(True)
				
			if event.key == pygame.K_i:
				mynotism.triggershow(2, " FPS: " + str(int(clock.get_fps())))
		
		
		if mySimpleDialog.visible: mySimpleDialog.checkinput(event); break
		
		#allways check for input on statusbar menu button... IF NOT a Dialog is active :)
		mystatusbar.checkinput(event)
				
		if mainmenuscreen.visible: mainmenuscreen.checkinput(event); break
		if screens[current_screen]=="Timelapse folders": mylist.checkinput(event); break
		if screens[current_screen]=="Camera preview": campreviewmenu.checkinput(event)
	
	
	ScreenTimer.run(seconds)
	#Activate Screensaver if required
	if ScreenTimer.screensaver:
		pass
		#print "screensaver kicked in..." COULD DIM Screen here or SCreensaver or else...
	
			
	#draw according to current menu postion / mode
	if screens[current_screen] == "Home":	screen.blit(background, (0,0)); mymonitorscreen.draw() 
	if screens[current_screen] ==  "Timelapse folders":	screen.blit(background, (0,0)); mylist.draw()
	if screens[current_screen] ==  "Camera preview":	
		if mjpgCam.connected:
			mjpgCam.BlitPygameSurface(screen)
		else:
			screen.blit(background, (0,0))
		campreviewmenu.draw()
	
	#allways draw statusbar
	mystatusbar.draw()
	
	#draw menu over if visible is set...
	if mainmenuscreen.visible: mainmenuscreen.draw()
	
	#Draw mySimpleDialog over if visible
	if mySimpleDialog.visible: mySimpleDialog.draw()
	
			
	#render only once triggered for amount of time
	mynotism.show(seconds)
	mynotiwait.show_fix()
	
	t.run()

	pygame.display.update()
		
#General DEFs go here------------------------------------------------------------------------------------------------------
def getcmdlineargs(argv):
	global headless
	global windowed
	global mousevisible
	
	options, rest = getopt.getopt(argv, ':hfm', ['headless', 'fullscreen', 'hidemouse'])
	print 'OPTIONS   :', options

	for opt, arg in options:
		if opt in ('-h', '--headless'):
			headless = True
		elif opt in ('-f', '--fullscreen'):
			windowed = False
		elif opt in ('-m', '--hidemouse'):
			mousevisible = False

	print 'headless   :', headless
	print 'windowed   :', windowed
	print 'mousevisible   :', mousevisible

def ToggleTimeLapse(setfoldername = ""):
	
	if mjpgCam.is_running:
		mjpgCam.stop()
	
		if headless == False:
			mainmenuscreen.mainmenu.updatebuttontext(3,"start timelapse")
		print "Timelapse Stopped"
	else:
		if mjpgCam.connected:
			mjpgCam.starttimelapse(setfoldername)
			print "Timelapse Started"

			if headless == False:
				mainmenuscreen.mainmenu.updatebuttontext(3,"stop timelapse")
		else:
			if headless == False:
				mynotism.triggershow(1, "Camera NOT connected, can't start.")

def TakePicture():
	
	if mjpgCam.connected:
		
		if headless == False: 
			mynotiwait.triggershow_fix('Taking picture...please wait.')
			mynotiwait.show_fix()
			pygame.display.update()
		
		mjpgCam.TakeScreenShot()
		
		if headless == False: 
			mynotiwait.hide_fix()
			mainmenuscreen.toggle()
	else:
		if headless == False: 
			mynotism.triggershow(1, "Camera NOT connected, can't take picture.")
				
def EndMe(exit):
	
	if headless == False: ScreenTimer.reset()
	if mjpgCam.is_running: mjpgCam.stop()
	
	if headless == False:
		periodic.stop()
	serialscheduler.stop()
	
	tornado_main_loop.stop()
	
	sp.close()
	try:
		gpioP.close()
	except NameError:
		pass
	
	pygame.quit()
	
	if exit == True:
		print "All closed...Bye Bye!"
		sys.exit()

def CreatePrintIsStartingSurface(surf):
	fnt=pygame.font.Font(None, generalfontsize+5)
	fnt_big=pygame.font.Font(None, generalfontsize+10)
	fnt_huge=pygame.font.Font(None, generalfontsize+80)
	#drawTextSurface(surf, "Testing", lightfontcolor, (10,45,300,120), fnt, aa=False, bkg=pygame.Color('#bbbbbb'))
	
	#monitor changes in the for the TL Autostart button
	UpdateTLAutostartButtonText()
	
	#Fill the variables...
	printer_status = printerstatus["status"]
	printer_file = printerstatus["file"][0] + " (" + helpers.bytes2human(printerstatus["file"][1]) + ")"
	printer_nozzle = str(printerstatus["temp"][0]) + " / " + str(printerstatus["temp"][1])
	#printer_nozzle = "195.0 / 200.0"
	printer_HB = str(printerstatus["temp"][2]) + " / " + str(printerstatus["temp"][3])
	#printer_HB = "45.1 / 65.0"
	printer_countdown=printerstatus["print_start_countdown"]
	
	
	#if the countdown is starting display it
	temp_surf=fnt_big.render("Starting print in: ", True, generalfontcolor, pygame.Color('#bbbbbb'))
	textpos = temp_surf.get_rect()
	textpos.x = 15
	textpos.centery = 70
	surf.blit(temp_surf, textpos)

	if not printer_countdown == -1:
		printer_countdown_str=str(printer_countdown)
		cd_col=button_yellow
	else:
		printer_countdown_str="?"
		cd_col=lightfontcolor
		
	
	temp_surf=fnt_huge.render(printer_countdown_str, True, cd_col, pygame.Color('#bbbbbb'))
	textpos = temp_surf.get_rect()
	textpos.centerx = 240
	textpos.centery = 70
	surf.blit(temp_surf, textpos)

		
	#Blit the variables to the screen
	surf.blit(fnt.render(printer_status, True, darkfontcolor, pygame.Color('#bbbbbb')),(15,110))
	surf.blit(fnt.render("SD-File: "+printer_file, True, generalfontcolor, pygame.Color('#bbbbbb')),(15,130))

	title_surf=fnt.render("T1: ", True, generalfontcolor, pygame.Color('#bbbbbb'))
	surf.blit(title_surf,(15,150))
	title_nozzle=fnt.render(printer_nozzle, True, darkfontcolor, pygame.Color('#bbbbbb'))
	
	surf.blit(title_nozzle,(15+title_surf.get_width(),150))
	dist=15+title_surf.get_width()+20+title_nozzle.get_width()

	title_surf=fnt.render("HB: ", True, generalfontcolor, pygame.Color('#bbbbbb'))
	surf.blit(title_surf,(dist,150))
	surf.blit(fnt.render(printer_HB, True, darkfontcolor, pygame.Color('#bbbbbb')),(dist+title_surf.get_width(),150))
	
	
	
	return surf

def ToggleTLAutostart():
	if cfg.settings["General"]["tl_autostart"] == "True":
		cfg.settings["General"]["tl_autostart"] = "False"
	else:
		cfg.settings["General"]["tl_autostart"] = "True"
	
	cfg.Save()

def UpdateTLAutostartButtonText():
	if cfg.settings["General"]["tl_autostart"] == "True":
		button_text = "TL auto: ON"
	else:
		button_text = "TL auto: OFF"

	mySimpleDialog.set_button_text(1, button_text)
	
def PrintIsStartingDialog():
	mySimpleDialog.reset()
	mySimpleDialog.name="printstart"
	mySimpleDialog.set_window_title("Printer is heating up to print")	
	mySimpleDialog.add_button(None, "close", "mySimpleDialog.toggle();" ,(60,40), 10)
	
	if cfg.settings["General"]["tl_autostart"] == "True":
		button_text = "TL auto: ON"
	else:
		button_text = "TL auto: OFF"
	
	mySimpleDialog.add_button(None, button_text , "ToggleTLAutostart(); " , (110,40), 200, col=button_red, col_over=button_red_on)
	
	mySimpleDialog.add_button(None, "manual start", 'taskQ.put({"CMD": "STARTMANUAL", "DATA": ""}); ', (110,40), 85)
	
	mySimpleDialog.set_specialsurface_function(CreatePrintIsStartingSurface)
	mySimpleDialog.visible = True

def PowerOptionsDialog():
	mySimpleDialog.reset()
	mySimpleDialog.name="poweroptions"
	mySimpleDialog.set_window_title("Power options")
	mySimpleDialog.set_text("What would you like to do? If you shut your raspberry pi down you will need to also unplug the usb power adapter. Restarting will bring you back into the application.")
	
	mySimpleDialog.add_button(None, "Cancel", "mySimpleDialog.toggle();" ,(60,40), 10)
	mySimpleDialog.add_button(os.path.join(resourcesdir, "icon_shutdown-50.png"), "Shutdown", "ShutdownServer(); mySimpleDialog.toggle(); mainmenuscreen.toggle()" , (110,40), 85, col=button_red, col_over=button_red_on)
	mySimpleDialog.add_button(os.path.join(resourcesdir, "icon_restart-50.png"), "Restart", "RestartServer(); mySimpleDialog.toggle(); mainmenuscreen.toggle()", (110,40), 200, col=button_green, col_over=button_green_on)
	
	#mySimpleDialog.set_button_text(0, "Go away!")
	#mySimpleDialog.set_button_text(1, "HA!")
	
	#mySimpleDialog.set_button_action(0, 'print "What the fuck, I am unloading..."; mySimpleDialog.toggle();')
	#mySimpleDialog.set_button_action(1, 'print "OKAY";')
	
	#mySimpleDialog.remove_button(1)
	#mySimpleDialog.remove_all_buttons()
	
	mySimpleDialog.visible = True

def RestartServer():
	print "Restarting Server"
	EndMe(False)
	os.system("sudo reboot")
	sys.exit

def CleanArg(arg, default):
	temp=str(arg)[2:-2]
	if temp == "":
		return default
	else:
		return temp
	
def SendGcodeSpecial(args):
	cmd = CleanArg(args['command'], "")

	if cmd == "FULLSTOP":
		SendGodeLog("M25") #Pause
		SendGodeLog("M26 S0") #Reset file Position
		
		SendGodeLog("M107") #FAN OFF
		SendGodeLog("M104 S0") #extruder heater off
		SendGodeLog("M140 S0") #heated bed heater off (if you have it)
		
		SendGodeLog("G91") #relative positioning
		SendGodeLog("G1 E-1 F300") #retract the filament a bit before lifting the nozzle, to release some of the pressure
		SendGodeLog("G1 Z+0.5 E-5 X-20 Y-20 F9000")#move Z up a bit and retract filament even more
		SendGodeLog("G28 X0 Y0") #move X/Y to min endstops
						
		SendGodeLog("M84") #steppers off
		SendGodeLog("G90") #absolute positioning
		
	
	if cmd == "MOVEREL":
		moveby=CleanArg(args['moveby'], "0")
		axis=CleanArg(args['axis'], "X")
		speed=CleanArg(args['speed'], "")
		
		SendGodeLog("G91")
		SendGodeLog("G1 "+axis+moveby+" "+speed)
		SendGodeLog("G90")

def SendGodeLog(cmd):
	taskQ.put({"CMD": "SERIAL", "DATA": cmd})
	updateSerialLog("sent: "+cmd)
	
def ShutdownServer():
	print "Shuting down"
	EndMe(False)
	os.system("sudo shutdown -h now")
	sys.exit
		
def RestartApplication():
	print "Restarting Application"
	EndMe(False)
	os.execl(sys.executable, *([sys.executable]+sys.argv))
	
def checkSerialQResults():
	global printerstatus
	if not resultQ.empty():
		result = resultQ.get()

		#printer status handler...
		if result["CMD"] == "STATUS":
			printerstatus = result["DATA"]
			#print printerstatus
			
			#react to a change if printer starts to heat up for printing
			if headless == False and printerstatus["isheatingup"]:
				#if any other dialog is open, close it first
				if mySimpleDialog.visible and not mySimpleDialog.name == "printstart":
					mySimpleDialog.toggle()
					
				if not mySimpleDialog.visible:
					#ensure its actually visible ;)
					ScreenTimer.reset()
					ScreenTimer.enabled = False
					PrintIsStartingDialog()
					


		#command handler handler...
		if result["CMD"] == "COMMAND":
			cmd = result["DO"]
	
			if cmd == "PRINTSTART":
				print "PRINTSTART received"
				
				if headless == False:
					#turn the screensaver back ON
					ScreenTimer.enabled = True
					
					#if the print dialog is still visible, hide it
					if mySimpleDialog.visible:
						mySimpleDialog.toggle()
				
				#turn on the lights if desired
				if cfg.settings["General"]["lights_on_onstart"] == "True":
					print "Lights ON"
					SendGodeLog(cfg.settings["Printer"]["gcode_lights_on"])
					
				
				if cfg.settings["General"]["tl_autostart"] == "True" and mjpgCam.connected:
					
					if not mjpgCam.is_running:
						
						if not printerstatus:
							autostarted=True
							ToggleTimeLapse("auto")
						else:
							autostarted=True
							ToggleTimeLapse("auto_"+printerstatus["file"][0])
					else:
						print "TL started, will not stop and restart..."
			
			if cmd == "PRINTSTOP":
				print "PRINTSTOP received"
				
				email_text=""
				email_text_status=""
				email_attachement=None
				
				if printerstatus:
					email_text_status = "Printer file: "+printerstatus["file"][0] + " with " +  helpers.bytes2human(printerstatus["file"][1]) + ".\n" + "Starttime was " + printerstatus["progress_time"][0] + " and it took " + printerstatus["progress_time"][1] + " to print."
				else:
					email_text_status=""
				
				
				#ALSO STOP if NOT autostarted...
				if cfg.settings["General"]["tl_autostop"] == "True" and mjpgCam.connected:				
					if mjpgCam.is_running:
						autostarted=False
						print "TOGGLE (to Stopped)!"
						ToggleTimeLapse()
					
						if cfg.settings["General"]["email_on_complete"] == "True":
							folder=os.path.join(timelapsedir, mjpgCam.getCurrentTLFolder())
														
							filecount = len([name for name in os.listdir(folder) if os.path.isfile(os.path.join(folder,name))])
							totalsize =  helpers.bytes2human(sum(os.path.getsize(os.path.join(folder,name)) for name in os.listdir(folder) if os.path.isfile(os.path.join(folder,name))))
							#lastfile=getlastpic(os.path.join(timelapsedir, mjpgCam.getCurrentTLFolder()))
							
							email_text="Printing Done.\nTaken " + str(filecount) + " pictures and saved them in " + folder + " ("+ totalsize +").\n"
							#email_attachement=lastfile
					

				
				if cfg.settings["General"]["email_on_complete"] == "True":
					
					if mjpgCam.connected and email_attachement==None:
						#take a screenshot if the camera is connected, in the general pic directory						
						#modified to ALLWAYs take a screenshot in the general dir so all prints get documented :) changed toggle tl code above to not include the last file of the TL directory
						email_attachement = os.path.join(generalpicsdir,mjpgCam.TakeScreenShot())
					
					#set default text if empty
					if email_text=="": 
						email_text="Printing Done.\n"
					
					helpers.send_mail_async(cfg.settings["General"]["email_to"], cfg.settings["General"]["email_from"],
												mytitle + " - Printstatus " + datetime.datetime.now().strftime("%d.%B %Y %H:%M"), email_text+email_text_status,	email_attachement,
												cfg.settings["General"]["email_user"], cfg.settings["General"]["email_pw"],
												cfg.settings["General"]["email_server"], int(cfg.settings["General"]["email_server_port"])
												)
								#turn off the lights if desired
				if cfg.settings["General"]["lights_off_oncomplete"] == "True":
					print "Lights OFF"
					SendGodeLog(cfg.settings["Printer"]["gcode_lights_off"])
				
		#SERIAL handler for the serial log interface...
		if result["CMD"] == "SERIAL":
			updateSerialLog("rec: " + result["DATA"])
			print "rec: " + result["DATA"]
			
		#GPIO Result handler
		if result["CMD"] == "GPIO":
			#print "GPIO Data: " + str(result["DATA"])
			pass
		
def updateSerialLog(data):
	if len(serialQ) > (int(cfg.settings["Serial"]["web_serial_ln_buffer"])-1):
		serialQ.pop(0)
	serialQ.append(data)

def MyExtruderTimer():
	print "text"

#Main Program with Main LOOP for Tornado, periodic for serial and if interface enabled periodic for pygame		
if __name__ == '__main__':
		
	#get the dict filled with users (windows and Linux plus find if run with sudo).
	systemuser=helpers.fill_user_system_dict(systemuser)
	print "User " + systemuser["username"] + " (sudo: "+str(systemuser["sudo"])+")" + " on host " + systemuser["hostname"] + " running "+systemuser["system"]
	
	if systemuser["system"] == "Linux" and not systemuser["sudo"]:
		#set it to false even if the GPIO module was sucessfully imported
		systemuser["gpio_enabled"]=False
		print "This program needs elevated priviliges to access GPIOs. Try 'sudo'. GPIO access disabled."
	
	# Get commandline options...
	getcmdlineargs(sys.argv[1:])
	
	#startup from here
	print ""
		
	if headless == False:
		initPyGame()
		#init class to check for custom mouse events...
		custevt=PygameCustomEvents()
	
	#create worker thread for timer, timeout in s and call to def NOT WORKING CORRECTLY, needs work...
	#t = helpers.MyTimer(10, MyTimer)
	#t.start()
	
	# Timer based on pygame, so loop until and reset type
	t=helpers.MySimpleTimer(1,MyExtruderTimer)
	t.intervall = 2
	#t.start()
	
	
	if headless == False:
		initUpdateStatus("icon_settings-50.png", "Reading Settings from "+inifile+"... ")
	
	#Create config object from ini, set defaults and read them
	cfg=helpers.config(inifile)
	cfg.defaults = {"General": {"pics_per_second": "5", "tl_autostart": "False", "tl_autostop": "False",
								"email_on_complete": "False","lights_on_onstart": "False", "lights_off_oncomplete": "False", "email_to": "test@send.com", "email_from": "from@gmail.com", "email_user": "test@gmail.com", "email_pw": "***", 
								"email_server": "smtp.gmail.com", "email_server_port": "587" },
					"Webserver": {"mjpg_ip": "192.168.1.15", "mjpg_port": "8080", "mjpg_urlsnapshot": "/?action=snapshot", "mjpg_urlstream": "/?action=stream", "tornadoport": "8081"},
					"Serial": {"serial_port": "COM1", "serial_baud": "250000", "web_serial_ln_buffer": "250"},
					"Printer": {"x_max_mm": "200", "y_max_mm": "200", "z_max_mm": "195", "gcode_lights_on": "M42 P12 S255", "gcode_lights_off": "M42 P12 S0"}}
					
	cfg.Load()

	#cfg.settings["General"]["pics_per_second"]
	
	if headless == False:
		initUpdateStatus("icon_camera-50.png", "Connecting camera " + cfg.settings["Webserver"]["mjpg_ip"] + ":" + cfg.settings["Webserver"]["mjpg_port"] +"...")
	
	#initcamera
	mjpgCam = mjpegcam.mjpegCamera(cfg.settings["Webserver"]["mjpg_ip"], cfg.settings["Webserver"]["mjpg_port"], cfg.settings["Webserver"]["mjpg_urlsnapshot"], timelapsedir, generalpicsdir , int(cfg.settings["General"]["pics_per_second"]))
	mjpgCam.connect()
	
	if headless == False:
		initUpdateStatus("icon_usb-50.png", "Connecting serial " + cfg.settings["Serial"]["serial_port"] +" @ "+ cfg.settings["Serial"]["serial_baud"] + "...")
	
	#Init the Serial Q, that holds the history up to the defined buffer length, for the web text box
	serialQ=[]
	
	#initialise the Queue object, for handing over tasks / receive results from the serial process (MUST for tornado)
	taskQ = multiprocessing.Queue()
	resultQ = multiprocessing.Queue()
	
	#Serial Interface 
	sp = serialProcess.SerialProcess_mp(cfg.settings["Serial"]["serial_port"], cfg.settings["Serial"]["serial_baud"], .1, taskQ, resultQ)
	#serail: if the port could open then start the daemon, else DON't (Windows...)
	if sp.initOK:
		sp.daemon = True
		sp.start()
	
	
	if systemuser["gpio_enabled"]:
		if headless == False:
			initUpdateStatus("icon_gpio-50.png", "Connecting GPIO Interface...")
			
		#GPIO Process Interface 
		gpioP = gpioProcess.gpioProcess_mp(resultQ)
		if gpioP.initOK:
			gpioP.daemon = True
			gpioP.start()
	
	
	if headless == False:
		initUpdateStatus("icon_cloud-50.png", "Starting Tornado webserver @ "+cfg.settings["Webserver"]["tornadoport"]+"...")

	

	
	application = tornado.web.Application([
	#all commands are sent to http://*:port/com
	#each command is differentiated by the "op" (operation) JSON parameter
	(r"/(com.*)", CommandHandler ),
	(r"/ws/", WebSocketHandler ),
	(r"/", IndexHandler),
	(r"/upload", UploadHandler),
	(r"/(.*\.html)", IndexHandler),
	(r"/(.*\.*)", tornado.web.StaticFileHandler,{"path": cwd }),
	], debug=TornadoDebug, template_path=cwd, queue=taskQ)
	
	if not platform.system() == "Windows":
		application.listen(cfg.settings["Webserver"]["tornadoport"], '0.0.0.0')
	else:
		application.listen(cfg.settings["Webserver"]["tornadoport"])
	
	#application.listen(tornadoport)
	tornado_main_loop = tornado.ioloop.IOLoop.instance()
	if headless == False:
		periodic = tornado.ioloop.PeriodicCallback(PyInterfaceMainLoop, 10, io_loop = tornado_main_loop)
		periodic.start()
	
	#Serial / GPIO Q Monitor
	serialscheduler = tornado.ioloop.PeriodicCallback(checkSerialQResults, 10, io_loop = tornado_main_loop)
	serialscheduler.start()
		
	
	if (headless == False) and mjpgCam.connected:
			initUpdateStatus("icon_camera-50.png", "smile ultimaker, smile ...")
			#if the camera is connected replace the background surface with a cam picture...
			mjpgCam.UpdatePygameSurface()
			mjpgCam.BlitPygameSurface(background)
			background.blit(my_logo,(185,200))
	
	try:
		tornado_main_loop.start()
	except KeyboardInterrupt:
		EndMe(True)
