from sortedcontainers import SortedDict
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
import time
from datetime import datetime as dt
import threading
import curses
import Adafruit_SSD1306
import Adafruit_GPIO.SPI as SPI 

#def recordNow():
    #
    
def now():
    # Return current time and date as a string
    return dt.now().strftime("%Y-%m-%d_%H.%M.%S")
def nowt():
    # Return current time as a formatted string
    return dt.now().strftime("%H:%M")
def nowti():
    # Return current time as an int
    return (dt.now().strftime("%H%M"))
               
def code1440(time):
    # Convert a 2400 time to 1440 time
    if(len(time) == 4):
        tRaw = (int(time[0])*600+int(time[1])*60)+int(time[2])+int(time[3])
    elif(len(time) == 3):
        tRaw = (int(time[0])*60)+int(time[1])+int(time[2])
    elif(len(time) == 2):
        tRaw = int(time[0])+int(time[1])
    else:
        tRaw = int(time[0])
    return tRaw
def code2400(time):
    # Convert a 1400 time to 2400
    if(len(time) == 4):
        tRaw = (int(time[0])*600+int(time[1])*60)+int(time[2])+int(time[3])
    elif(len(time) == 3):
        tRaw = (int(time[0])*60)+int(time[1])+int(time[2])
    elif(len(time) == 2):
        tRaw = int(time[0])+int(time[1])
    else:
        tRaw = int(time[0])
    return tRaw

    

class Schedule(object):

    def __init__(self, name, source):
        self.name = name
        self.source = source            # Source file
        self.file = open(source)
        self.content = self.file.read() # Intermediary data for read/write
        self.file.close()
        self.events = []                # List of schedule events
        self.ED = SortedDict(self.events)
        
    #   Display Schedule source file data
    def showSource(self):
        self.file = open(self.source)
        print("Source content:",)
        print(self.file.read())
        self.file.close()

    #   Display cuurent Schedule content
    def showContent(self):
        print("Schedule's current content:")
        print(self.content)

    #   Display list of user-defined events
    def showEvents(self):
        print("All events:")
        for event in self.events:
            print("From %04d to %04d" % (event['start'], (event['start']+event['length'])))
        print("\nSorted:")
        for event in self.ED:
            print("From %s to %s" % (event[0], (event[0]+event[1])))
        print("\n")

    #   Convert an events list to Witty Pi schedule text
    def EventsToWpi(self):
            # rules:
            #   Minimize OFF periods (1M only) to right before a recording
            #   Maximize ON WAIT periods since unit will decay to shutdown
            #   Recording length stored in comment in ON line
            #   ON line w/o a comment is a wait period
            #   Start and end days with a wait period
            #   All elements seperated by tabs
            # ON    H1 M59  WAIT
            # OFF   M1
            # ON    H22  WAIT    #H1
        # converts the event list to wpi format and store in self.content
        self.content = ''
        wpiCommands = ["#"]
        i = 0
        curTime = 0
        def code(time, **k_parems):
            h = ''
            m = ''
            
            timeS = str(time)
            print(": "+"timeS: "+timeS+" curTime: "+str(curTime))
            if(time>=100): # Has an hour component
                if(time>=1000): # more than 10 hours
                    h = 'H%s%s'% (timeS[0], timeS[1])
                    if('state' in k_parems and k_parems['state'] == 'ON'): # For an ON command
                        if(timeS[2] != '0' or timeS[3] != '0'): # there are minutes
                            h = 'H%s'% timeS[0:1]
                            m = 'M%d'% (int(timeS[2:3])-1) # subtract 1 minute for OFF state
                        else: # m goes from 00 to 59
                            h = 'H%d'% (int(timeS[0:2]) - 1)
                            m = 'M59'
                    else:
                        h = 'H%s'% timeS[0:1]
                        m = 'M%s%s'% (timeS[2], timeS[3])
                    code = h+' '+m
                    
                else:   # less than 10 hours
                    if('state' in k_parems and k_parems['state'] == 'ON'): # For an ON command
                        if(timeS[1] != '0' or timeS[2] != '0'): # there are minutes                            
                            h = 'H%s'% timeS[0]
                            m = 'M%d'% (int(timeS[1:2])-1) # subtract 1 minute for OFF state
                        else:                           
                            h = 'H%d'% (int(timeS[0]) - 1)
                            m = 'M59' 
                    else:
                        h = 'H%s'% timeS[0]
                        m = 'M%s%s'% (timeS[1], timeS[2])
                    code = h+' '+m
            else:   # Only has a minute component
                code = 'M%s'% time
            return code
            

        
        for event in self.events:   # For each event in the list...
            print("Event %d: %04d to %04d" % (i, event['start'], (event['start']+event['length'])))
            if(i==0 and len(self.events)>1):   # First event
                print("First event ..."),
                if(event['start']>0):   # If starting after midnight, add morning buffer
                    print("Adding morning buffer ..."),
                    wpiCommands.append('ON\t%s\tWAIT'% code(event['start'],state="ON"))
                    wpiCommands.append('OFF\tM1')
                    curTime+= event['start']
                #   Actual first event
                wpiCommands.append('ON\t%s\tWAIT\t#%s'% (code(self.events[i+1]['start']-(curTime), state="ON"),code(event['length'])))
                wpiCommands.append('OFF\tM1')
                curTime = self.events[i+1]['start']
                
            elif(i==len(self.events)-1): # Last or only event
                print("Last (only?) event ..."),
                if(i==0):
                    print("Adding morning buffer for ONLY event..."),
                    wpiCommands.append('ON\t%s\tWAIT'% code(event['start'],state="ON"))
                    wpiCommands.append('OFF\tM1')
                sleep = 2400 - curTime  # stretch until midnight
                wpiCommands.append('ON\t%s\tWAIT\t#%s' %(code(sleep, state="ON"),code(event['length'])))
                print(curTime," + ",sleep," should be 2400!")
                                            
            else:       # All other events
                print("Average event ..."),
                wpiCommands.append('ON\t%s\tWAIT\t#%s' %(code(self.events[i+1]['start']-(curTime), state="ON"),code(event['length'])))
                wpiCommands.append('OFF\tM1')
                curTime = self.events[i+1]['start']
            i+= 1
            
        #   Combine all command stings into contents
        self.content = '\n'.join(wpiCommands)
        self.showContent()
        
    #   Convert Witty Pi schedule text to an events list
    def WpiToEvents(self):
        wpiLines = self.content.split('\n')
        tempEvent = self.clearEvent()
        i = 0
        curLength = 0

        # converts the wpi time codes to 0000 formatted time int
        def time(code):
            code0000 = 0000
            if(' ' not in code): # if the command has 1 number
                if(code[0] == 'H'):
                    hours = int(code[1:len(code)])*100
                    code0000+= hours
                if(code[0] == 'M'):
                    mins = int(code[1:len(code)])
                    if(mins > 59): mins = 100
                    code0000+= mins
            elif(' ' in curCommand[1]):   # Hour and minute present
                splitCode = code.split(' ')
                hours = int(splitCode[0][1:len(splitCode[0])])*100
                mins = int(splitCode[1][1:len(splitCode[1])])+1
                if(mins > 59): mins = 100
                code0000+= hours
                code0000+= mins
            return code0000

        ##  While reading header
        while len(wpiLines[i]) < 1 or wpiLines[i][0] == '#':
            print(i," ", wpiLines[i])
            i += 1
        print(i," ", wpiLines[i])  # BEGIN
        i+=1
        print(i," ", wpiLines[i])  # END
        i+=1
        curTime = 0

        ##  While reading WPI command lines
        while i < len(wpiLines):
            curCommand = wpiLines[i].split('\t')
            print(i," ", curCommand),
            curType = curCommand[0]
##            print("%s command Length: %d"% (curType, curLength))
            if(curType == 'ON'):
                #   If theres a recording length comment
                if('#' in curCommand[len(curCommand)-1]):
                    curTime+= time(curCommand[1])
                    comment = curCommand[len(curCommand)-1].split('#')
                    
                    tempEvent['length'] = time(comment[1])-1
##                    print("Length is %d"%tempEvent['length']),
##                    tempEvent['end'] = tempEvent['start']+time(comment[1])-1
                    self.events.append(tempEvent)
                    self.ED = SortedDict(self.events)
                    self.showEvents()
                    tempEvent = self.clearEvent()
                    i+=1
                #   Otherwise this is a gap without recording length
                else:
                    curTime+= time(curCommand[1])
                    tempEvent = self.clearEvent()
                    print("ON Gap ending at %d, not recording"% curTime)
                    i+=1
                    
            elif(curType == 'OFF'):
                tempEvent['start'] = curTime
                i+=1
            else:
                print("NON-command on this line ", curCommand)
                i+=1





    #
    #   Ask for and append a new event entry (start/end times)
    def addEvent(self, s, l):
        print("Adding an event ... "),
        # Create an empty new event
        newEvent = {'start' : 0000,
                  'length' : 0000}
        
        while True:
            try:
                newEvent['start'] = s
                newEvent['length'] = l

                assert (newEvent['start'] < 2400) or (newEvent['length'] < 2400), "Entered a start%d/length%d greater than 2400!"% (newEvent['start'], newEvent['start'])
                assert newEvent['length'] != 0, "Entered 0000 for length!"
                break
            except ValueError:
                print("Not a valid time! Quit?"),
                if(self.confirmed()): return
            except AssertionError as strerror:
                print("%s Try again!"% strerror),
        
        self.events.append(newEvent)
        self.ED = SortedDict(self.events)
        print("New event added! There are %d events:" % len(self.events))
        self.showEvents()

    #
    #   Empty the schedule's event list
    def clearAllEvents(self):
        print("Clearing events..."),
        newEvent = {'start' : 0000,
                  'length' : 0000}
        self.events.clear()
        self.ED = SortedDict(self.events)
        print("Events cleared! There are %d events:" % len(self.events))
    
    #   Return a blank event item
    def clearEvent(self):
        blankEvent = {'start' : 0000,
                 'length' : 0000}
        return blankEvent


    def sync(self):
        # sync object with schedule file
        # truncate
        # write header comments
        # write BEGIN and END
        # wrie events in wpi format
        self.file = open(source, '-a')
        self.file.write(self.content)
        print("File appended")
        self.file.close()





##  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


def nav(screen):
    screen.addstr(8,8,"Surfin >")
    screen.keypad(1)
    # halfdelay blocks for getch call for x tenths of a second
    screen.nodelay(1)
    action = True
    while action:
        try:
            event = screen.getkey()
            action = True
        except Exception as inst:            
            screen.addstr(10, 1,"* nav error: %s"% inst)
##            print("*** nav error: %s"%inst)
##            return 'e'
##            return 'decay'
##            action = False
        else:
            screen.addstr(4, 1,"Got nav event %s"%event)
##            if screen.getch
            if event == '0': return 0
            elif event == ord("2"):
                return chr(event)
            elif event == 'KEY_HOME':
                return 'CH'
            elif event == 'KEY_PPAGE':
                return 'CH-'
            elif event == 'KEY_NPAGE':
                return 'CH+'
            elif event == 'KEY_F(3)':
                return 'L'
            elif event == 'KEY_F(4)':
                return 'R'
            elif event == 'KEY_END':
                return 'P'
            elif event == 'KEY_UP':
                return 'U'
            elif event == 'KEY_DOWN':
                return 'D'
            elif event == 'KEY_ENTER':
                return 'ENT'
            
            elif event == 'KEY_F1':     # 100+ button
                return 'F1'
            elif event == 'KEY_F2':     # 200+ button
                return 'F2'
            elif event == '0': return 0
            elif event == '1': return 1
            else:
                screen.addstr(5, 1,"TRY AGAIN (not %s) >"%event)
    screen.addstr(5, 1,"OUT\n\n")

#   Get user confirmation
def getConfirm(screen):
    screen.addstr(3,8,"Confirm by pressing ENTER >")
    screen.nodelay(0)
    screen.keypad(1)
    curses.echo()
    try:
        event = screen.getkey()
    except Exception as inst:            
        screen.addstr(11, 1,"* conf error: %s"% inst)
    else:
        screen.addstr(5, 1,"Got confirm event %s"% event)
        if event == '\n':
            screen.addstr(5, 20,"CONFIRMED")
            return True
        else: return False
        

#   Get user-input time string
def getTime(screen):
    screen.addstr(3,8,"Enter a time and press ENTER >")
    screen.nodelay(0)
    curses.echo()
    time = screen.getstr()
    return int(time)


class Display(object):
    def __init__(self, sch):
        print('Display instance starting...')
        RST = 24
        DC = 23
        SPI_PORT = 0
        SPI_DEVICE = 0
        self.disp = Adafruit_SSD1306.SSD1306_128_32(rst=RST, dc=DC, spi=SPI.SpiDev(SPI_PORT, SPI_DEVICE, max_speed_hz=8000000))
        self.width = self.disp.width
        self.height = self.disp.height
        self.font = ImageFont.truetype("GameCube.ttf", 7)
        if sch == 0:
            self.schedule = []
        else:
            self.schedule = sch
            self.events = sch.events

        
        print('...')
        self.mode = -1
        self.fresh = True
        self.start = 60
        # length of decay countdowm
        self.decay = self.start
        # initialize decay countdown

        
        print('....')
        self.disp.begin()
        self.image = Image.new('1', (self.width, self.height))
        
        print('.....')
        self.draw = ImageDraw.Draw(self.image)
        self.draw.rectangle((0,0,self.width,self.height), outline=0, fill=0)

##        
##        self.screen = curses.initscr()
##        curses.echo()
##        curses.curs_set(0)
##        self.screen.keypad(1)





##
##    class AwaitCommand(threading.Thread):
##        def run(self):
##            print("Awaiting command")
##            c = input()
##            if(c == '1'):
##                print(c)
##                self.mode = 1

    def update(self):
        self.disp.clear()
        self.disp.image(self.image)
        self.disp.display()

    def clear(self):
        # Clear image buffer by drawing a black filled box.
        self.draw.rectangle((0,0,self.width,self.height), outline=0, fill=0)



    def welcome(self):
        # Load default font.
        font = ImageFont.truetype("electroharmonix.ttf", 12)
        self.draw.text((2, 2),    'Hello',  font=self.font, fill=255)
        self.draw.text((2, 15), 'ViewHive v0.6!', font=self.font, fill=255)
        self.update()
        time.sleep(3)



    def startRooms(self):
##        self.clear()
##        self.mode = 'TIME'
##        self.tabs()
##        self.update()
        recRes = 0.01
        while self.decay>0:
            com = curses.wrapper(nav)
            if(self.fresh == True):
                i = 0   # If this view is fresh, reset item index
            if(com == 'decay'):
                self.update()
                self.decay -= recRes*2
                time.sleep(recRes)
                continue
            # Interpret selections at a navigation level
            # nav has nodelay on, so without an entry, continue
            if(com == 'CH'):
                self.mode = 'ADD'
                self.fresh = True
                self.decay = self.start
            elif(com == 'CH-'):
                if(self.mode == 'VIEW'): self.mode = 'TIME'
                elif(self.mode == 'ADD'): self.mode = 'VIEW'
                elif(self.mode == 'DEL'): self.mode = 'ADD'
                elif(self.mode == 'TIME'): self.mode = 'DEL'
                self.fresh = True
                self.decay = self.start
            elif(com == 'CH+'):
                if(self.mode == 'VIEW'): self.mode = 'ADD'
                elif(self.mode == 'ADD'): self.mode = 'DEL'
                elif(self.mode == 'DEL'): self.mode = 'TIME'
                elif(self.mode == 'TIME'): self.mode = 'VIEW'
                self.fresh = True
                self.decay = self.start

            
            elif(com == 'P' or com == 'ENT'):
                 if(self.mode == 'TIME' or self.mode == 'ADD'): i = -1
                 self.fresh = False
                 
            elif (com == 0 and self.mode == 'DEL'): i = -1
            elif (com == 1 and self.mode == 'ADD'): i = -1
            
            # Interpret Left and Right commands
            elif(com == 'R'):
                if(i==len(self.events)-1): pass
                else:
                    i += 1
                    self.fresh = False
            elif(com == 'L'):
                if(i==0): pass
                else:
                    i -= 1 
                    self.fresh = False
                    
            
            
            if(self.decay < self.start/2):  # When decay is almost complete, show countdown
                self.mode = 'TIME'
                # Clear image buffer by drawing a black filled box.
                self.draw.rectangle((0,12,self.width,24), outline=0, fill=0)
                self.draw.text((self.width/2-25,self.height/2), '%.2f' % round(float(self.decay),3),
                        font=self.font, fill=1)

            
            self.tabs()
            self.showRoom(self.mode, i)
            self.eventsBar()
            self.draw.text((120,self.height/2), '%s' % i,
                        font=self.font, fill=1)
            
            self.update()
            self.decay -= recRes*2
            time.sleep(recRes/2)
        # Decay is complete, SHUTDOWN
        self.mode == 'TIME'
        self.tabs()
        self.update()

    def showRoom(self, mode, i):
        if(mode == 'VIEW'): self.roomView(i)
        if(mode == 'ADD'): self.roomAdd(i)
        if(mode == 'DEL'): self.roomDelete(i)
        if(mode == 'TIME'): self.roomTime(i)







            

    def roomMain(self):
        # Clear image buffer by drawing a black filled box.
        self.draw.rectangle((0,12,self.width,24), outline=0, fill=0)
        self.draw.text((1,self.height/2), 'MAIN main', font=self.font, fill=1)

    
    def roomView(self, i):
        i = i
        if(len(self.events)==0):
            curString = 'No events scheduled'
        else:
            cur = self.events[i]
            curString = '%d) %d'%(i+1, cur['start'])+' for '+'%d.'%cur['length']
            if(len(self.events)>1 and i<len(self.events)-1):
                self.draw.text((self.width-10,self.height/2), '...',
                            font=self.font, fill=1)
        # Clear image buffer by drawing a black filled box.
        self.draw.rectangle((0,12,self.width,24), outline=0, fill=0)
        self.draw.text((3 ,self.height/2), '%s' % curString,
                        font=self.font, fill=1)
##        self.eventsBar()

    def roomDelete(self, i):
        i = i
        # Clear image buffer by drawing a black filled box.
        self.draw.rectangle((0,12,self.width,24), outline=0, fill=0)
        if i == -1:
            self.draw.text((2, self.height/2), "Delete all events?",
                           font=self.font, fill=1)
            
            self.update()
            answer = curses.wrapper(getConfirm)
            
            self.draw.rectangle((0,12,self.width,24), outline=0, fill=0)
            if answer == True :
                ## Call schedule delete function
                self.schedule.clearAllEvents()
                self.draw.text((self.width/2-30, self.height/2), "DELETED!",
                           font=self.font, fill=1)
            else:
                self.draw.text((self.width/2-28, self.height/2), "Canceled",
                           font=self.font, fill=1)
            self.update()
            time.sleep(2)
            self.fresh = True
        elif i == 0:
            self.draw.text((2, self.height/2), "Press 0",
                           font=self.font, fill=1)
            self.fresh = True
                
        
    def roomTime(self, i):
        # Clear image buffer by drawing a black filled box.
        self.draw.rectangle((0,12,self.width,24), outline=0, fill=0)
        i = i
        if(i == -1):    # Setting system/RTC time
            self.draw.text((3 ,self.height/2), 'Give cur. time:',
                       font=self.font, fill=1)
            
            time = curses.wrapper(getTime)
            # Clear image buffer by drawing a black filled box.
            self.draw.rectangle((0,12,self.width,24), outline=0, fill=0)
            self.draw.text((3 ,self.height/2), '%d' % time,
                       font=self.font, fill=1)
            self.fresh = True
        else:           # Show current time in tabs and decay coutdown
            time = nowt()
            self.draw.text((self.width/2-25,self.height/2), '%.2f' % round(float(self.decay),3),
                        font=self.font, fill=1)
        
        

    def roomAdd(self, i):
        # Add an event

        i = i
        # Clear image buffer by drawing a black filled box.
        self.draw.rectangle((0,12,self.width,24), outline=0, fill=0)
        if i == -1:
            self.draw.text((2, self.height/2), "Add an event?",
                           font=self.font, fill=1)
            self.update()
            
            answer = curses.wrapper(getConfirm)
            self.draw.rectangle((0,12,self.width,24), outline=0, fill=0)
            if answer == True :
                self.draw.text((1, self.height/2), 'ADDING', font=self.font, fill=1)
                self.update()
                time.sleep(2)
                # Get start and length times for new event
                self.draw.rectangle((0,12,self.width,24), outline=0, fill=0)
                self.draw.text((1, self.height/2), 'Enter start time 0000 >',
                               font=self.font, fill=1)
                self.update()
                start = curses.wrapper(getTime)     # Start time from 0000 to 24000
                self.draw.rectangle((0,12,self.width,24), outline=0, fill=0)
                self.draw.text((1, self.height/2), 'Enter rec. length 0000 >',
                               font=self.font, fill=1)
                self.update()
                length = curses.wrapper(getTime)    # Length of event

                # Now confirm these entries
                self.draw.rectangle((0,12,self.width,24), outline=0, fill=0)
                self.draw.text((2, self.height/2), "At %d for %d?"% (start,length),
                           font=self.font, fill=1)
                self.update()
                
                conf = curses.wrapper(getConfirm)
                self.draw.rectangle((0,12,self.width,24), outline=0, fill=0)
                if conf == True :
                    ## Call schedule add function
                    self.schedule.addEvent(start, length)
                    self.draw.text((1, self.height/2), 'Event ADDED...', font=self.font, fill=1)
                    ## Call schedule synch function





                    
                    self.draw.text((1, self.height/2), 'Events SYNCHED', font=self.font, fill=1)
                else:
                    self.draw.text((self.width/2-28, self.height/2), "Canceled SAVE",
                               font=self.font, fill=1)
            else:
                self.draw.text((self.width/2-28, self.height/2), "Canceled ADD",
                           font=self.font, fill=1)
            
        elif i == 0:
            self.draw.text((2, self.height/2), "Press 1",
                           font=self.font, fill=1)
            self.fresh = True

    




                

    def eventsBar(self):
        i=0     #   1440 minutes in a day
        # Clear image buffer by drawing a black filled box.
        self.draw.rectangle((0,28,self.width,self.height), outline=0, fill=0)
        while(i<=1440):
            x = (128*(i/1400))
            if(i%720 == 0):
                self.draw.line(((x,26) , (x,self.height)), fill=1)
            elif(i%180 == 0):
                self.draw.line(((x,28), (x,self.height)), fill=1)            
            elif(i%60 == 0):
                self.draw.line(((x,30) , (x,self.height)), fill=1)
            else:
                ##self.draw.line(((x,31), (x,self.height)), fill=1)
                pass
            i+=30
        for ev in self.events:
            start = code1440(str(ev['start']))
            length = code1440(str(ev['length']))
            
            s = 128*(start/1440)
            e = (128*((start+length)/1440))
            self.draw.chord((s,28 , e,self.height), -180,0, outline=1, fill=1)
##            self.draw.line(((s, 20) , (s,32)), fill=1)

    def tabs(self):
        length = 40
        off = 6
        buf = 8
        h = 10
        if(self.mode == 'VIEW'):
            self.draw.polygon([(buf,0), (buf+length,0), (buf+length-off/2,h) , (buf+off/2,h)],
                              outline=0, fill=1)
            self.draw.text((10+off/2, 0), 'VIEW',  font=self.font, fill=0)

            self.draw.polygon([(buf+length,0), (buf+(length*2)-off,0), (buf+(length*2)+off/2,h) , (buf+length-5,h)],
                              outline=255, fill=0)
            self.draw.text((buf+length+5, 0), 'ADD',  font=self.font, fill=255)
        
            self.draw.polygon([(buf+(length*2-off),0), (buf+length*3-off,0), (buf+length*3-off-off/2,h) , (buf+length*2-off/2,h)],
                              outline=255, fill=0)
            self.draw.text((buf+length*2+5, 0), 'DEL',  font=self.font, fill=255)

        elif(self.mode == 'ADD'):
            self.draw.polygon([(buf,0), (buf+length,0), (buf+length-off/2,h) , (buf+off/2,h)],
                              outline=1, fill=0)
            self.draw.text((10+off/2, 0), 'VIEW',  font=self.font, fill=1)

            self.draw.polygon([(buf+length,0), (buf+(length*2)-off,0), (buf+(length*2)+off/2,h) , (buf+length-off/2,h)],
                              outline=0, fill=1)
            self.draw.text((buf+length+5, 0), 'ADD',  font=self.font, fill=0)
        
            self.draw.polygon([(buf+(length*2-+off),0), (buf+length*3-off,0), (buf+length*3-off-off/2,h) , (buf+length*2-off/2,h)],
                              outline=1, fill=0)
            self.draw.text((buf+length*2+5, 0), 'DEL',  font=self.font, fill=1)

        elif(self.mode == 'DEL'):
            self.draw.polygon([(buf,0), (buf+length,0), (buf+length-off/2,h) , (buf+off/2,h)],
                              outline=1, fill=0)
            self.draw.text((10+off/2, 0), 'VIEW',  font=self.font, fill=1)

            self.draw.polygon([(buf+length,0), (buf+(length*2)-off,0), (buf+(length*2)+off/2,h) , (buf+length-off/2,h)],
                              outline=1, fill=0)
            self.draw.text((buf+length+5, 0), 'ADD',  font=self.font, fill=1)
        
            self.draw.polygon([(buf+(length*2-off),0), (buf+length*3-off,0), (buf+length*3-off-off/2,h) , (buf+length*2-off/2,h)],
                              outline=0, fill=1)
            self.draw.text((buf+length*2+5, 0), 'DEL',  font=self.font, fill=0)

        elif(self.mode == 'TIME'):
            self.draw.polygon([(buf,0), (self.width-buf,0), (self.width-buf-off/2,h) , (buf+off/2,h)],
                              outline=1, fill=0)
            self.draw.text((self.width/2-25, 0), "%s" % nowt(),  font=self.font, fill=1)
        else:
            self.draw.polygon([(buf,0), (self.width-buf,0), (self.width-buf-off/2,h) , (buf+off/2,h)],
                              outline=0, fill=1)
            self.draw.text((self.width/2-25, 0), 'VIEWHIVE',  font=self.font, fill=0)

##
##
##schedule_cur = Schedule("HVScriptUTIL.wpi")
##schedule_cur.showContent()
##schedule_cur.WpiToEvents()
##schedule_cur.EventsToWpi()
##
##while True:
##    schedule_cur.addEvent()
##    schedule_cur.EventsToWpi()
##    schedule_cur.clearAllEvents()
##    schedule_cur.addEvent()
##    schedule_cur.showContent()
