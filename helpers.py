#  File: helpers.py
#  Description: helper routines for email (threaded), timers, config parsing, diskusage, file system ...
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

import collections
import os
import ConfigParser
import threading
import datetime
import socket
import time

#email
import smtplib
from email.MIMEMultipart import MIMEMultipart
from email.MIMEBase import MIMEBase
from email.MIMEText import MIMEText
from email.MIMEImage import MIMEImage
from email import Encoders


#Linux / Raspi commands -----------------------------------------------------------------------------------------------

#cmd config touch CMD for PiTFT Calibration, resistive type, need tslib
cmd_calibrate_touch="sudo TSLIB_FBDEVICE=/dev/fb1 TSLIB_TSDEVICE=/dev/input/touchscreen ts_calibrate"
cmd_test_touch="sudo TSLIB_FBDEVICE=/dev/fb1 TSLIB_TSDEVICE=/dev/input/touchscreen ts_test"

#cmd mjpeg streamer
cmd_mjpeg_start='./mjpg_streamer -i "./input_raspicam.so -fps 30 -x 1024 -y 768 -quality 90" -o "./output_http.so -w ./www"'

#CPU USAGE (Windows, slow... WMI takes a second to execute---)
def get_cpu_load():
    """ Returns a list CPU Loads"""
    result = []
    cmd = "WMIC CPU GET LoadPercentage "
    response = os.popen(cmd + ' 2>&1','r').read().strip().split("\r\n")
    for load in response[1:]:
       result.append(int(load))
    return result

# ... Unix / Pi                              
def get_cpu_load_PI():
    return(str(os.popen("top -n1 | awk '/Cpu\(s\):/ {print $2}'").readline().strip(\
)))

#DISKUSAGE -------------------------------------------------------------------------------------------------------------------

#Diskusage tuple
_ntuple_diskusage = collections.namedtuple('usage', 'total used free')

#diskusage app
if hasattr(os, 'statvfs'):  # POSIX
    def disk_usage(path):
        st = os.statvfs(path)
        free = st.f_bavail * st.f_frsize
        total = st.f_blocks * st.f_frsize
        used = (st.f_blocks - st.f_bfree) * st.f_frsize
        return _ntuple_diskusage(total, used, free)
elif os.name == 'nt':       # Windows
    import ctypes
    import sys

    def disk_usage(path):
        _, total, free = ctypes.c_ulonglong(), ctypes.c_ulonglong(), \
                           ctypes.c_ulonglong()
        if sys.version_info >= (3,) or isinstance(path, unicode):
            fun = ctypes.windll.kernel32.GetDiskFreeSpaceExW
        else:
            fun = ctypes.windll.kernel32.GetDiskFreeSpaceExA
        ret = fun(path, ctypes.byref(_), ctypes.byref(total), ctypes.byref(free))
        if ret == 0:
            raise ctypes.WinError()
        used = total.value - free.value
        return _ntuple_diskusage(total.value, used, free.value)
else:
    raise NotImplementedError("platform not supported")

#Byte conversion -------------------------------------------------------------------------------------------------------------------
def bytes2human(n): 
    symbols = (' KB', ' MB', ' GB', ' TB', ' PB', ' EB', ' ZB', ' YB') 
    prefix = {} 
    for i, s in enumerate(symbols): 
        prefix[s] = 1 << (i+1)*10 
    for s in reversed(symbols): 
        if n >= prefix[s]: 
            value = float(n) / prefix[s] 
            return '%.1f%s' % (value, s) 
    return "%sB" % n

#seconds to days h m s
def seconds_to_dhms_string(seconds):
	days = seconds // (3600 * 24)
	hours = (seconds // 3600) % 24
	minutes = (seconds // 60) % 60
	seconds = seconds % 60

	if days > 0:
		strng=str(int(days)).zfill(2) + " day, " + str(int(hours)).zfill(2) +":" +str(int(minutes)).zfill(2) + ":" +str(int(seconds)).zfill(2) 
	else: 
		strng=str(int(hours)).zfill(2) +":" +str(int(minutes)).zfill(2) + ":" +str(int(seconds)).zfill(2) 

	return strng	

# System and User variables in dict
def fill_user_system_dict(mydict):
	# if it's linux check for Sudo and fill the system user dict
	if mydict["system"] == "Linux":
		mydict["username"] = os.environ.get("SUDO_USER")
		if mydict["username"] is None:
			mydict["username"] = os.environ.get("USER")
			mydict["sudo"]=False
			mydict["gpio_enabled"]=False
			#sys.exit()
		else:
			mydict["sudo"]=True
			mydict["sudo_gid"]=os.environ.get('SUDO_GID')
			mydict["sudo_uid"]=os.environ.get('SUDO_UID')
			
	else:
		#we assume Windows
		mydict["username"] = os.environ.get('USERNAME')
		mydict["sudo"]=False
	
	return mydict

#correct ownership if in sudo mode
def fix_ownership(path):
	#Change the owner of the file to SUDO_UID
	uid = os.environ.get('SUDO_UID')
	gid = os.environ.get('SUDO_GID')

	if uid is not None:
		os.chown(path, int(uid), int(gid))
	
#EMAIL sender function------------------------------------------------------------------------------------------------------------------
#Usage: helpers.sendmail("bienzma@gmail.com", "from@gmail.com", "Print done", "Print successful, took 2 hourse to print.", username, password, server, port)

class EmailThread(threading.Thread):
	def __init__(self, to, efrom,  subject, text, attach, user, pw, server, port, callback=None):
		self.msg = MIMEMultipart()

		self.text = text
		self.attach = attach
		self.to = to
		self.efrom = efrom
		
		self.callbackfunction=callback

		self.gmail_user = user
		self.gmail_pwd = pw
		self.server=server
		self.port=port

		self.msg['From'] = self.efrom
		self.msg['To'] = self.to
		self.msg['Subject'] = subject
		print "SENDMAIL: Sending started."
		thread=threading.Thread.__init__(self)
		return thread

	def run (self):
		
		self.msg.attach(MIMEText(self.text))
		
		if not self.attach == None:
			part = MIMEBase('application', 'octet-stream')
			part.set_payload(open(self.attach, 'rb').read())
			Encoders.encode_base64(part)
			part.add_header('Content-Disposition',
			   'attachment; filename="%s"' % os.path.basename(self.attach))
			self.msg.attach(part)

		#set mailServer to None
		mailServer=None
		returnmsg=False, "n/a"
		
		try:
			mailServer = smtplib.SMTP(self.server, self.port)
			mailServer.ehlo()
			mailServer.starttls()
			mailServer.ehlo()
			mailServer.login(self.gmail_user, self.gmail_pwd)
			mailServer.sendmail(self.gmail_user, self.to, self.msg.as_string())
			returnmsg=True, "SENDMAIL: OK, Message accepted."
		
		
		except Exception as e:
			returnmsg=False, "SENDMAIL: ABORTED! Error: {name} ({msg}).".format(name=e.__class__.__name__, msg=e)
			
		finally:
			if mailServer:
				# Should be mailServer.quit(), but that crashes...
				mailServer.close()
		
		#if it has a callback defined send the status back to the caller
		if not self.callbackfunction == None:
			self.callbackfunction(returnmsg)
		print returnmsg[1]
		
	
def send_mail_async(to, efrom, subject, text, attach, user, pw, server, port, callback=None):
	mailthread=EmailThread(to, efrom, subject, text, attach, user, pw, server, port, callback)
	mailthread.start()
	return "SENDMAIL: Sending started."

	
#not used
def sendmailattach(to, subject, text, attach):
	msg = MIMEMultipart()

	gmail_user = ""
	gmail_pwd = ""

	msg['From'] = gmail_user
	msg['To'] = to
	msg['Subject'] = subject

	msg.attach(MIMEText(text))

	part = MIMEBase('application', 'octet-stream')
	part.set_payload(open(attach, 'rb').read())
	Encoders.encode_base64(part)
	part.add_header('Content-Disposition',
		   'attachment; filename="%s"' % os.path.basename(attach))
	msg.attach(part)

	mailServer = smtplib.SMTP("smtp.gmail.com", 587)
	mailServer.ehlo()
	mailServer.starttls()
	mailServer.ehlo()
	mailServer.login(gmail_user, gmail_pwd)
	mailServer.sendmail(gmail_user, to, msg.as_string())
	# Should be mailServer.quit(), but that crashes...
	mailServer.close()
#not used
def sendmail(to, subject, content):
	SMTP_SERVER = 'smtp.gmail.com'
	SMTP_PORT = 587
	GMAIL_USERNAME = ''
	GMAIL_PASSWORD = '' #CAUTION: This is stored in plain text!
	

	recipient = to
	subject = subject
	emailText = content

	emailText = "" + content + ""

	headers = ["From: " + GMAIL_USERNAME,
			   "Subject: " + subject,
			   "To: " + recipient,
			   "MIME-Version: 1.0",
			   "Content-Type: text/html"]
	headers = "\r\n".join(headers)

	session = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)

	session.ehlo()
	session.starttls()
	session.ehlo

	session.login(GMAIL_USERNAME, GMAIL_PASSWORD)

	session.sendmail(GMAIL_USERNAME, recipient, headers + "\r\n\r\n" + emailText)
	session.quit()

	
#get hostname------------------------------------------------------------------------------
def gethostname():
	return socket.gethostname()
	
#CONFIG CLASS - reads from / saves to inifile and creates dict----------------------------------------------------------------------------
	
class config():
	def __init__(self, configfile):
		self.settings = {}
		self.configfile = configfile
		self.defaults = {}
	
	def LoadDict(self, cfg):
		self.settings = {s:{k:v for k,v in cfg.items(s)} for s in cfg.sections()}
		
	def SafeDict(self, defaults=False):
		config = ConfigParser.RawConfigParser()
		
		if defaults==True:
			self.settings = self.defaults
		
		for s in self.settings.keys():
			config.add_section(s)
			for k,v in self.settings[s].iteritems():
				#print k + ": " + v
				config.set(s, k, v)
		
		with open(self.configfile, 'wb') as configfile:
			config.write(configfile)
		
		fix_ownership(self.configfile)
	
	def Load(self):
		config = ConfigParser.RawConfigParser()
		
		if not os.path.exists(self.configfile):
			self.SafeDict(True)
			
		config.read(self.configfile)
		
		self.LoadDict(config)
			
	
	def Save(self):
		self.SafeDict()

#timer based on the pygame loop (to be placed in a loop and need to call run() frequently
class MySimpleTimer():
	def __init__(self, intervall, function, *args, **kwargs):
		self.enabled = False
		
		
		self.intervall = intervall
		self.function = function
		self.args       = args
		self.kwargs     = kwargs
		
		#temp variable to store current time + delta in seconds
		self.timeplusintervall = self.makeNewTimeout(self.intervall)
		self.counter=0
		
	def run(self):
		if self.enabled:
			if  time.time() > self.timeplusintervall:
				#self.counter=self.counter+1
				#print "Fired"
				self.function(*self.args, **self.kwargs)
				self.timeplusintervall = self.makeNewTimeout(self.intervall)
	
	def start(self):
		self.enabled = True
		#allways reset the timer, so no immediate fire happens
		self.timeplusintervall = self.makeNewTimeout(self.intervall)
		self.counter=0
		
	def stop(self):
		self.enabled = False
	def makeNewTimeout(self, sec):
		now = time.time()
		return now + sec


		#Threaded timer, generic use----------------------------------------------------------------------------
class MyTimer(object):
	def __init__(self, interval, function, *args, **kwargs):
		self._timer     = None
		self.interval   = interval
		self.function   = function
		self.args       = args
		self.kwargs     = kwargs
		self.is_running = False
		#self.start()

	def _run(self):
		
		if self.is_running:
			self.function(*self.args, **self.kwargs)
			self.is_running = False
			self.start()

	def start(self):
		if not self.is_running:
			self._timer = threading.Timer(self.interval, self._run)
			self._timer.start()
			self.is_running = True

	def stop(self):
		self._timer.cancel()
		self.is_running = False
		
		
#Speed test class
class SpeedTest():
	def __init__(self):
		#self.starttime = datetime.datetime.now()
		self.start()
		
	def start(self):
		self.starttime = datetime.datetime.now()
	def stop(self):
		self.stoptime = datetime.datetime.now()
		delta = self.stoptime - self.starttime
		return delta, int(delta.total_seconds() * 1000)		
		
	
	

		