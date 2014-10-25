import os, sys, configparser, logging,  psutil,  subprocess,  time,  threading,  logging.handlers
from http.server import BaseHTTPRequestHandler,HTTPServer
from daemon import daemon
#Load a config file
config = configparser.ConfigParser();
if os.path.isfile('/etc/autosuspend.conf'):
    config.read('/etc/autosuspend.conf')
elif os.path.isfile('autosuspend.conf'):
    config.read('autosuspend.conf')
else:
    print('Failed to read configuration file')
    sys.exit(2)

#Logging
debug = config['autosuspend'].getboolean('debug')
logfile = config['autosuspend']['logfile']
logger = logging.getLogger()
if debug:
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.INFO)
filehandler = logging.handlers.TimedRotatingFileHandler(logfile, when='midnight', interval=1,backupCount=10)
filehandler.setFormatter(logging.Formatter(fmt='%(asctime)s %(levelname)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
logger.addHandler(filehandler)

#Class for the daemon
class autosuspend(daemon):
        def run(self):
            daemon_thread = threading.Thread(target=checkservices)
            daemon_thread.start()
            logger.debug("daemon_thread started")
    
#Webserver
class httphandler(BaseHTTPRequestHandler):
    def do_GET(self):
        webpass = config['autosuspend']['webpass']
        logger.debug("http path: "+self.path[1:])
        if self.path[1:] == webpass:
            self.send_response(200)
            self.send_header('Content-type','text/html')
            self.end_headers()
            logger.debug("webserver auth successful")
            execute_suspend("webserver")
            self.wfile.write(bytes("suspending", "utf-8"))
        else:
            self.send_response(401)
            self.send_header('Content-type','text/html')
            self.end_headers()
            logger.debug("webserver auth failed")
            self.wfile.write(bytes("Unauthorized access", "utf-8"))
        return

def webserver():
        webport = int(config['autosuspend']['webport'])
        server = HTTPServer(('', int(webport)), httphandler)
        logger.debug ('Started httpserver')
        server.serve_forever()

#Ping Hosts
def ping():
    global ping
    pingcfg = config['autosuspend'].getboolean('ping')
    if pingcfg:
        pinghosts = config['autosuspend']['pinghosts'].split(',')
        for host in range(len(pinghosts)):
            pingcmd = "ping -q -c 1 " + pinghosts[host] + " &> /dev/null"
            if os.system(pingcmd) == 0:
                logging.debug ("host "+pinghosts[host]+" appears to be up")
                return True
    return False

#Check SSH-Connections
def ssh():
    global ssh
    users=list(psutil.users())
    for user in range(len(users)):
        userdetails = list(users[user])
        logger.debug (userdetails)
        sshusers = config['autosuspend']['sshusers'].split(',')
        sshhosts = config['autosuspend']['sshhosts'].split(',')
        for name in range(len(sshusers)):
            if userdetails[0] == sshusers[name]:
                logger.debug (userdetails[0]+" "+sshusers[name])
                return True
        for host in range(len(sshhosts)):
            if userdetails[2].startswith(sshhosts[host]):
                logger.debug (userdetails[2]+" "+sshhosts[host])
                return True
    return False
        
#Check SAMBA Connections
def smb():
    smbcommand = "ssh central sudo smbstatus -b"
    smboutput = subprocess.getoutput(smbcommand+"| sed '/^$/d'")
    logger.debug("smboutput:\n"+smboutput)
    smboutput_split = smboutput.splitlines()
    smboutput_startline = -1
    logger.debug(len(smboutput_split))
    for line in range(len(smboutput_split)):
        if smboutput_split[line].startswith("----"):
            smboutput_startline = line+1
            
    if smboutput_startline == -1:
        logger.debug(smboutput)
        logger.info('Execution of smbstatus failed or generated unexpected output.\n')
        sys.exit(2)
        return False
    elif smboutput_startline < len(smboutput_split):
        logger.debug(smboutput_startline)
        logger.debug("smb connection detected")
    logger.debug(smboutput_startline)
    return False
    
#Check NFS connections
def nfs():
    nfscommand = "ssh central showmount --no-headers -a"
    nfsoutput = subprocess.getoutput(nfscommand+"| sed '/^$/d'")
    logger.debug("showmount:\n"+nfsoutput)
    nfsoutput_split = nfsoutput.splitlines()
    if len(nfsoutput_split) > 0:
        return True
    return False

#Check running processes
def process():
    processes = config['autosuspend']['processes'].split(',')
    for proc in psutil.process_iter():
        try:
            pinfo = proc.name()
        except psutil.NoSuchProcess:
            pass
        else:
            for name in range(len(processes)):
                if pinfo == processes[name]:
                    logger.debug (pinfo+" "+processes[name])
                    return True
    return False

#Check system load
def load():
    global load
    loadthreshold = float(config['autosuspend']['loadthreshold'])
    loadcurrent = os.getloadavg()[1]
    logger.debug("Load: "+str(loadcurrent))
    if loadcurrent > loadthreshold:
        return True
    return False

#Execute suspend
def execute_suspend(type):
        logger.info  ("Shutting down, cause: " + type)
        suspend_cmd = str(config['autosuspend']['suspend_cmd'])
        logger.debug(suspend_cmd)
        try:
            os.system(suspend_cmd)
        except:
            logger.info("Executing "+suspend_cmd+" failed")

#Check all services and conditions
def checkservices():
        while True:
            condition =""
            if ping():
                condition += "ping, "
                logger.debug(condition)
            if ssh():
                condition += "ssh, "
                logger.debug(condition)
            if smb():
                condition += "smb, "
                logger.debug(condition)
            if nfs():
                condition += "nfs, "
                logger.debug(condition)
            if process():
                condition += "process, "
                logger.debug(condition)
            if load():
                condition += "load"
                logger.debug(condition)
            
            if not condition == "":
                logger.debug(condition+" matched, NOT suspending")
            else:
                logger.debug("No condition matched suspending")
                execute_suspend(condition)
            time.sleep(int(config['autosuspend']['interval']))

if __name__ == "__main__":
        daemon = autosuspend('/tmp/autosuspend.pid')
        if len(sys.argv) == 2:
                if 'start' == sys.argv[1]:
                    logger.info  ("Starting Daemon")
                    daemon.start()
                    webserver()
                elif 'stop' == sys.argv[1]:
                    daemon.stop()
                    logger.info  ("Stopping Daemon")
                elif 'restart' == sys.argv[1]:
                    daemon.restart()
                    webserver()
                else:
                    print ("Unknown Parameter: " + sys.argv[1])
                    sys.exit(2)
                sys.exit(0)
        else:
                print("usage: %s start|stop|restart" % sys.argv[0])
                sys.exit(2)
