import sys
import picamera
import Adafruit_GPIO.SPI as SPI
import Adafruit_SSD1306
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
import shutil
from multiprocessing.dummy import Pool as ThreadPool
from subprocess import check_call as run
SRC_DIR = "$HOME/.src" # checkout directory
TGT_DIR = "/home/pi/pywork/ViewHive/" # update target
UPDATE_CMD = ( # base command
'pip install --src="%s" --target %s --upgrade -e ' 
'git://github.com/damonmcc/ViewHive.git@master#egg=ViewHive'
) % (SRC_DIR, TGT_DIR)
from viewhive.WittyPi import *
loggerVH = logging.getLogger('vhutil')
VH_VERSION = "0.9.7.4"
# FONT_PATH = os.environ.get("FONT_PATH", "/viewhive/GameCube.ttf")


def progressUpdate(bytescopied):
    print(bytescopied)


class Display(object):
    def __init__(self, **k_parems):
        loggerVH.info('Display instance starting, at %s with parems:' % now(), k_parems)
        loggerVH.debug("Display initiated")
        time.sleep(1)
        RST = 24
        DC = 23
        SPI_PORT = 0
        SPI_DEVICE = 0
        self.disp = Adafruit_SSD1306.SSD1306_128_32(rst=RST, dc=DC,
                                                    spi=SPI.SpiDev(SPI_PORT, SPI_DEVICE, max_speed_hz=8000000))

        # Initialize library and display constants.
        self.disp.begin()

        self.width = self.disp.width    # 128 pixels
        self.height = self.disp.height  # 32 pixels
        self.padding = 4
        self.textHpad = 5
        self.shape_width = 20
        self.top = self.padding*2.5
        # self.top = 0
        self.bottom = self.height - self.padding*2

        # Clear display.
        self.disp.clear()
        self.disp.display()

        # Create blank image for drawing.
        # Make sure to create image with mode '1' for 1-bit color.
        width = self.disp.width
        height = self.disp.height
        self.image = Image.new('1', (width, height))

        # Get drawing object to draw on image.
        self.draw = ImageDraw.Draw(self.image)

        loggerVH.debug("Current Working Directory: {}".format(os.getcwd()))
        self.fontDefault = ImageFont.load_default()
        # self.font = ImageFont.load("GameCube.ttf")
        self.font = ImageFont.truetype("viewhive/GameCube.ttf", 6)
        self.fontBig = ImageFont.truetype("viewhive/GameCube.ttf", 7)
        self.extraInfo = ''

        loggerVH.debug('..schedule..')
        if 'schedule' in k_parems:
            # If the assigned schedule is listed...
            self.schedule = k_parems['schedule']
        else:
            loggerVH.debug('..Using VHScriptIMPORT from wittyPi..')
            self.schedule = Schedule("Import", "/home/pi/wittyPi/schedules/VHScriptIMPORT.wpi")
        # Call schedule sync function
        self.schedule.sync()
        loggerVH.debug('...')

        # Create a navigation object with menus and knob features
        loggerVH.debug('..navigation..')
        self.nav = Navigation()
        # Create a navigation object for time entry
        self.navTime = Navigation(menu=menuTime)
        # Create a navigation object for viewing events
        self.navView = Navigation(menu=menuView(self.schedule.events))
        loggerVH.debug('...')

        self.mode = -1
        self.fresh = True
        self.manual = False

        # Length of decay countdown in minutes
        self.decayLength = 5
        # Initialize decay countdown: self.decay is a future time to shutdown
        self.decay = code1440(nowti()) + self.decayLength

        loggerVH.debug('..cam..')
        if 'cam' in k_parems and k_parems['cam']:
            # If cam is listed as True...
            try:
                recorder = Recorder()
            except Exception as inst:
                # screen.addstr(11, 1,"*CAM error: %s"% inst)
                # NameError: name 'screen' is not found
                loggerVH.error("Recorder/camera creation exception: %s" % inst)
                self.mode = 'ERR'
                self.draw.text((1, 1), 'CAM ERROR', font=self.font, fill=255)
            else:
                self.cam = recorder
                loggerVH.debug('...cam created..')
        else:
            self.recorder = []
            loggerVH.warning('...blank cam created..')
        self.calibrate()

    def update(self):
        """Refresh display."""
        self.disp.image(self.image)
        self.disp.display()

    def calibrate(self):
        """Draw shapes and menu text to confirm screen size
        and font loading."""
        # Draw a black filled box to clear the image.
        self.draw.rectangle((0, 0, self.width, self.height), outline=0, fill=0)
        # Move left to right keeping track of the current x position for drawing shapes.
        x = self.padding
        # Draw an ellipse.
        self.draw.ellipse((x, self.top, x + self.shape_width, self.bottom), outline=255, fill=0)
        x += self.shape_width + self.padding
        # Draw a rectangle.
        self.draw.rectangle((x, self.top, x + self.shape_width, self.bottom), outline=255, fill=0)
        x += self.shape_width + self.padding
        # Draw a triangle.
        self.draw.polygon([(x, self.bottom), (x + self.shape_width / 2, self.top), (x + self.shape_width, self.bottom)],
                          outline=255, fill=0)
        x += self.shape_width + self.padding
        # Draw an X.
        self.draw.line((x, self.bottom, x + self.shape_width, self.top), fill=255)
        self.draw.line((x, self.top, x + self.shape_width, self.bottom), fill=255)
        x += self.shape_width + self.padding

        # Write two lines of text.
        self.draw.text((x, self.top - 2), '    ', font=self.font, fill=255)
        self.draw.text((x, self.top + 8), '    ', font=self.font, fill=255)
        self.draw.text((x - 15, self.top + 15), 'V: ' + str(VH_VERSION),
                       font=self.font, fill=255)
        if self.mode == 'ERR':
            self.draw.text((1, 1), 'CAM ERROR', font=self.font, fill=255)
        self.update()
        time.sleep(5)

    def runNavigation(self):
        """Main camera navigation logic. """
        loggerVH.info('runNavigation (camera menu) started')
        while True:
            # os.system("clear")
            # self.nav.menuMain.display()
            self.tabCurrent()
            self.timeBar()
            self.eventsBar()
            if self.cam.recording:
                self.dot()
                self.cam.refresh()
            else:
                # Check for inactivity
                if code1440(nowti()) == self.decay:
                    self.shutdown()
            if self.liveNow():
                # print("live!!!!!!!!")
                if not self.cam.recording: self.cam.start()
                # Restart shutdown counter if recording
                self.decay = code1440(nowti()) + self.decayLength
            else:
                if self.cam.recording and not self.manual: self.cam.stop()
                # print("Will shutdown at " + code2400(str(self.decay)))
            self.update()

            actionString = self.nav.menuMain.action()
            if actionString == 'exec_joke':
                self.clearEvents()
            elif actionString == 'exec_add_conf':
                self.extraInfo = ''
                self.tabEvent()
                self.decay = code1440(nowti()) + self.decayLength
                self.nav.menuMain.up()
            elif actionString == 'exec_del_events':
                self.clearEvents()
                self.decay = code1440(nowti()) + self.decayLength
                self.nav.menuMain.up()
            elif actionString == 'exec_rec_now':
                if self.cam.recording:
                    # print('!recording already!')
                    pass
                else:
                    self.cam.start()
                    self.manual = True
                    self.nav.menuMain.up()
            elif actionString == 'exec_stop_now':
                self.tabCurrent()
                self.update()
                if self.cam.recording:
                    self.cam.stop()
                    self.manual = False
                    self.decay = code1440(nowti()) + self.decayLength
                    self.nav.menuMain.up()
                else:
                    # print('!not recording!')
                    pass
            elif actionString == 'exec_day_view':
                # Restart shutdown counter if events viewed
                self.decay = code1440(nowti()) + self.decayLength
                res = self.viewEvents()
            elif actionString == "exec_copy":
                self.extraInfo = 'USB...'
                self.tabCurrentInfo()
                self.update()
                if self.cam.copy():
                    self.extraInfo = 'Done!'
                    self.update()
                    time.sleep(2)
                    self.nav.menuMain.up()
                    self.nav.menuMain.up()
                else:
                    self.extraInfo = 'Failed!'
                    self.update()
                    time.sleep(4)
                    self.nav.menuMain.up()
                    self.nav.menuMain.up()
                self.decay = code1440(nowti()) + self.decayLength
            elif actionString == 'exec_storage':
                self.decay = code1440(nowti()) + self.decayLength
                if not self.viewVideos():
                    self.nav.menuMain.up()
                self.decay = code1440(nowti()) + self.decayLength
            elif actionString == 'exec_del_storage':
                self.clearVideos()
                self.decay = code1440(nowti()) + self.decayLength
                self.nav.menuMain.up()
            elif actionString == 'exec_cam_prev':
                self.cam.previewToggle()
                self.nav.menuMain.up()
                self.decay = code1440(nowti()) + self.decayLength
            elif actionString == 'exec_updateVH':
                self.updateVH()
            elif actionString == 'exec_showVersion':
                self.viewVersion()
                print('Version: ' + VH_VERSION)
                self.update()
                time.sleep(3)
                self.decay = code1440(nowti()) + self.decayLength
                self.nav.menuMain.up()
            elif actionString == 'exec_wifi_show':
                print(show_wifi())
            elif actionString == 'exec_ip_show':
                self.viewIP()
                print('IP: ' + show_ip())
                self.update()
                time.sleep(3)
                self.decay = code1440(nowti()) + self.decayLength
                self.nav.menuMain.up()
            elif actionString == 'exec_time_show':
                print(show_time())
                print(now())
            elif actionString == 'exec_time_set':
                # print(sync_time())
                self.setTime()
                self.nav.menuMain.up()
                time.sleep(3)
            elif actionString == 'exec_wifi_up':
                wifi_up()
                time.sleep(3)
                self.nav.menuMain.up()
            elif actionString == 'exec_wifi_down':
                wifi_down()
                time.sleep(3)
                self.nav.menuMain.up()
            elif actionString == 'softstop':
                print('!!stopping program!!'.format(nowdts()))
                sleepTic = 0.5
                deathTics = 7
                i = 0
                while i < deathTics:
                    self.viewDeath(i)
                    self.update()
                    time.sleep(sleepTic)
                    i += 1
                break
            elif actionString == 'shutdown':
                loggerVH.warning('!!!!SHUTTING DOWN at {}!!!!'.format(nowdts()))
                sleepTic = 1
                deathTics = 8
                i = 0
                while i < deathTics:
                    self.viewDeath(i)
                    self.update()
                    time.sleep(sleepTic)
                    i += 1
                self.shutdown()
            elif actionString == 1:
                loggerVH.debug('HI')
            elif actionString == -1:
                loggerVH.warning('EXIT FROM TOP MENU')
            # else:
                # loggerVH.debug(actionString)
                # print(actionString)
            self.update()

    def viewEvents(self):
        if len(self.schedule.events) < 1:
            # loggerVH.debug('!NO EVENTS!')
            # print('!NO EVENTS!')
            # self.tabViewMenu()
            # self.update()
            return
        # Refresh events list used in event navigation object
        mv = menuView(self.schedule.events)
        self.navView = Navigation(menu=mv)
        while True:
            # os.system("clear")
            # self.nav.menuMain.display()
            # self.tabCurrent()
            self.timeBar()
            self.tabViewMenu()
            self.eventsBar()
            if self.cam.recording:
                self.dot()
                self.cam.refresh()
            if self.liveNow():
                if not self.cam.recording: self.cam.start()
            else:
                if self.cam.recording and not self.manual: self.cam.stop()
            self.update()
            actionString = self.nav.menuMain.action()

            if self.navView.actionString is None:
                break
            if self.navView.actionString == "L0":
                return "LO exit"

    def viewVideos(self):
        """
        Create a menuView for viewing saved videos in a given path
        """
        pathVideos = self.cam.dstroot
        pathVideosUSB = self.cam.usbroot
        videos = []
        p = subprocess.Popen("ls", shell=True,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             cwd=pathVideos)
        p_status = p.wait()
        for line in iter(p.stdout.readline, b''):
            print(line),
            temp = line.decode("utf-8")
            print(temp)
            vid = temp
            videos.append(vid)
        if len(videos) < 1:
            print('!NO VIDEOS!')
            return False
        mv = menuView(videos, files=True)
        self.navView = Navigation(menu=mv)
        while True:
            # os.system("clear")
            # self.tabCurrent()
            self.timeBar()
            self.tabViewMenu()
            if self.cam.recording:
                self.cam.refresh()
            self.update()
            if self.navView.actionString is None:
                break
            if self.navView.actionString == "L0":
                return "LO exit"
    def viewIP(self):
        ip_addr = show_ip()
        """Redraw the info tab with the time """
        tabWidth = 30
        x = self.padding + tabWidth
        # Draw a small black filled box to clear the image.
        self.draw.rectangle((x, self.top, self.width, self.bottom), outline=0, fill=0)
        self.draw.polygon([(x, self.top), (x + tabWidth*2, self.top),
                           (x + tabWidth*2 + (tabWidth / 2)+10, self.height / 2),
                           (x + tabWidth*2, self.bottom), (x, self.bottom)
                           ],
                          outline=0, fill=255)
        self.draw.text((x + self.padding, self.height / 2 - self.textHpad),
                       ip_addr, font=self.fontDefault, fill=0)
        # self.draw.text((self.padding, self.height / 2 - self.textHpad),
        #                self.navTime.menuMain.displayCurrent(), font=self.font, fill=0)
    def viewVersion(self):
        ip_addr = show_ip()
        """Redraw the info tab with the time """
        tabWidth = 30
        x = self.padding + tabWidth
        # Draw a small black filled box to clear the image.
        self.draw.rectangle((x, self.top, self.width, self.bottom), outline=0, fill=0)
        self.draw.polygon([(x, self.top), (x + tabWidth*2, self.top),
                           (x + tabWidth*2 + (tabWidth / 2)+10, self.height / 2),
                           (x + tabWidth*2, self.bottom), (x, self.bottom)
                           ],
                          outline=0, fill=255)
        self.draw.text((x + self.padding, self.height / 2 - self.textHpad),
                       VH_VERSION, font=self.fontDefault, fill=0)
        # self.draw.text((self.padding, self.height / 2 - self.textHpad),
        #                self.navTime.menuMain.displayCurrent(), font=self.font, fill=0)

    def tabEvent(self):
        """Redraw the display to show time event time entry menus"""
        tabWidth = 60
        x = self.padding
        # # Draw a small black filled box to clear the image.
        # self.draw.rectangle((0, 0, self.width, self.height), outline=0, fill=0)
        # Draw white tab and current menu choice
        self.draw.polygon([(0, self.top), (tabWidth, self.top),
                           (tabWidth + (tabWidth / 2), self.height / 2),
                           (tabWidth, self.bottom), (0, self.bottom)
                           ],
                          outline=20, fill=255)
        self.draw.text((self.padding, self.height / 2 - 3),
                       'Start:', font=self.font, fill=0)
        start = self.chooseTime()
        loggerVH.debug("Start time will be:" + start)
        # Redraw tab and Length title
        self.draw.polygon([(0, self.top), (tabWidth, self.top),
                           (tabWidth + (tabWidth / 2), self.height / 2),
                           (tabWidth, self.bottom), (0, self.bottom)
                           ],
                          outline=20, fill=255)
        self.draw.text((self.padding/2, self.top+1),
                       'Length:', font=self.font, fill=0)
        self.draw.text((self.padding, self.height / 2 + 1),
                       start, font=self.font, fill=0)
        length = self.chooseTime()

        if int(length) == 0:
            self.draw.text((1, self.height / 2 - 3), 'Length of 0?', font=self.font, fill=0)
            self.update()
            time.sleep(3)
        elif not length:    # If chooseTime returns false...
            loggerVH.error("Length entry failed, leaving addEvent")
            # Redraw tab
            self.draw.text((1, self.height / 2 - 3), 'FAILED',
                           font=self.font, fill=0)
            self.update()
            time.sleep(3)
        else:
            # Call schedule add function
            self.schedule.addEvent(start, length)
            # Redraw tab
            self.draw.polygon([(0, self.top), (tabWidth, self.top),
                               (tabWidth + (tabWidth / 2), self.height / 2),
                               (tabWidth, self.bottom), (0, self.bottom)
                               ],
                              outline=20, fill=255)
            self.draw.text((1, self.height / 2 - 3), 'ADDED...',
                           font=self.font, fill=0)
            self.update()
            # Call schedule sync function
            self.schedule.sync()
            # Redraw tab
            self.draw.polygon([(0, self.top), (tabWidth, self.top),
                               (tabWidth + (tabWidth / 2), self.height / 2),
                               (tabWidth, self.bottom), (0, self.bottom)
                               ],
                              outline=20, fill=255)
            self.draw.text((1, self.height / 2 - 3), 'SYNCED',
                           font=self.font, fill=0)
            self.update()
            time.sleep(3)

    def clearEvents(self):
        if len(self.schedule.events) > 0:
            # Call schedule clear function
            self.draw.text((1, self.height / 2), 'Clearing...', font=self.font, fill=1)
            self.schedule.clearAllEvents()
            # Call schedule sync function
            self.schedule.sync()
            time.sleep(3)
        else:
            pass

    def clearVideos(self):
        try:
            # Call video clear function
            self.draw.text((1, self.height / 2), 'Clearing...', font=self.font, fill=1)
            # Delete with unlink
            for root, dirs, files in os.walk(self.cam.dstroot):
                for f in files:
                    os.unlink(os.path.join(root, f))
                for d in dirs:
                    shutil.rmtree(os.path.join(root, d))
            # time.sleep(3)
            loggerVH.info("Deleting videos from %s" % self.cam.dstroot)
        except Exception as inst:
            raise

    def setTime(self):
        """Redraw the left-most tab with current menu choice"""
        tabWidth = 60
        x = self.padding
        # # Draw a small black filled box to clear the image.
        # self.draw.rectangle((0, 0, self.width, self.height), outline=0, fill=0)
        # Draw white tab and current menu choice
        self.draw.polygon([(0, self.top), (tabWidth, self.top),
                           (tabWidth + (tabWidth / 2), self.height / 2),
                           (tabWidth, self.bottom), (0, self.bottom)
                           ],
                          outline=20, fill=255)
        self.draw.text((self.padding, self.height / 2 - 3),
                       'mmdd:', font=self.font, fill=0)
        curMMDD = self.chooseTime()
        loggerVH.debug("setting mmdd: "+curMMDD)
        # Draw white tab and current menu choice
        self.draw.polygon([(0, self.top), (tabWidth, self.top),
                           (tabWidth + (tabWidth / 2), self.height / 2),
                           (tabWidth, self.bottom), (0, self.bottom)
                           ],
                          outline=20, fill=255)
        self.draw.text((self.padding, self.height / 2 - 3),
                       'Time:', font=self.font, fill=0)
        curTime = self.chooseTime()
        loggerVH.debug("setting time: "+curTime)
        # Draw white tab and current menu choice
        self.draw.polygon([(0, self.top), (tabWidth, self.top),
                           (tabWidth + (tabWidth / 2), self.height / 2),
                           (tabWidth, self.bottom), (0, self.bottom)
                           ],
                          outline=20, fill=255)
        self.draw.text((self.padding, self.height / 2 - 3),
                       'Year:', font=self.font, fill=0)
        curYear = self.chooseTime()
        loggerVH.debug("setting year: "+curYear)
        try:
            if int(curTime) > 2400:
                loggerVH.error("Entered weird time: " + curTime)
                self.draw.text((1, self.height / 2), 'Weird Time!', font=self.font, fill=1)
            else:
                # Call schedule add function
                set_system_time(curMMDD, curTime, curYear)
                self.draw.text((1, self.height / 2), 'ADDED...', font=self.font, fill=1)
                # Call schedule sync function
                self.schedule.sync()
                self.draw.text((1, self.height / 2), 'SYNCED', font=self.font, fill=1)
                loggerVH.info("Time set to: {} {} {}".format(curMMDD, curTime, curYear))
        except:
            loggerVH.error("setTime failed")
        time.sleep(3)

    def chooseTime(self):
        mt = menuTime(TimeMenu)
        self.navTime = Navigation(menu=mt)
        while True:
            # os.system("clear")
            # self.navTime.menuMain.display()
            self.tabTimeMenu()
            self.update()

            # Return if the time is at 4 digits
            if len(self.navTime.menuMain.time) > 3:
                loggerVH.debug("..the time is ready"+self.navTime.menuMain.time)
                self.navTime.menuMain.display()
                self.tabTimeMenu()
                self.update()
                # time.sleep(2)
                return self.navTime.menuMain.time

            # Otherwise, go up if a digit was chosen and continue
            if isinstance(self.navTime.actionString, str):
                # If a number action was selected,
                # go back up to display level
                # action = self.navTime.menuMain.action()
                # loggerVH.debug("..action is a string")
                # time.sleep(1)
                self.navTime.menuMain.up()

            if self.navTime.actionString is None:
                loggerVH.debug("..time shorter than 4 digits")
                # if self.navTime.menuMain.time == 0:
                #     loggerVH.debug("time ABORTED")
                #     self.extraInfo = "ABORTED!"
                #     self.navTime.menuMain.display()
                #     self.tabTimeMenu()
                #     self.update()
                #     time.sleep(2)
                #     return False
                return self.navTime.menuMain.displayTime()

            elif self.navTime.actionString == -2:
                loggerVH.debug("time shortened")

    def chooseTimeTest(self):
        mt = menuTime(TimeMenu)
        self.navTime = Navigation(menu=mt)
        while True:
            # os.system("clear")
            self.navTime.menuMain.display()
            self.tabTimeMenu()
            self.update()
            # loggerVH.debug(action)
            c = getch()
            if c == "x": break
            if c == "n": self.navTime.menuMain.next()  # Simulate NEXT button
            if c == "s":  # Simulate SELECT button
                s = self.navTime.menuMain.select()
                if s:
                    if s == -1: break
                    action = self.navTime.menuMain.action()
                    self.navTime.menuMain.up()
        return self.navTime.menuMain.displayTime()

    def tabCurrent(self):
        """Redraw the left-most tab with current menu choice"""
        tabWidth = 62
        x = self.padding
        # Draw a small black filled box to clear the image.
        self.draw.rectangle((0, 0, self.width, self.height), outline=0, fill=0)
        # Draw white tab and current menu choice
        self.draw.polygon([(0, self.top), (tabWidth, self.top),
                           (tabWidth+(tabWidth/6), self.height/2),
                           (tabWidth, self.bottom), (0, self.bottom)
                           ],
                          outline=20, fill=255)
        self.draw.text((self.padding, self.height/2-3),
                       self.nav.menuMain.displayCurrent(), font=self.font, fill=0)

    def tabCurrentInfo(self):
        """Redraw info tab with current menu choice's extra info"""
        tabWidth = 50
        x = self.padding
        # Draw a small black filled box to clear the image.
        self.draw.rectangle((0, 0, self.width, self.height), outline=0, fill=0)
        # Draw white tab and current menu choice
        self.draw.polygon([(0, self.top), (tabWidth, self.top),
                           (tabWidth+(tabWidth/2), self.height/2),
                           (tabWidth, self.bottom), (0, self.bottom)
                           ],
                          outline=20, fill=255)
        self.draw.text((self.padding, self.height/2-3),
                       self.nav.menuMain.displayCurrent(), font=self.font, fill=0)
        tabWidth = 40
        x = self.padding + tabWidth
        # Draw a small black filled box to clear the image.
        # self.draw.rectangle((x, self.top, self.width, self.bottom), outline=0, fill=0)
        # Draw second tab and text
        self.draw.polygon([(x, self.top), (x + tabWidth, self.top),
                           (x + tabWidth + (tabWidth / 2), self.height / 2),
                           (x + tabWidth, self.bottom), (x, self.bottom)
                           ],
                          outline=0, fill=255)
        self.draw.text((x + self.padding, self.height / 2 - self.textHpad),
                       self.extraInfo, font=self.fontDefault, fill=0)

    def tabTimeMenu(self):
        """Redraw the info tab with the time as it's entered"""
        tabWidth = 60
        x = self.padding + 30
        # Draw a small black filled box to clear the image.
        self.draw.rectangle((x, self.top, self.width, self.bottom), outline=0, fill=0)
        self.draw.polygon([(x, self.top), (x+tabWidth, self.top),
                           (x+tabWidth + (tabWidth / 2), self.height / 2),
                           (x+tabWidth, self.bottom), (x, self.bottom)
                           ],
                          outline=0, fill=255)
        self.draw.text((x + self.padding, self.height / 2 - self.textHpad),
                       self.navTime.menuMain.time, font=self.fontDefault, fill=0)
        self.draw.text((x + 30 - self.padding*2, self.height / 2 - self.textHpad),
                       self.navTime.menuMain.displayCurrent(), font=self.fontDefault, fill=0)
        self.draw.text((x + 30, self.height / 2 - self.textHpad),
                       self.extraInfo, font=self.fontDefault, fill=0)

    def tabViewMenu(self):
        """Draw the currently selected event details"""
        tabWidth = 30
        x = self.padding + tabWidth
        tabScale = 2.5
        # Draw a small black filled box to clear the image.
        self.draw.rectangle((x, self.top, self.width,
                             self.bottom+self.padding), outline=0, fill=0)
        # Draw tab
        self.draw.polygon([(x, self.top), (x + tabWidth*tabScale, self.top),
                           (x + tabWidth*tabScale + (tabWidth / 2), self.height / 2),
                           (x + tabWidth*tabScale, self.bottom), (x, self.bottom)
                           ],
                          outline=0, fill=255)
        # Draw text, split into two lines if too long for screen
        textCut = 11
        if len(self.navView.menuMain.displayCurrent()) > textCut:
            self.draw.polygon([(x, self.top), (x + tabWidth * tabScale, self.top),
                               (x + tabWidth * tabScale + (tabWidth / 2), self.height / 2),
                               (x + tabWidth * tabScale, self.bottom+self.padding),
                               (x, self.bottom+self.padding)
                               ],
                              outline=0, fill=255)
            # ImageFont.truetype("electroharmonix.ttf"
            text = self.navView.menuMain.displayCurrent()
            self.draw.text((x + self.padding, self.height / 2 - self.textHpad-1),
                           text[:textCut],
                           font=self.fontDefault, fill=0)
            self.draw.text((x + self.padding, self.height / 2 + 1),
                           text[textCut:len(text)],
                           font=self.fontDefault, fill=0)
        else:
            self.draw.text((x + self.padding, self.height / 2 - self.textHpad),
                       self.navView.menuMain.displayCurrent(), font=self.fontDefault, fill=0)

        # self.draw.text((self.padding, self.height / 2 - 3),
        #                self.navTime.menuMain.displayCurrent(), font=self.font, fill=0)

    def dot(self):
        # Draw a dot to show the camera is recording.
        x = self.width - 10
        d = 5
        self.draw.ellipse((x, 0, x + d, d), outline=255, fill=1)

    def timeBar(self):
        # Draw the time in top left corner
        x = 2
        d = 6
        # Draw a small black filled box to clear the image.
        self.draw.rectangle((0, 0, self.width, self.top), outline=0, fill=0)
        self.draw.text((x, 0),
                       nowdtsShort(), font=self.fontBig, fill=255)
        # self.draw.polygon((self.width, d, self.width, self.height-d, self.width - d, self.height-d,
        #                    self.width - d/2, self.height/2, self.width - d, d), fill=255)

    def viewDeath(self, i):
        # Use an integer parameter to create a pattern
        j = i * 2
        self.draw.polygon([(self.width/2, 0 + j),
                           (self.width - j, self.height/2),
                           ( self.width/2, self.height - 1 - j),
                           (0 + j, self.height/2)],
                          outline=255, fill=0)
        x = self.width/2 - 10
        d = 5
        # self.draw.ellipse((x, self.height/2, x + d, self.height/2+ d), outline=255, fill=0)

    def example(self):
        # Draw a black filled box to clear the image.
        draw = self.draw
        image = self.image
        width = self.disp.width
        height = self.disp.height
        draw.rectangle((0, 0, width, height), outline=0, fill=0)

        # Draw some shapes.
        # First define some constants to allow easy resizing of shapes.
        padding = 2
        shape_width = 20
        top = padding
        bottom = height - padding
        # Move left to right keeping track of the current x position for drawing shapes.
        x = padding
        # Draw an ellipse.
        draw.ellipse((x, top, x + shape_width, bottom), outline=255, fill=0)
        x += shape_width + padding
        # Draw a rectangle.
        draw.rectangle((x, top, x + shape_width, bottom), outline=255, fill=0)
        x += shape_width + padding
        # Draw a triangle.
        draw.polygon([(x, bottom), (x + shape_width / 2, top), (x + shape_width, bottom)], outline=255, fill=0)
        x += shape_width + padding
        # Draw an X.
        draw.line((x, bottom, x + shape_width, top), fill=255)
        draw.line((x, top, x + shape_width, bottom), fill=255)
        x += shape_width + padding

        # Load default font.
        font = ImageFont.load_default()

        # Alternatively load a TTF font.  Make sure the .ttf font file is in the same directory as the python script!
        # Some other nice fonts to try: http://www.dafont.com/bitmap.php
        # font = ImageFont.truetype('Minecraftia.ttf', 8)

        # Write two lines of text.
        draw.text((x, top), 'Hi', font=font, fill=255)
        draw.text((x, top + 20), 'Youuuu!', font=font, fill=255)

        # Display image.
        self.disp.image(image)
        self.disp.display()
        time.sleep(5)

    def welcome(self):
        # Load default font.
        font = ImageFont.truetype("electroharmonix.ttf", 12)
        # Draw a black filled box to clear the image.
        self.draw.rectangle((0, 0, self.width, self.height), outline=0, fill=0)
        self.draw.text((2, 2), 'Hello', font=font, fill=255)
        self.draw.text((2, 15), 'ViewHive v%s' % VH_VERSION,
                       font=font, fill=255)
        self.update()
        time.sleep(3)
        # Call schedule sync function

    # self.schedule.sync()
    # Don't call now, old system time will overwrite correct RTC
    # Recording will not start

    def shutdown(self):
        loggerVH.warning("*** Shutting down ***")
        self.cam.camera.close()
        os.system("sudo gpio mode 7 out")
        # 'gpio mode 7 out' for wittypi intead of 'sudo shutdown -h now'

    def updateVH(self):
        sudo = True
        src_dir = SRC_DIR
        release = 'master'
        commit = None
        """Redraw the info tab with update text """
        tabWidth = 30
        x = self.padding + tabWidth
        # Draw a small black filled box to clear the image.
        self.draw.rectangle((x, self.top, self.width, self.bottom), outline=0, fill=0)
        self.draw.polygon([(x, self.top), (x + tabWidth * 2, self.top),
                           (x + tabWidth * 2 + (tabWidth / 2) + 10, self.height / 2),
                           (x + tabWidth * 2, self.bottom), (x, self.bottom)
                           ],
                          outline=0, fill=255)
        self.draw.text((x + self.padding, self.height / 2 - self.textHpad),
                       "UPDATING...", font=self.fontBig, fill=0)
        self.update()
        loggerVH.info("Clearing changes with: git reset --hard origin/master")
        p = subprocess.Popen('git reset --hard origin/master',
                                  shell=True, cwd=TGT_DIR,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for line in iter(p.stdout.readline, b''):
            loggerVH.info(line),
        loggerVH.info("Updating with: git pull")
        # run('sudo %s' % UPDATE_CMD)
        p = subprocess.Popen('git pull',
                                  shell=True, cwd=TGT_DIR,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for line in iter(p.stdout.readline, b''):
            loggerVH.info(line),
        # subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-U',
        #                        'git+https://github.com/damonmcc/ViewHive#egg=ViewHive'])
        loggerVH.info("Update complete, restarting program")
        # Draw a small black filled box to clear the image.
        self.draw.rectangle((x, self.top, self.width, self.bottom), outline=0, fill=0)
        self.draw.polygon([(x, self.top), (x + tabWidth * 2, self.top),
                           (x + tabWidth * 2 + (tabWidth / 2) + 10, self.height / 2),
                           (x + tabWidth * 2, self.bottom), (x, self.bottom)
                           ],
                          outline=0, fill=255)
        self.draw.text((x + self.padding, self.height / 2 - self.textHpad),
                       "RESTART ME!!", font=self.fontBig, fill=0)
        self.update()
        time.sleep(2)
        # os.execv(sys.executable, sys.argv + ['--updated'])
        sys.stdout.flush()  # flushing data buffered on open files
        # os.chdir(SRC_DIR)
        restartSRC = '/docs/RPi-scripts/restartVH.sh'


        subprocess.call("./docs/restartVH.sh")


    def liveNow(self):
        # Function to check if an event is scheduled for right now
        for ev in self.schedule.events:
            start = code1440(ev['start'])
            length = code1440(ev['length'])
            now = code1440(nowti())

            s = self.width * (start / 1440)
            e = (self.width * ((start + length) / 1440))
            if start <= now < start + length:
                # print('%r >= %r and <%r' % (now, start, start + length))
                return True
        if self.manual: return True
        return False

    def eventsBar(self):
        # Draw events bar at the bottom of the screen and decay line on the right
        j = 1440  # 1440 minutes in a day
        # Clear area by drawing a black filled box.
        self.draw.rectangle((0, 27, self.width, self.height), outline=0, fill=0)
        # Draw minor ticks for every hour, major every 3 hours, and tallest for noon
        while j > 0:
            x = (self.width * (float(j) / float(1440)))
            if j % 720 == 0:
                self.draw.line(((x, 27), (x, self.height)), fill=1)
            elif j % 180 == 0:
                self.draw.line(((x, 29), (x, self.height)), fill=1)
            elif j % 60 == 0:
                self.draw.line(((x, 31), (x, self.height)), fill=1)
            j -= 60
        # For each scheduled event
        for ev in self.schedule.events:
            start = code1440(ev['start'])
            length = code1440(ev['length'])
            end = start + length
            s = (self.width * (float(start) / float(1440)))
            e = (self.width * (float(end) / float(1440)))
            m = e - (e - s / 2)
            # loggerVH.debug("%r,%r, %r ~ %r, %r"%(start,length,end, s,e))
            padding = 2
            shape_w = 2
            bottom = self.height
            top = 26
            # Draw a trapezoid (shorter on bottom) for each event
            self.draw.polygon([(s, bottom), (s - shape_w / 2, top),
                               (e + shape_w / 2, top), (e, bottom)],
                              outline=255, fill=1)
        # Draw decay bar on right side
        heightMult = (self.decay-code1440(nowti()))/self.decayLength
        self.draw.line(((self.width-1, self.height),
                    (self.width-1, 0)), fill=1)
        self.draw.line(((self.width-1, self.height),
                    (self.width-1, self.height * heightMult)),
                       fill=0)
            # self.draw.line(((s,27) , (s,self.height)), fill=1)
            # self.draw.chord((s,30, e,self.height), -180,0, outline=1, fill=0)
            # self.draw.line(((f, 20) , (f,32)), fill=1)

            # self.draw.line(((10,self.width), (20, self.height)), fill=1)

    def tabs(self):
        length = 40
        off = 6
        buf = 8
        h = 10
        # Clear tab buffer by drawing a black filled box.
        self.draw.rectangle((0, 0, self.width, h), outline=0, fill=0)
        if self.mode == 'VIEW':
            self.draw.polygon([(buf, 0), (buf + length, 0), (buf + length - off / 2, h), (buf + off / 2, h)],
                              outline=0, fill=1)
            self.draw.text((10 + off / 2, 0), 'VIEW', font=self.font, fill=0)

            self.draw.polygon([(buf + length, 0), (buf + (length * 2) - off, 0), (buf + (length * 2) + off / 2, h),
                               (buf + length - 5, h)],
                              outline=255, fill=0)
            self.draw.text((buf + length + 5, 0), 'ADD', font=self.font, fill=255)

            self.draw.polygon(
                [(buf + (length * 2 - off), 0), (buf + length * 3 - off, 0), (buf + length * 3 - off - off / 2, h),
                 (buf + length * 2 - off / 2, h)],
                outline=255, fill=0)
            self.draw.text((buf + length * 2 + 5, 0), 'DEL', font=self.font, fill=255)

        elif self.mode == 'ADD':
            self.draw.polygon([(buf, 0), (buf + length, 0), (buf + length - off / 2, h), (buf + off / 2, h)],
                              outline=1, fill=0)
            self.draw.text((10 + off / 2, 0), 'VIEW', font=self.font, fill=1)

            self.draw.polygon([(buf + length, 0), (buf + (length * 2) - off, 0), (buf + (length * 2) + off / 2, h),
                               (buf + length - off / 2, h)],
                              outline=0, fill=1)
            self.draw.text((buf + length + 5, 0), 'ADD', font=self.font, fill=0)

            self.draw.polygon(
                [(buf + (length * 2 - +off), 0), (buf + length * 3 - off, 0), (buf + length * 3 - off - off / 2, h),
                 (buf + length * 2 - off / 2, h)],
                outline=1, fill=0)
            if not self.fresh:
                self.draw.text((self.width - 37, 1), "%s" % nowt(), font=self.font, fill=1)
            else:
                self.draw.text((buf + length * 2 + 5, 0), 'DEL', font=self.font, fill=1)

        elif self.mode == 'DEL':
            self.draw.polygon([(buf, 0), (buf + length, 0), (buf + length - off / 2, h), (buf + off / 2, h)],
                              outline=1, fill=0)
            self.draw.text((10 + off / 2, 0), 'VIEW', font=self.font, fill=1)

            self.draw.polygon([(buf + length, 0), (buf + (length * 2) - off, 0), (buf + (length * 2) + off / 2, h),
                               (buf + length - off / 2, h)],
                              outline=1, fill=0)
            self.draw.text((buf + length + 5, 0), 'ADD', font=self.font, fill=1)

            self.draw.polygon(
                [(buf + (length * 2 - off), 0), (buf + length * 3 - off, 0), (buf + length * 3 - off - off / 2, h),
                 (buf + length * 2 - off / 2, h)],
                outline=0, fill=1)
            self.draw.text((buf + length * 2 + 5, 0), 'DEL', font=self.font, fill=0)

        elif self.mode == 'TIME':
            self.draw.polygon([(buf, 0), (self.width - buf, 0), (self.width - buf - off / 2, h), (buf + off / 2, h)],
                              outline=1, fill=0)
            self.draw.text((self.width - 105, 1), "%s" % nowt(), font=self.font, fill=1)
        else:
            self.draw.polygon([(buf, 0), (self.width - buf, 0), (self.width - buf - off / 2, h), (buf + off / 2, h)],
                              outline=0, fill=1)
            self.draw.text((self.width / 2 - 25, 0), 'VIEWHIVE', font=self.font, fill=0)


class Navigation(object):
    def __init__(self, **k_parems):
        """
        Initiating the ViewHive menu navigation controlled by a
        knob with rotary switch and push button
        """
        if 'menu' in k_parems:
            # If the assigned menu is listed...
            self.menuMain = k_parems['menu']
        else:
            loggerVH.debug('..Using default ViewHiveMenu..')
            menuDef = menu(ViewHiveMenu)
            self.menuMain = menuDef
        self.actionString = ""
        awake = True
        # Looking at bottom of the rotary switch with 3-pin side down:
        # PinA: bottom right
        # PinB: bottom left
        # PinPush: top right
        rotaryPinA = 16
        rotaryPinB = 20
        rotaryPinPush = 26

        def callbackR(way):
            self.dec.place += way
            # loggerVH.debug("pos={}".format(self.dec.place))
            if way > 0: self.menuMain.next()
            if way < 0: self.menuMain.back()

        def callbackS(val):
            # loggerVH.debug("state={}".format(self.dec.state))
            if val:     # pressed
                self.dec.bounce = 10
                s = self.menuMain.select()
                # time.sleep(1)
                if s:   # If selection is an action
                    if s == -1: pass    # If at top/first level do nothing
                    self.actionString = self.menuMain.action()
                # time.sleep(.100)

        knobpi = pigpio.pi()    # Create pigpio object for
        self.dec = decoder(knobpi, rotaryPinA, rotaryPinB, rotaryPinPush, callbackR, callbackS)


    def testRun(self):
        while self.menuMain.action() != "shutdown":
            os.system("clear")
            print(self.menuMain)
            self.menuMain.display()
            if self.menuMain.action() == 'exec_wifi_show':
                print(show_wifi())
            elif self.menuMain.action() == 'exec_ip_show':
                print('IP addr: ' + show_ip())
            elif self.menuMain.action() == 'exec_time_show':
                print(show_time())
                print(now())
            elif self.menuMain.action() == 'exec_time_sync':
                print(sync_time())
                time.sleep(3)
                self.menuMain.up()
            elif self.menuMain.action() == 'exec_wifi_down':
                print(wifi_down())
                time.sleep(4)
                self.menuMain.up()
            elif self.menuMain.action() == 'exec_wifi_up':
                print(wifi_up())
                time.sleep(4)
                self.menuMain.up()
            else:
                print(self.menuMain.action())
            time.sleep(0.01)


class Recorder(object):
    def __init__(self):
        if getattr(self.__class__, '_has_instance', False):
            raise RuntimeError('Cannot create another instance')
        self.__class__._has_instance = True
        loggerVH.debug('.. Recorder init.. ')
        self.camera = picamera.PiCamera()
        loggerVH.debug('.. ')
        # self.camera.rotation = 180
        # self.camera.resolution = (1920, 1080)
        # self.camera.framerate = 30
        self.camera.resolution = (1296, 730)
        self.camera.framerate = 24
        # self.camera.framerate = 49
        self.camera.annotate_background = picamera.Color('grey')
        self.camera.annotate_foreground = picamera.Color('purple')
        loggerVH.debug('.')
        self.timestamp = now()
        self.startTime = 0
        self.timeElapsed = 0
        self.recording = False
        self.preview = False
        self.recRes = 0.01  # resolution of elapsed time counter (seconds)
        #####
        #
        # 3600 seconds per hour
        self.recPeriod = 10  # Seconds to record

        self.usbname = 'VIEWHIVE'
        self.usbroot = '/media/pi/' + self.usbname + '/'
        self.dstroot = '/home/pi/Videos'
        self.srcfile = ''
        self.srcroot = ''
        self.convCommand = ''
        #####
        loggerVH.debug('*** Recorder born %s***\n' % self.timestamp)
        os.system("sudo gpio -g mode 5 out")
        os.system("sudo gpio -g mode 6 out")
        os.system("sudo gpio -g write 5 0")
        os.system("sudo gpio -g write 6 0")
        self.camera.led = False

    def start(self):
        # Wait for USB drive named VIEWHIVE
        # waitforUSB(self.usbname)
        # Name files with current timestamp
        self.timestamp = now()
        self.startTime = time.time()
        self.srcfile = '%s.h264' % self.timestamp
        self.srcroot = '/home/pi/Videos/%s' % self.srcfile
        self.convCommand = 'MP4Box -add {0}.h264 {1}.mp4'.format(self.timestamp, self.timestamp)

        self.camera.start_recording(self.srcroot, format='h264')
        loggerVH.info("*** Recording started at %s ***" % self.timestamp)
        self.recording = True
        # self.camera.led = True
        os.system("gpio -g write 5 1")
        os.system("gpio -g write 6 1")
        # self.camera.start_preview(alpha=120)
        self.camera.annotate_text = "%s | START" % nowdts()
        pool = ThreadPool(4)
        my_array = []
        results = pool.map(self.refresh, my_array)

    def refresh(self):
        # loggerVH.debug('annotating!')
        self.timeElapsed = time.time() - self.startTime
        self.camera.annotate_text = "%s | %.3f" % (nowdts(), self.timeElapsed)
        os.system("gpio -g write 5 1")
        os.system("gpio -g write 6 1")

    def stop(self):
        self.camera.annotate_text = "%s | %.2f END" % (nowdts(), self.timeElapsed)
        os.system("gpio -g write 5 0")
        os.system("gpio -g write 6 0")
        self.camera.wait_recording(1)
        self.camera.stop_recording()
        self.recording = False
        loggerVH.info('Video recording stopped')
        loggerVH.info('Saved as: %s' % self.srcroot)
        # self.camera.stop_preview()
        self.timeElapsed = 0
        self.camera.led = False
        loggerVH.info("*** Recording stopped at %s ***" % now())

    def copy(self):
        src = self.dstroot
        dst = self.usbroot

        def progress(bytescopied):
            # progressUpdate(bytescopied)
            pass
        try:
            if not os.path.exists(dst):  # If there's no media/pi/VIEWHIVE directory (unmounted)
                if os.path.exists('/dev/disk/by-label/VIEWHIVE'):   # If a USB drive is seen
                    loggerVH.info('USB named VIEWHIVE detected')
                    os.makedirs(dst)    # Create destination folder
                else:
                    print("No VIEWHIVE USB detected!")
                    loggerVH.info('USB named VIEWHIVE not detected')
            # Try to mount usb stick with VIEWHIVE name no matter what
            os.system("sudo mount -t vfat /dev/disk/by-label/VIEWHIVE " + dst)
            loggerVH.info('VIEWHIVE disk mounted at %s', dst)
        except Exception as inst:
            print("FAILED sudo mount -t vfat /dev/disk/by-label/VIEWHIVE")
            loggerVH.error('COPY error: %s', inst)
            loggerVH.error('VIEWHIVE disk failed to mount at %s', dst)
        # Print contents of dstroot
        loggerVH.debug("dstroot %s contains:" % self.dstroot)
        p = subprocess.Popen("ls", shell=True,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             cwd=self.dstroot)
        for line in iter(p.stdout.readline, b''):
            loggerVH.debug(line),

        # Copy all files from dstroot to USB
        try:
            # shutil.copy(self.srcroot, self.dstroot)
            # Copy entire Videos folder and
            # Wait for USB drive named VIEWHIVE
            # shutil.copytree(self.dstroot, waitforUSB(self.usbroot))
            # copy_tree(self.dstroot, waitforUSB(self.usbroot), verbose=1)
            for item in os.listdir(src):
                s = os.path.join(src, item)
                d = os.path.join(dst, item)
                if not os.path.exists(d) or os.stat(s).st_mtime - os.stat(d).st_mtime > 1:
                    # shutil.copy2(s, d)
                    loggerVH.info('Copying %s...', s)
                    with open(s, 'rb') as fsrc:
                        with open(d, 'wb') as fdst:
                            self.copyfileobj(fsrc, fdst, progress)
                    # os.unlink(s)  # Delete as you copy
            # Copy log file to USB stick
            loggerVH.info('Videos copied to USB, coping log file')
            os.system('sudo cp /home/pi/pywork/ViewHive/ViewHive.log '+
                      dst+'ViewHive_'+now()+'.log')
            loggerVH.debug('usbroot %s contains:' % self.usbroot)
            p = subprocess.Popen("ls", shell=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 cwd=self.usbroot)
            for line in iter(p.stdout.readline, b''):
                loggerVH.debug(line),
            loggerVH.debug("..Copied to USB!")
            # Finally, unmount and clear usbroot
            os.system("sudo umount " + dst)
            os.system("sudo rm -rf " + dst)
            loggerVH.info('USB drive unmounted and ran:\nsudo rm -rf /media/pi/VIEWHIVE')
            return True
        except Exception as inst:
            # Copy failed, print error and return False
            print("COPY error: %s" % inst)
            loggerVH.error("COPY error: %s" % inst)
            return False

    def copyfileobj(self, fsrc, fdst, callback, length=16 * 1024):
        copied = 0
        while True:
            buf = fsrc.read(length)
            if not buf:
                break
            fdst.write(buf)
            copied += len(buf)
            callback(copied)

    def previewToggle(self):
        if not self.preview:
            self.camera.start_preview(alpha=120)
            self.preview = True
            os.system("gpio -g write 5 1")
            os.system("gpio -g write 6 1")
        else:
            self.camera.stop_preview()
            self.preview = False
            os.system("gpio -g write 5 0")
            os.system("gpio -g write 6 0")
        # NO MORE CONVERTING TO MP4
        #        print(self.convCommand)
        #        conv = subprocess.Popen(self.convCommand, shell=True,
        #                            cwd=self.dstroot)
        #        conv_status = conv.wait()
        #        if conv_status==0:
        #            print ("*** Conversion complete ***")
        #        else:
        #            print ("**! Conversion FAILED !**")
        #        silentremove("{0}{1}.h264".format(self.dstroot,self.timestamp))


if __name__ == '__main__':
    display = Display(cam=True)
    # print(display.nav.menuMain.struct)
    # self.assertTrue(display.nav.menuMain.struct[5][2], "Config")
    display.calibrate()
    display.runNavigation()