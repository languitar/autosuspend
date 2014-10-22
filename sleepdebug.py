import os, sys, configparser, logging,  psutil
config = configparser.ConfigParser();
config.read('sleepd.conf')
debug = config['Basic'].getboolean('debug')
global suspend 
global hostsup
global ssh
hostsup = False
suspend = False
ssh = False
if debug: 
    logging.basicConfig(stream=sys.stderr,  level=logging.DEBUG)

def ping():
    ping = config['Basic'].getboolean('ping')
    if ping:
        pinghosts = config['Basic']['pinghosts'].split(',')
        for host in range(len(pinghosts)):
            pingcmd = "ping -q -c 1 " + pinghosts[host] + " &> /dev/null"
            if os.system(pingcmd) == 0:
                logging.debug ("host "+pinghosts[host]+" appears to be up")
                hostsup = True
            logging.debug  (hostsup)

           

def ssh():
    users=list(psutil.users())
    for user in range(len(users)):
        userdetails = list(users[user])
        logging.debug (userdetails)
        global ssh
        sshusers = config['Basic']['sshusers'].split(',')
        sshhosts = config['Basic']['sshhosts'].split(',')
        sshvt = config['Basic']['sshvt'].split(',')
        for name in range(len(sshusers)):
            if userdetails[0] == sshusers[name]:
                logging.debug (userdetails[0]+" "+sshusers[name])
                ssh = True
        for vt in range(len(sshvt)):
            if userdetails[1].startswith(sshvt[vt]):
                logging.debug (userdetails[1]+" "+sshvt[vt])
                ssh = True
        for host in range(len(sshhosts)):
            if userdetails[2].startswith(sshhosts[host]):
                logging.debug (userdetails[2]+" "+sshhosts[host])
                ssh = True
        logging.debug (ssh)
        
ping()
ssh()
if suspend:
    logging.debug  ("Suspending")
else:
    logging.debug  ("NOT Suspending")
