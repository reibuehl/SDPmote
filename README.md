# umcam
Python app that uses an internal webserver (tornado) to serve a client to control your ultimaker / other marlin based 3d printer. Can also use mjpeg-streamer to stream and record pictures (TLs). It will run on Window, Linux and on the Raspberry Pi (wheezy, jessie).

#Credits go to:
- Octoprint, Gina Häussge, http://octoprint.org/
- bootsrap, http://getbootstrap.com/
- mjpeg-streamer, https://github.com/jacksonliam/mjpg-streamer
- jquery, http://jquery.com/
- python 2.7, https://www.python.org/
  - pygame, http://www.pygame.org/hifi.html
  - Tornado, http://www.tornadoweb.org/en/stable/
  - pyserial ()

#Installation Routine (Raspberry Pi)

Base configuration
Start with a fresh install of the latest wheezy or Jessie. Expand filesystem, install piTFT drivers, touchscreen interface etc.

#install pygame
sudo apt-get install python-pygame

#install tornado / serial if required
sudo apt-get install python-pip
(sudo pip install pyserial)
sudo pip install tornado

#make sure the user pi has access to the serial port
sudo usermod -a -G tty pi
sudo usermod -a -G dialout pi

#install mjpeg-streamer
cd ~
sudo apt-get install git subversion libjpeg8-dev imagemagick libav-tools cmake
git clone https://github.com/jacksonliam/mjpg-streamer.git
cd mjpg-streamer/mjpg-streamer-experimental
export LD_LIBRARY_PATH=.
make

#install umcam
cd ~
git clone https://github.com/MartinBienz/umcam.git
