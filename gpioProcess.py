#  File: gpioProcess.py
#  Description: handles the GPIO io communicationin a seperate thread, not doing much at the moment
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
import os
import helpers

try:
	import RPi.GPIO as io
	GPIO_enabled=True
except ImportError:
	print "RPi.GPIO import Error, not running on the PI? GPIO Module disabled..."
	GPIO_enabled=False

#overwrite for testing
#GPIO_enabled=True

#Serial Interface Class, currently only works on the PI
class gpioProcess_mp(multiprocessing.Process):
	enabled=GPIO_enabled
	
	def __init__(self, resultQ):
		multiprocessing.Process.__init__(self)
		#we do not want to receive any tasks... for now
		#self.taskQ = taskQ
		self.resultQ = resultQ
		self.initOK = False
		self.intervallsec = 1 #intervall in seconds
		
		if not self.enabled:
			self.initOK=False
		else:
			self.initOK=True
			io.setmode(io.BCM)
			
			self.pir_pin = 18
			io.setup(self.pir_pin, io.IN, pull_up_down=io.PUD_UP)
			
			#THIS IS NOT WORKING, as RPI.GPIO says "no can do this channel", maybe wirinpgi?
			#self.backlight_pin_virtual = 508
			#io.setup(self.backlight_pin_virtual, io.OUT)
			#io.output(self.backlight_pin_virtual, 0)
 
	def close(self):
		self.initOK = False
		GPIO.cleanup()
 	
	def makeNewTimeout(self, sec):
		now = time.time()
		return now + sec
	
	def run(self):
		if (self.initOK == True): 
			temp_intervall = self.makeNewTimeout(self.intervallsec)

		while (self.initOK == True):
			
			#check for intervall tasks
			if  time.time() > temp_intervall:
				self.resultQ.put({"CMD": "GPIO", "DATA": io.input(self.pir_pin)})
				#FOR FUTURE USE: self.taskQ.put({"CMD": "SERIAL", "DATA": "..."})
				temp_intervall = self.makeNewTimeout(self.intervallsec)

