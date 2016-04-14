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

#Serial Interface Class, currently only works on the PI
class SerialProcess_mp(multiprocessing.Process):
 
	def __init__(self, port, baud, timeo, taskQ, resultQ, gcode_dirs):
		multiprocessing.Process.__init__(self)
		self.taskQ = taskQ
		self.resultQ = resultQ
		self.gcode_dirs = gcode_dirs
		self.port = port
		self.baud = baud
		self.timeout = timeo
		self.initOK = False
	
		self.m105intervallsec = 9
		self.tempmonitor_enabled = True
		self.m27intervallsec = 10
		
		self.printer_statusdisplay = "unknown" #idle, unknown, printing, heating up bed, heating up extruder, print finished
		self.printer_heatingup = False
		self.print_start_countdown=-1 #stores the value as serial commands start to count down before startprint (W:?)
		self.printer_isprinting = False
		self.printer_isstreaming = False
		self.printer_streamingmode=""
		self.printer_temp = (0.0, 0.0,0.0,0.0)
		self.printer_progress = (0.0, 0 ,0)
		self.printer_fileselected = ("", 0)
		# record time of print start, elapsed, expected time to finish
		self.print_time = (datetime.datetime.now(), datetime.timedelta(seconds=+1), "00:00:00")
		
		self.writetofilereceived = False
		
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
		
		self.tryopen()
		
	def tryopen(self):
	
		try:
			self.sp = serial.Serial(self.port, self.baud, timeout=self.timeout)
			msg=str(self.port)+" ready."
			self.printer_statusdisplay =  msg
			self.initOK = True
			print msg
		except Exception as e:
			msg = "Serial interface on Port "+str(self.port)+" could not open. Error: {name} ({msg}).".format(name=e.__class__.__name__, msg=e)
			self.printer_statusdisplay = "Unable to open "+str(self.port)
			self.sp = None
			self.initOK = False
			print msg
		
		self.resultQ.put({"CMD": "STATUS", "DATA": self.GetPrinterStatus()})
		return (msg)
	
	def close(self):
		
		if self.initOK:
			self.initOK = False
			self.taskQ.put({"CMD": "KILL"})
		
			if(not(self.sp == None)):
				self.sp.close()
				self.sp = None
			
		self.printer_statusdisplay = str(self.port)+" closed."
		self.resultQ.put({"CMD": "STATUS", "DATA": self.GetPrinterStatus()})
				
		print self.printer_statusdisplay
		return (self.printer_statusdisplay)

	def sendData(self, data):
		print "sendData start..."
		self.sp.write(data+ '\n')
		time.sleep(.1)
		print "sendData done: " + data
		
	def updateweblog(self, cmd):
		self.resultQ.put({"CMD": "UPDATE_SERIAL_LOG", "DATA": cmd})
		
	
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
		
		if self.printer_isprinting or self.printer_isstreaming:
			self.print_updatetime()
					
		return {"status": self.printer_statusdisplay,
				"initok": self.initOK,
				"isheatingup": self.printer_heatingup,
				"isprinting": self.printer_isprinting,
				"isstreaming": self.printer_isstreaming,
				"streamingmode": self.printer_streamingmode,
				"temp": self.printer_temp,
				"progress": self.printer_progress,
				"progress_time": (self.print_time[0].strftime("%d.%B %Y %H:%M"), helpers.seconds_to_dhms_string(self.print_time[1].total_seconds()), self.print_time[2]),
				"file": self.printer_fileselected,
				"sdrefresh": self.sdrefresh,
				"sdfiles": self.sdfilelist,
				"print_start_countdown": self.print_start_countdown
				}
	
	
	#Stream or Save to SD starter
	def StreamOrSaveSD(self, mode, filename):
		self.printer_isstreaming = True
		self.printer_streamingmode = mode #"sd" or "print" or ""
		

		if self.printer_streamingmode == "sd":
			# to SD - Card
			self.tempmonitor_enabled = False			
			self.filetostream=self.StreamFile(os.path.join(self.gcode_dirs["root_dir"], self.gcode_dirs["sd-card_dir"], filename), self.printer_streamingmode)
			print "File "+self.filetostream.filename+" has "+str(self.filetostream.getlinecount())+" lines, size is "+self.filetostream.filesize_str
			self.printer_fileselected = (self.filetostream.filename, self.filetostream.filesize)
			self.print_setstarttime()
			
			self.taskQ.put({"CMD": "SERIAL", "DATA": "M28 " + self.filetostream.getsdfilename()})
		else:
			# Stream it! First LINE to kick it off
			self.filetostream=self.StreamFile(os.path.join(self.gcode_dirs["root_dir"], self.gcode_dirs["print_dir"], filename), self.printer_streamingmode)
			print "File "+self.filetostream.filename+" has "+str(self.filetostream.getlinecount())+" lines, size is "+self.filetostream.filesize_str
			
			self.printer_fileselected = (self.filetostream.filename, self.filetostream.filesize)
			self.printer_statusdisplay= "Streaming " + self.filetostream.filename + " (" + self.filetostream.filesize_str +")"
			
			eof, gcode_line, lnr = self.filetostream.nextline()
			if eof == True:
				self.toggle_stopprint()
				return True
			

			
			self.taskQ.put({"CMD": "SERIAL", "DATA": gcode_line})
	
	
	class StreamFile():
		def __init__(self, file, scope):
			
			self.filehandle = None 
			self.filenameandpath = file
			self.filename = os.path.basename(self.filenameandpath)
			
			#create a filename that can be stored on the sd-card
			self.sdfilename=self.make83filename(self.filename)
						
			self.currentline = 0
			self.linecount = -1
			
			if not os.path.exists(self.filenameandpath) or not os.path.isfile(self.filenameandpath): 
				raise IOError("File %s does not exist" % self.filenameandpath) 
			self.filesize = os.stat(self.filenameandpath).st_size
			self.filesize_str = helpers.bytes2human(self.filesize)
			
			self.scope = scope # "sd": Safe to SD-Card / "print": streams directly to printer
			
			self.open()
			self.linecount = self.enum_file()
			
		def setfileeof(self):
			self.filehandle.seek(self.linecount+1)
			self.currentline=self.linecount+1
		
		def getlinecount(self):
			return self.linecount
		
		def checksum(self, cmd_tosend):
			#return reduce(lambda x,y:x+y, map(ord, cmd_tosend))
			
			#xor way with per char ascii
			checksum=0			
			for ch in cmd_tosend:
				checksum ^= ord(ch)
			return "*"+str(checksum)
		
		def enum_file(self):
			try:
				for i, line in enumerate(self.filehandle):
					pass
					#checking for cura specific slicer settings...
					#if ";Sliced at: " in line: print line.strip()
					#if ";Basic settings: " in line: print line.strip()
					#if ";Print time: " in line: print line.strip()
					#if ";Filament used: " in line: print line.strip()
			finally:
				pass
			self.filehandle.seek(0)
			return i+1
			
		def getcurrentline(self):
			return self.currentline
		
		def open(self):
			#open the file for reading, needs to be in r+ (write also) mode to enable seek
			self.filehandle = open(self.filenameandpath, "r+")
			
		def close(self):
			self.filehandle.close() 
			self.filehandle = None 
		
		def getsdfilename(self):
			return self.sdfilename
		
		def make83filename(self, fname):
			#VEEEERY simple... uuh, needs a better algorythm second file will be overwritten
			filename, file_extension = os.path.splitext(fname)
			
			if len(filename) > 8:
				fname83 = filename[:6] +"~1"+ ".gco"
			else:
				fname83 = filename + ".gco"
				
			return fname83.replace(" ", "_").lower()
		
		def nextline(self):
	
			while True:
			
				self.currentline=self.currentline+1
				
				ori_line=self.filehandle.readline() #.strip() will use strip for streaming
				
				#EOF handling
				if not ori_line: 
					self.close()
					return True, "", self.currentline
					
				#get rid of all comments and whitespace
				line = ori_line.split(';', 1)[0]
				line = line.rstrip()
										
				#if empty (comment, blank...) advance
				if len(line.strip()) == 0 or len(line)==0 or line =="":
					# do something with empty line
					pass
				else: 
					#print str(self.currentline)+":LINE:"+line+"--L:"+str(len(line))+":O:"+ori_line
					break
				
			return False, line, self.currentline 
	
	
	def abort_print(self, msg):
		self.printer_statusdisplay =  msg
		
		if self.printer_isprinting == True and self.printer_isstreaming == False:
			#print from SD card
			print "ABORT: SD-Printing..."
			self.printer_progress = (0.0,0,0)
			
			self.taskQ.put({"CMD": "SERIAL", "DATA": "M25"})
			self.taskQ.put({"M26 S0"}) #Reset file Position
			self.taskQ.put({"CMD": "SERIAL", "DATA": "M107"})#FAN OFF
			self.taskQ.put({"CMD": "SERIAL", "DATA": "M104 S0"})#extruder heater off
			self.taskQ.put({"CMD": "SERIAL", "DATA": "M140 S0"})#heated bed heater off (if you have it)
						
			self.taskQ.put({"CMD": "SERIAL", "DATA": "G91"}) #relative positioning
			self.taskQ.put({"CMD": "SERIAL", "DATA": "G1 E-1 F300"}) #retract the filament a bit before lifting the nozzle, to release some of the pressure
			self.taskQ.put({"CMD": "SERIAL", "DATA": "G1 Z+0.5 E-5 X-20 Y-20 F9000"})#move Z up a bit and retract filament even more
			self.taskQ.put({"CMD": "SERIAL", "DATA": "G28 X0 Y0"}) #move X/Y to min endstops
							
			self.taskQ.put({"CMD": "SERIAL", "DATA": "M84"}) #steppers off
			self.taskQ.put({"CMD": "SERIAL", "DATA": "G90"}) #absolute positioning
			
			self.printer_isprinting=False
				
		
		if self.printer_streamingmode == "print" and self.printer_isstreaming == True:
			#streaming from the pi
			print "ABORT: Stream printing..."
			self.filetostream.setfileeof()
			
			#clear the q
			while not self.taskQ.empty():
				self.taskQ.get()
			
			self.printer_progress = (0.0,0,0)
			self.printer_isstreaming = False
			
			self.printer_streamingmode = "" #"sd" or "print" or ""
			
			#add print stop to the mix
			if self.printer_isprinting:
				self.taskQ.put({"CMD": "SERIAL", "DATA": "M25"})
				self.taskQ.put({"CMD": "SERIAL", "DATA": "M107"})#FAN OFF
				self.taskQ.put({"CMD": "SERIAL", "DATA": "M104 S0"})#extruder heater off
				self.taskQ.put({"CMD": "SERIAL", "DATA": "M140 S0"})#heated bed heater off (if you have it)
							
				self.taskQ.put({"CMD": "SERIAL", "DATA": "G91"}) #relative positioning
				self.taskQ.put({"CMD": "SERIAL", "DATA": "G1 E-1 F300"}) #retract the filament a bit before lifting the nozzle, to release some of the pressure
				self.taskQ.put({"CMD": "SERIAL", "DATA": "G1 Z+0.5 E-5 X-20 Y-20 F9000"})#move Z up a bit and retract filament even more
				self.taskQ.put({"CMD": "SERIAL", "DATA": "G28 X0 Y0"}) #move X/Y to min endstops
								
				self.taskQ.put({"CMD": "SERIAL", "DATA": "M84"}) #steppers off
				self.taskQ.put({"CMD": "SERIAL", "DATA": "G90"}) #absolute positioning
				
				self.printer_isprinting=False
			
			
			
		if self.printer_streamingmode == "sd" and self.printer_isstreaming == True:
			#streaming to SD from the pi
			print "ABORT: SD-Save, deleting file..."
			self.filetostream.setfileeof()
			
			#clear the q
			while not self.taskQ.empty():
				self.taskQ.get()
			
			self.printer_progress = (0.0,0,0)
			self.printer_isstreaming = False
			self.printer_streamingmode = "" #"sd" or "print" or ""
			self.writetofilereceived = False
			self.tempmonitor_enabled = True
			
			self.taskQ.put({"CMD": "SERIAL", "DATA": "M29"})
			self.taskQ.put({"CMD": "SERIAL", "DATA": "M30 "+ self.filetostream.getsdfilename()})
		
		if self.printer_heatingup:
			self.taskQ.put({"CMD": "SERIAL", "DATA": "M104 S0"})#extruder heater off
			self.taskQ.put({"CMD": "SERIAL", "DATA": "M140 S0"})#heated bed heater off (if you have it)
			self.tempmonitor_enabled = True
		
	
	def toggle_stopprint(self, msg):
		self.printer_statusdisplay =  msg
		
		if self.printer_isprinting:
			self.printer_isprinting=False
			self.resultQ.put({"CMD": "COMMAND", "DO": "PRINTSTOP"})
		
		if self.printer_streamingmode == "sd":
			self.taskQ.put({"CMD": "SERIAL", "DATA": "M29"})
			self.tempmonitor_enabled = True
		
		if self.printer_streamingmode == "print":
			self.printer_isstreaming = False
			self.printer_streamingmode = "" #"sd" or "print" or ""

		
	
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
		
		if 'Writing to file:' in line and self.printer_isstreaming:
			#this means M28 was issued with a new file, you can now start to stream
			self.printer_statusdisplay =  "Streaming " + self.filetostream.filename + " to " + self.printer_streamingmode
			self.writetofilereceived = True
			return True
		
		if 'open failed,' in line and self.printer_isstreaming:
			self.printer_statusdisplay =  "Error saving " + self.filetostream.getsdfilename() + " to SD-Card"
			self.printer_progress = (0.0,0,0)
			self.printer_isstreaming = False
			self.printer_streamingmode = "" #"sd" or "print" or ""
			self.writetofilereceived = False
			self.tempmonitor_enabled = True
			
			return True
		
		if line == 'ok' and self.printer_isstreaming:
			#ok after M28 or subsequent lines to save the file to SD
			#uh... receive an ok if there are spaces in the m28 filename... so make sure it's not starting to stream directly it that happens
			doreturn=True
			
			if not self.writetofilereceived and self.printer_streamingmode == "sd":
				self.printer_statusdisplay =  "Error saving " + self.filetostream.getsdfilename() + " to SD-Card"
				print  "ABORT: Error saving " + self.filetostream.getsdfilename() + " to SD-Card"
				self.printer_progress = (0.0,0,0)
				self.printer_isstreaming = False
				self.printer_streamingmode = "" #"sd" or "print" or ""
				self.writetofilereceived = False
				self.tempmonitor_enabled = True
				return True
			
			
			eof, gcode_line, lnr = self.filetostream.nextline()
			if eof == True:
				#end of file, so streaming is done!
				self.toggle_stopprint("STREAM: EOF received, streaming done.")
				return True
				
			if lnr % 50 == 0:
				lineprintedpercentage=float(lnr) / float(self.filetostream.getlinecount()) * 100
				self.printer_progress = ( round(lineprintedpercentage, 2) , lnr, self.filetostream.getlinecount())
				doreturn=True
			else:
				doreturn=False
			
			#hang on for 10 milisecond to make sure the buffer catches up
			#time.sleep(0.01)
			self.taskQ.put({"CMD": "SERIAL", "DATA": gcode_line})
			#time.sleep(0.01)
		
			return doreturn

				
		if 'Done saving file.' in line and self.printer_isstreaming:
			#stream finished, file written
			self.printer_statusdisplay =  "Saved " + self.filetostream.getsdfilename() + " to SD-Card"
			self.printer_progress = (0.0,0,0)
			self.printer_isstreaming = False
			self.printer_streamingmode = "" #"sd" or "print" or ""
			self.writetofilereceived = False
			self.tempmonitor_enabled = True
			return True
		
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
			self.tempmonitor_enabled = False
			
			
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
						self.tempmonitor_enabled = True
						
					else:
						self.printer_statusdisplay =  "Heating DONE, start in "+str(self.print_start_countdown)
			
			

		if 'ok T' in line:
			news=True
			#answering M105 with ok to get Temp readings "ok T:21.5 /0.0 B:18.7 /0.0 T0:21.5 /0.0 @:0 B@:0"
			#											 "ok T:24.0 /0.0 B:20.6 /0.0 @:0 B@:0" !!!!UM2!!!!!
			
			#line = "ok T:24.0 /0.0 B:20.6 /0.0 @:0 B@:0"
			
			maxToolNum, parsedTemps =  self.parseTemp(line)
			
			# bed temperature
			if "B" in parsedTemps.keys():
				toolNum, actual_bed, target_bed = parsedTemps["B"]
				#print "Bed temperature: {0:} target: {1:}".format(actual_bed, target_bed)
			else:
				#no bed?
				actual_bed, target_bed = (0.0, 0.0)
			
			#nozzle T0 and T
			if "T0" in parsedTemps.keys():
				toolNum, actual_ext, target_ext = parsedTemps["T0"]
				#print "Nozzle temperature: {0:} target: {1:}".format(actual_ext, target_ext)
			else:		
				if "T" in parsedTemps.keys():
					toolNum, actual_ext, target_ext = parsedTemps["T"]
					#print "Nozzle temperature: {0:} target: {1:}".format(actual_ext, target_ext)
				else:
					actual_ext, target_ext = (0.0, 0.0)
			
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
			if  time.time() > temp_m105intervall and self.tempmonitor_enabled:
				self.taskQ.put({"CMD": "SERIAL", "DATA": "M105"})
				temp_m105intervall = self.makeNewTimeout(self.m105intervallsec)
			
			if  time.time() > temp_m27intervall:
				if self.printer_isprinting and (not self.printer_isstreaming):
					self.taskQ.put({"CMD": "SERIAL", "DATA": "M27"})
				temp_m27intervall = self.makeNewTimeout(self.m27intervallsec)
			
						
			# look for incoming tornado request
			if not self.taskQ.empty():
				task = self.taskQ.get()
				# send it to the arduino
				if task["CMD"] == "SERIAL":
					
					#if not self.printer_isstreaming:
					print time.strftime("%H:%M:%S")+" sent: " + task["DATA"]
					self.updateweblog(time.strftime("%H:%M:%S")+" sent: "+task["DATA"])
					self.sp.write(str(task["DATA"])+ '\n')
					#time.sleep(0.01)
				
				if task["CMD"] == "SAVESD":
					print "SAVING"+ str(task["DATA"]) + " to SD-Card"
					self.StreamOrSaveSD("sd", str(task["DATA"]))
				
				if task["CMD"] == "STREAMFILE":
					print "Streaming "+ str(task["DATA"]) + " to printer"
					self.StreamOrSaveSD("print", str(task["DATA"]))
					
				if task["CMD"] == "ABORTPRINT":
					print "SERIAL: ABORTING print / stream..."
					self.abort_print("SERIAL: ABORTING print / stream...")
				
				if task["CMD"] == "KILL":
					#break the loop and end the thread
					self.initOK=False
				
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