# -*- coding: utf-8 -*-
import time
import os
import sys
from time import gmtime, strftime
from PIL import Image
from Queue import Queue
import socket
import threading
PING_SERVER = "www.google.com"
reload(sys)
sys.setdefaultencoding('utf8')

from base import Base
from rgbmatrix import graphics, RGBMatrix, RGBMatrixOptions

sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/..'))

class RunText(Base):
    def __init__(self, *args, **kwargs):
        super(RunText, self).__init__(*args, **kwargs)
        self.loopHCount = 0
        self.loopCount = 0
        self.showNetCross = False
        self.showHeatWarning = False
        self.showNetWarning = False
        self.netCheckOngoing = False
        self.queue = Queue()
        self.scrollLength = 0
        self.scrollString = ""
        self.scrollPosition = 0
        self.heatlimit = 60
        self.byteCount = 0;

    @staticmethod
    def printLog(msg, source):
        print(strftime("%H:%M:%S", gmtime()) + "@" + source + "> " + msg)

    def run(self):
        offscreen_canvas = self.matrix.CreateFrameCanvas()
        if not self.CheckPipe("pipes/mainpipe"):
            self.printLog("Pipe does not exist","PIPE")

        font = graphics.Font()
        font.LoadFont("fonts/TerminusEdit.bdf")
        font2 = graphics.Font()
        font2.LoadFont("fonts/ter-u12n.bdf")
        self.scrollPosition = offscreen_canvas.width

        pipe_fd = os.open("pipes/mainpipe", os.O_RDONLY | os.O_NONBLOCK)
        self.printLog("Opening FIFO...","PIPE")
        with os.fdopen(pipe_fd) as pipe:
            self.printLog("FIFO opened","PIPE")
            while True:
                offscreen_canvas.Clear()

                self.HandlePipeInput(pipe)
                self.DrawClock(offscreen_canvas,font)
                self.DrawScrollMessage(offscreen_canvas,font2,21)
                self.ConstructStatusBar()

                time.sleep(0.015)
                offscreen_canvas = self.matrix.SwapOnVSync(offscreen_canvas)
                if self.loopCount >= 10000: self.loopCount = 0;
                else: self.loopCount += 1
                if self.byteCount >= 100: self.byteCount = 0;
                else: self.byteCount += 2

    def AddToQueue(self,text):
        self.queue.put(text)
    def HandlePipeInput(self,pipe):
        if self.CheckPipe("pipes/mainpipe"):
            message = pipe.read()
            if message:
                if message.find('%ACT:') == -1:
                    self.AddToQueue(message.rstrip())
                else:
                    try:
                        self.HandleAction(message.split(":")[1].rstrip())
                    except IndexError: pass
                self.printLog("Received: '%s'" % message.rstrip(), "PIPE")
    def ConstructStatusBar(self,x=1,y=25):
        #Overheat Check
        temp = self.ReadCPUTemp()
        if temp > self.heatlimit:
            if self.loopHCount >= 100:
                if self.loopHCount > 10000: self.loopHCount = 100 #prevent overflow
                self.DrawHeatWarning(x,y)
                x += 9
            self.loopHCount += 1
        else:
            self.loopHCount = 0

        #Network Check
        thr = threading.Thread(target=self.CheckNet, args=(), kwargs={})
        if not self.netCheckOngoing: thr.start()
        if self.showNetWarning:
            if (self.loopCount % 50) == 0:
                self.showNetCross = not self.showNetCross
            if self.showNetCross:
                image = Image.open("bitmaps/networkmaskz.ppm")
            else:
                image = Image.open("bitmaps/network.ppm")
            self.matrix.SetImage(image, x, y)

            if self.showNetCross:
                self.DrawCross(x,y)
                x += 9
    def DrawCross(self,x,y,r=255,g=0,b=0):
        self.matrix.SetPixel(x+1,y,r,g,b)
        self.matrix.SetPixel(x+5,y,r,g,b)
        self.matrix.SetPixel(x+2,y+1,r,g,b)
        self.matrix.SetPixel(x+4,y+1,r,g,b)
        self.matrix.SetPixel(x+3,y+2,r,g,b)
        self.matrix.SetPixel(x+2,y+3,r,g,b)
        self.matrix.SetPixel(x+4,y+3,r,g,b)
        self.matrix.SetPixel(x+1,y+4,r,g,b)
        self.matrix.SetPixel(x+5,y+4,r,g,b)
    def DrawHeatWarning(self,x = 1,y = 25):
            if (self.loopCount % 20) == 0:
                self.showHeatWarning = not self.showHeatWarning
            if self.showHeatWarning:
                image = Image.open("bitmaps/overheat.ppm")
                self.matrix.SetImage(image, x, y)
    def DrawScrollMessage(self,offscreen_canvas,font,y = 10):
        if self.scrollPosition + self.scrollLength * 6 < 0 or self.scrollString == "":
            if not self.queue.empty():
                string = self.queue.get()
                self.scrollLength = len(string)
                self.scrollString = string
            else:
                self.scrollLength = 0
                self.scrollString = ""
            self.scrollPosition = offscreen_canvas.width
        elif not self.scrollString == "":
            self.scrollPosition -= 1
            graphics.DrawText(offscreen_canvas, font, self.scrollPosition, y, graphics.Color(255, 255, 255), self.scrollString)
    def DrawClock(self,offscreen_canvas,font,x = 3,y = 10):
        lenCStart = graphics.DrawText(offscreen_canvas, font, x, y, graphics.Color(255, 0, 0), "<")
        lenCHour = graphics.DrawText(offscreen_canvas, font, x + lenCStart, y, graphics.Color(255, 125, 0),
                                     time.strftime('%H'))
        lenCSep = graphics.DrawText(offscreen_canvas, font, x + lenCStart + lenCHour, y,
                                    graphics.Color(255, 0, 0), ":")
        lenCMin = graphics.DrawText(offscreen_canvas, font, x + lenCStart + lenCHour + lenCSep, y,
                                    graphics.Color(255, 125, 0), time.strftime('%M'))
        lenCSep2 = graphics.DrawText(offscreen_canvas, font, x + lenCStart + lenCHour + lenCSep + lenCMin, y,
                                     graphics.Color(255, 0, 0), ":")
        lenCSec = graphics.DrawText(offscreen_canvas, font,
                                    x + lenCStart + lenCHour + lenCSep + lenCMin + lenCSep2, y,
                                    graphics.Color(255, 125, 0), time.strftime('%S'))
        lenCEnd = graphics.DrawText(offscreen_canvas, font,
                                    x + lenCStart + lenCHour + lenCSep + lenCMin + lenCSep2 + lenCSec, y,
                                    graphics.Color(255, 0, 0), ">")
    def CheckNet(self):
        self.showNetWarning = not self.IsOnline(PING_SERVER)
    def IsOnline(self,hostname):
        self.netCheckOngoing = True;
        try:
            host = socket.gethostbyname(hostname)
            s = socket.create_connection((host, 80), 2)
            s.close()
            self.netCheckOngoing = False;
            return True
        except:
            pass
        self.netCheckOngoing = False;
        return False
    def HandleAction(self,action):
        print action

    def ReadCPUTemp(self):
        tFile = open('/sys/class/thermal/thermal_zone0/temp')
        temp = float(tFile.read())
        tFile.close()
        return temp / 1000
    def CheckPipe(self,pipe_path):
        return os.path.exists(pipe_path)


# Main function
if __name__ == "__main__":
    run_text = RunText()
    if not run_text.process():
        run_text.print_help()