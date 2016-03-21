#  File: serialProcess.py
#  Description: handles the serial io (communication with the printer) in a seperate thread
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
import time
import datetime
import multiprocessing
import serial
import re
import os
import helpers

#prototype, do not try out :)
def TestSaveSD():
	testfile=sp.SaveFiletoSD(os.path.join("web", "temp", "test.gcode") )
	print "Has: "+str(testfile.linecount())+" LINES"
	
	testfile.close()
	testfile.open()
	
	f = open(os.path.join("web", "temp", "testCOPY.gcode") ,'w')

	
	while 1:
		eof, line = testfile.nextline()
		if eof == True: break
		f.write (line)
		print line
	
	f.close()
	
	
#Serial Interface Class, currently only works on the PI
class SerialProcess_mp(multiprocessing.Process):
 
	def __init__(self, port, baud, timeo, taskQ, resultQ):
		multiprocessing.Process.__init__(self)
		self.taskQ = taskQ
		self.resultQ = resultQ
		self.port = port
		self.baud = baud
		self.timeout = timeo
		self.initOK = False
		
		self.m105intervallsec = 9
		self.m27intervallsec = 10
		
		self.printer_statusdisplay = "unknown" #idle, unknown, printing, heating up bed, heating up extruder, print finished
		self.printer_heatingup = False
		self.print_start_countdown=-1 #stores the value as serial commands start to count down before startprint (W:?)
		self.printer_isprinting = False
		self.printer_sdstream = False
		self.printer_temp = (0.0, 0.0,0.0,0.0)
		self.printer_progress = (0.0, 0 ,0)
		self.printer_fileselected = ("", 0)
		# record time of print start, elapsed, expected time to finish
		self.print_time = (datetime.datetime.now(), datetime.timedelta(seconds=+1), "00:00:00")
		
		self.getfilelistflag=False
		self.sdfilelist = []
		self.sdrefresh = time.time()
		
		
		self.floatPattern = "[-+]?[0-9]*\.?[0-9]+"
		self.positiveFloatPattern = "[+]?[0-9]*\.?[0-9]+"
		self.intPattern = "\d+"

		self.regex_float = re.compile(self.floatPattern)

		self.regex_paramTFloat = re.compile("T:\s*(%s)" % self.positiveFloatPattern)
		self.regex_paramBFloat = re.compile("B:\s*(%s)" % self.positiveFloatPattern)
		self.regex_paramWInt = re.compile("W:\s*(%s)" % self.intPattern)
		self.regex_paramWQuestionMark = re.compile("W:\s*\?")

		self.regex_sdPrintingByte = re.compile("([0-9]*)/([0-9]*)")
		self.regex_sdFileOpened = re.compile("File opened:\s*(.*?)\s+Size:\s*(%s)" % self.intPattern)
		self.regex_temp = re.compile("(B|T(\d*)):\s*(%s)(\s*\/?\s*(%s))?" % (self.positiveFloatPattern, self.positiveFloatPattern))
		
		try:
			self.sp = serial.Serial(self.port, self.baud, timeout=self.timeout)
			print "Serial interface on Port "+str(self.port)+" open."
			self.printer_statusdisplay = str(self.port)+" ready."
			self.initOK = True
		except Exception as e:
			print "Serial interface on Port "+str(self.port)+" could not open."
			print "Error: {name} ({msg}).".format(
			name=e.__class__.__name__, 
			msg=e)
			self.printer_statusdisplay = "Unable to open "+str(self.port)
			self.initOK = False
		
		self.resultQ.put({"CMD": "STATUS", "DATA": self.GetPrinterStatus()})
		
		
	def close(self):
		self.initOK = False
		#time.sleep(1)
		if self.initOK == True:
			self.sp.close()
 
	def sendData(self, data):
		print "sendData start..."
		self.sp.write(data+ '\n')
		time.sleep(.1)
		print "sendData done: " + data
	
	def parseTemp(self, line):
		result = {}
		maxToolNum = 0
		for match in re.finditer(self.regex_temp, line):
			tool = match.group(1)
			toolNumber = int(match.group(2)) if match.group(2) and len(match.group(2)) > 0 else None
			if toolNumber > maxToolNum:
				maxToolNum = toolNumber
			try:
				actual = float(match.group(3))
				target = None
				if match.group(4) and match.group(5):
					target = float(match.group(5))
				result[tool] = (toolNumber, actual, target)
			except ValueError:
				pass

		if "T0" in result.keys() and "T" in result.keys():
			del result["T"]

		return maxToolNum, result
	
	def cleanAscii(self, line):
		return unicode(line, 'ascii', 'replace').encode('ascii', 'replace').rstrip()
	
	def makeNewTimeout(self, sec):
		now = time.time()
		return now + sec
	
	def print_setstarttime(self):
		self.print_time = (datetime.datetime.now(), datetime.timedelta(seconds=+1), "00:00:00")
		
	def print_updatetime(self):
		# record time of print start 0, elapsed  1, expected time to finish 2
		elapsed = datetime.datetime.now()-self.print_time[0]
		
		if self.printer_progress[0] > 0:
			totaltimeest = elapsed.total_seconds()/self.printer_progress[0]*100
			togo = totaltimeest-elapsed.total_seconds()
			self.print_time = (self.print_time[0], elapsed, helpers.seconds_to_dhms_string(togo))
		else:
			self.print_time = (self.print_time[0], elapsed, "00:00:00")

	def GetPrinterStatus(self):
		
		if self.printer_isprinting:
			self.print_updatetime()
					
		return {"status": self.printer_statusdisplay,
				"isheatingup": self.printer_heatingup,
				"isprinting": self.printer_isprinting,
				"temp": self.printer_temp,
				"progress": self.printer_progress,
				"progress_time": (self.print_time[0].strftime("%d.%B %Y %H:%M"), helpers.seconds_to_dhms_string(self.print_time[1].total_seconds()), self.print_time[2]),
				"file": self.printer_fileselected,
				"sdrefresh": self.sdrefresh,
				"sdfiles": self.sdfilelist,
				"print_start_countdown": self.print_start_countdown
				}
	
	class SaveFiletoSD():
		def __init__(self, file):
			
			self.filehandle = None 
			self.filename=file
			
			self.currentline = 0
			
			if not os.path.exists(self.filename) or not os.path.isfile(self.filename): 
				raise IOError("File %s does not exist" % self.filename) 
			self.filesize = os.stat(self.filename).st_size
			
			self.open()
			
		def linecount(self):
			try:
				for i, line in enumerate(self.filehandle):
					pass
			finally:
				pass
			return i+1
			
			#reset position by reopening seek(0) on the handle does not seem to work... #needs to close the file and reopen it!


		def getcurrentline(self):
			return self.currentline
		
		def open(self):
			#open the file for reading
			self.filehandle = open(self.filename, "r")
			
		def close(self):
			self.filehandle.close() 
			self.filehandle = None 

		def nextline(self):
			self.currentline=self.currentline+1
			line=self.filehandle.readline()

			#EOF handling
			if not line: 
				self.close()
				return True, ""
			
			return False, line
	
	def toggle_stopprint(self, msg):
		self.printer_statusdisplay =  msg
		if self.printer_isprinting:
			self.printer_isprinting=False
			self.resultQ.put({"CMD": "COMMAND", "DO": "PRINTSTOP"})
	
	def toggle_startprint(self, msg):
		self.printer_statusdisplay = msg
		self.printer_heatingup=False
		self.print_start_countdown=-1
		self.printer_isprinting=True
		self.print_setstarttime()
		#starting the timelapse here, if not allready printing
		self.resultQ.put({"CMD": "COMMAND", "DO": "PRINTSTART"})
	
	def monitor(self, line):
	
		news=False
		
		if 'Begin file list' in line:
			self.getfilelistflag=True
			self.sdfilelist[:] = []
			return False
		
		if 'End file list' in line:
			#print self.sdfilelist
			self.sdfilelist=sorted(self.sdfilelist)
			self.getfilelistflag=False
			self.sdrefresh=time.time()
			news=True
		
		if 	self.getfilelistflag:
			#get files as long as no end file list is sent via serial port
			self.sdfilelist.append(line.lower())
			#return as we can only expect files from now on
			return False
		
		
		if line.startswith('T:') and not self.printer_isprinting: 
			news=True
			#Warming up to print
			self.printer_heatingup=True
			
			
			if 'B:' in line:

				match = self.regex_paramBFloat.search(line)
				self.printer_statusdisplay = "Heating bed: "+match.group(1)+""
				# udpate only bed temperature, leafe the rest as is...
				self.printer_temp = (self.printer_temp[0],self.printer_temp[1],round(float(match.group(1)),2), self.printer_temp[3])

			if 'W:' in line:

				match = self.regex_paramTFloat.search(line)
				self.printer_statusdisplay =  "Heating extruder: "+match.group(1)+""
				# udpate only ext temperature, leafe the rest as is...
				self.printer_temp = (round(float(match.group(1)),2),self.printer_temp[1],self.printer_temp[2], self.printer_temp[3])
				
				#find if W: allready counting down
				match = self.regex_paramWInt.search(line)
				if match == None:
					pass 
				else:
					
					self.print_start_countdown = int(match.group(1))
					#check if W: (countdown to print) is smaller or equal to 1, when only checking for 0 there were some issues, thanks Amedee
					if self.print_start_countdown <= 1:
						#tooggle print start with notification
						self.toggle_startprint("Heating DONE, start printing.")
						
					else:
						self.printer_statusdisplay =  "Heating DONE, start in "+str(self.print_start_countdown)
			
			

		if 'ok T' in line:
			news=True
			#answering M105 with ok to get Temp readings "ok T:21.5 /0.0 B:18.7 /0.0 T0:21.5 /0.0 @:0 B@:0"

			maxToolNum, parsedTemps =  self.parseTemp(line)
			
			# bed temperature
			if "B" in parsedTemps.keys():
				toolNum, actual_bed, target_bed = parsedTemps["B"]
				#print "Bed temperature: {0:} target: {1:}".format(actual_bed, target_bed)
			
			#nozzle
			if "T0" in parsedTemps.keys():
				toolNum, actual_ext, target_ext = parsedTemps["T0"]
				#print "Nozzle temperature: {0:} target: {1:}".format(actual_ext, target_ext)
			
			try:		
				self.printer_temp = (round(float(actual_ext),2),round(float(target_ext),2),round(float(actual_bed),2), round(float(target_bed),2))	
			except:
				#error while reading (half lines etc...), only happend once so far but better safe than sorry...
				self.printer_temp = (0.0, 0.0,0.0,0.0)

		if 'Done printing file' in line:
			news = True
			# Serial sent once print is done
			self.toggle_stopprint("Print finished")
		
		if 'Not SD printing' in line:
			news = True
			self.toggle_stopprint("SD Printing stopped - idle")
			self.printer_progress = ( 0.0 , 0, 0)

		if 'SD printing byte' in line:
			news = True
			# M27 Marlin "SD printing byte %/%"
			match = self.regex_sdPrintingByte.search(line)
			
			self.printer_statusdisplay =  "Printing from SD"
			
			if not match.group(2) == "0":
				bytesprintedpercentage=float(match.group(1)) / float(match.group(2)) * 100
				#print "SD Printing Progress: {0:.2f}% (Bytes {1:} / {2:})".format(bytesprintedpercentage, match.group(1), match.group(2))
				self.printer_progress = (round(bytesprintedpercentage,2), int(match.group(1)) ,int(match.group(2)))
				
				# is at 100% so printing is done
				if bytesprintedpercentage == 100:
					self.toggle_stopprint("Print finished")
				else:
					self.printer_isprinting=True
				
			else:
				#print "SD Printing Progress: NOT Printing"
				self.toggle_stopprint("Not printing, idle")
				self.printer_progress = ( 0.0 , 0, 0)
			

		if 'File opened:' in line:
			news=True
			# Sent to serial as file selected to print, "File opened: %filename Size: %size"
			match = self.regex_sdFileOpened.search(line)
			
			self.printer_isprinting=False
			self.printer_isheatingup=False
			self.printer_fileselected = (match.group(1), int( match.group(2)))
			self.printer_statusdisplay = "File selected for printing: {0:} (Size: {1:} Bytes)".format(match.group(1), match.group(2))

		return news
		
	def run(self):
		if (self.initOK == True): 
			self.sp.flushInput()
			
			temp_m105intervall = self.makeNewTimeout(self.m105intervallsec)
			temp_m27intervall = self.makeNewTimeout(self.m27intervallsec)

		while (self.initOK == True):
			
			#check for intervall tasks
			if  time.time() > temp_m105intervall and not self.printer_heatingup:
				self.taskQ.put({"CMD": "SERIAL", "DATA": "M105"})
				temp_m105intervall = self.makeNewTimeout(self.m105intervallsec)
			
			if  time.time() > temp_m27intervall and self.printer_isprinting:
				self.taskQ.put({"CMD": "SERIAL", "DATA": "M27"})
				temp_m27intervall = self.makeNewTimeout(self.m27intervallsec)
			
						
			# look for incoming tornado request
			if not self.taskQ.empty():
				task = self.taskQ.get()
				# send it to the arduino
				if task["CMD"] == "SERIAL":
					print "sent: " + task["DATA"]
					self.sp.write(str(task["DATA"])+ '\n')
					
				if task["CMD"] == "STARTMANUAL":
					print "START print sent, override!"
					self.toggle_startprint("Manual override, started printing.")
				
			# look for incoming serial data
			if (self.sp.inWaiting() > 0):
				result = self.cleanAscii(self.sp.readline())
				#check if anything send back matches our expectations...
				if self.monitor(result):
					self.resultQ.put({"CMD": "STATUS", "DATA": self.GetPrinterStatus()})
					
				# send it back to tornado
				self.resultQ.put({"CMD": "SERIAL", "DATA": result})	
							
