# -*- coding: utf-8 -*-
import time, os, sys, socket, threading, re, sched
from time import gmtime, strftime
from PIL import Image
from Queue import Queue
import RPi.GPIO as GPIO
PING_SERVER = "www.google.com"
reload(sys)
sys.setdefaultencoding('utf8')

from base import Base
from rgbmatrix import graphics, RGBMatrix, RGBMatrixOptions
import datetime

os.chdir("/home/pi/Matrix")

sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/..'))

class RunText(Base):
    def __init__(self, *args, **kwargs):
        super(RunText, self).__init__(*args, **kwargs)
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(37, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # General
        self.requestPowerChange = 0  # 0 No, 1 Off, 2 On/Unused!
        self.simulatebutton = False
        self.forcePowerOn = True  # False
        self.power = True  # False
        self.queue = Queue()
        self.defaultscene = 0
        self.scene = 0

        # Counters
        self.loopHCount = 0
        self.loopCount = 0
        self.loopLCount = 0

        #Net/Heat Checks
        self.showNetCross = False
        self.showNetWarning = False
        self.netCheckOngoing = False
        self.showHeatWarning = False
        self.heatlimit = 70

        #Scroller
        self.scrollLength = 0
        self.scrollString = ""
        self.scrollPosition = 0
        self.scrollR = 255
        self.scrollG = 255
        self.scrollB = 255

        # Actions
        self.actionQueue = Queue()
        self.currentAction = ""

        # Flexible Counter for Actions
        self.actionCount = 0
        self.actionCountMax = 0
        self.actionCountReset = 0
        self.actionCountIncrease = 0

        # Notifications
        self.allowContent = {"Google", "Notificator", "Google Play Store", "Gmail"}
        self.blacklistedApps = {"Paket-Installer", "Game Tools", "YouTube", "reddit offline"}
        self.blacklistedTitles = {"Sound Assistant wird über anderen Apps angezeigt",
                                  "Google Play Dienste wird über anderen Apps angezeigt"}

        # Scene 1
        self.pulseClockS1 = False
        self.flickerenabletime = time.time()
        self.flickerduration = -1

        # Short Power
        self.spowerenabletime = time.time()
        self.spowerduration = -1

    @staticmethod
    def printLog(msg, source):
        print(strftime("%H:%M:%S", gmtime()) + "@" + source + "> " + msg)

    def run(self):
        self.scrollPosition = self.matrix.width
        offscreen_canvas = self.matrix.CreateFrameCanvas()
        if not self.CheckPipe("pipes/mainpipe"):
            self.printLog("Pipe does not exist", "PIPE")

        font = self.InitFont("fonts/TerminusEdit.bdf")
        font2 = self.InitFont("fonts/ter-u12n.bdf")
        bigfont = self.InitFont("fonts/other/ie9x14u.bdf")
        bigfont2 = self.InitFont("fonts/5x7_edit.bdf")

        pipe_fd = os.open("pipes/mainpipe", os.O_RDONLY | os.O_NONBLOCK)
        self.printLog("Opening FIFO...","PIPE")
        with os.fdopen(pipe_fd) as pipe:
            self.printLog("FIFO opened", "PIPE")
            powered = self.power
            while True:
                #Clear background buffer
                offscreen_canvas.Clear()

                # Check Pipe and handle incoming messages
                if self.requestPowerChange == 0:
                    self.HandlePipeInput(pipe)
                    self.ProcessAction()

                gpio_btn = GPIO.input(37)
                if not gpio_btn: self.power = True

                # Draw to background buffer
                if self.power:
                    self.DrawAll(offscreen_canvas, font, font2, bigfont, bigfont2)
                    if self.requestPowerChange == 0: powered = True
                if powered and gpio_btn and (
                        self.scrollString == "" and not (self.forcePowerOn or self.simulatebutton)):
                    self.requestPowerChange = 1
                    self.loopLCount = 0
                    powered = False

                time.sleep(0.018)

                # Turn LEDs smoothly off if necessary
                self.HandlePowerOff(offscreen_canvas, font, font2, bigfont, bigfont2)

                if not self.spowerduration == -1 and self.time_passed(self.spowerenabletime, self.spowerduration):
                    self.requestPowerChange = 1
                    self.spowerduration = -1

                #Increment counters
                if self.loopCount >= 10000: self.loopCount = 0;
                else: self.loopCount += 1

                if not self.actionCountMax == 0 and self.actionCount >= self.actionCountMax:
                    self.actionCount = self.actionCountReset;
                else:
                    self.actionCount += self.actionCountIncrease

                # Swap background buffer to foreground
                offscreen_canvas = self.matrix.SwapOnVSync(offscreen_canvas)

    # Actions
    def ProcessAction(self):
        if self.currentAction == "":
            if not self.actionQueue.empty():
                self.SetActionCounter(0, 0, 0, 0)  # Reset counter
                self.currentAction = self.actionQueue.get()
                if self.currentAction == "dim":
                    self.SetActionCounter(0, 0, 0, 5)
                elif self.currentAction == "bright":
                    self.SetActionCounter(0, 0, 0, 5)
            else:
                return
        a = self.currentAction
        self.currentAction = ""
        if a == "dim":
            if self.actionCount >= 97:
                self.currentAction = ""
                self.SetActionCounter(0, 0, 0, 0)
                self.matrix.brightness = 5
            else:
                self.matrix.brightness = 100 - self.actionCount
        elif a == "bright":
            if self.actionCount >= 100:
                self.currentAction = ""
                self.SetActionCounter(0, 0, 0, 0)
                self.matrix.brightness = 100
            else:
                self.matrix.brightness = self.actionCount
        elif a == "powercycle":
            self.forcePowerOn = True  # False
            self.power = True
            self.spowerduration = 3
            self.spowerenabletime = time.time()

        elif a == "poweron":
            self.power = True
            self.forcePowerOn = True
        elif a == "poweroff":
            if self.power:
                self.requestPowerChange = 1
            self.power = False
            self.forcePowerOn = False
        elif a.startswith("flicker"):
            duration = re.sub('[^0-9]', '', a)
            self.simulatebutton = True  # False
            if duration == "":
                self.flickerduration = 30
            else:
                self.flickerduration = duration
            self.power = True
            self.SwitchScene(2)
            self.flickerenabletime = time.time()
        elif a.startswith("scene"):
            data = re.sub('[^0-9]', '', a)
            self.power = True
            self.simulatebutton = True
            self.SwitchScene(int(data))
        elif a.find("notification") == 0:
            data = re.split("\|\|\|", a)
            if len(data) <= 2:
                return
            elif len(data) <= 3:
                self.HandleNotification(data[1], data[2])
            else:
                self.HandleNotification(data[1], data[2], data[3])

    def SetActionCounter(self, count, max, reset, increase):
        if not count == -1: self.actionCount = count
        if not max == -1: self.actionCountMax = max
        if not reset == -1: self.actionCountReset = reset
        if not increase == -1: self.actionCountIncrease = increase

    # Notifications
    def HandleNotification(self, app, title, content=""):
        if content == "%evtprm3": content = ""
        if app in self.blacklistedApps:
            self.printLog(app + " is blacklisted", "NOTY")
        elif title in self.blacklistedTitles:
            self.printLog(app + " is blacklisted (Title)", "NOTY")
        else:
            self.power = True
            color = self.GetColorByName(app)
            if app in self.allowContent:
                self.AddToQueue(app + ": " + title + "; " + content + "|||" + color)
            else:
                self.AddToQueue(app + ": " + title + "|||" + color)

    def GetColorByName(self, app):
        if app == "WhatsApp":
            return "0,255,0"
        elif app == "Twitter":
            return "0,70,255"
        else:
            return "255,255,255"

    # Queue
    def AddToQueue(self, text, color=""):
        if color == "":
            self.queue.put(text)
        else:
            self.queue.put(text + "|||" + color)

    def AddToActionQueue(self, text):
        self.actionQueue.put(text)

    # Power
    def HandlePowerOff(self, offscreen_canvas, font, font2, bigfont, bigfont2):
        if self.requestPowerChange == 1:
            self.DrawAll(offscreen_canvas, font, font2, bigfont, bigfont2)
            for y in range(0, self.loopLCount):
                graphics.DrawLine(offscreen_canvas, 0, y, 64, y, graphics.Color(0, 0, 0))
            if self.loopLCount > 32:
                self.loopLCount = 0;
                self.requestPowerChange = 0
                self.power = False
            self.loopLCount += 1
    #Pipe
    def HandlePipeInput(self,pipe):
        if self.CheckPipe("pipes/mainpipe"):
            message = pipe.read()
            if message:
                if message.find('%ACT:') == -1:
                    self.printLog("Text: '%s'" % message.rstrip(), "PIPE")
                    self.power = True
                    self.AddToQueue(message.rstrip())
                else:
                    try:
                        self.printLog("Action: '%s'" % message.split(":")[1].rstrip(), "PIPE")
                        self.AddToActionQueue(message.split(":")[1].rstrip())
                    except IndexError:
                        self.printLog("Malformed action command", "PIPE")
                        pass

    def CheckPipe(self, pipe_path):
        return os.path.exists(pipe_path)

    # Draw Routines
    def SwitchScene(self, scene):
        self.scene = scene

    def DrawAll(self, offscreen_canvas, font, font2, bigfont, bigfont2):
        if self.scene == 0:
            self.DrawClock(offscreen_canvas, bigfont, 3, 10, True, False)
            self.DrawSeconds(offscreen_canvas, bigfont2, 50)
            self.DrawScrollMessage(offscreen_canvas, bigfont2, 21)
            self.ConstructStatusBar()
        elif self.scene == 1:
            self.DrawClock(offscreen_canvas, font)
            self.DrawScrollMessage(offscreen_canvas, font2, 21)
            self.ConstructStatusBar()
        elif self.scene == 2:
            if self.time_passed(self.flickerenabletime, int(self.flickerduration) - 2):
                self.simulatebutton = False  # Prepare power off

            if self.time_passed(self.flickerenabletime, self.flickerduration):
                self.SwitchScene(self.defaultscene)
                self.flickerduration = -1

            if (self.loopCount % 30) == 0:
                self.pulseClockS1 = not self.pulseClockS1
            self.DrawClock(offscreen_canvas, bigfont, 3, 16, True, self.pulseClockS1)
            self.DrawSeconds(offscreen_canvas, bigfont2, 50, 16)
            self.DrawScrollMessage(offscreen_canvas, bigfont2, 26)

    def ConstructStatusBar(self, x=1, y=25):
        #Overheat
        temp = self.ReadCPUTemp()
        if temp > self.heatlimit:
            if self.loopHCount >= 100:
                if self.loopHCount > 10000: self.loopHCount = 100 #prevent overflow
                self.DrawHeatWarning(x,y)
                x += 9
            self.loopHCount += 1
        else:
            self.loopHCount = 0
        #Network
        thr = threading.Thread(target=self.CheckNet, args=(), kwargs={})
        if not self.netCheckOngoing: thr.start()
        if self.showNetWarning:
            if (self.loopCount % 50) == 0:
                self.showNetCross = not self.showNetCross
            if self.showNetCross:
                image = Image.open("bitmaps/networkmask.ppm")
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
                data = re.split("\|\|\|", string)
                if len(data) <= 1:
                    self.scrollLength = len(string)
                    self.scrollString = string
                    self.scrollR = 255
                    self.scrollG = 255
                    self.scrollB = 255
                else:
                    self.scrollLength = len(data[0])
                    self.scrollString = data[0]
                    color = data[1].split(",")
                    if len(color) == 3:
                        self.scrollR = int(color[0])
                        self.scrollG = int(color[1])
                        self.scrollB = int(color[2])
            else:
                self.scrollLength = 0
                self.scrollString = ""
                self.scrollPosition = offscreen_canvas.width
        elif not self.scrollString == "":
            self.scrollPosition -= 1
            graphics.DrawText(offscreen_canvas, font, self.scrollPosition, y,
                              graphics.Color(self.scrollR, self.scrollG, self.scrollB), self.scrollString)

    def DrawClock(self, offscreen_canvas, font, x=3, y=10, small=False, hide=False):
        if hide:
            digitColor = graphics.Color(0, 0, 0)
        else:
            digitColor = graphics.Color(255, 125, 0)
        seperatorColor = graphics.Color(255, 0, 0)
        if not small:
            lenCStart = graphics.DrawText(offscreen_canvas, font, x, y, seperatorColor, "<")
        else:
            lenCStart = 0

        lenCHour = graphics.DrawText(offscreen_canvas, font, x + lenCStart, y,digitColor ,
                                     time.strftime('%H'))
        lenCSep = graphics.DrawText(offscreen_canvas, font, x + lenCStart + lenCHour, y,
                                    seperatorColor, ":")
        lenCMin = graphics.DrawText(offscreen_canvas, font, x + lenCStart + lenCHour + lenCSep, y,
                                    digitColor, time.strftime('%M'))

        if not small:
            lenCSep2 = graphics.DrawText(offscreen_canvas, font, x + lenCStart + lenCHour + lenCSep + lenCMin, y,
                                         seperatorColor, ":")
        else:
            lenCSep2 = 0
        if not small:
            lenCSec = graphics.DrawText(offscreen_canvas, font,
                                        x + lenCStart + lenCHour + lenCSep + lenCMin + lenCSep2, y,
                                        digitColor, time.strftime('%S'))
        else:
            lenCSec = 0
        if not small:
            lenCEnd = graphics.DrawText(offscreen_canvas, font,
                                        x + lenCStart + lenCHour + lenCSep + lenCMin + lenCSep2 + lenCSec, y,
                                        seperatorColor, ">")
        else:
            lenCEnd = 0

    def DrawSeconds(self, offscreen_canvas, font, x=3, y=10):
        lenCSec = graphics.DrawText(offscreen_canvas, font,
                                    x, y,
                                    graphics.Color(255, 125, 0), time.strftime('%S'))

    def InitFont(self, path):
        font = graphics.Font()
        font.LoadFont(path)
        return font
    #Network Checks
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

    #Temperature Checks
    def ReadCPUTemp(self):
        tFile = open('/sys/class/thermal/thermal_zone0/temp')
        temp = float(tFile.read())
        tFile.close()
        return temp / 1000

    # Time
    def time_passed(self, oldepoch, duration_sec):
        return time.time() - oldepoch >= float(duration_sec)

# Main function
if __name__ == "__main__":
    run_text = RunText()
    if not run_text.process():
        run_text.print_help()