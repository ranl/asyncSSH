#!/usr/bin/env python

'''
This Module is intended to execute a single script / command
from a local server to a remote one via SSH in a Async fashion

ssh client should be installed on the system
Linux Support only
Only key authentication is supported 
'''

# Python Libs
import os
import subprocess
import tempfile
import shutil
import time
from optparse import OptionParser

def prepareOpts():
    '''
    Parse option from the shell
    '''
    
    def err( string ):
        print 'Error: {0}'.format( string )
        parser.print_help()
        print __doc__
        exit(1)
    
    parser = OptionParser()
    parser.add_option('-t', '--target', dest='target', type='string', help='remote host ip / fqdn')
    parser.add_option('-k', '--key', dest='key', type='string', help='ssh private key')
    parser.add_option('-p', '--port', dest='port', type='int', help='ssh port', default=22)
    parser.add_option('-u', '--user', dest='user', type='string', help='ssh username', default='root')
    parser.add_option('-i', '--interval', dest='interval', type='int', help='how many times we should wait for the script to end', default=5)
    parser.add_option('-s', '--sleep', dest='sleep', type='int', help='how many seconds to wait in each interval', default=60)
    (opts, args) = parser.parse_args()
    
    if not args:
        err('missing command to execute !')
    command = args.pop(0)
    
    return (opts, command, args)

class asyncSSH():
    
    def __init__(self, host, keyfile, port=22, user='root'):
        self.keyfile = keyfile
        self.host = host
        self.port = port
        self.user = user
        self._init_ssh_args()
        
    def _init_ssh_args(self):
        self.ssh_opt = '-o ControlPath=none'
        self.ssh_opt += ' -o PasswordAuthentication=no'
        self.ssh_opt += ' -o ChallengeResponseAuthentication=no'
        self.ssh_opt += ' -o PubkeyAuthentication=yes'
        self.ssh_opt += ' -o KbdInteractiveAuthentication=no'
        self.ssh_opt += ' -o ConnectTimeout=5'
        self.ssh_opt += ' -o StrictHostKeyChecking=no' 
        
        self.ssh_arg = '-p {0} -l {1} -i "{2}" {3} -n'.format(self.port, self.user, self.keyfile, self.ssh_opt)
        self.scp_arg = '-P {0} -i "{1}" {2}'.format(self.port, self.keyfile, self.ssh_opt)
    
    def _shell(self, cmd):
        '''
        will execute the cmd in a Shell and will return the hash res
        res['out'] -> array of the stdout (bylines)
        res['err'] -> same as above only stderr
        res['exit'] -> the exit code of the command
        '''
        
        res = {}
        proc = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=None
        )
        tmp = proc.communicate()
        res['out'] = tmp[0].splitlines()
        res['err'] = tmp[1].splitlines()
        res['exit'] = proc.returncode
        
        return res
    
    def _scp(self, source, destination):
        '''
        Send ssh command
        '''
        
        command = 'scp {0} {1} {2}@{3}:{4}'.format(
            self.scp_arg,
            source,
            self.user,
            self.host,
            destination,
        )
        return self._shell(command)
    
    def _ssh(self, cmd):
        '''
        Send ssh command
        '''
        
        command = 'ssh {0} {1} \'{2}\''.format(
            self.ssh_arg,
            self.host,
            cmd,
        )
        return self._shell(command)
    
    def _sshPing(self):
        return self._ssh('hostname')['exit'] == 0
    
    def _sshProcPing(self, pid):
        return self._ssh('ps -p {0}'.format(pid))['exit'] == 0
    
    def _normalizeString(self, string):
        if not string.startswith('"'):
            string = '"' + string
        if not string.endswith('"'):
            string = string + '"'
        return string
    
    def _generateRemoteScript(self, script, args, lock):
        normArgs = ''
        for string in args:
            normArgs += ' ' + self._normalizeString(string)
        fh = tempfile.NamedTemporaryFile()
        filename = os.path.abspath(fh.name)
        
        fh.write('#!/bin/bash\n')
        fh.write('touch "{0}"\n'.format(lock))
        fh.write('{0} {1}\n'.format(script, normArgs))
        fh.write('if [ $? == 0 ] ; then\n')
        fh.write('  rm -f "{0}"\n'.format(lock))
        fh.write('fi\n')
        fh.write('\n')
        fh.flush()
        
        scpRet = self._scp(filename, filename)
        if scpRet['exit'] != 0:
            raise Exception( 'Error scping {0}\n{1}'.format(filename,scpRet) )
        self._ssh('chmod +x "{0}"'.format(filename))
        
        return filename
    
    def _waitForPid(self, pid, lock, sleepBetweenCheck, numOfChecks):
        ret = {
               'result': True,
               'msg': ''
               }
        counter=numOfChecks
        time.sleep(1)
        scriptRunning=self._sshProcPing(pid)
        while counter > 0 and scriptRunning:
             counter += -1
             time.sleep(sleepBetweenCheck)
             if not self._sshPing():
                 print 'error sshing into {0}, waiting another {1} seconds'.format(self.host, sleepBetweenCheck)
                 continue
             
             if self._sshProcPing(pid):
                 print 'remote script is still running with pid={0}'.format(pid)
             else:
                 print 'remote script ended, pid no longer exists'
                 scriptRunning=False
        
        if not scriptRunning:
            if self._ssh('[ -f "{0}" ]'.format(lock))['exit'] == 0:
                ret['msg'] = 'ERROR: the remote script ended with an error !'
                ret['result'] = False
        else:
            ret['msg'] = 'ERROR: the remote script didn\'t finish after {0} seconds'.format(numOfChecks*sleepBetweenCheck)
            ret['result'] = False
        
        ret['msg'] = 'the remote script finished successfully !'
        return ret
    
    def sendCommand(self, script, args=[], sleepBetweenCheck=60, numOfChecks=5, log=''):
        lock = '/tmp/{0}.lock'.format(os.path.basename(script))
        remoteScript = self._generateRemoteScript(script, args, lock)
        if not log:
            log = '/tmp/{0}.log'.format(os.path.basename(remoteScript))
        
        compiledCommand = 'nohup "{0}" < /dev/null &> {1} & echo $!'.format(
                                                                          remoteScript,
                                                                          log,
                                                                          )
        print 'Send command {0} with args {1} to {2} via {3}'.format(
                                                                     script,
                                                                     args,
                                                                     self.host,
                                                                     remoteScript
                                                                     )
        pid = int(self._ssh(compiledCommand)['out'][0])
        watcherResult = self._waitForPid(pid, lock, sleepBetweenCheck, numOfChecks)
        
        print watcherResult['msg'] 
        print 'check out the log file {0} for debugging'.format(log)
        if watcherResult['result']:
            self._ssh('rm -f "{0}"'.format(remoteScript))
        return watcherResult['result']
    
    @staticmethod
    def main():
        '''
        Main function
        '''
        
        (opts, command, args) = prepareOpts()
        assh = asyncSSH(opts.target, opts.key, opts.port, opts.user)
        ret = assh.sendCommand(command, args, opts.sleep, opts.interval)
        if not ret:
            exit(1)
        exit(0)
        
if __name__ == '__main__':
    asyncSSH.main()
